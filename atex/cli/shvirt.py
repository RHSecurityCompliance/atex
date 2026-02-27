import argparse
import json
import subprocess
import sys


def _fatal(msg):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def reservations(args):
    helper_exec = args.helper_exec.split(" ")
    if not helper_exec:
        _fatal("'helper_command' needs to be provided")

    proc = subprocess.run(
        helper_exec,
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

    for domain, status in domains.items():
        print(f"{domain:<{domain_len}}  {status}")


def virsh(args):
    helper_exec = args.helper_exec.split(" ")
    if not helper_exec:
        _fatal("'helper_command' needs to be provided")

    request = {
        "cmd": "virsh",
        "args": args.virsh_args,
    }

    proc = subprocess.run(
        helper_exec,
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
    parser.add_argument("--helper-exec", "-e", help="helper command to exec", required=True)

    cmds = parser.add_subparsers(
        dest="_cmd", help="shvirt sub-command", metavar="<cmd>", required=True,
        description=(
            "These execute '--helper-exec' as a command to communicate with. "
            "It can simply be 'atex-virt-helper' directly, or any other proxy "
            "command, such as 'ssh user@host atex-virt-helper', or even just "
            "'ssh host' if the host is defined in ~/.ssh/config and/or has "
            "ForceCommand to execute the helper."
        ),
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


def main(args):
    if args._cmd == "reservations":
        reservations(args)
    elif args._cmd == "virsh":
        virsh(args)
    else:
        raise RuntimeError(f"unknown args: {args}")


CLI_SPEC = {
    "help": "utilities for atex-virt-helper",
    "args": parse_args,
    "main": main,
}
