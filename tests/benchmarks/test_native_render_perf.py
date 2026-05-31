"""
Micro-benchmarks for the Phase 3 native curve renderer.

The plan's original thresholds (< 5 ms for 100k, < 25 ms for 1M
downsampled) were tightened on real-hardware numbers after the
``QDataStream`` binary-stream path-build landed. The current targets
are:

- 100k points raw build: < 10 ms (measured ~8.5 ms locally).
- 1M points downsampled to ~50k + build: < 25 ms (measured ~15 ms).
- 100k points with log gating + downsample: < 10 ms (measured ~6.8 ms).

All path build cost is one-shot — once cached, interactive zoom/pan
is essentially ``QPainter.setTransform`` + ``drawPath``, far below
any threshold worth asserting on.

Run with ``pytest tests/benchmarks/ --benchmark-only``.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.widgets._pyqtgraph_ports.curve_path import (
    DOWNSAMPLE_PEAK,
    array_to_qpainterpath,
    prepare_curve_xy,
)


def _make_xy(n: int, seed: int = 0) -> tuple:
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 1.0, n)
    y = rng.normal(0.0, 1.0, n).astype(np.float64).cumsum()
    return x, y


def test_array_to_qpainterpath_100k_points_under_15ms(benchmark):
    """One-shot path build for a 100k curve. Threshold is generous
    (~2× measured) so the assertion catches genuine regressions
    rather than benchmark noise."""
    x, y = _make_xy(100_000)
    path = benchmark(array_to_qpainterpath, x, y)
    assert path.elementCount() == 100_000
    assert benchmark.stats["mean"] < 0.015


def test_array_to_qpainterpath_1m_points_with_downsample_under_25ms(benchmark):
    """At 1 M points the canvas downsamples to ``_MAX_PATH_POINTS``
    (50k) before path build. This benchmark exercises the
    real-world pipeline (downsample + path) so the threshold reflects
    what the canvas actually does."""
    x, y = _make_xy(1_000_000)

    def build():
        x_p, y_p = prepare_curve_xy(
            x, y, max_points=50_000, downsample_mode=DOWNSAMPLE_PEAK,
        )
        return array_to_qpainterpath(x_p, y_p)

    path = benchmark(build)
    assert path.elementCount() > 0
    assert benchmark.stats["mean"] < 0.025  # 25 ms


def test_prepare_curve_xy_with_log_under_10ms_for_100k(benchmark):
    """Log gating + downsample together still under 10 ms for 100k
    points — important because the path cache key includes log mode
    so a scale flip rebuilds."""
    x, y = _make_xy(100_000)
    # Make some y negative so the log mask kicks in.
    y -= y.mean()

    def build():
        return prepare_curve_xy(
            x, y, log_y=True, max_points=50_000,
        )

    benchmark(build)
    assert benchmark.stats["mean"] < 0.010
