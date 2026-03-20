# TRANS-QML Deprecated and Redundant Implementations Balance

This document provides a comprehensive balance sheet of all deprecated, redundant, and legacy implementations in the TRANS-QML codebase, along with their status, recommended actions, and migration paths.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Deprecated Components](#2-deprecated-components)
3. [Redundant Implementations](#3-redundant-implementations)
4. [Legacy Code (Maintained for Reference)](#4-legacy-code-maintained-for-reference)
5. [Fixed Issues (Historical Record)](#5-fixed-issues-historical-record)
6. [Migration Guide](#6-migration-guide)
7. [Recommendations](#7-recommendations)

---

## 1. Executive Summary

### Status Overview

| Category | Count | Priority |
|----------|-------|----------|
| **Deprecated** (should be removed) | 4 | High |
| **Redundant** (duplicate functionality) | 6 | Medium |
| **Legacy** (kept for reference) | 4 | Low |
| **Fixed** (previously broken, now working) | 8 | Resolved |

### Key Findings

1. **Window Management Duplication**: The codebase has both standalone `Window` components and embedded `EmbeddedWindow` components serving similar purposes
2. **Content vs Wrapper Components**: Several "Content" QML files duplicate functionality from "Entity" wrappers
3. **Widget Evolution**: Python widget implementations evolved through multiple iterations, leaving legacy versions
4. **Formula Engine**: Exists in both `TableDataModel` and standalone `FormulaEngine` class

---

## 2. Deprecated Components

### 2.1 Standalone Window Components (DEPRECATED)

These components create OS-level windows but are superseded by the embedded window system in `UnifiedWorkspace`.

| Component | Location | Replacement | Status |
|-----------|----------|-------------|--------|
| `table_window.py` | `src/widgets/` | `TableEntity.qml` + `TableDataModel` | **DEPRECATED** |
| `TableWindow.qml` | Not present | `TableEntity.qml` | N/A |
| `plot_window.py` | `src/widgets/` | `GraphEntity.qml` + `QmlGraphCanvas` | **DEPRECATED** |
| `PlotWindow.qml` | Not present | `GraphEntity.qml` | N/A |

**Reason for Deprecation:**
- TRANS-QML now uses an MDI (Multiple Document Interface) approach where all content windows are embedded within `UnifiedWorkspace`
- Standalone windows create window management complexity and don't integrate with the tileable workspace
- User preference is for single-window applications with dockable/tileable sub-windows

**Migration Path:**
```python
# OLD (deprecated)
from src.widgets.table_window import TableWindow
window = TableWindow(parent=None)
window.show()

# NEW (recommended)
# Call from QML or emit signal from backend
self.createFloatingTableRequested.emit(entity_id, title, data, headers)
```

### 2.2 Duplicate Content Components

These QML components have been superseded by integrated Entity components.

| Component | Location | Replacement | Status |
|-----------|----------|-------------|--------|
| `TableWindowContent.qml` | `src/qml/components/` | Integrated into `TableEntity.qml` | **CANDIDATE FOR REMOVAL** |
| `GraphWindowContent.qml` | `src/qml/components/` | Integrated into `GraphEntity.qml` | **CANDIDATE FOR REMOVAL** |
| `TableContent.qml` | `src/qml/components/` | Used by `EmbeddedWindow` | KEEP (for now) |
| `GraphContent.qml` | `src/qml/components/` | Used by `EmbeddedWindow` | KEEP (for now) |

**Note:** `TableContent.qml` and `GraphContent.qml` are thin wrappers used by the `EmbeddedWindow` system and should be kept until that system is deprecated.

### 2.3 Unused QML Components

Components created during development that are no longer used.

| Component | Location | Reason | Status |
|-----------|----------|--------|--------|
| `MapWindowContent.qml` | `src/qml/components/` | Map editing uses `MapEditorWorkstation` | **CANDIDATE FOR REMOVAL** |

---

## 3. Redundant Implementations

### 3.1 Table/Spreadsheet Implementations

The codebase has multiple table implementations:

| Implementation | Location | Features | Status |
|----------------|----------|----------|--------|
| `TableDataModel` | `src/models/table_data_model.py` | Full QAbstractTableModel, formulas, statistics | **CANONICAL** |
| `enhanced_table_window.py` | `src/widgets/` | FormulaEngine reference implementation | **LEGACY** |
| `TableEntity.qml` (inline) | `src/qml/components/` | QML-only simple table | **INTEGRATED** |

**Recommended Action:** Use `TableDataModel` for all new table functionality. The inline QML table in `TableEntity.qml` has been updated to use `TableDataModel` as its backend.

### 3.2 Graph/Plot Implementations

Multiple graph rendering approaches exist:

| Implementation | Location | Technology | Status |
|----------------|----------|------------|--------|
| `QmlGraphCanvas` | `src/widgets/qml_graph_canvas.py` | Matplotlib via QQuickPaintedItem | **CANONICAL** |
| `QmlProfileCanvas` | `src/widgets/qml_profile_canvas.py` | Matplotlib (1D profiles) | **CANONICAL** |
| `enhanced_plot_window.py` | `src/widgets/` | PyQtGraph or Matplotlib | **LEGACY** |
| `GraphEntity.qml` Canvas2D | `src/qml/components/` | QML Canvas placeholder | **REMOVED** |

**History:** `GraphEntity.qml` originally used a QML Canvas2D placeholder due to a crash in `QmlGraphCanvas`. This has been fixed by removing `notify=` from Property definitions.

### 3.3 Map Canvas Implementations

| Implementation | Location | Features | Status |
|----------------|----------|----------|--------|
| `QmlMapCanvas` | `src/widgets/qml_map_canvas.py` | Full map rendering, TRANS_v3 block selection | **CANONICAL** |
| `MapEntity.qml` | `src/qml/components/` | Wrapper for floating entities | Uses QmlMapCanvas |
| `MapEditorWorkstation.qml` | `src/qml/map_editor/` | Full map editing interface | **CANONICAL** |

### 3.4 Formula Engine Duplication

| Implementation | Location | Features | Status |
|----------------|----------|----------|--------|
| `FormulaEngine` (in TableDataModel) | `src/models/table_data_model.py` | Full formula support, cell refs, column refs | **CANONICAL** |
| `FormulaEngine` (standalone) | `src/widgets/enhanced_table_window.py` | Reference implementation | **LEGACY** |

The `FormulaEngine` in `TableDataModel` is the canonical implementation with these features:
- Cell references: `A1`, `B2`, `$A$1`
- Column references: `[A]`, `[ColumnName]`
- Row index: `i` (1-based)
- Functions: `SUM`, `AVG`, `MIN`, `MAX`, `SQRT`, `SIN`, `COS`, `TAN`, `LOG`, `LOG10`, `EXP`, `ABS`, `ROUND`, `RANDOM`
- Constants: `pi`, `e`

---

## 4. Legacy Code (Maintained for Reference)

These implementations are kept for reference but should not be used for new development.

### 4.1 Widget Legacy Files

| File | Location | Purpose | Keep For |
|------|----------|---------|----------|
| `table_window.py` | `src/widgets/` | Standalone table window | Reference for PyQt patterns |
| `plot_window.py` | `src/widgets/` | Standalone plot window | Reference for curve management |
| `enhanced_table_window.py` | `src/widgets/` | Enhanced table features | FormulaEngine reference |
| `enhanced_plot_window.py` | `src/widgets/` | Enhanced plot features | Curve operation reference |

### 4.2 Loader Legacy

| File | Location | Purpose | Status |
|------|----------|---------|--------|
| `nanosurf_sts_loader.py` | `src/data_loaders/` | Basic NID loading | Superseded by `nanosurf_sts_enhanced.py` |
| `neaspec_snom_loader.py` | `src/data_loaders/` | Basic SNOM loading | Superseded by `neaspec_snom_enhanced.py` |

**Note:** The "enhanced" versions provide additional metadata parsing and channel support. The basic versions are kept for compatibility.

---

## 5. Fixed Issues (Historical Record)

### 5.1 QmlGraphCanvas Crash (FIXED)

**Issue:** The `QmlGraphCanvas` widget caused a crash during QML property cache building:
```
Thread 11 Crashed:: QQmlThread
QMetaProperty::notifySignalIndex() const
QQmlPropertyCache::append()
```

**Root Cause:** PySide6 property registration issue where `notify=` signals were referenced before being defined.

**Fix Applied:** Removed `notify=` from non-essential Properties in `qml_graph_canvas.py`. Properties that require notification still work via explicit signal emission.

**Status:** ✅ FIXED (December 2025)

### 5.2 Entity Content Sizing (FIXED)

**Issue:** Content in `FloatingEntity` components didn't fill available space.

**Fix Applied:** Added `anchors.fill: parent` to content components in:
- `GraphEntity.qml`
- `TableEntity.qml`
- `MapEntity.qml`

**Status:** ✅ FIXED (December 2025)

### 5.3 Component Initialization (FIXED)

**Issue:** Python QQuickPaintedItem widgets didn't initialize properly.

**Fix Applied:** Added `componentComplete()` override to:
- `qml_graph_canvas.py`
- `qml_map_canvas.py`
- `qml_profile_canvas.py`

**Status:** ✅ FIXED (December 2025)

### 5.4 TableEntity Inline Implementation (FIXED)

**Issue:** `TableEntity.qml` contained a basic Row/Repeater pattern without formula support.

**Fix Applied:** Integrated `TableDataModel` with:
- 3-tab interface (Data, Columns, Plot)
- Formula bar
- Context menus (SciDAVis-style)
- Column configuration

**Status:** ✅ FIXED (December 2025)

### 5.5 WorkflowCanvas Signal Names (FIXED)

**Issue:** Signal handler names in `WorkflowCanvas.qml` didn't match `WorkflowNode.qml` signals.

**Fix Applied:** Changed:
- `onNodeClicked` → `onNodeSelected`
- `onNodeDragged` → `onNodeMoved`

**Status:** ✅ FIXED (December 2025)

### 5.6 ProjectBrowserEntity Invalid Signals (FIXED)

**Issue:** `ProjectBrowserEntity` connected to non-existent signals.

**Fix Applied:** Removed invalid signal connections:
- `datasetDoubleClicked`
- `datasetActivated`
- `spectrumRequestedFromBrowser`

**Status:** ✅ FIXED (December 2025)

---

## 6. Migration Guide

### 6.1 Migrating from Standalone Windows to Embedded Windows

**Before (Deprecated):**
```python
# Python - Creating standalone window
from src.widgets.table_window import TableWindow

class AppBackend(QObject):
    def openTable(self, dataset_name):
        window = TableWindow()
        window.loadData(self._datasets[dataset_name])
        window.show()
```

**After (Recommended):**
```python
# Python - Emitting signal for QML to create embedded window
class AppBackend(QObject):
    createFloatingTableRequested = Signal(str, str, 'QVariantList', 'QVariantList')

    def openTable(self, dataset_name):
        dataset = self._datasets[dataset_name]
        entity_id = f"table_{uuid.uuid4().hex[:8]}"

        # Convert data to QML-compatible format
        data_rows = dataset.data.values.tolist()
        headers = dataset.data.columns.tolist()

        self.createFloatingTableRequested.emit(
            entity_id, dataset_name, data_rows, headers
        )
```

```qml
// QML - Handling the signal
Connections {
    target: backend

    function onCreateFloatingTableRequested(entityId, title, dataRows, headers) {
        workspace.createTableEntity(title, 100, 100, 600, 400, dataRows, headers)
    }
}
```

### 6.2 Migrating from Legacy Widgets to QML Canvas

**Before (Legacy):**
```python
from src.widgets.enhanced_plot_window import EnhancedPlotWindow

plot = EnhancedPlotWindow()
plot.add_curve("Curve1", x_data, y_data)
```

**After (Recommended):**
```qml
// In QML component
import TransQML 1.0

GraphCanvas {
    id: graphCanvas
    anchors.fill: parent

    Component.onCompleted: {
        addCurve("Curve1", x_data, y_data, "#5BCEFA", 2.0)
    }
}
```

### 6.3 Using TableDataModel Instead of Inline Tables

**Before (Simple inline table):**
```qml
// Basic Row/Repeater pattern
Flickable {
    contentWidth: row.width
    contentHeight: row.height

    Row {
        Repeater {
            model: tableData
            // ... basic cells
        }
    }
}
```

**After (With TableDataModel):**
```qml
import TransQML 1.0

Rectangle {
    property var tableModel: TableDataModel {}

    Component.onCompleted: {
        tableModel.setTableData(data, headers)
    }

    TableView {
        anchors.fill: parent
        model: tableModel

        delegate: Rectangle {
            implicitWidth: 100
            implicitHeight: 30

            TextInput {
                text: model.display
                onEditingFinished: {
                    tableModel.setData(
                        tableModel.index(row, column),
                        text
                    )
                }
            }
        }
    }
}
```

---

## 7. Recommendations

### 7.1 Immediate Actions (High Priority)

1. **Remove Deprecated Window Components**
   - [ ] Remove `src/widgets/table_window.py` after confirming no imports
   - [ ] Remove `src/widgets/plot_window.py` after confirming no imports
   - [ ] Archive `TableWindowContent.qml` and `GraphWindowContent.qml`

2. **Consolidate Formula Engines**
   - [ ] Remove standalone FormulaEngine from `enhanced_table_window.py`
   - [ ] Document canonical FormulaEngine API in `TableDataModel`

### 7.2 Medium-Term Actions

1. **Audit Import Statements**
   ```bash
   grep -r "from src.widgets.table_window" src/
   grep -r "from src.widgets.plot_window" src/
   grep -r "TableWindowContent" src/qml/
   grep -r "GraphWindowContent" src/qml/
   ```

2. **Review EmbeddedWindow System**
   - Evaluate if `EmbeddedWindow` + `WindowManager` pattern should be the sole windowing approach
   - Consider removing `FloatingEntity` system if redundant

3. **Update Documentation**
   - [ ] Update API_REFERENCE.md with deprecated notices
   - [ ] Create migration examples for common patterns

### 7.3 Long-Term Architecture Goals

1. **Single Windowing System**
   - Choose either `EmbeddedWindow`/`WindowManager` OR `FloatingEntity` system
   - Currently both exist, creating maintenance burden

2. **Unified Canvas Pattern**
   - All Python canvases should follow the same pattern:
     - `QQuickPaintedItem` subclass
     - `componentComplete()` initialization
     - Consistent signal naming
     - Matplotlib backend

3. **Model-View Separation**
   - All data display should use Qt Model/View architecture
   - Tables: `TableDataModel` (QAbstractTableModel)
   - Graphs: Curve data model (to be implemented)
   - Maps: Channel data model (to be implemented)

---

## Appendix A: File Status Matrix

| File | Type | Status | Action |
|------|------|--------|--------|
| `src/widgets/table_window.py` | Widget | DEPRECATED | Archive |
| `src/widgets/plot_window.py` | Widget | DEPRECATED | Archive |
| `src/widgets/enhanced_table_window.py` | Widget | LEGACY | Keep for reference |
| `src/widgets/enhanced_plot_window.py` | Widget | LEGACY | Keep for reference |
| `src/widgets/qml_graph_canvas.py` | Widget | CANONICAL | Maintain |
| `src/widgets/qml_map_canvas.py` | Widget | CANONICAL | Maintain |
| `src/widgets/qml_profile_canvas.py` | Widget | CANONICAL | Maintain |
| `src/models/table_data_model.py` | Model | CANONICAL | Maintain |
| `src/qml/components/TableEntity.qml` | QML | CURRENT | Maintain |
| `src/qml/components/GraphEntity.qml` | QML | CURRENT | Maintain |
| `src/qml/components/MapEntity.qml` | QML | CURRENT | Maintain |
| `src/qml/components/TableWindowContent.qml` | QML | REDUNDANT | Archive |
| `src/qml/components/GraphWindowContent.qml` | QML | REDUNDANT | Archive |
| `src/qml/components/TableContent.qml` | QML | IN USE | Keep (for EmbeddedWindow) |
| `src/qml/components/GraphContent.qml` | QML | IN USE | Keep (for EmbeddedWindow) |
| `src/qml/components/MapContent.qml` | QML | IN USE | Keep (for EmbeddedWindow) |
| `src/qml/components/WindowManager.qml` | QML | CURRENT | Maintain |
| `src/qml/components/EmbeddedWindow.qml` | QML | CURRENT | Maintain |

---

## Appendix B: Signal/Slot Audit Results

### Orphaned Signals (Defined but Never Connected)

| Class | Signal | Location | Recommendation |
|-------|--------|----------|----------------|
| None found | - | - | N/A |

### Duplicate Signal Patterns

| Pattern | Locations | Recommendation |
|---------|-----------|----------------|
| `dataChanged` | TableDataModel, QmlProfileCanvas, QmlMapCanvas | Keep - standard Qt pattern |
| `statusMessage` | WorkflowCanvas, WorkflowWindow | Keep - different scopes |

---

## Appendix C: Test Coverage for Deprecated Code

### Tests That Use Deprecated Components

| Test File | Deprecated Component Used | Action Required |
|-----------|--------------------------|-----------------|
| None found | - | N/A |

### Tests for Replacement Components

| Replacement Component | Test File | Coverage |
|-----------------------|-----------|----------|
| `TableDataModel` | `tests/test_models/test_table_data_model.py` | 48 tests |
| `QmlGraphCanvas` | (Integration tests) | Manual testing |
| `WorkflowManager` | `tests/test_backend/test_workflow_manager.py` | Present |

---

*TRANS-QML Deprecated Implementations Balance Sheet*
*Last updated: December 2025*
