import json

from atex.aggregator.jsonl import JSONLinesAggregator
from tests.aggregator import shared


def test_ingest_one(tmp_dir):
    """Single test with one result line."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    artifacts = shared.make_artifacts(tmp_dir, [{"status": "pass"}])
    with JSONLinesAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    content = target.read_text()
    assert content.count("\n") == 1
    assert json.loads(content) == ["platform1", "pass", "/test1", None, [], None]


def test_ingest_multiple_tests(tmp_dir):
    """Two different tests both appear in output."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    artifacts1 = shared.make_artifacts(tmp_dir, [{"status": "pass"}], name="art1")
    artifacts2 = shared.make_artifacts(tmp_dir, [{"status": "fail"}], name="art2")
    with JSONLinesAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts1)
        aggregator.ingest("platform1", "/test2", artifacts2)
    content = target.read_text()
    assert content.count("\n") == 2
    first, second = content.rstrip("\n").split("\n")
    assert json.loads(first) == ["platform1", "pass", "/test1", None, [], None]
    assert json.loads(second) == ["platform1", "fail", "/test2", None, [], None]


def test_ingest_with_subtest(tmp_dir):
    """Result line with a subtest name."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    artifacts = shared.make_artifacts(
        tmp_dir,
        [
            {"status": "fail", "name": "sub1"},
            {"status": "pass"},
        ],
    )
    with JSONLinesAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    content = target.read_text()
    assert content.count("\n") == 2
    first, second = content.rstrip("\n").split("\n")
    assert json.loads(first) == ["platform1", "fail", "/test1", "sub1", [], None]
    assert json.loads(second) == ["platform1", "pass", "/test1", None, [], None]


def test_ingest_multiple_results(tmp_dir):
    """Single test reporting multiple result lines."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    artifacts = shared.make_artifacts(
        tmp_dir,
        [
            {"status": "pass"},
            {"status": "fail"},
        ],
    )
    with JSONLinesAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    content = target.read_text()
    assert content.count("\n") == 2
    first, second = content.rstrip("\n").split("\n")
    assert json.loads(first) == ["platform1", "pass", "/test1", None, [], None]
    assert json.loads(second) == ["platform1", "fail", "/test1", None, [], None]


def test_ingest_no_status(tmp_dir):
    """Result line without a status field."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    artifacts = shared.make_artifacts(tmp_dir, [{"name": "sub1"}])
    with JSONLinesAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    content = target.read_text()
    assert content.count("\n") == 1
    assert json.loads(content) == ["platform1", None, "/test1", "sub1", [], None]


def test_ingest_with_note(tmp_dir):
    """Result line with a note field."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    artifacts = shared.make_artifacts(
        tmp_dir,
        [{"status": "infra", "note": "TestAbortedError(timeout)"}],
    )
    with JSONLinesAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    content = target.read_text()
    assert content.count("\n") == 1
    assert json.loads(content) == [
        "platform1", "infra", "/test1", None, [], "TestAbortedError(timeout)",
    ]


# -----------------------------------------------------------------------------
def test_ingest_with_files(tmp_dir):
    """Basic binary file transfer."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    with JSONLinesAggregator(target, files) as aggregator:
        shared.ingest_with_files(tmp_dir, aggregator, files)


def test_ingest_with_subpath_files(tmp_dir):
    """File transfer to a subdirectory path."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    with JSONLinesAggregator(target, files) as aggregator:
        shared.ingest_with_subpath_files(tmp_dir, aggregator, files)


def test_ingest_no_files(tmp_dir):
    """No files directory created when artifacts have no files."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    with JSONLinesAggregator(target, files) as aggregator:
        shared.ingest_no_files(tmp_dir, aggregator, files)


def test_ingest_duplicate_reject(tmp_dir):
    """Duplicate test name raises AggregatorError."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    with JSONLinesAggregator(target, files) as aggregator:
        shared.ingest_duplicate_reject(tmp_dir, aggregator)


def test_ingest_duplicate_allow(tmp_dir):
    """Duplicate test name with allow_duplicate appends a counter suffix."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    with JSONLinesAggregator(target, files, allow_duplicate=True) as aggregator:
        shared.ingest_duplicate_allow(tmp_dir, aggregator, files)


def test_ingest_missing_results(tmp_dir):
    """Missing results file raises FileNotFoundError."""
    target = tmp_dir / "target.jsonl"
    files = tmp_dir / "files"
    with JSONLinesAggregator(target, files) as aggregator:
        shared.ingest_missing_results(tmp_dir, aggregator)
