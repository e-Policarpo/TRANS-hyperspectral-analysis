"""
Single persistent worker thread for long-running operations
Prevents UI freezing and avoids Qt threading issues
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import logging
from typing import Any, Callable, List
from queue import Queue
from PySide6.QtCore import (
    QThread, Signal, QObject, QMutex, QMutexLocker, QCoreApplication, Slot,
)

logger = logging.getLogger(__name__)


class Task:
    """Represents a task to be executed"""
    def __init__(self, name: str, operation: Callable, args: tuple, kwargs: dict,
                 on_finished: Callable = None, on_error: Callable = None):
        self.name = name
        self.operation = operation
        self.args = args
        self.kwargs = kwargs
        self.on_finished = on_finished
        self.on_error = on_error
        self.cancelled = False
        self.progress = 0


class PersistentWorker(QThread):
    """
    Single persistent worker thread that processes tasks from a queue.
    Never gets destroyed - just waits for new tasks.
    """

    # Signals
    task_started = Signal(str)  # task name
    task_completed = Signal(str, object)  # task name, result
    task_failed = Signal(str, str, str)  # task name, error title, error message

    def __init__(self, name: str = "TRANS-PersistentWorker"):
        super().__init__()
        # Name the thread so any future "QThread destroyed while running"
        # diagnostics point here instead of an anonymous ''.
        self.setObjectName(name)
        self.task_queue = Queue()
        self._running = True
        self._current_task = None
        self._current_task_name = None
        logger.info("PersistentWorker initialized")

    def run(self):
        """Main loop - waits for tasks and executes them."""
        logger.info("PersistentWorker thread started")

        while self._running:
            try:
                # Wait for next task (blocking)
                task = self.task_queue.get(timeout=0.5)

                if task is None:  # Poison pill to stop thread
                    break

                # Check if task was already cancelled before starting
                if task.cancelled:
                    logger.info(f"Task {task.name} was cancelled before execution")
                    continue

                self._current_task = task
                self._current_task_name = task.name
                self.task_started.emit(task.name)
                logger.info(f"Executing task: {task.name}")

                try:
                    # Execute the operation, passing task as first argument
                    # This allows operations to check task.cancelled during execution
                    result = task.operation(task, *task.args, **task.kwargs)

                    # Check if task was cancelled during execution
                    if task.cancelled:
                        logger.info(f"Task {task.name} was cancelled during execution")
                        continue

                    logger.info(f"Task completed: {task.name}")
                    # Emit signal - callbacks will be invoked in main thread by WorkerManager
                    self.task_completed.emit(task.name, result)

                except Exception as e:
                    logger.error(f"Task failed: {task.name} - {e}", exc_info=True)
                    error_msg = str(e)
                    # Emit signal - callbacks will be invoked in main thread by WorkerManager
                    self.task_failed.emit(task.name, "Operation Error", error_msg)

                finally:
                    self._current_task = None
                    self._current_task_name = None

            except:
                # Timeout - just continue waiting
                continue

        logger.info("PersistentWorker thread stopped")

    def submit_task(self, task: Task):
        """Add a task to the queue."""
        self.task_queue.put(task)
        logger.info(f"Task queued: {task.name}")

    def stop(self):
        """Stop the worker thread gracefully."""
        logger.info("PersistentWorker stop() called")
        self._running = False
        # Put poison pill to wake up the thread if it's waiting
        try:
            self.task_queue.put(None, block=False)
        except:
            pass
        logger.info("PersistentWorker stop signal sent")


class WorkerManager(QObject):
    """
    Manages a single persistent worker thread.
    Provides same interface as before but uses one thread.
    """

    # Signals
    worker_started = Signal(str)  # operation name
    worker_completed = Signal(str)  # operation name
    worker_failed = Signal(str, str)  # operation name, error message
    worker_cancelled = Signal(str)  # operation name
    task_rejected = Signal(str)  # duplicate submission dropped (name pending)

    def __init__(self, max_concurrent=1):  # Only 1 since we have single thread
        super().__init__()
        self.worker = PersistentWorker()
        # Separate thread for saves / disk persistence, so a multi-minute
        # project save never queues interactive tasks (derivatives, imports)
        # behind it.
        self.io_worker = PersistentWorker("TRANS-IOWorker")
        self._shutdown_done = False
        # Workers that outlived shutdown's budget. Holding the reference keeps
        # Qt from destroying a QThread that is still running, which aborts with
        # "QThread: Destroyed while thread is still running".
        self._abandoned: List[PersistentWorker] = []

        # Store callbacks to invoke them in main thread.
        # A name present here also means "this task is queued or running" —
        # submit() uses that to drop duplicate submissions.
        self._task_callbacks = {}  # task_name -> (on_finished, on_error)

        # Connect worker signals
        for w in (self.worker, self.io_worker):
            w.task_started.connect(self._on_task_started)
            w.task_completed.connect(self._on_task_completed)
            w.task_failed.connect(self._on_task_failed)

        # Start the persistent workers
        self.worker.start()
        self.io_worker.start()

        # Stop the thread on application exit. Connecting here (when the
        # backend is constructed, before the QML engine is even loaded) means
        # this fires BEFORE any cleanup wired up later in main.py — so the
        # worker is always stopped and waited before its QThread is destroyed,
        # regardless of what the window-teardown path does. Without this the
        # idle worker outlived shutdown and Qt aborted with
        # "QThread: Destroyed while thread is still running".
        _app = QCoreApplication.instance()
        if _app is not None:
            _app.aboutToQuit.connect(self.shutdown)

        logger.info("WorkerManager initialized with persistent worker")

    def submit(self,
               name: str,
               operation: Callable,
               *args,
               on_finished: Callable = None,
               on_error: Callable = None,
               on_progress: Callable = None,
               **kwargs):
        """
        Submit an operation to run in background.

        Parameters:
        -----------
        name : str
            Unique name for this operation
        operation : Callable
            Function to run
        on_finished : Callable, optional
            Callback when operation completes
        on_error : Callable, optional
            Callback if operation fails
        on_progress : Callable, optional
            Progress callback (not used currently)
        *args, **kwargs
            Arguments for operation
        """
        return self._submit_to(self.worker, name, operation, args, kwargs,
                               on_finished, on_error)

    def submit_io(self,
                  name: str,
                  operation: Callable,
                  *args,
                  on_finished: Callable = None,
                  on_error: Callable = None,
                  **kwargs):
        """Submit a save/persistence operation to the dedicated I/O thread.

        Use this for project saves, autosaves and disk exports so they never
        block interactive tasks on the main worker.
        """
        return self._submit_to(self.io_worker, name, operation, args, kwargs,
                               on_finished, on_error)

    def _submit_to(self, worker, name, operation, args, kwargs,
                   on_finished, on_error) -> bool:
        # Drop duplicate submissions: a task with this name is still queued or
        # running (repeated button clicks, autosave ticking while the previous
        # autosave hasn't finished). Re-submitting would both waste a full
        # recompute and clobber the stored callbacks of the in-flight task.
        if name in self._task_callbacks:
            logger.info(f"Task '{name}' already pending — duplicate submission ignored")
            self.task_rejected.emit(name)
            return False

        # Store callbacks to invoke them in main thread
        self._task_callbacks[name] = (on_finished, on_error)

        # Don't pass callbacks to task - we'll handle them via signals
        task = Task(name, operation, args, kwargs, None, None)
        worker.submit_task(task)
        return True

    def _on_task_started(self, name: str):
        """Handle task start."""
        self.worker_started.emit(name)

    def _on_task_completed(self, name: str, result: Any):
        """Handle task completion - runs in main thread via signal."""
        self.worker_completed.emit(name)

        # Invoke callback in main thread
        if name in self._task_callbacks:
            on_finished, _ = self._task_callbacks[name]
            if on_finished:
                try:
                    on_finished(result)
                except Exception as e:
                    logger.error(f"Error in task completion callback for {name}: {e}", exc_info=True)
            del self._task_callbacks[name]

    def _on_task_failed(self, name: str, title: str, message: str):
        """Handle task failure - runs in main thread via signal."""
        self.worker_failed.emit(name, message)

        # Invoke error callback in main thread
        if name in self._task_callbacks:
            _, on_error = self._task_callbacks[name]
            if on_error:
                try:
                    on_error(title, message)
                except Exception as e:
                    logger.error(f"Error in task failure callback for {name}: {e}", exc_info=True)
            del self._task_callbacks[name]

    def cancel_all(self):
        """Cancel all pending tasks."""
        # Clear the queues, releasing the pending-name entries so the same
        # task names can be submitted again later.
        for w in (self.worker, self.io_worker):
            while not w.task_queue.empty():
                try:
                    task = w.task_queue.get_nowait()
                    if task is not None:
                        self._task_callbacks.pop(task.name, None)
                except:
                    break
        logger.info("All pending tasks cancelled")

    def cancel_current(self):
        """Cancel the currently running operation."""
        if self.worker._current_task:
            self.worker._current_task.cancelled = True
            task_name = self.worker._current_task.name
            # A cancelled task emits neither completed nor failed, so drop its
            # callback entry here — otherwise the name would stay "pending"
            # and dedup would silently swallow every future submission of it.
            self._task_callbacks.pop(task_name, None)
            logger.info(f"Cancelling current task: {task_name}")
            self.worker_cancelled.emit(task_name)
            return True
        return False

    def get_current_operation(self) -> str:
        """Get the name of the currently running operation."""
        return self.worker._current_task_name if self.worker._current_task_name else ""

    def is_busy(self) -> bool:
        """Check if worker is processing a task."""
        return self.worker._current_task_name is not None or not self.worker.task_queue.empty()

    #: An idle worker stops the moment it sees the poison pill; these budgets
    #: only matter when a task is still running. A project save legitimately
    #: takes tens of seconds at GB scale, so the I/O worker -- the one that
    #: might be holding a half-written .hrt -- gets far longer than the
    #: compute worker, whose work is always reproducible.
    COMPUTE_DRAIN_MS = 15_000
    IO_DRAIN_MS = 300_000
    _DRAIN_LOG_INTERVAL_MS = 3_000

    def _drain(self, worker: PersistentWorker, budget_ms: int) -> bool:
        """Wait for a worker to finish, logging what it is still doing."""
        waited = 0
        while waited < budget_ms:
            slice_ms = min(self._DRAIN_LOG_INTERVAL_MS, budget_ms - waited)
            if worker.wait(slice_ms):
                return True
            waited += slice_ms
            busy = worker._current_task_name
            logger.info("%s still busy after %.0fs%s", worker.objectName(),
                        waited / 1000.0, f" running '{busy}'" if busy else "")
        return False

    @Slot()
    def shutdown(self):
        """Stop the worker threads and wait for them to finish.

        Idempotent, and safe to call from both the aboutToQuit signal and an
        explicit cleanup.

        A task that is mid-flight is never killed. ``QThread.terminate()`` on
        a thread executing Python is undefined behaviour -- it was crashing
        the app when the user quit right after a save -- and on the I/O worker
        it would also leave a truncated project file behind. Waiting costs a
        slow quit; terminating costs the user's data.
        """
        if self._shutdown_done:
            return
        self._shutdown_done = True
        try:
            for w, budget in ((self.worker, self.COMPUTE_DRAIN_MS),
                              (self.io_worker, self.IO_DRAIN_MS)):
                if not w.isRunning():
                    continue
                logger.info(f"WorkerManager: stopping {w.objectName()}...")
                w.stop()
                if self._drain(w, budget):
                    continue

                stuck = w._current_task_name
                if stuck:
                    # Past the budget and still working. Leave it be: a
                    # half-written file is worse than a slow exit, and the
                    # process teardown will reclaim the thread.
                    logger.error(
                        "%s still running '%s' after %.0fs; leaving it to finish "
                        "rather than terminating mid-operation",
                        w.objectName(), stuck, budget / 1000.0)
                    self._abandoned.append(w)
                else:
                    # Idle but unresponsive: nothing in flight to corrupt.
                    logger.warning("%s did not stop in %.0fs; terminating",
                                   w.objectName(), budget / 1000.0)
                    w.terminate()
                    w.wait(1000)
            logger.info("WorkerManager shutdown complete")
        except Exception as e:
            logger.error(f"Error during WorkerManager shutdown: {e}")

    def has_pending_io(self) -> bool:
        """True while a project write is queued or running.

        The UI can use this to hold a quit until the save lands, instead of
        letting the user close into a several-second stall.
        """
        return (self.io_worker._current_task_name is not None
                or not self.io_worker.task_queue.empty())
