import os
import subprocess

import pytest

from atex.provisioner.podman import (
    PodmanProvisioner,
    SystemdPodmanProvisioner,
    build_container_with_deps,
    build_systemd_container_with_deps,
    pull_image,
)
from tests.executor.fmf.conftest import setup_timeout  # noqa: F401
from tests.provisioner.test_podman import IMAGE


@pytest.fixture(scope="session")
def custom_image():
    base_image = os.environ.get("BASE_IMAGE")
    if base_image is None:
        base_image = pull_image(IMAGE)

    image = build_container_with_deps(
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
        yield image
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", image),
            check=True,
            stdout=subprocess.DEVNULL,
        )


@pytest.fixture
def provisioner(custom_image):
    with PodmanProvisioner(custom_image) as prov:
        yield prov


@pytest.fixture(scope="session")
def custom_image_systemd():
    base_image = os.environ.get("BASE_IMAGE")
    if base_image is None:
        base_image = pull_image(IMAGE)

    image = build_systemd_container_with_deps(
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
        yield image
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", image),
            check=True,
            stdout=subprocess.DEVNULL,
        )


@pytest.fixture
def provisioner_systemd(custom_image_systemd):
    with SystemdPodmanProvisioner(custom_image_systemd) as prov:
        yield prov
