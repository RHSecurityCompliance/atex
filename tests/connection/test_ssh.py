import os
import shutil
import subprocess

import pytest
import testutil

from atex import util
from atex.connection.ssh import ManagedSSHConnection, StatelessSSHConnection
from atex.provisioner.podman import pull_image
from tests.conftest import DEFAULT_IMAGE, IMAGES

requires_sshpass = pytest.mark.skipif(
    not shutil.which("sshpass"),
    reason="sshpass not found",
)


@pytest.fixture(scope="module")
def ssh_key(tmp_path_factory):
    key_dir = tmp_path_factory.mktemp("ssh")
    return util.ssh_keygen(key_dir)


@pytest.fixture(scope="module")
def image_id(ssh_key):
    pulled = os.environ.get("BASE_IMAGE") or pull_image(IMAGES[DEFAULT_IMAGE])
    _, pubkey_path = ssh_key
    pubkey = pubkey_path.read_text().rstrip()
    image = testutil.build_ssh_image(
        pulled, pubkey,
        extra_pkgs=("sudo", "shadow-utils"),
        extra_content="RUN sed -i '1i PasswordAuthentication yes' /etc/ssh/sshd_config\n",
    )
    try:
        yield image
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", image),
            check=False,
            stdout=subprocess.DEVNULL,
        )


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(300):
        yield


def setup_sudo(remote, user):
    remote.cmd(
        ("tee", f"/etc/sudoers.d/{user}"),
        input=f"{user} ALL=(ALL) NOPASSWD: ALL\n",
        check=True, text=True, stdout=subprocess.DEVNULL,
    )


# -----------------------------------------------------------------------------
def test_managed_cmd_user(image_id, ssh_key):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser")
        with ManagedSSHConnection(testutil.ssh_options(remote, user="testuser")) as conn:
            proc = conn.cmd(
                ("whoami",),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "testuser"


def test_managed_sudo_cmd(image_id, ssh_key):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser")
        setup_sudo(remote, "testuser")
        opts = testutil.ssh_options(remote, user="testuser")
        with ManagedSSHConnection(opts, sudo="root") as conn:
            proc = conn.cmd(
                ("whoami",),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "root"


def test_managed_sudo_rsync(image_id, ssh_key, tmp_path):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser")
        setup_sudo(remote, "testuser")
        opts = testutil.ssh_options(remote, user="testuser")
        with ManagedSSHConnection(opts, sudo="root") as conn:
            src = tmp_path / "testfile"
            src.write_text("sudo rsync test\n")
            conn.rsync(str(src), "remote:/tmp/sudo_rsync_test")
            proc = conn.cmd(
                ("stat", "-c", "%U", "/tmp/sudo_rsync_test"),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "root"


# -----------------------------------------------------------------------------
@requires_sshpass
def test_managed_sshpass_cmd(image_id, ssh_key):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser", "testpasswd")
        opts = testutil.ssh_options(remote, user="testuser", password="testpasswd")
        with ManagedSSHConnection(opts, password="testpasswd") as conn:
            proc = conn.cmd(
                ("whoami",),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "testuser"


@requires_sshpass
def test_managed_sshpass_rsync(image_id, ssh_key, tmp_path):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser", "testpasswd")
        opts = testutil.ssh_options(remote, user="testuser", password="testpasswd")
        with ManagedSSHConnection(opts, password="testpasswd") as conn:
            src = tmp_path / "testfile"
            src.write_bytes(b"\x00\x01\n\x02\x03")
            conn.rsync(str(src), "remote:/tmp/sshpass_rsync_test")
            proc = conn.cmd(
                ("cat", "/tmp/sshpass_rsync_test"),
                stdout=subprocess.PIPE, check=True,
            )
            assert proc.stdout == b"\x00\x01\n\x02\x03"


@requires_sshpass
def test_managed_sshpass_sudo_cmd(image_id, ssh_key):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser", "testpasswd")
        setup_sudo(remote, "testuser")
        opts = testutil.ssh_options(remote, user="testuser", password="testpasswd")
        with ManagedSSHConnection(opts, password="testpasswd", sudo="root") as conn:
            proc = conn.cmd(
                ("whoami",),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "root"


# -----------------------------------------------------------------------------
def test_stateless_cmd_user(image_id, ssh_key):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser")
        with StatelessSSHConnection(testutil.ssh_options(remote, user="testuser")) as conn:
            proc = conn.cmd(
                ("whoami",),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "testuser"


def test_stateless_sudo_cmd(image_id, ssh_key):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser")
        setup_sudo(remote, "testuser")
        opts = testutil.ssh_options(remote, user="testuser")
        with StatelessSSHConnection(opts, sudo="root") as conn:
            proc = conn.cmd(
                ("whoami",),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "root"


def test_stateless_sudo_rsync(image_id, ssh_key, tmp_path):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser")
        setup_sudo(remote, "testuser")
        opts = testutil.ssh_options(remote, user="testuser")
        with StatelessSSHConnection(opts, sudo="root") as conn:
            src = tmp_path / "testfile"
            src.write_text("sudo rsync test\n")
            conn.rsync(str(src), "remote:/tmp/sudo_rsync_test")
            proc = conn.cmd(
                ("stat", "-c", "%U", "/tmp/sudo_rsync_test"),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "root"


# -----------------------------------------------------------------------------
@requires_sshpass
def test_stateless_sshpass_cmd(image_id, ssh_key):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser", "testpasswd")
        opts = testutil.ssh_options(remote, user="testuser", password="testpasswd")
        with StatelessSSHConnection(opts, password="testpasswd") as conn:
            proc = conn.cmd(
                ("whoami",),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "testuser"


@requires_sshpass
def test_stateless_sshpass_rsync(image_id, ssh_key, tmp_path):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser", "testpasswd")
        opts = testutil.ssh_options(remote, user="testuser", password="testpasswd")
        with StatelessSSHConnection(opts, password="testpasswd") as conn:
            src = tmp_path / "testfile"
            src.write_bytes(b"\x00\x01\n\x02\x03")
            conn.rsync(str(src), "remote:/tmp/sshpass_rsync_test")
            proc = conn.cmd(
                ("cat", "/tmp/sshpass_rsync_test"),
                stdout=subprocess.PIPE, check=True,
            )
            assert proc.stdout == b"\x00\x01\n\x02\x03"


@requires_sshpass
def test_stateless_sshpass_sudo_cmd(image_id, ssh_key):
    privkey, _ = ssh_key
    with testutil.SSHPodmanProvisioner(image_id, privkey) as p:
        p.provision(1)
        remote = p.get_remote()
        testutil.setup_user(remote, "testuser", "testpasswd")
        setup_sudo(remote, "testuser")
        opts = testutil.ssh_options(remote, user="testuser", password="testpasswd")
        with StatelessSSHConnection(opts, password="testpasswd", sudo="root") as conn:
            proc = conn.cmd(
                ("whoami",),
                stdout=subprocess.PIPE, check=True, text=True,
            )
            assert proc.stdout.rstrip("\n") == "root"
