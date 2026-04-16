import json
import shutil

from atex.executor.beakerlib import BeakerlibExecutor
from atex.executor.fmf import discover


def test_library_require_paren(provisioner, tmp_dir):
    """Ensure that the library(x/y) syntax works in fmf 'require' key."""
    # copy fmf_trees to tmp_dir since libraries=True modifies it
    shutil.copytree("fmf_trees", tmp_dir / "fmf_trees", symlinks=True)
    fmf_tests = discover(tmp_dir / "fmf_trees" / "libraries", plan="/plan", libraries=True)
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_library_require_paren", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "command not found" not in output
    results = (tmp_dir / "results").read_text()
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


def test_library_require_url(provisioner, tmp_dir):
    """Ensure that the type:library syntax works in fmf 'require' key."""
    # copy fmf_trees to tmp_dir since libraries=True modifies it
    shutil.copytree("fmf_trees", tmp_dir / "fmf_trees", symlinks=True)
    fmf_tests = discover(tmp_dir / "fmf_trees" / "libraries", plan="/plan", libraries=True)
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_library_require_url", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "command not found" not in output
    results = (tmp_dir / "results").read_text()
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
