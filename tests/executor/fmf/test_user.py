import pytest
import testutil

from atex.connection.ssh import ManagedSSHConnection
from atex.executor.fmf import FMFExecutor, discover


# override the conftest backend fixture to run only with the ssh backend,
# as these tests exercise FMFExecutor under an unprivileged user via SSH
@pytest.fixture(params=("ssh",))
def backend(request):
    return request.param


def test_output(provisioner, tmp_path):
    provisioner.provision(1)
    remote = provisioner.get_remote()
    testutil.setup_user(remote, "testuser")
    fmf_tests = discover("fmf_trees/user", plan="/plan")
    opts = testutil.ssh_options(remote, user="testuser")
    with ManagedSSHConnection(opts) as conn:
        artifacts = tmp_path / "artifacts"
        artifacts.mkdir()
        with FMFExecutor(conn, fmf_tests=fmf_tests) as e:
            e.run_test("/test_output", artifacts)
        output = (artifacts / "files" / "output.txt").read_bytes()
        assert output == b"test output \x00\x01\x02\x03"


def test_whoami(provisioner, tmp_path):
    provisioner.provision(1)
    remote = provisioner.get_remote()
    testutil.setup_user(remote, "testuser")
    fmf_tests = discover("fmf_trees/user", plan="/plan")
    opts = testutil.ssh_options(remote, user="testuser")
    with ManagedSSHConnection(opts) as conn:
        artifacts = tmp_path / "artifacts"
        artifacts.mkdir()
        with FMFExecutor(conn, fmf_tests=fmf_tests) as e:
            e.run_test("/test_whoami", artifacts)
        output = (artifacts / "files" / "output.txt").read_text().rstrip("\n")
        assert output == "testuser"
