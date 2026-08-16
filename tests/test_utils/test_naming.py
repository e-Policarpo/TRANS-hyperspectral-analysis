"""Tests for the zero-padded index helpers.

The point of padding is that *lexicographic* order matches numeric order,
because every surface that lists datasets sorts alphabetically. These tests
assert that property directly rather than just checking string shapes.
"""

import pytest

from src.utils.naming import (MIN_WIDTH, pad, pad_all, pad_width,
                              padded_series, strip_acquisition_time)


class TestPadWidth:
    def test_small_counts_use_the_minimum_width(self):
        assert pad_width(1) == MIN_WIDTH
        assert pad_width(9) == MIN_WIDTH
        assert pad_width(99) == 2

    def test_width_grows_with_magnitude(self):
        assert pad_width(100) == 3
        assert pad_width(1500) == 4

    def test_non_numeric_falls_back_to_minimum(self):
        assert pad_width(None) == MIN_WIDTH
        assert pad_width("nope") == MIN_WIDTH


class TestPad:
    def test_pads_to_the_width_of_the_largest(self):
        assert pad(3, 120) == "003"
        assert pad(3, 9) == "03"
        assert pad(120, 120) == "120"

    def test_negative_indices_are_left_alone(self):
        # Never occurs for dataset indices; padding one would be misleading.
        assert pad(-4, 100) == "-4"

    def test_non_numeric_passes_through(self):
        assert pad("x", 10) == "x"


class TestPaddedSeries:
    def test_series_shape(self):
        assert padded_series("Spectrum", 3) == [
            "Spectrum_01", "Spectrum_02", "Spectrum_03"]

    def test_series_can_start_at_zero(self):
        assert padded_series("Px", 3, start=0) == ["Px_00", "Px_01", "Px_02"]

    def test_empty_and_negative_counts(self):
        assert padded_series("S", 0) == []
        assert padded_series("S", -2) == []

    def test_custom_separator(self):
        assert padded_series("Rep", 2, sep="-") == ["Rep-01", "Rep-02"]

    @pytest.mark.parametrize("count", [9, 10, 11, 99, 100, 101, 250])
    def test_alphabetical_order_matches_numeric_order(self, count):
        """The whole reason padding exists."""
        names = padded_series("Spectrum", count)
        assert sorted(names) == names

    def test_unpadded_names_would_shuffle(self):
        """Guards the premise: without padding, sorting reorders them."""
        unpadded = [f"Spectrum_{i}" for i in range(1, 13)]
        assert sorted(unpadded) != unpadded

    def test_width_is_stable_within_one_series(self):
        names = padded_series("S", 120)
        assert len({len(n) for n in names}) == 1


class TestStripAcquisitionTime:
    """The clock-time block makes names unreadable; the date is what people
    recognise. Stripping must be conservative — it runs over every browser
    label and every exported filename."""

    @pytest.mark.parametrize("raw,expected", [
        ("2026Jun29-203950", "2026Jun29"),
        ("2026Jun15-203637", "2026Jun15"),
        ("2026Jun5-203637", "2026Jun5"),
        ("2026Jun29_203950", "2026Jun29"),
        ("2026-06-29-20-39-50", "2026-06-29"),
        ("2026-06-29_203950", "2026-06-29"),
        ("20260629-203950", "20260629"),
        ("2026Jun29-203950_scan", "2026Jun29_scan"),
    ])
    def test_removes_date_anchored_times(self, raw, expected):
        assert strip_acquisition_time(raw) == expected

    @pytest.mark.parametrize("raw", [
        "Sample_083011",         # six digits, but no date to anchor to
        "ParkRun_2026",
        "DtBuTPZ_run3",
        "2026Jun29",             # already timeless
        "08_11",                 # run/scan indices
        "Spectrum_01",
        "",
    ])
    def test_leaves_everything_else_alone(self, raw):
        assert strip_acquisition_time(raw) == raw

    def test_does_not_eat_minus_signs(self):
        """A naive separator cleanup turned "Map_-0.500" into "Map_0.500",
        silently flipping the sign in generated map names."""
        assert strip_acquisition_time("Map_-0.500_-0.300") == "Map_-0.500_-0.300"

    def test_non_string_input_passes_through(self):
        assert strip_acquisition_time(None) is None

    def test_never_returns_empty(self):
        assert strip_acquisition_time("2026Jun29-203950") != ""


class TestPadAll:
    def test_shares_one_width_across_the_collection(self):
        assert pad_all([1, 5, 100]) == ["001", "005", "100"]

    def test_empty(self):
        assert pad_all([]) == []
