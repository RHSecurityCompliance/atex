import json

import pytest

from atex.aggregator.jsonl import JSONLinesAggregator
from atex.executor.command import CommandExecutor
from atex.orchestrator.adhoc import AdHocOrchestrator
from atex.provisioner.local import LocalProvisioner


def run_orchestrator(tmp_dir, tests, *, cls=AdHocOrchestrator, use_old_aggregator=False):
    target = tmp_dir / "results.jsonl"
    files = tmp_dir / "aggregator_files"

    old_target = tmp_dir / "old_results.jsonl"
    old_files = tmp_dir / "old_aggregator_files"

    with LocalProvisioner() as provisioner:
        with JSONLinesAggregator(target, files) as aggregator:
            old_aggregator = None
            if use_old_aggregator:
                old_aggregator = JSONLinesAggregator(
                    old_target, old_files, allow_duplicate=True,
                )
                old_aggregator.start()

            try:
                with cls(
                    "test-platform",
                    tests.keys(),
                    (provisioner,),
                    lambda conn, t=tests: CommandExecutor(conn, t),
                    aggregator,
                    old_aggregator=old_aggregator,
                ) as orchestrator:
                    orchestrator.serve_forever()
            finally:
                if old_aggregator:
                    old_aggregator.stop()

    with open(target) as f:
        results = [json.loads(line) for line in f]

    old_results = []
    if use_old_aggregator and old_target.exists():
        with open(old_target) as f:
            old_results = [json.loads(line) for line in f]

    return (results, old_results)


def test_single_test(tmp_dir):
    """Single passing test is aggregated correctly."""
    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\necho hello\n")
    script.chmod(0o755)
    tests = {"/test1": (script,)}
    results, _ = run_orchestrator(tmp_dir, tests)
    assert len(results) == 1
    assert results[0][0] == "test-platform"
    assert results[0][1] == "pass"
    assert results[0][2] == "/test1"


def test_multiple_tests(tmp_dir):
    """Multiple passing tests are all aggregated."""
    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\necho hello\n")
    script.chmod(0o755)
    tests = {
        "/test1": (script,),
        "/test2": (script,),
        "/test3": (script,),
    }
    results, _ = run_orchestrator(tmp_dir, tests)
    assert len(results) == 3
    names = {r[2] for r in results}
    assert names == {"/test1", "/test2", "/test3"}
    assert all(r[1] == "pass" for r in results)


def test_pass_and_fail(tmp_dir):
    """Mix of passing and failing tests produces correct statuses."""
    pass_script = tmp_dir / "pass.sh"
    pass_script.write_text("#!/bin/bash\nexit 0\n")
    pass_script.chmod(0o755)
    fail_script = tmp_dir / "fail.sh"
    fail_script.write_text("#!/bin/bash\nexit 1\n")
    fail_script.chmod(0o755)
    tests = {
        "/passing": (pass_script,),
        "/failing": (fail_script,),
    }
    results, _ = run_orchestrator(tmp_dir, tests)
    assert len(results) == 2
    by_name = {r[2]: r[1] for r in results}
    assert by_name["/passing"] == "pass"
    assert by_name["/failing"] == "fail"


def test_rerun(tmp_dir):
    """Failed test is rerun, old result goes to old_aggregator, final to aggregator."""
    class RerunOnceOrchestrator(AdHocOrchestrator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._rerun_counts = {}

        def should_be_rerun(self, info, /):
            past = self._rerun_counts.get(info.test_name, 0)
            if past >= 1:
                return False
            self._rerun_counts[info.test_name] = past + 1
            return True

    sentinel = tmp_dir / "sentinel"
    script = tmp_dir / "test.sh"
    script.write_text(
        f"#!/bin/bash\n"
        f"if [ -f {sentinel} ]; then\n"
        f"  echo passed\n"
        f"  exit 0\n"
        f"fi\n"
        f"touch {sentinel}\n"
        f"echo failed\n"
        f"exit 1\n",
    )
    script.chmod(0o755)
    tests = {"/flaky": (script,)}
    results, old_results = run_orchestrator(
        tmp_dir, tests, cls=RerunOnceOrchestrator, use_old_aggregator=True,
    )
    # final result should be pass
    assert len(results) == 1
    assert results[0][1] == "pass"
    assert results[0][2] == "/flaky"
    # old (failed) result should be in old_aggregator
    assert len(old_results) == 1
    assert old_results[0][1] == "fail"
    assert old_results[0][2] == "/flaky"


def test_next_test_override(tmp_dir):
    """Subclass can override next_test() to control test selection."""
    picked = []

    class TrackingOrchestrator(AdHocOrchestrator):
        def next_test(self, to_run, previous, /):  # noqa: PLR6301, ARG002
            choice = list(to_run)[-1]
            picked.append(choice)
            return choice

    script = tmp_dir / "test.sh"
    script.write_text("#!/bin/bash\necho hello\n")
    script.chmod(0o755)
    tests = {
        "/aaa": (script,),
        "/bbb": (script,),
        "/ccc": (script,),
    }
    results, _ = run_orchestrator(tmp_dir, tests, cls=TrackingOrchestrator)
    assert len(results) == 3
    # next_test was called for each test and always picked the last element
    assert len(picked) == 3
    assert picked[0] == "/ccc"


def test_empty_tests(tmp_dir):
    """Empty test list raises ValueError."""
    target = tmp_dir / "results.jsonl"
    files = tmp_dir / "aggregator_files"
    with LocalProvisioner() as provisioner:
        with JSONLinesAggregator(target, files) as aggregator:
            with pytest.raises(ValueError):
                AdHocOrchestrator(
                    "test-platform",
                    [],
                    (provisioner,),
                    lambda conn: CommandExecutor(conn, {}),
                    aggregator,
                )
