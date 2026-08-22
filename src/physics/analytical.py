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

    max_m = 6
    max_n = 6
    max_l = 10

    bessel_zeros = {}
    for m_ang in range(max_m):
        bessel_zeros[m_ang] = jn_zeros(m_ang, max_n)

    energies = []
    for m_ang in range(max_m):
        for n_rad in range(1, max_n + 1):
            x_mn = bessel_zeros[m_ang][n_rad - 1]
            for l_ax in range(1, max_l + 1):
                E = prefactor * ((x_mn / R)**2 + (l_ax * pi / H)**2)
                energies.append((E / e, (m_ang, n_rad, l_ax)))

    energies.sort(key=lambda x: x[0])
    return energies[:n_levels]
