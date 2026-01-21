import json

from atex.fmf import FMFTests
from atex.executor import Executor, TestSetupError


def test_prepare(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_tree", plan_name="/pkgs/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        e.plan_prepare()
        e.run_test("/pkgs/test_prepare", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output.startswith("bsd-games-")


def test_require(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_tree", plan_name="/pkgs/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        e.plan_prepare()
        e.run_test("/pkgs/test_require", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output.startswith("rogue-")
    results = (tmp_dir / "results").read_text()
    assert results.count("\n") == 1
    json_results = json.loads(results)
    assert "status" in json_results
    assert json_results["status"] == "pass"


def test_require_fail(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_tree", plan_name="/pkgs/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        try:
            e.plan_prepare()
            e.run_test("/pkgs/test_require_fail", tmp_dir)
            raise AssertionError("TestSetupError was not raised")
        except TestSetupError as e:
            if "No match for argument: nonexistent_pkg" not in str(e):
                raise
    results = (tmp_dir / "results").read_text()
    assert results.count("\n") == 1
    json_results = json.loads(results)
    assert "status" in json_results
    assert json_results["status"] == "infra"


def test_recommend(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_tree", plan_name="/pkgs/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        e.plan_prepare()
        e.run_test("/pkgs/test_recommend", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output.startswith("rogue-")
    results = (tmp_dir / "results").read_text()
    assert results.count("\n") == 1
    json_results = json.loads(results)
    assert "status" in json_results
    assert json_results["status"] == "pass"
