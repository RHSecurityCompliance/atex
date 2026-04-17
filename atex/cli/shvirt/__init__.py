import argparse
import json
import logging
import re
import subprocess

from ... import util
from .common import make_helper_cmd
from .install import add_install_args
from .install import install as install
from .reserve import add_reserve_args
from .reserve import reserve as reserve


def _natural_sort(key):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", key)]


def reservations(args):
    helper_cmd = make_helper_cmd(args)
    logging.debug(f"connecting to helper: {helper_cmd}")
    proc = subprocess.run(
        helper_cmd,
        stdout=subprocess.PIPE,
        text=True,
        check=True,
        input='{"cmd": "reservations"}\n',
    )
    response_raw = proc.stdout.rstrip("\n")
    if not response_raw:
        raise RuntimeError("got empty response from helper")

    response = json.loads(response_raw)
    if not response["success"]:
        raise RuntimeError(f"failed: {response['reply']}")

    domains = response["domains"]
    domain_len = max(len(name) for name in domains)

    for domain in sorted(domains, key=_natural_sort):
        print(f"{domain:<{domain_len}}  {domains[domain]}")


def virsh(args):
    request = {
        "cmd": "virsh",
        "args": args.virsh_args,
    }

    helper_cmd = make_helper_cmd(args)
    logging.debug(f"connecting to helper: {helper_cmd}")
    proc = subprocess.run(
        helper_cmd,
        stdout=subprocess.PIPE,
        text=True,
        check=True,
        input=json.dumps(request) + "\n",
    )
    response_raw = proc.stdout.rstrip("\n")
    if not response_raw:
        raise RuntimeError("got empty response from helper")

    response = json.loads(response_raw)
    print(response["reply"], end="")
    raise SystemExit(0 if response["success"] else 1)


def parse_args(parser):
    grp = parser.add_argument_group(
        title="Helper connection",
        description=(
            "These specify how to connect to atex-virt-helper. "
            "Use either '--helper-localhost' OR '--helper-host/user/port', not both."
        ),
    )
    mutex = grp.add_mutually_exclusive_group(required=True)
    mutex.add_argument(
        "--helper-localhost",
        help="spawn a local atex-virt-helper",
        action="store_true",
    )
    mutex.add_argument("--helper-host", help="connect via ssh to a remote helper")
    grp.add_argument("--helper-port", help="connect via ssh to this port", type=int, default=22)
    grp.add_argument("--helper-user", help="connect via ssh as this user", default="root")
    grp.add_argument(
        "--helper-sshkey",
        help="connect via ssh using this key, for reservations too",
        default=util.default_ssh_key(),
    )
    grp.add_argument("--helper-cmd", help="cmd + args instead of atex-virt-helper (shlex syntax)")

    cmds = parser.add_subparsers(
        dest="_cmd", help="shvirt sub-command", metavar="<cmd>", required=True,
    )

    cmd = cmds.add_parser(
        "reservations",
        help="list active domain reservations",
    )

    cmd = cmds.add_parser(
        "virsh",
        help="run an arbitrary virsh command via the helper",
    )
    cmd.add_argument("virsh_args", nargs=argparse.REMAINDER)

    cmd = cmds.add_parser(
        "install",
        help="use virt-install to install a new image (volume)",
    )
    add_install_args(cmd)

    cmd = cmds.add_parser(
        "reserve",
        help="reserve a domain and clone an existing image for it",
    )
    add_reserve_args(cmd)


def main(args):
    if args.helper_host and not args.helper_sshkey:
        raise RuntimeError("--helper-sshkey is required when using --helper-host")

    match args._cmd:
        case "reservations":
            reservations(args)
        case "virsh":
            virsh(args)
        case "install":
            install(args)
        case "reserve":
            if not args.helper_sshkey:
                raise RuntimeError("--helper-sshkey is required for reserve")
            reserve(args)
        case _:
            raise RuntimeError(f"unknown args: {args}")


CLI_SPEC = {
    "help": "utilities for atex-virt-helper",
    "args": parse_args,
    "main": main,
}
