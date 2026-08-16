"""
Tests for surface leveling — polynomial plane correction and facet reorientation.

These are the SPM background-removal tools shared by the map editor, the image
viewer and the file-based workflow path, so the algorithms are pinned here once.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest

from src.processing.plane_correction import (
    apply_leveling, facet_level, polynomial_level,
)


@pytest.fixture
def grid():
    """(Y, X) index grids for a 50×60 frame."""
    return np.mgrid[0:50, 0:60].astype(np.float64)


# ---------------------------------------------------------------------------
# polynomial_level
# ---------------------------------------------------------------------------

def test_plane_is_removed_to_noise_floor(grid):
    Y, X = grid
    noise = np.random.default_rng(1).normal(0, 0.01, X.shape)
    z = 3.0 * X + 2.0 * Y + 7.0 + noise
    out = polynomial_level(z, order=1)
    # Nothing but the noise should survive.
    assert np.std(out) == pytest.approx(0.01, abs=0.003)
    assert abs(np.mean(out)) < 0.01


def test_order_zero_removes_only_the_mean(grid):
    Y, X = grid
    z = 3.0 * X + 2.0 * Y + 7.0
    out = polynomial_level(z, order=0)
    assert np.mean(out) == pytest.approx(0.0, abs=1e-9)
    # The tilt must remain — order 0 is not a plane fit.
    assert np.std(out) == pytest.approx(np.std(z), rel=1e-9)


def test_high_order_fit_is_well_conditioned(grid):
    """The old inline fit used raw pixel indices, so an order-6 term with
    X~666 reached ~1e16 and the lstsq lost all precision. Normalised
    coordinates must reproduce a pure polynomial to near machine epsilon."""
    Y, X = grid
    z = (X / 59.0) ** 6 * 1e3 + (Y / 49.0) ** 5 * 500.0
    out = polynomial_level(z, order=6)
    assert np.abs(out).max() < 1e-6 * np.abs(z).max()


def test_curvature_needs_order_two(grid):
    """A bowed surface (scanner creep) is not removable by a plane."""
    Y, X = grid
    z = ((X - 30) / 30.0) ** 2 * 50.0
    assert np.std(polynomial_level(z, order=1)) > 1.0
    assert np.abs(polynomial_level(z, order=2)).max() < 1e-9


def test_nan_pixels_are_ignored_and_preserved(grid):
    Y, X = grid
    z = 3.0 * X + 2.0 * Y + 7.0
    z[0:5, 0:5] = np.nan
    out = polynomial_level(z, order=1)
    assert np.isnan(out[0:5, 0:5]).all(), "NaNs must be preserved"
    # The fit must still be exact on the finite part.
    assert np.nanmax(np.abs(out)) < 1e-9


def test_returns_input_when_too_few_finite_samples():
    z = np.full((4, 4), np.nan)
    z[0, 0] = 1.0
    out = polynomial_level(z, order=3)   # far more coefficients than samples
    np.testing.assert_array_equal(np.isnan(out), np.isnan(z))
    assert out[0, 0] == 1.0


def test_input_is_never_mutated(grid):
    Y, X = grid
    z = 3.0 * X + 2.0 * Y + 7.0
    before = z.copy()
    polynomial_level(z, order=2)
    np.testing.assert_array_equal(z, before)


def test_rejects_non_2d():
    with pytest.raises(ValueError):
        polynomial_level(np.arange(10.0), order=1)


# ---------------------------------------------------------------------------
# facet_level
# ---------------------------------------------------------------------------

def test_facet_level_flattens_dominant_terrace_and_keeps_the_step(grid):
    """The point of facet leveling: a step must NOT drag the correction off
    true the way a mean-plane fit does."""
    Y, X = grid
    z = 0.5 * X.copy()
    z[:, 30:] += 100.0          # a tall step over the right-hand third

    out = facet_level(z)
    # Dominant facet is now horizontal...
    assert np.ptp(out[:, :29]) < 1e-6
    # ...but the step itself is still there (it is real topography).
    assert out[:, 35].mean() - out[:, 10].mean() == pytest.approx(100.0, rel=1e-6)

    # A plane fit, by contrast, gets pulled by the step and leaves the
    # terrace tilted.
    assert np.ptp(polynomial_level(z, order=1)[:, :29]) > 1.0


def test_facet_level_is_robust_to_spikes(grid):
    Y, X = grid
    z = 0.5 * X + 0.25 * Y
    z[10, 10] = 1e6             # cosmic-ray-scale spike
    out = facet_level(z)
    finite = np.delete(out.ravel(), 10 * 60 + 10)
    assert np.ptp(finite) < 1e-6


def test_facet_level_input_not_mutated(grid):
    Y, X = grid
    z = 0.5 * X + 0.25 * Y
    before = z.copy()
    facet_level(z)
    np.testing.assert_array_equal(z, before)


def test_facet_level_handles_degenerate_shapes():
    assert facet_level(np.zeros((1, 5))).shape == (1, 5)
    assert facet_level(np.zeros((5, 1))).shape == (5, 1)


def test_facet_level_rejects_non_2d():
    with pytest.raises(ValueError):
        facet_level(np.arange(10.0))


# ---------------------------------------------------------------------------
# apply_leveling dispatch — the shared entry point for both viewers
# ---------------------------------------------------------------------------

def test_dispatch_plane_level_is_order_one(grid):
    Y, X = grid
    z = 3.0 * X + 2.0 * Y + 7.0
    np.testing.assert_allclose(
        apply_leveling('plane_level', z), polynomial_level(z, order=1))


def test_dispatch_poly_level_honours_order(grid):
    Y, X = grid
    z = ((X - 30) / 30.0) ** 3 * 20.0
    np.testing.assert_allclose(
        apply_leveling('poly_level', z, {'order': 3}),
        polynomial_level(z, order=3))
    # Default order is 2.
    np.testing.assert_allclose(
        apply_leveling('poly_level', z), polynomial_level(z, order=2))


def test_dispatch_accepts_workflow_alias(grid):
    """The file-based workflow path calls the operation
    ``polynomial_bg_removal``; it must hit the same code."""
    Y, X = grid
    z = ((X - 30) / 30.0) ** 2 * 20.0
    np.testing.assert_allclose(
        apply_leveling('polynomial_bg_removal', z, {'order': 2}),
        polynomial_level(z, order=2))


def test_dispatch_facet_level(grid):
    Y, X = grid
    z = 0.5 * X + 0.25 * Y
    assert np.ptp(apply_leveling('facet_level', z)) < 1e-6


def test_dispatch_unknown_operation_raises_keyerror(grid):
    Y, X = grid
    with pytest.raises(KeyError):
        apply_leveling('definitely_not_an_op', X)


def test_dispatch_tolerates_missing_params(grid):
    Y, X = grid
    assert apply_leveling('plane_level', X, None).shape == X.shape
    assert apply_leveling('facet_level', X, None).shape == X.shape
