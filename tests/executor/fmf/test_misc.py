import shutil
import time

import pytest

from atex import util
from atex.executor.fmf import FMFExecutor, TestAbortedError, discover


def test_output(provisioner, tmp_path, monkeypatch):
    fmf_tests = discover("fmf_trees/misc", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    artifacts = tmp_path / "artifacts"
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        artifacts.mkdir()
        e.run_test("/test_output", artifacts)
        output = (artifacts / "files" / "output.txt").read_bytes()
        assert output == b"test output \x00\x01\x02\x03"
        shutil.rmtree(artifacts)

        artifacts.mkdir()
        monkeypatch.setenv("ATEX_DEBUG_TEST_OUTPUT_FD", "1")
        e.run_test("/test_output", artifacts)
        monkeypatch.delenv("ATEX_DEBUG_TEST_OUTPUT_FD")
        output = (artifacts / "files" / "output.txt").read_bytes()
        assert b"test output" not in output
        shutil.rmtree(artifacts)


def test_cancel(provisioner, tmp_path):
    fmf_tests = discover("fmf_trees/misc", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()

    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        thread = util.ThreadJoin(target=e.run_test, args=("/test_cancel", tmp_path))
        thread.start()
        time.sleep(10)
        e.cancel()
        with pytest.raises(TestAbortedError):
            thread.join(timeout=30)
