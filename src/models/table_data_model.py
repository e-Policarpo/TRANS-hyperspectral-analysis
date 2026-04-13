"""
Table Data Model - QAbstractTableModel with formula support for QML TableView
Provides spreadsheet functionality with column metadata, formulas, and statistics.
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
import pandas as pd
import re
import logging
from typing import Optional, List, Dict, Any, Tuple, Union
from dataclasses import dataclass, field

from PySide6.QtCore import (
    Qt, Signal, Slot, Property, QAbstractTableModel, QModelIndex, QObject
)

logger = logging.getLogger(__name__)


def parse_number(value: str) -> float:
    """
    Parse a number string supporting both comma and dot as decimal separator.

    Handles:
    - "1.234" (dot decimal)
    - "1,234" (comma decimal - European style)
    - "1.234,56" (European thousands with comma decimal)
    - "1,234.56" (US thousands with dot decimal)
    - Scientific notation: "1.23e-4", "1,23e-4"

    Returns:
    --------
    float: Parsed number

    Raises:
    -------
    ValueError: If string cannot be parsed as number
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"Cannot parse: {value}")

    s = value.strip()

    # Handle scientific notation with comma
    if 'e' in s.lower():
        s = s.replace(',', '.')
        return float(s)

    # Count dots and commas
    num_dots = s.count('.')
    num_commas = s.count(',')

    if num_dots == 0 and num_commas == 0:
        # Plain integer
        return float(s)
    elif num_dots == 0 and num_commas == 1:
        # Comma is decimal separator (European): "1,234" -> 1.234
        return float(s.replace(',', '.'))
    elif num_dots == 1 and num_commas == 0:
        # Dot is decimal separator (US): "1.234" -> 1.234
        return float(s)
    elif num_dots > 1 and num_commas == 1:
        # European format with thousands: "1.234.567,89" -> 1234567.89
        return float(s.replace('.', '').replace(',', '.'))
    elif num_commas > 1 and num_dots == 1:
        # US format with thousands: "1,234,567.89" -> 1234567.89
        return float(s.replace(',', ''))
    elif num_dots == 1 and num_commas == 1:
        # Ambiguous - check position
        dot_pos = s.rfind('.')
        comma_pos = s.rfind(',')
        if comma_pos > dot_pos:
            # Comma is decimal (European): "1.234,56" -> 1234.56
            return float(s.replace('.', '').replace(',', '.'))
        else:
            # Dot is decimal (US): "1,234.56" -> 1234.56
            return float(s.replace(',', ''))
    else:
        # Try simple replace and parse
        return float(s.replace(',', '.'))


@dataclass
class ColumnMetadata:
    """Metadata for a table column"""
    name: str
    unit: str = ""
    comment: str = ""
    formula: Optional[str] = None  # Column-wide formula (e.g., "[A] * 2")
    data_type: str = "numeric"  # "numeric", "text", "formula"
    color: str = ""  # Optional display color


class FormulaEngine:
    """
    Formula engine for spreadsheet calculations.

    Supports:
    - Basic arithmetic: +, -, *, /, ^
    - Functions: SUM, AVG, MIN, MAX, COUNT, SQRT, ABS, LOG, EXP, SIN, COS, TAN
    - Cell references: A1, B2, etc.
    - Column references: [A], [Column Name]
    - Range references: A1:A10
    - Statistical: MEAN, STD, INTEGRATE
    """

    def __init__(self, data_getter):
        """
        Initialize formula engine.

        Parameters:
        -----------
        data_getter : callable
            Function that takes (row, col) and returns value
        """
        self.get_cell = data_getter
        self._column_names: List[str] = []

    def set_column_names(self, names: List[str]):
        """Set column names for [Name] references"""
        self._column_names = names

    def evaluate_cell(self, formula: str, row: int, col: int) -> Any:
        """Evaluate a cell formula"""
        if not formula.startswith('='):
            return formula

        try:
            expr = formula[1:].strip()
            expr = self._replace_references(expr, row)
            return self._safe_eval(expr)
        except Exception as e:
            logger.error(f"Formula error at ({row}, {col}): {e}")
            return f"#ERROR"

    def evaluate_column(self, formula: str, num_rows: int) -> np.ndarray:
        """
        Evaluate a column formula for all rows.

        Column formulas use:
        - [A], [B], or [Column Name] for column references
        - i for row index (1-based, like in spreadsheets)
        - random() for random numbers
        - Standard math functions: sin, cos, sqrt, exp, log, etc.
        """
        try:
            # Parse column references
            expr = formula
            result = np.zeros(num_rows)

            # Support col(X) syntax — convert to [X] before processing
            expr = re.sub(r'col\(([^)]+)\)', r'[\1]', expr)

            # Replace column references with array operations
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
                            # Use parse_number for locale-aware parsing
                            col_data.append(parse_number(str(val)) if val != "" else 0.0)
                        except (ValueError, TypeError):
                            col_data.append(0.0)
                    arrays[ref] = np.array(col_data)
                    # Replace [ref] with safe variable name
                    safe_name = f"_col_{col_idx}"
                    expr = expr.replace(f"[{ref}]", safe_name)

            # Create row index array (1-based for user friendliness)
            row_indices = np.arange(1, num_rows + 1, dtype=np.float64)

            # Build namespace for evaluation
            namespace = {
                '__builtins__': {},
                'np': np,
                'sin': np.sin,
                'cos': np.cos,
                'tan': np.tan,
                'sqrt': np.sqrt,
                'abs': np.abs,
                'log': np.log,
                'log10': np.log10,
                'exp': np.exp,
                'mean': np.mean,
                'std': np.std,
                'sum': np.sum,
                'min': np.min,
                'max': np.max,
                'pi': np.pi,
                'e': np.e,
                # Row index variable (1-based)
                'i': row_indices,
                # Random function that returns array
                'random': lambda: np.random.random(num_rows),
            }

            # Add column arrays
            for ref, arr in arrays.items():
                col_idx = self._get_column_index(ref)
                namespace[f"_col_{col_idx}"] = arr

            # Handle random() function call - replace with array
            if 'random()' in expr:
                expr = expr.replace('random()', '_random_arr')
                namespace['_random_arr'] = np.random.random(num_rows)

            # Convert ^ to ** for power operation
            expr = expr.replace('^', '**')

            result = eval(expr, namespace)

            if np.isscalar(result):
                result = np.full(num_rows, result)

            return np.array(result, dtype=np.float64)

        except Exception as e:
            logger.error(f"Column formula error: {e}")
            return np.zeros(num_rows)

    def _get_column_index(self, ref: str) -> Optional[int]:
        """Get column index from reference (letter or name)"""
        # Check if it's a single letter (A, B, C, ...)
        if len(ref) == 1 and ref.isalpha():
            return ord(ref.upper()) - ord('A')

        # Check if it's column letters (AA, AB, ...)
        if ref.isalpha():
            idx = 0
            for i, letter in enumerate(reversed(ref.upper())):
                idx += (ord(letter) - ord('A') + 1) * (26 ** i)
            return idx - 1

        # Check if it's a column name
        if ref in self._column_names:
            return self._column_names.index(ref)

        return None

    def _replace_references(self, expr: str, current_row: int) -> str:
        """Replace cell references with values"""
        expr = expr.upper()

        # Replace cell references (A1, B2, etc.)
        cell_pattern = r'([A-Z]+)(\d+)'

        def replace_cell(match):
            col_letters = match.group(1)
            row_num = int(match.group(2)) - 1

            col_idx = 0
            for i, letter in enumerate(reversed(col_letters)):
                col_idx += (ord(letter) - ord('A') + 1) * (26 ** i)
            col_idx -= 1

            val = self.get_cell(row_num, col_idx)
            try:
                # Use parse_number for locale-aware parsing
                return str(parse_number(str(val))) if val not in ("", None) else "0"
            except (ValueError, TypeError):
                return "0"

        expr = re.sub(cell_pattern, replace_cell, expr)

        # Process functions
        expr = self._process_functions(expr)

        return expr

    def _process_functions(self, expr: str) -> str:
        """Process spreadsheet functions"""
        # Range functions
        for func_name, np_func in [('SUM', 'np.sum'), ('AVG', 'np.mean'),
                                    ('MIN', 'np.min'), ('MAX', 'np.max'),
                                    ('COUNT', 'len'), ('STD', 'np.std')]:
            expr = self._process_range_function(expr, func_name, np_func)

        # Math functions
        replacements = [
            ('SQRT(', 'np.sqrt('), ('ABS(', 'np.abs('),
            ('LOG(', 'np.log('), ('EXP(', 'np.exp('),
            ('SIN(', 'np.sin('), ('COS(', 'np.cos('),
            ('TAN(', 'np.tan('), ('MEAN(', 'np.mean('),
        ]
        for old, new in replacements:
            expr = expr.replace(old, new)

        # Power operator
        expr = expr.replace('^', '**')

        return expr

    def _process_range_function(self, expr: str, func_name: str, np_func: str) -> str:
        """Process range functions like SUM(A1:A10)"""
        pattern = f'{func_name}\\(([A-Z]+)(\\d+):([A-Z]+)(\\d+)\\)'

        def replace_func(match):
            start_col_letters = match.group(1)
            start_row = int(match.group(2)) - 1
            end_col_letters = match.group(3)
            end_row = int(match.group(4)) - 1

            start_col = 0
            for i, letter in enumerate(reversed(start_col_letters)):
                start_col += (ord(letter) - ord('A') + 1) * (26 ** i)
            start_col -= 1

            end_col = 0
            for i, letter in enumerate(reversed(end_col_letters)):
                end_col += (ord(letter) - ord('A') + 1) * (26 ** i)
            end_col -= 1

            values = []
            for row in range(start_row, end_row + 1):
                for col in range(start_col, end_col + 1):
                    val = self.get_cell(row, col)
                    try:
                        # Use parse_number for locale-aware parsing
                        values.append(parse_number(str(val)) if val not in ("", None) else 0)
                    except (ValueError, TypeError):
                        pass

            return f"{np_func}({values})"

        return re.sub(pattern, replace_func, expr)

    def _safe_eval(self, expr: str) -> Any:
        """Safely evaluate an expression"""
        namespace = {
            '__builtins__': {},
            'np': np,
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'len': len,
        }
        return eval(expr, namespace)


class TableDataModel(QAbstractTableModel):
    """
    QAbstractTableModel for use with QML TableView.

    Provides:
    - Editable cells with formula support
    - Column metadata (name, unit, comment)
    - Column-wide formulas
    - Statistics calculation
    - Add/remove columns
    - Integration with graph windows
    """

    # Signals
    columnAdded = Signal(int, str, arguments=['index', 'name'])
    columnRemoved = Signal(int, arguments=['index'])
    columnMetadataChanged = Signal(int, arguments=['index'])
    dataModified = Signal()
    statisticsCalculated = Signal(int, 'QVariant', arguments=['column', 'stats'])
    rowsChanged = Signal()
    columnsChanged = Signal()
    isEmptyChanged = Signal()
    dataRevisionChanged = Signal()
    displayFormatChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Data storage
        self._data: pd.DataFrame = pd.DataFrame()
        self._column_metadata: List[ColumnMetadata] = []
        self._cell_formulas: Dict[Tuple[int, int], str] = {}

        # Formula engine
        self._formula_engine = FormulaEngine(self._get_raw_cell)

        # Table ID for linking
        self._table_id: str = ""

        # Linked graph
        self._linked_graph_id: Optional[str] = None

        # Revision counter for QML data-binding refresh
        self._data_revision: int = 0

        # Display format: "auto" (current behavior), "scientific", "decimal"
        self._display_format: str = "auto"
        self._decimal_places: int = 6

        # Undo stack: list of (DataFrame snapshot, metadata snapshot, formulas snapshot)
        self._undo_stack: List[Tuple[pd.DataFrame, List[ColumnMetadata], Dict]] = []
        self._max_undo: int = 50
        self._batch_mode: bool = False  # suppress per-cell undo during bulk ops

    # =========================================================================
    # QAbstractTableModel required methods
    # =========================================================================

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._data.columns) if not self._data.empty else 0

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row, col = index.row(), index.column()

        if role == Qt.DisplayRole or role == Qt.EditRole:
            # Check for cell formula
            if (row, col) in self._cell_formulas:
                if role == Qt.EditRole:
                    return self._cell_formulas[(row, col)]
                else:
                    # Evaluate formula for display
                    formula = self._cell_formulas[(row, col)]
                    return self._formula_engine.evaluate_cell(formula, row, col)

            # Return raw value
            try:
                value = self._data.iloc[row, col]
                if pd.isna(value):
                    return ""
                if isinstance(value, float):
                    return self._format_float(value)
                return str(value)
            except (IndexError, KeyError):
                return ""

        elif role == Qt.TextAlignmentRole:
            return Qt.AlignRight | Qt.AlignVCenter

        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.EditRole:
            return False

        row, col = index.row(), index.column()

        try:
            if not self._batch_mode:
                self._save_undo()
            str_value = str(value).strip()

            # Check if it's a formula
            if str_value.startswith('='):
                self._cell_formulas[(row, col)] = str_value
            else:
                # Remove any existing formula
                if (row, col) in self._cell_formulas:
                    del self._cell_formulas[(row, col)]

                # Try to convert to numeric (supports both , and . as decimal separator)
                try:
                    self._data.iloc[row, col] = parse_number(str_value)
                except (ValueError, TypeError):
                    # parse_number failed — try evaluating as arithmetic expression
                    result = self._try_eval_expression(str_value)
                    if result is not None:
                        self._data.iloc[row, col] = result
                    else:
                        self._data.iloc[row, col] = str_value

            self.dataChanged.emit(index, index, [Qt.DisplayRole])
            self._bump_revision()
            self.dataModified.emit()
            return True

        except Exception as e:
            logger.error(f"setData error: {e}")
            return False

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.DisplayRole) -> Any:
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                if section < len(self._column_metadata):
                    meta = self._column_metadata[section]
                    if meta.unit:
                        return f"{meta.name} [{meta.unit}]"
                    return meta.name
                return self._data.columns[section] if section < len(self._data.columns) else ""
            else:
                return str(section + 1)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    # =========================================================================
    # Helper methods
    # =========================================================================

    def _get_raw_cell(self, row: int, col: int) -> Any:
        """Get raw cell value (for formula engine)"""
        try:
            if (row, col) in self._cell_formulas:
                # Recursively evaluate formulas
                return self._formula_engine.evaluate_cell(
                    self._cell_formulas[(row, col)], row, col
                )
            return self._data.iloc[row, col]
        except (IndexError, KeyError):
            return 0

    def _format_float(self, value: float) -> str:
        """Format a float according to current display settings."""
        if value == 0.0:
            if self._display_format == "decimal":
                return f"{value:.{self._decimal_places}f}"
            return "0"

        fmt = self._display_format
        dp = self._decimal_places
        if fmt == "scientific":
            return f"{value:.{dp}e}"
        elif fmt == "decimal":
            return f"{value:.{dp}f}"
        else:  # auto
            if abs(value) < 0.001 or abs(value) > 10000:
                return f"{value:.4e}"
            return f"{value:.6g}"

    def _try_eval_expression(self, expr: str) -> Optional[float]:
        """Try to evaluate a string as a simple arithmetic expression.
        Returns float result or None if it's not a valid expression."""
        # Only attempt if it contains arithmetic operators
        if not any(op in expr for op in ['+', '-', '*', '/', '^', '(', ')']):
            return None
        # Don't eval things that look like plain text
        if any(c.isalpha() and c not in ('e', 'E') for c in expr):
            return None
        try:
            safe_expr = expr.replace('^', '**')
            result = eval(safe_expr, {"__builtins__": {}}, {})
            return float(result)
        except Exception:
            return None

    def _save_undo(self):
        """Save current state to undo stack."""
        import copy
        snapshot = (
            self._data.copy(),
            copy.deepcopy(self._column_metadata),
            dict(self._cell_formulas),
        )
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)

    @Slot()
    def undo(self):
        """Restore previous state from undo stack."""
        if not self._undo_stack:
            return

        data, metadata, formulas = self._undo_stack.pop()

        self.beginResetModel()
        self._data = data
        self._column_metadata = metadata
        self._cell_formulas = formulas
        self._update_formula_engine_columns()
        self.endResetModel()

        self._emit_size_changed()
        self.dataModified.emit()

    @Slot(result=bool)
    def canUndo(self) -> bool:
        return len(self._undo_stack) > 0

    def _update_formula_engine_columns(self):
        """Update formula engine with current column names"""
        names = [meta.name for meta in self._column_metadata]
        self._formula_engine.set_column_names(names)

    # =========================================================================
    # Data loading/saving
    # =========================================================================

    @Slot(list, list)
    def setTableData(self, data: List[List], headers: List[str] = None):
        """Set table data from 2D list"""
        self.beginResetModel()

        if not data:
            self._data = pd.DataFrame()
            self._column_metadata = []
        else:
            self._data = pd.DataFrame(data)

            if headers and len(headers) == len(self._data.columns):
                self._data.columns = headers
                self._column_metadata = [ColumnMetadata(name=h) for h in headers]
            else:
                # Auto-generate column names (A, B, C, ...)
                col_names = [self._index_to_letters(i) for i in range(len(self._data.columns))]
                self._data.columns = col_names
                self._column_metadata = [ColumnMetadata(name=n) for n in col_names]

        self._cell_formulas.clear()
        self._update_formula_engine_columns()
        self.endResetModel()
        self._emit_size_changed()
        self.dataModified.emit()

    @Slot('QVariant', list)
    def loadFromDataFrame(self, df: pd.DataFrame, metadata: List[Dict] = None):
        """Load data from pandas DataFrame"""
        self.beginResetModel()

        self._data = df.copy()
        self._cell_formulas.clear()

        if metadata and len(metadata) == len(df.columns):
            self._column_metadata = [
                ColumnMetadata(**m) if isinstance(m, dict) else m
                for m in metadata
            ]
        else:
            self._column_metadata = [
                ColumnMetadata(name=str(col)) for col in df.columns
            ]

        self._update_formula_engine_columns()
        self.endResetModel()
        self._emit_size_changed()
        self.dataModified.emit()

    @Slot(result='QVariant')
    def toDataFrame(self) -> pd.DataFrame:
        """Export data as DataFrame"""
        return self._data.copy()

    @Slot(result=list)
    def toList(self) -> List[List]:
        """Export data as 2D list"""
        return self._data.values.tolist()

    def _index_to_letters(self, idx: int) -> str:
        """Convert column index to letters (A, B, ..., Z, AA, AB, ...)"""
        result = ""
        idx += 1
        while idx > 0:
            idx -= 1
            result = chr(ord('A') + idx % 26) + result
            idx //= 26
        return result

    # =========================================================================
    # Column management
    # =========================================================================

    @Slot(str, str, str)
    def addColumn(self, name: str, unit: str = "", comment: str = ""):
        """Add a new empty column"""
        if not self._batch_mode:
            self._save_undo()
        col_idx = len(self._data.columns)

        self.beginInsertColumns(QModelIndex(), col_idx, col_idx)

        # Add column to DataFrame
        if self._data.empty:
            self._data = pd.DataFrame({name: []})
        else:
            self._data[name] = 0.0

        # Add metadata
        self._column_metadata.append(ColumnMetadata(name=name, unit=unit, comment=comment))
        self._update_formula_engine_columns()

        self.endInsertColumns()
        self._emit_size_changed()
        self.columnAdded.emit(col_idx, name)
        self.dataModified.emit()

    @Slot(str, list)
    def addColumnWithData(self, name: str, data: List[float]):
        """Add a new column with data"""
        self._save_undo()
        col_idx = len(self._data.columns)

        self.beginInsertColumns(QModelIndex(), col_idx, col_idx)

        if self._data.empty:
            self._data = pd.DataFrame({name: data})
        else:
            # Extend or truncate data to match row count
            if len(data) < len(self._data):
                data = data + [0.0] * (len(self._data) - len(data))
            elif len(data) > len(self._data):
                data = data[:len(self._data)]
            self._data[name] = data

        self._column_metadata.append(ColumnMetadata(name=name))
        self._update_formula_engine_columns()

        self.endInsertColumns()
        self._emit_size_changed()
        self.columnAdded.emit(col_idx, name)
        self.dataModified.emit()

    @Slot(int)
    def removeColumnAt(self, col_idx: int):
        """Remove a column by index"""
        if col_idx < 0 or col_idx >= len(self._data.columns):
            return
        self._save_undo()

        self.beginRemoveColumns(QModelIndex(), col_idx, col_idx)

        # Remove from DataFrame
        col_name = self._data.columns[col_idx]
        self._data = self._data.drop(columns=[col_name])

        # Remove metadata
        if col_idx < len(self._column_metadata):
            del self._column_metadata[col_idx]

        # Remove formulas for this column
        self._cell_formulas = {
            (r, c): f for (r, c), f in self._cell_formulas.items()
            if c != col_idx
        }

        self._update_formula_engine_columns()

        self.endRemoveColumns()
        self._emit_size_changed()
        self.columnRemoved.emit(col_idx)
        self.dataModified.emit()

    @Slot(int, str)
    def setColumnFormula(self, col_idx: int, formula: str):
        """Set a column-wide formula"""
        if col_idx < 0 or col_idx >= len(self._column_metadata):
            return
        self._save_undo()

        self._column_metadata[col_idx].formula = formula

        if formula:
            # Evaluate and fill column
            try:
                values = self._formula_engine.evaluate_column(formula, len(self._data))
                col_name = self._data.columns[col_idx]
                self._data[col_name] = values

                # Emit changes
                top = self.index(0, col_idx)
                bottom = self.index(len(self._data) - 1, col_idx)
                self.dataChanged.emit(top, bottom, [Qt.DisplayRole])
                self._bump_revision()

            except Exception as e:
                logger.error(f"Column formula error: {e}")

        self.columnMetadataChanged.emit(col_idx)
        self.dataModified.emit()

    @Slot(int, str, str, str)
    def setColumnMetadata(self, col_idx: int, name: str, unit: str, comment: str):
        """Set column metadata"""
        if col_idx < 0 or col_idx >= len(self._column_metadata):
            return

        old_name = self._column_metadata[col_idx].name
        self._column_metadata[col_idx].name = name
        self._column_metadata[col_idx].unit = unit
        self._column_metadata[col_idx].comment = comment

        # Update DataFrame column name
        if old_name != name:
            self._data = self._data.rename(columns={old_name: name})

        self._update_formula_engine_columns()
        self.headerDataChanged.emit(Qt.Horizontal, col_idx, col_idx)
        self.columnMetadataChanged.emit(col_idx)

    @Slot(int, result='QVariant')
    def getColumnMetadata(self, col_idx: int) -> Dict:
        """Get column metadata as dict"""
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

    @Slot(result=list)
    def getColumnNames(self) -> List[str]:
        """Get list of column names"""
        return [meta.name for meta in self._column_metadata]

    @Slot(int, result=str)
    def getColumnName(self, col_idx: int) -> str:
        """Get a single column name by index"""
        if 0 <= col_idx < len(self._column_metadata):
            return self._column_metadata[col_idx].name
        return ""

    # =========================================================================
    # Row management
    # =========================================================================

    @Slot()
    def addRow(self):
        """Add an empty row"""
        if not self._batch_mode:
            self._save_undo()
        row_idx = len(self._data)
        self.beginInsertRows(QModelIndex(), row_idx, row_idx)

        new_row = pd.DataFrame([[0.0] * len(self._data.columns)],
                               columns=self._data.columns)
        self._data = pd.concat([self._data, new_row], ignore_index=True)

        self.endInsertRows()
        self._emit_size_changed()
        self.dataModified.emit()

    @Slot(int)
    def insertRowAt(self, row_idx: int):
        """Insert an empty row at specific index"""
        self._save_undo()
        if row_idx < 0:
            row_idx = 0
        if row_idx > len(self._data):
            row_idx = len(self._data)

        self.beginInsertRows(QModelIndex(), row_idx, row_idx)

        # Create new row with zeros
        new_row = pd.DataFrame([[0.0] * len(self._data.columns)],
                               columns=self._data.columns)

        # Split and concatenate
        if row_idx == 0:
            self._data = pd.concat([new_row, self._data], ignore_index=True)
        elif row_idx >= len(self._data):
            self._data = pd.concat([self._data, new_row], ignore_index=True)
        else:
            top = self._data.iloc[:row_idx]
            bottom = self._data.iloc[row_idx:]
            self._data = pd.concat([top, new_row, bottom], ignore_index=True)

        # Shift formulas for rows >= row_idx
        new_formulas = {}
        for (r, c), f in self._cell_formulas.items():
            if r >= row_idx:
                new_formulas[(r + 1, c)] = f
            else:
                new_formulas[(r, c)] = f
        self._cell_formulas = new_formulas

        self.endInsertRows()
        self._emit_size_changed()
        self.dataModified.emit()

    @Slot(int)
    def removeRowAt(self, row_idx: int):
        """Remove a row by index"""
        if row_idx < 0 or row_idx >= len(self._data):
            return
        self._save_undo()

        self.beginRemoveRows(QModelIndex(), row_idx, row_idx)

        self._data = self._data.drop(self._data.index[row_idx]).reset_index(drop=True)

        # Remove formulas for this row and shift higher rows down
        new_formulas = {}
        for (r, c), f in self._cell_formulas.items():
            if r < row_idx:
                new_formulas[(r, c)] = f
            elif r > row_idx:
                new_formulas[(r - 1, c)] = f
            # Skip r == row_idx (deleted row)
        self._cell_formulas = new_formulas

        self.endRemoveRows()
        self._emit_size_changed()
        self.dataModified.emit()

    @Slot(int)
    def clearRow(self, row_idx: int):
        """Clear all values in a row (set to 0)"""
        if row_idx < 0 or row_idx >= len(self._data):
            return
        self._save_undo()

        for col_idx in range(len(self._data.columns)):
            self._data.iloc[row_idx, col_idx] = 0.0
            # Remove any cell formulas
            if (row_idx, col_idx) in self._cell_formulas:
                del self._cell_formulas[(row_idx, col_idx)]

        # Emit changes
        left = self.index(row_idx, 0)
        right = self.index(row_idx, len(self._data.columns) - 1)
        self.dataChanged.emit(left, right, [Qt.DisplayRole])
        self._bump_revision()
        self.dataModified.emit()

    @Slot(int)
    def clearColumn(self, col_idx: int):
        """Clear all values in a column (set to 0)"""
        if col_idx < 0 or col_idx >= len(self._data.columns):
            return
        self._save_undo()

        col_name = self._data.columns[col_idx]
        self._data[col_name] = 0.0

        # Remove cell formulas for this column
        self._cell_formulas = {
            (r, c): f for (r, c), f in self._cell_formulas.items()
            if c != col_idx
        }

        # Clear column formula
        if col_idx < len(self._column_metadata):
            self._column_metadata[col_idx].formula = None

        # Emit changes
        top = self.index(0, col_idx)
        bottom = self.index(len(self._data) - 1, col_idx)
        self.dataChanged.emit(top, bottom, [Qt.DisplayRole])
        self._bump_revision()
        self.dataModified.emit()

    @Slot(int, bool)
    def sortByColumn(self, col_idx: int, ascending: bool = True):
        """Sort the table by a column"""
        if col_idx < 0 or col_idx >= len(self._data.columns):
            return
        self._save_undo()

        self.beginResetModel()

        col_name = self._data.columns[col_idx]

        # Try to sort numerically first, fall back to string sort
        try:
            self._data[col_name] = pd.to_numeric(self._data[col_name], errors='coerce')
        except Exception:
            pass

        self._data = self._data.sort_values(by=col_name, ascending=ascending, na_position='last')
        self._data = self._data.reset_index(drop=True)

        # Clear cell formulas (they would reference wrong rows after sort)
        self._cell_formulas.clear()

        self.endResetModel()
        self.dataModified.emit()

    # =========================================================================
    # Statistics
    # =========================================================================

    @Slot(int, result='QVariant')
    def calculateColumnStatistics(self, col_idx: int) -> Dict:
        """Calculate statistics for a column"""
        if col_idx < 0 or col_idx >= len(self._data.columns):
            return {}

        try:
            col_data = pd.to_numeric(self._data.iloc[:, col_idx], errors='coerce')
            col_data = col_data.dropna()

            if len(col_data) == 0:
                return {'error': 'No numeric data'}

            stats = {
                'count': len(col_data),
                'mean': float(col_data.mean()),
                'std': float(col_data.std()),
                'min': float(col_data.min()),
                'max': float(col_data.max()),
                'median': float(col_data.median()),
                'sum': float(col_data.sum())
            }

            self.statisticsCalculated.emit(col_idx, stats)
            return stats

        except Exception as e:
            logger.error(f"Statistics error: {e}")
            return {'error': str(e)}

    @Slot(int, result=float)
    def integrateColumn(self, col_idx: int, x_col_idx: int = 0) -> float:
        """Integrate a column using trapezoidal rule"""
        if col_idx < 0 or col_idx >= len(self._data.columns):
            return 0.0
        if x_col_idx < 0 or x_col_idx >= len(self._data.columns):
            x_col_idx = 0

        try:
            x = pd.to_numeric(self._data.iloc[:, x_col_idx], errors='coerce').values
            y = pd.to_numeric(self._data.iloc[:, col_idx], errors='coerce').values

            # Remove NaN
            mask = ~(np.isnan(x) | np.isnan(y))
            x, y = x[mask], y[mask]

            if len(x) < 2:
                return 0.0

            return float(np.trapz(y, x))

        except Exception as e:
            logger.error(f"Integration error: {e}")
            return 0.0

    # =========================================================================
    # Data access for graphs
    # =========================================================================

    @Slot(int, result=list)
    def getColumnData(self, col_idx: int) -> List[float]:
        """Get column data as list"""
        if col_idx < 0 or col_idx >= len(self._data.columns):
            return []

        try:
            col = pd.to_numeric(self._data.iloc[:, col_idx], errors='coerce')
            return col.fillna(0).tolist()
        except Exception:
            return []

    @Slot(int, int, result=list)
    def getPlotData(self, x_col: int, y_col: int) -> List:
        """Get X and Y data for plotting"""
        x_data = self.getColumnData(x_col)
        y_data = self.getColumnData(y_col)
        return [x_data, y_data]

    # =========================================================================
    # Properties
    # =========================================================================

    @Property(str)
    def tableId(self) -> str:
        return self._table_id

    @tableId.setter
    def tableId(self, value: str):
        self._table_id = value

    @Property(str)
    def linkedGraphId(self) -> str:
        return self._linked_graph_id or ""

    @linkedGraphId.setter
    def linkedGraphId(self, value: str):
        self._linked_graph_id = value if value else None

    @Property(int, notify=rowsChanged)
    def rows(self) -> int:
        return len(self._data)

    @Property(int, notify=columnsChanged)
    def columns(self) -> int:
        return len(self._data.columns) if not self._data.empty else 0

    @Property(bool, notify=isEmptyChanged)
    def isEmpty(self) -> bool:
        return self._data.empty

    @Property(str, notify=displayFormatChanged)
    def displayFormat(self) -> str:
        return self._display_format

    @displayFormat.setter
    def displayFormat(self, value: str):
        if value in ("auto", "scientific", "decimal") and value != self._display_format:
            self._display_format = value
            self.displayFormatChanged.emit()
            self._bump_revision()

    @Property(int, notify=displayFormatChanged)
    def decimalPlaces(self) -> int:
        return self._decimal_places

    @decimalPlaces.setter
    def decimalPlaces(self, value: int):
        value = max(0, min(15, value))
        if value != self._decimal_places:
            self._decimal_places = value
            self.displayFormatChanged.emit()
            self._bump_revision()

    @Slot(str, int)
    def setDisplayFormat(self, fmt: str, decimals: int):
        """Set display format from QML."""
        self.displayFormat = fmt
        self.decimalPlaces = decimals

    @Property(int, notify=dataRevisionChanged)
    def dataRevision(self) -> int:
        return self._data_revision

    def _bump_revision(self):
        """Increment revision counter so QML re-reads cell values."""
        self._data_revision += 1
        self.dataRevisionChanged.emit()

    def _emit_size_changed(self):
        """Emit all size-related signals for QML property updates."""
        self.rowsChanged.emit()
        self.columnsChanged.emit()
        self.isEmptyChanged.emit()
        self._bump_revision()

    # =========================================================================
    # Export & Clipboard
    # =========================================================================

    @Slot(str, result=bool)
    def exportToCSV(self, filepath: str) -> bool:
        """Export table data as CSV."""
        try:
            # Use column metadata names as headers
            headers = [meta.name for meta in self._column_metadata]
            export_df = self._data.copy()
            if len(headers) == len(export_df.columns):
                export_df.columns = headers
            export_df.to_csv(filepath, index=False)
            logger.info(f"Table exported to CSV: {filepath}")
            return True
        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            return False

    @Slot(int, int, int, int, result=str)
    def copyRange(self, startRow: int, startCol: int, endRow: int, endCol: int) -> str:
        """
        Copy cell range as tab-separated text and set to system clipboard.

        Returns the TSV string for convenience.
        """
        try:
            from PySide6.QtGui import QGuiApplication

            # Normalize range
            r1, r2 = min(startRow, endRow), max(startRow, endRow)
            c1, c2 = min(startCol, endCol), max(startCol, endCol)

            # Clamp to data bounds
            r1 = max(0, r1)
            c1 = max(0, c1)
            r2 = min(r2, len(self._data) - 1)
            c2 = min(c2, len(self._data.columns) - 1)

            lines = []
            for row in range(r1, r2 + 1):
                cells = []
                for col in range(c1, c2 + 1):
                    idx = self.index(row, col)
                    val = self.data(idx, Qt.DisplayRole)
                    cells.append(str(val) if val is not None else "")
                lines.append("\t".join(cells))

            tsv = "\n".join(lines)

            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(tsv)

            logger.info(f"Copied range ({r1},{c1})-({r2},{c2}) to clipboard")
            return tsv
        except Exception as e:
            logger.error(f"Copy range failed: {e}")
            return ""

    @Slot(int, int, int, int, result=str)
    def copyRangeWithHeaders(self, startRow: int, startCol: int, endRow: int, endCol: int) -> str:
        """Copy cell range with column headers as first row."""
        try:
            from PySide6.QtGui import QGuiApplication

            r1, r2 = min(startRow, endRow), max(startRow, endRow)
            c1, c2 = min(startCol, endCol), max(startCol, endCol)
            r1 = max(0, r1)
            c1 = max(0, c1)
            r2 = min(r2, len(self._data) - 1)
            c2 = min(c2, len(self._data.columns) - 1)

            # Header row
            headers = []
            for col in range(c1, c2 + 1):
                h = self.headerData(col, Qt.Horizontal, Qt.DisplayRole)
                headers.append(str(h) if h else "")
            lines = ["\t".join(headers)]

            # Data rows
            for row in range(r1, r2 + 1):
                cells = []
                for col in range(c1, c2 + 1):
                    idx = self.index(row, col)
                    val = self.data(idx, Qt.DisplayRole)
                    cells.append(str(val) if val is not None else "")
                lines.append("\t".join(cells))

            tsv = "\n".join(lines)

            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(tsv)

            logger.info(f"Copied range with headers ({r1},{c1})-({r2},{c2})")
            return tsv
        except Exception as e:
            logger.error(f"Copy with headers failed: {e}")
            return ""

    @Slot(int, int, int, int)
    def clearRange(self, startRow: int, startCol: int, endRow: int, endCol: int):
        """Clear all cells in a range (set to 0)."""
        self._save_undo()
        r1, r2 = min(startRow, endRow), max(startRow, endRow)
        c1, c2 = min(startCol, endCol), max(startCol, endCol)
        r1 = max(0, r1)
        c1 = max(0, c1)
        r2 = min(r2, len(self._data) - 1)
        c2 = min(c2, len(self._data.columns) - 1)

        for row in range(r1, r2 + 1):
            for col in range(c1, c2 + 1):
                self._data.iloc[row, col] = 0.0
                if (row, col) in self._cell_formulas:
                    del self._cell_formulas[(row, col)]

        if r1 <= r2 and c1 <= c2:
            top = self.index(r1, c1)
            bottom = self.index(r2, c2)
            self.dataChanged.emit(top, bottom, [Qt.DisplayRole])
            self._bump_revision()
            self.dataModified.emit()

    @Slot(int, int, str)
    def pasteFromClipboard(self, startRow: int, startCol: int, text: str = ""):
        """
        Paste tab-separated text into table starting at (startRow, startCol).
        If text is empty, reads from system clipboard.
        Handles Excel/Google Sheets \\r\\n line endings.
        """
        try:
            from PySide6.QtGui import QGuiApplication

            if not text:
                clipboard = QGuiApplication.clipboard()
                if clipboard:
                    text = clipboard.text()

            if not text:
                return

            self._save_undo()
            self._batch_mode = True

            # Normalize line endings (Excel uses \r\n)
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            lines = text.strip("\n").split("\n")

            for row_offset, line in enumerate(lines):
                cells = line.split("\t")
                for col_offset, cell_value in enumerate(cells):
                    row = startRow + row_offset
                    col = startCol + col_offset

                    # Expand table if needed
                    while row >= len(self._data):
                        self.addRow()
                    while col >= len(self._data.columns):
                        self.addColumn(self._index_to_letters(len(self._data.columns)))

                    # Set value directly to avoid per-cell revision bumps
                    try:
                        self._data.iloc[row, col] = parse_number(cell_value.strip())
                    except (ValueError, TypeError):
                        self._data.iloc[row, col] = cell_value.strip()

            self._batch_mode = False
            # Single refresh at end
            self._bump_revision()
            self.dataModified.emit()
            logger.info(f"Pasted {len(lines)} rows starting at ({startRow},{startCol})")
        except Exception as e:
            self._batch_mode = False
            logger.error(f"Paste failed: {e}")
