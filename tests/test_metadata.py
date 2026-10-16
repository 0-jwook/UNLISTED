import os
import shutil
import subprocess

import pytest

from musiclib.metadata import Metadata, is_jpeg, verify, write_tags

FFMPEG = shutil.which("ffmpeg")
EXIFTOOL = shutil.which("exiftool") or "/opt/homebrew/bin/exiftool"

pytestmark = pytest.mark.skipif(
    FFMPEG is None or not os.path.exists(EXIFTOOL),
    reason="ffmpeg/exiftool이 필요합니다",
)


@pytest.fixture
def media(tmp_path):
    """무음 M4A와 JPEG를 임시 폴더에 만든다 (실제 음원 아님)."""
    name = "아이유(IU) - 밤편지"
    audio = tmp_path / f"{name}.m4a"
    jpg = tmp_path / f"{name}.jpg"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-c:a", "aac", str(audio)],
        check=True,
    )
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=320x320",
         "-frames:v", "1", str(jpg)],
        check=True,
    )
    return audio, jpg


def test_write_then_verify_passes(media):
    audio, jpg = media
    meta = Metadata(album="아이유(IU) - 밤편지", artist="아이유(IU)", title="밤편지")
    write_tags(EXIFTOOL, audio, jpg, meta)
    assert verify(EXIFTOOL, audio, jpg, meta) == []


def test_album_only_when_artist_and_title_unknown(media):
    audio, jpg = media
    meta = Metadata(album="아이유(IU) - 밤편지")
    write_tags(EXIFTOOL, audio, jpg, meta)
    assert verify(EXIFTOOL, audio, jpg, meta) == []


def test_verify_detects_wrong_artist(media):
    audio, jpg = media
    write_tags(EXIFTOOL, audio, jpg, Metadata(album="아이유(IU) - 밤편지", artist="아이유(IU)", title="밤편지"))
    expected = Metadata(album="아이유(IU) - 밤편지", artist="다른 가수", title="밤편지")
    problems = verify(EXIFTOOL, audio, jpg, expected)
    assert any("Artist 불일치" in p for p in problems)


def test_verify_detects_different_cover_art(media):
    audio, jpg = media
    meta = Metadata(album="아이유(IU) - 밤편지", artist="아이유(IU)", title="밤편지")
    write_tags(EXIFTOOL, audio, jpg, meta)
    # 삽입된 앨범 아트와 다른 JPEG로 비교하면 실패로 보고해야 한다
    other = jpg.with_name("other.jpg")
    other.write_bytes(b"\xff\xd8not-the-same")
    problems = verify(EXIFTOOL, audio, other, meta)
    assert any("JPEG 파일과 다릅니다" in p for p in problems)


def test_is_jpeg_checks_magic_bytes(media, tmp_path):
    _, jpg = media
    assert is_jpeg(jpg)
    fake = tmp_path / "fake.jpg"
    fake.write_bytes(b"PNG....")
    assert not is_jpeg(fake)
