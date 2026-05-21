import yaml

from atex.aggregator.yamld import YAMLDocumentAggregator
from tests.aggregator import shared


def test_output_format(tmp_path):
    """Verify output is valid multi-document YAML with correct structure."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    artifacts1 = shared.make_artifacts(
        tmp_path,
        [{"status": "pass", "files": ["data.bin"]}],
        files={"data.bin": b"\x00\x01"},
        name="art1",
    )
    artifacts2 = shared.make_artifacts(
        tmp_path,
        [{"status": "fail", "note": "something went wrong"}],
        name="art2",
    )
    with YAMLDocumentAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts1)
        aggregator.ingest("platform1", "/test2", artifacts2)
    content = target.read_text()
    docs = list(yaml.safe_load_all(content))
    assert len(docs) == 2
    assert docs[0] == {
        "platform": "platform1",
        "name": "/test1",
        "status": "pass",
        "files": ["data.bin"],
    }
    assert docs[1] == {
        "platform": "platform1",
        "name": "/test2",
        "status": "fail",
        "note": "something went wrong",
    }


def test_subtests_grouped(tmp_path):
    """Subtests are collected into a subtests list, not top-level entries."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    artifacts = shared.make_artifacts(
        tmp_path,
        [
            {"status": "fail", "name": "sub1"},
            {"status": "pass", "name": "sub2", "note": "extra info"},
            {"status": "pass"},
        ],
    )
    with YAMLDocumentAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    content = target.read_text()
    docs = list(yaml.safe_load_all(content))
    assert len(docs) == 1
    doc = docs[0]
    assert doc["platform"] == "platform1"
    assert doc["name"] == "/test1"
    assert doc["status"] == "pass"
    assert len(doc["subtests"]) == 2
    assert doc["subtests"][0] == {"name": "sub1", "status": "fail"}
    assert doc["subtests"][1] == {
        "name": "sub2",
        "status": "pass",
        "note": "extra info",
    }


def test_empty_fields_omitted(tmp_path):
    """None/empty status, note, subtests, files are omitted entirely."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    artifacts = shared.make_artifacts(tmp_path, [{}])
    with YAMLDocumentAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    content = target.read_text()
    docs = list(yaml.safe_load_all(content))
    assert len(docs) == 1
    assert docs[0] == {"platform": "platform1", "name": "/test1"}


def test_multiple_results_merged(tmp_path):
    """Multiple non-subtest results: status/note overwrite, files accumulate."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    artifacts = shared.make_artifacts(
        tmp_path,
        [
            {"status": "fail", "files": ["first.txt"], "note": "initial note"},
            {"status": "pass", "files": ["second.txt"], "note": "final note"},
        ],
    )
    with YAMLDocumentAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    content = target.read_text()
    docs = list(yaml.safe_load_all(content))
    assert len(docs) == 1
    assert docs[0] == {
        "platform": "platform1",
        "name": "/test1",
        "status": "pass",
        "files": ["first.txt", "second.txt"],
        "note": "final note",
    }


def test_subtest_with_files(tmp_path):
    """Subtests can include file references."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    artifacts = shared.make_artifacts(
        tmp_path,
        [
            {"status": "fail", "name": "sub1", "files": ["sub1.log"]},
            {"status": "pass"},
        ],
    )
    with YAMLDocumentAggregator(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    content = target.read_text()
    docs = list(yaml.safe_load_all(content))
    assert len(docs) == 1
    doc = docs[0]
    assert doc["status"] == "pass"
    assert len(doc["subtests"]) == 1
    assert doc["subtests"][0] == {
        "name": "sub1",
        "status": "fail",
        "files": ["sub1.log"],
    }


# -----------------------------------------------------------------------------
def test_ingest_with_files(tmp_path):
    """Basic binary file transfer."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    with YAMLDocumentAggregator(target, files) as aggregator:
        shared.ingest_with_files(tmp_path, aggregator, files)


def test_ingest_with_subpath_files(tmp_path):
    """File transfer to a subdirectory path."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    with YAMLDocumentAggregator(target, files) as aggregator:
        shared.ingest_with_subpath_files(tmp_path, aggregator, files)


def test_ingest_no_files(tmp_path):
    """No files directory created when artifacts have no files."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    with YAMLDocumentAggregator(target, files) as aggregator:
        shared.ingest_no_files(tmp_path, aggregator, files)


def test_ingest_duplicate_reject(tmp_path):
    """Duplicate test name raises AggregatorError."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    with YAMLDocumentAggregator(target, files) as aggregator:
        shared.ingest_duplicate_reject(tmp_path, aggregator)


def test_ingest_duplicate_allow(tmp_path):
    """Duplicate test name with allow_duplicate appends a counter suffix."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    with YAMLDocumentAggregator(target, files, allow_duplicate=True) as aggregator:
        shared.ingest_duplicate_allow(tmp_path, aggregator, files)


def test_ingest_missing_results(tmp_path):
    """Missing results file raises FileNotFoundError."""
    target = tmp_path / "target.yaml"
    files = tmp_path / "files"
    with YAMLDocumentAggregator(target, files) as aggregator:
        shared.ingest_missing_results(tmp_path, aggregator)
