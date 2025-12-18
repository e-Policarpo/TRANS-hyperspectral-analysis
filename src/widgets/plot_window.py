"""
Simplified Plot Window with Matplotlib Integration
QtiPlot-style plotting with basic manipulation features
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import logging
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QToolBar, QComboBox, QPushButton, QLabel, QCheckBox)
from PySide6.QtCore import Signal, Qt

logger = logging.getLogger(__name__)


class PlotCanvas(FigureCanvasQTAgg):
    """Matplotlib canvas for Qt"""

    def __init__(self, parent=None, width=8, height=6, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)

        # Style the plot
        self.axes.set_facecolor('#1a1a1a')
        self.figure.patch.set_facecolor('#0d0d0d')
        self.axes.tick_params(colors='#ffffff', which='both')
        self.axes.spines['bottom'].set_color('#ffffff')
        self.axes.spines['top'].set_color('#ffffff')
        self.axes.spines['left'].set_color('#ffffff')
        self.axes.spines['right'].set_color('#ffffff')
        self.axes.xaxis.label.set_color('#ffffff')
        self.axes.yaxis.label.set_color('#ffffff')
        self.axes.title.set_color('#ffffff')

        self.figure.tight_layout()

    def plot(self, x, y, label=None, color=None, marker=None, linestyle='-'):
        """Add a curve to the plot"""
        line, = self.axes.plot(x, y, label=label, color=color,
                               marker=marker, linestyle=linestyle, linewidth=2)
        if label:
            self.axes.legend(facecolor='#2d2d2d', edgecolor='#ffffff',
                            labelcolor='#ffffff')
        self.draw()
        return line

    def clear(self):
        """Clear all curves"""
        self.axes.clear()
        self.draw()

    def set_labels(self, xlabel=None, ylabel=None, title=None):
        """Set axis labels and title"""
        if xlabel:
            self.axes.set_xlabel(xlabel)
        if ylabel:
            self.axes.set_ylabel(ylabel)
        if title:
            self.axes.set_title(title)
        self.draw()

    def set_grid(self, visible):
        """Toggle grid"""
        self.axes.grid(visible, color='#555555', linestyle='--', linewidth=0.5)
        self.draw()


class PlotWindow(QMainWindow):
    """
    Simplified plot window with QtiPlot-style interface
    Supports basic curve selection and manipulation
    """

    closed = Signal()

    def __init__(self, parent=None, datasets=None):
        super().__init__(parent)
        self.datasets = datasets or {}
        self.current_lines = []

        self.setWindowTitle("Plot Window")
        self.resize(900, 700)

        # Apply dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
                color: #ffffff;
            }
            QToolBar {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                spacing: 5px;
                padding: 5px;
            }
            QComboBox, QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
                min-width: 100px;
            }
            QComboBox:hover, QPushButton:hover {
                background-color: #4a4a4a;
            }
            QComboBox::drop-down {
                border: none;
            }
            QLabel {
                color: #ffffff;
            }
            QCheckBox {
                color: #ffffff;
            }
        """)

        self._setup_ui()

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

        # Dataset selector
        toolbar.addWidget(QLabel("Dataset:"))
        self.dataset_combo = QComboBox()
        self.dataset_combo.addItems(list(self.datasets.keys()))
        self.dataset_combo.currentTextChanged.connect(self._on_dataset_changed)
        toolbar.addWidget(self.dataset_combo)

        toolbar.addSeparator()

        # Plot type selector
        toolbar.addWidget(QLabel("Type:"))
        self.plot_type_combo = QComboBox()
        self.plot_type_combo.addItems(["Line", "Scatter", "Line+Scatter"])
        toolbar.addWidget(self.plot_type_combo)

        toolbar.addSeparator()

        # Plot button
        plot_btn = QPushButton("Plot")
        plot_btn.clicked.connect(self._plot_current)
        toolbar.addWidget(plot_btn)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_plot)
        toolbar.addWidget(clear_btn)

        toolbar.addSeparator()

        # Grid checkbox
        self.grid_checkbox = QCheckBox("Grid")
        self.grid_checkbox.setChecked(True)
        self.grid_checkbox.toggled.connect(self._toggle_grid)
        toolbar.addWidget(self.grid_checkbox)

        # Create canvas
        self.canvas = PlotCanvas(self, width=8, height=6, dpi=100)
        layout.addWidget(self.canvas)

        # Apply initial grid
        self.canvas.set_grid(True)

    def _on_dataset_changed(self, dataset_name):
        """Handle dataset selection change"""
        logger.info(f"Dataset changed to: {dataset_name}")

    def _plot_current(self):
        """Plot currently selected dataset"""
        dataset_name = self.dataset_combo.currentText()
        if not dataset_name or dataset_name not in self.datasets:
            return

        dataset = self.datasets[dataset_name]
        plot_type = self.plot_type_combo.currentText()

        try:
            # Get data
            if hasattr(dataset, 'independent_var') and hasattr(dataset, 'spectra'):
                # SpectralData object
                x = dataset.independent_var
                # Plot first spectrum as example
                if dataset.num_spectra > 0:
                    y = dataset.spectra.iloc[:, 0].values
                else:
                    return
            elif hasattr(dataset, 'values'):
                # DataFrame - plot first two columns
                if len(dataset.columns) >= 2:
                    x = dataset.iloc[:, 0].values
                    y = dataset.iloc[:, 1].values
                else:
                    return
            else:
                logger.warning(f"Unknown dataset type: {type(dataset)}")
                return

            # Determine plot style
            marker = None
            linestyle = '-'
            if plot_type == "Scatter":
                marker = 'o'
                linestyle = ''
            elif plot_type == "Line+Scatter":
                marker = 'o'
                linestyle = '-'

            # Plot
            line = self.canvas.plot(x, y, label=dataset_name, marker=marker,
                                    linestyle=linestyle)
            self.current_lines.append(line)

            # Set labels
            self.canvas.set_labels(
                xlabel="Independent Variable",
                ylabel="Value",
                title=f"Plot: {dataset_name}"
            )

            logger.info(f"Plotted: {dataset_name}")

        except Exception as e:
            logger.error(f"Error plotting {dataset_name}: {e}", exc_info=True)

    def _clear_plot(self):
        """Clear all curves from plot"""
        self.canvas.clear()
        self.current_lines.clear()
        self.canvas.set_grid(self.grid_checkbox.isChecked())
        logger.info("Plot cleared")

    def _toggle_grid(self, checked):
        """Toggle grid visibility"""
        self.canvas.set_grid(checked)

    def closeEvent(self, event):
        """Handle window close"""
        self.closed.emit()
        event.accept()
