"""
Tests for the shared session-organisation helpers.

These encode the rules the Omicron MATRIX loader established and the other
loaders now follow: a session is named after when it was taken, the clock time
is dropped only while it stays unambiguous, and a grid's sample positions come
out in metres and in row-major order.
"""

import numpy as np
import pytest
from datetime import datetime

from src.data_loaders.session_organization import (
    disambiguate_labels,
    format_session_label,
    grid_positions_m,
    session_labels_from_times,
    spatial_info,
)


class TestFormatSessionLabel:
    def test_date_only_by_default(self):
        assert format_session_label(datetime(2026, 5, 6, 19, 52, 31)) == "2026May06"

    def test_keeps_time_when_asked(self):
        assert format_session_label(
            datetime(2026, 5, 6, 19, 52, 31), keep_time=True) == "2026May06-195231"

    def test_falls_back_without_a_time(self):
        assert format_session_label(None, fallback="folder") == "folder"


class TestDisambiguateLabels:
    def test_short_label_kept_when_unique(self):
        times = [datetime(2026, 5, 2, 19, 51), datetime(2026, 5, 6, 19, 52)]
        assert session_labels_from_times(times) == ["2026May02", "2026May06"]

    def test_same_day_sessions_keep_their_times(self):
        """Dropping the time would merge two sessions into one folder."""
        times = [datetime(2026, 5, 2, 19, 51), datetime(2026, 5, 2, 19, 54)]
        assert session_labels_from_times(times) == [
            "2026May02-195100", "2026May02-195400"]

    def test_only_the_clashing_day_keeps_its_time(self):
        times = [datetime(2026, 5, 2, 19, 51), datetime(2026, 5, 2, 19, 54),
                 datetime(2026, 5, 6, 10, 0)]
        assert session_labels_from_times(times) == [
            "2026May02-195100", "2026May02-195400", "2026May06"]

    def test_labels_are_unique_even_when_the_full_form_collides(self):
        """Two sessions must never share a folder, whatever the inputs."""
        same = datetime(2026, 5, 2, 19, 51, 0)
        labels = session_labels_from_times([same, same])
        assert len(set(labels)) == 2

    def test_missing_times_share_a_fallback_but_stay_distinct(self):
        labels = session_labels_from_times([None, None], fallback="run")
        assert len(set(labels)) == 2
        assert labels[0] == "run"

    def test_generic_form(self):
        mapping = disambiguate_labels(
            ["a", "b"], lambda k: "same", lambda k: f"full-{k}")
        assert mapping == {"a": "full-a", "b": "full-b"}


class TestGridPositionsM:
    @pytest.fixture
    def geometry(self):
        return {'x_start': 0.0, 'y_start': 0.0,
                'x_end': 7e-9, 'y_end': 7e-9, 'nx': 8, 'ny': 8}

    def test_row_major_order(self, geometry):
        pos = grid_positions_m(geometry, 64)
        # First row varies x and holds y; the second row steps y.
        assert pos[0] == (0.0, 0.0)
        assert pos[7][0] == pytest.approx(7e-9)
        assert pos[7][1] == pytest.approx(0.0)
        assert pos[8][0] == pytest.approx(0.0)
        assert pos[8][1] == pytest.approx(1e-9)

    def test_spans_the_rectangle_end_to_end(self, geometry):
        pos = grid_positions_m(geometry, 64)
        assert pos[-1] == pytest.approx((7e-9, 7e-9))

    def test_single_sample_axis_sits_at_the_centre(self):
        pos = grid_positions_m(
            {'x_start': 0.0, 'y_start': 0.0, 'x_end': 4e-9, 'y_end': 2e-9,
             'nx': 1, 'ny': 2}, 2)
        assert pos[0][0] == pytest.approx(2e-9)

    def test_count_mismatch_returns_none(self, geometry):
        """Better no scale than an invented one."""
        assert grid_positions_m(geometry, 63) is None

    def test_missing_geometry_returns_none(self):
        assert grid_positions_m(None, 8) is None
        assert grid_positions_m({'nx': 2}, 8) is None

    def test_degenerate_grid_returns_none(self):
        assert grid_positions_m(
            {'x_start': 0, 'y_start': 0, 'x_end': 1e-9, 'y_end': 1e-9,
             'nx': 0, 'ny': 0}, 0) is None


class TestSpatialInfo:
    def test_omits_what_is_unknown(self):
        assert spatial_info() == {}

    def test_carries_what_is_known(self):
        info = spatial_info(spectrum_meta=[{'column': 'A'}],
                            positions_m=[(1.0, 2.0)], layout='line')
        assert info['spectrum_meta'] == [{'column': 'A'}]
        assert info['position_m'] == [[1.0, 2.0]]
        assert info['spatial_layout'] == 'line'
