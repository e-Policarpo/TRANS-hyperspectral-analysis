"""
Tests for src.processing.edge_analysis, written against the physics.

The module exists to stop a thermometer being reported as a material
property, so the tests are built the same way round: wherever there is a
closed form, the closed form is the oracle and the module is checked against
it, not against itself.

* The thermal ceiling is checked against a *derived* curve rather than a
  formula. Convolving a step density of states with ``-df/dE`` gives exactly
  ``g(E) = 1/(1 + exp(-E/k_B T))``, whose log-slope tends to ``1/k_B T`` deep
  in the tail. :func:`thermal_slope_ceiling` has to reproduce that number, and
  the measured slope must never exceed it.
* The modulation width is checked by measuring the FWHM of the semi-ellipse
  kernel itself, and the thermal one against ``4 ln(1 + sqrt 2) k_B T``, so a
  mistyped constant cannot pass.

Three failure modes the spec names as the worst are pinned down explicitly:

* **A single exponential branch cannot locate a band edge.** ``ln g = c -
  |V - V0|/E0`` is exactly degenerate in ``(c, V0)``; the test builds two
  parameter sets that differ and produce bit-comparable curves, and asserts
  the module offers no single-branch ``V0`` estimator to be tempted by.
* **``s_pow = V * s_exp`` is an identity, not an approximation.** It is
  asserted at zero absolute error, which only holds if it was encoded rather
  than re-differentiated.
* **A sample that cannot be logged is NaN in place, never dropped.** A
  negative, a NaN and a zero are planted in one curve; the array keeps its
  length and their neighbours keep their slopes.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.constants import e as ELEMENTARY_CHARGE, k as BOLTZMANN

from src.processing import edge_analysis as ea
from src.processing.edge_analysis import (
    MODULATION_CONVENTIONS,
    THERMAL_FWHM_FACTOR,
    differentiation_fwhm,
    edge_columns,
    edge_summary,
    feenstra_normalize,
    fit_two_regime,
    local_log_slopes,
    resolution_fwhm,
    thermal_slope_ceiling,
)
from src.processing.peak_detection import thermal_broadening

#: k_B T in volts, from scipy rather than from the module under test.
def kt_volts(temperature_k: float) -> float:
    return BOLTZMANN * temperature_k / ELEMENTARY_CHARGE


#: The Fermi-derivative FWHM in units of k_B T: -df/dE is sech^2(x/2)/4k_BT,
#: half maximum at cosh(x/2) = sqrt(2), so the full width is 4 ln(1 + sqrt 2).
FERMI_FWHM_FACTOR = 4.0 * math.log(1.0 + math.sqrt(2.0))


# ---------------------------------------------------------------------------
# Synthetic curves
# ---------------------------------------------------------------------------

def two_regime_curve(v_edge=0.35, e_in=0.02, e_out=0.30, n=401, vmax=1.0,
                     noise=0.0, seed=0):
    """A conductance that is piecewise exponential in ``|V|``.

    Inside ``|V| < v_edge`` it decays with energy ``e_in`` (the steep in-gap
    tail); outside, with ``e_out``. Noise is multiplicative -- log-normal --
    because that is what a fit on ``ln g`` actually sees.
    """
    rng = np.random.default_rng(seed)
    v = np.linspace(-vmax, vmax, n)
    u = np.abs(v)
    s_in, s_out = 1.0 / e_in, 1.0 / e_out
    ln_g = np.where(u < v_edge, s_in * u, s_in * v_edge + s_out * (u - v_edge))
    g = np.exp(ln_g - ln_g.max())
    if noise:
        g = g * np.exp(rng.normal(0.0, noise, v.size))
    return v, g


def broadened_step(temperature_k=94.0, n=4001, vmax=0.5):
    """A step density of states seen through ``-df/dE``, in closed form.

    The convolution is exact: ``int_{-inf}^{E} (-df/dE') dE' = 1 - f(E)``, so
    a step at zero comes out as the Fermi function itself. This is the
    sharpest edge that can exist at that temperature.
    """
    kt = kt_volts(temperature_k)
    v = np.linspace(-vmax, vmax, n)
    return v, 1.0 / (1.0 + np.exp(-v / kt))


def semi_ellipse_fwhm(v_mod, n=400001):
    """FWHM of the first-harmonic lock-in kernel, measured on a fine grid."""
    u = np.linspace(-v_mod, v_mod, n)
    kernel = (2.0 / (np.pi * v_mod ** 2)) * np.sqrt(np.clip(v_mod ** 2 - u ** 2,
                                                            0.0, None))
    above = u[kernel >= 0.5 * kernel.max()]
    return float(above[-1] - above[0])


# ---------------------------------------------------------------------------
# Instrumental resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("temperature_k", [4.2, 77.0, 94.0, 300.0])
def test_the_thermal_width_is_the_fermi_derivative_fwhm(temperature_k):
    """The oracle is 4 ln(1 + sqrt 2) k_B T, not the module's own constant."""
    expected = FERMI_FWHM_FACTOR * kt_volts(temperature_k)
    # The module keeps Klein et al.'s truncated 3.5251 rather than 3.525494,
    # which is a 1.1e-4 relative difference and deliberate.
    assert resolution_fwhm(temperature_k) == pytest.approx(expected, rel=2e-4)


def test_the_thermal_constant_is_the_closed_form_and_not_a_rounding_of_it():
    """It used to carry the 3.5251 usually quoted, which is low by 1.1e-4
    relative. Physically irrelevant, but it left an arbitrary constant in the
    module that decides what is resolvable, so it is now exact."""
    assert THERMAL_FWHM_FACTOR == pytest.approx(FERMI_FWHM_FACTOR, rel=1e-12)
    assert THERMAL_FWHM_FACTOR != 3.5251


def test_ninety_four_kelvin_is_twenty_eight_and_a_half_millivolts():
    """94 K -> 8.1 meV of k_B T -> 28.55 mV of resolution."""
    assert thermal_broadening(94.0, "eV") == pytest.approx(8.100e-3, rel=1e-3)
    assert resolution_fwhm(94.0) == pytest.approx(
        FERMI_FWHM_FACTOR * thermal_broadening(94.0, "eV"), rel=1e-12)
    assert resolution_fwhm(94.0) == pytest.approx(0.0285575, rel=1e-5)


def test_the_zero_to_peak_convention_is_the_semi_ellipse_fwhm():
    """sqrt(3) V_mod, measured off the kernel rather than taken on trust."""
    v_mod = 0.01
    measured = semi_ellipse_fwhm(v_mod)
    assert measured == pytest.approx(math.sqrt(3.0) * v_mod, rel=1e-4)
    # At zero temperature the modulation term is the whole answer.
    assert resolution_fwhm(0.0, v_mod, "zero_to_peak") == pytest.approx(measured,
                                                                       rel=1e-4)


@pytest.mark.parametrize("convention, factor", [
    ("zero_to_peak", math.sqrt(3.0)),
    ("rms", math.sqrt(6.0)),
    ("peak_to_peak", math.sqrt(3.0) / 2.0),
])
def test_each_amplitude_convention_scales_the_same_kernel(convention, factor):
    """An r.m.s. amplitude is V/sqrt2 and a peak-to-peak one is 2V."""
    assert MODULATION_CONVENTIONS[convention] == pytest.approx(factor, rel=1e-12)
    assert resolution_fwhm(0.0, 0.02, convention) == pytest.approx(factor * 0.02,
                                                                  rel=1e-12)


def test_thermal_and_modulation_add_in_quadrature():
    thermal = resolution_fwhm(94.0, 0.0)
    modulation = resolution_fwhm(0.0, 0.01, "zero_to_peak")
    assert resolution_fwhm(94.0, 0.01) == pytest.approx(
        math.hypot(thermal, modulation), rel=1e-12)


def test_an_unmodulated_measurement_is_thermally_limited_alone():
    """A numerically differentiated I(V) has no lock-in term to add."""
    assert resolution_fwhm(94.0, 0.0) == pytest.approx(
        THERMAL_FWHM_FACTOR * thermal_broadening(94.0, "eV"), rel=1e-12)


def test_no_temperature_and_no_modulation_is_no_known_limit():
    """0.0 reads as 'nothing is known about the resolution', not 'perfect'."""
    assert resolution_fwhm(0.0, 0.0) == 0.0


def test_an_unknown_convention_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="convention must be one of"):
        resolution_fwhm(94.0, 0.01, "peak-to-peak")


# ---------------------------------------------------------------------------
# The thermal slope ceiling
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("temperature_k, per_volt, decades", [
    (300.0, 38.7, 16.8),
    (94.0, 123.5, 53.6),
    (77.0, 150.7, 65.5),
    (4.2, 2763.0, 1200.0),
])
def test_the_memorised_ceilings(temperature_k, per_volt, decades):
    """The numbers that decide which experiment is worth doing."""
    got_per_volt, got_decades = thermal_slope_ceiling(temperature_k)
    assert got_per_volt == pytest.approx(per_volt, rel=2e-3)
    assert got_decades == pytest.approx(decades, rel=2e-3)


@pytest.mark.parametrize("temperature_k", [4.2, 77.0, 94.0, 300.0])
def test_the_ceiling_is_one_over_kt(temperature_k):
    per_volt, decades = thermal_slope_ceiling(temperature_k)
    assert per_volt == pytest.approx(1.0 / kt_volts(temperature_k), rel=1e-9)
    assert decades == pytest.approx(per_volt / math.log(10.0), rel=1e-12)


def test_a_thermally_broadened_step_rises_at_exactly_the_ceiling():
    """The physics oracle: the sharpest possible edge sits on the ceiling.

    A step density of states seen through -df/dE is the Fermi function, whose
    log-slope tends to 1/k_B T deep in the tail. No sample can be steeper, so
    the ceiling has to be that number.
    """
    v, g = broadened_step(94.0)
    slopes = local_log_slopes(v, g, window_v=0.02)
    ceiling = thermal_slope_ceiling(94.0)[0]

    tail = (v > -0.30) & (v < -0.10)
    assert np.nanmedian(slopes.s_exp[tail]) == pytest.approx(ceiling, rel=1e-6)
    # And nothing anywhere on the curve exceeds it.
    assert np.nanmax(slopes.s_exp) <= ceiling * (1.0 + 1e-9)


@pytest.mark.parametrize("temperature_k", [0.0, -5.0])
def test_an_unknown_temperature_gives_nan_not_infinity(temperature_k):
    """Undetermined, not unbounded -- so nothing reads as 'never limited'."""
    per_volt, decades = thermal_slope_ceiling(temperature_k)
    assert np.isnan(per_volt) and np.isnan(decades)


# ---------------------------------------------------------------------------
# Local log-slopes
# ---------------------------------------------------------------------------

def test_an_exponential_curve_has_a_flat_exponential_slope():
    """g ~ exp(V/E0) with E0 = 1/12 V: the slope is the decay rate."""
    v = np.linspace(-1.0, 1.0, 401)
    slopes = local_log_slopes(v, np.exp(12.0 * v), window_v=0.1)
    np.testing.assert_allclose(slopes.s_exp, 12.0, rtol=1e-9)


def test_a_power_law_curve_has_a_flat_power_slope():
    """g ~ |V|^p: s_pow is the exponent itself, not a proxy for it."""
    v = np.linspace(0.01, 1.0, 400)
    slopes = local_log_slopes(v, v ** 1.5, window_v=0.05)
    assert np.nanmedian(slopes.s_pow) == pytest.approx(1.5, rel=5e-3)


def test_the_power_slope_is_exactly_the_bias_times_the_exponential_slope():
    """An identity, so zero absolute error -- a second derivative would not."""
    v = np.linspace(-1.0, 1.0, 401)
    g = np.exp(12.0 * v) * (2.0 + np.cos(9.0 * v))
    slopes = local_log_slopes(v, g, window_v=0.08)
    finite = np.isfinite(slopes.s_pow)
    assert finite.any()
    np.testing.assert_array_equal(slopes.s_pow[finite],
                                  (v * slopes.s_exp)[finite])


def test_the_power_slope_is_undefined_at_zero_bias():
    """d ln|V| is not defined there; NaN, never a large number."""
    v = np.linspace(-1.0, 1.0, 401)
    slopes = local_log_slopes(v, np.exp(3.0 * v), window_v=0.1)
    zero = int(np.argmin(np.abs(v)))
    assert v[zero] == 0.0
    assert np.isnan(slopes.s_pow[zero])
    assert np.isfinite(slopes.s_exp[zero])


def test_a_sample_that_cannot_be_logged_is_nan_in_place_never_dropped():
    """Regression guard: reindexing would break every downstream map."""
    v = np.linspace(-1.0, 1.0, 401)
    g = np.exp(12.0 * v)
    g[100], g[150], g[200] = -1.0, np.nan, 0.0

    slopes = local_log_slopes(v, g, window_v=0.1)
    assert slopes.s_exp.size == v.size
    assert slopes.s_pow.size == v.size
    assert slopes.ln_g.size == v.size
    assert slopes.valid.size == v.size

    bad = [100, 150, 200]
    assert not slopes.valid[bad].any()
    assert np.isnan(slopes.s_exp[bad]).all()
    assert np.isnan(slopes.ln_g[bad]).all()
    # The neighbours survive: one bad sample must not blank out a window.
    assert slopes.valid[[99, 101, 149, 151, 199, 201]].all()
    np.testing.assert_allclose(slopes.s_exp[[99, 101, 199, 201]], 12.0, rtol=1e-6)


def test_zero_conductance_is_excluded_even_though_the_mask_keeps_it():
    """positive_mask keeps zero as a real reading; a logarithm cannot."""
    v = np.linspace(0.1, 1.0, 200)
    g = np.exp(4.0 * v)
    g[50] = 0.0
    slopes = local_log_slopes(v, g, window_v=0.1)
    assert not slopes.valid[50]
    assert np.isnan(slopes.ln_g[50])


def test_a_descending_sweep_reads_the_same_slope():
    """The median spacing comes out negative and the derivative sign follows."""
    v = np.linspace(-1.0, 1.0, 401)
    g = np.exp(12.0 * v)
    up = local_log_slopes(v, g, window_v=0.1)
    down = local_log_slopes(v[::-1], g[::-1], window_v=0.1)
    np.testing.assert_allclose(down.s_exp[::-1], up.s_exp, rtol=1e-9)


def test_a_curve_with_nothing_positive_is_all_nan():
    v = np.linspace(-1.0, 1.0, 101)
    slopes = local_log_slopes(v, np.full_like(v, -1.0), window_v=0.1)
    assert not slopes.valid.any()
    assert np.isnan(slopes.s_exp).all()
    assert np.isnan(slopes.s_pow).all()


def test_a_non_positive_window_is_an_error():
    v = np.linspace(0.1, 1.0, 200)
    with pytest.raises(ValueError, match="window_v must be positive"):
        local_log_slopes(v, np.exp(v), window_v=0.0)


def test_a_mismatched_axis_is_an_error_not_a_wrong_number():
    with pytest.raises(ValueError, match="samples"):
        local_log_slopes(np.linspace(0.0, 1.0, 10), np.ones(9))


# ---------------------------------------------------------------------------
# Normalised conductance
# ---------------------------------------------------------------------------

def test_an_ohmic_curve_normalises_to_one():
    """(dI/dV)/(I/V) is 1 for I = GV: no structure, and none invented."""
    v = np.linspace(-1.0, 1.0, 201)
    normalized = feenstra_normalize(v, 3.0 * v, np.full_like(v, 3.0))
    finite = np.isfinite(normalized)
    np.testing.assert_allclose(normalized[finite], 1.0, rtol=1e-12)


def test_the_setpoint_scale_divides_out():
    """The point of the method: a different tip height must not move the curve."""
    v = np.linspace(-1.0, 1.0, 401)
    current = np.sinh(3.0 * v)
    didv = 3.0 * np.cosh(3.0 * v)
    near = feenstra_normalize(v, current, didv)
    far = feenstra_normalize(v, 0.04 * current, 0.04 * didv)
    finite = np.isfinite(near) & np.isfinite(far)
    assert finite.sum() > 300
    np.testing.assert_allclose(near[finite], far[finite], rtol=1e-9)


def test_zero_bias_is_nan_unbroadened_and_finite_once_broadened():
    """I/V is 0/0 there; broadening it is what tames the gap divergence."""
    v = np.linspace(-1.0, 1.0, 201)
    current = np.sinh(3.0 * v)
    didv = 3.0 * np.cosh(3.0 * v)
    zero = int(np.argmin(np.abs(v)))
    assert v[zero] == 0.0

    bare = feenstra_normalize(v, current, didv)
    assert np.isnan(bare[zero])
    assert np.isnan(bare).sum() == 1

    smoothed = feenstra_normalize(v, current, didv, broadening_v=0.3)
    assert math.isfinite(smoothed[zero])
    assert np.isfinite(smoothed).all()


def test_where_the_current_vanishes_the_answer_is_nan_not_infinity():
    """An infinity here would propagate into every fit and map downstream."""
    v = np.linspace(-1.0, 1.0, 201)
    current = np.zeros_like(v)
    didv = np.ones_like(v)
    normalized = feenstra_normalize(v, current, didv)
    assert np.isnan(normalized).all()


def test_a_nan_current_sample_does_not_become_a_number():
    v = np.linspace(-1.0, 1.0, 201)
    current = np.sinh(3.0 * v)
    current[40] = np.nan
    normalized = feenstra_normalize(v, current, 3.0 * np.cosh(3.0 * v))
    assert np.isnan(normalized[40])


def test_mismatched_channels_are_an_error():
    v = np.linspace(-1.0, 1.0, 21)
    with pytest.raises(ValueError, match="must match"):
        feenstra_normalize(v, v[:5], np.ones_like(v))


# ---------------------------------------------------------------------------
# The two-regime fit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("branch, sign", [("neg", -1.0), ("pos", 1.0)])
def test_the_planted_decay_energies_and_edge_come_back(branch, sign):
    """Both branches read the same way, and v_edge comes back signed."""
    v, g = two_regime_curve(v_edge=0.35, e_in=0.02, e_out=0.30)
    fit = fit_two_regime(v, g, branch, 94.0)

    assert fit.valid
    assert fit.e_in_ev == pytest.approx(0.02, rel=1e-6)
    assert fit.e_out_ev == pytest.approx(0.30, rel=1e-6)
    assert fit.r2 == pytest.approx(1.0, abs=1e-9)
    # Half a grid step of 5 mV is all the breakpoint can be located to.
    assert fit.v_edge == pytest.approx(sign * 0.35, abs=0.005)
    assert math.copysign(1.0, fit.v_edge) == sign


def test_the_slopes_are_taken_against_absolute_bias_so_the_branches_agree():
    """slope_in is the steep in-gap side on BOTH branches, not the first one."""
    v, g = two_regime_curve()
    neg = fit_two_regime(v, g, "neg", 94.0)
    pos = fit_two_regime(v, g, "pos", 94.0)
    assert neg.slope_in == pytest.approx(pos.slope_in, rel=1e-6)
    assert abs(neg.slope_in) > abs(neg.slope_out)
    assert neg.e_in_ev < neg.e_out_ev


def test_the_edge_does_not_depend_on_the_grid():
    """Refining the sweep must converge on the planted breakpoint."""
    for n in (201, 401, 801, 1601):
        v, g = two_regime_curve(v_edge=0.35, n=n)
        fit = fit_two_regime(v, g, "pos", 94.0)
        spacing = 2.0 / (n - 1)
        assert fit.v_edge == pytest.approx(0.35, abs=spacing)
        assert fit.e_in_ev == pytest.approx(0.02, rel=1e-6)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_the_answer_survives_multiplicative_noise(seed):
    """3 % log-normal noise is what a real ln(g) fit sees."""
    v, g = two_regime_curve(noise=0.03, seed=seed)
    fit = fit_two_regime(v, g, "pos", 94.0)
    assert fit.valid
    assert fit.v_edge == pytest.approx(0.35, abs=0.02)
    assert fit.e_in_ev == pytest.approx(0.02, rel=0.05)
    assert fit.e_out_ev == pytest.approx(0.30, rel=0.05)
    assert fit.r2 > 0.99


def test_the_breakpoint_error_bar_brackets_the_truth():
    v, g = two_regime_curve(v_edge=0.35, noise=0.03, seed=7)
    fit = fit_two_regime(v, g, "pos", 94.0)
    assert math.isfinite(fit.v_edge_err) and fit.v_edge_err > 0
    assert abs(fit.v_edge - 0.35) <= max(fit.v_edge_err, 0.005) * 3.0


def test_a_single_exponential_branch_cannot_locate_the_edge():
    """The degeneracy the module refuses to paper over.

    ``ln g = c - |V - V0|/E0`` on one side of ``V0`` is
    ``(c - V0/E0) + V/E0``: shifting ``V0`` by ``d`` and ``c`` by ``d/E0``
    reproduces the curve sample for sample, so no single-branch fit can
    return an edge position that is anything but its own initial guess.
    """
    v = np.linspace(0.05, 1.0, 400)
    e0 = 0.02
    first = np.exp(1.0 - (0.35 - v) / e0)
    shift = 0.11
    second = np.exp(1.0 + shift / e0 - ((0.35 + shift) - v) / e0)
    np.testing.assert_allclose(second, first, rtol=1e-12)

    # And so the module exposes no single-branch edge-position estimator.
    tempting = [name for name in dir(ea)
                if not name.startswith("_") and "v0" in name.lower()]
    assert tempting == []


def test_the_resolution_window_is_excluded_from_the_fit():
    """Inside n_kt * k_B T the curve is rounded by the instrument, not the sample."""
    v, g = two_regime_curve(n=401, vmax=1.0)
    kept_all = fit_two_regime(v, g, "pos", 94.0, n_kt=0.0).n_points
    kept_cut = fit_two_regime(v, g, "pos", 94.0, n_kt=3.0).n_points

    cutoff = 3.0 * kt_volts(94.0)
    expected_drop = int(np.sum((v > 0) & (np.abs(v) < cutoff)))
    assert expected_drop > 0
    assert kept_all - kept_cut == expected_drop


def test_a_wider_exclusion_window_removes_more_samples():
    v, g = two_regime_curve(n=801)
    counts = [fit_two_regime(v, g, "pos", 94.0, n_kt=k).n_points
              for k in (0.0, 3.0, 10.0)]
    assert counts[0] > counts[1] > counts[2]


def test_a_slope_at_the_ceiling_is_flagged_and_its_energy_is_just_kt():
    """The whole point: this 'Urbach energy' is the temperature restated."""
    kt = thermal_broadening(94.0, "eV")
    v, g = two_regime_curve(e_in=kt, e_out=0.30)
    fit = fit_two_regime(v, g, "pos", 94.0)
    assert fit.thermally_limited
    assert fit.e_in_ev == pytest.approx(kt, rel=1e-6)


def test_a_genuinely_disordered_tail_is_not_flagged():
    """20 meV at 94 K is 2.5x the thermal limit -- a real measurement."""
    v, g = two_regime_curve(e_in=0.02, e_out=0.30)
    assert not fit_two_regime(v, g, "pos", 94.0).thermally_limited


def test_the_same_tail_is_impossible_at_room_temperature():
    """50 /V is well past the 38.7 /V ceiling: that curve cannot exist at 300 K."""
    v, g = two_regime_curve(e_in=0.02, e_out=0.30)
    assert fit_two_regime(v, g, "pos", 300.0).thermally_limited


def test_an_unknown_temperature_cannot_claim_thermal_limitation():
    """False here means 'cannot be claimed', not 'not limited'."""
    v, g = two_regime_curve(e_in=0.001)
    fit = fit_two_regime(v, g, "pos", 0.0)
    assert fit.valid
    assert not fit.thermally_limited


def test_too_few_usable_samples_is_a_reason_not_a_number():
    v = np.linspace(0.01, 0.10, 10)
    fit = fit_two_regime(v, np.ones_like(v), "pos", 94.0)
    assert not fit.valid
    assert fit.reason
    assert np.isnan(fit.v_edge) and np.isnan(fit.e_in_ev) and np.isnan(fit.r2)


def test_non_positive_conductance_is_skipped_not_logged():
    """A few over-subtracted samples must not take the branch down with them."""
    v, g = two_regime_curve(n=801)
    clean = fit_two_regime(v, g, "pos", 94.0)
    g[[420, 500, 610]] = [-1e-3, 0.0, np.nan]
    dirty = fit_two_regime(v, g, "pos", 94.0)
    assert dirty.valid
    assert dirty.n_points == clean.n_points - 3
    assert dirty.e_in_ev == pytest.approx(clean.e_in_ev, rel=1e-6)


def test_an_unknown_branch_is_an_error():
    v, g = two_regime_curve()
    with pytest.raises(ValueError, match="branch must be one of"):
        fit_two_regime(v, g, "both", 94.0)


def test_min_points_below_two_is_an_error():
    v, g = two_regime_curve()
    with pytest.raises(ValueError, match="min_points must be at least 2"):
        fit_two_regime(v, g, "pos", 94.0, min_points=1)


def test_a_mismatched_conductance_axis_is_an_error():
    with pytest.raises(ValueError, match="samples"):
        fit_two_regime(np.linspace(0.1, 1.0, 20), np.ones(19), "pos", 94.0)


# ---------------------------------------------------------------------------
# One flat row per spectrum
# ---------------------------------------------------------------------------

def test_the_row_is_exactly_the_declared_columns():
    """A table cannot line up if the row and the column list disagree."""
    v, g = two_regime_curve()
    row = edge_summary(v, g, 94.0, v_mod=0.01)
    assert set(row) == set(edge_columns())
    assert len(edge_columns()) == len(set(edge_columns()))


def test_the_column_list_leaves_spectrum_index_to_the_batch_loop():
    """As in spectral_features, so the two lists concatenate cleanly."""
    assert "Spectrum_Index" not in edge_columns()


def test_every_value_in_the_row_is_a_scalar():
    """It has to be, or it cannot become a map cell."""
    v, g = two_regime_curve()
    row = edge_summary(v, g, 94.0, v_mod=0.01)
    for name, value in row.items():
        assert np.isscalar(value) or isinstance(value, float), name
        assert isinstance(float(value), float), name


def test_the_row_carries_the_planted_physics_on_both_branches():
    v, g = two_regime_curve(v_edge=0.35, e_in=0.02, e_out=0.30)
    row = edge_summary(v, g, 94.0, v_mod=0.01)

    assert row["valid"] == 1.0
    assert row["e0_neg"] == pytest.approx(0.02, rel=1e-6)
    assert row["e0_pos"] == pytest.approx(0.02, rel=1e-6)
    assert row["e_out_neg"] == pytest.approx(0.30, rel=1e-6)
    assert row["e_out_pos"] == pytest.approx(0.30, rel=1e-6)
    assert row["v_edge_neg"] == pytest.approx(-0.35, abs=0.005)
    assert row["v_edge_pos"] == pytest.approx(0.35, abs=0.005)
    assert row["thermally_limited_neg"] == 0.0
    assert row["thermally_limited_pos"] == 0.0
    assert row["resolution_fwhm"] == pytest.approx(resolution_fwhm(94.0, 0.01))
    assert row["slope_ceiling"] == pytest.approx(thermal_slope_ceiling(94.0)[0])
    assert row["slope_ceiling_decades"] == pytest.approx(
        thermal_slope_ceiling(94.0)[1])


def test_a_branch_that_could_not_be_fitted_is_nan_never_zero():
    """0.0 would read as 'no disorder' on a map; NaN reads as 'no answer'."""
    v, g = two_regime_curve(n=401)
    g[v < 0] = -1.0                       # the negative branch is unusable
    row = edge_summary(v, g, 94.0)

    assert row["valid"] == 1.0            # one good branch is still a measurement
    for key in ("e0_neg", "e_out_neg", "v_edge_neg", "v_edge_err_neg",
                "thermally_limited_neg"):
        assert np.isnan(row[key]), key
    assert math.isfinite(row["e0_pos"])


def test_a_spectrum_with_no_fittable_branch_is_flagged_not_crashed():
    v = np.linspace(-1.0, 1.0, 41)
    row = edge_summary(v, np.full_like(v, -1.0), 94.0)
    assert row["valid"] == 0.0
    for key in ("e0_neg", "e0_pos", "v_edge_neg", "v_edge_pos"):
        assert np.isnan(row[key]), key
    # The instrument numbers are still known even when the sample is not.
    assert math.isfinite(row["slope_ceiling"])


def test_an_unknown_temperature_leaves_the_ceiling_columns_undetermined():
    """Without a temperature, "not thermally limited" is a claim, not a fact.

    Regression: the row used to write 0.0 here, which on a map reads as
    "confirmed real" -- the exact reading :func:`thermal_slope_ceiling`
    returns NaN rather than infinity to prevent.
    """
    v, g = two_regime_curve(e_in=0.02)
    row = edge_summary(v, g, 0.0)
    assert row["valid"] == 1.0
    assert math.isfinite(row["e0_pos"])
    assert np.isnan(row["slope_ceiling"])
    assert np.isnan(row["slope_ceiling_decades"])
    assert np.isnan(row["thermally_limited_neg"])
    assert np.isnan(row["thermally_limited_pos"])


def test_a_known_temperature_says_zero_rather_than_nan():
    """0.0 is a real answer once the ceiling exists, and must stay one."""
    v, g = two_regime_curve(e_in=0.02)
    row = edge_summary(v, g, 94.0)
    assert row["thermally_limited_neg"] == 0.0
    assert row["thermally_limited_pos"] == 0.0


def test_passing_a_current_switches_the_fit_to_the_normalised_curve():
    """The flag must record which curve was fitted; a table cannot mix the two."""
    v, g = two_regime_curve()
    current = np.cumsum(g) * (v[1] - v[0])
    current = current - current[int(np.argmin(np.abs(v)))]

    raw = edge_summary(v, g, 94.0)
    normalized = edge_summary(v, g, 94.0, current=current, broadening_v=0.1)
    direct = edge_summary(v, feenstra_normalize(v, current, g, 0.1), 94.0)

    assert raw["feenstra_normalized"] == 0.0
    assert normalized["feenstra_normalized"] == 1.0
    for key in ("e0_pos", "e_out_pos", "v_edge_pos", "e0_neg", "v_edge_neg"):
        assert normalized[key] == pytest.approx(direct[key], nan_ok=True), key


# ---------------------------------------------------------------------------
# Grid assumptions: found by running the ugly inputs, not by reading the code
# ---------------------------------------------------------------------------

def test_a_shuffled_bias_axis_is_refused_rather_than_differentiated():
    """A Savitzky-Golay derivative reads samples in the order it gets them, so
    a shuffled sweep makes it differentiate the shuffling. Measured on a pure
    |V|^2.7 curve it returned -1.17 and raised nothing at all."""
    v = np.linspace(0.02, 0.30, 200)
    shuffled = v.copy()
    np.random.default_rng(0).shuffle(shuffled)

    with pytest.raises(ValueError, match="monotonic"):
        local_log_slopes(shuffled, np.abs(shuffled) ** 2.7)


def test_a_descending_sweep_is_not_a_shuffled_one():
    """Monotonic downward is a perfectly ordinary sweep direction."""
    v = np.linspace(0.30, 0.02, 200)
    s = local_log_slopes(v, np.abs(v) ** 2.7)
    good = s.s_pow[np.isfinite(s.s_pow)]

    assert s.uniform_grid is True
    assert np.median(good) == pytest.approx(2.7, abs=5e-3)


def test_a_non_uniform_grid_is_resampled_rather_than_quietly_wrong():
    """One ``delta`` is right only where the local step matches the median, and
    the failure is invisible to a spot check: on this grid the exponent used to
    come back spread over 0.70 to 10.46 while its median sat at exactly 2.700.
    The median is what a reviewer looks at, which is why it needed running."""
    v = np.geomspace(0.02, 0.30, 200)
    s = local_log_slopes(v, np.abs(v) ** 2.7)
    good = s.s_pow[np.isfinite(s.s_pow)]

    assert s.uniform_grid is False, "the grid should be recognised as non-uniform"
    assert np.median(good) == pytest.approx(2.7, abs=0.05)
    # The point of the fix: every sample, not just the middle one.
    assert good.max() - good.min() < 0.5, (
        f"exponent still spread over {good.min():.3f}..{good.max():.3f}")


def test_a_uniform_grid_still_reports_itself_as_one():
    v = np.linspace(0.02, 0.30, 200)
    assert local_log_slopes(v, np.abs(v) ** 2.7).uniform_grid is True


def test_an_unknown_temperature_reports_no_resolution_in_the_summary_row():
    """``resolution_fwhm`` itself stays the pure formula, so the modulation
    kernel can be measured on its own. But the summary row is what a map is
    coloured by, and there a missing temperature must not come out as
    "resolution = sqrt(3)*V_mod" — a confident number standing in for one
    nobody recorded."""
    v = np.linspace(-0.3, -0.03, 300)
    g = np.exp(v / 0.022)

    known = edge_summary(v, g, 94.0, v_mod=0.010)
    unknown = edge_summary(v, g, 0.0, v_mod=0.010)

    assert math.isfinite(known["resolution_fwhm"])
    assert math.isnan(unknown["resolution_fwhm"])
    assert math.isnan(unknown["slope_ceiling"])
    # The primitive is untouched: T=0 still isolates the modulation kernel.
    assert resolution_fwhm(0.0, 0.010) == pytest.approx(math.sqrt(3) * 0.010)


# ---------------------------------------------------------------------------
# dI/dV without a lock-in: the differentiation window IS an instrument function
# ---------------------------------------------------------------------------

def _sg_derivative_step_fwhm(window, polyorder):
    """FWHM, in samples, of a Savitzky-Golay derivative's response to a step.

    The oracle for :func:`differentiation_fwhm`, and it is the definition
    rather than a model of it: a step in I(V) is a delta in dI/dV, so what the
    filter makes of one IS the instrument function.
    """
    from scipy.signal import savgol_filter

    n = 4001
    current = np.zeros(n)
    current[n // 2:] = 1.0
    deriv = savgol_filter(current, window, polyorder, deriv=1, delta=1.0,
                          mode="interp")
    above = np.flatnonzero(deriv >= 0.5 * deriv.max())
    return above[-1] - above[0] + 1


@pytest.mark.parametrize("window", [11, 21, 51, 101])
@pytest.mark.parametrize("polyorder", [1, 2, 3, 4])
def test_the_differentiation_width_matches_the_filter_it_models(window, polyorder):
    """Measured against the actual filter, not against a rule of thumb."""
    dv = 1e-3
    measured = _sg_derivative_step_fwhm(window, polyorder) * dv

    assert differentiation_fwhm(window * dv, polyorder) == pytest.approx(
        measured, rel=0.25)


def test_the_two_filter_families_are_the_two_that_exist():
    """Orders 1 and 2 share a filter, and so do 3 and 4 — a quadratic fitted
    to a symmetric window has the same first-derivative coefficients as a
    linear one. Two constants, not four."""
    assert differentiation_fwhm(0.05, 1) == differentiation_fwhm(0.05, 2)
    assert differentiation_fwhm(0.05, 3) == differentiation_fwhm(0.05, 4)
    # And the cubic family really is the cheaper one.
    assert differentiation_fwhm(0.05, 3) < differentiation_fwhm(0.05, 2)


def test_no_window_means_an_exact_derivative():
    assert differentiation_fwhm(0.0) == 0.0
    assert differentiation_fwhm(-0.05) == pytest.approx(differentiation_fwhm(0.05))


def test_an_unsupported_polynomial_order_is_refused():
    with pytest.raises(ValueError, match="polyorder"):
        differentiation_fwhm(0.05, 7)


def test_a_measurement_without_a_lock_in_is_not_thermally_limited():
    """The trap this exists to close. With no lock-in there is no V_mod to
    quote, so the resolution *looks* thermal — while the window that actually
    produced the curve, wider than the thermal kernel, goes unrecorded.

    At 94 K the thermal width is 28.6 mV. A 50 mV window contributes 36 mV and
    dominates it.
    """
    thermal_only = resolution_fwhm(94.0)
    with_window = resolution_fwhm(94.0, deriv_window_v=0.050)

    assert thermal_only == pytest.approx(0.0286, abs=5e-4)
    assert differentiation_fwhm(0.050) > thermal_only, (
        "a 50 mV window should dominate the 94 K thermal kernel")
    assert with_window == pytest.approx(
        math.hypot(thermal_only, differentiation_fwhm(0.050)), rel=1e-9)
    assert with_window > 1.5 * thermal_only


def test_the_three_widths_add_in_quadrature():
    total = resolution_fwhm(94.0, 0.010, "rms", 0.020, 2)
    thermal = resolution_fwhm(94.0)
    modulation = math.sqrt(6.0) * 0.010
    numerical = differentiation_fwhm(0.020, 2)

    assert total == pytest.approx(
        math.sqrt(thermal ** 2 + modulation ** 2 + numerical ** 2), rel=1e-9)


def test_the_window_defaults_to_zero_so_existing_callers_are_unchanged():
    assert resolution_fwhm(94.0, 0.010, "rms") == pytest.approx(
        resolution_fwhm(94.0, 0.010, "rms", 0.0, 2), rel=1e-12)


def _smooth_gradient_step_fwhm(window, polyorder=3):
    """FWHM of TRANS's own derivative pipeline: smooth, gradient, smooth."""
    from scipy.signal import savgol_filter

    n = 4001
    current = np.zeros(n)
    current[n // 2:] = 1.0
    deriv = np.gradient(savgol_filter(current, window, polyorder))
    deriv = savgol_filter(deriv, window, polyorder)
    above = np.flatnonzero(deriv >= 0.5 * deriv.max())
    return above[-1] - above[0] + 1


@pytest.mark.parametrize("window", [21, 51, 101])
def test_the_smooth_gradient_pipeline_is_modelled_from_its_own_response(window):
    dv = 1e-3
    measured = _smooth_gradient_step_fwhm(window) * dv
    modelled = differentiation_fwhm(window * dv, 3, "smooth_gradient")

    assert modelled == pytest.approx(measured, rel=0.2)
    # Conservative by construction: erring wide means declaring fewer states
    # resolved, which is the safe direction for a resolution figure.
    assert modelled >= measured * 0.95


@pytest.mark.parametrize("window", [21, 51, 101])
def test_one_pass_is_sharper_than_smooth_gradient_smooth(window):
    """The finding behind offering both: TRANS's Derivative tool filters twice
    around a bare gradient, which is ~30% wider than differentiating the
    fitted polynomial once at the same window."""
    dv = 1e-3
    one_pass = _sg_derivative_step_fwhm(window, 3) * dv
    pipeline = _smooth_gradient_step_fwhm(window) * dv

    assert pipeline > one_pass
    assert differentiation_fwhm(window * dv, 3, "smooth_gradient") > \
        differentiation_fwhm(window * dv, 3, "savgol_deriv")


def test_an_unknown_derivative_kind_is_refused():
    with pytest.raises(ValueError, match="kind"):
        differentiation_fwhm(0.05, 3, "magic")
