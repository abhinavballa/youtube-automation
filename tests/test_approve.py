import pytest
from pathlib import Path

import approve


@pytest.fixture
def output_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output" / "pending_review").mkdir(parents=True)
    (tmp_path / "output" / "approved").mkdir(parents=True)
    return tmp_path


def test_approve_moves_video_and_sidecar(output_dirs):
    tmp_path = output_dirs
    mp4 = tmp_path / "output" / "pending_review" / "abc-123.mp4"
    jf = tmp_path / "output" / "pending_review" / "abc-123.json"
    mp4.write_bytes(b"fake video")
    jf.write_text('{"title": "test"}')

    approve.approve("abc-123.mp4")

    assert not mp4.exists()
    assert not jf.exists()
    assert (tmp_path / "output" / "approved" / "abc-123.mp4").exists()
    assert (tmp_path / "output" / "approved" / "abc-123.json").exists()


def test_approve_accepts_full_path_prefix(output_dirs):
    tmp_path = output_dirs
    mp4 = tmp_path / "output" / "pending_review" / "abc-456.mp4"
    jf = tmp_path / "output" / "pending_review" / "abc-456.json"
    mp4.write_bytes(b"fake")
    jf.write_text("{}")

    approve.approve("output/pending_review/abc-456.mp4")

    assert (tmp_path / "output" / "approved" / "abc-456.mp4").exists()


def test_approve_raises_on_missing_video(output_dirs):
    with pytest.raises(FileNotFoundError, match="Video not found"):
        approve.approve("nonexistent.mp4")


def test_approve_raises_on_missing_sidecar(output_dirs):
    tmp_path = output_dirs
    mp4 = tmp_path / "output" / "pending_review" / "abc-789.mp4"
    mp4.write_bytes(b"fake")

    with pytest.raises(FileNotFoundError, match="Sidecar metadata not found"):
        approve.approve("abc-789.mp4")
