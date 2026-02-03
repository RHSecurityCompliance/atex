r"""
Command line interface to atex

Submodules (subpackages) of this one must define a module-level dict with
these keys:

  - help
    - short oneliner about what the submodule is about (for argparse --help)

  - aliases (optional)
    - tuple of aliases of the module name, for argument parsing

  - args
    - function (or other callable) for argument specification/parsing,
      gets passed one non-kw argument: argparse-style parser

  - main
    - function (or other callable) that will be called when invoked by the user,
      gets passed one non-kw argument: argparse-style Namespace

This module-level dict must be named `CLI_SPEC`.
"""

import sys
import importlib
import pkgutil
import argparse
import logging


def setup_logging(level):
    # also print urllib3 headers
    if level <= logging.DEBUG:
        import http.client  # noqa: PLC0415
        http.client.HTTPConnection.debuglevel = 5
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(asctime)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def collect_modules():
    for info in pkgutil.iter_modules(__spec__.submodule_search_locations):
        mod = importlib.import_module(f".{info.name}", __name__)
        if not hasattr(mod, "CLI_SPEC"):
            raise ValueError(f"CLI submodule '{info.name}' does not define CLI_SPEC")
        yield (info.name, mod.CLI_SPEC)


def main():
    parser = argparse.ArgumentParser()

    log_grp = parser.add_mutually_exclusive_group()
    log_grp.add_argument(
        "--debug", "-d", action="append", dest="debug_loggers", metavar="LOGGER", default=[],
        help="set logging.DEBUG for a given logger name",
    )
    log_grp.add_argument(
        "--debug-all", "-D", action="store_const", dest="loglevel", const=logging.DEBUG,
        help="set logging.DEBUG globally",
    )
    log_grp.add_argument(
        "--quiet", "-q", action="store_const", dest="loglevel", const=logging.WARNING,
        help="set logging.WARNING globally (suppress INFO)",
    )
    parser.set_defaults(loglevel=logging.INFO)

    mains = {}
    subparsers = parser.add_subparsers(dest="_module", metavar="<module>", required=True)
    for name, spec in collect_modules():
        aliases = spec["aliases"] if "aliases" in spec else ()
        subp = subparsers.add_parser(
            name,
            aliases=aliases,
            help=spec["help"],
        )
        spec["args"](subp)
        mains[name] = spec["main"]
        for alias in aliases:
            mains[alias] = spec["main"]

    args = parser.parse_args()

    setup_logging(args.loglevel)
    # per-logger overrides
    for logger in args.debug_loggers:
        logging.getLogger(logger).setLevel(logging.DEBUG)

    try:
        mains[args._module](args)
    except KeyboardInterrupt:
        raise SystemExit from None
