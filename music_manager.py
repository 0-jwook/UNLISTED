#!/usr/bin/env python3
"""YouTube 오디오 다운로드 → M4A 저장 → 썸네일 JPEG → Artist/Title/Album 기록 → 앨범 아트 삽입 → 검증."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_OUT_DIR = Path.home() / "Downloads" / "yt-music"
REQUIRED_TOOLS = {
    "yt-dlp": 'python3 -m pip install -U "yt-dlp[default]"',
    "ffmpeg": "brew install ffmpeg",
    "exiftool": "brew install exiftool",
}
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
JPEG_MAGIC = b"\xff\xd8"
# 자동 분리 구분자 (정확히 한 번 나올 때만 자동 분리)
SEPARATOR = " - "
# "곡 제목 / 커버 아티스트 COVER" 형식의 구분자 (파일명에서는 "/"가 "⧸"로 바뀜)
SLASH_SEPARATORS = (" ⧸ ", " / ")
COVER_PATTERN = re.compile(r"(.+?)\s+COVER", re.IGNORECASE)
# 제목 뒤에 붙은 [..] 또는 『..』 설명 블록 제거용
DECORATION_PATTERN = re.compile(r"\s*[\[『][^\]』]*[\]』]")


class ToolError(Exception):
    """외부 명령 실행 또는 파일 처리 실패."""


@dataclass
class Metadata:
    album: str
    artist: Optional[str]
    title: Optional[str]


def check_tools() -> None:
    missing = [name for name in REQUIRED_TOOLS if shutil.which(name) is None]
    if missing:
        print("다음 도구가 설치되어 있지 않습니다:")
        for name in missing:
            print(f"  - {name}: {REQUIRED_TOOLS[name]}")
        sys.exit(1)


def run(cmd: list[str]) -> str:
    """외부 명령을 인자 리스트로 실행(shell 미사용)하고 stdout을 반환한다."""
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        reason = lines[-1] if lines else "출력 없음"
        raise ToolError(f"{cmd[0]} 실패(종료 코드 {result.returncode}): {reason}")
    return result.stdout


def base_name(audio: Path) -> str:
    """'.m4a' 확장자만 제거한 전체 파일명 (Album 값)."""
    if not audio.name.endswith(".m4a"):
        raise ToolError(f"M4A 파일이 아닙니다: {audio.name}")
    return audio.name[: -len(".m4a")]


def parse_cover_title(album: str) -> Optional[tuple[str, str]]:
    """'곡 제목 / 커버 아티스트 COVER' 형태면 (커버 아티스트, 곡 제목)을 반환한다.

    예: 'One Last Kiss - 『원곡 정보』 ⧸ 하나코 나나 COVER' → ('하나코 나나', 'One Last Kiss')
    """
    for sep in SLASH_SEPARATORS:
        idx = album.rfind(sep)
        if idx == -1:
            continue
        left, right = album[:idx].strip(), album[idx + len(sep):].strip()
        cover = COVER_PATTERN.fullmatch(right)
        if not cover:
            continue
        # 곡 제목은 첫 " - " 앞부분에서, 설명 블록을 뺀 나머지다
        title = DECORATION_PATTERN.sub("", left.split(SEPARATOR, 1)[0]).strip()
        artist = cover.group(1).strip()
        if artist and title:
            return artist, title
    return None


def parse_artist_title(album: str) -> Optional[tuple[str, str]]:
    """Artist, Title을 파일명에서 판단한다. 판단할 수 없으면 None.

    1) 커버 형식 '곡 제목 / 커버 아티스트 COVER'
    2) ' - '가 정확히 하나인 '아티스트 - 제목'
    """
    cover = parse_cover_title(album)
    if cover:
        return cover
    parts = album.split(SEPARATOR)
    if len(parts) != 2:
        return None
    artist, title = parts[0].strip(), parts[1].strip()
    if not artist or not title:
        return None
    return artist, title


def expected_stem(url: str) -> str:
    """yt-dlp가 실제 다운로드 시 쓸 파일명(확장자 제외)을 다운로드 없이 구한다."""
    out = run(["yt-dlp", "--no-playlist", "--print", "filename", "-o", "%(title)s.%(ext)s", url])
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        raise ToolError("yt-dlp가 파일명을 반환하지 않았습니다(잘못된 URL 가능성)")
    return lines[-1].rsplit(".", 1)[0]


def existing_outputs(out_dir: Path, stem: str) -> list[Path]:
    return [p for p in (out_dir / f"{stem}.m4a", out_dir / f"{stem}.jpg") if p.exists()]


def download(url: str, out_dir: Path, overwrite: bool) -> Path:
    """오디오(M4A)와 썸네일(JPEG)을 내려받고 최종 M4A 경로를 반환한다."""
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "-x", "--audio-format", "m4a",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-P", str(out_dir),
        "-o", "%(title)s.%(ext)s",
        "--no-simulate",
        "--print", "after_move:filepath",
        "--force-overwrites" if overwrite else "--no-overwrites",
        url,
    ]
    lines = [line for line in run(cmd).splitlines() if line.strip()]
    if not lines:
        raise ToolError("다운로드 결과 경로를 확인할 수 없습니다")
    audio = Path(lines[-1])
    if not audio.exists():
        raise ToolError(f"M4A 파일이 생성되지 않았습니다: {audio.name}")
    return audio


def is_jpeg(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(2) == JPEG_MAGIC


def ensure_jpeg(audio: Path) -> Path:
    """오디오와 같은 기본 파일명의 JPEG를 확보한다. 없으면 원본 썸네일을 변환한다."""
    base = base_name(audio)
    jpg = audio.parent / f"{base}.jpg"
    if not jpg.exists():
        thumb = next(
            (
                p
                for p in audio.parent.iterdir()
                if p.name.startswith(base + ".") and p.suffix.lower() in {".webp", ".png"}
            ),
            None,
        )
        if thumb is None:
            raise ToolError("썸네일을 찾을 수 없습니다(썸네일 다운로드 실패 가능성)")
        # -n: 기존 파일을 덮어쓰지 않는다
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-i", str(thumb), "-q:v", "2", str(jpg)])
    if not is_jpeg(jpg):
        raise ToolError(f"JPEG 형식이 아닙니다: {jpg.name}")
    return jpg


def ask_artist_title() -> tuple[Optional[str], Optional[str]]:
    """자동 분리가 안 될 때 사용자에게 직접 입력받는다. 둘 다 비우면 Album만 기록한다."""
    artist = input("  Artist (빈 입력 시 생략): ").strip() or None
    title = input("  Title (빈 입력 시 생략): ").strip() or None
    return artist, title


def show_preview(meta: Metadata, audio: Path, jpg: Path) -> None:
    print("  [미리보기]")
    print(f"    파일     : {audio.name}")
    print(f"    Artist   : {meta.artist or '(기록 안 함)'}")
    print(f"    Title    : {meta.title or '(기록 안 함)'}")
    print(f"    Album    : {meta.album}")
    print(f"    CoverArt : {jpg.name}")


def confirm(question: str, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{question} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "예", "네"}


def write_tags(audio: Path, jpg: Path, meta: Metadata) -> None:
    # 인자 리스트로 전달하므로 한글·공백·괄호가 있어도 안전하다
    cmd = ["exiftool", "-charset", "filename=UTF8"]
    if meta.artist:
        cmd.append(f"-Artist={meta.artist}")
    if meta.title:
        cmd.append(f"-Title={meta.title}")
    cmd.append(f"-Album={meta.album}")
    cmd.append(f"-CoverArt<={jpg}")
    cmd.append(str(audio))
    run(cmd)


def verify(audio: Path, jpg: Path, meta: Metadata) -> list[str]:
    """기록 결과를 다시 읽어 확인한다. 문제 목록을 반환하며, 빈 리스트면 통과."""
    data = json.loads(run(["exiftool", "-j", "-charset", "filename=UTF8", "-Artist", "-Title", "-Album", str(audio)]))[0]
    problems = []
    if meta.artist and data.get("Artist") != meta.artist:
        problems.append(f"Artist 불일치(기대 {meta.artist!r}, 실제 {data.get('Artist')!r})")
    if meta.title and data.get("Title") != meta.title:
        problems.append(f"Title 불일치(기대 {meta.title!r}, 실제 {data.get('Title')!r})")
    if data.get("Album") != meta.album:
        problems.append(f"Album 불일치(기대 {meta.album!r}, 실제 {data.get('Album')!r})")

    cover = subprocess.run(["exiftool", "-b", "-CoverArt", str(audio)], capture_output=True)
    if cover.returncode != 0 or not cover.stdout:
        problems.append("앨범 아트(CoverArt)가 삽입되지 않았습니다")
    elif cover.stdout != jpg.read_bytes():
        problems.append("앨범 아트 내용이 JPEG 파일과 다릅니다")
    return problems


def process_url(url: str, out_dir: Path, dry_run: bool) -> tuple[str, str]:
    """URL 한 개를 처리하고 (상태, 설명)을 반환한다. 상태: 성공 / 건너뜀 / 실패 / 미리보기."""
    print("[1/6] 파일명 확인 중…")
    stem = expected_stem(url)
    print(f"  예상 파일명: {stem}")

    overwrite = False
    conflicts = existing_outputs(out_dir, stem)
    if conflicts:
        print(f"  같은 이름의 파일이 이미 있습니다: {', '.join(p.name for p in conflicts)}")
        if not dry_run:
            if not confirm("  덮어쓰시겠습니까? (기존 파일이 교체됩니다)", default=False):
                return "건너뜀", "기존 파일 유지"
            overwrite = True

    if dry_run:
        parsed = parse_artist_title(stem)
        if parsed:
            print(f"  Artist: {parsed[0]} / Title: {parsed[1]} / Album: {stem}")
        else:
            print(f"  구분자(' - ')가 하나가 아니므로 실제 처리 시 Artist/Title을 직접 입력받습니다. Album: {stem}")
        return "미리보기", stem

    print("[2/6] 다운로드 중 (오디오 M4A + 썸네일, 시간이 걸릴 수 있습니다)…")
    audio = download(url, out_dir, overwrite)
    print(f"  저장됨: {audio.name}")

    print("[3/6] 썸네일 JPEG 확인…")
    jpg = ensure_jpeg(audio)
    print(f"  JPEG: {jpg.name}")

    print("[4/6] 메타데이터 판단 및 미리보기…")
    album = base_name(audio)
    parsed = parse_artist_title(album)
    if parsed:
        artist, title = parsed
        print(f"  파일명에서 자동 분리: Artist={artist} / Title={title}")
    else:
        print(f"  구분자(' - ')가 하나가 아니어서 자동 분리할 수 없습니다: {album}")
        artist, title = ask_artist_title()
    meta = Metadata(album=album, artist=artist, title=title)
    show_preview(meta, audio, jpg)
    if not confirm("  이 내용으로 기록하시겠습니까?", default=True):
        return "건너뜀", f"사용자 취소(다운로드 파일 유지: {audio.name})"

    print("[5/6] 메타데이터 기록 및 앨범 아트 삽입…")
    write_tags(audio, jpg, meta)

    print("[6/6] 결과 검증…")
    problems = verify(audio, jpg, meta)
    if problems:
        return "실패", "검증 실패: " + "; ".join(problems)
    return "성공", audio.name


def parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YouTube 음원 다운로드 및 M4A 메타데이터 기록")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="저장 디렉터리 (기본: ~/Downloads/yt-music)")
    parser.add_argument("--dry-run", action="store_true", help="다운로드/기록 없이 파일명 분석 결과만 출력")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    check_tools()
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, str, str]] = []
    index = 0
    while True:
        try:
            url = input("\nYouTube URL (빈 입력 시 종료): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not url:
            break

        index += 1
        if not URL_PATTERN.match(url):
            print("  잘못된 URL입니다. http:// 또는 https://로 시작해야 합니다.")
            results.append((f"#{index}", "실패", "잘못된 URL"))
            continue

        try:
            status, detail = process_url(url, out_dir, args.dry_run)
        except ToolError as e:
            status, detail = "실패", str(e)
        except Exception as e:  # 예상치 못한 오류도 다음 곡 처리를 막지 않는다
            status, detail = "실패", f"예상치 못한 오류: {e}"
        print(f"  => {status}: {detail}")
        results.append((f"#{index}", status, detail))

    if results:
        print("\n=== 처리 결과 ===")
        for label, status, detail in results:
            print(f"[{status}] {label} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
