import re
import subprocess
import tempfile

from atex.executor.fmf import FMFExecutor, discover


def test_prepare_env(provisioner):
    fmf_tests = discover("fmf_trees/env", plan="/plan")
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
    assert "VAR_FROM_PLAN=foo bar\n" in proc.stdout


def test_test_env(provisioner, tmp_path):
    fmf_tests = discover("fmf_trees/env", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_env", tmp_path, env={"VAR_FROM_PARAM": "foo bar"})
    output = (tmp_path / "files" / "output.txt").read_text()
    assert "VAR_FROM_PLAN=foo bar\n" in output
    assert "VAR_FROM_PARAM=foo bar\n" in output


def test_envfile(provisioner, tmp_path):
    fmf_tests = discover("fmf_trees/env", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        with tempfile.TemporaryDirectory() as tmp_path2:
            e.run_test("/test_write_env", tmp_path2)
        e.run_test("/test_env", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert "VAR_FROM_TEST=foo bar\n" in output


def test_envfile_shared(provisioner, tmp_path):
    fmf_tests = discover("fmf_trees/env", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_env", tmp_path)
    plan_proc = remote.cmd(
        ("cat", "/tmp/plan_env"),
        stdout=subprocess.PIPE,
        check=True,
        text=True,
    )
    test_output = (tmp_path / "files" / "output.txt").read_text()
    assert "TMT_PLAN_ENVIRONMENT_FILE=" in plan_proc.stdout
    assert "TMT_PLAN_ENVIRONMENT_FILE=" in test_output
    plan_regex = re.search(r"TMT_PLAN_ENVIRONMENT_FILE=([^\n]+)", plan_proc.stdout)
    assert plan_regex is not None
    test_regex = re.search(r"TMT_PLAN_ENVIRONMENT_FILE=([^\n]+)", test_output)
    assert test_regex is not None
    # ensure both plan and test get the same path
    assert plan_regex.group(1) == test_regex.group(1)
