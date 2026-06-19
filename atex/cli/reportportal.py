import os

from ..aggregator.reportportal.api import ReportPortalAPI


def _get_api(args):
    url = (
        args.url
        or os.environ.get("ATEX_REPORTPORTAL_URL")
        or os.environ.get("TMT_PLUGIN_REPORT_REPORTPORTAL_URL")
    )
    if not url:
        raise RuntimeError("no URL passed or found via env vars")

    project = (
        args.project
        or os.environ.get("ATEX_REPORTPORTAL_PROJECT")
        or os.environ.get("TMT_PLUGIN_REPORT_REPORTPORTAL_PROJECT")
    )
    if not project:
        raise RuntimeError("no project passed or found via env vars")

    token = (
        args.token
        or os.environ.get("ATEX_REPORTPORTAL_TOKEN")
        or os.environ.get("TMT_PLUGIN_REPORT_REPORTPORTAL_TOKEN")
    )
    if not token:
        raise RuntimeError("no token passed or found via env vars")
    return ReportPortalAPI(url, project, token, ssl_verify=not args.no_ssl_verify)


def launch_start(args):
    api = _get_api(args)
    kwargs = {}
    if args.description:
        kwargs["description"] = args.description
    launch_uuid = api.launch_start(name=args.name, **kwargs)
    print(launch_uuid)


def launch_finish(args):
    api = _get_api(args)
    api.launch_finish(args.uuid)


def launch_list(args):
    api = _get_api(args)
    kwargs = {}
    if args.page_size is not None:
        kwargs["page_size"] = args.page_size
    kwargs["max_pages"] = args.max_pages
    for launch in api.launch_list(**kwargs):
        uuid = launch["uuid"]
        number = launch.get("number")
        number = f" #{number}" if number else ""
        status = launch.get("status") or "<no status>"
        name = launch["name"]
        print(f"{uuid} {status:>12}: {name}{number}")


def parse_args(parser):
    parser.add_argument("--url", help="RP instance URL (or ATEX_REPORTPORTAL_URL env)")
    parser.add_argument("--project", help="RP project name (or ATEX_REPORTPORTAL_PROJECT env)")
    parser.add_argument("--token", help="RP API token (or ATEX_REPORTPORTAL_TOKEN env)")
    parser.add_argument("--no-ssl-verify", help="disable SSL cert checking", action="store_true")
    cmds = parser.add_subparsers(
        dest="_cmd", help="RP helper to run", metavar="<cmd>", required=True,
    )

    cmd = cmds.add_parser(
        "launch-start", aliases=("start",),
        help="start (create) a new launch, print its UUID",
    )
    cmd.add_argument("--name", "-n", help="launch name", required=True)
    cmd.add_argument("--description", help="launch description")

    cmd = cmds.add_parser(
        "launch-finish", aliases=("finish",),
        help="finish a launch by its UUID",
    )
    cmd.add_argument("uuid", help="launch UUID")

    cmd = cmds.add_parser(
        "launch-list", aliases=("ls",),
        help="list launches in the project",
    )
    cmd.add_argument("--page-size", help="launches per page", type=int)
    cmd.add_argument("--max-pages", help="max pages to fetch", type=int, default=1)


def main(args):
    match args._cmd:
        case "launch-start" | "start":
            launch_start(args)
        case "launch-finish" | "finish":
            launch_finish(args)
        case "launch-list" | "ls":
            launch_list(args)
        case _:
            raise RuntimeError(f"unknown args: {args}")


CLI_SPEC = {
    "aliases": ("rp",),
    "help": "various utils for ReportPortal",
    "args": parse_args,
    "main": main,
}
