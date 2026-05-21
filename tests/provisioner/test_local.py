import tempfile
from pathlib import Path

import pytest
import testutil

from atex.provisioner.local import LocalProvisioner
from tests.provisioner import shared


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(30):
        yield


@pytest.fixture(scope="function")
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# ------------------------------------------------------------------------------
def test_one_remote():
    with LocalProvisioner() as p:
        shared.one_remote(p)


def test_two_remotes():
    with LocalProvisioner() as p:
        shared.two_remotes(p)


def test_cmd():
    with LocalProvisioner() as p:
        shared.cmd(p)


def test_cmd_input():
    with LocalProvisioner() as p:
        shared.cmd_input(p)


def test_cmd_binary():
    with LocalProvisioner() as p:
        shared.cmd_binary(p)


def test_cmd_cwd(tmp_dir):
    with LocalProvisioner(cwd=tmp_dir) as p:
        p.provision(1)
        rem = p.get_remote()
        rem.cmd(("touch", "testfile"), check=True)
        assert (tmp_dir / "testfile").exists()


def test_rsync(tmp_dir):
    with LocalProvisioner(cwd=tmp_dir) as p:
        shared.rsync(p)
