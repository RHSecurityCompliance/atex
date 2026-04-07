import pytest

from atex.executor.fmf import discover

fmf_tests = None


@pytest.fixture(scope="module", autouse=True)
def setup_parse_global_tests():
    global fmf_tests
    fmf_tests = discover("fmf_trees/metadata")


def test_simple():
    assert "/simple" in fmf_tests.data
    data = fmf_tests.data["/simple"]
    assert data["summary"] == "Simple test"
    assert data["test"] == "./test.sh"
    assert data["require"] == "some_package"
    assert data["duration"] == "5m"


def test_nontest():
    assert "/nontest" not in fmf_tests.data
    assert "/story" not in fmf_tests.data
    assert "/manual" not in fmf_tests.data


def test_disabled():
    assert "/disabled" not in fmf_tests.data


def test_virtual():
    # only leaf nodes
    assert "/virtual" not in fmf_tests.data
    assert "/virtual/subtest" in fmf_tests.data
    data = fmf_tests.data["/virtual/subtest"]
    assert data["test"] == "./test.sh"


def test_source_dir():
    subtest = fmf_tests.dirs["/virtual/subtest"]
    nested_subtest = fmf_tests.dirs["/virtual/nested/subtest"]
    assert subtest == nested_subtest  # defined in the same dir


def test_inherit():
    # even though it defines 'test:', /inherit should not exist
    # because it is not a leaf node
    assert "/inherit" not in fmf_tests.data
    assert "/inherit/child" in fmf_tests.data
    data = fmf_tests.data["/inherit/child"]
    assert "require" in data
    assert "foo bar" in data["require"]
    assert "baz" in data["require"]


def test_filter_plan():
    fmf_tests = discover("fmf_trees/metadata", "/plans/filtered")
    assert "/filters/filter1" not in fmf_tests.data
    assert "/filters/filter2" not in fmf_tests.data
    assert "/filters/filter3" not in fmf_tests.data
    assert "/filters/filter4" in fmf_tests.data
    assert "/filters/filter5" in fmf_tests.data
    assert "/simple" not in fmf_tests.data


def test_filter_args():
    fmf_tests = discover(
        "fmf_trees/metadata",
        filters=("tag:-tagged",),
        names=("/filters/filter3", "/filters/filter4"),
        excludes=("/filters/filter3",),
        conditions=("'extra_foobar' not in locals()",),
    )
    assert "/filters/filter1" not in fmf_tests.data
    assert "/filters/filter2" not in fmf_tests.data
    assert "/filters/filter3" not in fmf_tests.data
    assert "/filters/filter4" in fmf_tests.data
    assert "/filters/filter5" not in fmf_tests.data
    assert "/simple" not in fmf_tests.data


def test_filter_priority():
    # args override plan
    fmf_tests = discover(
        "fmf_trees/metadata",
        "/plans/filtered",
        names=("/filter1", "/filter2"),
    )
    # /filter1,3 are still excluded via filters/exclude
    assert "/filters/filter1" not in fmf_tests.data
    assert "/filters/filter2" in fmf_tests.data
    assert "/filters/filter3" not in fmf_tests.data
    assert "/filters/filter4" not in fmf_tests.data
    assert "/filters/filter5" not in fmf_tests.data
    assert "/simple" not in fmf_tests.data


def test_adjust():
    fmf_tests = discover(
        "fmf_trees/metadata",
        context={"distro": "fedora-2", "arch": "x86_64"},
    )
    no_foobar = fmf_tests.data["/adjusted/no_foobar"]
    assert "extra_foobar" not in no_foobar
    equals = fmf_tests.data["/adjusted/equals"]
    assert "extra_foobar" in equals
    assert equals["extra_foobar"] == 123
    greater_lesser = fmf_tests.data["/adjusted/greater_lesser"]
    assert "extra_foobar" in greater_lesser
    listlike = fmf_tests.data["/adjusted/listlike"]
    assert "extra_foobar" in listlike
    assert "extra_baz" in listlike


def test_environment():
    fmf_tests = discover("fmf_trees/metadata", "/plans/with_env")
    plan_env = fmf_tests.plan.get("environment")
    # no test: defined in the parent
    assert "/environment" in fmf_tests.data
    data = fmf_tests.data["/environment"]
    assert "environment" in data
    # plan env not merged with tests by default
    assert "VAR_FROM_TEST" in data["environment"]
    assert "VAR_FROM_PLAN" not in data["environment"]
    # instead, it is provided separately
    assert "VAR_FROM_TEST" not in plan_env
    assert "VAR_FROM_PLAN" in plan_env


def test_existing_tree():
    # external fmf module
    import fmf  # noqa: PLC0415
    tree = fmf.Tree("fmf_trees/metadata")
    fmf_tests = discover(tree)
    assert "/simple" in fmf_tests.data
