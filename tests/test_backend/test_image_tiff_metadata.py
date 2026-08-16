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


# ---------------------------------------------------------------------------
# Display range — float maps used to open all-black
# ---------------------------------------------------------------------------

def _float_image(dx=None, dy=None, unit=None, pixel_size_nm=None) -> ImageData:
    """A float32 map of physical values (~1e-9), the all-black case."""
    rng = np.random.default_rng(0)
    arr = (rng.normal(0.0, 1.0, (80, 64)).astype(np.float32) * 1e-9) + 5e-9
    info = {}
    if dx is not None:
        info["pixel_size"] = {"dx": dx, "dy": dy, "unit": unit}
    meta = ImageMetadata(source="omicron_mtrx", additional_info=info)
    if pixel_size_nm is not None:
        meta.pixel_size_nm = pixel_size_nm
    return ImageData(array=arr, mode=ImageMode.SINGLE_FLOAT, metadata=meta, name="zmap")


def test_float_image_gets_display_range():
    """float32 physical values carry no implicit range, so viewers render them
    black. A min/max must be embedded."""
    img = _float_image(dx=0.5, dy=0.5, unit="nm")
    desc = AppBackend._pixel_scale_tiff_kwargs(img)["description"]
    assert "min=" in desc and "max=" in desc
    lo = float(desc.split("min=")[1].split("\n")[0])
    hi = float(desc.split("max=")[1].split("\n")[0])
    assert hi > lo
    # Range must bracket the bulk of the data, in physical units (~1e-9).
    assert lo == pytest.approx(np.percentile(img.array, 1), rel=1e-6)
    assert hi == pytest.approx(np.percentile(img.array, 99), rel=1e-6)


def test_display_range_is_robust_to_outliers():
    """A single hot pixel must not flatten the contrast of everything else —
    that is what the 1–99 % clip is for."""
    img = _float_image(dx=0.5, dy=0.5, unit="nm")
    img.array[0, 0] = 1e3          # cosmic-ray-scale spike
    desc = AppBackend._pixel_scale_tiff_kwargs(img)["description"]
    hi = float(desc.split("max=")[1].split("\n")[0])
    assert hi < 1e-6, "display max chased the outlier instead of clipping it"


def test_integer_image_gets_no_display_range():
    """Integer data already displays correctly; a range would be noise."""
    img = _calibrated_image(0.5, 0.5, "µm")   # uint16
    desc = AppBackend._pixel_scale_tiff_kwargs(img)["description"]
    assert "min=" not in desc and "max=" not in desc


def test_display_range_survives_round_trip(tmp_path):
    """Written file must expose the range as ImageJ metadata, and the real
    float values must come back bit-for-bit."""
    img = _float_image(dx=0.5, dy=0.5, unit="nm")
    out = tmp_path / "zmap.tiff"
    tifffile.imwrite(
        str(out), img.array,
        **AppBackend._pixel_scale_tiff_kwargs(img),
    )
    with tifffile.TiffFile(str(out)) as tf:
        ij = tf.imagej_metadata
        assert ij is not None and "min" in ij and "max" in ij
        assert ij["unit"] == "nm"
        assert len([t for t in tf.pages[0].tags.values() if t.code == 270]) == 1
    assert np.array_equal(tifffile.imread(str(out)), img.array)


def test_data_override_drives_display_range():
    """When something other than ``image.array`` is written (an overlay
    composite, a converted map), the range must come from what is actually
    being written."""
    img = _float_image(dx=0.5, dy=0.5, unit="nm")
    other = np.full((10, 10), 42.0, dtype=np.float32)
    desc = AppBackend._pixel_scale_tiff_kwargs(img, data=other)["description"]
    lo = float(desc.split("min=")[1].split("\n")[0])
    hi = float(desc.split("max=")[1].split("\n")[0])
    # Constant array: helper must still emit a non-degenerate range.
    assert lo == pytest.approx(42.0)
    assert hi > lo


# ---------------------------------------------------------------------------
# pixel_size_nm fallback — how Omicron scan images carry their scale
# ---------------------------------------------------------------------------

def test_pixel_size_nm_fallback_supplies_scale():
    """Omicron images carry scale on ``metadata.pixel_size_nm`` (dy, dx) rather
    than the ``pixel_size`` dict; without the fallback they exported uncalibrated."""
    img = _float_image(pixel_size_nm=(0.25, 0.5))    # (dy, dx) nm
    dx, dy, unit = AppBackend._image_pixel_scale(img)
    assert (dx, dy, unit) == (0.5, 0.25, "nm")
    kw = AppBackend._pixel_scale_tiff_kwargs(img)
    (xn, xd), (yn, yd) = kw["resolution"]
    assert xn / xd == pytest.approx(1.0 / 0.5)
    assert yn / yd == pytest.approx(1.0 / 0.25)
    assert "unit=nm" in kw["description"]


def test_pixel_size_dict_wins_over_pixel_size_nm():
    """An explicit pixel_size dict is the more specific source."""
    img = _float_image(dx=2.0, dy=4.0, unit="µm", pixel_size_nm=(0.25, 0.5))
    assert AppBackend._image_pixel_scale(img) == (2.0, 4.0, "µm")


def test_pixel_size_nm_ignored_when_incomplete():
    img = _float_image(pixel_size_nm=(0.0, 0.5))
    assert AppBackend._image_pixel_scale(img) == (None, None, None)
