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
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)


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

        self._background = "#1a1a1a"
        self.figure = Figure(facecolor=self._background, dpi=self.BASE_DPI)
        self.canvas = FigureCanvasAgg(self.figure)

        self._cached_image: Optional[QImage] = None
        self._needs_redraw = True
        self._dpr = 1.0

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(self.RESIZE_DEBOUNCE_MS)
        self._resize_timer.timeout.connect(self._on_resize_finished)

    # ── properties ───────────────────────────────────────────────────────

    def _get_background(self) -> str:
        return self._background

    def _set_background(self, colour: str) -> None:
        colour = str(colour or "").strip()
        if not colour or colour == self._background:
            return
        self._background = colour
        try:
            self.figure.set_facecolor(colour)
        except (ValueError, TypeError):
            logger.warning("FigureCanvasItem: %r is not a colour", colour)
            return
        self.backgroundColorChanged.emit()
        self.redraw()

    backgroundColorChanged = Signal()

    #: The figure's own background, so a tool can follow the palette instead
    #: of painting a dark rectangle into a light theme.
    backgroundColor = Property(str, _get_background, _set_background,
                               notify=backgroundColorChanged)

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
