"""
A matplotlib ``Figure`` hosted inside a QML item.

The seam between "Python draws it" and "QML lays it out". A caller holds the
:attr:`figure`, draws into it with ordinary matplotlib — ``ax.plot``,
``pcolormesh``, a colorbar, ``mplot3d`` — and calls :meth:`redraw`; the item
blits the result. Nothing about the drawing has to know it is inside Qt,
which is what lets a plot written for another host move across unchanged.

It exists because the two canvases TRANS already has are the opposite trade:
:class:`~src.widgets.qml_graph_canvas.QMLGraphCanvas` and
:class:`~src.widgets.qml_map_canvas.QMLMapCanvas` reimplement their drawing
in QPainter for speed, and every new kind of plot costs another
reimplementation. This one is slower per frame and takes anything
matplotlib can draw.

HiDPI
-----
The figure's DPI is the base DPI times the window's device pixel ratio, so
the Agg buffer comes out at *device* resolution and the QImage carries that
ratio. Getting this wrong is the "blurry on Retina" bug this repository has
already fixed once — see the ``graph-canvas-native-coords`` notes. Sizes in
points (fonts, line widths) scale with the DPI, so the layout is identical
at any ratio; only the pixel count changes.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Property, QRectF, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQuick import QQuickPaintedItem

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import is_color_like, to_rgba
from matplotlib.figure import Figure
from src.widgets.series_palette import readable_on

logger = logging.getLogger(__name__)

#: How far apart, in plain RGB distance (0 … 441), two colours of a *scale*
#: have to sit before they still read as different marks. A good/marginal/bad
#: scale carries its meaning in the fact that its three colours differ, so a
#: scheme whose success/warning/error are three shades of the same grey —
#: "Straight Dark" has #6a6a6a / #787878 / #8a7070, all within 25 of each
#: other — has to be refused rather than drawn. RGB distance and not WCAG
#: contrast: contrast is luminance only, and green against red is a large
#: difference that no luminance measure sees.
SCALE_MIN_DISTANCE = 60.0


def _rgb_distance(first: str, second: str) -> float:
    """Straight-line distance between two colours in 0-255 RGB."""
    a, b = to_rgba(first)[:3], to_rgba(second)[:3]
    return 255.0 * sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def scale_or_default(colours, default):
    """``colours`` when they still tell each other apart, else ``default``.

    Used where the theme is allowed to recolour a semantic scale but not to
    destroy it. Every pair is checked, not just neighbours: it is the middle
    band collapsing onto either end that makes a reading wrong, and a scheme
    that themes two of the three still has to be refused as a whole.

    An unparseable colour counts as a collapse, because a scale that cannot
    be drawn is not a scale.
    """
    colours = tuple(colours)
    try:
        for i, one in enumerate(colours):
            for other in colours[i + 1:]:
                if _rgb_distance(one, other) < SCALE_MIN_DISTANCE:
                    return tuple(default)
    except (ValueError, TypeError):
        return tuple(default)
    return colours


class FigureCanvasItem(QQuickPaintedItem):
    """A QML item that shows whatever is drawn into its matplotlib figure."""

    #: Emitted after a re-render, so QML can react to a finished draw.
    rendered = Signal()

    #: Points per inch the figure is laid out at before the device pixel
    #: ratio is applied. 100 matches the other canvases.
    BASE_DPI = 100

    #: Milliseconds of quiet before a resize triggers a full re-render. The
    #: cached image is stretched in the meantime, which is what keeps a drag
    #: smooth — the same idiom as the other canvases.
    RESIZE_DEBOUNCE_MS = 150

    #: The palette a canvas paints with until something binds it. These are
    #: the colours this project's figures already carried as literals, so a
    #: canvas nobody themes looks exactly as it did. They are deliberately
    #: *not* read from the current colour scheme: a widget that guessed the
    #: theme would be right on one scheme and wrong on the other twenty-one,
    #: and there would be nothing to notice. The theme arrives by binding.
    DEFAULT_BACKGROUND = "#1a1a1a"
    DEFAULT_FOREGROUND = "#cccccc"
    DEFAULT_GRID = "#444444"
    DEFAULT_ACCENT = "#5BCEFA"
    DEFAULT_SUCCESS = "#2ECC71"
    DEFAULT_WARNING = "#FF9800"
    DEFAULT_ERROR = "#FF6B6B"

    #: Whether this canvas's 2-D axes are ruled. A subclass says so once
    #: rather than every plot repeating ``ax.grid(...)`` with its own colour.
    SHOW_GRID = False

    #: Tick label sizes, 2-D and mplot3d. The 3-D panels are a quarter of a
    #: figure and their three axes crowd; they have always been a point down.
    TICK_LABEL_SIZE = 7
    TICK_LABEL_SIZE_3D = 6

    #: An axes carrying this attribute keeps the background it was given.
    #: Set it where the ground itself is data — the line-scan strip paints
    #: "no confinement" as its own facecolor, and a restyle must not quietly
    #: turn that into "the smallest well on the line".
    KEEP_FACECOLOR = "_trans_keep_facecolor"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFlag(QQuickPaintedItem.ItemHasContents, True)
        # A framebuffer target gives a painter in logical coordinates, which
        # is what a device-pixel-ratio-tagged QImage expects to be drawn
        # into. With the default Image target on macOS HiDPI the painter is
        # not scaled and the figure lands in the top-left quarter.
        try:
            self.setRenderTarget(QQuickPaintedItem.FramebufferObject)
        except Exception:      # software-only Qt builds
            pass

        self._background = self.DEFAULT_BACKGROUND
        self._foreground = self.DEFAULT_FOREGROUND
        self._grid = self.DEFAULT_GRID
        self._accent = self.DEFAULT_ACCENT
        self._success = self.DEFAULT_SUCCESS
        self._warning = self.DEFAULT_WARNING
        self._error = self.DEFAULT_ERROR
        # What QML last *asked* for, which is not always what is painted: a
        # colour matplotlib cannot parse is remembered so a binding reads
        # back what it wrote, but is never handed to a draw call.
        self._requests: dict = {}
        # The last picture drawn, as (slot name, arguments), so a colour
        # change can draw it again. Recolouring the frame is not enough on
        # its own: the marks carry colour too, and a bar in a good/bad
        # scale that keeps the previous scheme's green says the wrong thing.
        self._last_draw = None

        self.figure = Figure(facecolor=self._background, dpi=self.BASE_DPI)
        self.canvas = FigureCanvasAgg(self.figure)

        self._cached_image: Optional[QImage] = None
        self._needs_redraw = True
        self._dpr = 1.0

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(self.RESIZE_DEBOUNCE_MS)
        self._resize_timer.timeout.connect(self._on_resize_finished)

    # ── the palette ──────────────────────────────────────────────────────
    #
    # Seven colours, written out one by one rather than generated: PySide
    # registers a Signal only when the class body carries it, so a loop
    # cannot make these, and the repetition is at least readable.
    #
    # Every setter has the same shape — record the request, and if the
    # painted colour actually moved, tell QML and restyle. The restyle is
    # the part that was missing: setting the figure's facecolor and
    # re-blitting leaves every *axes* at the previous scheme's colours,
    # because an axes' background, spines, ticks and labels are set when a
    # plot is drawn, not when the figure is. That is what produced a light
    # figure margin around two dark axes on a scheme change.

    def _set_colour(self, name: str, colour) -> bool:
        """Record a colour request. True when the painted colour moved.

        Empty means "no opinion" — a binding that has not resolved yet
        arrives as an empty string, and taking it literally would paint the
        figure black. An unparseable colour is remembered but not painted:
        handing matplotlib a bad colour raises in the middle of a draw, and
        that costs the whole figure rather than one wrong shade.
        """
        colour = str(colour or "").strip()
        if not colour:
            return False
        self._requests[name] = colour
        attribute = f"_{name}"
        if colour == getattr(self, attribute):
            return False        # idempotent: the same colour twice is a no-op
        if not is_color_like(colour):
            logger.warning("%s: %r is not a colour",
                           type(self).__name__, colour)
            return False
        setattr(self, attribute, colour)
        return True

    def _get_colour(self, name: str) -> str:
        return self._requests.get(name, getattr(self, f"_{name}"))

    backgroundColorChanged = Signal()
    foregroundColorChanged = Signal()
    gridColorChanged = Signal()
    accentColorChanged = Signal()
    successColorChanged = Signal()
    warningColorChanged = Signal()
    errorColorChanged = Signal()

    def _get_background(self) -> str:
        return self._get_colour("background")

    def _set_background(self, colour: str) -> None:
        if self._set_colour("background", colour):
            # The figure's own ground is set here and not in `_restyle`,
            # because a subclass that restyles by drawing everything again
            # touches its axes and never the figure around them — which is
            # exactly the light-margin-round-dark-axes picture, with the
            # halves the other way about.
            self.figure.set_facecolor(self._background)
            self.backgroundColorChanged.emit()
            self._restyle()

    #: The figure's own ground, so a tool can follow the palette instead of
    #: painting a dark rectangle into a light theme.
    backgroundColor = Property(str, _get_background, _set_background,
                               notify=backgroundColorChanged)

    def _get_foreground(self) -> str:
        return self._get_colour("foreground")

    def _set_foreground(self, colour: str) -> None:
        if self._set_colour("foreground", colour):
            self.foregroundColorChanged.emit()
            self._restyle()

    #: Text: titles, axis labels, tick labels, annotations.
    foregroundColor = Property(str, _get_foreground, _set_foreground,
                               notify=foregroundColorChanged)

    def _get_grid(self) -> str:
        return self._get_colour("grid")

    def _set_grid(self, colour: str) -> None:
        if self._set_colour("grid", colour):
            self.gridColorChanged.emit()
            self._restyle()

    #: Rules: spines, gridlines, colorbar outlines, the 3-D pane edges.
    gridColor = Property(str, _get_grid, _set_grid, notify=gridColorChanged)

    def _get_accent(self) -> str:
        return self._get_colour("accent")

    def _set_accent(self, colour: str) -> None:
        if self._set_colour("accent", colour):
            self.accentColorChanged.emit()
            self._restyle()

    #: The one colour a figure emphasises with. Not for anything that has to
    #: stay distinct from a *series* colour — see the notes on each canvas.
    accentColor = Property(str, _get_accent, _set_accent,
                           notify=accentColorChanged)

    def _get_success(self) -> str:
        return self._get_colour("success")

    def _set_success(self, colour: str) -> None:
        if self._set_colour("success", colour):
            self.successColorChanged.emit()
            self._restyle()

    #: "As good as the measurement" / "deeply bound". The scheme's `success`.
    successColor = Property(str, _get_success, _set_success,
                            notify=successColorChanged)

    def _get_warning(self) -> str:
        return self._get_colour("warning")

    def _set_warning(self, colour: str) -> None:
        if self._set_colour("warning", colour):
            self.warningColorChanged.emit()
            self._restyle()

    #: "Marginal". The scheme's `warning`.
    warningColor = Property(str, _get_warning, _set_warning,
                            notify=warningColorChanged)

    def _get_error(self) -> str:
        return self._get_colour("error")

    def _set_error(self, colour: str) -> None:
        if self._set_colour("error", colour):
            self.errorColorChanged.emit()
            self._restyle()

    #: "Does not explain this level" / "unbound". The scheme's `error`.
    errorColor = Property(str, _get_error, _set_error,
                          notify=errorColorChanged)

    # ── painting the palette onto a figure ───────────────────────────────

    def _seriesColour(self, colour):
        """A data colour, adjusted only if it cannot be seen on this ground.

        Identity colours — which feature holds a state, electron vs hole —
        are chosen by the canvas and must not follow the scheme, or the same
        feature would be a different colour in two panels. But they were all
        chosen against a ground that was hardcoded ``#1a1a1a`` and is now the
        scheme's ``bgDark``, which is near-white on eight of the twenty-two
        schemes. ``readable_on`` keeps the hue and moves only the lightness,
        and only when the colour actually falls under 3:1 — so every dark
        scheme still paints byte-identical values.
        """
        return readable_on(str(colour), self._background)

    def _style(self, ax) -> None:
        """Paint one 2-D axes in the current palette, at drawing time."""
        self._paint_axes(ax, grid=self.SHOW_GRID)

    def _paint_axes(self, ax, grid: bool) -> None:
        """The whole of an axes that carries a colour.

        ``grid`` switches the rules on; when it is False a grid that is
        already there is still *recoloured*. The distinction matters on a
        restyle, which walks ``figure.axes`` — a colorbar's axes is in that
        list, and ruling it would be a new drawing decision rather than a
        colour change.
        """
        if not getattr(ax, self.KEEP_FACECOLOR, False):
            ax.set_facecolor(self._background)
        for spine in ax.spines.values():
            spine.set_color(self._grid)
        ax.tick_params(colors=self._foreground, labelsize=self.TICK_LABEL_SIZE)
        ax.xaxis.label.set_color(self._foreground)
        ax.yaxis.label.set_color(self._foreground)
        ax.title.set_color(self._foreground)
        if grid:
            ax.grid(True, color=self._grid, alpha=0.3, linewidth=0.5)
        else:
            for line in ax.get_xgridlines() + ax.get_ygridlines():
                line.set_color(self._grid)

    def _style_3d(self, ax) -> None:
        """The same treatment for an mplot3d axes, which styles differently.

        Its panes, its axis lines and its grid are three separate things and
        none of them follows ``set_facecolor``; left alone they are the
        default light grey, which on a dark palette is a white box around
        the data.
        """
        ax.set_facecolor(self._background)
        pane = to_rgba(self._background)
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            try:
                axis.set_pane_color(pane)
            except AttributeError:
                axis.pane.set_facecolor(pane)
            try:
                axis.pane.set_edgecolor(self._grid)
                axis.line.set_color(self._grid)
                axis._axinfo['grid']['color'] = self._grid
            except (AttributeError, KeyError, TypeError):
                pass
            axis.label.set_color(self._foreground)
        ax.tick_params(colors=self._foreground,
                       labelsize=self.TICK_LABEL_SIZE_3D)
        ax.title.set_color(self._foreground)

    def _replay(self) -> bool:
        """Draw the last picture again. False when there is nothing to.

        Never raises: this runs from a property write — a QML binding
        firing — and an exception there is a broken window, not a message
        anyone can act on. A failed replay falls back to recolouring what
        is already on the figure.
        """
        if not self._last_draw:
            return False
        name, arguments = self._last_draw
        try:
            getattr(self, name)(*arguments)
            return True
        except Exception:
            logger.exception("%s: the last plot could not be drawn again",
                             type(self).__name__)
            return False

    def _restyle(self) -> None:
        """Re-apply the palette to whatever is already drawn.

        Drawing it again is the honest answer, because the marks carry the
        theme as well as the frame does. Where there is nothing to replay —
        a canvas that renders from its own state every frame — recolour the
        chrome of each existing axes in place instead.
        """
        if self._replay():
            return
        try:
            self.figure.set_facecolor(self._background)
            for ax in list(self.figure.axes):
                if hasattr(ax, 'zaxis'):
                    self._style_3d(ax)
                else:
                    self._paint_axes(ax, grid=False)
        except Exception:
            logger.exception("%s: the palette could not be applied",
                             type(self).__name__)
        self.redraw()

    # ── nothing to draw ──────────────────────────────────────────────────

    def _draw_message(self, message: str) -> None:
        """A line of text where a plot would be.

        Styled like any other axes even though its frame is hidden: the text
        colour is the whole of what is visible, and it has to be the theme's
        rather than matplotlib's near-black.
        """
        ax = self.figure.add_subplot(111)
        ax.axis("off")
        ax.set_facecolor(self._background)
        ax.text(0.5, 0.5, message, ha="center", va="center",
                color=self._foreground, fontsize=10, transform=ax.transAxes)
        self.redraw()

    @Slot(str)
    def showMessage(self, message: str) -> None:
        """Put a line of text where a plot would be — an empty result, or why."""
        message = str(message)
        # Recorded like any other picture: a message is what is on screen,
        # so a scheme change has to redraw *it* rather than the plot it
        # replaced.
        self._last_draw = ('showMessage', (message,))
        self.figure.clf()
        self._draw_message(message)

    # ── drawing ──────────────────────────────────────────────────────────

    @Slot()
    def redraw(self) -> None:
        """Re-render after a caller has changed the figure."""
        self._needs_redraw = True
        self.update()

    @Slot()
    def clearFigure(self) -> None:
        """Empty the figure. The caller adds its own axes back."""
        self.figure.clf()
        self.redraw()

    def paint(self, painter: QPainter) -> None:
        if self._needs_redraw:
            self._render()
            self._needs_redraw = False

        if self._cached_image is not None:
            painter.drawImage(QRectF(0, 0, self.width(), self.height()),
                              self._cached_image)

    def _device_pixel_ratio(self) -> float:
        """The window's ratio, or 1.0 when there is no window yet.

        Read every render rather than cached: a window dragged between a
        Retina display and an external monitor changes it, and a figure laid
        out for the old one is either blurry or oversized.
        """
        window = self.window()
        try:
            return float(window.devicePixelRatio()) if window else 1.0
        except Exception:
            return 1.0

    def _render(self) -> None:
        """Lay the figure out at the item's size and blit it."""
        width, height = int(self.width()), int(self.height())
        if width <= 0 or height <= 0:
            return

        self._dpr = max(1.0, self._device_pixel_ratio())
        # Size in inches stays the logical size; the DPI carries the ratio,
        # so the buffer is width*dpr x height*dpr device pixels and every
        # point-sized thing in the figure scales with it.
        self.figure.set_dpi(self.BASE_DPI * self._dpr)
        self.figure.set_size_inches(width / self.BASE_DPI,
                                    height / self.BASE_DPI)

        try:
            self.canvas.draw()
        except Exception:
            logger.exception("FigureCanvasItem: the figure could not be drawn")
            return

        buffer = self.canvas.buffer_rgba()
        buffer_w, buffer_h = self.canvas.get_width_height()
        image = QImage(buffer, buffer_w, buffer_h,
                       QImage.Format_RGBA8888).copy()
        # Without this the image is drawn at device size into a logical rect
        # and comes out either cropped or soft.
        image.setDevicePixelRatio(self._dpr)
        self._cached_image = image
        self.rendered.emit()

    # ── where a click lands in the data ──────────────────────────────────

    def data_at(self, x: float, y: float, ax=None):
        """``(x, y)`` in data coordinates for a point in item coordinates.

        Two conversions, and both are easy to get wrong. The figure is
        rendered at ``BASE_DPI * dpr``, so item coordinates have to be scaled
        by the device pixel ratio to reach it; and matplotlib's origin is the
        bottom-left where Qt's is the top-left, so y is flipped.

        Unlike the native-rendered canvases in this project, the axes here
        really are laid out — matplotlib drew the figure — so ``transData``
        is the honest transform rather than something to reimplement. Returns
        None when there is no axes to land in.
        """
        ax = ax or (self.figure.axes[0] if self.figure.axes else None)
        if ax is None or self._cached_image is None:
            return None
        height = self._cached_image.height()
        point = (float(x) * self._dpr, height - float(y) * self._dpr)
        try:
            data = ax.transData.inverted().transform(point)
        except Exception:
            return None
        return float(data[0]), float(data[1])

    def item_at(self, x: float, y: float, ax=None):
        """The inverse of :meth:`data_at` — data coordinates to item ones.

        Used for hit tests that have to be in pixels (a handle is a fixed
        size on screen, not a fixed size in nanometres).
        """
        ax = ax or (self.figure.axes[0] if self.figure.axes else None)
        if ax is None or self._cached_image is None:
            return None
        height = self._cached_image.height()
        try:
            point = ax.transData.transform((float(x), float(y)))
        except Exception:
            return None
        return float(point[0]) / self._dpr, (height - float(point[1])) / self._dpr

    # ── geometry ─────────────────────────────────────────────────────────

    def geometryChange(self, new_geometry, old_geometry) -> None:
        super().geometryChange(new_geometry, old_geometry)
        if new_geometry.size() != old_geometry.size():
            # Repaint immediately with the stretched cache, and re-render
            # properly once the drag stops.
            self.update()
            self._resize_timer.start()

    def _on_resize_finished(self) -> None:
        self.redraw()

    # ── export ───────────────────────────────────────────────────────────

    @Slot(str, result=bool)
    def exportToPNG(self, file_path: str) -> bool:
        """Save the figure as a high-resolution PNG.

        A picture of a plot, not measurement data — the export rule in
        CLAUDE.md is about fields, and this is deliberately a preview.
        """
        try:
            self.figure.savefig(file_path, dpi=300, bbox_inches="tight",
                                facecolor=self.figure.get_facecolor())
            logger.info("Figure exported to %s", file_path)
            return True
        except Exception:
            logger.exception("FigureCanvasItem: export to %s failed", file_path)
            return False

    # ── teardown ─────────────────────────────────────────────────────────

    @Slot()
    def cleanup(self) -> None:
        """Stop the timer and close the figure.

        Every canvas in this project has one: a Figure held past its window
        keeps its Agg buffer alive, and a running QTimer keeps firing into a
        deleted item.
        """
        try:
            self._resize_timer.stop()
        except Exception:
            pass
        try:
            import matplotlib.pyplot as plt
            plt.close(self.figure)
        except Exception:
            pass
        self._cached_image = None
