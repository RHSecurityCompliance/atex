import subprocess

import pytest
from testutil import SSHPodmanProvisioner, build_ssh_image

from atex.provisioner.podman import (
    PodmanProvisioner,
    SystemdPodmanProvisioner,
    build_container_with_deps,
    build_systemd_container_with_deps,
)


# -----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def custom_image(base_image):
    image = build_container_with_deps(base_image)
    try:
        yield image
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", image),
            check=True,
            stdout=subprocess.DEVNULL,
        )


@pytest.fixture(scope="session")
def custom_image_systemd(base_image):
    image = build_systemd_container_with_deps(base_image)
    try:
        yield image
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", image),
            check=True,
            stdout=subprocess.DEVNULL,
        )


@pytest.fixture(scope="session")
def custom_image_ssh(base_image, ssh_key):
    _, pubkey_path = ssh_key
    pubkey = pubkey_path.read_text().rstrip()
    image = build_ssh_image(base_image, pubkey)
    try:
        yield image
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", image),
            check=False,
            stdout=subprocess.DEVNULL,
        )


# -----------------------------------------------------------------------------
@pytest.fixture
def provisioner(request, backend, base_image):
    # base_image is not used directly, but must be in the signature so pytest
    # can see its parametrization and generate per-image test IDs;
    # the actual image fixtures are resolved lazily so that ie. running just
    # -k podman doesn't trigger building the ssh image (and vice versa)
    assert base_image
    match backend:
        case "podman":
            custom_image = request.getfixturevalue("custom_image")
            with PodmanProvisioner(custom_image) as prov:
                yield prov
        case "ssh":
            custom_image_ssh = request.getfixturevalue("custom_image_ssh")
            privkey, _ = request.getfixturevalue("ssh_key")
            with SSHPodmanProvisioner(custom_image_ssh, privkey) as prov:
                yield prov
        case _:
            raise ValueError(backend)


@pytest.fixture
def provisioner_systemd(request, backend, base_image):
    # see provisioner() above for why base_image is in the signature
    assert base_image
    match backend:
        case "podman":
            custom_image_systemd = request.getfixturevalue("custom_image_systemd")
            with SystemdPodmanProvisioner(custom_image_systemd) as prov:
                yield prov
        case "ssh":
            custom_image_ssh = request.getfixturevalue("custom_image_ssh")
            privkey, _ = request.getfixturevalue("ssh_key")
            with SSHPodmanProvisioner(custom_image_ssh, privkey) as prov:
                yield prov
        case _:
            raise ValueError(backend)
