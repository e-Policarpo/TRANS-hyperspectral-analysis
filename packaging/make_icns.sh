#!/bin/bash
# Build assets/icon.icns from assets/icon.png.
#
# macOS reads the Dock/Finder icon from an .icns; the .png is only what Qt
# uses for the window. iconutil requires an .iconset directory holding every
# size at 1x and 2x, which is what the loop below produces.
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="assets/icon.png"
SET="build/icon.iconset"
OUT="assets/icon.icns"

[ -f "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }

rm -rf "$SET"; mkdir -p "$SET"
for size in 16 32 128 256 512; do
    sips -z $size $size        "$SRC" --out "$SET/icon_${size}x${size}.png"      >/dev/null
    sips -z $((size*2)) $((size*2)) "$SRC" --out "$SET/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$SET" -o "$OUT"
rm -rf "$SET"
echo "wrote $OUT"
