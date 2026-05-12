"""
QQuickImageProvider that serves :class:`ImageData` entities as native QImages.

Registered with the QML engine under the URL scheme ``image://trans/<id>``,
so QML files can do::

    Image { source: "image://trans/" + imageId; ... }

and let Qt Quick handle scaling, mipmapping, and antialiasing natively
— no QPainter, no custom canvas, no moiré.

Optional query params on the URL drive single-channel rendering:

    image://trans/<id>?cmap=viridis&min=0&max=255

- ``cmap`` — colormap name (``original``/``gray``/``viridis``/``magma``/…)
- ``min`` / ``max`` — display range remap (intensity floor / ceiling)

RGB / RGBA images ignore the query params (they're always rendered
in their native byte order). Changing the URL invalidates Qt's Image
cache, so the side panel just needs to update the source.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import parse_qs

import numpy as np
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider

from src.models.image_data import ImageData, ImageMode

logger = logging.getLogger(__name__)


# Matplotlib LUT cache keyed by colormap name.
_LUT_CACHE: dict = {}


def _lut(name: str) -> np.ndarray:
    """Return a cached 256×3 uint8 LUT. ``original`` / ``gray`` is identity."""
    key = (name or "original").lower()
    if key in _LUT_CACHE:
        return _LUT_CACHE[key]
    if key in ("original", "gray", "grey"):
        ramp = np.tile(np.arange(256, dtype=np.uint8)[:, None], (1, 3))
        _LUT_CACHE[key] = ramp
        return ramp
    try:
        import matplotlib
        try:
            cmap = matplotlib.colormaps.get_cmap(key)
        except (AttributeError, ValueError, KeyError):
            from matplotlib import cm
            cmap = cm.get_cmap(key)
        samples = cmap(np.linspace(0, 1, 256))[:, :3]
        lut = (samples * 255).astype(np.uint8)
    except Exception as e:
        logger.warning("Colormap %r unavailable (%s); falling back to gray", key, e)
        lut = np.tile(np.arange(256, dtype=np.uint8)[:, None], (1, 3))
    _LUT_CACHE[key] = lut
    return lut


def imagedata_to_qimage(
    image: ImageData,
    cmap: str = "original",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
) -> Optional[QImage]:
    """Convert an :class:`ImageData` to a QImage.

    For RGB / RGBA images the byte order is the only thing that matters
    and ``cmap`` / ``vmin`` / ``vmax`` are ignored.

    For single-channel images:

    - ``cmap == "original"`` and the data is already 8- or 16-bit unsigned
      → ship it as native ``Format_Grayscale8`` / ``Format_Grayscale16``
      (no LUT round-trip).
    - Otherwise (fancy colormap, or float data, or explicit min/max) →
      remap to uint8 via ``[vmin, vmax]`` and apply the LUT to produce
      ``Format_RGB888``.
    """
    if image is None or image.array is None:
        return None
    arr = image.array
    mode = image.mode

    if mode == ImageMode.RGB:
        a = np.ascontiguousarray(arr, dtype=np.uint8)
        return QImage(
            a.data, a.shape[1], a.shape[0], a.shape[1] * 3,
            QImage.Format_RGB888,
        ).copy()

    if mode == ImageMode.RGBA:
        a = np.ascontiguousarray(arr, dtype=np.uint8)
        return QImage(
            a.data, a.shape[1], a.shape[0], a.shape[1] * 4,
            QImage.Format_RGBA8888,
        ).copy()

    # ------ single-channel ---------------------------------------------
    cmap_key = (cmap or "original").lower()
    use_native_gray = (
        cmap_key in ("original", "gray", "grey")
        and vmin is None and vmax is None
        and mode in (ImageMode.GRAY_U8, ImageMode.GRAY_U16)
    )

    if use_native_gray and mode == ImageMode.GRAY_U8:
        a = np.ascontiguousarray(arr, dtype=np.uint8)
        return QImage(
            a.data, a.shape[1], a.shape[0], a.shape[1],
            QImage.Format_Grayscale8,
        ).copy()
    if use_native_gray and mode == ImageMode.GRAY_U16:
        a = np.ascontiguousarray(arr, dtype=np.uint16)
        fmt = getattr(QImage, "Format_Grayscale16", None)
        if fmt is not None:
            return QImage(
                a.data, a.shape[1], a.shape[0], a.shape[1] * 2, fmt,
            ).copy()
        # Fall through to the rescale + LUT path.

    # Range remap to uint8.
    data = np.asarray(arr, dtype=np.float32)
    if vmin is None or vmax is None or vmax <= vmin:
        finite = data[np.isfinite(data)]
        if finite.size == 0:
            lo, hi = 0.0, 1.0
        else:
            lo = float(vmin) if vmin is not None else float(np.percentile(finite, 1))
            hi = float(vmax) if vmax is not None else float(np.percentile(finite, 99))
            if hi <= lo:
                hi = lo + 1.0
    else:
        lo, hi = float(vmin), float(vmax)
    normalized = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    idx = np.ascontiguousarray((normalized * 255.0).astype(np.uint8))

    if cmap_key in ("original", "gray", "grey"):
        return QImage(
            idx.data, idx.shape[1], idx.shape[0], idx.shape[1],
            QImage.Format_Grayscale8,
        ).copy()

    lut = _lut(cmap_key)
    rgb = np.ascontiguousarray(lut[idx])  # H×W×3 uint8
    return QImage(
        rgb.data, rgb.shape[1], rgb.shape[0], rgb.shape[1] * 3,
        QImage.Format_RGB888,
    ).copy()


class TransImageProvider(QQuickImageProvider):
    """Serves images by id via the ``image://trans/<id>`` URL scheme.

    The provider holds a reference to the :class:`AppBackend` so it can look
    up :attr:`AppBackend._images` directly. QML's ``Image`` element handles
    caching and scaling — we just hand back the QImage.
    """

    def __init__(self, app_backend):
        super().__init__(QQmlImageProviderBase.Image)
        self._backend = app_backend

    def requestImage(self, id_: str, requested_size: QSize, size: QSize):
        # Split optional query string: ``<image_id>?cmap=…&min=…&max=…``.
        raw = id_.strip().rstrip("/")
        if "?" in raw:
            image_id, query = raw.split("?", 1)
        else:
            image_id, query = raw, ""
        params = parse_qs(query) if query else {}
        cmap = params.get("cmap", ["original"])[0]
        try:
            vmin = float(params["min"][0]) if "min" in params else None
        except (ValueError, TypeError):
            vmin = None
        try:
            vmax = float(params["max"][0]) if "max" in params else None
        except (ValueError, TypeError):
            vmax = None

        image = None
        if hasattr(self._backend, "_images"):
            image = self._backend._images.get(image_id)
        if image is None:
            logger.warning("ImageProvider: unknown image id %r", image_id)
            placeholder = QImage(1, 1, QImage.Format_RGB888)
            placeholder.fill(0)
            return placeholder
        qimg = imagedata_to_qimage(image, cmap=cmap, vmin=vmin, vmax=vmax)
        if qimg is None:
            placeholder = QImage(1, 1, QImage.Format_RGB888)
            placeholder.fill(0)
            return placeholder
        return qimg
