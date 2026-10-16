"""메인 창: URL 입력·목록·상세 패널·로그·저장 위치. 실제 작업은 DownloadWorker가 맡는다."""

from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QClipboard, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from musiclib.metadata import Metadata
from musiclib.models import JobResult, JobStatus
from musiclib.pipeline import Tools, is_valid_url
from musiclib.urls import split_pasted, video_id
from ui.settings import AppSettings
from ui.worker import Ask, Bridge, DownloadWorker, TitleLookup

COL_TITLE, COL_STATUS, COL_PROGRESS = range(3)
FINISHED = {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.SKIPPED}


@dataclass
class Item:
    url: str
    title: str  # 영상 제목(파일명). 조회 전에는 URL을 보여준다
    status: JobStatus = JobStatus.WAITING
    progress: float = 0.0
    result: Optional[JobResult] = None
    title_error: Optional[str] = None


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, tools: Optional[Tools], missing: list[str]):
        super().__init__()
        self.setWindowTitle("Music Manager")
        self.resize(980, 640)
        self._settings = settings
        self._tools = tools
        self._missing = missing
        self._out_dir = settings.out_dir()
        self._items: list[Item] = []
        self._video_ids: set[str] = set()
        self._worker: Optional[DownloadWorker] = None
        self._cancel: Optional[threading.Event] = None
        self._bridge = Bridge(self)
        self._bridge.status.connect(self._on_status)
        self._bridge.progress.connect(self._on_progress)
        self._bridge.log.connect(self._log)
        self._bridge.finished_job.connect(self._on_finished)
        self._bridge.title_ready.connect(self._on_title_ready)
        self._bridge.title_failed.connect(self._on_title_failed)
        self._bridge.ask.connect(self._on_ask)

        self._build_ui()
        self._refresh_controls()
        if settings.geometry() is not None:
            self.restoreGeometry(settings.geometry())

    # ---------- 화면 구성 ----------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        if self._missing:
            banner = QLabel(
                "다음 도구가 없어 다운로드를 시작할 수 없습니다: "
                + ", ".join(self._missing)
                + "\n설치: brew install ffmpeg exiftool / python3 -m pip install -U \"yt-dlp[default]\""
            )
            banner.setWordWrap(True)
            banner.setStyleSheet("padding: 8px;")
            root.addWidget(banner)

        # URL 입력 영역
        input_row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("유튜브 URL을 입력하고 Enter 또는 추가")
        self._url_edit.returnPressed.connect(self._add_from_input)
        add_btn = QPushButton("URL 추가")
        add_btn.clicked.connect(self._add_from_input)
        paste_btn = QPushButton("붙여넣기")
        paste_btn.setToolTip("클립보드의 URL 여러 개를 한 번에 추가합니다")
        paste_btn.clicked.connect(self._add_from_clipboard)
        input_row.addWidget(self._url_edit, 1)
        input_row.addWidget(add_btn)
        input_row.addWidget(paste_btn)
        root.addLayout(input_row)

        # 목록 + 상세 패널
        splitter = QSplitter(Qt.Horizontal)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["영상", "상태", "진행률"])
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().resizeSection(COL_STATUS, 130)
        self._table.horizontalHeader().resizeSection(COL_PROGRESS, 150)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._show_detail)
        splitter.addWidget(self._table)
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        # 실행 버튼
        action_row = QHBoxLayout()
        self._remove_btn = QPushButton("선택 삭제")
        self._remove_btn.clicked.connect(self._remove_selected)
        self._cleanup_box = QCheckBox("완료 후 썸네일·백업 파일 삭제")
        self._cleanup_box.setToolTip("완성된 M4A만 남기고, 이번 작업에서 만든 썸네일과 백업을 지웁니다")
        self._cleanup_box.setChecked(self._settings.cleanup_enabled())
        self._cleanup_box.toggled.connect(self._settings.set_cleanup_enabled)
        self._start_btn = QPushButton("다운로드 시작")
        self._start_btn.setDefault(True)
        self._start_btn.clicked.connect(self._start)
        self._cancel_btn = QPushButton("취소")
        self._cancel_btn.clicked.connect(self._cancel_run)
        action_row.addWidget(self._remove_btn)
        action_row.addStretch(1)
        action_row.addWidget(self._cleanup_box)
        action_row.addWidget(self._cancel_btn)
        action_row.addWidget(self._start_btn)
        root.addLayout(action_row)

        # 저장 위치
        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("저장 위치:"))
        self._out_label = QLabel(str(self._out_dir))
        self._out_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        save_row.addWidget(self._out_label, 1)
        choose_btn = QPushButton("폴더 선택…")
        choose_btn.clicked.connect(self._choose_out_dir)
        open_btn = QPushButton("폴더 열기")
        open_btn.clicked.connect(lambda: subprocess.run(["open", str(self._out_dir)]))
        save_row.addWidget(choose_btn)
        save_row.addWidget(open_btn)
        root.addLayout(save_row)

        # 로그
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(2000)
        self._log_view.setMaximumHeight(160)
        root.addWidget(self._log_view)

        self.setCentralWidget(central)
        self.statusBar().showMessage("준비됨")

    def _build_detail_panel(self) -> QWidget:
        box = QGroupBox("상세 정보")
        layout = QVBoxLayout(box)
        form = QFormLayout()
        self._d_url = QLabel("-")
        self._d_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._d_url.setWordWrap(True)
        self._d_file = QLabel("-")
        self._d_file.setWordWrap(True)
        self._d_artist = QLabel("-")
        self._d_title = QLabel("-")
        self._d_album = QLabel("-")
        self._d_album.setWordWrap(True)
        self._d_result = QLabel("-")
        self._d_result.setWordWrap(True)
        for label, widget in (
            ("URL", self._d_url),
            ("파일명", self._d_file),
            ("Artist", self._d_artist),
            ("Title", self._d_title),
            ("Album", self._d_album),
            ("결과", self._d_result),
        ):
            form.addRow(label + ":", widget)
        layout.addLayout(form)
        self._d_thumb = QLabel()
        self._d_thumb.setFixedSize(180, 180)
        self._d_thumb.setAlignment(Qt.AlignCenter)
        self._d_thumb.setStyleSheet("border: 1px solid palette(mid);")
        layout.addWidget(self._d_thumb, 0, Qt.AlignHCenter)
        reveal = QPushButton("Finder에서 보기")
        reveal.clicked.connect(self._reveal_selected)
        layout.addWidget(reveal, 0, Qt.AlignHCenter)
        layout.addStretch(1)
        return box

    # ---------- URL 목록 ----------

    def _add_from_input(self) -> None:
        text = self._url_edit.text()
        self._url_edit.clear()
        self._add_urls(split_pasted(text))

    def _add_from_clipboard(self) -> None:
        text = QApplication.clipboard().text(QClipboard.Clipboard)
        self._add_urls(split_pasted(text))

    def _add_urls(self, urls: list[str]) -> None:
        added = 0
        for url in urls:
            if not is_valid_url(url):
                self._log(f"잘못된 URL 형식이라 추가하지 않음: {url}")
                continue
            vid = video_id(url)
            key = vid or url
            if key in self._video_ids:
                self._log(f"이미 목록에 있는 URL이라 건너뜀: {url}")
                continue
            self._video_ids.add(key)
            index = len(self._items)
            self._items.append(Item(url=url, title=url))
            self._insert_row(index)
            added += 1
            self._lookup_title(index, url)
        if added:
            self.statusBar().showMessage(f"{added}개 추가됨")
        self._refresh_controls()

    def _insert_row(self, index: int) -> None:
        self._table.insertRow(index)
        self._table.setItem(index, COL_TITLE, QTableWidgetItem())
        self._table.setItem(index, COL_STATUS, QTableWidgetItem())
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(True)
        self._table.setCellWidget(index, COL_PROGRESS, bar)
        self._refresh_row(index)

    def _refresh_row(self, index: int) -> None:
        item = self._items[index]
        self._table.item(index, COL_TITLE).setText(item.title)
        self._table.item(index, COL_STATUS).setText(item.status.value)
        bar = self._table.cellWidget(index, COL_PROGRESS)
        bar.setValue(int(item.progress))

    def _lookup_title(self, index: int, url: str) -> None:
        if self._tools is None:
            return
        QThreadPool.globalInstance().start(
            TitleLookup(index, url, self._tools.ytdlp, self._tools.env, self._bridge)
        )

    def _remove_selected(self) -> None:
        if self._is_running():
            return
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            if self._items[row].status is not JobStatus.WAITING:
                continue
            self._video_ids.discard(video_id(self._items[row].url) or self._items[row].url)
            del self._items[row]
            self._table.removeRow(row)
        # 행 번호가 바뀌었으므로 목록 전체를 다시 그린다
        for index in range(len(self._items)):
            self._refresh_row(index)
        self._refresh_controls()

    # ---------- 실행 ----------

    def _is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _start(self) -> None:
        if self._tools is None or self._is_running():
            return
        jobs = [(i, item.url) for i, item in enumerate(self._items) if item.status is JobStatus.WAITING]
        if not jobs:
            self.statusBar().showMessage("대기 중인 항목이 없습니다")
            return
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._cancel = threading.Event()
        self._worker = DownloadWorker(
            jobs, self._out_dir, self._tools, self._bridge, self._cancel,
            cleanup=self._cleanup_box.isChecked(),
        )
        self._worker.finished.connect(self._on_worker_finished)
        self._log(f"다운로드 시작: {len(jobs)}개")
        self._refresh_controls()
        self._worker.start()

    def _cancel_run(self) -> None:
        if self._cancel is not None and self._is_running():
            self._cancel.set()
            self._log("취소 요청됨 (진행 중인 작업을 종료합니다)")

    def _on_worker_finished(self) -> None:
        self._log("모든 작업이 끝났습니다")
        self.statusBar().showMessage("완료")
        self._refresh_controls()

    # ---------- 브리지 신호 처리 (메인 스레드) ----------

    def _on_status(self, index: int, status: JobStatus) -> None:
        self._items[index].status = status
        self._refresh_row(index)

    def _on_progress(self, index: int, percent: float) -> None:
        self._items[index].progress = percent
        self._refresh_row(index)

    def _on_finished(self, index: int, result: JobResult) -> None:
        item = self._items[index]
        item.result = result
        item.status = result.status
        item.progress = 100.0 if result.status is JobStatus.DONE else item.progress
        self._refresh_row(index)
        self._log(f"[{index + 1}] {result.status.value}: {result.detail}")
        if self._table.currentRow() == index:
            self._show_detail()

    def _on_title_ready(self, index: int, stem: str) -> None:
        if index < len(self._items):
            self._items[index].title = stem
            self._refresh_row(index)

    def _on_title_failed(self, index: int, message: str) -> None:
        if index < len(self._items):
            self._items[index].title_error = message
            self._log(f"[{index + 1}] 제목 조회 실패: {message}")

    def _on_ask(self, ask: Ask) -> None:
        index, payload = ask.payload
        if ask.kind == "overwrite":
            names = "\n".join(p.name for p in payload)
            answer = QMessageBox.question(
                self, "같은 이름의 파일이 있습니다",
                f"다음 파일이 이미 있습니다. 덮어쓰면 기존 파일이 교체됩니다.\n\n{names}\n\n덮어쓸까요?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            ask.result = answer == QMessageBox.Yes
        elif ask.kind == "artist_title":
            ask.result = self._prompt_artist_title(payload)
        elif ask.kind == "confirm_write":
            ask.result = self._confirm_write_dialog(payload)
        ask.event.set()

    def _confirm_write_dialog(self, meta: Metadata) -> Optional[Metadata]:
        """이대로 기록할지 묻는다. '아니요'를 고르면 Artist/Title을 고친 뒤 다시 묻는다.

        반환: 기록할 메타데이터, 또는 None(기록 안 함).
        """
        while True:
            box = QMessageBox(self)
            box.setWindowTitle("메타데이터 기록")
            box.setText("이대로 진행할까요?")
            box.setInformativeText(
                f"Artist: {meta.artist or '(기록 안 함)'}\n"
                f"Title: {meta.title or '(기록 안 함)'}\n"
                f"Album: {meta.album}"
            )
            yes_btn = box.addButton("예", QMessageBox.AcceptRole)
            no_btn = box.addButton("아니요", QMessageBox.ActionRole)
            box.addButton("기록 안 함", QMessageBox.RejectRole)
            box.setDefaultButton(yes_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked is yes_btn:
                return meta
            if clicked is no_btn:
                meta = self._edit_artist_title(meta)
                continue
            return None

    def _edit_artist_title(self, meta: Metadata) -> Metadata:
        """현재 값을 채운 입력창으로 Artist와 Title을 고친다. Album은 파일명 값이라 바꾸지 않는다."""
        artist, ok1 = QInputDialog.getText(self, "Artist 수정", "Artist (비우면 기록하지 않음):", text=meta.artist or "")
        if not ok1:
            return meta
        title, ok2 = QInputDialog.getText(self, "Title 수정", "Title (비우면 기록하지 않음):", text=meta.title or "")
        if not ok2:
            return Metadata(album=meta.album, artist=artist.strip() or None, title=meta.title)
        return Metadata(album=meta.album, artist=artist.strip() or None, title=title.strip() or None)

    def _prompt_artist_title(self, album: str) -> tuple[Optional[str], Optional[str]]:
        message = (
            "파일명에서 Artist와 Title을 자동으로 나눌 수 없습니다.\n"
            f"파일명: {album}\n비워 두면 해당 항목은 기록하지 않습니다."
        )
        artist, ok1 = QInputDialog.getText(self, "Artist 입력", message + "\n\nArtist:")
        if not ok1:
            return None, None
        title, ok2 = QInputDialog.getText(self, "Title 입력", "Title:")
        if not ok2:
            return artist.strip() or None, None
        return artist.strip() or None, title.strip() or None

    # ---------- 상세 패널 ----------

    def _show_detail(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        index = rows[0].row()
        item = self._items[index]
        self._d_url.setText(item.url)
        self._d_file.setText(item.title)
        result = item.result
        if result is None:
            for label in (self._d_artist, self._d_title, self._d_album, self._d_result):
                label.setText("-")
            self._d_thumb.clear()
            return
        self._d_artist.setText(result.artist or "-")
        self._d_title.setText(result.title or "-")
        self._d_album.setText(result.album or "-")
        self._d_result.setText(result.status.value + (f" — {result.detail}" if result.detail else ""))
        if result.thumbnail and result.thumbnail.exists():
            pixmap = QPixmap(str(result.thumbnail))
            self._d_thumb.setPixmap(pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self._d_thumb.clear()

    def _reveal_selected(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        result = self._items[rows[0].row()].result
        if result and result.audio and result.audio.exists():
            subprocess.run(["open", "-R", str(result.audio)])

    # ---------- 저장 위치 ----------

    def _choose_out_dir(self) -> None:
        if self._is_running():
            QMessageBox.information(self, "알림", "작업이 끝난 뒤에 저장 위치를 바꿔 주세요.")
            return
        chosen = QFileDialog.getExistingDirectory(self, "저장 위치 선택", str(self._out_dir))
        if not chosen:
            return
        path = Path(chosen)
        if not os.access(path, os.W_OK):
            QMessageBox.warning(self, "저장 위치", "선택한 폴더에 쓸 수 없습니다.")
            return
        self._out_dir = path
        self._settings.set_out_dir(path)
        self._out_label.setText(str(path))
        self._log(f"저장 위치 변경: {path}")

    # ---------- 공통 ----------

    def _refresh_controls(self) -> None:
        running = self._is_running()
        has_tools = self._tools is not None
        self._start_btn.setEnabled(has_tools and not running)
        self._cancel_btn.setEnabled(running)
        self._remove_btn.setEnabled(not running)

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._log_view.appendPlainText(f"{stamp}  {message}")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 시그니처)
        if self._is_running():
            self._cancel_run()
            self._worker.wait(10_000)
        self._settings.set_geometry(self.saveGeometry())
        super().closeEvent(event)
