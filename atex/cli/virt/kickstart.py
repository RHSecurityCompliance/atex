import importlib.resources
import re
from pathlib import Path

_ks_builtin = importlib.resources.files(__package__).joinpath("ks.cfg")


def add_kickstart_args(parser):
    """
    Add common kickstart-related CLI arguments to an argparse parser.
    """
    grp = parser.add_argument_group("Kickstart")
    grp.add_argument("--ks-packages", help=r"string with \n-separated extra RPMs to install")
    grp.add_argument("--ks-sshkeys", help=r"string with \n-separated ssh keys for root")
    grp.add_argument(
        "--ks-cmd",
        help="kickstart cmd with args, replaces built-in one",
        action="append",
        default=[],
    )
    grp.add_argument(
        "--ks-del",
        help=r"multi-line regexp to delete from the built-in kickstart",
        action="append",
        default=[],
    )
    grp.add_argument(
        "--ks-append",
        help="verbatim string to append to kickstart",
        action="append",
        default=[],
    )
    grp.add_argument("--ks", help="full kickstart file to use, ignore other --ks-* opts")


def _build_kickstart(*, ks, ks_cmd, ks_del, ks_append, ks_packages, ks_sshkeys):
    if ks is not None:
        return Path(ks).read_text()

    contents = _ks_builtin.read_text()

    for regex in ks_del:
        contents = re.sub(regex, "", contents, flags=re.MULTILINE | re.DOTALL)

    if ks_cmd:
        cmds = {cmd.partition(" ")[0]: cmd for cmd in ks_cmd}
        new_lines = contents.splitlines()
        for i, line in enumerate(new_lines):
            line_cmd = line.partition(" ")[0]
            if new_content := cmds.get(line_cmd):
                new_lines[i] = new_content
        contents = "\n".join(new_lines) + "\n"

    if ks_packages:
        contents += (
            "\n%packages --ignoremissing\n" +
            ks_packages.strip("\n") +
            "\n%end\n"
        )

    if ks_sshkeys:
        contents += (
            "\n%post --erroronfail\n"
            "mkdir -p /root/.ssh\n"
            "cat > /root/.ssh/authorized_keys <<'EOF'\n"
        ) + ks_sshkeys.strip("\n") + (
            "\nEOF\n"
            "chmod go-rwx -R /root/.ssh\n"
            "chown root:root -R /root/.ssh\n"
            "%end\n"
        )

    for extra in ks_append:
        contents += f"\n{extra}\n"

    return contents


def kickstart_from_args(args):
    """
    Build a kickstart string from parsed CLI arguments, as added by
    `add_kickstart_args()`.
    """
    return _build_kickstart(
        ks=args.ks,
        ks_cmd=args.ks_cmd,
        ks_del=args.ks_del,
        ks_append=args.ks_append,
        ks_packages=args.ks_packages,
        ks_sshkeys=args.ks_sshkeys,
    )
