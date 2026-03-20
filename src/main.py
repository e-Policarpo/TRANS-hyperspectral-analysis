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

    # Set application icon (icon is in parent directory)
    icon_path = Path(__file__).parent.parent / "icon.png"
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
    qmlRegisterType(MapEditorBackend, "TransQML", 1, 0, "MapEditorBackend")

    # Create QML engine
    engine = QQmlApplicationEngine()

    # Create backend
    backend = AppBackend()

    # Expose backend to QML
    engine.rootContext().setContextProperty("backend", backend)

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

        # Stop worker thread gracefully
        if hasattr(backend, 'worker_manager') and hasattr(backend.worker_manager, 'worker'):
            worker = backend.worker_manager.worker
            if worker.isRunning():
                logger.info("Stopping worker thread...")
                worker.stop()

                # Give it time to finish current task
                if not worker.wait(3000):  # Wait up to 3 seconds
                    logger.warning("Worker thread did not stop gracefully, terminating...")
                    worker.terminate()
                    worker.wait(1000)  # Wait for termination

                logger.info("Worker thread stopped")
            else:
                logger.info("Worker thread already stopped")

        logger.info("=== Cleanup complete ===")

    # Connect to aboutToQuit signal
    app.aboutToQuit.connect(cleanup)

    # Load main QML file (now relative to src/ directory)
    qml_file = Path(__file__).parent / "qml" / "main" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

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
