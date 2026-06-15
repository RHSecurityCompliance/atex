import contextlib
import subprocess

from ... import connection
from .podman import PodmanProvisioner, PodmanRemote
from .utils import build_systemd_container_with_deps


class SystemdPodmanRemote(PodmanRemote, connection.podman.SystemdPodmanConnection):
    pass


class SystemdPodmanProvisioner(PodmanProvisioner):

    def __init__(self, image, *, run_options=None, run_command=("/sbin/init",), **kwargs):
        opts = ["--systemd=always", "--restart=always"]
        if run_options:
            opts += run_options
        super().__init__(image, run_options=opts, run_command=run_command, **kwargs)

    @classmethod
    @contextlib.contextmanager
    def build_from(cls, origin, *, extra_pkgs=None, extra_content="", **kwargs):
        """
        Build a systemd-enabled image from `origin` and instantiate + start the
        provisioner class using it.

        The arguments passed to `build_systemd_container_with_deps()`:

        - `origin` is a local image name or ID (ie. from `pull_image()`).

        - `extra_pkgs` are additional packages to install on top of
          the base dependencies and `systemd`.

        - `extra_content` is appended to the Containerfile.

        - `kwargs` are passed to the provisioner constructor.
        """
        built = build_systemd_container_with_deps(
            origin,
            extra_pkgs=extra_pkgs,
            extra_content=extra_content,
        )
        try:
            with cls(built, **kwargs) as instance:
                yield instance
        finally:
            subprocess.run(
                ("podman", "image", "rm", "-f", built),
                check=False,  # ignore if it fails
                stdout=subprocess.DEVNULL,
            )

    def _make_remote(self, container_id, release_hook):
        return SystemdPodmanRemote(
            self.image,
            release_hook=release_hook,
            container=container_id,
        )
