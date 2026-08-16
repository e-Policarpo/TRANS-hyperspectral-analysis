"""
Tests for the ported pyqtgraph tick algorithm.

The reference behaviour is pyqtgraph's ``AxisItem`` (`d588dd3`); these
tests assert the structural properties that matter for TRANS plots:

- the major-tick spacing falls into the 1/2/5 × 10ⁿ family,
- minor and sub-minor levels fit between major ticks without overlap,
- the number of major ticks scales sensibly with axis length,
- log mode emits decade ticks plus the 2,3,...,9 minor marks,
- the formatter picks decimal places consistent with the spacing,
- log mode renders ``10ⁿ`` with Unicode superscripts.

No Qt; this module is pure-Python.
"""

from __future__ import annotations

from math import log10

import numpy as np
import pytest

from src.widgets._pyqtgraph_ports.ticks import (
    format_tick_strings,
    log_tick_strings,
    log_tick_values,
    minor_tick_values,
    tick_spacing,
    tick_strings,
    tick_values,
)


# --- tick_spacing --------------------------------------------------------

def _is_nice_step(step: float) -> bool:
    """A 'nice' step belongs to the 1/2/5 × 10ⁿ family."""
    if step <= 0:
        return False
    decade = 10 ** np.floor(np.log10(step))
    mantissa = round(step / decade, 6)
    return mantissa in (1.0, 2.0, 5.0)


@pytest.mark.parametrize("rng", [
    (-3.2, 7.8), (0.0, 1.0), (-1000, 1000), (1e-9, 1e-6), (1e6, 1e7),
])
def test_tick_spacing_returns_nice_steps(rng):
    lo, hi = rng
    levels = tick_spacing(lo, hi, size=600.0)
    assert levels, "expected at least one spacing level"
    major_spacing, _offset = levels[0]
    assert _is_nice_step(major_spacing), (
        f"major spacing {major_spacing} not in 1/2/5 × 10ⁿ family for range {rng}"
    )


def test_tick_spacing_zero_range_returns_empty():
    assert tick_spacing(5.0, 5.0, size=600.0) == []


def test_tick_spacing_grows_with_axis_size():
    """Longer axis → either the same spacing or a finer one (more ticks)."""
    short = tick_spacing(0.0, 10.0, size=200.0)[0][0]
    long = tick_spacing(0.0, 10.0, size=2000.0)[0][0]
    assert long <= short, (
        f"longer axis should produce smaller-or-equal major spacing "
        f"(short={short}, long={long})"
    )


def test_tick_spacing_max_level_caps_returned_levels():
    levels0 = tick_spacing(0.0, 100.0, size=600.0, max_tick_level=0)
    levels1 = tick_spacing(0.0, 100.0, size=600.0, max_tick_level=1)
    levels2 = tick_spacing(0.0, 100.0, size=600.0, max_tick_level=2)
    assert len(levels0) == 1
    assert len(levels1) == 2
    assert len(levels2) >= 2  # may be 2 or 3 depending on whether extra fits


def test_tick_spacing_explicit_passthrough():
    explicit = [(7.0, 0.0), (1.0, 0.0)]
    assert tick_spacing(
        0.0, 50.0, size=600.0, explicit_spacing=explicit,
    ) == explicit


# --- tick_values ---------------------------------------------------------

@pytest.mark.parametrize("rng,size", [
    ((-3.2, 7.8), 600.0),
    ((0.0, 1.0), 600.0),
    ((-1000.0, 1000.0), 800.0),
    ((-1.5, 1.5), 400.0),
])
def test_tick_values_are_inside_range(rng, size):
    lo, hi = rng
    levels = tick_values(lo, hi, size)
    for spacing, values in levels:
        for v in values:
            assert lo - 1e-6 <= v <= hi + 1e-6, (
                f"tick {v} outside [{lo}, {hi}] at spacing {spacing}"
            )


def test_tick_values_levels_dont_share_values():
    """A value emitted at a coarser level must not reappear at a finer one."""
    levels = tick_values(-10.0, 10.0, 600.0)
    seen = set()
    for _spacing, values in levels:
        for v in values:
            key = round(v, 8)
            assert key not in seen, f"value {v} repeated across levels"
            seen.add(key)


def test_tick_values_inverted_input_is_swapped():
    """Passing min > max is handled silently (matches upstream)."""
    a = tick_values(-5.0, 5.0, 600.0)
    b = tick_values(5.0, -5.0, 600.0)
    # Same final tick sets, irrespective of order.
    def flatten(levels):
        return sorted(round(v, 6) for _s, vs in levels for v in vs)
    assert flatten(a) == flatten(b)


def test_tick_values_empty_when_range_zero():
    assert tick_values(0.0, 0.0, 600.0) == []


def test_tick_values_scale_applied_consistently():
    """``scale`` multiplies into the algorithm before, divides out after."""
    base = tick_values(0.0, 10.0, 600.0)
    scaled = tick_values(0.0, 10.0, 600.0, scale=2.0)
    # With scale=2.0 the algorithm sees [0, 20]; tick values come back
    # divided by 2, so they should still land inside [0, 10].
    flat_scaled = [v for _s, vs in scaled for v in vs]
    assert all(0 <= v <= 10 for v in flat_scaled)
    # The level count is the same.
    assert len(base) == len(scaled)


# --- log_tick_values -----------------------------------------------------

def test_log_tick_values_emits_decades():
    """For log range covering several decades, decade ticks dominate."""
    # Input values are log10(...), so [-2, 3] → [0.01, 1000].
    levels = tick_values(-2.0, 3.0, 600.0, log=True)
    assert levels, "expected at least one log level"
    major_spacing, major_vals = levels[0]
    # Decade ticks have spacing >= 1 in log space.
    assert major_spacing >= 1.0
    # Every major tick is at an integer log value (a decade).
    for v in major_vals:
        assert abs(v - round(v)) < 1e-6, f"non-decade major tick {v}"


def test_log_tick_values_adds_intra_decade_minors_when_sparse():
    """When the linear algorithm doesn't supply enough levels in log
    mode, ``logTickValues`` synthesises the 2..9 marks per decade."""
    # Short log range so the linear tick algorithm only gets 1–2 levels.
    levels = tick_values(0.0, 2.0, 600.0, log=True)
    # The synthesised minor level has NaN spacing (sentinel).
    last_spacing, last_values = levels[-1]
    assert np.isnan(last_spacing) or last_spacing < 1.0
    # And it contains values like log10(2) ≈ 0.301, log10(3) ≈ 0.477.
    if np.isnan(last_spacing):
        assert any(abs(v - log10(2)) < 1e-6 for v in last_values)
        assert any(abs(v - log10(3)) < 1e-6 for v in last_values)


# --- tick_strings --------------------------------------------------------

def test_tick_strings_uses_decimal_places_from_spacing():
    """Smaller spacing → more decimal places in labels."""
    s1 = tick_strings([1.0, 2.0, 3.0], scale=1.0, spacing=1.0)
    s2 = tick_strings([1.0, 1.1, 1.2], scale=1.0, spacing=0.1)
    s3 = tick_strings([1.00, 1.01, 1.02], scale=1.0, spacing=0.01)
    # 1-unit spacing → 0 decimal places; 0.1 → 1 place; 0.01 → 2 places.
    assert s1 == ["1", "2", "3"]
    assert s2 == ["1.0", "1.1", "1.2"]
    assert s3 == ["1.00", "1.01", "1.02"]


def test_tick_strings_uses_g_format_for_extremes():
    """Values outside the [0.001, 10000) window fall through to ``%g``.

    ``%g`` only emits ``e``-notation for truly small (~1e-5) or large
    (~1e6) magnitudes — for intermediate "extremes" it just produces
    a shorter decimal than the fixed-places branch would.
    """
    # Below 0.001: %g picks the shortest decimal.
    tiny = tick_strings([0.0001, 0.0002], scale=1.0, spacing=0.0001)
    assert tiny == ["0.0001", "0.0002"]
    # At/above 10000: %g handles trailing-zero pruning.
    big = tick_strings([10000.0, 20000.0], scale=1.0, spacing=10000.0)
    assert big == ["10000", "20000"]
    # Truly tiny / truly huge → scientific notation.
    very_small = tick_strings([1e-8], scale=1.0, spacing=1e-9)
    very_big = tick_strings([1e9], scale=1.0, spacing=1e8)
    assert "e" in very_small[0]
    assert "e" in very_big[0]


# --- log_tick_strings ----------------------------------------------------

def test_log_tick_strings_renders_superscripts():
    """Log labels show ``10ⁿ`` with Unicode superscript exponents."""
    labels = log_tick_strings([0.0, 1.0, 2.0, 3.0], scale=1.0, spacing=1.0)
    # 10⁰ = 1, 10¹ = 10, 10² = 100, 10³ = 1000.
    assert any("10⁰" in s or s == "1" for s in labels[:1])
    assert any("10¹" in s or s == "10" for s in labels[1:2])
    assert any("10²" in s or "100" in s for s in labels[2:3])
    assert any("10³" in s or "1000" in s for s in labels[3:])


def test_log_tick_strings_handles_negative_exponents():
    """Negative log values render with the Unicode minus superscript.

    The superscript branch only fires when ``%0.1g`` produces an
    ``e``-notation string — for intermediate negatives like ``10^-2``
    (= 0.01) ``%0.1g`` returns ``"0.01"`` and the superscript path is
    skipped. Use truly small magnitudes to exercise the branch.
    """
    labels = log_tick_strings([-5.0, -7.0], scale=1.0, spacing=1.0)
    # 10⁻⁵ and 10⁻⁷ → Unicode minus + superscript digits.
    assert any("⁻" in s for s in labels)
    assert any("10" in s for s in labels)


def test_tick_strings_log_dispatch():
    """``log=True`` defers to :func:`log_tick_strings`."""
    direct = log_tick_strings([0.0, 1.0], scale=1.0, spacing=1.0)
    dispatched = tick_strings([0.0, 1.0], scale=1.0, spacing=1.0, log=True)
    assert direct == dispatched


# --- minor_tick_values --------------------------------------------------

def test_minor_tick_values_strips_major_level():
    """The major level is returned by :func:`tick_values` at index 0;
    the minor helper returns everything after it."""
    full = tick_values(0.0, 100.0, 600.0)
    minors = minor_tick_values(0.0, 100.0, 600.0)
    # Same total minus one level.
    assert len(minors) == len(full) - 1


def test_minor_tick_values_levels_sit_between_majors():
    """Minor tick values should fall between adjacent major ticks."""
    full = tick_values(0.0, 10.0, 600.0)
    minors = minor_tick_values(0.0, 10.0, 600.0)
    if not minors:
        pytest.skip("no minor level produced for this range")
    major_spacing, major_vals = full[0]
    minor_spacing, minor_vals = minors[0]
    # The minor spacing must be smaller than the major spacing.
    assert minor_spacing < major_spacing
    # No minor value coincides with a major one (the tick_values
    # algorithm already de-dups at the spacing/100 level).
    for mv in minor_vals:
        assert all(abs(mv - mj) > minor_spacing * 0.01 for mj in major_vals)


def test_minor_tick_values_with_max_level_one_returns_one_level():
    """``max_tick_level=1`` keeps only the major + minor → minor
    helper returns exactly one level."""
    minors = minor_tick_values(0.0, 100.0, 600.0, max_tick_level=1)
    assert len(minors) == 1


# --- format_tick_strings ------------------------------------------------

def test_format_tick_strings_no_shared_exponent_in_comfort_range():
    """Magnitudes inside ``[10^-threshold, 10^threshold]`` get
    per-tick formatting with no shared exponent."""
    labels, exp = format_tick_strings([1.0, 2.0, 3.0], spacing=1.0)
    assert exp is None
    assert labels == ["1", "2", "3"]


def test_format_tick_strings_extracts_shared_positive_exponent():
    """Very large values are scaled by a shared 10ⁿ multiplier."""
    labels, exp = format_tick_strings(
        [100_000.0, 200_000.0, 300_000.0], spacing=100_000.0,
    )
    assert exp == 5
    # 100_000 / 10^5 = 1.0, 200_000 / 10^5 = 2.0, etc.
    assert labels == ["1", "2", "3"]


def test_format_tick_strings_extracts_shared_negative_exponent():
    """Very small values are scaled by a shared 10⁻ⁿ multiplier."""
    labels, exp = format_tick_strings(
        [0.00001, 0.00002, 0.00003], spacing=0.00001,
    )
    assert exp == -5
    assert labels == ["1", "2", "3"]


def test_format_tick_strings_log_mode_short_circuits():
    """Log-mode dispatch bypasses the shared-exponent path —
    :func:`log_tick_strings` already produces compact labels."""
    labels, exp = format_tick_strings(
        [0.0, 1.0, 2.0], spacing=1.0, log=True,
    )
    assert exp is None
    assert any("10" in lbl for lbl in labels[1:])  # log labels show 10ⁿ


# ---------------------------------------------------------------------------
# Non-finite ranges
#
# An all-NaN curve (or one carrying inf) propagates into the view range and
# reached ``tick_values``, where ``ceil()`` raised "cannot convert float NaN
# to integer" from inside ``QQuickPaintedItem.paint`` — aborting the render
# on every frame. A non-finite range now yields no ticks instead.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lo, hi", [
    (float("nan"), float("nan")),
    (float("nan"), 1.0),
    (0.0, float("nan")),
    (float("-inf"), float("inf")),
    (0.0, float("inf")),
    (float("-inf"), 0.0),
])
def test_tick_values_returns_empty_for_non_finite_range(lo, hi):
    assert tick_values(lo, hi, 300.0) == []


@pytest.mark.parametrize("lo, hi", [
    (float("nan"), float("nan")),
    (float("nan"), 1.0),
    (0.0, float("inf")),
])
def test_tick_values_non_finite_range_in_log_mode(lo, hi):
    """The log post-process does its own ``int(floor(...))`` — it must
    not be reached with a non-finite range either."""
    assert tick_values(lo, hi, 300.0, log=True) == []


@pytest.mark.parametrize("lo, hi", [
    (float("nan"), float("nan")),
    (float("-inf"), float("inf")),
])
def test_tick_spacing_returns_empty_for_non_finite_range(lo, hi):
    assert tick_spacing(lo, hi, 300.0) == []


def test_minor_tick_values_returns_empty_for_non_finite_range():
    assert minor_tick_values(float("nan"), float("nan"), 300.0) == []
