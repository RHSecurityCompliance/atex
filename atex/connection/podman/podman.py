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
        self._connected = False

    def connect(self):
        # get the full long OCI container ID, not just a short ID or podman name
        # (needed by "crun exec")
        self.logger.info(f"connecting to {self.container}")
        proc = subprocess.run(
            ("podman", "inspect", "--format", "{{.ID}}", self.container),
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        self._container_id = proc.stdout.strip()
        self._connected = True

    def disconnect(self):
        self.logger.info(f"disconnecting from {self.container}")
        self._connected = False
        self._container_id = None

    def cmd(self, command, *, func=subprocess.run, **func_args):
        if not self._connected:
            raise NotConnectedError("this Connection requires .connect() first")
        return func(
            (
                "systemd-run", "--quiet", "--user", "--scope", "--collect", "--",
                "crun", "exec", self._container_id, *command,
            ),
            **func_args,
        )

    def rsync(self, *args, func=subprocess.run, **func_args):
        if not self._connected:
            raise NotConnectedError("this Connection requires .connect() first")
        return func(
            (
                "rsync",
                "-e",
                (
                    # use shell to strip off the destination argument rsync passes
                    #   cmd[0]=/bin/bash cmd[1]=-c cmd[2]=exec crun ... cmd[3]=destination
                    #   cmd[4]=rsync cmd[5]=--server cmd[6]=-vve.LsfxCIvu cmd[7]=. cmd[8]=.
                    "/bin/bash -c '"
                    "exec systemd-run --quiet --user --scope --collect -- "
                    f'crun exec {self._container_id} "$@"'
                    "'"
                ),
                *args,
            ),
            **{"check": True, "stdin": subprocess.DEVNULL} | func_args,
        )


class SystemdPodmanConnection(PodmanConnection):
    systemd_boot_wait = 3000  # tenths of a second

    def _wait_for_systemd(self):
        # wait for the full system to be up
        # (--wait doesn't exist on old RHELs and needs extra waiting
        #  for /run/systemd/private)
        for _ in range(self.systemd_boot_wait):
            proc = super().cmd(
                ("systemctl", "is-system-running"),
                stdout=subprocess.PIPE,
                # also silence systemd-run and crun errors during container
                # shutdown, when it's off, and when it's being set-up
                stderr=subprocess.DEVNULL,
            )
            out = proc.stdout.strip()
            if out in (b"running", b"degraded"):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(f"systemctl is-system-running failed: {out}")

    def connect(self):
        super().connect()
        self.logger.debug(f"waiting for systemd on {self.container}")
        self._wait_for_systemd()
        self.logger.debug(f"wait for systemd finished on {self.container}")
