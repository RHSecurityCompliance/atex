import shlex
from pathlib import Path

from ...provisioner.shvirt import SharedVirtProvisioner


def make_helper_cmd(args):
    cmd = shlex.split(args.helper_cmd) if args.helper_cmd else SharedVirtProvisioner.helper_command
    if args.helper_localhost:
        return cmd
    else:
        return (
            "ssh",
            "-oLogLevel=ERROR",
            "-oStrictHostKeyChecking=no", "-oUserKnownHostsFile=/dev/null",
            "-oConnectionAttempts=3", "-oServerAliveCountMax=4", "-oServerAliveInterval=5",
            "-oTCPKeepAlive=no", "-oEscapeChar=none", "-oRequestTTY=no",
            f"-oIdentityFile={str(Path(args.helper_sshkey).absolute())}",
            f"-oUser={args.helper_user}", f"-oHostname={args.helper_host}",
            f"-oPort={args.helper_port}",
            "ignored_arg", "--",
            *cmd,
        )
