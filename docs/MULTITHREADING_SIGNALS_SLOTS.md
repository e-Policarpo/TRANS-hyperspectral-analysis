# TRANS-QML Multithreading and Signals/Slots Architecture

This document provides detailed technical documentation of the multithreading patterns, Qt signals/slots system, and QML-Python communication mechanisms used in TRANS-QML.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Multithreading Architecture](#2-multithreading-architecture)
3. [Qt Signals and Slots in Python](#3-qt-signals-and-slots-in-python)
4. [QML Signals and Connections](#4-qml-signals-and-connections)
5. [QML-Python Bridge Patterns](#5-qml-python-bridge-patterns)
6. [Widget Implementation Patterns](#6-widget-implementation-patterns)
7. [Data Flow Diagrams](#7-data-flow-diagrams)
8. [Best Practices and Guidelines](#8-best-practices-and-guidelines)

---

## 1. Architecture Overview

TRANS-QML uses a hybrid Python/QML architecture where:

- **Python (PySide6)**: Handles data processing, file I/O, scientific computation, and business logic
- **QML**: Handles the user interface, animations, and user interactions
- **Qt Signals/Slots**: Provides thread-safe communication between components

### Key Architectural Principles

1. **Non-blocking UI**: All long-running operations execute in background threads
2. **Thread-safe communication**: Qt signals ensure safe cross-thread data transfer
3. **Reactive updates**: Property bindings automatically propagate state changes
4. **Decoupled components**: Signal/slot connections allow loose coupling

---

## 2. Multithreading Architecture

### 2.1 Worker Thread Pattern

**Location**: `src/backend/worker.py`

TRANS-QML uses a **persistent worker thread** pattern to handle background operations. This approach avoids the overhead of creating/destroying threads for each operation.

#### Task Class

```python
class Task:
    """Represents a task to be executed in the worker thread."""
    def __init__(self, name: str, operation: Callable, args: tuple, kwargs: dict,
                 on_finished: Callable = None, on_error: Callable = None):
        self.name = name           # Display name for the task
        self.operation = operation  # The function to execute
        self.args = args           # Positional arguments
        self.kwargs = kwargs       # Keyword arguments
        self.on_finished = on_finished  # Success callback
        self.on_error = on_error   # Error callback
        self.cancelled = False     # Cancellation flag
        self.progress = 0          # Progress tracking (0-100)
```

#### PersistentWorker Class

The `PersistentWorker` is a `QThread` subclass that:
1. Maintains a task queue
2. Processes tasks sequentially
3. Emits signals on task lifecycle events
4. Supports task cancellation

```python
class PersistentWorker(QThread):
    """Single persistent worker thread that processes tasks from a queue."""

    # Signals for task lifecycle events
    task_started = Signal(str)           # Emits task name when starting
    task_completed = Signal(str, object) # Emits task name and result
    task_failed = Signal(str, str, str)  # Emits task name, error title, message

    def run(self):
        """Main loop - waits for tasks and executes them."""
        while self._running:
            try:
                task = self.task_queue.get(timeout=0.5)

                if task is None:  # Poison pill to stop thread
                    break

                if task.cancelled:
                    continue

                self._current_task = task
                self.task_started.emit(task.name)

                try:
                    # Execute operation with task as first arg for cancellation checking
                    result = task.operation(task, *task.args, **task.kwargs)

                    if not task.cancelled:
                        self.task_completed.emit(task.name, result)

                except Exception as e:
                    self.task_failed.emit(task.name, "Operation Error", str(e))

            except:
                continue  # Timeout - keep waiting
```

#### WorkerManager Class

The `WorkerManager` provides a high-level interface for submitting tasks:

```python
class WorkerManager(QObject):
    """Manages the persistent worker thread."""

    # Public signals for external consumption
    worker_started = Signal(str)    # operation name
    worker_completed = Signal(str)  # operation name
    worker_failed = Signal(str, str) # operation name, error message
    worker_cancelled = Signal(str)   # operation name

    def submit(self, name: str, operation: Callable, *args,
               on_finished: Callable = None, on_error: Callable = None,
               on_progress: Callable = None, **kwargs):
        """Submit an operation to run in the background."""
        # Store callbacks for main-thread execution
        self._task_callbacks[name] = (on_finished, on_error)

        task = Task(name, operation, args, kwargs, None, None)
        self.worker.submit_task(task)
```

### 2.2 Thread-Safe Callback Execution

A critical pattern in TRANS-QML is ensuring callbacks execute in the main thread:

```python
def _on_task_completed(self, name: str, result: Any):
    """Handle task completion - runs in main thread via signal."""
    self.worker_completed.emit(name)

    # Invoke callback in main thread (safe for UI updates)
    if name in self._task_callbacks:
        on_finished, _ = self._task_callbacks[name]
        if on_finished:
            try:
                on_finished(result)
            except Exception as e:
                logger.error(f"Error in callback for {name}: {e}")
        del self._task_callbacks[name]
```

### 2.3 Task Cancellation Pattern

Tasks can check for cancellation during execution:

```python
def smooth_curves(self, task, dataset_name: str, window_size: int, ...):
    """Long-running operation with cancellation support."""

    for i, spectrum in enumerate(spectra):
        # Check for cancellation periodically
        if task.cancelled:
            logger.info(f"Task cancelled at spectrum {i}")
            return None

        # Process spectrum...
        task.progress = (i / total) * 100
```

### 2.4 Usage in AppBackend

```python
class AppBackend(ToolImplementations, QObject):
    def __init__(self):
        # Initialize worker manager
        self.worker_manager = WorkerManager(max_concurrent=3)

        # Connect worker signals to backend slots
        self.worker_manager.worker_started.connect(self._on_worker_started)
        self.worker_manager.worker_completed.connect(self._on_worker_completed)
        self.worker_manager.worker_failed.connect(self._on_worker_failed)
        self.worker_manager.worker_cancelled.connect(self._on_worker_cancelled)

    @Slot(str, int, int, str)
    def smoothCurves(self, dataset_name: str, window_size: int,
                     poly_order: int, smoothing_type: str):
        """QML-callable slot that runs smoothing in background."""

        self.worker_manager.submit(
            name=f"Smoothing {dataset_name}",
            operation=self.smooth_curves,  # Internal implementation
            dataset_name=dataset_name,
            window_size=window_size,
            poly_order=poly_order,
            smoothing_type=smoothing_type,
            on_finished=self._on_smooth_finished,
            on_error=self._on_tool_error
        )

    def _on_worker_started(self, name: str):
        """Called when a worker task starts."""
        self.status = f"Processing: {name}"
        self.isBusyChanged.emit(True)

    def _on_worker_completed(self, name: str):
        """Called when a worker task completes."""
        self.status = "Ready"
        self.isBusyChanged.emit(False)
```

---

## 3. Qt Signals and Slots in Python

### 3.1 Signal Definitions

Signals are defined as class attributes using `PySide6.QtCore.Signal`:

```python
from PySide6.QtCore import QObject, Signal, Slot, Property

class AppBackend(QObject):
    # Simple signals
    statusChanged = Signal(str)
    isBusyChanged = Signal(bool)

    # Signals with multiple parameters
    progressChanged = Signal(int, int, str)  # current, total, message
    errorOccurred = Signal(str, str)         # title, message

    # Signals with complex types
    dataLoaded = Signal(str)                    # dataset_name
    toolCompleted = Signal(str, str)            # tool_name, output_path
    createFloatingGraphRequested = Signal(str, str, 'QVariantList', str, str)
```

### 3.2 Slot Definitions

Slots are Python methods decorated with `@Slot`:

```python
class AppBackend(QObject):
    @Slot(str, str)
    def createProject(self, project_path: str, project_name: str) -> None:
        """Create a new project at the specified path."""
        # Implementation...

    @Slot(str, result=bool)
    def openProjectFile(self, file_path: str) -> bool:
        """Open a .hrt project file. Returns True on success."""
        # Implementation...
        return True

    @Slot(str, result='QVariantMap')
    def getDatasetInfo(self, dataset_name: str) -> Dict:
        """Get metadata about a dataset."""
        # Return a dictionary that becomes QVariantMap in QML
        return {
            'name': dataset_name,
            'num_spectra': self._datasets[dataset_name].num_spectra,
            'num_points': self._datasets[dataset_name].num_points
        }
```

### 3.3 Property System

Qt Properties expose Python values to QML with change notification:

```python
class AppBackend(QObject):
    # Private storage
    _status = "Ready"
    _project_ready = False

    # Property with getter, setter, and notify signal
    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if self._status != value:
            self._status = value
            self.statusChanged.emit(value)

    # Read-only property
    @Property(bool, notify=projectReadyChanged)
    def projectReady(self):
        return self._project_ready

    # Constant property (doesn't change after creation)
    @Property(QObject, constant=True)
    def workflowManager(self):
        return self.workflow_manager
```

### 3.4 Signal Connections in Python

```python
class AppBackend(QObject):
    def __init__(self):
        super().__init__()

        # Connect internal signals
        self.worker_manager.worker_started.connect(self._on_worker_started)
        self.worker_manager.worker_completed.connect(self._on_worker_completed)

        # Connect to external manager signals
        self.workflow_manager.workflowExecutionCompleted.connect(
            self._on_workflow_completed
        )

    def _on_worker_started(self, name: str):
        self.status = f"Processing: {name}"
```

---

## 4. QML Signals and Connections

### 4.1 QML Signal Definitions

In QML, signals are defined in component properties:

```qml
Rectangle {
    id: workflowCanvas

    // Signal definitions
    signal nodeSelected(var node)
    signal nodeDeselected()
    signal connectionCreated(string sourceNode, string sourcePort,
                            string targetNode, string targetPort)
    signal connectionRemoved(string connectionId)
    signal nodeRemoved(string nodeId)
    signal nodeAdded(string nodeId, string toolName, real x, real y)
    signal statusMessage(string message, color messageColor)
    signal nodeParameterChanged(string nodeId, string paramName, var value)
}
```

### 4.2 Signal Emission in QML

```qml
MouseArea {
    onClicked: function(mouse) {
        // Emit signal with parameters
        nodeSelected(nodeData)
    }
}

function addNode(toolName, x, y) {
    if (workflowManager && workflowId) {
        var nodeId = workflowManager.addNode(workflowId, toolName, x, y)
        if (nodeId) {
            // Emit signal after operation
            nodeAdded(nodeId, toolName, x, y)
        }
    }
}
```

### 4.3 Connections Component

The `Connections` component connects to signals from other objects:

```qml
ApplicationWindow {
    id: mainWindow

    // Connect to backend signals
    Connections {
        target: backend

        function onDataLoaded(datasetName) {
            console.log("Data loaded:", datasetName)
            statusText.text = "Loaded: " + datasetName
            mapEditorWorkstation.linkDatasetsFromBackend(backend)
        }

        function onErrorOccurred(title, message) {
            errorDialog.title = title
            errorDialog.text = message
            errorDialog.open()
        }

        function onProgressChanged(current, total, message) {
            progressDialog.current = current
            progressDialog.total = total
            progressDialog.message = message

            if (current === total) {
                progressDialog.close()
            } else if (!progressDialog.visible) {
                progressDialog.open()
            }
        }

        function onToolOpened(toolName) {
            console.log("Tool opened:", toolName)
        }

        function onLargeDatasetConfirmation(datasetName, numSpectra, numPoints) {
            largeDatasetDialog.datasetName = datasetName
            largeDatasetDialog.numSpectra = numSpectra
            largeDatasetDialog.numPoints = numPoints
            largeDatasetDialog.open()
        }
    }

    // Connect to workflow manager signals
    Connections {
        target: backend ? backend.workflowManager : null

        function onWorkflowExecutionStarted(name) {
            workflowExecutionOverlay.visible = true
            workflowExecutionOverlay.workflowName = name
        }

        function onWorkflowExecutionProgress(current, total, message) {
            workflowExecutionOverlay.currentStep = current
            workflowExecutionOverlay.totalSteps = total
            workflowExecutionOverlay.currentMessage = message
        }

        function onWorkflowExecutionCompleted(name, success, errors) {
            workflowExecutionOverlay.visible = false
            workflowResultDialog.isSuccess = success
            workflowResultDialog.workflowName = name
            workflowResultDialog.open()
        }
    }

    // Connect to preferences manager for theme changes
    Connections {
        target: backend ? backend.preferencesManager : null
        enabled: backend && backend.preferencesManager

        function onColorSchemeChanged(schemeName) {
            console.log("Color scheme changed:", schemeName)
            applyColorScheme()
        }
    }
}
```

### 4.4 Property Bindings as Implicit Signals

QML property bindings automatically update when source properties change:

```qml
ApplicationWindow {
    // Reactive properties bound to backend
    property bool projectReady: backend.projectReady

    // Color binds to bgDark, updates when applyColorScheme() changes it
    color: bgDark

    // Title binds to backend properties
    title: backend.projectReady ?
           "TRANS-QML - " + backend.projectName :
           "TRANS-QML - Hyperspectral Data Analysis"
}

// Child components inherit and bind to parent properties
UnifiedWorkspace {
    // Reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"

    // These update automatically when mainWin properties change
    color: bgDark
}
```

---

## 5. QML-Python Bridge Patterns

### 5.1 Calling Python Slots from QML

```qml
Button {
    text: "Load Project"
    onClicked: {
        // Call Python slot with arguments
        backend.openProject(projectPath, projectName)
    }
}

MenuItem {
    text: "Save Project"
    enabled: backend.projectReady  // Bind to Python property
    onTriggered: backend.saveProjectFile("")
}

// Using return values from Python slots
function loadDatasetInfo(name) {
    var info = backend.getDatasetInfo(name)
    console.log("Spectra:", info.num_spectra)
    console.log("Points:", info.num_points)
}
```

### 5.2 Python Emitting Signals to QML

```python
class AppBackend(QObject):
    # Signal definition
    createFloatingGraphRequested = Signal(str, str, 'QVariantList', str, str)

    def create_graph_output(self, title: str, curves: list):
        """Create a floating graph entity in QML."""
        entity_id = f"graph_{uuid.uuid4().hex[:8]}"

        # Convert numpy arrays to QML-compatible lists
        qml_curves = []
        for curve in curves:
            qml_curves.append({
                'x': curve['x'].tolist(),
                'y': curve['y'].tolist(),
                'label': curve.get('label', ''),
                'color': curve.get('color', '#5BCEFA')
            })

        # Emit signal - QML Connections will handle it
        self.createFloatingGraphRequested.emit(
            entity_id, title, qml_curves, "X", "Y"
        )
```

QML handling of the signal:

```qml
Connections {
    target: backend

    function onCreateFloatingGraphRequested(entityId, title, curves, xLabel, yLabel) {
        console.log("Creating floating graph:", entityId, title)

        // Switch to appropriate tab
        if (currentTabIndex > 1) {
            currentTabIndex = 0
        }

        // Create the graph entity in workspace
        var graphId = workspace.createGraphEntity(
            title, 100, 100, 500, 350, curves, xLabel, yLabel
        )
        console.log("Floating graph created:", graphId)
    }
}
```

### 5.3 Complex Data Transfer

#### Python to QML (QVariantMap, QVariantList)

```python
@Slot(str, result='QVariantMap')
def getWorkflowData(self, workflow_id: str) -> Dict:
    """Get workflow data for QML consumption."""
    workflow = self._workflows.get(workflow_id)
    if not workflow:
        return {}

    # Convert to QML-compatible structure
    return {
        'id': workflow.id,
        'name': workflow.name,
        'nodes': [self._node_to_dict(n) for n in workflow.nodes],
        'connections': [self._conn_to_dict(c) for c in workflow.connections]
    }

def _node_to_dict(self, node):
    """Convert WorkflowNode to QML-compatible dict."""
    return {
        'id': node.id,
        'tool_name': node.tool_name,
        'display_name': node.display_name,
        'x': node.x,
        'y': node.y,
        'inputs': [self._port_to_dict(p) for p in node.inputs],
        'outputs': [self._port_to_dict(p) for p in node.outputs],
        'parameters': dict(node.parameters)  # Already a dict
    }
```

#### QML to Python

```qml
// Pass complex data to Python
function executeWithParams(params) {
    // QML object -> QVariantMap in Python
    backend.executeToolWithParams(toolName, {
        "window_size": windowSizeSlider.value,
        "poly_order": polyOrderSpinBox.value,
        "smoothing_type": smoothingTypeCombo.currentText,
        "intervals": [[start1, end1], [start2, end2]]
    })
}
```

---

## 6. Widget Implementation Patterns

### 6.1 QQuickPaintedItem Pattern

TRANS-QML uses `QQuickPaintedItem` to render matplotlib figures in QML.

**Location**: `src/widgets/qml_profile_canvas.py`, `qml_map_canvas.py`, `qml_graph_canvas.py`

```python
from PySide6.QtQuick import QQuickPaintedItem
from PySide6.QtCore import Signal, Slot, Property, QPointF
from PySide6.QtGui import QPainter, QImage
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend for thread safety
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

class QmlProfileCanvas(QQuickPaintedItem):
    """QML-compatible canvas for spectrum/profile plotting."""

    # Signals for QML interaction
    cursorMoved = Signal(float, float, arguments=['x', 'y'])
    pointClicked = Signal(float, float, arguments=['x', 'y'])
    rangeSelected = Signal(float, float, arguments=['x1', 'x2'])
    dataChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Accept mouse events
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        self.setAcceptHoverEvents(True)

        # Matplotlib setup
        self.figure = Figure(figsize=(6, 4), dpi=100)
        self.canvas = FigureCanvasAgg(self.figure)
        self.ax = self.figure.add_subplot(111)

        # Image buffer for rendering
        self._image = None
        self._needs_redraw = True

    def paint(self, painter: QPainter):
        """Called by QML to render the widget."""
        if self._needs_redraw or self._image is None:
            self._render_to_image()
            self._needs_redraw = False

        if self._image:
            painter.drawImage(0, 0, self._image)

    def _render_to_image(self):
        """Render matplotlib figure to QImage buffer."""
        # Resize figure to match widget size
        w, h = int(self.width()), int(self.height())
        if w <= 0 or h <= 0:
            return

        dpi = 100
        self.figure.set_size_inches(w / dpi, h / dpi)

        # Draw to canvas
        self.canvas.draw()

        # Convert to QImage
        buf = self.canvas.buffer_rgba()
        self._image = QImage(buf, w, h, QImage.Format_RGBA8888).copy()

    @Slot(result='QVariantMap')
    def pixelToData(self, px: float, py: float) -> dict:
        """Convert pixel coordinates to data coordinates."""
        # Use matplotlib's inverse transform
        inv = self.ax.transData.inverted()
        data_x, data_y = inv.transform((px, py))
        return {'x': float(data_x), 'y': float(data_y)}

    def mouseMoveEvent(self, event):
        """Handle mouse movement for cursor tracking."""
        pos = event.pos()
        coords = self.pixelToData(pos.x(), pos.y())
        self.cursorMoved.emit(coords['x'], coords['y'])

    def mousePressEvent(self, event):
        """Handle mouse click."""
        pos = event.pos()
        coords = self.pixelToData(pos.x(), pos.y())
        self.pointClicked.emit(coords['x'], coords['y'])
```

### 6.2 QAbstractTableModel Pattern

**Location**: `src/models/table_data_model.py`

```python
from PySide6.QtCore import QAbstractTableModel, Qt, Signal, Slot, Property

class TableDataModel(QAbstractTableModel):
    """Spreadsheet-like table model with formula support."""

    # Signals
    dataModified = Signal()
    columnCountChanged = Signal(int)
    rowCountChanged = Signal(int)
    formulaError = Signal(str, str)  # cell, error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = pd.DataFrame()
        self._column_metadata = {}
        self._formula_engine = FormulaEngine()

    # Required QAbstractTableModel methods
    def rowCount(self, parent=None) -> int:
        return len(self._data)

    def columnCount(self, parent=None) -> int:
        return len(self._data.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.DisplayRole:
            return str(self._data.iloc[index.row(), index.column()])
        elif role == Qt.EditRole:
            return self._data.iloc[index.row(), index.column()]
        elif role == Qt.TextAlignmentRole:
            return Qt.AlignRight | Qt.AlignVCenter

        return None

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.EditRole:
            return False

        # Check for formula
        if isinstance(value, str) and value.startswith('='):
            try:
                result = self._formula_engine.evaluate(
                    value[1:], self._data, index.row()
                )
                self._data.iloc[index.row(), index.column()] = result
            except Exception as e:
                self.formulaError.emit(
                    f"{chr(65 + index.column())}{index.row() + 1}",
                    str(e)
                )
                return False
        else:
            self._data.iloc[index.row(), index.column()] = value

        self.dataChanged.emit(index, index, [role])
        self.dataModified.emit()
        return True

    # QML-callable slots
    @Slot(int, result=str)
    def getColumnName(self, column: int) -> str:
        if 0 <= column < len(self._data.columns):
            return str(self._data.columns[column])
        return ""

    @Slot(int, result='QVariantList')
    def getColumnData(self, column: int) -> list:
        if 0 <= column < len(self._data.columns):
            return self._data.iloc[:, column].tolist()
        return []
```

### 6.3 Registration in QML

```python
# In main.py
from src.widgets.qml_profile_canvas import QmlProfileCanvas
from src.widgets.qml_map_canvas import QmlMapCanvas
from src.widgets.qml_graph_canvas import QmlGraphCanvas
from src.models.table_data_model import TableDataModel

# Register types for QML
qmlRegisterType(QmlProfileCanvas, "TransQML", 1, 0, "ProfileCanvas")
qmlRegisterType(QmlMapCanvas, "TransQML", 1, 0, "MapCanvas")
qmlRegisterType(QmlGraphCanvas, "TransQML", 1, 0, "GraphCanvas")
qmlRegisterType(TableDataModel, "TransQML", 1, 0, "TableDataModel")
```

Usage in QML:

```qml
import TransQML 1.0

Rectangle {
    ProfileCanvas {
        id: profileCanvas
        anchors.fill: parent

        onCursorMoved: function(x, y) {
            cursorLabel.text = `X: ${x.toFixed(2)}, Y: ${y.toFixed(2)}`
        }

        onPointClicked: function(x, y) {
            console.log("Clicked at:", x, y)
        }

        onRangeSelected: function(x1, x2) {
            backend.integrate(datasetName, [[x1, x2]])
        }
    }
}
```

---

## 7. Data Flow Diagrams

### 7.1 Tool Execution Flow

```
┌─────────┐     @Slot()      ┌──────────────┐
│   QML   │ ────────────────>│  AppBackend  │
│ Button  │  smoothCurves()  │              │
└─────────┘                  └──────┬───────┘
                                    │
                                    │ worker_manager.submit()
                                    v
                            ┌──────────────────┐
                            │  WorkerManager   │
                            │                  │
                            └────────┬─────────┘
                                     │
                                     │ task_queue.put()
                                     v
                            ┌──────────────────┐
                            │ PersistentWorker │
                            │   (QThread)      │
                            └────────┬─────────┘
                                     │
                                     │ task.operation()
                                     v
                            ┌──────────────────┐
                            │ smooth_curves()  │
                            │ (CPU-intensive)  │
                            └────────┬─────────┘
                                     │
                                     │ task_completed.emit()
                                     v
┌─────────┐     Signal       ┌──────────────────┐
│   QML   │ <────────────────│  WorkerManager   │
│ Updates │  worker_completed│ (main thread)    │
└─────────┘                  └──────────────────┘
```

### 7.2 Property Binding Flow

```
┌────────────────────────────────────────────────────────────┐
│                     Python (AppBackend)                     │
├────────────────────────────────────────────────────────────┤
│  @Property(str, notify=statusChanged)                       │
│  def status(self):                                          │
│      return self._status                                    │
│                                                             │
│  @status.setter                                             │
│  def status(self, value):                                   │
│      if self._status != value:                              │
│          self._status = value                               │
│          self.statusChanged.emit(value)  ──────────┐        │
└────────────────────────────────────────────────────│────────┘
                                                     │
                                                     │ Signal
                                                     v
┌────────────────────────────────────────────────────────────┐
│                      QML (Main.qml)                        │
├────────────────────────────────────────────────────────────┤
│  Text {                                                     │
│      id: statusText                                         │
│      text: backend.status  <───── Binding auto-updates     │
│  }                                                          │
└────────────────────────────────────────────────────────────┘
```

### 7.3 Workflow Execution Flow

```
┌─────────────┐          ┌─────────────────┐          ┌──────────────┐
│  QML Canvas │  ────>   │ WorkflowManager │  ────>   │    Worker    │
│  "Run" btn  │          │                 │          │   Thread     │
└─────────────┘          └────────┬────────┘          └──────┬───────┘
                                  │                          │
      workflowExecutionStarted    │                          │
      <───────────────────────────│                          │
                                  │   executeWorkflow()      │
                                  │ ─────────────────────>   │
                                  │                          │
      workflowExecutionProgress   │                          │
      <───────────────────────────│ <─── progress signals ───│
                                  │                          │
      workflowExecutionCompleted  │                          │
      <───────────────────────────│ <─── completion ─────────│
```

---

## 8. Best Practices and Guidelines

### 8.1 Thread Safety Rules

1. **Never access UI elements from worker threads**
   ```python
   # WRONG - direct UI access from worker
   def worker_operation(self, task, ...):
       self.status = "Processing"  # May crash!

   # CORRECT - emit signal, handle in main thread
   def worker_operation(self, task, ...):
       # Do processing
       return result

   def _on_worker_completed(self, name, result):
       self.status = "Done"  # Safe - main thread
   ```

2. **Use signals for cross-thread communication**
   ```python
   # Define signal
   progressChanged = Signal(int, int, str)

   # Emit from anywhere
   self.progressChanged.emit(50, 100, "Halfway done")

   # QML receives safely
   # Connections { function onProgressChanged(...) {} }
   ```

3. **Copy data before sending across threads**
   ```python
   # WRONG - sending reference that may be modified
   def submit_task(self, data_array):
       self.worker.submit(operation, data_array)

   # CORRECT - send copy
   def submit_task(self, data_array):
       self.worker.submit(operation, data_array.copy())
   ```

### 8.2 Signal/Slot Best Practices

1. **Use descriptive signal names**
   ```python
   # Good
   datasetLoaded = Signal(str)
   processingCompleted = Signal(str, bool)

   # Avoid
   done = Signal()
   signal1 = Signal(str)
   ```

2. **Declare signal arguments**
   ```python
   # With argument names (better for QML)
   pointClicked = Signal(float, float, arguments=['x', 'y'])

   # In QML:
   # function onPointClicked(x, y) { console.log(x, y) }
   ```

3. **Use Properties for bindable state**
   ```python
   # For state that QML should react to
   @Property(bool, notify=isBusyChanged)
   def isBusy(self):
       return self._is_busy

   # In QML:
   # BusyIndicator { running: backend.isBusy }
   ```

### 8.3 Performance Considerations

1. **Batch updates to avoid signal storms**
   ```python
   # WRONG - emit on every item
   for item in items:
       self._items.append(item)
       self.itemAdded.emit(item)

   # CORRECT - batch and emit once
   self._items.extend(items)
   self.itemsChanged.emit()
   ```

2. **Use `Qt.callLater` for deferred updates in QML**
   ```qml
   function refreshWorkflow() {
       // Defer expensive update to avoid blocking
       Qt.callLater(function() {
           nodeRepeater.model = nodes
           connectionCanvas.requestPaint()
       })
   }
   ```

3. **Limit canvas redraws**
   ```python
   def update_plot(self):
       self._needs_redraw = True
       self.update()  # Schedule repaint, don't force immediate
   ```

### 8.4 Error Handling

1. **Emit errors as signals for QML handling**
   ```python
   errorOccurred = Signal(str, str)  # title, message

   try:
       result = risky_operation()
   except Exception as e:
       self.errorOccurred.emit("Operation Failed", str(e))
   ```

2. **Wrap callbacks in try/except**
   ```python
   def _on_task_completed(self, name, result):
       try:
           callback = self._callbacks.get(name)
           if callback:
               callback(result)
       except Exception as e:
           logger.error(f"Callback error: {e}")
           self.errorOccurred.emit("Internal Error", str(e))
   ```

---

## Appendix: Signal/Slot Quick Reference

### Python Signal Types to QML

| Python Type | QML Type | Example |
|-------------|----------|---------|
| `str` | `string` | `Signal(str)` |
| `int` | `int` | `Signal(int)` |
| `float` | `real` | `Signal(float)` |
| `bool` | `bool` | `Signal(bool)` |
| `list` | `var` or `QVariantList` | `Signal('QVariantList')` |
| `dict` | `var` or `QVariantMap` | `Signal('QVariantMap')` |
| `QObject` | `QtObject` | `Signal(QObject)` |

### Common Signal Patterns

```python
# Progress reporting
progressChanged = Signal(int, int, str)  # current, total, message

# Error notification
errorOccurred = Signal(str, str)  # title, message

# State change
stateChanged = Signal(str)  # new state name

# Data updates
dataLoaded = Signal(str)  # item identifier
dataModified = Signal()   # no args, just notification

# Request pattern (Python to QML)
createWindowRequested = Signal(str, 'QVariantMap')  # type, config
```

---

*TRANS-QML Multithreading and Signals/Slots Documentation*
*Last updated: December 2025*
