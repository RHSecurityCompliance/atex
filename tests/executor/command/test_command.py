import json

from atex.connection.local import LocalConnection
from atex.executor.command import CommandExecutor


def test_pass(tmp_dir):
    """Command exiting 0 produces a pass result."""
    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\necho hello\n")
    script.chmod(0o755)
    artifacts = tmp_dir / "artifacts"
    artifacts.mkdir()
    tests = {"/test1": (script,)}
    with LocalConnection() as conn:
        with CommandExecutor(conn, tests) as executor:
            executor.run_test("/test1", artifacts)
    results = (artifacts / "results").read_text()
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "pass", "files": ["output.txt"]}
    output = (artifacts / "files" / "output.txt").read_text()
    assert output == "hello\n"


def test_fail(tmp_dir):
    """Command exiting non-zero produces a fail result."""
    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\necho failing\nexit 1\n")
    script.chmod(0o755)
    artifacts = tmp_dir / "artifacts"
    artifacts.mkdir()
    tests = {"/test1": (script,)}
    with LocalConnection() as conn:
        with CommandExecutor(conn, tests) as executor:
            executor.run_test("/test1", artifacts)
    results = (artifacts / "results").read_text()
    assert results.count("\n") == 1
    assert json.loads(results) == {"status": "fail", "files": ["output.txt"]}
    output = (artifacts / "files" / "output.txt").read_text()
    assert output == "failing\n"


def test_exit_code(tmp_dir):
    """run_test returns the actual exit code of the command."""
    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\nexit 123\n")
    script.chmod(0o755)
    artifacts = tmp_dir / "artifacts"
    artifacts.mkdir()
    tests = {"/test1": (script,)}
    with LocalConnection() as conn:
        with CommandExecutor(conn, tests) as executor:
            rc = executor.run_test("/test1", artifacts)
    assert rc == 123


def test_output_capture(tmp_dir):
    """Both stdout and stderr are captured into the output file."""
    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\necho stdout_line\necho stderr_line >&2\n")
    script.chmod(0o755)
    artifacts = tmp_dir / "artifacts"
    artifacts.mkdir()
    tests = {"/test1": (script,)}
    with LocalConnection() as conn:
        with CommandExecutor(conn, tests) as executor:
            executor.run_test("/test1", artifacts)
    output = (artifacts / "files" / "output.txt").read_text()
    assert "stdout_line" in output
    assert "stderr_line" in output


def test_binary_output(tmp_dir):
    """Binary data in command output is captured faithfully."""
    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\nprintf '\\x00\\x80\\xfe\\xff'\n")
    script.chmod(0o755)
    artifacts = tmp_dir / "artifacts"
    artifacts.mkdir()
    tests = {"/test1": (script,)}
    with LocalConnection() as conn:
        with CommandExecutor(conn, tests) as executor:
            executor.run_test("/test1", artifacts)
    output = (artifacts / "files" / "output.txt").read_bytes()
    assert output == b"\x00\x80\xfe\xff"


def test_custom_output_name(tmp_dir):
    """The output kwarg changes the captured output filename."""
    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\necho hello\n")
    script.chmod(0o755)
    artifacts = tmp_dir / "artifacts"
    artifacts.mkdir()
    tests = {"/test1": (script,)}
    with LocalConnection() as conn:
        with CommandExecutor(conn, tests) as executor:
            executor.run_test("/test1", artifacts, output="custom.log")
    assert not (artifacts / "files" / "output.txt").exists()
    output = (artifacts / "files" / "custom.log").read_text()
    assert output == "hello\n"
    results = (artifacts / "results").read_text()
    assert json.loads(results)["files"] == ["custom.log"]


def test_custom_evaluate(tmp_dir):
    """Subclass can override evaluate() to implement custom pass/fail logic."""

    class GrepExecutor(CommandExecutor):
        def evaluate(self, exit_code, output):  # noqa: PLR6301
            if b"FAIL" in output.read_bytes():
                return "fail"
            return "pass" if exit_code == 0 else "fail"

    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\necho 'result: FAIL'\nexit 0\n")
    script.chmod(0o755)
    artifacts = tmp_dir / "artifacts"
    artifacts.mkdir()
    tests = {"/test1": (script,)}
    with LocalConnection() as conn:
        with GrepExecutor(conn, tests) as executor:
            executor.run_test("/test1", artifacts)
    results = (artifacts / "results").read_text()
    assert json.loads(results)["status"] == "fail"
