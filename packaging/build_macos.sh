#!/bin/bash
#
# Build T.R.A.N.S. as a native macOS application.
#
#   ./packaging/build_macos.sh              # build
#   ./packaging/build_macos.sh --clean      # discard previous build first
#
# The result is dist/T.R.A.N.S..app — double-clickable, no terminal needed.
#
# It must be built from the arm64 virtualenv: PyInstaller freezes whatever
# interpreter runs it, so building from the x86_64 `trans` venv would silently
# produce an Intel app that runs under Rosetta.
set -euo pipefail
cd "$(dirname "$0")/.."

VENV="${TRANS_BUILD_VENV:-$HOME/.virtualenvs/trans-arm64}"
PY="$VENV/bin/python"

# Build OUTSIDE the project directory, and outside iCloud Drive.
#
# This repository lives under ~/Documents, which is synced by iCloud. The
# File Provider stamps com.apple.fileprovider.fpfs#P and com.apple.FinderInfo
# onto directories it manages — including every .framework inside a freshly
# built bundle — and `codesign` refuses to sign anything carrying them
# ("resource fork, Finder information, or similar detritus not allowed").
# `xattr -cr` does not help: the attributes are reapplied by the sync daemon.
# ~/Library/Caches is local, so nothing is added behind our backs.
BUILD_ROOT="${TRANS_BUILD_DIR:-$HOME/Library/Caches/TRANS-build}"
WORKPATH="$BUILD_ROOT/work"
DISTPATH="$BUILD_ROOT/dist"
APP="$DISTPATH/T.R.A.N.S..app"

# ---------------------------------------------------------------- checks
[ -x "$PY" ] || {
    echo "error: no interpreter at $PY" >&2
    echo "Create it with:" >&2
    echo "  /usr/bin/python3 -m venv $VENV" >&2
    echo "  $VENV/bin/pip install --only-binary :all: 'numpy<2' PySide6 pandas \\" >&2
    echo "      scipy scikit-learn matplotlib Pillow h5py tifffile \\" >&2
    echo "      access2theMatrix gwyfile pyobjc-framework-Cocoa pyinstaller" >&2
    exit 1
}

ARCH="$("$PY" -c 'import platform; print(platform.machine())')"
if [ "$ARCH" != "arm64" ]; then
    echo "error: $PY is $ARCH, not arm64." >&2
    echo "This branch builds the native Apple Silicon app; an x86_64" >&2
    echo "interpreter would produce a Rosetta build instead." >&2
    exit 1
fi

"$PY" -c 'import PyInstaller' 2>/dev/null || {
    echo "error: PyInstaller is not installed in $VENV" >&2
    exit 1
}

# ---------------------------------------------------------------- icon
# Cheap, and the .icns is derived from the .png rather than committed twice.
./packaging/make_icns.sh

# ---------------------------------------------------------------- build
if [ "${1:-}" = "--clean" ]; then
    echo "removing $BUILD_ROOT"
    rm -rf "$BUILD_ROOT"
fi
mkdir -p "$WORKPATH" "$DISTPATH"

echo "building with $("$PY" -c 'import sys,platform; print(sys.version.split()[0], platform.machine())')"
echo "build dir: $BUILD_ROOT"
"$PY" -m PyInstaller packaging/TRANS.spec --noconfirm \
    --distpath "$DISTPATH" --workpath "$WORKPATH"

[ -d "$APP" ] || { echo "error: $APP was not produced" >&2; exit 1; }

# ---------------------------------------------------------------- sign
# Ad-hoc signature. Enough for the app to launch on this Mac; it is NOT a
# Developer ID signature, so a copy sent to someone else is still quarantined
# by Gatekeeper (see packaging/README.md).
#
# Strip extended attributes first. Several files under assets/ carry Finder
# metadata (the "@" in `ls -l`), and it gets copied into the bundle; codesign
# refuses to sign anything with one, with the somewhat opaque message
# "resource fork, Finder information, or similar detritus not allowed".
echo "clearing extended attributes"
xattr -cr "$APP"

echo "signing (ad-hoc)"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "signature verifies"

echo
echo "built: $APP  ($(du -sh "$APP" | cut -f1))"
echo "architecture: $(lipo -archs "$APP/Contents/MacOS/TRANS" 2>/dev/null || echo unknown)"

# --install copies it where macOS expects an app to live. ~/Applications
# needs no administrator password and is indexed by Spotlight and Launchpad
# just like /Applications.
if [ "${1:-}" = "--install" ] || [ "${2:-}" = "--install" ]; then
    mkdir -p "$HOME/Applications"
    rm -rf "$HOME/Applications/T.R.A.N.S..app"
    cp -R "$APP" "$HOME/Applications/"
    echo "installed: $HOME/Applications/T.R.A.N.S..app"
fi

echo
printf 'run it:      open "%s"\n' "$APP"
echo "install it:  ./packaging/build_macos.sh --install"
