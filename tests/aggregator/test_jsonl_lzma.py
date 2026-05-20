import lzma

from atex.aggregator.jsonl import LZMAJSONLinesAggregator
from tests.aggregator import shared


def test_output_is_lzma(tmp_dir):
    """Verify output is valid LZMA, decompresses to correct JSONL."""
    shared.output_is_compressed(tmp_dir, LZMAJSONLinesAggregator, lzma.open, ".jsonl.xz")


def test_files_compressed(tmp_dir):
    """Uploaded files are LZMA-compressed with .xz suffix in results."""
    shared.files_compressed(tmp_dir, LZMAJSONLinesAggregator, lzma.open, ".xz")


def test_files_not_compressed(tmp_dir):
    """With compress_files=False, uploaded files are moved verbatim."""
    shared.files_not_compressed(tmp_dir, LZMAJSONLinesAggregator, ".jsonl.xz")


def test_files_exclude(tmp_dir):
    """Excluded files are moved verbatim, others are LZMA-compressed."""
    shared.files_exclude(tmp_dir, LZMAJSONLinesAggregator, lzma.open, ".xz")


def test_files_compressed_subpath(tmp_dir):
    """LZMA compression preserves subdirectory structure."""
    shared.files_compressed_subpath(tmp_dir, LZMAJSONLinesAggregator, lzma.open, ".xz")


def test_files_compressed_no_suffix(tmp_dir):
    """Empty suffix compresses files in-place without renaming."""
    shared.files_compressed_no_suffix(tmp_dir, LZMAJSONLinesAggregator, lzma.open, ".jsonl.xz")


def test_ingest_no_files(tmp_dir):
    """No files directory created when artifacts have no files."""
    target = tmp_dir / "target.jsonl.xz"
    files = tmp_dir / "files"
    with LZMAJSONLinesAggregator(target, files) as aggregator:
        shared.ingest_no_files(tmp_dir, aggregator, files)


def test_ingest_duplicate_reject(tmp_dir):
    """Duplicate test name raises AggregatorError."""
    target = tmp_dir / "target.jsonl.xz"
    files = tmp_dir / "files"
    with LZMAJSONLinesAggregator(target, files) as aggregator:
        shared.ingest_duplicate_reject(tmp_dir, aggregator)


def test_ingest_duplicate_allow(tmp_dir):
    """Duplicate test name with allow_duplicate appends a counter suffix."""
    target = tmp_dir / "target.jsonl.xz"
    files = tmp_dir / "files"
    with LZMAJSONLinesAggregator(target, files, allow_duplicate=True) as aggregator:
        shared.ingest_duplicate_allow(tmp_dir, aggregator, files)


def test_ingest_missing_results(tmp_dir):
    """Missing results file raises FileNotFoundError."""
    target = tmp_dir / "target.jsonl.xz"
    files = tmp_dir / "files"
    with LZMAJSONLinesAggregator(target, files) as aggregator:
        shared.ingest_missing_results(tmp_dir, aggregator)
