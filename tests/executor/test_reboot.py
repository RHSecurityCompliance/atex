import json
import time

from atex.executor import Executor, TestAbortedError
from atex.fmf import FMFTests


def wait_for_systemd(remote):
    # wait for systemd itself to create its socket
    for _ in range(100):
        proc = remote.cmd(("test", "-S", "/run/systemd/private"))
        if proc.returncode == 0:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("waiting for systemd socket failed")

    # wait for the full system to be up
    proc = remote.cmd(("systemctl", "is-system-running", "--wait"))
    if proc.returncode != 0:
        raise RuntimeError("systemctl is-system-running failed to wait")


def test_reboot(provisioner_systemd, tmp_dir):
    fmf_tests = FMFTests("fmf_tree", plan_name="/reboot/plan")
    provisioner_systemd.provision(1)
    remote = provisioner_systemd.get_remote()
    wait_for_systemd(remote)
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
    wait_for_systemd(remote)
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
    wait_for_systemd(remote)
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        try:
            e.run_test("/reboot/test_reboot_unexpected", tmp_dir)
            raise AssertionError("TestAbortedError should have triggered")
        except TestAbortedError as e:
            if "disconnect was not sent via test control" not in str(e):
                raise
