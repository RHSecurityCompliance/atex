import os
import pytest

from atex.provision.testingfarm import TestingFarmProvisioner

import testutil

from tests.provision import shared

COMPOSE = None


@pytest.fixture(scope="module", autouse=True)
def setup_check_env():
    # used internally by the API implementation
    if not os.environ.get("TESTING_FARM_API_TOKEN"):
        raise RuntimeError("TESTING_FARM_API_TOKEN not in environment")
    # exported here by us
    global COMPOSE
    COMPOSE = os.environ.get("TESTING_FARM_COMPOSE")
    if not COMPOSE:
        raise RuntimeError("TESTING_FARM_COMPOSE not in environment")


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(1800):
        yield


# ------------------------------------------------------------------------------


def test_pull():
    with TestingFarmProvisioner(COMPOSE):
        pass


def test_one_remote():
    with TestingFarmProvisioner(COMPOSE) as p:
        shared.one_remote(p)


def test_one_remote_nonblock():
    with TestingFarmProvisioner(COMPOSE) as p:
        shared.one_remote_nonblock(p)


def test_two_remotes():
    with TestingFarmProvisioner(COMPOSE, max_systems=2) as p:
        shared.two_remotes(p)


def test_two_remotes_nonblock():
    with TestingFarmProvisioner(COMPOSE, max_systems=2) as p:
        shared.two_remotes_nonblock(p)


def test_sharing_remote_slot():
    with TestingFarmProvisioner(COMPOSE, max_systems=1) as p:
        shared.sharing_remote_slot(p)


def test_sharing_remote_slot_nonblock():
    with TestingFarmProvisioner(COMPOSE, max_systems=1) as p:
        shared.sharing_remote_slot_nonblock(p)


def test_cmd():
    with TestingFarmProvisioner(COMPOSE) as p:
        shared.cmd(p)


def test_cmd_input():
    with TestingFarmProvisioner(COMPOSE) as p:
        shared.cmd_input(p)


def test_cmd_binary():
    with TestingFarmProvisioner(COMPOSE) as p:
        shared.cmd_binary(p)


def test_rsync():
    with TestingFarmProvisioner(COMPOSE) as p:
        shared.rsync(p)
