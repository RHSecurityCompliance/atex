import subprocess
import tempfile
import time
import uuid

from ... import util


def pull_image(origin):
    """
    Pull podman images from repositories.
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


def wait_for_systemd(conn):
    # wait for the full system to be up
    # (--wait doesn't exist on old RHELs and needs extra waiting
    #  for /run/systemd/private)
    for _ in range(600):
        proc = conn.cmd(
            ("systemctl", "is-system-running"),
            stdout=subprocess.PIPE,
        )
        if b"running" in proc.stdout or b"degraded" in proc.stdout:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("systemctl is-system-running failed")
