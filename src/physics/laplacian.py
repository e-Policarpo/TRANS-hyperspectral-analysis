"""
Finite-difference Laplacian builders for 1D, 2D, and 3D grids.
All functions are standalone (no class state) and return scipy sparse matrices.
BC strings are lowercase English: "dirichlet", "neumann", "periodic".
"""

import numpy as np
from scipy.sparse import diags, kron, identity, csr_matrix


# ─── 1D Laplacian ────────────────────────────────────────────────────────────

def lap1d(n, h, bc="dirichlet"):
    """
    1D second-difference matrix with specified boundary conditions.
    Returns sparse CSR matrix of shape (n, n), divided by h².
    """
    main = -2.0 * np.ones(n)
    off = 1.0 * np.ones(n - 1)

    bc = bc.lower()
    if bc == "dirichlet":
        L = diags([off, main, off], offsets=[-1, 0, 1], format="csr")
    elif bc == "neumann":
        L = diags([off, main, off], offsets=[-1, 0, 1], format="lil")
        L[0, 0] = -1.0
        L[n - 1, n - 1] = -1.0
        L = L.tocsr()
    elif bc == "periodic":
        L = diags([off, main, off], offsets=[-1, 0, 1], format="lil")
        L[0, n - 1] = 1.0
        L[n - 1, 0] = 1.0
        L = L.tocsr()
    else:
        raise ValueError(f"Unknown BC type: {bc}")

    return L / (h * h)


# ─── 2D Cartesian ────────────────────────────────────────────────────────────

def _parse_bc(bc, ndim):
    """Normalise *bc* to a tuple of length *ndim*.

    Accepts a single string (applied to every axis) or a tuple/list of per-axis
    strings, e.g. ``("periodic", "dirichlet")`` for a 2D problem periodic in x
    and Dirichlet in y.
    """
    if isinstance(bc, str):
        return (bc.lower(),) * ndim
    bc = tuple(b.lower() for b in bc)
    if len(bc) != ndim:
        raise ValueError(f"Expected {ndim} BC entries, got {len(bc)}")
    return bc


def lap2d_cartesian(Nx, Ny, dx, dy, bc="dirichlet"):
    """2D Laplacian via Kronecker sum of 1D operators.

    *bc* may be a single string or a 2-tuple of per-axis strings,
    e.g. ``("periodic", "dirichlet")``.
    """
    bcx, bcy = _parse_bc(bc, 2)
    Lx1 = lap1d(Nx, dx, bcx)
    Ly1 = lap1d(Ny, dy, bcy)
    Ix = identity(Nx, format="csr")
    Iy = identity(Ny, format="csr")
    return csr_matrix(kron(Lx1, Iy) + kron(Ix, Ly1))


# ─── 3D Cartesian ────────────────────────────────────────────────────────────

def lap3d_cartesian(Nx, Ny, Nz, dx, dy, dz, bc="dirichlet"):
    """3D Laplacian via Kronecker sum of 1D operators.

    *bc* may be a single string or a 3-tuple of per-axis strings,
    e.g. ``("periodic", "dirichlet", "dirichlet")`` for a nanotube
    (periodic along x, confined in y and z).
    """
    bcx, bcy, bcz = _parse_bc(bc, 3)
    Lx1 = lap1d(Nx, dx, bcx)
    Ly1 = lap1d(Ny, dy, bcy)
    Lz1 = lap1d(Nz, dz, bcz)
    Ix = identity(Nx, format="csr")
    Iy = identity(Ny, format="csr")
    Iz = identity(Nz, format="csr")
    Lap = (kron(kron(Lx1, Iy), Iz) +
           kron(kron(Ix, Ly1), Iz) +
           kron(kron(Ix, Iy), Lz1))
    return csr_matrix(Lap)


# ─── 2D Polar ────────────────────────────────────────────────────────────────

def lap2d_polar(Nr, Ntheta, R, bc_r="dirichlet"):
    """
    2D Laplacian in polar coordinates.
    ∇² = (1/r)∂/∂r(r∂/∂r) + (1/r²)∂²/∂θ²

    At r=0: regularity condition (dψ/dr=0 for m=0 modes).
    Returns (Lap, r, theta) where r is in meters.
    """
    dtheta = 2 * np.pi / Ntheta
    bc_r = bc_r.lower()

    if bc_r == "dirichlet":
        dr = R / (Nr + 1)
        r = np.linspace(dr, R - dr, Nr)
    elif bc_r == "neumann":
        dr = R / Nr
        r = np.linspace(dr, R, Nr)
    else:
        dr = R / Nr
        r = np.linspace(dr, R, Nr)

    # Radial part: conservative form (1/r)d/dr(r df/dr)
    Lr = np.zeros((Nr, Nr))
    for i in range(Nr):
        ri = r[i]
        r_plus = ri + dr / 2
        r_minus = ri - dr / 2
        coef_minus = r_minus / (ri * dr**2)
        coef_plus = r_plus / (ri * dr**2)
        coef_center = -(r_plus + r_minus) / (ri * dr**2)

        Lr[i, i] = coef_center
        if i > 0:
            Lr[i, i - 1] = coef_minus
        if i < Nr - 1:
            Lr[i, i + 1] = coef_plus

    # BC at r=0: regularity (ghost f_{-1} = f_1)
    r0 = r[0]
    r_minus_0 = r0 - dr / 2
    r_plus_0 = r0 + dr / 2
    Lr[0, 0] = -(r_plus_0 + r_minus_0) / (r0 * dr**2)
    if Nr > 1:
        Lr[0, 1] = (r_plus_0 + r_minus_0) / (r0 * dr**2)

    if bc_r == "neumann":
        ri = r[Nr - 1]
        r_minus = ri - dr / 2
        Lr[Nr - 1, Nr - 1] = -r_minus / (ri * dr**2)
        if Nr > 1:
            Lr[Nr - 1, Nr - 2] = r_minus / (ri * dr**2)

    # Angular part: periodic
    Ltheta_1d = np.zeros((Ntheta, Ntheta))
    for i in range(Ntheta):
        Ltheta_1d[i, i] = -2.0
        Ltheta_1d[i, (i + 1) % Ntheta] = 1.0
        Ltheta_1d[i, (i - 1) % Ntheta] = 1.0
    Ltheta_1d /= dtheta**2

    Lr_sparse = csr_matrix(Lr)
    Ltheta_sparse = csr_matrix(Ltheta_1d)

    Ir = identity(Nr, format="csr")
    Itheta = identity(Ntheta, format="csr")

    Lap_r = kron(Lr_sparse, Itheta)
    inv_r2 = diags(1.0 / r**2, 0, format="csr")
    Lap_theta = kron(inv_r2, Ltheta_sparse)

    Lap = Lap_r + Lap_theta
    theta = np.linspace(0, 2 * np.pi * (1 - 1 / Ntheta), Ntheta)
    return csr_matrix(Lap), r, theta


# ─── 3D Cylindrical ──────────────────────────────────────────────────────────

def lap3d_cylindrical(Nr, Ntheta, Nz, r, dr, dtheta, dz, bc="dirichlet"):
    """
    3D Laplacian in cylindrical coordinates (r, θ, z).
    ∇² = (1/r)∂/∂r(r∂/∂r) + (1/r²)∂²/∂θ² + ∂²/∂z²
    """
    # Radial part
    main_r = -2.0 * np.ones(Nr)
    off_r = np.ones(Nr - 1)
    Lr = diags([off_r, main_r, off_r], offsets=[-1, 0, 1], format="lil")
    for i in range(Nr):
        ri = r[i]
        if ri > 1e-10:
            if i > 0:
                Lr[i, i - 1] += -1.0 / (2.0 * ri * dr) * dr * dr
            if i < Nr - 1:
                Lr[i, i + 1] += 1.0 / (2.0 * ri * dr) * dr * dr
    Lr = csr_matrix(Lr) / (dr * dr)

    # Angular part: always periodic in θ
    main_theta = -2.0 * np.ones(Ntheta)
    off_theta = np.ones(Ntheta - 1)
    Ltheta = diags([off_theta, main_theta, off_theta], offsets=[-1, 0, 1], format="lil")
    Ltheta[0, Ntheta - 1] = 1.0
    Ltheta[Ntheta - 1, 0] = 1.0
    Ltheta = csr_matrix(Ltheta) / (dtheta * dtheta)

    # z part
    Lz = lap1d(Nz, dz, bc)

    Ir = identity(Nr, format="csr")
    Itheta = identity(Ntheta, format="csr")
    Iz = identity(Nz, format="csr")

    r_inv2 = np.array([1.0 / (ri * ri) if ri > 1e-10 else 0 for ri in r])
    R_inv2 = diags(r_inv2, 0, format="csr")

    Lap = (kron(kron(Lr, Itheta), Iz) +
           kron(kron(R_inv2, Ltheta), Iz) +
           kron(kron(Ir, Itheta), Lz))
    return csr_matrix(Lap)


# ─── 3D Spherical ────────────────────────────────────────────────────────────

def lap3d_spherical(Nr, Ntheta, Nphi, r, dr, dtheta, dphi, bc="dirichlet"):
    """
    3D Laplacian in spherical coordinates (r, θ, φ).
    ∇² = (1/r²)∂/∂r(r²∂/∂r) + (1/r²sinθ)∂/∂θ(sinθ∂/∂θ) + (1/r²sin²θ)∂²/∂φ²
    """
    # Radial part
    main_r = -2.0 * np.ones(Nr)
    off_r = np.ones(Nr - 1)
    Lr = diags([off_r, main_r, off_r], offsets=[-1, 0, 1], format="lil")
    for i in range(Nr):
        ri = r[i]
        if ri > 1e-10:
            if i > 0:
                Lr[i, i - 1] += -1.0 / (ri * dr) * dr * dr
            if i < Nr - 1:
                Lr[i, i + 1] += 1.0 / (ri * dr) * dr * dr
    Lr = csr_matrix(Lr) / (dr * dr)

    # Theta part with sin(θ) terms
    theta = np.linspace(dtheta / 2, np.pi - dtheta / 2, Ntheta)
    sin_theta = np.sin(theta)

    main_theta = -2.0 * np.ones(Ntheta)
    off_theta = np.ones(Ntheta - 1)
    Ltheta = diags([off_theta, main_theta, off_theta], offsets=[-1, 0, 1], format="lil")
    for i in range(Ntheta):
        if sin_theta[i] > 1e-10:
            cot = np.cos(theta[i]) / sin_theta[i]
            if i > 0:
                Ltheta[i, i - 1] += -cot / (2.0 * dtheta) * dtheta * dtheta
            if i < Ntheta - 1:
                Ltheta[i, i + 1] += cot / (2.0 * dtheta) * dtheta * dtheta
    Ltheta = csr_matrix(Ltheta) / (dtheta * dtheta)

    # Phi part: always periodic
    main_phi = -2.0 * np.ones(Nphi)
    off_phi = np.ones(Nphi - 1)
    Lphi = diags([off_phi, main_phi, off_phi], offsets=[-1, 0, 1], format="lil")
    Lphi[0, Nphi - 1] = 1.0
    Lphi[Nphi - 1, 0] = 1.0
    Lphi = csr_matrix(Lphi) / (dphi * dphi)

    Ir = identity(Nr, format="csr")
    Itheta = identity(Ntheta, format="csr")
    Iphi = identity(Nphi, format="csr")

    r_inv2 = np.array([1.0 / (ri * ri) if ri > 1e-10 else 0 for ri in r])
    sin2_inv = np.array([1.0 / (s * s) if s > 1e-10 else 0 for s in sin_theta])
    R_inv2 = diags(r_inv2, 0, format="csr")
    Sin2_inv = diags(sin2_inv, 0, format="csr")

    Lap = (kron(kron(Lr, Itheta), Iphi) +
           kron(kron(R_inv2 @ Ir, Ltheta), Iphi) +
           kron(R_inv2, kron(Sin2_inv, Lphi)))
    return csr_matrix(Lap)
