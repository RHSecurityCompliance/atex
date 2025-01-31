#!/usr/bin/python3

import sys
import logging
#from pathlib import Path
import tempfile
#import shutil
#import concurrent.futures

from atex import executor, connection, fmf


logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stderr,
    format="%(asctime)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

fmf_tests = fmf.FMFTests(
    "/home/user/gitit/contest",
    "/plans/daily",
    context={"distro": "centos-stream-9", "arch": "x86_64"},
    #names=["/hardening/host-os/oscap/hipaa"],
    names=["/scanning/oscap-eval"],
)

#prov = TestingFarmProvisioner("CentOS-Stream-9", arch="x86_64", max_systems=1, max_retries=1)

#with prov:
if True:
    ssh_options = {
        "User": "root",
        "Hostname": "18.222.123.94",
        "IdentityFile": "/tmp/tmpvrzfjiqs/key_rsa",
    }
    with connection.ssh.ManagedSSHConn(options=ssh_options) as conn:
        with executor.Executor(fmf_tests, conn) as ex:
            ex.upload_tests()
            ex.plan_prepare()
            for test_name in fmf_tests.tests:
                tmpdir = tempfile.TemporaryDirectory(dir="/tmp/runtest", delete=False)
                ex.run_test(test_name, tmpdir.name)
            ex.plan_finish()


#shutil.rmtree("/tmp/testme")
#Path("/tmp/testme").mkdir()
##print("\n\n------------------\n\n")
#
#with connection.ssh.ManagedSSHConn(options=ssh_options) as conn:
#    conn.cmd(["mkdir", "/var/myatex"])
#    with executor.Executor(fmf_tests, conn, state_dir="/var/myatex") as ex:
#        ex.upload_tests("/home/user/gitit/tmt-experiments")
#        ex.plan_prepare()
#
#
#def run_one():
#    with connection.ssh.ManagedSSHConn(options=ssh_options) as conn:
#        with executor.Executor(fmf_tests, conn, state_dir="/var/myatex") as ex:
#            for test_name in fmf_tests.tests:
#                tmpdir = tempfile.TemporaryDirectory(delete=False, dir="/tmp/testme")
#                files_dir = Path(tmpdir.name) / "files"
#                json_file = Path(tmpdir.name) / "json"
#                ex.run_test(test_name, json_file, files_dir)
#
##print("\n\n------------------\n\n")
#
#with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
#    for _ in range(1):
#        ex.submit(run_one)
#
#with connection.ssh.ManagedSSHConn(options=ssh_options) as conn:
#    conn.cmd(["rm", "-rf", "/var/myatex"])
