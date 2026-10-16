import os
import stat

from musiclib.tools import find_tool, subprocess_env


def _make_exe(path):
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_find_tool_uses_path_first(tmp_path, monkeypatch):
    _make_exe(tmp_path / "fake-tool")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert find_tool("fake-tool", extra_dirs=()) == str(tmp_path / "fake-tool")


def test_find_tool_falls_back_when_path_is_minimal(tmp_path, monkeypatch):
    # PATH에 없지만 알려진 경로에 있는 도구도 찾아야 한다 (.app 실행 환경 가정)
    _make_exe(tmp_path / "fake-tool")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert find_tool("fake-tool", extra_dirs=(str(tmp_path),)) == str(tmp_path / "fake-tool")


def test_find_tool_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert find_tool("definitely-not-installed-xyz", extra_dirs=(str(tmp_path),)) is None


def test_find_tool_ignores_non_executable_file(tmp_path, monkeypatch):
    (tmp_path / "not-exec").write_text("data")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert find_tool("not-exec", extra_dirs=(str(tmp_path),)) is None


def test_subprocess_env_prepends_tool_dirs_without_duplicates(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = subprocess_env([str(tmp_path / "yt-dlp"), str(tmp_path / "ffmpeg")])
    parts = env["PATH"].split(os.pathsep)
    assert parts[0] == str(tmp_path)
    assert parts.count(str(tmp_path)) == 1
    assert parts[-2:] == ["/usr/bin", "/bin"]
