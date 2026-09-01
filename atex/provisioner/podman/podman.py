import collections
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from ... import connection, util
from .. import Provisioner, ProvisionerError, Remote

_get_logger = util.get_loggers("atex.provisioner.podman")


class PodmanRemote(Remote, connection.podman.PodmanConnection):
    """
    - `image` is an image tag (used for `str(self)`).

    - `container` is a podman container ID / name.

    - `release_hook` is a callable called on `.release()` in addition
      to disconnecting the connection.

    - `kwargs` are passed to the underlying PodmanConnection.
    """

    def __init__(self, image, *, release_hook, **kwargs):
        super().__init__(**kwargs)
        self._lock = threading.RLock()
        self.image = image
        self._release_called = False
        self.release_hook = release_hook

    def release(self):
        # do everything under the lock - the storage for the container backing
        # this Remote must not be removed/umounted prior to the 'rm' below
        with self._lock:
            if self._release_called:
                return
            else:
                self._release_called = True

            try:
                self.disconnect()
            finally:
                # needs to be called before release_hook() removes it from remotes,
                # as .stop() collects remotes to a list when holding just the
                # provisioner-wide lock, not our self._lock
                subprocess.run(
                    (*self.podman_command, "container", "rm", "-f", "-t", "0", self.container),
                    check=False,  # ignore if it fails
                    stdout=subprocess.DEVNULL,
                )
                self.release_hook(self)

    def __str__(self):
        class_name = self.__class__.__name__

        if "/" in self.image:
            image = self.image.rsplit("/",1)[1]
        elif len(self.image) > 20:
            image = f"{self.image[:17]}..."
        else:
            image = self.image

        name = f"{self.container[:17]}..." if len(self.container) > 20 else self.container

        return f"{class_name}({image}, {name})"


class _PodmanIsolation:
    def __init__(self, podman_command):
        self.tmp_dir = None

        defaults_query = (
            '{"graphroot":{{json .Store.GraphRoot}},"driver":{{json .Store.GraphDriverName}}}'
        )
        defaults_reply = subprocess.run(
            (*podman_command, "info", "--format", defaults_query),
            stdout=subprocess.PIPE, text=True, check=True,
        )
        defaults = json.loads(defaults_reply.stdout)

        graphroot_parent = Path(defaults["graphroot"]).parent
        self.tmp_dir = tempfile.TemporaryDirectory(
            dir=graphroot_parent, prefix="atex-isolated-", delete=False,
            ignore_cleanup_errors=True,  # conmon vs tiny tmpdir files races
        )

        try:
            module_conf = '[engine]\nlock_type = "file"\n'
            (Path(self.tmp_dir.name) / "module.conf").write_text(module_conf)

            base_dir = Path(self.tmp_dir.name)
            self.podman_cmd_with_opts = (
                *podman_command,
                "--root", base_dir / "storage",
                "--runroot", base_dir / "run",
                "--tmpdir", base_dir / "tmp",
                "--storage-driver", defaults["driver"],
                "--module", base_dir / "module.conf",
                "--storage-opt", f".imagestore={defaults['graphroot']}",
            )
        except BaseException:
            self.cleanup()
            raise

    @staticmethod
    def _mounts_under(prefix):
        prefix = os.path.realpath(prefix)
        mounts = []
        with open("/proc/self/mountinfo") as f:
            for line in f:
                mount_point = (
                    line.split()[4]
                    # kernel escapes these four as octal
                    .replace("\\040", " ")
                    .replace("\\011", "\t")
                    .replace("\\012", "\n")
                    .replace("\\134", "\\")
                )
                if mount_point == prefix or mount_point.startswith(prefix + "/"):
                    mounts.append(mount_point)
        # umounting needs to happen deepest-first
        mounts.sort(key=len, reverse=True)
        return mounts

    def cleanup(self):
        if self.tmp_dir:
            if mounts := tuple(self._mounts_under(self.tmp_dir.name)):
                subprocess.run(
                    ("umount", "-l", *mounts),
                    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                )
            self.tmp_dir.cleanup()


class PodmanProvisioner(Provisioner):
    """
    - `image` is a string of image tag/ID to create containers from.
      It can be a local identifier or a URL.

    - `isolate` (if True) means to decouple podman storage-related operations
      from the default image storage, eliminating podman race conditions and
      allowing multiple provisioner instances to operate in parallel.

      Note that the default image storage is inherited as read-only, so you can
      freely pass pre-existing image names/IDs as `image`.

    - `max_remotes` is how many containers can exist at any one time.

    - `run_options` is an iterable with additional CLI options passed
      to `podman container run`.

    - `run_command` is an iterable (cmd + args) specifying the command
      to execute as the "init system" in the container.
    """

    # both get propagated to PodmanRemote / PodmanConnection
    podman_command = ("podman",)
    crun_command = ("crun",)

    def __init__(
        self, image, *,
        max_remotes=10, isolate=False, run_options=None, run_command=("sleep", "inf"),
    ):
        self._lock = threading.Condition()
        self.logger = _get_logger()

        self.image = image
        self.isolate = isolate
        self.max_remotes = max_remotes
        self.run_options = run_options or ()
        self.run_command = run_command

        self._remotes = set()
        self._to_reserve = 0
        self._reserving = 0
        self._stopped = threading.Event()
        self._stopped.set()
        self._connecting_queue = collections.deque()
        self._ready_queue = collections.deque()
        self._worker_thread = None
        self._isolation_handler = None
        self._podman = None

    def start(self):
        self.logger.debug(f"starting: {self}")
        with self._lock:
            if not self._stopped.is_set():
                raise ProvisionerError("the provisioner is already started")

            self._podman = self.podman_command
            if self.isolate:
                self._isolation_handler = _PodmanIsolation(self._podman)
                self._podman = self._isolation_handler.podman_cmd_with_opts

            self._stopped.clear()
            self._ready_queue.clear()
            self._worker_thread = threading.Thread(target=self._worker)
            self._worker_thread.start()

    def stop(self):
        self.logger.debug(f"stopping: {self}")
        with self._lock:
            self._stopped.set()
            self._to_reserve = 0
            worker_thread = self._worker_thread
            self._worker_thread = None
            self._lock.notify_all()

        if worker_thread:
            worker_thread.join()

        with self._lock:
            self._reserving = 0
            to_release = set(self._remotes)
            to_release.update(self._connecting_queue)
            self._remotes = set()
            self._connecting_queue.clear()
            self._ready_queue.clear()
            isolation_handler = self._isolation_handler
            self._isolation_handler = None
            self._podman = None

        for remote in to_release:
            try:
                remote.release()
            except Exception:
                self.logger.warning(f"failed to release {remote}", exc_info=True)

        if isolation_handler:
            isolation_handler.cleanup()  # after all containers are killed

    def provision(self, count=1):
        with self._lock:
            if self._stopped.is_set():
                raise ProvisionerError("the provisioner is stopped")
            self.logger.debug(f"provisioning {count}")
            self._to_reserve += count
            self._lock.notify_all()

    def _has_capacity(self):
        return len(self._remotes) + self._reserving < self.max_remotes

    def _make_remote(self, container_id, release_hook):
        return PodmanRemote(
            self.image,
            release_hook=release_hook,
            container=container_id,
        )

    def _worker(self):
        while True:
            # phase 1:
            # poll all remotes waiting for connection, moving successfully
            # connected ones to the output queue

            for remote in tuple(self._connecting_queue):
                if self._stopped.is_set():
                    return

                try:
                    remote.connect(block=False)
                # regular "not connected yet"
                except BlockingIOError:
                    continue
                # any unexpected exception - add a failure to the queue
                except BaseException as e:
                    try:
                        remote.release()
                    except Exception:
                        self.logger.warning(f"failed to release {remote}", exc_info=True)
                    with self._lock:
                        self._reserving -= 1
                        self._connecting_queue.remove(remote)
                        self._ready_queue.append(util.ThreadResult(exception=e))
                        self._lock.notify_all()
                    continue

                # success - add the remote to the queue
                with self._lock:
                    self._reserving -= 1
                    self._connecting_queue.remove(remote)
                    self._remotes.add(remote)
                    self._ready_queue.append(util.ThreadResult(value=remote))
                    self._lock.notify_all()

            if self._stopped.is_set():
                return

            # phase 2: create a new container if there is pending work

            with self._lock:
                if self._to_reserve > 0 and self._has_capacity():
                    self._to_reserve -= 1
                    self._reserving += 1
                    will_create = True
                else:
                    will_create = False

            if self._stopped.is_set():
                return

            if will_create:
                container_id = None
                remote = None

                try:
                    cmd = (
                        *self._podman,
                        "container", "run", "--quiet", "--detach", "--pull", "never",
                        *self.run_options, self.image, *self.run_command,
                    )
                    proc = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE)
                    container_id = proc.stdout.rstrip("\n")
                    self.logger.debug(f"new container: {cmd} --> {container_id}")

                    def release_hook(remote):
                        self.logger.debug(f"releasing {remote}")
                        with self._lock:
                            self._remotes.discard(remote)
                            self._lock.notify_all()

                    remote = self._make_remote(container_id, release_hook)
                    remote.podman_command = self._podman
                    remote.crun_command = self.crun_command
                    with self._lock:
                        self._connecting_queue.append(remote)

                except BaseException as e:
                    with self._lock:
                        self._reserving -= 1
                        self._ready_queue.append(util.ThreadResult(exception=e))
                        self._lock.notify_all()
                    if remote:
                        try:
                            remote.release()
                        except Exception:
                            self.logger.warning(f"failed to release {remote}", exc_info=True)
                    elif container_id:
                        subprocess.run(
                            (*self._podman, "container", "rm", "-f", "-t", "0", container_id),
                            check=False,
                            stdout=subprocess.DEVNULL,
                        )

                # try connecting to the newly created Remote (also all others)
                continue

            # phase 3: sleep

            # if there are remotes still waiting on connect, and we haven't
            # created a new container, add a small sleep to avoid a rapid retry
            with self._lock:
                connecting = len(self._connecting_queue)
            if connecting > 0:
                self._stopped.wait(timeout=0.1)
                continue

            # phase 4: wait for work to become available

            with self._lock:
                self._lock.wait_for(
                    lambda: (self._to_reserve > 0 and self._has_capacity())
                    or self._stopped.is_set(),
                )

    def get_remote(self, block=True):
        with self._lock:
            if block:
                self._lock.wait_for(lambda: len(self._ready_queue) > 0 or self._stopped.is_set())

            if self._stopped.is_set():
                raise ProvisionerError("the provisioner is stopped")

            try:
                item = self._ready_queue.popleft()
            except IndexError:
                return None  # only non-blocking

        return item.result()

    def clear(self):
        with self._lock:
            self._to_reserve = 0

    def __str__(self):
        class_name = self.__class__.__name__
        remotes = f"{len(self._remotes)}/{self.max_remotes}"
        return f"{class_name}({self.image}, {remotes} remotes)"
