import subprocess
import time

from ... import util
from .. import Connection, NotConnectedError

_get_logger = util.get_loggers("atex.connection.podman")


class PodmanConnection(Connection):
    def __init__(self, container):
        self.logger = _get_logger()

        self.container = container
        self._container_id = None
        self._rootless = None
        self._connected = False

    def connect(self, *, block=True):  # noqa: ARG002
        self.logger.info(f"connecting to {self.container}")

        try:
            if self._container_id is None:
                proc = subprocess.run(
                    ("podman", "inspect", "--format", "{{.ID}}", self.container),
                    stdout=subprocess.PIPE,
                    text=True,
                    check=True,
                )
                self._container_id = proc.stdout.strip()

            if self._rootless is None:
                proc = subprocess.run(
                    ("podman", "info", "--format", "{{.Host.Security.Rootless}}"),
                    stdout=subprocess.PIPE,
                    text=True,
                    check=True,
                )
                rootless = proc.stdout.strip()
                match rootless:
                    case "true":
                        self._rootless = True
                    case "false":
                        self._rootless = False
                    case _:
                        raise RuntimeError(f"invalid Rootless value: {rootless}")
        except subprocess.CalledProcessError as e:
            raise ConnectionError(e) from e

        self._connected = True

    def disconnect(self):
        self.logger.info(f"disconnecting from {self.container}")
        self._connected = False
        self._container_id = None

    def cmd(self, command, *, func=subprocess.run, **func_args):
        if not self._connected:
            raise NotConnectedError("this Connection requires .connect() first")

        # see README for both rootless (systemd-run) and rootful (env unset)
        if self._rootless:
            crun_cmd = (
                "systemd-run", "--quiet", "--user", "--scope", "--collect", "--",
                "crun", "exec", self._container_id, *command,
            )
        else:
            crun_cmd = (
                "env", "-u", "XDG_RUNTIME_DIR",
                "crun", "exec", self._container_id, *command,
            )

        return func(crun_cmd, **func_args)

    def rsync(self, *args, func=subprocess.run, **func_args):
        if not self._connected:
            raise NotConnectedError("this Connection requires .connect() first")

        # use shell to strip off the destination argument rsync passes
        #   cmd[0]=/bin/bash cmd[1]=-c cmd[2]=exec crun ... cmd[3]=destination
        #   cmd[4]=rsync cmd[5]=--server cmd[6]=-vve.LsfxCIvu cmd[7]=. cmd[8]=.
        if self._rootless:
            crun_cmd = (
                "/bin/bash -c '"
                "exec systemd-run --quiet --user --scope --collect -- "
                f'crun exec {self._container_id} "$@"'
                "'"
            )
        else:
            crun_cmd = (
                "/bin/bash -c '"
                f'env -u XDG_RUNTIME_DIR crun exec {self._container_id} "$@"'
                "'"
            )

        return func(
            ("rsync", "-e", crun_cmd, *args),
            **{"check": True, "stdin": subprocess.DEVNULL} | func_args,
        )


class SystemdPodmanConnection(PodmanConnection):
    systemd_boot_wait = 3000  # tenths of a second

    def __init__(self, container):
        super().__init__(container)
        self._systemd_boot_remaining = self.systemd_boot_wait

    def disconnect(self):
        super().disconnect()
        self._systemd_boot_remaining = self.systemd_boot_wait

    def _wait_for_systemd(self, block=True):
        # wait for the full system to be up
        # (--wait doesn't exist on old RHELs and needs extra waiting
        #  for /run/systemd/private)
        if self._systemd_boot_remaining <= 0:
            raise RuntimeError("systemctl is-system-running timed out")
        while self._systemd_boot_remaining > 0:
            self._systemd_boot_remaining -= 1
            proc = super().cmd(
                ("systemctl", "is-system-running"),
                stdout=subprocess.PIPE,
                # also silence systemd-run and crun errors during container
                # shutdown, when it's off, and when it's being set-up
                stderr=subprocess.PIPE,
            )
            out = proc.stdout.strip()
            if out in (b"running", b"degraded"):
                return True
            if not block:
                if self._systemd_boot_remaining > 0:
                    return False
                break
            time.sleep(0.1)
        errout = proc.stderr.strip()
        raise RuntimeError(f"systemctl is-system-running failed: {out} ({errout})")

    def connect(self, *, block=True):
        super().connect(block=block)
        self.logger.debug(f"waiting for systemd on {self.container}")
        if block:
            self._wait_for_systemd(block=True)
        else:
            if not self._wait_for_systemd(block=False):
                raise BlockingIOError("systemd not ready yet")
        self.logger.debug(f"wait for systemd finished on {self.container}")
