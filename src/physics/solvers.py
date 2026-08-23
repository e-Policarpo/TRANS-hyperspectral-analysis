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
from src.physics.laplacian import lap1d, lap2d_cartesian, lap3d_cartesian
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


def solve_well_1d(L_nm: float, N: int = 800, n_states: int = 8,
                  meff: float = 0.067, features: Optional[list] = None,
                  V_background_eV: float = 0.0,
                  bc: str = "dirichlet") -> dict:
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
                                         float(V_background_eV))

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
    # Just below the potential floor: the states wanted are the lowest ones.
    floor = float(flat.min())
    sigma = floor - (0.01 * e if floor == 0 else 0.1 * abs(floor))
    E, psi = eigsh(H, k=k, sigma=sigma, which="LM")
    order = np.argsort(E)
    return E[order], psi[:, order]


def solve_well_2d(Lx_nm: float, Ly_nm: float, Nx: int = 80, Ny: int = 80,
                  n_states: int = 6, meff: float = 0.067,
                  features: Optional[list] = None,
                  V_background_eV: float = 0.0,
                  bc=("dirichlet", "dirichlet")) -> dict:
    """Bound states of a 2-D box, with whatever features are inside it.

    Returns ``{'E_eV', 'psi', 'V_eV', 'x_nm', 'y_nm', 'shape'}``. ``psi``
    keeps the flat eigenvector layout the solver produced; ``shape`` is what
    to reshape a column to (``(Nx, Ny)``, C order), which is how the
    potential is already shaped.

    The cost is the grid squared: 80x80 is 6400 unknowns and quick, 300x300
    is 90 000 and not.
    """
    bcx, bcy = (bc, bc) if isinstance(bc, str) else (bc[0], bc[1])
    x_nm, dx = grid_axis(Lx_nm, Nx, bcx)
    y_nm, dy = grid_axis(Ly_nm, Ny, bcy)

    V, _ = build_potential_from_features(features or [], (x_nm, y_nm),
                                         float(V_background_eV))
    laplacian = lap2d_cartesian(len(x_nm), len(y_nm), dx, dy, bc=(bcx, bcy))
    E, psi = _solve_on_grid(V, laplacian, meff, n_states)

    logger.debug("2D well: %.4g x %.4g nm, %dx%d, %d state(s)",
                 Lx_nm, Ly_nm, len(x_nm), len(y_nm), len(E))
    return {'E_eV': E / e, 'psi': psi, 'V_eV': V / e, 'x_nm': x_nm,
            'y_nm': y_nm, 'shape': (len(x_nm), len(y_nm))}


def solve_well_3d(Lx_nm: float, Ly_nm: float, Lz_nm: float,
                  Nx: int = 24, Ny: int = 24, Nz: int = 24,
                  n_states: int = 6, meff: float = 0.067,
                  features: Optional[list] = None,
                  V_background_eV: float = 0.0,
                  bc=("dirichlet", "dirichlet", "dirichlet")) -> dict:
    """Bound states of a 3-D box, with whatever features are inside it.

    Same shape of answer as :func:`solve_well_2d`, one axis larger. The cost
    is the grid **cubed**: 24³ is 13 824 unknowns and seconds; 60³ is 216 000
    and minutes. That is why the defaults here are so much coarser than the
    2D ones, and why the caller is told the count before it runs.
    """
    if isinstance(bc, str):
        bcx = bcy = bcz = bc
    else:
        bcx, bcy, bcz = bc[0], bc[1], bc[2]
    x_nm, dx = grid_axis(Lx_nm, Nx, bcx)
    y_nm, dy = grid_axis(Ly_nm, Ny, bcy)
    z_nm, dz = grid_axis(Lz_nm, Nz, bcz)

    V, _ = build_potential_from_features(features or [], (x_nm, y_nm, z_nm),
                                         float(V_background_eV))
    laplacian = lap3d_cartesian(len(x_nm), len(y_nm), len(z_nm), dx, dy, dz,
                                bc=(bcx, bcy, bcz))
    E, psi = _solve_on_grid(V, laplacian, meff, n_states)

    logger.debug("3D well: %.4g x %.4g x %.4g nm, %dx%dx%d, %d state(s)",
                 Lx_nm, Ly_nm, Lz_nm, len(x_nm), len(y_nm), len(z_nm), len(E))
    return {'E_eV': E / e, 'psi': psi, 'V_eV': V / e, 'x_nm': x_nm,
            'y_nm': y_nm, 'z_nm': z_nm,
            'shape': (len(x_nm), len(y_nm), len(z_nm))}


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
