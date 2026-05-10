"""
QML Image Canvas - QQuickPaintedItem for displaying ImageData entities.

Lighter than ``QMLMapCanvas``: no matplotlib, no axes, no data-coordinate
transforms. Just paints a QImage onto the QML scene graph with pan/zoom,
crop-rectangle drawing, intensity-range remapping, and colormap LUT for
single-channel images.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: May 2026
License: GPL
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
from PySide6.QtCore import (
    Property, QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal, Slot,
)
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtQuick import QQuickPaintedItem

from src.models.image_data import ImageData, ImageMode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Colormap LUT cache
# ---------------------------------------------------------------------------

_LUT_CACHE: dict = {}


def _get_lut(name: str) -> np.ndarray:
    """Return a cached 256×3 uint8 lookup table for ``name``.

    ``"original"`` and ``"gray"`` produce a plain grayscale ramp. Other
    names go through matplotlib. Unknown names fall back to gray so the
    canvas always paints something.
    """
    key = (name or "original").lower()
    if key in _LUT_CACHE:
        return _LUT_CACHE[key]
    if key in ("original", "gray", "grey"):
        ramp = np.tile(np.arange(256, dtype=np.uint8)[:, None], (1, 3))
        _LUT_CACHE[key] = ramp
        return ramp
    try:
        import matplotlib
        # matplotlib 3.7+ moved to ``matplotlib.colormaps``; older versions
        # still expose ``cm.get_cmap``. Try both for safety.
        try:
            cmap = matplotlib.colormaps.get_cmap(key)
        except (AttributeError, ValueError, KeyError):
            from matplotlib import cm
            cmap = cm.get_cmap(key)
    except Exception as e:
        logger.warning("Could not load colormap %s: %s — using gray", key, e)
        ramp = np.tile(np.arange(256, dtype=np.uint8)[:, None], (1, 3))
        _LUT_CACHE[key] = ramp
        return ramp
    samples = cmap(np.linspace(0, 1, 256))[:, :3]  # drop alpha
    lut = (samples * 255).astype(np.uint8)
    _LUT_CACHE[key] = lut
    return lut


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

class QMLImageCanvas(QQuickPaintedItem):
    """QML-renderable image canvas with display-side controls.

    Properties (all Property-bound and notifying):
        ``displayMin``, ``displayMax`` — float range remap for single-channel.
        ``colormap`` — string colormap name (single-channel only).
        ``cropRect`` — overlay rectangle in image-pixel coordinates.
        ``cropActive`` — whether the user is currently dragging a crop.
        ``hasImage`` — true once an :class:`ImageData` is loaded.

    Slots:
        ``setImageData(image)`` — install a new :class:`ImageData`.
        ``getHistogram(bins)`` — returns histogram counts for the side panel.
        ``autoRange(percentile)`` — populate displayMin/Max via percentile clip.
        ``applyCrop()`` / ``resetCrop()`` — non-destructive crop preview.
        ``fitToWindow()`` / ``oneToOne()`` — pan/zoom helpers.
    """

    displayMinChanged = Signal(float)
    displayMaxChanged = Signal(float)
    colormapChanged = Signal(str)
    cropRectChanged = Signal()
    cropActiveChanged = Signal(bool)
    hasImageChanged = Signal(bool)
    imageInfoChanged = Signal()
    cropApplied = Signal('QVariantMap')  # {x0,y0,x1,y1}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.AllButtons)
        self.setAcceptHoverEvents(True)
        self.setFlag(QQuickPaintedItem.ItemHasContents, True)
        # Render via a GPU framebuffer so HiDPI scaling stays sharp instead
        # of producing the moiré pattern the default ``Image`` target gives
        # when its low-resolution intermediate gets stretched up by the
        # scene graph. Mipmap helps when the canvas is *smaller* than the
        # source (downscaled thumbnails).
        try:
            self.setRenderTarget(QQuickPaintedItem.FramebufferObject)
        except Exception:
            pass  # Software-only Qt builds don't support FBO targets
        try:
            self.setMipmap(True)
        except Exception:
            pass
        self.setSmooth(True)
        self.setAntialiasing(True)

        self._image: Optional[ImageData] = None
        self._qimage: Optional[QImage] = None
        self._needs_remap = True

        self._display_min: float = 0.0
        self._display_max: float = 1.0
        # ``original`` is treated as identity grayscale for single-channel
        # data and as a no-op pass-through for true RGB(A) images — sensible
        # default for the most common cases (optical video frames, AFM
        # amplitude/phase scans, color thumbnails). Other names map to
        # matplotlib colormaps via ``_get_lut``.
        self._colormap: str = "original"

        # Pan/zoom state (in image-pixel space → screen)
        self._pan = QPointF(0.0, 0.0)
        self._zoom: float = 1.0
        self._fit_to_window = True

        # Crop state
        self._crop_rect: Optional[QRectF] = None  # in image-pixel space
        self._crop_active: bool = False
        self._dragging_crop: bool = False
        self._drag_start: Optional[QPointF] = None
        self._drag_start_pan: Optional[QPointF] = None
        self._panning: bool = False

        # Resize debounce — same convention as QMLMapCanvas
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._on_resize_finished)

    # ------------------------------------------------------------- properties
    @Property(bool, notify=hasImageChanged)
    def hasImage(self) -> bool:
        return self._image is not None

    def _get_display_min(self) -> float:
        return self._display_min

    def _set_display_min(self, value: float) -> None:
        v = float(value)
        if v == self._display_min:
            return
        self._display_min = v
        self._needs_remap = True
        self.displayMinChanged.emit(v)
        self.update()

    displayMin = Property(
        float, fget=_get_display_min, fset=_set_display_min,
        notify=displayMinChanged,
    )

    def _get_display_max(self) -> float:
        return self._display_max

    def _set_display_max(self, value: float) -> None:
        v = float(value)
        if v == self._display_max:
            return
        self._display_max = v
        self._needs_remap = True
        self.displayMaxChanged.emit(v)
        self.update()

    displayMax = Property(
        float, fget=_get_display_max, fset=_set_display_max,
        notify=displayMaxChanged,
    )

    def _get_colormap(self) -> str:
        return self._colormap

    def _set_colormap(self, name: str) -> None:
        if name == self._colormap:
            return
        self._colormap = str(name)
        self._needs_remap = True
        self.colormapChanged.emit(self._colormap)
        self.update()

    colormap = Property(
        str, fget=_get_colormap, fset=_set_colormap, notify=colormapChanged,
    )

    @Property(int, notify=imageInfoChanged)
    def imageWidth(self) -> int:
        return self._image.width if self._image else 0

    @Property(int, notify=imageInfoChanged)
    def imageHeight(self) -> int:
        return self._image.height if self._image else 0

    @Property(str, notify=imageInfoChanged)
    def imageMode(self) -> str:
        return self._image.mode.value if self._image else ""

    @Property('QVariantMap', notify=cropRectChanged)
    def cropRect(self):
        if self._crop_rect is None:
            return {}
        return {
            'x0': float(self._crop_rect.x()),
            'y0': float(self._crop_rect.y()),
            'x1': float(self._crop_rect.x() + self._crop_rect.width()),
            'y1': float(self._crop_rect.y() + self._crop_rect.height()),
        }

    @Property(bool, notify=cropActiveChanged)
    def cropActive(self) -> bool:
        return self._crop_active

    # ----------------------------------------------------------------- slots
    @Slot(QObject, str)
    def loadImageById(self, app_backend, image_id: str) -> None:
        """Load an image from the backend by id (preferred QML entry point).

        Avoids passing the :class:`ImageData` through ``QVariant``, which is
        fragile — instead the canvas grabs the Python object directly from
        the backend's ``_images`` dict, so type information is preserved.
        """
        if app_backend is None or not image_id:
            self.setImageData(None)
            return
        # Prefer a clean accessor that returns the object directly. Falling
        # back to private dict access lets this slot work even if a custom
        # backend mock omits ``getImage`` (used in tests).
        image = None
        if hasattr(app_backend, "_images"):
            image = app_backend._images.get(image_id)
        if image is None and hasattr(app_backend, "getImage"):
            try:
                image = app_backend.getImage(image_id)
            except Exception:
                image = None
        if not isinstance(image, ImageData):
            logger.warning(
                "loadImageById: backend returned %s for id %s — abort",
                type(image).__name__, image_id,
            )
            return
        self.setImageData(image)

    @Slot('QVariant')
    def setImageData(self, image_data) -> None:
        """Install an :class:`ImageData` for display.

        ``image_data`` may be a Python :class:`ImageData` or a wrapped
        ``QVariant`` of one (QML brings them through unchanged since the
        backend exposes them as ``QVariant`` returns).

        Note: passing ``ImageData`` through ``QVariant`` from QML is fragile —
        depending on PySide6's marshalling, the unwrap may yield ``None`` or
        an opaque ``PyQt.QVariant``. Prefer :meth:`loadImageById` for the
        QML-driven path; this slot remains for tests and direct Python use.
        """
        if image_data is None:
            self._image = None
            self._qimage = None
            self._needs_remap = True
            self.hasImageChanged.emit(False)
            self.imageInfoChanged.emit()
            self.update()
            return

        # Unwrap if needed (PyQt sometimes hands back the raw Python object).
        if not isinstance(image_data, ImageData):
            try:
                image_data = ImageData.from_dict(image_data)
            except Exception:
                logger.warning("setImageData: unsupported argument type %r",
                               type(image_data))
                return

        self._image = image_data
        # Default range from auto-clip when display_min/max is uninitialized.
        lo, hi = image_data.auto_range()
        self._display_min = lo
        self._display_max = hi
        self.displayMinChanged.emit(lo)
        self.displayMaxChanged.emit(hi)
        self._crop_rect = None
        self.cropRectChanged.emit()
        self._needs_remap = True
        self.hasImageChanged.emit(True)
        self.imageInfoChanged.emit()
        self.update()

    @Slot(int, result='QVariantList')
    def getHistogram(self, bins: int = 64) -> list:
        """Return histogram counts as a flat list (for QML side-panel chart)."""
        if self._image is None:
            return []
        counts, _edges = self._image.histogram(bins=int(bins))
        return [int(c) for c in counts]

    @Slot(float, result='QVariantMap')
    def autoRange(self, percentile: float = 1.0) -> dict:
        """Compute and apply a robust display range; returns ``{min, max}``."""
        if self._image is None:
            return {'min': 0.0, 'max': 1.0}
        lo, hi = self._image.auto_range(percentile=float(percentile))
        self._set_display_min(lo)
        self._set_display_max(hi)
        return {'min': lo, 'max': hi}

    @Slot()
    def fitToWindow(self) -> None:
        self._fit_to_window = True
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self.update()

    @Slot()
    def oneToOne(self) -> None:
        self._fit_to_window = False
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self.update()

    @Slot()
    def beginCrop(self) -> None:
        self._crop_active = True
        self._crop_rect = None
        self.cropActiveChanged.emit(True)
        self.cropRectChanged.emit()
        self.update()

    @Slot()
    def cancelCrop(self) -> None:
        self._crop_active = False
        self._crop_rect = None
        self.cropActiveChanged.emit(False)
        self.cropRectChanged.emit()
        self.update()

    @Slot('QVariantMap')
    def applyCrop(self, rect=None) -> None:
        """Emit ``cropApplied`` so the QML side can register the cropped image
        as a new entity. Does NOT mutate the displayed image directly — the
        QML layer is responsible for invoking the backend's cropping API."""
        crop = rect or self.cropRect
        if not crop:
            return
        self._crop_active = False
        self.cropActiveChanged.emit(False)
        self.cropApplied.emit(crop)

    @Slot()
    def resetCrop(self) -> None:
        self._crop_rect = None
        self._crop_active = False
        self.cropRectChanged.emit()
        self.cropActiveChanged.emit(False)
        self.update()

    @Slot()
    def cleanup(self) -> None:
        self._resize_timer.stop()
        self._image = None
        self._qimage = None

    # -------------------------------------------------------------- internal
    def _on_resize_finished(self) -> None:
        self._needs_remap = True
        self.update()

    def _build_qimage(self) -> Optional[QImage]:
        if self._image is None:
            return None
        arr = self._image.array
        mode = self._image.mode

        if mode == ImageMode.RGB:
            # Direct: contiguous H×W×3 uint8.
            arr_c = np.ascontiguousarray(arr, dtype=np.uint8)
            qimg = QImage(
                arr_c.data, arr_c.shape[1], arr_c.shape[0],
                arr_c.shape[1] * 3, QImage.Format_RGB888,
            ).copy()
            return qimg
        if mode == ImageMode.RGBA:
            arr_c = np.ascontiguousarray(arr, dtype=np.uint8)
            qimg = QImage(
                arr_c.data, arr_c.shape[1], arr_c.shape[0],
                arr_c.shape[1] * 4, QImage.Format_RGBA8888,
            ).copy()
            return qimg

        # Single-channel — compute the uint8 brightness array from the
        # display range, then either ship it straight as ``Format_Grayscale8``
        # (clean, native, no LUT) or apply a colormap LUT for fancy display.
        data = arr.astype(np.float32, copy=False)
        lo = float(self._display_min)
        hi = float(self._display_max)
        if hi <= lo:
            hi = lo + 1.0
        normalized = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
        idx = np.ascontiguousarray((normalized * 255.0).astype(np.uint8))
        cmap = (self._colormap or "original").lower()

        if cmap in ("original", "gray", "grey"):
            # Native single-channel format — bytesPerLine = width, no row
            # padding, no LUT round-trip. Cleanest possible pipeline.
            qimg = QImage(
                idx.data, idx.shape[1], idx.shape[0],
                idx.shape[1], QImage.Format_Grayscale8,
            ).copy()
            return qimg

        # Colormap path: 8-bit index → 3-channel RGB via lookup table.
        lut = _get_lut(cmap)
        rgb = np.ascontiguousarray(lut[idx])  # H×W×3 uint8
        qimg = QImage(
            rgb.data, rgb.shape[1], rgb.shape[0],
            rgb.shape[1] * 3, QImage.Format_RGB888,
        ).copy()
        return qimg

    def _ensure_qimage(self) -> None:
        if self._needs_remap or self._qimage is None:
            self._qimage = self._build_qimage()
            self._needs_remap = False

    def _image_to_widget_rect(self) -> QRectF:
        """Compute where the image is drawn inside the widget."""
        w, h = self.width(), self.height()
        if self._image is None or w <= 0 or h <= 0:
            return QRectF(0, 0, w, h)
        iw, ih = self._image.width, self._image.height
        if self._fit_to_window:
            scale = min(w / iw, h / ih)
            dw, dh = iw * scale, ih * scale
            return QRectF((w - dw) / 2, (h - dh) / 2, dw, dh)
        scale = self._zoom
        dw, dh = iw * scale, ih * scale
        # Centred plus pan offset
        x = (w - dw) / 2 + self._pan.x()
        y = (h - dh) / 2 + self._pan.y()
        return QRectF(x, y, dw, dh)

    def _widget_to_image(self, p: QPointF) -> Optional[QPointF]:
        rect = self._image_to_widget_rect()
        if rect.width() <= 0 or rect.height() <= 0 or self._image is None:
            return None
        xn = (p.x() - rect.x()) / rect.width()
        yn = (p.y() - rect.y()) / rect.height()
        return QPointF(xn * self._image.width, yn * self._image.height)

    # ------------------------------------------------------------ rendering
    def paint(self, painter: QPainter) -> None:
        painter.fillRect(self.boundingRect(), QColor("#1a1a1a"))
        if self._image is None:
            painter.setPen(QPen(QColor("#666666")))
            painter.drawText(self.boundingRect(), Qt.AlignCenter, "No image")
            return
        self._ensure_qimage()
        if self._qimage is None:
            return
        rect = self._image_to_widget_rect()
        # Smooth interpolation when scaling up tiny images (e.g. 128×81
        # thumbnails blown up into a 760×480 viewport) — without this Qt
        # uses nearest-neighbor and the image looks chunky.
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawImage(rect, self._qimage)

        # Crop overlay
        if self._crop_rect is not None:
            wrect = self._image_rect_to_widget(self._crop_rect)
            painter.setPen(QPen(QColor("#FFD000"), 2, Qt.DashLine))
            painter.drawRect(wrect)

    def _image_rect_to_widget(self, irect: QRectF) -> QRectF:
        wrect = self._image_to_widget_rect()
        if self._image is None:
            return QRectF()
        sx = wrect.width() / self._image.width
        sy = wrect.height() / self._image.height
        return QRectF(
            wrect.x() + irect.x() * sx,
            wrect.y() + irect.y() * sy,
            irect.width() * sx,
            irect.height() * sy,
        )

    # ----------------------------------------------------------- mouse / wheel
    def mousePressEvent(self, event):
        if self._image is None:
            return
        if self._crop_active and event.button() == Qt.LeftButton:
            ip = self._widget_to_image(event.position())
            if ip is not None:
                self._dragging_crop = True
                self._drag_start = ip
                self._crop_rect = QRectF(ip.x(), ip.y(), 0, 0)
                self.cropRectChanged.emit()
                self.update()
        elif event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._panning = True
            self._drag_start = event.position()
            self._drag_start_pan = QPointF(self._pan)
            self._fit_to_window = False

    def mouseMoveEvent(self, event):
        if self._dragging_crop and self._drag_start is not None:
            ip = self._widget_to_image(event.position())
            if ip is None:
                return
            x0 = min(self._drag_start.x(), ip.x())
            y0 = min(self._drag_start.y(), ip.y())
            w = abs(ip.x() - self._drag_start.x())
            h = abs(ip.y() - self._drag_start.y())
            # Clamp to image bounds.
            x0 = max(0.0, x0)
            y0 = max(0.0, y0)
            if self._image is not None:
                w = min(w, self._image.width - x0)
                h = min(h, self._image.height - y0)
            self._crop_rect = QRectF(x0, y0, w, h)
            self.cropRectChanged.emit()
            self.update()
        elif self._panning and self._drag_start is not None:
            delta = event.position() - self._drag_start
            self._pan = self._drag_start_pan + delta
            self.update()

    def mouseReleaseEvent(self, event):
        if self._dragging_crop:
            self._dragging_crop = False
        if self._panning:
            self._panning = False

    def wheelEvent(self, event):
        if self._image is None:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.1 if delta > 0 else 1.0 / 1.1
        new_zoom = max(0.05, min(40.0, self._zoom * factor))
        self._zoom = new_zoom
        self._fit_to_window = False
        self.update()

    # --------------------------------------------------------------- resize
    def geometryChange(self, new_geometry, old_geometry):
        super().geometryChange(new_geometry, old_geometry)
        # Repaint the cached image on every pixel change to avoid lag,
        # actual remap deferred until the resize settles.
        self.update()
        self._resize_timer.start()
