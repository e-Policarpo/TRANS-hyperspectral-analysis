"""
Undo/Redo Manager for T.R.A.N.S. application.
Implements the Command pattern for undoable operations.
"""

import logging
from collections import deque
from dataclasses import dataclass
from typing import Callable
from PySide6.QtCore import QObject, Property, Signal, Slot

logger = logging.getLogger(__name__)


@dataclass
class UndoCommand:
    """Represents a single undoable operation."""
    description: str
    undo_fn: Callable
    redo_fn: Callable


class UndoManager(QObject):
    """Manages undo/redo stack with Command pattern."""

    canUndoChanged = Signal(bool)
    canRedoChanged = Signal(bool)
    undoTextChanged = Signal(str)
    redoTextChanged = Signal(str)

    def __init__(self, max_stack=50, parent=None):
        super().__init__(parent)
        self._undo_stack: deque[UndoCommand] = deque(maxlen=max_stack)
        self._redo_stack: list[UndoCommand] = []

    def push(self, command: UndoCommand):
        """Push a new undoable command. Clears redo stack."""
        self._undo_stack.append(command)
        self._redo_stack.clear()
        self._emit_state()
        logger.debug(f"Pushed undo command: {command.description}")

    @Slot()
    def undo(self):
        """Undo the last command."""
        if not self._undo_stack:
            return
        cmd = self._undo_stack.pop()
        try:
            cmd.undo_fn()
            self._redo_stack.append(cmd)
            logger.info(f"Undone: {cmd.description}")
        except Exception as e:
            logger.error(f"Undo failed for '{cmd.description}': {e}")
        self._emit_state()

    @Slot()
    def redo(self):
        """Redo the last undone command."""
        if not self._redo_stack:
            return
        cmd = self._redo_stack.pop()
        try:
            cmd.redo_fn()
            self._undo_stack.append(cmd)
            logger.info(f"Redone: {cmd.description}")
        except Exception as e:
            logger.error(f"Redo failed for '{cmd.description}': {e}")
        self._emit_state()

    def _can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def _can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def _undo_text(self) -> str:
        if self._undo_stack:
            return f"Undo {self._undo_stack[-1].description}"
        return "Undo"

    def _redo_text(self) -> str:
        if self._redo_stack:
            return f"Redo {self._redo_stack[-1].description}"
        return "Redo"

    canUndo = Property(bool, _can_undo, notify=canUndoChanged)
    canRedo = Property(bool, _can_redo, notify=canRedoChanged)
    undoText = Property(str, _undo_text, notify=undoTextChanged)
    redoText = Property(str, _redo_text, notify=redoTextChanged)

    def clear(self):
        """Clear both undo and redo stacks."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._emit_state()

    def _emit_state(self):
        self.canUndoChanged.emit(self._can_undo())
        self.canRedoChanged.emit(self._can_redo())
        self.undoTextChanged.emit(self._undo_text())
        self.redoTextChanged.emit(self._redo_text())
