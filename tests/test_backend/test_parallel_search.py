"""Parallel searches must give the serial answer, and every run its seed.

The pool only changes where the work runs. A search spread over processes is
replayed in serial order and has to return the same candidates bit for bit,
with its RNG left where the serial loop leaves it; a line searched one
position per process has to write the serial line's rows; and a run with
no seed given has to record the one it drew, so it can be repeated.
"""

import numpy as np
import pandas as pd
import pytest

from src.backend.compute_pool import PoolMapper
from src.backend.designer_pool import plan_workers
from src.physics.designer import Designer
from src.physics.quantum_dot import dot_energies
from tests.test_backend.test_line_scan_designer import (MockTask, _line,
                                                        _table, tool_impl)  # noqa: F401


def _lens(Lmax=13.0):
    Et = np.array([E for E, _ in dot_energies("disc", (4.0, 5.0), 0.322, 6)])
    return {'Et': Et, 'meff': 0.322, 'ndim': '0D', 'coords': 'disc',
            'sym': '', 'fixed': {'d1': None, 'd2': None, 'd3': None},
            'Lmin': 1.0, 'Lmax': Lmax, 'tol': 5.0, 'maxsol': 6,
            'priority': 'uniform', 'match': 'delta_e', 'carrier': 'e'}


def _key(sols):
    return [(tuple(map(float, s['dims'])), float(s['RRMSE']), s.get('meff'))
            for s in sols]


@pytest.mark.parametrize('method', ['find_solutions', 'enumerate_solutions'])
def test_a_pooled_search_returns_the_serial_candidates(method):
    p = _lens()
    serial, pooled = Designer(seed=12345), Designer(seed=12345,
                                                    mapper=PoolMapper(4))
    assert _key(getattr(pooled, method)(p)) == _key(getattr(serial, method)(p))
    # The speculative passes past the quota are rewound: a second search on
    # the same Designer draws what the serial one draws.
    assert (pooled._rng.bit_generator.state
            == serial._rng.bit_generator.state)


def test_masses_searched_one_after_another_share_the_serial_rng():
    p = {**_lens(), 'share_mass_search': False}
    carrier = {'Et': p['Et'], 'carrier': 'e', 'label': 'electron',
               'meffs': [0.3, 0.39]}
    serial = Designer(seed=7).search_carrier(p, carrier)
    pooled = Designer(seed=7, mapper=PoolMapper(4)).search_carrier(p, carrier)
    assert _key(pooled) == _key(serial)


def _rows(tool_impl, result):
    return _table(tool_impl, result).drop(columns=['seed'])


def test_a_pooled_line_writes_the_serial_rows(tool_impl):  # noqa: F811
    tool_impl._datasets['line'] = _line()
    params = {'height': 3.0, 'maxsol': 1, 'seed': 20260823, 'ndim': '1D',
              'coords': 'cartesian', 'match': 'delta_e', 'Lmax': 20.0}
    serial = tool_impl.design_line_scan(MockTask(), 'line',
                                        {**params, 'workers': 1})
    pooled = tool_impl.design_line_scan(MockTask(), 'line',
                                        {**params, 'workers': 4})
    pd.testing.assert_frame_equal(_rows(tool_impl, pooled),
                                  _rows(tool_impl, serial))


def test_a_blank_seed_is_drawn_once_and_recorded(tool_impl):  # noqa: F811
    tool_impl._datasets['line'] = _line()
    params = {'height': 3.0, 'maxsol': 1, 'ndim': '1D', 'coords': 'cartesian',
              'match': 'delta_e', 'Lmax': 20.0}
    first = tool_impl.design_line_scan(MockTask(), 'line',
                                       {**params, 'seed': None})
    seed = first['seed']
    assert isinstance(seed, int)
    table = _table(tool_impl, first)
    assert set(table['seed']) == {seed}
    assert tool_impl._datasets[first['dataset']].metadata \
        .additional_info['seed'] == seed

    again = tool_impl.design_line_scan(MockTask(), 'line',
                                       {**params, 'seed': seed})
    pd.testing.assert_frame_equal(_rows(tool_impl, again),
                                  _rows(tool_impl, first))


@pytest.mark.parametrize('requested,n,expected', [
    (1, 1, (1, 1)),        # serial asked for, serial given
    (1, 50, (1, 1)),
    (4, 1, (1, 4)),        # one spectrum: its search is spread
    (4, 2, (1, 4)),
    (4, 3, (3, 1)),        # enough spectra: one per worker
    (4, 50, (4, 1)),
])
def test_one_grain_of_parallelism_at_a_time(requested, n, expected):
    assert plan_workers(requested, n) == expected


# ── reusing an enumeration across a changed range ──────────────────────────

from src.backend import designer_memo  # noqa: E402
from src.physics.enum_memo import (EnumerationMemo, RANGE_ONLY,  # noqa: E402
                                   objective_key)
import tests.test_backend.test_designer_consensus as C  # noqa: E402


@pytest.mark.parametrize('all_spectra', [True, False])
def test_a_rerun_with_a_wider_range_writes_the_fresh_tables(tmp_path,
                                                           all_spectra):
    """Pool sweep (memo shipped to and from the workers) and one spectrum
    (memo in-process): after a run at 13 nm, the run at 18 nm reuses its
    nodes and must write what a run with reuse switched off writes."""
    designer_memo.clear()
    run = dict(search_mode='enumerate', all_spectra=all_spectra)
    C._run(tmp_path / "warm", C.TWO_WELLS, Lmax=13.0, **run)
    hits = sum(m.hits for m in designer_memo._memos.values())
    warm_tool, warm = C._run(tmp_path / "reuse", C.TWO_WELLS, Lmax=18.0, **run)
    # The rerun really reused the first run's refinements — a memo that is
    # silently dropped also writes the fresh tables, so this is the check
    # that the test tests anything.
    assert sum(m.hits for m in designer_memo._memos.values()) > hits
    cold_tool, cold = C._run(tmp_path / "cold", C.TWO_WELLS, Lmax=18.0,
                             enum_reuse=False, **run)
    assert warm['candidates_total'] == cold['candidates_total'] > 0
    for suffix in ('Candidates', 'Levels'):
        pd.testing.assert_frame_equal(C._table(warm_tool, suffix),
                                      C._table(cold_tool, suffix))


def test_the_key_ignores_only_what_the_objective_never_reads():
    p = _lens()
    assert objective_key({**p, 'Lmax': 25.0, 'tol': 1.0}) == objective_key(p)
    for changed in ({'meff': 0.39}, {'match': 'absolute'},
                    {'Et': p['Et'] * 1.01}, {'coords': 'spherical'},
                    {'fixed': {'d1': 4.0, 'd2': None, 'd3': None}}):
        assert objective_key({**p, **changed}) != objective_key(p)
    # The fields the objective path reads must never be range-only.
    assert not RANGE_ONLY & {'Et', 'meff', 'ndim', 'coords', 'sym', 'fixed',
                             'match', 'priority', 'assign'}


def test_a_memoised_enumeration_matches_a_fresh_one_after_each_range_change():
    memo = EnumerationMemo()
    for Lmin, Lmax in ((1.0, 13.0), (1.0, 18.0), (0.9, 18.0), (1.0, 13.0)):
        p = {**_lens(), 'Lmin': Lmin, 'Lmax': Lmax}
        fresh = Designer().enumerate_solutions(p)
        reused = Designer(memo=memo).enumerate_solutions(p)
        assert _key(reused) == _key(fresh)
