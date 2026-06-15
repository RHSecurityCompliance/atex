import json

import pytest

from atex.executor.fmf import FMFExecutor, TestAbortedError, discover

# these don't work with RHEL-7 podman when running on modern Fedora
# (as a host) due to cgroup v1 / v2 conflict, and possibly more


def test_reboot(provisioner_systemd, tmp_path):
    fmf_tests = discover("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot", tmp_path)
    results = (tmp_path / "results").read_text()
    assert json.loads(results).get("status") == "pass"
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output == "disconnecting\nrebooted\n"


def test_reboot_count(provisioner_systemd, tmp_path):
    fmf_tests = discover("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot_count", tmp_path)
    results = (tmp_path / "results").read_text()
    assert json.loads(results).get("status") == "pass"
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output == "first boot\nsecond boot\nthird boot\n"


def test_reboot_unexpected(provisioner_systemd, tmp_path):
    fmf_tests = discover("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        with pytest.raises(TestAbortedError, match="disconnect was not sent via test control"):
            e.run_test("/test_reboot_unexpected", tmp_path)
