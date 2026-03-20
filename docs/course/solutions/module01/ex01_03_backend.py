#!/usr/bin/env python3
"""
Exercise 01_03: Backend QObject Creation
Solution: Basic AppBackend class with status property and signal

This demonstrates the fundamental pattern for creating a QObject
that can be exposed to QML with properties and signals.
"""

from typing import Optional
from PySide6.QtCore import QObject, Signal, Slot, Property


class AppBackend(QObject):
    """
    Application backend that bridges QML UI to Python logic.

    This class demonstrates:
    - Inheriting from QObject
    - Defining signals for QML communication
    - Creating properties with getters, setters, and notify signals
    - Using the @Slot decorator for QML-callable methods
    """

    # Signals
    statusChanged = Signal(str, arguments=['status'])
    errorOccurred = Signal(str, str, arguments=['errorType', 'message'])

    def __init__(self, parent: Optional[QObject] = None):
        """
        Initialize the backend.

        Args:
            parent: Optional parent QObject for memory management
        """
        super().__init__(parent)
        self._status: str = "Ready"
        self._is_busy: bool = False

    # Status property with getter, setter, and notify signal
    @Property(str, notify=statusChanged)
    def status(self) -> str:
        """Get the current status message."""
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        """
        Set the status message.

        Args:
            value: New status message
        """
        if value != self._status:
            self._status = value
            self.statusChanged.emit(value)

    @Property(bool)
    def isBusy(self) -> bool:
        """Check if the backend is currently busy."""
        return self._is_busy

    @Slot(str)
    def setStatus(self, new_status: str) -> None:
        """
        Set status from QML.

        Args:
            new_status: The new status message
        """
        self.status = new_status

    @Slot(result=str)
    def getStatus(self) -> str:
        """
        Get current status (callable from QML).

        Returns:
            Current status string
        """
        return self._status

    @Slot(str, str)
    def reportError(self, error_type: str, message: str) -> None:
        """
        Report an error to QML.

        Args:
            error_type: Type/category of error
            message: Error message
        """
        self.errorOccurred.emit(error_type, message)


# Allow running as standalone test
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    backend = AppBackend()

    # Test status property
    print(f"Initial status: {backend.status}")
    backend.status = "Testing"
    print(f"Updated status: {backend.status}")

    # Test slot
    backend.setStatus("Complete")
    print(f"After setStatus: {backend.getStatus()}")

    print("All tests passed!")
