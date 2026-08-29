"""
QML Map Canvas - QQuickPaintedItem for matplotlib rendering in QML
Enables seamless integration of matplotlib maps into QML UI with
interactive tools for spatial-spectral reconstruction.
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
import os
from typing import Optional, Tuple, Dict, Any, List
from enum import Enum
import logging

from PySide6.QtCore import (
    Qt, Signal, Slot, Property, QPointF, QRectF, QObject, QTimer
)
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPen, QBrush, QCursor, QFontMetricsF, QPolygonF
)
from PySide6.QtQuick import QQuickPaintedItem

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from src.widgets._pyqtgraph_ports.image_render import (
    apply_levels_and_lut,
    downsample_image,
)
from src.widgets._pyqtgraph_ports.items.rect_roi import (
    HIT_NONE as ROI_HIT_NONE,
    RectROI,
)
from src.widgets._pyqtgraph_ports.mpl_apply import apply_pyqtgraph_ticks
from src.widgets._pyqtgraph_ports.ticks import (
    format_tick_strings,
    tick_values,
)
from src.widgets.lut import get_lut
from src.widgets.series_palette import readable_on
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


# =============================================================================
# Theme derivation
#
# The same three colours every canvas in TRANS takes from QML — the ground,
# the text and the rules — and the same reason for deriving the rest: a map's
# tick marks have to read as dimmer than the numbers beside them, and a fixed
# grey would be dimmer on a dark scheme and brighter on a light one.
#
# The twin of this block lives in ``qml_graph_canvas``; see the longer note
# there for why it is not a shared module.
# =============================================================================

def _alpha(colour: QColor, a: int) -> QColor:
    """The same colour at a given alpha, without mutating the original."""
    out = QColor(colour)
    out.setAlpha(a)
    return out


def _contrast_pole(background: QColor) -> QColor:
    """White on a dark ground, black on a light one."""
    luminance = (0.299 * background.redF() + 0.587 * background.greenF()
                 + 0.114 * background.blueF())
    return QColor('#ffffff') if luminance < 0.5 else QColor('#000000')


def _blend(base: QColor, towards: QColor, amount: float) -> QColor:
    """``base`` moved ``amount`` (0..1) of the way towards ``towards``."""
    amount = max(0.0, min(1.0, float(amount)))
    return QColor(
        round(base.red() + (towards.red() - base.red()) * amount),
        round(base.green() + (towards.green() - base.green()) * amount),
        round(base.blue() + (towards.blue() - base.blue()) * amount),
    )


def _fast_map_render_enabled_default() -> bool:
    """``TRANS_FAST_MAP_RENDER`` toggle. Default ``True`` — set the
    env var to ``0`` / ``false`` / ``no`` / ``off`` to fall back to
    the matplotlib pipeline if a regression is found. The matplotlib
    code path is still alive: ``_renderMatplotlib`` keeps driving
    ``exportToPNG`` / ``exportToSVG`` / ``exportToPDF`` so the export
    output stays high-DPI even when interactive rendering goes
    native."""
    val = os.environ.get("TRANS_FAST_MAP_RENDER", "").strip().lower()
    if val in ("0", "false", "no", "off"):
        return False
    return True


class MapTool(Enum):
    """Available map editing tools"""
    POINTER = "pointer"
    ZOOM_RECT = "zoom_rect"
    PAN = "pan"
    LINE_PROFILE = "line_profile"
    POINT_INSPECTOR = "point_inspector"
    RECT_SELECT = "rect_select"
    MEASURE = "measure"
    CROSSHAIR = "crosshair"
    BLOCK_SELECT = "block_select"  # For discretized block selection (TRANS_v3 style)


class QMLMapCanvas(QQuickPaintedItem):
    """
    Matplotlib canvas that renders directly in QML scene graph.

    This QQuickPaintedItem renders matplotlib figures and handles mouse
    events for interactive tools like point inspection, line profiles,
    and region selection.

    Signals:
        pointClicked(x, y, row, col, value): Emitted when clicking on map
        profileDrawn(startRow, startCol, endRow, endCol): line profile in data coords
        regionSelected(x1, y1, x2, y2): Emitted after rect selection
        cursorMoved(x, y, row, col, value): Emitted on cursor movement
        toolChanged(toolName): Emitted when tool changes
        mapUpdated(): Emitted after map data changes
    """

    # Signals to QML
    pointClicked = Signal(float, float, int, int, float, arguments=['x', 'y', 'row', 'col', 'value'])
    profileDrawn = Signal(int, int, int, int,
                          arguments=['startRow', 'startCol', 'endRow', 'endCol'])
    regionSelected = Signal(float, float, float, float, arguments=['x1', 'y1', 'x2', 'y2'])
    cursorMoved = Signal(float, float, int, int, float, arguments=['x', 'y', 'row', 'col', 'value'])
    toolChanged = Signal(str, arguments=['toolName'])
    mapUpdated = Signal()
    spectralDataRequested = Signal(int, int, arguments=['row', 'col'])
    # Emitted when a click lands on an STS marker dot (the index into the map's
    # sts_locations list), so the backend can plot that point's spectrum.
    stsMarkerClicked = Signal(int, arguments=['index'])

    # Block selection signals (TRANS_v3 style)
    blockSelected = Signal(int, int, float, bool, arguments=['blockRow', 'blockCol', 'value', 'isSelected'])
    blockSelectionChanged = Signal(arguments=[])  # Emitted when selection set changes

    # Phase 6.4 — RectROI overlay change signals. ``rect`` is
    # ``(col0, row0, col1, row1)`` in grid-index space, matching the
    # axis convention used by ``addRectROI``.
    roiChanged = Signal(
        str, float, float, float, float,
        arguments=['roiId', 'col0', 'row0', 'col1', 'row1'],
    )
    roiChangeFinished = Signal(
        str, float, float, float, float,
        arguments=['roiId', 'col0', 'row0', 'col1', 'row1'],
    )

    # Phase 7.4 — native render constants. Margins are slightly
    # tighter than the graph canvas's because the map has no axis
    # labels — just integer pixel-index ticks.
    _NATIVE_AX_MARGIN_LEFT = 40
    _NATIVE_AX_MARGIN_RIGHT = 16
    _NATIVE_AX_MARGIN_TOP = 12
    _NATIVE_AX_MARGIN_BOTTOM = 30
    # Only the fallback for an instance that never reached
    # ``_recomputeThemeColours`` — normally each of these is shadowed by an
    # instance attribute derived from backgroundColor / foregroundColor /
    # gridColor.
    _NATIVE_BG_COLOR = QColor("#1a1a1a")
    _NATIVE_AXIS_COLOR = QColor("#444444")
    _NATIVE_TICK_COLOR = QColor("#888888")
    _NATIVE_LABEL_COLOR = QColor("#cccccc")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.AllButtons)
        self.setAcceptHoverEvents(True)
        self.setFlag(QQuickPaintedItem.ItemHasContents, True)
        # Render via a GPU framebuffer so the painter is device-pixel-ratio
        # scaled on HiDPI/Retina. With the default Image target the paint
        # painter is not DPR-scaled on macOS, which drew the map into the
        # top-left quarter of the item while clicks/overlays used full logical
        # coords (matches the QMLImageCanvas / QMLGraphCanvas fix).
        try:
            self.setRenderTarget(QQuickPaintedItem.FramebufferObject)
        except Exception:
            pass  # Software-only Qt builds don't support FBO targets

        # Theme. The defaults reproduce the palette this canvas shipped with,
        # so a host that binds nothing looks exactly as it did; QML overwrites
        # all three from the colour scheme. Set before the Figure exists
        # because the Figure's own facecolor is one of the derived roles.
        self._background: str = "#1a1a1a"
        self._foreground: str = "#cccccc"
        self._grid_colour: str = "#444444"
        # Interaction chrome. Default is the former literal, so an unbound
        # canvas paints exactly what it painted before.
        self._accent: str = "#5bcefa"
        self._recomputeThemeColours()

        # Matplotlib setup
        self._dpi = 100
        self.figure = Figure(facecolor=self._background, dpi=self._dpi)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasAgg(self.figure)

        # Configure axes style. This used to set the facecolor, ticks and
        # spines but not the label or title text, which left them at
        # matplotlib's default black — invisible against the dark ground until
        # the first physical-units render reached the label colour further
        # down. ``_applyAxesStyle`` styles all of it, in one place, from the
        # same derived roles the native path paints with.
        self._applyAxesStyle()

        # Map data
        self._map_data: Optional[np.ndarray] = None
        self._colormap: str = 'viridis'
        self._vmin: Optional[float] = None
        self._vmax: Optional[float] = None
        # Percentile clip for auto-scaling; (0, 100) shows the full range.
        #
        # It used to default to 2-98, which throws away the tails — and in a
        # computed map the tails ARE the signal. On a bias-versus-position
        # LDOS map that kept 13% of the value range and drove 4% of the
        # pixels to a solid end colour: a thresholded-looking image where the
        # states should stand out. Auto-scale now spans the data; clipping is
        # available through setPercentileClip for scans where a railed pixel
        # would otherwise flatten everything.
        self._percentile_clip: Tuple[float, float] = (0.0, 100.0)
        self._image_handle = None

        # Tool state
        self._current_tool: MapTool = MapTool.POINTER
        self._is_dragging: bool = False
        self._drag_start: Optional[QPointF] = None
        self._drag_current: Optional[QPointF] = None

        # Overlay elements
        self._show_crosshair: bool = False
        self._crosshair_pos: Optional[Tuple[int, int]] = None
        # Profile line stored as axes-fraction endpoints ((nx0,ny0),(nx1,ny1))
        # — fractions within the image axes rect — so it tracks the data on
        # resize instead of sticking to absolute screen pixels.
        self._profile_line: Optional[Tuple[Tuple[float, float],
                                            Tuple[float, float]]] = None
        self._selection_rect: Optional[QRectF] = None

        # Coordinate transform cache
        self._data_to_pixel: Optional[Dict] = None

        # Render cache
        self._cached_image: Optional[QImage] = None
        self._needs_redraw: bool = True

        # Resize debounce timer — avoids re-rendering matplotlib on every pixel
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)  # ms
        self._resize_timer.timeout.connect(self._onResizeFinished)

        # Block selection state (TRANS_v3 style)
        # For discretized data where each cell represents a spatial block
        self._selected_blocks: set = set()  # Set of (row, col) tuples
        self._block_mode: bool = False  # True when displaying discretized blocks
        self._discretized_data: Optional[np.ndarray] = None  # Discretized (averaged) data
        self._block_size: Optional[Tuple[int, int]] = None  # (block_v, block_h) in original pixels

        # Grid overlay state for discretization
        self._show_grid_overlay: bool = False
        self._grid_block_h: int = 1  # Horizontal block size in pixels
        self._grid_block_v: int = 1  # Vertical block size in pixels
        self._hover_block: Optional[Tuple[int, int]] = None  # Grid block under cursor

        # STS grid region overlay (topography with spectral grid position)
        self._sts_region_rect: Optional[Tuple[float, float, float, float]] = None  # (x0, y0, x1, y1) in fractional coords

        # STS point markers — where spectra were taken on this scan image.
        # Each marker is {'row': int, 'col': int, 'label': str}; row/col are in
        # the map data grid (col = STS pixel x, row = STS pixel y).
        self._sts_markers: list = []
        self._show_sts_markers: bool = True
        # Line-scan outlines: each {'label': str, 'path': [{'row','col'}, …]}.
        # Drawn under the dots so a line reads as one acquisition instead of a
        # row of unrelated points.
        self._sts_lines: list = []
        # Optional per-axis description for the cursor read-out (a kymograph's
        # axes are different quantities). None → fall back to _phys_extent.
        self._axis_meta: Optional[dict] = None
        # Indices of currently-selected STS markers (their spectra are plotted).
        self._sts_selected: set = set()
        # ``index`` of the STS marker currently under the cursor (hover popup),
        # or None. Only tracked with the POINTER tool.
        self._hover_sts: Optional[int] = None

        # Spectral cube link for reconstruction
        self._spectral_cube: Optional[np.ndarray] = None  # Shape: (n_spectral_pts, rows, cols)
        self._independent_var: Optional[np.ndarray] = None  # Wavenumber/voltage axis
        self._independent_var_name: str = "x"

        # Phase 6.4 — ``RectROI`` overlay items. These live alongside
        # the existing RECT_SELECT / BLOCK_SELECT tools rather than
        # replacing them: this iteration adds the ROI as an
        # independently-controllable item the QML side can opt in to
        # via ``addRectROI``, so the existing tools keep working.
        self._rect_rois: List[RectROI] = []
        self._roi_drag: Optional[Dict[str, Any]] = None

        # Phase 7.4 — native (matplotlib-free) interactive renderer.
        # ``_renderForExport`` keeps matplotlib alive for high-DPI
        # ``exportTo*`` slots; on-screen ``paint`` goes through
        # ``_renderNative`` when the toggle is on (default).
        self._use_fast_render: bool = _fast_map_render_enabled_default()
        self._native_qimage: Optional[QImage] = None  # cached colourised map

        # Physical axis extent. When set, the map axes are labelled in real
        # units (e.g. nm) spanning the scan window instead of pixel indices.
        # ``(x_size, y_size, unit)`` with sizes in ``unit``; None → pixel
        # indices (default, unchanged for maps without calibration).
        self._phys_extent: Optional[Tuple[float, float, str]] = None

    @Slot()
    def cleanup(self):
        """Release matplotlib resources to prevent memory leaks."""
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
            logger.debug("MapCanvas cleaned up matplotlib resources")
        except Exception as e:
            logger.warning(f"Error during MapCanvas cleanup: {e}")

    # =========================================================================
    # Theme (QML-bindable)
    # =========================================================================

    def _recomputeThemeColours(self) -> None:
        """Derive every painted role from the three colours QML supplies.

        A map has no legend and no title, so it needs four roles rather than
        the graph canvas's eight, but the reasoning is the same one:

        * **background** — the ground, straight from ``backgroundColor``.
        * **axis frame** — ``gridColor``. A frame is a rule.
        * **tick marks** — the foreground pulled 40% back towards the ground,
          so the structure stays quieter than the numbers on it.
        * **tick labels and axis unit titles** — the foreground exactly, the
          pairing ``src/utils/color_contrast.py`` already enforces.
        """
        background = QColor(self._background)
        foreground = QColor(self._foreground)
        rules = QColor(self._grid_colour)

        self._tick_colour = _blend(foreground, background, 0.40)

        self._NATIVE_BG_COLOR = background
        self._NATIVE_AXIS_COLOR = rules
        self._NATIVE_TICK_COLOR = self._tick_colour
        self._NATIVE_LABEL_COLOR = foreground

        # The hover/tag chips are UI panels, not marks on the data, so they
        # are the one piece of map chrome a palette can legitimately drive:
        # the chip supplies its own ground, and the label sits on THAT, not
        # on whatever colormap value happens to be underneath.
        self._chip_bg = _blend(background, _contrast_pole(background), 0.06)
        self._chip_ink = QColor(readable_on(self._accent, self._chip_bg.name()))
        self._roi_colour = QColor(self._accent)

        # WHAT IS DELIBERATELY NOT THEMED, AND WHY.
        #
        # Every other overlay in this file — the STS rings and dots, the map
        # grid, the line-profile trace, the region/line/target marks — is drawn
        # ON TOP OF COLORMAP IMAGE DATA, not on the scheme's background. Their
        # ground is whatever value the user's data happens to take under the
        # mark, which a palette colour has no relationship to: binding them to
        # the scheme would trade a colour that is wrong on eight schemes for one
        # that is wrong on an arbitrary subset of pixels in all twenty-two, and
        # readable_on() cannot help because there is no single ground to be
        # readable against. They are also identity — the yellow ring IS the idle
        # STS marker — so recolouring them per scheme costs meaning as well.
        #
        # The fix those marks actually need is a two-tone stroke (a dark halo
        # under a light core, legible over any value), which is a visual design
        # change to every mark rather than a binding, and is left as such.

    def _applyAxesStyle(self) -> None:
        """Push the derived roles onto the matplotlib figure and axes.

        Called at construction and again after every ``axes.clear()`` in
        ``_render``, because clearing drops the styling with it.
        """
        if getattr(self, 'axes', None) is None:
            return
        if getattr(self, 'figure', None) is not None:
            self.figure.set_facecolor(self._background)
        self.axes.set_facecolor(self._background)
        self.axes.tick_params(colors=self._tick_colour.name(), labelsize=8)
        for spine in self.axes.spines.values():
            spine.set_color(self._grid_colour)
        self.axes.xaxis.label.set_color(self._foreground)
        self.axes.yaxis.label.set_color(self._foreground)
        self.axes.title.set_color(self._foreground)

    def _setThemeColour(self, attribute: str, colour, changed) -> None:
        """Idempotent, garbage-tolerant setter shared by the three roles.

        An empty string is an unresolved QML binding rather than a choice, and
        an unparseable one is a typo; neither should repaint the map in a
        half-applied palette, so both leave the current colour alone. The
        comparison is on the canonical ``#rrggbb`` form so ``"#1A1A1A"`` and
        ``"#1a1a1a"`` count as no change.
        """
        text = str(colour or "").strip()
        if not text:
            return
        parsed = QColor(text)
        if not parsed.isValid():
            logger.warning("MapCanvas: %r is not a colour", text)
            return
        canonical = parsed.name()
        if canonical == QColor(getattr(self, attribute)).name():
            return
        setattr(self, attribute, canonical)
        self._recomputeThemeColours()
        # The native path re-reads the ``_NATIVE_*`` attributes every frame,
        # but the matplotlib figure holds its styling, so push it now —
        # otherwise ``exportImage`` writes the previous scheme's chrome.
        self._applyAxesStyle()
        self._needs_redraw = True
        changed.emit()
        self.update()

    backgroundColorChanged = Signal()
    foregroundColorChanged = Signal()
    gridColorChanged = Signal()
    accentColorChanged = Signal()

    def _get_background_colour(self) -> str:
        return self._background

    def _set_background_colour(self, colour: str) -> None:
        self._setThemeColour('_background', colour, self.backgroundColorChanged)

    def _get_foreground_colour(self) -> str:
        return self._foreground

    def _set_foreground_colour(self, colour: str) -> None:
        self._setThemeColour('_foreground', colour, self.foregroundColorChanged)

    def _get_grid_colour(self) -> str:
        return self._grid_colour

    def _set_grid_colour(self, colour: str) -> None:
        self._setThemeColour('_grid_colour', colour, self.gridColorChanged)

    def _get_accent_colour(self) -> str:
        return self._accent

    def _set_accent_colour(self, colour: str) -> None:
        self._setThemeColour('_accent', colour, self.accentColorChanged)

    #: The margin around the map — the scheme's window background.
    backgroundColor = Property(str, _get_background_colour,
                               _set_background_colour,
                               notify=backgroundColorChanged)
    #: Text: tick labels and the axis unit titles; the tick marks are derived
    #: from it.
    foregroundColor = Property(str, _get_foreground_colour,
                               _set_foreground_colour,
                               notify=foregroundColorChanged)
    #: Rules: the axes frame.
    gridColor = Property(str, _get_grid_colour, _set_grid_colour,
                         notify=gridColorChanged)
    #: Interaction chrome: the STS line band and the hover/tag chips.
    accentColor = Property(str, _get_accent_colour, _set_accent_colour,
                           notify=accentColorChanged)

    # =========================================================================
    # Properties exposed to QML
    # =========================================================================

    @Property(str, notify=toolChanged)
    def currentTool(self) -> str:
        return self._current_tool.value

    @Property(str)
    def colormap(self) -> str:
        return self._colormap

    @colormap.setter
    def colormap(self, value: str):
        if value != self._colormap:
            self._colormap = value
            self._needs_redraw = True
            self.update()

    @Property(bool)
    def showCrosshair(self) -> bool:
        return self._show_crosshair

    @showCrosshair.setter
    def showCrosshair(self, value: bool):
        self._show_crosshair = value
        self.update()

    @Property(bool)
    def hasData(self) -> bool:
        return self._map_data is not None

    @Property(int)
    def dataRows(self) -> int:
        return self._map_data.shape[0] if self._map_data is not None else 0

    @Property(int)
    def dataCols(self) -> int:
        return self._map_data.shape[1] if self._map_data is not None else 0

    # =========================================================================
    # Slots callable from QML
    # =========================================================================

    @Slot(str)
    def setTool(self, tool_name: str):
        """Set the current active tool"""
        try:
            self._current_tool = MapTool(tool_name)
            self.toolChanged.emit(tool_name)
            self._updateCursor()
            self.update()
        except ValueError:
            logger.warning(f"Unknown tool: {tool_name}")

    @Slot(str)
    def setColormap(self, colormap: str):
        """Set the colormap for the map display"""
        self._colormap = colormap
        self._needs_redraw = True
        self.update()

    @Slot(float, float)
    def setValueRange(self, vmin: float, vmax: float):
        """Set explicit value range for colormap"""
        self._vmin = vmin
        self._vmax = vmax
        self._needs_redraw = True
        self.update()

    @Slot()
    def autoScale(self):
        """Auto-scale using percentile clipping"""
        self._vmin = None
        self._vmax = None
        self._needs_redraw = True
        self.update()

    @Slot(float, float)
    def setPercentileClip(self, low: float, high: float):
        """Set the auto-scale clip, in percent (0, 100 = the full range).

        Out-of-order or out-of-range values are ignored rather than producing
        an inverted colour scale.
        """
        try:
            low, high = float(low), float(high)
        except (TypeError, ValueError):
            return
        if not (0.0 <= low < high <= 100.0):
            logger.warning("Ignoring percentile clip (%s, %s): expected "
                           "0 <= low < high <= 100", low, high)
            return
        self._percentile_clip = (low, high)
        self._needs_redraw = True
        self.update()

    def _compute_display_levels(self) -> Tuple[float, float]:
        """Resolve the (lo, hi) colour levels for the current map.

        Explicit ``_vmin``/``_vmax`` win; otherwise percentile-clip the
        data. Guards against the degenerate cases that otherwise paint the
        whole map white: a map with no linked spectra is all-NaN (or
        empty), and ``np.nanpercentile`` returns NaN there — NaN levels
        feed the LUT as ``(data - NaN) / NaN`` → all-NaN → white. We fall
        back to a safe unit range and ensure ``hi > lo`` with finite ends.
        """
        if self._vmin is not None and self._vmax is not None:
            lo, hi = float(self._vmin), float(self._vmax)
        elif self._map_data is not None and np.isfinite(self._map_data).any():
            lo = float(np.nanpercentile(self._map_data, self._percentile_clip[0]))
            hi = float(np.nanpercentile(self._map_data, self._percentile_clip[1]))
        else:
            # No data / all-NaN / empty — nothing meaningful to scale to.
            lo, hi = 0.0, 1.0
        if not (np.isfinite(lo) and np.isfinite(hi)):
            lo, hi = 0.0, 1.0
        if hi <= lo:
            hi = lo + 1.0
        return lo, hi

    @Slot()
    def clearOverlays(self):
        """Clear all overlay elements"""
        self._profile_line = None
        self._selection_rect = None
        self._crosshair_pos = None
        self.update()

    @Slot(result='QVariantList')
    def getValueRange(self) -> List[float]:
        """Get current value range [min, max]"""
        if self._map_data is None:
            return [0.0, 1.0]
        lo, hi = self._compute_display_levels()
        return [lo, hi]

    # =========================================================================
    # Block selection methods (TRANS_v3 style)
    # =========================================================================

    @Slot(int, int)
    def toggleBlockSelection(self, row: int, col: int):
        """Toggle selection state of a block"""
        key = (row, col)
        if key in self._selected_blocks:
            self._selected_blocks.remove(key)
            is_selected = False
        else:
            self._selected_blocks.add(key)
            is_selected = True

        value = self.getValueAt(row, col)
        self.blockSelected.emit(row, col, value, is_selected)
        self.blockSelectionChanged.emit()
        self.update()

    @Slot()
    def clearBlockSelection(self):
        """Clear all block selections"""
        self._selected_blocks.clear()
        self.blockSelectionChanged.emit()
        self.update()

    @Slot()
    def selectAllBlocks(self):
        """Select all blocks"""
        if self._map_data is None:
            return
        for row in range(self._map_data.shape[0]):
            for col in range(self._map_data.shape[1]):
                self._selected_blocks.add((row, col))
        self.blockSelectionChanged.emit()
        self.update()

    @Slot(result=int)
    def getSelectedBlockCount(self) -> int:
        """Get number of selected blocks"""
        return len(self._selected_blocks)

    @Slot(result='QVariantList')
    def getSelectedBlocks(self) -> List[Dict]:
        """Get list of selected blocks with their values"""
        result = []
        for row, col in sorted(self._selected_blocks):
            value = self.getValueAt(row, col)
            result.append({'row': row, 'col': col, 'value': value})
        return result

    # =========================================================================
    # Phase 6.4 — RectROI overlay items
    # =========================================================================

    def _roi_data_to_pixel(self):
        """Return a ``(col, row) -> (pixel_x, pixel_y)`` callable.

        The ``RectROI`` port speaks generic ``(x, y)`` data coords; the
        map canvas's natural data space is ``(col, row)``. This adapter
        bridges the two so the ROI corners and the existing
        block-grid live on the same axes.
        """
        d = self._data_to_pixel
        if d is None:
            return lambda x, y: (0.0, 0.0)
        ax_left = d['ax_left']; ax_top = d['ax_top']
        ax_w = d['ax_right'] - ax_left
        ax_h = d['ax_bottom'] - ax_top
        rows = d['data_rows']; cols = d['data_cols']
        return lambda x, y: (
            ax_left + (float(x) / cols) * ax_w,
            ax_top + (float(y) / rows) * ax_h,
        )

    def _roi_pixel_to_data(
        self, px: float, py: float,
    ) -> Tuple[float, float]:
        """Inverse of ``_roi_data_to_pixel``. Returns ``(col, row)``
        in **float** units so partial-cell ROI corners survive."""
        d = self._data_to_pixel
        if d is None:
            return 0.0, 0.0
        ax_w = d['ax_right'] - d['ax_left']
        ax_h = d['ax_bottom'] - d['ax_top']
        col = (px - d['ax_left']) / ax_w * d['data_cols']
        row = (py - d['ax_top']) / ax_h * d['data_rows']
        return float(col), float(row)

    def _find_roi_at(
        self,
        x_pixel: float, y_pixel: float,
        ax_rect: QRectF,
    ) -> Optional[Tuple[RectROI, str]]:
        if not self._rect_rois:
            return None
        data_to_pixel = self._roi_data_to_pixel()
        for roi in reversed(self._rect_rois):
            hit = roi.hit_test(
                x_pixel, y_pixel,
                data_to_pixel=data_to_pixel,
                ax_rect=ax_rect,
            )
            if hit != ROI_HIT_NONE:
                return roi, hit
        return None

    def _emit_roi_change(
        self, roi: RectROI, finished: bool,
    ) -> None:
        rid = str(roi.roi_id)
        x0, y0, x1, y1 = roi.rect()
        if finished:
            self.roiChangeFinished.emit(rid, x0, y0, x1, y1)
        else:
            self.roiChanged.emit(rid, x0, y0, x1, y1)

    def _current_roi_snap_step(
        self,
    ) -> Optional[Tuple[Optional[float], Optional[float]]]:
        """Snap step in ``(col, row)`` units when the grid overlay is
        active and at least one axis has a non-trivial block size.
        ``None`` when the grid overlay is off — every freshly added
        ROI starts free-form."""
        if not self._show_grid_overlay:
            return None
        if self._grid_block_h <= 1 and self._grid_block_v <= 1:
            return None
        sx = float(self._grid_block_h) if self._grid_block_h > 1 else None
        sy = float(self._grid_block_v) if self._grid_block_v > 1 else None
        return (sx, sy)

    @Slot(str, float, float, float, float)
    def addRectROI(
        self,
        roiId: str,
        col0: float, row0: float,
        col1: float, row1: float,
    ) -> None:
        """Add an axis-aligned ROI between ``(col0, row0)`` and
        ``(col1, row1)``. When the discretization grid overlay is
        active the ROI auto-snaps to the block grid; otherwise it's
        free-form. Replaces any existing ROI with the same id."""
        self.addRectROIWithOptions(
            roiId, col0, row0, col1, row1, "", "",
        )

    @Slot(str, float, float, float, float, str, str)
    def addRectROIWithOptions(
        self,
        roiId: str,
        col0: float, row0: float,
        col1: float, row1: float,
        color: str,
        label: str,
    ) -> None:
        if not roiId:
            return
        self.removeRectROI(roiId)
        d = self._data_to_pixel
        bounds_x = bounds_y = None
        if d is not None:
            bounds_x = (0.0, float(d['data_cols']))
            bounds_y = (0.0, float(d['data_rows']))
        roi = RectROI(
            roi_id=roiId,
            rect=(float(col0), float(row0), float(col1), float(row1)),
            bounds_x=bounds_x,
            bounds_y=bounds_y,
            snap_step=self._current_roi_snap_step(),
            pen_color=color or "#5BCEFA",
            brush_color=color or "#5BCEFA",
            label=label or "",
        )
        self._rect_rois.append(roi)
        self.update()

    @Slot(str)
    def removeRectROI(self, roiId: str) -> None:
        before = len(self._rect_rois)
        self._rect_rois = [
            r for r in self._rect_rois
            if str(r.roi_id) != roiId
        ]
        if (
            self._roi_drag is not None
            and str(self._roi_drag.get("roi_id")) == roiId
        ):
            self._roi_drag = None
        if len(self._rect_rois) != before:
            self.update()

    @Slot()
    def clearRectROIs(self) -> None:
        if not self._rect_rois:
            return
        self._rect_rois.clear()
        self._roi_drag = None
        self.update()

    @Slot(str, result='QVariantList')
    def getRectROI(self, roiId: str):
        """Return ``[col0, row0, col1, row1]`` for the named ROI, or
        an empty list if absent."""
        for roi in self._rect_rois:
            if str(roi.roi_id) == roiId:
                x0, y0, x1, y1 = roi.rect()
                return [float(x0), float(y0), float(x1), float(y1)]
        return []

    @Slot(str, float, float, float, float)
    def setRectROI(
        self,
        roiId: str,
        col0: float, row0: float,
        col1: float, row1: float,
    ) -> None:
        for roi in self._rect_rois:
            if str(roi.roi_id) == roiId:
                if roi.set_rect(
                    float(col0), float(row0),
                    float(col1), float(row1),
                ):
                    self.update()
                return

    def getSelectionMask(self) -> np.ndarray:
        """
        Get 2D boolean mask from selected blocks.
        If in block mode with discretization, expands to original dimensions.
        """
        if self._map_data is None:
            return np.array([])

        rows, cols = self._map_data.shape
        mask = np.zeros((rows, cols), dtype=bool)

        for row, col in self._selected_blocks:
            if 0 <= row < rows and 0 <= col < cols:
                mask[row, col] = True

        # If we have block size info, expand mask to original dimensions
        if self._block_size is not None and self._block_mode:
            block_v, block_h = self._block_size
            orig_rows = rows * block_v
            orig_cols = cols * block_h
            expanded_mask = np.zeros((orig_rows, orig_cols), dtype=bool)

            for row, col in self._selected_blocks:
                r0 = row * block_v
                r1 = min((row + 1) * block_v, orig_rows)
                c0 = col * block_h
                c1 = min((col + 1) * block_h, orig_cols)
                expanded_mask[r0:r1, c0:c1] = True

            return expanded_mask

        return mask

    # =========================================================================
    # Grid Overlay for Discretization
    # =========================================================================

    @Slot(int, int)
    def setGridBlockSize(self, block_h: int, block_v: int):
        """Set grid block size and enable grid overlay."""
        self._grid_block_h = max(1, block_h)
        self._grid_block_v = max(1, block_v)
        self._show_grid_overlay = True
        self._selected_blocks.clear()
        self._hover_block = None
        self._needs_redraw = True
        self.blockSelectionChanged.emit()
        self.update()
        logger.info(f"Grid overlay enabled: block_h={block_h}, block_v={block_v}")

    @Slot(bool)
    def setGridOverlayVisible(self, visible: bool):
        """Show or hide the grid overlay."""
        self._show_grid_overlay = visible
        self.update()

    def setStsRegionRect(self, x0: float, y0: float, x1: float, y1: float):
        """
        Set the STS grid region rectangle overlay in fractional coordinates.

        (x0, y0) and (x1, y1) are opposite corners, each in [0,1] range
        relative to the map data extents.
        """
        self._sts_region_rect = (x0, y0, x1, y1)
        self._needs_redraw = True
        self.update()

    def clearStsRegionRect(self):
        """Remove the STS grid region rectangle overlay."""
        self._sts_region_rect = None
        self.update()

    @Slot("QVariantList")
    def setStsMarkers(self, markers):
        """Set the STS point markers (where spectra were taken on this scan).

        ``markers`` is a list of dicts with integer ``row``/``col`` (in the map
        data grid) and a ``label`` string. Pass an empty list to clear.
        """
        cleaned = []
        for m in markers or []:
            try:
                cleaned.append({
                    'row': int(m['row']), 'col': int(m['col']),
                    'label': str(m.get('label', '')),
                    'index': int(m.get('index', -1)),
                })
            except (KeyError, TypeError, ValueError):
                continue
        self._sts_markers = cleaned
        self._sts_selected = set()   # fresh markers → clear selection
        self._needs_redraw = True
        self.update()

    def _sts_marker_obstacles(self, fm) -> list:
        """Rectangles the line tags must stay off: every dot and its number.

        A tag parked on the points hides the very data it names, so the dots
        and their labels are treated as occupied space when a chip is placed.
        """
        if not (self._show_sts_markers and self._sts_markers
                and self._data_to_pixel is not None):
            return []
        rects, th = [], fm.height()
        for mk in self._sts_markers:
            x, y = self._dataToPixel(mk['row'], mk['col'])
            r = 9.0                        # the largest dot radius drawn
            rects.append(QRectF(x - r, y - r, 2 * r, 2 * r))
            label = mk.get('label', '')
            if label:
                rects.append(QRectF(x + r, y - r - 2 - th,
                                    fm.horizontalAdvance(label) + 2, th))
        return rects

    @staticmethod
    def _chip_candidates(pts, width, height, canvas_w, canvas_h) -> list:
        """Places a line's tag could sit, best first.

        Anchored beside the line's start, end and middle — above and below —
        so a horizontal line's tag has somewhere to go that is not on top of
        the line itself.
        """
        gap = 12.0
        anchors = [pts[0], pts[-1], pts[len(pts) // 2]]
        candidates = []
        for ax, ay in anchors:
            for dy in (-(height + gap), gap, -(height + gap) * 2, gap * 2 + height):
                for dx in (gap, -(width + gap)):
                    x = min(max(0.0, ax + dx), max(0.0, canvas_w - width))
                    y = min(max(0.0, ay + dy), max(0.0, canvas_h - height))
                    candidates.append(QRectF(x, y, width, height))
        return candidates

    @staticmethod
    def _place_chip(candidates, blockers) -> QRectF:
        """First candidate that hits nothing; failing that, the least-covered.

        Never returns None: with a crowded canvas a tag still has to be
        drawn, so the least-bad spot wins rather than the label vanishing.
        """
        if not candidates:
            return QRectF()
        if not blockers:
            return candidates[0]

        best, best_overlap = None, None
        for chip in candidates:
            overlap = 0.0
            for other in blockers:
                hit = chip.intersected(other)
                if not hit.isEmpty():
                    overlap += hit.width() * hit.height()
            if overlap == 0.0:
                return chip
            if best_overlap is None or overlap < best_overlap:
                best, best_overlap = chip, overlap
        return best

    @Slot("QVariantList")
    def setStsLines(self, lines):
        """Set the line-scan outlines drawn over this scan image.

        ``lines`` is a list of ``{'label': str, 'path': [{'row','col'}, …]}``
        in map-grid coordinates. Pass an empty list to clear.
        """
        cleaned = []
        for ln in lines or []:
            path = []
            for pt in (ln.get('path') or []):
                try:
                    path.append((int(pt['row']), int(pt['col'])))
                except (KeyError, TypeError, ValueError):
                    continue
            if len(path) < 2:
                continue
            cleaned.append({'label': str(ln.get('label', '')), 'path': path})
        self._sts_lines = cleaned
        self._needs_redraw = True
        self.update()

    @Slot("QVariantList")
    def setSelectedStsMarkers(self, indices):
        """Highlight the given STS marker indices as selected (spectra plotted)."""
        sel = set()
        for i in indices or []:
            try:
                sel.add(int(i))
            except (TypeError, ValueError):
                continue
        self._sts_selected = sel
        self.update()

    def _sts_marker_at(self, px: float, py: float, tol: float = 7.0):
        """Return the STS marker whose dot is within ``tol`` px of (px, py).

        Nearest dot wins when several overlap (dense line scans). Returns the
        marker dict or None. Assumes ``self._data_to_pixel`` is set.
        """
        if not (self._sts_markers and self._data_to_pixel is not None):
            return None
        best = None
        best_d2 = tol * tol
        for mk in self._sts_markers:
            mx, my = self._dataToPixel(mk['row'], mk['col'])
            d2 = (px - mx) ** 2 + (py - my) ** 2
            if d2 <= best_d2:
                best_d2 = d2
                best = mk
        return best

    @Slot()
    def clearStsMarkers(self):
        """Remove all STS point markers."""
        self._sts_markers = []
        self._hover_sts = None
        self.update()

    @Slot(bool)
    def setShowStsMarkers(self, show: bool):
        """Toggle visibility of the STS point markers."""
        self._show_sts_markers = bool(show)
        self.update()

    @Slot()
    def clearGridOverlay(self):
        """Remove grid overlay and reset grid state."""
        self._show_grid_overlay = False
        self._grid_block_h = 1
        self._grid_block_v = 1
        self._hover_block = None
        self._selected_blocks.clear()
        self.blockSelectionChanged.emit()
        self.update()

    def _pixelToGridBlock(self, x: float, y: float) -> Tuple[int, int]:
        """Convert pixel coordinates to grid block (grid_row, grid_col)."""
        row, col = self._pixelToData(x, y)
        if self._grid_block_h > 1 or self._grid_block_v > 1:
            grid_col = col // self._grid_block_h
            grid_row = row // self._grid_block_v
            return grid_row, grid_col
        return row, col

    # =========================================================================
    # Spectral-Spatial Reconstruction (TRANS_v3 core feature)
    # =========================================================================

    def linkSpectralCube(self,
                         cube: np.ndarray,
                         independent_var: np.ndarray,
                         independent_var_name: str = "x"):
        """
        Link a spectral cube for spatial-spectral reconstruction.
        Clicking on a position will retrieve the spectrum at that location.

        Parameters:
            cube: 3D array with shape (n_spectral_points, rows, cols)
            independent_var: 1D array (e.g., wavenumber, voltage)
            independent_var_name: Label for independent variable
        """
        if cube.ndim != 3:
            raise ValueError(f"Spectral cube must be 3D, got {cube.ndim}D")

        self._spectral_cube = cube
        self._independent_var = independent_var
        self._independent_var_name = independent_var_name
        logger.info(f"Linked spectral cube: {cube.shape}")

    def unlinkSpectralCube(self):
        """Remove spectral cube link"""
        self._spectral_cube = None
        self._independent_var = None

    @Slot(int, int, result='QVariantMap')
    def getSpectrumAt(self, row: int, col: int) -> Dict:
        """
        Get spectrum at a specific spatial position.
        This is the core spatial-spectral reconstruction feature from TRANS_v3.

        Parameters:
            row: Row index
            col: Column index

        Returns:
            Dict with 'x' (independent var), 'y' (values), 'name' labels
        """
        if self._spectral_cube is None:
            return {'error': 'No spectral data linked'}

        n_pts, n_rows, n_cols = self._spectral_cube.shape

        if not (0 <= row < n_rows and 0 <= col < n_cols):
            return {'error': f'Position ({row}, {col}) out of bounds'}

        values = self._spectral_cube[:, row, col]

        return {
            'x': self._independent_var.tolist() if self._independent_var is not None else list(range(n_pts)),
            'y': values.tolist(),
            'x_name': self._independent_var_name,
            'y_name': 'Intensity',
            'title': f'Spectrum at ({row}, {col})'
        }

    @Slot(result='QVariantMap')
    def getAverageSpectrumFromSelection(self) -> Dict:
        """
        Get average spectrum from all selected blocks.
        Key feature for discretized spatial averaging.
        """
        if self._spectral_cube is None:
            return {'error': 'No spectral data linked'}

        if not self._selected_blocks:
            return {'error': 'No blocks selected'}

        n_pts = self._spectral_cube.shape[0]
        accumulated = np.zeros(n_pts)
        count = 0

        for row, col in self._selected_blocks:
            if 0 <= row < self._spectral_cube.shape[1] and 0 <= col < self._spectral_cube.shape[2]:
                accumulated += self._spectral_cube[:, row, col]
                count += 1

        if count == 0:
            return {'error': 'No valid blocks in selection'}

        averaged = accumulated / count

        return {
            'x': self._independent_var.tolist() if self._independent_var is not None else list(range(n_pts)),
            'y': averaged.tolist(),
            'x_name': self._independent_var_name,
            'y_name': 'Intensity',
            'title': f'Average spectrum ({count} blocks)',
            'block_count': count
        }

    @Property(bool)
    def hasSpectralLink(self) -> bool:
        """Check if spectral data is linked"""
        return self._spectral_cube is not None

    @Property(int)
    def spectralPoints(self) -> int:
        """Get number of spectral points"""
        return self._spectral_cube.shape[0] if self._spectral_cube is not None else 0

    # =========================================================================
    # Data management (called from Python backend)
    # =========================================================================

    def setMapData(self, data: np.ndarray, colormap: str = None):
        """
        Set the map data to display.

        Parameters:
            data: 2D numpy array
            colormap: Optional colormap name
        """
        if data.ndim != 2:
            raise ValueError(f"Map data must be 2D, got {data.ndim}D")

        self._map_data = data.astype(np.float64)
        if colormap:
            self._colormap = colormap

        self._needs_redraw = True
        self._data_to_pixel = None  # Invalidate transform cache
        self.mapUpdated.emit()
        self.update()

    @Slot(float, float, str)
    def setPhysicalExtent(self, x_size: float, y_size: float, unit: str = "nm"):
        """Label the map axes in physical units instead of pixel indices.

        ``x_size``/``y_size`` are the scan-window dimensions in ``unit`` (the
        full width/height the data spans). Passing a non-positive size clears
        the physical extent and reverts to pixel-index axes.
        """
        if x_size and y_size and x_size > 0 and y_size > 0:
            self._phys_extent = (float(x_size), float(y_size), unit or "nm")
        else:
            self._phys_extent = None
        self._needs_redraw = True
        self.update()

    @Slot('QVariantMap')
    def setAxisMetadata(self, meta):
        """Describe the axes for the cursor read-out.

        ``{'x_size', 'x_unit', 'x_offset', 'y_size', 'y_unit', 'y_offset'}``,
        any subset. This exists because the two axes of a kymograph are
        different quantities — position across, bias up — which
        :meth:`setPhysicalExtent` cannot express (it carries one unit for
        both, and the tick labels still use it). Pass an empty map to clear.
        """
        if not meta:
            self._axis_meta = None
        else:
            self._axis_meta = {k: meta.get(k) for k in
                               ('x_size', 'x_unit', 'x_offset',
                                'y_size', 'y_unit', 'y_offset')}
        self._needs_redraw = True
        self.update()

    @Slot(int, int, result='QVariantMap')
    def physicalAt(self, row: int, col: int):
        """Where a pixel sits on the physical axes.

        Returns ``{'valid', 'x', 'y', 'unit'}``; ``valid`` is False when the
        map has no physical extent (an uncalibrated import), so callers show
        pixel indices instead of inventing a position. Coordinates are taken
        at the CENTRE of the pixel — a pixel covers a span, and its edge is
        not where the measurement was made.
        """
        empty = {'valid': False, 'x': 0.0, 'y': 0.0,
                 'x_unit': '', 'y_unit': '', 'unit': ''}
        if self._map_data is None:
            return empty
        rows, cols = self._map_data.shape
        if not (0 <= row < rows and 0 <= col < cols):
            return empty

        meta = self._axis_meta
        if meta:
            x_size = float(meta.get('x_size') or cols)
            y_size = float(meta.get('y_size') or rows)
            x_unit = str(meta.get('x_unit') or '')
            y_unit = str(meta.get('y_unit') or '')
            x_offset = float(meta.get('x_offset') or 0.0)
            y_offset = float(meta.get('y_offset') or 0.0)
        elif self._phys_extent is not None:
            x_size, y_size, unit = self._phys_extent
            x_unit = y_unit = unit
            x_offset = y_offset = 0.0
        else:
            return empty

        return {
            'valid': True,
            'x': x_offset + (col + 0.5) * float(x_size) / cols,
            'y': y_offset + (row + 0.5) * float(y_size) / rows,
            'x_unit': x_unit,
            'y_unit': y_unit,
            'unit': x_unit,          # kept for callers that assume one unit
        }

    @Slot()
    def clearPhysicalExtent(self):
        """Revert to pixel-index axes."""
        self._phys_extent = None
        self._needs_redraw = True
        self.update()

    def _physical_pixel_size(self):
        """``(dx, dy, unit)`` per pixel, or ``(None, None, None)``.

        The canvas stores the *total* scan extent for axis labelling; exports
        need it per pixel, so divide by the array shape.
        """
        if self._phys_extent is None or self._map_data is None:
            return (None, None, None)
        x_size, y_size, unit = self._phys_extent
        try:
            rows, cols = self._map_data.shape[:2]
        except Exception:
            return (None, None, None)
        if not rows or not cols:
            return (None, None, None)
        return (x_size / cols, y_size / rows, unit)

    def getMapData(self) -> Optional[np.ndarray]:
        """Get the current map data"""
        return self._map_data

    def getValueAt(self, row: int, col: int) -> float:
        """Get map value at specific position"""
        if self._map_data is None:
            return np.nan
        if 0 <= row < self._map_data.shape[0] and 0 <= col < self._map_data.shape[1]:
            return float(self._map_data[row, col])
        return np.nan

    # =========================================================================
    # Painting
    # =========================================================================

    def paint(self, painter: QPainter):
        """Phase 7.4 dispatch: native QPainter path by default; opt
        back into matplotlib via ``TRANS_FAST_MAP_RENDER=0``."""
        if self._use_fast_render:
            self._renderNative(painter)
            return

        if self._needs_redraw:
            self._renderMatplotlib()
            self._needs_redraw = False

        if self._cached_image is not None:
            target_rect = QRectF(0, 0, self.width(), self.height())
            painter.drawImage(target_rect, self._cached_image)
            self._drawOverlays(painter)

    # =====================================================================
    # Phase 7.4 — native (matplotlib-free) interactive renderer
    # =====================================================================

    def _renderNative(self, painter: QPainter) -> None:
        """Paint the map with QPainter primitives.

        Pipeline:

        1. Background fill + axes-rect from margin constants.
        2. vmin/vmax from explicit ``_vmin`` / ``_vmax`` or the
           percentile clip.
        3. (Optional) ``downsample_image`` when the source map is
           much larger than the on-screen rect — keeps the LUT
           lookup off the critical path on 4k+ maps.
        4. ``apply_levels_and_lut`` → uint8 RGB → QImage →
           ``painter.drawImage`` filling the axes rect.
        5. QPainter axes frame + tick marks + tick labels via the
           Phase 1 / Phase 4 tick algorithm.
        6. ``_data_to_pixel`` is populated so existing overlays
           (crosshair, profile line, grid overlay, selected blocks,
           ROIs) still render correctly via ``_drawOverlays``.
        """
        w, h = int(self.width()), int(self.height())
        if w <= 0 or h <= 0:
            return

        painter.fillRect(QRectF(0, 0, w, h), self._NATIVE_BG_COLOR)
        if self._map_data is None:
            return

        ax_left = self._NATIVE_AX_MARGIN_LEFT
        ax_top = self._NATIVE_AX_MARGIN_TOP
        ax_right = w - self._NATIVE_AX_MARGIN_RIGHT
        ax_bottom = h - self._NATIVE_AX_MARGIN_BOTTOM
        if ax_right <= ax_left or ax_bottom <= ax_top:
            return
        ax_rect = QRectF(
            ax_left, ax_top, ax_right - ax_left, ax_bottom - ax_top,
        )

        # Levels: explicit takes priority, else percentile clip.
        lo, hi = self._compute_display_levels()

        # Downsample large maps so the LUT lookup runs over the on-
        # screen pixel budget, not the full source array. The factor
        # 2× headroom keeps Qt's bilinear smoothing meaningful when
        # the user zooms in slightly past the native axes rect.
        src = self._map_data
        target = (
            max(1, int(ax_rect.width()) * 2),
            max(1, int(ax_rect.height()) * 2),
        )
        if src.shape[0] > target[1] * 2 or src.shape[1] > target[0] * 2:
            src = downsample_image(src, target_size=target, mode="mean")

        # Levels + LUT.
        cmap = (self._colormap or "viridis").lower()
        rgb = apply_levels_and_lut(
            np.asarray(src), levels=(lo, hi), lut=get_lut(cmap),
        )
        qimg = QImage(
            rgb.data, rgb.shape[1], rgb.shape[0],
            rgb.shape[1] * 3, QImage.Format_RGB888,
        ).copy()

        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setClipRect(ax_rect)
        painter.drawImage(ax_rect, qimg)
        painter.restore()

        # Axes frame + ticks. Map axes are pixel indices, linear.
        self._native_draw_axes(painter, ax_rect)

        # Update the transform cache used by every existing overlay.
        self._data_to_pixel = {
            'ax_left': ax_left,
            'ax_right': ax_right,
            'ax_top': ax_top,
            'ax_bottom': ax_bottom,
            'data_rows': self._map_data.shape[0],
            'data_cols': self._map_data.shape[1],
        }

        # Existing overlays — selected blocks, profile lines, ROIs,
        # the rubber-band, crosshair, etc.
        self._drawOverlays(painter)

    def _native_draw_axes(
        self,
        painter: QPainter,
        ax_rect: QRectF,
    ) -> None:
        """Frame + major / minor ticks + tick labels.

        Labels are physical coordinates (with a unit title) when a physical
        extent has been set via :meth:`setPhysicalExtent`; otherwise they are
        integer column / row pixel indices (the historical default). Linear
        either way, so no log mode.
        """
        if self._map_data is None:
            return
        rows, cols = self._map_data.shape

        # Axis domains: physical size spanning the scan window, or pixel counts.
        phys = self._phys_extent
        x_max = phys[0] if phys else float(cols)
        y_max = phys[1] if phys else float(rows)
        unit = phys[2] if phys else None
        if x_max <= 0 or y_max <= 0:
            phys, x_max, y_max, unit = None, float(cols), float(rows), None

        pen_axis = QPen(self._NATIVE_AXIS_COLOR)
        pen_axis.setWidthF(1.0)
        painter.setPen(pen_axis)
        painter.drawRect(ax_rect)

        x_levels = tick_values(0.0, x_max, ax_rect.width())
        y_levels = tick_values(0.0, y_max, ax_rect.height())

        x_major_spacing, x_majors = (
            x_levels[0] if x_levels else (1.0, [])
        )
        y_major_spacing, y_majors = (
            y_levels[0] if y_levels else (1.0, [])
        )

        x_labels, _ = (
            format_tick_strings(x_majors, spacing=x_major_spacing, log=False)
            if x_majors else ([], None)
        )
        y_labels, _ = (
            format_tick_strings(y_majors, spacing=y_major_spacing, log=False)
            if y_majors else ([], None)
        )

        tick_pen = QPen(self._NATIVE_TICK_COLOR)
        tick_pen.setWidthF(1.0)
        painter.setPen(tick_pen)
        tick_len = 4.0
        ax_w = ax_rect.width()
        ax_h = ax_rect.height()
        for x in x_majors:
            if 0.0 <= x <= x_max:
                px = ax_rect.left() + (x / x_max) * ax_w
                painter.drawLine(
                    QPointF(px, ax_rect.bottom()),
                    QPointF(px, ax_rect.bottom() + tick_len),
                )
        for y in y_majors:
            if 0.0 <= y <= y_max:
                py = ax_rect.top() + (y / y_max) * ax_h
                painter.drawLine(
                    QPointF(ax_rect.left() - tick_len, py),
                    QPointF(ax_rect.left(), py),
                )

        painter.setPen(self._NATIVE_LABEL_COLOR)
        f = painter.font(); f.setPointSize(8); f.setBold(False)
        painter.setFont(f)
        fm = QFontMetricsF(painter.font())
        for x, label in zip(x_majors, x_labels):
            if 0.0 <= x <= x_max:
                px = ax_rect.left() + (x / x_max) * ax_w
                tw = fm.horizontalAdvance(label)
                painter.drawText(
                    QPointF(
                        px - tw / 2,
                        ax_rect.bottom() + tick_len + fm.ascent() + 2,
                    ),
                    label,
                )
        for y, label in zip(y_majors, y_labels):
            if 0.0 <= y <= y_max:
                py = ax_rect.top() + (y / y_max) * ax_h
                tw = fm.horizontalAdvance(label)
                painter.drawText(
                    QPointF(
                        ax_rect.left() - tick_len - tw - 4,
                        py + fm.ascent() / 2 - 1,
                    ),
                    label,
                )

        # Axis unit titles (only when showing physical coordinates).
        if unit:
            painter.setPen(self._NATIVE_LABEL_COLOR)
            title = f"x ({unit})"
            tw = fm.horizontalAdvance(title)
            painter.drawText(
                QPointF(ax_rect.center().x() - tw / 2,
                        ax_rect.bottom() + tick_len + 2 * fm.height() + 2),
                title,
            )
            painter.save()
            painter.translate(ax_rect.left() - tick_len - fm.height() * 2.4,
                              ax_rect.center().y())
            painter.rotate(-90)
            ytitle = f"y ({unit})"
            painter.drawText(QPointF(-fm.horizontalAdvance(ytitle) / 2, 0),
                             ytitle)
            painter.restore()

    def _renderMatplotlib(self):
        """Render matplotlib figure to cached QImage"""
        if self._map_data is None:
            self._cached_image = None
            return

        # Resize figure to match item size
        w, h = int(self.width()), int(self.height())
        if w <= 0 or h <= 0:
            return

        self.figure.set_size_inches(w / self._dpi, h / self._dpi)

        # Clear and redraw
        self.axes.clear()
        self._applyAxesStyle()

        # Compute value range
        if self._vmin is not None and self._vmax is not None:
            vmin, vmax = self._vmin, self._vmax
        else:
            vmin = np.nanpercentile(self._map_data, self._percentile_clip[0])
            vmax = np.nanpercentile(self._map_data, self._percentile_clip[1])

        # Physical extent → label axes in real units; else pixel indices.
        phys = self._phys_extent
        extent = None
        if phys and phys[0] > 0 and phys[1] > 0:
            extent = [0.0, phys[0], phys[1], 0.0]  # origin='upper' → y flipped

        # Display image
        self._image_handle = self.axes.imshow(
            self._map_data,
            cmap=self._colormap,
            vmin=vmin,
            vmax=vmax,
            aspect='equal',
            origin='upper',
            interpolation='nearest',
            extent=extent,
        )

        # Style axes. ``imshow`` can reset the spines, so re-apply after it.
        self._applyAxesStyle()

        if extent is not None:
            # The unit titles used to be forced to the tick grey while the
            # native path drew the same strings in the label colour. They are
            # text, so they take the label colour on both paths now.
            self.axes.set_xlabel(f"x ({phys[2]})", color=self._foreground,
                                 fontsize=8)
            self.axes.set_ylabel(f"y ({phys[2]})", color=self._foreground,
                                 fontsize=8)

        # Ported pyqtgraph tick layout — keeps axis labelling consistent
        # across the graph/profile/map canvases. Linear axes, so log is off.
        # The size arguments are the on-screen axis lengths (they set tick
        # *density*); the tick *domain* comes from the axes limits, which
        # ``extent`` above has already switched to physical units.
        apply_pyqtgraph_ticks(
            self.axes,
            x_size_px=float(w),
            y_size_px=float(h),
            log_x=False, log_y=False,
        )

        # Tight layout
        self.figure.tight_layout(pad=0.5)

        # Render to buffer
        self.canvas.draw()
        buf = self.canvas.buffer_rgba()
        w_fig, h_fig = self.canvas.get_width_height()

        # Convert to QImage
        self._cached_image = QImage(
            buf, w_fig, h_fig, QImage.Format_RGBA8888
        ).copy()  # Make a copy since buffer may be reused

        # Update coordinate transform
        self._updateCoordinateTransform()

    def _updateCoordinateTransform(self):
        """Update pixel-to-data coordinate transformation"""
        if self._map_data is None or self._image_handle is None:
            self._data_to_pixel = None
            return

        # Get axes position in figure coordinates
        bbox = self.axes.get_position()
        fig_w, fig_h = self.canvas.get_width_height()

        # Axes bounds in pixels
        ax_left = bbox.x0 * fig_w
        ax_right = bbox.x1 * fig_w
        ax_top = (1 - bbox.y1) * fig_h
        ax_bottom = (1 - bbox.y0) * fig_h

        self._data_to_pixel = {
            'ax_left': ax_left,
            'ax_right': ax_right,
            'ax_top': ax_top,
            'ax_bottom': ax_bottom,
            'data_rows': self._map_data.shape[0],
            'data_cols': self._map_data.shape[1]
        }

    def _pixelToData(self, x: float, y: float) -> Tuple[int, int]:
        """Convert pixel coordinates to data row, col"""
        if self._data_to_pixel is None:
            return -1, -1

        d = self._data_to_pixel
        ax_width = d['ax_right'] - d['ax_left']
        ax_height = d['ax_bottom'] - d['ax_top']

        # Normalize to [0, 1] within axes
        norm_x = (x - d['ax_left']) / ax_width
        norm_y = (y - d['ax_top']) / ax_height

        # Convert to data coordinates
        col = int(norm_x * d['data_cols'])
        row = int(norm_y * d['data_rows'])

        # Clamp to valid range
        row = max(0, min(row, d['data_rows'] - 1))
        col = max(0, min(col, d['data_cols'] - 1))

        return row, col

    def _dataToPixel(self, row: int, col: int) -> Tuple[float, float]:
        """Convert data row, col to pixel coordinates"""
        if self._data_to_pixel is None:
            return 0, 0

        d = self._data_to_pixel
        ax_width = d['ax_right'] - d['ax_left']
        ax_height = d['ax_bottom'] - d['ax_top']

        x = d['ax_left'] + (col + 0.5) / d['data_cols'] * ax_width
        y = d['ax_top'] + (row + 0.5) / d['data_rows'] * ax_height

        return x, y

    def _pixel_to_axesfrac(self, x: float, y: float):
        """Screen pixel → fraction within the image axes rect.

        Not clamped, so points drawn outside the image keep their true
        position. Returns None when the axes geometry is unknown.
        """
        d = self._data_to_pixel
        if d is None:
            return None
        aw = d['ax_right'] - d['ax_left']
        ah = d['ax_bottom'] - d['ax_top']
        if aw == 0 or ah == 0:
            return None
        return ((x - d['ax_left']) / aw, (y - d['ax_top']) / ah)

    def _axesfrac_to_pixel(self, nx: float, ny: float):
        """Axes fraction → screen pixel using the current axes rect."""
        d = self._data_to_pixel
        if d is None:
            return None
        aw = d['ax_right'] - d['ax_left']
        ah = d['ax_bottom'] - d['ax_top']
        return (d['ax_left'] + nx * aw, d['ax_top'] + ny * ah)

    def _drawOverlays(self, painter: QPainter):
        """Draw interactive overlay elements"""
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Draw STS grid region rectangle overlay
        if self._sts_region_rect and self._data_to_pixel is not None:
            d = self._data_to_pixel
            ax_width = d['ax_right'] - d['ax_left']
            ax_height = d['ax_bottom'] - d['ax_top']
            x0, y0, x1, y1 = self._sts_region_rect

            # Convert fractional coords to pixel coords
            px_left = d['ax_left'] + min(x0, x1) * ax_width
            px_right = d['ax_left'] + max(x0, x1) * ax_width
            px_top = d['ax_top'] + min(y0, y1) * ax_height
            px_bottom = d['ax_top'] + max(y0, y1) * ax_height

            # Semi-transparent red fill
            painter.setBrush(QColor(245, 169, 184, 50))
            pen = QPen(QColor(245, 169, 184, 200))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(
                int(px_left), int(px_top),
                int(px_right - px_left), int(px_bottom - px_top)
            )

        # Outline each line scan first, so the dots sit on top of it: a wide
        # translucent band along the acquisition path, a thin bright edge, and
        # a tag naming the line ("line1 · 57pts ×3 · pt20→pt76").
        if (self._show_sts_markers and self._sts_lines
                and self._data_to_pixel is not None):
            # A tag must clear the points it names, their index labels, and
            # any tag already placed — two acquisitions can share one path,
            # so their tags would otherwise land on each other.
            placed_chips = list(self._sts_marker_obstacles(painter.fontMetrics()))
            for ln in self._sts_lines:
                pts = [self._dataToPixel(r, c) for r, c in ln['path']]
                poly = QPolygonF([QPointF(x, y) for x, y in pts])

                band = QPen(_alpha(self._roi_colour, 70))
                band.setWidth(14)
                band.setCapStyle(Qt.RoundCap)
                band.setJoinStyle(Qt.RoundJoin)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(band)
                painter.drawPolyline(poly)

                edge = QPen(_alpha(self._roi_colour, 220))
                edge.setWidth(2)
                edge.setCapStyle(Qt.RoundCap)
                painter.setPen(edge)
                painter.drawPolyline(poly)

                # End caps mark where the line starts and stops.
                for x, y in (pts[0], pts[-1]):
                    painter.drawEllipse(QRectF(x - 7, y - 7, 14, 14))

                label = ln.get('label', '')
                if not label:
                    continue
                # Tag beside the start of the line, in a chip so it stays
                # readable over bright topography.
                font = painter.font()
                font.setBold(True)
                painter.setFont(font)
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)
                th = fm.height()
                pad = 4
                chip = self._place_chip(
                    self._chip_candidates(pts, tw + 2 * pad, th + 2 * pad,
                                          self.width(), self.height()),
                    placed_chips)
                placed_chips.append(chip)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(_alpha(self._chip_bg, 225)))
                painter.drawRoundedRect(chip, 4, 4)
                painter.setPen(QPen(self._chip_ink))
                painter.drawText(chip, Qt.AlignCenter, label)

        # Draw STS point markers — where spectra were taken on this scan image.
        # Selected dots (whose spectrum is on the plot) are drawn bigger with a
        # white ring + cyan fill so the click clearly registered.
        if (self._show_sts_markers and self._sts_markers
                and self._data_to_pixel is not None):
            ring = QPen(QColor(255, 255, 0, 230))       # yellow ring (idle)
            ring.setWidth(2)
            sel_ring = QPen(QColor(255, 255, 255, 255))  # white ring (selected)
            sel_ring.setWidth(3)
            hover_pos = None   # (x, y, label) of the dot under the cursor
            for mk in self._sts_markers:
                x, y = self._dataToPixel(mk['row'], mk['col'])
                idx = mk.get('index', -1)
                selected = idx in self._sts_selected
                hovered = idx == self._hover_sts
                r = 8.0 if hovered else (7.0 if selected else 5.0)
                painter.setPen(sel_ring if (selected or hovered) else ring)
                painter.setBrush(QBrush(QColor(0, 200, 255, 210) if selected
                                        else QColor(255, 0, 0, 160)))
                painter.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
                label = mk.get('label', '')
                if hovered:
                    hover_pos = (x, y, label)
                elif label:
                    painter.setPen(QPen(QColor(255, 255, 0, 255)))
                    painter.drawText(int(x + r + 2), int(y - r - 2), label)

            # Hover popup drawn last so it sits above every dot: a filled chip
            # with the point index near the hovered dot.
            if hover_pos is not None:
                hx, hy, hlabel = hover_pos
                text = "#" + (hlabel if hlabel else str(self._hover_sts))
                font = painter.font()
                font.setBold(True)
                font.setPointSize(max(9, font.pointSize()))
                painter.setFont(font)
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(text)
                th = fm.height()
                pad = 4
                bx = hx + 10
                by = hy - th - 10
                # Keep the chip inside the canvas.
                if bx + tw + 2 * pad > self.width():
                    bx = hx - 10 - tw - 2 * pad
                if by < 0:
                    by = hy + 12
                chip = QRectF(bx, by, tw + 2 * pad, th + 2 * pad)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(_alpha(self._chip_bg, 235)))
                painter.drawRoundedRect(chip, 4, 4)
                painter.setPen(QPen(self._chip_ink))
                painter.drawText(chip, Qt.AlignCenter, text)

        # Draw grid overlay for discretization
        if self._show_grid_overlay and self._data_to_pixel is not None and self._map_data is not None:
            d = self._data_to_pixel
            ax_width = d['ax_right'] - d['ax_left']
            ax_height = d['ax_bottom'] - d['ax_top']
            data_rows, data_cols = d['data_rows'], d['data_cols']

            # Draw semi-transparent white grid lines
            pen = QPen(QColor(255, 255, 255, 100))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            # Vertical grid lines
            for gc in range(1, (data_cols // self._grid_block_h) + 1):
                px = gc * self._grid_block_h
                if px < data_cols:
                    x = d['ax_left'] + (px / data_cols) * ax_width
                    painter.drawLine(int(x), int(d['ax_top']), int(x), int(d['ax_bottom']))

            # Horizontal grid lines
            for gr in range(1, (data_rows // self._grid_block_v) + 1):
                py = gr * self._grid_block_v
                if py < data_rows:
                    y = d['ax_top'] + (py / data_rows) * ax_height
                    painter.drawLine(int(d['ax_left']), int(y), int(d['ax_right']), int(y))

            # Draw hover highlight on grid block
            if self._hover_block is not None and self._current_tool == MapTool.BLOCK_SELECT:
                hr, hc = self._hover_block
                cell_w = (self._grid_block_h / data_cols) * ax_width
                cell_h = (self._grid_block_v / data_rows) * ax_height
                rect_x = d['ax_left'] + hc * self._grid_block_h / data_cols * ax_width
                rect_y = d['ax_top'] + hr * self._grid_block_v / data_rows * ax_height
                painter.setPen(QPen(QColor(245, 169, 184, 180)))  # Pink hover
                painter.setBrush(QBrush(QColor(245, 169, 184, 50)))
                painter.drawRect(QRectF(rect_x, rect_y, cell_w, cell_h))

        # Draw selected blocks (TRANS_v3 style blue highlight)
        if self._selected_blocks and self._data_to_pixel is not None:
            pen = QPen(QColor(31, 119, 180, 200))  # Blue from TRANS_v3 (#1f77b4)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(31, 119, 180, 80)))

            d = self._data_to_pixel
            ax_width = d['ax_right'] - d['ax_left']
            ax_height = d['ax_bottom'] - d['ax_top']

            if self._show_grid_overlay and (self._grid_block_h > 1 or self._grid_block_v > 1):
                # Grid-snapped block selection
                cell_w = (self._grid_block_h / d['data_cols']) * ax_width
                cell_h = (self._grid_block_v / d['data_rows']) * ax_height
                for row, col in self._selected_blocks:
                    rect_x = d['ax_left'] + col * self._grid_block_h / d['data_cols'] * ax_width
                    rect_y = d['ax_top'] + row * self._grid_block_v / d['data_rows'] * ax_height
                    painter.drawRect(QRectF(rect_x, rect_y, cell_w, cell_h))
            else:
                # Per-pixel block selection
                cell_w = ax_width / d['data_cols']
                cell_h = ax_height / d['data_rows']
                for row, col in self._selected_blocks:
                    rect_x = d['ax_left'] + col * cell_w
                    rect_y = d['ax_top'] + row * cell_h
                    painter.drawRect(QRectF(rect_x, rect_y, cell_w, cell_h))

        # Draw crosshair. Show it whenever the crosshair tool is active
        # (it tracks the hover position in hoverMoveEvent) — not only when
        # the explicit ``_show_crosshair`` flag is set. Without this, the
        # CROSSHAIR tool blanked the OS cursor (Qt.BlankCursor) but never
        # drew its replacement, so the cursor just vanished.
        if (
            (self._show_crosshair or self._current_tool == MapTool.CROSSHAIR)
            and self._crosshair_pos is not None
        ):
            row, col = self._crosshair_pos
            x, y = self._dataToPixel(row, col)

            pen = QPen(QColor(255, 255, 0, 180))
            pen.setWidth(1)
            painter.setPen(pen)

            # Vertical line
            painter.drawLine(int(x), 0, int(x), int(self.height()))
            # Horizontal line
            painter.drawLine(0, int(y), int(self.width()), int(y))

        # Draw profile line — stored in axes fractions, converted to pixels
        # against the CURRENT axes rect so it stays glued to the data on resize.
        if self._profile_line is not None and self._data_to_pixel is not None:
            (nx0, ny0), (nx1, ny1) = self._profile_line
            p0 = self._axesfrac_to_pixel(nx0, ny0)
            p1 = self._axesfrac_to_pixel(nx1, ny1)
            if p0 is not None and p1 is not None:
                start = QPointF(*p0)
                end = QPointF(*p1)
                pen = QPen(QColor(255, 100, 100, 200))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(start, end)

                # Draw endpoints
                painter.setBrush(QBrush(QColor(255, 100, 100)))
                painter.drawEllipse(start, 4, 4)
                painter.drawEllipse(end, 4, 4)

        # Draw selection rectangle
        if self._selection_rect is not None:
            pen = QPen(QColor(100, 200, 255, 200))
            pen.setWidth(2)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(100, 200, 255, 50)))
            painter.drawRect(self._selection_rect)

        # Phase 6.4 — RectROI overlay items.
        if self._rect_rois and self._data_to_pixel is not None:
            d = self._data_to_pixel
            ax_rect = QRectF(
                d['ax_left'], d['ax_top'],
                d['ax_right'] - d['ax_left'],
                d['ax_bottom'] - d['ax_top'],
            )
            data_to_pixel = self._roi_data_to_pixel()
            active_id = (
                self._roi_drag["roi_id"]
                if self._roi_drag is not None else None
            )
            for roi in self._rect_rois:
                hover = (roi.roi_id == active_id)
                roi.render(
                    painter, ax_rect, data_to_pixel, hover=hover,
                )

        # Draw drag preview for current tool
        if self._is_dragging and self._drag_start and self._drag_current:
            if self._current_tool == MapTool.LINE_PROFILE:
                pen = QPen(QColor(255, 200, 100, 200))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(self._drag_start, self._drag_current)
            elif self._current_tool in (MapTool.RECT_SELECT, MapTool.ZOOM_RECT):
                rect = QRectF(self._drag_start, self._drag_current).normalized()
                pen = QPen(QColor(100, 255, 100, 200))
                pen.setWidth(1)
                pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(QBrush(QColor(100, 255, 100, 30)))
                painter.drawRect(rect)

    def _updateCursor(self):
        """Update cursor based on current tool"""
        cursor_map = {
            MapTool.POINTER: Qt.ArrowCursor,
            MapTool.ZOOM_RECT: Qt.CrossCursor,
            MapTool.PAN: Qt.OpenHandCursor,
            MapTool.LINE_PROFILE: Qt.CrossCursor,
            MapTool.POINT_INSPECTOR: Qt.CrossCursor,
            MapTool.RECT_SELECT: Qt.CrossCursor,
            MapTool.MEASURE: Qt.CrossCursor,
            MapTool.CROSSHAIR: Qt.BlankCursor,
            MapTool.BLOCK_SELECT: Qt.PointingHandCursor,
        }
        self.setCursor(QCursor(cursor_map.get(self._current_tool, Qt.ArrowCursor)))

    # =========================================================================
    # Mouse event handling
    # =========================================================================

    def mousePressEvent(self, event):
        """Handle mouse press events"""
        if self._map_data is None:
            return

        pos = event.position()
        # Phase 6.4 — RectROI overlays take priority over the
        # tool-driven dispatch below. A press on the body or any
        # corner handle captures the drag; anywhere else falls
        # through to the existing tool.
        if self._rect_rois and self._data_to_pixel is not None:
            d = self._data_to_pixel
            ax_rect = QRectF(
                d['ax_left'], d['ax_top'],
                d['ax_right'] - d['ax_left'],
                d['ax_bottom'] - d['ax_top'],
            )
            hit_result = self._find_roi_at(pos.x(), pos.y(), ax_rect)
            if hit_result is not None:
                roi, hit = hit_result
                col_data, row_data = self._roi_pixel_to_data(
                    pos.x(), pos.y(),
                )
                press_state = roi.begin_drag(col_data, row_data, hit)
                self._roi_drag = {
                    "roi_id": roi.roi_id,
                    "item": roi,
                    "press": press_state,
                }
                self._emit_roi_change(roi, finished=False)
                self.update()
                return

        # STS marker dots take priority over the tool dispatch: a click within
        # a few px of a dot plots that point's spectrum. Only active with the
        # POINTER tool so the dots don't intercept line-profile / block / etc.
        if (self._current_tool == MapTool.POINTER
                and self._show_sts_markers and self._sts_markers
                and self._data_to_pixel is not None):
            hit = self._sts_marker_at(pos.x(), pos.y())
            if hit is not None:
                self.stsMarkerClicked.emit(int(hit.get('index', -1)))
                return

        self._drag_start = pos
        self._is_dragging = True

        row, col = self._pixelToData(pos.x(), pos.y())
        value = self.getValueAt(row, col)

        if self._current_tool == MapTool.POINT_INSPECTOR:
            self.pointClicked.emit(pos.x(), pos.y(), row, col, value)
            self.spectralDataRequested.emit(row, col)
            self._crosshair_pos = (row, col)
            self.update()

        elif self._current_tool == MapTool.CROSSHAIR:
            self._crosshair_pos = (row, col)
            self.pointClicked.emit(pos.x(), pos.y(), row, col, value)
            self.update()

        elif self._current_tool == MapTool.BLOCK_SELECT:
            # TRANS_v3 style block selection - toggle on click
            # Snap to grid if grid overlay is active
            if self._show_grid_overlay and (self._grid_block_h > 1 or self._grid_block_v > 1):
                grid_row, grid_col = self._pixelToGridBlock(pos.x(), pos.y())
                self.toggleBlockSelection(grid_row, grid_col)
            else:
                self.toggleBlockSelection(row, col)
            # Also emit point clicked for spectrum display
            self.pointClicked.emit(pos.x(), pos.y(), row, col, value)
            self.spectralDataRequested.emit(row, col)

        elif self._current_tool == MapTool.POINTER:
            # Default pointer: emit click and show spectrum
            self.pointClicked.emit(pos.x(), pos.y(), row, col, value)
            self.spectralDataRequested.emit(row, col)

    def mouseMoveEvent(self, event):
        """Handle mouse move events"""
        if self._map_data is None:
            return

        pos = event.position()

        # Phase 6.4 — ROI drag short-circuits the tool-driven move
        # path (no cursor read-out, no drag-preview update).
        if self._roi_drag is not None:
            roi = self._roi_drag["item"]
            press = self._roi_drag["press"]
            col_data, row_data = self._roi_pixel_to_data(
                pos.x(), pos.y(),
            )
            if roi.update_drag(col_data, row_data, press):
                self._emit_roi_change(roi, finished=False)
                self.update()
            return

        row, col = self._pixelToData(pos.x(), pos.y())
        value = self.getValueAt(row, col)

        # Emit cursor position
        self.cursorMoved.emit(pos.x(), pos.y(), row, col, value)

        if self._is_dragging:
            self._drag_current = pos

            if self._current_tool == MapTool.CROSSHAIR:
                self._crosshair_pos = (row, col)
                self.pointClicked.emit(pos.x(), pos.y(), row, col, value)

            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release events"""
        # Phase 6.4 — ROI drag finalisation. Done before the existing
        # ``_is_dragging`` check because an ROI press doesn't flip
        # ``_is_dragging`` true.
        if self._roi_drag is not None:
            roi = self._roi_drag["item"]
            self._emit_roi_change(roi, finished=True)
            self._roi_drag = None
            self.update()
            return

        if not self._is_dragging or self._drag_start is None:
            return

        pos = event.position()
        self._is_dragging = False

        if self._current_tool == MapTool.LINE_PROFILE:
            # Store the line in axes fractions (resize-safe) and emit the
            # endpoints in DATA coords — computed against the real axes rect,
            # not the whole widget — so the extracted profile matches the line.
            f0 = self._pixel_to_axesfrac(self._drag_start.x(), self._drag_start.y())
            f1 = self._pixel_to_axesfrac(pos.x(), pos.y())
            self._profile_line = (f0, f1) if (f0 is not None and f1 is not None) else None
            r0, c0 = self._pixelToData(self._drag_start.x(), self._drag_start.y())
            r1, c1 = self._pixelToData(pos.x(), pos.y())
            self.profileDrawn.emit(r0, c0, r1, c1)

        elif self._current_tool in (MapTool.RECT_SELECT, MapTool.ZOOM_RECT):
            rect = QRectF(self._drag_start, pos).normalized()
            if self._current_tool == MapTool.RECT_SELECT:
                self._selection_rect = rect
            self.regionSelected.emit(rect.x(), rect.y(),
                                    rect.x() + rect.width(),
                                    rect.y() + rect.height())

        self._drag_start = None
        self._drag_current = None
        self.update()

    def hoverMoveEvent(self, event):
        """Handle hover move events (when not pressing)"""
        if self._map_data is None:
            return

        pos = event.position()
        row, col = self._pixelToData(pos.x(), pos.y())
        value = self.getValueAt(row, col)

        self.cursorMoved.emit(pos.x(), pos.y(), row, col, value)

        # STS-dot hover popup — only with the POINTER tool, matching the click
        # gate. Shows the dot's point index so the user knows which one they'll
        # click even in dense line scans.
        if (self._current_tool == MapTool.POINTER
                and self._show_sts_markers and self._sts_markers
                and self._data_to_pixel is not None):
            hit = self._sts_marker_at(pos.x(), pos.y())
            new_hover = int(hit['index']) if hit is not None else None
            if new_hover != self._hover_sts:
                self._hover_sts = new_hover
                self.setCursor(QCursor(
                    Qt.PointingHandCursor if hit is not None else Qt.ArrowCursor))
                self.update()
        elif self._hover_sts is not None:
            self._hover_sts = None
            self.update()

        if self._current_tool == MapTool.CROSSHAIR:
            self._crosshair_pos = (row, col)
            self.update()

        # Track hover block for grid overlay highlight
        if self._show_grid_overlay and self._current_tool == MapTool.BLOCK_SELECT:
            new_hover = self._pixelToGridBlock(pos.x(), pos.y())
            if new_hover != self._hover_block:
                self._hover_block = new_hover
                self.update()

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming"""
        # TODO: Implement zoom
        pass

    # =========================================================================
    # Geometry change handling
    # =========================================================================

    def geometryChange(self, newGeometry, oldGeometry):
        """Handle resize with debouncing — scale cached image during drag, re-render when done."""
        super().geometryChange(newGeometry, oldGeometry)
        if newGeometry.size() != oldGeometry.size():
            # During resize: just repaint with the existing cached image (scaled by Qt)
            self.update()
            # Restart debounce timer — full re-render happens when resizing stops
            self._resize_timer.start()

    def _onResizeFinished(self):
        """Called after resize stops (debounce). Triggers full matplotlib re-render."""
        self._needs_redraw = True
        self.update()

    # =========================================================================
    # Statistics and Export (for docked viewer)
    # =========================================================================

    @Slot(result='QVariantMap')
    def getStatistics(self) -> Dict:
        """Get statistics of the current map data"""
        if self._map_data is None:
            return {}

        data = self._map_data
        return {
            'min': float(np.nanmin(data)),
            'max': float(np.nanmax(data)),
            'mean': float(np.nanmean(data)),
            'std': float(np.nanstd(data)),
            'median': float(np.nanmedian(data)),
            'rows': data.shape[0],
            'cols': data.shape[1]
        }

    @Slot(float, float)
    def setColorLimits(self, vmin: float, vmax: float):
        """Set color scale limits"""
        self._vmin = vmin
        self._vmax = vmax
        self._needs_redraw = True
        self.update()

    @Slot(str, str, result=bool)
    def exportImage(self, path: str, format: str = 'png') -> bool:
        """Export the current map view as an image"""
        try:
            if self._cached_image is None:
                return False

            # Export matplotlib figure
            self.figure.savefig(
                path,
                dpi=300,
                bbox_inches='tight',
                # The figure's own ground, not a fourth hardcoded one: the
                # export used to come out #0d0d0d while everything on screen
                # was #1a1a1a.
                facecolor=self.figure.get_facecolor(),
                edgecolor='none'
            )
            logger.info(f"Map exported to: {path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting map image: {e}")
            return False

    @Slot(str, result=bool)
    def exportCsv(self, path: str) -> bool:
        """Export the map data as CSV"""
        try:
            if self._map_data is None:
                return False

            import pandas as pd
            df = pd.DataFrame(self._map_data)
            df.to_csv(path, index=False, header=False)
            logger.info(f"Map data exported to CSV: {path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting CSV: {e}")
            return False

    @Slot(str, result=bool)
    def saveMapData(self, path: str) -> bool:
        """Save the current map data to file"""
        try:
            if self._map_data is None:
                return False

            from pathlib import Path
            p = Path(path)
            ext = p.suffix.lower()

            if ext in ['.tif', '.tiff', '.gsf']:
                # Always write BOTH a calibrated TIFF and a .gsf: Gwyddion
                # only reads dimensions from the latter.
                from src.utils.field_export import export_field
                dx, dy, unit = self._physical_pixel_size()
                export_field(p.with_suffix(''), np.asarray(self._map_data),
                             dx=dx, dy=dy, unit=unit, title=p.stem,
                             context="map canvas save")
            elif ext == '.npy':
                np.save(str(p), self._map_data)
            elif ext == '.csv':
                import pandas as pd
                df = pd.DataFrame(self._map_data)
                df.to_csv(str(p), index=False, header=False)
            else:
                # Default to numpy
                np.save(str(p.with_suffix('.npy')), self._map_data)

            logger.info(f"Map data saved to: {path}")
            return True
        except Exception as e:
            logger.error(f"Error saving map data: {e}")
            return False
