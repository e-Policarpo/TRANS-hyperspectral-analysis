"""
Tests for the ``curve_path`` algorithm port.

The build-side functions are pure-NumPy plus a thin ``QPainterPath``
construction. Tests:

- ``apply_log_scale`` masks non-positive samples to ``NaN`` *before*
  taking ``log10`` — the path builder then splits at the NaN so a
  curve crossing zero doesn't render as garbage in log mode;
- ``array_to_qpainterpath`` builds a path of the expected
  vertex count for clean input;
- the path SPLITS at NaN (each finite run becomes its own sub-path),
  so the total element count equals (# finite samples) +
  (# finite runs - 1) MoveTos;
- ``downsample`` honours the three modes (subsample / mean / peak);
- ``prepare_curve_xy`` composes the log + downsample pipeline.
"""

from __future__ import annotations

import numpy as np
import pytest

from PySide6.QtGui import QPainterPath  # noqa: F401  (sanity import)

from src.widgets._pyqtgraph_ports.curve_path import (
    DOWNSAMPLE_MEAN,
    DOWNSAMPLE_PEAK,
    DOWNSAMPLE_SUBSAMPLE,
    apply_log_scale,
    array_to_qpainterpath,
    downsample,
    prepare_curve_xy,
)


# --- apply_log_scale ---------------------------------------------------

def test_apply_log_scale_off_is_passthrough():
    arr = np.array([1.0, 2.0, 3.0])
    out = apply_log_scale(arr, log=False)
    assert np.allclose(out, arr)
    # Returns a copy so the caller can mutate freely.
    out[0] = 99.0
    assert arr[0] == 1.0


def test_apply_log_scale_on_takes_log10():
    arr = np.array([1.0, 10.0, 100.0])
    out = apply_log_scale(arr, log=True)
    assert np.allclose(out, [0.0, 1.0, 2.0])


def test_apply_log_scale_masks_non_positive_to_nan():
    arr = np.array([10.0, 0.0, -3.0, 100.0])
    out = apply_log_scale(arr, log=True)
    assert out[0] == pytest.approx(1.0)
    assert np.isnan(out[1])     # zero → NaN
    assert np.isnan(out[2])     # negative → NaN
    assert out[3] == pytest.approx(2.0)


# --- array_to_qpainterpath ---------------------------------------------

def test_path_empty_when_fewer_than_two_points():
    p = array_to_qpainterpath(np.array([1.0]), np.array([2.0]))
    assert p.elementCount() == 0


def test_path_continuous_for_finite_input():
    """N finite samples → one MoveTo + (N-1) LineTos."""
    n = 50
    x = np.linspace(0.0, 10.0, n)
    y = np.sin(x)
    p = array_to_qpainterpath(x, y)
    assert p.elementCount() == n


def test_path_splits_at_nan():
    """A single NaN in the middle should split into two segments."""
    x = np.linspace(0.0, 9.0, 10)
    y = x.copy()
    y[5] = np.nan
    p = array_to_qpainterpath(x, y)
    # Two finite runs of length 5 and 4 → 5 + 4 elements total
    # (each MoveTo + subsequent LineTos).
    assert p.elementCount() == 9


def test_path_multiple_nan_runs():
    """NaN runs should be skipped, finite runs become separate paths."""
    x = np.arange(20, dtype=np.float64)
    y = x.copy()
    y[5:8] = np.nan       # break 1
    y[12:15] = np.nan     # break 2
    p = array_to_qpainterpath(x, y)
    # Finite runs: 0..4 (5), 8..11 (4), 15..19 (5) → 14 elements total.
    assert p.elementCount() == 14


def test_path_handles_all_nan_input():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([np.nan, np.nan, np.nan])
    p = array_to_qpainterpath(x, y)
    assert p.elementCount() == 0


def test_path_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        array_to_qpainterpath(np.array([1.0, 2.0]), np.array([1.0]))


def test_path_handles_chunked_large_curve():
    """Curves above the chunk-size threshold still produce a single
    contiguous path (the chunked builder joins sub-paths with
    ``connectPath`` so segment count == vertex count)."""
    n = 25_000  # well above the 10k chunk threshold
    x = np.linspace(0.0, 1.0, n)
    y = np.sin(x * 100)
    p = array_to_qpainterpath(x, y)
    # Joined contiguous; vertex count matches the input.
    assert p.elementCount() == n


# --- downsample --------------------------------------------------------

def test_downsample_noop_when_already_short():
    x = np.linspace(0.0, 1.0, 100)
    y = np.cos(x)
    xd, yd = downsample(x, y, target_n=200)
    assert xd is x
    assert yd is y


def test_downsample_subsample_takes_every_nth():
    x = np.arange(100, dtype=np.float64)
    y = x.copy()
    xd, yd = downsample(x, y, target_n=10, mode=DOWNSAMPLE_SUBSAMPLE)
    # stride = ceil(100/10) = 10
    assert len(xd) == 10
    assert np.allclose(xd, np.arange(0, 100, 10))


def test_downsample_mean_block_averages():
    x = np.arange(20, dtype=np.float64)
    y = x.copy()
    xd, yd = downsample(x, y, target_n=4, mode=DOWNSAMPLE_MEAN)
    # stride = 5; means of [0..4], [5..9], [10..14], [15..19]
    assert np.allclose(xd, [2, 7, 12, 17])
    assert np.allclose(yd, [2, 7, 12, 17])


def test_downsample_peak_emits_two_per_block():
    """Peak mode pairs the block min with the block max so the curve
    still traces the local extremes after reduction."""
    n = 40
    x = np.arange(n, dtype=np.float64)
    y = np.array([0.0, 5.0] * (n // 2))   # alternating 0 / 5
    xd, yd = downsample(x, y, target_n=10, mode=DOWNSAMPLE_PEAK)
    # stride = ceil(40 / 10) = 4 → 10 blocks → 20 output samples
    # (two per block: min, max).
    assert len(xd) == 20
    # Min of every block is 0; max is 5.
    assert np.allclose(yd[0::2], 0.0)
    assert np.allclose(yd[1::2], 5.0)


def test_downsample_rejects_unknown_mode():
    x = np.arange(100, dtype=np.float64)
    with pytest.raises(ValueError):
        downsample(x, x, target_n=10, mode="median-or-something")


# --- prepare_curve_xy --------------------------------------------------

def test_prepare_curve_xy_composes_log_and_downsample():
    n = 1000
    x = np.linspace(1.0, 1000.0, n)
    y = np.linspace(1.0, 1000.0, n)
    x_p, y_p = prepare_curve_xy(
        x, y, log_x=True, log_y=False,
        max_points=50, downsample_mode=DOWNSAMPLE_SUBSAMPLE,
    )
    # Log applied to x but not y.
    assert x_p[0] == pytest.approx(np.log10(1.0))
    assert y_p[0] == pytest.approx(1.0)
    # Downsampled to ~ target_n.
    assert len(x_p) <= 50 + 10


def test_prepare_curve_xy_passes_through_when_no_downsample():
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([10.0, 20.0, 30.0])
    x_p, y_p = prepare_curve_xy(x, y)
    assert np.allclose(x_p, x)
    assert np.allclose(y_p, y)
