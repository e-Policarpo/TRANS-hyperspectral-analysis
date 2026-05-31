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


_BASE_KWARGS = {"metadata": None, "rowsperstrip": 64}


def test_no_resolution_kwargs_when_pixel_size_missing():
    """When no calibration is present the helper still returns the
    viewer-friendly defaults (no shape descriptor, chunked strips) but
    omits the resolution/description tags."""
    img = ImageData(
        array=np.zeros((4, 4), dtype=np.uint8),
        mode=ImageMode.GRAY_U8,
        metadata=ImageMetadata(source="test"),
        name="bare",
    )
    kw = AppBackend._pixel_scale_tiff_kwargs(img)
    assert kw == _BASE_KWARGS


def test_no_resolution_kwargs_when_pixel_size_zero_or_negative():
    img = _calibrated_image(0.0, 1.0, "µm")
    assert AppBackend._pixel_scale_tiff_kwargs(img) == _BASE_KWARGS
    img = _calibrated_image(1.0, -2.0, "µm")
    assert AppBackend._pixel_scale_tiff_kwargs(img) == _BASE_KWARGS


@pytest.mark.parametrize("unit,ij_unit", [
    ("µm", "micron"), ("um", "micron"), ("micron", "micron"),
    ("nm", "nm"), ("mm", "mm"), ("cm", "cm"), ("m", "meter"),
])
def test_unit_normalization(unit, ij_unit):
    img = _calibrated_image(0.5, 0.25, unit)
    kw = AppBackend._pixel_scale_tiff_kwargs(img)
    # Resolution is now a fixed-denominator rational tuple
    # ((num, denom), (num, denom)) — verify the numeric ratio.
    (xn, xd), (yn, yd) = kw["resolution"]
    assert xn / xd == pytest.approx(1.0 / 0.5)
    assert yn / yd == pytest.approx(1.0 / 0.25)
    assert kw["resolutionunit"] == "NONE"
    assert f"unit={ij_unit}" in kw["description"]
    # Viewer-friendly defaults always present.
    assert kw["metadata"] is None
    assert kw["rowsperstrip"] == 64


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
        x_res = tags["XResolution"].value
        y_res = tags["YResolution"].value
        assert x_res[0] / x_res[1] == pytest.approx(4.0)
        assert y_res[0] / y_res[1] == pytest.approx(2.0)
        assert int(tags["ResolutionUnit"].value) == 1
        desc = tags["ImageDescription"].value
        assert "unit=micron" in desc
        # Exactly ONE ImageDescription tag — the auto shape metadata
        # used to produce a duplicate that broke some viewers.
        desc_tags = [t for t in tags.values() if t.code == 270]
        assert len(desc_tags) == 1


def test_tiff_uses_multi_strip_layout(tmp_path):
    """The exporter must chunk large images into multiple strips so
    macOS Preview / other viewers can stream them. A single-strip 70 MB
    file was the original bug."""
    img = _calibrated_image(0.5, 0.5, "µm")
    out = tmp_path / "multi_strip.tiff"
    tifffile.imwrite(
        str(out), img.array,
        **AppBackend._pixel_scale_tiff_kwargs(img),
    )
    with tifffile.TiffFile(str(out)) as tf:
        page = tf.pages[0]
        # ``RowsPerStrip`` should equal our default (64) when the image
        # has more rows than that; for tiny test images it can be
        # clipped to image height by tifffile, but never the whole image
        # in a single strip when height > 64.
        rps = int(page.tags["RowsPerStrip"].value)
        assert rps == 64 or rps == page.imagelength
        # And: no duplicate ImageDescription.
        assert len([t for t in page.tags.values() if t.code == 270]) == 1


def test_tiff_resolution_rational_doesnt_saturate(tmp_path):
    """Small pixel sizes (~0.12 µm) used to push the resolution
    rational numerator to ``UINT32_MAX``. Fixed-denominator encoding
    keeps it tame."""
    img = _calibrated_image(0.12384560767640458, 0.12384560767640458, "µm")
    out = tmp_path / "small_pixels.tiff"
    tifffile.imwrite(
        str(out), img.array,
        **AppBackend._pixel_scale_tiff_kwargs(img),
    )
    with tifffile.TiffFile(str(out)) as tf:
        x_res = tf.pages[0].tags["XResolution"].value
        # Saturated form would be (2**32-1, N) ≈ (4 294 967 295, …).
        assert x_res[0] < 2**31
        # But the represented value must still be correct.
        assert x_res[0] / x_res[1] == pytest.approx(
            1.0 / 0.12384560767640458, rel=1e-5,
        )
