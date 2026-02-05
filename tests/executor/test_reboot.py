import json

from atex.fmf import FMFTests
from atex.executor import Executor, TestAbortedError


def test_reboot(provisioner_systemd, tmp_dir):
    fmf_tests = FMFTests("fmf_tree", plan_name="/reboot/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    remote.cmd(("systemctl", "is-system-running", "--wait"), check=True)
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        e.run_test("/reboot/test_reboot", tmp_dir)
    results = (tmp_dir / "results").read_text()
    assert json.loads(results).get("status") == "pass"
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output == "disconnecting\nrebooted\n"


def test_reboot_count(provisioner_systemd, tmp_dir):
    fmf_tests = FMFTests("fmf_tree", plan_name="/reboot/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    remote.cmd(("systemctl", "is-system-running", "--wait"), check=True)
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        e.run_test("/reboot/test_reboot_count", tmp_dir)
    results = (tmp_dir / "results").read_text()
    assert json.loads(results).get("status") == "pass"
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output == "first boot\nsecond boot\nthird boot\n"


def test_reboot_unexpected(provisioner_systemd, tmp_dir):
    fmf_tests = FMFTests("fmf_tree", plan_name="/reboot/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    remote.cmd(("systemctl", "is-system-running", "--wait"), check=True)
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        try:
            e.run_test("/reboot/test_reboot_unexpected", tmp_dir)
            raise AssertionError("TestAbortedError should have triggered")
        except TestAbortedError as e:
            if "disconnect was not sent via test control" not in str(e):
                raise
