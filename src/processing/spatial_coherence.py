"""
Map-level statistics of the per-point band-edge fits.

:mod:`src.processing.edge_analysis` answers one spectrum at a time: how steep
is the tail, where is the band edge. This module asks the two questions that
only a *set* of points can answer, and both of them decide how the per-point
numbers may be read.

**Is the band tail the sample, or the apparatus?** An exponential edge of
decay energy ``E0`` has three possible sources: static compositional disorder,
a zero-point lattice term, and tip-induced band bending. Temperature cannot
separate them at a single temperature -- the Urbach thermal term goes as
``coth(hw / 2 k_B T)``, which *saturates* rather than vanishing as T falls, so
a temperature-independent ``E0`` is consistent with both static disorder and a
zero-point contribution. What does separate them is space: **a zero-point
lattice term is the same at every point on the sample; compositional disorder
is not.** :func:`e0_uniformity` tests exactly that, weighted by each point's
own error bar, so a spread that is only measurement scatter is not mistaken
for composition.

**How much does the disorder actually cost the dimensionality fit?** The
level-ratio method (:mod:`src.physics.level_ratio_fit`) fits one offset per
spectrum, so a fluctuation that moves a whole object's band edge together is
absorbed exactly and costs nothing. Only the part of the landscape varying
*within* one object degrades the ratios. Which of those you have is set by the
disorder correlation length against the object size, and
:func:`v0_correlation_length` measures it from the fitted band-edge positions.
A correlation length well above the object size means the worst-case error
budget on the ratios is far too pessimistic.

The correlation length is measured with a **semivariogram** rather than an
autocorrelation. Both describe the same field, but the semivariogram needs no
estimate of the mean -- which is the quantity most contaminated by a drifting
tip -- and it degrades gracefully on the irregular, gappy point sets that real
STS grids produce. Its fitted *nugget* is a bonus: it is the uncorrelated part
of the scatter, i.e. the measurement noise, separated from the real spatial
structure rather than folded into it.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
from scipy import stats
from scipy.optimize import curve_fit

logger = logging.getLogger(__name__)

__all__ = [
    "UniformityResult", "VariogramFit",
    "e0_uniformity", "semivariogram", "v0_correlation_length",
    "coherence_summary", "coherence_columns",
]

#: Below this p-value the points are not all reading the same ``E0``.
UNIFORMITY_P_VALUE = 1e-3

#: Fewest points that can carry either statistic. The uniformity test needs a
#: degree of freedom left after fitting the weighted mean; the variogram needs
#: enough pairs to bin at all.
MIN_POINTS_UNIFORMITY = 3
MIN_POINTS_VARIOGRAM = 8


@dataclass(frozen=True)
class UniformityResult:
    """Whether one number describes every point's band tail."""

    n_points: int
    weighted_mean_ev: float
    chi2: float
    dof: int
    p_value: float
    #: Scatter beyond what the error bars explain, in eV. NaN when the points
    #: are consistent with a single value -- there is no excess to report, and
    #: zero would read as "measured to be zero" rather than "none found".
    excess_scatter_ev: float
    verdict: str            # 'uniform' | 'varying' | 'undetermined'
    note: str


@dataclass(frozen=True)
class VariogramFit:
    """Correlation length of the fitted band-edge position across a sample."""

    n_points: int
    n_pairs: int
    correlation_length_m: float
    correlation_length_err_m: float
    sill_ev2: float         # variance of the correlated part
    nugget_ev2: float       # uncorrelated part: measurement noise
    r2: float
    verdict: str            # 'resolved' | 'unresolved' | 'undetermined'
    note: str


# ---------------------------------------------------------------------------
# Is the tail energy the same everywhere?
# ---------------------------------------------------------------------------

def e0_uniformity(e0_ev: Sequence[float],
                  e0_err_ev: Optional[Sequence[float]] = None
                  ) -> UniformityResult:
    """Test the per-point tail energies against a single common value.

    The null hypothesis is that every point measures the same ``E0`` and the
    spread is measurement scatter. Rejecting it means the tail energy varies
    across the sample, which a zero-point lattice term cannot do and
    compositional disorder does.

    ``e0_err_ev`` may be omitted, in which case every point is weighted
    equally and the test becomes a plain one-sample chi-squared about the
    unweighted mean using the sample's own scatter -- which can only ever say
    "consistent", never "varying", because the scatter is then the yardstick.
    That degenerate case is reported as ``'undetermined'`` rather than as a
    uniform result, because it is the absence of an error bar talking, not the
    sample.
    """
    e0 = np.asarray(e0_ev, dtype=np.float64).ravel()
    if e0_err_ev is None:
        finite = np.isfinite(e0)
        n = int(finite.sum())
        return UniformityResult(
            n_points=n, weighted_mean_ev=float(np.mean(e0[finite])) if n else float("nan"),
            chi2=float("nan"), dof=0, p_value=float("nan"),
            excess_scatter_ev=float("nan"), verdict="undetermined",
            note=("no per-point error bars: the scatter is its own yardstick, "
                  "so uniformity cannot be tested. Pass e0_err_ev -- the "
                  "repeated spectra at each point already measure it."))

    err = np.asarray(e0_err_ev, dtype=np.float64).ravel()
    if err.size == 1:
        err = np.full(e0.shape, float(err[0]))
    if err.shape != e0.shape:
        raise ValueError(f"e0_ev has {e0.size} points but e0_err_ev has {err.size}")

    keep = np.isfinite(e0) & np.isfinite(err) & (err > 0.0)
    e0, err = e0[keep], err[keep]
    n = int(e0.size)
    if n < MIN_POINTS_UNIFORMITY:
        return UniformityResult(
            n_points=n, weighted_mean_ev=float(np.mean(e0)) if n else float("nan"),
            chi2=float("nan"), dof=max(n - 1, 0), p_value=float("nan"),
            excess_scatter_ev=float("nan"), verdict="undetermined",
            note=f"{n} usable point(s); at least {MIN_POINTS_UNIFORMITY} are needed.")

    w = 1.0 / err ** 2
    mean = float(np.sum(w * e0) / np.sum(w))
    chi2 = float(np.sum(w * (e0 - mean) ** 2))
    dof = n - 1
    p = float(stats.chi2.sf(chi2, dof))

    # Excess scatter: the extra per-point spread that would make chi2/dof = 1.
    # Reported only when there IS an excess, so it never reads as a measured
    # zero when the points simply agree.
    var_excess = (chi2 - dof) / float(np.sum(w)) * n / dof if chi2 > dof else float("nan")
    excess = math.sqrt(var_excess) if (isinstance(var_excess, float)
                                       and math.isfinite(var_excess)
                                       and var_excess > 0) else float("nan")

    if p < UNIFORMITY_P_VALUE:
        verdict = "varying"
        note = (f"E0 is not the same at every point: chi2 = {chi2:.4g} on "
                f"{dof} dof, p = {p:.2g}. Excess scatter "
                f"{excess * 1e3:.1f} meV beyond the error bars. A zero-point "
                f"lattice term would be uniform, so this points at "
                f"compositional disorder -- or at tip-induced band bending, "
                f"which also varies with the local gap.")
    else:
        verdict = "uniform"
        note = (f"One E0 of {mean * 1e3:.1f} meV describes every point "
                f"(chi2 = {chi2:.4g} on {dof} dof, p = {p:.2g}). Consistent "
                f"with a uniform contribution -- a zero-point lattice term "
                f"rather than composition.")

    logger.info("e0_uniformity: %s — %d points, chi2/dof = %.3g, p = %.2g",
                verdict, n, chi2 / dof if dof else float("nan"), p)
    return UniformityResult(n_points=n, weighted_mean_ev=mean, chi2=chi2,
                            dof=dof, p_value=p, excess_scatter_ev=excess,
                            verdict=verdict, note=note)


# ---------------------------------------------------------------------------
# How far does the landscape stay correlated?
# ---------------------------------------------------------------------------

def semivariogram(positions_m: Sequence[float] | np.ndarray,
                  values: Sequence[float], n_bins: int = 12
                  ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(lag, gamma, counts)`` -- half the mean squared difference per lag bin.

    ``positions_m`` may be 1-D (a line scan) or ``(n, 2)`` / ``(n, 3)`` for a
    grid; separations are Euclidean either way. Empty bins are dropped rather
    than returned as NaN, so the arrays are ready to fit.
    """
    pos = np.asarray(positions_m, dtype=np.float64)
    if pos.ndim == 1:
        pos = pos[:, None]
    val = np.asarray(values, dtype=np.float64).ravel()
    if pos.shape[0] != val.size:
        raise ValueError(f"{pos.shape[0]} positions but {val.size} values")

    keep = np.isfinite(val) & np.all(np.isfinite(pos), axis=1)
    pos, val = pos[keep], val[keep]
    n = val.size
    if n < 2:
        empty = np.array([], dtype=np.float64)
        return empty, empty, np.array([], dtype=np.intp)

    i, j = np.triu_indices(n, k=1)
    sep = np.linalg.norm(pos[i] - pos[j], axis=1)
    diff2 = (val[i] - val[j]) ** 2

    good = sep > 0.0
    sep, diff2 = sep[good], diff2[good]
    if sep.size == 0:
        empty = np.array([], dtype=np.float64)
        return empty, empty, np.array([], dtype=np.intp)

    # Bin only the shorter half of the separations: the longest lags are made
    # of the few pairs at opposite corners of the scan, and a variogram is
    # conventionally not trusted beyond about half the field's extent.
    edges = np.linspace(0.0, float(np.max(sep)) * 0.5, int(n_bins) + 1)
    idx = np.digitize(sep, edges) - 1
    lag, gamma, counts = [], [], []
    for b in range(int(n_bins)):
        m = idx == b
        c = int(m.sum())
        if c >= 2:
            lag.append(float(np.mean(sep[m])))
            gamma.append(0.5 * float(np.mean(diff2[m])))
            counts.append(c)
    return (np.asarray(lag, dtype=np.float64),
            np.asarray(gamma, dtype=np.float64),
            np.asarray(counts, dtype=np.intp))


def _exponential_model(h, nugget, sill, xi):
    return nugget + sill * (1.0 - np.exp(-h / xi))


def v0_correlation_length(positions_m: Sequence[float] | np.ndarray,
                          v0_ev: Sequence[float], n_bins: int = 12
                          ) -> VariogramFit:
    """Fit ``gamma(h) = nugget + sill (1 - exp(-h/xi))`` to the band-edge field.

    ``xi`` is the distance over which the local band edge stays correlated.
    Compare it against the object size: ``xi`` well above the object means the
    landscape shifts whole objects together, the per-spectrum fitted offset
    absorbs it, and the level ratios are barely degraded. ``xi`` below the
    object size means the potential varies across a single object and the
    worst-case ratio error applies.

    **How much to trust one number.** Measured on 30 realisations of an AR(1)
    field with a true 8 nm range, sampled every 0.5 nm over 100 nm, the fitted
    ``xi`` had a median of 8.5 nm -- unbiased -- but individual realisations
    spanned 3.4 to 28.3 nm. A single line scan therefore fixes the correlation
    length only to within a factor of two or three, which is enough to answer
    "longer or shorter than the object?" and not enough to quote as a
    material parameter. Read it as an order of magnitude, and take the median
    over several scans if a number is needed.

    The fit is declared ``'unresolved'`` when the best ``xi`` runs past the
    largest lag the data covers: the variogram is then still rising at the
    edge of the field and all that can honestly be said is "longer than the
    scan", not a number.
    """
    lag, gamma, counts = semivariogram(positions_m, v0_ev, n_bins=n_bins)
    n_points = int(np.isfinite(np.asarray(v0_ev, dtype=np.float64)).sum())
    n_pairs = int(counts.sum()) if counts.size else 0

    blank = dict(n_points=n_points, n_pairs=n_pairs,
                 correlation_length_m=float("nan"),
                 correlation_length_err_m=float("nan"),
                 sill_ev2=float("nan"), nugget_ev2=float("nan"),
                 r2=float("nan"))
    if n_points < MIN_POINTS_VARIOGRAM or lag.size < 3:
        return VariogramFit(**blank, verdict="undetermined",
                            note=(f"{n_points} point(s) in {lag.size} usable lag "
                                  f"bin(s); at least {MIN_POINTS_VARIOGRAM} points "
                                  f"and 3 bins are needed to fit a range."))

    span = float(lag[-1])
    spread = float(np.var(np.asarray(v0_ev, dtype=np.float64)[
        np.isfinite(np.asarray(v0_ev, dtype=np.float64))]))
    p0 = (max(gamma[0], 1e-18), max(spread, 1e-18), max(span / 3.0, 1e-12))
    try:
        popt, pcov = curve_fit(
            _exponential_model, lag, gamma, p0=p0,
            bounds=((0.0, 0.0, 1e-15), (np.inf, np.inf, np.inf)),
            sigma=1.0 / np.sqrt(counts), absolute_sigma=False, maxfev=20000)
    except Exception:
        logger.debug("Variogram fit failed", exc_info=True)
        return VariogramFit(**blank, verdict="undetermined",
                            note="the variogram model would not converge.")

    nugget, sill, xi = (float(v) for v in popt)
    err = float(np.sqrt(pcov[2, 2])) if np.all(np.isfinite(pcov)) else float("nan")
    resid = gamma - _exponential_model(lag, *popt)
    ss_tot = float(np.sum((gamma - gamma.mean()) ** 2))
    r2 = 1.0 - float(np.dot(resid, resid)) / ss_tot if ss_tot > 0 else float("nan")

    if xi > span:
        verdict = "unresolved"
        note = (f"the band edge is still correlated at the largest lag the "
                f"scan covers ({span * 1e9:.1f} nm), so the correlation "
                f"length is longer than the field, not {xi * 1e9:.1f} nm. "
                f"Treat it as 'longer than the scan' -- which is the good "
                f"case for the level ratios.")
        xi, err = float("nan"), float("nan")
    else:
        verdict = "resolved"
        note = (f"band edge correlated over {xi * 1e9:.1f} nm "
                f"(+/- {err * 1e9:.1f} nm). Compare against the object size: "
                f"above it the landscape shifts whole objects together and "
                f"the fitted offset absorbs it; below it the potential varies "
                f"within one object and degrades the level ratios.")

    logger.info("v0_correlation_length: %s — xi = %s, nugget = %.3g eV^2, "
                "sill = %.3g eV^2, r2 = %.3f", verdict,
                f"{xi * 1e9:.1f} nm" if math.isfinite(xi) else "unresolved",
                nugget, sill, r2)
    return VariogramFit(n_points=n_points, n_pairs=n_pairs,
                        correlation_length_m=xi, correlation_length_err_m=err,
                        sill_ev2=sill, nugget_ev2=nugget, r2=r2,
                        verdict=verdict, note=note)


# ---------------------------------------------------------------------------
# One flat row for the tool
# ---------------------------------------------------------------------------

def coherence_columns() -> Tuple[str, ...]:
    """Stable key order of :func:`coherence_summary`."""
    return ("n_points", "e0_mean_ev", "e0_chi2", "e0_dof", "e0_p_value",
            "e0_excess_scatter_ev", "e0_verdict",
            "v0_correlation_length_m", "v0_correlation_length_err_m",
            "v0_nugget_ev2", "v0_sill_ev2", "v0_r2", "v0_verdict")


def coherence_summary(e0_ev: Sequence[float],
                      e0_err_ev: Optional[Sequence[float]] = None,
                      positions_m: Optional[Sequence[float]] = None,
                      v0_ev: Optional[Sequence[float]] = None,
                      n_bins: int = 12) -> Dict[str, object]:
    """Both statistics as one flat mapping, for a report or a dataset row.

    Either half may be skipped by leaving its inputs out; the missing keys
    come back NaN rather than absent, so the row shape never changes.
    """
    uni = e0_uniformity(e0_ev, e0_err_ev)
    if positions_m is not None and v0_ev is not None:
        var = v0_correlation_length(positions_m, v0_ev, n_bins=n_bins)
    else:
        var = VariogramFit(n_points=0, n_pairs=0,
                           correlation_length_m=float("nan"),
                           correlation_length_err_m=float("nan"),
                           sill_ev2=float("nan"), nugget_ev2=float("nan"),
                           r2=float("nan"), verdict="undetermined",
                           note="no positions given, so no spatial statistic.")

    return {
        "n_points": uni.n_points,
        "e0_mean_ev": uni.weighted_mean_ev,
        "e0_chi2": uni.chi2,
        "e0_dof": uni.dof,
        "e0_p_value": uni.p_value,
        "e0_excess_scatter_ev": uni.excess_scatter_ev,
        "e0_verdict": uni.verdict,
        "v0_correlation_length_m": var.correlation_length_m,
        "v0_correlation_length_err_m": var.correlation_length_err_m,
        "v0_nugget_ev2": var.nugget_ev2,
        "v0_sill_ev2": var.sill_ev2,
        "v0_r2": var.r2,
        "v0_verdict": var.verdict,
        "e0_note": uni.note,
        "v0_note": var.note,
    }
