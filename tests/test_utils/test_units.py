"""Length-unit conversion used by every loader's pixel calibration."""

import pytest

from src.utils.units import (nm_factor, pixel_size_to_nm, scale_from_metadata,
                             to_nm)


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


class TestNanosurfNestedGeometry:
    """Nanosurf records its scan geometry in NESTED dicts, which is why every
    map generated from that data exported as bare pixels: the loader had the
    numbers all along and nothing here looked inside them.
    """

    def test_a_spectroscopy_grid_gives_the_step_between_spectra(self):
        """x_start/x_end are the first and LAST spectrum, so a 100 wide grid
        spanning 1 µm has 99 gaps. Dividing by nx would shrink every pixel by
        1 % here and by 10 % on a 10 wide grid."""
        info = {"map_geometry": {"x_start": 0.0, "x_end": 1e-6,
                                 "y_start": 0.0, "y_end": 1e-6,
                                 "nx": 100, "ny": 100}}
        dx, dy, unit = scale_from_metadata(info)

        assert unit == "m"
        assert dx == pytest.approx(1e-6 / 99)
        assert dy == pytest.approx(1e-6 / 99)

    def test_a_topography_range_is_the_whole_field(self):
        """A scan RANGE is the full extent, so this one divides by the pixel
        count rather than by the gaps."""
        info = {"topo_geometry": {"scan_range_x": 1e-7, "scan_range_y": 1e-7}}
        dx, dy, unit = scale_from_metadata(info, shape=(100, 100))

        assert unit == "m"
        assert dx == pytest.approx(1e-9)
        assert dy == pytest.approx(1e-9)

    def test_the_spectroscopy_grid_wins_over_the_topography_scan(self):
        """They describe different things: the grid is what is being mapped,
        the scan range is the frame it sits in, and they routinely differ."""
        info = {"map_geometry": {"x_start": 0.0, "x_end": 1e-6,
                                 "y_start": 0.0, "y_end": 1e-6,
                                 "nx": 11, "ny": 11},
                "topo_geometry": {"scan_range_x": 5e-6, "scan_range_y": 5e-6}}
        dx, _dy, _unit = scale_from_metadata(info, shape=(11, 11))

        assert dx == pytest.approx(1e-6 / 10)

    def test_a_flat_key_still_wins_over_both(self):
        """Order of directness is unchanged: an explicit pixel size is not
        second-guessed by an extent."""
        info = {"pixel_size": {"dx": 2.0, "dy": 2.0, "unit": "nm"},
                "map_geometry": {"x_start": 0.0, "x_end": 1e-6, "y_start": 0.0,
                                 "y_end": 1e-6, "nx": 100, "ny": 100}}
        assert scale_from_metadata(info) == (2.0, 2.0, "nm")

    @pytest.mark.parametrize("mg", [
        {"x_start": 0.0, "x_end": 0.0, "y_start": 0.0, "y_end": 1e-6, "nx": 10, "ny": 10},
        {"x_start": 0.0, "x_end": 1e-6, "y_start": 0.0, "y_end": 1e-6, "nx": 1, "ny": 1},
        {"x_start": "?", "x_end": 1e-6, "y_start": 0.0, "y_end": 1e-6, "nx": 10, "ny": 10},
        {},
    ])
    def test_an_unusable_grid_is_declined_rather_than_invented(self, mg):
        """Don't invent a scale you don't have — the export warns instead."""
        assert scale_from_metadata({"map_geometry": mg}) == (None, None, None)
