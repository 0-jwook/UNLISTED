#!/bin/bash
# Music Manager.app을 배포용 .dmg로 묶는다. 먼저 build/build_app.sh를 실행해야 한다.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP="dist/Music Manager.app"
DMG="dist/Music Manager.dmg"
STAGE="build/work/dmg-stage"

if [ ! -d "$APP" ]; then
  echo "앱이 없습니다. 먼저 build/build_app.sh를 실행하세요." >&2
  exit 1
fi

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

hdiutil create \
  -volname "Music Manager" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "$DMG" >/dev/null

rm -rf "$STAGE"
echo "DMG 생성 완료: $ROOT/$DMG"
