"""
Tests for src.processing.spatial_coherence.

Both statistics decide how the per-point fits may be read, so both are tested
against fields whose answer is known by construction rather than against the
module's own output:

* The uniformity test gets points drawn from ONE true E0 with known error
  bars (must say uniform) and points drawn from two different ones (must say
  varying). The case that matters most is the third: no error bars at all,
  where the scatter is its own yardstick and the honest answer is "cannot
  tell" -- reporting uniform there would be the absence of an error bar
  talking, not the sample.
* The correlation length is measured on an AR(1) field, which has an
  exponential correlation function of exactly the length asked for, so the
  fitted xi has a true value to be checked against.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.processing.spatial_coherence import (
    MIN_POINTS_UNIFORMITY,
    UniformityResult,
    VariogramFit,
    coherence_columns,
    coherence_summary,
    e0_uniformity,
    semivariogram,
    v0_correlation_length,
)


def _ar1_field(n, dx_m, xi_m, sigma, seed):
    """A line of values with correlation exp(-h/xi) by construction.

    An AR(1) walk with ``a = exp(-dx/xi)`` has autocorrelation ``a**k =
    exp(-k dx / xi)``, i.e. exactly the exponential model the variogram fits.
    """
    rng = np.random.default_rng(seed)
    a = math.exp(-dx_m / xi_m)
    v = np.empty(n, dtype=np.float64)
    v[0] = rng.normal(0.0, sigma)
    for i in range(1, n):
        v[i] = a * v[i - 1] + rng.normal(0.0, sigma * math.sqrt(1.0 - a * a))
    return np.arange(n, dtype=np.float64) * dx_m, v


# ---------------------------------------------------------------------------
# Is the tail energy the same everywhere?
# ---------------------------------------------------------------------------

def test_one_true_e0_with_honest_error_bars_reads_uniform():
    rng = np.random.default_rng(11)
    truth, err = 0.022, 0.002
    e0 = truth + rng.normal(0.0, err, 24)

    r = e0_uniformity(e0, np.full(24, err))

    assert r.verdict == "uniform"
    assert r.weighted_mean_ev == pytest.approx(truth, abs=3 * err / math.sqrt(24))
    assert r.dof == 23
    assert r.p_value > 1e-3
    # No excess to report, and NaN rather than 0.0 so it cannot be read as
    # "measured to be zero".
    assert math.isnan(r.excess_scatter_ev)


def test_two_populations_read_varying():
    """Half the points at 18 meV, half at 30 meV, error bars of 2 meV: no
    single E0 describes them, which is what compositional disorder looks
    like and what a uniform zero-point term cannot produce."""
    rng = np.random.default_rng(12)
    err = 0.002
    e0 = np.concatenate([0.018 + rng.normal(0, err, 12),
                         0.030 + rng.normal(0, err, 12)])

    r = e0_uniformity(e0, np.full(24, err))

    assert r.verdict == "varying"
    assert r.p_value < 1e-3
    assert math.isfinite(r.excess_scatter_ev)
    assert r.excess_scatter_ev > err, "the excess must exceed the error bars"
    assert "compositional" in r.note


def test_without_error_bars_the_answer_is_undetermined_not_uniform():
    """The scatter cannot be its own yardstick. With no error bar the test can
    only ever conclude 'consistent', so it must decline instead -- otherwise a
    wildly varying sample comes back uniform purely for lack of a sigma."""
    e0 = np.array([0.005, 0.020, 0.045, 0.080, 0.011, 0.062])

    r = e0_uniformity(e0)

    assert r.verdict == "undetermined"
    assert math.isnan(r.p_value)
    assert "error bars" in r.note


def test_too_few_points_is_undetermined():
    r = e0_uniformity([0.022, 0.023], [0.002, 0.002])
    assert r.verdict == "undetermined"
    assert r.n_points < MIN_POINTS_UNIFORMITY


def test_non_finite_points_are_dropped_not_propagated():
    err = 0.002
    e0 = [0.022, np.nan, 0.023, np.inf, 0.021, 0.022, 0.0225]
    r = e0_uniformity(e0, [err] * 7)
    assert r.n_points == 5
    assert r.verdict == "uniform"


def test_a_scalar_error_bar_is_broadcast():
    rng = np.random.default_rng(13)
    e0 = 0.022 + rng.normal(0.0, 0.002, 20)
    assert (e0_uniformity(e0, 0.002).verdict
            == e0_uniformity(e0, np.full(20, 0.002)).verdict)


def test_mismatched_error_bar_length_is_refused():
    with pytest.raises(ValueError, match="points but"):
        e0_uniformity([0.02, 0.02, 0.02], [0.002, 0.002])


# ---------------------------------------------------------------------------
# How far does the landscape stay correlated?
# ---------------------------------------------------------------------------

def test_the_semivariogram_rises_from_near_zero_towards_the_variance():
    pos, v = _ar1_field(200, 0.5e-9, 8e-9, 0.01, seed=21)
    lag, gamma, counts = semivariogram(pos, v)

    assert lag.size >= 3
    assert np.all(np.diff(lag) > 0), "lag bins must be ordered"
    assert np.all(counts >= 2)
    assert gamma[0] < gamma[-1], "a correlated field must rise with lag"


def test_the_correlation_length_of_a_known_field_is_recovered():
    """AR(1) with xi = 8 nm sampled every 0.5 nm over 100 nm.

    Asserted on the MEDIAN over realisations, not on one draw. A single
    realisation of a random field has a noisy empirical variogram -- across 30
    seeds the fitted range spanned 3.4 to 28.3 nm around a true 8 nm -- so a
    per-draw assertion would be testing the seed rather than the estimator.
    The spread is the honest limitation and is recorded in the docstring; what
    is claimed here is only that the estimator is unbiased.
    """
    fits = [v0_correlation_length(*_ar1_field(200, 0.5e-9, 8e-9, 0.01, seed=s))
            for s in range(30)]
    resolved = [f for f in fits if math.isfinite(f.correlation_length_m)]

    assert len(resolved) >= 25, "the range should be measurable in most draws"
    xis = np.array([f.correlation_length_m for f in resolved])
    assert float(np.median(xis)) == pytest.approx(8e-9, rel=0.3)
    assert fits[0].n_points == 200


def test_one_realisation_is_only_an_order_of_magnitude():
    """Pinning the limitation so it cannot quietly become a quoted parameter:
    the per-draw scatter is large, and a caller reading a single xi as a
    material constant is reading noise."""
    xis = np.array([v0_correlation_length(
        *_ar1_field(200, 0.5e-9, 8e-9, 0.01, seed=s)).correlation_length_m
        for s in range(30)])
    xis = xis[np.isfinite(xis)]

    assert xis.max() / xis.min() > 3.0, (
        "if this ever tightens, the docstring's factor-of-two-to-three "
        "warning is too pessimistic and should be revised")


def test_a_field_correlated_beyond_the_scan_is_reported_unresolved():
    """The good case for the level ratios, and the one most easily faked: the
    variogram is still climbing at the largest lag, so all that can honestly
    be said is 'longer than the scan'."""
    pos = np.linspace(0.0, 20e-9, 40)
    v0 = 0.05 + 1e-3 * (pos / 20e-9)          # a smooth ramp, no roll-off

    fit = v0_correlation_length(pos, v0)

    assert fit.verdict == "unresolved"
    assert math.isnan(fit.correlation_length_m), "no number may be quoted"
    assert "longer than the field" in fit.note


def test_white_noise_puts_its_variance_in_the_nugget():
    """An uncorrelated field has no spatial structure to find: the variogram
    is flat and the fit should attribute the scatter to the nugget, which is
    measurement noise, rather than to a correlated sill."""
    rng = np.random.default_rng(23)
    pos = np.linspace(0.0, 100e-9, 200)
    v0 = rng.normal(0.05, 0.004, 200)

    fit = v0_correlation_length(pos, v0)

    assert fit.nugget_ev2 > 0.0
    assert fit.nugget_ev2 == pytest.approx(0.004 ** 2, rel=0.6)
    assert fit.sill_ev2 < fit.nugget_ev2, "no correlated component to find"


def test_two_dimensional_positions_are_accepted():
    rng = np.random.default_rng(24)
    xy = rng.uniform(0.0, 50e-9, size=(120, 2))
    v0 = 0.05 + 1e-3 * np.exp(-np.linalg.norm(xy - 25e-9, axis=1) / 10e-9)

    lag, gamma, counts = semivariogram(xy, v0)
    assert lag.size >= 3
    assert v0_correlation_length(xy, v0).n_points == 120


def test_too_few_points_gives_no_correlation_length():
    pos = np.linspace(0.0, 10e-9, 4)
    fit = v0_correlation_length(pos, [0.05, 0.051, 0.049, 0.05])
    assert fit.verdict == "undetermined"
    assert math.isnan(fit.correlation_length_m)


def test_positions_and_values_must_agree_in_length():
    with pytest.raises(ValueError, match="positions but"):
        semivariogram([0.0, 1e-9, 2e-9], [0.05, 0.05])


def test_coincident_positions_do_not_divide_by_zero():
    pos = np.zeros(12)
    lag, gamma, counts = semivariogram(pos, np.linspace(0.05, 0.06, 12))
    assert lag.size == 0 and gamma.size == 0


# ---------------------------------------------------------------------------
# The flat row
# ---------------------------------------------------------------------------

def test_the_summary_row_keeps_its_shape_when_half_the_inputs_are_missing():
    rng = np.random.default_rng(31)
    e0 = 0.022 + rng.normal(0.0, 0.002, 20)

    with_pos = coherence_summary(e0, 0.002, *_ar1_field(20, 2e-9, 8e-9, 0.01, 32))
    without = coherence_summary(e0, 0.002)

    for key in coherence_columns():
        assert key in with_pos and key in without
    assert math.isnan(without["v0_correlation_length_m"])
    assert without["v0_verdict"] == "undetermined"
    assert with_pos["e0_verdict"] == without["e0_verdict"] == "uniform"


def test_the_column_order_is_stable():
    cols = coherence_columns()
    assert cols[0] == "n_points"
    assert len(set(cols)) == len(cols)
    assert "e0_verdict" in cols and "v0_verdict" in cols
