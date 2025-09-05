#!/usr/bin/python3

import sys
import time
import logging
import contextlib

from atex.provisioner.podman import PodmanProvisioner
from atex.provisioner.testingfarm import TestingFarmProvisioner
from atex.provisioner.libvirt import LibvirtCloningProvisioner
from atex.connection.ssh import ManagedSSHConn
from atex import util
#from atex import fmf, orchestrator, util


logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stderr,
    format="%(asctime)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


ssh_opts = {
    "Hostname": "deimos....",
    "Port": "22",
    "IdentityFile": "/home/user/.ssh/id_rsa",
    "User": "root",
}

with ManagedSSHConn(ssh_opts) as ssh_conn:
#with contextlib.ExitStack() as dummy_stack:
    prov = LibvirtCloningProvisioner(
        host=ssh_conn,
        image="10.1.qcow2",
        domain_filter="scap-d.*",
        domain_sshkey="/home/user/.ssh/id_rsa",
    )
#    prov = TestingFarmProvisioner(
#        compose="CentOS-Stream-9",
#    )
#    prov = PodmanProvisioner(
#        "fedora",
#    )
    with prov:
        prov.provision(2)
        util.debug(f"getting first remote // {prov}")
        remote = prov.get_remote()
        util.debug(f"got remote: {remote} // {prov}")
        #remote.cmd(["ls", "/"])
        remote.cmd(("dnf", "-y", "--setopt=install_weak_deps=False", "install", "git-core", "python-srpm-macros"))
        #remote.release()
        util.debug(f"getting second remote // {prov}")
        while True:
            remote = prov.get_remote(block=False)
            if remote:
                util.debug(f"got remote: {remote} // {prov}")
                break
            else:
                util.debug(f"no second remote yet // {prov}")
                time.sleep(3)
