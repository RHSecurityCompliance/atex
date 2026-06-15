import os
import subprocess

import pytest
import testutil

from atex.provisioner.podman import (
    PodmanProvisioner,
    SystemdPodmanProvisioner,
    build_container_with_deps,
    build_systemd_container_with_deps,
    pull_image,
)
from tests.provisioner.test_podman import IMAGE


@pytest.fixture(scope="session")
def custom_image():
    base_image = os.environ.get("BASE_IMAGE")
    if base_image is None:
        base_image = pull_image(IMAGE)
    image = build_container_with_deps(base_image)
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
    image = build_systemd_container_with_deps(base_image)
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


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(300):
        yield
