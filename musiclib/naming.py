"""파일명에서 Artist/Title/Album을 판단하는 순수 함수 모음. 외부 프로그램을 호출하지 않는다."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

AUDIO_EXT = ".m4a"
# 자동 분리 구분자 (정확히 한 번 나올 때만 자동 분리)
SEPARATOR = " - "
# "곡 제목 / 커버 아티스트 COVER" 형식의 구분자 (파일명에서는 "/"가 "⧸"로 바뀜)
SLASH_SEPARATORS = (" ⧸ ", " / ")
COVER_PATTERN = re.compile(r"(.+?)\s+COVER", re.IGNORECASE)
# 제목 뒤에 붙은 [..] 또는 『..』 설명 블록 제거용
DECORATION_PATTERN = re.compile(r"\s*[\[『][^\]』]*[\]』]")


def base_name(audio: Path) -> str:
    """'.m4a' 확장자만 제거한 전체 파일명 (Album 값)."""
    if not audio.name.endswith(AUDIO_EXT):
        raise ValueError(f"M4A 파일이 아닙니다: {audio.name}")
    return audio.name[: -len(AUDIO_EXT)]


def parse_cover_title(album: str) -> Optional[tuple[str, str]]:
    """'곡 제목 / 커버 아티스트 COVER' 형태면 (커버 아티스트, 곡 제목)을 반환한다.

    예: 'One Last Kiss - 『원곡 정보』 ⧸ 하나코 나나 COVER' → ('하나코 나나', 'One Last Kiss')
    """
    for sep in SLASH_SEPARATORS:
        idx = album.rfind(sep)
        if idx == -1:
            continue
        left, right = album[:idx].strip(), album[idx + len(sep):].strip()
        cover = COVER_PATTERN.fullmatch(right)
        if not cover:
            continue
        # 곡 제목은 첫 " - " 앞부분에서, 설명 블록을 뺀 나머지다
        title = DECORATION_PATTERN.sub("", left.split(SEPARATOR, 1)[0]).strip()
        artist = cover.group(1).strip()
        if artist and title:
            return artist, title
    return None


def parse_artist_title(album: str) -> Optional[tuple[str, str]]:
    """Artist, Title을 파일명에서 판단한다. 판단할 수 없으면 None.

    1) 커버 형식 '곡 제목 / 커버 아티스트 COVER'
    2) ' - '가 정확히 하나인 '아티스트 - 제목'
    """
    cover = parse_cover_title(album)
    if cover:
        return cover
    parts = album.split(SEPARATOR)
    if len(parts) != 2:
        return None
    artist, title = parts[0].strip(), parts[1].strip()
    if not artist or not title:
        return None
    return artist, title
