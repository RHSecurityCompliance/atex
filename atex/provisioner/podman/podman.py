import subprocess
import threading

from ... import connection, util
from .. import Provisioner, Remote

get_logger = util.get_loggers("atex.provisioner.podman")


class PodmanRemote(Remote, connection.podman.PodmanConnection):
    """
    - `image` is an image tag (used for `str(self)`).

    - `container` is a podman container ID / name.

    - `release_hook` is a callable called on `.release()` in addition
      to disconnecting the connection.
    """

    def __init__(self, image, container, *, release_hook):
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

    - `run_options` is an iterable with additional CLI options passed
      to `podman container run`.

    - `run_command` is an iterable (cmd + args) specifying the command
      to execute as the "init system" in the container.
    """

    def __init__(self, image, *, run_options=None, run_command=("sleep", "inf")):
        self.lock = threading.RLock()
        self.logger = get_logger()

        self.image = image
        self.run_options = run_options or ()
        self.run_command = run_command

        self.remotes = []
        self._requested = 0
        self._cond = threading.Condition()
        self.started = False

    def start(self):
        self.logger.debug(f"starting: {self}")
        self.started = True

        if not self.image:
            raise ValueError("image cannot be empty")

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        with self._cond:
            self.started = False
            self._cond.notify_all()

        with self.lock:
            while self.remotes:
                self.remotes.pop().release()

    def provision(self, count=1):
        assert count >= 0
        self.logger.debug(f"provisioning {count}")
        with self._cond:
            self._requested += count
            self._cond.notify(count)

    def get_remote(self, block=True):
        with self._cond:
            if block:
                self._cond.wait_for(lambda: self._requested > 0 or not self.started)
                if not self.started:
                    return None
            elif self._requested <= 0:
                return None
            self._requested -= 1

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
            with self.lock:
                try:
                    self.remotes.remove(remote)
                except ValueError:
                    pass

        remote = PodmanRemote(
            self.image,
            container_id,
            release_hook=release_hook,
        )

        self.remotes.append(remote)
        return remote

    def clear(self):
        with self._cond:
            self._requested = 0

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({self.image}, {len(self.remotes)} remotes)"
