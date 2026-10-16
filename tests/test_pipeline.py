import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from musiclib.models import JobStatus
from musiclib.pipeline import Hooks, Tools, is_valid_url, process_url

FFMPEG = shutil.which("ffmpeg")
EXIFTOOL = shutil.which("exiftool") or "/opt/homebrew/bin/exiftool"
needs_media_tools = pytest.mark.skipif(
    FFMPEG is None or not os.path.exists(EXIFTOOL),
    reason="ffmpeg/exiftool이 필요합니다",
)

TITLE = "아이유(IU) - 밤편지"


def _fake_ytdlp(tmp_path: Path, title: str = TITLE, fail: bool = False) -> str:
    """title 이름의 M4A(무음)와 PNG 썸네일을 만드는 가짜 yt-dlp."""
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    audio_src = src / f"{title}.m4a"
    thumb_src = src / f"{title}.png"
    if FFMPEG:
        subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", "1", "-c:a", "aac", str(audio_src)],
            check=True,
        )
        subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=green:s=64x64",
             "-frames:v", "1", str(thumb_src)],
            check=True,
        )
    body = f"""#!/bin/sh
case "$*" in
  *"--print filename"*) echo "{title}.webm"; exit 0 ;;
esac
if [ "{int(fail)}" = "1" ]; then echo 'ERROR: Video unavailable' >&2; exit 1; fi
out=""; prev=""
for a in "$@"; do if [ "$prev" = "-P" ]; then out="$a"; fi; prev="$a"; done
echo "[download] 100.0% of 1MiB"
cp "{audio_src}" "$out/{title}.m4a"
cp "{thumb_src}" "$out/{title}.png"
echo "$out/{title}.m4a"
"""
    path = tmp_path / "bin" / "yt-dlp"
    path.parent.mkdir(exist_ok=True)
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


@pytest.mark.parametrize(
    "url, ok",
    [
        ("https://www.youtube.com/watch?v=x", True),
        ("http://youtu.be/x", True),
        ("", False),
        ("ftp://x", False),
        ("https://", False),
        ("youtube.com/watch", False),
    ],
)
def test_url_validation(url, ok):
    assert is_valid_url(url) is ok


def test_invalid_url_is_failed_without_running_tools(tmp_path):
    result = process_url("bad", tmp_path, Tools("nope", "nope", "nope"))
    assert result.status is JobStatus.FAILED


def test_ytdlp_failure_is_reported_not_raised(tmp_path):
    tools = Tools(_fake_ytdlp(tmp_path, fail=True), "ffmpeg", EXIFTOOL)
    result = process_url("https://www.youtube.com/watch?v=x", tmp_path / "out", tools)
    assert result.status is JobStatus.FAILED
    assert "Video unavailable" in result.detail


@needs_media_tools
def test_full_pipeline_succeeds_and_tags_file(tmp_path):
    out = tmp_path / "out"
    tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)
    statuses = []
    result = process_url(
        "https://www.youtube.com/watch?v=x",
        out,
        tools,
        Hooks(on_status=statuses.append),
    )
    assert result.status is JobStatus.DONE, result.detail
    assert result.audio == out / f"{TITLE}.m4a"
    assert statuses[-1] is JobStatus.DONE
    assert JobStatus.VERIFYING in statuses


@needs_media_tools
def test_existing_file_is_kept_by_default(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / f"{TITLE}.m4a").write_bytes(b"keep me")
    tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)
    result = process_url("https://www.youtube.com/watch?v=x", out, tools)
    assert result.status is JobStatus.SKIPPED
    assert (out / f"{TITLE}.m4a").read_bytes() == b"keep me"


@needs_media_tools
def test_user_declining_write_keeps_downloaded_file(tmp_path):
    out = tmp_path / "out"
    tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)
    result = process_url(
        "https://www.youtube.com/watch?v=x",
        out,
        tools,
        Hooks(confirm_write=lambda meta: False),
    )
    assert result.status is JobStatus.SKIPPED
    assert result.audio is not None and result.audio.exists()


@needs_media_tools
def test_ambiguous_name_asks_user_for_artist_and_title(tmp_path):
    # 구분자가 여러 개라 자동 판단할 수 없는 이름 (커버 형식도 아님)
    title = "곡 이름 - 부제 - 추가 설명"
    out = tmp_path / "out"
    asked = []

    def ask(album):
        asked.append(album)
        return ("가수", "수평선")

    tools = Tools(_fake_ytdlp(tmp_path, title=title), FFMPEG, EXIFTOOL)
    result = process_url("https://www.youtube.com/watch?v=x", out, tools, Hooks(ask_artist_title=ask))
    assert asked == [title]
    assert result.status is JobStatus.DONE, result.detail
