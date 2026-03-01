from pathlib import Path

from ...provisioner.shvirt import SharedVirtProvisioner


def make_helper_cmd(args):
    if args.helper_localhost:
        return SharedVirtProvisioner.helper_command
    else:
        return (
            "ssh",
            "-oLogLevel=ERROR",
            "-oStrictHostKeyChecking=no", "-oUserKnownHostsFile=/dev/null",
            "-oConnectionAttempts=3", "-oServerAliveCountMax=4", "-oServerAliveInterval=5",
            "-oTCPKeepAlive=no", "-oEscapeChar=none", "-oRequestTTY=no",
            f"-oIdentityFile={str(Path(args.helper_sshkey).absolute())}",
            f"-oUser={args.helper_user}", f"-oHostname={args.helper_host}",
            "ignored_arg", "--",
            *SharedVirtProvisioner.helper_command,
        )
