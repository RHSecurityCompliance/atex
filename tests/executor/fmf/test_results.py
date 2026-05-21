import json
import os
import sys
from pathlib import Path

import pytest

from atex.executor.fmf import FMFExecutor, TestAbortedError, discover
from atex.executor.fmf.testcontrol import BadControlError, BadReportJSONError


def run_fmf_test(provisioner, tmp_path, *, read_results=True):
    test = sys._getframe(1).f_code.co_name  # same as parent func name
    fmf_tests = discover("fmf_trees/results", plan="/plan")
    provisioner.provision(1)
    remote = provisioner.get_remote()
    with FMFExecutor(remote, fmf_tests=fmf_tests) as e:
        e.run_test(f"/{test}", tmp_path)
    if read_results:
        results = (tmp_path / "results").read_text()
        print(f"=== RESULTS ===\n{results}\n===============")
        return results


# -----------------------------------------------------------------------------
def test_noresult_pass(provisioner, tmp_path):
    """Automatic fallback result based on exit code."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass", "files": ["output.txt"]}  # default
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output == "passing the script\n"


def test_noresult_fail(provisioner, tmp_path):
    """Automatic fallback result based on exit code."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "fail", "files": ["output.txt"]}
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output == "failing the script\n"


def test_noresult_abort(provisioner, tmp_path):
    """Automatic fallback exception."""
    try:
        run_fmf_test(provisioner, tmp_path, read_results=False)
    except TestAbortedError as e:
        if str(e) != "test duration timeout reached":
            raise
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "infra",
        "note": "TestAbortedError(test duration timeout reached)",
        "files": ["output.txt"],
    }
    output = (tmp_path / "files" / "output.txt").read_text()
    assert output == "sleeping forever-ish\n"


# -----------------------------------------------------------------------------
def test_trivial(provisioner, tmp_path):
    """Trivial test-reported result."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}
    # no automatic test output written
    files = list((tmp_path / "files").iterdir())
    assert len(files) == 0


def test_trivial_multiline(provisioner, tmp_path):
    """Trivial test-reported result as a multi-line string."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}
    # no automatic test output written
    files = list((tmp_path / "files").iterdir())
    assert len(files) == 0


def test_trivial_repeated(provisioner, tmp_path):
    """Multiple test-reported results for the test itself."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {"status": "pass"}
    assert json.loads(second) == {"status": "fail"}


def test_trivial_exit_mismatch(provisioner, tmp_path):
    """Ensure that reported result is preferred and exit code ignored."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}


def test_trivial_abort(provisioner, tmp_path):
    """No fallback exception is written if test provided a result."""
    try:
        run_fmf_test(provisioner, tmp_path, read_results=False)
    except TestAbortedError as e:
        if str(e) != "test duration timeout reached":
            raise
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}
    # no output.txt, the reported result has no files,
    # despite the test having written to stdout (output discarded)
    files = list((tmp_path / "files").iterdir())
    assert len(files) == 0


# -----------------------------------------------------------------------------
def test_subtest(provisioner, tmp_path):
    """Basic subtest reporting."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {"status": "fail", "name": "subtest"}
    assert json.loads(second) == {"status": "pass"}


def test_subtest_nested(provisioner, tmp_path):
    """Subtest using sub/dir/s."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {"status": "fail", "name": "sub/res/ult"}
    assert json.loads(second) == {"status": "pass"}


def test_subtest_no_status(provisioner, tmp_path):
    """Status-less subtests are also valid."""
    results = run_fmf_test(provisioner, tmp_path)
    # 2 because we didn't provide a result for the test itself,
    # so a fallback result is used
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {"name": "subtest"}
    assert json.loads(second) == {"status": "pass", "files": ["output.txt"]}


def test_subtest_testout(provisioner, tmp_path):
    """Testout should be linked only to the subtest."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {
        "status": "fail",
        "name": "subtest",
        "files": ["subtest/out.txt"],
    }
    assert json.loads(second) == {
        "status": "pass",  # no automatic testout
    }
    assert (tmp_path / "files" / "subtest" / "out.txt").exists()
    # no automatic test output written for the main test result
    assert not (tmp_path / "files" / "output.txt").exists()


# -----------------------------------------------------------------------------
def test_files(provisioner, tmp_path):
    """Basic binary file transfer."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["some_file"],
    }
    output = (tmp_path / "files" / "some_file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


def test_files_upload(provisioner, tmp_path):
    """Round-trip of a binary file via test transfer + result upload."""
    rand_file_bytes = Path("fmf_trees/results/randfile").read_bytes()
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["rand_file"],
    }
    output = (tmp_path / "files" / "rand_file").read_bytes()
    assert output == rand_file_bytes


def test_files_subpath(provisioner, tmp_path):
    """Transfer to a subdirectory (file name contains slashes)."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["some/file"],
    }
    output = (tmp_path / "files" / "some" / "file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


def test_files_multiple(provisioner, tmp_path):
    """Transfer of multiple files in one result."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["first_file", "second_file"],
    }
    first = (tmp_path / "files" / "first_file").read_bytes()
    assert first == b"\x00\x10"
    second = (tmp_path / "files" / "second_file").read_bytes()
    assert second == b"\x20\x30\x40"


def test_files_multiple_results(provisioner, tmp_path):
    """Transfer of multiple files in multiple results."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {
        "status": "fail",
        "files": ["first_file"],
    }
    assert json.loads(second) == {
        "status": "pass",
        "files": ["second_file"],
    }
    first = (tmp_path / "files" / "first_file").read_bytes()
    assert first == b"\x00\x10"
    second = (tmp_path / "files" / "second_file").read_bytes()
    assert second == b"\x20\x30\x40"


def test_files_append(provisioner, tmp_path):
    """Appending to the same file in one result."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["one_file"],
    }
    output = (tmp_path / "files" / "one_file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


def test_files_subtest(provisioner, tmp_path):
    """Transfer to a subdirectory (caused by a subtest)."""
    results = run_fmf_test(provisioner, tmp_path)
    # 2 because we didn't provide a result for the test itself,
    # so a fallback result is used
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {
        "status": "pass",
        "name": "sub/res/ult",
        "files": ["some_file"],
    }
    assert json.loads(second) == {"status": "pass", "files": ["output.txt"]}
    output = (tmp_path / "files" / "sub" / "res" / "ult" / "some_file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


def test_files_sorted(provisioner, tmp_path):
    """Files are sorted by name in ascending order."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["file_A", "file_B", "file_C"],
    }
    first = (tmp_path / "files" / "file_B").read_bytes()
    assert first == b"\x00\x10"
    second = (tmp_path / "files" / "file_C").read_bytes()
    assert second == b"\x20\x30"
    third = (tmp_path / "files" / "file_A").read_bytes()
    assert third == b"\x40\x50"


# -----------------------------------------------------------------------------
def test_custom_keys(provisioner, tmp_path):
    """Using user-defined JSON metadata in the result."""
    results = run_fmf_test(provisioner, tmp_path)
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
def test_partial(provisioner, tmp_path):
    """Test partial:True reporting."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}
    # no automatic test output written
    files = list((tmp_path / "files").iterdir())
    assert len(files) == 0


def test_partial_false(provisioner, tmp_path):
    """Explicit partial:False reporting."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}
    # no automatic test output written
    files = list((tmp_path / "files").iterdir())
    assert len(files) == 0


def test_partial_abrupt(provisioner, tmp_path):
    """Abrupt test exit relying on partial:True."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "fail",
        "files": ["output.txt"],  # from fallback result
    }


def test_partial_abrupt_nostatus(provisioner, tmp_path):
    """Abrupt test exit without reported status (uses exit code)."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "fail",  # because of exit 1
        "files": ["output.txt"],  # from fallback result
    }


def test_partial_abrupt_files(provisioner, tmp_path):
    """No output.txt is added in fallback result if files contains it."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["output.txt"],  # from test, not fallback
    }
    first = (tmp_path / "files" / "output.txt").read_bytes()
    assert first == b"custom output"


def test_partial_abrupt_nofiles(provisioner, tmp_path):
    """Fallback output.txt is added if none given in files."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [
            "output.txt",  # from fallback result
            "custom.txt",  # from test
        ],
    }
    first = (tmp_path / "files" / "custom.txt").read_bytes()
    assert first == b"custom output"
    second = (tmp_path / "files" / "output.txt").read_bytes()
    assert second == b"stdout output\n"


def test_partial_abrupt_fileonly(provisioner, tmp_path):
    """Only a file provided by test, no status/testout, fallback finishes it."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "fail",  # because of exit 1
        "files": [
            "output.txt",  # from fallback result
            "custom.txt",  # from test
        ],
    }
    first = (tmp_path / "files" / "custom.txt").read_bytes()
    assert first == b"custom output"
    second = (tmp_path / "files" / "output.txt").read_bytes()
    assert second == b"stdout output\n"


def test_partial_abrupt_abort(provisioner, tmp_path):
    """Exception overrides status/note via a fallback result."""
    try:
        run_fmf_test(provisioner, tmp_path, read_results=False)
    except TestAbortedError as e:
        if str(e) != "test duration timeout reached":
            raise
    results = (tmp_path / "results").read_text()
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "infra",
        "note": "TestAbortedError(test duration timeout reached)",
        "files": ["output.txt"],  # from fallback result
    }
    output = (tmp_path / "files" / "output.txt").read_bytes()
    assert output == b"sleeping forever-ish\n"


def test_partial_merging(provisioner, tmp_path):
    """Merging of multiple partial:True result keys."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "attr1": "value1",
        "attr2": "value2",
    }


def test_partial_deleting(provisioner, tmp_path):
    """Deleting keys via partial:True using a null value."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass"}


def test_partial_overwriting(provisioner, tmp_path):
    """Appending / updating of partial:True keys based on value type."""
    results = run_fmf_test(provisioner, tmp_path)
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


def test_partial_subtests(provisioner, tmp_path):
    """Applying partial:True to a subtest."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 3
    first, second, third = results.rstrip("\n").split("\n")
    # sub1 finishes first (partial:True followed by non-partial)
    assert json.loads(first) == {"status": "pass", "name": "sub1"}
    # followed by a non-partial result
    assert json.loads(second) == {"status": "pass"}
    # followed by abrupt test end and replayed sub2 as partial:True
    assert json.loads(third) == {"status": "error", "name": "sub2"}


def test_partial_files(provisioner, tmp_path):
    """Splitting two-file transfer across partial:True results."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["first_file", "second_file"],
    }
    first = (tmp_path / "files" / "first_file").read_bytes()
    assert first == b"\x00\x10"
    second = (tmp_path / "files" / "second_file").read_bytes()
    assert second == b"\x20\x30\x40"


def test_partial_files_append(provisioner, tmp_path):
    """Appending to the same file across partial:True results."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["one_file"],
    }
    output = (tmp_path / "files" / "one_file").read_bytes()
    assert output == b"\x00\x10\x20\x30\x40"


# -----------------------------------------------------------------------------
def test_testout(provisioner, tmp_path):
    """Manual testout:file specification."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["here.txt"],
    }
    output = (tmp_path / "files" / "here.txt").read_bytes()
    assert output == b"first line\nsecond line\n"
    # no automatic test output written
    assert not (tmp_path / "files" / "output.txt").exists()


def test_testout_partial(provisioner, tmp_path):
    """Overwriting a partial:True specified testout:file."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["there.txt"],
    }
    output = (tmp_path / "files" / "there.txt").read_bytes()
    assert output == b"some line\n"
    # the partial:True entry should not exist
    assert not (tmp_path / "files" / "here.txt").exists()
    # no automatic test output written
    assert not (tmp_path / "files" / "output.txt").exists()


def test_testout_multiple(provisioner, tmp_path):
    """Writing to multiple testouts using partial:True results."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 2
    first, second = results.rstrip("\n").split("\n")
    assert json.loads(first) == {
        "status": "fail",
        "files": ["here.txt"],
    }
    assert json.loads(second) == {
        "status": "pass",
        "files": ["there.txt"],
    }
    first_output = (tmp_path / "files" / "here.txt").read_bytes()
    assert first_output == b"some line\n"
    second_output = (tmp_path / "files" / "there.txt").read_bytes()
    assert second_output == b"some line\n"
    # no automatic test output written
    assert not (tmp_path / "files" / "output.txt").exists()


def test_testout_fallback(provisioner, tmp_path):
    """Fallback testout if test doesn't report anything."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": ["output.txt"],
    }
    output = (tmp_path / "files" / "output.txt").read_bytes()
    assert output == b"some line\n"


def test_testout_fallback_partial(provisioner, tmp_path):
    """Fallback testout doesn't contain testout if partial did."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "fail",  # because of exit 1
        "files": ["here.txt"],
    }
    output = (tmp_path / "files" / "here.txt").read_bytes()
    assert output == b"some line\n"
    # no automatic test output written
    assert not (tmp_path / "files" / "output.txt").exists()


# -----------------------------------------------------------------------------
def test_bad_json(provisioner, tmp_path):
    """Bad JSON result reported by a test."""
    try:
        run_fmf_test(provisioner, tmp_path, read_results=False)
    except BadReportJSONError:
        pass


def test_empty_json(provisioner, tmp_path):
    """Empty JSON result reported by a test."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {}


def test_no_status(provisioner, tmp_path):
    """Result without status reported by a test."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {"attr1": "value1"}


def test_empty_files(provisioner, tmp_path):
    """Empty files list in a result."""
    results = run_fmf_test(provisioner, tmp_path)
    assert results.count("\n") == 1
    assert json.loads(results) == {
        "status": "pass",
        "files": [],
    }
    # no files uploaded
    files = list((tmp_path / "files").iterdir())
    assert len(files) == 0


def test_no_file_data(provisioner, tmp_path):
    """Test ending without providing promised file data."""
    os.environ["ATEX_DEBUG_NO_EXITCODE"] = "1"
    try:
        with pytest.raises(BadControlError, match=r"^EOF when reading data$"):
            run_fmf_test(provisioner, tmp_path, read_results=False)
    finally:
        del os.environ["ATEX_DEBUG_NO_EXITCODE"]


def test_some_file_data(provisioner, tmp_path):
    """Test ending without providing ALL promised file data."""
    os.environ["ATEX_DEBUG_NO_EXITCODE"] = "1"
    try:
        with pytest.raises(BadControlError, match=r"^EOF when reading data$"):
            run_fmf_test(provisioner, tmp_path, read_results=False)
    finally:
        del os.environ["ATEX_DEBUG_NO_EXITCODE"]


def test_empty_testout(provisioner, tmp_path):
    """Empty string for a testout:file name."""
    with pytest.raises(BadReportJSONError, match=r"^'testout' specified, but empty$"):
        run_fmf_test(provisioner, tmp_path, read_results=False)
