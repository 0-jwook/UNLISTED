"""유튜브 URL 정규화, 영상 ID 추출, 여러 줄 붙여넣기 분리."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_id(url: str) -> Optional[str]:
    """유튜브 URL에서 11자리 영상 ID를 뽑는다. 유튜브 주소가 아니면 None."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    candidate = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in {"youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        else:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
                candidate = parts[1]
    if candidate and VIDEO_ID_PATTERN.match(candidate):
        return candidate
    return None


def split_pasted(text: str) -> list[str]:
    """여러 줄(또는 공백)로 붙여넣은 URL 목록을 나눈다. 빈 항목은 버린다."""
    return [token for token in re.split(r"\s+", text.strip()) if token]
