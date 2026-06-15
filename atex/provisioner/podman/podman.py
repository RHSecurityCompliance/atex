import subprocess
import threading

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
        with self._lock:
            if self._release_called:
                return
            else:
                self._release_called = True
        self.disconnect()
        self.release_hook(self)
        subprocess.run(
            ("podman", "container", "rm", "-f", "-t", "0", self.container),
            check=False,  # ignore if it fails
            stdout=subprocess.DEVNULL,
        )

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


class PodmanProvisioner(Provisioner):
    """
    - `image` is a string of image tag/ID to create containers from.
      It can be a local identifier or a URL.

    - `max_remotes` is how many containers can exist at any one time.

    - `run_options` is an iterable with additional CLI options passed
      to `podman container run`.

    - `run_command` is an iterable (cmd + args) specifying the command
      to execute as the "init system" in the container.
    """

    def __init__(
        self, image, *,
        max_remotes=10, run_options=None, run_command=("sleep", "inf"),
    ):
        self._lock = threading.Condition()
        self.logger = _get_logger()

        self.image = image
        self.max_remotes = max_remotes
        self.run_options = run_options or ()
        self.run_command = run_command

        self._remotes = set()
        self._to_reserve = 0
        self._reserving = 0
        self._stopped = True

    def start(self):
        self.logger.debug(f"starting: {self}")
        self._stopped = False

    def stop(self):
        self.logger.debug(f"stopping: {self}")
        with self._lock:
            self._stopped = True
            self._to_reserve = 0
            # wait for currently-reserving get_remote() to finish and
            # self-release based on self._stopped == True
            self._lock.notify_all()
            self._lock.wait_for(lambda: self._reserving == 0)
            to_release = self._remotes
            self._remotes = set()
        for remote in to_release:
            remote.release()

    def provision(self, count=1):
        with self._lock:
            if self._stopped:
                raise ProvisionerError("the provisioner is stopped")
            self.logger.debug(f"provisioning {count}")
            self._to_reserve += count
            self._lock.notify(count)

    def _has_capacity(self):
        return len(self._remotes) + self._reserving < self.max_remotes

    def _make_remote(self, container_id, release_hook):
        return PodmanRemote(
            self.image,
            release_hook=release_hook,
            container=container_id,
        )

    def get_remote(self, block=True):
        with self._lock:
            if block:
                self._lock.wait_for(
                    lambda: (self._to_reserve > 0 and self._has_capacity()) or self._stopped,
                )
                if self._stopped:
                    raise ProvisionerError("the provisioner is stopped")
            elif self._to_reserve <= 0 or not self._has_capacity():
                return None
            self._to_reserve -= 1
            self._reserving += 1

        remote = None
        try:
            cmd = (
                "podman", "container", "run", "--quiet", "--detach", "--pull", "never",
                *self.run_options, self.image, *self.run_command,
            )

            proc = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE)
            container_id = proc.stdout.rstrip("\n")
            self.logger.debug(f"new container: {cmd} --> {container_id}")

            def release_hook(remote):
                self.logger.debug(f"releasing {remote}")
                # remove from the list of remotes inside this Provisioner
                with self._lock:
                    self._remotes.discard(remote)
                    self._lock.notify()

            remote = self._make_remote(container_id, release_hook)
            remote.connect()
        except BaseException:
            if remote:
                remote.release()
            with self._lock:
                self._reserving -= 1
                self._lock.notify()
            raise

        with self._lock:
            self._reserving -= 1
            # if .stop() was called while podman was starting up
            if self._stopped:
                remote.release()
                return None
            self._remotes.add(remote)

        return remote

    def clear(self):
        with self._lock:
            self._to_reserve = 0

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({self.image}, {len(self._remotes)} remotes)"
