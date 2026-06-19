import subprocess
import tempfile
import uuid

from ... import util


def pull_image(origin):
    """
    Pull a podman image from a repository.
    """
    proc = subprocess.run(
        ("podman", "image", "pull", "-q", origin),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return proc.stdout.rstrip("\n")


def build_container_with_deps(origin, tag=None, *, extra_pkgs=None, extra_content=""):
    """
    Create a new podman image with dependencies needed for PodmanProvisioner.

    - `origin` is a local image name or ID (ie. from `pull_image()`).

    - `tag` is a name (tag) for the newly created image.

    - `extra_pkgs` are additional packages to install on top of
      the base PodmanProvisioner dependencies.

    - `extra_content` is appended to the Containerfile.
    """
    # podman *requires* tags for images
    # - this is an undocumented quirk; any image without a tag is considered
    # a build artifact or otherwise a dangling image, and filtered internally
    # by buildah / other layers, so a second 'podman build' (using FROM purely
    # by hash, on an untagged image) fails with a cryptic error message
    # ... so just always assign some random tag, because this is really stupid
    if not tag:
        tag = str(uuid.uuid4())

    # python is needed by FMFExecutor,
    # rsync is needed by PodmanConnection
    pkgs = ["python", "rsync"]
    if extra_pkgs:
        pkgs += extra_pkgs
    pkgs_str = " ".join(pkgs)

    with tempfile.NamedTemporaryFile("w+t", delete_on_close=False) as tmpf:
        template = util.dedent(fr"""
            FROM {origin}
            RUN if command -v dnf >/dev/null; then \
                  pkg_tool="dnf -y -q --setopt=install_weak_deps=False"; \
              else \
                  pkg_tool="yum -y -q"; \
              fi; \
              have_dnf5=$(command -v dnf5); \
              skip_bad="--skip-broken${{have_dnf5:+ --skip-unavailable}}"; \
              $pkg_tool install $skip_bad {pkgs_str} >/dev/null; \
              $pkg_tool clean packages >/dev/null
        """) + "\n"
        tmpf.write(template)
        if extra_content:
            tmpf.write(extra_content)
        tmpf.close()
        proc = subprocess.run(
            ("podman", "image", "build", "-q", "-t", tag, "-f", tmpf.name, "."),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        return proc.stdout.rstrip("\n")


def build_systemd_container_with_deps(origin, tag=None, *, extra_pkgs=None, extra_content=""):
    """
    Create a new podman image with dependencies needed for
    SystemdPodmanProvisioner.

    This is a wrapper for `build_container_with_deps()` with pre-filled
    arguments for building systemd-as-init container images.

    - `origin` is a local image name or ID (ie. from `pull_image()`).

    - `tag` is a name (tag) for the newly created image.

    - `extra_pkgs` are additional packages to install on top of
      the base dependencies and `systemd`.

    - `extra_content` is appended to the Containerfile.
    """
    pkgs = ["systemd", "dbus-broker"]
    if extra_pkgs:
        pkgs += extra_pkgs
    # on RHEL-8 (systemd 239), systemd sends out SIGTERM to all processes
    # on reboot, but then waits for SIGCHLD, which does not arrive from
    # non-children ... and since we use 'crun exec' in .cmd(), the exec'd
    # process is never collected by PID 1 (systemd-shutdown), waiting for the
    # 90sec for SIGKILL broadcast - over the 60sec of _wait_for_systemd()
    # in SystemdPodmanConnection, ... so reduce the SIGKILL timer to 30sec
    content = (
        "RUN mkdir -p /etc/systemd/system.conf.d && "
        r"printf '[Manager]\nDefaultTimeoutStopSec=30s\n' > "
        "/etc/systemd/system.conf.d/container.conf"
        "\n"
    )
    # add user-passed content (if any)
    content += extra_content
    return build_container_with_deps(origin, tag=tag, extra_pkgs=pkgs, extra_content=content)
