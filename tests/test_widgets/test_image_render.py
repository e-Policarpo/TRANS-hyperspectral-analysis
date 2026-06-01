"""
Tests for ``apply_levels_and_lut`` / ``downsample_image`` /
``levels_from_array``.

Pure NumPy — no Qt fixtures needed.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.widgets._pyqtgraph_ports.image_render import (
    apply_levels_and_lut,
    downsample_image,
    levels_from_array,
)


def _gray_lut() -> np.ndarray:
    return np.tile(np.arange(256, dtype=np.uint8)[:, None], (1, 3))


def _viridis_like_lut() -> np.ndarray:
    """Build a deterministic non-grayscale LUT for testing — R rises,
    G falls, B is constant. We just need *some* mapping that isn't
    identity so we can verify the index lookup."""
    lut = np.zeros((256, 3), dtype=np.uint8)
    lut[:, 0] = np.arange(256, dtype=np.uint8)
    lut[:, 1] = 255 - np.arange(256, dtype=np.uint8)
    lut[:, 2] = 64
    return lut


# --- apply_levels_and_lut ------------------------------------------

def test_gray_lut_pass_through_uint8_full_range():
    arr = np.arange(256, dtype=np.uint8).reshape(16, 16)
    out = apply_levels_and_lut(arr, levels=(0, 255), lut=_gray_lut())
    # Every output triple matches the input value.
    flat_in = arr.ravel()
    flat_out = out.reshape(-1, 3)
    assert np.array_equal(flat_out[:, 0], flat_in)
    assert np.array_equal(flat_out[:, 1], flat_in)
    assert np.array_equal(flat_out[:, 2], flat_in)


def test_levels_clip_below_lo_to_black():
    arr = np.array([[-100.0, 50.0, 200.0]], dtype=np.float32)
    out = apply_levels_and_lut(arr, levels=(0.0, 100.0), lut=_gray_lut())
    # -100 → clip to 0; 50 → mid; 200 → clip to 255.
    assert out[0, 0, 0] == 0
    assert out[0, 1, 0] in (127, 128)
    assert out[0, 2, 0] == 255


def test_levels_none_uses_array_min_max():
    arr = np.linspace(10.0, 100.0, 256, dtype=np.float32).reshape(16, 16)
    out = apply_levels_and_lut(arr, levels=None, lut=_gray_lut())
    # Min sample → 0, max sample → 255.
    assert out.min() == 0
    assert out.max() == 255


def test_uint16_input():
    arr = (np.arange(256, dtype=np.uint16) * 100).reshape(16, 16)
    out = apply_levels_and_lut(
        arr, levels=(0, 25500), lut=_gray_lut(),
    )
    assert out.dtype == np.uint8
    assert out[0, 0, 0] == 0
    assert out[-1, -1, 0] == 255


def test_nan_clamped_to_low():
    arr = np.array([[np.nan, 50.0]], dtype=np.float32)
    out = apply_levels_and_lut(arr, levels=(0.0, 100.0), lut=_gray_lut())
    # NaN normalises → NaN → cast to uint8 → 0.
    assert out[0, 0, 0] == 0


def test_real_lut_indexing():
    """Verify the LUT lookup is actually consulted, not the identity."""
    arr = np.array([[0, 128, 255]], dtype=np.uint8)
    out = apply_levels_and_lut(
        arr, levels=(0, 255), lut=_viridis_like_lut(),
    )
    # R rises with the index, G falls, B is constant at 64.
    assert tuple(out[0, 0]) == (0, 255, 64)
    assert tuple(out[0, 2]) == (255, 0, 64)
    assert out[0, 1, 2] == 64


def test_zero_span_uses_unit_span():
    """Degenerate levels (lo == hi) must not divide by zero."""
    arr = np.array([[42.0, 42.0]], dtype=np.float32)
    out = apply_levels_and_lut(
        arr, levels=(42.0, 42.0), lut=_gray_lut(),
    )
    # We don't care exactly what it produces — just that it didn't
    # raise. The internal pipeline replaces hi with lo+1.
    assert out.shape == (1, 2, 3)


def test_bad_dimensions_raises():
    with pytest.raises(ValueError):
        apply_levels_and_lut(
            np.zeros((4, 4, 4), dtype=np.uint8),
            levels=(0, 255), lut=_gray_lut(),
        )


def test_bad_lut_raises():
    with pytest.raises(ValueError):
        apply_levels_and_lut(
            np.zeros((4, 4), dtype=np.uint8),
            levels=(0, 255),
            lut=np.zeros((100, 3), dtype=np.uint8),  # wrong height
        )


# --- downsample_image ----------------------------------------------

def test_downsample_no_op_when_small_enough():
    arr = np.arange(16, dtype=np.float32).reshape(4, 4)
    out = downsample_image(arr, target_size=(8, 8))
    # Already smaller than target — returns array unchanged.
    assert out is arr


def test_downsample_mean_preserves_intensity():
    arr = np.ones((20, 20), dtype=np.float32) * 5.0
    out = downsample_image(arr, target_size=(5, 5))
    # 4x4 pool of constant → still 5.
    assert out.shape == (5, 5)
    assert np.allclose(out, 5.0)


def test_downsample_mean_actually_averages():
    arr = np.arange(16, dtype=np.float32).reshape(4, 4)
    out = downsample_image(arr, target_size=(2, 2), mode="mean")
    assert out.shape == (2, 2)
    # Top-left 2x2 block: 0,1,4,5 → mean 2.5.
    assert out[0, 0] == pytest.approx(2.5)


def test_downsample_subsample_picks_strided():
    arr = np.arange(16, dtype=np.float32).reshape(4, 4)
    out = downsample_image(arr, target_size=(2, 2), mode="subsample")
    assert out.shape == (2, 2)
    # Stride-2 subsample of (0..15) reshaped: top-left = arr[0, 0] = 0.
    assert out[0, 0] == 0.0
    assert out[1, 1] == arr[2, 2]


def test_downsample_invalid_mode_raises():
    arr = np.ones((10, 10), dtype=np.float32)
    with pytest.raises(ValueError):
        downsample_image(arr, target_size=(2, 2), mode="bicubic")


def test_downsample_bad_dimensions_raises():
    with pytest.raises(ValueError):
        downsample_image(
            np.zeros((4, 4, 3), dtype=np.uint8),
            target_size=(2, 2),
        )


# --- levels_from_array ---------------------------------------------

def test_levels_from_array_finite_only():
    arr = np.array([[1.0, 2.0, np.nan], [np.inf, 3.0, -np.inf]])
    lo, hi = levels_from_array(arr)
    assert lo == 1.0 and hi == 3.0


def test_levels_from_array_all_nan_returns_default():
    arr = np.array([[np.nan, np.nan]])
    lo, hi = levels_from_array(arr)
    assert lo == 0.0 and hi == 1.0
