"""
The direct solvers: a geometry in, its levels out.

The inverse of the designer, and its companion. The designer answers "which
well would produce these energies?" with candidates it found analytically;
this answers "what does *this* well actually give?" numerically, on a grid.
Running a candidate through here is how you tell a real solution from an
alias that only matched the arithmetic.

Assembly only. The potential comes from :mod:`~src.physics.potentials` and
:mod:`~src.physics.features`, the operator from
:mod:`~src.physics.laplacian`, the eigenvalues from
:mod:`~src.physics.eigensolver`, and the 0D models from
:mod:`~src.physics.quantum_dot` — what was missing was the piece that puts
them together for one well, which used to live inside a Tk tab.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
from scipy.constants import e, hbar, m_e
from scipy.sparse import diags
from scipy.sparse.linalg import eigsh

from src.physics.features import SegmentFeature1D, build_potential_from_features
from src.physics.laplacian import (azimuth_nodes, cylindrical_weights, lap1d,
                                   lap2d_cartesian, lap2d_polar,
                                   lap3d_cartesian, lap3d_cylindrical,
                                   lap3d_spherical, polar_angle_nodes,
                                   polar_weights, radial_nodes,
                                   spherical_weights)
from src.physics.potentials import (build_potential_2d_polar,
                                    build_potential_3d_cylindrical,
                                    build_potential_3d_spherical)
from src.physics.quantum_dot import (DOT_DISC, DOT_PARABOLIC, DOT_SPHERICAL,
                                     Level, disc_dot, parabolic_dot,
                                     spherical_dot)
from src.physics.solution_spec import (MODEL_1D, MODEL_DOT_DISC,
                                       MODEL_DOT_PARABOLIC,
                                       MODEL_DOT_SPHERICAL, SolutionSpec)

logger = logging.getLogger(__name__)

#: Boundary conditions the 1D solver accepts, in the engine's own spelling.
BOUNDARY_CONDITIONS = ("dirichlet", "neumann", "periodic")

#: Which model each solver can simulate. A candidate the designer found in a
#: geometry nothing here solves is not a failure — it is a 2D/3D well, and
#: saying so beats simulating the wrong thing.
WELL_MODELS = (MODEL_1D,)
DOT_MODELS = (MODEL_DOT_SPHERICAL, MODEL_DOT_DISC, MODEL_DOT_PARABOLIC)

#: Never solve for more than this many states. The cost is superlinear and
#: nobody reads the four-hundredth level.
MAX_STATES = 40

#: Coordinate systems each solver can work in. Cartesian is the default
#: everywhere and is what every existing caller gets; the curved ones exist so
#: that a round shape can be solved on a grid that is round too, instead of on
#: a staircase of square cells. They are not a speed-up — a disc on a polar
#: grid is the same size of matrix — they are an accuracy one, and they are the
#: only way to put an *arbitrary* potential into a curved geometry, which the
#: closed-form levels in :mod:`~src.physics.analytical` cannot do.
COORDS_2D = ("cartesian", "polar")
COORDS_3D = ("cartesian", "cylindrical", "spherical")

#: Spellings the rest of the app already uses for the same thing — the
#: workflow engine offers "circular" and "disc", the designer says "sphere".
_COORD_ALIASES = {"circular": "polar", "disc": "polar", "disk": "polar",
                  "cylinder": "cylindrical", "sphere": "spherical",
                  "ball": "spherical"}


def _canonical_coords(coords, allowed):
    """One spelling of a coordinate system, or a refusal naming the choices."""
    name = str(coords or "cartesian").strip().lower()
    name = _COORD_ALIASES.get(name, name)
    if name not in allowed:
        raise ValueError(f"unknown coordinate system {coords!r}; expected one "
                         f"of {allowed}")
    return name


def solve_well_1d(L_nm: float, N: int = 800, n_states: int = 8,
                  meff: float = 0.067, features: Optional[list] = None,
                  V_background_eV: float = 0.0,
                  bc: str = "dirichlet", subsample: int = 1) -> dict:
    """Bound states of a 1-D box of width ``L_nm``, on a finite-difference grid.

    ``features`` are the wells and barriers inside the box (see
    :mod:`~src.physics.features`); with none, the box itself is the well and
    the answer is the textbook ladder.

    Returns ``{'E_eV', 'psi', 'V_eV', 'x_nm'}`` — the energies ascending, the
    normalised wavefunctions as columns, the potential the states live in,
    and the grid, all in eV and nm.
    """
    if L_nm <= 0:
        raise ValueError("the box width must be positive")
    N = max(16, int(N))
    n_states = max(1, min(int(n_states), MAX_STATES))
    bc = str(bc).lower()
    if bc not in BOUNDARY_CONDITIONS:
        raise ValueError(f"unknown boundary condition {bc!r}; "
                         f"expected one of {BOUNDARY_CONDITIONS}")

    L = L_nm * 1e-9
    if bc == "dirichlet":
        # The walls sit just outside the grid, so the first and last samples
        # are a step inside the box rather than on it.
        dx = L / (N + 1)
        x_nm = np.linspace(dx * 1e9, L_nm - dx * 1e9, N)
    else:
        dx = L / N
        x_nm = np.linspace(dx * 1e9 / 2, L_nm - dx * 1e9 / 2, N)

    V, _ = build_potential_from_features(features or [], (x_nm,),
                                         float(V_background_eV), subsample)

    laplacian = lap1d(N, dx, bc)
    mass = float(meff) * m_e
    H = -(hbar ** 2) / (2 * mass) * laplacian + diags(V, 0, format="csr")

    k = min(n_states, H.shape[0] - 2)
    # Shift-invert just below the potential floor: the states wanted are the
    # lowest ones, and asking for them by magnitude finds the top of the
    # spectrum instead.
    sigma = float(V.min()) - 0.01 * e
    E, psi = eigsh(H, k=k, sigma=sigma, which="LM")
    order = np.argsort(E)
    E, psi = E[order], psi[:, order]

    logger.debug("1D well: L=%.4g nm, N=%d, %d state(s), m*=%g",
                 L_nm, N, len(E), meff)
    return {'E_eV': (E / e), 'psi': psi, 'V_eV': (V / e), 'x_nm': x_nm}


def grid_axis(L_nm: float, N: int, bc: str = "dirichlet"):
    """``(x_nm, spacing_m)`` for one axis of a box of length ``L_nm``.

    Where the samples sit depends on the boundary: with Dirichlet the walls
    are just outside the grid, so the first and last samples are a step
    inside the box; otherwise the grid starts at the edge. Getting this wrong
    shifts every level by a fraction of a step, which looks like a physical
    result rather than an indexing choice.
    """
    if L_nm <= 0:
        raise ValueError("the box length must be positive")
    N = max(4, int(N))
    L = L_nm * 1e-9
    if str(bc).lower() == "dirichlet":
        spacing = L / (N + 1)
        axis = np.linspace(spacing * 1e9, L_nm - spacing * 1e9, N)
    else:
        spacing = L / N
        axis = np.linspace(0.0, L_nm - spacing * 1e9, N)
    return axis, spacing


def _solve_on_grid(potential_J, laplacian, meff: float, n_states: int):
    """Lowest ``n_states`` eigenpairs of -hbar²/2m ∇² + V, on any grid.

    Shared by 2D and 3D because the only difference between them is which
    Laplacian is handed in — the Hamiltonian, the shift and the ordering are
    the same problem at a different size.
    """
    flat = np.asarray(potential_J).flatten(order="C")
    H = (-(hbar ** 2) / (2.0 * float(meff) * m_e)) * laplacian + \
        diags(flat, 0, format="csr")

    k = max(1, min(int(n_states), MAX_STATES, H.shape[0] - 2))
    if k < 1:
        raise ValueError("the grid is too small to hold a state")
    E, psi = eigsh(H, k=k, sigma=_shift_below(flat), which="LM")
    order = np.argsort(E)
    return E[order], psi[:, order]


def _shift_below(flat):
    """Where to aim shift-invert: just below the potential floor.

    The states wanted are the lowest ones, and asking for them by magnitude
    finds the top of the spectrum instead.
    """
    floor = float(np.min(flat))
    return floor - (0.01 * e if floor == 0 else 0.1 * abs(floor))


def _solve_on_curved_grid(potential_J, laplacian, weights, meff, n_states):
    """:func:`_solve_on_grid` where the volume element is not 1.

    A curved Laplacian is not a symmetric matrix. It is self-adjoint under the
    metric weight — r on a disc, r² sin(theta) in a sphere — and handing the
    bare matrix to ``eigsh``, which assumes symmetry, gives answers that wander
    with the grid instead of converging: a 10 nm disc came back at 0.0320,
    0.0336 and 0.0298 eV on three refinements of the same problem, against an
    exact 0.03289.

    The cure is a similarity transform. S = W^½ H W^-½ is symmetric to machine
    precision (measured: 1e-17 relative), has exactly the same eigenvalues, and
    its eigenvectors are u = W^½ psi — so ``eigsh`` is honest again and the
    same disc lands on 0.03289. Dividing u back by sqrt(w) also leaves psi
    normalised in the right measure, since sum(w |psi|²) == sum(|u|²) == 1.
    """
    flat = np.asarray(potential_J).flatten(order="C")
    weights = np.asarray(weights, dtype=float)
    if weights.shape != flat.shape:
        raise ValueError(f"the metric weight has {weights.size} entries and "
                         f"the grid {flat.size}")

    H = (-(hbar ** 2) / (2.0 * float(meff) * m_e)) * laplacian + \
        diags(flat, 0, format="csr")
    root = np.sqrt(weights)
    S = (diags(root, 0, format="csr") @ H @
         diags(1.0 / root, 0, format="csr")).tocsc()

    k = max(1, min(int(n_states), MAX_STATES, S.shape[0] - 2))
    if k < 1:
        raise ValueError("the grid is too small to hold a state")
    E, u = eigsh(S, k=k, sigma=_shift_below(flat), which="LM")
    order = np.argsort(E)
    return E[order], (u[:, order] / root[:, None])


def _features_on_points(features, meshes, V_background_eV, wells_potential=None):
    """Sample Cartesian features at the points of a curved grid.

    :func:`~src.physics.features.build_potential_from_features` cannot be used
    here. It takes 1-D axes and its ``subsample`` fraction measures how much of
    an axis-aligned *cell* a feature covers — and a polar cell is a wedge that
    grows with r, not a square. So this asks ``contains`` at the node and
    nowhere else, which is exactly what ``subsample=1`` does on the Cartesian
    path. The staircase that costs is the price of solving in the coordinate
    system the shape actually lives in; for a shape aligned with the grid — the
    disc in a polar solve, the shell in a spherical one — there is no staircase
    left to pay for.
    """
    V = (np.full(meshes[0].shape, float(V_background_eV) * e)
         if wells_potential is None else np.asarray(wells_potential).copy())
    for feat in features or ():
        depth = (feat.potential_at(*meshes) * e
                 if hasattr(feat, 'potential_at') else feat.V0 * e)
        V = np.where(feat.contains(*meshes), depth, V)
    return V


def solve_well_2d(Lx_nm: float, Ly_nm: float, Nx: int = 80, Ny: int = 80,
                  n_states: int = 6, meff: float = 0.067,
                  features: Optional[list] = None,
                  V_background_eV: float = 0.0,
                  bc=("dirichlet", "dirichlet"),
                  subsample: int = 1, coords: str = "cartesian",
                  wells: Optional[list] = None) -> dict:
    """Bound states of a 2-D box, with whatever features are inside it.

    Returns ``{'E_eV', 'psi', 'V_eV', 'x_nm', 'y_nm', 'shape'}``. ``psi``
    keeps the flat eigenvector layout the solver produced; ``shape`` is what
    to reshape a column to (``(Nx, Ny)``, C order), which is how the
    potential is already shaped.

    The cost is the grid squared: 80x80 is 6400 unknowns and quick, 300x300
    is 90 000 and not.

    ``coords="polar"`` (also spelled "circular" or "disc") solves the disc
    **inscribed in the box** instead: radius ``min(Lx, Ly)/2``, centred where
    the box's centre is, with ``Nx`` radial nodes and ``Ny`` angular ones. The
    features keep the same nm frame either way, so the same feature list means
    the same shape in both — what changes is the grid it is sampled on, and a
    round wall stops being a staircase. The answer comes back keyed on ``r_nm``
    and ``theta_rad``; see :func:`solve_well_2d_polar`.

    ``bc`` does not cross into the polar branch: it names the x and y walls of
    a box, and a disc has one wall. Call :func:`solve_well_2d_polar` directly
    for anything other than a Dirichlet rim.
    """
    if _canonical_coords(coords, COORDS_2D) == "polar":
        return solve_well_2d_polar(
            min(float(Lx_nm), float(Ly_nm)) / 2.0, Nr=Nx, Ntheta=Ny,
            n_states=n_states, meff=meff, features=features, wells=wells,
            V_background_eV=V_background_eV,
            centre_nm=(float(Lx_nm) / 2.0, float(Ly_nm) / 2.0))

    bcx, bcy = (bc, bc) if isinstance(bc, str) else (bc[0], bc[1])
    x_nm, dx = grid_axis(Lx_nm, Nx, bcx)
    y_nm, dy = grid_axis(Ly_nm, Ny, bcy)

    V, _ = build_potential_from_features(features or [], (x_nm, y_nm),
                                         float(V_background_eV), subsample)
    laplacian = lap2d_cartesian(len(x_nm), len(y_nm), dx, dy, bc=(bcx, bcy))
    E, psi = _solve_on_grid(V, laplacian, meff, n_states)

    logger.debug("2D well: %.4g x %.4g nm, %dx%d, %d state(s)",
                 Lx_nm, Ly_nm, len(x_nm), len(y_nm), len(E))
    return {'E_eV': E / e, 'psi': psi, 'V_eV': V / e, 'x_nm': x_nm,
            'y_nm': y_nm, 'shape': (len(x_nm), len(y_nm)),
            'coords': "cartesian"}


def solve_well_3d(Lx_nm: float, Ly_nm: float, Lz_nm: float,
                  Nx: int = 24, Ny: int = 24, Nz: int = 24,
                  n_states: int = 6, meff: float = 0.067,
                  features: Optional[list] = None,
                  V_background_eV: float = 0.0,
                  bc=("dirichlet", "dirichlet", "dirichlet"),
                  subsample: int = 1, coords: str = "cartesian",
                  wells: Optional[list] = None) -> dict:
    """Bound states of a 3-D box, with whatever features are inside it.

    Same shape of answer as :func:`solve_well_2d`, one axis larger. The cost
    is the grid **cubed**: 24³ is 13 824 unknowns and seconds; 60³ is 216 000
    and minutes. That is why the defaults here are so much coarser than the
    2D ones, and why the caller is told the count before it runs.

    ``coords`` picks the grid the box is replaced by, on the same inscribed
    rule as :func:`solve_well_2d`: ``"cylindrical"`` is the cylinder of radius
    ``min(Lx, Ly)/2`` and height ``Lz``, with ``(Nx, Ny, Nz)`` read as
    ``(Nr, Ntheta, Nz)``; ``"spherical"`` is the ball of radius
    ``min(Lx, Ly, Lz)/2``, with ``(Nx, Ny, Nz)`` read as ``(Nr, Ntheta,
    Nphi)``. Both centre on the box's centre so features keep their frame.
    ``bc`` stays behind with the box, as in :func:`solve_well_2d`; the curved
    solvers take theirs as ``bc_r``/``bc_z``.
    """
    coords = _canonical_coords(coords, COORDS_3D)
    if coords != "cartesian":
        centre = (float(Lx_nm) / 2.0, float(Ly_nm) / 2.0, float(Lz_nm) / 2.0)
        shared = dict(n_states=n_states, meff=meff, features=features,
                      wells=wells, V_background_eV=V_background_eV,
                      centre_nm=centre)
        if coords == "cylindrical":
            return solve_well_3d_cylindrical(
                min(float(Lx_nm), float(Ly_nm)) / 2.0, float(Lz_nm),
                Nr=Nx, Ntheta=Ny, Nz=Nz, **shared)
        return solve_well_3d_spherical(
            min(float(Lx_nm), float(Ly_nm), float(Lz_nm)) / 2.0,
            Nr=Nx, Ntheta=Ny, Nphi=Nz, **shared)

    if isinstance(bc, str):
        bcx = bcy = bcz = bc
    else:
        bcx, bcy, bcz = bc[0], bc[1], bc[2]
    x_nm, dx = grid_axis(Lx_nm, Nx, bcx)
    y_nm, dy = grid_axis(Ly_nm, Ny, bcy)
    z_nm, dz = grid_axis(Lz_nm, Nz, bcz)

    V, _ = build_potential_from_features(features or [], (x_nm, y_nm, z_nm),
                                         float(V_background_eV), subsample)
    laplacian = lap3d_cartesian(len(x_nm), len(y_nm), len(z_nm), dx, dy, dz,
                                bc=(bcx, bcy, bcz))
    E, psi = _solve_on_grid(V, laplacian, meff, n_states)

    logger.debug("3D well: %.4g x %.4g x %.4g nm, %dx%dx%d, %d state(s)",
                 Lx_nm, Ly_nm, Lz_nm, len(x_nm), len(y_nm), len(z_nm), len(E))
    return {'E_eV': E / e, 'psi': psi, 'V_eV': V / e, 'x_nm': x_nm,
            'y_nm': y_nm, 'z_nm': z_nm,
            'shape': (len(x_nm), len(y_nm), len(z_nm)),
            'coords': "cartesian"}


# ── curved coordinates ──────────────────────────────────────────────────────
#
# Same three moves as the Cartesian solvers — lay out a grid, sample the
# potential on it, diagonalise — with two differences that are easy to get
# wrong and so are done once, here, rather than at each call site. The grids
# come from the node helpers in :mod:`~src.physics.laplacian`, because the
# operators are only regular at r = 0 on the grid those produce; and the
# eigenproblem goes through :func:`_solve_on_curved_grid`, because the
# operators are self-adjoint under the metric rather than symmetric.
#
# Features are Cartesian objects and stay that way: they are sampled at the
# Cartesian positions of the curved nodes, so the same feature list describes
# the same shape whichever grid it is solved on. ``wells`` is the other door —
# the native (r, theta, ...) wedge tuples that
# :mod:`~src.physics.potentials` builds — and the two compose, wells first.

def solve_well_2d_polar(R_nm: float, Nr: int = 120, Ntheta: int = 32,
                        n_states: int = 6, meff: float = 0.067,
                        features: Optional[list] = None,
                        wells: Optional[list] = None,
                        V_background_eV: float = 0.0,
                        centre_nm=(0.0, 0.0),
                        bc_r: str = "dirichlet") -> dict:
    """Bound states of a disc of radius ``R_nm``, on a polar grid.

    ``centre_nm`` is where r = 0 sits in the features' own nm frame, so a
    feature written for the Cartesian solver means the same shape here.

    Returns ``{'E_eV', 'psi', 'V_eV', 'r_nm', 'theta_rad', 'X_nm', 'Y_nm',
    'shape', 'weights', 'coords'}``. ``X_nm``/``Y_nm`` are the Cartesian
    positions of the nodes — 2-D, because a polar grid is not separable in x
    and y — and ``weights`` is the volume element each node carries, which is
    what an integral over the disc has to be summed against.
    """
    if R_nm <= 0:
        raise ValueError("the disc radius must be positive")
    # lap2d_polar lays out its own grid and hands it back, so there is one
    # grid rather than two that have to agree.
    laplacian, r_m, theta = lap2d_polar(Nr, Ntheta, float(R_nm) * 1e-9, bc_r)
    r_nm = r_m * 1e9

    R_grid, T_grid = np.meshgrid(r_nm, theta, indexing="ij")
    X = centre_nm[0] + R_grid * np.cos(T_grid)
    Y = centre_nm[1] + R_grid * np.sin(T_grid)

    base = None
    if wells:
        base, _, _ = build_potential_2d_polar(wells, r_nm, theta, len(r_nm),
                                              len(theta), V_background_eV)
    V = _features_on_points(features, (X, Y), V_background_eV, base)

    weights = polar_weights(r_nm, len(theta))
    E, psi = _solve_on_curved_grid(V, laplacian, weights, meff, n_states)

    logger.debug("2D disc: R=%.4g nm, %dx%d polar, %d state(s)",
                 R_nm, len(r_nm), len(theta), len(E))
    return {'E_eV': E / e, 'psi': psi, 'V_eV': V / e, 'r_nm': r_nm,
            'theta_rad': theta, 'X_nm': X, 'Y_nm': Y,
            'shape': (len(r_nm), len(theta)), 'weights': weights,
            'coords': "polar"}


def solve_well_3d_cylindrical(R_nm: float, H_nm: float, Nr: int = 24,
                              Ntheta: int = 16, Nz: int = 16,
                              n_states: int = 6, meff: float = 0.067,
                              features: Optional[list] = None,
                              wells: Optional[list] = None,
                              V_background_eV: float = 0.0,
                              centre_nm=(0.0, 0.0, 0.0),
                              bc_r: str = "dirichlet",
                              bc_z: str = "dirichlet") -> dict:
    """Bound states of a cylinder of radius ``R_nm`` and height ``H_nm``.

    Same answer shape as :func:`solve_well_2d_polar` with a ``z_nm`` axis
    added; the grid is ``(Nr, Ntheta, Nz)`` in C order. z runs from ``-H/2`` to
    ``+H/2`` about ``centre_nm[2]``, which is the convention
    :func:`~src.physics.potentials.build_potential_3d_cylindrical` samples
    ``wells`` on.
    """
    if R_nm <= 0 or H_nm <= 0:
        raise ValueError("the cylinder's radius and height must be positive")
    R_m, H_m = float(R_nm) * 1e-9, float(H_nm) * 1e-9
    r_m, dr_m = radial_nodes(R_m, Nr)
    theta, dtheta = azimuth_nodes(Ntheta)
    # z is the one axis here whose layout the boundary still changes, and it
    # has to be laid out exactly as build_potential_3d_cylindrical lays it
    # out — with Dirichlet the walls sit a step outside the grid, otherwise
    # the samples are cell-centred. Hardcoding the Dirichlet step, as this did
    # until the two were compared, sampled ``wells`` on a grid the states were
    # never solved on the moment bc_z was anything else.
    Nz = max(2, int(Nz))
    if str(bc_z).lower() == "dirichlet":
        dz_m = H_m / (Nz + 1)
        z_m = np.linspace(-H_m / 2 + dz_m, H_m / 2 - dz_m, Nz)
    else:
        dz_m = H_m / Nz
        z_m = np.linspace(-H_m / 2 + dz_m / 2, H_m / 2 - dz_m / 2, Nz)

    laplacian = lap3d_cylindrical(len(r_m), len(theta), Nz, r_m, dr_m,
                                  dtheta, dz_m, bc=(bc_r, bc_z))

    r_nm, z_nm = r_m * 1e9, z_m * 1e9
    R_grid, T_grid, Z_grid = np.meshgrid(r_nm, theta, z_nm, indexing="ij")
    X = centre_nm[0] + R_grid * np.cos(T_grid)
    Y = centre_nm[1] + R_grid * np.sin(T_grid)
    Z = centre_nm[2] + Z_grid

    base = None
    if wells:
        base, _ = build_potential_3d_cylindrical(
            wells, R_m, H_m, len(r_m), Nz, len(theta), V_background_eV,
            bc_z)
    V = _features_on_points(features, (X, Y, Z), V_background_eV, base)

    weights = cylindrical_weights(r_nm, len(theta), Nz)
    E, psi = _solve_on_curved_grid(V, laplacian, weights, meff, n_states)

    logger.debug("3D cylinder: R=%.4g nm, H=%.4g nm, %dx%dx%d, %d state(s)",
                 R_nm, H_nm, len(r_nm), len(theta), Nz, len(E))
    return {'E_eV': E / e, 'psi': psi, 'V_eV': V / e, 'r_nm': r_nm,
            'theta_rad': theta, 'z_nm': z_nm, 'X_nm': X, 'Y_nm': Y,
            'Z_nm': Z, 'shape': (len(r_nm), len(theta), Nz),
            'weights': weights, 'coords': "cylindrical"}


def solve_well_3d_spherical(R_nm: float, Nr: int = 24, Ntheta: int = 16,
                            Nphi: int = 16, n_states: int = 6,
                            meff: float = 0.067,
                            features: Optional[list] = None,
                            wells: Optional[list] = None,
                            V_background_eV: float = 0.0,
                            centre_nm=(0.0, 0.0, 0.0),
                            bc_r: str = "dirichlet") -> dict:
    """Bound states of a ball of radius ``R_nm``, on a spherical grid.

    The grid is ``(Nr, Ntheta, Nphi)`` in C order, theta the polar angle from
    +z. Angular resolution is what limits the higher levels here: the l = 0
    and l = 1 states converge quickly, l = 2 needs the theta and phi counts
    raised rather than the radial one.
    """
    if R_nm <= 0:
        raise ValueError("the ball radius must be positive")
    R_m = float(R_nm) * 1e-9
    r_m, dr_m = radial_nodes(R_m, Nr)
    theta, dtheta = polar_angle_nodes(Ntheta)
    phi, dphi = azimuth_nodes(Nphi)

    laplacian = lap3d_spherical(len(r_m), len(theta), len(phi), r_m, dr_m,
                                dtheta, dphi, bc=bc_r)

    r_nm = r_m * 1e9
    R_grid, T_grid, P_grid = np.meshgrid(r_nm, theta, phi, indexing="ij")
    X = centre_nm[0] + R_grid * np.sin(T_grid) * np.cos(P_grid)
    Y = centre_nm[1] + R_grid * np.sin(T_grid) * np.sin(P_grid)
    Z = centre_nm[2] + R_grid * np.cos(T_grid)

    base = None
    if wells:
        base, _ = build_potential_3d_spherical(
            wells, R_m, len(r_m), len(theta), len(phi), V_background_eV)
    V = _features_on_points(features, (X, Y, Z), V_background_eV, base)

    weights = spherical_weights(r_nm, theta, len(phi))
    E, psi = _solve_on_curved_grid(V, laplacian, weights, meff, n_states)

    logger.debug("3D ball: R=%.4g nm, %dx%dx%d spherical, %d state(s)",
                 R_nm, len(r_nm), len(theta), len(phi), len(E))
    return {'E_eV': E / e, 'psi': psi, 'V_eV': V / e, 'r_nm': r_nm,
            'theta_rad': theta, 'phi_rad': phi, 'X_nm': X, 'Y_nm': Y,
            'Z_nm': Z, 'shape': (len(r_nm), len(theta), len(phi)),
            'weights': weights, 'coords': "spherical"}


def density(psi, shape, index: int = 0):
    """|psi|² of one state, reshaped onto the grid it was solved on."""
    column = np.asarray(psi)[:, int(index)]
    return (np.abs(column) ** 2).reshape(shape, order="C")


def solve_dot(model: str, dims_nm, meff: float = 0.067,
              V0_eV: Optional[float] = None, channels: int = 3,
              n_per_channel: int = 4, N: int = 800) -> List[Level]:
    """Bound levels of a quantum dot, by model.

    ``dims_nm`` follows the model: ``(R,)`` spherical, ``(R, Lz)`` disc,
    ``(hw_xy, hw_z)`` parabolic — that last one in **meV**, not nm.
    """
    dims = [float(d) for d in dims_nm]
    if model in (MODEL_DOT_SPHERICAL, DOT_SPHERICAL):
        return spherical_dot(dims[0], V0_eV=V0_eV or None, meff=meff,
                             l_max=int(channels),
                             n_per_channel=int(n_per_channel), N=int(N))
    if model in (MODEL_DOT_DISC, DOT_DISC):
        return disc_dot(dims[0], dims[1], V0_eV=V0_eV or None, meff=meff,
                        m_max=int(channels), n_per_channel=int(n_per_channel),
                        N=int(N))
    if model in (MODEL_DOT_PARABOLIC, DOT_PARABOLIC):
        return parabolic_dot(dims[0], dims[1], n_shells=max(3, int(channels) + 2))
    raise ValueError(f"unknown dot model: {model!r}; expected one of "
                     f"{DOT_MODELS}")


# ── from a designer candidate to something a solver can run ─────────────────

def states_needed(spec: SolutionSpec) -> int:
    """How many states to solve for, to check one candidate.

    At least as far as the quantum number the inverse search used: matching a
    target with n = 9 and then solving only six levels compares the target
    with the wrong one.
    """
    n_targets = max(1, len(spec.targets_eV))
    max_qn = int((spec.extras or {}).get("max_qn", 0) or 0)
    if max_qn == 0:
        return max(4, min(2 * n_targets, MAX_STATES))
    return max(4, min(MAX_STATES, max(2 * n_targets, max_qn + 2)))


def well_from_spec(spec: SolutionSpec) -> dict:
    """Turn a 1D candidate into arguments for :func:`solve_well_1d`.

    The well becomes a feature of width L: with a finite barrier the floor is
    -V0 inside it and 0 outside; with an infinite barrier the box walls do
    the confining and the interior is flat.

    The box is **larger than the well** when the barrier is finite, to leave
    room for the evanescent tail — putting the wall against the well would
    return the box's levels rather than the well's.
    """
    if spec.model not in WELL_MODELS:
        raise ValueError(f"{spec.model!r} is not a 1D well")

    L_well = float(spec.dims_nm[0])
    if spec.infinite_barrier:
        return {'L_nm': L_well, 'meff': spec.meff,
                'features': [SegmentFeature1D(0.0, L_well, 0.0, spec.meff)],
                'V_background_eV': 0.0, 'bc': "dirichlet",
                'n_states': states_needed(spec)}

    L_box = max(3.0 * L_well, L_well + 10.0)
    x0 = (L_box - L_well) / 2.0
    return {'L_nm': L_box, 'meff': spec.meff,
            'features': [SegmentFeature1D(x0, L_well, -abs(spec.V0_eV),
                                          spec.meff)],
            'V_background_eV': 0.0, 'bc': "dirichlet",
            'n_states': states_needed(spec)}


def dot_from_spec(spec: SolutionSpec) -> dict:
    """Turn a 0D candidate into arguments for :func:`solve_dot`."""
    if spec.model not in DOT_MODELS:
        raise ValueError(f"{spec.model!r} is not a quantum dot")
    return {'model': spec.model, 'dims_nm': list(spec.dims_nm),
            'meff': spec.meff, 'V0_eV': spec.V0_eV,
            'channels': max(3, min(8, states_needed(spec) // 3 + 2))}


def can_simulate(spec: SolutionSpec) -> str:
    """Which solver can run this candidate: ``"well"``, ``"dot"`` or ``""``.

    An empty answer is a real one: a 2D or 3D candidate is a geometry no
    solver here builds, and saying so beats simulating something else.
    """
    if spec.model in WELL_MODELS:
        return "well"
    if spec.model in DOT_MODELS:
        return "dot"
    return ""


def compare_with_targets(levels_eV, spec: SolutionSpec) -> dict:
    """How well the numerical levels reproduce the candidate's targets.

    The point of simulating a candidate at all. ``rrmse_pct`` is the same
    relative error the designer reports, so the two numbers are comparable:
    a candidate whose analytic fit was perfect and whose numerical error is
    large was an alias of the arithmetic, not a well.
    """
    targets = [float(t) for t in (spec.targets_eV or ())]
    levels = [float(E) for E in levels_eV]
    if not targets or not levels:
        return {'matched': [], 'errors_pct': [], 'rrmse_pct': float('nan'),
                'targets': targets, 'covered': False}

    matched, errors = [], []
    for target in targets:
        nearest = min(levels, key=lambda E: abs(E - target))
        matched.append(nearest)
        errors.append((nearest - target) / target * 100.0 if target else 0.0)

    rrmse = float(np.sqrt(np.mean(np.square(errors))))
    return {'matched': matched, 'errors_pct': errors, 'rrmse_pct': rrmse,
            'targets': targets,
            # False when the highest target sits above the last level solved:
            # the match is then against the wrong level, however small its
            # error looks.
            'covered': max(targets) <= max(levels)}
