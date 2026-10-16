# music-manager

YouTube URL을 입력하면 오디오를 M4A로 내려받고, 썸네일을 JPEG로 만든 뒤, `Artist` / `Title` / `Album` 메타데이터와 앨범 아트를 M4A에 기록하고 결과를 검증하는 macOS용 도구입니다. 데스크톱 앱(`Music Manager.app`)과 터미널 CLI(`music_manager.py`) 두 가지로 쓸 수 있습니다.

## 앱 사용법 (GUI)

1. 필요한 도구를 설치합니다 (아래 [설치](#설치) 참고).
2. `Music Manager.app`을 실행합니다.
3. URL을 입력하고 **URL 추가**(Enter)를 누릅니다. 여러 개는 **붙여넣기**로 한 번에 넣을 수 있습니다.
4. **다운로드 시작**을 누르면 순서대로 처리합니다. 한 곡이 실패해도 다음 곡을 계속합니다.
5. 목록에서 항목을 고르면 상세 정보(Artist, Title, Album, 썸네일)를 볼 수 있습니다.

- 같은 영상(URL 형식이 달라도 같은 영상 ID)은 한 번만 목록에 들어갑니다.
- 같은 이름의 파일이 있으면 덮어쓸지 묻습니다. 기본값은 **유지**입니다.
- Artist/Title을 파일명에서 나눌 수 없으면 입력창이 뜹니다. 비우면 Album만 기록합니다.
- 기록 전에 값을 보여주고 확인을 받습니다.
- 저장 위치 기본값은 `~/Downloads/yt-music`이며 **폴더 선택**으로 바꿀 수 있습니다. 바꾼 위치는 다음 실행에도 유지됩니다.

### 앱 빌드

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./build/build_app.sh      # dist/Music Manager.app 생성
./build/build_dmg.sh      # dist/Music Manager.dmg 생성 (선택)
```

도구 탐색만 확인하려면 `dist/Music Manager.app/Contents/MacOS/Music Manager --selftest`를 실행합니다.

### 배포 시 참고

- 빌드는 개발용 ad-hoc 서명입니다. 다른 Mac에 배포하려면 Developer ID 서명과 공증이 필요합니다.
- 공증이 없으면 다른 Mac에서 처음 실행할 때 "확인되지 않은 개발자" 경고가 뜹니다. 시스템 설정 → 개인정보 보호 및 보안에서 열기를 허용해야 합니다.
- yt-dlp, FFmpeg, ExifTool은 앱에 포함되지 않습니다. 앱은 Homebrew와 Python 설치 경로에서 찾습니다.

## 설치

```bash
brew install ffmpeg exiftool
python3 -m pip install -U "yt-dlp[default]"
```

Python 3.9 이상, 표준 라이브러리만 사용합니다.

## 실행

```bash
cd "$HOME/Downloads/yt-music"
python3 /path/to/music-manager/music_manager.py
```

`music_manager.py`를 어느 위치에 두든 실행할 수 있으며, 결과물은 항상 `~/Downloads/yt-music`에 저장됩니다(`--out-dir`로 변경 가능).

```text
YouTube URL (빈 입력 시 종료): https://www.youtube.com/watch?v=...
[1/6] 파일명 확인 중…
[2/6] 다운로드 중 (오디오 M4A + 썸네일, 시간이 걸릴 수 있습니다)…
[3/6] 썸네일 JPEG 확인…
[4/6] 메타데이터 판단 및 미리보기…
  [미리보기]
    파일     : 아이유(IU) - 밤편지.m4a
    Artist   : 아이유(IU)
    Title    : 밤편지
    Album    : 아이유(IU) - 밤편지
    CoverArt : 아이유(IU) - 밤편지.jpg
  이 내용으로 기록하시겠습니까? [Y/n]
[5/6] 메타데이터 기록 및 앨범 아트 삽입…
[6/6] 결과 검증…
  => 성공: 아이유(IU) - 밤편지.m4a

YouTube URL (빈 입력 시 종료):

=== 처리 결과 ===
[성공] #1 아이유(IU) - 밤편지.m4a
```

빈 입력을 주면 종료되고, 그동안 처리한 곡의 결과 요약이 출력됩니다.

### 옵션

| 옵션 | 설명 |
|---|---|
| `--out-dir DIR` | 저장 디렉터리 지정 (기본: `~/Downloads/yt-music`) |
| `--dry-run` | 다운로드·기록 없이 예상 파일명과 Artist/Title/Album 판단 결과만 출력 |

## 파일명 규칙과 메타데이터

- 결과 파일: `~/Downloads/yt-music/<제목>.m4a`, `<제목>.jpg` (두 파일의 기본 이름은 항상 같습니다)
- 기록 항목은 `Artist`, `Title`, `Album` 세 가지뿐입니다. `Genre`는 기록하지 않습니다.
- `Album`은 실제 M4A 파일명에서 `.m4a`만 제거한 문자열입니다. 검색이나 추측을 하지 않습니다.
- `Artist`와 `Title`은 다음 순서로 자동 판단합니다.
  1. **커버 형식** `곡 제목 / 커버 아티스트 COVER` (파일명에서는 `/`가 `⧸`로 저장됨)
     - Artist = 마지막 `/` 뒤의 커버 아티스트 (`COVER` 제외)
     - Title = 마지막 `/` 앞부분에서 첫 ` - ` 앞까지, `[..]`·`『..』` 설명 블록 제거
     - 예: `One Last Kiss - 『…』 ⧸ 하나코 나나 COVER` → Artist `하나코 나나`, Title `One Last Kiss`
     - 예: `희극 (Comedy) [喜劇 / 호시노 겐] / 하나코 나나 COVER` → Artist `하나코 나나`, Title `희극 (Comedy)`
  2. **아티스트 - 제목** 형식: ` - `가 정확히 하나 있으면 나눕니다. 예: `아이유(IU) - 밤편지`
- 위 규칙으로 판단할 수 없으면 Artist와 Title을 물어봅니다. 둘 다 빈 입력이면 `Album`만 기록합니다.
- 파일명(제목)은 yt-dlp가 만드는 이름을 그대로 사용하므로, 영상 제목에 `(Official Video)` 같은 문구가 있으면 Title에 포함됩니다.

## 동작 세부사항

- 다운로드는 `bestaudio[ext=m4a]/bestaudio` 포맷을 우선 선택하므로, M4A 원본이 있으면 재인코딩 없이 저장됩니다.
- 재생목록 URL이 들어와도 한 영상만 처리하도록 `--no-playlist`를 사용합니다.
- 같은 이름의 `.m4a` 또는 `.jpg`가 이미 있으면 덮어쓰기 여부를 묻고, 기본값은 **유지(건너뜀)**입니다. 덮어쓰기를 선택하면 기존 파일이 교체되므로 주의하세요.
- 기존 파일은 프로그램이 삭제하지 않습니다.
- 태그 기록 시 ExifTool이 `파일명_original` 백업을 남깁니다. 이 백업은 자동 삭제하지 않으니 필요 없으면 직접 지우세요.
- 한 곡이 실패해도 다음 URL 처리는 계속됩니다. 마지막에 곡별 결과를 요약합니다.
- 미리보기에서 `n`을 선택하면 기록은 하지 않고, 이미 내려받은 파일은 그대로 둡니다.

## 검증 항목

기록 후 ExifTool로 다시 읽어 아래를 확인합니다. 하나라도 어긋나면 성공으로 표시하지 않고 원인을 출력합니다.

1. `Artist`가 판단한 값과 같은지 (판단된 경우에만)
2. `Title`이 판단한 값과 같은지 (판단된 경우에만)
3. `Album`이 파일명에서 `.m4a`만 뗀 문자열과 같은지
4. 앨범 아트가 삽입되었고, 내용이 JPEG 파일과 바이트 단위로 같은지

## 오류 해결

| 증상 | 원인 / 해결 |
|---|---|
| `다음 도구가 설치되어 있지 않습니다` | 표시된 설치 명령을 실행하세요. |
| `yt-dlp 실패 ...` (URL 단계) | URL이 잘못되었거나 영상이 비공개/삭제되었거나 네트워크 문제입니다. yt-dlp를 최신으로 업데이트해 보세요: `python3 -m pip install -U "yt-dlp[default]"` |
| `썸네일을 찾을 수 없습니다` | 해당 영상에 썸네일이 없거나 썸네일 다운로드가 실패했습니다. M4A는 남아 있으니 수동으로 JPEG를 준비한 뒤 태그를 기록하세요. |
| `JPEG 형식이 아닙니다` | 썸네일 변환 결과가 잘못되었습니다. 해당 JPEG를 확인하거나 삭제 후 재시도하세요. |
| `같은 이름의 파일이 이미 있습니다` | 기존 파일을 옮기거나 이름을 바꾼 뒤 다시 실행하거나, 덮어쓰기를 선택하세요. |
| `구분자(' - ')가 하나가 아니어서 자동 분리할 수 없습니다` | 정상 동작입니다. 질문에 Artist와 Title을 직접 입력하세요. 둘 다 비우면 Album만 기록됩니다. |
| `검증 실패 ...` | 메타데이터 기록이 실패했거나 값이 다릅니다. 해당 M4A에 `exiftool -Artist -Title -Album -CoverArt <파일>`로 직접 확인하세요. |
| 한글 파일명 깨짐 | 터미널 인코딩을 UTF-8로 설정하세요. |

## 파일 구성

```text
music-manager/
├── music_manager.py
└── README.md
```
