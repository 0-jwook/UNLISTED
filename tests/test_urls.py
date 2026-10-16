import pytest

from musiclib.urls import split_pasted, video_id


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=lZHyUw7LWSw", "lZHyUw7LWSw"),
        ("https://www.youtube.com/watch?v=lZHyUw7LWSw&t=10s", "lZHyUw7LWSw"),
        ("https://youtu.be/lZHyUw7LWSw?si=abc", "lZHyUw7LWSw"),
        ("https://m.youtube.com/watch?v=lZHyUw7LWSw", "lZHyUw7LWSw"),
        ("https://www.youtube.com/shorts/lZHyUw7LWSw", "lZHyUw7LWSw"),
        ("https://music.youtube.com/watch?v=lZHyUw7LWSw", "lZHyUw7LWSw"),
    ],
)
def test_video_id_from_common_url_forms(url, expected):
    assert video_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=lZHyUw7LWSw",  # 유튜브가 아님
        "https://www.youtube.com/watch?v=short",  # 11자리가 아님
        "https://www.youtube.com/watch",  # 영상 ID 없음
        "not a url",
        "",
    ],
)
def test_video_id_rejects_non_video_urls(url):
    assert video_id(url) is None


def test_split_pasted_handles_lines_and_spaces():
    text = "https://youtu.be/aaaaaaaaaaa\n\n  https://youtu.be/bbbbbbbbbbb   https://youtu.be/ccccccccccc\n"
    assert split_pasted(text) == [
        "https://youtu.be/aaaaaaaaaaa",
        "https://youtu.be/bbbbbbbbbbb",
        "https://youtu.be/ccccccccccc",
    ]


def test_split_pasted_empty_text():
    assert split_pasted("   \n  ") == []
