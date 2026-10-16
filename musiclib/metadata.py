"""ExifTool로 Artist/Title/Album과 앨범 아트를 기록·검증한다. Genre는 다루지 않는다."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .runner import ToolError, run_checked

JPEG_MAGIC = b"\xff\xd8"


@dataclass
class Metadata:
    album: str
    artist: Optional[str] = None
    title: Optional[str] = None


def is_jpeg(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(2) == JPEG_MAGIC


def write_tags(exiftool: str, audio: Path, jpg: Path, meta: Metadata, env: Optional[dict] = None) -> None:
    """인자 리스트로 전달하므로 한글·공백·괄호가 있어도 안전하다.

    ExifTool 기본 동작대로 원본을 `_original` 백업으로 남긴다.
    """
    cmd = [exiftool, "-charset", "filename=UTF8"]
    if meta.artist:
        cmd.append(f"-Artist={meta.artist}")
    if meta.title:
        cmd.append(f"-Title={meta.title}")
    cmd.append(f"-Album={meta.album}")
    cmd.append(f"-CoverArt<={jpg}")
    cmd.append(str(audio))
    run_checked(cmd, env=env)


def verify(exiftool: str, audio: Path, jpg: Path, meta: Metadata, env: Optional[dict] = None) -> list[str]:
    """기록 결과를 다시 읽어 확인한다. 문제 목록을 반환하며, 빈 리스트면 통과."""
    out = run_checked(
        [exiftool, "-j", "-charset", "filename=UTF8", "-Artist", "-Title", "-Album", str(audio)],
        env=env,
    )
    try:
        data = json.loads(out)[0]
    except (json.JSONDecodeError, IndexError) as e:
        raise ToolError(f"ExifTool 출력을 해석할 수 없습니다: {e}") from e

    problems = []
    if meta.artist and data.get("Artist") != meta.artist:
        problems.append(f"Artist 불일치(기대 {meta.artist!r}, 실제 {data.get('Artist')!r})")
    if meta.title and data.get("Title") != meta.title:
        problems.append(f"Title 불일치(기대 {meta.title!r}, 실제 {data.get('Title')!r})")
    if data.get("Album") != meta.album:
        problems.append(f"Album 불일치(기대 {meta.album!r}, 실제 {data.get('Album')!r})")

    cover = subprocess.run([exiftool, "-b", "-CoverArt", str(audio)], capture_output=True, env=env)
    if cover.returncode != 0 or not cover.stdout:
        problems.append("앨범 아트(CoverArt)가 삽입되지 않았습니다")
    elif cover.stdout != jpg.read_bytes():
        problems.append("앨범 아트 내용이 JPEG 파일과 다릅니다")
    return problems
