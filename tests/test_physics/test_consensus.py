"""
Tests for the consensus over a line of spectra.

Every test here plants a line whose answer is known and asks the module for
it back. The rows are the Designer Candidates table's own shape, built by
hand — nothing runs the solver, so the whole file is milliseconds.

The things worth checking are the claims the module makes about physics, not
its arithmetic: that a spectrum votes once however many candidates it
emitted, that grouping happens in R and not in a size that mixes R with an
undetermined L_z, that a mode nobody else backs is discarded, that a
spectrum the data cannot place says so instead of being forced onto a well,
and that the null contrast is reproducible.
"""

import math

import numpy as np
import pytest

from src.physics.consensus import (AdmissibleSet, ConsensusResult,
                                   admissible_sets, candidate_weight,
                                   consensus, coord_function, default_bandwidth,
                                   delta_stability, find_modes,
                                   identity_signature, log_first_dim,
                                   log_size_nm, MAX_BANDWIDTH, MIN_BANDWIDTH,
                                   normalised_weights, null_contrast,
                                   soft_assign)


def _row(spectrum, candidate=0, r_nm=5.0, err=1.0, n_levels=4, skipped=0,
         qn_min=1, lz_nm=3.0):
    """One row of the Designer Candidates table."""
    return {
        'spectrum_index': spectrum,
        'candidate': candidate,
        'd1_nm': r_nm,
        'd2_nm': lz_nm,
        'd3_nm': float('nan'),
        'size_nm': float((r_nm * r_nm * lz_nm) ** (1.0 / 3.0)),
        'rrmse_de_pct': err,
        'n_levels': n_levels,
        'levels_skipped': skipped,
        'qn_min': qn_min,
        'qn_max': qn_min + n_levels - 1,
    }


def _line(radii, err=1.0, **kwargs):
    """One single-candidate spectrum per radius."""
    return [_row(i, 0, r_nm=r, err=err, **kwargs) for i, r in enumerate(radii)]


# ─── the admissible set ──────────────────────────────────────────────────────

def test_the_band_is_the_tie_band_of_pick_best():
    rows = [_row(0, 0, err=1.0), _row(0, 1, err=1.05), _row(0, 2, err=1.2)]
    sets = admissible_sets(rows)
    assert len(sets) == 1
    assert isinstance(sets[0], AdmissibleSet)
    assert sets[0].band == pytest.approx(1.1)
    assert sets[0].admissible == [0, 1]
    assert sets[0].n_candidates == 3


def test_a_small_error_falls_back_on_the_absolute_floor():
    # 10% of 0.1 pp is 0.01 pp, well inside optimiser noise: the 0.05 pp
    # floor is what keeps two identical fits from being ranked.
    rows = [_row(0, 0, err=0.10), _row(0, 1, err=0.14), _row(0, 2, err=0.20)]
    sets = admissible_sets(rows)
    assert sets[0].band == pytest.approx(0.15)
    assert sets[0].admissible == [0, 1]


def test_placeholder_and_unusable_rows_are_not_candidates():
    rows = [_row(0, 0, err=1.0), _row(0, 1, err=float('nan')),
            _row(1, -1, err=float('nan')), _row(2, 0, r_nm=float('nan'))]
    sets = admissible_sets(rows, coord_fn=log_first_dim)
    assert [s.spectrum_index for s in sets] == [0]
    assert sets[0].row_indices == [0]


def test_a_wider_tolerance_admits_more():
    rows = [_row(0, 0, err=1.0), _row(0, 1, err=1.3), _row(0, 2, err=2.0)]
    assert admissible_sets(rows)[0].n_admissible == 1
    assert admissible_sets(rows, delta_rel=0.5)[0].n_admissible == 2
    assert admissible_sets(rows, delta_abs=1.0)[0].n_admissible == 3


# ─── weights ─────────────────────────────────────────────────────────────────

def test_more_levels_is_more_evidence():
    assert candidate_weight(_row(0, n_levels=5)) > candidate_weight(_row(0, n_levels=3))


def test_a_skipped_level_is_a_free_parameter_and_costs_weight():
    assert candidate_weight(_row(0, n_levels=4, skipped=2)) < \
           candidate_weight(_row(0, n_levels=4, skipped=0))


def test_each_spectrum_carries_exactly_one_vote():
    rows = ([_row(0, c, r_nm=5.0 + 0.01 * c, err=1.0) for c in range(6)] +
            [_row(1, 0, r_nm=9.0, err=1.0)])
    sets = admissible_sets(rows)
    weights = normalised_weights(rows, sets)
    for s in sets:
        assert sum(weights[i] for i in s.admissible) == pytest.approx(1.0)


def test_a_degenerate_spectrum_does_not_outvote_three_agreeing_ones():
    # One spectrum with six candidates at 9 nm against three spectra with one
    # candidate each at 4 nm. Counting candidates, 9 nm wins 6 to 3; counting
    # spectra — which is what the physics asks — 4 nm wins 3 to 1.
    rows = [_row(s, 0, r_nm=4.0) for s in range(3)]
    rows += [_row(3, c, r_nm=9.0 + 0.02 * c) for c in range(6)]
    result = consensus(rows, log_first_dim, bandwidth=0.05, min_support_spectra=1)
    by_r = sorted(result.modes, key=lambda m: m['R_nm'])
    assert len(by_r) == 2
    small, large = by_r
    assert small['R_nm'] == pytest.approx(4.0, rel=0.05)
    assert small['support_spectra'] == 3
    assert large['support_spectra'] == 1
    assert small['weight'] > large['weight']


# ─── the coordinate ──────────────────────────────────────────────────────────

def test_there_is_no_default_coordinate():
    with pytest.raises(ValueError):
        coord_function('geometric_mean')
    with pytest.raises(ValueError):
        coord_function(None)
    assert coord_function('log_r') is log_first_dim
    assert coord_function('log_size') is log_size_nm


def test_grouping_in_r_separates_what_the_geometric_mean_merges():
    # Two wells, R = 4 nm and R = 8 nm, with the L_z the optimiser happened to
    # return chosen so the geometric-mean sizes coincide exactly. L_z is not
    # determined by the level differences, so this is a thing the data allows;
    # in size_nm the two wells are one number, in R they are two.
    rows = ([_row(s, 0, r_nm=4.0, lz_nm=8.0) for s in range(6)] +
            [_row(6 + s, 0, r_nm=8.0, lz_nm=2.0) for s in range(6)])
    assert rows[0]['size_nm'] == pytest.approx(rows[-1]['size_nm'])

    in_r = consensus(rows, log_first_dim, bandwidth=0.05)
    in_size = consensus(rows, log_size_nm, bandwidth=0.05)
    assert len(in_r.modes) == 2
    assert [m['R_nm'] for m in in_r.modes] == pytest.approx([4.0, 8.0], rel=0.05)
    assert len(in_size.modes) == 1


def test_lz_is_reported_as_a_range_not_as_a_value():
    rows = [_row(s, 0, r_nm=5.0, lz_nm=2.0 + s) for s in range(6)]
    mode = consensus(rows, log_first_dim, bandwidth=0.05).modes[0]
    assert mode['Lz_lo_nm'] == pytest.approx(2.0)
    assert mode['Lz_hi_nm'] == pytest.approx(7.0)
    assert mode['R_lo_nm'] == pytest.approx(mode['R_hi_nm'])


# ─── modes ───────────────────────────────────────────────────────────────────

def test_planted_modes_are_recovered():
    planted = [3.0, 6.0, 12.0]
    rows = []
    for s in range(12):
        r = planted[s % 3] * (1.0 + 0.01 * ((s % 5) - 2))
        rows.append(_row(s, 0, r_nm=r))
    result = consensus(rows, log_first_dim, bandwidth=0.05)
    assert len(result.modes) == 3
    assert [m['R_nm'] for m in result.modes] == pytest.approx(planted, rel=0.03)
    assert all(m['support_spectra'] == 4 for m in result.modes)
    assert result.meta['spread'] < 0.05


def test_the_degeneracy_valley_does_not_chain_two_modes_into_one():
    # Gap clustering joins these: every neighbour is within a nanometre of the
    # next, so single linkage walks from 4 nm to 8 nm in one group. A density
    # with a support floor cannot, because the bridge is one spectrum wide.
    rows = [_row(s, 0, r_nm=4.0 + 0.02 * s) for s in range(8)]
    rows += [_row(8 + s, 0, r_nm=8.0 + 0.02 * s) for s in range(8)]
    rows += [_row(16, c, r_nm=r) for c, r in enumerate((5.0, 6.0, 7.0))]
    result = consensus(rows, log_first_dim, bandwidth=0.05)
    assert len(result.modes) == 2
    assert [m['R_nm'] for m in result.modes] == pytest.approx([4.07, 8.07], rel=0.05)


def test_a_mode_below_the_support_floor_is_discarded():
    rows = [_row(s, 0, r_nm=5.0) for s in range(10)]
    rows.append(_row(10, 0, r_nm=20.0))
    result = consensus(rows, log_first_dim, bandwidth=0.05, min_support_frac=0.2)
    assert len(result.modes) == 1
    assert result.modes[0]['R_nm'] == pytest.approx(5.0, rel=0.05)
    # The orphan is not deleted, and it is not forced onto the surviving
    # mode either: 20 nm is far past two bandwidths of a 5 nm peak, so it
    # belongs to no mode. Forcing it in is what used to stretch a mode's
    # range from the pool's edge to the midpoint between peaks.
    orphan = [c for c in result.per_candidate if c['row_index'] == 10][0]
    assert orphan['admissible'] is True
    assert orphan['mode'] == -1
    assert result.meta['n_unassigned'] == 1
    # Its spectrum fits no consensus well, and says so.
    lonely = [p for p in result.per_spectrum if p['spectrum_index'] == 10][0]
    assert lonely['mode'] == -1 and lonely['mode_prob'] == 0.0
    # And the surviving mode's width is the peak's, not the pool's.
    assert result.modes[0]['R_max_nm'] == pytest.approx(5.0, rel=0.05)


def test_a_mode_reports_its_core_and_its_extent_separately():
    # Ten spectra tightly at 5 nm plus one straggler at 6 nm, still inside
    # the cutoff: the extent reaches it, the core does not.
    rows = [_row(s, 0, r_nm=5.0 + 0.01 * s) for s in range(10)]
    rows.append(_row(10, 0, r_nm=6.0))
    result = consensus(rows, log_first_dim, bandwidth=0.1, min_support_frac=0.2)
    assert len(result.modes) == 1
    m = result.modes[0]
    assert m['R_max_nm'] == pytest.approx(6.0)
    assert m['R_hi_nm'] < 5.5          # the 84th percentile ignores one straggler
    assert m['R_lo_nm'] <= m['R_hi_nm'] <= m['R_max_nm']
    assert m['R_min_nm'] <= m['R_lo_nm']


def test_the_support_floor_keeps_a_mode_enough_spectra_back():
    rows = [_row(s, 0, r_nm=5.0) for s in range(8)]
    rows += [_row(8 + s, 0, r_nm=20.0) for s in range(4)]
    result = consensus(rows, log_first_dim, bandwidth=0.05, min_support_frac=0.25)
    assert len(result.modes) == 2
    assert result.modes[1]['support_spectra'] == 4


def test_find_modes_counts_spectra_and_not_candidates():
    # Six candidates of one spectrum raise a perfectly good peak. One
    # spectrum is not support.
    values = np.log(np.array([5.0] * 8 + [12.0] * 6))
    ids = np.array(list(range(8)) + [8] * 6)
    weights = np.array([1.0] * 8 + [1.0 / 6] * 6)
    modes = find_modes(values, weights, bandwidth=0.05, min_support_frac=0.2,
                       spectrum_ids=ids)
    assert len(modes) == 1
    assert modes[0]['value_nm'] == pytest.approx(5.0, rel=0.02)


def test_the_default_bandwidth_follows_the_data_and_stays_in_bounds():
    tight = np.log(np.array([5.0, 5.01, 4.99, 5.02, 5.0]))
    loose = np.log(np.array([1.0, 3.0, 9.0, 27.0, 81.0]))
    h_tight = default_bandwidth(tight, np.ones(5))
    h_loose = default_bandwidth(loose, np.ones(5))
    assert MIN_BANDWIDTH <= h_tight <= MAX_BANDWIDTH
    assert MIN_BANDWIDTH <= h_loose <= MAX_BANDWIDTH
    assert h_tight < h_loose


# ─── soft membership ─────────────────────────────────────────────────────────

def test_a_spectrum_straddling_two_modes_reports_both():
    rows = [_row(s, 0, r_nm=4.0) for s in range(6)]
    rows += [_row(6 + s, 0, r_nm=8.0) for s in range(6)]
    rows += [_row(12, 0, r_nm=4.0), _row(12, 1, r_nm=8.0)]
    result = consensus(rows, log_first_dim, bandwidth=0.05)
    assert len(result.modes) == 2
    straddler = [p for p in result.per_spectrum if p['spectrum_index'] == 12][0]
    assert straddler['n_admissible'] == 2
    assert straddler['mode_prob'] == pytest.approx(0.5)
    assert straddler['mode_2nd_prob'] == pytest.approx(0.5)
    assert straddler['mode_2nd'] != straddler['mode']
    assert straddler['mode_entropy'] == pytest.approx(math.log(2), rel=1e-6)
    assert straddler['R_lo_nm'] == pytest.approx(4.0)
    assert straddler['R_hi_nm'] == pytest.approx(8.0)

    decided = [p for p in result.per_spectrum if p['spectrum_index'] == 0][0]
    assert decided['mode_prob'] == pytest.approx(1.0)
    assert decided['mode_entropy'] == pytest.approx(0.0)


def test_soft_membership_lets_the_supports_sum_above_one():
    rows = [_row(s, 0, r_nm=4.0) for s in range(4)]
    rows += [_row(4 + s, 0, r_nm=8.0) for s in range(4)]
    rows += [_row(8 + s, c, r_nm=r) for s in range(2)
             for c, r in enumerate((4.0, 8.0))]
    result = consensus(rows, log_first_dim, bandwidth=0.05)
    assert sum(m['support_frac'] for m in result.modes) > 1.0


def test_soft_assign_rows_are_probabilities():
    values = np.log(np.array([4.0, 8.0, 4.0, 4.1]))
    weights = np.array([0.5, 0.5, 1.0, 1.0])
    ids = np.array([0, 0, 1, 2])
    out = soft_assign(values, weights, ids, [math.log(4.0), math.log(8.0)])
    assert out.membership.shape == (3, 2)
    assert out.membership.sum(axis=1) == pytest.approx([1.0, 1.0, 1.0])
    assert out.membership[0] == pytest.approx([0.5, 0.5])


# ─── assignment identity ─────────────────────────────────────────────────────

def test_the_signature_is_the_start_of_the_ladder_and_the_gaps_in_it():
    assert identity_signature(_row(0, qn_min=1, skipped=0)) == (1, 0)
    assert identity_signature(_row(0, qn_min=2, skipped=0)) != \
           identity_signature(_row(0, qn_min=1, skipped=0))
    # qn_max is not identity: it only says how many peaks the spectrum had.
    assert identity_signature(_row(0, qn_min=1, n_levels=3)) == \
           identity_signature(_row(0, qn_min=1, n_levels=5))


def test_the_same_radius_read_as_two_different_ladders_is_two_modes():
    rows = [_row(s, 0, r_nm=5.00, qn_min=1) for s in range(6)]
    rows += [_row(6 + s, 0, r_nm=5.05, qn_min=2) for s in range(6)]
    result = consensus(rows, log_first_dim, bandwidth=0.05)
    assert len(result.modes) == 2
    assert {m['signature'] for m in result.modes} == {(1, 0), (2, 0)}
    assert all(m['support_spectra'] == 6 for m in result.modes)
    assert [m['R_nm'] for m in result.modes] == pytest.approx([5.0, 5.05], rel=0.02)


def test_without_the_identity_rule_the_two_ladders_fuse():
    rows = [_row(s, 0, r_nm=5.00, qn_min=1) for s in range(6)]
    rows += [_row(6 + s, 0, r_nm=5.05, qn_min=2) for s in range(6)]
    result = consensus(rows, log_first_dim, bandwidth=0.05, identity=False)
    assert len(result.modes) == 1


def test_one_stray_assignment_does_not_split_a_good_mode():
    rows = [_row(s, 0, r_nm=5.0, qn_min=1) for s in range(11)]
    rows.append(_row(11, 0, r_nm=5.0, qn_min=3))
    result = consensus(rows, log_first_dim, bandwidth=0.05,
                       identity_split_frac=0.25)
    assert len(result.modes) == 1
    assert result.modes[0]['signature'] == (1, 0)


# ─── the tables ──────────────────────────────────────────────────────────────

def test_every_usable_row_appears_once_in_the_candidate_table():
    rows = [_row(0, 0, err=1.0), _row(0, 1, err=1.05), _row(0, 2, err=3.0),
            _row(1, 0, err=1.0), _row(1, -1, err=float('nan'))]
    result = consensus(rows, log_first_dim, bandwidth=0.05, min_support_spectra=1)
    assert sorted(c['row_index'] for c in result.per_candidate) == [0, 1, 2, 3]
    rejected = [c for c in result.per_candidate if c['row_index'] == 2][0]
    assert rejected['admissible'] is False
    assert rejected['weight'] == 0.0
    assert rejected['mode'] == -1
    assert sum(c['weight'] for c in result.per_candidate) == pytest.approx(2.0)


def test_the_spectrum_table_carries_the_band_it_was_judged_by():
    rows = [_row(0, 0, err=2.0), _row(0, 1, err=2.15), _row(1, 0, err=1.0)]
    result = consensus(rows, log_first_dim, bandwidth=0.05, min_support_spectra=1)
    first = result.per_spectrum[0]
    assert first['best_de_pct'] == pytest.approx(2.0)
    assert first['band_de_pct'] == pytest.approx(2.2)
    assert first['n_candidates'] == 2
    assert first['n_admissible'] == 2


def test_a_table_with_nothing_usable_gives_an_empty_consensus():
    rows = [_row(0, -1, err=float('nan')), _row(1, -1, err=float('nan'))]
    result = consensus(rows, log_first_dim)
    assert isinstance(result, ConsensusResult)
    assert result.modes == [] and result.per_spectrum == [] and result.per_candidate == []
    assert result.meta['n_spectra'] == 0
    assert consensus([], log_first_dim).modes == []


def test_the_result_converts_to_plain_dicts_for_a_table_writer():
    rows = _line([5.0, 5.05, 4.95])
    out = consensus(rows, log_first_dim, bandwidth=0.05).to_dict()
    assert set(out) == {'modes', 'per_spectrum', 'per_candidate', 'meta'}
    assert set(out['modes'][0]) >= {
        'mode', 'R_nm', 'R_lo_nm', 'R_hi_nm', 'Lz_lo_nm', 'Lz_hi_nm',
        'support_spectra', 'support_frac', 'mean_rrmse_de_pct', 'qn_min',
        'qn_max', 'levels_skipped_mean'}
    assert set(out['per_spectrum'][0]) >= {
        'spectrum_index', 'n_candidates', 'n_admissible', 'best_de_pct',
        'band_de_pct', 'R_lo_nm', 'R_hi_nm', 'R_consensus_nm', 'mode',
        'mode_prob', 'mode_2nd', 'mode_2nd_prob', 'mode_entropy'}
    assert set(out['per_candidate'][0]) >= {
        'row_index', 'admissible', 'band_de_pct', 'weight', 'mode',
        'mode_R_nm', 'dist_nm'}


# ─── is it better than chance? ───────────────────────────────────────────────

def _degenerate_line(n_spectra=12, true_r=5.0, seed=0):
    """Every spectrum sees the same well, plus two decoys it cannot rule out."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_spectra):
        rows.append(_row(s, 0, r_nm=true_r * (1 + 0.01 * rng.standard_normal()), err=1.0))
        for c in (1, 2):
            rows.append(_row(s, c, r_nm=float(np.exp(rng.uniform(math.log(2.0), math.log(20.0)))),
                             err=1.02))
    return rows


def test_the_null_contrast_is_reproducible_under_a_fixed_seed():
    rows = _degenerate_line()
    a = null_contrast(rows, log_first_dim, n_draws=25, seed=17, bandwidth=0.05)
    b = null_contrast(rows, log_first_dim, n_draws=25, seed=17, bandwidth=0.05)
    assert np.array_equal(a['spreads'], b['spreads'], equal_nan=True)
    assert a['p_value'] == b['p_value']
    c = null_contrast(rows, log_first_dim, n_draws=25, seed=18, bandwidth=0.05)
    assert not np.array_equal(a['spreads'], c['spreads'], equal_nan=True)


def test_the_null_contrast_touches_no_global_randomness():
    rows = _degenerate_line()
    np.random.seed(3)
    before = np.random.random()
    np.random.seed(3)
    null_contrast(rows, log_first_dim, n_draws=10, seed=1, bandwidth=0.05)
    assert np.random.random() == before


def test_a_shared_well_is_tighter_than_a_random_pick_from_the_same_sets():
    rows = _degenerate_line(n_spectra=14, seed=4)
    null = null_contrast(rows, log_first_dim, n_draws=200, seed=5, bandwidth=0.05)
    assert null['observed_spread'] < null['spread_median']
    assert null['p_value'] < 0.05
    assert null['tighter_than_chance'] is True
    assert null['mean_set_size'] == pytest.approx(3.0)


def test_spectra_from_all_different_wells_produce_no_tight_mode():
    radii = np.exp(np.linspace(math.log(2.0), math.log(20.0), 12))
    scattered = consensus(_line(radii), log_first_dim)
    planted = consensus(_line([5.0] * 12), log_first_dim)
    assert planted.meta['spread'] < 0.01
    assert scattered.meta['spread'] > 0.15
    # No mode is both broadly supported and tight — a broad blob is allowed to
    # exist, a well is not allowed to be invented.
    for m in scattered.modes:
        tight = m['R_hi_nm'] <= 1.2 * m['R_lo_nm']
        assert not (tight and m['support_frac'] >= 0.5)


def test_a_null_contrast_over_single_candidate_sets_has_nothing_to_say():
    # Nothing to draw: the test is over the choice inside the admissible set,
    # and here there is no choice. It must say so rather than claim support.
    null = null_contrast(_line([5.0] * 10), log_first_dim, n_draws=50, seed=2,
                         bandwidth=0.05)
    assert null['mean_set_size'] == pytest.approx(1.0)
    assert null['p_value'] == pytest.approx(1.0)
    assert null['tighter_than_chance'] is False


def test_null_contrast_with_no_draws_still_reports_the_observation():
    null = null_contrast(_degenerate_line(), log_first_dim, n_draws=0, seed=1)
    assert null['n_draws'] == 0
    assert np.isfinite(null['observed_spread'])
    assert math.isnan(null['p_value'])


# ─── stability in the tolerance ──────────────────────────────────────────────

def test_delta_stability_reports_one_row_per_tolerance():
    rows = _degenerate_line(n_spectra=10, seed=6)
    deltas = [(0.01, 0.02), (0.05, 0.1), (0.5, 1.0)]
    table = delta_stability(rows, log_first_dim, deltas, bandwidth=0.05)
    assert len(table) == 3
    assert [r['delta_abs'] for r in table] == [0.01, 0.05, 0.5]
    # A wider band can only admit more candidates, never fewer.
    sizes = [r['n_admissible'] for r in table]
    assert sizes == sorted(sizes)
    assert all(math.isnan(r['p_value']) for r in table)


def test_delta_stability_accepts_a_bare_tolerance_and_can_run_the_null():
    rows = _degenerate_line(n_spectra=8, seed=7)
    table = delta_stability(rows, log_first_dim, [0.05, 0.5], n_draws=15, seed=3,
                            bandwidth=0.05)
    assert [r['delta_abs'] for r in table] == [0.05, 0.5]
    assert all(np.isfinite(r['p_value']) for r in table)
    assert all(np.isfinite(r['null_median_spread']) for r in table)


def test_a_real_well_survives_the_whole_tolerance_range():
    rows = []
    for s in range(12):
        rows.append(_row(s, 0, r_nm=5.0 + 0.01 * (s % 3), err=1.0))
        rows.append(_row(s, 1, r_nm=5.0 + 0.01 * (s % 3), err=1.3))
    table = delta_stability(rows, log_first_dim,
                            [(0.01, 0.02), (0.05, 0.1), (0.2, 0.4)],
                            bandwidth=0.05)
    assert {r['n_modes'] for r in table} == {1}
    assert all(r['modes_R_nm'][0] == pytest.approx(5.01, rel=0.02) for r in table)
