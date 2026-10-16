"""URL 한 개를 다운로드부터 검증까지 처리한다.

사용자 확인이 필요한 지점(덮어쓰기, Artist/Title 입력, 기록 확인)은 Hooks 콜백으로 받는다.
CLI는 input()으로, GUI는 대화상자로 구현하며 파이프라인 로직은 공유한다.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .downloader import download, ensure_jpeg, existing_outputs, expected_stem
from .metadata import Metadata, verify, write_tags
from .models import JobResult, JobStatus
from .naming import base_name, parse_artist_title
from .runner import Cancelled, ToolError

URL_PREFIXES = ("http://", "https://")


@dataclass
class Tools:
    ytdlp: str
    ffmpeg: str
    exiftool: str
    env: Optional[dict] = None


@dataclass
class Hooks:
    # 같은 이름 파일이 있을 때 덮어쓸지 묻는다. 기본값은 유지(False)
    confirm_overwrite: Callable[[list[Path]], bool] = lambda paths: False
    # 자동 판단이 안 되면 (Artist, Title)을 받는다. None이면 Album만 기록
    ask_artist_title: Callable[[str], tuple[Optional[str], Optional[str]]] = lambda album: (None, None)
    # 기록 전 미리보기 확인. False면 기록하지 않는다
    confirm_write: Callable[[Metadata], bool] = lambda meta: True
    on_status: Callable[[JobStatus], None] = lambda status: None
    on_progress: Callable[[float], None] = lambda percent: None
    log: Callable[[str], None] = lambda message: None


def is_valid_url(url: str) -> bool:
    # 접두사 뒤에 실제 내용이 있어야 한다 (예: "https://"만 있는 입력은 거부)
    return any(url.startswith(prefix) and len(url) > len(prefix) for prefix in URL_PREFIXES)


def process_url(
    url: str,
    out_dir: Path,
    tools: Tools,
    hooks: Hooks = Hooks(),
    cancel: Optional[threading.Event] = None,
) -> JobResult:
    """URL 하나를 처리한다. 실패·취소도 JobResult로 돌려주며 예외를 밖으로 내보내지 않는다."""
    try:
        return _process(url, out_dir, tools, hooks, cancel)
    except Cancelled as e:
        hooks.log(str(e))
        hooks.on_status(JobStatus.CANCELLED)
        return JobResult(JobStatus.CANCELLED, str(e))
    except ToolError as e:
        hooks.log(f"오류: {e}")
        hooks.on_status(JobStatus.FAILED)
        return JobResult(JobStatus.FAILED, str(e))
    except Exception as e:  # 한 곡의 예상치 못한 오류가 다음 곡을 멈추지 않게 한다
        hooks.log(f"예상치 못한 오류: {e}")
        hooks.on_status(JobStatus.FAILED)
        return JobResult(JobStatus.FAILED, f"예상치 못한 오류: {e}")


def _process(
    url: str,
    out_dir: Path,
    tools: Tools,
    hooks: Hooks,
    cancel: Optional[threading.Event],
) -> JobResult:
    if not is_valid_url(url):
        hooks.on_status(JobStatus.FAILED)
        return JobResult(JobStatus.FAILED, "잘못된 URL입니다. http:// 또는 https://로 시작해야 합니다.")

    out_dir.mkdir(parents=True, exist_ok=True)

    hooks.log("파일명 확인 중")
    stem = expected_stem(tools.ytdlp, url, env=tools.env)
    overwrite = False
    conflicts = existing_outputs(out_dir, stem)
    if conflicts:
        hooks.log(f"같은 이름의 파일이 있습니다: {', '.join(p.name for p in conflicts)}")
        if not hooks.confirm_overwrite(conflicts):
            hooks.on_status(JobStatus.SKIPPED)
            return JobResult(JobStatus.SKIPPED, "기존 파일 유지")
        overwrite = True

    hooks.on_status(JobStatus.DOWNLOADING)
    hooks.log("오디오 다운로드 중")
    audio = download(
        tools.ytdlp,
        url,
        out_dir,
        overwrite=overwrite,
        env=tools.env,
        on_progress=hooks.on_progress,
        cancel=cancel,
    )
    hooks.log(f"저장됨: {audio.name}")

    hooks.on_status(JobStatus.THUMBNAIL)
    jpg = ensure_jpeg(tools.ffmpeg, audio, env=tools.env)

    album = base_name(audio)
    parsed = parse_artist_title(album)
    if parsed:
        artist, title = parsed
        hooks.log(f"파일명에서 자동 분리: Artist={artist} / Title={title}")
    else:
        hooks.log("구분자가 하나가 아니어서 자동 분리할 수 없습니다. 직접 입력이 필요합니다.")
        artist, title = hooks.ask_artist_title(album)
    meta = Metadata(album=album, artist=artist or None, title=title or None)

    if not hooks.confirm_write(meta):
        hooks.on_status(JobStatus.SKIPPED)
        return JobResult(JobStatus.SKIPPED, f"사용자 취소(다운로드 파일 유지: {audio.name})", audio=audio)

    hooks.on_status(JobStatus.TAGGING)
    write_tags(tools.exiftool, audio, jpg, meta, env=tools.env)

    hooks.on_status(JobStatus.VERIFYING)
    problems = verify(tools.exiftool, audio, jpg, meta, env=tools.env)
    if problems:
        hooks.on_status(JobStatus.FAILED)
        return JobResult(JobStatus.FAILED, "검증 실패: " + "; ".join(problems), audio=audio, problems=problems)

    hooks.on_status(JobStatus.DONE)
    return JobResult(JobStatus.DONE, audio.name, audio=audio)
