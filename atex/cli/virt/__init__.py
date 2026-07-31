from .install import add_install_args
from .install import install as install
from .reserve import add_reserve_args
from .reserve import reserve as reserve


def parse_args(parser):
    parser.add_argument("--connect", "-c", help="libvirt connection URI")
    cmds = parser.add_subparsers(
        dest="_cmd", help="virt sub-command", metavar="<cmd>", required=True,
    )

    cmd = cmds.add_parser(
        "install",
        help="use virt-install to install a new domain (VM)",
    )
    add_install_args(cmd)

    cmd = cmds.add_parser(
        "reserve",
        help="reserve a temporary domain and ssh into it",
    )
    add_reserve_args(cmd)


def main(args):
    match args._cmd:
        case "install":
            install(args)
        case "reserve":
            if not args.ssh_key:
                raise RuntimeError("--ssh-key is required (no default found)")
            reserve(args)
        case _:
            raise RuntimeError(f"unknown args: {args}")


CLI_SPEC = {
    "help": "utilities for libvirt virtualization",
    "args": parse_args,
    "main": main,
}
