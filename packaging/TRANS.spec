# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for T.R.A.N.S. as a native macOS application.

Build with ``packaging/build_macos.sh`` rather than calling PyInstaller
directly — the script checks it is running on the arm64 virtualenv first.

Three things this file exists to get right:

**The QML tree is data, not code.** PyInstaller follows ``import``
statements; it has no idea that ``Main.qml`` says ``import "../components"``.
All 98 .qml/.js files are therefore shipped verbatim, at the same relative
paths the source tree uses, so ``app_paths.resource_path()`` finds them in
either mode.

**The Basic QtQuick style must come along.** ``main.py`` calls
``QQuickStyle.setStyle("Basic")`` because it is the only style that honours
``palette``; the native macOS style paints the tool panels light and
unreadable. PyInstaller's PySide6 hook cannot see a style chosen by a string
at runtime, so it is requested explicitly.

**Several imports are invisible to static analysis** — scikit-learn's and
scipy's lazy submodules, matplotlib's backend, and the loaders' parsing
engines, some of which are only imported inside functions.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# SPECPATH is where this .spec lives (packaging/); the project is its parent.
PROJECT_ROOT = Path(SPECPATH).parent

APP_NAME = "T.R.A.N.S."
BUNDLE_ID = "org.trans-qml.trans"

# --------------------------------------------------------------------------
# Data files: everything read from disk at runtime, keyed by its path
# relative to the bundle root (see src/utils/app_paths.py).
# --------------------------------------------------------------------------
datas = [
    (str(PROJECT_ROOT / "src" / "qml"), "src/qml"),
    (str(PROJECT_ROOT / "assets" / "icon.png"), "assets"),
]

# matplotlib ships fonts and style sheets it reads at import time.
datas += collect_data_files("matplotlib")
# access2theMatrix and gwyfile are pure Python but carry package data.
datas += collect_data_files("access2thematrix", include_py_files=True)

# --------------------------------------------------------------------------
# Imports the analysis cannot see.
# --------------------------------------------------------------------------
hiddenimports = [
    # Chosen by string at runtime in main.py.
    "PySide6.QtQuickControls2",
    # Imported inside functions across the backend and loaders.
    "access2thematrix",
    "gwyfile",
    "tifffile",
    "h5py",
    "h5py.defs",
    "h5py.utils",
    "h5py._proxy",
    # matplotlib's Qt backend is selected at runtime, never imported by name.
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_agg",
    # Sets the menu-bar name on macOS; guarded by ImportError in main.py, but
    # the bundle should have it so the app is not called "Python".
    "Foundation",
    "objc",
]
# scikit-learn and scipy reach their internals lazily.
hiddenimports += collect_submodules("sklearn.utils")
hiddenimports += collect_submodules("scipy.special")
hiddenimports += collect_submodules("scipy.sparse.linalg")

# --------------------------------------------------------------------------
# Excluded: large packages nothing in the app imports. Each one removed is
# tens to hundreds of MB off the bundle.
# --------------------------------------------------------------------------
excludes = [
    "tkinter",
    "PyQt5", "PyQt6",
    "pytest", "_pytest", "pytest_qt", "pytest_benchmark",
    "IPython", "jupyter", "notebook",
    "sphinx", "docutils",
    # Qt modules this app never loads. QtWebEngine alone is ~200 MB.
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtWebSockets", "PySide6.QtWebChannel",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSql", "PySide6.QtTest",
]

a = Analysis(
    [str(PROJECT_ROOT / "run.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TRANS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # UPX corrupts signed Mach-O binaries on macOS
    console=False,         # no terminal window behind the app
    disable_windowed_traceback=False,
    argv_emulation=False,  # keep off: it swallows argv and confuses Qt
    target_arch=None,      # follow the building interpreter (arm64 here)
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TRANS",
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(PROJECT_ROOT / "assets" / "icon.icns"),
    bundle_identifier=BUNDLE_ID,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleExecutable": "TRANS",
        "CFBundleShortVersionString": "2.0",
        "CFBundleVersion": "2.0",
        "NSHumanReadableCopyright": "GPL — Eduarda Policarpo",
        # Qt renders its own text; without this the app is blurry on Retina.
        "NSHighResolutionCapable": True,
        # The app reads measurement data the user picks from these locations;
        # macOS shows these strings when it asks for permission.
        "NSDocumentsFolderUsageDescription":
            "T.R.A.N.S. opens and saves measurement projects in your Documents folder.",
        "NSDesktopFolderUsageDescription":
            "T.R.A.N.S. opens measurement data you select from your Desktop.",
        "NSDownloadsFolderUsageDescription":
            "T.R.A.N.S. opens measurement data you select from your Downloads folder.",
        "NSRemovableVolumesUsageDescription":
            "T.R.A.N.S. opens measurement data stored on external drives.",
        # Projects are .hrt files; let Finder associate them with the app.
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "T.R.A.N.S. Project",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "CFBundleTypeExtensions": ["hrt"],
                "CFBundleTypeIconFile": "icon.icns",
            }
        ],
    },
)
