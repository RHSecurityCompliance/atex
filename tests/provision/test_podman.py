import subprocess
import pytest

from atex import util
from atex.provision.podman import PodmanProvisioner

import testutil

from tests.provision import shared

IMAGE = "fedora"


# pull once, to avoid flooding the remote hub with pull requests
@pytest.fixture(scope="module", autouse=True)
def setup_pull():
    util.subprocess_run(
        ("podman", "image", "pull", "--quiet", IMAGE),
        check=True,
        stdout=subprocess.DEVNULL,
    )


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(300):
        yield


# ------------------------------------------------------------------------------


def test_pull():
    with PodmanProvisioner(IMAGE, pull=True):
        pass


def test_one_remote():
    with PodmanProvisioner(IMAGE, pull=False) as p:
        shared.one_remote(p)


def test_one_remote_nonblock():
    with PodmanProvisioner(IMAGE, pull=False) as p:
        shared.one_remote_nonblock(p)


def test_two_remotes():
    with PodmanProvisioner(IMAGE, pull=False, max_systems=2) as p:
        shared.two_remotes(p)


def test_two_remotes_nonblock():
    with PodmanProvisioner(IMAGE, pull=False, max_systems=2) as p:
        shared.two_remotes_nonblock(p)


def test_sharing_remote_slot():
    with PodmanProvisioner(IMAGE, pull=False, max_systems=1) as p:
        shared.sharing_remote_slot(p)


def test_sharing_remote_slot_nonblock():
    with PodmanProvisioner(IMAGE, pull=False, max_systems=1) as p:
        shared.sharing_remote_slot_nonblock(p)


def test_cmd():
    with PodmanProvisioner(IMAGE, pull=False) as p:
        shared.cmd(p)


def test_cmd_input():
    with PodmanProvisioner(IMAGE, pull=False) as p:
        shared.cmd_input(p)


def test_cmd_binary():
    with PodmanProvisioner(IMAGE, pull=False) as p:
        shared.cmd_binary(p)


def test_rsync():
    with PodmanProvisioner(IMAGE, pull=False) as p:
        shared.rsync(p)
