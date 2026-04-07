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


class _SettableCounter:
    def __init__(self, value=0):
        self.value = value
        self.cond = threading.Condition()

    def remove_one(self, block=True):
        with self.cond:
            if block:
                self.cond.wait_for(lambda: self.value > 0)
                self.value -= 1
                return True
            else:
                if self.value <= 0:
                    return False
                else:
                    self.value -= 1
                    return True

    def add(self, value):
        assert value >= 0
        with self.cond:
            self.value += value
            self.cond.notify(value)

    def zero(self):
        with self.cond:
            # no need to wake any threads because it's 0
            self.value = 0


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

        # created PodmanRemote instances, ready to be handed over to the user,
        # or already in use by the user
        self.remotes = []
        self.to_create = _SettableCounter(0)

    def start(self):
        self.logger.debug(f"starting: {self}")

        if not self.image:
            raise ValueError("image cannot be empty")

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        with self.lock:
            while self.remotes:
                self.remotes.pop().release()

    def provision(self, count=1):
        self.logger.debug(f"provisioning {count}")
        self.to_create.add(count)

    def get_remote(self, block=True):
        if not self.to_create.remove_one(block=block):
            return None

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
        self.to_create.zero()

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({self.image}, {len(self.remotes)} remotes)"
