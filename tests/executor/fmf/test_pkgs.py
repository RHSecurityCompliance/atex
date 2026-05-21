import json

import pytest

from atex.executor.fmf import FMFExecutor, TestSetupError, discover


def test_prepare(provisioner, tmp_path):
    fmf_tests = discover("fmf_trees/pkgs", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_prepare", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output.startswith("words-")


def test_require(provisioner, tmp_path):
    fmf_tests = discover("fmf_trees/pkgs", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_require", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output.startswith("units-")
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 1
    json_results = json.loads(results)
    assert "status" in json_results
    assert json_results["status"] == "pass"


# note that this fails on RHEL-7 with YUM, which exits with 0
# if at least one of the mentioned packages installed successfully,
# only noting that 'No package asdsd available.'
def test_require_fail(provisioner, tmp_path):
    fmf_tests = discover("fmf_trees/pkgs", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        with pytest.raises(
            TestSetupError,
            match=r"No match for argument|Unable to find a match",
        ):
            e.run_test("/test_require_fail", tmp_path)
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 1
    json_results = json.loads(results)
    assert "status" in json_results
    assert json_results["status"] == "infra"


def test_recommend(provisioner, tmp_path):
    fmf_tests = discover("fmf_trees/pkgs", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_recommend", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output.startswith("units-")
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 1
    json_results = json.loads(results)
    assert "status" in json_results
    assert json_results["status"] == "pass"
