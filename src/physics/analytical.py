"""Analytical energy levels for infinite quantum wells (1D, 2D, 3D)."""

import numpy as np
from scipy.constants import hbar, m_e, e, pi
from scipy.special import jn_zeros


# ─── 1D ──────────────────────────────────────────────────────────────────────

def box_energies_1d(L_nm, meff, n_levels):
    """
    Analytical energies for 1D infinite well.
    E(n) = (hbar^2 pi^2 n^2) / (2 m L^2),  n = 1, 2, ...

    Returns list of (energy_J, (n,)) sorted ascending.
    """
    L = L_nm * 1e-9
    m = meff * m_e
    prefactor = (hbar ** 2 * pi ** 2) / (2.0 * m * L ** 2)
    return [(prefactor * n ** 2, (n,)) for n in range(1, n_levels + 1)]


def box_energies_1d_eV(L_nm, meff, n_levels):
    """Same as box_energies_1d but returns energies in eV."""
    return [(E / e, qn) for E, qn in box_energies_1d(L_nm, meff, n_levels)]


# ─── 2D ──────────────────────────────────────────────────────────────────────

def disk_energies(R_nm, meff, n_levels):
    """
    Analytical energies for 2D infinite circular well (disk).
    E(m, n) = (hbar^2 / 2m) * (x_mn / R)^2
    where x_mn is the n-th zero of Bessel function J_m.

    Returns list of (energy_eV, (m, n)) sorted ascending.
    """
    R = R_nm * 1e-9
    mass = meff * m_e
    prefactor = hbar ** 2 / (2.0 * mass * R ** 2)

    max_m, max_n = 8, 8
    bessel_zeros = {m_ang: jn_zeros(m_ang, max_n) for m_ang in range(max_m)}

    energies = []
    for m_ang in range(max_m):
        for n_rad in range(1, max_n + 1):
            x_mn = bessel_zeros[m_ang][n_rad - 1]
            E = prefactor * x_mn ** 2
            energies.append((E / e, (m_ang, n_rad)))

    energies.sort(key=lambda x: x[0])
    return energies[:n_levels]


def box_energies_2d_eV(Lx_nm, Ly_nm, meff, n_levels):
    """
    Analytical 2D rectangular well energies in (energy_eV, (nx, ny)) format
    (flat list, not grouped by degeneracy).
    """
    Lx, Ly = Lx_nm * 1e-9, Ly_nm * 1e-9
    m = meff * m_e
    prefactor = (hbar ** 2 * pi ** 2) / (2.0 * m)

    max_n = max(15, int(np.ceil(n_levels ** 0.5) + 8))
    energies = []
    for nx in range(1, max_n + 1):
        for ny in range(1, max_n + 1):
            E = prefactor * ((nx / Lx) ** 2 + (ny / Ly) ** 2) / e
            energies.append((E, (nx, ny)))
    energies.sort(key=lambda x: x[0])
    return energies[:n_levels]


# ─── 3D ──────────────────────────────────────────────────────────────────────

def box_energies_3d(Lx_nm, Ly_nm, Lz_nm, meff, n_levels):
    """
    Analytical energies for 3D infinite rectangular well.
    E(nx,ny,nz) = (hbar^2 pi^2 / 2m) * [(nx/Lx)^2 + (ny/Ly)^2 + (nz/Lz)^2]

    Returns list of (energy_J, (nx, ny, nz)) sorted ascending.
    """
    Lx, Ly, Lz = Lx_nm * 1e-9, Ly_nm * 1e-9, Lz_nm * 1e-9
    m = meff * m_e
    prefactor = (hbar**2 * pi**2) / (2.0 * m)

    max_n = max(10, int(np.ceil(n_levels ** (1 / 3)) + 5))
    energies = []
    for nx in range(1, max_n + 1):
        for ny in range(1, max_n + 1):
            for nz in range(1, max_n + 1):
                E = prefactor * ((nx / Lx)**2 + (ny / Ly)**2 + (nz / Lz)**2)
                energies.append((E, (nx, ny, nz)))

    energies.sort(key=lambda x: x[0])
    return energies[:n_levels]


def box_energies_3d_eV(Lx_nm, Ly_nm, Lz_nm, meff, n_levels):
    """Same as box_energies_3d but returns energies in eV."""
    result = box_energies_3d(Lx_nm, Ly_nm, Lz_nm, meff, n_levels)
    return [(E / e, qn) for E, qn in result]


def box_energies_2d(Lx_nm, Ly_nm, meff, n_levels):
    """
    Analytical energies for 2D infinite rectangular well.
    Returns list of (energy_eV, [(nx, ny), ...]) grouped by degeneracy.
    """
    Lx, Ly = Lx_nm * 1e-9, Ly_nm * 1e-9
    m = meff * m_e
    prefactor = (hbar**2 * pi**2) / (2.0 * m)

    max_n = max(15, int(np.ceil(n_levels ** 0.5) + 8))
    all_states = []
    for nx in range(1, max_n + 1):
        for ny in range(1, max_n + 1):
            E_eV = prefactor * ((nx / Lx)**2 + (ny / Ly)**2) / e
            all_states.append((E_eV, (nx, ny)))

    all_states.sort(key=lambda x: x[0])

    # Group degenerate analytical states
    grouped = []
    tolerance = 1e-6
    used = set()

    for i, (E_i, qn_i) in enumerate(all_states):
        if i in used:
            continue
        group_qnums = [qn_i]
        used.add(i)
        for j in range(i + 1, len(all_states)):
            if j not in used and abs(all_states[j][0] - E_i) < tolerance:
                group_qnums.append(all_states[j][1])
                used.add(j)
        grouped.append((E_i, group_qnums))
        if len(grouped) >= n_levels * 2:
            break

    return grouped


def cylinder_energies(R_nm, H_nm, meff, n_levels):
    """
    Analytical energies for infinite cylindrical well.
    E(m,n,l) = (hbar^2/2m) * [(x_mn/R)^2 + (l*pi/H)^2]

    Returns list of (energy_eV, (m, n, l)) sorted ascending.
    """
    R, H = R_nm * 1e-9, H_nm * 1e-9
    mass = meff * m_e
    prefactor = (hbar**2) / (2.0 * mass)
    E_xy = lambda x: prefactor * (x / R) ** 2 / e          # noqa: E731
    E_ax = lambda l: prefactor * (l * pi / H) ** 2 / e      # noqa: E731

    # The basis grows until it provably holds the lowest n_levels. A fixed
    # 6 x 6 x 10 used to do: enough for anything squat, and short of the
    # axial ladder of a tall, thin cylinder, where the lowest levels ARE the
    # axial ones. Energy rises monotonically in each quantum number, so the
    # cheapest state just past each cap bounds everything beyond it — once
    # all three sit above the n_levels-th energy, nothing is missing.
    max_m, max_n, max_l = 6, 6, 10
    for _ in range(64):
        zeros = {m_ang: jn_zeros(m_ang, max_n) for m_ang in range(max_m)}
        energies = []
        for m_ang in range(max_m):
            for n_rad in range(1, max_n + 1):
                exy = E_xy(zeros[m_ang][n_rad - 1])
                for l_ax in range(1, max_l + 1):
                    energies.append((exy + E_ax(l_ax), (m_ang, n_rad, l_ax)))
        energies.sort(key=lambda x: x[0])
        if len(energies) < n_levels:
            max_m += 1; max_n += 1; max_l += 1
            continue
        cutoff = energies[n_levels - 1][0]
        grow = False
        if E_xy(zeros[0][0]) + E_ax(max_l + 1) <= cutoff and max_l < 96:
            max_l += 1; grow = True
        if E_xy(jn_zeros(0, max_n + 1)[-1]) + E_ax(1) <= cutoff and max_n < 24:
            max_n += 1; grow = True
        if E_xy(jn_zeros(max_m, 1)[0]) + E_ax(1) <= cutoff and max_m < 24:
            max_m += 1; grow = True
        if not grow:
            break
    return energies[:n_levels]


# ─── degeneracy ──────────────────────────────────────────────────────────────
#
# Everything above returns bare (energy, quantum numbers) pairs and always
# will: the inverse designer unpacks them as `for E, _ in …` in its hot loop,
# and those functions are frozen byte for byte against
# ``tests/fixtures/levels_golden.json``. What follows is purely additive — the
# same ladders, re-presented as `quantum_dot.Level` records that carry the one
# thing the pairs threw away, namely how many physical states each row stands
# for.
#
# TWO TOLERANCES, AND THEY MUST NEVER BE CONFLATED.
#
#   *Exact* degeneracy is a symmetry fact about the model. Partners here are
#   equal to machine precision because they are exact arithmetic on the same
#   integers or the same Bessel zeros — nx^2+ny^2+nz^2 = 27 is reached by
#   (1,1,5) and by (3,3,3) with no rounding in between. So the tolerance is
#   relative and extremely tight: GROUP_RTOL = 1e-9, borrowed from
#   `level_patterns` rather than redefined, so there is one number and not two.
#
#   *Resolvable* degeneracy is a measurement fact about a spectrum: 3.5 k_B T
#   (27 meV at 90 K, 91 meV at 300 K), or half the smallest gap the data
#   actually shows. It is four hundred times wider, it belongs to the
#   spectrum rather than to the model, and it is reported in its own column by
#   the designer — never here. A model that claimed a degeneracy the data
#   cannot see would be read as a measurement, which is worse than reporting
#   none.
#
# The old `calculadora_autoestados` package grouped with ABSOLUTE tolerances —
# `core/eigensolver.py:30` at 1e-4 eV and `core/analytical.py:106` at 1e-6 eV.
# Both are rejected here. 1e-4 eV (0.10 meV) is an `eigsh` convergence
# threshold wearing a physics costume: 270x below this sample's 90 K linewidth
# and 910x below its 300 K one, so it answers neither question. And being
# absolute it behaves differently at the two ends of a ladder that spans
# 0.03 to 2 eV — separating true partners at the bottom while merging
# unrelated levels at the top. `box_energies_2d` above still carries the old
# 1e-6 eV grouping; it is left exactly as it is because its output is frozen,
# and nothing new is built on it.


def group_degeneracy(entries, rtol=None, with_representative=False):
    """Collapse an ASCENDING state list onto distinct energies.

    ``entries`` are ``(E_eV, quantum_numbers)`` pairs, or
    ``(E_eV, quantum_numbers, weight)`` triples when one entry already stands
    for several states — the ``+/-m`` fold of a disc or cylinder, the ``2l+1``
    fold of a sphere. A pair weighs 1, which is right for the Cartesian boxes
    here: they enumerate every permutation of the quantum numbers as its own
    entry, so the multiplicity is in the list rather than in a formula.

    Returns the degeneracy of each distinct energy, in order — or, with
    ``with_representative``, ``(E_eV, degeneracy, quantum_numbers)`` triples
    naming the lowest member of each group.

    DEGENERACY IS COUNTED, NEVER COMPUTED FROM A FORMULA, and the reason is
    that a formula can only see one entry at a time while degeneracy is a
    property of a set. Two distinct kinds of coincidence live here:

    *Permutation* degeneracy, which a symmetric box has by construction — the
    5 nm cube's first ten levels run 1, 3, 3, 3, 1, 6, 3, 3, 3, 6.

    *Accidental* degeneracy, which is not a permutation of anything and which
    no per-entry rule can predict. The first one in that same cube is
    E = 1.2612192 eV with g = 4, where the distinct multisets (1,1,5) and
    (3,3,3) meet because 1+1+25 = 9+9+9 = 27; in the 5 nm square the
    ``n^2``-sum 65 gathers (1,8), (4,7), (7,4) and (8,1) into one level of
    g = 4. A parabolic dot at a commensurate ``hw_xy:hw_z`` does the same
    thing. Counting catches all of them; ``2l+1`` and friends catch none.

    ``rtol`` defaults to :data:`src.physics.level_patterns.GROUP_RTOL`. It is
    resolved at call time, not in the signature, only because
    ``level_patterns`` imports THIS module at module scope — naming it as a
    default would close an import cycle. The grouping itself delegates to
    ``level_patterns._group_levels`` rather than repeating it: that function
    is already relative-tolerance, already weight-carrying, and already the
    one the level-ratio fingerprints are built on, so a disc grouped for a
    fingerprint and the same disc grouped for a candidate table can never
    drift apart.
    """
    # Local import: `level_patterns` imports `analytical` at module scope, so
    # this direction has to stay lazy. One sys.modules lookup per call, against
    # at most a dozen calls per spectrum.
    from src.physics.level_patterns import GROUP_RTOL, _group_levels

    states = [(float(row[0]), tuple(int(q) for q in row[1]),
               int(row[2]) if len(row) > 2 else 1)
              for row in entries]
    groups = _group_levels(states, GROUP_RTOL if rtol is None else rtol)
    if with_representative:
        return groups
    return [degeneracy for _E, degeneracy, _qn in groups]


#: How many raw entries to enumerate per distinct level asked for, per model.
#: Only used when ``distinct=True``; it sizes the over-enumeration so that
#: groups are complete BEFORE the truncation. Degeneracy is what drives the
#: numbers: a 3D cube spends 20 entries on 7 distinct energies, a 2D square 20
#: on 12, a 1D line 20 on 20. They are start values — the builders below grow
#: the factor when a geometry turns out to be more degenerate than the guess,
#: so no caller has to know the ratio for its own aspect ratio.
_DISTINCT_FACTOR = {"box_1d": 1, "box_2d": 3, "box_3d": 5,
                    "disk": 2, "cylinder": 2}


def _levels_from(produce, weight_of, label_of, n_levels, distinct,
                 channel_of=None, factor=1):
    """Turn a row producer's ``(E_eV, qn)`` entries into ``Level`` records.

    ``produce(count)`` returns the ``count`` lowest entries, ascending — one
    of the ``*_energies_*`` functions above, bound to its dimensions.

    With ``distinct`` unset this is a relabelling and nothing more: the first
    ``n_levels`` entries, in the order and with the energies the designer
    fits against, each carrying its own symmetry weight.

    With ``distinct`` set the entries are over-enumerated by ``factor``,
    grouped, and only THEN truncated. That order is the whole point. Grouping
    after a cut would report half of a degenerate group as its full
    multiplicity, and a halved degeneracy is exactly the sort of wrong number
    a reader takes for a measurement. The last group is dropped whenever
    there is a spare level to drop it in favour of, since it is the only one
    the cut can have split; and ``factor`` doubles until enough complete
    groups exist or the producer runs out of basis, so a caller never has to
    know how degenerate its own aspect ratio happens to be.
    """
    # Imported here, not at module scope: `level_patterns` already imports
    # this module, so keeping every physics->physics edge lazy in this
    # direction means no future module-level import can close a cycle
    # through it.
    from src.physics.quantum_dot import Level

    def make(E, qn, degeneracy):
        return Level(E_eV=float(E), quantum_numbers=tuple(int(q) for q in qn),
                     label=label_of(qn), degeneracy=int(degeneracy),
                     channel=0 if channel_of is None else channel_of(qn),
                     bound=True)

    n_levels = max(1, int(n_levels))
    if not distinct:
        return [make(E, qn, weight_of(qn))
                for E, qn in produce(n_levels)[:n_levels]]

    for _ in range(6):
        want = n_levels * factor
        rows = produce(want)
        groups = group_degeneracy([(E, qn, weight_of(qn)) for E, qn in rows],
                                  with_representative=True)
        exhausted = len(rows) < want      # the producer's basis ran out
        if len(groups) > n_levels:
            return [make(E, qn, g) for E, g, qn in groups[:-1][:n_levels]]
        if exhausted:
            # Nothing more to be had: every group present is complete, since
            # the producer had no further state to add to any of them.
            return [make(E, qn, g) for E, g, qn in groups[:n_levels]]
        factor *= 2
    raise RuntimeError(  # pragma: no cover - 64x the basis is far past any use
        f"could not assemble {n_levels} complete distinct levels")


def box_levels_1d(L_nm, meff=0.067, n_levels=20, distinct=False):
    """The 1D box ladder of :func:`box_energies_1d_eV`, carrying degeneracy.

    A line has none: E ~ n^2 is strictly increasing, so every level is simple
    and ``distinct`` changes nothing. The function exists anyway, so that
    :func:`src.physics.quantum_dot.levels_for` has one branch per geometry and
    a caller never has to special-case the one model that happens to be
    non-degenerate today.
    """
    return _levels_from(lambda k: box_energies_1d_eV(L_nm, meff, k),
                        lambda qn: 1, lambda qn: f"n={int(qn[0])}",
                        n_levels, distinct,
                        factor=_DISTINCT_FACTOR["box_1d"])


def box_levels_2d(Lx_nm, Ly_nm, meff=0.067, n_levels=20, distinct=False):
    """The 2D rectangular ladder of :func:`box_energies_2d_eV`, with degeneracy.

    Every (nx, ny) permutation is its own entry upstream, so each weighs one
    and the multiplicity is obtained by counting. At Lx = Ly that recovers the
    familiar 1, 2, 1, 2, 2, 2, 1, … of a square, and it also catches the
    accidental levels a permutation count would miss — see
    :func:`group_degeneracy`.
    """
    return _levels_from(lambda k: box_energies_2d_eV(Lx_nm, Ly_nm, meff, k),
                        lambda qn: 1,
                        lambda qn: f"({int(qn[0])},{int(qn[1])})",
                        n_levels, distinct,
                        factor=_DISTINCT_FACTOR["box_2d"])


def box_levels_3d(Lx_nm, Ly_nm, Lz_nm, meff=0.067, n_levels=20, distinct=False):
    """The 3D rectangular ladder of :func:`box_energies_3d_eV`, with degeneracy.

    Same counting argument as :func:`box_levels_2d`, one dimension up, where
    it matters much more: a cube spends 20 enumerated entries on only 7
    distinct energies, so a search that asks for "twenty levels" and gets a
    flat list is really fitting against seven — which is precisely why
    ``distinct`` is offered.
    """
    return _levels_from(
        lambda k: box_energies_3d_eV(Lx_nm, Ly_nm, Lz_nm, meff, k),
        lambda qn: 1,
        lambda qn: f"({int(qn[0])},{int(qn[1])},{int(qn[2])})",
        n_levels, distinct, factor=_DISTINCT_FACTOR["box_3d"])


def disk_levels(R_nm, meff=0.067, n_levels=20, distinct=False):
    """The 2D disk ladder of :func:`disk_energies`, carrying degeneracy.

    ``disk_energies`` iterates ``m >= 0`` only, so every ``m != 0`` entry
    stands for the ``+m``/``-m`` pair and weighs 2 while ``m = 0`` weighs 1.
    Weighting by entry count instead would halve the multiplicity of every
    angular level.

    A LIMIT OF THE UNDERLYING ENUMERATION, RECORDED RATHER THAN PAPERED OVER:
    ``disk_energies`` opens a fixed 8 x 8 basis (``m = 0..7``, ``n = 1..8``),
    so it can return at most 64 entries and — more importantly — its sorted
    list first goes wrong at rank 18, where the true ladder's ``j_{8,1}``
    falls outside the basis. This function inherits that exactly, on purpose:
    :meth:`src.physics.designer.Designer.compute_energies` fits against
    ``disk_energies``, and a labelled ladder that disagreed with the fitted
    one would mislabel candidates. ``test_disk_energies_basis_is_capped`` pins
    the rank so the gap is visible to whoever widens that basis, at which
    point this docstring and that test both change together.
    """
    return _levels_from(lambda k: disk_energies(R_nm, meff, k),
                        lambda qn: 1 if int(qn[0]) == 0 else 2,
                        lambda qn: f"(m={int(qn[0])},n={int(qn[1])})",
                        n_levels, distinct,
                        channel_of=lambda qn: abs(int(qn[0])),
                        factor=_DISTINCT_FACTOR["disk"])


def cylinder_levels(R_nm, H_nm, meff=0.067, n_levels=20, distinct=False):
    """The cylinder ladder of :func:`cylinder_energies`, carrying degeneracy.

    ``(m, n, l)``: the same ``+/-m`` fold as the disk, times an axial ladder
    that is simple. Unlike :func:`disk_levels` there is no basis cap to
    inherit — ``cylinder_energies`` grows ``max_m``, ``max_n`` and ``max_l``
    until the cheapest state past each cap provably sits above the
    ``n_levels``-th energy.
    """
    return _levels_from(
        lambda k: cylinder_energies(R_nm, H_nm, meff, k),
        lambda qn: 1 if int(qn[0]) == 0 else 2,
        lambda qn: f"({int(qn[0])},{int(qn[1])},{int(qn[2])})",
        n_levels, distinct, channel_of=lambda qn: abs(int(qn[0])),
        factor=_DISTINCT_FACTOR["cylinder"])
