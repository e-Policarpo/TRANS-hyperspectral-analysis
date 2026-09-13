"""
The cancel path, from the button to the task actually stopping.

Cancel used to be the one thing in this app that could not be trusted. A
cancelled task emits neither ``task_completed`` nor ``task_failed`` — that is
deliberate, since a half-finished derivative is not a result — but it meant
nothing at all ever came back out of the worker, so the panel that asked for
the run sat on "Working..." until it was closed and reopened. The fix is a
third outcome, ``operationCancelled``, and these tests pin it together with
the two properties that make it usable: that it carries the name of the task
that stopped, and that cancelling by name only ever touches the task with
that name.

The rest of the file follows the same run down through the layers: the
WorkerManager bookkeeping that lets a cancelled name be submitted again, the
Line Scan Designer refusing to register a table it only half-filled, and the
designer search noticing the flag between its optimisation passes instead of
after the last one.

Cancelling something that is genuinely mid-flight is the only honest way to
test any of this — a task still in the queue has no running task for
``cancel_current`` to flag, and one that has finished has already emitted its
completion — so the operations here park on a threading Event and the test
drives them from the outside.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.physics.designer import Designer, MATCH_ABSOLUTE, PRIORITY_UNIFORM

# The Line Scan Designer needs a ToolImplementations host and a line scan with
# something on it. Both already exist next door; importing them rather than
# copying keeps the two modules from drifting apart on what a line scan looks
# like. `tool_impl` is a fixture — pytest picks it up from this namespace.
from tests.test_backend.test_line_scan_designer import (  # noqa: F401
    _line, tool_impl,
)

#: Long enough that a loaded machine does not fail the test, short enough that
#: a genuinely stuck worker does not hang the suite.
TIMEOUT = 5.0


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(qapp):
    """A real AppBackend, because the wiring under test IS the wiring.

    Everything here happens between the WorkerManager's signals and the
    slots QML calls, so a mock of either end would be a test of the mock.
    Construction is a millisecond once the imports are warm; the session
    fixture in conftest stops the worker threads afterwards.
    """
    return AppBackend()


class ParkedOperation:
    """A worker task that stops at a known point and waits to be let go.

    ``entered`` says the worker thread is inside the operation — which is
    also the point at which ``_current_task`` is set, so it is the signal the
    tests wait on before cancelling anything.
    """

    def __init__(self, result="done"):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.result = result
        #: What the task's own flag said at the moment it was let go — the
        #: operation's view of the cancel, as a long-running tool would see it.
        self.saw_cancelled = None

    def __call__(self, task, *args, **kwargs):
        self.entered.set()
        self.release.wait(TIMEOUT)
        self.saw_cancelled = bool(task.cancelled)
        return self.result

    def wait_until_running(self):
        assert self.entered.wait(TIMEOUT), "the worker never picked the task up"


@pytest.fixture
def park():
    """Hands out parked operations and lets every one of them go afterwards.

    A test that asserts something about a task while it is still running has
    no reason to release it, but a worker thread left blocked inside an
    operation cannot be stopped — conftest's per-test cleanup then waits out
    its full two-second budget on the way to the next test.
    """
    made = []

    def _make(result="done"):
        operation = ParkedOperation(result)
        made.append(operation)
        return operation

    yield _make
    for operation in made:
        operation.release.set()


def _pump(qapp, seconds=0.4):
    """Deliver whatever the worker thread queued at the main thread.

    Task completion crosses threads, so without an event loop it never
    arrives. Tests that assert something did NOT arrive have to pump too, or
    they pass for the wrong reason.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


def _wait_idle(manager, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if manager.worker._current_task is None:
            return True
        time.sleep(0.01)
    return False


class Recorder:
    """Collects a signal's arguments, newest last."""

    def __init__(self, *signals):
        self.calls = []
        for signal in signals:
            signal.connect(self._record)

    def _record(self, *args):
        self.calls.append(args if len(args) != 1 else args[0])

    def __len__(self):
        return len(self.calls)


# ─── the regression: a cancelled task now says so ────────────────────────────

class TestCancellingReachesTheUI:

    def test_cancelling_an_in_flight_task_announces_its_name(self, backend, qapp, park):
        """The whole point: the panel hears which run stopped."""
        cancelled = Recorder(backend.operationCancelled)
        parked = park()
        backend.worker_manager.submit(name="Derivative: ds1", operation=parked)
        parked.wait_until_running()

        backend.cancelOperation("Derivative: ds1")

        assert cancelled.calls == ["Derivative: ds1"]

    def test_the_running_task_is_told_it_was_cancelled(self, backend, park):
        """The flag the tool bodies poll is set, not just the signal emitted."""
        parked = park()
        backend.worker_manager.submit(name="Derivative: ds1", operation=parked)
        parked.wait_until_running()

        backend.cancelOperation("Derivative: ds1")
        parked.release.set()
        _wait_idle(backend.worker_manager)

        assert parked.saw_cancelled is True

    def test_a_cancelled_task_reports_no_completion_and_no_failure(
            self, backend, qapp, park):
        """Cancelled is a third outcome, not a quiet success or an error.

        This is the half of the bug that the signal fixes: the panel must not
        be told the run finished (it did not) nor that it failed (it did
        not), so operationCancelled has to be the only thing that arrives.
        """
        cancelled = Recorder(backend.operationCancelled)
        finished = Recorder(backend.worker_manager.worker_completed)
        failed = Recorder(backend.worker_manager.worker_failed)
        errors = Recorder(backend.errorOccurred)

        parked = park()
        backend.worker_manager.submit(name="Derivative: ds1", operation=parked)
        parked.wait_until_running()
        backend.cancelOperation("Derivative: ds1")
        parked.release.set()
        _wait_idle(backend.worker_manager)
        _pump(qapp)

        assert cancelled.calls == ["Derivative: ds1"]
        assert finished.calls == []
        assert failed.calls == []
        assert errors.calls == []

    def test_an_uncancelled_task_does_report_completion(self, backend, qapp, park):
        """Control for the test above — otherwise 'nothing arrived' proves
        only that the event pump is broken."""
        finished = Recorder(backend.worker_manager.worker_completed)

        parked = park()
        backend.worker_manager.submit(name="Derivative: ds1", operation=parked)
        parked.wait_until_running()
        parked.release.set()
        _wait_idle(backend.worker_manager)
        _pump(qapp)

        assert finished.calls == ["Derivative: ds1"]


# ─── cancelling by name ──────────────────────────────────────────────────────

class TestCancelByName:

    def test_a_name_that_is_not_running_cancels_nothing(self, backend, qapp, park):
        """A tool window closing must not kill somebody else's import.

        With one worker thread, the task running when a panel closes is very
        often not that panel's, which is exactly why cancelOperation exists.
        """
        cancelled = Recorder(backend.operationCancelled)
        parked = park()
        backend.worker_manager.submit(name="Import: big_file", operation=parked)
        parked.wait_until_running()

        backend.cancelOperation("Multi-Peak Fitting: ds1")

        assert cancelled.calls == []
        assert parked.saw_cancelled is None          # still running, untouched

        parked.release.set()
        _wait_idle(backend.worker_manager)
        assert parked.saw_cancelled is False

    def test_an_empty_name_cancels_nothing(self, backend, park):
        """A panel that never stored a name falls through to nothing at all,
        rather than to 'cancel whatever is running'."""
        cancelled = Recorder(backend.operationCancelled)
        parked = park()
        backend.worker_manager.submit(name="Import: big_file", operation=parked)
        parked.wait_until_running()

        backend.cancelOperation("")

        assert cancelled.calls == []
        parked.release.set()
        _wait_idle(backend.worker_manager)

    def test_cancelling_an_idle_backend_by_name_is_harmless(self, backend):
        cancelled = Recorder(backend.operationCancelled)

        backend.cancelOperation("Multi-Peak Fitting: ds1")

        assert cancelled.calls == []


# ─── the slots 17 QML callers already use ────────────────────────────────────

class TestTheOlderCancelSlotsAreUnchanged:

    def test_cancel_current_operation_still_stops_whatever_runs(self, backend, park):
        cancelled = Recorder(backend.operationCancelled)
        parked = park()
        backend.worker_manager.submit(name="Import: big_file", operation=parked)
        parked.wait_until_running()

        backend.cancelCurrentOperation()
        parked.release.set()
        _wait_idle(backend.worker_manager)

        assert cancelled.calls == ["Import: big_file"]
        assert parked.saw_cancelled is True

    def test_cancel_current_operation_leaves_a_save_alone(self, backend, park):
        """Cancel means "stop the computation". A project write is the one
        thing that cannot be abandoned halfway — the user would be left with
        a truncated file — so the I/O thread is untouched by the plain slot.
        """
        saving = park()
        backend.worker_manager.submit_io(name="Save Project", operation=saving)
        saving.wait_until_running()

        backend.cancelCurrentOperation()
        saving.release.set()
        assert saving.entered.is_set()

        deadline = time.monotonic() + TIMEOUT
        while (backend.worker_manager.io_worker._current_task is not None
               and time.monotonic() < deadline):
            time.sleep(0.01)
        assert saving.saw_cancelled is False

    def test_cancel_all_operations_stops_the_runner_and_clears_the_queue(
            self, backend, park):
        """The close-while-busy flow: quit without draining the queue."""
        cancelled = Recorder(backend.operationCancelled)
        parked = park()
        backend.worker_manager.submit(name="Import: big_file", operation=parked)
        parked.wait_until_running()
        backend.worker_manager.submit(name="Derivative: ds1", operation=lambda t: 1)

        backend.cancelAllOperations()
        parked.release.set()
        _wait_idle(backend.worker_manager)

        assert cancelled.calls == ["Import: big_file"]
        assert backend.worker_manager.worker.task_queue.empty()
        # The queued task's bookkeeping went with it, so its name is free.
        assert "Derivative: ds1" not in backend.worker_manager._task_callbacks

    def test_get_current_operation_names_the_running_task(self, backend, park):
        assert backend.getCurrentOperation() == ""

        parked = park()
        backend.worker_manager.submit(name="Import: big_file", operation=parked)
        parked.wait_until_running()

        assert backend.getCurrentOperation() == "Import: big_file"

        parked.release.set()
        _wait_idle(backend.worker_manager)


# ─── the name has to be free again afterwards ────────────────────────────────

class TestACancelledNameCanBeUsedAgain:

    def test_the_same_task_can_be_submitted_again_after_a_cancel(self, backend, park):
        """Cancel then Run again is the commonest thing a user does next.

        The duplicate-submission guard treats a name in ``_task_callbacks`` as
        "still in flight". A cancelled task emits neither completion nor
        failure, so nothing else would ever clear that entry and every later
        run of the same tool over the same datasets would be silently
        swallowed — the panel would spin with no task behind it.
        """
        first = park()
        name = "Multi-Peak Fitting: ds1"
        assert backend.worker_manager.submit(name=name, operation=first) is True
        first.wait_until_running()

        backend.cancelOperation(name)
        assert name not in backend.worker_manager._task_callbacks

        second = park()
        assert backend.worker_manager.submit(name=name, operation=second) is True

        first.release.set()
        second.wait_until_running()
        second.release.set()
        _wait_idle(backend.worker_manager)
        assert second.saw_cancelled is False

    def test_a_genuine_repeat_click_is_still_dropped(self, backend, park):
        """The guard itself must survive the fix: while the run really is in
        flight, submitting it again is still a no-op."""
        rejected = Recorder(backend.worker_manager.task_rejected)
        parked = park()
        name = "Multi-Peak Fitting: ds1"
        backend.worker_manager.submit(name=name, operation=parked)
        parked.wait_until_running()

        assert backend.worker_manager.submit(name=name, operation=parked) is False
        assert rejected.calls == [name]

        parked.release.set()
        _wait_idle(backend.worker_manager)


# ─── the name QML has to store ───────────────────────────────────────────────

class TestTheRunSlotsHandBackTheirTaskName:
    """The returned string is the contract: a panel cancels by it later, so it
    has to be exactly what was submitted, character for character."""

    @pytest.fixture
    def submitted(self, backend, monkeypatch):
        """Record submissions instead of running them — what is under test is
        the name that crosses to QML, not the tool behind it."""
        names = []

        def fake_submit(name, operation, **kwargs):
            names.append(name)
            return True

        monkeypatch.setattr(backend.worker_manager, "submit", fake_submit)
        return names

    def test_run_tool_on_datasets_returns_the_submitted_name(self, backend, submitted):
        returned = backend.runToolOnDatasets("multi_peak_fit", ["ds1", "ds2"], {})

        assert returned == "Multi-Peak Fitting: ds1, ds2"
        assert submitted == [returned]

    def test_a_long_selection_is_elided_with_a_real_ellipsis(self, backend, submitted):
        """U+2026, not three dots — QML compares the stored string to the one
        the backend is holding, so a lookalike would never match."""
        returned = backend.runToolOnDatasets(
            "multi_peak_fit", ["ds1", "ds2", "ds3", "ds4"], {})

        assert returned == "Multi-Peak Fitting: ds1, ds2, ds3" + "\u2026"
        assert submitted == [returned]

    def test_nothing_is_submitted_and_no_name_returned_on_the_error_paths(
            self, backend, submitted):
        assert backend.runToolOnDatasets("no_such_tool", ["ds1"], {}) == ""
        assert backend.runToolOnDatasets("multi_peak_fit", [], {}) == ""
        assert submitted == []

    def test_the_designer_slots_return_their_names(self, backend, submitted):
        assert (backend.runConfinementDesigner("ds1", {})
                == "Confinement Designer ds1")
        assert (backend.runLineScanDesigner("ds1", {})
                == "Line Scan Designer ds1")
        assert submitted == ["Confinement Designer ds1", "Line Scan Designer ds1"]


# ─── the Line Scan Designer registers nothing it half-filled ─────────────────

class CancellingTask:
    """Cancels after the run has read its flag ``after`` times.

    Counting reads rather than positions because the flag is polled from
    several places inside one position; what matters is only that the cancel
    lands somewhere in the middle of the run rather than before it starts.
    """

    def __init__(self, after=2):
        self.after = after
        self.progress = 0
        self._seen = 0

    @property
    def cancelled(self):
        self._seen += 1
        return self._seen > self.after

    @cancelled.setter
    def cancelled(self, value):
        pass


class AlreadyCancelledTask:
    cancelled = True
    progress = 0


class TestTheLineScanDesignerLeavesNothingBehind:
    """A cancelled line is mostly empty by construction — most positions were
    never visited. Registering that table would put a dataset named after a
    real measurement beside the real ones, and a size map built from it would
    be a map of where the user happened to press Cancel."""

    def _run(self, tool_impl, task, n_points=5):
        tool_impl._datasets['line'] = _line(n_points=n_points)
        before = set(tool_impl._datasets)
        result = tool_impl.design_line_scan(
            task, 'line',
            {'height': 3.0, 'maxsol': 1, 'seed': 1, 'match': 'delta_e'})
        return result, set(tool_impl._datasets) - before

    def test_a_cancelled_run_registers_no_table(self, tool_impl):
        result, new_datasets = self._run(tool_impl, CancellingTask(after=2))

        assert result['ok'] is False
        assert result['error'] == 'Cancelled'
        assert new_datasets == set()
        assert result['dataset'] == ''

    def test_a_cancelled_run_writes_no_map(self, tool_impl, monkeypatch):
        assembled = []
        monkeypatch.setattr(tool_impl, 'assemble_maps',
                            lambda *a, **k: assembled.append(a) or {})

        result, _ = self._run(tool_impl, CancellingTask(after=2))

        assert result['map_paths'] == []
        assert assembled == []

    def test_a_run_cancelled_before_it_starts_is_the_same_answer(self, tool_impl):
        result, new_datasets = self._run(tool_impl, AlreadyCancelledTask())

        assert result['error'] == 'Cancelled'
        assert new_datasets == set()

    def test_an_uncancelled_run_still_registers_its_table(self, tool_impl):
        """Control: the bail-out must be the cancel, not the run being broken."""
        from tests.test_backend.test_line_scan_designer import MockTask

        result, new_datasets = self._run(tool_impl, MockTask())

        assert result['ok'] is True
        assert result['dataset'] in new_datasets


# ─── the search itself notices the flag ──────────────────────────────────────

def _search_params(**over):
    p = {'ndim': "1D", 'coords': "cartesian", 'sym': "",
         'fixed': {'d1': None, 'd2': None, 'd3': None},
         'Lmin': 1.0, 'Lmax': 12.0, 'tol': 2.0, 'maxsol': 3,
         'priority': PRIORITY_UNIFORM, 'match': MATCH_ABSOLUTE,
         'meff': 0.067, 'Et': np.array([0.05, 0.20, 0.45])}
    p.update(over)
    return p


class CancelAfter:
    """A ``should_cancel`` stub that flips true after ``n`` questions."""

    def __init__(self, n):
        self.n = n
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.calls > self.n


class TestTheDesignerSearchStopsWhereItIs:
    """A carrier with three masses used to be one uninterruptible block: the
    Line Scan Designer polled between positions, so Cancel meant "after this
    position" — seconds of nothing happening after the click. The flag now
    goes down into the search, which is where the time actually goes."""

    MEFFS = [0.067, 0.15, 0.5]

    @staticmethod
    def _watched(designer, log):
        """A designer that records which mass each search was entered for."""
        original = designer.find_solutions

        def find_solutions(p, **kwargs):
            log.append(p['meff'])
            return original(p, **kwargs)

        designer.find_solutions = find_solutions
        return designer

    def _search(self, designer, should_cancel):
        return designer.search_carrier(
            _search_params(),
            {'carrier': 'e', 'label': 'electron',
             'Et': np.array([0.05, 0.20, 0.45]), 'meffs': list(self.MEFFS)},
            should_cancel=should_cancel)

    def test_the_mass_loop_asks_before_every_mass(self):
        """Three masses, cancelled at the start: no search is ever entered."""
        entered = []
        designer = self._watched(Designer(seed=20260823), entered)

        sols = self._search(designer, CancelAfter(0))

        assert entered == []
        assert sols == []

    def test_a_cancel_between_masses_skips_the_remaining_ones(self):
        entered = []
        designer = self._watched(Designer(seed=20260823), entered)

        self._search(designer, CancelAfter(10_000))
        complete = list(entered)

        entered.clear()
        self._search(designer, CancelAfter(1))

        assert complete == self.MEFFS            # the full sweep is all three
        assert entered == self.MEFFS[:1]         # the cancelled one is not

    def test_find_solutions_stops_between_its_optimisation_passes(self, monkeypatch):
        """The global passes are the expensive half — ``maxsol * 2`` of them —
        and a Cancel must not wait for the last one."""
        import src.physics.designer as designer_module

        passes = []
        real = designer_module.differential_evolution

        def counted(*args, **kwargs):
            passes.append(1)
            return real(*args, **kwargs)

        monkeypatch.setattr(designer_module, 'differential_evolution', counted)

        designer = Designer(seed=20260823)
        # tol=0 accepts nothing, so the sweep always runs to its full length
        # and the only thing that can shorten it is the cancel.
        never = CancelAfter(10_000)
        designer.find_solutions(_search_params(tol=0.0), should_cancel=never)
        complete = len(passes)

        passes.clear()
        cancelling = CancelAfter(4)
        designer.find_solutions(_search_params(tol=0.0), should_cancel=cancelling)

        assert complete == _search_params()['maxsol'] * 2
        assert len(passes) < complete
        assert cancelling.calls < never.calls

    def test_a_cancelled_search_returns_what_it_found_rather_than_raising(self):
        """The caller decides whether a partial list is worth keeping; the
        search must not make that call by throwing."""
        designer = Designer(seed=20260823)

        sols = designer.find_solutions(_search_params(),
                                       should_cancel=CancelAfter(2))

        assert isinstance(sols, list)
        assert len(sols) <= _search_params()['maxsol']
