"""
QML Graph Canvas - Enhanced QQuickPaintedItem for interactive graph plotting in QML
Provides full matplotlib integration with curve management, operations, and styling.
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import math
import os
import numpy as np
from typing import Optional, List, Dict, Any, Tuple
import logging
from dataclasses import dataclass, field
from scipy import signal
from scipy.ndimage import gaussian_filter1d

from PySide6.QtCore import (
    Qt, Signal, Slot, Property, QPointF, QRectF, QObject, QTimer,
)
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPen, QBrush, QFont,
    QFontMetricsF, QPainterPath, QTransform,
)
from PySide6.QtQuick import QQuickPaintedItem

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from src.widgets._pyqtgraph_ports.curve_path import (
    DOWNSAMPLE_PEAK,
    array_to_qpainterpath,
    prepare_curve_xy,
)
from src.widgets._pyqtgraph_ports.legend import (
    HIT_BODY,
    HIT_EYE,
    HIT_NONE,
    LegendBox,
    LegendEntry,
)
from src.widgets._pyqtgraph_ports.mpl_apply import apply_pyqtgraph_ticks
from src.widgets._pyqtgraph_ports.ticks import (
    format_tick_strings,
    minor_tick_values,
    tick_values,
)
from src.widgets._pyqtgraph_ports.viewbox import (
    MOUSE_MODE_PAN,
    MOUSE_MODE_RECT,
    ViewBoxState,
    ViewRect,
)


def _fast_render_enabled_default() -> bool:
    """Read ``TRANS_FAST_RENDER`` once at import time.

    Phase 4 flips the default — native rendering is now **on** by
    default. Set ``TRANS_FAST_RENDER=0`` / ``false`` / ``no`` /
    ``off`` to opt back into the matplotlib pipeline if a regression
    is hit. The matplotlib renderer still ships as
    ``_renderForExport`` (used by ``exportToPNG`` / ``exportToSVG`` /
    ``exportToPDF`` at high DPI) so flipping the toggle off is a
    safe fallback — it just re-routes the on-screen paint through
    the same code path the export uses.
    """
    val = os.environ.get("TRANS_FAST_RENDER", "").strip().lower()
    if val in ("0", "false", "no", "off"):
        return False
    return True

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

        # All view-range / interaction / scale-history state lives in
        # the ported pyqtgraph ViewBoxState. The canvas exposes thin
        # property shims (``_x_min`` / ``_x_max`` / ``_y_min`` /
        # ``_y_max`` / ``_auto_scale``) so the existing matplotlib
        # render code keeps reading and writing the same attribute
        # names, but the source of truth is ``self._viewbox``.
        self._viewbox = ViewBoxState()
        self._viewbox.set_dirty_callback(self._markViewboxDirty)

        # Cursor state
        self._cursor_x: Optional[float] = None
        self._cursor_y: Optional[float] = None
        self._show_cursor: bool = False

        # Render cache
        self._cached_image: Optional[QImage] = None
        self._needs_redraw: bool = True
        self._component_complete: bool = False

        # Resize debounce timer — avoids re-rendering matplotlib on every pixel
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)  # ms
        self._resize_timer.timeout.connect(self._onResizeFinished)

        # Coordinate transform (still backed by matplotlib's transData
        # in Phase 2; Phase 3 swaps it for a QTransform).
        self._data_bounds: Optional[Dict] = None

        # Phase 3 — native QPainterPath rendering. Off by default;
        # ``TRANS_FAST_RENDER=1`` opts in. Path cache is keyed on
        # ``(curve_id, x_log, y_log)`` so a scale flip invalidates
        # the cached paths automatically. ``_native_transform`` is
        # the data→pixel ``QTransform`` rebuilt every paint; its
        # inverse drives ``_pixelToData`` while fast-render is on.
        self._use_fast_render: bool = _fast_render_enabled_default()
        self._curve_paths: Dict[Tuple[int, bool, bool], QPainterPath] = {}
        self._dirty_curve_ids: set[int] = set()
        self._native_transform: Optional[QTransform] = None
        self._native_inv_transform: Optional[QTransform] = None

        # Phase 5 — self-laid-out legend. Owns its own anchor +
        # offset + per-curve visibility set; serialises through
        # ``legendState`` so the graph window save/restore picks it
        # up. Drag state lives on the canvas (legend is just laid
        # out per render); mouse handlers update it via
        # ``shift_offset``.
        self._legend = LegendBox()
        self._legend_drag_active: bool = False
        self._legend_drag_last_px: Optional[Tuple[float, float]] = None

    # =====================================================================
    # ViewBox shims — keep the existing render-side writes
    # (``self._x_min = ...``, ``self._auto_scale = False``) flowing
    # without churning ~30 attribute references. The shims forward
    # to the viewbox; the renderer never knows the difference.
    # =====================================================================

    @property
    def _x_min(self) -> float:
        return self._viewbox.view_range().x_min

    @_x_min.setter
    def _x_min(self, value: float) -> None:
        r = self._viewbox.view_range()
        self._viewbox.set_view_range(
            float(value), r.x_max, r.y_min, r.y_max,
            push_history=False, disable_auto=False,
        )

    @property
    def _x_max(self) -> float:
        return self._viewbox.view_range().x_max

    @_x_max.setter
    def _x_max(self, value: float) -> None:
        r = self._viewbox.view_range()
        self._viewbox.set_view_range(
            r.x_min, float(value), r.y_min, r.y_max,
            push_history=False, disable_auto=False,
        )

    @property
    def _y_min(self) -> float:
        return self._viewbox.view_range().y_min

    @_y_min.setter
    def _y_min(self, value: float) -> None:
        r = self._viewbox.view_range()
        self._viewbox.set_view_range(
            r.x_min, r.x_max, float(value), r.y_max,
            push_history=False, disable_auto=False,
        )

    @property
    def _y_max(self) -> float:
        return self._viewbox.view_range().y_max

    @_y_max.setter
    def _y_max(self, value: float) -> None:
        r = self._viewbox.view_range()
        self._viewbox.set_view_range(
            r.x_min, r.x_max, r.y_min, float(value),
            push_history=False, disable_auto=False,
        )

    @property
    def _auto_scale(self) -> bool:
        return self._viewbox.auto_range_enabled()

    @_auto_scale.setter
    def _auto_scale(self, value: bool) -> None:
        self._viewbox.set_auto_range_enabled(bool(value))

    def _markViewboxDirty(self) -> None:
        """Dirty callback the viewbox calls after any state mutation."""
        self._needs_redraw = True
        self.update()

    def _invalidate_curve_path(self, curve_id: int) -> None:
        """Drop every cached path for ``curve_id`` (across log/linear
        variants). Cheap; the next paint rebuilds on demand."""
        for key in list(self._curve_paths.keys()):
            if key[0] == curve_id:
                del self._curve_paths[key]
        self._dirty_curve_ids.discard(curve_id)

    def _invalidate_all_curve_paths(self) -> None:
        """Drop every cached path — used when curves are cleared or
        an axis scale flips so the next paint rebuilds from scratch."""
        self._curve_paths.clear()
        self._dirty_curve_ids.clear()

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
            self._invalidate_curve_path(curve_id)

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
        self._invalidate_all_curve_paths()
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
        """Re-enable auto-range and snap to the current data extent.

        Defers to the viewbox: if curves have been added the renderer
        already registered the data extent via ``_calculateAutoBounds``;
        otherwise the next render will register it and trigger.
        """
        self._viewbox.set_auto_range_enabled(True)
        self._viewbox.trigger_auto_range()
        self.scaleChanged.emit()

    @Slot(float, float, float, float)
    def setViewRange(self, x_min: float, x_max: float, y_min: float, y_max: float):
        """Set explicit view range (drops auto-range; pushes history)."""
        self._viewbox.set_view_range(x_min, x_max, y_min, y_max)
        self.scaleChanged.emit()

    @Slot(float)
    def zoomIn(self, factor: float = 1.2):
        """Zoom in by ``factor``, centred on the viewport. Uses the
        viewbox's wheel-zoom helper at the axes centre point so log
        scales stay correct via the registered pixel↔data adapter.
        """
        d = self._data_bounds
        if not d:
            return
        cx = d['ax_left'] + (d['ax_right'] - d['ax_left']) / 2
        cy = d['ax_top'] + (d['ax_bottom'] - d['ax_top']) / 2
        # Map the user-facing ``factor`` (>1 = zoom in) onto
        # ``handle_wheel``'s ``zoom_step`` (<1 = shrink) and use a
        # positive delta to take the "zoom in" branch.
        self._viewbox.handle_wheel(
            (cx, cy), delta_y=120.0, zoom_step=1.0 / float(factor),
        )
        self.scaleChanged.emit()

    @Slot(float)
    def zoomOut(self, factor: float = 1.2):
        """Zoom out by ``factor``, centred on the viewport."""
        d = self._data_bounds
        if not d:
            return
        cx = d['ax_left'] + (d['ax_right'] - d['ax_left']) / 2
        cy = d['ax_top'] + (d['ax_bottom'] - d['ax_top']) / 2
        self._viewbox.handle_wheel(
            (cx, cy), delta_y=-120.0, zoom_step=1.0 / float(factor),
        )
        self.scaleChanged.emit()

    @Slot()
    def undoZoom(self):
        """Pop the most recent prior view off the viewbox history."""
        if self._viewbox.undo_view():
            self.scaleChanged.emit()

    # mouseMode property — "pan" (default) or "rect" (drag = zoom-rect).
    mouseModeChanged = Signal(str)

    def _get_mouse_mode(self) -> str:
        return self._viewbox.mouse_mode()

    def _set_mouse_mode(self, value: str) -> None:
        current = self._viewbox.mouse_mode()
        new = value if value in (MOUSE_MODE_PAN, MOUSE_MODE_RECT) else current
        if new != current:
            self._viewbox.set_mouse_mode(new)
            self.mouseModeChanged.emit(new)

    mouseMode = Property(
        str, _get_mouse_mode, _set_mouse_mode, notify=mouseModeChanged,
    )

    # legendState — round-trips the legend's anchor + offset + hidden
    # curve list through the project file. Exposed as a QML Property
    # so the graph window's saveState() can include it transparently
    # alongside curve list / scale settings, and loadState() can hand
    # it back on reopen.
    legendStateChanged = Signal()

    @Slot(result="QVariantMap")
    def getLegendState(self):
        """Snapshot the legend state — used by the graph-window save
        path. Always includes anchor + offset_px; hidden_curves is
        included for completeness even though it's derived from
        ``curve.visible`` at render time."""
        return self._legend.get_state()

    @Slot("QVariantMap")
    def setLegendState(self, state):
        """Restore from :meth:`getLegendState`. Tolerant of missing
        keys / unknown anchors / malformed values (the underlying
        ``LegendBox.apply_state`` ignores them)."""
        if state is None:
            return
        self._legend.apply_state(dict(state))
        self._needs_redraw = True
        self.update()
        self.legendStateChanged.emit()

    @Slot(int, bool)
    def setCurveLegendVisible(self, curve_id: int, visible: bool):
        """Toggle a single curve's visibility from QML — equivalent
        to clicking its eye in the legend."""
        curve = self._curves.get(int(curve_id))
        if curve is None:
            return
        if curve.visible != bool(visible):
            curve.visible = bool(visible)
            self._needs_redraw = True
            self.update()

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
        """Render path: native QPainter (Phase 3) or matplotlib
        (legacy fallback). The branch is the ``_use_fast_render``
        toggle read once from ``TRANS_FAST_RENDER`` at startup."""
        if not self._component_complete:
            return

        if self._use_fast_render:
            self._renderNative(painter)
            self._needs_redraw = False
            return

        if self._needs_redraw:
            self._renderForExport()
            self._needs_redraw = False

        if self._cached_image is not None:
            target_rect = QRectF(0, 0, self.width(), self.height())
            painter.drawImage(target_rect, self._cached_image)

            # Draw overlays
            self._drawOverlays(painter)

    def _renderForExport(self):
        """Render the matplotlib figure to ``_cached_image``.

        Phase 4 renamed this from ``_renderMatplotlib`` — it's no
        longer the on-screen renderer (``_renderNative`` is), but
        ``exportToPNG`` / ``exportToSVG`` / ``exportToPDF`` still need
        a fully-laid-out matplotlib figure to call ``savefig`` against,
        and the same method services as the fallback paint path when
        ``TRANS_FAST_RENDER=0`` is set.
        """
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

    # =========================================================================
    # Native rendering (Phase 3) — QPainter / QPainterPath, no matplotlib.
    # =========================================================================

    # Layout margins inside the widget (left/right/top/bottom px).
    _AX_MARGIN_LEFT = 60
    _AX_MARGIN_RIGHT = 20
    _AX_MARGIN_TOP = 20
    _AX_MARGIN_BOTTOM = 45
    _AX_LABEL_PAD = 4
    # Cap path size so a million-point curve still builds in tens of ms.
    _MAX_PATH_POINTS = 50_000
    # Min log-axis value (avoid log10(0) when the user fills a zero-floor curve).
    _LOG_EPS = 1e-30

    # Dark-theme colours (mirror the matplotlib path so the visuals
    # match when the user toggles ``TRANS_FAST_RENDER``).
    _NATIVE_BG_COLOR = QColor("#1a1a1a")
    _NATIVE_AXIS_COLOR = QColor("#444444")
    _NATIVE_TICK_COLOR = QColor("#888888")
    _NATIVE_LABEL_COLOR = QColor("#cccccc")
    _NATIVE_TITLE_COLOR = QColor("#ffffff")
    _NATIVE_GRID_COLOR = QColor(51, 51, 51, 127)
    _NATIVE_LEGEND_BG = QColor(42, 42, 42, 230)
    _NATIVE_LEGEND_BORDER = QColor(68, 68, 68)

    def _renderNative(self, painter: QPainter) -> None:
        """Render the entire plot with QPainter primitives.

        Pipeline:

        1. Compute the axes rect inside the widget (accounting for
           margins).
        2. Run ``_calculateAutoBounds`` if auto-range is on (same code
           the matplotlib path uses).
        3. Build a data → pixel ``QTransform`` from the view range and
           axes rect. In log mode the transform sees the *post-log*
           data range and the path was built from ``log10(...)``.
        4. Paint the background, axes, grid, ticks, tick labels,
           axis labels and title — all with QPainter primitives + the
           ported tick algorithm from Phase 1.
        5. For each visible curve: pen + ``setTransform`` + ``drawPath``.
        6. Register the transform with the viewbox + ``_data_bounds``
           so the interaction handlers and ``_drawOverlays`` keep
           working unchanged.
        7. Legend + overlays.
        """
        w, h = int(self.width()), int(self.height())
        if w <= 0 or h <= 0:
            return

        painter.fillRect(QRectF(0, 0, w, h), self._NATIVE_BG_COLOR)

        ax_left = self._AX_MARGIN_LEFT
        ax_top = self._AX_MARGIN_TOP + (16 if self._title else 0)
        ax_right = w - self._AX_MARGIN_RIGHT
        ax_bottom = h - self._AX_MARGIN_BOTTOM
        if ax_right <= ax_left or ax_bottom <= ax_top:
            return
        ax_rect = QRectF(
            ax_left, ax_top, ax_right - ax_left, ax_bottom - ax_top,
        )

        if self._auto_scale:
            self._calculateAutoBounds()

        x_log = (self._x_scale == "log")
        y_log = (self._y_scale == "log")

        # View range in post-log coords (transform stays linear).
        x_vmin, x_vmax = self._native_log_safe(self._x_min, self._x_max, x_log)
        y_vmin, y_vmax = self._native_log_safe(self._y_min, self._y_max, y_log)
        if x_vmax == x_vmin or y_vmax == y_vmin:
            return

        transform = self._native_build_transform(
            x_vmin, x_vmax, y_vmin, y_vmax, ax_rect,
        )

        # Title.
        if self._title:
            painter.setPen(self._NATIVE_TITLE_COLOR)
            f = painter.font(); f.setPointSize(11); f.setBold(True)
            painter.setFont(f)
            painter.drawText(
                QRectF(0, 2, w, ax_top - 4),
                Qt.AlignHCenter | Qt.AlignVCenter, self._title,
            )

        # Background grid + ticks + axis labels.
        self._native_draw_axes(
            painter, ax_rect,
            x_vmin, x_vmax, y_vmin, y_vmax,
            x_log=x_log, y_log=y_log,
        )

        # Curves (clipped to the axes rect).
        painter.save()
        painter.setClipRect(ax_rect)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for cid, curve in self._curves.items():
            if not curve.visible:
                continue
            path = self._native_get_path(cid, curve, x_log, y_log)
            if path is None or path.elementCount() == 0:
                continue
            pen = QPen(QColor(curve.color))
            width = float(curve.linewidth)
            if cid == self._selected_curve_id:
                width += 1.0
            pen.setWidthF(width)
            ls = (curve.linestyle or "-").strip()
            if ls in ("--", "dashed"):
                pen.setStyle(Qt.DashLine)
            elif ls in (":", "dotted"):
                pen.setStyle(Qt.DotLine)
            elif ls in ("-.", "dashdot"):
                pen.setStyle(Qt.DashDotLine)
            else:
                pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.setTransform(transform, combine=False)
            painter.drawPath(path)
        painter.setTransform(QTransform())
        painter.restore()

        # Store transforms for interaction (viewbox + ``_pixelToData``).
        inv, ok = transform.inverted()
        self._native_transform = transform
        self._native_inv_transform = inv if ok else QTransform()
        self._data_bounds = {
            'ax_left': ax_left, 'ax_right': ax_right,
            'ax_top': ax_top, 'ax_bottom': ax_bottom,
            'x_min': self._x_min, 'x_max': self._x_max,
            'y_min': self._y_min, 'y_max': self._y_max,
        }
        self._viewbox.set_transforms(self._pixelToData, self._dataToPixel)
        self._viewbox.set_axes_pixel_rect(
            (ax_left, ax_top, ax_right, ax_bottom),
        )
        self._viewbox.set_auto_range_data(ViewRect(
            self._x_min, self._x_max, self._y_min, self._y_max,
        ))
        self._viewbox.set_auto_range_margin(0.0)

        # Legend + overlays. Sync the legend's "hidden" set from
        # ``curve.visible`` so the eye toggles render correctly.
        if self._show_legend and self._curves:
            hidden_ids = [
                cid for cid, curve in self._curves.items()
                if not curve.visible
            ]
            self._legend.set_hidden_curves(hidden_ids)
            self._native_draw_legend(painter, ax_rect)
        self._drawOverlays(painter)

    @staticmethod
    def _native_log_safe(
        lo: float, hi: float, log: bool,
    ) -> Tuple[float, float]:
        """Return the view range in post-log coords when ``log`` is
        on; clamp non-positive endpoints to ``_LOG_EPS`` first."""
        if not log:
            return float(lo), float(hi)
        lo_c = max(float(lo), QMLGraphCanvas._LOG_EPS)
        hi_c = max(float(hi), QMLGraphCanvas._LOG_EPS)
        return math.log10(lo_c), math.log10(hi_c)

    @staticmethod
    def _native_build_transform(
        x_min: float, x_max: float, y_min: float, y_max: float,
        ax_rect: QRectF,
    ) -> QTransform:
        """Affine that maps post-log data coords → axes-rect pixels.

        Y is flipped because pixel Y grows downward but data Y grows
        upward.
        """
        ax_w = ax_rect.width()
        ax_h = ax_rect.height()
        sx = ax_w / (x_max - x_min)
        sy = -ax_h / (y_max - y_min)
        tx = ax_rect.left() - x_min * sx
        ty = ax_rect.bottom() - y_min * sy
        return QTransform(sx, 0.0, 0.0, sy, tx, ty)

    def _native_get_path(
        self,
        cid: int,
        curve: "CurveData",
        x_log: bool,
        y_log: bool,
    ) -> Optional[QPainterPath]:
        """Return the cached path for ``(cid, x_log, y_log)``,
        building (and caching) it on first request."""
        key = (cid, bool(x_log), bool(y_log))
        cached = self._curve_paths.get(key)
        if cached is not None:
            return cached
        try:
            x_p, y_p = prepare_curve_xy(
                curve.x, curve.y,
                log_x=x_log, log_y=y_log,
                max_points=self._MAX_PATH_POINTS,
                downsample_mode=DOWNSAMPLE_PEAK,
            )
            path = array_to_qpainterpath(x_p, y_p)
        except Exception as exc:
            logger.warning(
                "Failed to build native path for curve %s: %s", cid, exc,
            )
            return None
        self._curve_paths[key] = path
        return path

    def _native_draw_axes(
        self,
        painter: QPainter,
        ax_rect: QRectF,
        x_vmin: float, x_vmax: float,
        y_vmin: float, y_vmax: float,
        *,
        x_log: bool,
        y_log: bool,
    ) -> None:
        """Frame + grid + major ticks + minor ticks + major-tick
        labels (with shared exponent when the magnitudes warrant) +
        axis labels.

        Minor ticks are drawn 3 px long with a lighter pen on the
        outside of the frame; majors are 5 px and the configured
        ``_NATIVE_TICK_COLOR``. Grid lines stay attached to majors so
        the plot doesn't get noisy at high tick densities."""
        # Axes pen + frame.
        pen_axis = QPen(self._NATIVE_AXIS_COLOR)
        pen_axis.setWidthF(1.0)
        painter.setPen(pen_axis)
        painter.drawRect(ax_rect)

        # All tick levels for each axis (Phase 1 algorithm).
        x_levels = tick_values(x_vmin, x_vmax, ax_rect.width(), log=x_log)
        y_levels = tick_values(y_vmin, y_vmax, ax_rect.height(), log=y_log)

        # Majors (level 0) drive labels + grid.
        x_major_spacing, x_majors = (
            x_levels[0] if x_levels else (1.0, [])
        )
        y_major_spacing, y_majors = (
            y_levels[0] if y_levels else (1.0, [])
        )

        # Minor + sub-minor levels (Phase 4).
        x_minors = x_levels[1:] if len(x_levels) > 1 else []
        y_minors = y_levels[1:] if len(y_levels) > 1 else []

        # Shared-exponent label formatting (Phase 4). When the axis
        # magnitudes spill outside ``[10⁻⁴, 10⁴]`` we factor out a
        # ``× 10ⁿ`` and render the labels compactly. Log axes
        # short-circuit to the per-tick formatter.
        x_labels, x_shared_exp = format_tick_strings(
            x_majors, spacing=x_major_spacing, log=x_log,
        ) if x_majors else ([], None)
        y_labels, y_shared_exp = format_tick_strings(
            y_majors, spacing=y_major_spacing, log=y_log,
        ) if y_majors else ([], None)

        # Grid (majors only).
        if self._show_grid:
            grid_pen = QPen(self._NATIVE_GRID_COLOR)
            grid_pen.setWidthF(0.5)
            painter.setPen(grid_pen)
            for x in x_majors:
                px = self._native_data_x_to_pixel(x, x_vmin, x_vmax, ax_rect)
                if ax_rect.left() <= px <= ax_rect.right():
                    painter.drawLine(
                        QPointF(px, ax_rect.top()),
                        QPointF(px, ax_rect.bottom()),
                    )
            for y in y_majors:
                py = self._native_data_y_to_pixel(y, y_vmin, y_vmax, ax_rect)
                if ax_rect.top() <= py <= ax_rect.bottom():
                    painter.drawLine(
                        QPointF(ax_rect.left(), py),
                        QPointF(ax_rect.right(), py),
                    )

        # Minor tick marks (3 px, lighter pen, no labels).
        if x_minors or y_minors:
            minor_color = QColor(self._NATIVE_TICK_COLOR)
            minor_color.setAlpha(120)
            minor_pen = QPen(minor_color)
            minor_pen.setWidthF(0.7)
            painter.setPen(minor_pen)
            minor_len = 3.0
            for _spacing, values in x_minors:
                for x in values:
                    px = self._native_data_x_to_pixel(x, x_vmin, x_vmax, ax_rect)
                    if ax_rect.left() <= px <= ax_rect.right():
                        painter.drawLine(
                            QPointF(px, ax_rect.bottom()),
                            QPointF(px, ax_rect.bottom() + minor_len),
                        )
            for _spacing, values in y_minors:
                for y in values:
                    py = self._native_data_y_to_pixel(y, y_vmin, y_vmax, ax_rect)
                    if ax_rect.top() <= py <= ax_rect.bottom():
                        painter.drawLine(
                            QPointF(ax_rect.left() - minor_len, py),
                            QPointF(ax_rect.left(), py),
                        )

        # Major tick marks (5 px).
        tick_pen = QPen(self._NATIVE_TICK_COLOR)
        tick_pen.setWidthF(1.0)
        painter.setPen(tick_pen)
        tick_len = 5.0
        for x in x_majors:
            px = self._native_data_x_to_pixel(x, x_vmin, x_vmax, ax_rect)
            if ax_rect.left() <= px <= ax_rect.right():
                painter.drawLine(
                    QPointF(px, ax_rect.bottom()),
                    QPointF(px, ax_rect.bottom() + tick_len),
                )
        for y in y_majors:
            py = self._native_data_y_to_pixel(y, y_vmin, y_vmax, ax_rect)
            if ax_rect.top() <= py <= ax_rect.bottom():
                painter.drawLine(
                    QPointF(ax_rect.left() - tick_len, py),
                    QPointF(ax_rect.left(), py),
                )

        # Major tick labels.
        painter.setPen(self._NATIVE_LABEL_COLOR)
        f = painter.font(); f.setPointSize(9); f.setBold(False)
        painter.setFont(f)
        fm = QFontMetricsF(painter.font())
        for x, label in zip(x_majors, x_labels):
            px = self._native_data_x_to_pixel(x, x_vmin, x_vmax, ax_rect)
            if ax_rect.left() <= px <= ax_rect.right():
                tw = fm.horizontalAdvance(label)
                painter.drawText(
                    QPointF(px - tw / 2, ax_rect.bottom() + tick_len + fm.ascent() + 2),
                    label,
                )
        for y, label in zip(y_majors, y_labels):
            py = self._native_data_y_to_pixel(y, y_vmin, y_vmax, ax_rect)
            if ax_rect.top() <= py <= ax_rect.bottom():
                tw = fm.horizontalAdvance(label)
                painter.drawText(
                    QPointF(ax_rect.left() - tick_len - tw - 4, py + fm.ascent() / 2 - 1),
                    label,
                )

        # Axis labels (with the shared exponent appended when present).
        if self._x_label or x_shared_exp is not None:
            painter.setPen(self._NATIVE_LABEL_COLOR)
            x_label_full = self._format_axis_label(
                self._x_label, x_shared_exp,
            )
            painter.drawText(
                QRectF(ax_rect.left(), ax_rect.bottom() + 22,
                       ax_rect.width(), 20),
                Qt.AlignHCenter | Qt.AlignTop, x_label_full,
            )
        if self._y_label or y_shared_exp is not None:
            painter.save()
            painter.translate(14.0, ax_rect.top() + ax_rect.height() / 2)
            painter.rotate(-90.0)
            painter.setPen(self._NATIVE_LABEL_COLOR)
            y_label_full = self._format_axis_label(
                self._y_label, y_shared_exp,
            )
            painter.drawText(
                QRectF(-ax_rect.height() / 2, -10,
                       ax_rect.height(), 20),
                Qt.AlignHCenter | Qt.AlignVCenter, y_label_full,
            )
            painter.restore()

    @staticmethod
    def _format_axis_label(
        label: str, shared_exponent: Optional[int],
    ) -> str:
        """Append ``× 10ⁿ`` (in Unicode superscript) to ``label`` when
        ``shared_exponent`` is set. Used by both axis-label calls in
        ``_native_draw_axes`` for the shared-exponent display."""
        if shared_exponent is None:
            return label
        # Unicode superscripts (Phase 1 already has the table; reuse
        # locally so this helper doesn't depend on the ticks module
        # at runtime).
        sup_map = str.maketrans({
            "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³",
            "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸",
            "9": "⁹",
        })
        exp_str = str(shared_exponent).translate(sup_map)
        suffix = f"× 10{exp_str}"
        return f"{label}  ({suffix})" if label else suffix

    @staticmethod
    def _native_data_x_to_pixel(
        x: float, x_vmin: float, x_vmax: float, ax_rect: QRectF,
    ) -> float:
        if x_vmax == x_vmin:
            return ax_rect.left()
        return ax_rect.left() + (x - x_vmin) / (x_vmax - x_vmin) * ax_rect.width()

    @staticmethod
    def _native_data_y_to_pixel(
        y: float, y_vmin: float, y_vmax: float, ax_rect: QRectF,
    ) -> float:
        if y_vmax == y_vmin:
            return ax_rect.bottom()
        return ax_rect.bottom() - (y - y_vmin) / (y_vmax - y_vmin) * ax_rect.height()

    def _native_draw_legend(
        self, painter: QPainter, ax_rect: QRectF,
    ) -> None:
        """Phase 5 — render via the ported ``LegendBox``.

        Builds a fresh :class:`LegendEntry` list from the current
        curve catalogue (label, pen colour, width, style), forwards
        the anchor / offset / hidden-curves state from ``self._legend``,
        and lets the legend lay itself out + paint. The geometry it
        produces is cached on the legend for the mouse handlers to
        hit-test against.
        """
        entries: List[LegendEntry] = [
            LegendEntry(
                curve_id=cid,
                label=curve.label,
                color=curve.color,
                linewidth=float(curve.linewidth),
                linestyle=curve.linestyle or "-",
            )
            for cid, curve in self._curves.items()
        ]
        if not entries:
            return
        f = painter.font(); f.setPointSize(9); f.setBold(False)
        self._legend.render(
            painter, f, ax_rect, entries,
            bg_color=self._NATIVE_LEGEND_BG,
            border_color=self._NATIVE_LEGEND_BORDER,
            text_color=self._NATIVE_LABEL_COLOR,
        )

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
        """Refresh the pixel-to-data mapping after each render.

        Also registers the transform adapters and the axes pixel rect
        with the viewbox so its interaction handlers can do their own
        pixel↔data math without referencing the canvas directly.
        Phase 3 will swap the matplotlib-backed adapter for a
        ``QTransform``-backed one without changing this call site.
        """
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

        # Plug the viewbox transform + axes rect for interaction math.
        self._viewbox.set_transforms(self._pixelToData, self._dataToPixel)
        self._viewbox.set_axes_pixel_rect((
            self._data_bounds['ax_left'],
            self._data_bounds['ax_top'],
            self._data_bounds['ax_right'],
            self._data_bounds['ax_bottom'],
        ))
        # Register the data extent so ``trigger_auto_range`` (used by
        # ``resetView`` and double-click) has something to snap to.
        # ``_calculateAutoBounds`` already wrote the current data
        # extent into ``_x_min/_x_max/_y_min/_y_max`` before
        # ``set_xlim``/``set_ylim`` were called.
        self._viewbox.set_auto_range_data(ViewRect(
            self._x_min, self._x_max, self._y_min, self._y_max,
        ))
        # ``_calculateAutoBounds`` already applies a 5 % margin to the
        # data extent, so leave the viewbox's auto-range margin at 0.
        self._viewbox.set_auto_range_margin(0.0)

    def _dataToPixel(self, x: float, y: float) -> Tuple[float, float]:
        """Data → pixel mapping. Uses the native ``QTransform`` while
        fast-render is on (pre-logging in log mode); falls back to
        matplotlib's ``transData`` otherwise."""
        if self._use_fast_render and self._native_transform is not None:
            x_log = (self._x_scale == "log")
            y_log = (self._y_scale == "log")
            x_d = math.log10(max(x, self._LOG_EPS)) if x_log else float(x)
            y_d = math.log10(max(y, self._LOG_EPS)) if y_log else float(y)
            pt = self._native_transform.map(QPointF(x_d, y_d))
            return float(pt.x()), float(pt.y())
        try:
            px, py = self.axes.transData.transform((x, y))
            return float(px), float(self.canvas.get_width_height()[1] - py)
        except Exception:
            return 0.0, 0.0

    def _pixelToData(self, px: float, py: float) -> Tuple[float, float]:
        """Pixel → data mapping. Uses the native ``QTransform`` inverse
        in fast-render mode (un-logging back to data coords); falls
        back to matplotlib's ``transData.inverted()`` otherwise."""
        if self._use_fast_render and self._native_inv_transform is not None:
            pt = self._native_inv_transform.map(QPointF(px, py))
            x = float(pt.x()); y = float(pt.y())
            if self._x_scale == "log":
                x = 10.0 ** x
            if self._y_scale == "log":
                y = 10.0 ** y
            return x, y
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

        # Draw the rubber-band selection rectangle from the viewbox.
        sel = self._viewbox.selection_box_data()
        if sel is not None:
            x_min, y_min, x_max, y_max = sel
            px1, py1 = self._dataToPixel(x_min, y_min)
            px2, py2 = self._dataToPixel(x_max, y_max)
            rect = QRectF(
                min(px1, px2), min(py1, py2),
                abs(px2 - px1), abs(py2 - py1),
            )
            pen = QPen(QColor(100, 200, 255, 180))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(100, 200, 255, 40)))
            painter.drawRect(rect)

    # =========================================================================
    # Mouse Events
    # =========================================================================

    def mousePressEvent(self, event):
        """Left → legend hit-test (eye toggle / drag-to-move) →
        ``pointClicked`` + curve-pick + viewbox drag-zoom rect.
        Right → start pan."""
        pos = event.position()
        pos_px = (pos.x(), pos.y())

        if event.button() == Qt.LeftButton:
            # Legend takes priority — clicks inside the legend
            # bounding rect don't reach the viewbox.
            if self._use_fast_render:
                hit, hit_cid = self._legend.hit_test(QPointF(*pos_px))
                if hit == HIT_EYE and hit_cid is not None:
                    self._toggle_curve_visibility(hit_cid)
                    return
                if hit == HIT_BODY:
                    self._legend_drag_active = True
                    self._legend_drag_last_px = pos_px
                    return

            x, y = self._pixelToData(*pos_px)
            self.pointClicked.emit(x, y)
            clicked_curve = self._findNearestCurve(x, y)
            if clicked_curve is not None:
                self._selected_curve_id = clicked_curve
                self.curveClicked.emit(clicked_curve)
                self.curveSelected.emit(clicked_curve)
                self._needs_redraw = True
                self.update()
            self._viewbox.handle_press_left(pos_px)

        elif event.button() == Qt.RightButton:
            self._viewbox.handle_press_right(pos_px)

    def _toggle_curve_visibility(self, curve_id: int) -> None:
        """Eye-click handler — flips ``curve.visible`` and triggers
        a repaint. Identical to ``updateCurveProperty(cid, 'visible',
        'false')`` but auto-derives the new value from the old."""
        curve = self._curves.get(curve_id)
        if curve is None:
            return
        curve.visible = not curve.visible
        self._needs_redraw = True
        self.update()

    def mouseMoveEvent(self, event):
        """Update cursor read-out + delegate the active pan / rubber-
        band-zoom interaction to the viewbox. Legend drag short-
        circuits viewbox motion."""
        pos = event.position()
        pos_px = (pos.x(), pos.y())
        x, y = self._pixelToData(*pos_px)
        self._cursor_x = x
        self._cursor_y = y
        self._show_cursor = True
        self.cursorMoved.emit(x, y)

        if self._legend_drag_active and self._legend_drag_last_px is not None:
            last = self._legend_drag_last_px
            dx = pos_px[0] - last[0]
            dy = pos_px[1] - last[1]
            self._legend_drag_last_px = pos_px
            geom = self._legend.geometry()
            if geom is not None:
                # Use the current axes rect as the soft bound for
                # the offset clamp inside ``shift_offset``.
                d = self._data_bounds
                if d:
                    ax_rect = QRectF(
                        d['ax_left'], d['ax_top'],
                        d['ax_right'] - d['ax_left'],
                        d['ax_bottom'] - d['ax_top'],
                    )
                    self._legend.shift_offset(dx, dy, ax_rect)
                    self._needs_redraw = True
                    self.update()
            return

        self._viewbox.handle_move(pos_px)

    def mouseReleaseEvent(self, event):
        """Finish a left-drag (zoom-rect, may emit ``rangeSelected``,
        or end a legend drag) or a right-drag (pan)."""
        pos = event.position()
        pos_px = (pos.x(), pos.y())
        if event.button() == Qt.LeftButton:
            if self._legend_drag_active:
                self._legend_drag_active = False
                self._legend_drag_last_px = None
                self.update()
                return
            result = self._viewbox.handle_release_left(pos_px)
            if result is not None:
                x_min, y_min, x_max, y_max = result
                self.scaleChanged.emit()
                self.rangeSelected.emit(x_min, y_min, x_max, y_max)
            self.update()
        elif event.button() == Qt.RightButton:
            self._viewbox.handle_release_right()

    def mouseDoubleClickEvent(self, event):
        """Double-click resets to auto-range via the viewbox."""
        if event.button() == Qt.LeftButton:
            self._viewbox.handle_double_click()
            self.scaleChanged.emit()

    def wheelEvent(self, event):
        """Wheel zoom centred on the cursor — viewbox does the math
        via the registered pixel↔data adapter (so log scale stays
        correct)."""
        pos = event.position()
        delta = float(event.angleDelta().y())
        if self._viewbox.handle_wheel((pos.x(), pos.y()), delta_y=delta):
            self.scaleChanged.emit()

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
        """Ensure the matplotlib figure is laid out with current data
        before an export ``savefig`` call. Phase 4 retargeted this
        from the renamed ``_renderMatplotlib`` to ``_renderForExport``
        so export-only changes don't touch the on-screen path."""
        self._renderForExport()

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
