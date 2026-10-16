"""외부 도구(yt-dlp, ffmpeg, exiftool) 경로 탐색.

.app은 터미널 PATH를 물려받지 않으므로 PATH에 없는 Homebrew·Python 경로까지 확인한다.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

INSTALL_HINTS = {
    "yt-dlp": 'python3 -m pip install -U "yt-dlp[default]"',
    "ffmpeg": "brew install ffmpeg",
    "exiftool": "brew install exiftool",
}

# PATH에 없어도 찾아볼 위치 (Apple Silicon Homebrew, Intel Homebrew, python.org Python)
FALLBACK_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/Library/Frameworks/Python.framework/Versions/Current/bin",
)


@dataclass(frozen=True)
class ToolStatus:
    name: str
    path: Optional[str]

    @property
    def found(self) -> bool:
        return self.path is not None


def find_tool(name: str, extra_dirs: tuple[str, ...] = FALLBACK_DIRS) -> Optional[str]:
    """도구의 절대 경로를 찾는다. 없으면 None."""
    found = shutil.which(name)
    if found:
        return found
    for directory in extra_dirs:
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def check_tools(names: tuple[str, ...] = tuple(INSTALL_HINTS)) -> list[ToolStatus]:
    return [ToolStatus(name, find_tool(name)) for name in names]


def subprocess_env(tool_paths: list[str]) -> dict[str, str]:
    """하위 프로세스가 도구를 찾을 수 있도록 PATH를 보강한 환경변수를 만든다.

    yt-dlp는 PATH에서 ffmpeg를 찾으므로, 찾은 도구의 디렉터리를 PATH 앞에 넣는다.
    """
    env = dict(os.environ)
    dirs = []
    for path in tool_paths:
        directory = str(Path(path).parent)
        if directory not in dirs:
            dirs.append(directory)
    existing = env.get("PATH", "/usr/bin:/bin")
    env["PATH"] = os.pathsep.join(dirs + [existing])
    return env
