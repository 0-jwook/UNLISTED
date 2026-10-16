"""백그라운드 다운로드 워커와 GUI 브리지.

작업 스레드는 파이프라인을 실행하고, 사용자 확인이 필요하면 브리지 신호로 메인 스레드에 요청한 뒤
응답이 올 때까지 기다린다. 메인 스레드(UI)는 그동안 계속 반응한다.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, QRunnable, QThread, Signal

from musiclib.downloader import expected_stem
from musiclib.models import JobResult, JobStatus
from musiclib.pipeline import Hooks, Tools, process_url

POLL_SECONDS = 0.2


UNANSWERED = object()  # 응답 없음과 None(=기록 안 함) 응답을 구분하기 위한 표식


@dataclass
class Ask:
    """메인 스레드가 응답을 채우고 event로 알리는 요청 상자."""

    kind: str
    payload: Any
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = UNANSWERED


class Bridge(QObject):
    """워커 스레드 → 메인 스레드 신호 모음. 모든 신호는 큐를 거쳐 메인 스레드에서 처리된다."""

    status = Signal(int, object)  # (작업 번호, JobStatus)
    progress = Signal(int, float)  # (작업 번호, 0~100 실제 진행률)
    log = Signal(str)
    finished_job = Signal(int, object)  # (작업 번호, JobResult)
    title_ready = Signal(int, str)  # (작업 번호, 영상 제목)
    title_failed = Signal(int, str)
    ask = Signal(object)  # Ask


class DownloadWorker(QThread):
    """작업 목록을 순서대로 처리한다. 한 곡이 실패해도 다음 곡을 계속 처리한다."""

    def __init__(self, jobs: list[tuple[int, str]], out_dir: Path, tools: Tools, bridge: Bridge,
                 cancel: threading.Event, cleanup: bool = True, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.jobs = jobs
        self.out_dir = out_dir
        self.tools = tools
        self.bridge = bridge
        self.cancel = cancel
        self.cleanup = cleanup

    def run(self) -> None:
        for index, url in self.jobs:
            if self.cancel.is_set():
                self.bridge.finished_job.emit(index, JobResult(JobStatus.CANCELLED, "사용자가 취소했습니다"))
                continue
            hooks = self._hooks(index)
            result = process_url(url, self.out_dir, self.tools, hooks, self.cancel, cleanup=self.cleanup)
            self.bridge.finished_job.emit(index, result)

    def _hooks(self, index: int) -> Hooks:
        return Hooks(
            confirm_overwrite=lambda paths: self._ask(index, "overwrite", paths, default=False),
            ask_artist_title=lambda album: self._ask(index, "artist_title", album, default=(None, None)),
            # 취소되면 기록하지 않는다(None)
            confirm_write=lambda meta: self._ask(index, "confirm_write", meta, default=None),
            on_status=lambda status: self.bridge.status.emit(index, status),
            on_progress=lambda percent: self.bridge.progress.emit(index, percent),
            log=lambda message: self.bridge.log.emit(f"[{index + 1}] {message}"),
        )

    def _ask(self, index: int, kind: str, payload: Any, default: Any) -> Any:
        """메인 스레드에 질문하고 응답을 기다린다. 취소되면 기본값을 돌려준다."""
        ask = Ask(kind=kind, payload=(index, payload))
        self.bridge.ask.emit(ask)
        while not ask.event.wait(POLL_SECONDS):
            if self.cancel.is_set():
                return default
        return default if ask.result is UNANSWERED else ask.result


class TitleLookup(QRunnable):
    """목록에 추가할 때 영상 제목(파일명)을 백그라운드로 가져온다."""

    def __init__(self, index: int, url: str, ytdlp: str, env: Optional[dict], bridge: Bridge):
        super().__init__()
        self.index = index
        self.url = url
        self.ytdlp = ytdlp
        self.env = env
        self.bridge = bridge

    def run(self) -> None:
        try:
            stem = expected_stem(self.ytdlp, self.url, env=self.env)
        except Exception as e:  # 제목 조회 실패는 목록에 표시만 하고 계속 진행한다
            self.bridge.title_failed.emit(self.index, str(e))
            return
        self.bridge.title_ready.emit(self.index, stem)
