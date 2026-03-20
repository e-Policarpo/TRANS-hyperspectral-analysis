#!/usr/bin/env python3
"""
Exercise 01_01: Basic QML Application
Solution: Minimal QML application with Python entry point

This demonstrates the fundamental pattern for creating a PySide6/QML application.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl


def main() -> int:
    """
    Application entry point.

    Returns:
        int: Exit code (0 for success)
    """
    # Create the application instance
    # QApplication is required for any Qt application
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("Hello TRANS")
    app.setOrganizationName("TRANS Course")

    # Create the QML engine
    # This is responsible for loading and running QML files
    engine = QQmlApplicationEngine()

    # Get the path to the QML file
    # Using Path for cross-platform compatibility
    qml_file = Path(__file__).parent / "Main.qml"

    # Load the QML file
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    # Check if the QML loaded successfully
    if not engine.rootObjects():
        print("Error: Failed to load QML file")
        return 1

    # Start the event loop
    # This blocks until the application exits
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
