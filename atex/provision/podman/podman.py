import os
import time
import enum
import threading
import subprocess

from ... import connection, util
from .. import Provisioner, Remote


class PodmanRemote(Remote, connection.podman.PodmanConn):
    """
    Built on the official Remote API, pulling in the Connection API
    as implemented by ManagedSSHConn.
    """

    def __init__(self, image, container, *, release_hook):
        """
        'image' is an image tag (used for repr()).

        'container' is a podman container id / name.

        'release_hook' is a callable called on .release() in addition
        to disconnecting the connection.
        """
        super().__init__(container=container)
        self.lock = threading.RLock()
        self.image = image
        self.container = container
        self.release_called = False
        self.release_hook = release_hook

    def release(self):
        with self.lock:
            if self.release_called:
                return
            else:
                self.release_called = True
        self.release_hook(self)
        self.disconnect()
        util.subprocess_run(
            ("podman", "container", "rm", "-f", "-t", "0", self.container),
            check=False,  # ignore if it fails
            stdout=subprocess.DEVNULL,
        )

    # not /technically/ a valid repr(), but meh
    def __repr__(self):
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
    class State(enum.Enum):
        WAITING_FOR_PULL = enum.auto()
        CREATING_CONTAINER = enum.auto()
        WAITING_FOR_CREATION = enum.auto()
        SETTING_UP_CONTAINER = enum.auto()
        WAITING_FOR_SETUP = enum.auto()

    # NOTE: this uses a single Popen process to run podman commands,
    #       to avoid double downloads/pulls, but also to avoid SQLite errors
    #       when creating multiple containers in parallel

    def __init__(self, image, run_options=None, *, pull=True, max_systems=1):
        """
        'image' is a string of image tag/id to create containers from.
        It can be a local identifier or an URL.

        'run_options' is an iterable with additional CLI options passed
        to 'podman container run'.

        'pull' specifies whether to attempt 'podman image pull' on the specified
        image tag/id before any container creation.

        'max_systems' is a maximum number of containers running at any one time.
        """
        self.lock = threading.RLock()
        self.image = image
        self.run_options = run_options or ()
        self.pull = pull
        self.max_systems = max_systems

        self.image_id = None
        self.container_id = None
        self.worker = None
        self.worker_output = bytearray()
        self.state = None
        # created PodmanRemote instances, ready to be handed over to the user,
        # or already in use by the user
        self.remotes = []

    @staticmethod
    def _spawn_proc(cmd):
        proc = util.subprocess_Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        os.set_blocking(proc.stdout.fileno(), False)
        return proc

#    @staticmethod
#    def _poll_proc(proc):
#        # read from the process to un-block any kernel buffers
#        try:
#            out = proc.stdout.read()  # non-blocking
#        except BlockingIOError:
#            out = ""
#        return (proc.poll(), out)

    def _make_remote(self, container):
        def release_hook(remote):
            # remove from the list of remotes inside this Provisioner
            with self.lock:
                try:
                    self.remotes.remove(remote)
                except ValueError:
                    pass

        remote = PodmanRemote(
            self.image,
            container,
            release_hook=release_hook,
        )
        self.remotes.append(remote)
        return remote

    def start(self):
        if not self.image:
            raise ValueError("image cannot be empty")

        if not self.pull:
            self.image_id = self.image
            self.state = self.State.CREATING_CONTAINER
        else:
            self.worker = self._spawn_proc(
                ("podman", "image", "pull", "--quiet", self.image),
            )
            self.state = self.State.WAITING_FOR_PULL

    def stop(self):
        with self.lock:
            while self.remotes:
                self.remotes.pop().release()
            worker = self.worker
            self.worker = None

        if worker:
            worker.kill()
            # don"t zombie forever, return EPIPE on any attempts to write to us
            worker.stdout.close()
            worker.wait()

    def stop_defer(self):
        # avoid SQLite errors by removing containers sequentially
        return self.stop

    @staticmethod
    def _nonblock_read(fobj):
        """Return b'' if there was nothing to read, instead of None."""
        data = fobj.read()
        return b"" if data is None else data

    def _get_remote_nonblock(self):
        if self.state is None:
            raise RuntimeError("the provisioner is in an invalid state")

        # NOTE: these are not 'elif' statements explicitly to allow a next block
        #       to follow a previous one (if the condition is met)
        if self.state is self.State.WAITING_FOR_PULL:
            self.worker_output += self._nonblock_read(self.worker.stdout)
            rc = self.worker.poll()
            if rc is None:
                return None  # still running
            elif rc != 0:
                out = self.worker_output.decode().rstrip("\n")
                self.worker_output.clear()
                self.worker = None
                self.state = None
                raise RuntimeError(f"podman image pull failed with {rc}:\n{out}")
            else:
                self.image_id = self.worker_output.decode().rstrip("\n")
                self.worker_output.clear()
                self.worker = None
                self.state = self.State.CREATING_CONTAINER

        if self.state is self.State.CREATING_CONTAINER:
            if len(self.remotes) < self.max_systems:
                self.worker = self._spawn_proc(
                    (
                        "podman", "container", "run", "--quiet", "--detach", "--pull", "never",
                        *self.run_options, self.image_id, "sleep", "inf",
                    ),
                )
                self.state = self.State.WAITING_FOR_CREATION
            else:
                # too many remotes requested
                return None

        if self.state is self.State.WAITING_FOR_CREATION:
            self.worker_output += self._nonblock_read(self.worker.stdout)
            rc = self.worker.poll()
            if rc is None:
                return None  # still running
            elif rc != 0:
                out = self.worker_output.decode().rstrip("\n")
                self.worker_output.clear()
                self.worker = None
                self.state = None
                raise RuntimeError(f"podman run failed with {rc}:\n{out}")
            else:
                self.container_id = self.worker_output.decode().rstrip("\n")
                self.worker_output.clear()
                self.worker = None
                self.state = self.State.SETTING_UP_CONTAINER

        if self.state is self.State.SETTING_UP_CONTAINER:
            cmd = ("dnf", "install", "-y", "-q", "--setopt=install_weak_deps=False", "rsync")
            self.worker = self._spawn_proc(
                ("podman", "container", "exec", self.container_id, *cmd),
            )
            self.state = self.State.WAITING_FOR_SETUP

        if self.state is self.State.WAITING_FOR_SETUP:
            self.worker_output += self._nonblock_read(self.worker.stdout)
            rc = self.worker.poll()
            if rc is None:
                return None  # still running
            elif rc != 0:
                out = self.worker_output.decode().rstrip("\n")
                self.worker_output.clear()
                self.worker = None
                self.state = None
                raise RuntimeError(f"setting up failed with {rc}:\n{out}")
            else:
                # everything ready, give the Remote to the caller and reset
                remote = self._make_remote(self.container_id)
                self.worker_output.clear()
                self.worker = None
                self.state = self.State.CREATING_CONTAINER
                return remote

        raise AssertionError(f"reached end (invalid state {self.state}?)")

    def get_remote(self, block=True):
        if not block:
            with self.lock:
                return self._get_remote_nonblock()
        else:
            while True:
                with self.lock:
                    if remote := self._get_remote_nonblock():
                        return remote
                time.sleep(0.1)

    # not /technically/ a valid repr(), but meh
    def __repr__(self):
        class_name = self.__class__.__name__
        return (
            f"{class_name}({self.image}, {len(self.remotes)}/{self.max_systems} remotes, "
            f"{hex(id(self))})"
        )
