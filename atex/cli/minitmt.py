import re
import pprint

#from .. import util
from ..minitmt import fmf


def _get_context(args):
    context = {}
    if args.context:
        for c in args.context:
            key, value = c.split('=', 1)
            context[key] = value
    return context or None


def discover(args):
    result = fmf.FMFData(args.root, args.plan, context=_get_context(args))
    for test in result.tests:
        print(test.name)


def show(args):
    result = fmf.FMFData(args.root, args.plan, context=_get_context(args))
    for test in result.tests:
        if re.match(args.test, test.name):
            pprint.pprint(test.data)
            break
    else:
        print(f"Not reachable via {args.plan} discovery: {args.test}")
        raise SystemExit(1)


def parse_args(parser):
    parser.add_argument('--root', default='.', help="path to directory with fmf tests")
    parser.add_argument('--context', '-c', help="tmt style key=value context", action='append')
    cmds = parser.add_subparsers(
        dest='_cmd', help="minitmt feature", metavar='<cmd>', required=True,
    )

    cmd = cmds.add_parser(
        'discover', aliases=('di',),
        help="list tests, post-processed by tmt plans",
    )
    cmd.add_argument('plan', help="tmt plan to use for discovery")

    cmd = cmds.add_parser(
        'show',
        help="show fmf data of a test",
    )
    cmd.add_argument('plan', help="tmt plan to use for discovery")
    cmd.add_argument('test', help="fmf style test regex")

    cmd = cmds.add_parser(
        'execute', aliases=('ex',),
        help="run a plan (or test) on a remote system",
    )
    grp = cmd.add_mutually_exclusive_group()
    grp.add_argument('--test', '-t', help="fmf style test regex")
    grp.add_argument('--plan', '-p', help="tmt plan name (path) inside metadata root")
    cmd.add_argument('--ssh-identity', '-i', help="path to a ssh keyfile for login")
    cmd.add_argument('user_host', help="ssh style user@host of the remote")


def main(args):
    if args._cmd in ('discover', 'di'):
        discover(args)
    elif args._cmd == 'show':
        show(args)
    elif args._cmd in ('execute', 'ex'):
        #execute(args)
        print("not implemented yet")
    else:
        raise RuntimeError(f"unknown args: {args}")


CLI_SPEC = {
    'aliases': ('tmt',),
    'help': "simple test executor using atex.minitmt",
    'args': parse_args,
    'main': main,
}
