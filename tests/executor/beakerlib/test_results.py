import json

from atex.executor.beakerlib import BeakerlibExecutor
from atex.executor.fmf import discover


def test_report_result(provisioner, tmp_dir):
    """Test rlReport use, both manually and via phases."""
    fmf_tests = discover("fmf_trees/results", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_report_result", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert ":::::" in output
    results = (tmp_dir / "results").read_text()
    assert results.count("\n") == 7
    results = results.rstrip("\n").split("\n")
    # Setup
    result = json.loads(results[0])
    assert result.get("status") == "pass"
    assert result.get("name") == "Setup"
    assert len(result.get("files", ())) == 1
    # custom rlReport
    result = json.loads(results[1])
    assert result.get("status") == "fail"
    assert result.get("name") == "some result name"
    assert "files" not in result
    # custom rlReport with log
    result = json.loads(results[2])
    assert result.get("status") == "pass"
    assert result.get("name") == "result name with log"
    assert len(result.get("files", ())) == 1
    fname = result["files"][0]
    output = (tmp_dir / "files" / "result name with log" / fname).read_text()
    assert output == "some log content\n"
    # Test phase with a standard name
    result = json.loads(results[3])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    assert len(result.get("files", ())) == 1
    # Test phase with a custom name
    result = json.loads(results[4])
    assert result.get("status") == "fail"
    assert result.get("name") == "some-phase-name"
    assert len(result.get("files", ())) == 1
    # Cleanup
    result = json.loads(results[5])
    assert result.get("status") == "pass"
    assert result.get("name") == "Cleanup"
    assert len(result.get("files", ())) == 1
    # nameless (test itself), fallback result
    assert json.loads(results[6]) == {
        "status": "fail",
        "files": ["output.txt"],
    }


def test_submit_log(provisioner, tmp_dir):
    """Test rlFileSubmit use, both default and custom name."""
    fmf_tests = discover("fmf_trees/results", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_submit_log", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert ":::::" in output
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
        "files": [
            "output.txt",
            "custom log name.txt",
            "log.txt",
        ],
    }
    first_log = (tmp_dir / "files" / "log.txt").read_text()
    assert first_log == "some log content\n"
    second_log = (tmp_dir / "files" / "custom log name.txt").read_text()
    assert first_log == second_log
