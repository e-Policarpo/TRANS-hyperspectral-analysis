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
        nz_max = max(2, int(np.ceil(n_levels / 8)))
        z_energies = [((hbar ** 2) * (np.pi * nz) ** 2 / (2.0 * m * Lz ** 2) / e, nz)
                      for nz in range(1, nz_max + 1)]
        for m_q in range(width + 1):
            for n, a in enumerate(_jn_zeros_cached(m_q, per_channel), 1):
                E_xy = (hbar ** 2) * a ** 2 / (2.0 * m * R ** 2) / e
                for E_z, nz in z_energies:
                    out.append((E_xy + E_z, (n, m_q, nz)))

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
    return out[:n_levels]


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
