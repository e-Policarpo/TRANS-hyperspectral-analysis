"""The vectorised score must be the reference score, bit for bit.

``Designer.fast_error`` replaces :meth:`Designer.match_and_score` inside the
optimiser's loop. A close answer is not good enough: ``flat_dims`` compares
scores at a few ulps, and the enumeration's nesting is promised bit for bit,
so the fast path has to return the same float or the search changes.
"""

import zlib

import numpy as np
import pytest

from src.physics.designer import (ASSIGN_ENERGY, ASSIGN_LOW_QN, MATCH_ABSOLUTE,
                                  MATCH_GAPS, MATCH_RATIOS, PRIORITY_GROUND,
                                  PRIORITY_LOW_QN, PRIORITY_UNIFORM, Designer)

GEOMETRIES = [
    ('0D', 'disc', '', 2),
    ('0D', 'spherical', '', 1),
    ('0D', 'parabolic', '', 2),
    ('1D', 'cartesian', '', 1),
    ('2D', 'circular', '', 1),
    ('2D', 'cartesian', 'rectangular', 2),
    ('3D', 'cylindrical', '', 2),
    ('3D', 'cartesian', 'orthorhombic', 3),
]


def _params(ndim, coords, sym, Et, match, priority):
    return {'ndim': ndim, 'coords': coords, 'sym': sym,
            'fixed': {'d1': None, 'd2': None, 'd3': None},
            'Lmin': 1.0, 'Lmax': 18.0, 'tol': 5.0, 'maxsol': 6,
            'priority': priority, 'assign': ASSIGN_ENERGY, 'match': match,
            'Et': Et, 'meff': 0.322}


def _reference(d, Ec, p, scale_term):
    matches, _offset, err = d.match_and_score(Ec, p['Et'], p)
    if scale_term:
        err += 1e-3 * d.abs_rrmse(matches, p['Et'], p['priority'])
    return err


@pytest.mark.parametrize('ndim,coords,sym,nfree', GEOMETRIES)
@pytest.mark.parametrize('match', [MATCH_GAPS, MATCH_ABSOLUTE, MATCH_RATIOS])
@pytest.mark.parametrize('priority', [PRIORITY_UNIFORM, PRIORITY_LOW_QN,
                                      PRIORITY_GROUND])
def test_fast_error_is_the_reference_float(ndim, coords, sym, nfree, match,
                                           priority):
    d = Designer(seed=0)
    rng = np.random.default_rng(
        zlib.crc32(f"{ndim}|{coords}|{match}|{priority}".encode()))
    for _ in range(60):
        n_targets = int(rng.integers(2, 8))
        # Read from E_F, so above the model's own levels: the delta-E
        # offset comes out negative, as it does on real spectra.
        Et = np.sort(rng.uniform(0.05, 1.5, n_targets)) + rng.uniform(0, 0.5)
        p = _params(ndim, coords, sym, Et, match, priority)
        opt = list(rng.uniform(1.0, 18.0, nfree))
        dims = d.params_to_dims(opt, p)
        Ec = d.compute_energies(dims, p['meff'], max(len(Et) * 3, 20), p)
        for scale_term in (False, True):
            fast = d.fast_error(Ec, Et, p, scale_term=scale_term)
            ref = _reference(d, Ec, p, scale_term and match == MATCH_RATIOS)
            assert fast == ref, (dims, Et, fast, ref)


def test_objective_and_score_dims_use_the_same_number():
    d = Designer(seed=0)
    Et = np.array([0.31, 0.36, 0.44, 0.47, 0.55])
    p = _params('0D', 'disc', '', Et, MATCH_GAPS, PRIORITY_UNIFORM)
    assert d.objective([4.1, 6.2], p) == d.score_dims((4.1, 6.2), p)


def test_rules_without_a_fast_form_fall_back():
    d = Designer(seed=0)
    Et = np.array([0.31, 0.36, 0.44])
    p = {**_params('0D', 'disc', '', Et, MATCH_GAPS, PRIORITY_UNIFORM),
         'assign': ASSIGN_LOW_QN}
    Ec = d.compute_energies((4.0, 5.0), p['meff'], 20, p)
    assert d.fast_error(Ec, Et, p) is None
    assert d.objective([4.0, 5.0], p) == d.match_and_score(Ec, Et, p)[2]
