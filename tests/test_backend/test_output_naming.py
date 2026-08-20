"""
Tests for output filenames: they must stay distinct.

A tool run over many datasets writes one file per dataset. If two datasets
produce the same filename, the second silently overwrites the first — which
is how 18 selected line scans left only 8 CSVs on disk.
"""

import pytest

from src.backend.app_backend import AppBackend


class Naming:
    """The naming helpers, without a Qt application behind them."""

    _naming_convention = "[dataset_name]"
    _naming_date_format = "dd-mm-yyyy"
    _current_file_index = 1
    MAX_FILENAME_LENGTH = AppBackend.MAX_FILENAME_LENGTH
    _FILENAME_TAIL = AppBackend._FILENAME_TAIL
    _sanitize_filename = AppBackend._sanitize_filename
    _disambiguate_filename = AppBackend._disambiguate_filename
    _extract_clean_base_name = AppBackend._extract_clean_base_name
    _apply_naming_convention = AppBackend._apply_naming_convention


@pytest.fixture
def naming():
    return Naming()


def line_dataset(line, pts, reps, span, sweep):
    return f"2026Jul21-143815 · {line} ({pts}pts_{reps}reps_{span}) · {sweep}"


class TestSanitize:
    def test_short_names_are_untouched_apart_from_spaces(self, naming):
        assert naming._sanitize_filename("STS grid 1") == "STS_grid_1"

    def test_path_characters_are_removed(self, naming):
        assert "/" not in naming._sanitize_filename("a/b:c*d")

    def test_a_long_name_keeps_its_tail(self, naming):
        """The tail is what distinguishes two outputs — cutting it merged
        Mixed, Forward and Backward onto one file."""
        name = "x" * 200 + "_Backward_1st_Derivative"
        safe = naming._sanitize_filename(name)
        assert len(safe) <= naming.MAX_FILENAME_LENGTH
        assert safe.endswith("_Backward_1st_Derivative")
        assert safe.startswith("xxxx")

    def test_names_differing_only_at_the_end_stay_different(self, naming):
        base = "y" * 200
        assert (naming._sanitize_filename(base + "_Forward")
                != naming._sanitize_filename(base + "_Backward"))


class TestLineScanFamily:
    """The case from the project: 6 lines x 3 sweeps."""

    def _names(self, naming):
        out = []
        for line, pts, reps, span in (("line1", 26, 63, "pt11->pt62"),
                                      ("line2", 62, 63, "pt67->pt190"),
                                      ("line3", 62, 63, "pt203->pt326"),
                                      ("line4", 26, 1, "pt12->pt63"),
                                      ("line5", 62, 1, "pt68->pt191"),
                                      ("line6", 62, 1, "pt204->pt327")):
            for sweep in ("Mixed", "Forward", "Backward"):
                out.append(naming._apply_naming_convention(
                    line_dataset(line, pts, reps, span, sweep),
                    operation="1st_Derivative"))
        return out

    def test_every_dataset_gets_its_own_file(self, naming):
        names = self._names(naming)
        assert len(names) == 18
        assert len(set(names)) == 18, "outputs would overwrite each other"

    def test_the_sweep_direction_survives(self, naming):
        names = self._names(naming)
        assert sum('Backward' in n for n in names) == 6
        assert sum('Forward' in n for n in names) == 6

    def test_the_operation_survives(self, naming):
        assert all('1st_Derivative' in n for n in self._names(naming))


class TestCollisionGuard:
    def test_two_datasets_that_sanitize_alike_do_not_share_a_file(self, naming):
        first = naming._apply_naming_convention("Sample (a)", operation="Smoothed")
        second = naming._apply_naming_convention("Sample [a]", operation="Smoothed")
        assert first != second

    def test_rerunning_the_same_dataset_reuses_its_name(self, naming):
        """Re-running a tool must overwrite its own output, not pile up
        copies."""
        first = naming._apply_naming_convention("Sample", operation="Smoothed")
        second = naming._apply_naming_convention("Sample", operation="Smoothed")
        assert first == second

    def test_a_preview_does_not_claim_the_name(self, naming):
        preview = naming._apply_naming_convention("Sample", operation="Smoothed",
                                                  preview=True)
        real = naming._apply_naming_convention("Sample", operation="Smoothed")
        assert preview == real
