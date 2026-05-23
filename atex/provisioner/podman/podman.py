import subprocess
import threading

from ... import connection, util
from .. import Provisioner, Remote

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
      It can be a local identifier or an URL.

    - `max_remotes` is how many containers can exist at any one time.

    - `run_options` is an iterable with additional CLI options passed
      to `podman container run`.

    - `run_command` is an iterable (cmd + args) specifying the command
      to execute as the "init system" in the container.
    """

    def __init__(
        self, image, *,
        max_remotes=None, run_options=None, run_command=("sleep", "inf"),
    ):
        self._lock = threading.RLock()
        self.logger = _get_logger()

        self.image = image
        self.max_remotes = max_remotes
        self.run_options = run_options or ()
        self.run_command = run_command

        self._remotes = []
        self._to_reserve = 0
        self._reserving = 0
        self._cond = threading.Condition()
        self._started = False

    def start(self):
        self.logger.debug(f"starting: {self}")
        self._to_reserve = 0
        self._reserving = 0
        self._started = True

        if not self.image:
            raise ValueError("image cannot be empty")

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        with self._cond:
            self._started = False
            self._to_reserve = 0
            self._reserving = 0
            self._cond.notify_all()

        with self._lock:
            while self._remotes:
                self._remotes.pop().release()

    def provision(self, count=1):
        assert count >= 0
        self.logger.debug(f"provisioning {count}")
        with self._cond:
            self._to_reserve += count
            self._cond.notify(count)

    def _has_capacity(self):
        return (
            self.max_remotes is None
            or len(self._remotes) + self._reserving < self.max_remotes
        )

    def get_remote(self, block=True):
        with self._cond:
            if block:
                self._cond.wait_for(
                    lambda: (self._to_reserve > 0 and self._has_capacity())
                    or not self._started,
                )
                if not self._started:
                    return None
            elif self._to_reserve <= 0 or not self._has_capacity():
                return None
            self._to_reserve -= 1
            self._reserving += 1

        try:
            cmd = (
                "podman", "container", "run", "--quiet", "--detach", "--pull", "never",
                *self.run_options, self.image, *self.run_command,
            )

            proc = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE)
            container_id = proc.stdout.rstrip("\n")
            self.logger.debug(f"new container: {cmd} --> {container_id}")
        except BaseException:
            with self._cond:
                self._reserving -= 1
                self._cond.notify()
            raise

        def release_hook(remote):
            self.logger.debug(f"releasing {remote}")
            # remove from the list of remotes inside this Provisioner
            with self._lock:
                try:
                    self._remotes.remove(remote)
                except ValueError:
                    pass
            with self._cond:
                self._cond.notify()

        remote = PodmanRemote(
            self.image,
            release_hook=release_hook,
            container=container_id,
        )

        with self._cond:
            self._reserving -= 1
            self._remotes.append(remote)
        return remote

    def clear(self):
        with self._cond:
            self._to_reserve = 0

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({self.image}, {len(self._remotes)} remotes)"
