import dataclasses
import re
from pathlib import Path, PurePath

# from system-wide sys.path
import fmf


@dataclasses.dataclass
class FMFTests:
    """
    Holds tests and their metadata, used for execution by FMFExecutor.

    All metadata are always fully 'adjust'ed, eg. in their final form.

    - `plan` - dict holding fmf metadata of the plan that was used to
      discover the tests.

    - `data` - dict, indexed by test name, holding fmf test metadata.

    - `dirs` - dict, indexed by test name, holding relative paths (strings)
      of each test's definition directory, eg. where the .fmf file defining
      the test is.

      Useful when deciding CWD for test execution.

    - `root` - Path to the fmf metadata tree root where the tests were
      discovered.

      Useful when uploading or copying the test files.
    """
    plan: dict
    data: dict
    dirs: dict
    root: Path


def listlike(data, key):
    """
    Get a piece of fmf metadata as a sequence, regardless of whether it was
    defined via a dict-value-like YAML syntax or a list-like syntax.

    This is needed because many fmf metadata keys can be used either as

        some_key: 123

    or as lists via YAML syntax

        some_key:
          - 123
          - 456

    and, for simplicity, we want to always deal with iterables/sequences.
    """
    if (value := data.get(key)) is not None:
        return value if isinstance(value, list) else (value,)
    else:
        return ()


def discover(fmf_tree, plan=None, *,
    names=None, filters=None, conditions=None, excludes=None,
    context=None,
):
    """
    Discover fmf tests in an `fmf_tree` (repository) location, using
    tmt `plan` for filtering and additional metadata, and return a fully
    resolved and filled-in FMFTests instance.

    - `fmf_tree` is filesystem path somewhere inside fmf metadata tree,
      or a root fmf.Tree instance.

    - `plan` is fmf identifier (like `/some/plan`) of a tmt plan
      to use for discovering tests. If None, a dummy (empty) plan is used.

    - `names`, `filters`, `conditions` and `excludes` (all tuple/list)
      are fmf tree filters (resolved by the fmf module), overriding any
      existing tree filters the plan's discover phase specifies, where:

        - `names` are test regexes like `["/some/test", "/another/test"]`.

        - `filters` are fmf-style filter expressions, as documented on
          https://fmf.readthedocs.io/en/stable/modules.html#fmf.filter

        - `conditions` are python expressions whose namespace `locals()`
          are set up to be a dictionary of the fmf tree. When any of the
          expressions returns `True`, the tree is returned, ie.

              ["environment['FOO'] == 'BAR'"]
              ["'enabled' not in locals() or enabled"]

          Note that KeyError is silently ignored and treated as `False`.

        - `excludes` are test regexes to exclude, format same as `names`.

    - `context` is a dict like `{'distro': 'rhel-9.6'}` used for additional
      adjustment of the discovered fmf metadata.
    """
    # fmf.Context instance, as used for test discovery
    context = fmf.Context(**context) if context else fmf.Context()

    # allow the user to pass fmf.Tree directly, greatly speeding up the
    # instantiation of multiple FMFTests instances
    tree = fmf_tree.copy() if isinstance(fmf_tree, fmf.Tree) else fmf.Tree(fmf_tree)
    tree.adjust(context=context)

    # lookup the plan first
    if plan:
        plan_node = tree.find(plan)
        if not plan_node:
            raise ValueError(f"plan {plan} not found in {tree.root}")
        if "test" in plan_node.data:
            raise ValueError(f"plan {plan} appears to be a test")
        if plan_node.children:
            children = ", ".join(plan_node.children)
            raise ValueError(f"'{plan}' matches multiple plans: {children}")
        plan_data = plan_node.data
    # fall back to dummy plan data
    else:
        plan_data = {}

    # gather all tests selected by the plan
    #
    # discover:
    #   - how: fmf
    #     filter:
    #       - tag:some_tag
    #     test:
    #       - some-test-regex
    #     exclude:
    #       - some-test-regex
    plan_filters = {}
    for entry in listlike(plan_data, "discover"):
        if entry.get("how") != "fmf":
            continue
        for meta_name in ("filter", "test", "exclude"):
            if value := listlike(entry, meta_name):
                if meta_name in plan_filters:
                    plan_filters[meta_name] += value
                else:
                    plan_filters[meta_name] = list(value)

    prune_kwargs = {}
    if names:
        prune_kwargs["names"] = names
    elif "test" in plan_filters:
        prune_kwargs["names"] = plan_filters["test"]
    if filters:
        prune_kwargs["filters"] = filters
    elif "filter" in plan_filters:
        prune_kwargs["filters"] = plan_filters["filter"]
    if conditions:
        prune_kwargs["conditions"] = conditions
    if not excludes:
        excludes = plan_filters.get("exclude")

    tests_data = {}
    tests_dirs = {}

    # actually discover the tests
    for child in tree.prune(**prune_kwargs):
        # excludes not supported by .prune(), we have to do it here
        if excludes and any(re.search(x, child.name) for x in excludes):
            continue
        # only tests
        if "test" not in child.data:
            continue
        # only enabled tests
        if "enabled" in child.data and not child.data["enabled"]:
            continue
        # no manual tests and no stories
        if child.data.get("manual") or child.data.get("story"):
            continue
        # adjusting was already done once, prevent accidental repeated adjust
        if "adjust" in child.data:
            del child.data["adjust"]

        tests_data[child.name] = child.data
        # child.sources ie. ['/abs/path/to/some.fmf', '/abs/path/to/some/node.fmf']
        tests_dirs[child.name] = str(PurePath(child.sources[-1]).parent.relative_to(tree.root))

    return FMFTests(
        plan=plan_data,
        data=tests_data,
        dirs=tests_dirs,
        root=Path(tree.root),
    )


def duration_to_seconds(string):
    string = str(string)  # just in case the YAML had an integer
    match = re.fullmatch(r"([0-9]+)([mhds]?)", string)
    if not match:
        raise ValueError(f"invalid fmf duration format: {string}")
    length, unit = match.groups()
    if unit == "m":
        return int(length)*60
    elif unit == "h":
        return int(length)*60*60
    elif unit == "d":
        return int(length)*60*60*24
    else:
        return int(length)


def test_pkg_requires(data, key="require"):
    """
    Yield RPM package names specified by test `data` (fmf metadata dict)
    in the metadata `key` (require or recommend), ignoring any non-RPM-package
    requires/recommends.
    """
    for entry in listlike(data, key):
        # skip type:library and type:path
        if not isinstance(entry, str):
            continue
        # skip "fake RPMs" that begin with 'library('
        if entry.startswith("library("):
            continue
        yield entry


def all_pkg_requires(fmf_tests, key="require"):
    """
    Yield RPM package names from the plan and all tests discovered by
    a class FMFTests instance `fmf_tests`, ignoring any non-RPM-package
    requires/recommends.
    """
    # use a set to avoid duplicates
    pkgs = set()
    for entry in listlike(fmf_tests.plan, "prepare"):
        if entry.get("how") == "install":
            pkgs.update(listlike(entry, "package"))
    for data in fmf_tests.data.values():
        pkgs.update(test_pkg_requires(data, key))
    yield from pkgs
