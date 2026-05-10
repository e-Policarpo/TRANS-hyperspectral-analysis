"""
QQuickImageProvider that serves :class:`ImageData` entities as native QImages.

Registered with the QML engine under the URL scheme ``image://trans/<id>``,
so QML files can do::

    Image { source: "image://trans/" + imageId; ... }

and let Qt Quick handle scaling, mipmapping, and antialiasing natively
— no QPainter, no custom canvas, no moiré.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider

from src.models.image_data import ImageData, ImageMode

logger = logging.getLogger(__name__)


def imagedata_to_qimage(image: ImageData) -> Optional[QImage]:
    """Convert an :class:`ImageData` to a QImage using the most native format
    available — no LUT, no rescaling unless required by the underlying type.

    - RGB / RGBA → ``Format_RGB888`` / ``Format_RGBA8888`` (zero-copy after
      the contiguous-array snapshot).
    - 8-bit grayscale → ``Format_Grayscale8``.
    - 16-bit grayscale → ``Format_Grayscale16`` when supported (Qt ≥ 5.13);
      otherwise auto-rescaled to 8-bit grayscale.
    - Float single-channel → auto-rescaled to 8-bit grayscale (display-only;
      the original float array stays intact in :class:`ImageData`).
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

    if mode == ImageMode.GRAY_U8:
        a = np.ascontiguousarray(arr, dtype=np.uint8)
        return QImage(
            a.data, a.shape[1], a.shape[0], a.shape[1],
            QImage.Format_Grayscale8,
        ).copy()

    if mode == ImageMode.GRAY_U16:
        a = np.ascontiguousarray(arr, dtype=np.uint16)
        fmt = getattr(QImage, "Format_Grayscale16", None)
        if fmt is not None:
            return QImage(
                a.data, a.shape[1], a.shape[0], a.shape[1] * 2, fmt,
            ).copy()
        # Fallback: rescale to 8-bit grayscale.
        scaled = (a.astype(np.float32) / 257.0).astype(np.uint8)
        scaled = np.ascontiguousarray(scaled)
        return QImage(
            scaled.data, scaled.shape[1], scaled.shape[0], scaled.shape[1],
            QImage.Format_Grayscale8,
        ).copy()

    if mode == ImageMode.SINGLE_FLOAT:
        # Display-only: stretch to [0, 255] uint8 so QML can show *something*
        # sensible. The full float precision lives on in ``image.array``.
        a = np.asarray(arr, dtype=np.float32)
        finite = a[np.isfinite(a)]
        if finite.size == 0:
            scaled = np.zeros(a.shape, dtype=np.uint8)
        else:
            lo = float(np.percentile(finite, 1))
            hi = float(np.percentile(finite, 99))
            if hi <= lo:
                hi = lo + 1.0
            normalized = np.clip((a - lo) / (hi - lo), 0.0, 1.0)
            scaled = (normalized * 255.0).astype(np.uint8)
        scaled = np.ascontiguousarray(scaled)
        return QImage(
            scaled.data, scaled.shape[1], scaled.shape[0], scaled.shape[1],
            QImage.Format_Grayscale8,
        ).copy()

    logger.warning("Unknown image mode %r — cannot convert to QImage", mode)
    return None


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
        # Strip any URL-decoding artifacts; QML may pass the id as-is.
        image_id = id_.strip().rstrip("/")
        image = None
        if hasattr(self._backend, "_images"):
            image = self._backend._images.get(image_id)
        if image is None:
            logger.warning("ImageProvider: unknown image id %r", image_id)
            placeholder = QImage(1, 1, QImage.Format_RGB888)
            placeholder.fill(0)
            return placeholder
        qimg = imagedata_to_qimage(image)
        if qimg is None:
            placeholder = QImage(1, 1, QImage.Format_RGB888)
            placeholder.fill(0)
            return placeholder
        return qimg
