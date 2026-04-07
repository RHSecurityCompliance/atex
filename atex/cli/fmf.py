import pprint

from ..executor.fmf import all_pkg_requires
from ..executor.fmf import discover as fmf_discover


def _get_context(args):
    context = {}
    if args.context:
        for c in args.context:
            key, value = c.split("=", 1)
            context[key] = value
    return context or None


def make_fmftests(args):
    return fmf_discover(
        args.root,
        args.plan,
        names=args.test or None,
        filters=args.filter or None,
        conditions=args.condition or None,
        excludes=args.exclude or None,
        context=_get_context(args),
    )


def requires(args):
    result = make_fmftests(args)
    all_pkgs = set()
    all_pkgs.update(all_pkg_requires(result, key="require"))
    all_pkgs.update(all_pkg_requires(result, key="recommend"))
    for pkg in sorted(all_pkgs):
        print(pkg)


def discover(args):
    result = make_fmftests(args)
    for name in result.data:
        print(name)


def show(args):
    result = make_fmftests(args)
    for name, data in result.data.items():
        print(f"\n--- {name} ---")
        pprint.pprint(data)


def add_fmf_options(parser):
    parser.add_argument("--root", help="path to directory with fmf tests", default=".")
    parser.add_argument("--plan", help="plan name (defaults to dummy plan)")
    parser.add_argument(
        "--test", "-t", help="test name regex (replacing 'test' from plan)",
        action="append",
    )
    parser.add_argument(
        "--exclude", help="test name regex (replacing 'exclude' from plan)",
        action="append",
    )
    parser.add_argument(
        "--condition", help="fmf-style python condition",
        action="append",
    )
    parser.add_argument(
        "--filter", help="fmf-style expression filter (replacing 'filter' from plan)",
        action="append",
    )
    parser.add_argument(
        "--context", "-c", help="tmt style key=value context",
        action="append",
    )


def parse_args(parser):
    add_fmf_options(parser)

    cmds = parser.add_subparsers(
        dest="_cmd", help="fmf feature", metavar="<cmd>", required=True,
    )

    cmds.add_parser(
        "requires", aliases=("req",),
        help="list requires/recommends of the plan and its tests",
    )

    cmds.add_parser(
        "discover", aliases=("di",),
        help="list tests, possibly post-processed by a tmt plan",
    )

    cmds.add_parser(
        "show",
        help="show fmf metadata of test(s)",
    )


def main(args):
    if args._cmd in ("requires", "req"):
        requires(args)
    elif args._cmd in ("discover", "di"):
        discover(args)
    elif args._cmd == "show":
        show(args)
    else:
        raise RuntimeError(f"unknown args: {args}")


CLI_SPEC = {
    "help": "simple CLI interface to atex.executor.fmf",
    "args": parse_args,
    "main": main,
}
