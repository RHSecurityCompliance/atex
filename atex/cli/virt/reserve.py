import logging
import subprocess

from ... import util
from ...provisioner.tempvirt import TempVirtProvisioner


def reserve(args):
    # silence connect/disconnect INFO messages on the CLI
    logging.getLogger("atex.connection.ssh").setLevel(logging.WARNING)

    with TempVirtProvisioner(
        args.origin_domain,
        domain_sshkey=args.ssh_key,
        domain_user=args.user,
        domain_sshport_from=args.port,
        uri=args.connect,
    ) as p:
        p.provision()
        remote = p.get_remote()
        # close the provisioner-provided ManagedSSHConnection,
        # we only need the ssh options for our ssh client
        remote.disconnect()

        host = remote.options["Hostname"]
        port = remote.options["Port"]
        user = remote.options["User"]
        key = remote.options["IdentityFile"]

        while True:
            proc = subprocess.run((
                "ssh", "-q", "-i", str(key), "-p", port,
                "-oStrictHostKeyChecking=no", "-oUserKnownHostsFile=/dev/null",
                f"{user}@{host}",
            ))
            if proc.returncode != 0:
                print(
                    f"\nssh -i {key} -p {port} {user}@{host}\n"
                    f"terminated with exit code {proc.returncode}\n",
                )
                try:
                    input("Press RETURN to try to reconnect, Ctrl-C to quit ...")
                except KeyboardInterrupt:
                    print()
                    break
            else:
                break


def add_reserve_args(parser):
    parser.add_argument(
        "origin_domain",
        help="source domain to base the temporary one on",
    )
    parser.add_argument(
        "--user", "-l",
        help="ssh user to connect to",
        default="root",
    )
    parser.add_argument(
        "--ssh-key", "-i",
        help="ssh key to use for the user",
        default=util.default_ssh_key(),
    )
    parser.add_argument(
        "--port", "-p",
        help="ssh port for the temp domain",
        type=int,
    )
