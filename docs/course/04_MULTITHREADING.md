# Module 4: Multithreading for Responsive UIs

## Learning Objectives

By the end of this module, you will:
- Understand why multithreading is essential for scientific applications
- Implement the Worker pattern with QThread
- Create thread-safe communication using signals
- Build a task queue system with cancellation support
- Report progress from background operations
- Avoid common threading pitfalls

---

## 4.1 Why Multithreading Matters

### The Problem: Frozen UI

```python
# BAD: This freezes the UI for 10 seconds!
def process_large_dataset(self):
    self.status = "Processing..."

    # Heavy computation blocks the main thread
    for i in range(10_000_000):
        result = expensive_calculation(i)

    self.status = "Done"  # User sees nothing until here
```

When a long operation runs on the **main (GUI) thread**:
- Buttons don't respond to clicks
- Windows can't be moved or resized
- Progress bars don't update
- OS may show "Not Responding"

### The Solution: Background Threads

```
┌─────────────────────────────────────────────────────────────┐
│                      Main Thread (GUI)                       │
│  - Handle user input                                         │
│  - Update UI elements                                        │
│  - Process signals from worker                               │
│  - NEVER do heavy computation                                │
└────────────────────────────┬────────────────────────────────┘
                             │ signals
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Worker Thread                            │
│  - Heavy computation                                         │
│  - File I/O                                                  │
│  - Network requests                                          │
│  - Emit progress signals                                     │
└─────────────────────────────────────────────────────────────┘
```

### Qt's Threading Rules

**Golden Rule**: Never access GUI elements from a background thread!

```python
# WRONG - crashes or undefined behavior
def worker_function(self):
    # This runs in worker thread
    self.label.setText("Done")  # NO! GUI access from worker!

# CORRECT - emit signal, let main thread update GUI
def worker_function(self):
    # Signal is thread-safe
    self.taskCompleted.emit("Done")

# Main thread handles the signal
def on_task_completed(self, message):
    self.label.setText(message)  # OK - main thread
```

---

## 4.2 QThread Basics

### Method 1: Subclass QThread (Simple)

```python
from PySide6.QtCore import QThread, Signal

class WorkerThread(QThread):
    """Simple worker thread that does one task."""

    # Signals for communication
    progressChanged = Signal(int, int)  # current, total
    resultReady = Signal(object)
    errorOccurred = Signal(str)

    def __init__(self, data):
        super().__init__()
        self.data = data
        self._should_stop = False

    def run(self):
        """This runs in the new thread."""
        try:
            total = len(self.data)

            for i, item in enumerate(self.data):
                # Check for cancellation
                if self._should_stop:
                    return

                # Do work
                result = self.process_item(item)

                # Report progress
                self.progressChanged.emit(i + 1, total)

            # Emit final result
            self.resultReady.emit(result)

        except Exception as e:
            self.errorOccurred.emit(str(e))

    def process_item(self, item):
        # Heavy computation here
        import time
        time.sleep(0.1)  # Simulate work
        return item * 2

    def stop(self):
        """Request thread to stop."""
        self._should_stop = True
```

Usage:

```python
class MainWindow(QObject):
    def startProcessing(self):
        self.worker = WorkerThread(data=list(range(100)))

        # Connect signals
        self.worker.progressChanged.connect(self.updateProgress)
        self.worker.resultReady.connect(self.handleResult)
        self.worker.errorOccurred.connect(self.handleError)
        self.worker.finished.connect(self.onWorkerFinished)

        # Start the thread
        self.worker.start()

    def updateProgress(self, current, total):
        self.progressBar.setValue(current * 100 // total)

    def handleResult(self, result):
        print(f"Result: {result}")

    def handleError(self, error):
        print(f"Error: {error}")

    def onWorkerFinished(self):
        print("Worker thread finished")

    def cancelProcessing(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()  # Wait for thread to finish
```

### Method 2: Worker Object (Flexible)

Move a worker object to a thread:

```python
from PySide6.QtCore import QObject, QThread, Signal, Slot

class Worker(QObject):
    """Worker object that runs in a separate thread."""

    progressChanged = Signal(int, int)
    resultReady = Signal(object)
    errorOccurred = Signal(str)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self._should_stop = False

    @Slot(list)
    def processData(self, data: list):
        """This slot will be called in the worker thread."""
        try:
            total = len(data)
            results = []

            for i, item in enumerate(data):
                if self._should_stop:
                    break

                result = self.heavyComputation(item)
                results.append(result)

                self.progressChanged.emit(i + 1, total)

            self.resultReady.emit(results)

        except Exception as e:
            self.errorOccurred.emit(str(e))

        finally:
            self.finished.emit()

    def heavyComputation(self, item):
        import time
        time.sleep(0.05)
        return item ** 2

    @Slot()
    def stop(self):
        self._should_stop = True


class Controller(QObject):
    """Controller that manages the worker thread."""

    # Signal to start work
    startWork = Signal(list)

    def __init__(self):
        super().__init__()

        # Create thread and worker
        self.thread = QThread()
        self.worker = Worker()

        # Move worker to thread
        self.worker.moveToThread(self.thread)

        # Connect signals
        self.startWork.connect(self.worker.processData)
        self.worker.finished.connect(self.thread.quit)
        self.worker.resultReady.connect(self.handleResults)
        self.worker.progressChanged.connect(self.updateProgress)

        # Start thread
        self.thread.start()

    def process(self, data: list):
        """Start processing (called from main thread)."""
        self.startWork.emit(data)

    def handleResults(self, results):
        print(f"Got {len(results)} results")

    def updateProgress(self, current, total):
        print(f"Progress: {current}/{total}")

    def cleanup(self):
        """Clean up when done."""
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()
```

---

## 4.3 The TRANS-QML Worker Pattern

TRANS-QML uses a **persistent worker** pattern for efficiency:

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      AppBackend                              │
│                                                             │
│  worker_manager.submit(                                      │
│      name="Smooth Curves",                                   │
│      operation=self.smooth_curves,                          │
│      on_finished=self._on_smooth_complete                   │
│  )                                                          │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    WorkerManager                             │
│                                                             │
│  - Manages task queue                                       │
│  - Stores callbacks                                         │
│  - Emits worker_started, worker_completed, worker_failed    │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   PersistentWorker                           │
│                      (QThread)                               │
│                                                             │
│  while running:                                              │
│      task = queue.get()                                     │
│      result = task.operation(task, *args, **kwargs)         │
│      emit task_completed(name, result)                      │
└─────────────────────────────────────────────────────────────┘
```

### The Task Class

From `src/backend/worker.py`:

```python
class Task:
    """Represents a task to be executed in the worker thread."""

    def __init__(self,
                 name: str,
                 operation: Callable,
                 args: tuple,
                 kwargs: dict,
                 on_finished: Callable = None,
                 on_error: Callable = None):
        """
        Initialize a task.

        Parameters:
        -----------
        name : str
            Display name for the task (shown in status)
        operation : Callable
            The function to execute. Receives 'task' as first argument
            for cancellation checking.
        args : tuple
            Positional arguments for operation
        kwargs : dict
            Keyword arguments for operation
        on_finished : Callable
            Callback when task completes successfully
        on_error : Callable
            Callback when task fails
        """
        self.name = name
        self.operation = operation
        self.args = args
        self.kwargs = kwargs
        self.on_finished = on_finished
        self.on_error = on_error

        # State
        self.cancelled = False
        self.progress = 0
```

### The PersistentWorker Class

```python
class PersistentWorker(QThread):
    """
    Single persistent worker thread that processes tasks from a queue.

    Benefits over creating new threads:
    - No thread creation overhead
    - Consistent thread affinity
    - Controlled concurrency
    """

    # Signals
    task_started = Signal(str)           # task name
    task_completed = Signal(str, object) # name, result
    task_failed = Signal(str, str, str)  # name, error_title, error_message
    task_progress = Signal(str, int)     # name, progress percentage

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task_queue = Queue()
        self._running = True
        self._current_task: Optional[Task] = None

    def run(self):
        """Main loop - waits for tasks and executes them."""
        logger.info("PersistentWorker started")

        while self._running:
            try:
                # Wait for task with timeout (allows checking _running flag)
                task = self.task_queue.get(timeout=0.5)

                if task is None:  # Poison pill to stop
                    break

                if task.cancelled:
                    continue

                self._current_task = task
                self.task_started.emit(task.name)

                try:
                    # Execute the operation
                    # Pass task as first arg so operation can check cancellation
                    result = task.operation(task, *task.args, **task.kwargs)

                    if not task.cancelled:
                        self.task_completed.emit(task.name, result)

                except Exception as e:
                    logger.exception(f"Task {task.name} failed")
                    self.task_failed.emit(
                        task.name,
                        "Operation Failed",
                        str(e)
                    )

                finally:
                    self._current_task = None

            except:
                # Queue timeout - continue loop
                continue

        logger.info("PersistentWorker stopped")

    def submit_task(self, task: Task):
        """Submit a task for execution."""
        self.task_queue.put(task)

    def cancel_current(self):
        """Cancel the currently running task."""
        if self._current_task:
            self._current_task.cancelled = True

    def stop(self):
        """Stop the worker thread."""
        self._running = False
        self.task_queue.put(None)  # Poison pill
```

### The WorkerManager Class

```python
class WorkerManager(QObject):
    """High-level manager for background tasks."""

    # Public signals
    worker_started = Signal(str)    # operation name
    worker_completed = Signal(str)  # operation name
    worker_failed = Signal(str, str)  # operation name, error message
    worker_cancelled = Signal(str)  # operation name

    def __init__(self, max_concurrent: int = 1, parent=None):
        super().__init__(parent)

        # Create persistent worker
        self.worker = PersistentWorker()
        self.worker.task_started.connect(self._on_task_started)
        self.worker.task_completed.connect(self._on_task_completed)
        self.worker.task_failed.connect(self._on_task_failed)

        # Store callbacks for execution in main thread
        self._task_callbacks: Dict[str, Tuple[Callable, Callable]] = {}

        # Start worker thread
        self.worker.start()

    def submit(self,
               name: str,
               operation: Callable,
               *args,
               on_finished: Callable = None,
               on_error: Callable = None,
               **kwargs):
        """
        Submit an operation to run in the background.

        Parameters:
        -----------
        name : str
            Display name for the operation
        operation : Callable
            Function to execute. Signature: operation(task, *args, **kwargs)
        *args, **kwargs : Any
            Arguments passed to operation
        on_finished : Callable
            Called with result when operation completes
        on_error : Callable
            Called with error message if operation fails
        """
        # Store callbacks
        self._task_callbacks[name] = (on_finished, on_error)

        # Create and submit task
        task = Task(name, operation, args, kwargs)
        self.worker.submit_task(task)

    def _on_task_started(self, name: str):
        """Handle task start (runs in main thread via signal)."""
        self.worker_started.emit(name)

    def _on_task_completed(self, name: str, result: Any):
        """Handle task completion (runs in main thread via signal)."""
        self.worker_completed.emit(name)

        # Execute callback in main thread
        if name in self._task_callbacks:
            on_finished, _ = self._task_callbacks[name]
            if on_finished:
                try:
                    on_finished(result)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

            del self._task_callbacks[name]

    def _on_task_failed(self, name: str, title: str, message: str):
        """Handle task failure (runs in main thread via signal)."""
        self.worker_failed.emit(name, message)

        if name in self._task_callbacks:
            _, on_error = self._task_callbacks[name]
            if on_error:
                on_error(title, message)

            del self._task_callbacks[name]

    def cancel_current(self):
        """Cancel the current operation."""
        self.worker.cancel_current()

    def shutdown(self):
        """Shutdown the worker manager."""
        self.worker.stop()
        self.worker.wait()
```

---

## 4.4 Using the Worker Manager

### Basic Usage

```python
class AppBackend(QObject):
    def __init__(self):
        super().__init__()

        # Create worker manager
        self.worker_manager = WorkerManager()

        # Connect to worker signals
        self.worker_manager.worker_started.connect(self._on_worker_started)
        self.worker_manager.worker_completed.connect(self._on_worker_completed)
        self.worker_manager.worker_failed.connect(self._on_worker_failed)

    def _on_worker_started(self, name: str):
        self.status = f"Processing: {name}"
        self.isBusyChanged.emit(True)

    def _on_worker_completed(self, name: str):
        self.status = "Ready"
        self.isBusyChanged.emit(False)

    def _on_worker_failed(self, name: str, error: str):
        self.status = "Error"
        self.isBusyChanged.emit(False)
        self.errorOccurred.emit("Processing Error", error)
```

### Implementing a Processing Operation

```python
@Slot(str, int, int, str)
def smoothCurves(self, dataset_name: str, window_size: int,
                 poly_order: int, smoothing_type: str):
    """Smooth curves in a dataset (QML-callable slot)."""

    self.worker_manager.submit(
        name=f"Smoothing {dataset_name}",
        operation=self._smooth_curves_impl,
        dataset_name=dataset_name,
        window_size=window_size,
        poly_order=poly_order,
        smoothing_type=smoothing_type,
        on_finished=self._on_smooth_complete,
        on_error=self._on_tool_error
    )

def _smooth_curves_impl(self, task: Task, dataset_name: str,
                        window_size: int, poly_order: int,
                        smoothing_type: str):
    """
    Implementation that runs in worker thread.

    Note: First parameter is always 'task' for cancellation checking.
    """
    from scipy.signal import savgol_filter

    dataset = self._datasets[dataset_name]
    spectra = dataset.spectra.values
    total = spectra.shape[1]
    smoothed = np.zeros_like(spectra)

    for i in range(total):
        # Check for cancellation periodically
        if task.cancelled:
            logger.info("Smoothing cancelled")
            return None

        # Apply smoothing
        smoothed[:, i] = savgol_filter(
            spectra[:, i],
            window_size,
            poly_order
        )

        # Update progress
        task.progress = int((i + 1) / total * 100)

    return {
        'dataset_name': dataset_name,
        'smoothed_data': smoothed
    }

def _on_smooth_complete(self, result: dict):
    """Called when smoothing completes (main thread)."""
    if result is None:  # Cancelled
        return

    # Update dataset with smoothed data
    name = result['dataset_name']
    self._datasets[name].spectra = pd.DataFrame(result['smoothed_data'])

    # Notify QML
    self.status = "Smoothing complete"
    self.dataLoaded.emit(name)

def _on_tool_error(self, title: str, message: str):
    """Called when operation fails."""
    self.errorOccurred.emit(title, message)
```

---

## 4.5 Progress Reporting

### From Worker to UI

```python
# In worker operation
def process_large_file(self, task: Task, filepath: str):
    """Process file with progress reporting."""

    file_size = os.path.getsize(filepath)
    processed = 0

    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            if task.cancelled:
                return None

            # Process chunk...
            processed += len(chunk)

            # Update progress (0-100)
            task.progress = int(processed / file_size * 100)

    return result
```

### Connecting Progress to UI

```python
# In WorkerManager
class WorkerManager(QObject):
    worker_progress = Signal(str, int)  # name, percentage

    def __init__(self):
        super().__init__()
        # ...

        # Poll progress periodically
        self._progress_timer = QTimer()
        self._progress_timer.timeout.connect(self._emit_progress)
        self._progress_timer.start(100)  # Every 100ms

    def _emit_progress(self):
        """Emit progress for current task."""
        task = self.worker._current_task
        if task:
            self.worker_progress.emit(task.name, task.progress)
```

```qml
// In QML
Connections {
    target: backend.workerManager

    function onWorker_progress(name, percentage) {
        progressBar.value = percentage / 100
        progressLabel.text = name + ": " + percentage + "%"
    }
}

ProgressBar {
    id: progressBar
    width: parent.width
    visible: backend.isBusy
}
```

---

## 4.6 Cancellation

### User-Initiated Cancellation

```python
class AppBackend(QObject):
    @Slot()
    def cancelCurrentOperation(self):
        """Cancel the currently running operation."""
        self.worker_manager.cancel_current()
        self.status = "Cancelled"
```

```qml
Button {
    text: "Cancel"
    visible: backend.isBusy
    onClicked: backend.cancelCurrentOperation()
}
```

### Checking for Cancellation in Operations

```python
def long_operation(self, task: Task, data: list):
    """Operation that respects cancellation."""

    results = []

    for i, item in enumerate(data):
        # Check frequently in long loops
        if task.cancelled:
            logger.info("Operation cancelled by user")
            return None  # Or partial results

        # Do work
        result = expensive_computation(item)
        results.append(result)

        # Update progress
        task.progress = int((i + 1) / len(data) * 100)

    return results
```

### Cleanup on Cancellation

```python
def operation_with_cleanup(self, task: Task, filepath: str):
    """Operation that cleans up on cancellation."""

    temp_file = None

    try:
        temp_file = create_temp_file()

        for chunk in process_chunks(filepath):
            if task.cancelled:
                raise CancelledException()

            write_to_temp(temp_file, chunk)

        return finalize(temp_file)

    except CancelledException:
        logger.info("Cancelled, cleaning up")
        if temp_file:
            os.remove(temp_file)
        return None

    except Exception as e:
        if temp_file:
            os.remove(temp_file)
        raise
```

---

## 4.7 Thread Safety Gotchas

### Gotcha 1: Shared Data Access

```python
# DANGEROUS - data can be modified while being read
class BadExample(QObject):
    def __init__(self):
        self._data = []

    def worker_operation(self, task):
        for item in self._data:  # Main thread might modify this!
            process(item)

# SAFE - copy data before worker access
class GoodExample(QObject):
    def start_processing(self):
        # Copy data for worker
        data_copy = self._data.copy()

        self.worker_manager.submit(
            "Process",
            self._process_impl,
            data_copy  # Worker gets its own copy
        )
```

### Gotcha 2: GUI Updates from Worker

```python
# CRASH - GUI access from worker thread
def worker_operation(self, task):
    self.label.setText("Processing")  # WRONG!

# CORRECT - emit signal
resultReady = Signal(str)

def worker_operation(self, task):
    result = do_work()
    # Signal will be delivered to main thread
    return result  # Callback runs in main thread

def on_complete(self, result):
    self.label.setText(f"Result: {result}")  # OK - main thread
```

### Gotcha 3: Object Ownership

```python
# WRONG - object created in worker, used in main
def worker_operation(self, task):
    widget = QWidget()  # Created in worker thread
    return widget  # Returned to main thread - BAD!

# CORRECT - return data, create objects in main thread
def worker_operation(self, task):
    data = compute_data()
    return data

def on_complete(self, data):
    widget = QWidget()  # Created in main thread
    widget.setData(data)
```

### Gotcha 4: Numpy Array Sharing

```python
# Be careful with numpy arrays
def worker_operation(self, task, array):
    # If array is a view, main thread might modify underlying data
    # Solution: ensure you have a copy
    local_array = array.copy()

    for i in range(len(local_array)):
        if task.cancelled:
            return None
        local_array[i] = process(local_array[i])

    return local_array
```

---

## 4.8 Testing Threaded Code

### Unit Testing Workers

```python
import pytest
from unittest.mock import MagicMock
from PySide6.QtCore import QCoreApplication
import sys

@pytest.fixture
def app():
    """Create QApplication for tests."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app

def test_worker_completes(app, qtbot):
    """Test that worker completes successfully."""
    manager = WorkerManager()

    results = []

    def on_complete(result):
        results.append(result)

    manager.submit(
        "test",
        lambda task: 42,
        on_finished=on_complete
    )

    # Wait for completion
    with qtbot.waitSignal(manager.worker_completed, timeout=5000):
        pass

    assert results == [42]

def test_worker_cancellation(app, qtbot):
    """Test that cancellation works."""
    manager = WorkerManager()

    def slow_operation(task):
        import time
        for i in range(100):
            if task.cancelled:
                return None
            time.sleep(0.1)
        return "completed"

    results = []
    manager.submit("test", slow_operation, on_finished=lambda r: results.append(r))

    # Cancel after 200ms
    QTimer.singleShot(200, manager.cancel_current)

    with qtbot.waitSignal(manager.worker_completed, timeout=5000):
        pass

    assert results == [None]  # Cancelled
```

---

## 4.9 Complete Example: File Processor

```python
"""
Complete example of a threaded file processor.
"""

from PySide6.QtCore import QObject, Signal, Slot, Property
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class FileProcessor(QObject):
    """Process files in background with progress and cancellation."""

    # Signals
    statusChanged = Signal(str)
    progressChanged = Signal(int, int, str)  # current, total, filename
    processingStarted = Signal()
    processingCompleted = Signal(int)  # files processed
    processingCancelled = Signal()
    errorOccurred = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._status = "Ready"
        self._is_processing = False

        # Create worker manager
        self.worker_manager = WorkerManager()
        self.worker_manager.worker_started.connect(self._on_started)
        self.worker_manager.worker_completed.connect(self._on_completed)
        self.worker_manager.worker_failed.connect(self._on_failed)

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str):
        if self._status != value:
            self._status = value
            self.statusChanged.emit(value)

    @Slot(list)
    def processFiles(self, filepaths: list):
        """Start processing files."""
        if self._is_processing:
            return

        self._is_processing = True
        self.processingStarted.emit()

        self.worker_manager.submit(
            name="Processing Files",
            operation=self._process_files_impl,
            filepaths=filepaths,
            on_finished=self._on_process_complete,
            on_error=self._on_process_error
        )

    def _process_files_impl(self, task, filepaths: list):
        """Worker implementation - runs in background thread."""
        import time

        processed = 0
        results = []

        for i, filepath in enumerate(filepaths):
            # Check cancellation
            if task.cancelled:
                logger.info("Processing cancelled")
                return {'cancelled': True, 'processed': processed}

            # Report progress
            task.progress = int((i / len(filepaths)) * 100)
            self.progressChanged.emit(i + 1, len(filepaths), Path(filepath).name)

            try:
                # Simulate file processing
                result = self._process_single_file(filepath)
                results.append(result)
                processed += 1

            except Exception as e:
                logger.error(f"Error processing {filepath}: {e}")
                # Continue with other files

        return {
            'cancelled': False,
            'processed': processed,
            'results': results
        }

    def _process_single_file(self, filepath: str):
        """Process a single file (runs in worker thread)."""
        import time
        time.sleep(0.5)  # Simulate work

        # Read and process file
        with open(filepath, 'r') as f:
            content = f.read()

        return {
            'path': filepath,
            'size': len(content),
            'lines': content.count('\n')
        }

    def _on_process_complete(self, result: dict):
        """Handle completion (main thread)."""
        self._is_processing = False

        if result.get('cancelled'):
            self.processingCancelled.emit()
            self.status = "Cancelled"
        else:
            count = result.get('processed', 0)
            self.processingCompleted.emit(count)
            self.status = f"Processed {count} files"

    def _on_process_error(self, title: str, message: str):
        """Handle error (main thread)."""
        self._is_processing = False
        self.status = "Error"
        self.errorOccurred.emit(title, message)

    @Slot()
    def cancel(self):
        """Cancel current processing."""
        if self._is_processing:
            self.worker_manager.cancel_current()
            self.status = "Cancelling..."

    def _on_started(self, name: str):
        self.status = f"Started: {name}"

    def _on_completed(self, name: str):
        pass  # Handled by callback

    def _on_failed(self, name: str, error: str):
        self.status = "Failed"
```

---

## 4.10 Exercises

### Exercise 4.1: Download Manager

Create a download manager that:
1. Downloads multiple files concurrently (use multiple workers)
2. Reports progress for each file
3. Supports pausing and resuming
4. Handles network errors gracefully

### Exercise 4.2: Image Processor

Build an image processing pipeline:
1. Load images from a folder
2. Apply filters (resize, rotate, color adjustment)
3. Save processed images
4. Show thumbnails as they complete

### Exercise 4.3: Data Analysis Pipeline

Create a scientific data pipeline:
1. Load CSV/Excel files
2. Apply transformations (normalize, filter, aggregate)
3. Compute statistics
4. Generate plots
5. All steps cancellable with progress

---

## 4.11 Key Takeaways

1. **Never block the main thread** - use workers for heavy computation
2. **Signals are thread-safe** - use them for worker-to-main communication
3. **Never access GUI from workers** - emit signals instead
4. **Copy data before sending to workers** - avoid shared state issues
5. **Check cancellation frequently** in long loops
6. **Handle errors gracefully** - don't let exceptions crash workers
7. **Test threaded code carefully** - race conditions are subtle

---

## Next Module

In [Module 5: Custom QML Components with Python](./05_CUSTOM_COMPONENTS.md), we'll learn:
- QQuickPaintedItem for custom rendering
- Integrating matplotlib with QML
- Mouse and keyboard event handling
- Building interactive visualization widgets
