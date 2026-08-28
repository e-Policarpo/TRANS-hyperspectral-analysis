"""
TRANS-QML Main Application Entry Point
Hyperspectral Data Analysis Platform

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import sys
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QIcon

# Setup Python path for imports - add parent directory (TRANS_QML) to path
app_dir = Path(__file__).parent.parent  # Go up one level from src/
sys.path.insert(0, str(app_dir))

# Now we can import from src as a package
from src.backend.app_backend import AppBackend
from src.widgets.qml_map_canvas import QMLMapCanvas
from src.widgets.qml_profile_canvas import QMLProfileCanvas
from src.widgets.qml_graph_canvas import QMLGraphCanvas
from src.widgets.qml_figure_canvas import FigureCanvasItem
from src.widgets.qml_designer_canvas import DesignerCanvas
from src.widgets.qml_solver_canvas import SolverCanvas
from src.widgets.qml_potential_canvas import PotentialCanvas
from src.widgets.qml_states_canvas import StatesCanvas
from src.backend.modeling_backend import ModelingBackend
from src.widgets.qml_image_canvas import QMLImageCanvas
from src.widgets.image_provider import TransImageProvider
from src.backend.map_editor_backend import MapEditorBackend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trans_qml.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main application entry point."""
    logger.info("Starting TRANS-QML Application")

    # Set Qt Quick Controls style BEFORE creating QApplication
    import os
    os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'

    # macOS: Set application name in menu bar (requires PyObjC)
    # This must be done BEFORE creating QApplication
    if sys.platform == 'darwin':
        try:
            from Foundation import NSBundle
            bundle = NSBundle.mainBundle()
            if bundle:
                info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
                if info:
                    info['CFBundleName'] = 'T.R.A.N.S.'
                    info['CFBundleDisplayName'] = 'T.R.A.N.S.'
            logger.info("macOS application name set via NSBundle")
        except ImportError:
            logger.warning("PyObjC not available - menu bar will show 'Python'. Install with: pip install pyobjc-framework-Cocoa")
        except Exception as e:
            logger.warning(f"Could not set macOS application name: {e}")

    # High DPI scaling is automatic in Qt6 - no need to set attributes
    # AA_EnableHighDpiScaling and AA_UseHighDpiPixmaps are deprecated and ignored

    app = QApplication(sys.argv)
    app.setApplicationName("T.R.A.N.S.")
    app.setApplicationDisplayName("T.R.A.N.S.")
    app.setOrganizationName("Research Lab")
    app.setOrganizationDomain("trans-qml.org")

    # Set application icon. Lives in <project>/assets/; the bare parent-dir
    # path is the pre-reorganisation location, kept as a fallback so a
    # checkout that predates the move still finds it.
    project_root = Path(__file__).parent.parent
    icon_path = project_root / "assets" / "icon.png"
    if not icon_path.exists():
        icon_path = project_root / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
        logger.info(f"Application icon set: {icon_path}")
    else:
        logger.warning(f"Icon file not found: {icon_path}")

    # Register custom QML types for Map Editor
    # This allows using MapCanvas, ProfileCanvas, and MapEditorBackend directly in QML
    qmlRegisterType(QMLMapCanvas, "TransQML", 1, 0, "MapCanvas")
    qmlRegisterType(QMLProfileCanvas, "TransQML", 1, 0, "ProfileCanvas")
    qmlRegisterType(QMLGraphCanvas, "TransQML", 1, 0, "GraphCanvas")
    qmlRegisterType(QMLImageCanvas, "TransQML", 1, 0, "ImageCanvas")
    qmlRegisterType(MapEditorBackend, "TransQML", 1, 0, "MapEditorBackend")
    # A matplotlib figure hosted in QML, and the designer plots drawn into
    # one. Any tool that wants a real matplotlib plot — colorbars, 3-D
    # surfaces — uses FigureCanvas rather than reimplementing it in QPainter.
    qmlRegisterType(FigureCanvasItem, "TransQML", 1, 0, "FigureCanvas")
    qmlRegisterType(DesignerCanvas, "TransQML", 1, 0, "DesignerCanvas")
    qmlRegisterType(SolverCanvas, "TransQML", 1, 0, "SolverCanvas")
    # The Modeling workstation: an interactive potential and the backend
    # that owns the features in it.
    qmlRegisterType(PotentialCanvas, "TransQML", 1, 0, "PotentialCanvas")
    # What a solved model looks like: the |psi|^2 cloud with its features
    # around it, its three cuts, and the tunnelling picture behind the same
    # canvas's mode.
    qmlRegisterType(StatesCanvas, "TransQML", 1, 0, "StatesCanvas")
    qmlRegisterType(ModelingBackend, "TransQML", 1, 0, "ModelingBackend")

    # Create QML engine
    engine = QQmlApplicationEngine()

    # Create backend
    backend = AppBackend()

    # Apply the saved font family/size as the Qt application default so that
    # the preference takes effect across every widget that doesn't override
    # font.family explicitly (most of the UI). Live in-session changes are
    # handled by the QML theme properties; this covers the startup baseline.
    try:
        from PySide6.QtGui import QFont
        prefs = backend.preferencesManager
        scheme = prefs.getCurrentScheme()
        font_cfg = (scheme or {}).get('font', {}) if isinstance(scheme, dict) else {}
        family = font_cfg.get('family') or ""
        if family and family not in ("system-ui", ".AppleSystemUIFont"):
            app_font = QFont(family)
            size_pt = font_cfg.get('sizeMedium')
            if isinstance(size_pt, (int, float)) and size_pt > 0:
                app_font.setPointSize(int(size_pt))
            app.setFont(app_font)
            logger.info(f"Application default font set to {family}")
    except Exception as e:
        logger.warning(f"Could not apply saved application font: {e}")

    # Expose backend to QML
    engine.rootContext().setContextProperty("backend", backend)

    # Register the image provider so QML's Image element can pull entities
    # by id via ``image://trans/<image_id>``. The provider keeps a
    # reference to the backend's _images dict for lookups.
    engine.addImageProvider("trans", TransImageProvider(backend))

    # Setup cleanup on application exit
    cleanup_done = [False]  # Use list to allow modification in nested function

    def cleanup():
        """Cleanup function called before application exits."""
        if cleanup_done[0]:
            return  # Already cleaned up

        cleanup_done[0] = True
        logger.info("=== Application shutting down ===")

        # Close all open windows FIRST (before stopping worker)
        if hasattr(backend, 'open_windows'):
            logger.info(f"Closing {len(backend.open_windows)} open windows...")
            windows_to_close = list(backend.open_windows)  # Make a copy
            for window in windows_to_close:
                try:
                    if hasattr(window, 'close'):
                        window.close()
                        window.deleteLater()
                except Exception as e:
                    logger.warning(f"Error closing window: {e}")
            logger.info("All windows closed")

        # Stop worker thread gracefully. This is idempotent: WorkerManager also
        # stops the thread on aboutToQuit (connected earlier, so it usually runs
        # first); whichever fires first wins and the second call is a no-op.
        if hasattr(backend, 'worker_manager'):
            try:
                backend.worker_manager.shutdown()
            except Exception as e:
                logger.warning(f"Error stopping worker manager: {e}")

        logger.info("=== Cleanup complete ===")

    # Connect to aboutToQuit signal
    app.aboutToQuit.connect(cleanup)

    # Load main QML file (now relative to src/ directory)
    qml_file = Path(__file__).parent / "qml" / "main" / "Main.qml"
    import time
    t0 = time.time()
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    t1 = time.time()
    logger.info(f"QML engine.load() took {t1 - t0:.2f}s")

    if not engine.rootObjects():
        logger.error("Failed to load QML")
        cleanup()  # Cleanup even on error
        return -1

    logger.info("Application started successfully")

    # Run the application event loop
    exit_code = app.exec()

    # Cleanup is handled by aboutToQuit signal
    # Do NOT call cleanup() here again as it would be redundant
    logger.info(f"Application event loop exited with code {exit_code}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
