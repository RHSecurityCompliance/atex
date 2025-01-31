#!/usr/bin/python3

import sys
import logging
from pathlib import Path
import shutil
import tempfile
import concurrent.futures

#from atex.provision.testingfarm import TestingFarmProvisioner

from atex import executor, connection, fmf, orchestrator


logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stderr,
    format="%(asctime)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

fmf_tests = fmf.FMFTests(
    "/home/user/gitit/tmt-experiments",
    "/plans/friday-demo",
    context=None,
)

shutil.rmtree("/tmp/testme")
Path("/tmp/testme").mkdir()

ssh_options = {
    "User": "root",
    "Hostname": "3.142.239.8",
    "IdentityFile": "/tmp/tmpn97lvido/key_rsa",
}

print("\n\n------------------\n\n")

with connection.ssh.ManagedSSHConn(options=ssh_options) as conn:
    conn.cmd(["mkdir", "/var/myatex"])
    with executor.Executor(fmf_tests, conn, state_dir="/var/myatex") as ex:
        ex.upload_tests()
        ex.plan_prepare()

aggr = orchestrator.CSVAggregator("/tmp/csv_file", "/tmp/storage_dir")
aggr.open()
print(f"\n\n====== {aggr.csv_writer} =====\n\n")

def run_one(num):
    with connection.ssh.ManagedSSHConn(options=ssh_options) as conn:
        with executor.Executor(fmf_tests, conn, state_dir="/var/myatex") as ex:
            for test_name in fmf_tests.tests:
                safe_test_name = test_name.strip("/").replace("/","-")
                # TODO: actually delete them if test passed (or leave them if some DEBUG was set)
                tmpdir = tempfile.TemporaryDirectory(prefix=f"{safe_test_name}-", delete=False, dir="/tmp/testme")
                files_dir = Path(tmpdir.name) / "files"
                json_file = Path(tmpdir.name) / "json"
                ex.run_test(test_name, json_file, files_dir)
                aggr.ingest(f"platform-{num}", test_name, json_file, files_dir)

print("\n\n------------------\n\n")

run_one(1)
n = 2

with concurrent.futures.ThreadPoolExecutor(max_workers=9) as ex:
    for _ in range(9):
        ex.submit(run_one, n)
        n += 1

aggr.close()

with connection.ssh.ManagedSSHConn(options=ssh_options) as conn:
    conn.cmd(["rm", "-rf", "/var/myatex"])
