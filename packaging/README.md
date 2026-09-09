# Packaging T.R.A.N.S. as a macOS app

Builds `T.R.A.N.S..app` — a native **Apple Silicon (arm64)** application you
double-click, with no terminal and no virtualenv to activate.

```bash
./packaging/build_macos.sh              # build
./packaging/build_macos.sh --clean      # discard the previous build first
./packaging/build_macos.sh --install    # also copy it to ~/Applications
```

Roughly four minutes, and about 600 MB.

Running from source is unaffected — `python run.py` still works exactly as
before.

---

## One-time setup: the arm64 virtualenv

PyInstaller freezes *whatever interpreter runs it*. The `trans` virtualenv is
**x86_64 running under Rosetta**, so building from it would silently produce an
Intel app. The build therefore uses a separate arm64 environment, and refuses
to run if it is handed anything else.

```bash
/usr/bin/python3 -m venv ~/.virtualenvs/trans-arm64        # Apple's arm64 Python
~/.virtualenvs/trans-arm64/bin/pip install --only-binary :all: \
    'numpy<2' PySide6 pandas scipy scikit-learn matplotlib Pillow h5py \
    tifffile access2theMatrix gwyfile pyobjc-framework-Cocoa pyinstaller
```

Override the location with `TRANS_BUILD_VENV=/path/to/venv`.

### Why Python 3.9, and why `numpy<2`

`/usr/bin/python3` (3.9.6) is the only **arm64** Python on this machine —
every Homebrew and MacPorts interpreter here is x86_64. Every dependency has an
arm64 wheel for 3.9, so no compiler is needed.

Staying on 3.9 pins a few packages to older releases than the `trans`
environment uses:

| package | `trans` (x86_64, 3.13) | arm64 build (3.9) |
|---|---|---|
| numpy | 1.26.4 | 1.26.4 — *pinned* |
| scipy | 1.16.3 | 1.13.1 |
| scikit-learn | 1.7.2 | 1.6.1 |
| matplotlib | 3.10.7 | 3.9.4 |
| tifffile | 2025.10.16 | 2024.8.30 |
| PySide6 | 6.10.0 | 6.10.3 |

`numpy<2` is a **required** pin, not a preference: NumPy 2 removed `np.trapz`,
and `src/models/table_data_model.py:1036` calls it directly. Without the pin,
integrating a table column raises `AttributeError` in the packaged app.

Installing an arm64 Python 3.13 (Homebrew at `/opt/homebrew`, or the
python.org universal2 installer) would let the app match the development stack
exactly. See *Known differences* below for what that would buy.

---

## What the build does

| step | file |
|---|---|
| `assets/icon.png` → `assets/icon.icns` | `make_icns.sh` |
| freeze the app | `TRANS.spec` |
| ad-hoc code signature | `build_macos.sh` |

### Things the spec has to be told

- **The QML tree is data.** PyInstaller follows `import` statements and has no
  idea `Main.qml` says `import "../components"`. All 98 `.qml`/`.js` files ship
  verbatim at their source-relative paths.
- **The QtQuick `Basic` style.** `main.py` selects it by string at runtime
  because it is the only style that honours `palette`; the native macOS style
  paints the tool panels unreadably light. A string cannot be seen by static
  analysis, so the plugin is requested explicitly.
- **Lazy imports** — scikit-learn and scipy submodules, matplotlib's Qt
  backend, and the loaders' parsing engines (`access2theMatrix`, `gwyfile`,
  `tifffile`, `h5py`), several of which are imported inside functions.
- **Exclusions.** QtWebEngine, QtMultimedia, Qt3D, tkinter and the test
  packages are dropped; QtWebEngine alone is ~200 MB.

### Where files go at runtime

A bundled app cannot write next to its own executable, and an app launched
from Finder starts with `/` as its working directory. `src/utils/app_paths.py`
is the single place that knows this:

| what | where |
|---|---|
| QML, icon | inside the bundle (`sys._MEIPASS`) |
| log | `~/Library/Logs/TRANS/trans_qml.log` |
| preferences, dock layout, recent projects | `~/.trans_qml/` |
| projects | `~/Documents/TRANS_QML_Projects/` |

Three paths had to change for this. `logging.FileHandler('trans_qml.log')`
wrote to the working directory — as `/`, that raises `PermissionError` at
import time, before there is a window to report it in, so the app would simply
never appear. `_get_projects_directory()` pointed inside the bundle.
`_get_workflows_dir()`'s fallback was a bare relative `Path("workflows")`.

---

## Gotchas found while building this

**The build must happen outside iCloud Drive.** This repository lives under
`~/Documents`, which iCloud syncs. The File Provider stamps
`com.apple.fileprovider.fpfs#P` and `com.apple.FinderInfo` on directories it
manages — including every `.framework` inside a fresh bundle — and `codesign`
rejects them with *"resource fork, Finder information, or similar detritus not
allowed"*. `xattr -cr` does not help; the sync daemon puts them back. The build
therefore runs in `~/Library/Caches/TRANS-build`, which is local. Override with
`TRANS_BUILD_DIR`.

**Do not enable UPX.** It corrupts signed Mach-O binaries.

**Leave `argv_emulation` off.** It swallows `argv` and confuses Qt's own
argument handling.

---

## Sharing it with someone else

The build is signed **ad hoc**. That is enough to launch on this Mac, but a
copy that travels to another machine is quarantined by Gatekeeper, which will
say the app "is damaged and can't be opened" — which is not what is wrong.

Whoever receives it can clear the quarantine flag:

```bash
xattr -dr com.apple.quarantine "/Applications/T.R.A.N.S..app"
```

or right-click → **Open** → **Open** the first time.

For distribution without that step you need an Apple Developer ID
(99 USD/year), and the app must be signed with a hardened runtime and
notarized:

```bash
codesign --force --deep --options runtime --timestamp \
    --sign "Developer ID Application: YOUR NAME (TEAMID)" "$APP"
ditto -c -k --keepParent "$APP" TRANS.zip
xcrun notarytool submit TRANS.zip --apple-id you@example.com \
    --team-id TEAMID --password "app-specific-password" --wait
xcrun stapler staple "$APP"
```

The app is **arm64 only** — it will not run on an Intel Mac. That is the point
of this branch; x86_64 and Windows are handled separately.

---

## Known differences from the development stack

Verified: the app launches, loads all 98 QML files, initialises all six data
loaders, writes its log to the right place, and reports `arm64`.

The test suite on the arm64/3.9 stack is **3782 passed, 7 failed**, against
3785/4 on x86_64/3.13. The four cosmic-ray failures are pre-existing and
unrelated. The three extra ones are stack differences, not packaging faults:

- `test_the_ambiguity_threshold_is_where_the_verdict_flips` — the test sits
  exactly on a threshold; arm64 computes `ΔAIC = 1.9999999999999982` where
  x86_64 gives `2.0`. Floating-point associativity, not a behaviour change.
- `test_fit_multipeak_terminates_quickly_on_noisy_flat_signal` — a wall-clock
  budget; flaky on both stacks.
- `test_detected_bins_land_on_a_linear_energy_axis` — **worth knowing about.**
  The Map Generator found fewer occupied bins under scipy 1.13.1 than under
  1.16.3, so no joined interval map was produced. Peak detection is genuinely
  slightly different on the older scipy. If maps must agree bin-for-bin with
  results produced from source, build against an arm64 Python 3.13 so the
  scientific stack matches.
