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
from matplotlib.colors import is_color_like

from src.widgets._pyqtgraph_ports.mpl_apply import apply_pyqtgraph_ticks
from src.widgets._pyqtgraph_ports.viewbox import ViewBoxState
from src.widgets.series_palette import readable_on

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

    # Palette change notifications. QML needs these for a two-way binding to
    # settle; nothing inside this class listens to them, because the palette
    # is re-applied wholesale on every render rather than patched in a
    # handler (see _setupAxesStyle).
    backgroundColorChanged = Signal()
    foregroundColorChanged = Signal()
    gridColorChanged = Signal()
    accentColorChanged = Signal()
    cursorColorChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.AllButtons)
        self.setAcceptHoverEvents(True)
        self.setFlag(QQuickPaintedItem.ItemHasContents, True)

        # Matplotlib setup
        self._dpi = 100

        # Palette. These are only the colours the canvas falls back to when
        # nothing binds it — ProfileViewer binds them to the active colour
        # scheme. They are deliberately not read as one-off construction
        # arguments: every one is re-applied on each render, so a scheme
        # change cannot leave the axes showing the previous scheme.
        self._background: str = '#1a1a1a'
        self._foreground: str = '#aaaaaa'
        self._grid: str = '#444444'
        # Interaction chrome, drawn by QPainter over the finished figure.
        # These two are separate properties rather than one accent because
        # a drag shows both at once — the band and the cursor line inside
        # it — and one colour would merge them.
        self._accent: str = '#64c8ff'
        self._cursor: str = '#ffff64'

        self.figure = Figure(facecolor=self._background, dpi=self._dpi)
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

        # Selection / view state is owned by the ported ViewBoxState in
        # x-mode-only configuration (profile selection is a 1-D x-range).
        self._viewbox = ViewBoxState(x_mode_only=True)
        self._viewbox.set_dirty_callback(self._markViewboxDirty)

        # Render cache
        self._cached_image: Optional[QImage] = None
        self._needs_redraw: bool = True

        # Coordinate transform
        self._data_bounds: Optional[Dict] = None

    def _markViewboxDirty(self) -> None:
        """Dirty callback the viewbox calls after any state mutation."""
        self._needs_redraw = True
        self.update()

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
        """Re-apply the palette to the figure and the axes.

        _renderMatplotlib calls this after every axes.clear(), which is why
        the colour setters below only have to ask for a redraw. There is no
        separate restyle path that a scheme change could miss, and no state
        that survives a frame: whatever the properties hold when a frame is
        drawn is what that frame shows.

        This used to hardcode five distinct greys — #1a1a1a ground, #444444
        spines, #888888 ticks, #aaaaaa labels, #cccccc title. They collapse
        onto the three themed roles, which costs the title its slight
        emphasis over the tick labels but buys a canvas that is legible on a
        light scheme instead of being a black box in a white window. The
        grid keeps its subordinate weight through alpha rather than through
        a second, darker grey (see _renderMatplotlib).
        """
        self.figure.set_facecolor(self._background)
        self.axes.set_facecolor(self._background)
        self.axes.tick_params(colors=self._foreground, labelsize=8)
        for spine in self.axes.spines.values():
            spine.set_color(self._grid)
        self.axes.xaxis.label.set_color(self._foreground)
        self.axes.yaxis.label.set_color(self._foreground)
        self.axes.title.set_color(self._foreground)

    # =========================================================================
    # Palette
    # =========================================================================

    def _setThemeColour(self, attr: str, value, signal) -> None:
        """Assign one palette colour, ignoring anything unusable.

        A QML binding can hand us an empty string while its host window is
        still resolving its own colours, and an unresolved colour arrives as
        a nonsense string rather than as an exception. Either would make
        matplotlib raise from inside paint(), which leaves a blank widget
        with no way back; keeping the previous colour instead degrades to a
        canvas that is merely a scheme behind. is_color_like is the right
        test because matplotlib, not Qt, is what finally consumes these.

        Assigning the value the canvas already holds does nothing at all, so
        a binding that re-evaluates to the same colour costs no redraw.
        """
        colour = str(value or "").strip()
        if not colour:
            return
        if not is_color_like(colour):
            logger.warning("ProfileCanvas: %r is not a colour", colour)
            return
        if colour == getattr(self, attr):
            return
        setattr(self, attr, colour)
        signal.emit()
        self._needs_redraw = True
        self.update()

    def _overlayColour(self, colour: str, alpha: int) -> QColor:
        """A palette colour as a QPainter colour at a fixed alpha.

        The overlays are drawn by QPainter on top of the rendered figure,
        not by matplotlib, so they need the Qt form; the alpha is the
        overlay's own weight and does not come from the scheme."""
        qc = QColor(colour)
        if not qc.isValid():
            qc = QColor(255, 255, 255)
        qc.setAlpha(alpha)
        return qc

    def _get_background(self) -> str:
        return self._background

    def _set_background(self, value: str) -> None:
        self._setThemeColour('_background', value, self.backgroundColorChanged)

    #: The figure and axes ground — bind to the scheme's bgDark.
    backgroundColor = Property(str, _get_background, _set_background,
                               notify=backgroundColorChanged)

    def _get_foreground(self) -> str:
        return self._foreground

    def _set_foreground(self, value: str) -> None:
        self._setThemeColour('_foreground', value, self.foregroundColorChanged)

    #: Ticks, tick labels, axis labels and title — the scheme's textMuted.
    foregroundColor = Property(str, _get_foreground, _set_foreground,
                               notify=foregroundColorChanged)

    def _get_grid(self) -> str:
        return self._grid

    def _set_grid(self, value: str) -> None:
        self._setThemeColour('_grid', value, self.gridColorChanged)

    #: Spines, gridlines and the legend frame — the scheme's borderColor.
    gridColor = Property(str, _get_grid, _set_grid, notify=gridColorChanged)

    def _get_accent(self) -> str:
        return self._accent

    def _set_accent(self, value: str) -> None:
        self._setThemeColour('_accent', value, self.accentColorChanged)

    #: The rubber-band range selection. Optional — the default matches what
    #: this canvas drew before it was themed.
    accentColor = Property(str, _get_accent, _set_accent,
                           notify=accentColorChanged)

    def _get_cursor(self) -> str:
        return self._cursor

    def _set_cursor(self, value: str) -> None:
        self._setThemeColour('_cursor', value, self.cursorColorChanged)

    #: The hover cursor line. Optional, and deliberately a different hue
    #: from accentColor: both can be on screen at once.
    cursorColor = Property(str, _get_cursor, _set_cursor,
                           notify=cursorColorChanged)

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
        # cleanup() drops the figure, and a colour binding settling after
        # that would otherwise schedule a paint into nothing.
        if self.figure is None or self.axes is None:
            return

        self.figure.set_size_inches(w / self._dpi, h / self._dpi)

        # Clear and configure
        self.axes.clear()
        self._setupAxesStyle()

        # Plot main data
        if self._x_data is not None and self._y_data is not None:
            self.axes.plot(
                self._x_data, self._y_data,
                color=readable_on(self._line_color, self._background),
                linewidth=self._line_width,
                label='Profile'
            )

        # Plot additional curves
        for curve in self._curves:
            self.axes.plot(
                curve['x'], curve['y'],
                color=readable_on(curve['color'], self._background),
                linewidth=self._line_width,
                label=curve['name'],
                alpha=0.8
            )

        # Configure axes
        if self._show_grid:
            # Same colour as the spines; the alpha is what keeps the grid
            # from competing with them, and it does that on any scheme.
            self.axes.grid(True, color=self._grid, linestyle='-',
                           linewidth=0.5, alpha=0.5)

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
            # The legend sits on the plot ground rather than a shade of its
            # own, because the three themed roles carry no mid-tone. Near-
            # opaque so curves running underneath do not show through the
            # text; the frame is what separates it from the plot.
            self.axes.legend(loc='upper right', fontsize=8,
                            facecolor=self._background, edgecolor=self._grid,
                            labelcolor=self._foreground, framealpha=0.92)

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
        """Refresh pixel↔data mapping and register adapters with the
        viewbox so its interaction handlers can do the math
        themselves."""
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

        self._viewbox.set_transforms(self._pixelToData, self._dataToPixel)
        self._viewbox.set_axes_pixel_rect((
            self._data_bounds['ax_left'],
            self._data_bounds['ax_top'],
            self._data_bounds['ax_right'],
            self._data_bounds['ax_bottom'],
        ))

    def _pixelToData(self, px: float, py: float) -> Tuple[float, float]:
        """Linear pixel→data mapping (matches the profile canvas's
        original non-log behaviour)."""
        if self._data_bounds is None:
            return 0.0, 0.0
        d = self._data_bounds
        ax_w = d['ax_right'] - d['ax_left']
        ax_h = d['ax_bottom'] - d['ax_top']
        if ax_w <= 0 or ax_h <= 0:
            return 0.0, 0.0
        norm_x = (px - d['ax_left']) / ax_w
        norm_y = (py - d['ax_top']) / ax_h
        x = d['x_min'] + norm_x * (d['x_max'] - d['x_min'])
        y = d['y_max'] - norm_y * (d['y_max'] - d['y_min'])  # Y inverted
        return x, y

    def _dataToPixel(self, x: float, y: float) -> Tuple[float, float]:
        """Inverse of :meth:`_pixelToData` — needed by the viewbox
        for rubber-band hit-tests."""
        if self._data_bounds is None:
            return 0.0, 0.0
        d = self._data_bounds
        ax_w = d['ax_right'] - d['ax_left']
        ax_h = d['ax_bottom'] - d['ax_top']
        if d['x_max'] == d['x_min'] or d['y_max'] == d['y_min']:
            return float(d['ax_left']), float(d['ax_top'])
        norm_x = (x - d['x_min']) / (d['x_max'] - d['x_min'])
        norm_y = (d['y_max'] - y) / (d['y_max'] - d['y_min'])
        return (d['ax_left'] + norm_x * ax_w,
                d['ax_top'] + norm_y * ax_h)

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
                pen = QPen(self._overlayColour(self._cursor, 150))
                pen.setWidth(1)
                painter.setPen(pen)
                painter.drawLine(int(px), int(d['ax_top']),
                               int(px), int(d['ax_bottom']))

        # Draw selection range — read from the viewbox.
        sel = self._viewbox.selection_box_data()
        if sel is not None:
            d = self._data_bounds
            if d:
                ax_width = d['ax_right'] - d['ax_left']

                x1_norm = (sel[0] - d['x_min']) / (d['x_max'] - d['x_min'])
                x2_norm = (sel[2] - d['x_min']) / (d['x_max'] - d['x_min'])

                px1 = d['ax_left'] + x1_norm * ax_width
                px2 = d['ax_left'] + x2_norm * ax_width

                rect = QRectF(min(px1, px2), d['ax_top'],
                             abs(px2 - px1), d['ax_bottom'] - d['ax_top'])

                pen = QPen(self._overlayColour(self._accent, 150))
                pen.setWidth(1)
                painter.setPen(pen)
                painter.setBrush(QBrush(self._overlayColour(self._accent, 40)))
                painter.drawRect(rect)

    # =========================================================================
    # Mouse events
    # =========================================================================

    def mousePressEvent(self, event):
        """Start an x-range selection via the viewbox."""
        pos = event.position()
        x, y = self._pixelToData(pos.x(), pos.y())
        self.pointClicked.emit(x, y)
        self._viewbox.handle_press_left((pos.x(), pos.y()))

    def mouseMoveEvent(self, event):
        """Update cursor read-out + active rubber-band selection."""
        pos = event.position()
        x, y = self._pixelToData(pos.x(), pos.y())
        self.cursorMoved.emit(x, y)
        self._cursor_x = x
        self._show_cursor = True
        self._viewbox.handle_move((pos.x(), pos.y()))

    def mouseReleaseEvent(self, event):
        """Finalise the x-range selection, emit ``rangeSelected``."""
        pos = event.position()
        result = self._viewbox.handle_release_left(
            (pos.x(), pos.y()), drag_threshold_px=2.0,
        )
        if result is not None:
            x_min, _y_min, x_max, _y_max = result
            self.rangeSelected.emit(x_min, x_max)
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
