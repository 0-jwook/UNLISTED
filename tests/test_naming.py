from pathlib import Path

import pytest

from musiclib.naming import base_name, parse_artist_title, parse_cover_title


def test_base_name_strips_only_m4a_extension():
    assert base_name(Path("/x/아이유(IU) - 밤편지.m4a")) == "아이유(IU) - 밤편지"


def test_base_name_rejects_other_extensions():
    with pytest.raises(ValueError):
        base_name(Path("song.mp3"))


@pytest.mark.parametrize(
    "album, expected",
    [
        ("아이유(IU) - 밤편지", ("아이유(IU)", "밤편지")),
        ("Artist - Song Title", ("Artist", "Song Title")),
    ],
)
def test_dash_separator_splits_once(album, expected):
    assert parse_artist_title(album) == expected


@pytest.mark.parametrize("album", ["A - B - C", "제목만 있음", " - 빈아티스트", "빈제목 - "])
def test_dash_separator_ambiguous_returns_none(album):
    assert parse_artist_title(album) is None


def test_cover_format_with_slash_mark_takes_cover_artist():
    album = "One Last Kiss - 『원곡 정보』 ⧸ 하나코 나나 COVER"
    assert parse_cover_title(album) == ("하나코 나나", "One Last Kiss")


def test_cover_format_with_plain_slash_and_bracket_split():
    album = "희극 (Comedy) [喜劇 / 호시노 겐] / 하나코 나나 COVER"
    assert parse_artist_title(album) == ("하나코 나나", "희극 (Comedy)")


def test_cover_format_keeps_parentheses_in_title():
    album = "수평선 (水平線, back number) ⧸ 하나코 나나 COVER"
    assert parse_artist_title(album) == ("하나코 나나", "수평선 (水平線, back number)")


def test_cover_marker_is_case_insensitive():
    assert parse_cover_title("곡 ⧸ 가수 cover") == ("가수", "곡")


def test_cover_format_wins_over_dash_rule():
    # " - "가 있어도 커버 형식이면 커버 아티스트를 Artist로 사용한다
    album = "One Last Kiss - 원곡 ⧸ 하나코 나나 COVER"
    assert parse_artist_title(album) == ("하나코 나나", "One Last Kiss")
