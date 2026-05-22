import json

from atex.executor.beakerlib import BeakerlibExecutor
from atex.executor.fmf import discover


def test_fallback_status_pass(provisioner, tmp_path):
    """Check that fallback result reports pass based on previous results."""
    fmf_tests = discover("fmf_trees/sanity", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_fallback_status_pass", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "Running true" in output
    assert "Running false" not in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 2
    results = results.rstrip("\n").split("\n")
    # Test
    result = json.loads(results[0])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    assert len(result.get("files", ())) == 1
    # nameless (test itself), fallback result
    assert json.loads(results[1]) == {
        "status": "pass",
        "files": ["output.txt"],
    }


def test_fallback_status_fail(provisioner, tmp_path):
    """Check that fallback result reports fail based on previous results."""
    fmf_tests = discover("fmf_trees/sanity", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_fallback_status_fail", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "Running true" in output
    assert "Running false" in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 2
    results = results.rstrip("\n").split("\n")
    # Test
    result = json.loads(results[0])
    assert result.get("status") == "fail"
    assert result.get("name") == "Test"
    assert len(result.get("files", ())) == 1
    # nameless (test itself), fallback result
    assert json.loads(results[1]) == {
        "status": "fail",
        "files": ["output.txt"],
    }


def test_fallback_status_exit(provisioner, tmp_path):
    """Check that fallback reports fail on non-zero exit without results."""
    fmf_tests = discover("fmf_trees/sanity", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_fallback_status_exit", tmp_path)
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "fail",
        "files": ["output.txt"],
    }
