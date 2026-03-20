# Module 8: Application Architecture

## Backend/Frontend Separation, State Management, and System Design

This final module covers the high-level architecture patterns that make TRANS-QML maintainable and extensible. You'll learn how to separate concerns between Python and QML, manage application state, implement project save/load, and design plugin systems.

---

## Learning Objectives

By the end of this module, you will be able to:
- Design clean backend/frontend separation
- Implement centralized state management
- Build project save/load systems
- Create workflow and plugin architectures
- Write effective tests for Qt/QML applications

---

## 8.1 The Backend/Frontend Split

### Why Separate?

Scientific applications have two distinct concerns:
- **Frontend (QML)**: User interaction, layout, animations, visual feedback
- **Backend (Python)**: Data processing, file I/O, numerical computation

Keeping these separate provides:
- **Testability** - Python code can be tested without UI
- **Maintainability** - Changes to one don't break the other
- **Performance** - Heavy computation in Python, smooth UI in QML
- **Reusability** - Backend can serve CLI, web, or other frontends

### The Bridge Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                        QML Frontend                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Button  │  │ Canvas  │  │ TableView│ │ Dialogs │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       │            │            │            │              │
│       ▼            ▼            ▼            ▼              │
│  ╔═══════════════════════════════════════════════════╗     │
│  ║          Signals & Slots (the bridge)             ║     │
│  ╚═══════════════════════════════════════════════════╝     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Python Backend                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    AppBackend (QObject)                 │ │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐          │ │
│  │  │ DataLoader│  │WorkerMgr │  │ProjectMgr │          │ │
│  │  └───────────┘  └───────────┘  └───────────┘          │ │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐          │ │
│  │  │WorkflowMgr│  │ PrefsMgr  │  │ToolImpl   │          │ │
│  │  └───────────┘  └───────────┘  └───────────┘          │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### The AppBackend Class

```python
# src/backend/app_backend.py
class AppBackend(ToolImplementations, QObject):
    """
    Main application backend that bridges QML UI to Python logic.
    Uses multiple inheritance to include tool implementations.
    """

    # Signals for QML communication
    statusChanged = Signal(str)
    progressChanged = Signal(int, int, str)  # current, total, message
    dataLoaded = Signal(str)
    errorOccurred = Signal(str, str)  # error_type, message
    toolCompleted = Signal(str, str)  # tool_name, output_path
    projectLoaded = Signal(str)
    projectSaved = Signal(str)
    isBusyChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Application state
        self._status = "Ready"
        self._project_path = None
        self._project_ready = False

        # Data storage
        self._datasets = {}
        self._active_dataset = None

        # Sub-managers (composition over inheritance)
        self.worker_manager = WorkerManager(max_concurrent=3)
        self.project_manager = ProjectManager()
        self.workflow_manager = WorkflowManager(self)
        self._preferences_manager = PreferencesManager(self)

        # Connect worker signals
        self.worker_manager.worker_completed.connect(self._on_worker_completed)
        self.worker_manager.worker_failed.connect(self._on_worker_failed)
```

### Exposing Backend to QML

```python
# main.py
def main():
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()

    # Create backend
    backend = AppBackend()

    # Expose to QML as context property
    engine.rootContext().setContextProperty("backend", backend)

    # Also expose the workflow manager
    engine.rootContext().setContextProperty("workflowManager", backend.workflow_manager)

    engine.load("src/qml/main/Main.qml")
```

### Using Backend in QML

```qml
// Main.qml
ApplicationWindow {
    id: mainWindow

    // Status bar shows backend status
    footer: StatusBar {
        Label {
            text: backend.status
        }

        ProgressBar {
            value: backend.progress / 100
            visible: backend.isBusy
        }
    }

    // Connect to backend signals
    Connections {
        target: backend

        function onDataLoaded(datasetName) {
            console.log("Dataset loaded:", datasetName)
            projectBrowser.refresh()
        }

        function onErrorOccurred(errorType, message) {
            errorDialog.show(errorType, message)
        }

        function onToolCompleted(toolName, outputPath) {
            statusBar.showMessage(`${toolName} completed: ${outputPath}`)
        }
    }

    // Call backend methods
    Button {
        text: "Load Data"
        onClicked: backend.openFile()
    }
}
```

---

## 8.2 State Management

### Centralized State

TRANS-QML uses a centralized state pattern where:
- **Backend holds the truth** - All data lives in Python
- **Properties expose state** - QML binds to backend properties
- **Signals notify changes** - Backend emits when state changes
- **Slots accept commands** - QML calls slots to modify state

```python
class AppBackend(QObject):
    # State change signals
    activeDatasetChanged = Signal(str)
    projectReadyChanged = Signal(bool)

    def __init__(self):
        self._active_dataset = None
        self._project_ready = False

    # Property pattern for state
    @Property(str, notify=activeDatasetChanged)
    def activeDataset(self):
        return self._active_dataset or ""

    @activeDataset.setter
    def activeDataset(self, name):
        if name != self._active_dataset:
            self._active_dataset = name
            self.activeDatasetChanged.emit(name)

    @Property(bool, notify=projectReadyChanged)
    def projectReady(self):
        return self._project_ready
```

### Dataset Registry

```python
class AppBackend(QObject):
    def __init__(self):
        self._datasets: Dict[str, SpectralData] = {}

    @Slot(result='QVariantList')
    def getDatasetNames(self):
        """Get list of loaded dataset names"""
        return list(self._datasets.keys())

    @Slot(str, result='QVariantMap')
    def getDatasetInfo(self, name):
        """Get dataset metadata for QML"""
        if name not in self._datasets:
            return {}

        data = self._datasets[name]
        return {
            'name': name,
            'type': data.data_type,
            'numSpectra': data.num_spectra,
            'numPoints': data.num_points,
            'xLabel': data.x_label,
            'yLabel': data.y_label,
            'metadata': data.metadata
        }

    @Slot(str, result='QVariantList')
    def getSpectrumData(self, name):
        """Get spectrum data as [x_list, y_list]"""
        if name not in self._datasets:
            return [[], []]

        data = self._datasets[name]
        return [
            data.x_data.tolist(),
            data.y_data.tolist()
        ]
```

---

## 8.3 Project Management

### Project Structure

TRANS-QML projects are directories with a defined structure:

```
MyProject/
├── project.json          # Project metadata
├── data/                 # Raw imported data
│   ├── STS_sample1.npy
│   └── SNOM_map.npy
├── outputs/              # Tool outputs (lazy created)
│   ├── curves/
│   ├── derivatives/
│   ├── fft/
│   ├── maps/
│   └── workflows/
├── workflows/            # Saved workflow definitions
│   └── preprocessing.json
└── preferences.json      # Project-specific settings
```

### Project Manager

```python
class ProjectManager:
    """Handles project creation, saving, and loading"""

    def __init__(self):
        self.project_path = None
        self.project_data = {}

    def create_project(self, path: Path, name: str) -> bool:
        """Create a new project at the given path"""
        project_dir = path / name
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create project file
        project_data = {
            'name': name,
            'version': '1.0',
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat(),
            'datasets': [],
            'outputs': [],
            'workflows': []
        }

        project_file = project_dir / 'project.json'
        with open(project_file, 'w') as f:
            json.dump(project_data, f, indent=2)

        self.project_path = project_dir
        self.project_data = project_data
        return True

    def load_project(self, path: Path) -> bool:
        """Load an existing project"""
        project_file = path / 'project.json'
        if not project_file.exists():
            raise FileNotFoundError(f"Not a valid project: {path}")

        with open(project_file, 'r') as f:
            self.project_data = json.load(f)

        self.project_path = path
        return True

    def save_project(self) -> bool:
        """Save current project state"""
        if not self.project_path:
            return False

        self.project_data['modified'] = datetime.now().isoformat()

        project_file = self.project_path / 'project.json'
        with open(project_file, 'w') as f:
            json.dump(self.project_data, f, indent=2)

        return True
```

### Recent Projects

```python
def _load_recent_projects(self):
    """Load recent projects from settings"""
    settings_path = Path.home() / ".trans_qml" / "recent_projects.json"

    if settings_path.exists():
        with open(settings_path, 'r') as f:
            self._recent_projects = json.load(f)
    else:
        self._recent_projects = []

def _add_to_recent_projects(self, project_path: str, project_name: str):
    """Add a project to recent list"""
    # Remove if already exists (to move to front)
    self._recent_projects = [
        p for p in self._recent_projects
        if p.get('path') != project_path
    ]

    # Add to front
    self._recent_projects.insert(0, {
        'path': project_path,
        'name': project_name,
        'lastOpened': datetime.now().isoformat()
    })

    # Keep only last 10
    self._recent_projects = self._recent_projects[:10]
    self._save_recent_projects()

@Slot(result='QVariantList')
def getRecentProjects(self):
    """Get recent projects for QML"""
    return self._recent_projects
```

---

## 8.4 Preferences System

### User Preferences

```python
class PreferencesManager(QObject):
    """Manages user preferences with auto-save"""

    preferencesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prefs = {}
        self._prefs_path = Path.home() / ".trans_qml" / "preferences.json"
        self._load()

    def _load(self):
        """Load preferences from file"""
        if self._prefs_path.exists():
            with open(self._prefs_path, 'r') as f:
                self._prefs = json.load(f)

    def _save(self):
        """Save preferences to file"""
        self._prefs_path.parent.mkdir(exist_ok=True)
        with open(self._prefs_path, 'w') as f:
            json.dump(self._prefs, f, indent=2)

    @Slot(str, result='QVariant')
    def get(self, key: str, default=None):
        """Get a preference value"""
        return self._prefs.get(key, default)

    @Slot(str, 'QVariant')
    def set(self, key: str, value):
        """Set a preference value"""
        self._prefs[key] = value
        self._save()
        self.preferencesChanged.emit()

    @Slot(result='QVariantMap')
    def getAll(self):
        """Get all preferences"""
        return self._prefs.copy()
```

### Defaults and Validation

```python
# Default preferences
DEFAULT_PREFS = {
    'theme': 'dark',
    'fontSizeSmall': 10,
    'fontSizeMedium': 12,
    'fontSizeLarge': 14,
    'autoSave': True,
    'autoSaveInterval': 300,  # seconds
    'defaultColormap': 'viridis',
    'recentFilesLimit': 20,
    'confirmBeforeClose': True
}

def get(self, key: str, default=None):
    """Get preference with fallback to defaults"""
    if key in self._prefs:
        return self._prefs[key]
    if key in DEFAULT_PREFS:
        return DEFAULT_PREFS[key]
    return default
```

---

## 8.5 Workflow System

### Workflow Definition

TRANS-QML uses a node-based workflow system for reproducible processing:

```python
class WorkflowManager(QObject):
    """Manages workflow creation, execution, and persistence"""

    workflowCreated = Signal(str)  # workflow_id
    workflowExecutionStarted = Signal(str)
    workflowExecutionCompleted = Signal(str)
    nodeExecuted = Signal(str, str)  # workflow_id, node_id

    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self._workflows = {}  # workflow_id -> workflow_data
        self._workflow_counter = 0

    @Slot(str, result=str)
    def createWorkflow(self, name: str) -> str:
        """Create a new workflow"""
        workflow_id = f"wf_{self._workflow_counter}"
        self._workflow_counter += 1

        self._workflows[workflow_id] = {
            'id': workflow_id,
            'name': name,
            'nodes': [],
            'connections': [],
            'created': datetime.now().isoformat()
        }

        self.workflowCreated.emit(workflow_id)
        return workflow_id
```

### Workflow Nodes

```python
@Slot(str, str, float, float, result=str)
def addNode(self, workflow_id: str, node_type: str, x: float, y: float) -> str:
    """Add a node to a workflow"""
    if workflow_id not in self._workflows:
        return ""

    node_id = f"node_{len(self._workflows[workflow_id]['nodes'])}"

    node = {
        'id': node_id,
        'type': node_type,
        'x': x,
        'y': y,
        'parameters': self._get_default_parameters(node_type),
        'inputs': [],
        'outputs': []
    }

    self._workflows[workflow_id]['nodes'].append(node)
    return node_id

def _get_default_parameters(self, node_type: str) -> Dict:
    """Get default parameters for a node type"""
    defaults = {
        'smooth': {'method': 'savgol', 'window': 11, 'poly_order': 3},
        'derivative': {'order': 1},
        'fft': {'window': 'hanning'},
        'integrate': {'method': 'trapz'},
        'normalize': {'method': 'minmax'}
    }
    return defaults.get(node_type, {})
```

### Workflow Execution

```python
@Slot(str, str)
def executeWorkflow(self, workflow_id: str, input_dataset: str):
    """Execute a workflow on a dataset"""
    if workflow_id not in self._workflows:
        return

    workflow = self._workflows[workflow_id]
    self.workflowExecutionStarted.emit(workflow_id)

    # Get input data
    data = self.backend._datasets.get(input_dataset)
    if not data:
        return

    # Topological sort nodes by dependencies
    sorted_nodes = self._topological_sort(workflow)

    # Execute nodes in order
    results = {}
    for node in sorted_nodes:
        node_id = node['id']

        # Get inputs (from previous nodes or original data)
        inputs = self._gather_inputs(node, results, data)

        # Execute node
        result = self._execute_node(node, inputs)
        results[node_id] = result

        self.nodeExecuted.emit(workflow_id, node_id)

    self.workflowExecutionCompleted.emit(workflow_id)
    return results
```

---

## 8.6 Tool Implementation Pattern

### Base Tool Pattern

```python
# src/backend/tool_implementations.py
class ToolImplementations:
    """Mixin class providing all tool implementations"""

    @Slot(str, str, 'QVariantMap', result='QVariantMap')
    def runTool(self, tool_name: str, input_dataset: str, parameters: Dict) -> Dict:
        """
        Universal tool execution interface.

        Parameters:
            tool_name: Name of tool to run
            input_dataset: Name of input dataset
            parameters: Tool-specific parameters

        Returns:
            Dict with 'success', 'output_path', 'result_data', etc.
        """
        # Get the tool method
        method_name = f"_run_{tool_name.lower().replace(' ', '_')}"
        method = getattr(self, method_name, None)

        if not method:
            return {'success': False, 'error': f'Unknown tool: {tool_name}'}

        # Get input data
        if input_dataset not in self._datasets:
            return {'success': False, 'error': f'Dataset not found: {input_dataset}'}

        data = self._datasets[input_dataset]

        try:
            # Execute the tool
            result = method(data, parameters)

            # Register output
            if result.get('output_path'):
                self._register_output(tool_name, result['output_path'])

            return result

        except Exception as e:
            logger.exception(f"Tool {tool_name} failed")
            return {'success': False, 'error': str(e)}
```

### Example Tool Implementation

```python
def _run_derivative(self, data: SpectralData, params: Dict) -> Dict:
    """Calculate derivative of spectral data"""
    order = params.get('order', 1)
    smoothing = params.get('smoothing', 0)

    x = data.x_data
    y = data.y_data

    # Apply smoothing before derivative if requested
    if smoothing > 0:
        from scipy.ndimage import gaussian_filter1d
        y = gaussian_filter1d(y, sigma=smoothing)

    # Calculate derivative
    result = np.gradient(y, x)
    if order == 2:
        result = np.gradient(result, x)

    # Create output dataset
    output_name = f"{data.name}_d{order}"
    output_data = SpectralData(
        x_data=x,
        y_data=result,
        name=output_name,
        x_label=data.x_label,
        y_label=f"d{order}({data.y_label})/d({data.x_label}){order}"
    )

    # Save and register
    output_path = self._ensure_output_dir('derivatives')
    output_file = output_path / f"{output_name}.csv"
    output_data.save_csv(output_file)

    # Add to datasets
    self._datasets[output_name] = output_data
    self.dataLoaded.emit(output_name)

    return {
        'success': True,
        'output_path': str(output_file),
        'output_dataset': output_name,
        'result_data': {'x': x.tolist(), 'y': result.tolist()}
    }
```

---

## 8.7 Testing Strategies

### Unit Testing Backend

```python
# tests/test_backend/test_app_backend.py
import pytest
import numpy as np
from src.backend.app_backend import AppBackend
from src.models.spectral_data import SpectralData


@pytest.fixture
def backend():
    """Create a fresh backend for each test"""
    backend = AppBackend()
    yield backend
    # Cleanup


@pytest.fixture
def sample_data():
    """Create sample spectral data"""
    x = np.linspace(0, 100, 500)
    y = np.sin(x * 0.1) + np.random.normal(0, 0.1, 500)
    return SpectralData(x_data=x, y_data=y, name="test_data")


class TestDerivativeTool:
    def test_first_derivative(self, backend, sample_data):
        backend._datasets["test"] = sample_data

        result = backend.runTool("Derivative", "test", {"order": 1})

        assert result["success"] is True
        assert "test_d1" in backend._datasets

    def test_second_derivative(self, backend, sample_data):
        backend._datasets["test"] = sample_data

        result = backend.runTool("Derivative", "test", {"order": 2})

        assert result["success"] is True
        assert "test_d2" in backend._datasets
```

### Testing Signals

```python
from PySide6.QtCore import QSignalSpy

class TestBackendSignals:
    def test_data_loaded_signal(self, backend, sample_data, qtbot):
        # Create signal spy
        spy = QSignalSpy(backend.dataLoaded)

        # Add data
        backend._datasets["test"] = sample_data
        backend.dataLoaded.emit("test")

        # Verify signal was emitted
        assert len(spy) == 1
        assert spy[0][0] == "test"

    def test_progress_signal(self, backend, qtbot):
        spy = QSignalSpy(backend.progressChanged)

        backend.progressChanged.emit(50, 100, "Processing...")

        assert len(spy) == 1
        assert spy[0] == [50, 100, "Processing..."]
```

### Integration Testing with QML

```python
# tests/test_integration/test_qml_backend.py
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem

def test_backend_accessible_from_qml(app, backend):
    """Test that backend is accessible from QML"""
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)

    # Load a test QML file that uses the backend
    engine.loadData(b'''
        import QtQuick 2.15
        Item {
            id: root
            property string status: backend.status
        }
    ''')

    root = engine.rootObjects()[0]
    assert root.property("status") == "Ready"
```

---

## 8.8 Error Handling

### Backend Error Propagation

```python
class AppBackend(QObject):
    errorOccurred = Signal(str, str)  # error_type, message

    def _handle_error(self, error_type: str, message: str, exc: Exception = None):
        """Centralized error handling"""
        if exc:
            logger.exception(f"{error_type}: {message}")
        else:
            logger.error(f"{error_type}: {message}")

        self.errorOccurred.emit(error_type, message)
        self.statusChanged.emit("Error")

    @Slot(str)
    def loadFile(self, path: str):
        try:
            # ... loading logic
            pass
        except FileNotFoundError as e:
            self._handle_error("FileError", f"File not found: {path}", e)
        except PermissionError as e:
            self._handle_error("PermissionError", f"Cannot read file: {path}", e)
        except Exception as e:
            self._handle_error("LoadError", f"Failed to load: {str(e)}", e)
```

### QML Error Display

```qml
// ErrorDialog.qml
Dialog {
    id: errorDialog
    title: "Error"
    modal: true
    standardButtons: Dialog.Ok

    property string errorType: ""
    property string errorMessage: ""

    contentItem: Column {
        spacing: 10

        Text {
            text: errorType
            font.bold: true
            color: "#ff6b6b"
        }

        Text {
            text: errorMessage
            wrapMode: Text.Wrap
            width: 400
        }
    }

    function show(type, message) {
        errorType = type
        errorMessage = message
        open()
    }
}

// In Main.qml
Connections {
    target: backend
    function onErrorOccurred(errorType, message) {
        errorDialog.show(errorType, message)
    }
}
```

---

## 8.9 Performance Considerations

### Lazy Loading

```python
def _ensure_output_dir(self, subdir: str) -> Path:
    """
    Lazy directory creation - only create when saving.
    Avoids creating empty project structure prematurely.
    """
    if self._output_base_dir is None:
        raise ValueError("No project set")

    output_path = self._output_base_dir / subdir
    if not output_path.exists():
        output_path.mkdir(parents=True, exist_ok=True)

    return output_path
```

### Data Caching

```python
class AppBackend(QObject):
    def __init__(self):
        # LRU cache for computed results
        self._result_cache = {}
        self._max_cache_size = 50

    def _get_cached(self, key: str):
        """Get cached result if available"""
        return self._result_cache.get(key)

    def _set_cached(self, key: str, value):
        """Cache a result"""
        if len(self._result_cache) >= self._max_cache_size:
            # Remove oldest entry
            oldest = next(iter(self._result_cache))
            del self._result_cache[oldest]

        self._result_cache[key] = value
```

### Batch Operations

```python
@Slot('QVariantList', str, 'QVariantMap')
def runToolBatch(self, dataset_names: List[str], tool_name: str, params: Dict):
    """Run a tool on multiple datasets efficiently"""

    # Suppress individual signals during batch
    self._batch_mode = True

    results = []
    for i, name in enumerate(dataset_names):
        self.progressChanged.emit(i, len(dataset_names), f"Processing {name}")
        result = self.runTool(tool_name, name, params)
        results.append(result)

    self._batch_mode = False

    # Single notification at end
    self.batchCompleted.emit(tool_name, len(results))
    return results
```

---

## 8.10 Summary

### Architecture Principles

1. **Separation of Concerns** - Backend handles data, frontend handles display
2. **Centralized State** - Single source of truth in backend
3. **Signal-Based Communication** - Loose coupling between components
4. **Composition Over Inheritance** - Sub-managers instead of giant classes
5. **Lazy Operations** - Create resources only when needed

### File Structure Recap

```
TRANS/
├── src/
│   ├── main.py                 # Entry point
│   ├── backend/
│   │   ├── app_backend.py      # Main backend QObject
│   │   ├── worker.py           # Multithreading
│   │   ├── workflow_manager.py # Workflow execution
│   │   ├── project_manager.py  # Project save/load
│   │   └── preferences_manager.py
│   ├── models/
│   │   ├── spectral_data.py    # Data structures
│   │   └── table_data_model.py # Qt model
│   ├── widgets/
│   │   └── qml_*.py            # Custom QML items
│   └── qml/
│       ├── main/Main.qml       # Main window
│       ├── components/         # Reusable components
│       ├── tools/              # Tool UIs
│       └── workflow/           # Workflow editor
└── tests/
    ├── test_backend/
    ├── test_models/
    └── test_integration/
```

### Key Takeaways

| Aspect | Pattern |
|--------|---------|
| Backend-Frontend | QObject with signals/slots |
| State | Properties with notify signals |
| Projects | JSON metadata + lazy directories |
| Preferences | Auto-saving JSON file |
| Workflows | Node-based with topological execution |
| Tools | Method dispatch with standardized return |
| Testing | pytest + QSignalSpy |
| Errors | Centralized handler with signal propagation |

---

## Course Completion

Congratulations! You've completed the TRANS-QML course. You now understand:

- **Module 1**: PySide6/QML fundamentals and project structure
- **Module 2**: Python-QML type registration and integration
- **Module 3**: Signal/slot mechanism and reactive properties
- **Module 4**: Thread-safe multithreading patterns
- **Module 5**: Custom QML components with matplotlib
- **Module 6**: Scientific data models and formula engines
- **Module 7**: Advanced UI patterns (docking, windows, themes)
- **Module 8**: Application architecture and best practices

### Next Steps

1. **Build your own application** using these patterns
2. **Contribute to TRANS-QML** - issues, features, documentation
3. **Explore Qt Quick 3D** for 3D visualization
4. **Learn Qt for WebAssembly** for web deployment

### Resources

- [Qt Documentation](https://doc.qt.io/)
- [PySide6 Reference](https://doc.qt.io/qtforpython/)
- [TRANS-QML Repository](https://github.com/your-repo/trans-qml)
- [Qt Forum](https://forum.qt.io/)

---

*Module 8 of 8 | TRANS-QML Course*
*Course Version 1.0 | Based on TRANS-QML Implementation*
