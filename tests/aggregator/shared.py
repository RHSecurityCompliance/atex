import json

from atex.aggregator import AggregatorError


def make_artifacts(base, results_lines, files=None, *, name="artifacts"):
    artifacts = base / name
    artifacts.mkdir()
    (artifacts / "results").write_text(
        "".join(json.dumps(line) + "\n" for line in results_lines),
    )
    files_dir = artifacts / "files"
    files_dir.mkdir()
    if files:
        for fname, content in files.items():
            path = files_dir / fname
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return artifacts


def ingest_with_files(tmp_dir, aggregator, files):
    artifacts = make_artifacts(
        tmp_dir,
        [{"status": "pass", "files": ["data.bin"]}],
        files={"data.bin": b"\x00\x01\x02\x03"},
    )
    aggregator.ingest("platform1", "/test1", artifacts)
    moved = files / "platform1" / "test1" / "data.bin"
    assert moved.exists()
    assert moved.read_bytes() == b"\x00\x01\x02\x03"


def ingest_with_subpath_files(tmp_dir, aggregator, files):
    artifacts = make_artifacts(
        tmp_dir,
        [{"status": "pass", "files": ["sub/dir/data.bin"]}],
        files={"sub/dir/data.bin": b"\xaa\xbb\xcc"},
    )
    aggregator.ingest("platform1", "/test1", artifacts)
    moved = files / "platform1" / "test1" / "sub" / "dir" / "data.bin"
    assert moved.exists()
    assert moved.read_bytes() == b"\xaa\xbb\xcc"


def ingest_no_files(tmp_dir, aggregator, files):
    artifacts = make_artifacts(tmp_dir, [{"status": "pass"}])
    aggregator.ingest("platform1", "/test1", artifacts)
    assert not (artifacts / "results").exists()
    assert not (files / "platform1").exists()


def ingest_duplicate_reject(tmp_dir, aggregator):
    artifacts1 = make_artifacts(tmp_dir, [{"status": "pass"}], name="artifacts1")
    artifacts2 = make_artifacts(tmp_dir, [{"status": "pass"}], name="artifacts2")
    aggregator.ingest("platform1", "/test1", artifacts1)
    try:
        aggregator.ingest("platform1", "/test1", artifacts2)
        raise AssertionError("AggregatorError should have triggered")
    except AggregatorError:
        pass


def ingest_duplicate_allow(tmp_dir, aggregator, files):
    artifacts1 = make_artifacts(
        tmp_dir,
        [{"status": "pass", "files": ["data.bin"]}],
        files={"data.bin": b"\x00\x01"},
        name="artifacts1",
    )
    artifacts2 = make_artifacts(
        tmp_dir,
        [{"status": "pass", "files": ["data.bin"]}],
        files={"data.bin": b"\x02\x03"},
        name="artifacts2",
    )
    aggregator.ingest("platform1", "/test1", artifacts1)
    aggregator.ingest("platform1", "/test1", artifacts2)
    assert (files / "platform1" / "test1").exists()
    assert (files / "platform1" / "test1 (1)").exists()


def ingest_missing_results(tmp_dir, aggregator):
    artifacts = tmp_dir / "artifacts"
    artifacts.mkdir()
    (artifacts / "files").mkdir()
    try:
        aggregator.ingest("platform1", "/test1", artifacts)
        raise AssertionError("FileNotFoundError should have triggered")
    except FileNotFoundError:
        pass


# -----------------------------------------------------------------------------
# Compressed aggregator helpers.
# These handle lifecycle internally because compressed target files must be
# closed before they can be read back (gzip/lzma write a trailer on close).

def output_is_compressed(tmp_dir, cls, decompress_open, ext):
    target = tmp_dir / f"target{ext}"
    files = tmp_dir / "files"
    artifacts = make_artifacts(tmp_dir, [{"status": "pass"}])
    with cls(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    with decompress_open(target, "rt") as f:
        content = f.read()
    assert content.count("\n") == 1
    assert json.loads(content) == ["platform1", "pass", "/test1", None, [], None]


def files_compressed(tmp_dir, cls, decompress_open, suffix):
    target = tmp_dir / f"target.jsonl{suffix}"
    files = tmp_dir / "files"
    artifacts = make_artifacts(
        tmp_dir,
        [{"status": "pass", "files": ["data.bin"]}],
        files={"data.bin": b"\x00\x01\x02\x03"},
    )
    with cls(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    moved = files / "platform1" / "test1" / f"data.bin{suffix}"
    assert moved.exists()
    with decompress_open(moved, "rb") as f:
        assert f.read() == b"\x00\x01\x02\x03"
    with decompress_open(target, "rt") as f:
        result = json.loads(f.read().strip())
    assert result[4] == [f"data.bin{suffix}"]


def files_not_compressed(tmp_dir, cls, ext):
    target = tmp_dir / f"target{ext}"
    files = tmp_dir / "files"
    artifacts = make_artifacts(
        tmp_dir,
        [{"status": "pass", "files": ["data.bin"]}],
        files={"data.bin": b"\x00\x01\x02\x03"},
    )
    with cls(target, files, compress_files=False) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    moved = files / "platform1" / "test1" / "data.bin"
    assert moved.exists()
    assert moved.read_bytes() == b"\x00\x01\x02\x03"


def files_exclude(tmp_dir, cls, decompress_open, suffix):
    target = tmp_dir / f"target.jsonl{suffix}"
    files = tmp_dir / "files"
    artifacts = make_artifacts(
        tmp_dir,
        [{"status": "pass", "files": ["data.bin", "keep.txt"]}],
        files={
            "data.bin": b"\x00\x01\x02\x03",
            "keep.txt": b"plain text",
        },
    )
    with cls(target, files, compress_files_exclude=("keep.txt",)) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    compressed = files / "platform1" / "test1" / f"data.bin{suffix}"
    assert compressed.exists()
    with decompress_open(compressed, "rb") as f:
        assert f.read() == b"\x00\x01\x02\x03"
    plain = files / "platform1" / "test1" / "keep.txt"
    assert plain.exists()
    assert plain.read_bytes() == b"plain text"
    with decompress_open(target, "rt") as f:
        result = json.loads(f.read().strip())
    assert f"data.bin{suffix}" in result[4]
    assert "keep.txt" in result[4]


def files_compressed_subpath(tmp_dir, cls, decompress_open, suffix):
    target = tmp_dir / f"target.jsonl{suffix}"
    files = tmp_dir / "files"
    artifacts = make_artifacts(
        tmp_dir,
        [{"status": "pass", "files": ["sub/dir/data.bin"]}],
        files={"sub/dir/data.bin": b"\xaa\xbb\xcc"},
    )
    with cls(target, files) as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    moved = files / "platform1" / "test1" / "sub" / "dir" / f"data.bin{suffix}"
    assert moved.exists()
    with decompress_open(moved, "rb") as f:
        assert f.read() == b"\xaa\xbb\xcc"


def files_compressed_no_suffix(tmp_dir, cls, decompress_open, ext):
    target = tmp_dir / f"target{ext}"
    files = tmp_dir / "files"
    artifacts = make_artifacts(
        tmp_dir,
        [{"status": "pass", "files": ["data.bin"]}],
        files={"data.bin": b"\x00\x01\x02\x03"},
    )
    with cls(target, files, compress_files_suffix="") as aggregator:
        aggregator.ingest("platform1", "/test1", artifacts)
    moved = files / "platform1" / "test1" / "data.bin"
    assert moved.exists()
    with decompress_open(moved, "rb") as f:
        assert f.read() == b"\x00\x01\x02\x03"
    with decompress_open(target, "rt") as f:
        result = json.loads(f.read().strip())
    assert result[4] == ["data.bin"]
