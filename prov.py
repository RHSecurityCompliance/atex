#!/usr/bin/python3

import sys
import logging

from atex.provision.libvirt import LibvirtCloningProvisioner
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
    "Hostname": "deimos.....",
    "Port": "22",
    "IdentityFile": "/home/user/.ssh/id_rsa",
    "User": "root",
}

with ManagedSSHConn(ssh_opts) as ssh_conn:
    prov = LibvirtCloningProvisioner(
        host=ssh_conn,
        image="10.1.qcow2",
        domain_filter="scap-d1",
        domain_sshkey="/home/user/.ssh/id_rsa",
    )
    with prov:
        remote = prov.get_remote()
        util.debug(f"got remote: {remote}")
        #remote.cmd(["ls", "/"])
        remote.cmd(("dnf", "-y", "--setopt=install_weak_deps=False", "install", "git-core", "python-srpm-macros"))
        remote = prov.get_remote()
