#import os
#import subprocess
#import tempfile
#from pathlib import Path
import os
import subprocess

import pytest

from atex.provisioner.podman import PodmanProvisioner, build_container_with_deps, pull_image
from tests.executor.fmf.conftest import setup_timeout, tmp_dir  # noqa: F401
from tests.provisioner.test_podman import IMAGE


@pytest.fixture(scope="module")
def provisioner():
    base_image = os.environ.get("BASE_IMAGE")
    if base_image is None:
        base_image = pull_image(IMAGE)

    custom_image = build_container_with_deps(
        base_image,
        extra_pkgs=("beakerlib", "git-core", "epel-release"),
        extra_content=(
            # epel-release above enables EPEL, so now we can install beakerlib
            "RUN rpm --quiet -q beakerlib || if command -v dnf >/dev/null; then "
            "dnf -y -q --setopt=install_weak_deps=False install beakerlib; "
            "else yum -y -q install beakerlib; fi"
        ),
    )

    try:
        with PodmanProvisioner(custom_image) as prov:
            yield prov
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", custom_image),
            check=True,
            stdout=subprocess.DEVNULL,
        )


@pytest.fixture(scope="module")
def provisioner_systemd():
    base_image = os.environ.get("BASE_IMAGE")
    if base_image is None:
        base_image = pull_image(IMAGE)

    custom_image = build_container_with_deps(
        base_image,
        extra_pkgs=("systemd", "beakerlib", "git-core", "epel-release"),
        extra_content=(
            "RUN systemctl mask systemd-oomd systemd-resolved systemd-hostnamed\n"
            # epel-release above enables EPEL, so now we can install beakerlib
            "RUN rpm --quiet -q beakerlib || if command -v dnf >/dev/null; then "
            "dnf -y -q --setopt=install_weak_deps=False install beakerlib; "
            "else yum -y -q install beakerlib; fi"
        ),
    )

    opts = ("--systemd=always", "--restart=always")
    cmd = ("/sbin/init",)
    try:
        with PodmanProvisioner(custom_image, run_options=opts, run_command=cmd) as prov:
            yield prov
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", custom_image),
            check=True,
            stdout=subprocess.DEVNULL,
        )
