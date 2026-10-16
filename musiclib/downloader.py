"""yt-dlp 다운로드, 파일명 확인, 썸네일 JPEG 확보."""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Callable, Optional

from .metadata import is_jpeg
from .naming import AUDIO_EXT, base_name
from .runner import ToolError, run_checked, run_command

PERCENT_PATTERN = re.compile(r"\[download\]\s+([\d.]+)%")
THUMB_SUFFIXES = {".webp", ".png"}


def expected_stem(ytdlp: str, url: str, env: Optional[dict] = None) -> str:
    """다운로드 없이 yt-dlp가 만들 파일명(확장자 제외)을 구한다."""
    out = run_checked(
        [ytdlp, "--no-playlist", "--print", "filename", "-o", "%(title)s.%(ext)s", url],
        env=env,
    )
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        raise ToolError("yt-dlp가 파일명을 반환하지 않았습니다(잘못된 URL 가능성)")
    return lines[-1].rsplit(".", 1)[0]


def existing_outputs(out_dir: Path, stem: str) -> list[Path]:
    """같은 이름으로 이미 존재하는 결과물 목록."""
    return [p for p in (out_dir / f"{stem}{AUDIO_EXT}", out_dir / f"{stem}.jpg") if p.exists()]


def download(
    ytdlp: str,
    url: str,
    out_dir: Path,
    *,
    overwrite: bool = False,
    env: Optional[dict] = None,
    on_progress: Optional[Callable[[float], None]] = None,
    cancel: Optional[threading.Event] = None,
) -> Path:
    """오디오(M4A)와 썸네일(JPEG)을 내려받고 최종 M4A 경로를 반환한다.

    on_progress에는 오디오 다운로드 진행률(0~100)만 전달한다. 실제 값만 보고하며 임의 값은 만들지 않는다.
    """
    cmd = [
        ytdlp,
        "--no-playlist",
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "-x", "--audio-format", "m4a",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-P", str(out_dir),
        "-o", "%(title)s.%(ext)s",
        "--no-simulate",
        "--newline", "--progress",
        "--print", "after_move:filepath",
        "--force-overwrites" if overwrite else "--no-overwrites",
        url,
    ]

    def handle_line(line: str) -> None:
        match = PERCENT_PATTERN.search(line)
        if match and on_progress:
            on_progress(float(match.group(1)))

    result = run_command(cmd, env=env, on_line=handle_line, cancel=cancel)
    if result.returncode != 0:
        tail = [line for line in result.lines if line.strip() and not line.startswith("[")]
        reason = tail[-1] if tail else "출력 없음"
        raise ToolError(f"다운로드 실패(종료 코드 {result.returncode}): {reason}")

    # 최종 경로는 after_move:filepath 출력의 마지막 .m4a 줄이다
    paths = [line.strip() for line in result.lines if line.strip().endswith(AUDIO_EXT)]
    if not paths:
        raise ToolError("다운로드 결과 경로를 확인할 수 없습니다")
    audio = Path(paths[-1])
    if not audio.exists():
        raise ToolError(f"M4A 파일이 생성되지 않았습니다: {audio.name}")
    return audio


def ensure_jpeg(ffmpeg: str, audio: Path, env: Optional[dict] = None) -> Path:
    """오디오와 같은 기본 파일명의 JPEG를 확보한다. 없으면 원본 썸네일을 변환한다."""
    base = base_name(audio)
    jpg = audio.parent / f"{base}.jpg"
    if not jpg.exists():
        thumb = next(
            (
                p
                for p in audio.parent.iterdir()
                if p.name.startswith(base + ".") and p.suffix.lower() in THUMB_SUFFIXES
            ),
            None,
        )
        if thumb is None:
            raise ToolError("썸네일을 찾을 수 없습니다(썸네일 다운로드 실패 가능성)")
        # -n: 기존 파일을 덮어쓰지 않는다
        run_checked(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-n", "-i", str(thumb), "-q:v", "2", str(jpg)],
            env=env,
        )
    if not is_jpeg(jpg):
        raise ToolError(f"JPEG 형식이 아닙니다: {jpg.name}")
    return jpg
