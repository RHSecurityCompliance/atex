import re
import collections
from pathlib import Path

# from system-wide sys.path
import fmf


def listlike(data, key):
    """
    Get a piece of fmf metadata as an iterable regardless of whether it was
    defined as a dict or a list.

    This is needed because many fmf metadata keys can be used either as
        some_key: 123
    or as lists via YAML syntax
        some_key:
          - 123
          - 456
    and, for simplicity, we want to always deal with lists (iterables).
    """
    if value := data.get(key):
        return value if isinstance(value, list) else (value,)
    else:
        return ()


class FMFTests:
    """
    FMF test metadata parsed from on-disk metadata using a specific plan name,
    with all metadata dictionaries for all nodes being adjusted by that plan
    and (optionally) a specified context.
    """
    # TODO: usage example ^^^^

    def __init__(
        self, fmf_tree, plan_name=None, *,
        names=None, filters=None, conditions=None, excludes=None,
        context=None,
    ):
        """
        'fmf_tree' is filesystem path somewhere inside fmf metadata tree,
        or a root fmf.Tree instance.

        'plan_name' is fmf identifier (like /some/thing) of a tmt plan
        to use for discovering tests. If None, a dummy (empty) plan is used.

        'names', 'filters', 'conditions' and 'exclude' (all tuple/list)
        are fmf tree filters (resolved by the fmf module), overriding any
        existing tree filters in the plan's discover phase specifies, where:

            'names' are test regexes like ["/some/test", "/another/test"]

            'filters' are fmf-style filter expressions, as documented on
            https://fmf.readthedocs.io/en/stable/modules.html#fmf.filter

            'conditions' are python expressions whose namespace locals()
            are set up to be a dictionary of the fmf tree. When any of the
            expressions returns True, the tree is returned, ie.
                ["environment['FOO'] == 'BAR'"]
                ["'enabled' not in locals() or enabled"]
            Note that KeyError is silently ignored and treated as False.

            'excludes' are test regexes to exclude, format same as 'names'

        'context' is a dict like {'distro': 'rhel-9.6'} used for additional
        adjustment of the discovered fmf metadata.
        """
        # list of packages to install, as extracted from plan
        self.prepare_pkgs = []
        # list of scripts to run, as extracted from plan
        self.prepare_scripts = []
        self.finish_scripts = []
        # dict of environment, as extracted from plan
        self.plan_env = {}
        # dict indexed by test name, value is dict with fmf-parsed metadata
        self.tests = {}
        # dict indexed by test name, value is pathlib.Path of relative path
        # of the fmf metadata root towards the test metadata location
        self.test_dirs = {}

        # fmf.Context instance, as used for test discovery
        context = fmf.Context(**context) if context else fmf.Context()
        # allow the user to pass fmf.Tree directly, greatly speeding up the
        # instantiation of multiple FMFTests instances
        tree = fmf_tree.copy() if isinstance(fmf_tree, fmf.Tree) else fmf.Tree(fmf_tree)
        tree.adjust(context=context)

        # Path of the metadata root
        self.root = Path(tree.root)

        # lookup the plan first
        if plan_name:
            plan = tree.find(plan_name)
            if not plan:
                raise ValueError(f"plan {plan_name} not found in {tree.root}")
            if "test" in plan.data:
                raise ValueError(f"plan {plan_name} appears to be a test")
        # fall back to a dummy plan
        else:
            class plan:  # noqa: N801
                data = {}

        # gather and merge plan-defined environment variables
        #
        # environment:
        #  - FOO: BAR
        #    BAR: BAZ
        for entry in listlike(plan.data, "environment"):
            self.plan_env.update(entry)

        # gather all prepare scripts / packages
        #
        # prepare:
        #   - how: install
        #     package:
        #       - some-rpm-name
        #   - how: shell
        #     script:
        #       - some-command
        for entry in listlike(plan.data, "prepare"):
            if entry.get("how") == "install":
                self.prepare_pkgs += listlike(entry, "package")
            elif entry.get("how") == "shell":
                self.prepare_scripts += listlike(entry, "script")

        # gather all finish scripts, same as prepare scripts
        for entry in listlike(plan.data, "finish"):
            if entry.get("how") == "shell":
                self.finish_scripts += listlike(entry, "script")

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
        plan_filters = collections.defaultdict(list)
        for entry in listlike(plan.data, "discover"):
            if entry.get("how") != "fmf":
                continue
            for meta_name in ("filter", "test", "exclude"):
                if value := listlike(entry, meta_name):
                    plan_filters[meta_name] += value

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

        # actually discover the tests
        for child in tree.prune(**prune_kwargs):
            # excludes not supported by .prune(), we have to do it here
            if excludes and any(re.match(x, child.name) for x in excludes):
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
            # after adjusting above, any adjusts are useless, free some space
            if "adjust" in child.data:
                del child.data["adjust"]

            self.tests[child.name] = child.data
            # child.sources ie. ['/abs/path/to/some.fmf', '/abs/path/to/some/node.fmf']
            self.test_dirs[child.name] = \
                Path(child.sources[-1]).parent.relative_to(self.root)


def test_pkg_requires(data, key="require"):
    """
    Yield RPM package names specified by test 'data' (fmf metadata dict)
    in the metadata 'key' (require or recommend), ignoring any non-RPM-package
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
    a class FMFTests instance 'fmf_tests', ignoring any non-RPM-package
    requires/recommends.
    """
    # use a set to avoid duplicates
    pkgs = set()
    pkgs.update(fmf_tests.prepare_pkgs)
    for data in fmf_tests.tests.values():
        pkgs.update(test_pkg_requires(data, key))
    yield from pkgs


# Some extra notes for fmf.prune() arguments:
#
# Set 'names' to filter by a list of fmf node names, ie.
#     ['/some/test', '/another/test']
#
# Set 'filters' to filter by a list of fmf-style filter expressions, see
#     https://fmf.readthedocs.io/en/stable/modules.html#fmf.filter
#
# Set 'conditions' to filter by a list of python expressions whose namespace
# locals() are set up to be a dictionary of the tree. When any of the
# expressions returns True, the tree is returned, ie.
#     ['environment["FOO"] == "BAR"']
#     ['"enabled" not in locals() or enabled']
# Note that KeyError is silently ignored and treated as False.
#
# Set 'context' to a dictionary to post-process the tree metadata with
# adjust expressions (that may be present in a tree) using the specified
# context. Any other filters are applied afterwards to allow modification
# of tree metadata by the adjust expressions. Ie.
#     {'distro': 'rhel-9.6.0', 'arch': 'x86_64'}
