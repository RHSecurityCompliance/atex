import gzip

from atex.aggregator.jsonl import GzipJSONLinesAggregator
from tests.aggregator import shared


def test_output_is_gzip(tmp_dir):
    """Verify output is valid gzip, decompresses to correct JSONL."""
    shared.output_is_compressed(tmp_dir, GzipJSONLinesAggregator, gzip.open, ".jsonl.gz")


def test_files_compressed(tmp_dir):
    """Uploaded files are gzip-compressed with .gz suffix in results."""
    shared.files_compressed(tmp_dir, GzipJSONLinesAggregator, gzip.open, ".gz")


def test_files_not_compressed(tmp_dir):
    """With compress_files=False, uploaded files are moved verbatim."""
    shared.files_not_compressed(tmp_dir, GzipJSONLinesAggregator, ".jsonl.gz")


def test_files_exclude(tmp_dir):
    """Excluded files are moved verbatim, others are gzip-compressed."""
    shared.files_exclude(tmp_dir, GzipJSONLinesAggregator, gzip.open, ".gz")


def test_files_compressed_subpath(tmp_dir):
    """Gzip compression preserves subdirectory structure."""
    shared.files_compressed_subpath(tmp_dir, GzipJSONLinesAggregator, gzip.open, ".gz")


def test_files_compressed_no_suffix(tmp_dir):
    """Empty suffix compresses files in-place without renaming."""
    shared.files_compressed_no_suffix(tmp_dir, GzipJSONLinesAggregator, gzip.open, ".jsonl.gz")


def test_ingest_no_files(tmp_dir):
    """No files directory created when artifacts have no files."""
    target = tmp_dir / "target.jsonl.gz"
    files = tmp_dir / "files"
    with GzipJSONLinesAggregator(target, files) as aggregator:
        shared.ingest_no_files(tmp_dir, aggregator, files)


def test_ingest_duplicate_reject(tmp_dir):
    """Duplicate test name raises AggregatorError."""
    target = tmp_dir / "target.jsonl.gz"
    files = tmp_dir / "files"
    with GzipJSONLinesAggregator(target, files) as aggregator:
        shared.ingest_duplicate_reject(tmp_dir, aggregator)


def test_ingest_duplicate_allow(tmp_dir):
    """Duplicate test name with allow_duplicate appends a counter suffix."""
    target = tmp_dir / "target.jsonl.gz"
    files = tmp_dir / "files"
    with GzipJSONLinesAggregator(target, files, allow_duplicate=True) as aggregator:
        shared.ingest_duplicate_allow(tmp_dir, aggregator, files)


def test_ingest_missing_results(tmp_dir):
    """Missing results file raises FileNotFoundError."""
    target = tmp_dir / "target.jsonl.gz"
    files = tmp_dir / "files"
    with GzipJSONLinesAggregator(target, files) as aggregator:
        shared.ingest_missing_results(tmp_dir, aggregator)
