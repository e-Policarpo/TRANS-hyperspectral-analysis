"""Record the byte-exact output of every analytic level generator.

STEP 0 of the Confinement Designer work: this runs against the CURRENT tree
and freezes what ``quantum_dot.dot_energies`` and every
``analytical.*_energies_*`` return, as the full ``repr`` of each float. The
degeneracy work that follows restructures those functions internally, and the
only acceptable proof that it changed nothing is exact equality against this
file -- not ``pytest.approx``, which would let a real change through.

Re-record with::

    QT_QPA_PLATFORM=offscreen ~/.virtualenvs/trans-arm64/bin/python \
        scripts/record_levels_golden.py

and note that RE-RECORDING AFTER A CHANGE DEFEATS THE PURPOSE: the fixture is
committed alongside this script so the recording can be audited, not so it can
be refreshed when a test goes red.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.physics import analytical as A                      # noqa: E402
from src.physics import quantum_dot as Q                      # noqa: E402

N_LEVELS = (1, 4, 20, 60)
MEFFS = (0.067, 0.322, 0.39)

#: (R,) spherical, (R, Lz) disc, (hw_xy_meV, hw_z_meV) parabolic. The disc
#: entries deliberately straddle the flat-lens and tall-pillar regimes, since
#: `_disc_levels` grows its axial basis differently in each; the parabolic
#: pair 20/30 is commensurate (2:3) and 20/31.7 is not, which is where
#: accidental degeneracy appears and disappears.
DIMS = {
    Q.DOT_SPHERICAL: [(5.0,), (2.0,), (12.5,)],
    Q.DOT_DISC: [(5.0, 3.0), (3.0, 20.0), (10.0, 1.5), (4.0, 5.0), (3.5, 11.0)],
    Q.DOT_PARABOLIC: [(20.0, 30.0), (20.0, 31.7), (30.0, 100.0)],
}


def _pairs(rows):
    """``[(E, qn), ...]`` -> JSON with the float written out in full."""
    return [[repr(float(E)), [int(q) for q in qn]] for E, qn in rows]


def main():
    out = {"dot_energies": {}, "analytical": {}}

    for model, dims_list in DIMS.items():
        for dims in dims_list:
            for meff in MEFFS:
                for n in N_LEVELS:
                    key = f"{model}|{dims}|{meff}|{n}"
                    out["dot_energies"][key] = _pairs(
                        Q.dot_energies(model, dims, meff, n))

    a = out["analytical"]
    for meff in MEFFS:
        for n in N_LEVELS:
            for L in (1.0, 5.0, 8.0, 20.0):
                a[f"box_energies_1d|{L}|{meff}|{n}"] = _pairs(
                    A.box_energies_1d(L, meff, n))
                a[f"box_energies_1d_eV|{L}|{meff}|{n}"] = _pairs(
                    A.box_energies_1d_eV(L, meff, n))
            for (Lx, Ly) in ((5.0, 5.0), (10.0, 6.0), (1.0, 1.0)):
                a[f"box_energies_2d_eV|{Lx},{Ly}|{meff}|{n}"] = _pairs(
                    A.box_energies_2d_eV(Lx, Ly, meff, n))
                # box_energies_2d groups: (E, [qn, qn, ...]).
                a[f"box_energies_2d|{Lx},{Ly}|{meff}|{n}"] = [
                    [repr(float(E)), [[int(q) for q in qn] for qn in group]]
                    for E, group in A.box_energies_2d(Lx, Ly, meff, n)]
            for (Lx, Ly, Lz) in ((5.0, 5.0, 5.0), (8.0, 6.0, 5.0), (5.0, 5.0, 12.0)):
                a[f"box_energies_3d|{Lx},{Ly},{Lz}|{meff}|{n}"] = _pairs(
                    A.box_energies_3d(Lx, Ly, Lz, meff, n))
                a[f"box_energies_3d_eV|{Lx},{Ly},{Lz}|{meff}|{n}"] = _pairs(
                    A.box_energies_3d_eV(Lx, Ly, Lz, meff, n))
            for R in (1.0, 5.0, 10.0):
                a[f"disk_energies|{R}|{meff}|{n}"] = _pairs(
                    A.disk_energies(R, meff, n))
            for (R, H) in ((5.0, 10.0), (1.0, 3.0), (10.0, 2.0)):
                a[f"cylinder_energies|{R},{H}|{meff}|{n}"] = _pairs(
                    A.cylinder_energies(R, H, meff, n))

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "tests", "fixtures", "levels_golden.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(f"wrote {path}: {len(out['dot_energies'])} dot rows, "
          f"{len(out['analytical'])} analytical rows")


if __name__ == "__main__":
    main()
