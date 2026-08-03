import subprocess
import threading
from pathlib import Path

from atex import connection, util
from atex.connection import NotConnectedError
from atex.connection.ssh import ManagedSSHConnection
from atex.provisioner import Remote
from atex.provisioner.podman import SystemdPodmanProvisioner, build_systemd_container_with_deps


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
            "Port": str(self.ssh_port),
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
            try:
                self.release_hook(self)
            finally:
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


def build_ssh_image(origin, pubkey, *, extra_pkgs=None, extra_content=""):
    """
    Build a systemd-enabled container image with openssh-server configured
    for key-based root login.

    - `origin` is a local image name or ID (ie. from `pull_image()`).

    - `pubkey` is the public key string to authorize for root.

    - `extra_pkgs` are additional packages to install on top of
      the base dependencies and openssh-server.

    - `extra_content` is appended to the Containerfile.
    """
    pkgs = ["openssh-server"]
    if extra_pkgs:
        pkgs += extra_pkgs
    content = (
        "RUN ssh-keygen -A\n"
        "RUN systemctl enable sshd\n"
        "RUN sed -i '1i UsePAM no' /etc/ssh/sshd_config\n"
        "RUN usermod -U root && chage -d 1 root\n"
        "RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh"
        f" && echo '{pubkey}' > /root/.ssh/authorized_keys"
        " && chmod 600 /root/.ssh/authorized_keys\n"
    )
    content += extra_content
    return build_systemd_container_with_deps(origin, extra_pkgs=pkgs, extra_content=content)


def ssh_options(remote, *, user="root", password=None):
    options = {
        "Hostname": remote.ssh_host,
        "Port": str(remote.ssh_port),
        "User": user,
    }
    if password is None:
        options["IdentityFile"] = Path(remote.ssh_key).absolute()
    return options


def setup_user(remote, user, password="dummy_password"):
    remote.cmd(("useradd", "-m", user), check=True)
    # unlock the account - UsePAM=no rejects locked accounts even for key auth
    remote.cmd(("chpasswd",), input=f"{user}:{password}\n", check=True, text=True)
    remote.cmd(("mkdir", "-p", f"/home/{user}/.ssh"), check=True)
    remote.cmd(("chmod", "700", f"/home/{user}/.ssh"), check=True)
    remote.cmd(("cp", "/root/.ssh/authorized_keys", f"/home/{user}/.ssh/"), check=True)
    remote.cmd(("chmod", "600", f"/home/{user}/.ssh/authorized_keys"), check=True)
    remote.cmd(("chown", "-R", f"{user}:{user}", f"/home/{user}/.ssh"), check=True)
