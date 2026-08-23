"""
Tests for the "negative LDOS is not a measurement" rule.

The interesting case is the segment that crosses zero. Clipping the samples
first and then running a trapezoid moves the crossing to the end of the
segment and over-counts everything beyond it — on a curve that swings evenly
about zero that is a factor of two. The integral solves for the crossing
instead, so the answer does not depend on how coarse the bias grid is.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest

from src.processing.positivity import positive_integral, positive_mask, positive_part


# ── the mask a fit uses ─────────────────────────────────────────────────────

def test_mask_keeps_zero_and_drops_negatives_and_nan():
    y = np.array([-1e-12, 0.0, 1e-12, np.nan, -np.inf, np.inf])
    np.testing.assert_array_equal(
        positive_mask(y), [False, True, True, False, False, False])


def test_zero_is_kept_because_it_is_a_reading():
    # Dropping it would bias a fit through a gap interior upward.
    assert positive_mask(np.zeros(5)).all()


def test_positive_part_reads_nan_as_zero():
    np.testing.assert_allclose(
        positive_part(np.array([-2.0, 0.0, 3.0, np.nan])), [0.0, 0.0, 3.0, 0.0])


# ── the integral ────────────────────────────────────────────────────────────

def test_all_positive_matches_an_ordinary_trapezoid():
    x = np.linspace(0.0, 1.0, 101)
    y = np.sin(np.pi * x)
    np.testing.assert_allclose(positive_integral(y, x), np.trapz(y, x), rtol=1e-12)


def test_all_negative_integrates_to_zero():
    x = np.linspace(0.0, 1.0, 51)
    assert positive_integral(-np.ones_like(x), x) == 0.0


def test_a_crossing_is_solved_for_not_clipped():
    # -1 → +1 → -1 over two unit steps: the positive part is two triangles of
    # base 1/2 and height 1, so 1/2 in total. Clipping first would say 1.
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([-1.0, 1.0, -1.0])
    assert positive_integral(y, x) == pytest.approx(0.5)
    assert np.trapz(np.maximum(y, 0.0), x) == pytest.approx(1.0)


def test_the_answer_does_not_depend_on_the_grid():
    # A sine's positive half has area 2/pi over its period, whatever the
    # sampling — that is the property clipping destroys.
    for n in (51, 201, 1001):
        x = np.linspace(0.0, 2.0 * np.pi, n)
        assert positive_integral(np.sin(x), x) == pytest.approx(2.0, rel=2e-3)


def test_it_never_returns_less_than_zero():
    rng = np.random.default_rng(0)
    x = np.linspace(-1.0, 1.0, 200)
    for _ in range(20):
        assert positive_integral(rng.normal(0.0, 1.0, x.size), x) >= 0.0


def test_it_is_never_more_than_the_clipped_trapezoid():
    rng = np.random.default_rng(1)
    x = np.linspace(-1.0, 1.0, 200)
    for _ in range(20):
        y = rng.normal(0.0, 1.0, x.size)
        assert positive_integral(y, x) <= np.trapz(np.maximum(y, 0.0), x) + 1e-12


def test_a_signed_integral_and_a_positive_one_agree_on_positive_data():
    x = np.linspace(0.0, 1.0, 64)
    y = np.abs(np.cos(4.0 * x)) + 0.1
    np.testing.assert_allclose(positive_integral(y, x), np.trapz(y, x), rtol=1e-12)


# ── the shape the app actually passes ───────────────────────────────────────

def test_two_dimensional_input_integrates_each_column():
    x = np.array([0.0, 1.0, 2.0])
    block = np.column_stack([[-1.0, 1.0, -1.0], [1.0, 1.0, 1.0], [-1.0, -1.0, -1.0]])
    np.testing.assert_allclose(positive_integral(block, x, axis=0), [0.5, 2.0, 0.0])


def test_nan_does_not_wipe_out_a_whole_spectrum():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([1.0, np.nan, 1.0, 1.0])
    assert positive_integral(y, x) > 0.0


def test_uneven_spacing_is_honoured():
    x = np.array([0.0, 1.0, 10.0])
    y = np.array([1.0, 1.0, 1.0])
    assert positive_integral(y, x) == pytest.approx(10.0)


def test_a_mismatched_axis_is_an_error_not_a_wrong_number():
    with pytest.raises(ValueError):
        positive_integral(np.ones(5), np.linspace(0, 1, 4))


def test_a_single_sample_has_no_area():
    assert positive_integral(np.array([5.0]), np.array([0.0])) == 0.0
