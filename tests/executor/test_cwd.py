from atex import util
from atex.fmf import FMFTests
from atex.executor import Executor


def test_prepare_cwd(provisioner):
    fmf_tests = FMFTests("fmf_tree", plan_name="/cwd/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        e.plan_prepare()
    output = remote.cmd(("cat", "/tmp/file_contents"), func=util.subprocess_output)
    assert output == "123"  # util.subprocess_output strips trailing \n


def test_test_cwd(provisioner, tmp_dir):
    fmf_tests = FMFTests("fmf_tree", plan_name="/cwd/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        e.run_test("/cwd/test_cwd", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output == "123\n"
