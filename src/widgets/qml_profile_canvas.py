"""
QML Profile Canvas - QQuickPaintedItem for profile/spectrum plotting in QML
Renders line plots using matplotlib with interactive features.
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
from typing import Optional, List, Dict, Any, Tuple
import logging

from PySide6.QtCore import (
    Qt, Signal, Slot, Property, QPointF, QRectF
)
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtQuick import QQuickPaintedItem

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from src.widgets._pyqtgraph_ports.mpl_apply import apply_pyqtgraph_ticks

logger = logging.getLogger(__name__)


class QMLProfileCanvas(QQuickPaintedItem):
    """
    Matplotlib canvas for plotting line profiles and spectra in QML.

    Features:
    - Line profile display
    - Spectrum visualization
    - Multiple overlays (cursors, markers)
    - Auto-scaling with percentile clipping
    - Grid and axis styling

    Signals:
        cursorMoved(x, y): Emitted when cursor moves over plot
        pointClicked(x, y): Emitted on click
        rangeSelected(x1, x2): Emitted after range selection
    """

    # Signals to QML
    cursorMoved = Signal(float, float, arguments=['x', 'y'])
    pointClicked = Signal(float, float, arguments=['x', 'y'])
    rangeSelected = Signal(float, float, arguments=['x1', 'x2'])
    dataChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.AllButtons)
        self.setAcceptHoverEvents(True)
        self.setFlag(QQuickPaintedItem.ItemHasContents, True)

        # Matplotlib setup
        self._dpi = 100
        self.figure = Figure(facecolor='#1a1a1a', dpi=self._dpi)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasAgg(self.figure)

        # Style axes
        self._setupAxesStyle()

        # Data storage
        self._x_data: Optional[np.ndarray] = None
        self._y_data: Optional[np.ndarray] = None
        self._x_label: str = "Distance"
        self._y_label: str = "Value"
        self._title: str = ""

        # Multiple curves support
        self._curves: List[Dict[str, Any]] = []

        # Display options
        self._line_color: str = '#ff6b6b'
        self._line_width: float = 1.5
        self._show_grid: bool = True
        self._show_markers: bool = False
        self._auto_scale: bool = True

        # Cursor/overlay state
        self._cursor_x: Optional[float] = None
        self._show_cursor: bool = False

        # Selection state
        self._is_selecting: bool = False
        self._selection_start: Optional[float] = None
        self._selection_end: Optional[float] = None

        # Render cache
        self._cached_image: Optional[QImage] = None
        self._needs_redraw: bool = True

        # Coordinate transform
        self._data_bounds: Optional[Dict] = None

    @Slot()
    def cleanup(self):
        """Release matplotlib resources to prevent memory leaks."""
        import matplotlib.pyplot as plt
        try:
            if hasattr(self, 'figure') and self.figure is not None:
                self.figure.clear()
                plt.close(self.figure)
                self.figure = None
                self.axes = None
                self.canvas = None
            self._cached_image = None
            self._curves.clear()
            self._x_data = None
            self._y_data = None
            logger.debug("ProfileCanvas cleaned up matplotlib resources")
        except Exception as e:
            logger.warning(f"Error during ProfileCanvas cleanup: {e}")

    def _setupAxesStyle(self):
        """Configure axes appearance for dark theme"""
        self.axes.set_facecolor('#1a1a1a')
        self.axes.tick_params(colors='#888888', labelsize=8)
        for spine in self.axes.spines.values():
            spine.set_color('#444444')
        self.axes.xaxis.label.set_color('#aaaaaa')
        self.axes.yaxis.label.set_color('#aaaaaa')
        self.axes.title.set_color('#cccccc')

    # =========================================================================
    # Properties
    # =========================================================================

    @Property(str)
    def lineColor(self) -> str:
        return self._line_color

    @lineColor.setter
    def lineColor(self, value: str):
        if value != self._line_color:
            self._line_color = value
            self._needs_redraw = True
            self.update()

    @Property(bool)
    def showGrid(self) -> bool:
        return self._show_grid

    @showGrid.setter
    def showGrid(self, value: bool):
        if value != self._show_grid:
            self._show_grid = value
            self._needs_redraw = True
            self.update()

    @Property(bool)
    def hasData(self) -> bool:
        return self._x_data is not None and self._y_data is not None

    @Property(str)
    def xLabel(self) -> str:
        return self._x_label

    @xLabel.setter
    def xLabel(self, value: str):
        self._x_label = value
        self._needs_redraw = True
        self.update()

    @Property(str)
    def yLabel(self) -> str:
        return self._y_label

    @yLabel.setter
    def yLabel(self, value: str):
        self._y_label = value
        self._needs_redraw = True
        self.update()

    # =========================================================================
    # Slots
    # =========================================================================

    @Slot(list, list)
    def setProfileData(self, x_data: List[float], y_data: List[float]):
        """Set profile/line data"""
        self._x_data = np.array(x_data, dtype=np.float64)
        self._y_data = np.array(y_data, dtype=np.float64)
        self._needs_redraw = True
        self.dataChanged.emit()
        self.update()

    @Slot()
    def clearData(self):
        """Clear all data"""
        self._x_data = None
        self._y_data = None
        self._curves.clear()
        self._needs_redraw = True
        self.dataChanged.emit()
        self.update()

    @Slot()
    def clearProfile(self):
        """Alias for clearData - Clear all data"""
        self.clearData()

    @Slot(str, list, list, str)
    def addCurve(self, name: str, x_data: List[float], y_data: List[float], color: str = ""):
        """Add additional curve overlay"""
        curve = {
            'name': name,
            'x': np.array(x_data, dtype=np.float64),
            'y': np.array(y_data, dtype=np.float64),
            'color': color or self._getNextColor(len(self._curves))
        }
        self._curves.append(curve)
        self._needs_redraw = True
        self.update()

    @Slot(list, list, str)
    def addCurveSimple(self, x_data: List[float], y_data: List[float], color: str = ""):
        """Add curve with auto-generated name"""
        name = f"Curve_{len(self._curves) + 1}"
        self.addCurve(name, x_data, y_data, color)

    @Slot(str)
    def removeCurve(self, name: str):
        """Remove curve by name"""
        self._curves = [c for c in self._curves if c['name'] != name]
        self._needs_redraw = True
        self.update()

    @Slot()
    def clearCurves(self):
        """Clear all additional curves"""
        self._curves.clear()
        self._needs_redraw = True
        self.update()

    @Slot(str, str)
    def setLabels(self, x_label: str, y_label: str):
        """Set axis labels"""
        self._x_label = x_label
        self._y_label = y_label
        self._needs_redraw = True
        self.update()

    @Slot(str, str)
    def setAxisLabels(self, x_label: str, y_label: str):
        """Alias for setLabels - Set axis labels"""
        self.setLabels(x_label, y_label)

    @Slot(str)
    def setTitle(self, title: str):
        """Set plot title"""
        self._title = title
        self._needs_redraw = True
        self.update()

    def _getNextColor(self, index: int) -> str:
        """Get color for curve by index"""
        colors = ['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4',
                  '#ffeaa7', '#dfe6e9', '#fd79a8', '#a29bfe']
        return colors[index % len(colors)]

    # =========================================================================
    # Data access
    # =========================================================================

    def setData(self, x: np.ndarray, y: np.ndarray,
                x_label: str = "Distance", y_label: str = "Value"):
        """Set plot data from Python"""
        self._x_data = x.astype(np.float64)
        self._y_data = y.astype(np.float64)
        self._x_label = x_label
        self._y_label = y_label
        self._needs_redraw = True
        self.dataChanged.emit()
        self.update()

    def getData(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Get current data"""
        return self._x_data, self._y_data

    # =========================================================================
    # Painting
    # =========================================================================

    def paint(self, painter: QPainter):
        """Render matplotlib figure and overlays"""
        if self._needs_redraw:
            self._renderMatplotlib()
            self._needs_redraw = False

        if self._cached_image is not None:
            target_rect = QRectF(0, 0, self.width(), self.height())
            painter.drawImage(target_rect, self._cached_image)

            # Draw overlays
            self._drawOverlays(painter)

    def _renderMatplotlib(self):
        """Render matplotlib figure to cached QImage"""
        w, h = int(self.width()), int(self.height())
        if w <= 0 or h <= 0:
            return

        self.figure.set_size_inches(w / self._dpi, h / self._dpi)

        # Clear and configure
        self.axes.clear()
        self._setupAxesStyle()

        # Plot main data
        if self._x_data is not None and self._y_data is not None:
            self.axes.plot(
                self._x_data, self._y_data,
                color=self._line_color,
                linewidth=self._line_width,
                label='Profile'
            )

        # Plot additional curves
        for curve in self._curves:
            self.axes.plot(
                curve['x'], curve['y'],
                color=curve['color'],
                linewidth=self._line_width,
                label=curve['name'],
                alpha=0.8
            )

        # Configure axes
        if self._show_grid:
            self.axes.grid(True, color='#333333', linestyle='-', linewidth=0.5, alpha=0.5)

        self.axes.set_xlabel(self._x_label, fontsize=9)
        self.axes.set_ylabel(self._y_label, fontsize=9)

        if self._title:
            self.axes.set_title(self._title, fontsize=10)

        # Auto-scale with margin
        if self._auto_scale and self._y_data is not None:
            y_range = np.nanmax(self._y_data) - np.nanmin(self._y_data)
            margin = y_range * 0.05 if y_range > 0 else 1
            self.axes.set_ylim(np.nanmin(self._y_data) - margin,
                               np.nanmax(self._y_data) + margin)

        # Legend if multiple curves
        if self._curves:
            self.axes.legend(loc='upper right', fontsize=8,
                            facecolor='#2a2a2a', edgecolor='#444444',
                            labelcolor='#cccccc')

        # Apply the ported pyqtgraph tick layout for parity with the
        # graph canvas (1/2/5 × 10ⁿ family, sensible decimal places).
        # Profile axes are linear-only today, so log mode is off.
        apply_pyqtgraph_ticks(
            self.axes,
            x_size_px=float(w),
            y_size_px=float(h),
            log_x=False, log_y=False,
        )

        self.figure.tight_layout(pad=0.5)

        # Render to buffer
        self.canvas.draw()
        buf = self.canvas.buffer_rgba()
        w_fig, h_fig = self.canvas.get_width_height()

        self._cached_image = QImage(
            buf, w_fig, h_fig, QImage.Format_RGBA8888
        ).copy()

        # Update coordinate transform
        self._updateDataBounds()

    def _updateDataBounds(self):
        """Update pixel-to-data coordinate mapping"""
        if self._x_data is None:
            self._data_bounds = None
            return

        bbox = self.axes.get_position()
        fig_w, fig_h = self.canvas.get_width_height()

        xlim = self.axes.get_xlim()
        ylim = self.axes.get_ylim()

        self._data_bounds = {
            'ax_left': bbox.x0 * fig_w,
            'ax_right': bbox.x1 * fig_w,
            'ax_top': (1 - bbox.y1) * fig_h,
            'ax_bottom': (1 - bbox.y0) * fig_h,
            'x_min': xlim[0],
            'x_max': xlim[1],
            'y_min': ylim[0],
            'y_max': ylim[1]
        }

    def _pixelToData(self, px: float, py: float) -> Tuple[float, float]:
        """Convert pixel to data coordinates"""
        if self._data_bounds is None:
            return 0, 0

        d = self._data_bounds
        ax_width = d['ax_right'] - d['ax_left']
        ax_height = d['ax_bottom'] - d['ax_top']

        # Normalize within axes
        norm_x = (px - d['ax_left']) / ax_width
        norm_y = (py - d['ax_top']) / ax_height

        # Convert to data coordinates
        x = d['x_min'] + norm_x * (d['x_max'] - d['x_min'])
        y = d['y_max'] - norm_y * (d['y_max'] - d['y_min'])  # Y is inverted

        return x, y

    def _drawOverlays(self, painter: QPainter):
        """Draw interactive overlays"""
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Draw cursor line
        if self._show_cursor and self._cursor_x is not None and self._data_bounds:
            d = self._data_bounds
            ax_width = d['ax_right'] - d['ax_left']

            # Convert x to pixel
            norm_x = (self._cursor_x - d['x_min']) / (d['x_max'] - d['x_min'])
            px = d['ax_left'] + norm_x * ax_width

            if d['ax_left'] <= px <= d['ax_right']:
                pen = QPen(QColor(255, 255, 100, 150))
                pen.setWidth(1)
                painter.setPen(pen)
                painter.drawLine(int(px), int(d['ax_top']),
                               int(px), int(d['ax_bottom']))

        # Draw selection range
        if self._selection_start is not None and self._selection_end is not None:
            d = self._data_bounds
            if d:
                ax_width = d['ax_right'] - d['ax_left']

                x1_norm = (self._selection_start - d['x_min']) / (d['x_max'] - d['x_min'])
                x2_norm = (self._selection_end - d['x_min']) / (d['x_max'] - d['x_min'])

                px1 = d['ax_left'] + x1_norm * ax_width
                px2 = d['ax_left'] + x2_norm * ax_width

                rect = QRectF(min(px1, px2), d['ax_top'],
                             abs(px2 - px1), d['ax_bottom'] - d['ax_top'])

                pen = QPen(QColor(100, 200, 255, 150))
                pen.setWidth(1)
                painter.setPen(pen)
                painter.setBrush(QBrush(QColor(100, 200, 255, 40)))
                painter.drawRect(rect)

    # =========================================================================
    # Mouse events
    # =========================================================================

    def mousePressEvent(self, event):
        """Handle mouse press"""
        pos = event.position()
        x, y = self._pixelToData(pos.x(), pos.y())
        self.pointClicked.emit(x, y)

        # Start selection
        self._is_selecting = True
        self._selection_start = x
        self._selection_end = x

    def mouseMoveEvent(self, event):
        """Handle mouse move"""
        pos = event.position()
        x, y = self._pixelToData(pos.x(), pos.y())
        self.cursorMoved.emit(x, y)

        self._cursor_x = x
        self._show_cursor = True

        if self._is_selecting:
            self._selection_end = x
            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if self._is_selecting and self._selection_start != self._selection_end:
            x1 = min(self._selection_start, self._selection_end)
            x2 = max(self._selection_start, self._selection_end)
            self.rangeSelected.emit(x1, x2)

        self._is_selecting = False
        self._selection_start = None
        self._selection_end = None
        self.update()

    def hoverMoveEvent(self, event):
        """Handle hover"""
        pos = event.position()
        x, y = self._pixelToData(pos.x(), pos.y())
        self.cursorMoved.emit(x, y)
        self._cursor_x = x
        self._show_cursor = True
        self.update()

    def hoverLeaveEvent(self, event):
        """Handle hover leave"""
        self._show_cursor = False
        self.update()

    # =========================================================================
    # Geometry
    # =========================================================================

    def geometryChange(self, newGeometry, oldGeometry):
        """Handle resize"""
        super().geometryChange(newGeometry, oldGeometry)
        if newGeometry.size() != oldGeometry.size():
            self._needs_redraw = True
            self.update()
