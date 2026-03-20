# Module 1: Introduction and Project Setup

## Learning Objectives

By the end of this module, you will:
- Understand the Qt/QML ecosystem and why it's ideal for scientific applications
- Know the difference between PySide6 and PyQt6
- Set up a proper project structure for large applications
- Create your first QML application with a Python backend
- Understand the application lifecycle

---

## 1.1 Why Qt and QML for Scientific Applications?

### The Challenge of Scientific Software UI

Scientific applications have unique requirements:
- **Data-intensive visualizations**: Plots, heatmaps, 3D surfaces
- **Long-running computations**: Must not freeze the UI
- **Cross-platform**: Windows, macOS, Linux
- **Professional appearance**: Publication-quality outputs
- **Flexibility**: Researchers need customizable interfaces

### Traditional Approaches and Their Limitations

| Approach | Pros | Cons |
|----------|------|------|
| Tkinter | Built-in, simple | Dated look, limited widgets |
| PyQt Widgets | Mature, many widgets | C++ patterns, complex styling |
| Web (Electron) | Modern UI, flexible | Heavy, memory-intensive |
| Matplotlib GUI | Familiar to scientists | Limited interactivity |

### Why QML + Python?

**QML (Qt Modeling Language)** provides:
- Declarative UI definition (like HTML/CSS but better)
- Smooth animations and transitions
- Modern, customizable appearance
- Responsive layouts
- Hardware-accelerated rendering

**Python backend** provides:
- NumPy/SciPy for numerical computation
- Pandas for data manipulation
- Matplotlib for publication plots
- Easy file I/O and data parsing

**Together**, they give you the best of both worlds: beautiful, responsive UIs with powerful scientific computing.

---

## 1.2 The Qt Ecosystem

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Qt Framework                            │
├─────────────────┬─────────────────┬─────────────────────────┤
│   Qt Widgets    │    Qt Quick     │      Qt Core            │
│   (C++ classes) │    (QML + JS)   │   (Signals, Objects)    │
├─────────────────┴─────────────────┴─────────────────────────┤
│                    Python Bindings                           │
│              PySide6 (official) / PyQt6                      │
└─────────────────────────────────────────────────────────────┘
```

### Qt Widgets vs Qt Quick (QML)

**Qt Widgets** (the older approach):
```python
# Python-only, imperative style
button = QPushButton("Click Me")
button.clicked.connect(self.on_click)
layout.addWidget(button)
```

**Qt Quick/QML** (the modern approach):
```qml
// Declarative style, separate from logic
Button {
    text: "Click Me"
    onClicked: backend.handleClick()
}
```

For scientific applications, we use **both**:
- QML for the UI structure and interactions
- Python (via QQuickPaintedItem) for custom visualizations

### PySide6 vs PyQt6

| Feature | PySide6 | PyQt6 |
|---------|---------|-------|
| License | LGPL (commercial-friendly) | GPL (or commercial) |
| Maintainer | Qt Company (official) | Riverbank Computing |
| API | Nearly identical | Nearly identical |
| Documentation | Improving | More extensive |

**We use PySide6** because:
- It's the official Python binding from Qt
- LGPL license allows commercial use
- Better long-term support

---

## 1.3 Project Structure

A well-organized project is crucial for maintainability. Here's the structure we use:

```
my_scientific_app/
├── src/
│   ├── __init__.py
│   ├── main.py                    # Entry point
│   │
│   ├── backend/                   # Python business logic
│   │   ├── __init__.py
│   │   ├── app_backend.py         # Main QObject for QML
│   │   ├── worker.py              # Multithreading
│   │   └── data_processor.py      # Domain-specific logic
│   │
│   ├── models/                    # Data structures
│   │   ├── __init__.py
│   │   ├── data_model.py          # QAbstractTableModel subclasses
│   │   └── domain_objects.py      # Scientific data classes
│   │
│   ├── widgets/                   # Custom QML items (Python)
│   │   ├── __init__.py
│   │   ├── plot_canvas.py         # Matplotlib integration
│   │   └── custom_widget.py       # Other custom widgets
│   │
│   ├── data_loaders/              # File format handlers
│   │   ├── __init__.py
│   │   └── file_loader.py
│   │
│   └── qml/                       # QML files
│       ├── main/
│       │   └── Main.qml           # Main window
│       ├── components/            # Reusable components
│       │   ├── qmldir             # Component registration
│       │   ├── CustomButton.qml
│       │   └── DataTable.qml
│       └── dialogs/
│           └── SettingsDialog.qml
│
├── tests/                         # Test suite
│   ├── test_backend/
│   ├── test_models/
│   └── test_integration/
│
├── resources/                     # Images, icons, etc.
│   └── icons/
│
├── docs/                          # Documentation
│
├── requirements.txt
├── setup.py
└── README.md
```

### Key Principles

1. **Separation of Concerns**
   - `backend/`: All Python business logic
   - `qml/`: All UI definition
   - `models/`: Data structures shared between both

2. **The `qmldir` File**
   - Registers QML components for import
   - Located in each component directory

3. **No UI Logic in Backend**
   - Backend emits signals
   - QML decides how to display

---

## 1.4 Application Entry Point

Let's examine a minimal but complete entry point:

### File: `src/main.py`

```python
#!/usr/bin/env python3
"""
Application entry point for a Scientific QML Application.
"""

import sys
import os
from pathlib import Path

# PySide6 imports
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtCore import QUrl

# Import our backend and custom widgets
from src.backend.app_backend import AppBackend
from src.widgets.plot_canvas import PlotCanvas


def setup_qml_imports(engine: QQmlApplicationEngine):
    """Add QML import paths for our components."""

    # Get the directory containing our QML files
    qml_dir = Path(__file__).parent / "qml"

    # Add import paths
    engine.addImportPath(str(qml_dir))
    engine.addImportPath(str(qml_dir / "components"))


def register_types():
    """Register Python types for use in QML."""

    # Register custom widgets
    # qmlRegisterType(PythonClass, "ModuleName", major, minor, "QMLName")
    qmlRegisterType(PlotCanvas, "MyApp", 1, 0, "PlotCanvas")


def main():
    """Main entry point."""

    # Create the application
    app = QApplication(sys.argv)
    app.setApplicationName("My Scientific App")
    app.setOrganizationName("MyOrg")

    # Register custom types BEFORE creating the engine
    register_types()

    # Create the QML engine
    engine = QQmlApplicationEngine()

    # Setup import paths
    setup_qml_imports(engine)

    # Create the backend and expose to QML
    backend = AppBackend()
    engine.rootContext().setContextProperty("backend", backend)

    # Load the main QML file
    qml_file = Path(__file__).parent / "qml" / "main" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    # Check if QML loaded successfully
    if not engine.rootObjects():
        print("Error: Failed to load QML")
        sys.exit(1)

    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

### Understanding the Entry Point

#### Step 1: Create QApplication
```python
app = QApplication(sys.argv)
```
- Required for any Qt application
- Handles command-line arguments
- Manages the event loop

#### Step 2: Register Types
```python
qmlRegisterType(PlotCanvas, "MyApp", 1, 0, "PlotCanvas")
```
- Makes Python classes available in QML
- Must be done BEFORE engine creation
- Format: `(Class, "ImportModule", majorVersion, minorVersion, "QMLTypeName")`

#### Step 3: Create QML Engine
```python
engine = QQmlApplicationEngine()
```
- Loads and manages QML components
- Handles property bindings
- Manages the QML object tree

#### Step 4: Expose Backend
```python
engine.rootContext().setContextProperty("backend", backend)
```
- Makes Python object accessible in QML as `backend`
- Can call methods, read properties, connect to signals

#### Step 5: Load QML
```python
engine.load(QUrl.fromLocalFile(str(qml_file)))
```
- Loads and instantiates the main QML file
- Creates the window and all child components

---

## 1.5 Your First QML File

### File: `src/qml/main/Main.qml`

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: mainWindow

    // Window properties
    visible: true
    width: 1200
    height: 800
    title: "My Scientific Application"

    // Custom properties
    property color accentColor: "#5BCEFA"
    property color bgColor: "#1a1a2e"

    // Background
    color: bgColor

    // Menu bar
    menuBar: MenuBar {
        Menu {
            title: "&File"

            Action {
                text: "&Open..."
                shortcut: "Ctrl+O"
                onTriggered: backend.openFile()
            }

            Action {
                text: "&Save"
                shortcut: "Ctrl+S"
                onTriggered: backend.saveFile()
            }

            MenuSeparator {}

            Action {
                text: "&Quit"
                shortcut: "Ctrl+Q"
                onTriggered: Qt.quit()
            }
        }

        Menu {
            title: "&Help"
            Action {
                text: "&About"
                onTriggered: aboutDialog.open()
            }
        }
    }

    // Main content area
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        // Header
        Label {
            text: "Welcome to My Scientific App"
            font.pixelSize: 24
            font.bold: true
            color: accentColor
            Layout.alignment: Qt.AlignHCenter
        }

        // Status display (bound to backend property)
        Label {
            text: "Status: " + backend.status
            color: "white"
            Layout.alignment: Qt.AlignHCenter
        }

        // Main content placeholder
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Qt.darker(bgColor, 1.2)
            radius: 8

            Label {
                anchors.centerIn: parent
                text: "Content Area"
                color: "gray"
            }
        }

        // Button row
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 20

            Button {
                text: "Process Data"
                onClicked: backend.processData()
            }

            Button {
                text: "Clear"
                onClicked: backend.clearData()
            }
        }
    }

    // Connect to backend signals
    Connections {
        target: backend

        function onDataProcessed(result) {
            console.log("Data processed:", result)
            resultDialog.resultText = result
            resultDialog.open()
        }

        function onErrorOccurred(title, message) {
            errorDialog.title = title
            errorDialog.text = message
            errorDialog.open()
        }
    }

    // Dialogs
    Dialog {
        id: aboutDialog
        title: "About"
        modal: true
        anchors.centerIn: parent

        Label {
            text: "My Scientific Application v1.0\n\nBuilt with PySide6 and QML"
        }

        standardButtons: Dialog.Ok
    }

    Dialog {
        id: resultDialog
        title: "Result"
        modal: true
        anchors.centerIn: parent

        property string resultText: ""

        Label {
            text: resultDialog.resultText
        }

        standardButtons: Dialog.Ok
    }

    Dialog {
        id: errorDialog
        title: "Error"
        modal: true
        anchors.centerIn: parent

        property alias text: errorLabel.text

        Label {
            id: errorLabel
        }

        standardButtons: Dialog.Ok
    }
}
```

### QML Syntax Breakdown

#### 1. Imports
```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
```
- `QtQuick`: Core QML types (Rectangle, Item, etc.)
- `QtQuick.Controls`: UI controls (Button, TextField, etc.)
- `QtQuick.Layouts`: Layout managers (RowLayout, ColumnLayout)

#### 2. Properties
```qml
property color accentColor: "#5BCEFA"
property string myString: "hello"
property int counter: 0
property bool isEnabled: true
```
- Custom properties with type declaration
- Automatically create change signals

#### 3. Property Bindings
```qml
text: "Status: " + backend.status
```
- Reactive: Updates automatically when `backend.status` changes
- This is the magic of QML!

#### 4. Signal Handlers
```qml
onClicked: backend.processData()
```
- Format: `on<SignalName>` in camelCase
- Can be inline code or function call

#### 5. Connections Component
```qml
Connections {
    target: backend
    function onDataProcessed(result) { ... }
}
```
- Connect to signals from external objects
- Handler format: `function on<SignalName>(args)`

---

## 1.6 Minimal Backend

### File: `src/backend/app_backend.py`

```python
"""
Minimal backend demonstrating QML integration.
"""

from PySide6.QtCore import QObject, Signal, Slot, Property
import logging

logger = logging.getLogger(__name__)


class AppBackend(QObject):
    """
    Main backend class exposed to QML.

    This class:
    - Exposes properties that QML can bind to
    - Provides slots that QML can call
    - Emits signals that QML can handle
    """

    # ===== SIGNALS =====
    # Signals are class attributes, defined before __init__

    statusChanged = Signal(str)
    dataProcessed = Signal(str)  # result string
    errorOccurred = Signal(str, str)  # title, message

    def __init__(self, parent=None):
        super().__init__(parent)

        # Private storage for properties
        self._status = "Ready"
        self._data = None

        logger.info("AppBackend initialized")

    # ===== PROPERTIES =====
    # Properties expose Python values to QML with change notification

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        """Current status message."""
        return self._status

    @status.setter
    def status(self, value: str):
        if self._status != value:
            self._status = value
            self.statusChanged.emit(value)
            logger.debug(f"Status changed to: {value}")

    # ===== SLOTS =====
    # Slots are methods that QML can call

    @Slot()
    def openFile(self):
        """Open a file (placeholder)."""
        logger.info("openFile called")
        self.status = "Opening file..."
        # In real app: show file dialog, load data
        self.status = "File opened"

    @Slot()
    def saveFile(self):
        """Save current data (placeholder)."""
        logger.info("saveFile called")
        self.status = "Saving..."
        # In real app: save data
        self.status = "Saved"

    @Slot()
    def processData(self):
        """Process the current data."""
        logger.info("processData called")
        self.status = "Processing..."

        try:
            # Simulate processing
            result = "Processed 100 data points successfully!"
            self.status = "Done"

            # Emit result signal
            self.dataProcessed.emit(result)

        except Exception as e:
            logger.error(f"Processing error: {e}")
            self.status = "Error"
            self.errorOccurred.emit("Processing Error", str(e))

    @Slot()
    def clearData(self):
        """Clear all data."""
        logger.info("clearData called")
        self._data = None
        self.status = "Cleared"

    @Slot(str, result=bool)
    def loadData(self, filepath: str) -> bool:
        """
        Load data from file.

        This demonstrates:
        - Slot with parameter
        - Slot with return value
        """
        logger.info(f"loadData called with: {filepath}")

        try:
            # In real app: load and parse file
            self._data = {"filepath": filepath, "loaded": True}
            self.status = f"Loaded: {filepath}"
            return True

        except Exception as e:
            self.errorOccurred.emit("Load Error", str(e))
            return False
```

### Key Patterns

#### Signal Definition
```python
# Class attribute, before __init__
statusChanged = Signal(str)  # One string parameter
errorOccurred = Signal(str, str)  # Two string parameters
dataLoaded = Signal()  # No parameters
```

#### Property Definition
```python
@Property(str, notify=statusChanged)
def status(self) -> str:
    return self._status

@status.setter
def status(self, value: str):
    if self._status != value:  # Only emit if changed
        self._status = value
        self.statusChanged.emit(value)
```

#### Slot Definition
```python
@Slot()  # No parameters, no return
def doSomething(self):
    pass

@Slot(str)  # One string parameter
def doWithArg(self, arg: str):
    pass

@Slot(str, int, result=bool)  # Parameters and return value
def doWithReturn(self, name: str, count: int) -> bool:
    return True
```

---

## 1.7 Running the Application

### Directory Structure for Minimal Example

```
minimal_app/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── backend/
│   │   ├── __init__.py
│   │   └── app_backend.py
│   └── qml/
│       └── main/
│           └── Main.qml
└── requirements.txt
```

### requirements.txt
```
PySide6>=6.5.0
```

### Running
```bash
cd minimal_app
python -m src.main
```

---

## 1.8 Exercises

### Exercise 1.1: Add a Counter
Modify the backend to add:
- A `counter` property (int)
- A `counterChanged` signal
- An `incrementCounter` slot
- A `resetCounter` slot

Modify QML to:
- Display the counter
- Add "+" and "Reset" buttons

### Exercise 1.2: Add Settings
Add a settings system:
- Backend: `username` property with getter/setter
- QML: TextField to edit username
- Backend: `saveSettings` and `loadSettings` slots

### Exercise 1.3: Error Handling
Implement proper error handling:
- Add a method that can fail
- Emit `errorOccurred` signal on failure
- Display error in a dialog

---

## 1.9 Key Takeaways

1. **PySide6** is the official Python binding for Qt
2. **QML** provides declarative, reactive UI definition
3. **Signals** notify about events
4. **Slots** are callable methods
5. **Properties** provide reactive data binding
6. **Connections** component handles external signals
7. Always **register types before** creating the engine
8. Use **context properties** to expose Python objects

---

## Next Module

In [Module 2: QML-Python Integration Fundamentals](./02_QML_PYTHON_BASICS.md), we'll dive deeper into:
- Type registration patterns
- Complex type conversion
- QML component lifecycle
- Debugging QML-Python communication
