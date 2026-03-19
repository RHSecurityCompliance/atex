import json

from atex.executor.fmf import FMFExecutor, FMFTests, TestSetupError


def test_prepare(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/pkgs", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_prepare", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output.startswith("bsd-games-")


def test_require(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/pkgs", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_require", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output.startswith("rogue-")
    results = (tmp_dir / "results").read_text()
    assert results.count("\n") == 1
    json_results = json.loads(results)
    assert "status" in json_results
    assert json_results["status"] == "pass"


def test_require_fail(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/pkgs", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        try:
            e.run_test("/test_require_fail", tmp_dir)
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
    fmf_tests = FMFTests("fmf_trees/pkgs", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_recommend", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output.startswith("rogue-")
    results = (tmp_dir / "results").read_text()
    assert results.count("\n") == 1
    json_results = json.loads(results)
    assert "status" in json_results
    assert json_results["status"] == "pass"
