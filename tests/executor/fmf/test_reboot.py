import json

from atex.executor.fmf import FMFExecutor, FMFTests, TestAbortedError
from atex.provisioner.podman import wait_for_systemd

# these don't work with RHEL-7 podman when running on modern Fedora
# (as a host) due to cgroup v1 / v2 conflict, and possibly more


def test_reboot(provisioner_systemd, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    wait_for_systemd(remote)
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot", tmp_dir)
    results = (tmp_dir / "results").read_text()
    assert json.loads(results).get("status") == "pass"
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output == "disconnecting\nrebooted\n"


def test_reboot_count(provisioner_systemd, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    wait_for_systemd(remote)
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_reboot_count", tmp_dir)
    results = (tmp_dir / "results").read_text()
    assert json.loads(results).get("status") == "pass"
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output == "first boot\nsecond boot\nthird boot\n"


def test_reboot_unexpected(provisioner_systemd, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/reboot", plan="/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    wait_for_systemd(remote)
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        try:
            e.run_test("/test_reboot_unexpected", tmp_dir)
            raise AssertionError("TestAbortedError should have triggered")
        except TestAbortedError as e:
            if "disconnect was not sent via test control" not in str(e):
                raise
