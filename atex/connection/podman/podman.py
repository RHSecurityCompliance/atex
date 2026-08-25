import shlex
import subprocess
import time

from ... import util
from .. import Connection, NotConnectedError

_get_logger = util.get_loggers("atex.connection.podman")


class PodmanConnection(Connection):
    podman_command = ("podman",)
    crun_command = ("crun",)

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
                    (*self.podman_command, "inspect", "--format", "{{.ID}}", self.container),
                    stdout=subprocess.PIPE,
                    text=True,
                    check=True,
                )
                self._container_id = proc.stdout.strip()

            if self._rootless is None:
                proc = subprocess.run(
                    (*self.podman_command, "info", "--format", "{{.Host.Security.Rootless}}"),
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
                *self.crun_command, "exec", self._container_id, *command,
            )
        else:
            crun_cmd = (
                "env", "-u", "XDG_RUNTIME_DIR",
                *self.crun_command, "exec", self._container_id, *command,
            )

        return func(crun_cmd, **func_args)

    def rsync(self, *args, func=subprocess.run, **func_args):
        if not self._connected:
            raise NotConnectedError("this Connection requires .connect() first")

        if self._rootless:
            crun_argv = (
                "systemd-run", "--quiet", "--user", "--scope", "--collect", "--",
                *self.crun_command, "exec", self._container_id,
            )
        else:
            crun_argv = (
                "env", "-u", "XDG_RUNTIME_DIR",
                *self.crun_command, "exec", self._container_id,
            )

        # rsync runs the -e command as "<cmd> <destination> rsync --server ...",
        # so pass crun_argv as bash positional params ($1..$N), then exec them
        # with the rsync args ($N+2..) while dropping the destination at $N+1.
        # the whole rsh string is shlex-quoted so rsync's -e tokenizer (which
        # honors quotes but does no backslash escaping) splits it back into the
        # original words - keeping any spaces inside crun_command intact.
        n = len(crun_argv)
        script = f'exec "${{@:1:{n}}}" "${{@:{n + 2}}}"'
        rsh = shlex.join(("/bin/bash", "-c", script, "_", *crun_argv))

        return func(
            ("rsync", "-e", rsh, *args),
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
