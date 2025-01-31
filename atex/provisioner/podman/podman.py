import tempfile
import threading
import subprocess

from ... import connection, util
from .. import Provisioner, Remote


class PodmanRemote(Remote, connection.podman.PodmanConnection):
    """
    Built on the official Remote API, pulling in the Connection API
    as implemented by ManagedSSHConnection.
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
    def __init__(self, image, run_options=None):
        """
        'image' is a string of image tag/id to create containers from.
        It can be a local identifier or an URL.

        'run_options' is an iterable with additional CLI options passed
        to 'podman container run'.
        """
        self.lock = threading.RLock()
        self.image = image
        self.run_options = run_options or ()

        # created PodmanRemote instances, ready to be handed over to the user,
        # or already in use by the user
        self.remotes = []
        self.to_create = 0

    def start(self):
        if not self.image:
            raise ValueError("image cannot be empty")

    def stop(self):
        with self.lock:
            while self.remotes:
                self.remotes.pop().release()

    def provision(self, count=1):
        with self.lock:
            self.to_create += count

    def get_remote(self, block=True):
        if self.to_create <= 0:
            if block:
                raise RuntimeError("no .provision() requested, would block forever")
            else:
                return None

        proc = util.subprocess_run(
            (
                "podman", "container", "run", "--quiet", "--detach", "--pull", "never",
                *self.run_options, self.image, "sleep", "inf",
            ),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        container_id = proc.stdout.rstrip("\n")

        def release_hook(remote):
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

        with self.lock:
            self.remotes.append(remote)
            self.to_create -= 1

        return remote

    # not /technically/ a valid repr(), but meh
    def __repr__(self):
        class_name = self.__class__.__name__
        return (
            f"{class_name}({self.image}, {len(self.remotes)} remotes, {hex(id(self))})"
        )


def pull_image(origin):
    proc = util.subprocess_run(
        ("podman", "image", "pull", "-q", origin),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return proc.stdout.rstrip("\n")


def build_container_with_deps(origin, tag=None, *, extra_pkgs=None):
    tag_args = ("-t", tag) if tag else ()

    pkgs = ["rsync"]
    if extra_pkgs:
        pkgs += extra_pkgs
    pkgs_str = " ".join(pkgs)

    with tempfile.NamedTemporaryFile("w+t", delete_on_close=False) as tmpf:
        tmpf.write(util.dedent(fr"""
            FROM {origin}
            RUN dnf -y -q --setopt=install_weak_deps=False install {pkgs_str} >/dev/null
            RUN dnf -y -q clean packages >/dev/null
        """))
        tmpf.close()
        proc = util.subprocess_run(
            ("podman", "image", "build", "-q", "-f", tmpf.name, *tag_args, "."),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        return proc.stdout.rstrip("\n")
