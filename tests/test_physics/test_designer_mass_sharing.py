"""One search for a list of masses must answer what one search per mass did.

The physics is exact — every model depends on m*·L² only — so the checks
here are about the bookkeeping: each mass gets candidates inside its own
box, carrying its own mass and ladder, at the error its geometry really has,
and the best fit per mass is the one the per-mass search found.
"""

import numpy as np
import pytest

from src.physics.designer import MATCH_GAPS, Designer
from src.physics.quantum_dot import dot_energies

MEFFS = [0.322, 0.39, 0.25]


def _search(**over):
    lv = [E for E, _ in dot_energies('disc', (4.0, 6.0), 0.322, 20)]
    Et = np.array(sorted(set(np.round(lv, 6)))[1:7]) + 0.3
    p = {'ndim': '0D', 'coords': 'disc', 'sym': '',
         'fixed': {'d1': None, 'd2': None, 'd3': None},
         'Lmin': 1.0, 'Lmax': 18.0, 'box': {}, 'tol': 5.0, 'maxsol': 6,
         'priority': 'uniform', 'assign': 'energy', 'match': MATCH_GAPS,
         'enum_polish': 40, 'temperature_K': 90.0}
    p.update(over)
    carrier = {'carrier': 'e', 'label': 'electron', 'Et': Et, 'meffs': MEFFS}
    return p, carrier


def _enumerate(d):
    return lambda pm, _label: d.enumerate_solutions(pm)


def test_equivalent_geometry_scores_the_same():
    d = Designer(seed=0)
    p, carrier = _search()
    pm = {**p, 'Et': carrier['Et']}
    for m in MEFFS[1:]:
        k = np.sqrt(MEFFS[0] / m)
        for dims in [(4.0, 6.0), (2.3, 11.0), (7.5, 3.1)]:
            a = d.score_dims(dims, pm, MEFFS[0])
            b = d.score_dims(tuple(x * k for x in dims), pm, m)
            assert b == pytest.approx(a, rel=1e-12)


@pytest.mark.parametrize('mode', ['enumerate', 'sample'])
def test_each_mass_gets_its_own_rebuilt_candidates(mode):
    d = Designer(seed=0)
    p, carrier = _search()
    search = (_enumerate(d) if mode == 'enumerate' else
              (lambda pm, _label: d.find_solutions(pm)))
    shared = d.search_masses(p, carrier, search)
    for m in MEFFS:
        mine = [s for s in shared if s['meff'] == m]
        assert mine
        box = d.bounds({**p, 'meff': m})
        for s in mine:
            # Its own mass, its own box, its own ladder at the error it
            # reports — rebuilt, not copied from the reference.
            assert all(lo <= v <= hi for v, (lo, hi) in zip(s['dims'], box))
            assert s['RRMSE'] <= p['tol']
            assert d.score_dims(s['dims'], {**p, 'Et': carrier['Et']},
                                m) == s['RRMSE']
    # The same population at every mass: one search, rescaled.
    errors = {m: sorted(round(s['RRMSE'], 9) for s in shared
                        if s['meff'] == m) for m in MEFFS}
    assert errors[MEFFS[1]] == errors[MEFFS[0]]


def test_the_backend_enumerates_each_mass_separately_by_default():
    from src.backend.tool_implementations import ToolImplementations
    calls = []

    class Spy(Designer):
        def enumerate_solutions(self, p, **kw):
            calls.append(p['meff'])
            return []

    p, carrier = _search()
    ToolImplementations._designer_find(Spy(0), p, carrier,
                                       {'search_mode': 'enumerate'},
                                       lambda: False)
    assert calls == MEFFS
    calls.clear()
    ToolImplementations._designer_find(Spy(0), p, carrier,
                                       {'search_mode': 'enumerate',
                                        'share_mass_search': True},
                                       lambda: False)
    assert calls == [MEFFS[0]]


def test_a_pinned_dimension_keeps_the_per_mass_searches():
    d = Designer(seed=0)
    p, carrier = _search(fixed={'d1': None, 'd2': 6.0, 'd3': None})
    assert not d.shares_mass_search(p, MEFFS)
    assert not d.shares_mass_search(_search()[0], MEFFS[:1])
    assert d.shares_mass_search(_search()[0], MEFFS)


def test_the_reference_box_covers_every_mass():
    d = Designer(seed=0)
    p, _carrier = _search(box={'d1': (2.0, 8.0)})
    ref = d.reference_search(p, MEFFS)
    for m in MEFFS:
        k = np.sqrt(m / MEFFS[0])
        for key in ('d1', 'd2'):
            lo, hi = d._box(p, key)
            rlo, rhi = ref['box'][key]
            assert rlo <= lo * k * (1 + 1e-12) and hi * k <= rhi * (1 + 1e-12)
