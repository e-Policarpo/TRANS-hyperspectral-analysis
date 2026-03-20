# TRANS-QML Code Cleanup and Consolidation Plan

## Executive Summary

This document identifies duplicate, deprecated, and vestigial code that was introduced during recent development, and provides a systematic plan to consolidate the codebase around the existing production-ready implementations.

---

## Part 1: Issues Identified

### 1.1 Sloppy Implementations That Replaced Good Code

#### A. TableEntity.qml - Reverted to Inline Implementation

**Problem:** The current `TableEntity.qml` contains a basic inline table implementation (simple Row/Repeater pattern) instead of using the existing:
- `TableDataModel` (QAbstractTableModel with full formula support)
- `TableWindowContent.qml` (comprehensive tabbed interface)

**Evidence:**
- Lines 48-345: Inline `contentComponent` with basic Flickable/Row/Repeater
- No integration with `TableDataModel`
- No formula bar, no column configuration, no plot integration
- Missing tabs (Data, Columns, Plot)

**Impact:** Lost functionality:
- ❌ Cell formulas (`=A1+B1`, `=SUM(A:A)`)
- ❌ Column metadata (units, comments)
- ❌ Statistics panel
- ❌ Direct backend model integration
- ❌ Plot column selection

#### B. GraphEntity.qml - Replaced with Placeholder

**Problem:** The current `GraphEntity.qml` uses a QML Canvas2D placeholder instead of the production-ready `QMLGraphCanvas` (qml_graph_canvas.py).

**Evidence:**
- Line 14: `// import TransQML 1.0  // Temporarily disabled`
- Lines 177-229: Placeholder Canvas with stub methods
- Lines 217-223: Empty stub functions (`resetView`, `zoomIn`, `addCurve`, etc.)

**Impact:** Lost functionality:
- ❌ Matplotlib rendering (publication-quality plots)
- ❌ Interactive curve selection
- ❌ Math operations (derivative, smooth, FFT, integrate)
- ❌ Proper zoom/pan
- ❌ Curve styling (color, linewidth, markers)
- ❌ Export capabilities

### 1.2 Root Cause of GraphCanvas Crash

The crash in `QMLGraphCanvas` occurs during QML property cache building:
```
Thread 11 Crashed:: QQmlThread
QMetaProperty::notifySignalIndex() const
QQmlPropertyCache::append()
```

**Likely Cause:** PySide6 property registration issue. The working canvases (`QMLProfileCanvas`, `QMLMapCanvas`) use similar patterns but may have subtle differences in property/signal ordering.

---

## Part 2: Consolidation Plan

### Phase 1: Fix QMLGraphCanvas (Priority: HIGH)

**File:** `/src/widgets/qml_graph_canvas.py`

**Actions:**
1. Compare property definitions with working `qml_map_canvas.py`
2. Ensure all signals are defined BEFORE properties that reference them
3. Test with minimal property set to isolate the crash
4. Consider removing `notify=` from non-essential properties temporarily

**Verification:**
```bash
python3 -c "from src.widgets.qml_graph_canvas import QMLGraphCanvas; print('OK')"
```

### Phase 2: Restore GraphEntity.qml (Priority: HIGH)

**File:** `/src/qml/components/GraphEntity.qml`

**Actions:**
1. Re-enable `import TransQML 1.0`
2. Replace Canvas2D placeholder with actual `GraphCanvas`
3. Restore proper signal connections
4. Keep the toolbar and operations bar (those are good)
5. Optionally: Use `GraphWindowContent.qml` via Loader for full tabbed interface

**Target Structure:**
```qml
import TransQML 1.0

FloatingEntity {
    contentComponent: Component {
        ColumnLayout {
            // Toolbar (keep existing)
            RowLayout { ... }

            // Actual GraphCanvas (restore)
            GraphCanvas {
                id: graphCanvas
                // ... proper bindings
            }

            // Operations bar (keep existing)
            RowLayout { ... }
        }
    }
}
```

### Phase 3: Integrate TableDataModel into TableEntity (Priority: MEDIUM)

**Files:**
- `/src/qml/components/TableEntity.qml`
- `/src/models/table_data_model.py`
- `/src/backend/app_backend.py`

**Actions:**
1. Replace inline Row/Repeater with proper `TableView` + `TableDataModel`
2. Add backend integration for model creation:
   ```javascript
   Component.onCompleted: {
       var model = backend.createTableDataModel(entityId)
       tableView.model = model
   }
   ```
3. Add formula bar from `TableWindowContent.qml`
4. Add column configuration tab
5. Add plot column selection

**Alternative:** Use `TableWindowContent.qml` via Loader (simpler but less flexible)

### Phase 4: Verify Backend Integration (Priority: MEDIUM)

**File:** `/src/backend/app_backend.py`

**Actions:**
1. Verify `createTableDataModel()` returns model properly to QML
2. Test `loadDatasetToTable()` with actual datasets
3. Verify `linkTableToGraph()` creates bidirectional links
4. Test `applyTableColumnOperation()` processing

---

## Part 3: Vestigial Code Removal Schematic

### 3.1 Files to Audit

| Path | Type | Action | Reason |
|------|------|--------|--------|
| `widgets/table_window.py` | Widget | KEEP (legacy) | May still be used for standalone windows |
| `widgets/enhanced_table_window.py` | Widget | KEEP | FormulaEngine implementation used by TableDataModel |
| `widgets/plot_window.py` | Widget | KEEP (legacy) | May still be used for standalone windows |
| `widgets/enhanced_plot_window.py` | Widget | KEEP | Has good curve management code |
| `qml/components/GraphWindowContent.qml` | QML | REVIEW | May have unused code if GraphEntity uses inline |
| `qml/components/TableWindowContent.qml` | QML | REVIEW | May have unused code if TableEntity uses inline |

### 3.2 Specific Code Sections to Remove

#### In GraphEntity.qml (after Phase 2):
```
REMOVE: Lines 177-229 (Canvas2D placeholder)
REMOVE: Lines 217-223 (stub functions)
RESTORE: GraphCanvas usage
```

#### In TableEntity.qml (after Phase 3):
```
REMOVE: Lines 48-295 (inline Flickable/Row/Repeater implementation)
REPLACE WITH: TableView + TableDataModel or Loader { source: "TableWindowContent.qml" }
```

### 3.3 Import Cleanup

**Files to check for unused imports:**
- `main.py` - verify all registered types are used
- `backend/app_backend.py` - check for unused model imports
- `widgets/__init__.py` - verify all exports are used

### 3.4 Signal/Slot Audit

Search for orphaned signals (defined but never connected):
```bash
grep -r "Signal(" src/widgets/*.py | grep -v "#"
grep -r "\.connect(" src/ | grep -v "#"
```

---

## Part 4: Execution Checklist

### Immediate Actions (Today) - COMPLETED

- [x] 1. Debug `qml_graph_canvas.py` property crash - FIXED (removed notify= from Properties)
- [x] 2. Create minimal test case for GraphCanvas - Tested via app launch
- [x] 3. Restore GraphEntity.qml with working GraphCanvas - DONE

### Short-term (This Week) - COMPLETED

- [x] 4. Integrate TableDataModel into TableEntity - DONE (full formula bar, backend integration)
- [x] 5. Test formula functionality end-to-end - Backend tests pass
- [x] 6. Verify table-graph linking works - Backend methods verified

### Additional Fixes Applied

- [x] Fix content sizing in all Entity components (anchors.fill: parent)
- [x] Add componentComplete() to all Python canvases for proper initialization
- [x] Add MapEntity anchoring fix
- [x] Add getColumnName() method to TableDataModel

### TableEntity Enhancements (December 2025)

- [x] Add SciDAVis-style context menus:
  - Cell context menu (Clear Cell, Insert Row Above/Below, Delete Row)
  - Column context menu (Set Column Values, Fill Column, Sort, Statistics, Clear)
  - Row context menu (Insert Row Above/Below, Clear Row, Delete Row)
- [x] Add Set Column Values dialog (SciDAVis-style formula input)
- [x] Add Fill Column dialog (Row Numbers, Linear, Constant, Random)
- [x] Add right-click support to cells, column headers, and row numbers

### TableDataModel Enhancements (December 2025)

- [x] Add `insertRow(row_idx)` - Insert row at specific position
- [x] Add `clearRow(row_idx)` - Clear all values in a row
- [x] Add `clearColumn(col_idx)` - Clear all values in a column
- [x] Add `sortByColumn(col_idx, ascending)` - Sort table by column
- [x] Add `parse_number()` function for locale-aware decimal parsing (US dot, European comma)

### FormulaEngine Enhancements (December 2025)

- [x] Add `i` row index variable (1-based) for column formulas
- [x] Add `random()` function for random values
- [x] Add `pi` and `e` mathematical constants
- [x] Add `log10()` function
- [x] Fix `^` power operator to work in column formulas (converts to `**`)

### Tests Added (December 2025)

- [x] `tests/test_models/test_table_data_model.py` - 48 comprehensive tests covering:
  - `parse_number()` decimal format parsing (US, European, scientific notation)
  - Basic model operations (data, headers, columns, rows)
  - Row operations (add, insert, remove, clear)
  - Column operations (add, remove, clear, sort, metadata)
  - Statistics calculations
  - FormulaEngine (i, i^2, sin, column references, random, constants)
  - Integration tests (workflow, export, large datasets)

### Medium-term (Next Week) - COMPLETED

- [x] 7. Full audit of vestigial code - DONE (January 2026)
  - Removed duplicate `src/table_window.py` (was copy of `src/widgets/table_window.py`)
  - Verified all widget files in `src/widgets/` are imported and used
  - Identified potentially unused signals (tableDataLoaded, tableColumnAdded, tableGraphLinked, graphCurvesUpdated) - kept for future use
- [x] 8. Remove unused widget implementations if confirmed - DONE
  - Basic `PlotWindow` and `TableWindow` kept as they're exported via `__init__.py`
  - Enhanced versions (`EnhancedPlotWindow`, `EnhancedTableWindow`) are actively used
  - `MapVisualizationWindow` is actively used
- [x] 9. Consolidate duplicate functionality - DONE
  - All QML content components (`TableContent`, `GraphContent`, `MapContent`) confirmed in use by `UnifiedWorkspace`
  - All QML window content components (`TableWindowContent`, `GraphWindowContent`) confirmed in use by `WindowManager`
- [x] 10. Update documentation - DONE

---

## Part 5: Testing Matrix

After each phase, run these verification tests:

### GraphCanvas Tests
```python
# Test 1: Import without crash
from src.widgets.qml_graph_canvas import QMLGraphCanvas

# Test 2: Create instance
canvas = QMLGraphCanvas()

# Test 3: Add curve
canvas.addCurve("Test", [1,2,3], [4,5,6], "#ff0000", 2.0)

# Test 4: Apply operation
canvas.applyCurveOperation(0, "derivative", {})
```

### TableDataModel Tests
```bash
# Run all 48 tests
python3 -m pytest tests/test_models/test_table_data_model.py -v
```

```python
# Test 1: Import with parse_number
from src.models.table_data_model import TableDataModel, FormulaEngine, parse_number

# Test 2: Decimal parsing (US and European formats)
assert parse_number("1.234") == 1.234    # US decimal
assert parse_number("1,234") == 1.234    # European decimal
assert parse_number("1.234,56") == 1234.56  # European thousands

# Test 3: Create with data
model = TableDataModel()
model.setTableData([[1, 2], [3, 4], [5, 6]], ['A', 'B'])

# Test 4: Row operations
model.insertRow(1)  # Insert at position 1
model.clearRow(1)   # Clear row 1
model.removeRow(1)  # Remove row 1

# Test 5: Column operations
model.addColumn("C", "units", "comment")
model.sortByColumn(0, True)   # Sort ascending
model.clearColumn(0)          # Clear column

# Test 6: Formula with row index
model.setColumnFormula(0, 'i^2')  # i = row index (1-based)

# Test 7: Formula with column reference
model.setColumnFormula(0, '[B] * 2')

# Test 8: Formula with math functions
model.setColumnFormula(0, 'sin(i * 0.1) + random()')

# Test 9: Statistics
stats = model.calculateColumnStatistics(0)
# Returns: {count, mean, std, min, max, median, sum}
```

### Integration Tests
```
1. Launch app
2. Create new table (View > New Table)
3. Verify table appears with empty state
4. Create new graph (View > New Graph)
5. Verify graph appears with matplotlib rendering
6. Link table to graph
7. Add data to table
8. Plot columns from table
```

---

## Part 6: Architecture Target State

After cleanup, the architecture should be:

```
User Interaction
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│                    QML Layer                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │ TableEntity │  │ GraphEntity │  │ MapEntity   │      │
│  │   (uses     │  │   (uses     │  │   (uses     │      │
│  │TableDataMdl)│  │GraphCanvas) │  │ MapCanvas)  │      │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘      │
└─────────┼────────────────┼────────────────┼─────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────┐
│                 Python Backend                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │TableDataMdl │  │QMLGraphCanv │  │QMLMapCanvas │      │
│  │(formulas,   │  │(matplotlib, │  │(matplotlib, │      │
│  │ statistics) │  │ operations) │  │ tools)      │      │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘      │
└─────────┼────────────────┼────────────────┼─────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────┐
│                   AppBackend                             │
│  - Table/Graph management                                │
│  - Linking and synchronization                           │
│  - Processing operations                                 │
│  - Signal emission to QML                                │
└─────────────────────────────────────────────────────────┘
```

**Key Principles:**
1. **One implementation per concept** - No duplicate table or graph implementations
2. **QML for UI, Python for logic** - Heavy processing in Python
3. **Clear ownership** - Each entity owns its model instance
4. **Signal-based communication** - Loose coupling between components

---

## Appendix: File Inventory

### Production-Ready (DO NOT MODIFY without review)
- `models/table_data_model.py` - ✅ Complete with full spreadsheet functionality:
  - `parse_number()` - Locale-aware decimal parsing (US/European)
  - `FormulaEngine` - Cell and column formulas with `i`, `random()`, math functions
  - Row operations: `addRow`, `insertRow`, `removeRow`, `clearRow`
  - Column operations: `addColumn`, `removeColumn`, `clearColumn`, `sortByColumn`
  - Statistics: `calculateColumnStatistics`, `integrateColumn`
  - 48 comprehensive tests in `tests/test_models/test_table_data_model.py`
- `models/spectral_data.py` - ✅ Complete
- `models/topography_data.py` - ✅ Complete
- `widgets/qml_map_canvas.py` - ✅ Complete (added componentComplete)
- `widgets/qml_profile_canvas.py` - ✅ Complete (added componentComplete)
- `widgets/qml_graph_canvas.py` - ✅ FIXED (removed notify= from Properties, added componentComplete)

### Fixed (December 2025)
- `qml/components/GraphEntity.qml` - ✅ FIXED (restored GraphCanvas, proper anchoring)
- `qml/components/TableEntity.qml` - ✅ FIXED with full spreadsheet features:
  - 3-tab interface (Data, Columns, Plot)
  - Formula bar with cell reference display
  - SciDAVis-style context menus (right-click cells, columns, rows)
  - Set Column Values dialog with formula support
  - Fill Column dialog (Row Numbers, Linear, Constant, Random)
  - Column configuration (name, unit, comment, formula)
  - Plot column selection with statistics
- `qml/components/MapEntity.qml` - ✅ FIXED (added anchors.fill: parent)

### Legacy (Keep for reference)
- `widgets/table_window.py` - Legacy floating window implementation
- `widgets/plot_window.py` - Legacy floating window implementation
- `widgets/enhanced_table_window.py` - Has useful FormulaEngine reference
- `widgets/enhanced_plot_window.py` - Has useful curve management reference

### Audit Results (January 2026)

**Files Removed:**
- `src/table_window.py` - Duplicate of `src/widgets/table_window.py` (removed)

**Files Confirmed In Use:**
- `qml/components/TableWindowContent.qml` - Used by WindowManager.createEnhancedTableWindow()
- `qml/components/GraphWindowContent.qml` - Used by WindowManager.createGraphWindow()
- `qml/components/TableContent.qml` - Used by UnifiedWorkspace.createTableEntityEmbed()
- `qml/components/GraphContent.qml` - Used by UnifiedWorkspace.createGraphEntityEmbed()
- `qml/components/MapContent.qml` - Used by UnifiedWorkspace.createMapEntityEmbed()

**Potentially Unused Signals (kept for future use):**
- `tableDataLoaded` - Defined and emitted but no QML handler
- `tableColumnAdded` - Defined and emitted but no QML handler
- `tableGraphLinked` - Defined and emitted but no QML handler
- `graphCurvesUpdated` - Defined and emitted but no QML handler
