"""Length-unit conversion used by every loader's pixel calibration."""

import pytest

from src.utils.units import nm_factor, pixel_size_to_nm, to_nm


class TestNmFactor:
    @pytest.mark.parametrize("unit,expected", [
        ("m", 1e9), ("mm", 1e6), ("µm", 1e3), ("um", 1e3), ("μm", 1e3),
        ("nm", 1.0), ("pm", 1e-3), ("Å", 0.1), ("angstrom", 0.1),
        ("micron", 1e3), ("micrometers", 1e3), ("Meters", 1e9),
    ])
    def test_known_units(self, unit, expected):
        assert nm_factor(unit) == pytest.approx(expected)

    def test_case_and_whitespace_insensitive(self):
        assert nm_factor("  NM  ") == 1.0

    @pytest.mark.parametrize("unit", ["volts", "V", "", None, 42])
    def test_non_length_units_are_rejected(self, unit):
        assert nm_factor(unit) is None


class TestToNm:
    def test_converts(self):
        assert to_nm(2.5, "µm") == pytest.approx(2500.0)
        assert to_nm(1e-8, "m") == pytest.approx(10.0)

    def test_unknown_unit_returns_none(self):
        assert to_nm(1.0, "volts") is None

    def test_non_numeric_returns_none(self):
        assert to_nm("abc", "nm") is None

    def test_nan_is_rejected(self):
        assert to_nm(float("nan"), "nm") is None


class TestPixelSizeToNm:
    def test_returns_dy_dx_order(self):
        """Deliberately (row, column), matching ImageMetadata.pixel_size_nm."""
        assert pixel_size_to_nm(0.5, 0.25, "um") == (250.0, 500.0)

    @pytest.mark.parametrize("dx,dy,unit", [
        (0.0, 1.0, "nm"),      # zero axis
        (1.0, -1.0, "nm"),     # negative axis
        (1.0, 1.0, "volts"),   # not a length
    ])
    def test_bad_input_leaves_calibration_unset(self, dx, dy, unit):
        assert pixel_size_to_nm(dx, dy, unit) is None
