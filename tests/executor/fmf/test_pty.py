from atex.executor.fmf import FMFExecutor, discover


def test_with_pty(provisioner, tmp_dir):
    fmf_tests = discover("fmf_trees/pty", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_with_pty", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_bytes()
    assert b"test1" in output
    assert b"test10" in output


def test_more_with_pty(provisioner, tmp_dir):
    fmf_tests = discover("fmf_trees/pty", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_more_with_pty", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_bytes()
    assert b"test1" in output
    assert b"test10" in output
    assert b"--More--" in output


def test_with_pty_false(provisioner, tmp_dir):
    fmf_tests = discover("fmf_trees/pty", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_with_pty_false", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_bytes()
    assert b"test1" in output
    assert b"test10" in output
    assert b"--More--" not in output


def test_without_pty(provisioner, tmp_dir):
    fmf_tests = discover("fmf_trees/pty", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test("/test_without_pty", tmp_dir)
    output = (tmp_dir / "files" / "output.txt").read_bytes()
    assert b"test1" in output
    assert b"test10" in output
    assert b"--More--" not in output
