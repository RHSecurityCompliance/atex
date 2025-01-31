import subprocess
import pytest

from atex.provisioner.podman import PodmanProvisioner
from atex.provisioner.podman import pull_image, build_container_with_deps

import testutil

from tests.provisioner import shared

IMAGE = "registry.fedoraproject.org/fedora"


# pull once, to avoid flooding the remote hub with pull requests
@pytest.fixture(scope="module")
def image_id():
    pulled = pull_image(IMAGE)
    custom_image = build_container_with_deps(pulled)
    yield custom_image
    subprocess.run(
        ("podman", "image", "rm", "-f", custom_image),
        check=True,
        stdout=subprocess.DEVNULL,
    )


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(300):
        yield


# ------------------------------------------------------------------------------


def test_one_remote(image_id):
    with PodmanProvisioner(image_id) as p:
        shared.one_remote(p)


#def test_one_remote_nonblock(image_id):
#    with PodmanProvisioner(image_id) as p:
#        shared.one_remote_nonblock(p)


def test_two_remotes(image_id):
    with PodmanProvisioner(image_id) as p:
        shared.two_remotes(p)


#def test_two_remotes_nonblock(image_id):
#    with PodmanProvisioner(image_id) as p:
#        shared.two_remotes_nonblock(p)


#def test_sharing_remote_slot(image_id):
#    with PodmanProvisioner(image_id, max_systems=1) as p:
#        shared.sharing_remote_slot(p)
#
#
#def test_sharing_remote_slot_nonblock(image_id):
#    with PodmanProvisioner(image_id, max_systems=1) as p:
#        shared.sharing_remote_slot_nonblock(p)


def test_cmd(image_id):
    with PodmanProvisioner(image_id) as p:
        shared.cmd(p)


def test_cmd_input(image_id):
    with PodmanProvisioner(image_id) as p:
        shared.cmd_input(p)


def test_cmd_binary(image_id):
    with PodmanProvisioner(image_id) as p:
        shared.cmd_binary(p)


def test_rsync(image_id):
    with PodmanProvisioner(image_id) as p:
        shared.rsync(p)
