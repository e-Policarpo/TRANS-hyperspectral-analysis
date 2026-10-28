"""
0D confinement — quantum dots.

A 1D/2D well confines in one or two directions and leaves continuous
sub-bands in the rest; a quantum dot confines in ALL of them, and the
spectrum becomes discrete, with shells and degeneracies like an atom's
(1s, 1p, 1d, …).

Three models, all solved in the radial coordinate — the symmetry reduces the
3D problem to one ODE per angular-momentum channel, which is exact for the
geometries below and thousands of times cheaper than a 3D mesh:

``spherical``
    Spherical dot of radius R, finite or infinite barrier. Channel l: each
    level has degeneracy 2l+1 (orbital) — the colloidal-nanocrystal case.

``disc``
    Lens/disc: confinement in the plane (radius R) and in z (height Lz),
    separable, E = E_plane(n,m) + E_z(nz). The geometry of flattened
    self-assembled dots, where the z separation is the largest scale.

``parabolic``
    Harmonic confinement (Fock-Darwin with no field): E = hw_xy(n_xy+1) +
    hw_z(n_z+1/2). Analytical, useful as a reference and for
    electrostatically defined dots, whose potential is smooth.

Energies in eV, lengths in nm — the units the rest of the program uses.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional, Tuple

import numpy as np
from scipy.constants import hbar, m_e, e
from scipy.sparse import diags
from scipy.sparse.linalg import eigsh
from scipy.special import spherical_jn, jn_zeros

# np.trapezoid is the NumPy 2 name; this project still runs on 1.26, where
# only np.trapz exists.
_trapz = getattr(np, "trapezoid", None) or np.trapz

#: Dot models. These keys are deliberately the same strings as the 0D
#: entries of :data:`src.physics.solution_spec.COORDS`, so a candidate's
#: ``coords`` names its model directly and no lookup table sits between them.
DOT_SPHERICAL = "spherical"
DOT_DISC = "disc"
DOT_PARABOLIC = "parabolic"

MODELS = (DOT_SPHERICAL, DOT_DISC, DOT_PARABOLIC)

MODEL_LABELS = {
    DOT_SPHERICAL: "Spherical",
    DOT_DISC: "Disc / lens",
    DOT_PARABOLIC: "Parabolic",
}

#: Spectroscopic label of the angular-momentum channel.
ORBITALS = "spdfghiklmno"


def orbital_label(n: int, l: int) -> str:
    """``1s``, ``1p``, ``2s``, … — n counts the levels WITHIN channel l."""
    letter = ORBITALS[l] if l < len(ORBITALS) else f"[l={l}]"
    return f"{n}{letter}"


@dataclass
class Level:
    """One confined level.

    ``degeneracy`` is the orbital one (2l+1 for the sphere, 2 for m != 0 on
    the disc); spin is NOT included — ``occupancy`` does include it, because
    the occupancy is what a charge measurement is compared against.
    """

    E_eV: float
    quantum_numbers: Tuple[int, ...]
    label: str
    degeneracy: int = 1
    channel: int = 0                 # l (spherical) or |m| (disc)
    radial: Optional[np.ndarray] = field(default=None, repr=False)
    r_nm: Optional[np.ndarray] = field(default=None, repr=False)
    bound: bool = True

    @property
    def occupancy(self) -> int:
        """Electrons the level holds, counting spin."""
        return 2 * self.degeneracy


def _radial_hamiltonian(r, V_J, meff, centrifugal):
    """H for an already-reduced 1D radial ODE, on a uniform grid."""
    dr = r[1] - r[0]
    m = meff * m_e
    kinetic = -(hbar ** 2) / (2.0 * m * dr ** 2)
    n = r.size
    main = np.full(n, -2.0 * kinetic) + V_J + centrifugal
    off = np.full(n - 1, kinetic)
    return diags([off, main, off], [-1, 0, 1], format="csr")


def _solve_channel(r, V_J, meff, centrifugal, k):
    """Smallest k eigenvalues of a radial channel. Returns (E_J, vectors)."""
    H = _radial_hamiltonian(r, V_J, meff, centrifugal)
    k = max(1, min(k, H.shape[0] - 2))
    E, vec = eigsh(H, k=k, sigma=float(np.min(V_J + centrifugal)) - 0.05 * e,
                   which="LM")
    order = np.argsort(E)
    return E[order], vec[:, order]


def spherical_dot(R_nm, V0_eV=None, meff=0.067, l_max=3, n_per_channel=4,
                  N=800, box_factor=2.5, meff_barrier=None) -> List[Level]:
    """Levels of a spherical dot of radius ``R_nm``.

    ``V0_eV=None`` (or <= 0) treats the barrier as infinite and uses the
    zeros of j_l, which are exact; with a finite barrier the radial ODE is
    solved in a box of ``box_factor * R``, large enough for the evanescent
    tail. The substitution u = r*R(r) turns the radial operator into -u''/2m
    plus the centrifugal term, with u(0)=0 — no singularity at r=0.
    """
    if R_nm <= 0:
        raise ValueError("R must be positive")

    if V0_eV is None or V0_eV <= 0:
        return _spherical_infinite(R_nm, meff, l_max, n_per_channel)

    m_out = meff if meff_barrier is None else meff_barrier
    r_max = box_factor * R_nm
    r = np.linspace(r_max / N, r_max, N) * 1e-9
    R = R_nm * 1e-9

    inside = r <= R
    V_J = np.where(inside, 0.0, V0_eV * e)
    # Effective mass per region: the difference shifts the shallow levels,
    # which are the ones that leak furthest into the barrier.
    m_r = np.where(inside, meff, m_out)

    levels: List[Level] = []
    for l in range(l_max + 1):
        centrifugal = (hbar ** 2) * l * (l + 1) / (2.0 * m_r * m_e * r ** 2)
        E_J, vec = _solve_channel(r, V_J, meff, centrifugal, n_per_channel)
        for i, (E, u) in enumerate(zip(E_J, vec.T), start=1):
            E_eV = E / e
            if E_eV >= V0_eV:          # above the barrier: not bound
                continue
            levels.append(Level(
                E_eV=E_eV, quantum_numbers=(i, l), label=orbital_label(i, l),
                degeneracy=2 * l + 1, channel=l,
                radial=u / np.sqrt(_trapz(u ** 2, r)), r_nm=r * 1e9,
                bound=True,
            ))

    levels.sort(key=lambda lv: lv.E_eV)
    return levels


def _spherical_infinite(R_nm, meff, l_max, n_per_channel) -> List[Level]:
    """Infinite barrier: E = hbar^2 a_{nl}^2 / (2 m R^2), a = zeros of j_l."""
    R = R_nm * 1e-9
    m = meff * m_e
    r_nm = np.linspace(0.0, R_nm, 400)

    levels: List[Level] = []
    for l in range(l_max + 1):
        zeros = _spherical_jn_zeros(l, n_per_channel)
        for i, a in enumerate(zeros, start=1):
            E_J = (hbar ** 2) * a ** 2 / (2.0 * m * R ** 2)
            u = r_nm * spherical_jn(l, a * r_nm / R_nm)
            norm = np.sqrt(_trapz(u ** 2, r_nm * 1e-9)) or 1.0
            levels.append(Level(
                E_eV=E_J / e, quantum_numbers=(i, l), label=orbital_label(i, l),
                degeneracy=2 * l + 1, channel=l,
                radial=u / norm, r_nm=r_nm, bound=True,
            ))

    levels.sort(key=lambda lv: lv.E_eV)
    return levels


@lru_cache(maxsize=64)
def _jn_zeros_cached(m: int, count: int) -> tuple:
    """Zeros of J_m, memoised — they depend on neither R nor m*."""
    return tuple(jn_zeros(m, count))


@lru_cache(maxsize=64)
def _spherical_jn_zeros_cached(l: int, count: int) -> tuple:
    return tuple(_spherical_jn_zeros(l, count))


def _spherical_jn_zeros(l: int, count: int) -> np.ndarray:
    """The first ``count`` zeros of j_l.

    For l=0 they are n*pi; above that the zeros of j_l lie between those of
    J_{l+1/2}, so a sign search on a fine grid isolates them and bisection
    refines them — with no table to depend on.
    """
    if l == 0:
        return np.pi * np.arange(1, count + 1)

    # The zeros of j_l always sit above l and below those of j_{l+1}; a grid
    # up to a generous upper bound covers the first `count`.
    upper = np.pi * (count + l + 2)
    x = np.linspace(1e-6, upper, 20000)
    f = spherical_jn(l, x)
    sign_change = np.where(np.sign(f[:-1]) * np.sign(f[1:]) < 0)[0]

    roots = []
    for idx in sign_change[:count]:
        lo, hi = x[idx], x[idx + 1]
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if spherical_jn(l, lo) * spherical_jn(l, mid) <= 0:
                hi = mid
            else:
                lo = mid
        roots.append(0.5 * (lo + hi))
    return np.array(roots)


def disc_dot(R_nm, Lz_nm, V0_eV=None, meff=0.067, m_max=3, n_per_channel=3,
             nz_max=2, N=600, box_factor=2.5) -> List[Level]:
    """Levels of a disc/lens-shaped dot.

    The potential is separable, V(r) + V(z), so the in-plane problem (radius
    R, azimuthal quantum number m) and the z problem (a well of width Lz) are
    solved separately and the energies added. States with m != 0 are doubly
    degenerate (+|m| and -|m|).
    """
    if R_nm <= 0 or Lz_nm <= 0:
        raise ValueError("R and Lz must be positive")

    plane = _disc_plane_levels(R_nm, V0_eV, meff, m_max, n_per_channel,
                               N, box_factor)
    z_levels = _z_levels(Lz_nm, V0_eV, meff, nz_max, N, box_factor)

    levels: List[Level] = []
    for (E_xy, n, m_q, radial, r_nm) in plane:
        for (E_z, nz) in z_levels:
            if V0_eV and (E_xy + E_z) >= V0_eV:
                continue
            levels.append(Level(
                E_eV=E_xy + E_z, quantum_numbers=(n, m_q, nz),
                label=f"({n},{m_q:+d},{nz})" if m_q else f"({n},0,{nz})",
                degeneracy=2 if m_q != 0 else 1, channel=abs(m_q),
                radial=radial, r_nm=r_nm, bound=True,
            ))

    levels.sort(key=lambda lv: lv.E_eV)
    return levels


def _disc_plane_levels(R_nm, V0_eV, meff, m_max, n_per_channel, N, box_factor):
    """In-plane states of a disc. Returns (E_eV, n, m, radial, r_nm)."""
    out = []
    if V0_eV is None or V0_eV <= 0:
        # Hard wall: zeros of J_m.
        R = R_nm * 1e-9
        m = meff * m_e
        r_nm = np.linspace(1e-3, R_nm, 400)
        from scipy.special import jv
        for m_q in range(0, m_max + 1):
            for i, a in enumerate(jn_zeros(m_q, n_per_channel), start=1):
                E_J = (hbar ** 2) * a ** 2 / (2.0 * m * R ** 2)
                radial = jv(m_q, a * r_nm / R_nm)
                # One record per |m|; the two signs of m enter as the level's
                # degeneracy, not as repeated states.
                out.append((E_J / e, i, m_q, radial, r_nm))
        return out

    # Finite barrier: 2D radial ODE with u = sqrt(r) * R(r), whose
    # centrifugal term becomes (m^2 - 1/4)/r^2 — the standard 2D form.
    r_max = box_factor * R_nm
    r = np.linspace(r_max / N, r_max, N) * 1e-9
    V_J = np.where(r <= R_nm * 1e-9, 0.0, V0_eV * e)
    for m_q in range(0, m_max + 1):
        centrifugal = (hbar ** 2) * (m_q ** 2 - 0.25) / (2.0 * meff * m_e * r ** 2)
        E_J, vec = _solve_channel(r, V_J, meff, centrifugal, n_per_channel)
        for i, (E, u) in enumerate(zip(E_J, vec.T), start=1):
            if E / e >= V0_eV:
                continue
            out.append((E / e, i, m_q, u / np.sqrt(_trapz(u ** 2, r)), r * 1e9))
    return out


def _z_levels(Lz_nm, V0_eV, meff, nz_max, N, box_factor):
    """Levels of the confinement in z. Returns (E_eV, nz)."""
    if V0_eV is None or V0_eV <= 0:
        Lz = Lz_nm * 1e-9
        m = meff * m_e
        return [((hbar ** 2) * (np.pi * nz) ** 2 / (2.0 * m * Lz ** 2) / e, nz)
                for nz in range(1, nz_max + 1)]

    z_max = box_factor * Lz_nm
    z = np.linspace(-z_max / 2, z_max / 2, N) * 1e-9
    V_J = np.where(np.abs(z) <= Lz_nm * 1e-9 / 2, 0.0, V0_eV * e)
    E_J, _vec = _solve_channel(z, V_J, meff, np.zeros_like(z), nz_max)
    return [(E / e, nz) for nz, E in enumerate(E_J, start=1) if E / e < V0_eV]


def parabolic_dot(hw_xy_meV, hw_z_meV, n_shells=5) -> List[Level]:
    """Harmonic dot (Fock-Darwin with no field).

    E = hw_xy (n_xy + 1) + hw_z (n_z + 1/2), with n_xy = 0, 1, 2, … and shell
    n_xy holding n_xy+1 in-plane states.
    """
    if hw_xy_meV <= 0 or hw_z_meV <= 0:
        raise ValueError("the confinement energies must be positive")

    levels: List[Level] = []
    for n_xy in range(n_shells):
        for n_z in range(n_shells):
            E_meV = hw_xy_meV * (n_xy + 1) + hw_z_meV * (n_z + 0.5)
            levels.append(Level(
                E_eV=E_meV / 1000.0, quantum_numbers=(n_xy, n_z),
                label=f"({n_xy},{n_z})", degeneracy=n_xy + 1,
                channel=n_xy, bound=True,
            ))
    levels.sort(key=lambda lv: lv.E_eV)
    return levels



def _disc_levels(R, Lz, m, n_levels, width, per_channel):
    """The ``n_levels`` lowest states of the disc, whatever its shape.

    The basis used to be a fixed count — ``ceil(n_levels / 8)`` axial states,
    three for the twenty the designer asks for — which is fine for a flat
    lens, where the second axial level is already far above everything, and
    wrong for a tall one: with L_z above R the low-lying spectrum IS the
    axial ladder, and a cut at n_z = 3 leaves out states that belong in the
    first twenty. The fit then had to explain those peaks with in-plane
    states, and the same measurement came back as a different geometry from
    the "cylindrical" model — which is the same formula with a deeper basis.

    So the basis grows until it provably holds the lowest ``n_levels``: the
    energy rises monotonically in each quantum number, so every excluded
    state is at least as high as the cheapest one just past a cap. Once all
    three of those sit above the ``n_levels``-th energy, nothing is missing.
    A few iterations at most; the caps are only a runaway guard.
    """
    pref = (hbar ** 2) / (2.0 * m) / e
    E_xy = lambda a: pref * a ** 2 / R ** 2           # noqa: E731
    E_z = lambda nz: pref * (np.pi * nz) ** 2 / Lz ** 2   # noqa: E731

    nz_max = max(2, int(np.ceil(n_levels / 8)))
    a01 = _jn_zeros_cached(0, 1)[0]
    for _ in range(64):
        levels = []
        for m_q in range(width + 1):
            for n, a in enumerate(_jn_zeros_cached(m_q, per_channel), 1):
                exy = E_xy(a)
                for nz in range(1, nz_max + 1):
                    levels.append((exy + E_z(nz), (n, m_q, nz)))
        levels.sort(key=lambda item: item[0])
        if len(levels) < n_levels:
            nz_max += 1; per_channel += 1; width += 1
            continue
        cutoff = levels[n_levels - 1][0]
        grow = False
        # Cheapest state just past each cap. Each is a lower bound on
        # everything beyond that cap, by monotonicity.
        if E_xy(a01) + E_z(nz_max + 1) <= cutoff and nz_max < 64:
            nz_max += 1; grow = True
        if E_xy(_jn_zeros_cached(0, per_channel + 1)[-1]) + E_z(1) <= cutoff \
                and per_channel < 24:
            per_channel += 1; grow = True
        if E_xy(_jn_zeros_cached(width + 1, 1)[0]) + E_z(1) <= cutoff \
                and width < 24:
            width += 1; grow = True
        if not grow:
            return levels
    return levels

def _dot_states(model: str, dims, meff=0.067, n_levels=20):
    """The raw enumerated ladder of an infinite-barrier dot, ascending.

    Returns ``[(E_eV, (quantum numbers)), …]`` for the WHOLE basis it opened,
    with no truncation — one entry per set of quantum numbers the model
    distinguishes, which is not the same as one entry per distinct energy.

    This is the enumeration :func:`dot_energies` has always performed; it was
    lifted out unchanged so that :func:`dot_levels` can label the very same
    states with their degeneracy instead of enumerating them a second time.
    Two enumerations would eventually disagree — one of them would gain a
    basis-growth rule the other lacked — and a degeneracy that describes a
    slightly different ladder than the one the designer fits is worse than no
    degeneracy at all: it would be read as a measurement.

    ``n_levels`` sizes the basis; it does NOT trim the result. The caller
    truncates, because "the lowest 20 entries" and "the lowest 20 distinct
    energies" are different requests and only the caller knows which it made.
    """
    n_levels = max(1, int(n_levels))
    # How many channels to open to have at least n_levels before truncating.
    width = min(8, max(2, int(round(np.sqrt(n_levels)))))
    per_channel = max(2, int(np.ceil(n_levels / (width + 1))))
    m = meff * m_e

    out = []
    if model == DOT_SPHERICAL:
        R = float(dims[0]) * 1e-9
        if R <= 0:
            raise ValueError("R must be positive")
        for l in range(width + 1):
            for n, a in enumerate(_spherical_jn_zeros_cached(l, per_channel), 1):
                out.append(((hbar ** 2) * a ** 2 / (2.0 * m * R ** 2) / e, (n, l)))

    elif model == DOT_DISC:
        R, Lz = float(dims[0]) * 1e-9, float(dims[1]) * 1e-9
        if R <= 0 or Lz <= 0:
            raise ValueError("R and Lz must be positive")
        out = _disc_levels(R, Lz, m, n_levels, width, per_channel)

    elif model == DOT_PARABOLIC:
        hw_xy, hw_z = float(dims[0]), float(dims[1])
        if hw_xy <= 0 or hw_z <= 0:
            raise ValueError("the confinement energies must be positive")
        shells = max(3, int(np.ceil(np.sqrt(n_levels))))
        for n_xy in range(shells):
            for n_z in range(shells):
                out.append(((hw_xy * (n_xy + 1) + hw_z * (n_z + 0.5)) / 1000.0,
                            (n_xy, n_z)))

    else:
        raise ValueError(f"unknown dot model: {model!r}; "
                         f"expected one of {MODELS}")

    out.sort(key=lambda item: item[0])
    return out


def dot_energies(model: str, dims, meff=0.067, n_levels=20):
    """Levels of an infinite-barrier dot, in `physics.analytical`'s format.

    Returns ``[(E_eV, (quantum numbers)), …]`` in ascending order — the same
    signature as ``box_energies_1d_eV`` and friends, which is what the
    inverse designer consumes.

    Infinite barrier only, and deliberately so: there all three models are
    analytical (zeros of j_l, zeros of J_m, the oscillator ladder) and cost
    microseconds, which is what a global optimiser calling this thousands of
    times demands. A finite barrier is for the direct solver, where it is
    solved once.

    ``dims`` follows the model: ``(R,)`` spherical, ``(R, Lz)`` disc,
    ``(hw_xy, hw_z)`` parabolic — that last one **in meV**, not in nm.

    It stays a list of bare pairs, and stays the designer's entry point, even
    though :func:`dot_levels` now returns the same states carrying their
    degeneracy. Two reasons, both measured rather than assumed. The signature
    is unpackable as ``for E, _ in …`` at
    :mod:`src.physics.level_ratio_fit` and across four test modules, so a
    third element would break every one of them. And building twenty
    :class:`Level` dataclasses costs tens of microseconds against an
    objective evaluation of ~0.8 ms — a few per cent of the designer's hot
    loop, spent on fields that loop never reads.
    """
    return _dot_states(model, dims, meff, n_levels)[:max(1, int(n_levels))]


def _dot_weight(model: str, qn) -> int:
    """How many orbital states one enumerated entry stands for.

    Spin excluded, exactly as :attr:`Level.degeneracy` is defined. This is
    the *symmetry* multiplicity of a single set of quantum numbers — the
    projections the enumeration folded away — and nothing else; an accidental
    coincidence between two different entries is not visible from one entry
    and is counted by grouping (see :func:`dot_levels`).

    Each rule is verified against a brute-force enumeration of the full
    quantum-number lattice in ``tests/test_physics/test_level_degeneracy.py``,
    because a wrong degeneracy would be read as a measurement:

    ``spherical``
        2l+1 — the m_l projections, which the radial reduction removes.
    ``disc``
        2 for m != 0, 1 for m = 0 — the +/-m pair. ``_disc_levels`` iterates
        ``m_q >= 0`` only, so each of its m > 0 entries stands for two
        states. That fold is correct and complete, not a bug: the brute force
        over both signs reproduces its energy list exactly.
    ``parabolic``
        n_xy+1 — the in-plane oscillator shell. Note this one CAN be joined
        by accidental partners: at commensurate hw_xy:hw_z the shells
        interleave, and 20/30 meV puts (n_xy=0, n_z=2) and (n_xy=3, n_z=0) at
        the same 0.095 eV for a total of 5 rather than the 3 this rule sees
        for either entry alone.
    """
    if model == DOT_SPHERICAL:
        return 2 * int(qn[1]) + 1
    if model == DOT_DISC:
        return 2 if int(qn[1]) != 0 else 1
    if model == DOT_PARABOLIC:
        return int(qn[0]) + 1
    raise ValueError(f"unknown dot model: {model!r}; expected one of {MODELS}")


def _dot_label(model: str, qn) -> str:
    """The label ``spherical_dot`` / ``disc_dot`` / ``parabolic_dot`` uses.

    Deliberately the same strings as the forward solvers produce, so a level
    named in the Quantum Dot tool and the same level named in a designer
    candidate table are recognisably the same level.
    """
    if model == DOT_SPHERICAL:
        return orbital_label(int(qn[0]), int(qn[1]))
    if model == DOT_DISC:
        n, m_q, nz = (int(q) for q in qn)
        return f"({n},{m_q:+d},{nz})" if m_q else f"({n},0,{nz})"
    return f"({int(qn[0])},{int(qn[1])})"


def dot_levels(model: str, dims, meff=0.067, n_levels=20,
               distinct: bool = False) -> List[Level]:
    """The same ladder as :func:`dot_energies`, carrying its degeneracy.

    Analytic throughout, microseconds per call — it mirrors
    :func:`_dot_states` rather than calling :func:`disc_dot` or
    :func:`spherical_dot`, which build radial grids and run ``eigsh`` and
    would cost seconds per candidate. Those solvers already carry
    :attr:`Level.degeneracy` correctly; what was missing was a path from the
    *fast* enumeration to the same field.

    ``distinct`` picks which question is being asked, and the two answers
    differ for every model with degenerate entries:

    ``False`` (the default, and what the designer's ladder is)
        One :class:`Level` per enumerated entry, the first ``n_levels`` of
        them, in the exact order and with the exact energies
        :func:`dot_energies` returns. ``degeneracy`` is that entry's own
        symmetry multiplicity — how many physical states that row stands for.
        Summing the column over the rows gives the number of orbital states:
        a 4 nm / 5 nm lens's first eight "levels" are thirteen orbital
        states, twenty-six with spin, which is the thing a peak assignment
        needs to know and could not previously be told.

    ``True``
        One :class:`Level` per distinct ENERGY, the first ``n_levels`` of
        them, with ``degeneracy`` the total over every entry at that energy —
        symmetry multiplicity plus any accidental coincidence, which no
        per-entry formula can see. ``quantum_numbers`` and ``label`` name the
        lowest member of the group.

    The grouping tolerance is *relative* and extremely tight
    (:data:`src.physics.level_patterns.GROUP_RTOL`, 1e-9), because this is a
    symmetry fact about the model: true partners here agree to machine
    precision, since they are exact arithmetic on integers or on shared
    Bessel zeros. It is NOT the tolerance that answers "can this measurement
    tell these two levels apart" — that one is 3.5 k_B T, four hundred times
    wider at 90 K, belongs to the spectrum rather than to the model, and is
    reported separately. Conflating them would let the model claim a
    degeneracy the data cannot see.

    Degenerate groups are formed BEFORE the truncation, so ``distinct=True``
    can never cut a group in half and report half its multiplicity.
    """
    n_levels = max(1, int(n_levels))

    if not distinct:
        raw = dot_energies(model, dims, meff, n_levels)
        return [Level(E_eV=float(E), quantum_numbers=tuple(int(q) for q in qn),
                      label=_dot_label(model, qn),
                      degeneracy=_dot_weight(model, qn),
                      channel=_dot_channel(model, qn), bound=True)
                for E, qn in raw]

    # Distinct energies: enumerate well past n_levels, group, then cut. The
    # basis is sized for `factor * n_levels` entries and only that many are
    # grouped, so the sole group the cut can split is the last one — which is
    # therefore dropped. `factor` grows when the model turns out to be more
    # degenerate than the first guess (a commensurate parabolic dot collapses
    # 25 entries onto 17 energies), so no caller has to know the ratio.
    from src.physics.analytical import group_degeneracy
    for factor in (4, 8, 16, 32):
        raw = _dot_states(model, dims, meff, factor * n_levels)
        prefix = raw[:factor * n_levels]
        groups = group_degeneracy(
            [(E, qn, _dot_weight(model, qn)) for E, qn in prefix],
            with_representative=True)
        if len(groups) - 1 >= n_levels or len(prefix) < factor * n_levels:
            complete = groups[:-1] if len(groups) > n_levels else groups
            return [Level(E_eV=float(E),
                          quantum_numbers=tuple(int(q) for q in qn),
                          label=_dot_label(model, qn), degeneracy=int(g),
                          channel=_dot_channel(model, qn), bound=True)
                    for E, g, qn in complete[:n_levels]]
    raise RuntimeError(  # pragma: no cover - the 32x basis is far past any use
        f"{model} did not yield {n_levels} distinct levels at a 32x basis")


def _dot_channel(model: str, qn) -> int:
    """l for the sphere, |m| for the disc, the shell index for the parabola."""
    if model == DOT_SPHERICAL:
        return int(qn[1])
    if model == DOT_DISC:
        return abs(int(qn[1]))
    return int(qn[0])


def levels_for(ndim: str, coords: str, dims, meff=0.067, n_levels=20,
               distinct: bool = False) -> List[Level]:
    """Labelled levels for any geometry the inverse designer can produce.

    One dispatch, mirroring :meth:`src.physics.designer.Designer.compute_energies`
    case for case — 0D by model name, 1D a box, 2D circular or Cartesian, 3D
    cylindrical or Cartesian. There are deliberately two functions rather than
    one because they answer different questions (that one returns bare pairs
    into an optimiser's inner loop; this one returns records into a table),
    but they must never disagree about which model a configuration *means*:
    ``test_levels_for_matches_compute_energies`` asserts the energies are
    equal branch by branch, so a model added to one and forgotten in the
    other fails a test rather than mislabelling a candidate.

    ``dims`` is in nm, in the model's own order, except a parabolic dot's
    ``(hw_xy, hw_z)`` in meV — the same convention
    :meth:`~src.physics.designer.Designer.params_to_dims` hands over.

    ``distinct`` is passed straight through; see :func:`dot_levels`. It
    defaults to False, so a caller that just wants the designer's own ladge
    labelled gets exactly that ladder.
    """
    # Imported here rather than at module scope: `src.physics.level_patterns`
    # imports THIS module for `spherical_dot`, and `analytical` is what
    # `level_patterns` builds on, so a module-level import would close a
    # cycle at the first `import src.physics.analytical`. The cost is one
    # sys.modules lookup per call, against a call rate of at most a dozen per
    # spectrum.
    from src.physics import analytical

    if ndim == "0D":
        return dot_levels(coords, dims, meff, n_levels, distinct=distinct)
    if ndim == "1D":
        return analytical.box_levels_1d(dims[0], meff, n_levels,
                                        distinct=distinct)
    if ndim == "2D":
        if coords == "circular":
            return analytical.disk_levels(dims[0], meff, n_levels,
                                          distinct=distinct)
        return analytical.box_levels_2d(dims[0], dims[1], meff, n_levels,
                                        distinct=distinct)
    if ndim == "3D":
        if coords == "cylindrical":
            return analytical.cylinder_levels(dims[0], dims[1], meff, n_levels,
                                              distinct=distinct)
        return analytical.box_levels_3d(dims[0], dims[1], dims[2], meff,
                                        n_levels, distinct=distinct)
    raise ValueError(f"unknown ndim: {ndim!r}; expected 0D, 1D, 2D or 3D")


def hw_from_length(l_nm, meff=0.067):
    """hbar*omega (meV) of an oscillator with confinement length ``l_nm``.

    l = sqrt(hbar / (m* w)) is the size of the ground state, so
    hbar*w = hbar^2 / (m* l^2). This lets the inverse designer search for a
    parabolic dot in nanometres, as it does for every other geometry,
    instead of in meV — a user can estimate a size, not a hbar*omega.
    """
    if l_nm <= 0:
        raise ValueError("the confinement length must be positive")
    return (hbar ** 2) / (meff * m_e * (l_nm * 1e-9) ** 2) / e * 1000.0


def length_from_hw(hw_meV, meff=0.067):
    """Inverse of :func:`hw_from_length` — hbar*omega (meV) to l (nm)."""
    if hw_meV <= 0:
        raise ValueError("hbar*omega must be positive")
    return np.sqrt((hbar ** 2) / (meff * m_e * hw_meV / 1000.0 * e)) * 1e9


# ─── analysis ───────────────────────────────────────────────────────────────

def shell_table(levels: List[Level], tol_eV=1e-4):
    """Group degenerate levels into shells.

    Returns ``[(E_eV, [labels], total_degeneracy, cumulative_occupancy)]``,
    which is how a quantum-dot spectrum is read: one filled shell at a time.
    """
    shells = []
    used = set()
    filled = 0
    for i, lv in enumerate(levels):
        if i in used:
            continue
        group = [lv]
        used.add(i)
        for j in range(i + 1, len(levels)):
            if j not in used and abs(levels[j].E_eV - lv.E_eV) < tol_eV:
                group.append(levels[j])
                used.add(j)
        degeneracy = sum(g.degeneracy for g in group)
        filled += 2 * degeneracy
        shells.append((lv.E_eV, [g.label for g in group], degeneracy, filled))
    return shells


def addition_energies(levels: List[Level], charging_eV=0.0):
    """Addition energy in the constant-interaction model.

    ``E_add(N) = E(N+1) - E(N) + Ec``: the cost of adding the next electron.
    With ``charging_eV=0`` only the level spacings are left, and the peaks
    mark each shell closing — the signature a Coulomb-blockade measurement
    shows.
    """
    ladder = []
    for lv in levels:
        ladder.extend([lv.E_eV] * lv.occupancy)
    ladder.sort()
    return [ladder[i + 1] - ladder[i] + charging_eV for i in range(len(ladder) - 1)]


def level_spectrum(levels: List[Level], broadening_eV=0.005, n_points=1200,
                   e_min=None, e_max=None):
    """Gaussian density of states — what a dI/dV measurement would see.

    Each level enters weighted by its degeneracy, so a filled shell's peak is
    proportionally taller.
    """
    if not levels:
        return np.zeros(0), np.zeros(0)
    energies = np.array([lv.E_eV for lv in levels])
    weights = np.array([lv.degeneracy for lv in levels], dtype=float)
    lo = energies.min() - 6 * broadening_eV if e_min is None else e_min
    hi = energies.max() + 6 * broadening_eV if e_max is None else e_max
    grid = np.linspace(lo, hi, n_points)
    dos = np.zeros_like(grid)
    for E, w in zip(energies, weights):
        dos += w * np.exp(-0.5 * ((grid - E) / broadening_eV) ** 2)
    dos /= broadening_eV * np.sqrt(2 * np.pi)
    return grid, dos
