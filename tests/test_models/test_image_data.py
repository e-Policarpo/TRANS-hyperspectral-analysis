"""
Tests for the ImageData model.

Covers:
- Mode inference / coercion contracts
- Crop, histogram, auto_range
- ``to_bytes`` / ``from_dict`` round-trip for every mode
- ``from_file`` decoding via PIL / tifffile
- ``from_map_channel`` factory

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

from src.models.image_data import (
    ImageData,
    ImageMetadata,
    ImageMode,
)


# =============================================================================
# Construction & mode inference
# =============================================================================

def test_infer_mode_from_rgb_array():
    arr = np.zeros((4, 6, 3), dtype=np.uint8)
    img = ImageData.from_array(arr)
    assert img.mode == ImageMode.RGB
    assert img.shape == (4, 6, 3)
    assert img.height == 4 and img.width == 6
    assert img.n_channels == 3


def test_infer_mode_from_rgba_array():
    arr = np.zeros((4, 6, 4), dtype=np.uint8)
    img = ImageData.from_array(arr)
    assert img.mode == ImageMode.RGBA
    assert img.n_channels == 4


def test_infer_mode_from_uint8_grayscale():
    arr = np.zeros((4, 6), dtype=np.uint8)
    img = ImageData.from_array(arr)
    assert img.mode == ImageMode.GRAY_U8
    assert img.n_channels == 1


def test_infer_mode_from_uint16_grayscale():
    arr = np.zeros((4, 6), dtype=np.uint16)
    img = ImageData.from_array(arr)
    assert img.mode == ImageMode.GRAY_U16


def test_infer_mode_from_float_array():
    arr = np.zeros((4, 6), dtype=np.float64)
    img = ImageData.from_array(arr)
    assert img.mode == ImageMode.SINGLE_FLOAT
    assert img.dtype == np.float32  # coerced down to float32


def test_explicit_mode_mismatch_raises():
    arr = np.zeros((4, 6), dtype=np.uint8)  # 2D
    with pytest.raises(ValueError):
        ImageData.from_array(arr, mode=ImageMode.RGB)


def test_id_is_unique_and_stable():
    img1 = ImageData.from_array(np.zeros((4, 6), dtype=np.uint8))
    img2 = ImageData.from_array(np.zeros((4, 6), dtype=np.uint8))
    assert img1.id != img2.id
    assert img1.id == img1.id  # stable across reads


# =============================================================================
# Crop
# =============================================================================

def test_crop_returns_new_image():
    arr = np.arange(20 * 30, dtype=np.uint8).reshape(20, 30)
    img = ImageData.from_array(arr)
    cropped = img.crop(5, 2, 15, 12)
    assert cropped.shape == (10, 10)
    assert np.array_equal(cropped.array, arr[2:12, 5:15])
    # Original unchanged.
    assert img.shape == (20, 30)
    # Origin recorded in metadata.
    assert cropped.metadata.additional_info["crop_origin"] == (5, 2)


def test_crop_clamps_to_bounds():
    arr = np.zeros((10, 10), dtype=np.uint8)
    img = ImageData.from_array(arr)
    cropped = img.crop(-100, -100, 1000, 1000)
    assert cropped.shape == (10, 10)


def test_crop_empty_raises():
    arr = np.zeros((10, 10), dtype=np.uint8)
    img = ImageData.from_array(arr)
    with pytest.raises(ValueError):
        img.crop(5, 5, 5, 5)


def test_crop_preserves_mode():
    arr = np.random.rand(5, 7).astype(np.float32)
    img = ImageData.from_array(arr)
    cropped = img.crop(1, 1, 4, 4)
    assert cropped.mode == ImageMode.SINGLE_FLOAT


# =============================================================================
# Histogram
# =============================================================================

def test_histogram_single_channel_default_range():
    arr = np.array([[0, 1, 2, 3], [4, 5, 6, 7]], dtype=np.uint8)
    img = ImageData.from_array(arr)
    counts, edges = img.histogram(bins=8)
    assert counts.sum() == arr.size
    assert len(edges) == 9


def test_histogram_rgb_uses_luminance_proxy():
    arr = np.zeros((2, 2, 3), dtype=np.uint8)
    arr[..., 0] = 255  # red
    img = ImageData.from_array(arr)
    counts, edges = img.histogram(bins=4)
    assert counts.sum() == 4  # one entry per pixel


def test_auto_range_robust_to_outliers():
    arr = np.zeros((100, 100), dtype=np.float32)
    arr[0, 0] = 1e6  # single huge outlier
    img = ImageData.from_array(arr)
    lo, hi = img.auto_range(percentile=2.0)
    # 2% percentile clip should ignore the outlier.
    assert hi < 1e6


# =============================================================================
# Persistence (to_dict / from_dict)
# =============================================================================

@pytest.mark.parametrize("mode,arr", [
    (ImageMode.RGB, np.random.randint(0, 255, (8, 12, 3), dtype=np.uint8)),
    (ImageMode.RGBA, np.random.randint(0, 255, (8, 12, 4), dtype=np.uint8)),
    (ImageMode.GRAY_U8, np.random.randint(0, 255, (8, 12), dtype=np.uint8)),
    (ImageMode.GRAY_U16, np.random.randint(0, 65535, (8, 12), dtype=np.uint16)),
    (ImageMode.SINGLE_FLOAT, np.random.rand(8, 12).astype(np.float32) * 100),
])
def test_to_dict_from_dict_round_trip(mode, arr):
    """Every mode should round-trip pixel-exact through serialization."""
    img = ImageData(array=arr, mode=mode, name="rt-test")
    payload = img.to_dict()
    restored = ImageData.from_dict(payload)
    assert restored.id == img.id
    assert restored.name == img.name
    assert restored.mode == mode
    assert restored.shape == img.shape
    assert restored.dtype == img.dtype
    assert np.array_equal(restored.array, img.array)


def test_to_bytes_single_float_uses_raw_format():
    arr = np.random.rand(4, 6).astype(np.float32)
    img = ImageData.from_array(arr)
    fmt, raw = img.to_bytes()
    assert fmt == "f32_raw"
    assert len(raw) == arr.size * 4


def test_to_bytes_rgb_uses_png():
    arr = np.zeros((4, 6, 3), dtype=np.uint8)
    img = ImageData.from_array(arr)
    fmt, raw = img.to_bytes()
    assert fmt == "png"
    assert raw.startswith(b"\x89PNG")


# =============================================================================
# Factories: from_file, from_map_channel
# =============================================================================

def test_from_file_png(tmp_path):
    # Build a synthetic PNG and read it back.
    pil = pytest.importorskip("PIL.Image")
    arr = np.tile(np.arange(0, 256, dtype=np.uint8), (10, 1))
    pil.fromarray(arr, mode="L").save(tmp_path / "scan.png")
    img = ImageData.from_file(tmp_path / "scan.png")
    assert img.mode == ImageMode.GRAY_U8
    assert img.shape == (10, 256)
    assert img.metadata.original_filename == "scan.png"
    assert img.name == "scan"


def test_from_file_float_tiff(tmp_path):
    tifffile = pytest.importorskip("tifffile")
    arr = np.random.rand(8, 16).astype(np.float32)
    f = tmp_path / "z.tif"
    tifffile.imwrite(str(f), arr)
    img = ImageData.from_file(f)
    assert img.mode == ImageMode.SINGLE_FLOAT
    assert np.array_equal(img.array, arr)


def test_from_map_channel_preserves_data():
    channel = (np.random.rand(20, 30) * 1e-9).astype(np.float32)
    img = ImageData.from_map_channel(
        channel, map_name="topography", channel_name="Z",
        pixel_size_nm=(1.5, 1.5),
    )
    assert img.mode == ImageMode.SINGLE_FLOAT
    assert np.array_equal(img.array, channel)
    assert img.metadata.source == "map_channel"
    assert img.metadata.pixel_size_nm == (1.5, 1.5)
    assert img.metadata.additional_info["map_name"] == "topography"
    assert img.metadata.additional_info["channel_name"] == "Z"
    assert img.name == "topography · Z (raw)"


def test_from_map_channel_rejects_3d():
    with pytest.raises(ValueError):
        ImageData.from_map_channel(
            np.zeros((4, 4, 3), dtype=np.float32),
            map_name="m", channel_name="c",
        )


# =============================================================================
# Serialization edge cases
# =============================================================================

def test_round_trip_metadata_preserves_dict():
    arr = np.zeros((4, 4), dtype=np.float32)
    meta = ImageMetadata(
        source="test", original_filename="x.tif",
        pixel_size_nm=(0.5, 0.5),
        additional_info={"custom_key": [1, 2, 3], "flag": True},
    )
    img = ImageData(array=arr, metadata=meta, name="x")
    restored = ImageData.from_dict(img.to_dict())
    assert restored.metadata.source == "test"
    assert restored.metadata.pixel_size_nm == (0.5, 0.5)
    assert restored.metadata.additional_info == {
        "custom_key": [1, 2, 3], "flag": True,
    }
