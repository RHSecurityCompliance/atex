import dataclasses
import re
from pathlib import Path


@dataclasses.dataclass
class FMFTests:
    """
    Holds tests and their metadata, used for execution by FMFExecutor.

    All metadata are always fully 'adjust'ed, eg. in their final form.

    - `plan` - dict holding fmf metadata of the plan that was used to
      discover the tests.

    - `data` - dict, indexed by test name, holding fmf test metadata.

    - `sources` - dict, indexed by test name, holding relative paths (strings)
      of each test's definition directory, eg. where the .fmf file defining
      the test is.

      Useful when deciding CWD for test execution.

    - `root` - Path to the fmf metadata tree root with discovered tests.

      Useful when uploading or copying the test files.
    """
    plan: dict
    data: dict
    sources: dict
    root: Path

    def __str__(self):
        class_name = self.__class__.__name__
        tests = len(self.data)
        root = str(self.root)
        return f"{class_name}(<holding {tests} tests>, root={root})"


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
        # skip type:library and type:file
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
