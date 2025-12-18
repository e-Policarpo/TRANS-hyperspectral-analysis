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
from typing import Callable, Any
from queue import Queue
from PySide6.QtCore import QThread, Signal, QObject, QMutex, QMutexLocker

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

    def __init__(self):
        super().__init__()
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

    def __init__(self, max_concurrent=1):  # Only 1 since we have single thread
        super().__init__()
        self.worker = PersistentWorker()

        # Store callbacks to invoke them in main thread
        self._task_callbacks = {}  # task_name -> (on_finished, on_error)

        # Connect worker signals
        self.worker.task_started.connect(self._on_task_started)
        self.worker.task_completed.connect(self._on_task_completed)
        self.worker.task_failed.connect(self._on_task_failed)

        # Start the persistent worker
        self.worker.start()
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
        # Store callbacks to invoke them in main thread
        self._task_callbacks[name] = (on_finished, on_error)

        # Don't pass callbacks to task - we'll handle them via signals
        task = Task(name, operation, args, kwargs, None, None)
        self.worker.submit_task(task)

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
        # Clear the queue
        while not self.worker.task_queue.empty():
            try:
                self.worker.task_queue.get_nowait()
            except:
                break
        logger.info("All pending tasks cancelled")

    def cancel_current(self):
        """Cancel the currently running operation."""
        if self.worker._current_task:
            self.worker._current_task.cancelled = True
            task_name = self.worker._current_task.name
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

    def shutdown(self):
        """Shutdown the worker thread."""
        self.worker.stop()
        self.worker.wait()  # Wait for thread to finish
        logger.info("WorkerManager shutdown complete")
