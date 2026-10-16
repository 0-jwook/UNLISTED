import os
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402

from musiclib.models import JobStatus  # noqa: E402
from musiclib.pipeline import Tools  # noqa: E402
from ui.worker import Bridge, DownloadWorker  # noqa: E402

from test_pipeline import EXIFTOOL, FFMPEG, TITLE, _fake_ytdlp  # noqa: E402

pytestmark = pytest.mark.skipif(
    FFMPEG is None or not os.path.exists(EXIFTOOL) or shutil.which("ffmpeg") is None,
    reason="ffmpeg/exiftool이 필요합니다",
)


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


def _answer(bridge, answers):
    """질문이 오면 kind별 미리 정한 응답을 주는 가짜 메인 스레드."""
    asked = []

    def handle(ask):
        index, payload = ask.payload
        asked.append(ask.kind)
        ask.result = answers.get(ask.kind)
        ask.event.set()

    bridge.ask.connect(handle)
    return asked


def test_worker_continues_after_failure_and_reports_each_job(qapp, tmp_path):
    bridge = Bridge()
    results = {}
    bridge.finished_job.connect(lambda index, result: results.__setitem__(index, result))
    ok_tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)
    jobs = [(0, "bad-url"), (1, "https://www.youtube.com/watch?v=lZHyUw7LWSw")]

    worker = DownloadWorker(jobs, tmp_path / "out", ok_tools, bridge, cancel=__import__("threading").Event())
    _answer(bridge, {"confirm_write": True})
    worker.run()  # 같은 스레드에서 실행해 신호가 바로 전달되도록 한다

    assert results[0].status is JobStatus.FAILED
    assert results[1].status is JobStatus.DONE, results[1].detail
    assert (tmp_path / "out" / f"{TITLE}.m4a").exists()


def test_overwrite_question_defaults_to_keep(qapp, tmp_path):
    bridge = Bridge()
    results = {}
    bridge.finished_job.connect(lambda index, result: results.__setitem__(index, result))
    out = tmp_path / "out"
    out.mkdir()
    (out / f"{TITLE}.m4a").write_bytes(b"keep")
    tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)

    asked = _answer(bridge, {"overwrite": False})
    worker = DownloadWorker([(0, "https://www.youtube.com/watch?v=lZHyUw7LWSw")], out, tools, bridge,
                            cancel=__import__("threading").Event())
    worker.run()

    assert asked == ["overwrite"]
    assert results[0].status is JobStatus.SKIPPED
    assert (out / f"{TITLE}.m4a").read_bytes() == b"keep"


def test_cancelled_before_start_marks_remaining_jobs_cancelled(qapp, tmp_path):
    import threading

    bridge = Bridge()
    results = {}
    bridge.finished_job.connect(lambda index, result: results.__setitem__(index, result))
    cancel = threading.Event()
    cancel.set()
    tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)
    worker = DownloadWorker([(0, "https://www.youtube.com/watch?v=lZHyUw7LWSw")], tmp_path / "out", tools,
                            bridge, cancel=cancel)
    worker.run()
    assert results[0].status is JobStatus.CANCELLED
