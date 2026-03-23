import subprocess

from atex.executor.fmf import FMFExecutor, FMFTests


def test_prepare_cwd(provisioner):
    fmf_tests = FMFTests("fmf_trees/cwd", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests):
        pass
    proc = remote.cmd(
        ("cat", "/tmp/file_contents"),
        stdout=subprocess.PIPE,
        check=True,
        text=True,
    )
    assert proc.stdout == "123\n"


def test_test_cwd(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/cwd", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_cwd", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output == "123\n"
