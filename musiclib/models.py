"""작업(URL 한 개)의 상태와 결과 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class JobStatus(str, Enum):
    WAITING = "대기 중"
    DOWNLOADING = "다운로드 중"
    THUMBNAIL = "썸네일 처리 중"
    TAGGING = "메타데이터 기록 중"
    VERIFYING = "검증 중"
    DONE = "완료"
    FAILED = "실패"
    CANCELLED = "취소됨"
    SKIPPED = "건너뜀"


@dataclass
class JobResult:
    status: JobStatus
    detail: str = ""
    audio: Optional[Path] = None
    thumbnail: Optional[Path] = None
    # 판단하거나 입력받은 메타데이터 (상세 패널 표시용). 기록 전에 중단되면 None
    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    problems: list[str] = field(default_factory=list)
