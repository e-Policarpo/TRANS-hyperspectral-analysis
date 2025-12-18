"""
Enhanced Table Window with Formula Support and Column Operations
Provides spreadsheet functionality similar to Excel/LibreOffice Calc
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import logging
import re
import pandas as pd
import numpy as np
from PySide6.QtWidgets import (QMainWindow, QTableWidget, QTableWidgetItem,
                                QToolBar, QPushButton, QWidget, QVBoxLayout,
                                QHBoxLayout, QHeaderView, QLineEdit, QLabel,
                                QComboBox, QMessageBox, QFileDialog, QInputDialog,
                                QMenu, QDialog, QFormLayout, QSpinBox)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QFont, QBrush, QColor

logger = logging.getLogger(__name__)


class FormulaEngine:
    """
    Simple formula engine for spreadsheet calculations.

    Supports:
    - Basic arithmetic: +, -, *, /, ^
    - Functions: SUM, AVG, MIN, MAX, COUNT, SQRT, ABS, LOG, EXP, SIN, COS, TAN
    - Cell references: A1, B2, etc.
    - Range references: A1:A10
    """

    def __init__(self, table_data_getter):
        """
        Initialize formula engine.

        Parameters:
        -----------
        table_data_getter : callable
            Function that returns (row, col) -> value
        """
        self.get_cell_value = table_data_getter

    def evaluate(self, formula, current_row, current_col):
        """
        Evaluate a formula.

        Parameters:
        -----------
        formula : str
            Formula string starting with '='
        current_row : int
            Row of the cell containing the formula
        current_col : int
            Column of the cell containing the formula

        Returns:
        --------
        result : float or str
            Evaluated result or error string
        """
        if not formula.startswith('='):
            return formula

        try:
            # Remove '=' prefix
            expr = formula[1:].strip().upper()

            # Replace cell references with values
            expr = self._replace_cell_references(expr)

            # Handle functions
            expr = self._process_functions(expr)

            # Evaluate expression
            # Use restricted eval for safety
            allowed_names = {
                '__builtins__': {},
                'abs': abs,
                'min': min,
                'max': max,
                'sum': sum,
                'len': len
            }

            result = eval(expr, allowed_names, {})

            return result

        except Exception as e:
            logger.error(f"Formula evaluation error: {e}")
            return f"#ERROR: {str(e)}"

    def _replace_cell_references(self, expr):
        """Replace cell references like A1, B2 with their values"""
        # Match patterns like A1, AB10, etc.
        pattern = r'([A-Z]+)(\d+)'

        def replace_ref(match):
            col_letters = match.group(1)
            row_num = int(match.group(2)) - 1  # Convert to 0-based

            # Convert column letters to index
            col_num = self._col_letters_to_index(col_letters)

            # Get cell value
            value = self.get_cell_value(row_num, col_num)

            # Try to convert to number
            try:
                return str(float(value)) if value != "" else "0"
            except (ValueError, TypeError):
                return "0"

        return re.sub(pattern, replace_ref, expr)

    def _col_letters_to_index(self, letters):
        """Convert column letters (A, B, AA, etc.) to 0-based index"""
        index = 0
        for i, letter in enumerate(reversed(letters)):
            index += (ord(letter) - ord('A') + 1) * (26 ** i)
        return index - 1

    def _process_functions(self, expr):
        """Process spreadsheet functions"""
        # SUM(range)
        expr = self._process_range_function(expr, 'SUM', lambda vals: sum(vals))

        # AVG(range)
        expr = self._process_range_function(expr, 'AVG',
                                            lambda vals: sum(vals) / len(vals) if vals else 0)

        # MIN(range)
        expr = self._process_range_function(expr, 'MIN',
                                            lambda vals: min(vals) if vals else 0)

        # MAX(range)
        expr = self._process_range_function(expr, 'MAX',
                                            lambda vals: max(vals) if vals else 0)

        # COUNT(range)
        expr = self._process_range_function(expr, 'COUNT',
                                            lambda vals: len([v for v in vals if v != 0]))

        # Math functions
        expr = expr.replace('SQRT(', 'np.sqrt(')
        expr = expr.replace('ABS(', 'abs(')
        expr = expr.replace('LOG(', 'np.log(')
        expr = expr.replace('EXP(', 'np.exp(')
        expr = expr.replace('SIN(', 'np.sin(')
        expr = expr.replace('COS(', 'np.cos(')
        expr = expr.replace('TAN(', 'np.tan(')

        # Power operator
        expr = expr.replace('^', '**')

        return expr

    def _process_range_function(self, expr, func_name, func):
        """Process range-based functions like SUM(A1:A10)"""
        pattern = f'{func_name}\\(([A-Z]+)(\\d+):([A-Z]+)(\\d+)\\)'

        def replace_func(match):
            start_col = self._col_letters_to_index(match.group(1))
            start_row = int(match.group(2)) - 1
            end_col = self._col_letters_to_index(match.group(3))
            end_row = int(match.group(4)) - 1

            values = []
            for row in range(start_row, end_row + 1):
                for col in range(start_col, end_col + 1):
                    val = self.get_cell_value(row, col)
                    try:
                        values.append(float(val) if val != "" else 0)
                    except (ValueError, TypeError):
                        pass

            try:
                result = func(values)
                return str(result)
            except:
                return "0"

        return re.sub(pattern, replace_func, expr)


class EnhancedTableWindow(QMainWindow):
    """
    Enhanced spreadsheet window with formula support and column operations.

    Features:
    - Formula evaluation (=SUM(A1:A10), etc.)
    - Column operations (fill, sort, statistics)
    - Cell formatting
    - Export to CSV/Excel
    - Large dataset handling with warnings
    """

    closed = Signal()

    def __init__(self, parent=None, data=None, max_preview_rows=1000):
        super().__init__(parent)

        self.max_preview_rows = max_preview_rows
        self.full_data = None  # Store full dataset if large
        self.is_limited = False  # Flag if showing limited view

        # Formula tracking
        self.formulas = {}  # {(row, col): formula_string}

        self.setWindowTitle("Enhanced Table")
        self.resize(1000, 700)

        # Apply dark theme
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1a1a1a;
                color: #ffffff;
            }
            QToolBar {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                spacing: 5px;
                padding: 5px;
            }
            QPushButton, QComboBox {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px 10px;
                min-width: 80px;
            }
            QPushButton:hover, QComboBox:hover {
                background-color: #4a4a4a;
            }
            QLineEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
            }
            QTableWidget {
                background-color: #1a1a1a;
                alternate-background-color: #222222;
                color: #ffffff;
                gridline-color: #404040;
                border: 1px solid #404040;
                selection-background-color: #ff66b2;
                selection-color: #000000;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #404040;
                padding: 5px;
                font-weight: bold;
            }
            QHeaderView::section:hover {
                background-color: #3a3a3a;
            }
            QLabel {
                color: #ffffff;
            }
        """)

        self._setup_ui()

        # Initialize with data
        if data is not None:
            self._load_data(data)
        else:
            self._init_default_table()

        # Create formula engine
        self.formula_engine = FormulaEngine(self._get_cell_value_for_formula)

    def _setup_ui(self):
        """Setup user interface"""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Create toolbars
        self._create_main_toolbar()
        self._create_column_toolbar()

        # Formula bar
        formula_layout = QHBoxLayout()
        formula_layout.addWidget(QLabel("Formula:"))
        self.formula_bar = QLineEdit()
        self.formula_bar.setPlaceholderText("Enter formula (=SUM(A1:A10)) or value...")
        self.formula_bar.returnPressed.connect(self._apply_formula)
        formula_layout.addWidget(self.formula_bar)

        apply_formula_btn = QPushButton("Apply")
        apply_formula_btn.clicked.connect(self._apply_formula)
        formula_layout.addWidget(apply_formula_btn)

        main_layout.addLayout(formula_layout)

        # Create table widget
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_item_changed)

        # Set context menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        # Set font
        font = QFont("Monospace", 10)
        self.table.setFont(font)

        main_layout.addWidget(self.table)

        # Status bar
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)

    def _create_main_toolbar(self):
        """Create main toolbar"""
        toolbar = QToolBar("Main")
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # Add row
        add_row_btn = QPushButton("Add Row")
        add_row_btn.clicked.connect(self._add_row)
        toolbar.addWidget(add_row_btn)

        # Add column
        add_col_btn = QPushButton("Add Column")
        add_col_btn.clicked.connect(self._add_column)
        toolbar.addWidget(add_col_btn)

        toolbar.addSeparator()

        # Remove row
        remove_row_btn = QPushButton("Remove Row")
        remove_row_btn.clicked.connect(self._remove_row)
        toolbar.addWidget(remove_row_btn)

        # Remove column
        remove_col_btn = QPushButton("Remove Column")
        remove_col_btn.clicked.connect(self._remove_column)
        toolbar.addWidget(remove_col_btn)

        toolbar.addSeparator()

        # Clear all
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_table)
        toolbar.addWidget(clear_btn)

        toolbar.addSeparator()

        # Plot
        plot_btn = QPushButton("Plot Columns...")
        plot_btn.clicked.connect(self._plot_columns)
        toolbar.addWidget(plot_btn)

        toolbar.addSeparator()

        # Export
        export_btn = QPushButton("Export...")
        export_btn.clicked.connect(self._export_table)
        toolbar.addWidget(export_btn)

        # Load full data (if limited)
        self.load_full_btn = QPushButton("Load Full Data")
        self.load_full_btn.clicked.connect(self._load_full_data)
        self.load_full_btn.setVisible(False)
        toolbar.addWidget(self.load_full_btn)

    def _create_column_toolbar(self):
        """Create column operations toolbar"""
        toolbar = QToolBar("Column Operations")
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        toolbar.addWidget(QLabel("Column Ops:"))

        # Fill column
        fill_btn = QPushButton("Fill...")
        fill_btn.clicked.connect(self._fill_column)
        toolbar.addWidget(fill_btn)

        # Sort column
        sort_asc_btn = QPushButton("Sort ↑")
        sort_asc_btn.clicked.connect(lambda: self._sort_by_column(ascending=True))
        toolbar.addWidget(sort_asc_btn)

        sort_desc_btn = QPushButton("Sort ↓")
        sort_desc_btn.clicked.connect(lambda: self._sort_by_column(ascending=False))
        toolbar.addWidget(sort_desc_btn)

        toolbar.addSeparator()

        # Column statistics
        stats_btn = QPushButton("Statistics")
        stats_btn.clicked.connect(self._show_column_stats)
        toolbar.addWidget(stats_btn)

    def _init_default_table(self):
        """Initialize with default empty table"""
        self.table.setRowCount(20)
        self.table.setColumnCount(10)

        # Set column headers (A, B, C, ...)
        headers = [self._col_index_to_letters(i) for i in range(10)]
        self.table.setHorizontalHeaderLabels(headers)

        # Initialize empty cells
        self._init_empty_cells()

    def _init_empty_cells(self):
        """Initialize all cells with empty items"""
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                if not self.table.item(row, col):
                    item = QTableWidgetItem("")
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, item)

    def _load_data(self, data):
        """Load data into table with large dataset warning"""
        if isinstance(data, pd.DataFrame):
            num_rows = len(data)

            # Check if data is too large
            if num_rows > self.max_preview_rows:
                reply = QMessageBox.question(
                    self, "Large Dataset Warning",
                    f"This dataset has {num_rows} rows, which may cause performance issues.\n\n"
                    f"Load only first {self.max_preview_rows} rows for preview?\n"
                    f"(You can load full data later)",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )

                if reply == QMessageBox.Yes:
                    self.full_data = data
                    self.is_limited = True
                    data = data.head(self.max_preview_rows)
                    self.load_full_btn.setVisible(True)
                    self.status_label.setText(
                        f"⚠️ Showing {self.max_preview_rows} of {num_rows} rows (preview mode)"
                    )
                    self.status_label.setStyleSheet("color: #ffaa66; font-weight: bold;")

            # Load DataFrame
            self.table.setRowCount(len(data))
            self.table.setColumnCount(len(data.columns))

            # Set headers
            headers = [self._col_index_to_letters(i) for i in range(len(data.columns))]
            self.table.setHorizontalHeaderLabels(headers)

            # Block signals during loading
            self.table.blockSignals(True)

            # Load data
            for row in range(len(data)):
                for col in range(len(data.columns)):
                    value = data.iloc[row, col]
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, item)

            self.table.blockSignals(False)

            logger.info(f"Loaded {len(data)} rows, {len(data.columns)} columns")

        else:
            logger.warning(f"Unknown data type: {type(data)}")
            self._init_default_table()

    def _load_full_data(self):
        """Load full dataset (after warning)"""
        if self.full_data is not None:
            reply = QMessageBox.question(
                self, "Confirm",
                f"Load all {len(self.full_data)} rows?\nThis may take a moment...",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self._load_data(self.full_data)
                self.is_limited = False
                self.load_full_btn.setVisible(False)
                self.status_label.setText("Full dataset loaded")
                self.status_label.setStyleSheet("color: #66ff66;")

    def _col_index_to_letters(self, index):
        """Convert column index to letters (0->A, 25->Z, 26->AA, etc.)"""
        letters = ""
        index += 1  # Make 1-based
        while index > 0:
            index -= 1
            letters = chr(ord('A') + (index % 26)) + letters
            index //= 26
        return letters

    def _get_cell_value_for_formula(self, row, col):
        """Get cell value for formula engine"""
        item = self.table.item(row, col)
        if not item:
            return ""

        # If cell contains a formula, return computed value (prevent circular refs)
        if (row, col) in self.formulas:
            text = item.text()
            # Return displayed value, not formula
            return text if not text.startswith('=') else ""

        return item.text()

    def _on_selection_changed(self):
        """Handle cell selection change"""
        current = self.table.currentItem()
        if current:
            row, col = self.table.currentRow(), self.table.currentColumn()

            # Show formula in formula bar if cell has one
            if (row, col) in self.formulas:
                self.formula_bar.setText(self.formulas[(row, col)])
            else:
                self.formula_bar.setText(current.text())

            # Update status
            col_letter = self._col_index_to_letters(col)
            self.status_label.setText(f"Cell: {col_letter}{row + 1}")
            if not self.is_limited:
                self.status_label.setStyleSheet("color: #ffffff;")

    def _on_item_changed(self, item):
        """Handle item change - recalculate formulas if needed"""
        row, col = self.table.row(item), self.table.column(item)

        text = item.text()

        # If it's a formula, evaluate it
        if text.startswith('='):
            self.formulas[(row, col)] = text
            self._recalculate_cell(row, col)
        else:
            # Remove formula if exists
            if (row, col) in self.formulas:
                del self.formulas[(row, col)]

    def _apply_formula(self):
        """Apply formula from formula bar to current cell"""
        current = self.table.currentItem()
        if not current:
            return

        formula_text = self.formula_bar.text()
        self.table.blockSignals(True)
        current.setText(formula_text)
        self.table.blockSignals(False)

        # Trigger evaluation
        row, col = self.table.currentRow(), self.table.currentColumn()

        if formula_text.startswith('='):
            self.formulas[(row, col)] = formula_text
            self._recalculate_cell(row, col)
        else:
            if (row, col) in self.formulas:
                del self.formulas[(row, col)]

    def _recalculate_cell(self, row, col):
        """Recalculate a cell's formula"""
        if (row, col) not in self.formulas:
            return

        formula = self.formulas[(row, col)]
        result = self.formula_engine.evaluate(formula, row, col)

        item = self.table.item(row, col)
        self.table.blockSignals(True)
        item.setText(str(result))

        # Color formula cells differently
        if str(result).startswith('#ERROR'):
            item.setForeground(QBrush(QColor('#ff6666')))
        else:
            item.setForeground(QBrush(QColor('#66b3ff')))

        self.table.blockSignals(False)

    def _recalculate_all(self):
        """Recalculate all formulas"""
        for (row, col) in self.formulas:
            self._recalculate_cell(row, col)

    def _add_row(self):
        """Add a new row"""
        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
        for col in range(self.table.columnCount()):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_count, col, item)

    def _add_column(self):
        """Add a new column"""
        col_count = self.table.columnCount()
        self.table.insertColumn(col_count)
        self.table.setHorizontalHeaderItem(
            col_count,
            QTableWidgetItem(self._col_index_to_letters(col_count))
        )
        for row in range(self.table.rowCount()):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col_count, item)

    def _remove_row(self):
        """Remove selected row"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
            # Remove formulas in that row
            self.formulas = {(r, c): f for (r, c), f in self.formulas.items()
                           if r != current_row}

    def _remove_column(self):
        """Remove selected column"""
        current_col = self.table.currentColumn()
        if current_col >= 0:
            self.table.removeColumn(current_col)
            # Remove formulas in that column
            self.formulas = {(r, c): f for (r, c), f in self.formulas.items()
                           if c != current_col}

    def _clear_table(self):
        """Clear all data"""
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setText("")
        self.formulas.clear()

    def _fill_column(self):
        """Fill column with a value or pattern"""
        current_col = self.table.currentColumn()
        if current_col < 0:
            QMessageBox.warning(self, "No Column", "Please select a column")
            return

        value, ok = QInputDialog.getText(
            self, "Fill Column",
            f"Enter value or formula to fill column {self._col_index_to_letters(current_col)}:"
        )

        if ok and value:
            self.table.blockSignals(True)
            for row in range(self.table.rowCount()):
                item = self.table.item(row, current_col)
                if item:
                    item.setText(value)
            self.table.blockSignals(False)
            self._recalculate_all()

    def _sort_by_column(self, ascending=True):
        """Sort table by selected column"""
        current_col = self.table.currentColumn()
        if current_col < 0:
            QMessageBox.warning(self, "No Column", "Please select a column")
            return

        self.table.sortItems(current_col, Qt.AscendingOrder if ascending else Qt.DescendingOrder)

    def _show_column_stats(self):
        """Show statistics for selected column"""
        current_col = self.table.currentColumn()
        if current_col < 0:
            QMessageBox.warning(self, "No Column", "Please select a column")
            return

        # Collect numeric values
        values = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, current_col)
            if item and item.text():
                try:
                    values.append(float(item.text()))
                except ValueError:
                    pass

        if not values:
            QMessageBox.information(self, "No Data", "No numeric values in column")
            return

        # Calculate statistics
        stats = {
            'Count': len(values),
            'Sum': np.sum(values),
            'Mean': np.mean(values),
            'Median': np.median(values),
            'Std Dev': np.std(values),
            'Min': np.min(values),
            'Max': np.max(values)
        }

        msg = f"Statistics for Column {self._col_index_to_letters(current_col)}:\n\n"
        for name, value in stats.items():
            msg += f"{name}: {value:.4f}\n"

        QMessageBox.information(self, "Column Statistics", msg)

    def _show_context_menu(self, position):
        """Show context menu"""
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #404040;
            }
            QMenu::item:selected {
                background-color: #ff66b2;
                color: #000000;
            }
        """)

        copy_action = menu.addAction("Copy")
        paste_action = menu.addAction("Paste")
        menu.addSeparator()
        clear_action = menu.addAction("Clear Cell")
        delete_formula_action = menu.addAction("Delete Formula")

        action = menu.exec_(self.table.mapToGlobal(position))

        if action == clear_action:
            current = self.table.currentItem()
            if current:
                current.setText("")
        elif action == delete_formula_action:
            row, col = self.table.currentRow(), self.table.currentColumn()
            if (row, col) in self.formulas:
                del self.formulas[(row, col)]

    def _export_table(self):
        """Export table to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Table", "",
            "CSV Files (*.csv);;Excel Files (*.xlsx);;All Files (*)"
        )

        if filename:
            try:
                df = self.get_dataframe()
                if filename.endswith('.xlsx'):
                    df.to_excel(filename, index=False)
                else:
                    df.to_csv(filename, index=False)

                logger.info(f"Table exported to: {filename}")
                QMessageBox.information(self, "Success", f"Table saved to:\n{filename}")
            except Exception as e:
                logger.error(f"Export error: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def get_dataframe(self):
        """Export table data as pandas DataFrame"""
        data = []
        headers = []

        # Get headers
        for col in range(self.table.columnCount()):
            header_item = self.table.horizontalHeaderItem(col)
            headers.append(header_item.text() if header_item else f"Col{col+1}")

        # Get data
        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                text = item.text() if item else ""
                # Try to convert to number
                try:
                    value = float(text) if text and not text.startswith('#') else text
                except ValueError:
                    value = text
                row_data.append(value)
            data.append(row_data)

        return pd.DataFrame(data, columns=headers)

    def _plot_columns(self):
        """Open dialog to select columns and create plot"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel, QListWidgetItem
        from src.widgets.enhanced_plot_window import EnhancedPlotWindow

        # Create selection dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Plot Columns")
        dialog.resize(400, 500)
        dialog.setStyleSheet(self.styleSheet())

        layout = QVBoxLayout(dialog)

        # Instructions
        layout.addWidget(QLabel("Select X-axis column (single selection):"))

        # X column list
        x_list = QListWidget()
        x_list.setSelectionMode(QListWidget.SingleSelection)
        for col in range(self.table.columnCount()):
            header = self.table.horizontalHeaderItem(col)
            col_name = header.text() if header else f"Col{col+1}"
            item = QListWidgetItem(col_name)
            item.setData(Qt.UserRole, col)
            x_list.addItem(item)
        if x_list.count() > 0:
            x_list.setCurrentRow(0)
        layout.addWidget(x_list)

        layout.addWidget(QLabel("Select Y-axis column(s) (multi-selection):"))

        # Y columns list
        y_list = QListWidget()
        y_list.setSelectionMode(QListWidget.MultiSelection)
        for col in range(self.table.columnCount()):
            header = self.table.horizontalHeaderItem(col)
            col_name = header.text() if header else f"Col{col+1}"
            item = QListWidgetItem(col_name)
            item.setData(Qt.UserRole, col)
            y_list.addItem(item)
        if y_list.count() > 1:
            y_list.item(1).setSelected(True)
        layout.addWidget(y_list)

        # Buttons
        button_layout = QHBoxLayout()
        plot_btn = QPushButton("Plot")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(plot_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        cancel_btn.clicked.connect(dialog.reject)

        def do_plot():
            x_item = x_list.currentItem()
            y_items = y_list.selectedItems()

            if not x_item or not y_items:
                QMessageBox.warning(dialog, "Invalid Selection",
                                  "Please select X column and at least one Y column")
                return

            x_col = x_item.data(Qt.UserRole)
            y_cols = [item.data(Qt.UserRole) for item in y_items]

            # Extract data
            try:
                x_data = []
                for row in range(self.table.rowCount()):
                    item = self.table.item(row, x_col)
                    if item and item.text():
                        try:
                            x_data.append(float(item.text()))
                        except ValueError:
                            pass

                if not x_data:
                    QMessageBox.warning(dialog, "No Data", "No numeric data in X column")
                    return

                x_data = np.array(x_data)

                # Create plot window
                plot_window = EnhancedPlotWindow()
                plot_window.setWindowTitle(f"Plot from Table: {self.windowTitle()}")

                # Plot each Y column
                for y_col in y_cols:
                    y_data = []
                    for row in range(min(len(x_data), self.table.rowCount())):
                        item = self.table.item(row, y_col)
                        if item and item.text():
                            try:
                                y_data.append(float(item.text()))
                            except ValueError:
                                y_data.append(0)
                        else:
                            y_data.append(0)

                    y_data = np.array(y_data[:len(x_data)])

                    # Get column name
                    header = self.table.horizontalHeaderItem(y_col)
                    y_name = header.text() if header else f"Col{y_col+1}"

                    # Add curve
                    plot_window.canvas.add_curve(x_data, y_data, label=y_name)

                # Set labels
                x_header = self.table.horizontalHeaderItem(x_col)
                x_name = x_header.text() if x_header else f"Col{x_col+1}"

                plot_window.canvas.set_labels(
                    xlabel=x_name,
                    ylabel="Value",
                    title=f"Plot from {self.windowTitle()}"
                )

                plot_window.show()
                dialog.accept()

                logger.info(f"Created plot from table: {len(y_cols)} curves")

            except Exception as e:
                logger.error(f"Plot error: {e}", exc_info=True)
                QMessageBox.critical(dialog, "Plot Error", f"Failed to create plot:\n{e}")

        plot_btn.clicked.connect(do_plot)

        dialog.exec_()

    def closeEvent(self, event):
        """Handle window close"""
        self.closed.emit()
        event.accept()
