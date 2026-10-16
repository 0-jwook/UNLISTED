import sys
import threading
import time

import pytest

from musiclib.runner import Cancelled, ToolError, run_checked, run_command


def test_collects_stdout_and_stderr_lines():
    cmd = [sys.executable, "-c", "print('가 나 다', flush=True); import sys; print('err 라인', file=sys.stderr, flush=True)"]
    result = run_command(cmd)
    assert result.returncode == 0
    assert result.lines == ["가 나 다", "err 라인"]


def test_streams_each_line_to_callback():
    seen = []
    cmd = [sys.executable, "-c", "for i in range(3): print(f'line {i}')"]
    run_command(cmd, on_line=seen.append)
    assert seen == ["line 0", "line 1", "line 2"]


def test_arguments_with_spaces_and_brackets_are_passed_intact():
    text = "아이유(IU) - 밤편지 [x] (y)"
    cmd = [sys.executable, "-c", "import sys; print(sys.argv[1])", text]
    assert run_checked(cmd) == text


def test_run_checked_raises_with_reason_on_failure():
    cmd = [sys.executable, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(3)"]
    with pytest.raises(ToolError, match="종료 코드 3.*boom"):
        run_checked(cmd)


def test_cancel_terminates_process_group_promptly():
    cancel = threading.Event()
    # 자식이 또 다른 자식을 띄워도 그룹째로 종료되어야 한다
    script = (
        "import subprocess, sys, time;"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "print('started', flush=True);"
        "time.sleep(60)"
    )
    timer = threading.Timer(1.0, cancel.set)
    timer.start()
    start = time.monotonic()
    with pytest.raises(Cancelled):
        run_command([sys.executable, "-c", script], cancel=cancel)
    timer.cancel()
    assert time.monotonic() - start < 15
