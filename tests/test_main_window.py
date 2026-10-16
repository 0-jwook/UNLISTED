import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QSettings, QThreadPool  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from musiclib.models import JobStatus  # noqa: E402
from musiclib.pipeline import Tools  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.settings import AppSettings  # noqa: E402

from test_pipeline import EXIFTOOL, FFMPEG, TITLE, _fake_ytdlp  # noqa: E402

MEDIA_OK = FFMPEG is not None and os.path.exists(EXIFTOOL)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _close_windows(qapp):
    yield
    # 창을 닫고 백그라운드 제목 조회가 끝난 뒤에 테스트를 마친다 (삭제 중 신호 사용 방지)
    for window in _OPENED:
        window.close()
        window.deleteLater()
    _OPENED.clear()
    QThreadPool.globalInstance().waitForDone(10_000)
    qapp.processEvents()
    qapp.sendPostedEvents(None, 0)


_OPENED: list[MainWindow] = []


def _settings(tmp_path):
    store = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)
    return AppSettings(store)


def _window(qapp, tmp_path, tools=None, missing=()):
    window = MainWindow(_settings(tmp_path), tools, list(missing))
    window._out_dir = tmp_path / "out"
    _OPENED.append(window)
    return window


def _wait_until_idle(qapp, window, timeout=60):
    deadline = time.monotonic() + timeout
    while window._is_running() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    qapp.processEvents()


def test_adding_urls_skips_invalid_and_duplicates(qapp, tmp_path):
    window = _window(qapp, tmp_path, tools=None, missing=["yt-dlp"])
    window._add_urls([
        "https://www.youtube.com/watch?v=lZHyUw7LWSw",
        "https://youtu.be/lZHyUw7LWSw",  # 같은 영상 ID → 중복
        "not-a-url",
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
    ])
    assert [i.url for i in window._items] == [
        "https://www.youtube.com/watch?v=lZHyUw7LWSw",
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
    ]
    assert window._table.rowCount() == 2


def test_start_is_disabled_without_tools(qapp, tmp_path):
    window = _window(qapp, tmp_path, tools=None, missing=["ffmpeg"])
    window._add_urls(["https://www.youtube.com/watch?v=lZHyUw7LWSw"])
    assert not window._start_btn.isEnabled()


def test_remove_selected_item_and_reindexes(qapp, tmp_path):
    window = _window(qapp, tmp_path, tools=None, missing=["yt-dlp"])
    window._add_urls([
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
        "https://www.youtube.com/watch?v=ccccccccccc",
    ])
    window._table.selectRow(0)
    window._remove_selected()
    assert [i.url[-11:] for i in window._items] == ["bbbbbbbbbbb", "ccccccccccc"]
    assert window._table.rowCount() == 2
    assert window._table.item(0, 0).text() == window._items[0].title


def test_full_run_with_fake_tools_shows_result(qapp, tmp_path, monkeypatch):
    if not MEDIA_OK:
        pytest.skip("ffmpeg/exiftool이 필요합니다")
    # 덮어쓰기 질문이 없도록 임시 폴더를 쓰고, 기록 확인은 자동으로 예
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    # 기록 확인은 '예'로 답한다 (실제 대화상자 대신)
    monkeypatch.setattr(MainWindow, "_confirm_write_dialog", lambda self, meta: meta)
    tools = Tools(_fake_ytdlp(tmp_path), FFMPEG, EXIFTOOL)
    window = _window(qapp, tmp_path, tools=tools)
    window._add_urls(["https://www.youtube.com/watch?v=lZHyUw7LWSw"])
    window._start()
    _wait_until_idle(qapp, window)

    item = window._items[0]
    assert item.status is JobStatus.DONE, item.result and item.result.detail
    assert item.result.artist == "아이유(IU)"
    assert item.result.title == "밤편지"
    assert item.result.album == TITLE
    assert (window._out_dir / f"{TITLE}.m4a").exists()
    assert window._table.item(0, 1).text() == JobStatus.DONE.value
    assert window._table.cellWidget(0, 2).value() == 100


def _select(window, *rows):
    """여러 행을 함께 선택한다. selectRow()는 이전 선택을 바꾸므로 선택 모델을 직접 쓴다."""
    from PySide6.QtCore import QItemSelectionModel

    window._table.clearSelection()
    selection = window._table.selectionModel()
    for row in rows:
        index = window._table.model().index(row, 0)
        selection.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)


def test_can_remove_finished_and_failed_items(qapp, tmp_path):
    from musiclib.models import JobStatus

    window = _window(qapp, tmp_path, tools=None, missing=["yt-dlp"])
    window._add_urls([
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
    ])
    window._items[0].status = JobStatus.FAILED
    window._items[1].status = JobStatus.DONE
    _select(window, 0, 1)
    window._refresh_controls()
    assert window._remove_btn.isEnabled()
    window._remove_selected()
    assert window._items == []
    assert window._table.rowCount() == 0


def test_restart_requeues_only_restartable_items(qapp, tmp_path, monkeypatch):
    from musiclib.models import JobStatus

    window = _window(qapp, tmp_path, tools=None, missing=["yt-dlp"])
    window._add_urls([
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
        "https://www.youtube.com/watch?v=ccccccccccc",
    ])
    window._items[0].status = JobStatus.CANCELLED
    window._items[1].status = JobStatus.DONE
    window._items[2].status = JobStatus.SKIPPED
    started = []
    monkeypatch.setattr(MainWindow, "_start", lambda self: started.append(True))
    _select(window, 0, 1, 2)
    window._restart_selected()
    assert [i.status for i in window._items] == [JobStatus.WAITING, JobStatus.DONE, JobStatus.WAITING]
    assert started == [True]


def test_title_update_targets_the_right_item_after_deletion(qapp, tmp_path):
    window = _window(qapp, tmp_path, tools=None, missing=["yt-dlp"])
    window._add_urls([
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
        "https://www.youtube.com/watch?v=ccccccccccc",
    ])
    third_uid = window._items[2].uid
    _select(window, 0)
    window._remove_selected()
    # 앞 항목을 지워 행 번호가 바뀌어도, 고정 번호로 온 제목은 원래 항목에 붙어야 한다
    window._bridge.title_ready.emit(third_uid, "세 번째 곡")
    assert [i.title for i in window._items] == [
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
        "세 번째 곡",
    ]


def test_breakable_keeps_visible_text_and_adds_wrap_points():
    from ui.main_window import breakable

    url = "https://www.youtube.com/watch?v=lZHyUw7LWSw&t=10s"
    wrapped = breakable(url)
    assert wrapped.replace("​", "") == url
    assert "/​" in wrapped and "?​" in wrapped and "&​" in wrapped


def test_breakable_splits_long_unbroken_runs():
    from ui.main_window import breakable

    run = "PL" + "x" * 80
    wrapped = breakable(run)
    assert wrapped.replace("​", "") == run
    # 구분 문자가 없어도 20자마다 끊을 수 있어야 한다
    chunks = wrapped.split("​")
    assert all(len(c) <= 20 for c in chunks)


def test_detail_panel_is_scrollable_with_minimum_width(qapp, tmp_path):
    from PySide6.QtWidgets import QScrollArea

    from ui.main_window import DETAIL_MIN_WIDTH

    window = _window(qapp, tmp_path, tools=None, missing=["yt-dlp"])
    scrolls = [s for s in window.findChildren(QScrollArea) if s.isAncestorOf(window._d_url)]
    assert scrolls, "상세 패널이 스크롤 영역 안에 있어야 합니다"
    assert scrolls[0].minimumWidth() == DETAIL_MIN_WIDTH
    assert window._d_url.wordWrap()
    assert DETAIL_MIN_WIDTH >= 340


def test_long_detail_text_is_wrapped_not_clipped(qapp, tmp_path):
    from musiclib.models import JobResult

    window = _window(qapp, tmp_path, tools=None, missing=["yt-dlp"])
    long_url = "https://www.youtube.com/watch?v=" + "a" * 11 + "&list=" + "b" * 120
    window._add_urls([long_url])
    window._items[0].result = JobResult(JobStatus.FAILED, "검증 실패: " + "가" * 200)
    window._table.selectRow(0)
    window._show_detail()
    window.resize(980, 640)
    window.show()
    qapp.processEvents()
    # 줄바꿈 가능한 텍스트이므로 높이가 한 줄보다 커야 한다 (잘리지 않고 여러 줄로 보임)
    assert window._d_url.height() > window._d_url.fontMetrics().height()
    assert window._d_result.height() > window._d_result.fontMetrics().height()
