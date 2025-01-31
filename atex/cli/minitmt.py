import sys
#import re
import pprint
#import subprocess
from pathlib import Path

from .. import connection, provision, minitmt
from ..orchestrator import aggregator


def _fatal(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def _get_context(args):
    context = {}
    if args.context:
        for c in args.context:
            key, value = c.split("=", 1)
            context[key] = value
    return context or None


def discover(args):
    result = minitmt.fmf.FMFTests(args.root, args.plan, context=_get_context(args))
    for name in result.tests:
        print(name)


def show(args):
    result = minitmt.fmf.FMFTests(args.root, args.plan, context=_get_context(args))
    if tests := list(result.match(args.test)):
        for test in tests:
            print(f"\n--- {test.name} ---")
            pprint.pprint(test.data)
    else:
        _fatal(f"Not reachable via {args.plan} discovery: {args.test}")


def execute(args):
    # remote system connection
    ssh_keypath = Path(args.ssh_identity)
    if not ssh_keypath.exists():
        _fatal(f"SSH Identity {args.ssh_identity} does not exist")
    ssh_options = {
        "User": args.user,
        "Hostname": args.host,
        "IdentityFile": ssh_keypath,
    }
    env = dict(x.split("=",1) for x in args.env)

    # dummy Remote that just wraps the connection
    class DummyRemote(provision.Remote, connection.ssh.ManagedSSHConn):
        @staticmethod
        def release():
            return

        @staticmethod
        def alive():
            return True

    # result aggregation
    with aggregator.CSVAggregator(args.results_csv, args.results_dir) as csv_aggregator:
        platform_aggregator = csv_aggregator.for_platform(args.platform)

        # tests discovery and selection
        result = minitmt.fmf.FMFTests(args.root, args.plan, context=_get_context(args))
        if args.test:
            tests = list(result.match(args.test))
            if not tests:
                _fatal(f"Not reachable via plan {args.plan} discovery: {args.test}")
        else:
            tests = list(result.as_fmftests())
            if not tests:
                _fatal(f"No tests found for plan {args.plan}")

        # test run
        with DummyRemote(ssh_options) as remote:
            executor = minitmt.executor.Executor(remote, platform_aggregator, env=env)
            executor.upload_tests(args.root)
            executor.setup_plan(result)
            for test in tests:
                executor.run_test(test)


def setup_script(args):
    result = minitmt.fmf.FMFTests(args.root, args.plan, context=_get_context(args))
    try:
        test = result.as_fmftest(args.test)
    except KeyError:
        print(f"Not reachable via {args.plan} discovery: {args.test}")
        raise SystemExit(1) from None
    output = minitmt.scripts.test_setup(
        test=test,
        tests_dir=args.remote_root,
        debug=args.script_debug,
    )
    print(output, end="")


def parse_args(parser):
    parser.add_argument("--root", help="path to directory with fmf tests", default=".")
    parser.add_argument("--context", "-c", help="tmt style key=value context", action="append")
    cmds = parser.add_subparsers(
        dest="_cmd", help="minitmt feature", metavar="<cmd>", required=True,
    )

    cmd = cmds.add_parser(
        "discover", aliases=("di",),
        help="list tests, post-processed by tmt plans",
    )
    cmd.add_argument("plan", help="tmt plan to use for discovery")

    cmd = cmds.add_parser(
        "show",
        help="show fmf data of a test",
    )
    cmd.add_argument("plan", help="tmt plan to use for discovery")
    cmd.add_argument("test", help="fmf style test regex")

    cmd = cmds.add_parser(
        "execute", aliases=("ex",),
        help="run a plan (or test) on a remote system",
    )
    #grp = cmd.add_mutually_exclusive_group()
    #grp.add_argument("--test", "-t", help="fmf style test regex")
    #grp.add_argument("--plan", "-p", help="tmt plan name (path) inside metadata root")
    cmd.add_argument("--env", "-e", help="environment to pass to prepare/test", action="append")
    cmd.add_argument("--test", "-t", help="fmf style test regex")
    cmd.add_argument(
        "--plan", "-p", help="tmt plan name (path) inside metadata root", required=True,
    )
    cmd.add_argument("--platform", help="platform name, ie. rhel9@x86_64", required=True)
    cmd.add_argument("--user", help="ssh user to connect via", required=True)
    cmd.add_argument("--host", help="ssh host to connect to", required=True)
    cmd.add_argument(
        "--ssh-identity", help="path to a ssh keyfile for login", required=True,
    )
    cmd.add_argument(
        "--results-csv", help="path to would-be-created .csv.gz results", required=True,
    )
    cmd.add_argument(
        "--results-dir", help="path to would-be-created dir for uploaded files", required=True,
    )

    cmd = cmds.add_parser(
        "setup-script",
        help="generate a script prepping tests for run",
    )
    cmd.add_argument("--remote-root", help="path to tests repo on the remote", required=True)
    cmd.add_argument("--script-debug", help="do 'set -x' in the script", action="store_true")
    cmd.add_argument("plan", help="tmt plan to use for discovery")
    cmd.add_argument("test", help="full fmf test name (not regex)")


def main(args):
    if args._cmd in ("discover", "di"):
        discover(args)
    elif args._cmd == "show":
        show(args)
    elif args._cmd in ("execute", "ex"):
        execute(args)
    elif args._cmd == "setup-script":
        setup_script(args)
    else:
        raise RuntimeError(f"unknown args: {args}")


CLI_SPEC = {
    "aliases": ("tmt",),
    "help": "simple test executor using atex.minitmt",
    "args": parse_args,
    "main": main,
}
