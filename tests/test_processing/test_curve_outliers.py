"""
Tests for curve-outlier classification.

An outlier here is not a bad curve — it is a curve that does not belong to
the population it is about to be averaged into. The three kinds are told
apart by *where* along the sweep a curve departs, so most of these tests
plant one kind and check that only that kind is reported.
"""

import numpy as np
import pytest

from src.processing.curve_outliers import (
    BANDGAP,
    GROUP_BY_DATASET,
    GROUP_BY_POINT,
    KINDS,
    MIN_GROUP_SIZE,
    OFFSET,
    SATURATION,
    analyze_grouped,
    analyze_outliers,
    build_groups,
    select_grouped,
    select_outliers,
)

V = np.linspace(-1.5, 1.5, 128)


def _edge(gap_hi=0.8, gap_lo=-0.7, scale=1.0):
    """A tunnelling dI/dV: flat gap between two rising band edges."""
    return scale * (np.exp((V - gap_hi) / 0.06) / (1 + np.exp((V - gap_hi) / 0.06))
                    + np.exp(-(V - gap_lo) / 0.06) / (1 + np.exp(-(V - gap_lo) / 0.06)))


def _population(n=20, seed=0, noise=0.01):
    rng = np.random.default_rng(seed)
    return [_edge() + rng.normal(0, noise, V.size) for _ in range(n)]


def _matrix(curves):
    return np.column_stack(curves), [f"C{i:02d}" for i in range(len(curves))]


class TestCleanPopulation:
    """Nothing should be flagged when nothing is wrong."""

    @pytest.mark.parametrize("seed", range(6))
    def test_no_false_positives(self, seed):
        spectra, columns = _matrix(_population(20, seed=seed))
        assert analyze_outliers(V, spectra, columns).counts() == {
            OFFSET: 0, BANDGAP: 0, SATURATION: 0}

    def test_a_lone_departing_interval_is_noise(self):
        """Contiguity is what separates a band edge from a fluctuation.

        Measured over 40 clean populations: 3.6% of curves flagged when a
        single interval was enough, 0.0% requiring two adjacent ones.
        """
        curves = _population(20, seed=1)
        # Nudge one interval of one curve, in isolation.
        band = (V > 0.0) & (V < 0.35)
        curves[4] = curves[4].copy()
        curves[4][band] += 5.0
        spectra, columns = _matrix(curves)
        assert analyze_outliers(V, spectra, columns).kind_of.get(columns[4]) is None
        # Two adjacent intervals is a shape, and is reported.
        wider = (V > 0.0) & (V < 0.75)
        curves[4] = curves[4].copy()
        curves[4][wider] += 5.0
        spectra, _ = _matrix(curves)
        assert analyze_outliers(V, spectra, columns).kind_of[columns[4]] == BANDGAP


class TestOffsetOutliers:
    def test_a_curve_scaled_up_departs_everywhere(self):
        curves = _population(20, seed=2)
        curves[7] = curves[7] * 400
        spectra, columns = _matrix(curves)
        analysis = analyze_outliers(V, spectra, columns)
        assert analysis.of_kind(OFFSET) == [columns[7]]

    def test_a_curve_displaced_below_is_still_found(self):
        """Integrating the positive part only must not hide a negative offset:
        its intervals read ~0 against everyone else's positive area."""
        curves = _population(20, seed=3)
        curves[5] = curves[5] - 50.0
        spectra, columns = _matrix(curves)
        assert columns[5] in analyze_outliers(V, spectra, columns).of_kind(OFFSET)

    def test_reported_as_departing_most_intervals(self):
        curves = _population(20, seed=4)
        curves[2] = curves[2] * 500
        spectra, columns = _matrix(curves)
        info = analyze_outliers(V, spectra, columns).diagnostics[columns[2]]
        assert info['fraction'] >= 0.75
        assert info['max_abs_z'] > 10


class TestBandgapOutliers:
    def test_an_edge_in_the_wrong_place_departs_locally(self):
        curves = _population(20, seed=5)
        curves[9] = _edge(gap_hi=0.2)          # edge rises far earlier
        spectra, columns = _matrix(curves)
        analysis = analyze_outliers(V, spectra, columns)
        assert analysis.of_kind(BANDGAP) == [columns[9]]
        info = analysis.diagnostics[columns[9]]
        assert info['fraction'] < 0.75
        assert info['longest_run'] >= 2

    def test_the_departing_intervals_are_reported_in_volts(self):
        curves = _population(20, seed=6)
        curves[3] = _edge(gap_hi=0.2)
        spectra, columns = _matrix(curves)
        info = analyze_outliers(V, spectra, columns).diagnostics[columns[3]]
        # The edge moved from 0.8 V down to 0.2 V, so the intervals between
        # them are the ones that must differ.
        lows = [lo for lo, _ in info['intervals']]
        assert any(0.0 <= lo <= 0.9 for lo in lows), info['intervals']


class TestSaturationOutliers:
    def test_a_truncated_curve_is_saturation_not_offset(self):
        curves = _population(20, seed=7)
        clipped = curves[6].copy()
        clipped[:40] = np.nan
        clipped[-40:] = np.nan
        curves[6] = clipped
        spectra, columns = _matrix(curves)
        analysis = analyze_outliers(V, spectra, columns)
        assert analysis.of_kind(SATURATION) == [columns[6]]
        assert analysis.of_kind(OFFSET) == []

    def test_coverage_is_recorded(self):
        curves = _population(20, seed=8)
        clipped = curves[1].copy()
        clipped[:50] = np.nan
        curves[1] = clipped
        spectra, columns = _matrix(curves)
        info = analyze_outliers(V, spectra, columns).diagnostics[columns[1]]
        assert info['coverage'] < info['median_coverage']

    def test_a_truncated_curve_does_not_move_the_population(self):
        """It is excluded from the comparison it is not a member of, so it
        cannot drag the median and hide a real offset elsewhere."""
        curves = _population(20, seed=9)
        clipped = curves[0].copy()
        clipped[:60] = np.nan
        curves[0] = clipped
        curves[11] = curves[11] * 300
        spectra, columns = _matrix(curves)
        analysis = analyze_outliers(V, spectra, columns)
        assert analysis.of_kind(SATURATION) == [columns[0]]
        assert analysis.of_kind(OFFSET) == [columns[11]]


class TestTooFewCurves:
    def test_below_three_there_is_no_population(self):
        spectra, columns = _matrix(_population(2, seed=10))
        assert analyze_outliers(V, spectra, columns).counts() == {
            OFFSET: 0, BANDGAP: 0, SATURATION: 0}

    def test_mismatched_columns_are_rejected(self):
        spectra, columns = _matrix(_population(5, seed=11))
        with pytest.raises(ValueError):
            analyze_outliers(V, spectra, columns[:3])


class TestGrouping:
    """A line scan's overview holds many points; comparing across them would
    call the ends of the line outliers, because they genuinely differ."""

    def _two_points(self):
        rng = np.random.default_rng(12)
        columns, meta, curves = [], [], []
        for point in (1, 2):
            for rep in range(1, 21):
                name = f"P{point:02d}R{rep:02d}"
                columns.append(name)
                meta.append({'column': name, 'point_index': point, 'rep': rep})
                curves.append(_edge(gap_hi=0.8 if point == 1 else 0.4)
                              + rng.normal(0, 0.01, V.size))
        return np.column_stack(curves), columns, meta

    def test_point_grouping_reads_the_metadata(self):
        _, columns, meta = self._two_points()
        groups = build_groups(columns, meta, GROUP_BY_POINT)
        assert sorted(groups) == ['point 1', 'point 2']
        assert all(len(v) == 20 for v in groups.values())

    def test_dataset_grouping_is_one_population(self):
        _, columns, meta = self._two_points()
        groups = build_groups(columns, meta, GROUP_BY_DATASET)
        assert list(groups) == ['all curves']

    def test_line_position_is_used_when_there_is_no_point(self):
        columns = [f"P{p}R{r}" for p in (1, 2) for r in (1, 2)]
        meta = [{'column': c, 'line_pos': i // 2} for i, c in enumerate(columns)]
        assert sorted(build_groups(columns, meta)) == ['position 0', 'position 1']

    def test_without_metadata_everything_is_one_population(self):
        columns = [f"C{i}" for i in range(5)]
        assert list(build_groups(columns, None)) == ['all curves']
        assert list(build_groups(columns, [])) == ['all curves']

    def test_metadata_that_groups_nothing_falls_back(self):
        """One curve per group is not a grouping."""
        columns = [f"C{i}" for i in range(5)]
        meta = [{'column': c, 'point_index': i} for i, c in enumerate(columns)]
        assert list(build_groups(columns, meta)) == ['all curves']

    def test_points_are_compared_separately(self):
        """Two points with genuinely different gaps are not outliers of
        each other — but an odd curve inside one point still is."""
        spectra, columns, meta = self._two_points()
        spectra = spectra.copy()
        spectra[:, columns.index('P02R07')] *= 400

        grouped = analyze_grouped(V, spectra, columns,
                                  build_groups(columns, meta, GROUP_BY_POINT))
        flagged = [c for a in grouped.values() for c in a.kind_of]
        assert flagged == ['P02R07']

    def test_small_groups_are_skipped_not_guessed_at(self):
        columns = ['a', 'b', 'c', 'd']
        meta = [{'column': 'a', 'point_index': 1}, {'column': 'b', 'point_index': 1},
                {'column': 'c', 'point_index': 2}, {'column': 'd', 'point_index': 2}]
        groups = build_groups(columns, meta)
        assert all(len(v) < MIN_GROUP_SIZE for v in groups.values())
        assert analyze_grouped(V, np.zeros((V.size, 4)), columns, groups) == {}


class TestSelection:
    """The limit is what turns 'found' into 'removed'."""

    def _with_offsets(self, n_bad):
        curves = _population(30, seed=13)
        for i in range(n_bad):
            curves[i] = curves[i] * (300 + 10 * i)
        spectra, columns = _matrix(curves)
        return analyze_outliers(V, spectra, columns)

    def test_within_the_limit_they_are_removed(self):
        analysis = self._with_offsets(3)
        removed, messages = select_outliers(
            analysis, {OFFSET: True}, {OFFSET: 5})
        assert len(removed) == 3
        assert any("Removed 3 offset" in m for m in messages)

    def test_beyond_the_limit_nothing_is_removed(self):
        """That many is a distribution, not a few odd curves."""
        analysis = self._with_offsets(8)
        removed, messages = select_outliers(
            analysis, {OFFSET: True}, {OFFSET: 5})
        assert removed == []
        assert any("distribution" in m and "check them by eye" in m
                   for m in messages)

    def test_a_disabled_kind_is_left_alone(self):
        analysis = self._with_offsets(2)
        removed, messages = select_outliers(
            analysis, {OFFSET: False}, {OFFSET: 5})
        assert removed == []
        assert messages == []

    def test_kinds_are_decided_independently(self):
        curves = _population(20, seed=14)
        curves[1] = curves[1] * 400                 # offset
        curves[2] = _edge(gap_hi=0.2)               # bandgap
        spectra, columns = _matrix(curves)
        analysis = analyze_outliers(V, spectra, columns)
        removed, _ = select_outliers(
            analysis, {OFFSET: True, BANDGAP: False}, {OFFSET: 5, BANDGAP: 5})
        assert removed == [columns[1]]

    def test_limits_apply_per_group(self):
        """'At most 5 bad repetitions at this point', not 5 across a
        two-thousand-column overview."""
        rng = np.random.default_rng(15)
        columns, meta, curves = [], [], []
        for point in (1, 2):
            for rep in range(1, 21):
                name = f"P{point}R{rep:02d}"
                columns.append(name)
                meta.append({'column': name, 'point_index': point, 'rep': rep})
                curve = _edge() + rng.normal(0, 0.01, V.size)
                if rep <= 3:                     # 3 bad in each point
                    curve = curve * 400
                curves.append(curve)
        spectra = np.column_stack(curves)
        grouped = analyze_grouped(V, spectra, columns,
                                  build_groups(columns, meta, GROUP_BY_POINT))
        removed, _ = select_grouped(grouped, {OFFSET: True}, {OFFSET: 5})
        assert len(removed) == 6          # 3 per point, both within the limit

    def test_grouped_messages_name_their_group(self):
        rng = np.random.default_rng(16)
        columns, meta, curves = [], [], []
        for rep in range(1, 21):
            name = f"P01R{rep:02d}"
            columns.append(name)
            meta.append({'column': name, 'point_index': 1, 'rep': rep})
            curve = _edge() + rng.normal(0, 0.01, V.size)
            curves.append(curve * 400 if rep == 4 else curve)
        grouped = analyze_grouped(V, np.column_stack(curves), columns,
                                  build_groups(columns, meta, GROUP_BY_POINT))
        _, messages = select_grouped(grouped, {OFFSET: True}, {OFFSET: 5})
        assert any(m.startswith("point 1:") for m in messages)

    def test_clean_groups_stay_quiet(self):
        """16 points each saying 'nothing found' would bury the one that did."""
        rng = np.random.default_rng(17)
        columns, meta, curves = [], [], []
        for point in (1, 2, 3):
            for rep in range(1, 21):
                name = f"P{point}R{rep:02d}"
                columns.append(name)
                meta.append({'column': name, 'point_index': point, 'rep': rep})
                curves.append(_edge() + rng.normal(0, 0.01, V.size))
        grouped = analyze_grouped(V, np.column_stack(curves), columns,
                                  build_groups(columns, meta, GROUP_BY_POINT))
        _, messages = select_grouped(grouped, {k: True for k in KINDS},
                                     {k: 5 for k in KINDS})
        assert messages == []
