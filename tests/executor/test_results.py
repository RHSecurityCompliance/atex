import os
import sys
import json
from pathlib import Path

from atex.fmf import FMFTests
from atex.executor import Executor
from atex.executor.testcontrol import BadReportJSONError, BadControlError


def run_fmf_test(provisioner, tmp_dir, *, read_results=True):
    test = sys._getframe(1).f_code.co_name  # same as parent func name
    fmf_tests = FMFTests("fmf_tree", plan_name="/results/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with Executor(fmf_tests, remote) as e:
        e.upload_tests()
        e.run_test(f"/results/{test}", tmp_dir)
    if read_results:
        results = (tmp_dir / "results").read_text()
        print(f"=== RESULTS ===\n{results}\n===============")
        return results


# -----------------------------------------------------------------------------
def test_noresult_pass(provisioner, tmp_dir):
    """Automatic fallback result based on exit code."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass", "testout": "output.txt"}  # default
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output == "passing the script\n"


def test_noresult_fail(provisioner, tmp_dir):
    """Automatic fallback result based on exit code."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "fail", "testout": "output.txt"}
    output = (tmp_dir / "files" / "output.txt").read_text()
    assert output == "failing the script\n"


# -----------------------------------------------------------------------------
def test_trivial(provisioner, tmp_dir):
    """Trivial test-reported result."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}
    # no automatic testout created
    files = list((tmp_dir / "files").iterdir())
    assert len(files) == 0


def test_trivial_multiline(provisioner, tmp_dir):
    """Trivial test-reported result as a multi-line string."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}
    # no automatic testout created
    files = list((tmp_dir / "files").iterdir())
    assert len(files) == 0


def test_trivial_repeated(provisioner, tmp_dir):
    """Multiple test-reported results for the test itself."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {"status": "pass"}
    assert json.loads(second) == {"status": "fail"}


def test_trivial_exit_mismatch(provisioner, tmp_dir):
    """Ensure that reported result is preferred and exit code ignored."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}


# -----------------------------------------------------------------------------
def test_subtest(provisioner, tmp_dir):
    """Basic subtest reporting."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {"status": "fail", "name": "subtest"}
    assert json.loads(second) == {"status": "pass"}


def test_subtest_nested(provisioner, tmp_dir):
    """Subresult using sub/dir/s."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {"status": "fail", "name": "sub/res/ult"}
    assert json.loads(second) == {"status": "pass"}


def test_subtest_no_status(provisioner, tmp_dir):
    """Status-less subtests are also valid."""
    results = run_fmf_test(provisioner, tmp_dir)
    # 2 because we didn't provide a result for the test itself,
    # so a fallback result is used
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {"name": "subtest"}
    assert json.loads(second) == {"status": "pass", "testout": "output.txt"}


# -----------------------------------------------------------------------------
def test_files(provisioner, tmp_dir):
    """Basic binary file transfer."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [{"name": "some_file", "length": 5}],
    }
    output = (tmp_dir / "files" / "some_file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


def test_files_upload(provisioner, tmp_dir):
    """Round-trip of a binary file via test transfer + result upload."""
    rand_file_bytes = Path("fmf_tree/results/randfile").read_bytes()
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [{"name": "rand_file", "length": len(rand_file_bytes)}],
    }
    output = (tmp_dir / "files" / "rand_file").read_bytes()
    assert output == rand_file_bytes


def test_files_subpath(provisioner, tmp_dir):
    """Transfer to a subdirectory (file name contains slashes)."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [{"name": "some/file", "length": 5}],
    }
    output = (tmp_dir / "files" / "some" / "file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


def test_files_multiple(provisioner, tmp_dir):
    """Transfer of multiple files in one result."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [
            {"name": "first_file", "length": 2},
            {"name": "second_file", "length": 3},
        ],
    }
    first = (tmp_dir / "files" / "first_file").read_bytes()
    assert first == b"\x00\x10"
    second = (tmp_dir / "files" / "second_file").read_bytes()
    assert second == b"\x20\x30\x40"


def test_files_multiple_results(provisioner, tmp_dir):
    """Transfer of multiple files in multiple results."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {
        "status": "fail",
        "files": [{"name": "first_file", "length": 2}],
    }
    assert json.loads(second) == {
        "status": "pass",
        "files": [{"name": "second_file", "length": 3}],
    }
    first = (tmp_dir / "files" / "first_file").read_bytes()
    assert first == b"\x00\x10"
    second = (tmp_dir / "files" / "second_file").read_bytes()
    assert second == b"\x20\x30\x40"


def test_files_append(provisioner, tmp_dir):
    """Appending to the same file in one result."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [
            {"name": "one_file", "length": 2},
            {"name": "one_file", "length": 3},
        ],
    }
    output = (tmp_dir / "files" / "one_file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


def test_files_subtest(provisioner, tmp_dir):
    """Transfer to a subdirectory (caused by a subtest)."""
    results = run_fmf_test(provisioner, tmp_dir)
    # 2 because we didn't provide a result for the test itself,
    # so a fallback result is used
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {
        "status": "pass",
        "name": "sub/res/ult",
        "files": [{"name": "some_file", "length": 5}],
    }
    assert json.loads(second) == {"status": "pass", "testout": "output.txt"}
    output = (tmp_dir / "files" / "sub" / "res" / "ult" / "some_file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


# -----------------------------------------------------------------------------
def test_custom_keys(provisioner, tmp_dir):
    """Using user-defined JSON metadata in the result."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "custom_string": "some string",
        "custom_number": 123,
        "custom_list": [1, 2, 3],
        "custom_object": {
            "some key": "some value",
        },
    }


# -----------------------------------------------------------------------------
def test_partial(provisioner, tmp_dir):
    """Test partial:True reporting."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}
    # no automatic testout created
    files = list((tmp_dir / "files").iterdir())
    assert len(files) == 0


def test_partial_false(provisioner, tmp_dir):
    """Explicit partial:False reporting."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}
    # no automatic testout created
    files = list((tmp_dir / "files").iterdir())
    assert len(files) == 0


def test_partial_abrupt(provisioner, tmp_dir):
    """Abrupt test exit relying on partial:True."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "fail"}
    # no automatic testout created
    files = list((tmp_dir / "files").iterdir())
    assert len(files) == 0


def test_partial_merging(provisioner, tmp_dir):
    """Merging of multiple partial:True result keys."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "attr1": "value1",
        "attr2": "value2",
    }


def test_partial_deleting(provisioner, tmp_dir):
    """Deleting keys via partial:True using a null value."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}


def test_partial_overwriting(provisioner, tmp_dir):
    """Appending / updating of partial:True keys based on value type."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "custom_string": "second string",
        "custom_number": 456,
        "custom_list": [1, 2, 3, 4, 5, 6],
        "custom_object": {
            "first key": "first value",
            "second key": "second value",
        },
    }


def test_partial_subtests(provisioner, tmp_dir):
    """Applying partial:True to a subtest."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 3
    first, second, third = results.rstrip("\n").split("\n")
    # sub1 finishes first (partial:True followed by non-partial)
    assert json.loads(first) == {"status": "pass", "name": "sub1"}
    # followed by a non-partial result
    assert json.loads(second) == {"status": "pass"}
    # followed by abrupt test end and replayed sub2 as partial:True
    assert json.loads(third) == {"status": "error", "name": "sub2"}


def test_partial_files(provisioner, tmp_dir):
    """Splitting two-file transfer across partial:True results."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [
            {"name": "first_file", "length": 2},
            {"name": "second_file", "length": 3},
        ],
    }
    first = (tmp_dir / "files" / "first_file").read_bytes()
    assert first == b"\x00\x10"
    second = (tmp_dir / "files" / "second_file").read_bytes()
    assert second == b"\x20\x30\x40"


def test_partial_files_append(provisioner, tmp_dir):
    """Appending to the same file across partial:True results."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [
            {"name": "one_file", "length": 2},
            {"name": "one_file", "length": 3},
        ],
    }
    output = (tmp_dir / "files" / "one_file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


# -----------------------------------------------------------------------------
def test_testout(provisioner, tmp_dir):
    """Manual testout:file specification."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "testout": "here.txt",
    }
    output = (tmp_dir / "files" / "here.txt").read_bytes()
    assert output == b"first line\nsecond line\n"
    # no automatic testout created
    assert not (tmp_dir / "files" / "output.txt").exists()


def test_testout_fallback(provisioner, tmp_dir):
    """Fallback testout if test doesn't report anything."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "testout": "output.txt",
    }
    output = (tmp_dir / "files" / "output.txt").read_bytes()
    assert output == b"some line\n"


def test_testout_partial(provisioner, tmp_dir):
    """Overwriting a partial:True specified testout:file."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "testout": "there.txt",
    }
    output = (tmp_dir / "files" / "there.txt").read_bytes()
    assert output == b"some line\n"
    # the partial:True entry should not exist
    assert not (tmp_dir / "files" / "here.txt").exists()
    # no automatic testout created
    assert not (tmp_dir / "files" / "output.txt").exists()


def test_testout_multiple(provisioner, tmp_dir):
    """Writing to multiple testouts using partial:True results."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {
        "status": "fail",
        "testout": "here.txt",
    }
    assert json.loads(second) == {
        "status": "pass",
        "testout": "there.txt",
    }
    first_output = (tmp_dir / "files" / "here.txt").read_bytes()
    assert first_output == b"some line\n"
    second_output = (tmp_dir / "files" / "there.txt").read_bytes()
    assert second_output == b"some line\n"
    # no automatic testout created
    assert not (tmp_dir / "files" / "output.txt").exists()


# -----------------------------------------------------------------------------
def test_bad_json(provisioner, tmp_dir):
    """Bad JSON result reported by a test."""
    try:
        run_fmf_test(provisioner, tmp_dir, read_results=False)
    except BadReportJSONError:
        pass


def test_empty_json(provisioner, tmp_dir):
    """Empty JSON result reported by a test."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {}


def test_no_status(provisioner, tmp_dir):
    """Result without status reported by a test."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {"attr1": "value1"}


def test_empty_files(provisioner, tmp_dir):
    """Empty files list in a result."""
    results = run_fmf_test(provisioner, tmp_dir)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [],
    }
    # no files uploaded
    files = list((tmp_dir / "files").iterdir())
    assert len(files) == 0


def test_no_file_data(provisioner, tmp_dir):
    """Test ending without providing promised file data."""
    os.environ["ATEX_DEBUG_NO_EXITCODE"] = "1"
    try:
        run_fmf_test(provisioner, tmp_dir, read_results=False)
        raise AssertionError("BadControlError should have triggered")
    except BadControlError as e:
        if str(e) != "EOF when reading data":
            raise
    finally:
        del os.environ["ATEX_DEBUG_NO_EXITCODE"]


def test_some_file_data(provisioner, tmp_dir):
    """Test ending without providing ALL promised file data."""
    os.environ["ATEX_DEBUG_NO_EXITCODE"] = "1"
    try:
        run_fmf_test(provisioner, tmp_dir, read_results=False)
        raise AssertionError("BadControlError should have triggered")
    except BadControlError as e:
        if str(e) != "EOF when reading data":
            raise
    finally:
        del os.environ["ATEX_DEBUG_NO_EXITCODE"]


def test_empty_testout(provisioner, tmp_dir):
    """Empty string for a testout:file name."""
    try:
        run_fmf_test(provisioner, tmp_dir, read_results=False)
        raise AssertionError("BadReportJSONError should have triggered")
    except BadReportJSONError as e:
        if str(e) != "'testout' specified, but empty":
            raise
