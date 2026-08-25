import contextlib
import subprocess
import threading
import time
from pathlib import Path

from atex import util
from atex.connection.ssh import ManagedSSHConnection
from atex.provisioner import Remote
from atex.provisioner.podman import (
    SystemdPodmanProvisioner,
    build_systemd_container_with_deps,
)


class SSHPodmanRemote(Remote, ManagedSSHConnection):
    # how many worker poll steps to wait for the container's sshd to come up
    # before giving up (~5 minutes worth of retries)
    connect_retries = 3000

    def __init__(self, container, *, ssh_host, ssh_port, ssh_key, release_hook):
        super().__init__({
            "Hostname": ssh_host,
            "Port": str(ssh_port),
            "IdentityFile": Path(ssh_key).absolute(),
            "User": "root",
        })
        self._lock = threading.RLock()
        self.container = container
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_key = ssh_key
        self.release_hook = release_hook
        self._release_called = False
        self._connect_waiter = None

    def _connect_gen(self):
        with contextlib.closing(
            util.wait_for_sshd(self.ssh_host, self.ssh_port, logger=self.logger),
        ) as waiter:
            for _ in range(self.connect_retries):
                try:
                    next(waiter)
                except StopIteration:
                    break
                yield
            else:
                raise ConnectionError(
                    f"sshd did not come up on {self.ssh_host}:{self.ssh_port}",
                )

        while True:
            try:
                super().connect(block=False)
                return
            except BlockingIOError:
                yield

    def connect(self, *, block=True):
        with self._lock:
            if self._release_called:
                raise ConnectionError("remote released, cannot connect")
        if self._connect_waiter is None:
            self._connect_waiter = self._connect_gen()
        try:
            if block:
                for _ in self._connect_waiter:
                    time.sleep(0.1)
            else:
                try:
                    next(self._connect_waiter)
                # a spent (returned) generator raises StopIteration, which reads
                # as success - fine, connect() is idempotent once connected
                except StopIteration:
                    pass  # connected
                else:
                    raise BlockingIOError("not connected yet")
        except BlockingIOError:
            raise
        except Exception:
            # drop the spent generator so the next connect() retries with
            # a fresh one, instead of a dead generator's next() raising
            # StopIteration and being misread as connected
            self._connect_waiter = None
            raise

    def disconnect(self):
        if self._connect_waiter is not None:
            self._connect_waiter.close()
            self._connect_waiter = None
        super().disconnect()

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
                    check=False,  # ignore if it fails
                    stdout=subprocess.DEVNULL,
                )

    def __str__(self):
        class_name = self.__class__.__name__
        name = f"{self.container[:17]}..." if len(self.container) > 20 else self.container
        return f"{class_name}({name}, root@{self.ssh_host}:{self.ssh_port})"


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
