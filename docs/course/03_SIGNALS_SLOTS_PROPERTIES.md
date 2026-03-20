# Module 3: Signals, Slots, and Properties

## Learning Objectives

By the end of this module, you will:
- Master Qt's signal/slot mechanism for event-driven programming
- Implement reactive properties with proper change notification
- Design loosely-coupled architectures using signals
- Handle complex signal patterns (chaining, filtering, queuing)
- Debug signal/slot connections effectively

---

## 3.1 Understanding Qt's Signal/Slot Paradigm

### The Observer Pattern

Qt's signal/slot mechanism implements the **observer pattern**:

```
┌─────────────┐          ┌─────────────┐
│   Subject   │ ──────>  │  Observer   │
│  (Emitter)  │  signal  │  (Receiver) │
└─────────────┘          └─────────────┘

Subject emits signals when state changes
Observers react by executing slots
Multiple observers can watch one subject
One observer can watch multiple subjects
```

### Why Signals and Slots?

**Traditional callback approach**:
```python
# Tight coupling - button knows about handler
button.onClick = self.handle_click

# Callback signature must match exactly
# Hard to add/remove handlers dynamically
```

**Qt's signal/slot approach**:
```python
# Loose coupling - button just emits
button.clicked.connect(self.handle_click)
button.clicked.connect(self.log_click)      # Multiple handlers
button.clicked.connect(analytics.track)      # Cross-object

# Easy to disconnect
button.clicked.disconnect(self.log_click)
```

### Thread Safety

Signals are **thread-safe by default**:
- Cross-thread signals are queued automatically
- The receiving slot executes in the receiver's thread
- No explicit locking needed for signal emission

---

## 3.2 Defining Signals in Python

### Basic Signal Definition

```python
from PySide6.QtCore import QObject, Signal

class MyClass(QObject):
    # Signals are CLASS attributes, defined before __init__

    # No parameters
    taskCompleted = Signal()

    # Single parameter
    statusChanged = Signal(str)

    # Multiple parameters
    progressChanged = Signal(int, int)  # current, total

    # Complex types
    dataReady = Signal('QVariantList')
    configUpdated = Signal('QVariantMap')

    # Object reference
    itemSelected = Signal(QObject)

    def __init__(self):
        super().__init__()
        # Signals are ready to use
```

### Named Arguments for QML

```python
# Named arguments help QML handlers
coordinateChanged = Signal(
    float, float, float,
    arguments=['x', 'y', 'z']
)

# In QML:
# onCoordinateChanged: (x, y, z) => console.log(x, y, z)
```

### TRANS-QML Signal Examples

From `src/backend/app_backend.py`:
```python
class AppBackend(QObject):
    # Status and progress
    statusChanged = Signal(str)
    progressChanged = Signal(int, int, str)  # current, total, message
    isBusyChanged = Signal(bool)

    # Data events
    dataLoaded = Signal(str)  # dataset_name
    datasetDeleted = Signal(str)
    datasetRenamed = Signal(str, str)  # old_name, new_name

    # Errors
    errorOccurred = Signal(str, str)  # title, message

    # Window management
    tableCreated = Signal(str, str)  # table_id, title
    graphCreated = Signal(str, str)  # graph_id, title

    # Project events
    projectLoaded = Signal(str)  # project_path
    projectSaved = Signal(str)
    projectModifiedChanged = Signal(bool)

    # Request signals (Python → QML)
    createFloatingGraphRequested = Signal(str, str, 'QVariantList', str, str)
    createFloatingTableRequested = Signal(str, str, 'QVariantList', 'QVariantList')
```

---

## 3.3 Emitting Signals

### Basic Emission

```python
class DataProcessor(QObject):
    progressChanged = Signal(int, int)
    taskCompleted = Signal()
    resultReady = Signal(str)

    def process(self):
        total = 100

        for i in range(total):
            # Do work...

            # Emit progress
            self.progressChanged.emit(i + 1, total)

        # Emit completion
        self.taskCompleted.emit()
        self.resultReady.emit("Processing complete!")
```

### Conditional Emission (Optimization)

Only emit when value actually changes:

```python
class Settings(QObject):
    themeChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self._theme = "dark"

    def setTheme(self, theme: str):
        # Only emit if changed - prevents infinite loops and unnecessary updates
        if self._theme != theme:
            self._theme = theme
            self.themeChanged.emit(theme)
```

### Emitting Complex Data

```python
class DataManager(QObject):
    curvesReady = Signal('QVariantList')
    statsReady = Signal('QVariantMap')

    def computeCurves(self):
        curves = []
        for i in range(5):
            curves.append({
                'x': list(range(100)),
                'y': [math.sin(j * 0.1 + i) for j in range(100)],
                'label': f'Curve {i}',
                'color': f'#{i*30:02x}80{255-i*30:02x}'
            })

        # Emit list of dicts
        self.curvesReady.emit(curves)

    def computeStats(self):
        stats = {
            'mean': 42.5,
            'std': 3.2,
            'min': 35.0,
            'max': 50.0,
            'count': 1000
        }

        # Emit dict
        self.statsReady.emit(stats)
```

---

## 3.4 Connecting Signals to Slots

### Python-to-Python Connections

```python
class Controller(QObject):
    def __init__(self):
        super().__init__()

        self.model = DataModel()
        self.view = DataView()
        self.logger = Logger()

        # Connect signals to slots
        self.model.dataChanged.connect(self.view.refresh)
        self.model.dataChanged.connect(self.logger.logChange)
        self.model.errorOccurred.connect(self.handleError)

    def handleError(self, title: str, message: str):
        print(f"Error: {title} - {message}")

    def cleanup(self):
        # Disconnect when done
        self.model.dataChanged.disconnect(self.view.refresh)

        # Or disconnect all
        self.model.dataChanged.disconnect()
```

### Lambda Connections

```python
# Pass additional context with lambda
button.clicked.connect(lambda: self.handleButton("button1"))

# Transform signal parameters
slider.valueChanged.connect(
    lambda val: self.setOpacity(val / 100.0)
)

# Ignore some parameters
model.progressChanged.connect(
    lambda current, total: self.updateProgress(current)
)
```

### Connection Types

```python
from PySide6.QtCore import Qt

# Auto (default) - direct if same thread, queued if cross-thread
signal.connect(slot, Qt.AutoConnection)

# Direct - immediate call, same thread only
signal.connect(slot, Qt.DirectConnection)

# Queued - call is queued, cross-thread safe
signal.connect(slot, Qt.QueuedConnection)

# Unique - prevents duplicate connections
signal.connect(slot, Qt.UniqueConnection)

# Blocking Queued - blocks until slot completes (cross-thread)
signal.connect(slot, Qt.BlockingQueuedConnection)
```

---

## 3.5 Properties in Depth

### The Property Pattern

Properties provide:
1. **Encapsulation**: Getter/setter with validation
2. **Change notification**: Automatic signal emission
3. **QML binding**: Reactive updates in UI

### Basic Property

```python
from PySide6.QtCore import QObject, Signal, Property

class Person(QObject):
    # Change signal
    nameChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self._name = ""

    # Getter
    def getName(self) -> str:
        return self._name

    # Setter
    def setName(self, value: str):
        if self._name != value:
            self._name = value
            self.nameChanged.emit(value)

    # Property declaration
    name = Property(str, getName, setName, notify=nameChanged)
```

### Decorator Syntax (Preferred)

```python
class Person(QObject):
    nameChanged = Signal(str)
    ageChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self._name = ""
        self._age = 0

    @Property(str, notify=nameChanged)
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        if self._name != value:
            self._name = value
            self.nameChanged.emit(value)

    @Property(int, notify=ageChanged)
    def age(self) -> int:
        return self._age

    @age.setter
    def age(self, value: int):
        if self._age != value:
            self._age = max(0, value)  # Validation
            self.ageChanged.emit(self._age)
```

### Read-Only Properties

```python
class DataModel(QObject):
    itemCountChanged = Signal()

    def __init__(self):
        super().__init__()
        self._items = []

    @Property(int, notify=itemCountChanged)
    def itemCount(self) -> int:
        """Read-only: count of items."""
        return len(self._items)

    # No setter - property is read-only from QML

    def addItem(self, item):
        self._items.append(item)
        self.itemCountChanged.emit()
```

### Constant Properties

```python
class AppInfo(QObject):
    @Property(str, constant=True)
    def version(self) -> str:
        """Constant: never changes."""
        return "1.0.0"

    @Property(str, constant=True)
    def author(self) -> str:
        return "Your Name"
```

### Complex Type Properties

```python
class SettingsManager(QObject):
    colorSchemeChanged = Signal()

    def __init__(self):
        super().__init__()
        self._color_scheme = {
            'primary': '#5BCEFA',
            'secondary': '#F5A9B8',
            'background': '#1a1a2e'
        }

    @Property('QVariantMap', notify=colorSchemeChanged)
    def colorScheme(self) -> dict:
        return self._color_scheme

    @colorScheme.setter
    def colorScheme(self, value: dict):
        self._color_scheme = value
        self.colorSchemeChanged.emit()
```

### TRANS-QML Property Examples

From `src/backend/app_backend.py`:
```python
class AppBackend(QObject):
    # Signals for properties
    statusChanged = Signal(str)
    projectReadyChanged = Signal(bool)
    isBusyChanged = Signal(bool)
    activeDatasetChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self._status = "Ready"
        self._project_ready = False
        self._is_busy = False
        self._active_dataset = ""

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str):
        if self._status != value:
            self._status = value
            self.statusChanged.emit(value)

    @Property(bool, notify=projectReadyChanged)
    def projectReady(self) -> bool:
        return self._project_ready

    @Property(bool, notify=isBusyChanged)
    def isBusy(self) -> bool:
        return self._is_busy

    @Property(str, notify=activeDatasetChanged)
    def activeDataset(self) -> str:
        return self._active_dataset

    @activeDataset.setter
    def activeDataset(self, value: str):
        if self._active_dataset != value:
            self._active_dataset = value
            self.activeDatasetChanged.emit(value)

    # Read-only computed property
    @Property(int, notify=statusChanged)  # Reuse status signal
    def datasetCount(self) -> int:
        return len(self._datasets)

    # Constant property
    @Property(QObject, constant=True)
    def workflowManager(self):
        return self._workflow_manager
```

---

## 3.6 QML Property Bindings

### Automatic Updates

When Python properties change, QML bindings update automatically:

```qml
// QML automatically updates when backend.status changes
Label {
    text: "Status: " + backend.status
    color: backend.isBusy ? "orange" : "white"
}

// Complex binding
Rectangle {
    width: parent.width
    height: backend.datasetCount * 30

    visible: backend.projectReady && backend.datasetCount > 0
}
```

### The Connections Component

For handling signals with parameters:

```qml
Connections {
    target: backend

    // Signal with no parameters
    function onTaskCompleted() {
        busyIndicator.visible = false
    }

    // Signal with parameters
    function onProgressChanged(current, total, message) {
        progressBar.value = current / total
        progressLabel.text = message
    }

    // Signal with complex data
    function onCurvesReady(curves) {
        for (var i = 0; i < curves.length; i++) {
            graphCanvas.addCurve(
                curves[i].label,
                curves[i].x,
                curves[i].y,
                curves[i].color
            )
        }
    }

    // Error handling
    function onErrorOccurred(title, message) {
        errorDialog.title = title
        errorDialog.text = message
        errorDialog.open()
    }
}
```

### Conditional Connections

```qml
Connections {
    target: backend
    enabled: mainWindow.visible  // Only active when window visible

    function onDataChanged() {
        refreshView()
    }
}
```

### Multiple Targets

```qml
// Connect to main backend
Connections {
    target: backend
    function onStatusChanged(status) { /* ... */ }
}

// Connect to workflow manager
Connections {
    target: backend.workflowManager
    enabled: backend.workflowManager !== null

    function onWorkflowCompleted(name) { /* ... */ }
}

// Connect to preferences
Connections {
    target: preferencesManager
    function onThemeChanged(theme) {
        applyTheme(theme)
    }
}
```

---

## 3.7 Advanced Signal Patterns

### Signal Chaining

Forward signals through layers:

```python
class Model(QObject):
    dataChanged = Signal()

class ViewModel(QObject):
    modelDataChanged = Signal()

    def __init__(self, model: Model):
        super().__init__()
        self._model = model

        # Chain model signal to viewmodel signal
        self._model.dataChanged.connect(self.modelDataChanged.emit)
```

### Signal Aggregation

Combine multiple signals:

```python
class Dashboard(QObject):
    anyDataChanged = Signal()

    def __init__(self):
        super().__init__()

        self.chart1 = Chart()
        self.chart2 = Chart()
        self.table = Table()

        # Aggregate all change signals
        self.chart1.dataChanged.connect(self.anyDataChanged.emit)
        self.chart2.dataChanged.connect(self.anyDataChanged.emit)
        self.table.dataChanged.connect(self.anyDataChanged.emit)
```

### Debouncing Signals

Prevent rapid-fire updates:

```python
from PySide6.QtCore import QTimer

class SearchBox(QObject):
    textChanged = Signal(str)
    searchRequested = Signal(str)

    def __init__(self):
        super().__init__()
        self._text = ""
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emitSearch)

    def setText(self, text: str):
        self._text = text
        self.textChanged.emit(text)

        # Restart debounce timer (300ms delay)
        self._debounce_timer.stop()
        self._debounce_timer.start(300)

    def _emitSearch(self):
        self.searchRequested.emit(self._text)
```

### Blocking Signal Emission

Temporarily block signals:

```python
class BatchUpdater(QObject):
    itemChanged = Signal(int)
    batchComplete = Signal()

    def updateMany(self, items: list):
        # Block signals during batch
        self.blockSignals(True)

        for i, item in enumerate(items):
            self._updateItem(i, item)
            # itemChanged NOT emitted

        # Re-enable signals
        self.blockSignals(False)

        # Emit single notification
        self.batchComplete.emit()
```

---

## 3.8 Cross-Component Communication

### Event Bus Pattern

Central event dispatcher:

```python
class EventBus(QObject):
    """Application-wide event dispatcher."""

    # Define all app-wide events
    userLoggedIn = Signal(str)  # username
    userLoggedOut = Signal()
    themeChanged = Signal(str)
    languageChanged = Signal(str)
    dataImported = Signal(str, int)  # name, count
    errorOccurred = Signal(str, str)

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

Usage:

```python
# In auth module
EventBus.instance().userLoggedIn.emit("john_doe")

# In UI module
EventBus.instance().userLoggedIn.connect(self.updateUserDisplay)
EventBus.instance().themeChanged.connect(self.applyTheme)
```

### Parent-Child Communication

```python
class Parent(QObject):
    def __init__(self):
        super().__init__()
        self.child = Child()

        # Listen to child
        self.child.taskCompleted.connect(self.onChildComplete)

    def onChildComplete(self, result: str):
        print(f"Child completed: {result}")


class Child(QObject):
    taskCompleted = Signal(str)

    def doWork(self):
        # Do work...
        self.taskCompleted.emit("Success!")
```

---

## 3.9 TRANS-QML Signal Flow Example

### Complete Flow: Loading a Dataset

```
User clicks "Open" button
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ QML: Main.qml                                               │
│                                                             │
│ MenuItem {                                                  │
│     text: "Open..."                                         │
│     onTriggered: fileDialog.open()                          │
│ }                                                           │
│                                                             │
│ FileDialog {                                                │
│     onAccepted: backend.loadDataset(selectedFile)           │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ @Slot(str)
┌─────────────────────────────────────────────────────────────┐
│ Python: app_backend.py                                      │
│                                                             │
│ def loadDataset(self, filepath: str):                       │
│     self.status = "Loading..."           ──> statusChanged  │
│     self.isBusyChanged.emit(True)        ──> isBusyChanged  │
│                                                             │
│     self.worker_manager.submit(                             │
│         name="Load Dataset",                                │
│         operation=self._load_dataset_impl,                  │
│         filepath=filepath,                                  │
│         on_finished=self._on_load_complete                  │
│     )                                                       │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ (Worker Thread)
┌─────────────────────────────────────────────────────────────┐
│ Python: worker.py                                           │
│                                                             │
│ def run(self):                                              │
│     result = task.operation(...)                            │
│     self.task_completed.emit(name, result)  ──> signal      │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ (Main Thread via signal)
┌─────────────────────────────────────────────────────────────┐
│ Python: app_backend.py                                      │
│                                                             │
│ def _on_load_complete(self, dataset):                       │
│     self._datasets[name] = dataset                          │
│     self.status = "Ready"                ──> statusChanged  │
│     self.isBusyChanged.emit(False)       ──> isBusyChanged  │
│     self.dataLoaded.emit(name)           ──> dataLoaded     │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ QML: Main.qml                                               │
│                                                             │
│ Connections {                                               │
│     target: backend                                         │
│                                                             │
│     function onDataLoaded(datasetName) {                    │
│         console.log("Loaded:", datasetName)                 │
│         projectBrowser.refresh()                            │
│     }                                                       │
│                                                             │
│     function onStatusChanged(status) {                      │
│         statusBar.text = status  // Automatic binding       │
│     }                                                       │
│ }                                                           │
│                                                             │
│ BusyIndicator {                                             │
│     running: backend.isBusy  // Property binding            │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3.10 Debugging Signals and Slots

### Logging Signal Emissions

```python
import logging
logger = logging.getLogger(__name__)

class MyClass(QObject):
    valueChanged = Signal(int)

    def setValue(self, value: int):
        logger.debug(f"setValue called with: {value}")

        if self._value != value:
            self._value = value
            logger.debug(f"Emitting valueChanged: {value}")
            self.valueChanged.emit(value)
```

### Tracing Connections

```python
# Monkey-patch for debugging
original_connect = Signal.connect

def traced_connect(self, slot, *args, **kwargs):
    logger.debug(f"Connecting {self} to {slot}")
    return original_connect(self, slot, *args, **kwargs)

Signal.connect = traced_connect
```

### QML Debugging

```qml
Connections {
    target: backend

    function onAnySignal() {
        console.log("Signal received from backend")
        console.trace()  // Print call stack
    }

    function onProgressChanged(current, total, message) {
        console.log("Progress:", current, "/", total, message)
        console.log("Type of current:", typeof current)
    }
}
```

### Common Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| Signal not received | Wrong handler name | Use `on` + PascalCase |
| Handler never called | Target is null | Check target with `enabled: target !== null` |
| Value always undefined | Type mismatch | Check parameter types |
| UI doesn't update | Forgot notify signal | Add `notify=signalName` to Property |
| Infinite loop | Setting value in setter | Check `if value != current` before emit |

---

## 3.11 Exercises

### Exercise 3.1: Selection Model

Create a selection model:
1. `selectedItems` property (list of strings)
2. `selectionChanged` signal
3. `select(item)`, `deselect(item)`, `toggleSelection(item)` slots
4. `isSelected(item)` slot returning bool
5. QML list with checkboxes bound to selection

### Exercise 3.2: Undo/Redo with Signals

Implement undo/redo:
1. `undoAvailable` and `redoAvailable` properties
2. `historyChanged` signal
3. `undo()` and `redo()` slots
4. QML buttons enabled by properties

### Exercise 3.3: Settings Sync

Create synchronized settings:
1. Python settings backend
2. Multiple QML components reading same settings
3. Change in one component updates all others
4. Use signals for synchronization

---

## 3.12 Key Takeaways

1. **Signals** are the Qt way to notify about events
2. **Slots** are methods that can be connected to signals
3. **Properties** combine getter/setter/signal for reactive binding
4. Always emit **notify signal** when property value changes
5. Use **Connections** component for handling signals in QML
6. **Named arguments** make QML handlers cleaner
7. Consider **debouncing** for rapid-fire events
8. Use **conditional emission** to prevent unnecessary updates

---

## Next Module

In [Module 4: Multithreading for Responsive UIs](./04_MULTITHREADING.md), we'll learn:
- QThread and worker patterns
- Thread-safe signal communication
- Progress reporting
- Task cancellation
