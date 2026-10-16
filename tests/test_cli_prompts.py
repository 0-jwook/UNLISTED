import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import music_manager  # noqa: E402


def _inputs(monkeypatch, *answers):
    queue = list(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": queue.pop(0))


@pytest.mark.parametrize(
    "answer, expected",
    [("", "y"), ("y", "y"), ("Y", "y"), ("예", "y"), ("n", "n"), ("아니요", "n"), ("s", "s"), ("건너뛰기", "s")],
)
def test_choose_write_maps_answers(monkeypatch, answer, expected):
    _inputs(monkeypatch, answer)
    assert music_manager.choose_write() == expected


def test_empty_answer_keeps_current_value(monkeypatch):
    _inputs(monkeypatch, "", "")
    assert music_manager.ask_artist_title("기존 가수", "기존 제목") == ("기존 가수", "기존 제목")


def test_typed_answer_replaces_value(monkeypatch):
    _inputs(monkeypatch, "새 가수", "새 제목")
    assert music_manager.ask_artist_title("기존 가수", "기존 제목") == ("새 가수", "새 제목")


def test_dash_clears_value(monkeypatch):
    _inputs(monkeypatch, "-", "-")
    assert music_manager.ask_artist_title("기존 가수", "기존 제목") == (None, None)


def test_empty_without_current_value_means_not_recorded(monkeypatch):
    _inputs(monkeypatch, "", "")
    assert music_manager.ask_artist_title() == (None, None)
