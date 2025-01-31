#!/usr/bin/python3

import sys
import shutil
import logging
from pathlib import Path

from atex.provision.testingfarm import TestingFarmProvisioner
from atex.provision.libvirt import LibvirtCloningProvisioner
from atex.connection.ssh import ManagedSSHConn
from atex import fmf, orchestrator, util


logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def calculate_guest_tag(tags):
    if "snapshottable" not in tags:
        return None
    name = "default"
    if "with-gui" in tags:
        name += "_gui"
    if "uefi" in tags:
        name += "_uefi"
    if "fips" in tags:
        name += "_fips"
    return name


class ContestOrchestrator(orchestrator.Orchestrator):
    @classmethod
    def run_setup(cls, sinfo):
        super().run_setup(sinfo)
        # upload pre-built content
        sinfo.remote.rsync(
            "-rv" if util.in_debug_mode() else "-rq",
            "--exclude=.git/",
            "/home/user/gitit/scap-content/",
            "remote:/root/upstream-content",
        )

    @classmethod
    def next_test(cls, to_run, all_tests, previous):
        # fresh remote, prefer running destructive tests (which likely need
        # clean OS) to get them out of the way and prevent them from running
        # on a tainted OS later
        if isinstance(previous, orchestrator.Orchestrator.SetupInfo):
            for next_name in to_run:
                next_tags = all_tests[next_name].get("tag", ())
                if "destructive" in next_tags:
                    return next_name

        # previous test was run and finished non-destructively,
        # try to find a next test with the same Contest lib.virt guest tags
        # as the previous one, allowing snapshot reuse by Contest
        elif isinstance(previous, orchestrator.Orchestrator.FinishedInfo):
            finished_tags = all_tests[previous.test_name].get("tag", ())
            # if Guest tag is None, don't bother searching
            if finished_guest_tag := calculate_guest_tag(finished_tags):
                for next_name in to_run:
                    next_tags = all_tests[next_name].get("tag", ())
                    next_guest_tag = calculate_guest_tag(next_tags)
                    if next_guest_tag and finished_guest_tag == next_guest_tag:
                        return next_name

        # fallback to the default next_test()
        return super().next_test(to_run, all_tests, previous)

    @classmethod
    def destructive(cls, info, test_data):
        # if Executor ended with an exception (ie. duration exceeded),
        # consider the test destructive
        if info.exception:
            return True

        # if the test returned non-0 exit code, it could have thrown
        # a python exception of its own, or (if bash) aborted abruptly
        # due to 'set -e', don't trust the remote, consider it destroyed
        # (0 = pass, 2 = fail, anything else = bad)
        if info.exit_code not in [0,2]:
            return True

        # if the test was destructive, assume the remote is destroyed
        tags = test_data.get("tag", ())
        if "destructive" in tags:
            return True

        return False


fmf_tests = fmf.FMFTests(
    "/home/user/gitit/contest",
    "/plans/daily",
#    names=["/hardening/host-os/oscap/(cis|ospp|hipaa)"],
#    names=["/hardening/(oscap|anaconda|kickstart|image-builder)/[^/]+$"],
#    names=["/hardening/host-os/oscap"],
    context={"distro": "rhel-10.1", "arch": "x86_64"},
)

print("will run:")
for test in fmf_tests.tests:
    print(f"  {test}")

#prov = TestingFarmProvisioner(
#    "RHEL-9.7.0-Nightly", arch="x86_64",
##    max_systems=20, max_retries=1,
#    max_systems=1, max_retries=1,
#    timeout=720,
#    hardware={"virtualization":{"is-supported":True},"memory":">= 7 GB"},
#)

Path("/tmp/json_file").unlink(missing_ok=True)
if Path("/tmp/storage_dir").exists():
    shutil.rmtree("/tmp/storage_dir")

aggr = orchestrator.JSONAggregator("/tmp/json_file", "/tmp/storage_dir")
aggr.open()

Path("/tmp/storage_dir/orch_tmp").mkdir()


deimos_opts = {
    "Hostname": "deimos....",
    "Port": "22",
    "IdentityFile": "/home/user/.ssh/id_rsa",
    "User": "root",
    #"Compression": "yes",
}
with ManagedSSHConn(deimos_opts) as deimos_conn:
    prov = LibvirtCloningProvisioner(
        host=deimos_conn,
        image="10.1.qcow2",
        domain_filter="scap-d.*",
        #domain_filter="scap-d1",
        domain_sshkey="/home/user/.ssh/id_rsa",
        reserve_time=28800,
    )
    orch = ContestOrchestrator(
        platform="10@x86_64",
        fmf_tests=fmf_tests,
        provisioners=(prov,),
        aggregator=aggr,
        tmp_dir="/tmp/storage_dir/orch_tmp",
        max_reruns=0,
        env={"CONTEST_CONTENT": "/root/upstream-content"},
    )
    with orch:
        orch.serve_forever()
