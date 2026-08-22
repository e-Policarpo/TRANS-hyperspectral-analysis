"""
Tunnelling analysis: WKB rates, overlap matrices, and state assignment.
Supports 1D, 2D and 3D. Every function is standalone (no class state).
"""

import numpy as np
from scipy.constants import hbar, m_e, e


def compute_overlap_matrix(psi):
    """Overlap matrix |<psi_i|psi_j>| over every pair of states."""
    n = psi.shape[1]
    S = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            S[i, j] = np.abs(np.vdot(psi[:, i], psi[:, j]))
    return S


# ── Potential interpolation (1D / 2D / 3D) ──────────────────────────────────

def _interp_V(V, pos_nm, grid_nm):
    """Generic nearest-neighbour interpolation (N-D).

    V : ndarray (N-dimensional)
    pos_nm : array-like — position in nm, one entry per dimension
    grid_nm : tuple of 1-D arrays in nm, one per dimension
    """
    idx = []
    for p, g in zip(pos_nm, grid_nm):
        i = int(np.searchsorted(g, p))
        i = max(0, min(i, len(g) - 1))
        idx.append(i)
    return V[tuple(idx)]


# ── State → feature assignment ──────────────────────────────────────────────

def assign_states_to_features(psi, V_shape, features, grid_nm):
    """Identify which feature each eigenstate is localised in.

    Parameters
    ----------
    psi : ndarray (N_total, n_states)
    V_shape : tuple — shape of the potential grid
    features : list of Feature objects (with ``.contains()``)
    grid_nm : tuple of 1-D arrays in nm (one per dimension)

    Returns
    -------
    assignments : list of int (-1 where the state is not localised)
    """
    ndim = len(grid_nm)
    meshes = np.meshgrid(*grid_nm, indexing='ij')

    assignments = []
    for s in range(psi.shape[1]):
        psi_s = psi[:, s].reshape(V_shape, order='C')
        dens = np.abs(psi_s) ** 2
        max_idx = np.unravel_index(np.argmax(dens), V_shape)

        # Position of the maximum, in nm
        pos = np.array([grid_nm[d][max_idx[d]] for d in range(ndim)])

        feat_id = -1
        for j, feat in enumerate(features):
            # Build the point to test
            if ndim == 1:
                inside = feat.contains(np.array([pos[0]]))[0]
            elif ndim == 2:
                inside = feat.contains(np.array([[pos[0]]]),
                                        np.array([[pos[1]]]))[0, 0]
            else:
                inside = feat.contains(np.array([[[pos[0]]]]),
                                        np.array([[[pos[1]]]]),
                                        np.array([[[pos[2]]]]))[0, 0, 0]
            if inside:
                feat_id = j
                break
        assignments.append(feat_id)

    return assignments


# ── Generic WKB rate ────────────────────────────────────────────────────────

def wkb_rate(feat_i, feat_j, E_avg, V, grid_nm, E_array, n_samples=200):
    """WKB tunnelling rate along the line joining two features' centres.

    Gamma ~ omega_0 * exp(-2 * integral sqrt(2m(V-E)/hbar^2) dl)

    Works in any dimensionality (1D, 2D, 3D).
    """
    ci = feat_i.center_nm()
    cj = feat_j.center_nm()
    diff = (cj - ci) * 1e-9          # in metres
    dist = np.linalg.norm(diff)
    if dist < 1e-15:
        return 0.0
    direction = diff / dist

    s = np.linspace(0, dist, n_samples)
    ds = s[1] - s[0]

    m_avg = np.mean([feat_i.meff, feat_j.meff]) * m_e

    integral = 0.0
    for si in s[:-1]:
        pos_m = ci * 1e-9 + si * direction
        pos_nm = pos_m * 1e9
        V_val = _interp_V(V, pos_nm, grid_nm)
        if V_val > E_avg:
            integral += np.sqrt(2 * m_avg * (V_val - E_avg)) / hbar * ds

    omega_0 = abs(E_array[1] - E_array[0]) / hbar if len(E_array) > 1 else 1e12
    return omega_0 * np.exp(-2 * integral)


# ── Unified interface ───────────────────────────────────────────────────────

def compute_tunneling_analysis(psi, E_array, V, features, grid_nm):
    """Full tunnelling analysis, in any dimensionality.

    Returns
    -------
    tunneling_rates : dict {(i, j): rate_Hz}
    overlap_matrix : ndarray (n_states, n_states)
    assignments : list of int
    """
    V_shape = V.shape
    assignments = assign_states_to_features(psi, V_shape, features, grid_nm)
    overlap = compute_overlap_matrix(psi)

    n_states = psi.shape[1]
    rates = {}
    for i in range(n_states):
        fi = assignments[i]
        if fi == -1:
            continue
        for j in range(i + 1, n_states):
            fj = assignments[j]
            if fj == -1 or fj == fi:
                continue
            E_avg = (E_array[i] + E_array[j]) / 2
            rate = wkb_rate(features[fi], features[fj], E_avg,
                            V, grid_nm, E_array)
            rates[(i, j)] = rate

    return rates, overlap, assignments
