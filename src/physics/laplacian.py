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



# ─── Curved grids: where the nodes go, and why ───────────────────────────────
#
# Every curved Laplacian here is written in flux (conservative) form,
#
#     (1/w_i) [ w_{i-1/2} (f_{i-1} - f_i) + w_{i+1/2} (f_{i+1} - f_i) ] / h^2,
#
# with the metric weight w evaluated on the cell *faces* and on the node. That
# is not a stylistic choice. The naive form, f'' + (k/r) f', has a 1/r in it
# that has to be guarded against r = 0; the flux form has the weight itself —
# r on a disc, r^2 in a sphere, sin(theta) at a pole — and that weight is
# *zero* at exactly the places the coordinate system is singular. Put the
# innermost face on the singularity and the term multiplies itself out: no
# ghost point, no regularity condition to impose by hand, no `r > 1e-10`.
#
# The second payoff is symmetry. A curved Laplacian is never symmetric as a
# matrix, but written this way it is exactly self-adjoint under the weight —
# w_i L_ij == w_j L_ji to machine precision — so a solver can symmetrise it
# with W^{1/2} L W^{-1/2} and use the real-symmetric eigensolver honestly. The
# weight arrays for that transform are :func:`polar_weights` and friends
# below; see ``_solve_on_curved_grid`` in :mod:`~src.physics.solvers`.


def radial_nodes(R, Nr):
    """Cell-centred radial nodes on ``(0, R]``: ``r_i = (i + 1/2) dr``.

    Half a step off the origin, deliberately — see the note above. Returns
    ``(r, dr)`` in whatever unit *R* was given in (the solvers use metres).
    """
    Nr = int(Nr)
    if Nr < 1:
        raise ValueError("a radial grid needs at least one node")
    dr = float(R) / Nr
    return (np.arange(Nr) + 0.5) * dr, dr


def azimuth_nodes(Ntheta):
    """Nodes for a full turn, ``theta_i = i * dtheta``, and ``dtheta``.

    The last node stops one step short of 2*pi rather than landing on the
    first one: the angle is periodic, so a node at 2*pi would be the node at 0
    counted twice.
    """
    Ntheta = int(Ntheta)
    if Ntheta < 3:
        raise ValueError("a periodic angle needs at least three nodes")
    dtheta = 2.0 * np.pi / Ntheta
    return np.arange(Ntheta) * dtheta, dtheta


def polar_angle_nodes(Ntheta):
    """Cell-centred nodes on ``(0, pi)`` for the spherical polar angle.

    The same trick as :func:`radial_nodes`, at both ends: ``sin(theta)``
    vanishes on the two pole faces, so the poles need no special row either.
    """
    Ntheta = int(Ntheta)
    if Ntheta < 2:
        raise ValueError("a polar angle needs at least two nodes")
    dtheta = np.pi / Ntheta
    return (np.arange(Ntheta) + 0.5) * dtheta, dtheta


def _check_cell_centred(nodes, spacing, what):
    """Refuse a grid the flux form is not valid on.

    The whole construction rests on the first face sitting on the singularity,
    which is true only for the cell-centred grid these builders' node helpers
    produce. A caller that passes ``linspace(dr, R - dr, Nr)`` instead would
    get an answer that looks plausible and is wrong by several percent in
    every state that does not vanish at the origin, so this is worth a loud
    failure rather than a silent one.
    """
    nodes = np.asarray(nodes, dtype=float)
    tol = 1e-6 * abs(spacing)
    ok = abs(nodes[0] - spacing / 2.0) <= tol
    if ok and len(nodes) > 1:
        ok = np.all(np.abs(np.diff(nodes) - spacing) <= tol)
    if not ok:
        raise ValueError(
            f"the {what} grid must be the cell-centred one — first node at "
            f"h/2, uniform step h. Build it with the node helpers in "
            f"src.physics.laplacian, not with linspace.")
    return nodes


def _flux_operator(face_weight, node_weight, h, outer="dirichlet"):
    """The 1-D operator ``(1/w) d/dx (w d/dx)`` on a cell-centred grid.

    *face_weight* has one entry per face (``N + 1`` of them), *node_weight* one
    per node. A face whose weight is zero is a boundary that closes itself —
    nothing flows through it — which is how the origin and the poles are
    handled. *outer* says what to do at the last face, where the weight is not
    zero: ``"dirichlet"`` mirrors the ghost node to ``-f`` so the field
    vanishes on the face, ``"neumann"`` copies it so nothing flows out.
    """
    node_weight = np.asarray(node_weight, dtype=float)
    face_weight = np.asarray(face_weight, dtype=float)
    N = len(node_weight)
    inv = 1.0 / (node_weight * h * h)
    w_minus, w_plus = face_weight[:-1], face_weight[1:]

    main = -(w_minus + w_plus) * inv
    if outer == "dirichlet":
        main[-1] -= w_plus[-1] * inv[-1]
    elif outer == "neumann":
        main[-1] += w_plus[-1] * inv[-1]
    else:
        raise ValueError(f"Unknown BC type: {outer}")

    lower = w_minus[1:] * inv[1:]
    upper = w_plus[:-1] * inv[:-1]
    return diags([lower, main, upper], offsets=[-1, 0, 1], format="csr")


def _radial_2d(r, dr, bc="dirichlet"):
    """``(1/r) d/dr (r d/dr)`` — the polar and cylindrical radial part."""
    return _flux_operator(np.concatenate(([0.0], r + dr / 2.0)), r, dr, bc)


def _radial_3d(r, dr, bc="dirichlet"):
    """``(1/r^2) d/dr (r^2 d/dr)`` — the spherical radial part."""
    faces = np.concatenate(([0.0], (r + dr / 2.0) ** 2))
    return _flux_operator(faces, r ** 2, dr, bc)


def _polar_angle(theta, dtheta):
    """``(1/sin t) d/dt (sin t d/dt)`` — the theta part, poles included."""
    faces = np.sin(np.concatenate(([0.0], theta + dtheta / 2.0)))
    # sin(pi) is 1.2e-16, not 0, and a face weight that is merely tiny is a
    # leak out of the pole rather than a closed boundary.
    faces[-1] = 0.0
    return _flux_operator(faces, np.sin(theta), dtheta, outer="neumann")


# ─── 2D Polar ────────────────────────────────────────────────────────────────

def lap2d_polar(Nr, Ntheta, R, bc_r="dirichlet"):
    """
    2D Laplacian in polar coordinates.
    ∇² = (1/r)∂/∂r(r∂/∂r) + (1/r²)∂²/∂θ²

    Builds its own grid, because where the nodes sit is part of the operator
    (see the note above). Returns ``(Lap, r, theta)`` with *r* in the unit *R*
    was given in and *theta* in radians; pair it with :func:`polar_weights`.
    """
    r, dr = radial_nodes(R, Nr)
    theta, dtheta = azimuth_nodes(Ntheta)

    Lap = (kron(_radial_2d(r, dr, bc_r.lower()),
                identity(len(theta), format="csr")) +
           kron(diags(1.0 / r ** 2, 0, format="csr"),
                lap1d(len(theta), dtheta, "periodic")))
    return csr_matrix(Lap), r, theta


def polar_weights(r, Ntheta):
    """Volume element per node, ``r``, flattened C-order over ``(Nr, Ntheta)``."""
    return np.repeat(np.asarray(r, dtype=float), int(Ntheta))


# ─── 3D Cylindrical ──────────────────────────────────────────────────────────

def lap3d_cylindrical(Nr, Ntheta, Nz, r, dr, dtheta, dz, bc="dirichlet"):
    """
    3D Laplacian in cylindrical coordinates (r, θ, z).
    ∇² = (1/r)∂/∂r(r∂/∂r) + (1/r²)∂²/∂θ² + ∂²/∂z²

    *r* must be the cell-centred grid from :func:`radial_nodes` and *dtheta*
    must be ``2*pi/Ntheta``; both are checked, because the two ways of getting
    them wrong are silent. *bc* is the radial and axial boundary — one string
    for both, or ``(bc_r, bc_z)``. Theta is periodic by construction.
    """
    r = _check_cell_centred(r, dr, "radial")
    if abs(dtheta - 2.0 * np.pi / int(Ntheta)) > 1e-9 * dtheta:
        raise ValueError("dtheta must be 2*pi/Ntheta — theta wraps, and a "
                         "step that does not close the circle silently solves "
                         "a wedge instead of a cylinder")
    bc_r, bc_z = _parse_bc(bc, 2)

    Ir = identity(len(r), format="csr")
    Itheta = identity(int(Ntheta), format="csr")
    Iz = identity(int(Nz), format="csr")

    Lap = (kron(kron(_radial_2d(r, dr, bc_r), Itheta), Iz) +
           kron(kron(diags(1.0 / r ** 2, 0, format="csr"),
                     lap1d(int(Ntheta), dtheta, "periodic")), Iz) +
           kron(kron(Ir, Itheta), lap1d(int(Nz), dz, bc_z)))
    return csr_matrix(Lap)


def cylindrical_weights(r, Ntheta, Nz):
    """Volume element per node, ``r``, over ``(Nr, Ntheta, Nz)`` in C order."""
    return np.repeat(np.asarray(r, dtype=float), int(Ntheta) * int(Nz))


# ─── 3D Spherical ────────────────────────────────────────────────────────────

def lap3d_spherical(Nr, Ntheta, Nphi, r, dr, dtheta, dphi, bc="dirichlet"):
    """
    3D Laplacian in spherical coordinates (r, θ, φ).
    ∇² = (1/r²)∂/∂r(r²∂/∂r) + (1/r²sinθ)∂/∂θ(sinθ∂/∂θ) + (1/r²sin²θ)∂²/∂φ²

    *r* must come from :func:`radial_nodes`, *dtheta* from
    :func:`polar_angle_nodes` (``pi/Ntheta``) and *dphi* from
    :func:`azimuth_nodes` (``2*pi/Nphi``); all three are checked. *bc* is the
    radial boundary only — the theta and phi ends are the poles and the wrap,
    which the geometry fixes.
    """
    r = _check_cell_centred(r, dr, "radial")
    theta, dtheta_grid = polar_angle_nodes(Ntheta)
    if abs(dtheta - dtheta_grid) > 1e-9 * dtheta_grid:
        raise ValueError("dtheta must be pi/Ntheta — the theta grid is built "
                         "here and has to be the one the caller sampled the "
                         "potential on")
    if abs(dphi - 2.0 * np.pi / int(Nphi)) > 1e-9 * dphi:
        raise ValueError("dphi must be 2*pi/Nphi — phi wraps")

    Itheta = identity(len(theta), format="csr")
    Iphi = identity(int(Nphi), format="csr")
    r_inv2 = diags(1.0 / r ** 2, 0, format="csr")
    sin_inv2 = diags(1.0 / np.sin(theta) ** 2, 0, format="csr")

    Lap = (kron(kron(_radial_3d(r, dr, _parse_bc(bc, 1)[0]), Itheta), Iphi) +
           kron(kron(r_inv2, _polar_angle(theta, dtheta)), Iphi) +
           kron(r_inv2, kron(sin_inv2, lap1d(int(Nphi), dphi, "periodic"))))
    return csr_matrix(Lap)


def spherical_weights(r, theta, Nphi):
    """Volume element per node, ``r² sin(theta)``, over ``(Nr, Ntheta, Nphi)``."""
    r = np.asarray(r, dtype=float)
    theta = np.asarray(theta, dtype=float)
    return (np.repeat(r ** 2, len(theta) * int(Nphi)) *
            np.tile(np.repeat(np.sin(theta), int(Nphi)), len(r)))
