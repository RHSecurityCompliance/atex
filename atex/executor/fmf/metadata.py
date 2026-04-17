import dataclasses
import re
import shutil
from pathlib import Path, PurePath

import fmf  # from system-wide sys.path
import urllib3


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
    context=None, libraries=False,
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

    - `libraries` enables resolution of beakerlib library dependencies
      ('require: type: library' and old 'library(foo/bar)' syntax).\
      When True, libraries are cloned into 'libs' under the fmf tree root,
      and any RPM dependencies found in their metadata are added to the
      requiring test's require/recommend metadata.

      NOTE that **this modifies the on-disk fmf tree** by adding 'libs'.
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

    if libraries:
        resolve_libraries(tests_data.values(), tree, context)

    return FMFTests(
        plan=plan_data,
        data=tests_data,
        dirs=tests_dirs,
        root=Path(tree.root),
    )


_http = urllib3.PoolManager()


def resolve_libraries(tests_data, tests_tree, context):
    """
    Resolve all beakerlib libraries for all tests defined by `tests_data`
    (as parsed fmf metadata) inside (root) `tests_tree`.

    If fetching a remote fmf definition, adjust it using `context`.
    """
    libs_dir = Path(tests_tree.root) / "libs"

    # used to avoid re-parsing of library metadata when updating multiple tests;
    # also used to resolve circular deps by:
    # - first storing pre-recursion values
    # - updating them after recursion
    # - checking if the cache has anything - if so, avoid recursing
    cache = {}

    def resolve(entry):
        new_require = []
        new_recommend = []

        def update_from_cache(nick, name):
            key = f"{nick}{name}"
            if key in cache:
                cached_require, cached_recommend = cache[key]
                new_require.extend(cached_require)
                new_recommend.extend(cached_recommend)
                return True
            return False

        for recommend in listlike(entry, "recommend"):
            if not isinstance(recommend, str):
                t = type(recommend).__name__
                raise ValueError(f"non-string '{t}' not allowed in 'recommend': {recommend}")
            new_recommend.append(recommend)

        for require in listlike(entry, "require"):
            # non-library dict - ie. type:file, just pass it along
            if isinstance(require, dict) and require.get("type", "library") != "library":
                new_require.append(require)
                continue

            # any string - pkg name or library(foo/bar)
            elif isinstance(require, str):
                # old-style library(foo/bar)
                if m := re.match(r"library\(([^/]+)(/[^)]+)\)$", require):
                    nick, name = m.groups()
                    if update_from_cache(nick, name):
                        continue

                    target = libs_dir / nick / name.lstrip("/")
                    if target.exists():
                        raise ValueError(f"{require} already exists in {target}")

                    url = f"https://github.com/beakerlib/{nick}"
                    # query using urllib3 to avoid git-clone asking for password
                    response = _http.request("HEAD", url, redirect=False)
                    # if it exists, define a Tree.node using it
                    if response.status < 400:
                        node = fmf.Tree.node({"url": url, "name": name})
                        node.adjust(context=context)
                        source = Path(node.root) / node.name.lstrip("/")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(source, target, symlinks=True)

                    # else leave it for the package manager to install
                    else:
                        new_require.append(require)
                        continue

                # pkg name
                else:
                    new_require.append(require)
                    continue

            # no fetching - reuse existing in-tree library
            elif isinstance(require, dict) and "url" not in require and "path" not in require:
                # nick must be defined
                if not (nick := require.get("nick")):
                    raise ValueError(f"'nick' must be defined for url-less: {require}")
                # do not default to '/' since it makes no sense in a tree with tests
                node = tests_tree.find(require.get("name"))
                if node is None:
                    raise ValueError(f"couldn't find library node: {require}")
                if update_from_cache(nick, node.name):
                    continue

                target = libs_dir / nick / node.name.lstrip("/")
                # referencing a library inside the tests tree, but not in libs/
                # - just symlink it to libs/
                if not target.exists():
                    source = Path(node.root) / node.name.lstrip("/")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(source.relative_to(target.parent, walk_up=True))

            # finally, a valid remote require: type: library
            elif isinstance(require, dict):
                name = require.get("name", "/")
                if not (nick := require.get("nick")):
                    if "url" in require:
                        url = require["url"].rstrip("/")
                        # nick is basename of the url, without optional .git
                        nick = url.rpartition("/")[2] if "/" in url else url
                        nick = nick.removesuffix(".git")
                    elif "path" in require:
                        # nick is basename of the path
                        nick = Path(require["path"]).name

                if update_from_cache(nick, name):
                    continue

                target = libs_dir / nick / name.lstrip("/")
                if target.exists():
                    raise ValueError(f"{require} already exists in {target}")

                # use fmf-native cloning/fetching
                node = fmf.Tree.node(require)
                node.adjust(context=context)
                source = Path(node.root) / node.name.lstrip("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, target, symlinks=True)

            # invalid require?
            else:
                raise ValueError(f"invalid require (bad type?): {require}")

            # recurse into the library's own deps, with a sentinel
            # for circular dependency protection
            key = f"{nick}{node.name}"
            cache[key] = ((), ())
            node_require, node_recommend = resolve(node.data)
            cache[key] = (node_require, node_recommend)
            new_require += node_require
            new_recommend += node_recommend

        return (new_require, new_recommend)

    for test_data in tests_data:
        new_require, new_recommend = resolve(test_data)
        test_data["require"] = new_require
        test_data["recommend"] = new_recommend


def duration_to_seconds(string):
    string = str(string)  # just in case the YAML had an integer
    m = re.fullmatch(r"([0-9]+)([mhds]?)", string)
    if not m:
        raise ValueError(f"invalid fmf duration format: {string}")
    length, unit = m.groups()
    match unit:
        case "m":
            return int(length) * 60
        case "h":
            return int(length) * 60 * 60
        case "d":
            return int(length) * 60 * 60 * 24
        case _:
            return int(length)


def test_pkg_requires(data, key="require"):
    """
    Yield RPM package names specified by test `data` (fmf metadata dict)
    in the metadata `key` (require or recommend), ignoring any non-RPM-package
    requires/recommends.
    """
    for entry in listlike(data, key):
        # skip type:library and type:path
        if isinstance(entry, str):
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
