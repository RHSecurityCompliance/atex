#!/usr/bin/python3

import sys
import shutil
import logging
from pathlib import Path

from atex.provisioner.testingfarm import TestingFarmProvisioner
from atex.fmf import FMFTests
from atex.aggregator.json import JSONAggregator
from atex.orchestrator.adhoc import AdHocOrchestrator


logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


fmf_tests = FMFTests("/home/user/gitit/tmt-experiments", "/plans/friday-demo")

prov = TestingFarmProvisioner("CentOS-Stream-9", arch="x86_64")

Path("/tmp/aggr_file").unlink(missing_ok=True)
if Path("/tmp/storage_dir").exists():
    shutil.rmtree("/tmp/storage_dir")

with JSONAggregator("/tmp/aggr_file", "/tmp/storage_dir") as aggr:
    Path("/tmp/storage_dir/orch_tmp").mkdir()

    orch = AdHocOrchestrator(
        platform="9@x86_64",
        fmf_tests=fmf_tests,
        provisioners=(prov,),
        aggregator=aggr,
        tmp_dir="/tmp/storage_dir/orch_tmp",
        max_reruns=1,
    )

    with orch:
        orch.serve_forever()
