import re
import collections
from pathlib import Path

# from system-wide sys.path
import fmf

# name: fmf path to the test as string, ie. /some/test
# data: dict of the parsed fmf metadata (ie. {'tag': ... , 'environment': ...})
# dir:  relative pathlib.Path of the test .fmf to repo root, ie. some/test
#       (may be different from name for "virtual" tests that share the same dir)
FMFTest = collections.namedtuple("FMFTest", ["name", "data", "dir"])


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

    def __init__(self, fmf_tree, plan_name, context=None):
        """
        'fmf_tree' is filesystem path somewhere inside fmf metadata tree,
        or a root fmf.Tree instance.

        'plan_name' is fmf identifier (like /some/thing) of a tmt plan
        to use for discovering tests.

        'context' is a dict like {'distro': 'rhel-9.6'} used for filtering
        discovered tests.
        """
        # list of packages to install, as extracted from plan
        self.prepare_pkgs = []
        # list of scripts to run, as extracted from plan
        self.prepare_scripts = []
        # dict of environment, as extracted from plan
        self.plan_env = {}
        # dict indexed by test name, value is dict with fmf-parsed metadata
        self.tests = {}
        # dict indexed by test name, value is pathlib.Path of relative path
        # of the fmf metadata root towards the test metadata location
        self.test_dirs = {}

        tree = fmf_tree.copy() if isinstance(fmf_tree, fmf.Tree) else fmf.Tree(fmf_tree)
        ctx = fmf.Context(**context) if context else fmf.Context()
        tree.adjust(context=ctx)

        self.fmf_root = tree.root

        # lookup the plan first
        plan = tree.find(plan_name)
        if not plan:
            raise ValueError(f"plan {plan_name} not found in {tree.root}")
        if "test" in plan.data:
            raise ValueError(f"plan {plan_name} appears to be a test")

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
            if "how" not in entry:
                continue
            if entry["how"] == "install":
                self.prepare_pkgs += listlike(entry, "package")
            elif entry["how"] == "shell":
                self.prepare_scripts += listlike(entry, "script")

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
        if "discover" in plan.data:
            discover = plan.data["discover"]
            if not isinstance(discover, list):
                discover = (discover,)

            for entry in discover:
                if entry.get("how") != "fmf":
                    continue

                filtering = {}
                for meta_name in ("filter", "test", "exclude"):
                    if value := listlike(entry, meta_name):
                        filtering[meta_name] = value

                children = tree.prune(
                    names=filtering.get("test"),
                    filters=filtering.get("filter"),
                )
                for child in children:
                    # excludes not supported by .prune(), we have to do it here
                    excludes = filtering.get("exclude")
                    if excludes and any(re.match(x, child.name) for x in excludes):
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
                        Path(child.sources[-1]).parent.relative_to(self.fmf_root)

    def as_fmftest(self, name):
        return FMFTest(name, self.tests[name], self.test_dirs[name])

    def as_fmftests(self):
        for name, data in self.tests.items():
            yield FMFTest(name, data, self.test_dirs[name])

    def match(self, regex):
        """
        Return an iterable of FMFTest instances with test names matching the
        specified regex via re.match(), just like how 'tmt' discovers tests.
        """
        for name, data in self.tests.items():
            if re.match(regex, name):
                yield FMFTest(name, data, self.test_dirs[name])


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

Platform = collections.namedtuple("Platform", ["distro", "arch"])


def combine_platforms(fmf_path, plan_name, platforms):
    # TODO: document
    fmf_tests = {}
    tree = fmf.Tree(fmf_path)
    for platform in platforms:
        context = {"distro": platform.distro, "arch": platform.arch}
        fmf_tests[platform] = FMFTests(tree, plan_name, context=context)
    return fmf_tests

# TODO: in Orchestrator, when a Provisioner becomes free, have it pick a test
#       from the appropriate tests[platform] per the Provisioner's platform
