#!/usr/bin/python3

import sys
import logging
from pathlib import Path

from atex.provision.testingfarm import TestingFarmProvisioner
from atex import fmf, orchestrator
from atex.orchestrator import CSVAggregator, JSONAggregator


logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


fmf_tests = fmf.FMFTests("/home/user/gitit/tmt-experiments", "/plans/friday-demo")

prov = TestingFarmProvisioner("CentOS-Stream-9", arch="x86_64", max_systems=5, max_retries=1)

#aggr = orchestrator.CSVAggregator("/tmp/csv_file", "/tmp/storage_dir")
aggr = orchestrator.JSONAggregator("/tmp/aggr_file", "/tmp/storage_dir")
aggr.open()

Path("/tmp/storage_dir/orch_tmp").mkdir()

orch = orchestrator.Orchestrator(
    platform="9@x86_64",
    fmf_tests=fmf_tests,
    provisioners=(prov,),
    aggregator=aggr,
    tmp_dir="/tmp/storage_dir/orch_tmp",
    max_reruns=1,
)

with orch:
    orch.serve_forever()
