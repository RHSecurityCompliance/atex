import json

from atex.executor.beakerlib import BeakerlibExecutor
from atex.executor.fmf import discover


def test_report_result(provisioner, tmp_path):
    """Test rlReport use, both manually and via phases."""
    fmf_tests = discover("fmf_trees/results", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_report_result", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 7
    results = results.rstrip("\n").split("\n")
    # Setup
    result = json.loads(results[0])
    assert result.get("status") == "pass"
    assert result.get("name") == "Setup"
    assert "files" not in result  # no logs for Setup
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
    output = (tmp_path / "files" / "result name with log" / fname).read_text()
    assert output == "some log content\n"
    # Test phase with a standard name
    result = json.loads(results[3])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    assert "files" not in result  # no logs for Test
    # Test phase with a custom name
    result = json.loads(results[4])
    assert result.get("status") == "fail"
    assert result.get("name") == "some-phase-name"
    assert len(result.get("files", ())) == 1
    # Cleanup
    result = json.loads(results[5])
    assert result.get("status") == "pass"
    assert result.get("name") == "Cleanup"
    assert "files" not in result  # no logs for Cleanup
    # nameless (test itself), fallback result
    assert json.loads(results[6]) == {
        "status": "fail",
        "files": ["output.txt"],
    }


def test_submit_log(provisioner, tmp_path):
    """Test rlFileSubmit use, both default and custom name."""
    fmf_tests = discover("fmf_trees/results", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_submit_log", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 2
    results = results.rstrip("\n").split("\n")
    # Test
    result = json.loads(results[0])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    assert "files" not in result  # no logs for Test
    # nameless (test itself), fallback result
    assert json.loads(results[1]) == {
        "status": "pass",
        "files": [
            "output.txt",
            "custom log name.txt",
            "log.txt",
        ],
    }
    first_log = (tmp_path / "files" / "log.txt").read_text()
    assert first_log == "some log content\n"
    second_log = (tmp_path / "files" / "custom log name.txt").read_text()
    assert first_log == second_log
