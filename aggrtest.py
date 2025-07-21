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


aggr = orchestrator.JSONAggregator("aggr_file.gz", "storage_dir")
aggr.open()

tmp = Path("/tmp/runtest/tmp4a2rgiyg")
aggr.ingest(f"9@x86_64", "/scanning/oscap-eval", tmp/"results", tmp/"files")
tmp = Path("/tmp/runtest/tmp5qaer7l1")
aggr.ingest(f"9@x86_64", "/static-checks/ansible/syntax-check", tmp/"results", tmp/"files")
tmp = Path("/tmp/runtest/tmp9j079r86")
aggr.ingest(f"9@x86_64", "/static-checks/rule-identifiers", tmp/"results", tmp/"files")
tmp = Path("/tmp/runtest/tmphkur52nt")
aggr.ingest(f"9@x86_64", "/static-checks/unit-tests-metadata", tmp/"results", tmp/"files")
tmp = Path("/tmp/runtest/tmprty5b_gj")
aggr.ingest(f"9@x86_64", "/static-checks/rpmbuild-ctest", tmp/"results", tmp/"files")
tmp = Path("/tmp/runtest/tmptmj_fmzw")
aggr.ingest(f"9@x86_64", "/static-checks/removed-rules", tmp/"results", tmp/"files")
tmp = Path("/tmp/runtest/tmpx8e0j1q2")
aggr.ingest(f"9@x86_64", "/static-checks/ansible/allowed-modules", tmp/"results", tmp/"files")

aggr.close()
