import subprocess
import threading
from pathlib import Path

import pytest

from atex import connection, util
from atex.connection import NotConnectedError
from atex.connection.ssh import ManagedSSHConnection
from atex.provisioner import Remote
from atex.provisioner.podman import (
    PodmanProvisioner,
    SystemdPodmanProvisioner,
    build_container_with_deps,
    build_systemd_container_with_deps,
)


class SSHPodmanRemote(Remote, connection.podman.SystemdPodmanConnection):
    def __init__(self, container, ssh_host, ssh_port, ssh_key, *, release_hook):
        self._lock = threading.RLock()
        super().__init__(container=container)
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_key = ssh_key
        self.release_hook = release_hook
        self._ssh_conn = None
        self._release_called = False

    def connect(self):
        # wait for systemd via crun exec
        super().connect()
        # then connect via SSH
        util.wait_for_sshd(self.ssh_host, self.ssh_port)
        new_conn = ManagedSSHConnection({
            "Hostname": self.ssh_host,
            "Port": self.ssh_port,
            "IdentityFile": Path(self.ssh_key).absolute(),
            "User": "root",
        })
        new_conn.connect()
        with self._lock:
            self._ssh_conn = new_conn

    def disconnect(self):
        with self._lock:
            if self._ssh_conn:
                self._ssh_conn.disconnect()
                self._ssh_conn = None
        super().disconnect()

    def cmd(self, command, *, func=subprocess.run, **func_args):
        if not self._ssh_conn:
            raise NotConnectedError
        return self._ssh_conn.cmd(command, func=func, **func_args)

    def rsync(self, *args, func=subprocess.run, **func_args):
        if not self._ssh_conn:
            raise NotConnectedError
        return self._ssh_conn.rsync(*args, func=func, **func_args)

    def release(self):
        with self._lock:
            if self._release_called:
                return
            else:
                self._release_called = True
        try:
            self.disconnect()
        finally:
            self.release_hook(self)
            subprocess.run(
                ("podman", "container", "rm", "-f", "-t", "0", self.container),
                check=False,
                stdout=subprocess.DEVNULL,
            )


class SSHPodmanProvisioner(SystemdPodmanProvisioner):
    def __init__(self, image, ssh_key, *, run_options=None, **kwargs):
        publish_port = ("-p", "127.0.0.1::22")
        combined = publish_port if not run_options else tuple(run_options) + publish_port
        super().__init__(image, run_options=combined, **kwargs)
        self._ssh_key = ssh_key

    def _make_remote(self, container_id, release_hook):
        # get podman-style published port mapping, like "127.0.0.1:12345"
        proc = subprocess.run(
            ("podman", "port", container_id, "22"),
            check=True, text=True, stdout=subprocess.PIPE,
        )
        output = proc.stdout.rstrip()
        # since we requested ipv4 127.0.0.1, there should be no ipv6 line
        assert "\n" not in output
        _, _, port = output.partition(":")
        assert port
        return SSHPodmanRemote(
            container=container_id,
            ssh_host="127.0.0.1",
            ssh_port=int(port),
            ssh_key=self._ssh_key,
            release_hook=release_hook,
        )


# ---------------------------------------------------------------------------
# Session-scoped image builds
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def custom_image(base_image):
    image = build_container_with_deps(base_image)
    try:
        yield image
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", image),
            check=True,
            stdout=subprocess.DEVNULL,
        )


@pytest.fixture(scope="session")
def custom_image_systemd(base_image):
    image = build_systemd_container_with_deps(base_image)
    try:
        yield image
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", image),
            check=True,
            stdout=subprocess.DEVNULL,
        )


@pytest.fixture(scope="session")
def custom_image_ssh(base_image, ssh_key):
    _, pubkey_path = ssh_key
    pubkey = pubkey_path.read_text().rstrip()
    image = build_systemd_container_with_deps(
        base_image,
        extra_pkgs=("openssh-server",),
        extra_content=(
            "RUN ssh-keygen -A\n"
            "RUN systemctl enable sshd\n"
            "RUN sed -i '1i UsePAM no' /etc/ssh/sshd_config\n"
            "RUN usermod -U root && chage -d 1 root\n"
            "RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh"
            f" && echo '{pubkey}' > /root/.ssh/authorized_keys"
            " && chmod 600 /root/.ssh/authorized_keys\n"
        ),
    )
    try:
        yield image
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", image),
            check=False,
            stdout=subprocess.DEVNULL,
        )


# ---------------------------------------------------------------------------
# Provisioner fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def provisioner(backend, custom_image, custom_image_ssh, ssh_key):
    if backend == "podman":
        with PodmanProvisioner(custom_image) as prov:
            yield prov
    else:
        privkey, _ = ssh_key
        with SSHPodmanProvisioner(custom_image_ssh, privkey) as prov:
            yield prov


@pytest.fixture
def provisioner_systemd(backend, custom_image_systemd, custom_image_ssh, ssh_key):
    if backend == "podman":
        with SystemdPodmanProvisioner(custom_image_systemd) as prov:
            yield prov
    else:
        privkey, _ = ssh_key
        with SSHPodmanProvisioner(custom_image_ssh, privkey) as prov:
            yield prov
