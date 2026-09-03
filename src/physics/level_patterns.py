"""Dimensionless level-ratio fingerprints of confined geometries.

The energy of a hard-wall level carries three things a measurement cannot
separate: the size of the object, the effective mass of the carrier, and the
zero of the energy axis. The *ratios* E_n / E_1 carry none of them. Every
level of a box scales as ``hbar^2 / (2 m L^2)``, so that prefactor cancels
exactly in a ratio, and what is left is pure arithmetic — 1, 4, 9, 16 for a
line, 1, 2.5, 4, 5 for a square, 1, 2, 3, 11/3 for a cube. Two dots of the
same shape and different sizes, measured with different tips on different
materials, produce the same list.

Why that matters more than it looks: the ratios are built from feature
*positions*, and a symmetric broadening kernel preserves a centroid. Thermal
smearing at 94 K widens a peak by k_B*T ~ 8 meV without moving it, so the
fingerprint survives a warm measurement of a disordered sample, which almost
no other observable does. Peak *heights* do not survive nearly as well, which
is why :func:`expected_step_heights` is offered as a secondary check rather
than as the discriminator.

The patterns and the values they must reproduce (E2/E1):

===============  =======  ========================================
``box_1d``       4.000    a line, n^2
``box_2d_square``  2.500  a square, nx^2 + ny^2
``disc_2d``      2.538    a circle, squares of the zeros of J_m
``box_3d_cube``  2.000    a cube, nx^2 + ny^2 + nz^2
``sphere_3d``    2.046    a ball, squares of the zeros of j_l
===============  =======  ========================================

**This only works for fixed-aspect or isotropic shapes.** A rectangle with a
free aspect ratio has ``E(nx,ny) ~ (nx/a)^2 + (ny/b)^2``: the ratios then
depend on ``b/a``, a second free parameter, and with enough freedom such a
ladder can be fitted to almost any measured one. The signature stops
identifying anything. That is the whole reason only the square and the cube
are offered here, and why an anisotropic candidate belongs in the inverse
search of :mod:`src.physics.designer`, which fits dimensions explicitly,
rather than in a fingerprint lookup.

**Degeneracies are states, not entries.** :mod:`src.physics.analytical` lists
a disc's and a cylinder's ``m > 0`` levels once even though each is a +/-m
pair, and lists a box's degenerate permutations separately. Both conventions
are normalised here: ``ratios`` holds *distinct* energies and
``degeneracies`` counts the states sitting at each. Spin is not included —
it multiplies every level by two and so cancels in
:func:`expected_step_heights` anyway.

Everything is evaluated at unit size and unit effective mass, since those
cancel; the numbers below are therefore constants of the geometry, computed
once and memoised. The module is free of Qt, of file I/O and of any TRANS
data model.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Tuple

from src.physics.analytical import (
    box_energies_1d_eV,
    box_energies_2d_eV,
    box_energies_3d_eV,
    disk_energies,
)
from src.physics.quantum_dot import spherical_dot

logger = logging.getLogger(__name__)

__all__ = [
    "LevelPattern",
    "PATTERN_NAMES",
    "PATTERN_LABELS",
    "MAX_LEVELS",
    "DEFAULT_LEVELS",
    "pattern",
    "all_patterns",
    "expected_step_heights",
]


#: The geometries whose fingerprint is size-independent. Ordered by the
#: number of confined directions, then by symmetry, because that is the order
#: a UI list wants them in.
PATTERN_NAMES = (
    "box_1d",
    "box_2d_square",
    "disc_2d",
    "box_3d_cube",
    "sphere_3d",
)

#: Human-readable names for the UI. Kept beside the identifiers rather than
#: in a QML file so that a console session shows the same words as the app.
PATTERN_LABELS = {
    "box_1d": "1D box (line)",
    "box_2d_square": "2D square box",
    "disc_2d": "2D disc",
    "box_3d_cube": "3D cubic box",
    "sphere_3d": "3D sphere",
}

#: Confined directions per pattern -- the quantity a fingerprint match is
#: really reporting, since it is dimensionality, not shape, that the ratios
#: separate most cleanly (4.00 against 2.50 against 2.00).
CONFINED_DIMS = {
    "box_1d": 1,
    "box_2d_square": 2,
    "disc_2d": 2,
    "box_3d_cube": 3,
    "sphere_3d": 3,
}

#: Levels returned by default. Eight is already far more than a real dI/dV
#: resolves -- past the fourth or fifth state the band edge and the
#: level spacing have usually run into each other -- but a few spare levels
#: cost nothing and let a caller trim.
DEFAULT_LEVELS = 8

#: Hard ceiling on ``n_levels``. It is set by :func:`disk_energies`, whose
#: Bessel grid stops at ``m = 7``: from the 18th distinct level onward its
#: ordering is wrong because the first ``m = 8`` state is missing. Verified
#: against a brute-force ordering over ``m <= 19``; 16 leaves a margin.
MAX_LEVELS = 16

#: Relative tolerance for calling two levels degenerate. The energies here
#: are exact arithmetic on integers or on Bessel zeros, so true partners
#: agree to machine precision and genuine near-misses are percent-level
#: apart; anything between the two would be a bug, not a judgement call.
GROUP_RTOL = 1e-9


# ---------------------------------------------------------------------------
# The pattern record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LevelPattern:
    """The size- and mass-independent signature of one geometry.

    Frozen and built from tuples because these are constants of nature, not
    settings: they are memoised and handed to many callers, and a caller that
    could mutate ``ratios`` in place would corrupt every other one.
    """

    #: Identifier, one of :data:`PATTERN_NAMES`.
    name: str
    #: Human-readable name, from :data:`PATTERN_LABELS`.
    label: str
    #: Number of CONFINED directions (1, 2 or 3) -- not the embedding
    #: dimension. A disc and a square both confine in two.
    confined_dims: int
    #: E_n / E_1 for the distinct energies, ascending. ``ratios[0]`` is
    #: exactly 1.0 by construction and the sequence is strictly increasing.
    ratios: Tuple[float, ...]
    #: How many states sit at each energy, spin excluded. Same length as
    #: :attr:`ratios`.
    degeneracies: Tuple[int, ...]
    #: One representative quantum-number tuple per distinct energy -- the
    #: lowest member of the degenerate group, for labelling a plot.
    quantum_numbers: Tuple[Tuple[int, ...], ...]

    @property
    def n_levels(self) -> int:
        """How many distinct energies the pattern carries."""
        return len(self.ratios)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

#: A raw state: (energy in eV at unit size and unit mass, quantum numbers,
#: how many physical states that entry stands for).
_State = Tuple[float, Tuple[int, ...], int]


def _group_levels(states: List[_State],
                  rtol: float = GROUP_RTOL) -> List[Tuple[float, int, Tuple[int, ...]]]:
    """Collapse an ascending state list onto distinct energies.

    Returns ``(energy, total_degeneracy, representative_qn)`` per distinct
    level. The tolerance is relative rather than absolute because the ladder
    spans two orders of magnitude between the ground state and the last level
    of a warm-looking spectrum, and an absolute tolerance that separates the
    bottom would merge the top.

    :func:`src.physics.eigensolver.group_degenerate` is deliberately not used
    here: it takes joules, applies an absolute tolerance in eV, and returns
    indices rather than counts -- three mismatches against what this needs.
    """
    groups: List[Tuple[float, int, Tuple[int, ...]]] = []
    for energy, qn, weight in states:
        if groups and abs(energy - groups[-1][0]) <= rtol * abs(groups[-1][0]):
            prev_energy, prev_weight, prev_qn = groups[-1]
            groups[-1] = (prev_energy, prev_weight + weight, prev_qn)
        else:
            groups.append((energy, weight, qn))
    return groups


def _box_states(dims: int, count: int) -> List[_State]:
    """Ascending states of a 1D line, a square or a cube, at unit size.

    ``analytical`` enumerates every permutation of the quantum numbers as its
    own entry, so each entry stands for exactly one state and the weight is
    1. The eV-returning entry points are used on purpose: ``box_energies_1d``
    and ``box_energies_3d`` return joules, and since only ratios are taken
    here the mistake would be invisible.
    """
    if dims == 1:
        raw = box_energies_1d_eV(1.0, 1.0, count)
    elif dims == 2:
        raw = box_energies_2d_eV(1.0, 1.0, 1.0, count)
    else:
        raw = box_energies_3d_eV(1.0, 1.0, 1.0, 1.0, count)
    return [(float(energy), tuple(qn), 1) for energy, qn in raw]


def _disc_states(count: int) -> List[_State]:
    """Ascending states of a disc at unit radius.

    ``disk_energies`` iterates ``m >= 0`` only, so every ``m > 0`` entry
    stands for the +/-m pair and weighs 2. Weighting by entry count instead
    would under-count every angular level by a factor of two and flatten the
    predicted step heights.
    """
    raw = disk_energies(1.0, 1.0, count)
    return [(float(energy), tuple(qn), 1 if qn[0] == 0 else 2)
            for energy, qn in raw]


def _sphere_states(count: int) -> List[_State]:
    """Ascending states of a ball at unit radius.

    Delegated to :func:`src.physics.quantum_dot.spherical_dot` with an
    infinite barrier, which already root-finds the zeros of j_l (scipy has no
    routine for them) and already carries the 2l+1 orbital degeneracy on
    :class:`~src.physics.quantum_dot.Level`. ``l_max`` and ``n_per_channel``
    are both sized to ``count`` so the first ``count`` sorted levels cannot
    be missing a member: an energy rises with both quantum numbers, so the
    k-th level never needs more than k steps along either axis.
    """
    levels = spherical_dot(1.0, V0_eV=None, meff=1.0,
                           l_max=count, n_per_channel=count)
    return [(float(lv.E_eV), tuple(lv.quantum_numbers), int(lv.degeneracy))
            for lv in levels]


#: How many raw states must be generated to be sure of ``k`` complete
#: distinct levels. Degeneracy is what drives it: 17 distinct 3D levels need
#: 66 states, 17 disc levels need 17. Measured by brute force, then rounded
#: up -- generating spare states costs microseconds, generating too few
#: silently truncates a degenerate group and understates its step height.
_RAW_PER_LEVEL = {
    "box_1d": 1,
    "box_2d_square": 3,
    "disc_2d": 1,
    "box_3d_cube": 5,
    "sphere_3d": 1,
}


def _states_for(name: str, count: int) -> List[_State]:
    """Raw ascending states for ``name``, enough for ``count`` distinct ones."""
    raw_count = count * _RAW_PER_LEVEL[name]
    if name == "box_1d":
        return _box_states(1, raw_count)
    if name == "box_2d_square":
        return _box_states(2, raw_count)
    if name == "box_3d_cube":
        return _box_states(3, raw_count)
    if name == "disc_2d":
        return _disc_states(raw_count)
    return _sphere_states(raw_count)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def pattern(name: str, n_levels: int = DEFAULT_LEVELS) -> LevelPattern:
    """The fingerprint of one geometry, to ``n_levels`` distinct energies.

    Memoised: the result depends on nothing but its two arguments, and the
    sphere costs a root search per angular channel that is not worth
    repeating. The returned object is frozen, so sharing it is safe.

    Raises ``ValueError`` for an unknown name, or for an ``n_levels`` outside
    1..:data:`MAX_LEVELS` -- above the ceiling the underlying Bessel grid
    would silently reorder the ladder, and a wrong fingerprint is worse than
    a refused one.
    """
    if name not in PATTERN_NAMES:
        raise ValueError(
            f"name must be one of {PATTERN_NAMES}, got {name!r}")
    n_levels = int(n_levels)
    if n_levels < 1 or n_levels > MAX_LEVELS:
        raise ValueError(
            f"n_levels must be between 1 and {MAX_LEVELS}, got {n_levels!r}")

    # One spare level, then discarded: the last group of a truncated list may
    # be missing degenerate partners that fell outside the raw count, which
    # would understate its degeneracy without changing its energy.
    groups = _group_levels(_states_for(name, n_levels + 1))
    if len(groups) < n_levels + 1:
        raise ValueError(
            f"{name!r} produced only {len(groups)} distinct levels, "
            f"needed {n_levels + 1}")
    groups = groups[:n_levels]

    ground = groups[0][0]
    if not ground > 0:
        raise ValueError(
            f"{name!r} has a non-positive ground level {ground!r}")

    ratios = tuple(energy / ground for energy, _, _ in groups)
    if any(b <= a for a, b in zip(ratios, ratios[1:])):
        raise ValueError(
            f"{name!r} ratios are not strictly increasing: {ratios!r}")

    return LevelPattern(
        name=name,
        label=PATTERN_LABELS[name],
        confined_dims=CONFINED_DIMS[name],
        ratios=ratios,
        degeneracies=tuple(int(weight) for _, weight, _ in groups),
        quantum_numbers=tuple(qn for _, _, qn in groups),
    )


def all_patterns(n_levels: int = DEFAULT_LEVELS) -> Tuple[LevelPattern, ...]:
    """Every pattern in :data:`PATTERN_NAMES` order, ready to compare against."""
    return tuple(pattern(name, n_levels) for name in PATTERN_NAMES)


def expected_step_heights(p: LevelPattern) -> Tuple[float, ...]:
    """Degeneracies normalised to the ground level's -- the relative weights.

    A conductance step, or the area under a dI/dV peak, scales with the
    number of states at that energy, so a cube's second level should come in
    three times the ground one's while a line's should match it. Treat it as
    corroboration only: heights depend on the tunnel matrix element, on the
    tip, and on whatever background was subtracted, none of which the
    :attr:`~LevelPattern.ratios` depend on.

    Returns NaN for every level if the ground degeneracy is not positive,
    which cannot happen for the patterns here but would otherwise be reported
    as a spurious 0.0.
    """
    if not p.degeneracies:
        return ()
    ground = p.degeneracies[0]
    if ground <= 0:
        logger.warning("Pattern %r has a non-positive ground degeneracy %r",
                       p.name, ground)
        return tuple(float("nan") for _ in p.degeneracies)
    return tuple(float(d) / float(ground) for d in p.degeneracies)
