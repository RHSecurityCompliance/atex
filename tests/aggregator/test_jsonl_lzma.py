import lzma

from atex.aggregator.jsonl import LZMAJSONLinesAggregator
from tests.aggregator import shared


def test_output_is_lzma(tmp_path):
    """Verify output is valid LZMA, decompresses to correct JSONL."""
    shared.output_is_compressed(tmp_path, LZMAJSONLinesAggregator, lzma.open, ".jsonl.xz")


def test_files_compressed(tmp_path):
    """Uploaded files are LZMA-compressed with .xz suffix in results."""
    shared.files_compressed(tmp_path, LZMAJSONLinesAggregator, lzma.open, ".xz")


def test_files_not_compressed(tmp_path):
    """With compress_files=False, uploaded files are moved verbatim."""
    shared.files_not_compressed(tmp_path, LZMAJSONLinesAggregator, ".jsonl.xz")


def test_files_exclude(tmp_path):
    """Excluded files are moved verbatim, others are LZMA-compressed."""
    shared.files_exclude(tmp_path, LZMAJSONLinesAggregator, lzma.open, ".xz")


def test_files_compressed_subpath(tmp_path):
    """LZMA compression preserves subdirectory structure."""
    shared.files_compressed_subpath(tmp_path, LZMAJSONLinesAggregator, lzma.open, ".xz")


def test_files_compressed_no_suffix(tmp_path):
    """Empty suffix compresses files in-place without renaming."""
    shared.files_compressed_no_suffix(tmp_path, LZMAJSONLinesAggregator, lzma.open, ".jsonl.xz")


def test_ingest_no_files(tmp_path):
    """No files directory created when artifacts have no files."""
    target = tmp_path / "target.jsonl.xz"
    files = tmp_path / "files"
    with LZMAJSONLinesAggregator(target, files) as aggregator:
        shared.ingest_no_files(tmp_path, aggregator, files)


def test_ingest_duplicate_reject(tmp_path):
    """Duplicate test name raises AggregatorError."""
    target = tmp_path / "target.jsonl.xz"
    files = tmp_path / "files"
    with LZMAJSONLinesAggregator(target, files) as aggregator:
        shared.ingest_duplicate_reject(tmp_path, aggregator)


def test_ingest_duplicate_allow(tmp_path):
    """Duplicate test name with allow_duplicate appends a counter suffix."""
    target = tmp_path / "target.jsonl.xz"
    files = tmp_path / "files"
    with LZMAJSONLinesAggregator(target, files, allow_duplicate=True) as aggregator:
        shared.ingest_duplicate_allow(tmp_path, aggregator, files)


def test_ingest_missing_results(tmp_path):
    """Missing results file raises FileNotFoundError."""
    target = tmp_path / "target.jsonl.xz"
    files = tmp_path / "files"
    with LZMAJSONLinesAggregator(target, files) as aggregator:
        shared.ingest_missing_results(tmp_path, aggregator)
