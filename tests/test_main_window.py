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
    _OPENED.clear()
    QThreadPool.globalInstance().waitForDone(10_000)
    qapp.processEvents()


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


def test_remove_only_waiting_items_and_reindexes(qapp, tmp_path):
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
