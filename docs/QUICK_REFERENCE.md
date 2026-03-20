# TRANS-QML Quick Reference Card

## File Locations

| What | Where |
|------|-------|
| Entry point | `main.py` |
| Main window | `src/qml/main/Main.qml` |
| Backend logic | `src/backend/app_backend.py` |
| Tool implementations | `src/backend/tool_implementations.py` |
| Workflow definitions | `src/backend/workflow_engine.py` |
| Workflow execution | `src/backend/workflow_manager.py` |
| Data model | `src/models/spectral_data.py` |

---

## Common Tasks

### Add a New Tool (Backend Only)

1. **Add method** to `tool_implementations.py`:
   ```python
   def my_tool(self, task, dataset_name, param1):
       # Implementation
       return output_path
   ```

2. **Add QML slot** to `app_backend.py`:
   ```python
   @Slot(str, int)
   def myTool(self, dataset_name: str, param1: int):
       self.worker_manager.submit(...)
   ```

3. **Add UI** in `src/qml/tools/MyTool.qml`

---

### Add a New Workflow Node

1. **Define node** in `workflow_engine.py` `TOOL_DEFINITIONS`:
   ```python
   "MyNode": {
       "display_name": "My Node",
       "category": "Processing",
       "inputs": [...],
       "outputs": [...],
       "parameters": {...}
   }
   ```

2. **Add executor** in `workflow_manager.py` `_execute_node()`:
   ```python
   elif tool_name == "MyNode":
       # Execute logic
   ```

---

### Add a New Data Loader

1. **Create loader** in `src/data_loaders/my_loader.py`:
   ```python
   class MyLoader(BaseLoader):
       def can_load(self, path): ...
       def load(self, path) -> SpectralData: ...
   ```

2. **Register** in `app_backend.py` import detection

---

### Add a New Parameter Type (Workflow UI)

1. **Add case** in `NodeParameterEditor.qml` `createParameterControl()`:
   ```qml
   case "my_param_type":
       component = myParamComponent
       break
   ```

2. **Create component**:
   ```qml
   Component {
       id: myParamComponent
       // Parameter UI
   }
   ```

---

## Key Classes

| Class | File | Purpose |
|-------|------|---------|
| `AppBackend` | app_backend.py | QML ↔ Python bridge |
| `SpectralData` | spectral_data.py | Core data container |
| `Workflow` | workflow_engine.py | Workflow graph |
| `WorkflowExecutor` | workflow_manager.py | Run workflows |
| `PersistentWorker` | worker.py | Background threading |
| `ProjectManager` | project_manager.py | .hrt file I/O |

---

## Signal/Slot Patterns

### Python → QML (Signal)

```python
# Python
self.dataLoaded.emit(name)
```

```qml
// QML
Connections {
    target: backend
    function onDataLoaded(name) { ... }
}
```

### QML → Python (Slot)

```qml
// QML
backend.smoothCurves(name, 11, 3, "savgol")
```

```python
# Python
@Slot(str, int, int, str)
def smoothCurves(self, name, ws, po, st): ...
```

---

## Theme Colors

```qml
readonly property color bgDark: "#1a1a1a"
readonly property color bgMedium: "#2a2a2a"
readonly property color bgLight: "#3a3a3a"
readonly property color accentPink: "#ff66b2"
readonly property color accentBlue: "#66b3ff"
readonly property color accentGreen: "#66ff99"
readonly property color accentOrange: "#ffaa66"
readonly property color textLight: "#ffffff"
readonly property color textMuted: "#cccccc"
readonly property color borderColor: "#555555"
```

---

## Port Types

| Type | Use For |
|------|---------|
| `dataset` | Full SpectralData |
| `flat_data` | 2D integrated data |
| `image` | File path to image |
| `intervals` | List of [start, end] |
| `number` | Single value |
| `string` | Text |
| `any` | Accepts anything |

---

## Output Naming Convention

**Files**: `{CleanName}_{operation}_{params}.csv`
- Example: `Sample1_smoothed_savgol.csv`

**Datasets**: `{Source} - {Operation} ({Params})`
- Example: `Sample1 - Truncated (-1.0 to 1.0)`

---

## Running the App

```bash
cd /path/to/TRANS_QML
python main.py
```

**Debug mode** (verbose logging):
```bash
python main.py --debug
```

---

## Common QML Patterns

### Tool Panel Template

```qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    color: "#2a2a2a"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10

        // Dataset selector
        ComboBox {
            id: datasetCombo
            model: backend.datasetList
        }

        // Parameters
        SpinBox { id: param1; value: 10 }

        // Execute button
        Button {
            text: "Apply"
            onClicked: backend.myTool(
                datasetCombo.currentText,
                param1.value
            )
        }
    }
}
```

### Workflow Node Template (Definition)

```python
"MyTool": {
    "display_name": "My Tool",
    "category": "Processing",
    "description": "Does something useful",
    "inputs": [
        {"id": "in", "name": "Input", "port_type": "dataset", "required": True}
    ],
    "outputs": [
        {"id": "out", "name": "Output", "port_type": "dataset"}
    ],
    "parameters": {
        "value": {"type": "int", "label": "Value", "default": 10, "min": 1}
    }
}
```

---

*Quick Reference for TRANS-QML Development*
