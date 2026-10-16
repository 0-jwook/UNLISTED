"""앱 설정 저장. 저장 경로와 창 geometry만 보관하며, URL이나 개인정보는 저장하지 않는다."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

DEFAULT_OUT_DIR = Path.home() / "Downloads" / "yt-music"
ORG = "0-jwook"
APP = "Music Manager"


class AppSettings:
    def __init__(self, store: QSettings | None = None):
        self._store = store or QSettings(ORG, APP)

    def out_dir(self) -> Path:
        value = self._store.value("paths/out_dir", "")
        return Path(value) if value else DEFAULT_OUT_DIR

    def set_out_dir(self, path: Path) -> None:
        self._store.setValue("paths/out_dir", str(path))

    def cleanup_enabled(self) -> bool:
        # 기본값은 켜짐: 완성 M4A만 남긴다
        value = self._store.value("options/cleanup", True)
        return value in (True, "true", "True", 1, "1")

    def set_cleanup_enabled(self, enabled: bool) -> None:
        self._store.setValue("options/cleanup", bool(enabled))

    def geometry(self) -> QByteArray | None:
        value = self._store.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    def set_geometry(self, data: QByteArray) -> None:
        self._store.setValue("window/geometry", data)
