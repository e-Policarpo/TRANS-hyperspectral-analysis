"""Fixed-seed candidate lists from ``Designer.find_solutions``.

The degeneracy work touches the level generators the designer calls thousands
of times per search. That is the riskiest kind of edit there is: a reordering
or a one-ulp change anywhere in ``dot_energies`` moves every RRMSE and so the
whole candidate list, silently. This records the list for a spread of
geometries with the RNG pinned, so "the default search is unchanged" is a
claim that can be checked rather than asserted.

Usage::

    QT_QPA_PLATFORM=offscreen ~/.virtualenvs/trans-arm64/bin/python \
        scripts/record_designer_proof.py <output.json>
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                            # noqa: E402

from src.physics.designer import Designer                     # noqa: E402
from src.physics.analytical import (box_energies_1d_eV,       # noqa: E402
                                    box_energies_2d_eV,
                                    cylinder_energies)
from src.physics.quantum_dot import dot_energies              # noqa: E402

SEED = 12345

#: Her case first: a 0D lens matched on level SPACINGS, which is the only
#: mode an unknown doping offset leaves usable. The rest cover every branch
#: of ``compute_energies`` so no model can drift unnoticed.
CASES = [
    dict(name="0D disc delta_e Lmax13", ndim="0D", coords="disc", meff=0.322,
         Lmax=13.0, match="delta_e",
         Et=[E for E, _ in dot_energies("disc", (4.0, 5.0), 0.322, 6)]),
    dict(name="0D disc delta_e Lmax18", ndim="0D", coords="disc", meff=0.322,
         Lmax=18.0, match="delta_e",
         Et=[E for E, _ in dot_energies("disc", (4.0, 5.0), 0.322, 6)]),
    dict(name="0D spherical absolute", ndim="0D", coords="spherical",
         meff=0.067, Lmax=20.0, match="absolute",
         Et=[E for E, _ in dot_energies("spherical", (6.0,), 0.067, 4)]),
    dict(name="0D parabolic absolute", ndim="0D", coords="parabolic",
         meff=0.067, Lmax=20.0, match="absolute",
         Et=[E for E, _ in dot_energies("parabolic", (30.0, 100.0), 0.067, 4)]),
    dict(name="1D box absolute", ndim="1D", coords="cartesian", meff=0.067,
         Lmax=20.0, match="absolute",
         Et=[E for E, _ in box_energies_1d_eV(8.0, 0.067, 3)]),
    dict(name="2D cartesian absolute", ndim="2D", coords="cartesian",
         sym="orthorhombic", meff=0.067, Lmax=20.0, match="absolute",
         Et=[E for E, _ in box_energies_2d_eV(10.0, 6.0, 0.067, 4)]),
    dict(name="3D cylindrical absolute", ndim="3D", coords="cylindrical",
         meff=0.067, Lmax=20.0, match="absolute",
         Et=[E for E, _ in cylinder_energies(5.0, 10.0, 0.067, 4)]),
]


def run(case):
    p = {
        'Et': np.array(case['Et'], dtype=float),
        'meff': case['meff'],
        'ndim': case['ndim'],
        'coords': case['coords'],
        'sym': case.get('sym', ''),
        'fixed': {'d1': None, 'd2': None, 'd3': None},
        'Lmin': 1.0,
        'Lmax': case['Lmax'],
        'tol': 5.0,
        'maxsol': 6,
        'priority': 'uniform',
        'match': case['match'],
        'carrier': 'e',
    }
    # One Designer per case, seeded identically: `find_solutions` draws its
    # differential_evolution seeds from this RNG, so a shared instance would
    # make every case depend on the order the cases run in.
    sols = Designer(seed=SEED).find_solutions(p)
    return [{
        'dims': [repr(float(d)) for d in s['dims']],
        'RRMSE': repr(float(s['RRMSE'])),
        'RRMSE_abs': repr(float(s['RRMSE_abs'])),
        'RRMSE_dE': repr(float(s['RRMSE_dE'])),
        'offset': repr(float(s['offset'])),
        'matches': [[repr(float(m['target_E'])), repr(float(m['computed_E'])),
                     [int(q) for q in m['qn']], int(m['idx'])]
                    for m in s['matches']],
    } for s in sols]


def main():
    out = {case['name']: run(case) for case in CASES}
    path = sys.argv[1] if len(sys.argv) > 1 else "designer_proof.json"
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(f"wrote {path}")
    for name, sols in out.items():
        print(f"  {name}: {len(sols)} candidates, "
              f"best {sols[0]['RRMSE'] if sols else '-'}")


if __name__ == "__main__":
    main()
