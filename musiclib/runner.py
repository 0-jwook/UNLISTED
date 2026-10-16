"""외부 명령 실행기. 인자 리스트 방식(shell 미사용), 줄 단위 출력 스트리밍, 취소를 지원한다."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional


class ToolError(Exception):
    """외부 명령 실패 또는 취소 외의 처리 오류."""


class Cancelled(Exception):
    """사용자 취소로 외부 명령을 중단했다."""


@dataclass
class RunResult:
    returncode: int
    lines: list[str] = field(default_factory=list)

    @property
    def output(self) -> str:
        return "\n".join(self.lines)


def run_command(
    cmd: list[str],
    *,
    env: Optional[dict[str, str]] = None,
    on_line: Optional[Callable[[str], None]] = None,
    cancel: Optional[threading.Event] = None,
) -> RunResult:
    """명령을 실행하고 stdout+stderr를 줄 단위로 모은다.

    on_line이 있으면 줄이 나올 때마다 호출한다 (진행률 파싱용).
    cancel이 설정되면 프로세스 그룹 전체를 종료하고 Cancelled를 던진다.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        # 새 프로세스 그룹으로 실행해야 취소 시 yt-dlp가 띄운 ffmpeg까지 함께 종료된다
        start_new_session=True,
    )
    # 출력이 없어도 취소에 바로 반응하도록, 취소 신호를 별도 스레드가 감시한다
    stop_watch = threading.Event()
    watcher = None
    if cancel is not None:
        watcher = threading.Thread(target=_watch_cancel, args=(proc, cancel, stop_watch), daemon=True)
        watcher.start()

    lines: list[str] = []
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            lines.append(line)
            if on_line:
                on_line(line)
        returncode = proc.wait()
    finally:
        stop_watch.set()
        if watcher is not None:
            watcher.join()
        if proc.poll() is None:
            _kill_group(proc)

    if cancel is not None and cancel.is_set():
        raise Cancelled("사용자가 작업을 취소했습니다")
    return RunResult(returncode=returncode, lines=lines)


def _watch_cancel(proc: subprocess.Popen, cancel: threading.Event, stop: threading.Event) -> None:
    while not stop.is_set():
        if cancel.wait(timeout=0.2):
            _kill_group(proc)
            return


def run_checked(cmd: list[str], *, env: Optional[dict[str, str]] = None) -> str:
    """실패하면 ToolError를 던지고, 성공하면 출력 문자열을 반환한다."""
    result = run_command(cmd, env=env)
    if result.returncode != 0:
        tail = [line for line in result.lines if line.strip()]
        reason = tail[-1] if tail else "출력 없음"
        raise ToolError(f"{os.path.basename(cmd[0])} 실패(종료 코드 {result.returncode}): {reason}")
    return result.output


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
