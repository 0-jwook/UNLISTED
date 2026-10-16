"""Music Manager GUI 진입점. `python3 main.py --selftest`는 도구 탐색만 확인하고 종료한다."""

from __future__ import annotations

import sys

from musiclib.tools import INSTALL_HINTS, check_tools, subprocess_env


def build_tools():
    from musiclib.pipeline import Tools

    statuses = {s.name: s.path for s in check_tools()}
    missing = [name for name, path in statuses.items() if path is None]
    if missing:
        return None, missing
    paths = [statuses["yt-dlp"], statuses["ffmpeg"], statuses["exiftool"]]
    tools = Tools(
        ytdlp=statuses["yt-dlp"],
        ffmpeg=statuses["ffmpeg"],
        exiftool=statuses["exiftool"],
        env=subprocess_env(paths),
    )
    return tools, []


def selftest() -> int:
    statuses = check_tools()
    ok = True
    for status in statuses:
        if status.found:
            print(f"{status.name}: {status.path}")
        else:
            ok = False
            print(f"{status.name}: 없음 ({INSTALL_HINTS[status.name]})")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    from PySide6.QtWidgets import QApplication

    from ui.main_window import MainWindow
    from ui.settings import AppSettings

    app = QApplication(sys.argv)
    app.setApplicationName("Music Manager")
    tools, missing = build_tools()
    window = MainWindow(AppSettings(), tools, missing)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
