import subprocess
import tempfile
import time

from ... import util


def pull_image(origin):
    proc = subprocess.run(
        ("podman", "image", "pull", "-q", origin),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return proc.stdout.rstrip("\n")


def build_container_with_deps(origin, tag=None, *, extra_pkgs=None, extra_content=""):
    tag_args = ("-t", tag) if tag else ()

    # python is needed by FMFExecutor,
    # rsync is needed by PodmanConnection
    pkgs = ["python", "rsync"]
    if extra_pkgs:
        pkgs += extra_pkgs
    pkgs_str = " ".join(pkgs)

    with tempfile.NamedTemporaryFile("w+t", delete_on_close=False) as tmpf:
        tmpf.write(util.dedent(fr"""
            FROM {origin}
            RUN dnf -y -q --setopt=install_weak_deps=False install {pkgs_str} >/dev/null
            RUN dnf -y -q clean packages >/dev/null
            {extra_content}
        """))
        tmpf.close()
        proc = subprocess.run(
            ("podman", "image", "build", "-q", "-f", tmpf.name, *tag_args, "."),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        return proc.stdout.rstrip("\n")


def wait_for_systemd(conn):
    # wait for the full system to be up
    # (--wait doesn't exist on old RHELs and needs extra waiting
    #  for /run/systemd/private)
    for _ in range(300):
        proc = conn.cmd(
            ("systemctl", "is-system-running"),
            stdout=subprocess.PIPE,
        )
        if b"running" in proc.stdout or b"degraded" in proc.stdout:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("systemctl is-system-running failed")
