import subprocess
import tempfile

from ... import util


def pull_image(origin):
    proc = util.subprocess_run(
        ("podman", "image", "pull", "-q", origin),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return proc.stdout.rstrip("\n")


def build_container_with_deps(origin, tag=None, *, extra_pkgs=None, extra_content=""):
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
            {extra_content}
        """))
        tmpf.close()
        proc = util.subprocess_run(
            ("podman", "image", "build", "-q", "-f", tmpf.name, *tag_args, "."),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        return proc.stdout.rstrip("\n")
