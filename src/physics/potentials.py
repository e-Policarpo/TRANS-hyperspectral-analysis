"""
Potential builders for 2D and 3D quantum well systems.
All functions are standalone — they take physical parameters and return arrays.
"""

import numpy as np
from scipy.constants import e

from src.physics.laplacian import (azimuth_nodes, polar_angle_nodes,
                                   radial_nodes)


def _angular_mask(grid, centre_rad, sweep_rad):
    """Which nodes of a periodic angle a sweep of *sweep_rad* about
    *centre_rad* covers.

    There are two ways to get this wrong and the 3-D builders had one of them.
    A full turn is it: reduced mod 2*pi the two ends land on the same angle, so
    a well meant to wrap the whole way round came out exactly one node wide —
    and a ring is the commonest shape there is on a cylindrical or spherical
    grid, which made the wedge door useless for the shapes it was most wanted
    for. The other is a sweep straddling the seam at 0, where the interval is
    the union of two rather than an intersection.
    """
    sweep = float(sweep_rad)
    if sweep >= 2 * np.pi - 1e-12:
        return np.ones_like(grid, dtype=bool)
    lo = (centre_rad - sweep / 2) % (2 * np.pi)
    hi = (centre_rad + sweep / 2) % (2 * np.pi)
    if lo <= hi:
        return (grid >= lo) & (grid <= hi)
    return (grid >= lo) | (grid <= hi)


# ─── 3D Cartesian ────────────────────────────────────────────────────────────

def build_potential_3d_cartesian(wells, L1, L2, L3, N1, N2, N3,
                                  V_barrier_eV=0.0, bc="dirichlet"):
    """
    Build 3D potential on a Cartesian grid centered at (0,0,0).

    Parameters
    ----------
    wells : list of tuples
        Each: (cx_nm, cy_nm, cz_nm, wLx_nm, wLy_nm, wLz_nm, V0_eV, meff)
        cx/cy/cz are well centres in nm; wLx/wLy/wLz are sizes in nm.
    L1, L2, L3 : float
        Domain sizes in metres (Lx, Ly, Lz).
    N1, N2, N3 : int
        Grid points per axis.
    V_barrier_eV : float
        Background potential in eV.
    bc : str
        Boundary condition type ("dirichlet" or other).

    Returns
    -------
    V : ndarray shape (N1, N2, N3), in Joules
    coords : (x, y, z) arrays in metres
    """
    half_L1, half_L2, half_L3 = L1 / 2, L2 / 2, L3 / 2

    if bc.lower() == "dirichlet":
        dx, dy, dz = L1 / (N1 + 1), L2 / (N2 + 1), L3 / (N3 + 1)
        x = np.linspace(-half_L1 + dx, half_L1 - dx, N1)
        y = np.linspace(-half_L2 + dy, half_L2 - dy, N2)
        z = np.linspace(-half_L3 + dz, half_L3 - dz, N3)
    else:
        dx, dy, dz = L1 / N1, L2 / N2, L3 / N3
        x = np.linspace(-half_L1 + dx / 2, half_L1 - dx / 2, N1)
        y = np.linspace(-half_L2 + dy / 2, half_L2 - dy / 2, N2)
        z = np.linspace(-half_L3 + dz / 2, half_L3 - dz / 2, N3)

    X, Y, Z = np.meshgrid(x, y, z, indexing='ij')
    V = np.full((N1, N2, N3), V_barrier_eV * e)

    for (cx_nm, cy_nm, cz_nm, wLx_nm, wLy_nm, wLz_nm, V0_eV, _meff) in wells:
        cx, cy, cz = cx_nm * 1e-9, cy_nm * 1e-9, cz_nm * 1e-9
        wLx, wLy, wLz = wLx_nm * 1e-9, wLy_nm * 1e-9, wLz_nm * 1e-9

        x_min, x_max = cx - wLx / 2, cx + wLx / 2
        y_min, y_max = cy - wLy / 2, cy + wLy / 2
        z_min, z_max = cz - wLz / 2, cz + wLz / 2

        mask = ((X >= x_min) & (X <= x_max) &
                (Y >= y_min) & (Y <= y_max) &
                (Z >= z_min) & (Z <= z_max))
        V[mask] = V0_eV * e

    return V, (x, y, z)


# ─── 3D Cylindrical ──────────────────────────────────────────────────────────

def build_potential_3d_cylindrical(wells, R, Lz, Nr, Nz, Ntheta,
                                    V_barrier_eV=0.0, bc="dirichlet"):
    """
    Build 3D potential on a cylindrical grid.

    Parameters
    ----------
    wells : list of tuples
        Each: (r_c_nm, theta_c_deg, z_c_nm, dr_nm, dtheta_deg, dz_nm, V0_eV, meff)
    R : float  — max radius in metres
    Lz : float — height in metres
    Nr, Nz, Ntheta : int
    bc : str
        Boundary condition along z, which is the only axis whose grid it can
        still change: the radial nodes are cell-centred either way, because
        that is what makes the operator in :mod:`~src.physics.laplacian`
        regular at r = 0, and a potential sampled anywhere else would be
        sampled off the grid the states are solved on.
    """
    half_Lz = Lz / 2
    r, dr = radial_nodes(R, Nr)
    theta, _ = azimuth_nodes(Ntheta)

    if bc.lower() == "dirichlet":
        dz = Lz / (Nz + 1)
        z = np.linspace(-half_Lz + dz, half_Lz - dz, Nz)
    else:
        dz = Lz / Nz
        z = np.linspace(-half_Lz + dz / 2, half_Lz - dz / 2, Nz)

    RR, TT, ZZ = np.meshgrid(r, theta, z, indexing='ij')
    V = np.full((Nr, Ntheta, Nz), V_barrier_eV * e)

    for (r_c_nm, theta_c_deg, z_c_nm, dr_nm, dtheta_deg, dz_nm, V0_eV, _meff) in wells:
        r_c = r_c_nm * 1e-9
        z_c = z_c_nm * 1e-9
        dr_well = dr_nm * 1e-9
        dz_well = dz_nm * 1e-9
        theta_c = np.radians(theta_c_deg)
        dtheta_well = np.radians(dtheta_deg)

        r_min = max(0, r_c - dr_well / 2)
        r_max = r_c + dr_well / 2
        z_min = z_c - dz_well / 2
        z_max = z_c + dz_well / 2

        r_mask = (RR >= r_min) & (RR <= r_max)
        z_mask = (ZZ >= z_min) & (ZZ <= z_max)
        theta_mask = _angular_mask(TT, theta_c, dtheta_well)

        V[r_mask & theta_mask & z_mask] = V0_eV * e

    return V, (r, theta, z)


# ─── 3D Spherical ────────────────────────────────────────────────────────────

def build_potential_3d_spherical(wells, R, Nr, Ntheta, Nphi,
                                  V_barrier_eV=0.0):
    """
    Build 3D potential on a spherical grid.

    Parameters
    ----------
    wells : list of tuples
        Each: (r_c_nm, theta_c_deg, phi_c_deg, dr_nm, dtheta_deg, dphi_deg, V0_eV, meff)
    R : float  — max radius in metres

    There is no boundary-condition argument: every axis of a spherical grid is
    cell-centred, r off the origin and theta off both poles, so the wall at R
    is the operator's business rather than the grid's.
    """
    r, dr = radial_nodes(R, Nr)
    theta, _ = polar_angle_nodes(Ntheta)
    phi, _ = azimuth_nodes(Nphi)

    RR, TT, PP = np.meshgrid(r, theta, phi, indexing='ij')
    V = np.full((Nr, Ntheta, Nphi), V_barrier_eV * e)

    for (r_c_nm, theta_c_deg, phi_c_deg, dr_nm, dtheta_deg, dphi_deg, V0_eV, _meff) in wells:
        r_c = r_c_nm * 1e-9
        dr_well = dr_nm * 1e-9
        theta_c = np.radians(theta_c_deg)
        dtheta_well = np.radians(dtheta_deg)
        phi_c = np.radians(phi_c_deg)
        dphi_well = np.radians(dphi_deg)

        r_min = max(0, r_c - dr_well / 2)
        r_max = r_c + dr_well / 2
        # theta is not periodic — it runs from pole to pole — so it clamps
        # rather than wrapping, and only phi goes through _angular_mask.
        theta_min = max(0, theta_c - dtheta_well / 2)
        theta_max = min(np.pi, theta_c + dtheta_well / 2)

        r_mask = (RR >= r_min) & (RR <= r_max)
        theta_mask = (TT >= theta_min) & (TT <= theta_max)
        phi_mask = _angular_mask(PP, phi_c, dphi_well)

        V[r_mask & theta_mask & phi_mask] = V0_eV * e

    return V, (r, theta, phi)


# ─── 2D Cartesian ────────────────────────────────────────────────────────────

def build_potential_2d_cartesian(features, x, y, Nx, Ny, V_barrier_eV=0.0):
    """
    Build 2D potential from rectangular features on a Cartesian grid.

    Parameters
    ----------
    features : list of (x0_nm, y0_nm, w_nm, h_nm, V0_eV)
        x0/y0 are lower-left corner in nm, w/h are sizes in nm.
    x, y : 1-D arrays in nm (grid coordinates)
    Nx, Ny : int
    V_barrier_eV : float

    Returns
    -------
    V : ndarray (Nx, Ny) in Joules
    X, Y : meshgrid arrays
    """
    X, Y = np.meshgrid(x, y, indexing="ij")
    V = np.full((Nx, Ny), V_barrier_eV * e)

    for (x0, y0, fw, fh, V0_eV) in features:
        mask = (X >= x0) & (X <= x0 + fw) & (Y >= y0) & (Y <= y0 + fh)
        V[mask] = V0_eV * e

    return V, X, Y


# ─── 2D Polar ────────────────────────────────────────────────────────────────

def build_potential_2d_polar(features, r_nm, theta, Nr, Ntheta, V_barrier_eV=0.0):
    """
    Build 2D potential from wedge features on a polar grid.

    Parameters
    ----------
    features : list of (r0_nm, theta0_deg, dr_nm, dtheta_deg, V0_eV)
    r_nm : 1-D array of radial positions in nm
    theta : 1-D array of angles in radians
    """
    R_grid, Theta_grid = np.meshgrid(r_nm, theta, indexing="ij")
    V = np.full((Nr, Ntheta), V_barrier_eV * e)

    for (r0_nm, theta0_deg, dr_nm, dtheta_deg, V0_eV) in features:
        r0 = r0_nm
        r1 = r0_nm + dr_nm
        theta0 = np.radians(theta0_deg)
        theta1 = np.radians(theta0_deg + dtheta_deg)

        if dtheta_deg >= 360:
            mask_theta = np.ones_like(Theta_grid, dtype=bool)
        elif theta1 <= 2 * np.pi:
            mask_theta = (Theta_grid >= theta0) & (Theta_grid <= theta1)
        else:
            mask_theta = (Theta_grid >= theta0) | (Theta_grid <= theta1 - 2 * np.pi)

        mask_r = (R_grid >= r0) & (R_grid <= r1)
        V[mask_r & mask_theta] = V0_eV * e

    return V, R_grid, Theta_grid
