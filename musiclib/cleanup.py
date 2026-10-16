"""변환 완료 후 남는 중간 파일(썸네일, ExifTool 백업) 정리.

- 완성된 M4A는 절대 지우지 않는다.
- 이번 작업에서 새로 생긴 파일만 지운다. 작업 전부터 있던 파일은 그대로 둔다.
  단, 덮어쓰기로 교체된 썸네일은 이번 작업의 산출물이므로 지운다.
- 정리는 검증이 끝나 성공한 뒤에만 호출한다.
"""

from __future__ import annotations

from pathlib import Path

from .naming import AUDIO_EXT

THUMB_SUFFIXES = (".jpg", ".webp", ".png")
BACKUP_SUFFIX = "_original"


def snapshot(out_dir: Path) -> set[str]:
    """작업 전 폴더에 있던 파일 이름 목록."""
    if not out_dir.exists():
        return set()
    return {p.name for p in out_dir.iterdir()}


def intermediate_names(base: str) -> list[str]:
    """한 곡의 중간 파일 이름 후보. 완성 M4A(base.m4a)는 포함하지 않는다."""
    return [f"{base}{suffix}" for suffix in THUMB_SUFFIXES] + [f"{base}{AUDIO_EXT}{BACKUP_SUFFIX}"]


def remove_intermediates(out_dir: Path, base: str, before: set[str], overwrite: bool) -> list[str]:
    """지운 파일 이름 목록을 반환한다."""
    removed = []
    for name in intermediate_names(base):
        path = out_dir / name
        if not path.is_file():
            continue
        existed_before = name in before
        is_thumb = name.endswith(THUMB_SUFFIXES)
        # 작업 전부터 있었던 파일은 보존한다. 단 덮어쓰기로 새로 받은 썸네일은 예외
        if existed_before and not (overwrite and is_thumb):
            continue
        path.unlink()
        removed.append(name)
    return removed
