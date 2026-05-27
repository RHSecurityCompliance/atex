import argparse
import os
import subprocess
import tempfile
import uuid

import pytest
import testutil

from atex import util
from atex.cli.virt import install
from atex.cli.virt import parse_args as setup_virt_parser
from atex.provisioner.tempvirt import TempVirtProvisioner
from tests.provisioner import shared


@pytest.fixture(scope="module")
def domain_and_sshkey():
    location = os.environ.get("TEMPVIRT_LOCATION")
    if not location:
        raise RuntimeError("TEMPVIRT_LOCATION not in environment")

    domain_name = f"atex-tests-{uuid.uuid4()}"

    with tempfile.TemporaryDirectory() as tmpdir:
        sshkey, sshpubkey = util.ssh_keygen(tmpdir)

        parser = argparse.ArgumentParser()
        setup_virt_parser(parser)
        args = parser.parse_args([
            "install",
            "--name", domain_name,
            "--location", location,
            "--ks-sshkeys", sshpubkey.read_text(),
            "--final-memory", "2048",
            "--emulate-pty",
        ])
        install(args)

        yield (domain_name, sshkey)

    subprocess.run(
        ("virsh", "-q", "undefine", domain_name, "--remove-all-storage", "--nvram"),
        check=True,
        stdout=subprocess.DEVNULL,
    )


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(1200):
        yield


# ------------------------------------------------------------------------------


def test_start_stop(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey):
        pass


def test_one_remote(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey) as p:
        shared.one_remote(p)


def test_one_remote_nonblock(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey) as p:
        shared.one_remote_nonblock(p)


def test_two_remotes(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey) as p:
        shared.two_remotes(p)


def test_two_remotes_nonblock(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey) as p:
        shared.two_remotes_nonblock(p)


def test_sharing_remote_slot(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey, max_remotes=1) as p:
        shared.sharing_remote_slot(p)


def test_sharing_remote_slot_nonblock(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey, max_remotes=1) as p:
        shared.sharing_remote_slot_nonblock(p)


def test_cmd(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey) as p:
        shared.cmd(p)


def test_cmd_input(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey) as p:
        shared.cmd_input(p)


def test_cmd_binary(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey) as p:
        shared.cmd_binary(p)


def test_rsync(domain_and_sshkey):
    domain_name, sshkey = domain_and_sshkey
    with TempVirtProvisioner(domain_name, domain_sshkey=sshkey) as p:
        shared.rsync(p)
