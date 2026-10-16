import shutil
import stat
import subprocess
import threading

import pytest

from musiclib.downloader import download, ensure_jpeg, existing_outputs, expected_stem
from musiclib.runner import Cancelled, ToolError

FFMPEG = shutil.which("ffmpeg")

# 네트워크 없이 yt-dlp 동작을 흉내 내는 가짜 실행 파일
FAKE_YTDLP = r"""#!/bin/sh
case "$*" in
  *"--print filename"*) echo "테스트 - 곡 제목 COVER.webm"; exit 0 ;;
esac
out=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-P" ]; then out="$a"; fi
  prev="$a"
done
echo "[download]   0.0% of 4.00MiB"
echo "[download]  50.0% of 4.00MiB"
echo "[download] 100.0% of 4.00MiB"
echo "[ExtractAudio] Destination: $out/곡.m4a"
printf 'm4a' > "$out/곡.m4a"
printf 'webp' > "$out/곡.webp"
echo "$out/곡.m4a"
"""

FAKE_YTDLP_FAIL = "#!/bin/sh\necho 'ERROR: Video unavailable' >&2\nexit 1\n"


def _install(tmp_path, body, name="yt-dlp"):
    path = tmp_path / "bin" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_expected_stem_strips_extension(tmp_path):
    ytdlp = _install(tmp_path, FAKE_YTDLP)
    assert expected_stem(ytdlp, "https://www.youtube.com/watch?v=x") == "테스트 - 곡 제목 COVER"


def test_download_reports_real_progress_and_returns_m4a(tmp_path):
    ytdlp = _install(tmp_path, FAKE_YTDLP)
    out = tmp_path / "out"
    out.mkdir()
    seen = []
    audio = download(ytdlp, "https://www.youtube.com/watch?v=x", out, on_progress=seen.append)
    assert audio == out / "곡.m4a"
    assert seen == [0.0, 50.0, 100.0]


def test_download_failure_reports_reason(tmp_path):
    ytdlp = _install(tmp_path, FAKE_YTDLP_FAIL)
    with pytest.raises(ToolError, match="Video unavailable"):
        download(ytdlp, "https://www.youtube.com/watch?v=x", tmp_path)


def test_download_cancel_raises_cancelled(tmp_path):
    slow = _install(tmp_path, "#!/bin/sh\necho '[download]  10.0%'\nsleep 60\n")
    cancel = threading.Event()
    timer = threading.Timer(0.5, cancel.set)
    timer.start()
    with pytest.raises(Cancelled):
        download(slow, "https://www.youtube.com/watch?v=x", tmp_path, cancel=cancel)
    timer.cancel()


def test_existing_outputs_lists_conflicts(tmp_path):
    (tmp_path / "곡.m4a").write_bytes(b"x")
    assert existing_outputs(tmp_path, "곡") == [tmp_path / "곡.m4a"]
    assert existing_outputs(tmp_path, "없음") == []


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg가 필요합니다")
def test_ensure_jpeg_converts_png_thumbnail(tmp_path):
    # 테스트 환경의 ffmpeg에 webp 인코더가 없어서 PNG 썸네일로 변환 경로를 검증한다
    audio = tmp_path / "곡 (테스트).m4a"
    audio.write_bytes(b"m4a")
    thumb = tmp_path / "곡 (테스트).png"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64",
         "-frames:v", "1", str(thumb)],
        check=True,
    )
    jpg = ensure_jpeg(FFMPEG, audio)
    assert jpg == tmp_path / "곡 (테스트).jpg"
    assert jpg.read_bytes()[:2] == b"\xff\xd8"


def test_ensure_jpeg_fails_without_thumbnail(tmp_path):
    audio = tmp_path / "곡.m4a"
    audio.write_bytes(b"m4a")
    with pytest.raises(ToolError, match="썸네일을 찾을 수 없습니다"):
        ensure_jpeg("ffmpeg", audio)
