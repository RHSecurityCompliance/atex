import subprocess
import time

from .. import Connection, NotConnectedError


class PodmanConnection(Connection):
    def __init__(self, container):
        self.container = container
        self._container_id = None
        self._connected = False

    def connect(self):
        # get the full long OCI container ID, not just a short ID or podman name
        # (needed by "crun exec")
        proc = subprocess.run(
            ("podman", "inspect", "--format", "{{.ID}}", self.container),
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        self._container_id = proc.stdout.strip()
        self._connected = True

    def disconnect(self):
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
    def _wait_for_systemd(self):
        # wait for the full system to be up
        # (--wait doesn't exist on old RHELs and needs extra waiting
        #  for /run/systemd/private)
        for _ in range(600):
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
        self._wait_for_systemd()
