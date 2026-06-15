import json

from atex.executor.beakerlib import BeakerlibExecutor
from atex.executor.fmf import discover

# these don't work with RHEL-7 podman when running on modern Fedora
# (as a host) due to cgroup v1 / v2 conflict, and possibly more


def test_reboot_rhts(provisioner_systemd, tmp_path):
    fmf_tests = discover("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot_rhts", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "Running true before reboot" in output
    assert "Running true after reboot" in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 3
    results = results.rstrip("\n").split("\n")
    # Test before reboot
    result = json.loads(results[0])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    # Test after reboot
    result = json.loads(results[1])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    # nameless (test itself), fallback result
    assert json.loads(results[2]) == {
        "status": "pass",
        "files": ["output.txt"],
    }


def test_reboot_tmt(provisioner_systemd, tmp_path):
    fmf_tests = discover("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot_tmt", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "Running true before reboot" in output
    assert "Running true after reboot" in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 3
    results = results.rstrip("\n").split("\n")
    # Test before reboot
    result = json.loads(results[0])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    # Test after reboot
    result = json.loads(results[1])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    # nameless (test itself), fallback result
    assert json.loads(results[2]) == {
        "status": "pass",
        "files": ["output.txt"],
    }


def test_reboot_fail_before(provisioner_systemd, tmp_path):
    fmf_tests = discover("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot_fail_before", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "Running false before reboot" in output
    assert "Running true after reboot" in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 3
    results = results.rstrip("\n").split("\n")
    # Test before reboot
    result = json.loads(results[0])
    assert result.get("status") == "fail"
    assert result.get("name") == "Test"
    # Test after reboot
    result = json.loads(results[1])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    # nameless (test itself), fallback result
    assert json.loads(results[2]) == {
        "status": "fail",
        "files": ["output.txt"],
    }


def test_reboot_fail_after(provisioner_systemd, tmp_path):
    fmf_tests = discover("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot_fail_after", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "Running true before reboot" in output
    assert "Running false after reboot" in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 3
    results = results.rstrip("\n").split("\n")
    # Test before reboot
    result = json.loads(results[0])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    # Test after reboot
    result = json.loads(results[1])
    assert result.get("status") == "fail"
    assert result.get("name") == "Test"
    # nameless (test itself), fallback result
    assert json.loads(results[2]) == {
        "status": "fail",
        "files": ["output.txt"],
    }


def test_reboot_no_phase_end(provisioner_systemd, tmp_path):
    fmf_tests = discover("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot_no_phase_end", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "Running false before reboot" in output
    assert "Running true after reboot" in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 2  # phase before reboot is discarded
    results = results.rstrip("\n").split("\n")
    # Test after reboot
    result = json.loads(results[0])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    # nameless (test itself), fallback result
    assert json.loads(results[1]) == {
        "status": "pass",  # despite false before reboot
        "files": ["output.txt"],
    }


def test_reboot_rlrun(provisioner_systemd, tmp_path):
    fmf_tests = discover("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    with BeakerlibExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot_rlrun", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert ":::::" in output
    assert "Running false before reboot" in output
    assert "Running true after reboot" in output
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 2  # phase before reboot is discarded
    results = results.rstrip("\n").split("\n")
    # Test after reboot
    result = json.loads(results[0])
    assert result.get("status") == "pass"
    assert result.get("name") == "Test"
    # nameless (test itself), fallback result
    assert json.loads(results[1]) == {
        "status": "pass",  # despite false before reboot
        "files": ["output.txt"],
    }
