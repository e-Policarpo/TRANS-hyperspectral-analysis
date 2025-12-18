"""
Map Visualization Window
Displays spatial maps with colorbar, zoom, and export functionality
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import logging
import numpy as np
from pathlib import Path
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.colors import Normalize
from matplotlib import cm
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QToolBar, QComboBox, QPushButton, QLabel,
                                QSlider, QSpinBox, QFileDialog, QGroupBox,
                                QFormLayout, QDoubleSpinBox, QCheckBox)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction
from PIL import Image

logger = logging.getLogger(__name__)


class MapCanvas(FigureCanvasQTAgg):
    """Matplotlib canvas for map visualization"""

    def __init__(self, parent=None, width=8, height=6, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)

        self.map_data = None
        self.image_obj = None
        self.colorbar = None
        self.current_cmap = 'viridis'

        self._apply_dark_theme()
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

    def load_map(self, map_path: str):
        """Load map from file (supports PNG, TIFF, CSV)"""
        path = Path(map_path)
        logger.info(f"Loading map from: {path}")

        try:
            if path.suffix.lower() == '.csv':
                # Load from CSV
                import pandas as pd
                df = pd.read_csv(path, header=None)
                self.map_data = df.values
            elif path.suffix.lower() in ['.tiff', '.tif']:
                # Load from TIFF
                import tifffile
                self.map_data = tifffile.imread(str(path))
            else:
                # Load from image (PNG, etc.)
                img = Image.open(path)
                self.map_data = np.array(img)

            # Convert RGB to grayscale if needed
            if len(self.map_data.shape) == 3:
                self.map_data = np.mean(self.map_data, axis=2)

            self.display_map()
            logger.info(f"Map loaded: shape={self.map_data.shape}")

        except Exception as e:
            logger.error(f"Error loading map: {e}")
            raise

    def set_map_data(self, data: np.ndarray):
        """Set map data directly from numpy array"""
        self.map_data = data
        self.display_map()

    def display_map(self, cmap: str = None):
        """Display the current map data"""
        if self.map_data is None:
            return

        if cmap:
            self.current_cmap = cmap

        self.axes.clear()
        self._apply_dark_theme()

        # Display image
        self.image_obj = self.axes.imshow(
            self.map_data,
            cmap=self.current_cmap,
            aspect='auto',
            origin='upper'
        )

        # Add colorbar
        if self.colorbar:
            self.colorbar.remove()

        self.colorbar = self.figure.colorbar(self.image_obj, ax=self.axes)
        self.colorbar.ax.yaxis.set_tick_params(color='#ffffff')
        self.colorbar.ax.yaxis.set_ticklabels(
            [t.get_text() for t in self.colorbar.ax.yaxis.get_ticklabels()],
            color='#ffffff'
        )

        # Labels
        self.axes.set_xlabel('X (pixels)', color='#ffffff')
        self.axes.set_ylabel('Y (pixels)', color='#ffffff')

        self.figure.tight_layout()
        self.draw()

    def set_colormap(self, cmap: str):
        """Change the colormap"""
        self.current_cmap = cmap
        if self.image_obj:
            self.image_obj.set_cmap(cmap)
            self.draw()

    def set_clim(self, vmin: float, vmax: float):
        """Set color limits"""
        if self.image_obj:
            self.image_obj.set_clim(vmin, vmax)
            self.draw()

    def autoscale(self):
        """Auto-scale color limits to data range"""
        if self.map_data is not None and self.image_obj:
            vmin, vmax = np.nanmin(self.map_data), np.nanmax(self.map_data)
            self.image_obj.set_clim(vmin, vmax)
            self.draw()


class MapVisualizationWindow(QMainWindow):
    """
    Window for visualizing spatial maps with colorbar and tools.

    Features:
    - Multiple colormap options
    - Adjustable color scale
    - Zoom/pan (matplotlib toolbar)
    - Export to various formats
    - Statistics display
    """

    closed = Signal()

    def __init__(self, parent=None, map_path: str = None, map_data: np.ndarray = None, title: str = "Map"):
        super().__init__(parent)

        self.map_path = map_path
        self.setWindowTitle(f"Map: {title}")
        self.resize(900, 700)

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
            QSlider::groove:horizontal {
                background: #3a3a3a;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ff66b2;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
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

        # Load data
        if map_data is not None:
            self.canvas.set_map_data(map_data)
            self._update_stats()
        elif map_path:
            self.load_map(map_path)

    def _setup_ui(self):
        """Setup user interface"""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Left panel - canvas
        canvas_layout = QVBoxLayout()

        # Canvas
        self.canvas = MapCanvas(self)
        canvas_layout.addWidget(self.canvas)

        # Matplotlib toolbar
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setStyleSheet("""
            QToolBar { background-color: #2d2d2d; border: none; }
            QToolButton { background-color: #3a3a3a; border: 1px solid #555; margin: 2px; padding: 3px; }
            QToolButton:hover { background-color: #4a4a4a; }
        """)
        canvas_layout.addWidget(self.toolbar)

        layout.addLayout(canvas_layout, stretch=3)

        # Right panel - controls
        controls_widget = QWidget()
        controls_widget.setMaximumWidth(250)
        controls_layout = QVBoxLayout(controls_widget)

        # Colormap selection
        cmap_group = QGroupBox("Colormap")
        cmap_layout = QFormLayout(cmap_group)

        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems([
            'viridis', 'plasma', 'inferno', 'magma', 'cividis',
            'hot', 'cool', 'coolwarm', 'RdYlBu', 'RdBu',
            'Spectral', 'seismic', 'twilight', 'turbo',
            'gray', 'bone', 'copper', 'pink'
        ])
        self.cmap_combo.currentTextChanged.connect(self._on_cmap_changed)
        cmap_layout.addRow("Colormap:", self.cmap_combo)

        self.invert_cmap = QCheckBox("Invert")
        self.invert_cmap.toggled.connect(self._on_cmap_changed)
        cmap_layout.addRow(self.invert_cmap)

        controls_layout.addWidget(cmap_group)

        # Color scale
        scale_group = QGroupBox("Color Scale")
        scale_layout = QFormLayout(scale_group)

        self.vmin_spin = QDoubleSpinBox()
        self.vmin_spin.setRange(-1e10, 1e10)
        self.vmin_spin.setDecimals(4)
        self.vmin_spin.valueChanged.connect(self._on_scale_changed)
        scale_layout.addRow("Min:", self.vmin_spin)

        self.vmax_spin = QDoubleSpinBox()
        self.vmax_spin.setRange(-1e10, 1e10)
        self.vmax_spin.setDecimals(4)
        self.vmax_spin.valueChanged.connect(self._on_scale_changed)
        scale_layout.addRow("Max:", self.vmax_spin)

        auto_scale_btn = QPushButton("Auto Scale")
        auto_scale_btn.clicked.connect(self._on_auto_scale)
        scale_layout.addRow(auto_scale_btn)

        controls_layout.addWidget(scale_group)

        # Statistics
        stats_group = QGroupBox("Statistics")
        stats_layout = QFormLayout(stats_group)

        self.min_label = QLabel("-")
        self.max_label = QLabel("-")
        self.mean_label = QLabel("-")
        self.std_label = QLabel("-")
        self.shape_label = QLabel("-")

        stats_layout.addRow("Min:", self.min_label)
        stats_layout.addRow("Max:", self.max_label)
        stats_layout.addRow("Mean:", self.mean_label)
        stats_layout.addRow("Std:", self.std_label)
        stats_layout.addRow("Shape:", self.shape_label)

        controls_layout.addWidget(stats_group)

        # Export
        export_group = QGroupBox("Export")
        export_layout = QVBoxLayout(export_group)

        export_png_btn = QPushButton("Export PNG")
        export_png_btn.clicked.connect(lambda: self._export_image('png'))
        export_layout.addWidget(export_png_btn)

        export_tiff_btn = QPushButton("Export TIFF")
        export_tiff_btn.clicked.connect(lambda: self._export_image('tiff'))
        export_layout.addWidget(export_tiff_btn)

        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self._export_csv)
        export_layout.addWidget(export_csv_btn)

        controls_layout.addWidget(export_group)

        controls_layout.addStretch()
        layout.addWidget(controls_widget)

    def load_map(self, map_path: str):
        """Load map from file"""
        self.map_path = map_path
        self.canvas.load_map(map_path)
        self._update_stats()
        self.setWindowTitle(f"Map: {Path(map_path).stem}")

    def _update_stats(self):
        """Update statistics display"""
        if self.canvas.map_data is None:
            return

        data = self.canvas.map_data
        self.min_label.setText(f"{np.nanmin(data):.4g}")
        self.max_label.setText(f"{np.nanmax(data):.4g}")
        self.mean_label.setText(f"{np.nanmean(data):.4g}")
        self.std_label.setText(f"{np.nanstd(data):.4g}")
        self.shape_label.setText(f"{data.shape[0]} x {data.shape[1]}")

        # Update scale spinboxes
        self.vmin_spin.blockSignals(True)
        self.vmax_spin.blockSignals(True)
        self.vmin_spin.setValue(np.nanmin(data))
        self.vmax_spin.setValue(np.nanmax(data))
        self.vmin_spin.blockSignals(False)
        self.vmax_spin.blockSignals(False)

    def _on_cmap_changed(self):
        """Handle colormap change"""
        cmap = self.cmap_combo.currentText()
        if self.invert_cmap.isChecked():
            cmap += '_r'
        self.canvas.set_colormap(cmap)

    def _on_scale_changed(self):
        """Handle color scale change"""
        vmin = self.vmin_spin.value()
        vmax = self.vmax_spin.value()
        self.canvas.set_clim(vmin, vmax)

    def _on_auto_scale(self):
        """Auto-scale to data range"""
        self.canvas.autoscale()
        self._update_stats()

    def _export_image(self, format: str):
        """Export map as image"""
        if format == 'png':
            filter_str = "PNG Files (*.png)"
            suffix = '.png'
        else:
            filter_str = "TIFF Files (*.tiff *.tif)"
            suffix = '.tiff'

        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Export as {format.upper()}", "", filter_str
        )

        if file_path:
            if not file_path.endswith(suffix):
                file_path += suffix

            self.canvas.figure.savefig(
                file_path, dpi=300, bbox_inches='tight',
                facecolor='#0d0d0d', edgecolor='none'
            )
            logger.info(f"Map exported to: {file_path}")

    def _export_csv(self):
        """Export map data as CSV"""
        if self.canvas.map_data is None:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export as CSV", "", "CSV Files (*.csv)"
        )

        if file_path:
            if not file_path.endswith('.csv'):
                file_path += '.csv'

            import pandas as pd
            df = pd.DataFrame(self.canvas.map_data)
            df.to_csv(file_path, index=False, header=False)
            logger.info(f"Map data exported to: {file_path}")

    def closeEvent(self, event):
        """Handle window close"""
        self.closed.emit()
        event.accept()
