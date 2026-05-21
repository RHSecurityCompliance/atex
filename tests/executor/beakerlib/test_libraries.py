import json

from atex.executor.beakerlib import BeakerlibExecutor
from atex.executor.fmf import discover


def run_one(provisioner, tmp_path, test):
    fmf_tests = discover("fmf_trees/libraries", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test(test, tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "command not found" not in output
    results = (tmp_path / "results").read_text()
    return (results, output)


def test_library_require_paren(provisioner, tmp_path):
    """Ensure that the library(x/y) syntax works in fmf 'require' key."""
    results, _ = run_one(provisioner, tmp_path, "/test_library_require_paren")
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


def test_library_require_paren_all(provisioner, tmp_path):
    """Ensure that the library(x/y) syntax works in fmf 'require' key."""
    results, _ = run_one(provisioner, tmp_path, "/test_library_require_paren_all")
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


def test_library_require_url(provisioner, tmp_path):
    """Ensure that the type:library syntax works in fmf 'require' key."""
    results, _ = run_one(provisioner, tmp_path, "/test_library_require_url")
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


def test_library_require_url_all(provisioner, tmp_path):
    """Ensure that the type:library syntax works in fmf 'require' key."""
    results, _ = run_one(provisioner, tmp_path, "/test_library_require_url_all")
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
