"""
Splitting a dI/dV peak list into the electron and hole branches.

In STS the sample voltage has physical meaning: at V > 0 the tip injects
into empty states — the ladder of **electrons** confined above the bottom of
the conduction band; at V < 0 it removes from filled states — the ladder of
**holes** below the top of the valence band. A single curve therefore
already carries both sets of targets the two-carrier designer needs; what
separates them is the sign of the voltage, and the hole enters with |V|.

The energies come out counted from E_F, and the model counts from the bottom
of the well: an unknown offset is left over. That is why the matching mode
recommended on import is **differences (delta-E)**, in which that origin
cancels.

Peaks are found by TRANS's own engine — :mod:`src.processing.peak_detection`,
imported directly. The standalone calculator had to load it by file path;
inside the repository there is nothing to bridge.

The CSV reader that used to live here is gone: datasets come from the
project's loaders, not from disk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

from src.processing.peak_detection import (
    CONFINEMENT_DEFAULTS, analyze, params_from_dict,
)

logger = logging.getLogger(__name__)


@dataclass
class DidvCurve:
    """One dI/dV curve: the sweep and the signal, and what to call it."""

    x: np.ndarray                  # sample voltage (V)
    y: np.ndarray                  # dI/dV (arbitrary units)
    name: str = ""


@dataclass
class DidvPeaks:
    """What the analysis found, already separated by carrier.

    The energies come out counted from each branch's **boundary**, not from
    E_F: with the boundaries at zero (the default) the two coincide, and with
    the boundary at the band edge the target becomes E_n directly, which is
    what the model computes.
    """

    electron_eV: List[float]       # peaks above split_e, measured from there
    hole_eV: List[float]           # peaks below split_h, measured from there
    peaks_V: List[float]           # every centre, as it was found
    curve: Optional[DidvCurve] = None
    baseline: Optional[np.ndarray] = None
    corrected: Optional[np.ndarray] = None
    #: Boundaries used to separate the branches (V).
    split_e: float = 0.0
    split_h: float = 0.0
    #: Peaks that fell BETWEEN the boundaries — in the gap, no carrier.
    in_gap_V: List[float] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.peaks_V)


def split_peaks(centres: Sequence[float], split_e: float = 0.0,
                split_h: float = 0.0, min_gap_V: float = 0.0) -> DidvPeaks:
    """Split a list of peaks into an electron branch and a hole branch.

    The right boundary is the **band edge**, not E_F. The sign of the voltage
    says whether a state is empty or filled, and that only coincides with
    "electron or hole" when E_F falls inside the gap. In a charged (n-doped)
    dot the lowest electron levels are occupied: they sit ABOVE E_c and BELOW
    E_F, appear at negative voltage, and a split at V = 0 would tear the
    electron ladder in half — half of it would end up in the hole search,
    where it fits nicely and lies.

    With the boundaries at zero this is exactly the sign-of-voltage rule.
    """
    centres = [float(v) for v in centres]
    electron = sorted(v - split_e for v in centres if v > split_e + min_gap_V)
    hole = sorted(split_h - v for v in centres if v < split_h - min_gap_V)
    in_gap = sorted(v for v in centres
                    if split_h - min_gap_V <= v <= split_e + min_gap_V)
    return DidvPeaks(electron_eV=electron, hole_eV=hole, peaks_V=centres,
                     split_e=float(split_e), split_h=float(split_h),
                     in_gap_V=in_gap)


def analyze_curve(curve: DidvCurve, params: Optional[dict] = None,
                  min_abs_V: float = 0.0, split_e: float = 0.0,
                  split_h: float = 0.0) -> DidvPeaks:
    """Find the peaks with TRANS's engine and split the two branches.

    ``split_e``/``split_h`` are the branch boundaries — see
    :func:`split_peaks`. ``min_abs_V`` widens the neutral band around them,
    where a dI/dV usually carries zero-current noise that is no state at all.

    The knobs default to :data:`CONFINEMENT_DEFAULTS`, so this search and the
    Confinement Analysis tool see the same peaks by construction rather than
    by a copied dictionary.
    """
    knobs = {**CONFINEMENT_DEFAULTS, **(params or {})}
    detect = params_from_dict(knobs)
    detect.validate()
    result = analyze(np.asarray(curve.x, dtype=float),
                     np.asarray(curve.y, dtype=float), detect)

    centres = [float(pk.x) for pk in result.peaks]
    peaks = split_peaks(centres, split_e, split_h, min_abs_V)
    peaks.curve = curve
    peaks.baseline = result.baseline
    peaks.corrected = result.y_corrected
    # debug and not info: on a line scan this fires once per spectrum, and
    # what matters there is the one line per position.
    logger.debug("dI/dV: %d peak(s) — %d above %+.4f V (electrons), "
                 "%d below %+.4f V (holes), %d between the boundaries",
                 len(centres), len(peaks.electron_eV), split_e,
                 len(peaks.hole_eV), split_h, len(peaks.in_gap_V))
    return peaks


def relative_to_edge(levels: Sequence[float]) -> List[float]:
    """Energies counted from the first level instead of from E_F.

    The first peak on each side is the band edge; counting from there puts
    the energies in the model's frame — but it consumes the ground level, so
    the result has one target fewer and is only worth using when the edge was
    genuinely detected.
    """
    if len(levels) < 2:
        return list(levels)
    first = levels[0]
    return [lv - first for lv in levels[1:]]


def format_targets(levels: Sequence[float], precision: int = 5) -> str:
    """The list as the target-energies field expects it."""
    return ", ".join(f"{lv:.{precision}f}" for lv in levels)
