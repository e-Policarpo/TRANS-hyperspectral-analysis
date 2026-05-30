"""
Tests for the µm/pixel TIFF metadata that AppBackend stamps on every
ImageData it persists.

Covers _pixel_scale_tiff_kwargs in isolation (no QApplication needed) and
asserts that a TIFF written with those kwargs round-trips through tifffile
with the expected XResolution / YResolution / ImageDescription tags.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest

tifffile = pytest.importorskip("tifffile")

from src.backend.app_backend import AppBackend
from src.models.image_data import ImageData, ImageMetadata, ImageMode


def _calibrated_image(dx: float, dy: float, unit: str) -> ImageData:
    arr = np.arange(48, dtype=np.uint16).reshape(6, 8) * 100
    meta = ImageMetadata(
        source="witec_wip_bitmap",
        additional_info={
            "pixel_size": {"dx": dx, "dy": dy, "unit": unit},
        },
    )
    return ImageData(array=arr, mode=ImageMode.GRAY_U16, metadata=meta, name="probe")


def test_no_kwargs_when_pixel_size_missing():
    img = ImageData(
        array=np.zeros((4, 4), dtype=np.uint8),
        mode=ImageMode.GRAY_U8,
        metadata=ImageMetadata(source="test"),
        name="bare",
    )
    assert AppBackend._pixel_scale_tiff_kwargs(img) == {}


def test_no_kwargs_when_pixel_size_zero_or_negative():
    img = _calibrated_image(0.0, 1.0, "µm")
    assert AppBackend._pixel_scale_tiff_kwargs(img) == {}
    img = _calibrated_image(1.0, -2.0, "µm")
    assert AppBackend._pixel_scale_tiff_kwargs(img) == {}


@pytest.mark.parametrize("unit,ij_unit", [
    ("µm", "micron"), ("um", "micron"), ("micron", "micron"),
    ("nm", "nm"), ("mm", "mm"), ("cm", "cm"), ("m", "meter"),
])
def test_unit_normalization(unit, ij_unit):
    img = _calibrated_image(0.5, 0.25, unit)
    kw = AppBackend._pixel_scale_tiff_kwargs(img)
    # Pixels-per-unit: 1/dx, 1/dy
    assert kw["resolution"] == (1.0 / 0.5, 1.0 / 0.25)
    assert kw["resolutionunit"] == "NONE"
    assert f"unit={ij_unit}" in kw["description"]


def test_tiff_round_trip_carries_scale(tmp_path):
    """Write through tifffile, read back, confirm tags + description survive."""
    img = _calibrated_image(0.25, 0.5, "µm")  # 4 px/µm x, 2 px/µm y
    out = tmp_path / "probe.tiff"
    tifffile.imwrite(
        str(out), img.array,
        **AppBackend._pixel_scale_tiff_kwargs(img),
    )

    with tifffile.TiffFile(str(out)) as tf:
        page = tf.pages[0]
        tags = page.tags
        x_res = tags["XResolution"].value  # rational (num, den)
        y_res = tags["YResolution"].value
        # Reduce to a float so the comparison survives tifffile's rationalization.
        assert x_res[0] / x_res[1] == pytest.approx(4.0)
        assert y_res[0] / y_res[1] == pytest.approx(2.0)
        # ResolutionUnit=NONE → tag value 1 ("no absolute unit")
        assert int(tags["ResolutionUnit"].value) == 1
        desc = tags["ImageDescription"].value
        assert "unit=micron" in desc
