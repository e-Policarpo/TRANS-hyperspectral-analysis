"""
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy

Where things live, whether the app is running from source or from a bundle.

Running ``python run.py``, the project directory is both where the code lives
and somewhere you can write. Inside a macOS ``.app`` those are two different
places, and getting them mixed up is what breaks a packaged build:

- **Read-only resources** (the QML tree, the icon) are unpacked by PyInstaller
  into a temporary directory named by ``sys._MEIPASS``. ``Path(__file__)`` does
  still resolve there, but only because the bundle happens to mirror the source
  layout; ``resource_path()`` says so explicitly instead of relying on it.
- **Anything written** must go to the user's own directories. The working
  directory of an app launched from Finder is ``/``, so a relative path like
  ``trans_qml.log`` or ``workflows/`` raises ``PermissionError`` — and a log
  handler that fails does it at import time, before there is a window to show
  an error in. Writing inside the bundle is no better: it is read-only in
  practice and breaks the code signature.

Every path the application writes to therefore comes from this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Where the user's own files live. ``~/.trans_qml`` predates this module and
# already holds preferences, the dock layout and the recent-projects list.
USER_DATA_DIRNAME = ".trans_qml"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def bundle_root() -> Path:
    """Directory holding the application's read-only resources.

    The PyInstaller unpack directory when frozen, otherwise the project root
    (the directory containing ``run.py``).
    """
    if is_frozen():
        return Path(sys._MEIPASS)
    # src/utils/app_paths.py -> src/utils -> src -> project root
    return Path(__file__).resolve().parent.parent.parent


def resource_path(*parts: str) -> Path:
    """Absolute path to a bundled, read-only resource.

    ``resource_path('src', 'qml', 'main', 'Main.qml')`` works in both modes,
    because the spec file lays the bundle out with the same relative paths the
    source tree uses.
    """
    return bundle_root().joinpath(*parts)


def user_data_dir() -> Path:
    """The user's TRANS settings directory, created if missing."""
    path = Path.home() / USER_DATA_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    """Where the application log is written, created if missing.

    ``~/Library/Logs/TRANS`` on macOS — the conventional place, and the one
    Console.app shows. Elsewhere it sits with the other settings.
    """
    if sys.platform == 'darwin':
        path = Path.home() / "Library" / "Logs" / "TRANS"
    else:
        path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file() -> Path:
    """Full path of the application log file."""
    return log_dir() / "trans_qml.log"


def default_projects_dir() -> Path:
    """Where the file dialogs start when looking for projects.

    ``~/Documents/TRANS_QML_Projects`` — the same place the "create project"
    flow already defaults to, so opening and creating agree. It is deliberately
    outside the application: a frozen build cannot write next to its own
    executable, and projects the user made should outlive an app they replace.
    """
    path = Path.home() / "Documents" / "TRANS_QML_Projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fallback_workflows_dir() -> Path:
    """Workflow storage for when no project is open.

    Used only as a fallback — with a project open, workflows live in that
    project's own ``workflows/`` folder.
    """
    path = user_data_dir() / "workflows"
    path.mkdir(parents=True, exist_ok=True)
    return path
