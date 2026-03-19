from atex import util
from atex.executor.fmf import FMFExecutor, FMFTests


def test_prepare_cwd(provisioner):
    fmf_tests = FMFTests("fmf_trees/cwd", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests):
        pass
    output = remote.cmd(("cat", "/tmp/file_contents"), func=util.subprocess_output)
    assert output == "123"  # util.subprocess_output strips trailing \n


def test_test_cwd(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_trees/cwd", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_cwd", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output == "123\n"
