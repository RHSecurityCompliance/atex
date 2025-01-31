import sys
import re

import libvirt

from ..provision.libvirt import locking


def _libvirt_open(url=None):
    # pass no arguments if url is None
    conn = libvirt.open(*((url,) if url else ()))
    print(f"Connected to {conn.getHostname()} via {conn.getURI()}\n")
    return conn


def get_locks(args):
    conn = _libvirt_open(args.connect)
    domains = conn.listAllDomains(libvirt.VIR_CONNECT_LIST_DOMAINS_PERSISTENT)
    for domain in sorted(domains, key=lambda d: d.name()):
        print(f"{domain.name()}:")
        for sig, stamp in locking.get_locks(domain, expired=args.expired):
            print(f"    {sig} {stamp}")
        print()


def unlock(args):
    conn = _libvirt_open(args.connect)
    dom = conn.lookupByName(args.domain)
    locking.unlock(dom, args.signature)


def lock(args):
    conn = _libvirt_open(args.connect)
    dom = conn.lookupByName(args.domain)
    if locking.lock(dom, args.signature, args.timestamp):
        print("Succeeded.")
        sys.exit(0)
    else:
        print("Failed (already locked).")
        sys.exit(2)


def unlock_all(args):
    conn = _libvirt_open(args.connect)
    if args.domains:
        def domains(dom):
            return bool(re.fullmatch(args.domains, dom.name()))
    else:
        def domains(_):
            return True
    locking.unlock_all(conn, args.signature, args.shutdown, domains)


def cleanup_expired(args):
    conn = _libvirt_open(args.connect)
    if args.domains:
        def domains(dom):
            return bool(re.fullmatch(args.domains, dom.name()))
    else:
        def domains(_):
            return True
    locking.cleanup_expired(conn, args.timestamp, domains)


def parse_args(parser):
    parser.add_argument("--connect", "-c", help="Libvirt URL to connect to", metavar="URL")
    cmds = parser.add_subparsers(
        dest="_cmd", help="libvirt helper to run", metavar="<cmd>", required=True,
    )

    cmd = cmds.add_parser(
        "get-locks",
        help="List all locks (signatures)",
    )
    cmd.add_argument("--expired", help="List also expired locks", action="store_true")

    cmd = cmds.add_parser(
        "unlock",
        help="Remove a lock signature from a domain",
    )
    cmd.add_argument("domain", help="Domain name")
    cmd.add_argument("signature", help="Lock signature UUID")

    cmd = cmds.add_parser(
        "lock",
        help="Lock a domain (exit 0:success, 2:fail)",
    )
    cmd.add_argument("domain", help="Domain name")
    cmd.add_argument("signature", help="Lock signature UUID")
    cmd.add_argument("timestamp", help="Expiration time for the lock")

    cmd = cmds.add_parser(
        "unlock-all",
        help="Remove all lock signatures from all domains",
    )
    cmd.add_argument("--signature", help="Only remove this UUID")
    cmd.add_argument("--shutdown", help="Also destroy the domains", action="store_true")
    cmd.add_argument("--domains", help="Which domains names to impact", metavar="REGEX")

    cmd = cmds.add_parser(
        "cleanup-expired",
        help="Remove expired lock signatures from all domains",
    )
    cmd.add_argument("--timestamp", help="Check against this instead of UTC now()")
    cmd.add_argument("--domains", help="Which domains names to impact", metavar="REGEX")


def main(args):
    if args._cmd == "get-locks":
        get_locks(args)
    elif args._cmd == "unlock":
        unlock(args)
    elif args._cmd == "lock":
        lock(args)
    elif args._cmd == "unlock-all":
        unlock_all(args)
    elif args._cmd == "cleanup-expired":
        cleanup_expired(args)
    else:
        raise RuntimeError(f"unknown args: {args}")


CLI_SPEC = {
    "help": "various utils for the Libvirt provisioner",
    "args": parse_args,
    "main": main,
}
