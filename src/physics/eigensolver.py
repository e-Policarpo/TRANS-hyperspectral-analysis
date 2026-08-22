"""Eigenvalue solver wrapper and degeneracy grouping."""

import numpy as np
from scipy.sparse.linalg import eigsh
from scipy.constants import e


def solve_eigenstates(H, k, use_shift_invert=False, sigma=None):
    """
    Solve for k smallest eigenvalues/eigenvectors of sparse Hamiltonian H.
    Returns (E, psi) sorted by ascending energy.

    If use_shift_invert=True and sigma is None, sigma is auto-computed
    from the diagonal minimum.
    """
    k = min(k, H.shape[0] - 2)

    if use_shift_invert:
        if sigma is None:
            diag = H.diagonal()
            sigma = diag.min() - 0.1 * abs(diag.min()) if diag.min() != 0 else -0.1
        E, psi = eigsh(H, k=k, sigma=sigma, which="LM")
    else:
        E, psi = eigsh(H, k=k, which="SA")

    idx = np.argsort(E)
    return E[idx], psi[:, idx]


def group_degenerate(E_joules, tolerance=1e-4):
    """
    Group nearly degenerate energy levels.
    Returns list of (energy_eV, [state_indices]).
    """
    E_eV = E_joules / e
    groups = []
    used = set()

    for i, Ei in enumerate(E_eV):
        if i in used:
            continue
        group_indices = [i]
        used.add(i)
        for j in range(i + 1, len(E_eV)):
            if j not in used and abs(E_eV[j] - Ei) < tolerance:
                group_indices.append(j)
                used.add(j)
        groups.append((Ei, group_indices))

    return groups
