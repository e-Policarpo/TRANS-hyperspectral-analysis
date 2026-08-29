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
from src.widgets._pyqtgraph_ports.items.infinite_line import (
    HIT_LINE as IL_HIT_LINE,
    HIT_NONE as IL_HIT_NONE,
    ORIENT_HORIZONTAL as IL_ORIENT_H,
    ORIENT_VERTICAL as IL_ORIENT_V,
    InfiniteLine,
)
from src.widgets._pyqtgraph_ports.items.linear_region import (
    HIT_BODY as LR_HIT_BODY,
    HIT_HANDLE_HI as LR_HIT_HANDLE_HI,
    HIT_HANDLE_LO as LR_HIT_HANDLE_LO,
    HIT_NONE as LR_HIT_NONE,
    LinearRegionItem,
)
from src.widgets._pyqtgraph_ports.items.target_item import (
    HIT_NONE as TI_HIT_NONE,
    HIT_TARGET as TI_HIT_TARGET,
    SYMBOL_CROSSHAIR as TI_SYMBOL_CROSSHAIR,
    SYMBOL_CIRCLE as TI_SYMBOL_CIRCLE,
    TargetItem,
)
from src.widgets._pyqtgraph_ports.legend import (
    HIT_BODY,
    HIT_EYE,
    HIT_NONE,
    LegendBox,
    LegendEntry,
)
from src.widgets._pyqtgraph_ports.mpl_apply import apply_pyqtgraph_ticks
from src.widgets.series_palette import readable_on
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


# =============================================================================
# Theme derivation
#
# QML hands a canvas three colours — the ground, the text and the rules —
# because that is what a colour scheme actually distinguishes. A plot needs
# more roles than three: a title has to read as more emphatic than a tick
# label, and a grid line has to sit *under* the data rather than compete with
# it. Rather than demand eight colours a scheme does not have, the extra roles
# are derived from the three by blending towards the ground (dimmer) or away
# from it (brighter). Deriving rather than hardcoding is what makes the
# hierarchy survive a light scheme: on white, "dimmer" means darker, and a
# fixed #888888 tick would have been the wrong direction.
#
# The twin of this block lives in ``qml_map_canvas``. The two canvases share
# no base class, and thirty lines of colour arithmetic did not justify a third
# module that both would have to import.
# =============================================================================

def _blend(base: QColor, towards: QColor, amount: float) -> QColor:
    """``base`` moved ``amount`` (0..1) of the way towards ``towards``."""
    amount = max(0.0, min(1.0, float(amount)))
    return QColor(
        round(base.red() + (towards.red() - base.red()) * amount),
        round(base.green() + (towards.green() - base.green()) * amount),
        round(base.blue() + (towards.blue() - base.blue()) * amount),
    )


def _with_alpha(colour: QColor, alpha: int) -> QColor:
    """A copy of ``colour`` at ``alpha`` (0-255)."""
    faded = QColor(colour)
    faded.setAlpha(int(alpha))
    return faded


def _contrast_pole(background: QColor) -> QColor:
    """White over a dark ground, black over a light one.

    Relative luminance rather than a mean of the channels: green carries most
    of the perceived brightness, so a mean calls a saturated blue "light".
    """
    luminance = (0.2126 * background.redF()
                 + 0.7152 * background.greenF()
                 + 0.0722 * background.blueF())
    return QColor("#ffffff") if luminance < 0.5 else QColor("#000000")


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
    selectedCurveIdChanged = Signal(int, arguments=['curveId'])
    cursorMoved = Signal(float, float, arguments=['x', 'y'])
    pointClicked = Signal(float, float, arguments=['x', 'y'])
    rangeSelected = Signal(float, float, float, float, arguments=['x1', 'y1', 'x2', 'y2'])
    curveProcessed = Signal(int, str, int, arguments=['curveId', 'operation', 'newCurveId'])
    curvesChanged = Signal()
    scaleChanged = Signal()

    # Phase 6 — interactive overlay items. ``regionId`` is whatever
    # string identifier the caller passed to ``addLinearRegion``.
    overlayRegionChanged = Signal(
        str, float, float,
        arguments=['regionId', 'xLow', 'xHigh'],
    )
    overlayRegionChangeFinished = Signal(
        str, float, float,
        arguments=['regionId', 'xLow', 'xHigh'],
    )
    overlayLineChanged = Signal(
        str, float, arguments=['lineId', 'value'],
    )
    overlayLineChangeFinished = Signal(
        str, float, arguments=['lineId', 'value'],
    )
    overlayTargetChanged = Signal(
        str, float, float,
        arguments=['targetId', 'x', 'y'],
    )
    overlayTargetChangeFinished = Signal(
        str, float, float,
        arguments=['targetId', 'x', 'y'],
    )

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
        # Render through a GPU framebuffer so the painter is scaled by the
        # device pixel ratio (Retina). With the default Image target the paint
        # painter is NOT DPR-scaled on macOS HiDPI, so drawing at logical
        # coordinates landed the whole plot in the top-left quarter of the item
        # while the interaction math used full logical coords — the plot looked
        # "stuck to the top-left" and the cursor/pan didn't track the data. The
        # FBO target gives a logical-coordinate painter (matches QMLImageCanvas).
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
        # Interaction chrome. The default is the rubber band's own former
        # literal, so a canvas nobody binds paints exactly what it used to.
        self._accent: str = "#64c8ff"
        self._recomputeThemeColours()

        # Matplotlib setup
        self._dpi = 100
        self.figure = Figure(facecolor=self._background, dpi=self._dpi)
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
        # Latch so a non-finite view range warns once, not once per frame.
        self._warned_nonfinite_range: bool = False

        # Phase 5 — self-laid-out legend. Owns its own anchor +
        # offset + per-curve visibility set; serialises through
        # ``legendState`` so the graph window save/restore picks it
        # up. Drag state lives on the canvas (legend is just laid
        # out per render); mouse handlers update it via
        # ``shift_offset``.
        self._legend = LegendBox()
        self._legend_drag_active: bool = False
        self._legend_drag_last_px: Optional[Tuple[float, float]] = None

        # Phase 6 — interactive overlay items (LinearRegionItem
        # first; InfiniteLine / TargetItem / RectROI in subsequent
        # sub-commits). Ordering matters: drawn in list order on top
        # of curves, hit-tested in reverse so a newer overlay can
        # cover an older one.
        self._overlay_items: list[LinearRegionItem] = []
        self._infinite_lines: list[InfiniteLine] = []
        self._target_items: list[TargetItem] = []
        self._overlay_drag: Optional[Dict[str, Any]] = None

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
        """Push the derived theme roles onto the matplotlib axes.

        Called after every ``axes.clear()`` in ``_renderForExport`` as well as
        at construction, because clearing an axes drops its styling — which is
        also why a colour change only has to invalidate, not re-render.
        """
        if getattr(self, 'axes', None) is None:
            return
        if getattr(self, 'figure', None) is not None:
            self.figure.set_facecolor(self._background)
        self.axes.set_facecolor(self._background)
        self.axes.tick_params(colors=self._tick_colour.name(), labelsize=9)
        for spine in self.axes.spines.values():
            spine.set_color(self._grid_colour)
        self.axes.xaxis.label.set_color(self._foreground)
        self.axes.yaxis.label.set_color(self._foreground)
        self.axes.title.set_color(self._title_colour.name())

    # =========================================================================
    # Theme (QML-bindable)
    # =========================================================================

    def _recomputeThemeColours(self) -> None:
        """Derive every painted role from the three colours QML supplies.

        The mapping, and why each one is what it is:

        * **background** — the ground, straight from ``backgroundColor``.
        * **axis frame / legend border** — ``gridColor``. The frame is a rule,
          which is what that colour names.
        * **grid lines** — ``gridColor`` at 45% alpha. Majors run across the
          whole plot; at full strength they read as data.
        * **tick marks** — the foreground pulled 40% back towards the ground.
          Ticks are structure, not text, and the numbers next to them have to
          win. 40% is the ratio the hand-picked pair (#cccccc label against a
          #888888 tick on #1a1a1a) used, kept so nothing shifts on the dark
          scheme this replaces.
        * **tick and axis labels** — the foreground exactly. This is the one
          pairing the WCAG guard in ``src/utils/color_contrast.py`` already
          enforces (textMuted on bgDark, 4.5:1 over all 22 schemes), so
          routing label text here inherits a checked contrast rather than
          inventing an unchecked one.
        * **title** — the foreground pushed 55% towards white on a dark ground
          or black on a light one, so it reads brighter than the labels
          without needing a fourth property the scheme would have to supply.
        * **legend ground** — the background lifted 10% towards the foreground
          so the panel separates from the plot, at alpha 230 as before.
        """
        background = QColor(self._background)
        foreground = QColor(self._foreground)
        rules = QColor(self._grid_colour)

        self._tick_colour = _blend(foreground, background, 0.40)
        self._title_colour = _blend(foreground, _contrast_pole(background), 0.55)
        self._legend_bg_colour = _blend(background, foreground, 0.10)

        # The ``_NATIVE_*`` names are class constants on the class and instance
        # attributes here: assigning them shadows the defaults, so the fifteen
        # paint sites that read ``self._NATIVE_...`` keep working untouched and
        # a canvas that never receives a colour still has the old palette.
        self._NATIVE_BG_COLOR = background
        self._NATIVE_AXIS_COLOR = rules
        self._NATIVE_TICK_COLOR = self._tick_colour
        self._NATIVE_LABEL_COLOR = foreground
        self._NATIVE_TITLE_COLOR = self._title_colour
        self._NATIVE_GRID_COLOR = _with_alpha(rules, 115)
        self._NATIVE_LEGEND_BG = _with_alpha(self._legend_bg_colour, 230)
        self._NATIVE_LEGEND_BORDER = rules

        # Interaction chrome. Both were literals tuned for the hardcoded
        # #1a1a1a ground and washed out on the eight light schemes.
        #
        # The crosshair keeps its own hue: it is identity, like a series
        # colour — the yellow dashed line IS the cursor — so it goes through
        # readable_on rather than becoming the accent, and every dark scheme
        # gets it back byte-identical. The selection box has no identity to
        # protect; a selection is the canonical accent-coloured thing, so it
        # follows accentColor. They stay tellable apart by form regardless:
        # the cursor is a dashed rule, the selection a filled rectangle.
        self._cursor_colour = _with_alpha(
            QColor(readable_on(self._CURSOR_HUE, self._background)), 100)
        selection = QColor(readable_on(self._accent, self._background))
        self._selection_edge = _with_alpha(selection, 180)
        self._selection_fill = _with_alpha(selection, 40)

    def _seriesColour(self, colour):
        """A curve colour, adjusted only if it cannot be seen on this ground.

        Series colours are identity — they come from the caller (the QML
        palette, a user's picker, a tool) and this canvas does not choose
        them. But the ground is no longer fixed: it follows the scheme, and
        eight of the twenty-two schemes are near-white, where nine of the ten
        stock hues fall under the 3:1 threshold for a graphical mark. The hue
        is preserved and only the lightness moves, so the identity survives
        and a colour that already reads is returned byte-identical.
        """
        return readable_on(str(colour), self._background)

    def _setThemeColour(self, attribute: str, colour, changed) -> None:
        """Idempotent, garbage-tolerant setter shared by the three roles.

        An empty string is an unresolved QML binding rather than a choice, and
        an unparseable one is a typo; neither should repaint the canvas in a
        half-applied palette, so both leave the current colour alone. The
        comparison is on the canonical ``#rrggbb`` form so ``"#1A1A1A"`` and
        ``"#1a1a1a"`` — or ``"red"`` twice — count as no change.
        """
        text = str(colour or "").strip()
        if not text:
            return
        parsed = QColor(text)
        if not parsed.isValid():
            logger.warning("GraphCanvas: %r is not a colour", text)
            return
        canonical = parsed.name()
        if canonical == QColor(getattr(self, attribute)).name():
            return
        setattr(self, attribute, canonical)
        self._recomputeThemeColours()
        # Both render paths have to follow: ``_renderNative`` reads the
        # ``_NATIVE_*`` attributes on every frame, but the matplotlib figure
        # holds its styling, so push it now — otherwise a PNG export carries
        # the previous scheme's chrome.
        self._setupAxesStyle()
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

    #: The plot ground — the scheme's window background.
    backgroundColor = Property(str, _get_background_colour,
                               _set_background_colour,
                               notify=backgroundColorChanged)
    #: Text: tick labels, axis labels, legend entries; the title and the tick
    #: marks are derived from it.
    foregroundColor = Property(str, _get_foreground_colour,
                               _set_foreground_colour,
                               notify=foregroundColorChanged)
    #: Rules: the axes frame, the grid, the legend border.
    gridColor = Property(str, _get_grid_colour, _set_grid_colour,
                         notify=gridColorChanged)
    #: Interaction chrome: the rubber-band selection box. Not data and not
    #: structure — the colour the app uses to say "you are doing this".
    accentColor = Property(str, _get_accent_colour, _set_accent_colour,
                           notify=accentColorChanged)

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

    def _get_selected_curve_id(self) -> int:
        return self._selected_curve_id if self._selected_curve_id is not None else -1

    def _set_selected_curve_id(self, value: int) -> None:
        """Writable so QML can assign it (e.g. ``onCurveSelected`` handlers)
        without crashing — previously this was read-only with no setter, so
        a QML write triggered a 'NoneType is not callable' metacall error.
        Also notifyable so ``enabled: canvas.selectedCurveId >= 0`` bindings
        actually re-evaluate when the selection changes."""
        new = None if value is None or int(value) < 0 else int(value)
        if new is not None and new not in self._curves:
            new = None
        if new == self._selected_curve_id:
            return
        self._selected_curve_id = new
        self._needs_redraw = True
        self.update()
        self.selectedCurveIdChanged.emit(self._get_selected_curve_id())

    selectedCurveId = Property(
        int, _get_selected_curve_id, _set_selected_curve_id,
        notify=selectedCurveIdChanged,
    )

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
                self.selectedCurveIdChanged.emit(-1)

            self._needs_redraw = True
            self.curvesChanged.emit()
            self.update()
            logger.info(f"Removed curve: {label}")

    @Slot('QVariantList')
    def setCurves(self, curves):
        """Replace every curve in one pass.

        Adding N curves one at a time costs O(N**2): each ``addCurve`` emits
        ``curvesChanged``, and every emission makes QML rebuild the whole
        curve ListView. Windows that are re-populated wholesale (a plot of
        every selected STS point, a tool result) go through here instead, so
        the list is rebuilt once and the canvas repaints once.
        """
        self._curves.clear()
        self._invalidate_all_curve_paths()
        had_selection = self._selected_curve_id is not None
        self._selected_curve_id = None
        self._curve_counter = 0

        self._build_curves(curves)

        self._needs_redraw = True
        self.curvesChanged.emit()
        self.curveSelected.emit(-1)
        if had_selection:
            self.selectedCurveIdChanged.emit(-1)
        self.update()
        logger.info("Set %d curves in one pass", len(self._curves))

    @Slot('QVariantList')
    def appendCurves(self, curves):
        """Add several curves in one pass, keeping the existing ones.

        Same reason as :meth:`setCurves`: one ``curvesChanged``, one repaint.
        """
        added = self._build_curves(curves)
        if not added:
            return
        self._needs_redraw = True
        self.curvesChanged.emit()
        self.update()

    def _build_curves(self, curves) -> int:
        """Turn {label, x, y, color, linewidth} specs into curves. Returns the
        number added."""
        added = 0
        for spec in (curves or []):
            if not isinstance(spec, dict):
                continue
            x_data = spec.get('x') or []
            y_data = spec.get('y') or []
            if len(x_data) == 0 or len(y_data) == 0:
                continue
            curve_id = self._curve_counter
            self._curve_counter += 1
            color = spec.get('color') or self.DEFAULT_COLORS[
                curve_id % len(self.DEFAULT_COLORS)]
            self._curves[curve_id] = CurveData(
                curve_id=curve_id,
                label=spec.get('label') or f"Curve {curve_id + 1}",
                x=np.array(x_data, dtype=np.float64),
                y=np.array(y_data, dtype=np.float64),
                color=color,
                linewidth=float(spec.get('linewidth') or 2.0),
            )
            added += 1
        return added

    @Slot()
    def clearCurves(self):
        """Remove all curves"""
        had_selection = self._selected_curve_id is not None
        self._curves.clear()
        self._invalidate_all_curve_paths()
        self._selected_curve_id = None
        self._curve_counter = 0
        self._needs_redraw = True
        self.curvesChanged.emit()
        self.curveSelected.emit(-1)
        if had_selection:
            self.selectedCurveIdChanged.emit(-1)
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
            self.selectedCurveIdChanged.emit(self._get_selected_curve_id())
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
        """Re-enable auto-range and frame the current data extent.

        When curves exist this computes the data bounds directly
        (``_calculateAutoBounds`` writes the view range with a 5 %
        margin) instead of waiting for the next paint to register the
        extent with the viewbox. That makes the toolbar "Reset View"
        button and the auto-fit-on-open call work immediately, even
        before the first render. With no curves yet it falls back to the
        viewbox's registered extent (if any).
        """
        self._viewbox.set_auto_range_enabled(True)
        if self._curves:
            # Writes via the ``_x_min`` … setters keep auto-range on
            # (disable_auto=False), so the view stays live-fitted until
            # the user interacts.
            self._calculateAutoBounds()
        else:
            self._viewbox.trigger_auto_range()
        self._needs_redraw = True
        self.update()
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
                'color': self._seriesColour(curve.color),
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
            # alpha 0.45 mirrors the native path's 115/255 grid alpha, so the
            # exported PNG and the on-screen render agree.
            self.axes.grid(True, color=self._grid_colour, linestyle='-',
                           linewidth=0.5, alpha=0.45)

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
                    facecolor=self._legend_bg_colour.name(),
                    edgecolor=self._grid_colour,
                    labelcolor=self._foreground,
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

    # Painted colours for the native path (they mirror the matplotlib path so
    # the visuals match when the user toggles ``TRANS_FAST_RENDER``). These
    # class-level values are only the fallback for an instance that never
    # reached ``_recomputeThemeColours`` — normally every one of them is
    # shadowed by an instance attribute derived from backgroundColor /
    # foregroundColor / gridColor.
    _NATIVE_BG_COLOR = QColor("#1a1a1a")
    _NATIVE_AXIS_COLOR = QColor("#444444")
    _NATIVE_TICK_COLOR = QColor("#888888")
    _NATIVE_LABEL_COLOR = QColor("#cccccc")
    _NATIVE_TITLE_COLOR = QColor("#ffffff")
    _NATIVE_GRID_COLOR = QColor(51, 51, 51, 127)
    _NATIVE_LEGEND_BG = QColor(42, 42, 42, 230)
    _NATIVE_LEGEND_BORDER = QColor(68, 68, 68)
    #: The cursor's identity hue, corrected per ground in
    #: ``_recomputeThemeColours`` and never themed away.
    _CURSOR_HUE = "#ffff64"

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
        # NaN fails every comparison, so the degenerate-range check below
        # lets it straight through into the transform and the tick
        # algorithm. Reject non-finite ranges explicitly.
        if not all(math.isfinite(v) for v in (x_vmin, x_vmax, y_vmin, y_vmax)):
            if not self._warned_nonfinite_range:
                self._warned_nonfinite_range = True
                logger.warning(
                    "Non-finite view range (x=%s..%s, y=%s..%s) — skipping "
                    "render; check the curve data for all-NaN/inf columns.",
                    x_vmin, x_vmax, y_vmin, y_vmax,
                )
            return
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
        # The painter already carries Qt's device-pixel-ratio scale (e.g. 2×
        # on Retina). The data→pixel ``transform`` must be COMPOSED with it,
        # not replace it — otherwise the DPR scale is wiped and curves render
        # at logical size in the top-left quarter while the DPR-scaled ticks /
        # frame fill the full item. ``transform * base_xform`` applies the data
        # transform first, then the painter's existing (DPR) transform.
        base_xform = painter.transform()
        for cid, curve in self._curves.items():
            if not curve.visible:
                continue
            path = self._native_get_path(cid, curve, x_log, y_log)
            if path is None or path.elementCount() == 0:
                continue
            pen = QPen(QColor(self._seriesColour(curve.color)))
            width = float(curve.linewidth)
            if cid == self._selected_curve_id:
                width += 1.0
            pen.setWidthF(width)
            # The path is stroked while the data→pixel ``transform`` is active,
            # so a non-cosmetic pen has its width scaled by the transform. With
            # small-magnitude data (e.g. STM currents ~1e-6) that scale is huge
            # and a 1.5px line floods the whole plot. A cosmetic pen keeps the
            # width in device pixels regardless of the transform.
            pen.setCosmetic(True)
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
            painter.setTransform(transform * base_xform)
            painter.drawPath(path)
        painter.setTransform(base_xform)
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
        if self._overlay_items:
            self._render_overlay_items(painter, ax_rect)
        if self._infinite_lines:
            self._render_infinite_lines(painter, ax_rect)
        if self._target_items:
            self._render_target_items(painter, ax_rect)
        self._drawOverlays(painter)

    # =========================================================================
    # Phase 6 — interactive overlay items
    # =========================================================================

    def _overlay_data_to_pixel_x(self):
        """Build a 1-D ``data_to_pixel_x`` callable from the canvas's
        full ``_dataToPixel``. The y-coordinate is unused for vertical
        overlay items but the helper needs a numeric to feed through."""
        y_anchor = self._y_min
        return lambda x: self._dataToPixel(x, y_anchor)[0]

    def _render_overlay_items(
        self,
        painter: QPainter,
        ax_rect: QRectF,
    ) -> None:
        data_to_pixel_x = self._overlay_data_to_pixel_x()
        active_id = (
            self._overlay_drag["region_id"]
            if self._overlay_drag is not None else None
        )
        for item in self._overlay_items:
            hover = (item.region_id == active_id)
            item.render(
                painter, ax_rect, data_to_pixel_x, hover=hover,
            )

    def _find_overlay_at(
        self,
        x_pixel: float,
        ax_rect: QRectF,
    ) -> Optional[Tuple[LinearRegionItem, str]]:
        """Return the topmost overlay (last-drawn) that claims a press
        at ``x_pixel``, paired with its hit type."""
        if not self._overlay_items:
            return None
        data_to_pixel_x = self._overlay_data_to_pixel_x()
        for item in reversed(self._overlay_items):
            hit = item.hit_test(
                x_pixel,
                data_to_pixel_x=data_to_pixel_x,
                ax_rect=ax_rect,
            )
            if hit != LR_HIT_NONE:
                return item, hit
        return None

    def _emit_overlay_change(
        self,
        item: LinearRegionItem,
        finished: bool,
    ) -> None:
        lo, hi = item.region()
        rid = str(item.region_id)
        if finished:
            self.overlayRegionChangeFinished.emit(rid, lo, hi)
        else:
            self.overlayRegionChanged.emit(rid, lo, hi)

    # --- QML-facing slots ----------------------------------------------------

    @Slot(str, float, float)
    def addLinearRegion(
        self,
        regionId: str,
        xLow: float,
        xHigh: float,
    ) -> None:
        """Add a vertical-band overlay between ``xLow`` and ``xHigh``.
        Replaces any existing region with the same id."""
        self.addLinearRegionWithOptions(regionId, xLow, xHigh, "", "")

    @Slot(str, float, float, str, str)
    def addLinearRegionWithOptions(
        self,
        regionId: str,
        xLow: float,
        xHigh: float,
        color: str,
        label: str,
    ) -> None:
        """Variant accepting ``color`` (hex string, empty = default)
        and ``label`` (empty = none)."""
        if not regionId:
            return
        self.removeOverlay(regionId)
        item = LinearRegionItem(
            region_id=regionId,
            values=(float(xLow), float(xHigh)),
            pen_color=color or "#5BCEFA",
            brush_color=color or "#5BCEFA",
            label=label or "",
        )
        self._overlay_items.append(item)
        self._needs_redraw = True
        self.update()

    @Slot(str)
    def removeOverlay(self, regionId: str) -> None:
        """Remove the overlay with this id (no-op if not found)."""
        before = len(self._overlay_items)
        self._overlay_items = [
            it for it in self._overlay_items
            if str(it.region_id) != regionId
        ]
        if (
            self._overlay_drag is not None
            and self._overlay_drag.get("region_id") == regionId
        ):
            self._overlay_drag = None
        if len(self._overlay_items) != before:
            self._needs_redraw = True
            self.update()

    @Slot()
    def clearOverlays(self) -> None:
        if not self._overlay_items:
            return
        self._overlay_items.clear()
        self._overlay_drag = None
        self._needs_redraw = True
        self.update()

    @Slot(str, result='QVariantList')
    def getOverlayRegion(self, regionId: str):
        """Return ``[xLow, xHigh]`` for the named region, or an empty
        list if the region is missing."""
        for item in self._overlay_items:
            if str(item.region_id) == regionId:
                lo, hi = item.region()
                return [float(lo), float(hi)]
        return []

    @Slot(str, float, float)
    def setOverlayRegion(
        self, regionId: str, xLow: float, xHigh: float,
    ) -> None:
        for item in self._overlay_items:
            if str(item.region_id) == regionId:
                if item.set_region(float(xLow), float(xHigh)):
                    self._needs_redraw = True
                    self.update()
                return

    # --- InfiniteLine helpers + slots ---------------------------------------

    def _render_infinite_lines(
        self,
        painter: QPainter,
        ax_rect: QRectF,
    ) -> None:
        active_id = (
            self._overlay_drag["region_id"]
            if (
                self._overlay_drag is not None
                and self._overlay_drag.get("kind") == "infinite_line"
            )
            else None
        )
        for line in self._infinite_lines:
            hover = (line.line_id == active_id)
            line.render(
                painter, ax_rect, self._dataToPixel, hover=hover,
            )

    def _find_infinite_line_at(
        self,
        x_pixel: float,
        y_pixel: float,
        ax_rect: QRectF,
    ) -> Optional[Tuple[InfiniteLine, str]]:
        if not self._infinite_lines:
            return None
        for line in reversed(self._infinite_lines):
            hit = line.hit_test(
                x_pixel, y_pixel,
                data_to_pixel=self._dataToPixel,
                ax_rect=ax_rect,
            )
            if hit != IL_HIT_NONE:
                return line, hit
        return None

    def _emit_infinite_line_change(
        self,
        line: InfiniteLine,
        finished: bool,
    ) -> None:
        lid = str(line.line_id)
        v = line.value()
        if finished:
            self.overlayLineChangeFinished.emit(lid, v)
        else:
            self.overlayLineChanged.emit(lid, v)

    @Slot(str, str, float)
    def addInfiniteLine(
        self,
        lineId: str,
        orientation: str,
        value: float,
    ) -> None:
        """Add a vertical (``orientation='vertical'``) or horizontal
        (``orientation='horizontal'``) line at the given data value.
        Replaces any existing line with the same id."""
        self.addInfiniteLineWithOptions(
            lineId, orientation, value, "", "",
        )

    @Slot(str, str, float, str, str)
    def addInfiniteLineWithOptions(
        self,
        lineId: str,
        orientation: str,
        value: float,
        color: str,
        label: str,
    ) -> None:
        self._add_infinite_line(lineId, orientation, value, color, label, True)

    @Slot(str, str, float, str, str)
    def addFixedInfiniteLine(
        self,
        lineId: str,
        orientation: str,
        value: float,
        color: str,
        label: str,
    ) -> None:
        """A line the user cannot drag.

        Markers that annotate a computed result -- a detected peak centre, say
        -- are read-outs, not controls: dragging one would imply the value
        could be edited, when in fact the next redraw discards the change.
        """
        self._add_infinite_line(lineId, orientation, value, color, label, False)

    def _add_infinite_line(
        self,
        lineId: str,
        orientation: str,
        value: float,
        color: str,
        label: str,
        movable: bool,
    ) -> None:
        if not lineId:
            return
        if orientation not in (IL_ORIENT_V, IL_ORIENT_H):
            logger.warning(
                "Ignoring addInfiniteLine: bad orientation %r", orientation,
            )
            return
        self.removeInfiniteLine(lineId)
        line = InfiniteLine(
            line_id=lineId,
            orientation=orientation,
            value=float(value),
            movable=movable,
            pen_color=color or "#FFD700",
            label=label or "",
        )
        self._infinite_lines.append(line)
        self._needs_redraw = True
        self.update()

    @Slot(str)
    def removeInfiniteLine(self, lineId: str) -> None:
        before = len(self._infinite_lines)
        self._infinite_lines = [
            ln for ln in self._infinite_lines
            if str(ln.line_id) != lineId
        ]
        if (
            self._overlay_drag is not None
            and self._overlay_drag.get("kind") == "infinite_line"
            and self._overlay_drag.get("region_id") == lineId
        ):
            self._overlay_drag = None
        if len(self._infinite_lines) != before:
            self._needs_redraw = True
            self.update()

    @Slot()
    def clearInfiniteLines(self) -> None:
        if not self._infinite_lines:
            return
        self._infinite_lines.clear()
        if (
            self._overlay_drag is not None
            and self._overlay_drag.get("kind") == "infinite_line"
        ):
            self._overlay_drag = None
        self._needs_redraw = True
        self.update()

    @Slot(str, result=float)
    def getInfiniteLineValue(self, lineId: str) -> float:
        """Return the line's current data value. ``NaN`` if absent."""
        for line in self._infinite_lines:
            if str(line.line_id) == lineId:
                return float(line.value())
        return float("nan")

    @Slot(str, float)
    def setInfiniteLineValue(self, lineId: str, value: float) -> None:
        for line in self._infinite_lines:
            if str(line.line_id) == lineId:
                if line.set_value(float(value)):
                    self._needs_redraw = True
                    self.update()
                return

    # --- TargetItem helpers + slots -----------------------------------------

    def _render_target_items(
        self,
        painter: QPainter,
        ax_rect: QRectF,
    ) -> None:
        active_id = (
            self._overlay_drag["region_id"]
            if (
                self._overlay_drag is not None
                and self._overlay_drag.get("kind") == "target"
            )
            else None
        )
        for tgt in self._target_items:
            hover = (tgt.target_id == active_id)
            tgt.render(
                painter, ax_rect, self._dataToPixel, hover=hover,
            )

    def _find_target_at(
        self,
        x_pixel: float,
        y_pixel: float,
        ax_rect: QRectF,
    ) -> Optional[Tuple[TargetItem, str]]:
        if not self._target_items:
            return None
        for tgt in reversed(self._target_items):
            hit = tgt.hit_test(
                x_pixel, y_pixel,
                data_to_pixel=self._dataToPixel,
                ax_rect=ax_rect,
            )
            if hit != TI_HIT_NONE:
                return tgt, hit
        return None

    def _emit_target_change(
        self,
        tgt: TargetItem,
        finished: bool,
    ) -> None:
        tid = str(tgt.target_id)
        x, y = tgt.position()
        if finished:
            self.overlayTargetChangeFinished.emit(tid, x, y)
        else:
            self.overlayTargetChanged.emit(tid, x, y)

    @Slot(str, float, float)
    def addTarget(
        self,
        targetId: str,
        x: float,
        y: float,
    ) -> None:
        """Add a crosshair marker at ``(x, y)``. Replaces any existing
        target with the same id."""
        self.addTargetWithOptions(
            targetId, x, y, "", "", TI_SYMBOL_CROSSHAIR,
        )

    @Slot(str, float, float, str, str, str)
    def addTargetWithOptions(
        self,
        targetId: str,
        x: float,
        y: float,
        color: str,
        label: str,
        symbol: str,
    ) -> None:
        if not targetId:
            return
        if symbol and symbol not in (TI_SYMBOL_CROSSHAIR, TI_SYMBOL_CIRCLE):
            logger.warning(
                "Ignoring addTarget: bad symbol %r", symbol,
            )
            return
        self.removeTarget(targetId)
        tgt = TargetItem(
            target_id=targetId,
            position=(float(x), float(y)),
            pen_color=color or "#FFD700",
            brush_color=color or "#5BCEFA",
            label=label or "",
            symbol=symbol or TI_SYMBOL_CROSSHAIR,
        )
        self._target_items.append(tgt)
        self._needs_redraw = True
        self.update()

    @Slot(str)
    def removeTarget(self, targetId: str) -> None:
        before = len(self._target_items)
        self._target_items = [
            t for t in self._target_items
            if str(t.target_id) != targetId
        ]
        if (
            self._overlay_drag is not None
            and self._overlay_drag.get("kind") == "target"
            and self._overlay_drag.get("region_id") == targetId
        ):
            self._overlay_drag = None
        if len(self._target_items) != before:
            self._needs_redraw = True
            self.update()

    @Slot()
    def clearTargets(self) -> None:
        if not self._target_items:
            return
        self._target_items.clear()
        if (
            self._overlay_drag is not None
            and self._overlay_drag.get("kind") == "target"
        ):
            self._overlay_drag = None
        self._needs_redraw = True
        self.update()

    @Slot(str, result='QVariantList')
    def getTargetPosition(self, targetId: str):
        """Return ``[x, y]`` for the named target, or an empty list
        if it's missing."""
        for tgt in self._target_items:
            if str(tgt.target_id) == targetId:
                x, y = tgt.position()
                return [float(x), float(y)]
        return []

    @Slot(str, float, float)
    def setTargetPosition(
        self, targetId: str, x: float, y: float,
    ) -> None:
        for tgt in self._target_items:
            if str(tgt.target_id) == targetId:
                if tgt.set_position(float(x), float(y)):
                    self._needs_redraw = True
                    self.update()
                return

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
                color=self._seriesColour(curve.color),
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
        """Compute auto-scale bounds from all visible curves and apply
        them to the viewbox in a single update.

        Setting the four edges through the individual ``_x_min`` …
        property setters used to route each assignment through
        ``set_view_range``'s ``sorted()`` against the *previous*
        (possibly default 0–1) range, which transiently swapped an edge
        and inflated the first-frame margin. Computing the range locally
        and pushing it once avoids that and is cheaper (one viewbox
        mutation instead of six)."""
        if not self._curves:
            self._viewbox.set_view_range(
                0.0, 1.0, 0.0, 1.0,
                push_history=False, disable_auto=False,
            )
            return

        x_mins, x_maxs = [], []
        y_mins, y_maxs = [], []

        for curve in self._curves.values():
            if not curve.visible or len(curve.x) == 0:
                continue
            # Only finite samples define the range. ``np.nanmin`` still
            # returns NaN for an all-NaN curve (and keeps ±inf as-is), and
            # a single NaN/inf edge propagates into the view range, the
            # data→pixel transform and the tick algorithm — where ``ceil``
            # raises "cannot convert float NaN to integer" and aborts the
            # paint on every frame. A fully non-finite curve is skipped.
            xf = np.asarray(curve.x, dtype=float)
            yf = np.asarray(curve.y, dtype=float)
            n = min(xf.size, yf.size)  # ragged curve: only the paired head plots
            xf, yf = xf[:n], yf[:n]
            finite = np.isfinite(xf) & np.isfinite(yf)
            if not finite.any():
                continue
            x_mins.append(xf[finite].min())
            x_maxs.append(xf[finite].max())
            y_mins.append(yf[finite].min())
            y_maxs.append(yf[finite].max())

        if not x_mins:
            return

        x_min, x_max = float(min(x_mins)), float(max(x_maxs))
        y_min, y_max = float(min(y_mins)), float(max(y_maxs))

        # 5 % margin; fall back to ±0.5 for a degenerate (zero-width) axis.
        x_margin = (x_max - x_min) * 0.05 or 0.5
        y_margin = (y_max - y_min) * 0.05 or 0.5

        self._viewbox.set_view_range(
            x_min - x_margin, x_max + x_margin,
            y_min - y_margin, y_max + y_margin,
            push_history=False, disable_auto=False,
        )

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
                pen = QPen(self._cursor_colour)
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
            pen = QPen(self._selection_edge)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(QBrush(self._selection_fill))
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

            # Overlay items (LinearRegionItem etc.) come next: if the
            # press lands on a handle or band, take it for that item
            # and short-circuit the viewbox so a region drag doesn't
            # also begin a zoom-rect.
            if self._use_fast_render and self._data_bounds and (
                self._overlay_items or self._infinite_lines
                or self._target_items
            ):
                d = self._data_bounds
                ax_rect = QRectF(
                    d['ax_left'], d['ax_top'],
                    d['ax_right'] - d['ax_left'],
                    d['ax_bottom'] - d['ax_top'],
                )
                hit_result = self._find_overlay_at(pos_px[0], ax_rect)
                if hit_result is not None:
                    item, lr_hit = hit_result
                    x_data, _ = self._pixelToData(*pos_px)
                    press_state = item.begin_drag(x_data, lr_hit)
                    self._overlay_drag = {
                        "kind": "linear_region",
                        "region_id": item.region_id,
                        "item": item,
                        "press": press_state,
                    }
                    self._emit_overlay_change(item, finished=False)
                    self._needs_redraw = True
                    self.update()
                    return
                line_result = self._find_infinite_line_at(
                    pos_px[0], pos_px[1], ax_rect,
                )
                if line_result is not None:
                    line, _ = line_result
                    x_data, y_data = self._pixelToData(*pos_px)
                    press_state = line.begin_drag(x_data, y_data)
                    self._overlay_drag = {
                        "kind": "infinite_line",
                        "region_id": line.line_id,
                        "item": line,
                        "press": press_state,
                    }
                    self._emit_infinite_line_change(line, finished=False)
                    self._needs_redraw = True
                    self.update()
                    return
                target_result = self._find_target_at(
                    pos_px[0], pos_px[1], ax_rect,
                )
                if target_result is not None:
                    tgt, _ = target_result
                    x_data, y_data = self._pixelToData(*pos_px)
                    press_state = tgt.begin_drag(x_data, y_data)
                    self._overlay_drag = {
                        "kind": "target",
                        "region_id": tgt.target_id,
                        "item": tgt,
                        "press": press_state,
                    }
                    self._emit_target_change(tgt, finished=False)
                    self._needs_redraw = True
                    self.update()
                    return

            x, y = self._pixelToData(*pos_px)
            self.pointClicked.emit(x, y)
            clicked_curve = self._findNearestCurve(x, y)
            if clicked_curve is not None and clicked_curve != self._selected_curve_id:
                self._selected_curve_id = clicked_curve
                self.curveClicked.emit(clicked_curve)
                self.curveSelected.emit(clicked_curve)
                self.selectedCurveIdChanged.emit(clicked_curve)
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

        if self._overlay_drag is not None:
            kind = self._overlay_drag.get("kind", "linear_region")
            item = self._overlay_drag["item"]
            press = self._overlay_drag["press"]
            x_data, y_data = self._pixelToData(*pos_px)
            if kind == "linear_region":
                if item.update_drag(x_data, press):
                    self._emit_overlay_change(item, finished=False)
                    self._needs_redraw = True
                    self.update()
            elif kind == "infinite_line":
                if item.update_drag(x_data, y_data, press):
                    self._emit_infinite_line_change(item, finished=False)
                    self._needs_redraw = True
                    self.update()
            elif kind == "target":
                if item.update_drag(x_data, y_data, press):
                    self._emit_target_change(item, finished=False)
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
            if self._overlay_drag is not None:
                kind = self._overlay_drag.get("kind", "linear_region")
                item = self._overlay_drag["item"]
                if kind == "linear_region":
                    self._emit_overlay_change(item, finished=True)
                elif kind == "infinite_line":
                    self._emit_infinite_line_change(item, finished=True)
                elif kind == "target":
                    self._emit_target_change(item, finished=True)
                self._overlay_drag = None
                self._needs_redraw = True
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
        """Find the curve nearest to a click, measured in pixel space.

        Both the click point and the curve samples are mapped through
        the canvas's own ``_dataToPixel`` (the native ``QTransform`` in
        fast-render mode), so the distance check lives in a single
        coordinate space. The old path mapped curve points with
        ``self.axes.transData`` — but in native mode the matplotlib
        axes is never laid out (default 0–1 limits), so the comparison
        was against garbage pixels and clicking a curve never selected
        it.
        """
        if not self._curves or not self._data_bounds:
            return None

        click_px, click_py = self._dataToPixel(x, y)
        threshold_px = 15.0  # pixels

        best_dist = threshold_px
        best_id = None

        for cid, curve in self._curves.items():
            if not curve.visible or len(curve.x) == 0:
                continue

            # Downsample for the distance check if the curve is huge.
            cx, cy = curve.x, curve.y
            if len(cx) > 500:
                step = len(cx) // 500
                cx, cy = cx[::step], cy[::step]

            # Map each sample with the same transform the canvas renders
            # with (handles native + matplotlib fallback + log scale).
            try:
                pts = np.array(
                    [self._dataToPixel(float(px), float(py))
                     for px, py in zip(cx, cy)],
                    dtype=np.float64,
                )
            except Exception:
                continue
            if pts.size == 0:
                continue

            dists = np.hypot(pts[:, 0] - click_px, pts[:, 1] - click_py)
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
