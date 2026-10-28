#!/usr/bin/env python
"""Record the Confinement Designer's DEFAULT search output as a fixture.

Why this exists
---------------
``Designer.find_solutions`` is the one function in the program whose answer a
user reads as a measurement. Any change to the search — even one that only
ADDS an option — has to be able to prove that it did not move a number that
somebody has already written into a thesis. A tolerance-based comparison
cannot prove that: it lets a real change through as long as it is small.

So the contract is exact equality on the full float ``repr``. This script
records the contract from whatever tree it is run on; the test
``tests/test_physics/test_designer_search.py::test_default_path_is_unchanged``
replays it and compares with ``==``.

Run it BEFORE editing the designer::

    QT_QPA_PLATFORM=offscreen ~/.virtualenvs/trans-arm64/bin/python \
        scripts/record_designer_golden.py

It writes ``tests/fixtures/designer_golden.json`` (~160 configurations, a
little under half an hour). The seed is pinned, so the file is reproducible
on the same tree; regenerating it on a CHANGED tree is exactly the thing the
test is there to stop, so do not do it to make a red test go green.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.physics.analytical import box_energies_1d_eV      # noqa: E402
from src.physics.designer import (                          # noqa: E402
    MATCH_ABSOLUTE, MATCH_GAPS, MATCH_RATIOS,
    PRIORITY_UNIFORM, PRIORITY_GROUND, PRIORITY_LOW_QN,
    SYM_ORTHORHOMBIC, SYM_RECTANGULAR, SYM_TETRAGONAL, Designer,
)

SEED = 12345

#: The measured ladder this whole investigation is about: five levels off a
#: disordered MBE sample, none of them an exact model energy.
TARGETS_MEASURED = [1.503, 1.577, 1.622, 1.719, 1.804]

#: A synthetic ladder that IS exactly a 5 nm 1D box at m* = 0.067, so the
#: search has a true zero to find and a regression shows up as a non-zero
#: error rather than as a slightly different wrong answer.
TARGETS_SYNTHETIC_1D = [round(E, 12) for E, _qn
                        in box_energies_1d_eV(5.0, 0.067, 5)]

#: (name, ndim, coords, sym) — every geometry the search can be asked for.
GEOMETRIES = [
    ("0D_disc",           "0D", "disc",        ""),
    ("0D_spherical",      "0D", "spherical",   ""),
    ("0D_parabolic",      "0D", "parabolic",   ""),
    ("1D",                "1D", "cartesian",   ""),
    ("2D_circular",       "2D", "circular",    ""),
    ("2D_rectangular",    "2D", "cartesian",   SYM_RECTANGULAR),
    ("3D_orthorhombic",   "3D", "cartesian",   SYM_ORTHORHOMBIC),
    ("3D_tetragonal",     "3D", "cartesian",   SYM_TETRAGONAL),
]

MATCHES = (MATCH_ABSOLUTE, MATCH_GAPS, MATCH_RATIOS)
PRIORITIES = (PRIORITY_UNIFORM, PRIORITY_GROUND, PRIORITY_LOW_QN)
LMAXES = (13.0, 18.0)


def make_params(ndim, coords, sym, match, priority, Lmax, targets, meff):
    """The parameter dict exactly as the tool builds it, defaults and all."""
    return {
        'Et': list(targets),
        'meff': meff,
        'ndim': ndim,
        'coords': coords,
        'sym': sym,
        'fixed': {'d1': None, 'd2': None, 'd3': None},
        'Lmin': 1.0,
        'Lmax': Lmax,
        'tol': 5.0,
        'maxsol': 6,
        'match': match,
        'priority': priority,
        'carrier': 'e',
    }


def record_solution(sol):
    """One candidate, in a form that compares byte-for-byte.

    Floats go in as their full ``repr`` rather than as JSON numbers: a JSON
    round-trip through a double is lossless in CPython, but the repr is what
    a diff of the fixture shows a human, and it removes any question of the
    encoder's formatting mattering.
    """
    return {
        'dims': [repr(float(d)) for d in sol['dims']],
        'RRMSE': repr(float(sol['RRMSE'])),
        'RRMSE_abs': repr(float(sol['RRMSE_abs'])),
        'RRMSE_dE': repr(float(sol['RRMSE_dE'])),
        'offset': repr(float(sol['offset'])),
        'meff': repr(float(sol['meff'])),
        'matches': [
            {'target_E': repr(float(m['target_E'])),
             'computed_E': repr(float(m['computed_E'])),
             'qn': list(m['qn']),
             'idx': int(m['idx'])}
            for m in sol['matches']
        ],
    }


def configurations():
    """Every (label, params) the fixture covers."""
    for name, ndim, coords, sym in GEOMETRIES:
        for match in MATCHES:
            for priority in PRIORITIES:
                for Lmax in LMAXES:
                    label = f"{name}|{match}|{priority}|Lmax={Lmax:g}"
                    yield label, make_params(ndim, coords, sym, match,
                                             priority, Lmax,
                                             TARGETS_MEASURED, 0.322)
    # The synthetic ladder, on the geometry that generated it.
    for match in MATCHES:
        for priority in PRIORITIES:
            for Lmax in LMAXES:
                label = f"1D_synthetic|{match}|{priority}|Lmax={Lmax:g}"
                yield label, make_params("1D", "cartesian", "", match,
                                         priority, Lmax,
                                         TARGETS_SYNTHETIC_1D, 0.067)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "fixtures", "designer_golden.json"))
    ap.add_argument("--only", default=None,
                    help="substring filter on the config label (for a probe)")
    args = ap.parse_args()

    configs = [(lab, p) for lab, p in configurations()
               if args.only is None or args.only in lab]
    out = {'seed': SEED,
           'targets_measured': [repr(float(t)) for t in TARGETS_MEASURED],
           'targets_synthetic_1d': [repr(float(t))
                                    for t in TARGETS_SYNTHETIC_1D],
           'configs': {}}

    t0 = time.perf_counter()
    for i, (label, p) in enumerate(configs, 1):
        # A FRESH Designer per config: the RNG is drawn from in sequence, so
        # sharing one instance would make every entry depend on the order the
        # configs happen to run in, and on which ones are filtered out.
        started = time.perf_counter()
        sols = Designer(SEED).find_solutions(p)
        out['configs'][label] = [record_solution(s) for s in sols]
        print(f"[{i}/{len(configs)}] {label}: {len(sols)} candidate(s) "
              f"in {time.perf_counter() - started:.1f}s", flush=True)

    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(f"wrote {args.out} ({len(out['configs'])} configs, "
          f"{time.perf_counter() - t0:.0f}s total)")


if __name__ == "__main__":
    main()
