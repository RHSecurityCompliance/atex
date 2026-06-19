import json
import logging

import pytest

from atex.aggregator.jsonl import JSONLinesAggregator
from atex.aggregator.multi import MultiAggregator
from tests.aggregator import shared


def test_artifact_isolation(tmp_path):
    """Both children see the same artifacts despite destructive ingest."""
    target1 = tmp_path / "out1.jsonl"
    target2 = tmp_path / "out2.jsonl"
    files1 = tmp_path / "files1"
    files2 = tmp_path / "files2"
    artifacts = shared.make_artifacts(
        tmp_path,
        [{"status": "fail", "files": ["data.bin"]}],
        files={"data.bin": b"\xaa\xbb\xcc"},
    )
    with MultiAggregator([
        JSONLinesAggregator(target1, files1),
        JSONLinesAggregator(target2, files2),
    ]) as multi:
        multi.ingest("platform1", "/test1", artifacts)
    result1 = json.loads(target1.read_text())
    result2 = json.loads(target2.read_text())
    assert result1 == result2
    assert (files1 / "platform1" / "test1" / "data.bin").read_bytes() == b"\xaa\xbb\xcc"
    assert (files2 / "platform1" / "test1" / "data.bin").read_bytes() == b"\xaa\xbb\xcc"


def test_temp_cleanup_on_failure(tmp_path):
    """No temporary dirs leak when a child's ingest raises."""
    target = tmp_path / "target.jsonl"
    files = tmp_path / "files"
    # create artifacts without a 'results' file so the child raises
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "files").mkdir()
    with MultiAggregator([
        JSONLinesAggregator(target, files),
        JSONLinesAggregator(tmp_path / "dummy.jsonl", tmp_path / "dummy_files"),
    ]) as multi:
        with pytest.raises(FileNotFoundError):
            multi.ingest("platform1", "/test1", artifacts)
    leftovers = list(tmp_path.glob("atex-multi-*"))
    assert leftovers == []


def test_stop_resilience(tmp_path, caplog):
    """One child's stop() failing doesn't prevent the other from stopping."""
    target = tmp_path / "target.jsonl"
    files = tmp_path / "files"

    class BadStop(JSONLinesAggregator):
        def stop(self):
            super().stop()
            raise RuntimeError("stop failed")

    bad = BadStop(tmp_path / "bad.jsonl", tmp_path / "bad_files")
    good = JSONLinesAggregator(target, files)
    # bad first, good second -- good must still be stopped
    multi = MultiAggregator([bad, good])
    multi.start()
    with caplog.at_level(logging.DEBUG):
        multi.stop()
    assert "stop failed" in caplog.text
    assert f"stopping: {good}" in caplog.text
