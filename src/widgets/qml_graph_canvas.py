"""
QML Graph Canvas - Enhanced QQuickPaintedItem for interactive graph plotting in QML
Provides full matplotlib integration with curve management, operations, and styling.
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
from typing import Optional, List, Dict, Any, Tuple
import logging
from dataclasses import dataclass, field
from scipy import signal
from scipy.ndimage import gaussian_filter1d

from PySide6.QtCore import (
    Qt, Signal, Slot, Property, QPointF, QRectF, QObject, QTimer
)
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtQuick import QQuickPaintedItem

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from src.widgets._pyqtgraph_ports.mpl_apply import apply_pyqtgraph_ticks

logger = logging.getLogger(__name__)


@dataclass
class CurveData:
    """Data class for curve properties"""
    curve_id: int
    label: str
    x: np.ndarray
    y: np.ndarray
    color: str = "#5BCEFA"
    linestyle: str = "-"
    linewidth: float = 2.0
    marker: str = ""
    alpha: float = 1.0
    visible: bool = True
    # Link to table for processing
    table_id: Optional[str] = None
    column_index: Optional[int] = None


class QMLGraphCanvas(QQuickPaintedItem):
    """
    Enhanced matplotlib canvas for QML with full curve management.

    Features:
    - Multiple curves with individual styling
    - Interactive curve selection
    - Math operations (derivative, smooth, integrate)
    - Linear/log scale support
    - Grid and legend control
    - Zoom, pan, and auto-scale
    - Export capabilities

    Signals:
        curveClicked(curveId): Emitted when a curve is clicked
        curveSelected(curveId): Emitted when curve selection changes
        cursorMoved(x, y): Emitted on cursor movement
        rangeSelected(x1, y1, x2, y2): Emitted after range selection
        curveProcessed(curveId, operation, newCurveId): Emitted after operation
    """

    # Signals to QML
    curveClicked = Signal(int, arguments=['curveId'])
    curveSelected = Signal(int, arguments=['curveId'])
    cursorMoved = Signal(float, float, arguments=['x', 'y'])
    pointClicked = Signal(float, float, arguments=['x', 'y'])
    rangeSelected = Signal(float, float, float, float, arguments=['x1', 'y1', 'x2', 'y2'])
    curveProcessed = Signal(int, str, int, arguments=['curveId', 'operation', 'newCurveId'])
    curvesChanged = Signal()
    scaleChanged = Signal()

    # Color palette for auto-assignment
    DEFAULT_COLORS = [
        '#5BCEFA', '#F5A9B8', '#66ff66', '#FFD700', '#FF6B6B',
        '#9B4F96', '#00BCD4', '#FF9800', '#E91E63', '#2ECC71'
    ]

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

        # Curve storage
        self._curves: Dict[int, CurveData] = {}
        self._curve_counter: int = 0
        self._selected_curve_id: Optional[int] = None

        # Labels and title
        self._x_label: str = "X"
        self._y_label: str = "Y"
        self._title: str = ""

        # Scale options
        self._x_scale: str = "linear"  # "linear" or "log"
        self._y_scale: str = "linear"

        # Display options
        self._show_grid: bool = True
        self._show_legend: bool = True
        self._auto_scale: bool = True
        self._x_min: float = 0
        self._x_max: float = 1
        self._y_min: float = 0
        self._y_max: float = 1

        # Cursor state
        self._cursor_x: Optional[float] = None
        self._cursor_y: Optional[float] = None
        self._show_cursor: bool = False

        # Selection / drag-zoom state
        self._is_selecting: bool = False
        self._selection_start: Optional[Tuple[float, float]] = None
        self._selection_end: Optional[Tuple[float, float]] = None

        # Pan state (right-drag, tracked in pixel space for log-scale correctness)
        self._is_panning: bool = False
        self._pan_last_px: Optional[Tuple[float, float]] = None

        # Zoom state
        self._zoom_level: float = 1.0

        # Render cache
        self._cached_image: Optional[QImage] = None
        self._needs_redraw: bool = True
        self._component_complete: bool = False

        # Resize debounce timer — avoids re-rendering matplotlib on every pixel
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)  # ms
        self._resize_timer.timeout.connect(self._onResizeFinished)

        # Coordinate transform
        self._data_bounds: Optional[Dict] = None

    def componentComplete(self):
        """Called when QML component is fully constructed"""
        super().componentComplete()
        self._component_complete = True
        self._needs_redraw = True
        self.update()

    @Slot()
    def cleanup(self):
        """Release matplotlib resources to prevent memory leaks."""
        import matplotlib.pyplot as plt
        try:
            if hasattr(self, '_resize_timer'):
                self._resize_timer.stop()
            if hasattr(self, 'figure') and self.figure is not None:
                self.figure.clear()
                plt.close(self.figure)
                self.figure = None
                self.axes = None
                self.canvas = None
            self._cached_image = None
            self._curves.clear()
            logger.debug("GraphCanvas cleaned up matplotlib resources")
        except Exception as e:
            logger.warning(f"Error during GraphCanvas cleanup: {e}")

    def _setupAxesStyle(self):
        """Configure axes appearance for dark theme"""
        self.axes.set_facecolor('#1a1a1a')
        self.axes.tick_params(colors='#888888', labelsize=9)
        for spine in self.axes.spines.values():
            spine.set_color('#444444')
        self.axes.xaxis.label.set_color('#cccccc')
        self.axes.yaxis.label.set_color('#cccccc')
        self.axes.title.set_color('#ffffff')

    # =========================================================================
    # Properties (QML accessible)
    # Using simpler property definitions to avoid PySide6 cache issues
    # =========================================================================

    @Property(str)
    def xLabel(self) -> str:
        return self._x_label

    @xLabel.setter
    def xLabel(self, value: str):
        if value != self._x_label:
            self._x_label = value
            self._needs_redraw = True
            self.scaleChanged.emit()
            self.update()

    @Property(str)
    def yLabel(self) -> str:
        return self._y_label

    @yLabel.setter
    def yLabel(self, value: str):
        if value != self._y_label:
            self._y_label = value
            self._needs_redraw = True
            self.scaleChanged.emit()
            self.update()

    @Property(str)
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str):
        if value != self._title:
            self._title = value
            self._needs_redraw = True
            self.scaleChanged.emit()
            self.update()

    @Property(str)
    def xScale(self) -> str:
        return self._x_scale

    @xScale.setter
    def xScale(self, value: str):
        if value in ("linear", "log") and value != self._x_scale:
            self._x_scale = value
            self._needs_redraw = True
            self.scaleChanged.emit()
            self.update()

    @Property(str)
    def yScale(self) -> str:
        return self._y_scale

    @yScale.setter
    def yScale(self, value: str):
        if value in ("linear", "log") and value != self._y_scale:
            self._y_scale = value
            self._needs_redraw = True
            self.scaleChanged.emit()
            self.update()

    @Property(bool)
    def showGrid(self) -> bool:
        return self._show_grid

    @showGrid.setter
    def showGrid(self, value: bool):
        if value != self._show_grid:
            self._show_grid = value
            self._needs_redraw = True
            self.curvesChanged.emit()
            self.update()

    @Property(bool)
    def showLegend(self) -> bool:
        return self._show_legend

    @showLegend.setter
    def showLegend(self, value: bool):
        if value != self._show_legend:
            self._show_legend = value
            self._needs_redraw = True
            self.curvesChanged.emit()
            self.update()

    @Property(bool)
    def autoScale(self) -> bool:
        return self._auto_scale

    @autoScale.setter
    def autoScale(self, value: bool):
        if value != self._auto_scale:
            self._auto_scale = value
            self._needs_redraw = True
            self.update()

    @Property(int)
    def selectedCurveId(self) -> int:
        return self._selected_curve_id if self._selected_curve_id is not None else -1

    @Property(int)
    def curveCount(self) -> int:
        return len(self._curves)

    @Property(bool)
    def hasCurves(self) -> bool:
        return len(self._curves) > 0

    # =========================================================================
    # Curve Management Slots
    # =========================================================================

    @Slot(str, list, list, str, float, result=int)
    def addCurve(self, label: str, x_data: List[float], y_data: List[float],
                 color: str = "", linewidth: float = 2.0) -> int:
        """
        Add a curve to the graph.

        Returns:
            int: The curve ID for future reference
        """
        curve_id = self._curve_counter
        self._curve_counter += 1

        # Auto-assign color if not provided
        if not color:
            color = self.DEFAULT_COLORS[curve_id % len(self.DEFAULT_COLORS)]

        curve = CurveData(
            curve_id=curve_id,
            label=label or f"Curve {curve_id + 1}",
            x=np.array(x_data, dtype=np.float64),
            y=np.array(y_data, dtype=np.float64),
            color=color,
            linewidth=linewidth
        )
        self._curves[curve_id] = curve

        self._needs_redraw = True
        self.curvesChanged.emit()
        self.update()

        logger.info(f"Added curve: {label} (ID: {curve_id})")
        return curve_id

    @Slot(int, str, list, list, str, int, int)
    def addCurveWithTableLink(self, curve_id: int, label: str, x_data: List[float],
                               y_data: List[float], table_id: str,
                               x_col: int, y_col: int):
        """Add a curve linked to a table column"""
        if curve_id == -1:
            curve_id = self._curve_counter
            self._curve_counter += 1

        color = self.DEFAULT_COLORS[curve_id % len(self.DEFAULT_COLORS)]

        curve = CurveData(
            curve_id=curve_id,
            label=label,
            x=np.array(x_data, dtype=np.float64),
            y=np.array(y_data, dtype=np.float64),
            color=color,
            table_id=table_id,
            column_index=y_col
        )
        self._curves[curve_id] = curve

        self._needs_redraw = True
        self.curvesChanged.emit()
        self.update()

    @Slot(int)
    def removeCurve(self, curve_id: int):
        """Remove a curve by ID"""
        if curve_id in self._curves:
            label = self._curves[curve_id].label
            del self._curves[curve_id]

            if self._selected_curve_id == curve_id:
                self._selected_curve_id = None
                self.curveSelected.emit(-1)

            self._needs_redraw = True
            self.curvesChanged.emit()
            self.update()
            logger.info(f"Removed curve: {label}")

    @Slot()
    def clearCurves(self):
        """Remove all curves"""
        self._curves.clear()
        self._selected_curve_id = None
        self._curve_counter = 0
        self._needs_redraw = True
        self.curvesChanged.emit()
        self.curveSelected.emit(-1)
        self.update()

    @Slot(int, str, str)
    def updateCurveProperty(self, curve_id: int, prop: str, value: str):
        """Update a curve property"""
        if curve_id not in self._curves:
            return

        curve = self._curves[curve_id]

        if prop == "label":
            curve.label = value
        elif prop == "color":
            curve.color = value
        elif prop == "linestyle":
            curve.linestyle = value
        elif prop == "linewidth":
            curve.linewidth = float(value)
        elif prop == "marker":
            curve.marker = value
        elif prop == "visible":
            curve.visible = value.lower() == "true"
        elif prop == "alpha":
            curve.alpha = float(value)

        self._needs_redraw = True
        # Don't emit curvesChanged for property updates — only for add/remove.
        # This prevents the ListView from being fully rebuilt on every checkbox toggle.
        self.update()

    @Slot(int)
    def selectCurve(self, curve_id: int):
        """Select a curve by ID"""
        if curve_id in self._curves or curve_id == -1:
            self._selected_curve_id = curve_id if curve_id != -1 else None
            self.curveSelected.emit(curve_id)
            self._needs_redraw = True
            self.update()

    @Slot(result='QVariantList')
    def getCurveList(self) -> List[Dict]:
        """Get list of curves with their properties"""
        curves = []
        for cid, curve in self._curves.items():
            curves.append({
                'id': cid,
                'label': curve.label,
                'color': curve.color,
                'linestyle': curve.linestyle,
                'linewidth': curve.linewidth,
                'visible': curve.visible,
                'pointCount': len(curve.x)
            })
        return curves

    @Slot(int, result='QVariantList')
    def getCurveData(self, curve_id: int) -> List:
        """Get curve data as [x_list, y_list]"""
        if curve_id in self._curves:
            curve = self._curves[curve_id]
            return [curve.x.tolist(), curve.y.tolist()]
        return [[], []]

    # =========================================================================
    # Math Operations
    # =========================================================================

    @Slot(int, str, 'QVariantMap', result=int)
    def applyCurveOperation(self, curve_id: int, operation: str, params: Dict = None) -> int:
        """
        Apply a mathematical operation to a curve and add result as new curve.

        Operations:
        - derivative: First or second derivative
        - smooth: Savitzky-Golay or Gaussian smoothing
        - integrate: Cumulative integration
        - normalize: Normalize to [0, 1]
        - baseline: Subtract baseline

        Returns:
            int: New curve ID, or -1 on error
        """
        if curve_id not in self._curves:
            logger.error(f"Curve {curve_id} not found")
            return -1

        params = params or {}
        curve = self._curves[curve_id]
        x = curve.x.copy()
        y = curve.y.copy()

        try:
            if operation == "derivative":
                order = params.get('order', 1)
                y_new = np.gradient(y, x)
                if order == 2:
                    y_new = np.gradient(y_new, x)
                label = f"{curve.label} (d{order})"

            elif operation == "smooth":
                method = params.get('method', 'savgol')
                window = params.get('window', 11)
                if window % 2 == 0:
                    window += 1

                if method == 'savgol':
                    poly_order = min(params.get('poly_order', 3), window - 1)
                    y_new = signal.savgol_filter(y, window, poly_order)
                elif method == 'gaussian':
                    sigma = window / 6.0
                    y_new = gaussian_filter1d(y, sigma)
                else:  # moving average
                    kernel = np.ones(window) / window
                    y_new = np.convolve(y, kernel, mode='same')
                label = f"{curve.label} (smooth)"

            elif operation == "integrate":
                y_new = np.cumsum(y) * np.gradient(x).mean()
                label = f"{curve.label} (integral)"

            elif operation == "normalize":
                y_min, y_max = np.min(y), np.max(y)
                if y_max - y_min > 0:
                    y_new = (y - y_min) / (y_max - y_min)
                else:
                    y_new = y.copy()
                label = f"{curve.label} (norm)"

            elif operation == "baseline":
                # Simple linear baseline from endpoints
                slope = (y[-1] - y[0]) / (x[-1] - x[0])
                baseline = y[0] + slope * (x - x[0])
                y_new = y - baseline
                label = f"{curve.label} (no baseline)"

            elif operation == "fft":
                # Magnitude of FFT
                n = len(y)
                freq = np.fft.fftfreq(n, d=(x[1] - x[0]) if len(x) > 1 else 1)
                fft_vals = np.fft.fft(y)
                y_new = np.abs(fft_vals[:n // 2])
                x = freq[:n // 2]
                label = f"{curve.label} (FFT)"

            else:
                logger.error(f"Unknown operation: {operation}")
                return -1

            # Add new curve
            new_id = self.addCurve(label, x.tolist(), y_new.tolist(), "", curve.linewidth)

            # Link to same table if original was linked
            if curve.table_id:
                self._curves[new_id].table_id = curve.table_id

            self.curveProcessed.emit(curve_id, operation, new_id)
            return new_id

        except Exception as e:
            logger.error(f"Operation {operation} failed: {e}")
            return -1

    # =========================================================================
    # View Control
    # =========================================================================

    @Slot()
    def resetView(self):
        """Reset to auto-scale view"""
        self._auto_scale = True
        self._zoom_level = 1.0
        self._needs_redraw = True
        self.update()

    @Slot(float, float, float, float)
    def setViewRange(self, x_min: float, x_max: float, y_min: float, y_max: float):
        """Set explicit view range"""
        self._auto_scale = False
        self._x_min = x_min
        self._x_max = x_max
        self._y_min = y_min
        self._y_max = y_max
        self._needs_redraw = True
        self.scaleChanged.emit()
        self.update()

    @Slot(float)
    def zoomIn(self, factor: float = 1.2):
        """Zoom in by factor, centered on viewport (works with log scale)"""
        d = self._data_bounds
        if not d:
            return

        ax_w = d['ax_right'] - d['ax_left']
        ax_h = d['ax_bottom'] - d['ax_top']
        if ax_w <= 0 or ax_h <= 0:
            return

        shrink = 1.0 / factor
        cx = d['ax_left'] + ax_w / 2
        cy = d['ax_top'] + ax_h / 2

        new_left = cx - ax_w * shrink / 2
        new_right = cx + ax_w * shrink / 2
        new_top = cy - ax_h * shrink / 2
        new_bottom = cy + ax_h * shrink / 2

        xmin, ymax = self._pixelToData(new_left, new_top)
        xmax, ymin = self._pixelToData(new_right, new_bottom)
        self.setViewRange(xmin, xmax, ymin, ymax)

    @Slot(float)
    def zoomOut(self, factor: float = 1.2):
        """Zoom out by factor"""
        self.zoomIn(1.0 / factor)

    @Slot(str, str)
    def setLabels(self, x_label: str, y_label: str):
        """Set axis labels"""
        self._x_label = x_label
        self._y_label = y_label
        self._needs_redraw = True
        self.update()

    # =========================================================================
    # Rendering
    # =========================================================================

    def paint(self, painter: QPainter):
        """Render matplotlib figure and overlays"""
        # Don't render until component is complete and has valid size
        if not self._component_complete:
            return

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

        # Set figure size to match widget size exactly
        # figure_size_inches * figure_dpi = widget_pixels
        self.figure.set_size_inches(w / self._dpi, h / self._dpi)

        # Clear and configure
        self.axes.clear()
        self._setupAxesStyle()

        # Set scales
        self.axes.set_xscale(self._x_scale)
        self.axes.set_yscale(self._y_scale)

        # Plot all visible curves
        # Determine max display points based on widget width (no need for more than 2× pixel count)
        max_points = max(2000, w * 2)

        for cid, curve in self._curves.items():
            if not curve.visible:
                continue

            line_kwargs = {
                'color': curve.color,
                'linewidth': curve.linewidth,
                'linestyle': curve.linestyle,
                'alpha': curve.alpha,
                'label': curve.label,
            }

            if curve.marker:
                line_kwargs['marker'] = curve.marker

            # Highlight selected curve
            if cid == self._selected_curve_id:
                line_kwargs['linewidth'] = curve.linewidth + 1
                line_kwargs['alpha'] = 1.0

            # Downsample large curves for rendering performance
            x_plot, y_plot = curve.x, curve.y
            if len(x_plot) > max_points:
                step = len(x_plot) // max_points
                x_plot = x_plot[::step]
                y_plot = y_plot[::step]

            self.axes.plot(x_plot, y_plot, **line_kwargs)

        # Grid
        if self._show_grid:
            self.axes.grid(True, color='#333333', linestyle='-', linewidth=0.5, alpha=0.5)

        # Labels
        self.axes.set_xlabel(self._x_label, fontsize=10)
        self.axes.set_ylabel(self._y_label, fontsize=10)

        if self._title:
            self.axes.set_title(self._title, fontsize=11)

        # Legend
        if self._show_legend and self._curves:
            visible_curves = [c for c in self._curves.values() if c.visible]
            if visible_curves:
                self.axes.legend(
                    loc='best',
                    fontsize=9,
                    facecolor='#2a2a2a',
                    edgecolor='#444444',
                    labelcolor='#cccccc',
                    framealpha=0.9
                )

        # Set axis limits
        if self._auto_scale:
            self._calculateAutoBounds()
        self.axes.set_xlim(self._x_min, self._x_max)
        self.axes.set_ylim(self._y_min, self._y_max)

        # Ported pyqtgraph tick layout (1/2/5 × 10ⁿ family, log-aware
        # superscript formatting). Replaces matplotlib's auto-locator
        # so the same tick rules apply across all three TRANS canvases.
        apply_pyqtgraph_ticks(
            self.axes,
            x_size_px=float(w),
            y_size_px=float(h),
            log_x=(self._x_scale == "log"),
            log_y=(self._y_scale == "log"),
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

    def _calculateAutoBounds(self):
        """Calculate auto-scale bounds from all curves"""
        if not self._curves:
            self._x_min, self._x_max = 0, 1
            self._y_min, self._y_max = 0, 1
            return

        x_mins, x_maxs = [], []
        y_mins, y_maxs = [], []

        for curve in self._curves.values():
            if curve.visible and len(curve.x) > 0:
                x_mins.append(np.nanmin(curve.x))
                x_maxs.append(np.nanmax(curve.x))
                y_mins.append(np.nanmin(curve.y))
                y_maxs.append(np.nanmax(curve.y))

        if x_mins:
            self._x_min = min(x_mins)
            self._x_max = max(x_maxs)
            self._y_min = min(y_mins)
            self._y_max = max(y_maxs)

            # Add margin
            x_margin = (self._x_max - self._x_min) * 0.05
            y_margin = (self._y_max - self._y_min) * 0.05

            if x_margin == 0:
                x_margin = 0.5
            if y_margin == 0:
                y_margin = 0.5

            self._x_min -= x_margin
            self._x_max += x_margin
            self._y_min -= y_margin
            self._y_max += y_margin

    def _updateDataBounds(self):
        """Update pixel-to-data coordinate mapping"""
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

    def _dataToPixel(self, x: float, y: float) -> Tuple[float, float]:
        """Convert data coordinates to pixel coordinates (handles log scale)"""
        try:
            px, py = self.axes.transData.transform((x, y))
            return float(px), float(self.canvas.get_width_height()[1] - py)
        except Exception:
            return 0.0, 0.0

    def _pixelToData(self, px: float, py: float) -> Tuple[float, float]:
        """Convert pixel to data coordinates (handles log scale)"""
        try:
            fig_h = self.canvas.get_width_height()[1]
            x, y = self.axes.transData.inverted().transform((px, fig_h - py))
            return float(x), float(y)
        except Exception:
            return 0.0, 0.0

    def _drawOverlays(self, painter: QPainter):
        """Draw interactive overlays (uses matplotlib transforms — correct for log scale)"""
        painter.setRenderHint(QPainter.Antialiasing, True)

        if not self._data_bounds:
            return

        d = self._data_bounds

        # Draw cursor crosshairs
        if self._show_cursor and self._cursor_x is not None:
            cpx, cpy = self._dataToPixel(self._cursor_x, self._cursor_y or 0)

            if d['ax_left'] <= cpx <= d['ax_right']:
                pen = QPen(QColor(255, 255, 100, 100))
                pen.setWidth(1)
                pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                painter.drawLine(int(cpx), int(d['ax_top']), int(cpx), int(d['ax_bottom']))

            if self._cursor_y is not None and d['ax_top'] <= cpy <= d['ax_bottom']:
                painter.drawLine(int(d['ax_left']), int(cpy), int(d['ax_right']), int(cpy))

        # Draw selection rectangle
        if self._selection_start is not None and self._selection_end is not None:
            px1, py1 = self._dataToPixel(self._selection_start[0], self._selection_start[1])
            px2, py2 = self._dataToPixel(self._selection_end[0], self._selection_end[1])

            rect = QRectF(min(px1, px2), min(py1, py2),
                         abs(px2 - px1), abs(py2 - py1))

            pen = QPen(QColor(100, 200, 255, 180))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(100, 200, 255, 40)))
            painter.drawRect(rect)

    # =========================================================================
    # Mouse Events
    # =========================================================================

    def mousePressEvent(self, event):
        """Handle mouse press — left: select/zoom-rect, right: pan"""
        pos = event.position()
        x, y = self._pixelToData(pos.x(), pos.y())

        if event.button() == Qt.LeftButton:
            self.pointClicked.emit(x, y)

            # Check for curve click (simple proximity check)
            clicked_curve = self._findNearestCurve(x, y)
            if clicked_curve is not None:
                self._selected_curve_id = clicked_curve
                self.curveClicked.emit(clicked_curve)
                self.curveSelected.emit(clicked_curve)
                self._needs_redraw = True
                self.update()

            # Start drag-zoom selection
            self._is_selecting = True
            self._selection_start = (x, y)
            self._selection_end = (x, y)

        elif event.button() == Qt.RightButton:
            # Start panning (track in pixel space for log-scale correctness)
            self._is_panning = True
            self._pan_last_px = (pos.x(), pos.y())

    def mouseMoveEvent(self, event):
        """Handle mouse move — drag-zoom rect or pan"""
        pos = event.position()
        x, y = self._pixelToData(pos.x(), pos.y())

        self._cursor_x = x
        self._cursor_y = y
        self._show_cursor = True
        self.cursorMoved.emit(x, y)

        if self._is_selecting:
            self._selection_end = (x, y)
            self.update()
        elif self._is_panning and self._pan_last_px is not None:
            # Pan in pixel space — works correctly for both linear and log scale
            dx_px = pos.x() - self._pan_last_px[0]
            dy_px = pos.y() - self._pan_last_px[1]

            d = self._data_bounds
            if d:
                ax_w = d['ax_right'] - d['ax_left']
                ax_h = d['ax_bottom'] - d['ax_top']
                if ax_w > 0 and ax_h > 0:
                    # Convert viewport corners shifted by pixel delta back to data coords
                    new_xmin, _ = self._pixelToData(d['ax_left'] - dx_px, d['ax_top'])
                    new_xmax, _ = self._pixelToData(d['ax_right'] - dx_px, d['ax_top'])
                    _, new_ymin = self._pixelToData(d['ax_left'], d['ax_bottom'] - dy_px)
                    _, new_ymax = self._pixelToData(d['ax_left'], d['ax_top'] - dy_px)

                    self.setViewRange(new_xmin, new_xmax, new_ymin, new_ymax)
                    self._pan_last_px = (pos.x(), pos.y())

    def mouseReleaseEvent(self, event):
        """Handle mouse release — drag-zoom to selected rectangle"""
        if event.button() == Qt.LeftButton and self._is_selecting:
            if self._selection_start and self._selection_end:
                x1, y1 = self._selection_start
                x2, y2 = self._selection_end

                # Check pixel distance to distinguish click from drag
                px1, py1 = self._dataToPixel(x1, y1)
                px2, py2 = self._dataToPixel(x2, y2)
                if abs(px2 - px1) > 5 and abs(py2 - py1) > 5:
                    xlo, xhi = min(x1, x2), max(x1, x2)
                    ylo, yhi = min(y1, y2), max(y1, y2)
                    self.setViewRange(xlo, xhi, ylo, yhi)
                    self.rangeSelected.emit(xlo, ylo, xhi, yhi)

            self._is_selecting = False
            self._selection_start = None
            self._selection_end = None
            self.update()

        elif event.button() == Qt.RightButton:
            self._is_panning = False
            self._pan_last_px = None

    def mouseDoubleClickEvent(self, event):
        """Double-click to reset view"""
        if event.button() == Qt.LeftButton:
            self.resetView()

    def wheelEvent(self, event):
        """Handle scroll wheel for zoom centered on cursor (works with log scale)"""
        d = self._data_bounds
        if not d:
            return

        pos = event.position()
        delta = event.angleDelta().y()
        shrink = 0.85 if delta > 0 else 1.0 / 0.85  # fraction of current range to keep

        ax_w = d['ax_right'] - d['ax_left']
        ax_h = d['ax_bottom'] - d['ax_top']
        if ax_w <= 0 or ax_h <= 0:
            return

        # Cursor fraction within axes area
        fx = (pos.x() - d['ax_left']) / ax_w
        fy = (pos.y() - d['ax_top']) / ax_h
        fx = max(0.0, min(1.0, fx))
        fy = max(0.0, min(1.0, fy))

        # New pixel bounds: shrink/expand around cursor pixel
        new_left = pos.x() - fx * ax_w * shrink
        new_right = pos.x() + (1 - fx) * ax_w * shrink
        new_top = pos.y() - fy * ax_h * shrink
        new_bottom = pos.y() + (1 - fy) * ax_h * shrink

        # Convert back to data coords (handles log scale via matplotlib transform)
        xmin, ymax = self._pixelToData(new_left, new_top)
        xmax, ymin = self._pixelToData(new_right, new_bottom)

        self.setViewRange(xmin, xmax, ymin, ymax)

    def hoverMoveEvent(self, event):
        """Handle hover — emit cursor position but don't repaint (avoids excessive redraws)"""
        pos = event.position()
        x, y = self._pixelToData(pos.x(), pos.y())
        self._cursor_x = x
        self._cursor_y = y
        self._show_cursor = True
        self.cursorMoved.emit(x, y)

    def hoverLeaveEvent(self, event):
        """Handle hover leave"""
        self._show_cursor = False
        self.update()

    def _findNearestCurve(self, x: float, y: float) -> Optional[int]:
        """Find curve nearest to click point in pixel space (works with log scale)"""
        if not self._curves or not self._data_bounds:
            return None

        click_px, click_py = self._dataToPixel(x, y)
        threshold_px = 15.0  # pixels

        best_dist = threshold_px
        best_id = None

        for cid, curve in self._curves.items():
            if not curve.visible or len(curve.x) == 0:
                continue

            # Downsample for distance check if curve is huge
            cx, cy = curve.x, curve.y
            if len(cx) > 500:
                step = len(cx) // 500
                cx, cy = cx[::step], cy[::step]

            # Convert curve points to pixel space
            try:
                pts = self.axes.transData.transform(np.column_stack([cx, cy]))
                fig_h = self.canvas.get_width_height()[1]
                pts[:, 1] = fig_h - pts[:, 1]
            except Exception:
                continue

            dists = np.sqrt((pts[:, 0] - click_px)**2 + (pts[:, 1] - click_py)**2)
            min_dist = float(np.min(dists))

            if min_dist < best_dist:
                best_dist = min_dist
                best_id = cid

        return best_id

    # =========================================================================
    # Geometry
    # =========================================================================

    def geometryChange(self, newGeometry, oldGeometry):
        """Handle resize with debouncing — scale cached image during drag, re-render when done."""
        super().geometryChange(newGeometry, oldGeometry)
        if newGeometry.size() != oldGeometry.size():
            # During resize: just repaint with the existing cached image (scaled by Qt)
            # This is fast because paint() draws _cached_image into the new rect
            self.update()
            # Restart debounce timer — full re-render happens when resizing stops
            self._resize_timer.start()

    def _onResizeFinished(self):
        """Called after resize stops (debounce). Triggers full matplotlib re-render."""
        self._needs_redraw = True
        self.update()

    # =========================================================================
    # Export
    # =========================================================================

    def _ensureRendered(self):
        """Ensure the figure is rendered with current data before exporting."""
        self._renderMatplotlib()

    @Slot(str, result=bool)
    def exportToPNG(self, filepath: str) -> bool:
        """Export graph as high-res PNG."""
        try:
            self._ensureRendered()
            self.figure.savefig(filepath, dpi=300, bbox_inches='tight',
                                facecolor=self.figure.get_facecolor())
            logger.info(f"Exported PNG to {filepath}")
            return True
        except Exception as e:
            logger.error(f"PNG export failed: {e}")
            return False

    @Slot(str, result=bool)
    def exportToSVG(self, filepath: str) -> bool:
        """Export graph as SVG vector."""
        try:
            self._ensureRendered()
            self.figure.savefig(filepath, bbox_inches='tight', format='svg',
                                facecolor=self.figure.get_facecolor())
            logger.info(f"Exported SVG to {filepath}")
            return True
        except Exception as e:
            logger.error(f"SVG export failed: {e}")
            return False

    @Slot(str, result=bool)
    def exportToPDF(self, filepath: str) -> bool:
        """Export graph as PDF."""
        try:
            self._ensureRendered()
            self.figure.savefig(filepath, bbox_inches='tight', format='pdf',
                                facecolor=self.figure.get_facecolor())
            logger.info(f"Exported PDF to {filepath}")
            return True
        except Exception as e:
            logger.error(f"PDF export failed: {e}")
            return False

    @Slot(str, result=bool)
    def exportToCSV(self, filepath: str) -> bool:
        """Export all visible curve data as CSV."""
        try:
            import csv
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                # Build header and data columns
                headers = []
                columns = []
                for curve in self._curves.values():
                    if not curve.visible:
                        continue
                    label = curve.label
                    headers.extend([f"{label}_X", f"{label}_Y"])
                    columns.extend([curve.x, curve.y])

                if not headers:
                    return False

                writer.writerow(headers)
                max_len = max(len(c) for c in columns)
                for i in range(max_len):
                    row = []
                    for col in columns:
                        row.append(col[i] if i < len(col) else '')
                    writer.writerow(row)

            logger.info(f"Exported CSV to {filepath}")
            return True
        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            return False
