# Module 2: QML-Python Integration Fundamentals

## Learning Objectives

By the end of this module, you will:
- Master different methods of exposing Python to QML
- Understand type conversion between Python and QML
- Handle complex data types (lists, dicts, objects)
- Debug QML-Python communication issues
- Implement the QML component lifecycle

---

## 2.1 Three Ways to Expose Python to QML

### Overview

| Method | Use Case | Persistence |
|--------|----------|-------------|
| Context Property | Singleton instances | Application lifetime |
| Type Registration | Custom components | Create in QML |
| QML Singleton | Global services | Application lifetime |

### Method 1: Context Properties

**Best for**: Backend services, managers, global state

```python
# In main.py
backend = AppBackend()
engine.rootContext().setContextProperty("backend", backend)
```

```qml
// In QML - accessible anywhere
Label { text: backend.status }
Button { onClicked: backend.doSomething() }
```

**TRANS-QML Example** (from `src/main.py`):
```python
# Create backend and managers
backend = AppBackend()
workflow_manager = WorkflowManager(backend)

# Expose to QML
context = engine.rootContext()
context.setContextProperty("backend", backend)
context.setContextProperty("workflowManager", workflow_manager)
```

### Method 2: Type Registration

**Best for**: Custom widgets, reusable components, models

```python
# Register before engine creation
from PySide6.QtQml import qmlRegisterType
qmlRegisterType(MyCustomWidget, "MyApp", 1, 0, "CustomWidget")
```

```qml
import MyApp 1.0

CustomWidget {
    id: myWidget
    // Properties and handlers
}
```

**TRANS-QML Example** (from `src/main.py`):
```python
# Register custom canvas widgets
qmlRegisterType(QMLMapCanvas, "TransQML", 1, 0, "MapCanvas")
qmlRegisterType(QMLProfileCanvas, "TransQML", 1, 0, "ProfileCanvas")
qmlRegisterType(QMLGraphCanvas, "TransQML", 1, 0, "GraphCanvas")

# Register data models
qmlRegisterType(TableDataModel, "TransQML", 1, 0, "TableDataModel")
```

```qml
// In QML
import TransQML 1.0

Rectangle {
    MapCanvas {
        id: mapCanvas
        anchors.fill: parent
        onPointClicked: (x, y, row, col, value) => {
            console.log("Clicked:", x, y, "Value:", value)
        }
    }
}
```

### Method 3: QML Singleton

**Best for**: Services that should have exactly one instance

```python
from PySide6.QtQml import qmlRegisterSingletonType

def create_preferences_manager(engine, script_engine):
    return PreferencesManager()

qmlRegisterSingletonType(
    PreferencesManager,
    "MyApp",
    1, 0,
    "Preferences",
    create_preferences_manager
)
```

```qml
import MyApp 1.0

// Access singleton anywhere
Label { text: Preferences.themeName }
```

---

## 2.2 Type Conversion: Python ↔ QML

### Automatic Conversions

| Python Type | QML Type | Notes |
|-------------|----------|-------|
| `str` | `string` | Direct |
| `int` | `int` | Direct |
| `float` | `real` | Direct |
| `bool` | `bool` | Direct |
| `list` | `var` or `QVariantList` | Becomes JavaScript array |
| `dict` | `var` or `QVariantMap` | Becomes JavaScript object |
| `None` | `null` / `undefined` | |
| `QObject` subclass | `QtObject` | Object reference |

### Working with Lists

**Python → QML:**
```python
@Slot(result='QVariantList')
def getItems(self) -> list:
    return ["apple", "banana", "cherry"]

@Slot(result='QVariantList')
def getNumbers(self) -> list:
    return [1, 2, 3, 4, 5]

@Slot(result='QVariantList')
def getComplexData(self) -> list:
    return [
        {"name": "Item 1", "value": 100},
        {"name": "Item 2", "value": 200}
    ]
```

```qml
// Using in QML
Component.onCompleted: {
    var items = backend.getItems()
    console.log(items[0])  // "apple"
    console.log(items.length)  // 3

    var data = backend.getComplexData()
    for (var i = 0; i < data.length; i++) {
        console.log(data[i].name, data[i].value)
    }
}
```

**QML → Python:**
```python
@Slot('QVariantList')
def processItems(self, items: list):
    for item in items:
        print(f"Processing: {item}")

@Slot('QVariantList', 'QVariantList')
def processXY(self, x_data: list, y_data: list):
    # Convert to numpy for processing
    import numpy as np
    x = np.array(x_data)
    y = np.array(y_data)
```

### Working with Dictionaries

**Python → QML:**
```python
@Slot(str, result='QVariantMap')
def getDatasetInfo(self, name: str) -> dict:
    return {
        'name': name,
        'numPoints': 1000,
        'numSpectra': 64,
        'units': {'x': 'nm', 'y': 'counts'},
        'channels': ['Forward', 'Backward', 'Mixed']
    }
```

```qml
// Using in QML
Button {
    onClicked: {
        var info = backend.getDatasetInfo("dataset1")
        console.log("Name:", info.name)
        console.log("Points:", info.numPoints)
        console.log("X units:", info.units.x)
        console.log("Channels:", info.channels)
    }
}
```

**QML → Python:**
```python
@Slot('QVariantMap')
def applySettings(self, settings: dict):
    window_size = settings.get('windowSize', 10)
    threshold = settings.get('threshold', 0.5)
    enabled = settings.get('enabled', True)
```

```qml
Button {
    onClicked: {
        backend.applySettings({
            "windowSize": 15,
            "threshold": 0.75,
            "enabled": true
        })
    }
}
```

### TRANS-QML Real Example: Curve Data Transfer

From `src/backend/app_backend.py`:
```python
@Slot(str)
def createFloatingGraphForDataset(self, dataset_name: str):
    """Create a floating graph in QML with dataset curves."""

    dataset = self._datasets[dataset_name]
    entity_id = f"graph_{uuid.uuid4().hex[:8]}"

    # Build QML-compatible curve list
    curves = []
    x = dataset.independent_var.tolist()  # numpy → list

    for i in range(min(10, dataset.num_spectra)):
        y = dataset.spectra.iloc[:, i].values.tolist()
        curves.append({
            'x': x,
            'y': y,
            'label': f"Spectrum {i+1}",
            'color': self._get_curve_color(i)
        })

    # Emit signal with QML-compatible data
    self.createFloatingGraphRequested.emit(
        entity_id,
        f"Graph: {dataset_name}",
        curves,  # List of dicts → QVariantList of QVariantMaps
        "Wavelength (nm)",
        "Intensity"
    )
```

---

## 2.3 Signal Parameter Types

### Declaring Signal Types

```python
from PySide6.QtCore import Signal

class MyBackend(QObject):
    # No parameters
    taskCompleted = Signal()

    # Simple types
    statusChanged = Signal(str)
    progressChanged = Signal(int)
    valueChanged = Signal(float)

    # Multiple parameters
    errorOccurred = Signal(str, str)  # title, message
    coordinatesChanged = Signal(float, float, float)  # x, y, z

    # Named parameters (helps QML)
    pointClicked = Signal(float, float, arguments=['x', 'y'])

    # Complex types
    dataReady = Signal('QVariantList')
    configChanged = Signal('QVariantMap')
    objectCreated = Signal(QObject)
```

### Named Arguments for Better QML Integration

```python
# Python - with named arguments
pointClicked = Signal(float, float, int, int, float,
                      arguments=['x', 'y', 'row', 'col', 'value'])
```

```qml
// QML - can use named parameters
MapCanvas {
    onPointClicked: (x, y, row, col, value) => {
        console.log(`Clicked at (${x}, ${y}), value: ${value}`)
    }
}

// Or destructured
MapCanvas {
    onPointClicked: function(x, y, row, col, value) {
        statusLabel.text = `Row: ${row}, Col: ${col}`
    }
}
```

### TRANS-QML Signal Examples

From `src/widgets/qml_map_canvas.py`:
```python
class QMLMapCanvas(QQuickPaintedItem):
    """Map canvas with rich signal interface."""

    # Point interaction
    pointClicked = Signal(float, float, int, int, float,
                          arguments=['x', 'y', 'row', 'col', 'value'])

    # Line profile
    profileDrawn = Signal(float, float, float, float,
                          arguments=['x1', 'y1', 'x2', 'y2'])

    # Block selection (TRANS_v3 paradigm)
    blockSelected = Signal(int, int, float, bool,
                           arguments=['blockRow', 'blockCol', 'value', 'isSelected'])

    # Cursor tracking
    cursorMoved = Signal(float, float, float,
                         arguments=['x', 'y', 'value'])

    # Selection state
    selectionChanged = Signal(int, arguments=['blockCount'])
```

---

## 2.4 The QML Component Lifecycle

### Component States

```
┌─────────────┐
│   Created   │  Component instantiated, properties set
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Loading   │  Child components being created
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Ready    │  Component.onCompleted called
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Running   │  Normal operation
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Destruction │  Component.onDestruction called
└─────────────┘
```

### Component.onCompleted

Called when the component and all children are fully created:

```qml
Rectangle {
    id: myComponent

    property var dataModel: null

    Component.onCompleted: {
        console.log("Component ready!")

        // Safe to access children
        console.log("Child count:", children.length)

        // Safe to call backend
        dataModel = backend.createDataModel()

        // Safe to access size
        console.log("Size:", width, "x", height)
    }
}
```

### Component.onDestruction

Called when component is being destroyed:

```qml
Rectangle {
    Component.onDestruction: {
        console.log("Cleaning up...")

        // Save state
        backend.saveComponentState(myState)

        // Disconnect signals
        // Release resources
    }
}
```

### Python Component Lifecycle

For `QQuickPaintedItem` subclasses, use `componentComplete()`:

```python
class MyCanvas(QQuickPaintedItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._initialized = False

    def componentComplete(self):
        """Called when QML component is fully initialized."""
        super().componentComplete()

        # Now safe to:
        # - Access size (width(), height())
        # - Set up rendering
        # - Connect to other components

        self._initialized = True
        self._setup_figure()
        self.update()  # Trigger first paint

    def paint(self, painter):
        if not self._initialized:
            return  # Not ready yet

        # Render content
```

**TRANS-QML Example** (from `src/widgets/qml_map_canvas.py`):
```python
def componentComplete(self):
    """Called when QML component is fully created."""
    super().componentComplete()

    # Initialize matplotlib figure with actual size
    self._init_figure()

    # Set up colormap
    self._setup_colormap()

    # Mark as ready
    self._component_ready = True

    # Force initial render
    self.update()

    logger.debug(f"MapCanvas componentComplete: {self.width()}x{self.height()}")
```

---

## 2.5 Debugging QML-Python Communication

### Enable QML Debugging

```python
# In main.py, before creating engine
import os
os.environ["QML_IMPORT_TRACE"] = "1"  # Trace imports
os.environ["QT_DEBUG_PLUGINS"] = "1"   # Debug plugin loading
```

### Console Logging

**Python side:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class MyBackend(QObject):
    @Slot(str)
    def doSomething(self, arg: str):
        logger.debug(f"doSomething called with: {arg}")
```

**QML side:**
```qml
Button {
    onClicked: {
        console.log("Button clicked")
        console.log("Backend status:", backend.status)
        console.log("Type:", typeof backend.status)
        backend.doSomething("test")
    }
}
```

### Common Issues and Solutions

#### Issue 1: "backend is not defined"

**Cause**: Context property not set before QML load

**Solution**:
```python
# WRONG
engine.load(qml_file)
engine.rootContext().setContextProperty("backend", backend)

# CORRECT
engine.rootContext().setContextProperty("backend", backend)
engine.load(qml_file)
```

#### Issue 2: Slot not being called

**Cause**: Missing @Slot decorator or wrong signature

**Solution**:
```python
# WRONG - no decorator
def myMethod(self, arg):
    pass

# WRONG - wrong parameter type
@Slot(int)  # But QML sends string
def myMethod(self, arg: str):
    pass

# CORRECT
@Slot(str)
def myMethod(self, arg: str):
    pass
```

#### Issue 3: Signal not received in QML

**Cause**: Signal name mismatch or missing Connection

**Solution**:
```python
# Python
dataLoaded = Signal(str)  # Note: camelCase
```

```qml
// QML - handler must be onDataLoaded (on + PascalCase)
Connections {
    target: backend
    function onDataLoaded(name) { ... }  // Correct
    // function ondataLoaded(name) { }   // Wrong
    // function onDataloaded(name) { }   // Wrong
}
```

#### Issue 4: Type conversion failing

**Cause**: Complex types not properly annotated

**Solution**:
```python
# WRONG
@Slot(list)
def process(self, items):
    pass

# CORRECT
@Slot('QVariantList')
def process(self, items: list):
    pass

# For dicts
@Slot('QVariantMap')
def configure(self, config: dict):
    pass
```

#### Issue 5: Property not updating in QML

**Cause**: Signal not emitted or wrong notify signal

**Solution**:
```python
# WRONG - forgot to emit signal
@Property(str, notify=nameChanged)
def name(self):
    return self._name

@name.setter
def name(self, value):
    self._name = value  # No signal emission!

# CORRECT
@name.setter
def name(self, value):
    if self._name != value:
        self._name = value
        self.nameChanged.emit(value)  # Emit signal!
```

---

## 2.6 The qmldir File

The `qmldir` file registers QML components for import:

### Basic Structure

```
# src/qml/components/qmldir

# Module declaration
module Components

# Singleton (optional)
singleton ThemeManager 1.0 ThemeManager.qml

# Components
CustomButton 1.0 CustomButton.qml
DataTable 1.0 DataTable.qml
FloatingWindow 1.0 FloatingWindow.qml
```

### TRANS-QML qmldir Example

From `src/qml/components/qmldir`:
```
module Components

# Entity components (floating windows)
FloatingEntity 1.0 FloatingEntity.qml
GraphEntity 1.0 GraphEntity.qml
TableEntity 1.0 TableEntity.qml
MapEntity 1.0 MapEntity.qml

# Content components (embeddable)
GraphContent 1.0 GraphContent.qml
TableContent 1.0 TableContent.qml
MapContent 1.0 MapContent.qml

# Workspace components
UnifiedWorkspace 1.0 UnifiedWorkspace.qml
DockPanel 1.0 DockPanel.qml
WorkspaceCanvas 1.0 WorkspaceCanvas.qml

# Window management
WindowManager 1.0 WindowManager.qml
EmbeddedWindow 1.0 EmbeddedWindow.qml

# Browser
ProjectBrowser 1.0 ProjectBrowser.qml
```

### Using qmldir

```qml
// Import the module
import Components 1.0

// Use registered components
FloatingEntity {
    title: "My Window"

    GraphContent {
        id: graphContent
    }
}
```

---

## 2.7 Practical Example: Data Browser

Let's build a complete example that ties together all concepts:

### Python Backend

```python
# src/backend/data_browser_backend.py

from PySide6.QtCore import QObject, Signal, Slot, Property
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class DataItem:
    """Simple data container."""
    def __init__(self, name: str, data_type: str, size: int):
        self.name = name
        self.data_type = data_type
        self.size = size


class DataBrowserBackend(QObject):
    """Backend for a data browser component."""

    # Signals
    itemsChanged = Signal()
    selectedItemChanged = Signal(str)
    errorOccurred = Signal(str, str)
    loadingChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._items: List[DataItem] = []
        self._selected_item: str = ""
        self._is_loading: bool = False

        # Add sample data
        self._add_sample_data()

    def _add_sample_data(self):
        """Add sample items for demonstration."""
        self._items = [
            DataItem("spectrum_001", "STS", 1024),
            DataItem("spectrum_002", "STS", 1024),
            DataItem("topography", "Image", 512*512),
            DataItem("map_data", "SpectralMap", 64*64*1024),
        ]
        self.itemsChanged.emit()

    # ===== Properties =====

    @Property('QVariantList', notify=itemsChanged)
    def items(self) -> List[Dict[str, Any]]:
        """List of items as QML-compatible dicts."""
        return [
            {
                'name': item.name,
                'dataType': item.data_type,
                'size': item.size,
                'sizeFormatted': self._format_size(item.size)
            }
            for item in self._items
        ]

    @Property(str, notify=selectedItemChanged)
    def selectedItem(self) -> str:
        return self._selected_item

    @selectedItem.setter
    def selectedItem(self, value: str):
        if self._selected_item != value:
            self._selected_item = value
            self.selectedItemChanged.emit(value)
            logger.debug(f"Selected item: {value}")

    @Property(bool, notify=loadingChanged)
    def isLoading(self) -> bool:
        return self._is_loading

    @Property(int, notify=itemsChanged)
    def itemCount(self) -> int:
        return len(self._items)

    # ===== Slots =====

    @Slot(str)
    def selectItem(self, name: str):
        """Select an item by name."""
        self.selectedItem = name

    @Slot(str, result='QVariantMap')
    def getItemDetails(self, name: str) -> Dict[str, Any]:
        """Get detailed info about an item."""
        for item in self._items:
            if item.name == name:
                return {
                    'name': item.name,
                    'dataType': item.data_type,
                    'size': item.size,
                    'sizeFormatted': self._format_size(item.size),
                    'canPlot': item.data_type in ['STS', 'SpectralMap'],
                    'canExport': True
                }
        return {}

    @Slot(str)
    def deleteItem(self, name: str):
        """Delete an item by name."""
        self._items = [i for i in self._items if i.name != name]
        self.itemsChanged.emit()

        if self._selected_item == name:
            self.selectedItem = ""

        logger.info(f"Deleted item: {name}")

    @Slot(str, str, int)
    def addItem(self, name: str, data_type: str, size: int):
        """Add a new item."""
        self._items.append(DataItem(name, data_type, size))
        self.itemsChanged.emit()
        logger.info(f"Added item: {name}")

    @Slot(str, result=bool)
    def exportItem(self, name: str) -> bool:
        """Export an item (placeholder)."""
        logger.info(f"Exporting: {name}")
        # In real app: show save dialog, export data
        return True

    # ===== Helpers =====

    def _format_size(self, size: int) -> str:
        """Format size for display."""
        if size < 1024:
            return f"{size} points"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} K points"
        else:
            return f"{size / (1024*1024):.1f} M points"
```

### QML Component

```qml
// src/qml/components/DataBrowser.qml

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: dataBrowser

    property var browserBackend: null

    color: "#1a1a2e"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        // Header
        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Data Browser"
                font.pixelSize: 16
                font.bold: true
                color: "#5BCEFA"
            }

            Item { Layout.fillWidth: true }

            Label {
                text: browserBackend ? browserBackend.itemCount + " items" : "0 items"
                color: "#888"
            }
        }

        // Search/filter (placeholder)
        TextField {
            id: searchField
            Layout.fillWidth: true
            placeholderText: "Search..."
            background: Rectangle {
                color: "#2a2a3e"
                radius: 4
            }
            color: "white"
        }

        // Item list
        ListView {
            id: itemList
            Layout.fillWidth: true
            Layout.fillHeight: true

            model: browserBackend ? browserBackend.items : []
            clip: true

            delegate: Rectangle {
                width: itemList.width
                height: 60
                color: modelData.name === browserBackend.selectedItem ?
                       "#3a3a5e" : "transparent"

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 10

                    // Icon based on type
                    Rectangle {
                        width: 40
                        height: 40
                        radius: 4
                        color: getTypeColor(modelData.dataType)

                        Label {
                            anchors.centerIn: parent
                            text: getTypeIcon(modelData.dataType)
                            font.pixelSize: 20
                        }
                    }

                    // Info
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Label {
                            text: modelData.name
                            color: "white"
                            font.pixelSize: 14
                        }

                        Label {
                            text: modelData.dataType + " • " + modelData.sizeFormatted
                            color: "#888"
                            font.pixelSize: 11
                        }
                    }

                    // Actions
                    Button {
                        text: "..."
                        flat: true
                        onClicked: contextMenu.popup()

                        Menu {
                            id: contextMenu

                            MenuItem {
                                text: "View Details"
                                onTriggered: showDetails(modelData.name)
                            }
                            MenuItem {
                                text: "Export..."
                                onTriggered: browserBackend.exportItem(modelData.name)
                            }
                            MenuSeparator {}
                            MenuItem {
                                text: "Delete"
                                onTriggered: confirmDelete(modelData.name)
                            }
                        }
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: browserBackend.selectItem(modelData.name)
                    onDoubleClicked: showDetails(modelData.name)
                }
            }

            // Empty state
            Label {
                anchors.centerIn: parent
                text: "No data loaded"
                color: "#666"
                visible: itemList.count === 0
            }
        }

        // Details panel (shows when item selected)
        Rectangle {
            Layout.fillWidth: true
            height: detailsVisible ? 120 : 0
            color: "#2a2a3e"
            radius: 8
            clip: true

            property bool detailsVisible: browserBackend &&
                                          browserBackend.selectedItem !== ""

            Behavior on height {
                NumberAnimation { duration: 200 }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                visible: parent.detailsVisible

                Label {
                    text: "Details: " + (browserBackend ? browserBackend.selectedItem : "")
                    color: "#5BCEFA"
                    font.bold: true
                }

                Label {
                    id: detailsLabel
                    color: "white"
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
    }

    // Helper functions
    function getTypeColor(dataType) {
        switch(dataType) {
            case "STS": return "#F5A9B8"
            case "Image": return "#5BCEFA"
            case "SpectralMap": return "#9B59B6"
            default: return "#666"
        }
    }

    function getTypeIcon(dataType) {
        switch(dataType) {
            case "STS": return "~"
            case "Image": return "#"
            case "SpectralMap": return "@"
            default: return "?"
        }
    }

    function showDetails(name) {
        if (!browserBackend) return

        var details = browserBackend.getItemDetails(name)
        detailsLabel.text = "Type: " + details.dataType +
                           "\nSize: " + details.sizeFormatted +
                           "\nCan plot: " + (details.canPlot ? "Yes" : "No")
    }

    function confirmDelete(name) {
        deleteDialog.itemToDelete = name
        deleteDialog.open()
    }

    // Delete confirmation dialog
    Dialog {
        id: deleteDialog
        title: "Confirm Delete"
        modal: true
        anchors.centerIn: parent

        property string itemToDelete: ""

        Label {
            text: "Delete '" + deleteDialog.itemToDelete + "'?"
        }

        standardButtons: Dialog.Yes | Dialog.No

        onAccepted: {
            browserBackend.deleteItem(itemToDelete)
        }
    }

    // Connect to backend signals
    Connections {
        target: browserBackend

        function onSelectedItemChanged(name) {
            if (name) {
                showDetails(name)
            }
        }

        function onErrorOccurred(title, message) {
            console.error(title + ": " + message)
        }
    }
}
```

---

## 2.8 Exercises

### Exercise 2.1: Add Search Functionality

Extend the DataBrowser:
1. Add a `filterItems(searchText)` slot to the backend
2. Make search field filter the displayed items
3. Implement case-insensitive partial matching

### Exercise 2.2: Add Sorting

Implement sorting:
1. Add `sortBy` property (name, type, size)
2. Add `sortAscending` property
3. Create sort controls in QML

### Exercise 2.3: Add Drag and Drop

Implement drag to reorder:
1. Enable drag on list items
2. Handle drop to reorder
3. Sync order to backend

---

## 2.9 Key Takeaways

1. **Three methods** to expose Python: context properties, type registration, singletons
2. **Type annotations** are crucial: use `'QVariantList'` and `'QVariantMap'` for complex types
3. **Signal arguments** help QML with parameter names
4. **componentComplete** is the safe initialization point
5. **qmldir** files register components for clean imports
6. **Logging** on both sides aids debugging

---

## Next Module

In [Module 3: Signals, Slots, and Properties](./03_SIGNALS_SLOTS_PROPERTIES.md), we'll explore:
- Advanced signal patterns
- Property bindings in depth
- Cross-component communication
- The observer pattern in Qt
