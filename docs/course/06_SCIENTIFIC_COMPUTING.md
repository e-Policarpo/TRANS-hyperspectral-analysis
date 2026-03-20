# Module 6: Scientific Computing Integration

## Building Data Models, Tables, and Formula Engines

Scientific applications need robust data handling beyond simple UI widgets. This module teaches you how to build spreadsheet-like interfaces with pandas, create Qt data models for efficient display, and implement formula engines for user-defined calculations.

---

## Learning Objectives

By the end of this module, you will be able to:
- Implement `QAbstractTableModel` for efficient data display
- Integrate NumPy and Pandas with Qt/QML
- Build formula engines for spreadsheet calculations
- Handle locale-aware number parsing
- Create column metadata systems for scientific data

---

## 6.1 QAbstractTableModel: The Foundation

### Why Custom Models?

QML's TableView needs a data model to display tabular data. While simple `ListModel` works for small datasets, scientific applications often need:
- **Millions of cells** - Can't create QML objects for each
- **NumPy/Pandas integration** - Direct data access
- **Formulas** - Calculated columns
- **Metadata** - Units, comments, data types

`QAbstractTableModel` provides:
- Efficient data access (no QML object per cell)
- Role-based data display (text, alignment, colors)
- Edit support with validation
- Insertion/deletion notifications

### Basic Structure

```python
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex

class SimpleTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # 2D list or numpy array
        self._headers = []

    # REQUIRED: Row count
    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    # REQUIRED: Column count
    def columnCount(self, parent=QModelIndex()):
        return len(self._data[0]) if self._data else 0

    # REQUIRED: Data access
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row, col = index.row(), index.column()

        if role == Qt.DisplayRole:
            return str(self._data[row][col])

        return None

    # OPTIONAL: Headers
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal and section < len(self._headers):
                return self._headers[section]
            elif orientation == Qt.Vertical:
                return str(section + 1)  # Row numbers
        return None
```

### The Role System

Qt models use "roles" to return different aspects of data:

| Role | Purpose | Example |
|------|---------|---------|
| `Qt.DisplayRole` | Text to display | "42.5" |
| `Qt.EditRole` | Value for editing | 42.5 |
| `Qt.TextAlignmentRole` | Cell alignment | Qt.AlignRight |
| `Qt.BackgroundRole` | Cell background | QColor("#ffcccc") |
| `Qt.ForegroundRole` | Text color | QColor("#ff0000") |
| `Qt.ToolTipRole` | Hover tooltip | "Original value: 42.51" |

```python
def data(self, index, role=Qt.DisplayRole):
    row, col = index.row(), index.column()
    value = self._data[row][col]

    if role == Qt.DisplayRole:
        # Format for display
        if isinstance(value, float):
            if abs(value) < 0.001 or abs(value) > 10000:
                return f"{value:.4e}"  # Scientific notation
            return f"{value:.6g}"      # General format
        return str(value)

    elif role == Qt.EditRole:
        # Raw value for editing
        return value

    elif role == Qt.TextAlignmentRole:
        # Numbers right-aligned
        if isinstance(value, (int, float)):
            return Qt.AlignRight | Qt.AlignVCenter
        return Qt.AlignLeft | Qt.AlignVCenter

    return None
```

---

## 6.2 Editable Tables

### Enabling Editing

To make cells editable, implement `setData()` and `flags()`:

```python
def flags(self, index):
    """Specify which cells are editable"""
    if not index.isValid():
        return Qt.NoItemFlags
    return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

def setData(self, index, value, role=Qt.EditRole):
    """Handle cell edits"""
    if not index.isValid() or role != Qt.EditRole:
        return False

    row, col = index.row(), index.column()

    try:
        # Try to convert to number
        self._data[row][col] = float(value)
    except (ValueError, TypeError):
        # Keep as string
        self._data[row][col] = str(value)

    # Notify views that data changed
    self.dataChanged.emit(index, index, [Qt.DisplayRole])
    return True
```

### Row/Column Insertion

```python
def addRow(self):
    """Add a row at the end"""
    row_idx = len(self._data)

    # MUST call begin/end methods
    self.beginInsertRows(QModelIndex(), row_idx, row_idx)

    # Add empty row
    self._data.append([0.0] * self.columnCount())

    self.endInsertRows()

def removeRow(self, row_idx):
    """Remove a row"""
    if row_idx < 0 or row_idx >= len(self._data):
        return

    self.beginRemoveRows(QModelIndex(), row_idx, row_idx)
    del self._data[row_idx]
    self.endRemoveRows()
```

**Critical:** Always call `beginInsertRows`/`endInsertRows` or `beginRemoveRows`/`endRemoveRows` - views depend on these signals!

### Resetting the Model

When completely replacing data:

```python
def loadData(self, new_data):
    """Replace all data"""
    self.beginResetModel()  # Notify views to reset

    self._data = new_data

    self.endResetModel()    # Views will refresh
```

---

## 6.3 Pandas Integration

### The TableDataModel Class

TRANS-QML's `TableDataModel` uses pandas internally:

```python
import pandas as pd
import numpy as np

class TableDataModel(QAbstractTableModel):
    """
    QAbstractTableModel backed by pandas DataFrame.

    Benefits:
    - Efficient columnar storage
    - Built-in statistical functions
    - Easy import/export (CSV, Excel)
    """

    # Signals
    dataModified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = pd.DataFrame()
        self._column_metadata = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._data.columns) if not self._data.empty else 0

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row, col = index.row(), index.column()

        if role in (Qt.DisplayRole, Qt.EditRole):
            try:
                value = self._data.iloc[row, col]
                if pd.isna(value):
                    return ""
                if isinstance(value, float):
                    if abs(value) < 0.001 or abs(value) > 10000:
                        return f"{value:.4e}"
                    return f"{value:.6g}"
                return str(value)
            except (IndexError, KeyError):
                return ""

        return None
```

### Loading Data from Files

```python
@Slot(str)
def loadFromCsv(self, filepath):
    """Load data from CSV file"""
    self.beginResetModel()

    try:
        self._data = pd.read_csv(filepath)
        self._column_metadata = [
            ColumnMetadata(name=str(col))
            for col in self._data.columns
        ]
    except Exception as e:
        logger.error(f"CSV load error: {e}")
        self._data = pd.DataFrame()

    self.endResetModel()
    self.dataModified.emit()

@Slot(result='QVariant')
def toDataFrame(self):
    """Export as DataFrame (for Python use)"""
    return self._data.copy()

@Slot(result=list)
def toList(self):
    """Export as 2D list (for QML use)"""
    return self._data.values.tolist()
```

### Column Operations

```python
@Slot(str, list)
def addColumnWithData(self, name, data):
    """Add a new column with data"""
    col_idx = len(self._data.columns)

    self.beginInsertColumns(QModelIndex(), col_idx, col_idx)

    if self._data.empty:
        self._data = pd.DataFrame({name: data})
    else:
        # Adjust data length to match existing rows
        if len(data) < len(self._data):
            data = data + [0.0] * (len(self._data) - len(data))
        elif len(data) > len(self._data):
            data = data[:len(self._data)]
        self._data[name] = data

    self._column_metadata.append(ColumnMetadata(name=name))

    self.endInsertColumns()

@Slot(int, result=list)
def getColumnData(self, col_idx):
    """Get column as list (for graphs)"""
    if col_idx < 0 or col_idx >= len(self._data.columns):
        return []

    col = pd.to_numeric(self._data.iloc[:, col_idx], errors='coerce')
    return col.fillna(0).tolist()
```

---

## 6.4 Column Metadata System

Scientific data needs more than just values - units, comments, and data types:

### The ColumnMetadata Class

```python
from dataclasses import dataclass

@dataclass
class ColumnMetadata:
    """Metadata for a table column"""
    name: str
    unit: str = ""
    comment: str = ""
    formula: str = None    # Column-wide formula
    data_type: str = "numeric"  # "numeric", "text", "formula"
    color: str = ""        # Display color
```

### Displaying Metadata in Headers

```python
def headerData(self, section, orientation, role=Qt.DisplayRole):
    if role == Qt.DisplayRole:
        if orientation == Qt.Horizontal:
            if section < len(self._column_metadata):
                meta = self._column_metadata[section]
                if meta.unit:
                    return f"{meta.name} [{meta.unit}]"
                return meta.name
            return str(section)
        else:
            # Row numbers (1-based like spreadsheets)
            return str(section + 1)

    elif role == Qt.ToolTipRole and orientation == Qt.Horizontal:
        if section < len(self._column_metadata):
            meta = self._column_metadata[section]
            tooltip = f"Column: {meta.name}"
            if meta.unit:
                tooltip += f"\nUnit: {meta.unit}"
            if meta.comment:
                tooltip += f"\nComment: {meta.comment}"
            if meta.formula:
                tooltip += f"\nFormula: {meta.formula}"
            return tooltip

    return None
```

### Metadata Slots for QML

```python
@Slot(int, str, str, str)
def setColumnMetadata(self, col_idx, name, unit, comment):
    """Set column metadata from QML"""
    if col_idx < 0 or col_idx >= len(self._column_metadata):
        return

    old_name = self._column_metadata[col_idx].name
    self._column_metadata[col_idx].name = name
    self._column_metadata[col_idx].unit = unit
    self._column_metadata[col_idx].comment = comment

    # Update DataFrame column name
    if old_name != name:
        self._data = self._data.rename(columns={old_name: name})

    # Notify header change
    self.headerDataChanged.emit(Qt.Horizontal, col_idx, col_idx)

@Slot(int, result='QVariant')
def getColumnMetadata(self, col_idx):
    """Get column metadata as dict for QML"""
    if col_idx < 0 or col_idx >= len(self._column_metadata):
        return {}

    meta = self._column_metadata[col_idx]
    return {
        'name': meta.name,
        'unit': meta.unit,
        'comment': meta.comment,
        'formula': meta.formula or "",
        'data_type': meta.data_type
    }
```

---

## 6.5 Formula Engine

### Design Goals

Scientific users expect spreadsheet-like formulas:
- Cell references: `=A1 + B1`
- Column formulas: `=[A] * 2 + [B]`
- Functions: `=SUM(A1:A10)`, `=SQRT([A])`
- Row variable: `=i * 0.1` (row index)

### The FormulaEngine Class

```python
import re
import numpy as np

class FormulaEngine:
    """
    Formula engine for spreadsheet calculations.

    Supports:
    - Arithmetic: +, -, *, /, ^
    - Functions: SUM, AVG, MIN, MAX, SQRT, ABS, LOG, EXP, SIN, COS
    - Cell refs: A1, B2
    - Column refs: [A], [Column Name]
    - Range refs: A1:A10
    """

    def __init__(self, data_getter):
        """
        Parameters:
            data_getter: Callable(row, col) -> value
        """
        self.get_cell = data_getter
        self._column_names = []

    def set_column_names(self, names):
        """Set column names for [Name] references"""
        self._column_names = names
```

### Evaluating Cell Formulas

```python
def evaluate_cell(self, formula, row, col):
    """Evaluate a single cell formula like =A1+B1"""
    if not formula.startswith('='):
        return formula

    try:
        expr = formula[1:].strip()
        expr = self._replace_references(expr, row)
        return self._safe_eval(expr)
    except Exception as e:
        logger.error(f"Formula error at ({row}, {col}): {e}")
        return "#ERROR"

def _replace_references(self, expr, current_row):
    """Replace cell references with values"""
    expr = expr.upper()

    # Pattern for cell references: A1, B2, AA10
    cell_pattern = r'([A-Z]+)(\d+)'

    def replace_cell(match):
        col_letters = match.group(1)
        row_num = int(match.group(2)) - 1  # 0-indexed

        # Convert letters to index (A=0, B=1, ..., AA=26)
        col_idx = 0
        for i, letter in enumerate(reversed(col_letters)):
            col_idx += (ord(letter) - ord('A') + 1) * (26 ** i)
        col_idx -= 1

        val = self.get_cell(row_num, col_idx)
        try:
            return str(float(val)) if val not in ("", None) else "0"
        except (ValueError, TypeError):
            return "0"

    expr = re.sub(cell_pattern, replace_cell, expr)

    # Process functions
    expr = self._process_functions(expr)

    return expr
```

### Column Formulas with NumPy

Column formulas operate on entire columns at once using NumPy:

```python
def evaluate_column(self, formula, num_rows):
    """
    Evaluate a column formula for all rows.

    Uses:
    - [A], [B], or [Column Name] for column references
    - i for row index (1-based)
    - Standard math functions
    """
    try:
        expr = formula

        # Find column references [A], [Column Name], etc.
        col_pattern = r'\[([^\]]+)\]'
        col_refs = re.findall(col_pattern, expr)

        # Build arrays for each referenced column
        arrays = {}
        for ref in col_refs:
            col_idx = self._get_column_index(ref)
            if col_idx is not None:
                col_data = []
                for row in range(num_rows):
                    val = self.get_cell(row, col_idx)
                    try:
                        col_data.append(float(val) if val != "" else 0.0)
                    except (ValueError, TypeError):
                        col_data.append(0.0)
                arrays[ref] = np.array(col_data)

                # Replace [ref] with safe variable name
                safe_name = f"_col_{col_idx}"
                expr = expr.replace(f"[{ref}]", safe_name)

        # Create row index array (1-based)
        row_indices = np.arange(1, num_rows + 1, dtype=np.float64)

        # Build evaluation namespace
        namespace = {
            '__builtins__': {},
            'np': np,
            'sin': np.sin, 'cos': np.cos, 'tan': np.tan,
            'sqrt': np.sqrt, 'abs': np.abs,
            'log': np.log, 'log10': np.log10, 'exp': np.exp,
            'mean': np.mean, 'std': np.std, 'sum': np.sum,
            'min': np.min, 'max': np.max,
            'pi': np.pi, 'e': np.e,
            'i': row_indices,  # Row index variable
            'random': lambda: np.random.random(num_rows),
        }

        # Add column arrays
        for ref, arr in arrays.items():
            col_idx = self._get_column_index(ref)
            namespace[f"_col_{col_idx}"] = arr

        # Convert ^ to ** for power
        expr = expr.replace('^', '**')

        result = eval(expr, namespace)

        # Ensure result is array
        if np.isscalar(result):
            result = np.full(num_rows, result)

        return np.array(result, dtype=np.float64)

    except Exception as e:
        logger.error(f"Column formula error: {e}")
        return np.zeros(num_rows)
```

### Using Formulas in the Model

```python
@Slot(int, str)
def setColumnFormula(self, col_idx, formula):
    """Set a column-wide formula"""
    if col_idx < 0 or col_idx >= len(self._column_metadata):
        return

    self._column_metadata[col_idx].formula = formula

    if formula:
        try:
            # Evaluate formula for all rows
            values = self._formula_engine.evaluate_column(
                formula, len(self._data)
            )

            # Update column
            col_name = self._data.columns[col_idx]
            self._data[col_name] = values

            # Notify views
            top = self.index(0, col_idx)
            bottom = self.index(len(self._data) - 1, col_idx)
            self.dataChanged.emit(top, bottom, [Qt.DisplayRole])

        except Exception as e:
            logger.error(f"Formula error: {e}")
```

### QML Usage

```qml
// Set column formula from QML
Button {
    text: "Apply Formula"
    onClicked: {
        // Calculate column C = A * B
        tableModel.setColumnFormula(2, "[A] * [B]")
    }
}

Button {
    text: "Create X Axis"
    onClicked: {
        // Create evenly spaced X values
        tableModel.setColumnFormula(0, "i * 0.1")
    }
}

Button {
    text: "Normalize"
    onClicked: {
        // Normalize column B by its max
        tableModel.setColumnFormula(1, "[B] / max([B])")
    }
}
```

---

## 6.6 Locale-Aware Number Parsing

European users write "1,5" for 1.5, US users write "1,500" for 1500. Your application should handle both:

```python
def parse_number(value):
    """
    Parse a number string supporting both comma and dot decimal separator.

    Handles:
    - "1.234" (dot decimal)
    - "1,234" (comma decimal - European)
    - "1.234,56" (European thousands with comma decimal)
    - "1,234.56" (US thousands with dot decimal)
    - Scientific: "1.23e-4", "1,23e-4"
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"Cannot parse: {value}")

    s = value.strip()

    # Handle scientific notation
    if 'e' in s.lower():
        s = s.replace(',', '.')
        return float(s)

    num_dots = s.count('.')
    num_commas = s.count(',')

    if num_dots == 0 and num_commas == 0:
        # Plain integer: "1234"
        return float(s)

    elif num_dots == 0 and num_commas == 1:
        # Comma is decimal (European): "1,234" -> 1.234
        return float(s.replace(',', '.'))

    elif num_dots == 1 and num_commas == 0:
        # Dot is decimal (US): "1.234" -> 1.234
        return float(s)

    elif num_dots > 1 and num_commas == 1:
        # European with thousands: "1.234.567,89" -> 1234567.89
        return float(s.replace('.', '').replace(',', '.'))

    elif num_commas > 1 and num_dots == 1:
        # US with thousands: "1,234,567.89" -> 1234567.89
        return float(s.replace(',', ''))

    elif num_dots == 1 and num_commas == 1:
        # Ambiguous - check position
        dot_pos = s.rfind('.')
        comma_pos = s.rfind(',')
        if comma_pos > dot_pos:
            # Comma is decimal: "1.234,56" -> 1234.56
            return float(s.replace('.', '').replace(',', '.'))
        else:
            # Dot is decimal: "1,234.56" -> 1234.56
            return float(s.replace(',', ''))

    # Fallback
    return float(s.replace(',', '.'))
```

### Using in setData

```python
def setData(self, index, value, role=Qt.EditRole):
    if not index.isValid() or role != Qt.EditRole:
        return False

    row, col = index.row(), index.column()
    str_value = str(value).strip()

    # Check if it's a formula
    if str_value.startswith('='):
        self._cell_formulas[(row, col)] = str_value
    else:
        # Try locale-aware number parsing
        try:
            self._data.iloc[row, col] = parse_number(str_value)
        except (ValueError, TypeError):
            # Keep as string
            self._data.iloc[row, col] = str_value

    self.dataChanged.emit(index, index, [Qt.DisplayRole])
    return True
```

---

## 6.7 Statistics and Integration

### Column Statistics

```python
@Slot(int, result='QVariant')
def calculateColumnStatistics(self, col_idx):
    """Calculate statistics for a column"""
    if col_idx < 0 or col_idx >= len(self._data.columns):
        return {}

    try:
        col_data = pd.to_numeric(
            self._data.iloc[:, col_idx], errors='coerce'
        )
        col_data = col_data.dropna()

        if len(col_data) == 0:
            return {'error': 'No numeric data'}

        return {
            'count': len(col_data),
            'mean': float(col_data.mean()),
            'std': float(col_data.std()),
            'min': float(col_data.min()),
            'max': float(col_data.max()),
            'median': float(col_data.median()),
            'sum': float(col_data.sum())
        }

    except Exception as e:
        logger.error(f"Statistics error: {e}")
        return {'error': str(e)}
```

### Numerical Integration

```python
@Slot(int, int, result=float)
def integrateColumn(self, y_col_idx, x_col_idx=0):
    """Integrate a column using trapezoidal rule"""
    if y_col_idx < 0 or y_col_idx >= len(self._data.columns):
        return 0.0

    try:
        x = pd.to_numeric(
            self._data.iloc[:, x_col_idx], errors='coerce'
        ).values
        y = pd.to_numeric(
            self._data.iloc[:, y_col_idx], errors='coerce'
        ).values

        # Remove NaN values
        mask = ~(np.isnan(x) | np.isnan(y))
        x, y = x[mask], y[mask]

        if len(x) < 2:
            return 0.0

        return float(np.trapz(y, x))

    except Exception as e:
        logger.error(f"Integration error: {e}")
        return 0.0
```

### QML Usage for Statistics

```qml
Button {
    text: "Calculate Statistics"
    onClicked: {
        var stats = tableModel.calculateColumnStatistics(selectedColumn)
        if (!stats.error) {
            statsLabel.text = `Mean: ${stats.mean.toFixed(3)}
Std: ${stats.std.toFixed(3)}
Min: ${stats.min.toFixed(3)}
Max: ${stats.max.toFixed(3)}
Count: ${stats.count}`
        }
    }
}

Button {
    text: "Integrate"
    onClicked: {
        var integral = tableModel.integrateColumn(1, 0)  // Y column 1, X column 0
        integralLabel.text = `∫ = ${integral.toExponential(4)}`
    }
}
```

---

## 6.8 Connecting Tables to Graphs

A powerful feature is linking table columns to graph curves:

### Getting Plot Data

```python
@Slot(int, int, result=list)
def getPlotData(self, x_col, y_col):
    """Get X and Y data for plotting"""
    x_data = self.getColumnData(x_col)
    y_data = self.getColumnData(y_col)
    return [x_data, y_data]
```

### QML Integration

```qml
import TransWidgets 1.0

Item {
    TableView {
        id: tableView
        model: tableModel

        // ... column delegates
    }

    ProfileCanvas {
        id: graphPlot
    }

    Button {
        text: "Plot Column"
        onClicked: {
            var data = tableModel.getPlotData(0, 1)  // X=col0, Y=col1
            graphPlot.setProfileData(data[0], data[1])

            var meta = tableModel.getColumnMetadata(1)
            graphPlot.setLabels(
                tableModel.getColumnName(0),
                meta.name + (meta.unit ? ` [${meta.unit}]` : "")
            )
        }
    }
}
```

---

## 6.9 Complete Example: Scientific Table Widget

Here's a complete QML component that integrates all the features:

```qml
// ScientificTable.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import TransWidgets 1.0

Item {
    id: root

    property alias model: tableView.model
    signal plotRequested(int xCol, int yCol)

    ColumnLayout {
        anchors.fill: parent
        spacing: 4

        // Toolbar
        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Add Column"
                onClicked: columnDialog.open()
            }

            Button {
                text: "Add Row"
                onClicked: model.addRow()
            }

            ToolSeparator {}

            Button {
                text: "Statistics"
                enabled: tableView.currentColumn >= 0
                onClicked: {
                    var stats = model.calculateColumnStatistics(tableView.currentColumn)
                    statsPopup.show(stats)
                }
            }

            Button {
                text: "Formula"
                enabled: tableView.currentColumn >= 0
                onClicked: formulaDialog.open()
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Plot"
                onClicked: plotDialog.open()
            }
        }

        // Table
        TableView {
            id: tableView
            Layout.fillWidth: true
            Layout.fillHeight: true

            property int currentColumn: -1

            columnWidthProvider: function(column) { return 100 }
            rowHeightProvider: function(row) { return 25 }

            delegate: Rectangle {
                color: selected ? "#3d5a80" : (row % 2 === 0 ? "#2a2a2a" : "#323232")

                required property bool selected
                required property bool current

                TextInput {
                    anchors.fill: parent
                    anchors.margins: 4
                    text: display
                    color: "#ffffff"
                    horizontalAlignment: Text.AlignRight

                    onEditingFinished: {
                        model.edit = text
                    }
                }
            }

            // Header
            HorizontalHeaderView {
                id: horizontalHeader
                syncView: tableView
                anchors.left: tableView.left

                delegate: Rectangle {
                    color: "#1a1a1a"
                    border.color: "#444444"

                    Text {
                        anchors.centerIn: parent
                        text: display
                        color: "#cccccc"
                        font.bold: true
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: tableView.currentColumn = index
                    }
                }
            }
        }

        // Status bar
        RowLayout {
            Layout.fillWidth: true

            Label {
                text: `${model.rows} rows × ${model.columns} columns`
                color: "#888888"
            }

            Item { Layout.fillWidth: true }

            Label {
                id: statusLabel
                color: "#888888"
            }
        }
    }

    // Formula dialog
    Dialog {
        id: formulaDialog
        title: "Column Formula"
        standardButtons: Dialog.Ok | Dialog.Cancel

        ColumnLayout {
            TextField {
                id: formulaField
                placeholderText: "[A] * 2 + sin([B])"
                Layout.preferredWidth: 300
            }

            Label {
                text: "Variables: [A], [B], ..., [ColumnName], i (row index)"
                color: "#888888"
                font.pixelSize: 11
            }
        }

        onAccepted: {
            model.setColumnFormula(tableView.currentColumn, formulaField.text)
        }
    }

    // Plot dialog
    Dialog {
        id: plotDialog
        title: "Plot Columns"
        standardButtons: Dialog.Ok | Dialog.Cancel

        GridLayout {
            columns: 2

            Label { text: "X Column:" }
            ComboBox {
                id: xColCombo
                model: root.model.getColumnNames()
            }

            Label { text: "Y Column:" }
            ComboBox {
                id: yColCombo
                model: root.model.getColumnNames()
            }
        }

        onAccepted: {
            root.plotRequested(xColCombo.currentIndex, yColCombo.currentIndex)
        }
    }
}
```

---

## 6.10 Summary

### Key Concepts

1. **QAbstractTableModel** - Efficient Qt model for large datasets
2. **Role system** - Different data representations (display, edit, tooltip)
3. **Pandas integration** - Store data in DataFrames for scientific operations
4. **Column metadata** - Units, comments, formulas per column
5. **Formula engine** - Support cell and column formulas
6. **Locale-aware parsing** - Handle both comma and dot decimals

### Best Practices

| Do | Don't |
|----|-------|
| Use begin/end methods for row/column changes | Modify data without notification |
| Store data in pandas/numpy | Create QML objects for each cell |
| Validate in setData | Accept any value |
| Support formulas starting with = | Treat all text as data |
| Parse numbers locale-aware | Assume US number format |

---

## Exercises

### Exercise 6.1: Basic Model
Create a simple QAbstractTableModel that displays a numpy array with row/column headers.

### Exercise 6.2: Editable Table
Add editing support with validation (numbers only in numeric columns).

### Exercise 6.3: Statistics Panel
Create a QML component that displays column statistics in real-time as users select columns.

### Exercise 6.4: CSV Import/Export
Add methods to load from and save to CSV files with proper encoding.

### Exercise 6.5: Formula Expansion
Extend the formula engine with additional functions (AVERAGE, STDEV, PERCENTILE).

---

## Next Steps

In **Module 7: Advanced UI Patterns**, you'll learn:
- Floating/dockable windows
- Workspace management
- Theme systems and styling
- Context menus and drag-and-drop

---

*Module 6 of 8 | TRANS-QML Course*
