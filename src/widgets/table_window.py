"""
Simplified Table Window with QtiPlot-style aesthetics
Basic spreadsheet functionality
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import logging
import pandas as pd
from PySide6.QtWidgets import (QMainWindow, QTableWidget, QTableWidgetItem,
                                QToolBar, QPushButton, QWidget, QVBoxLayout,
                                QHeaderView)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


class TableWindow(QMainWindow):
    """
    Simplified table window with QtiPlot-style appearance
    Basic spreadsheet with row/column add/remove
    """

    closed = Signal()

    def __init__(self, parent=None, data=None):
        super().__init__(parent)

        self.setWindowTitle("Table")
        self.resize(800, 600)

        # Apply dark theme with QtiPlot-style colors
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
            }
            QToolBar {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                spacing: 5px;
                padding: 5px;
            }
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px 10px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
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
        """)

        self._setup_ui()

        # Initialize with default or provided data
        if data is not None:
            self._load_data(data)
        else:
            self._init_default_table()

    def _setup_ui(self):
        """Setup user interface"""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Create toolbar
        toolbar = QToolBar()
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # Add row button
        add_row_btn = QPushButton("Add Row")
        add_row_btn.clicked.connect(self._add_row)
        toolbar.addWidget(add_row_btn)

        # Add column button
        add_col_btn = QPushButton("Add Column")
        add_col_btn.clicked.connect(self._add_column)
        toolbar.addWidget(add_col_btn)

        toolbar.addSeparator()

        # Remove row button
        remove_row_btn = QPushButton("Remove Row")
        remove_row_btn.clicked.connect(self._remove_row)
        toolbar.addWidget(remove_row_btn)

        # Remove column button
        remove_col_btn = QPushButton("Remove Column")
        remove_col_btn.clicked.connect(self._remove_column)
        toolbar.addWidget(remove_col_btn)

        toolbar.addSeparator()

        # Clear button
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_table)
        toolbar.addWidget(clear_btn)

        # Create table widget
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(30)

        # Set font
        font = QFont("Monospace", 10)
        self.table.setFont(font)

        layout.addWidget(self.table)

    def _init_default_table(self):
        """Initialize with default empty table"""
        self.table.setRowCount(10)
        self.table.setColumnCount(5)

        # Set column headers
        headers = [f"Col{i+1}" for i in range(5)]
        self.table.setHorizontalHeaderLabels(headers)

        # Initialize empty cells
        for row in range(10):
            for col in range(5):
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

    def _load_data(self, data):
        """Load data into table"""
        if isinstance(data, pd.DataFrame):
            # Load from DataFrame
            self.table.setRowCount(len(data))
            self.table.setColumnCount(len(data.columns))
            self.table.setHorizontalHeaderLabels(data.columns.tolist())

            for row in range(len(data)):
                for col in range(len(data.columns)):
                    value = data.iloc[row, col]
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, item)
        else:
            logger.warning(f"Unknown data type: {type(data)}")
            self._init_default_table()

    def _add_row(self):
        """Add a new row at the end"""
        row_count = self.table.rowCount()
        self.table.insertRow(row_count)

        # Initialize empty cells
        for col in range(self.table.columnCount()):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_count, col, item)

        logger.info(f"Added row {row_count + 1}")

    def _add_column(self):
        """Add a new column at the end"""
        col_count = self.table.columnCount()
        self.table.insertColumn(col_count)
        self.table.setHorizontalHeaderItem(col_count,
                                          QTableWidgetItem(f"Col{col_count + 1}"))

        # Initialize empty cells
        for row in range(self.table.rowCount()):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col_count, item)

        logger.info(f"Added column {col_count + 1}")

    def _remove_row(self):
        """Remove currently selected row"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
            logger.info(f"Removed row {current_row + 1}")

    def _remove_column(self):
        """Remove currently selected column"""
        current_col = self.table.currentColumn()
        if current_col >= 0:
            self.table.removeColumn(current_col)
            logger.info(f"Removed column {current_col + 1}")

    def _clear_table(self):
        """Clear all data from table"""
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                self.table.item(row, col).setText("")
        logger.info("Table cleared")

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
                    value = float(text) if text else None
                except ValueError:
                    value = text
                row_data.append(value)
            data.append(row_data)

        return pd.DataFrame(data, columns=headers)

    def closeEvent(self, event):
        """Handle window close"""
        self.closed.emit()
        event.accept()
