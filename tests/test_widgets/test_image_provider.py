"""
Tests for the QML image provider that serves ImageData entities to
``image://trans/<id>`` URLs.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtGui")
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QGuiApplication

from src.models.image_data import ImageData, ImageMode
from src.widgets.image_provider import (
    TransImageProvider,
    imagedata_to_qimage,
)


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


# =============================================================================
# imagedata_to_qimage primitives
# =============================================================================

def test_rgb_round_trips_via_qimage(app):
    arr = np.zeros((10, 12, 3), dtype=np.uint8)
    arr[..., 0] = 200  # red-tinted
    arr[5, 6] = (10, 20, 30)
    img = ImageData.from_array(arr, mode=ImageMode.RGB)
    qi = imagedata_to_qimage(img)
    assert qi is not None
    assert qi.width() == 12 and qi.height() == 10
    assert qi.format() == QImage.Format_RGB888
    c = qi.pixelColor(6, 5)
    assert (c.red(), c.green(), c.blue()) == (10, 20, 30)


def test_uint8_grayscale_uses_native_format(app):
    arr = np.linspace(0, 255, 8 * 12, dtype=np.uint8).reshape(8, 12)
    img = ImageData.from_array(arr, mode=ImageMode.GRAY_U8)
    qi = imagedata_to_qimage(img)
    assert qi.format() == QImage.Format_Grayscale8
    assert qi.width() == 12 and qi.height() == 8


def test_uint16_grayscale_keeps_full_dynamic_range_when_possible(app):
    arr = np.linspace(0, 65535, 8 * 12, dtype=np.uint16).reshape(8, 12)
    img = ImageData.from_array(arr, mode=ImageMode.GRAY_U16)
    qi = imagedata_to_qimage(img)
    fmt16 = getattr(QImage, "Format_Grayscale16", None)
    if fmt16 is not None:
        assert qi.format() == fmt16
    else:
        assert qi.format() == QImage.Format_Grayscale8


def test_single_float_is_rescaled_to_grayscale(app):
    arr = np.linspace(-1.0, 1.0, 8 * 12, dtype=np.float32).reshape(8, 12)
    img = ImageData.from_array(arr, mode=ImageMode.SINGLE_FLOAT)
    qi = imagedata_to_qimage(img)
    assert qi.format() == QImage.Format_Grayscale8
    # Center of the gradient should be roughly mid-gray.
    midpix = qi.pixelColor(6, 4).red()
    assert 80 < midpix < 200


# =============================================================================
# TransImageProvider lookup
# =============================================================================

class _StubBackend:
    def __init__(self):
        self._images = {}


def test_provider_returns_qimage_for_known_id(app):
    backend = _StubBackend()
    arr = np.zeros((4, 6, 3), dtype=np.uint8)
    arr[..., 1] = 128
    img = ImageData.from_array(arr, mode=ImageMode.RGB, name="X")
    backend._images[img.id] = img

    provider = TransImageProvider(backend)
    qi = provider.requestImage(img.id, QSize(0, 0), QSize())
    assert isinstance(qi, QImage)
    assert qi.width() == 6 and qi.height() == 4
    c = qi.pixelColor(3, 2)
    assert c.green() == 128


def test_provider_returns_placeholder_for_unknown_id(app):
    backend = _StubBackend()
    provider = TransImageProvider(backend)
    qi = provider.requestImage("does_not_exist", QSize(0, 0), QSize())
    assert isinstance(qi, QImage)
    # Tiny placeholder, not the original (because original doesn't exist).
    assert qi.width() == 1 and qi.height() == 1


def test_provider_parses_query_params_for_single_channel(app):
    """``image://trans/<id>?cmap=viridis&min=…&max=…`` should apply LUT."""
    backend = _StubBackend()
    arr = np.linspace(0, 1, 16 * 24, dtype=np.float32).reshape(16, 24)
    img = ImageData.from_array(arr, mode=ImageMode.SINGLE_FLOAT, name="g")
    backend._images[img.id] = img

    provider = TransImageProvider(backend)
    qi_gray = provider.requestImage(img.id, QSize(0, 0), QSize())
    qi_viridis = provider.requestImage(
        f"{img.id}?cmap=viridis&min=0&max=1", QSize(0, 0), QSize(),
    )
    # Default (no params) → grayscale single-byte; viridis → RGB triplet.
    assert qi_gray.format() == QImage.Format_Grayscale8
    assert qi_viridis.format() == QImage.Format_RGB888
    # Midpoint pixel should differ noticeably between the two outputs.
    g = qi_gray.pixelColor(12, 8)
    v = qi_viridis.pixelColor(12, 8)
    assert (v.red(), v.green(), v.blue()) != (g.red(), g.green(), g.blue())


def test_provider_range_clip_affects_output(app):
    """vmin/vmax narrowing should brighten the midpoint."""
    backend = _StubBackend()
    arr = np.full((8, 8), 0.5, dtype=np.float32)
    img = ImageData.from_array(arr, mode=ImageMode.SINGLE_FLOAT, name="mid")
    backend._images[img.id] = img

    provider = TransImageProvider(backend)
    qi_wide = provider.requestImage(
        f"{img.id}?min=0&max=1", QSize(0, 0), QSize(),
    )
    qi_narrow = provider.requestImage(
        f"{img.id}?min=0.4&max=0.6", QSize(0, 0), QSize(),
    )
    # 0.5 in [0,1] → 127; 0.5 in [0.4,0.6] → 127 too (mid). Try shifting min.
    qi_high = provider.requestImage(
        f"{img.id}?min=0&max=0.5", QSize(0, 0), QSize(),
    )
    # 0.5 at the top of [0, 0.5] → 255
    assert qi_wide.pixelColor(4, 4).red() == 127
    assert qi_high.pixelColor(4, 4).red() == 255
