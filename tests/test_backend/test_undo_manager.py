"""
Tests for UndoManager
"""

import pytest
from src.backend.undo_manager import UndoManager, UndoCommand


class TestUndoCommand:
    """Tests for UndoCommand dataclass."""

    def test_creation(self):
        cmd = UndoCommand(
            description="Test",
            undo_fn=lambda: None,
            redo_fn=lambda: None
        )
        assert cmd.description == "Test"
        assert callable(cmd.undo_fn)
        assert callable(cmd.redo_fn)


class TestUndoManager:
    """Tests for UndoManager."""

    @pytest.fixture
    def manager(self):
        return UndoManager(max_stack=10)

    @pytest.fixture
    def tracked_state(self):
        """A mutable state dict for tracking undo/redo side effects."""
        return {"value": 0}

    def _make_command(self, desc, state, old_val, new_val):
        return UndoCommand(
            description=desc,
            undo_fn=lambda ov=old_val: state.__setitem__("value", ov),
            redo_fn=lambda nv=new_val: state.__setitem__("value", nv),
        )

    def test_initial_state(self, manager):
        assert not manager.canUndo
        assert not manager.canRedo
        assert manager.undoText == "Undo"
        assert manager.redoText == "Redo"

    def test_push_command(self, manager, tracked_state):
        cmd = self._make_command("Set to 1", tracked_state, 0, 1)
        manager.push(cmd)
        assert manager.canUndo
        assert not manager.canRedo
        assert manager.undoText == "Undo Set to 1"

    def test_undo(self, manager, tracked_state):
        tracked_state["value"] = 1
        cmd = self._make_command("Set to 1", tracked_state, 0, 1)
        manager.push(cmd)

        manager.undo()
        assert tracked_state["value"] == 0
        assert not manager.canUndo
        assert manager.canRedo
        assert manager.redoText == "Redo Set to 1"

    def test_redo(self, manager, tracked_state):
        tracked_state["value"] = 1
        cmd = self._make_command("Set to 1", tracked_state, 0, 1)
        manager.push(cmd)

        manager.undo()
        assert tracked_state["value"] == 0

        manager.redo()
        assert tracked_state["value"] == 1
        assert manager.canUndo
        assert not manager.canRedo

    def test_push_clears_redo_stack(self, manager, tracked_state):
        cmd1 = self._make_command("Cmd 1", tracked_state, 0, 1)
        cmd2 = self._make_command("Cmd 2", tracked_state, 1, 2)
        manager.push(cmd1)
        manager.push(cmd2)

        manager.undo()
        assert manager.canRedo

        # Pushing a new command should clear the redo stack
        cmd3 = self._make_command("Cmd 3", tracked_state, 1, 3)
        manager.push(cmd3)
        assert not manager.canRedo

    def test_multiple_undo_redo(self, manager, tracked_state):
        for i in range(5):
            cmd = self._make_command(f"Set to {i+1}", tracked_state, i, i+1)
            tracked_state["value"] = i + 1
            manager.push(cmd)

        assert tracked_state["value"] == 5

        # Undo all
        for i in range(5):
            manager.undo()
        assert tracked_state["value"] == 0
        assert not manager.canUndo

        # Redo all
        for i in range(5):
            manager.redo()
        assert tracked_state["value"] == 5
        assert not manager.canRedo

    def test_max_stack_size(self, manager, tracked_state):
        # Push more than max_stack (10) commands
        for i in range(15):
            cmd = self._make_command(f"Cmd {i}", tracked_state, i, i+1)
            manager.push(cmd)

        # Should only have 10 undo entries
        count = 0
        while manager.canUndo:
            manager.undo()
            count += 1
        assert count == 10

    def test_undo_on_empty_stack(self, manager):
        # Should not raise
        manager.undo()
        assert not manager.canUndo

    def test_redo_on_empty_stack(self, manager):
        # Should not raise
        manager.redo()
        assert not manager.canRedo

    def test_clear(self, manager, tracked_state):
        cmd = self._make_command("Test", tracked_state, 0, 1)
        manager.push(cmd)
        manager.undo()

        assert manager.canRedo
        manager.clear()
        assert not manager.canUndo
        assert not manager.canRedo

    def test_signals_emitted(self, manager, tracked_state):
        """Test that state change signals are emitted."""
        signals_received = {"can_undo": [], "can_redo": [], "undo_text": [], "redo_text": []}

        manager.canUndoChanged.connect(lambda v: signals_received["can_undo"].append(v))
        manager.canRedoChanged.connect(lambda v: signals_received["can_redo"].append(v))
        manager.undoTextChanged.connect(lambda v: signals_received["undo_text"].append(v))
        manager.redoTextChanged.connect(lambda v: signals_received["redo_text"].append(v))

        cmd = self._make_command("Test", tracked_state, 0, 1)
        manager.push(cmd)

        assert True in signals_received["can_undo"]
        assert "Undo Test" in signals_received["undo_text"]

    def test_undo_with_failing_function(self, manager):
        """Test that undo handles exceptions gracefully."""
        def failing_undo():
            raise ValueError("undo failed")

        cmd = UndoCommand(
            description="Failing",
            undo_fn=failing_undo,
            redo_fn=lambda: None
        )
        manager.push(cmd)
        # Should not raise, just log the error
        manager.undo()
