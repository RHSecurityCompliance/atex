import subprocess

from atex.executor.fmf import FMFExecutor, discover


def test_prepare_cwd(provisioner):
    """Prepare script runs with CWD set to the fmf tree root."""
    fmf_tests = discover("fmf_trees/cwd", plan="/plan")
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


def test_test_cwd(provisioner, tmp_path):
    """Test script runs with CWD set to the test's fmf definition directory."""
    fmf_tests = discover("fmf_trees/cwd", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_cwd", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output == "123\n"


def test_cwd_named_section(provisioner, tmp_path):
    """CWD is correct when discover section has a name prefix."""
    fmf_tests = discover("fmf_trees/cwd", plan="/plan_named")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/section/test_cwd", tmp_path)
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output == "123\n"


def test_cwd_two_named_sections(provisioner, tmp_path):
    """CWD is correct for each test across two named discover sections."""
    fmf_tests = discover("fmf_trees/cwd", plan="/plan_two_sections")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    artifacts1 = tmp_path / "artifacts1"
    artifacts1.mkdir()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/root_tests/test_cwd", artifacts1)
    output = (artifacts1 / "files" / "output.txt").read_text()
    assert output == "123\n"
    artifacts2 = tmp_path / "artifacts2"
    artifacts2.mkdir()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/sub_tests/subdir/test_subdir_cwd", artifacts2)
    output = (artifacts2 / "files" / "output.txt").read_text()
    assert output == "456\n"
