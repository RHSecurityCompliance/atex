from pathlib import Path

import fmf
import pytest

from atex.executor.fmf import discover
from atex.executor.fmf.discover import resolve_libraries


def test_single_section():
    """Single unnamed discover section discovers all tests without prefix."""
    fmf_tests = discover("fmf_trees/discover", plan="/plans/single", libraries=False)
    assert "/test_one" in fmf_tests.data
    assert "/test_two" in fmf_tests.data
    assert "/test_three" in fmf_tests.data
    assert "/test_with_lib" in fmf_tests.data
    assert "/test_with_path_lib" in fmf_tests.data
    assert "/subdir/test_nested" in fmf_tests.data
    assert len(fmf_tests.data) == 6


def test_multi_local_sections():
    """Two named sections with different tag filters produce prefixed names."""
    fmf_tests = discover(
        "fmf_trees/discover", plan="/plans/filtered", libraries=False,
    )
    # group_a section: test_one (group_a) and test_three (group_a, group_b)
    assert "/group_a/test_one" in fmf_tests.data
    assert "/group_a/test_three" in fmf_tests.data
    assert "/group_a/subdir/test_nested" in fmf_tests.data
    assert "/group_a/test_two" not in fmf_tests.data
    # group_b section: test_two (group_b) and test_three (group_a, group_b)
    assert "/group_b/test_two" in fmf_tests.data
    assert "/group_b/test_three" in fmf_tests.data
    assert "/group_b/test_one" not in fmf_tests.data
    # no unprefixed tests
    assert "/test_one" not in fmf_tests.data
    assert len(fmf_tests.data) == 5


def test_duplicate_sections():
    """Two identical sections produce every test twice under prefixes."""
    fmf_tests = discover(
        "fmf_trees/discover", plan="/plans/duplicate", libraries=False,
    )
    for name in (
        "/test_one", "/test_two", "/test_three", "/test_with_lib",
        "/test_with_path_lib", "/subdir/test_nested",
    ):
        assert f"/first{name}" in fmf_tests.data
        assert f"/second{name}" in fmf_tests.data
    assert len(fmf_tests.data) == 12
    # no unprefixed
    assert "/test_one" not in fmf_tests.data


def test_section_name_in_sources():
    """Sources paths include the section name prefix for named sections."""
    fmf_tests = discover(
        "fmf_trees/discover", plan="/plans/filtered", libraries=False,
    )
    assert fmf_tests.sources
    for name, source in fmf_tests.sources.items():
        section = name.split("/")[1]  # group_a or group_b
        assert source == section or source.startswith(f"{section}/")


def test_local_library_symlink():
    """In-tree library with nick + no url gets symlinked into libs/."""
    fmf_tests = discover("fmf_trees/discover", plan="/plans/single")
    target = fmf_tests.root / "libs" / "mylib" / "mylib"
    assert target.is_symlink()
    assert target.resolve().exists()
    # library's own dependencies should be propagated to the test
    test_data = fmf_tests.data["/test_with_lib"]
    requires = [r for r in test_data.get("require", []) if isinstance(r, str)]
    recommends = [r for r in test_data.get("recommend", []) if isinstance(r, str)]
    assert "some_dependency" in requires
    assert "optional_dependency" in recommends



def test_http_section():
    """One local + one HTTP section using beakerlib/yum."""
    try:
        fmf_tests = discover(
            "fmf_trees/discover", plan="/plans/with_http", libraries=False,
        )
    except fmf.utils.FetchError:
        pytest.skip("network unavailable for HTTP discover section")
    # local section tests
    assert "/local/test_one" in fmf_tests.data
    assert "/local/test_two" in fmf_tests.data
    # remote section should have discovered something from beakerlib/yum
    remote_tests = [n for n in fmf_tests.data if n.startswith("/remote/")]
    assert len(remote_tests) > 0


def test_absolute_path_library():
    """Library referenced via absolute path gets resolved into libs/."""
    extlib_path = str(Path("fmf_trees/discover/extlib").resolve())
    fmf_tests = discover(
        "fmf_trees/discover", plan="/plans/single",
        names=("/test_with_path_lib",),
    )
    # inject the path-based require (can't be in .fmf - absolute path varies)
    fmf_tests.data["/test_with_path_lib"]["require"] = [
        {"type": "library", "path": extlib_path, "name": "/extfunc"},
    ]
    # re-run library resolution on the modified data
    tree = fmf.Tree(str(fmf_tests.root))
    resolve_libraries(
        [fmf_tests.data["/test_with_path_lib"]], tree,
        fmf_tests.root / "libs", fmf.Context(),
    )
    # the library's own require should be added to the test's require
    test_data = fmf_tests.data["/test_with_path_lib"]
    requires = test_data.get("require", [])
    require_strings = [r for r in requires if isinstance(r, str)]
    assert "ext_dependency" in require_strings
    # library content should be at the expected path
    assert (fmf_tests.root / "libs" / "extlib" / "extfunc" / "main.fmf").exists()
