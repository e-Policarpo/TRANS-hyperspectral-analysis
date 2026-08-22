"""
Tests for splitting a dI/dV peak list into carrier branches.

The curve now comes from a dataset rather than a file, so the CSV reader
these tests used to exercise is gone with it; what is left is the physics —
which peak belongs to which carrier, and where the boundary between them
goes. The peaks themselves are found by TRANS's own engine, which is now a
plain import rather than something to skip on.
"""

import numpy as np
import pytest

from src.physics.branches import (DidvCurve, analyze_curve, format_targets,
                                  relative_to_edge, split_peaks)


def _synthetic(states_e=(0.20, 0.34, 0.52), states_h=(-0.15, -0.28, -0.44)):
    """dI/dV with exponential band edges and planted states."""
    V = np.linspace(-1.2, 1.2, 1201)
    y = 0.02 * np.random.RandomState(0).randn(V.size)
    y += 3 * np.exp((V - 0.7) * 6) * (V > 0)
    y += 3 * np.exp(-(V + 0.6) * 6) * (V < 0)
    for c in tuple(states_e) + tuple(states_h):
        y += 0.5 * np.exp(-((V - c) / 0.02) ** 2)
    return DidvCurve(x=V, y=y, name="dI/dV")


# ─── analysis ────────────────────────────────────────────────────────────────

def test_positive_bias_gives_electrons_and_negative_gives_holes():
    """The sign of the voltage is what separates the two carriers."""
    peaks = analyze_curve(_synthetic())

    for planted in (0.20, 0.34, 0.52):
        assert min(abs(p - planted) for p in peaks.electron_eV) < 0.01
    for planted in (0.15, 0.28, 0.44):
        assert min(abs(p - planted) for p in peaks.hole_eV) < 0.01
    # Holes enter with |V|: no target energy is negative.
    assert all(p > 0 for p in peaks.hole_eV)
    assert peaks.electron_eV == sorted(peaks.electron_eV)


def test_a_curve_with_only_empty_states_yields_no_hole_targets():
    V = np.linspace(0.02, 1.0, 500)
    y = 0.01 * np.random.RandomState(1).randn(V.size)
    for c in (0.25, 0.45):
        y += 0.5 * np.exp(-((V - c) / 0.02) ** 2)
    peaks = analyze_curve(DidvCurve(x=V, y=y))
    assert peaks.hole_eV == []
    assert peaks.electron_eV


def test_peaks_around_zero_can_be_excluded():
    curve = _synthetic(states_e=(0.02, 0.30), states_h=(-0.02, -0.30))
    everything = analyze_curve(curve, min_abs_V=0.0)
    away = analyze_curve(curve, min_abs_V=0.05)
    assert min(away.electron_eV) >= 0.05
    assert len(away.peaks_V) == len(everything.peaks_V)   # the same curve


def test_the_engine_settings_reach_the_search():
    """The list goes straight into the search: a noise peak costs a geometry."""
    V = np.linspace(-0.6, 0.6, 1201)
    rng = np.random.RandomState(7)
    y = 0.05 * rng.randn(V.size)
    for c in (-0.30, 0.30):
        y += 1.0 * np.exp(-((V - c) / 0.02) ** 2)   # two strong states
    curve = DidvCurve(x=V, y=y)

    sensitive = analyze_curve(curve, {"height": 1.0})
    strict = analyze_curve(curve, {"height": 3.0})
    assert len(strict.peaks_V) < len(sensitive.peaks_V)
    assert len(strict.electron_eV) == 1 and len(strict.hole_eV) == 1
    assert strict.electron_eV[0] == pytest.approx(0.30, abs=0.01)


def test_the_defaults_are_the_engine_s_own():
    """Not a copied dictionary: this search and Confinement Analysis see the
    same peaks because they read the same defaults."""
    from src.processing.peak_detection import CONFINEMENT_DEFAULTS
    from src.backend.tool_implementations import (
        CONFINEMENT_DEFAULTS as BACKEND_DEFAULTS)

    assert CONFINEMENT_DEFAULTS is BACKEND_DEFAULTS


def test_the_curve_and_its_background_ride_along():
    """The corrected curve is what a preview draws; it must survive."""
    curve = _synthetic()
    peaks = analyze_curve(curve)

    assert peaks.curve is curve
    assert peaks.baseline is not None and peaks.corrected is not None
    assert peaks.total == len(peaks.peaks_V)


# ─── formatting ──────────────────────────────────────────────────────────────

def test_targets_are_formatted_for_the_entry_field():
    assert format_targets([0.1, 0.25]) == "0.10000, 0.25000"
    assert format_targets([]) == ""


def test_counting_from_the_band_edge_drops_the_first_level():
    assert relative_to_edge([0.10, 0.25, 0.40]) == pytest.approx([0.15, 0.30])
    assert relative_to_edge([0.10]) == [0.10]


# ─── boundaries between the branches ─────────────────────────────────────────

def test_boundaries_at_zero_are_the_sign_of_the_bias():
    """The default cannot have changed what already worked."""
    peaks = split_peaks([-0.30, -0.15, 0.20, 0.34])
    assert peaks.electron_eV == pytest.approx([0.20, 0.34])
    assert peaks.hole_eV == pytest.approx([0.15, 0.30])
    assert peaks.in_gap_V == pytest.approx([])


def test_energies_are_counted_from_the_boundary():
    """With the boundary at the edge, the target becomes E_n directly."""
    peaks = split_peaks([0.44, 0.70], split_e=0.35)
    assert peaks.electron_eV == pytest.approx([0.09, 0.35])


def test_a_charged_well_keeps_its_filled_levels_on_the_electron_branch():
    """Occupied electron levels sit above E_c and below E_F.

    Splitting at V = 0 would send the one at -0.012 V into the hole search,
    where it fits nicely and lies. Splitting at E_c returns it to its own
    ladder.
    """
    centres = [-0.012, 0.251, 0.689, -0.763, -0.802]
    naive = split_peaks(centres)
    assert -0.012 in [-v for v in naive.hole_eV]     # it landed in the holes

    correct = split_peaks(centres, split_e=-0.10, split_h=-0.75)
    assert len(correct.electron_eV) == 3             # the whole ladder
    assert correct.electron_eV[0] == pytest.approx(0.088, abs=1e-3)
    assert len(correct.hole_eV) == 2


def test_peaks_between_the_boundaries_are_set_aside():
    peaks = split_peaks([-0.5, -0.02, 0.03, 0.5], split_e=0.1, split_h=-0.1)
    assert peaks.in_gap_V == pytest.approx([-0.02, 0.03])
    assert len(peaks.electron_eV) == 1 and len(peaks.hole_eV) == 1


def test_a_neutral_band_around_the_boundary_can_be_widened():
    """Zero-current noise near the boundary is not a state."""
    peaks = split_peaks([-0.30, -0.01, 0.01, 0.30], min_gap_V=0.05)
    assert peaks.electron_eV == pytest.approx([0.30])
    assert peaks.hole_eV == pytest.approx([0.30])


def test_the_boundaries_are_recorded_on_the_result():
    peaks = split_peaks([-0.5, 0.5], split_e=0.1, split_h=-0.2)
    assert (peaks.split_e, peaks.split_h) == (0.1, -0.2)
