#!/bin/bash
# Music Manager.app 빌드. 실행 위치와 관계없이 프로젝트 루트 기준으로 동작한다.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "먼저 가상환경을 만드세요: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

.venv/bin/python -m PyInstaller \
  --windowed \
  --noconfirm \
  --clean \
  --name "Music Manager" \
  --osx-bundle-identifier "com.jwook.musicmanager" \
  --workpath "build/work" \
  --distpath "dist" \
  --specpath "build" \
  main.py

APP="dist/Music Manager.app"
# 개발용 ad-hoc 서명. 다른 Mac 배포 시에는 Developer ID 서명과 공증이 필요하다.
codesign --force --deep --sign - "$APP"
echo "빌드 완료: $ROOT/$APP"
