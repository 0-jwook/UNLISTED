import os

import pytest

from musiclib.models import JobStatus
from musiclib.pipeline import Tools, process_url

from test_pipeline import EXIFTOOL, FFMPEG, TITLE, _fake_ytdlp

pytestmark = pytest.mark.skipif(
    FFMPEG is None or not os.path.exists(EXIFTOOL),
    reason="ffmpeg/exiftool이 필요합니다",
)

URL = "https://www.youtube.com/watch?v=lZHyUw7LWSw"


def test_success_leaves_only_final_m4a(tmp_path):
    out = tmp_path / "out"
    tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)
    result = process_url(URL, out, tools)
    assert result.status is JobStatus.DONE, result.detail
    remaining = sorted(p.name for p in out.iterdir())
    assert remaining == [f"{TITLE}.m4a"]
    assert result.thumbnail is None


def test_cleanup_can_be_disabled(tmp_path):
    out = tmp_path / "out"
    tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)
    result = process_url(URL, out, tools, cleanup=False)
    assert result.status is JobStatus.DONE, result.detail
    names = {p.name for p in out.iterdir()}
    assert f"{TITLE}.jpg" in names
    assert f"{TITLE}.m4a_original" in names


def test_preexisting_backup_is_kept(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / f"{TITLE}.m4a_original").write_bytes(b"user backup")
    tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)
    # 같은 이름의 최종 파일이 없으므로 진행되고, 기존 백업은 지우지 않는다
    result = process_url(URL, out, tools)
    assert result.status is JobStatus.DONE, result.detail
    assert (out / f"{TITLE}.m4a_original").read_bytes() == b"user backup"


def test_failure_does_not_trigger_cleanup(tmp_path):
    out = tmp_path / "out"
    tools = Tools(_fake_ytdlp(tmp_path, fail=True), FFMPEG, EXIFTOOL)
    result = process_url(URL, out, tools)
    assert result.status is JobStatus.FAILED
    assert not out.exists() or not any(out.iterdir())
