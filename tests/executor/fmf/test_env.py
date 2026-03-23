import re
import subprocess
import tempfile

from atex.executor.fmf import FMFExecutor, FMFTests


def test_prepare_env(provisioner):
    fmf_tests = FMFTests("fmf_trees/env", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests):
        pass
    proc = remote.cmd(
        ("cat", "/tmp/plan_env"),
        stdout=subprocess.PIPE,
        check=True,
        text=True,
    )
    assert "\nVAR_FROM_PLAN=foo bar\n" in proc.stdout


def test_test_env(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/env", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_env", tmp_dir, env={"VAR_FROM_PARAM": "foo bar"})
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert "\nVAR_FROM_PLAN=foo bar\n" in output
    assert "\nVAR_FROM_PARAM=foo bar\n" in output


def test_envfile(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/env", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        with tempfile.TemporaryDirectory() as tmp_dir2:
            e.run_test("/test_write_env", tmp_dir2)
        e.run_test("/test_env", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert "\nVAR_FROM_TEST=foo bar\n" in output


def test_envfile_shared(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/env", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_env", tmp_dir)
    plan_proc = remote.cmd(
        ("cat", "/tmp/plan_env"),
        stdout=subprocess.PIPE,
        check=True,
        text=True,
    )
    test_output = (tmp_dir / "files" / "output.txt").read_text()
    assert "\nTMT_PLAN_ENVIRONMENT_FILE=" in plan_proc.stdout
    assert "\nTMT_PLAN_ENVIRONMENT_FILE=" in test_output
    plan_regex = re.search(r"TMT_PLAN_ENVIRONMENT_FILE=([^\n]+)", plan_proc.stdout)
    assert plan_regex is not None
    test_regex = re.search(r"TMT_PLAN_ENVIRONMENT_FILE=([^\n]+)", test_output)
    assert test_regex is not None
    # ensure both plan and test get the same path
    assert plan_regex.group(1) == test_regex.group(1)
