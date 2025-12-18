"""
Enhanced Interactive Plot Window with Full Matplotlib Features
Provides zoom, pan, curve selection, color customization, and more
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import logging
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.colors import CSS4_COLORS
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QToolBar, QComboBox, QPushButton, QLabel,
                                QCheckBox, QListWidget, QListWidgetItem, QDockWidget,
                                QColorDialog, QSpinBox, QDoubleSpinBox, QGroupBox,
                                QFormLayout, QMessageBox, QFileDialog)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)


class InteractivePlotCanvas(FigureCanvasQTAgg):
    """Enhanced matplotlib canvas with interactive features"""

    line_selected = Signal(object)  # Emits selected line

    def __init__(self, parent=None, width=10, height=8, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)

        # Track plot lines and their properties
        self.plot_lines = {}  # {line_id: {'line': line_obj, 'data': (x, y), 'label': str, ...}}
        self.line_counter = 0
        self.selected_line = None

        # Style the plot
        self._apply_dark_theme()

        # Connect mouse events for interactive selection
        self.mpl_connect('pick_event', self._on_pick)
        self.mpl_connect('button_press_event', self._on_click)

        self.figure.tight_layout()

    def _apply_dark_theme(self):
        """Apply dark theme to plot"""
        self.axes.set_facecolor('#1a1a1a')
        self.figure.patch.set_facecolor('#0d0d0d')
        self.axes.tick_params(colors='#ffffff', which='both')
        for spine in self.axes.spines.values():
            spine.set_color('#ffffff')
        self.axes.xaxis.label.set_color('#ffffff')
        self.axes.yaxis.label.set_color('#ffffff')
        self.axes.title.set_color('#ffffff')

    def add_curve(self, x, y, label=None, color=None, marker=None, linestyle='-',
                  linewidth=2, alpha=1.0):
        """
        Add a curve to the plot with full customization.

        Returns:
        --------
        line_id : int
            Identifier for the added curve
        """
        # Auto-generate label if not provided
        if label is None:
            label = f"Curve {self.line_counter + 1}"

        # Auto-assign color if not provided
        if color is None:
            colors = ['#ff66b2', '#66b3ff', '#66ff66', '#ffff66', '#ff6666',
                     '#ff66ff', '#66ffff', '#ffaa66', '#aa66ff', '#66ffaa']
            color = colors[self.line_counter % len(colors)]

        # Plot the line with picker enabled for selection
        line, = self.axes.plot(x, y, label=label, color=color, marker=marker,
                               linestyle=linestyle, linewidth=linewidth,
                               alpha=alpha, picker=5)

        # Store line information
        line_id = self.line_counter
        self.plot_lines[line_id] = {
            'line': line,
            'data': (x.copy(), y.copy()),
            'label': label,
            'color': color,
            'marker': marker,
            'linestyle': linestyle,
            'linewidth': linewidth,
            'alpha': alpha,
            'visible': True
        }

        self.line_counter += 1

        # Update legend
        self._update_legend()
        self.draw()

        return line_id

    def remove_curve(self, line_id):
        """Remove a curve from the plot"""
        if line_id in self.plot_lines:
            line_info = self.plot_lines[line_id]
            line_info['line'].remove()
            del self.plot_lines[line_id]
            self._update_legend()
            self.draw()
            logger.info(f"Removed curve: {line_info['label']}")

    def update_curve_properties(self, line_id, **kwargs):
        """
        Update properties of a curve.

        Supported properties:
        - label, color, marker, linestyle, linewidth, alpha, visible
        """
        if line_id not in self.plot_lines:
            return

        line_info = self.plot_lines[line_id]
        line = line_info['line']

        # Update properties
        for prop, value in kwargs.items():
            if prop == 'label':
                line.set_label(value)
                line_info['label'] = value
            elif prop == 'color':
                line.set_color(value)
                line_info['color'] = value
            elif prop == 'marker':
                line.set_marker(value)
                line_info['marker'] = value
            elif prop == 'linestyle':
                line.set_linestyle(value)
                line_info['linestyle'] = value
            elif prop == 'linewidth':
                line.set_linewidth(value)
                line_info['linewidth'] = value
            elif prop == 'alpha':
                line.set_alpha(value)
                line_info['alpha'] = value
            elif prop == 'visible':
                line.set_visible(value)
                line_info['visible'] = value

        self._update_legend()
        self.draw()

    def _update_legend(self):
        """Update legend with current curves"""
        visible_lines = [info['line'] for info in self.plot_lines.values()
                        if info['visible']]
        if visible_lines:
            self.axes.legend(facecolor='#2d2d2d', edgecolor='#ffffff',
                           labelcolor='#ffffff', loc='best')
        else:
            legend = self.axes.get_legend()
            if legend:
                legend.remove()

    def _on_pick(self, event):
        """Handle line pick event"""
        line = event.artist
        # Find which line_id corresponds to this line
        for line_id, info in self.plot_lines.items():
            if info['line'] == line:
                self.selected_line = line_id
                self.line_selected.emit(line_id)
                logger.info(f"Selected: {info['label']}")
                break

    def _on_click(self, event):
        """Handle click event"""
        if event.button == 3:  # Right click
            # Deselect
            self.selected_line = None

    def clear_all(self):
        """Clear all curves"""
        self.axes.clear()
        self.plot_lines.clear()
        self.line_counter = 0
        self.selected_line = None
        self._apply_dark_theme()
        self.draw()

    def set_labels(self, xlabel=None, ylabel=None, title=None):
        """Set axis labels and title"""
        if xlabel:
            self.axes.set_xlabel(xlabel, color='#ffffff')
        if ylabel:
            self.axes.set_ylabel(ylabel, color='#ffffff')
        if title:
            self.axes.set_title(title, color='#ffffff')
        self.draw()

    def set_grid(self, visible, which='both', axis='both'):
        """Toggle grid"""
        self.axes.grid(visible, which=which, axis=axis, color='#555555',
                      linestyle='--', linewidth=0.5)
        self.draw()

    def set_log_scale(self, x_log=False, y_log=False):
        """Set logarithmic scale for axes"""
        if x_log:
            self.axes.set_xscale('log')
        else:
            self.axes.set_xscale('linear')

        if y_log:
            self.axes.set_yscale('log')
        else:
            self.axes.set_yscale('linear')

        self.draw()

    def autoscale(self):
        """Auto-scale axes to fit all data"""
        self.axes.autoscale()
        self.draw()


class EnhancedPlotWindow(QMainWindow):
    """
    Enhanced plot window with full matplotlib navigation and customization.

    Features:
    - Zoom, pan (matplotlib toolbar)
    - Curve selection and manipulation
    - Color, marker, linestyle customization
    - Multiple curve support
    - Grid, log scale toggle
    - Export to image
    """

    closed = Signal()

    def __init__(self, parent=None, datasets=None):
        super().__init__(parent)
        self.datasets = datasets or {}

        self.setWindowTitle("Enhanced Plot Window")
        self.resize(1200, 800)

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
            QComboBox, QPushButton, QSpinBox, QDoubleSpinBox {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
                min-width: 80px;
            }
            QComboBox:hover, QPushButton:hover {
                background-color: #4a4a4a;
            }
            QLabel {
                color: #ffffff;
                padding: 2px;
            }
            QCheckBox {
                color: #ffffff;
            }
            QListWidget {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 1px solid #404040;
            }
            QListWidget::item:selected {
                background-color: #ff66b2;
                color: #000000;
            }
            QDockWidget {
                titlebar-close-icon: url(close.png);
                titlebar-normal-icon: url(float.png);
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 5px;
            }
            QGroupBox {
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 3px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)

        self._setup_ui()

    def _setup_ui(self):
        """Setup user interface"""
        # Central widget with canvas
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Create canvas
        self.canvas = InteractivePlotCanvas(self, width=10, height=8, dpi=100)
        self.canvas.line_selected.connect(self._on_line_selected)

        # Add matplotlib navigation toolbar
        self.nav_toolbar = NavigationToolbar2QT(self.canvas, self)
        self.nav_toolbar.setStyleSheet("""
            QToolBar {
                background-color: #2d2d2d;
                border: none;
                spacing: 3px;
            }
        """)

        layout.addWidget(self.nav_toolbar)
        layout.addWidget(self.canvas)

        # Create main toolbar
        self._create_main_toolbar()

        # Create curve list dock
        self._create_curve_list_dock()

        # Create properties dock
        self._create_properties_dock()

        # Apply initial settings
        self.canvas.set_grid(True)

    def _create_main_toolbar(self):
        """Create main toolbar with plot controls"""
        toolbar = QToolBar("Main")
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # Dataset selector
        toolbar.addWidget(QLabel("Dataset:"))
        self.dataset_combo = QComboBox()
        self.dataset_combo.addItems(list(self.datasets.keys()))
        toolbar.addWidget(self.dataset_combo)

        toolbar.addSeparator()

        # Add curve button
        add_btn = QPushButton("Add Curve")
        add_btn.clicked.connect(self._add_curve_from_dataset)
        toolbar.addWidget(add_btn)

        # Remove curve button
        remove_btn = QPushButton("Remove Curve")
        remove_btn.clicked.connect(self._remove_selected_curve)
        toolbar.addWidget(remove_btn)

        # Clear all button
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_all_curves)
        toolbar.addWidget(clear_btn)

        toolbar.addSeparator()

        # Grid toggle
        self.grid_check = QCheckBox("Grid")
        self.grid_check.setChecked(True)
        self.grid_check.toggled.connect(lambda checked: self.canvas.set_grid(checked))
        toolbar.addWidget(self.grid_check)

        # Log scale toggles
        self.log_x_check = QCheckBox("Log X")
        self.log_x_check.toggled.connect(self._update_scales)
        toolbar.addWidget(self.log_x_check)

        self.log_y_check = QCheckBox("Log Y")
        self.log_y_check.toggled.connect(self._update_scales)
        toolbar.addWidget(self.log_y_check)

        toolbar.addSeparator()

        # Autoscale button
        autoscale_btn = QPushButton("Autoscale")
        autoscale_btn.clicked.connect(self.canvas.autoscale)
        toolbar.addWidget(autoscale_btn)

        # Export button
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._export_plot)
        toolbar.addWidget(export_btn)

        # View data table button
        view_data_btn = QPushButton("View Data Table")
        view_data_btn.clicked.connect(self._view_data_table)
        toolbar.addWidget(view_data_btn)

    def _create_curve_list_dock(self):
        """Create dockable curve list"""
        dock = QDockWidget("Curves", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        # Curve list widget
        self.curve_list = QListWidget()
        self.curve_list.itemClicked.connect(self._on_curve_list_click)
        self.curve_list.itemDoubleClicked.connect(self._on_curve_list_double_click)

        dock.setWidget(self.curve_list)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _create_properties_dock(self):
        """Create dockable properties panel"""
        dock = QDockWidget("Properties", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Curve properties group
        group = QGroupBox("Curve Properties")
        form_layout = QFormLayout()

        # Color button
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self._choose_color)
        self.color_btn.setMaximumWidth(100)
        form_layout.addRow("Color:", self.color_btn)

        # Line width
        self.linewidth_spin = QDoubleSpinBox()
        self.linewidth_spin.setRange(0.5, 10.0)
        self.linewidth_spin.setValue(2.0)
        self.linewidth_spin.setSingleStep(0.5)
        self.linewidth_spin.valueChanged.connect(self._update_curve_properties)
        form_layout.addRow("Width:", self.linewidth_spin)

        # Line style
        self.linestyle_combo = QComboBox()
        self.linestyle_combo.addItems(["-", "--", "-.", ":", "None"])
        self.linestyle_combo.currentTextChanged.connect(self._update_curve_properties)
        form_layout.addRow("Style:", self.linestyle_combo)

        # Marker
        self.marker_combo = QComboBox()
        self.marker_combo.addItems(["None", "o", "s", "^", "v", "<", ">", "d", "*", "+", "x"])
        self.marker_combo.currentTextChanged.connect(self._update_curve_properties)
        form_layout.addRow("Marker:", self.marker_combo)

        # Alpha
        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setRange(0.0, 1.0)
        self.alpha_spin.setValue(1.0)
        self.alpha_spin.setSingleStep(0.1)
        self.alpha_spin.valueChanged.connect(self._update_curve_properties)
        form_layout.addRow("Opacity:", self.alpha_spin)

        group.setLayout(form_layout)
        layout.addWidget(group)

        layout.addStretch()

        dock.setWidget(widget)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        # Initially disable properties
        group.setEnabled(False)
        self.properties_group = group

    def _add_curve_from_dataset(self):
        """Add curve from selected dataset - shows curve selector dialog"""
        dataset_name = self.dataset_combo.currentText()
        if not dataset_name or dataset_name not in self.datasets:
            QMessageBox.warning(self, "No Dataset", "Please select a valid dataset")
            return

        dataset = self.datasets[dataset_name]

        try:
            # Get data
            if hasattr(dataset, 'independent_var') and hasattr(dataset, 'spectra'):
                # Show curve selector dialog
                self._show_curve_selector(dataset_name, dataset)
            elif hasattr(dataset, 'values'):
                # For DataFrame-like objects, just add the first curve
                if len(dataset.columns) >= 2:
                    x = dataset.iloc[:, 0].values
                    y = dataset.iloc[:, 1].values
                    label = f"{dataset_name}"
                    self.canvas.add_curve(x, y, label=label)
                    self._update_curve_list()
                    self.canvas.set_labels(
                        xlabel=getattr(dataset, 'independent_var_name', 'X'),
                        ylabel='Value',
                        title=dataset_name
                    )
            else:
                QMessageBox.warning(self, "Error", "Unknown dataset format")
                return

        except Exception as e:
            logger.error(f"Error adding curve: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to add curve: {e}")

    def _show_curve_selector(self, dataset_name, dataset):
        """Show dialog to select which curves to add"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Select Curves from {dataset_name}")
        dialog.resize(400, 500)
        dialog.setStyleSheet(self.styleSheet())  # Apply same dark theme

        layout = QVBoxLayout(dialog)

        # Info label
        info_label = QLabel(f"Dataset: {dataset_name}\nSpectra: {dataset.num_spectra}")
        layout.addWidget(info_label)

        # List widget with checkboxes
        list_widget = QListWidget()
        list_widget.setSelectionMode(QListWidget.MultiSelection)

        # Add all curve indices to list
        for i in range(dataset.num_spectra):
            item = QListWidgetItem(f"Curve {i + 1}")
            item.setData(Qt.UserRole, i)  # Store the index
            list_widget.addItem(item)

        # Select first curve by default
        if list_widget.count() > 0:
            list_widget.item(0).setSelected(True)

        layout.addWidget(list_widget)

        # Buttons
        button_layout = QHBoxLayout()

        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: list_widget.selectAll())
        button_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(lambda: list_widget.clearSelection())
        button_layout.addWidget(deselect_all_btn)

        button_layout.addStretch()

        add_btn = QPushButton("Add Selected")
        add_btn.setDefault(True)
        add_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(add_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Execute dialog
        if dialog.exec() == QDialog.Accepted:
            # Get selected indices
            selected_items = list_widget.selectedItems()
            if not selected_items:
                return

            # Add all selected curves
            x = dataset.independent_var
            for item in selected_items:
                idx = item.data(Qt.UserRole)
                if 0 <= idx < dataset.num_spectra:
                    y = dataset.spectra.iloc[:, idx].values
                    label = f"{dataset_name} - Curve {idx + 1}"
                    self.canvas.add_curve(x, y, label=label)
                    logger.info(f"Added curve: {label}")

            # Update curve list
            self._update_curve_list()

            # Set labels
            self.canvas.set_labels(
                xlabel=getattr(dataset, 'independent_var_name', 'X'),
                ylabel='Intensity',
                title=dataset_name
            )

    def _remove_selected_curve(self):
        """Remove currently selected curve"""
        current_item = self.curve_list.currentItem()
        if not current_item:
            return

        line_id = current_item.data(Qt.UserRole)
        self.canvas.remove_curve(line_id)
        self._update_curve_list()

    def _clear_all_curves(self):
        """Clear all curves"""
        self.canvas.clear_all()
        self._update_curve_list()
        self.canvas.set_grid(self.grid_check.isChecked())

    def _update_curve_list(self):
        """Update curve list widget"""
        self.curve_list.clear()
        for line_id, info in self.canvas.plot_lines.items():
            item = QListWidgetItem(info['label'])
            item.setData(Qt.UserRole, line_id)
            self.curve_list.addItem(item)

    def _on_curve_list_click(self, item):
        """Handle curve list click"""
        line_id = item.data(Qt.UserRole)
        self._select_curve(line_id)

    def _on_curve_list_double_click(self, item):
        """Handle curve list double click - toggle visibility"""
        line_id = item.data(Qt.UserRole)
        info = self.canvas.plot_lines[line_id]
        new_visibility = not info['visible']
        self.canvas.update_curve_properties(line_id, visible=new_visibility)

    def _on_line_selected(self, line_id):
        """Handle line selection from canvas"""
        # Update curve list selection
        for i in range(self.curve_list.count()):
            item = self.curve_list.item(i)
            if item.data(Qt.UserRole) == line_id:
                self.curve_list.setCurrentItem(item)
                break
        self._select_curve(line_id)

    def _select_curve(self, line_id):
        """Select a curve and update properties panel"""
        if line_id not in self.canvas.plot_lines:
            return

        info = self.canvas.plot_lines[line_id]
        self.canvas.selected_line = line_id

        # Enable and update properties
        self.properties_group.setEnabled(True)

        # Update property widgets
        color = QColor(info['color'])
        self.color_btn.setStyleSheet(f"background-color: {info['color']};")
        self.linewidth_spin.setValue(info['linewidth'])

        linestyle_map = {'-': 0, '--': 1, '-.': 2, ':': 3, 'None': 4}
        self.linestyle_combo.setCurrentIndex(linestyle_map.get(info['linestyle'], 0))

        marker_map = {'None': 0, 'o': 1, 's': 2, '^': 3, 'v': 4, '<': 5, '>': 6,
                     'd': 7, '*': 8, '+': 9, 'x': 10}
        marker = info['marker'] if info['marker'] else 'None'
        self.marker_combo.setCurrentIndex(marker_map.get(marker, 0))

        self.alpha_spin.setValue(info['alpha'])

    def _choose_color(self):
        """Open color picker dialog"""
        if self.canvas.selected_line is None:
            return

        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            self.color_btn.setStyleSheet(f"background-color: {hex_color};")
            self.canvas.update_curve_properties(self.canvas.selected_line, color=hex_color)

    def _update_curve_properties(self):
        """Update selected curve properties"""
        if self.canvas.selected_line is None:
            return

        linestyle = self.linestyle_combo.currentText()
        marker = self.marker_combo.currentText()
        if marker == "None":
            marker = None

        self.canvas.update_curve_properties(
            self.canvas.selected_line,
            linewidth=self.linewidth_spin.value(),
            linestyle=linestyle,
            marker=marker,
            alpha=self.alpha_spin.value()
        )

    def _update_scales(self):
        """Update axis scales"""
        self.canvas.set_log_scale(
            self.log_x_check.isChecked(),
            self.log_y_check.isChecked()
        )

    def _export_plot(self):
        """Export plot to image file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Plot", "",
            "PNG Files (*.png);;PDF Files (*.pdf);;SVG Files (*.svg);;All Files (*)"
        )

        if filename:
            try:
                self.canvas.figure.savefig(filename, dpi=300, bbox_inches='tight',
                                          facecolor='#0d0d0d')
                logger.info(f"Plot exported to: {filename}")
                QMessageBox.information(self, "Success", f"Plot saved to:\n{filename}")
            except Exception as e:
                logger.error(f"Export error: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def _view_data_table(self):
        """Create table window from selected curves"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel, QListWidgetItem, QCheckBox
        from src.widgets.enhanced_table_window import EnhancedTableWindow
        import pandas as pd

        if not self.canvas.plot_lines:
            QMessageBox.information(self, "No Data", "No curves to display in table")
            return

        # Create selection dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Curves for Table")
        dialog.resize(400, 400)
        dialog.setStyleSheet(self.styleSheet())

        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Select curves to include in table:"))

        # Curve list
        curve_list = QListWidget()
        curve_list.setSelectionMode(QListWidget.MultiSelection)
        for line_id, info in self.canvas.plot_lines.items():
            item = QListWidgetItem(info['label'])
            item.setData(Qt.UserRole, line_id)
            item.setSelected(True)  # Select all by default
            curve_list.addItem(item)
        layout.addWidget(curve_list)

        # Options
        common_x_check = QCheckBox("Use common X-axis (interpolate if needed)")
        common_x_check.setChecked(True)
        layout.addWidget(common_x_check)

        # Buttons
        button_layout = QHBoxLayout()
        create_btn = QPushButton("Create Table")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(create_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        cancel_btn.clicked.connect(dialog.reject)

        def create_table():
            selected_items = curve_list.selectedItems()

            if not selected_items:
                QMessageBox.warning(dialog, "No Selection", "Please select at least one curve")
                return

            try:
                # Get selected curve data
                curve_data = {}
                for item in selected_items:
                    line_id = item.data(Qt.UserRole)
                    info = self.canvas.plot_lines[line_id]
                    x, y = info['data']
                    curve_data[info['label']] = (x.copy(), y.copy())

                # Create DataFrame
                if common_x_check.isChecked() and len(curve_data) > 1:
                    # Find common X range
                    all_x = [x for x, y in curve_data.values()]
                    x_min = max(x.min() for x in all_x)
                    x_max = min(x.max() for x in all_x)

                    # Use first curve's X as reference, filter to common range
                    first_x = list(curve_data.values())[0][0]
                    mask = (first_x >= x_min) & (first_x <= x_max)
                    common_x = first_x[mask]

                    # Build DataFrame
                    data_dict = {'X': common_x}

                    for label, (x, y) in curve_data.items():
                        # Interpolate Y values to common X
                        y_interp = np.interp(common_x, x, y)
                        data_dict[label] = y_interp

                    df = pd.DataFrame(data_dict)
                else:
                    # Each curve gets its own X column
                    max_len = max(len(x) for x, y in curve_data.values())

                    data_dict = {}
                    for label, (x, y) in curve_data.items():
                        # Pad with NaN if needed
                        x_padded = np.pad(x, (0, max_len - len(x)), constant_values=np.nan)
                        y_padded = np.pad(y, (0, max_len - len(y)), constant_values=np.nan)

                        data_dict[f"{label}_X"] = x_padded
                        data_dict[f"{label}_Y"] = y_padded

                    df = pd.DataFrame(data_dict)

                # Create table window
                table_window = EnhancedTableWindow(data=df)
                table_window.setWindowTitle(f"Data from {self.windowTitle()}")
                table_window.show()

                dialog.accept()

                logger.info(f"Created table from {len(selected_items)} curves")

            except Exception as e:
                logger.error(f"Table creation error: {e}", exc_info=True)
                QMessageBox.critical(dialog, "Error", f"Failed to create table:\n{e}")

        create_btn.clicked.connect(create_table)

        dialog.exec_()

    def closeEvent(self, event):
        """Handle window close"""
        self.closed.emit()
        event.accept()
