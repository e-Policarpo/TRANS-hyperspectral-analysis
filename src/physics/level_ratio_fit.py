"""Which confinement geometry does one spectrum actually support?

:mod:`src.physics.designer` answers a different question. It *assumes* a
geometry and searches for the size and the effective mass that reproduce a
measured ladder. That is the right tool once the geometry is known, and the
wrong one for deciding *which* geometry it is: with two free parameters per
model, every model can be made to pass through a short ladder, and the search
returns a confident number either way.

This module compares the geometries against each other instead, and reports
which one the data supports — or refuses to answer. It works on the **ratios**
of the level positions, which is why it never needs the effective mass::

    E_measured[k] = scale * pattern.ratios[assignment[k]] + offset

``scale`` is the ground level of that geometry (all ratio tuples start at
1.0), so it carries the mass and the size together and neither has to be known
in advance. ``offset`` is the band-edge reference V0 — a **fitted** parameter,
never assumed to be zero, because STS counts energy from E_F while the model
counts it from the bottom of the well. Once an assignment of measured levels
to pattern entries is chosen the model is linear in both, so each candidate
assignment costs one weighted least-squares solve and the whole comparison is
a ranking by AIC.

**Why ratios survive the junction.** A double-barrier tunnel junction divides
the applied bias: only a fraction eta of V drops across the dot, so a level at
energy E appears at V = E / eta. A bias-independent lever arm rescales *every*
level by the same factor, which the fitted ``scale`` absorbs exactly — the
ratios, and therefore the verdict, are unchanged. This is what makes the
geometry identifiable from a single spectrum with no calibration.

**What ratios do NOT survive.** Coulomb charging adds an electrostatic term
that grows with the number of electrons already on the dot, i.e. with the
level index, and neither ``scale`` (a multiplier) nor ``offset`` (a constant)
can absorb something that grows. The symptom is diagnostic: successive ratios
E_(k+1)/E_k trend towards 1 as the ladder is compressed from above, and the
fitted geometry drifts towards the flattest pattern available. See Jdira,
Liljeroth, Stoffels, Vanmaekelbergh & Speller, *Size-dependent single-particle
energy levels and interparticle Coulomb interactions in CdSe quantum dots
measured by scanning tunneling spectroscopy*, Phys. Rev. B **73**, 115305
(2006).

**Why positions and not lineshapes.** Thermal and instrumental broadening
convolve the spectrum with a kernel that is even about each feature: it
preserves the feature *positions* and the integrated weight, and destroys the
onset *shapes* — a 1D van Hove edge, a 2D step and a 3D root all look like the
same smooth rise at 94 K. So this module fits positions, and uses
degeneracy-weighted step heights (:func:`level_patterns.expected_step_heights`)
only as a secondary discriminator, never a lineshape.

**One degeneracy that is not noise.** A square 2D box contains the 1D ladder
exactly: its (n, 1) family is n^2 + 1, which is the 1D ladder shifted by the
transverse zero-point energy — and a constant shift is precisely what the
fitted ``offset`` absorbs. So a perfect 1D spectrum is reproduced with zero
residual by the 2D pattern too, at half the scale and a negative offset. This
is a genuine property of the model rather than a defect in the fit, and it is
the clearest case for reporting ``'ambiguous'`` instead of picking. Where AIC
ties, :func:`fit_pattern`'s ``n_skipped`` breaks it towards the pattern that
had to invent fewest unresolved states, which recovers the 1D answer without
pretending the 2D one was excluded.

**Expected precision, and why one spectrum is rarely enough.** Propagating a
22 meV disorder amplitude onto levels near 60 and 150 meV gives
E2/E1 = 2.5 +/- 1.0 from a single spectrum. That separates 1D (E2/E1 = 4.0)
from everything else, but it does **not** separate 2D (2.5) from 3D (2.0).
Per-point verdicts are therefore expected to come back ``'ambiguous'``, and
that is the honest answer: the discrimination lives in the *distribution* of
fits across many points, not in any one of them. The mandatory
``'underdetermined'`` guard in :func:`rank_patterns` exists for the same
reason — with two free parameters and two measured levels every pattern fits
exactly, dof = 0, and a ranking would be pure noise dressed as a result.

The module is free of Qt, of file I/O and of any TRANS data model: everything
here takes plain arrays of energies, so it can be tested and reasoned about on
its own.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import itertools
import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats

from src.physics.level_patterns import LevelPattern, all_patterns

logger = logging.getLogger(__name__)

__all__ = [
    "PatternFit",
    "RatioVerdict",
    "VERDICTS",
    "UNDERDETERMINED",
    "AMBIGUOUS",
    "CONCLUSIVE",
    "AMBIGUITY_DELTA_AIC",
    "TIE_QUANTUM",
    "fit_pattern",
    "rank_patterns",
    "size_from_scale",
    "ratio_with_error",
]

#: The three answers this module is allowed to give. They are stable keys —
#: a map colours by them and a summary counts them.
UNDERDETERMINED = "underdetermined"
AMBIGUOUS = "ambiguous"
CONCLUSIVE = "conclusive"

REJECTED = "rejected"

VERDICTS = (UNDERDETERMINED, REJECTED, AMBIGUOUS, CONCLUSIVE)

#: Below this chi-squared survival probability the winning pattern is rejected
#: outright. AIC is a purely RELATIVE criterion: it names the least bad of the
#: candidates and says nothing about whether any of them describes the data.
#: Without an absolute gate a ladder that fits no geometry at all — a Coulomb
#: staircase, a disorder-scrambled spectrum, mis-picked peaks — still comes
#: back labelled with whichever geometry lost by least. The verdict then reads
#: as an identification. This is the gate that lets the module answer "none of
#: these".
REJECTION_P_VALUE = 1e-3

#: Below this difference in AIC the two best patterns are not distinguishable.
#: Burnham & Anderson's conventional threshold: delta < 2 means the runner-up
#: has substantial support, i.e. the data does not choose between them.
AMBIGUITY_DELTA_AIC = 2.0

#: Smallest usable uncertainty, in eV. A sigma of zero is a division by zero
#: dressed as a measurement; anything below a microvolt is well past the
#: resolution of any STS experiment this module will ever see.
MIN_SIGMA_EV = 1e-9

#: Granularity below which two chi-squared or AIC values are the same number.
#: Some of these patterns contain one another *exactly* — a cube reproduces a
#: square's ladder with one skipped entry, a square reproduces a line's with
#: two — so their chi-squared agrees to the last digit and the comparison is
#: decided by round-off. Left alone, ``best`` would then flip between two
#: identical fits when every level is multiplied by a lever arm, which is the
#: one thing the ratios are supposed to be immune to. Quantising first hands
#: those ties to the documented tie-break (fewest invented states) instead. It
#: is six orders of magnitude below :data:`AMBIGUITY_DELTA_AIC`, so it can
#: never merge two fits the data actually distinguishes.
TIE_QUANTUM = 1e-6


def _tie_bucket(value: float) -> float:
    """``value`` snapped to the tie grid, for use as a sort key."""
    if not math.isfinite(value):
        return value
    return math.floor(value / TIE_QUANTUM + 0.5) * TIE_QUANTUM


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PatternFit:
    """One geometry's best fit to one measured ladder.

    Frozen because a fit is a record of what happened, and the ranking hands
    the same object to several callers.
    """

    pattern: str                    # LevelPattern.name
    label: str                      # human-readable, from the pattern
    confined_dims: int              # 1, 2 or 3
    scale_ev: float                 # ground level of the geometry, > 0
    scale_err_ev: float             # 1 sigma, from the fit covariance
    offset_ev: float                # band-edge reference V0
    offset_err_ev: float            # 1 sigma; exactly 0.0 when offset was fixed
    assignment: Tuple[int, ...]     # pattern index used by each measured level
    chi2: float
    dof: int                        # n - k; 0 means an exact, untestable fit
    p_value: float                  # chi-squared survival at dof; NaN when dof <= 0
    k_eff: int                      # continuous parameters + fitted skips
    aic: float                      # AICc where the sample allows the correction
    residuals_ev: Tuple[float, ...]
    rms_ev: float

    @property
    def n_skipped(self) -> int:
        """Pattern entries the fit had to declare unresolved.

        At 94 K the resolution is ~29 meV, so missing levels are expected, not
        a defect. A fit that needs many of them is nevertheless weaker
        evidence than one that needs none.
        """
        if not self.assignment:
            return 0
        return int(self.assignment[-1] - (len(self.assignment) - 1))


@dataclass(frozen=True)
class RatioVerdict:
    """The ranking of every geometry against one measured ladder."""

    ranked: Tuple[PatternFit, ...]      # ascending AIC; empty when underdetermined
    best: Optional[PatternFit]          # None when underdetermined
    runner_up: Optional[PatternFit]
    delta_aic: float                    # runner_up.aic - best.aic; inf with no rival
    verdict: str                        # one of VERDICTS
    n_levels: int                       # measured levels the verdict rests on
    ratio_21: float                     # E2/E1 of the levels AS GIVEN
    ratio_21_err: float
    note: str                           # why this verdict, in words
    p_value: float = float("nan")       # chi-squared survival of ``best``
    #: ``ratio_21`` recomputed about the fitted band edge, i.e.
    #: ``(E2 - offset) / (E1 - offset)``. This is the number to compare
    #: against the textbook table (4.00 / 2.50 / 2.54 / 2.00 / 2.05), because
    #: it is measured in the same frame the ranking fitted in. ``ratio_21``
    #: itself is the raw quotient of the levels as handed in; the two agree
    #: only when the band edge sits at zero, which is the whole reason
    #: ``offset`` is a fitted parameter. Reading the raw one against the table
    #: while the verdict came from the fitted one is how this module would
    #: contradict itself, so both are carried and named apart.
    ratio_21_corrected: float = float("nan")
    ratio_21_corrected_err: float = float("nan")


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def _levels_and_sigma(levels_ev: Sequence[float], sigma_ev):
    """The measured levels and their uncertainties, cleaned together.

    Together, and not one after the other, because both operations reorder:
    a non-finite level is dropped and the rest are sorted ascending, so a
    per-level sigma array has to be carried through the same mask and the same
    permutation or the third level's error bar ends up on the second level's
    energy. Doing it in two independent helpers is exactly how that goes wrong
    silently.

    A scalar sigma is the usual case — the resolution is set by temperature,
    not by which level you are looking at — but a per-level array is accepted
    so a caller who fitted each feature individually can pass its own error.
    A length that matches neither is a mismatched axis, and a wrong number is
    worse than an exception.

    A level whose uncertainty is not finite is dropped along with a level that
    is not finite itself, and for the same reason: it is not a measurement. It
    must **not** be floored at :data:`MIN_SIGMA_EV` — the weight is 1/sigma^2,
    so flooring would hand the one level nothing is known about the largest
    weight in the fit, which is exactly backwards. A sigma of *zero* is a
    different animal and is floored: it is a caller saying "no error bar", not
    "no information".
    """
    levels = np.asarray(levels_ev, dtype=np.float64).ravel()
    sigma = np.asarray(sigma_ev, dtype=np.float64).ravel()
    if sigma.size == 1:
        sigma = np.repeat(sigma, levels.size)
    if sigma.size != levels.size:
        raise ValueError(
            f"sigma_ev has {sigma.size} values but there are {levels.size} "
            f"levels")

    keep = np.isfinite(levels) & np.isfinite(sigma)
    levels, sigma = levels[keep], sigma[keep]
    order = np.argsort(levels, kind="stable")
    levels, sigma = levels[order], sigma[order]

    return levels, np.maximum(np.abs(sigma), MIN_SIGMA_EV)


def _assignments(n_measured: int, n_pattern: int, max_skips: int):
    """Strictly increasing injections of the measured levels into the pattern.

    Skips are unresolved states, and they may fall before the first measured
    level as well as between two of them — a spectrum whose weakest features
    are its lowest ones starts at pattern entry 2, not 0. Because the
    assignment is strictly increasing, the number of skipped entries is
    exactly ``last_index - (n_measured - 1)``, so bounding the last index
    bounds the skips and the enumeration stays trivial: at most
    C(n + max_skips, n) combinations, a handful for n_levels <= 8.
    """
    if n_measured <= 0 or n_measured > n_pattern:
        return
    limit = min(n_pattern, n_measured + max(0, int(max_skips)))
    yield from itertools.combinations(range(limit), n_measured)


def _weighted_fit(p: np.ndarray, energies: np.ndarray, sigma: np.ndarray,
                  offset_fixed: Optional[float]):
    """Weighted least squares for ``E = scale * p + offset``.

    Solved from the normal equations rather than via :func:`numpy.linalg.lstsq`
    because the covariance is wanted as well as the solution, and for two
    parameters the closed form is both exact and faster inside the assignment
    loop.

    Returns ``(scale, scale_var, offset, offset_var)``, or None when the
    system is singular — which happens whenever the assignment gives fewer
    distinct ratios than there are free parameters.
    """
    w = 1.0 / (sigma * sigma)

    if offset_fixed is not None:
        offset = float(offset_fixed)
        spp = float(np.sum(w * p * p))
        if not math.isfinite(spp) or spp <= 0.0:
            return None
        scale = float(np.sum(w * p * (energies - offset)) / spp)
        return scale, float(1.0 / spp), offset, 0.0

    sw = float(np.sum(w))
    sp = float(np.sum(w * p))
    spp = float(np.sum(w * p * p))
    se = float(np.sum(w * energies))
    spe = float(np.sum(w * p * energies))

    det = spp * sw - sp * sp
    # Degenerate whenever every assigned ratio is the same value (n = 1, or a
    # pattern with repeated entries): the line through them is not determined.
    if not math.isfinite(det) or det <= 0.0:
        return None

    scale = (spe * sw - sp * se) / det
    offset = (spp * se - sp * spe) / det
    return float(scale), float(sw / det), float(offset), float(spp / det)


def _aic(chi2: float, n: int, k: int, k_eff: Optional[int] = None) -> float:
    """AIC on a Gaussian likelihood, corrected for a small sample.

    ``chi2 + 2k`` is AIC up to a constant that is the same for every pattern,
    so it ranks them correctly. The AICc correction matters here: with three
    or four measured levels and two parameters the plain AIC under-penalises
    complexity badly, and it is exactly the regime this module works in. It is
    only defined for ``n - k - 1 > 0``; below that the fit is already at or
    past the underdetermined guard.
    """
    #: ``k_eff`` is what actually gets penalised. The continuous parameters
    #: are the same two for every pattern, so on their own they cancel out of
    #: every AIC difference and ``delta_aic`` degenerates into a bare
    #: ``delta_chi2``. But choosing an assignment IS fitting a discrete
    #: parameter — each skipped pattern entry is a state the fit invented to
    #: explain a gap in the ladder — and a pattern allowed more skips can
    #: always reach a lower chi-squared. Charging one parameter per skip is
    #: what makes the comparison between a long ladder used sparsely and a
    #: short one used fully an honest one.
    kk = int(k if k_eff is None else k_eff)
    aic = float(chi2) + 2.0 * kk
    # The small-sample correction is computed from the CONTINUOUS parameters
    # only, not from ``kk``. Folding the skips in makes ``n - kk - 1`` go
    # non-positive for any pattern that skips much, and the correction is then
    # silently dropped — so the most complex fit is the one that escapes the
    # complexity penalty, which is exactly backwards. Charging 2 per skip in
    # the AIC term and leaving the correction on ``k`` keeps the penalty
    # monotone in the number of skips, which is the property that matters.
    if n - k - 1 > 0:
        aic += 2.0 * k * (k + 1) / (n - k - 1)
    return aic


# ---------------------------------------------------------------------------
# Fitting one pattern
# ---------------------------------------------------------------------------

def fit_pattern(levels_ev: Sequence[float], sigma_ev, pattern: LevelPattern,
                *, offset_fixed: Optional[float] = None,
                max_skips: int = 2) -> Optional[PatternFit]:
    """Best fit of one geometry's ratio ladder to the measured levels.

    Every allowed assignment is tried and the one with the lowest chi-squared
    is returned; ties go to the assignment that skips fewest pattern entries,
    since inventing unresolved states is a cost even when it is free in
    chi-squared.

    ``scale`` is constrained to be positive. A negative scale would invert the
    ladder — the model would be reproducing the *order* of the levels by
    running the geometry backwards, which is not a confinement solution at
    all — so such assignments are discarded rather than fitted.

    Returns None when the pattern cannot be fitted: fewer measured levels than
    free parameters, more measured levels than the pattern has entries, or no
    assignment with a positive scale.
    """
    levels, sigma = _levels_and_sigma(levels_ev, sigma_ev)
    n = int(levels.size)
    ratios = np.asarray(pattern.ratios, dtype=np.float64)
    k = 1 if offset_fixed is not None else 2

    if n < k:
        logger.debug("Pattern %r: %d levels cannot determine %d parameters",
                     pattern.name, n, k)
        return None
    if n > ratios.size:
        logger.debug("Pattern %r: %d levels but the pattern has only %d entries",
                     pattern.name, n, ratios.size)
        return None

    best = None
    best_key = None
    for assignment in _assignments(n, int(ratios.size), max_skips):
        p = ratios[list(assignment)]
        solved = _weighted_fit(p, levels, sigma, offset_fixed)
        if solved is None:
            continue
        scale, scale_var, offset, offset_var = solved
        if not math.isfinite(scale) or scale <= 0.0:
            continue

        model = scale * p + offset
        residuals = levels - model
        chi2 = float(np.sum((residuals / sigma) ** 2))
        if not math.isfinite(chi2):
            continue

        skips = assignment[-1] - (n - 1)
        key = (_tie_bucket(chi2), skips)
        if best_key is None or key < best_key:
            best_key = key
            best = (assignment, scale, scale_var, offset, offset_var,
                    chi2, residuals)

    if best is None:
        logger.debug("Pattern %r: no assignment gave a positive scale",
                     pattern.name)
        return None

    assignment, scale, scale_var, offset, offset_var, chi2, residuals = best
    rms = float(np.sqrt(np.mean(residuals ** 2))) if residuals.size else float("nan")

    skips = int(assignment[-1] - (len(assignment) - 1)) if len(assignment) else 0
    k_eff = int(k + skips)
    dof = int(n - k)
    # dof deliberately counts only the continuous parameters. Selecting the
    # assignment also consumes information, so the true effective dof is lower
    # and this p-value is optimistic — which errs toward NOT rejecting, the
    # safe direction for a gate whose job is to catch fits that are absurd.
    p_value = float(stats.chi2.sf(chi2, dof)) if dof > 0 else float("nan")

    return PatternFit(
        pattern=pattern.name,
        label=pattern.label,
        confined_dims=int(pattern.confined_dims),
        scale_ev=float(scale),
        scale_err_ev=float(math.sqrt(scale_var)) if scale_var >= 0 else float("nan"),
        offset_ev=float(offset),
        offset_err_ev=float(math.sqrt(offset_var)) if offset_var >= 0 else float("nan"),
        assignment=tuple(int(i) for i in assignment),
        chi2=chi2,
        dof=dof,
        p_value=p_value,
        k_eff=k_eff,
        aic=_aic(chi2, n, k, k_eff),
        residuals_ev=tuple(float(r) for r in residuals),
        rms_ev=rms,
    )


# ---------------------------------------------------------------------------
# Ranking the patterns against each other
# ---------------------------------------------------------------------------

def rank_patterns(levels_ev: Sequence[float], sigma_ev, *,
                  patterns: Optional[Sequence[LevelPattern]] = None,
                  offset_fixed: Optional[float] = None,
                  max_skips: int = 2) -> RatioVerdict:
    """Rank every geometry against the measured ladder, and say how sure it is.

    The guard comes first and is not negotiable. With a free offset the model
    has two parameters, so two measured levels are reproduced *exactly* by
    every pattern in the list: chi-squared is zero everywhere, dof is zero, the
    AIC differences are zero, and whichever pattern happens to be first in the
    tuple would be reported as the answer. Handing back a confident geometry
    from two levels is the single worst thing this module could do, so that
    case returns ``verdict='underdetermined'`` with ``best=None`` and an empty
    ranking — there is deliberately nothing to read out of it.

    Above the guard the ranking is by AIC ascending, and the margin to the
    runner-up decides between ``'ambiguous'`` and ``'conclusive'``. Expect
    ``'ambiguous'`` from a single spectrum: at realistic disorder the 2D and 3D
    ladders are within each other's error bars, and it is the distribution of
    verdicts over a map that separates them.
    """
    levels, sigma = _levels_and_sigma(levels_ev, sigma_ev)
    n = int(levels.size)
    ratio_21, ratio_21_err = ratio_with_error(levels, sigma)

    k = 1 if offset_fixed is not None else 2
    minimum = k + 1
    if n < minimum:
        note = (f"{n} level(s) and {k} free parameter(s): every pattern fits "
                f"exactly, so nothing is measured. At least {minimum} levels "
                f"are needed"
                + (" with a fitted offset." if offset_fixed is None
                   else " with the offset fixed."))
        logger.info("rank_patterns: underdetermined — %d levels, %d parameters",
                    n, k)
        return RatioVerdict(ranked=(), best=None, runner_up=None,
                            delta_aic=float("nan"), verdict=UNDERDETERMINED,
                            n_levels=n, ratio_21=ratio_21,
                            ratio_21_err=ratio_21_err, note=note)

    candidates = tuple(all_patterns()) if patterns is None else tuple(patterns)

    fits: List[PatternFit] = []
    for pattern in candidates:
        fit = fit_pattern(levels, sigma, pattern,
                          offset_fixed=offset_fixed, max_skips=max_skips)
        if fit is not None:
            fits.append(fit)

    if not fits:
        note = ("No pattern could be fitted: the ladder is longer than every "
                "pattern, or no assignment gave a positive scale.")
        logger.info("rank_patterns: no pattern fitted %d levels", n)
        return RatioVerdict(ranked=(), best=None, runner_up=None,
                            delta_aic=float("nan"), verdict=UNDERDETERMINED,
                            n_levels=n, ratio_21=ratio_21,
                            ratio_21_err=ratio_21_err, note=note)

    fits.sort(key=lambda f: (_tie_bucket(f.aic), f.n_skipped, f.pattern))
    best = fits[0]
    runner_up = fits[1] if len(fits) > 1 else None

    if runner_up is None:
        # Nothing to be confused with. Infinite, not zero: the margin is
        # unbounded because no rival survived, and reporting 0.0 would read as
        # a tie between patterns that were never compared.
        delta_aic = float("inf")
        verdict = CONCLUSIVE
        note = (f"Only {best.label} could be fitted; no rival to compare "
                f"against.")
    else:
        delta_aic = float(runner_up.aic - best.aic)
        # Snap before comparing. Charging one parameter per skip makes an
        # integer delta common — two fits of equal chi-squared differing by
        # one invented state land on exactly 2.0 — and a bare ``<`` then
        # resolves the threshold on the last bit. That is how the same physics
        # scaled by a lever arm came back with a different verdict: the
        # levels and their errors both scale, chi-squared is invariant to
        # 1e-16, and the round-off decided the answer.
        if _tie_bucket(delta_aic) < AMBIGUITY_DELTA_AIC:
            verdict = AMBIGUOUS
            note = (f"{best.label} leads {runner_up.label} by only "
                    f"dAIC = {delta_aic:.2f}; both are supported by this "
                    f"spectrum.")
        else:
            verdict = CONCLUSIVE
            note = (f"{best.label} beats {runner_up.label} by "
                    f"dAIC = {delta_aic:.2f}.")

    # The absolute gate goes last so it can override a relative win. A
    # pattern can lead the field by a mile and still be nowhere near the data.
    if math.isfinite(best.p_value) and best.p_value < REJECTION_P_VALUE:
        verdict = REJECTED
        note = (f"{best.label} ranked first but does not describe the data: "
                f"chi2 = {best.chi2:.4g} on {best.dof} dof, p = "
                f"{best.p_value:.2g}. No offered geometry fits this ladder — "
                f"check for Coulomb charging, mis-picked peaks, or a "
                f"disorder-scrambled spectrum.")

    ratio_c, ratio_c_err = _ratio_about_offset(levels, sigma, best)

    logger.info("rank_patterns: %s — best %s (chi2=%.3g, dof=%d, p=%.2g), "
                "dAIC=%.3g, E2/E1=%.3g (corrected %.3g)", verdict,
                best.pattern, best.chi2, best.dof, best.p_value, delta_aic,
                ratio_21, ratio_c)

    return RatioVerdict(ranked=tuple(fits), best=best, runner_up=runner_up,
                        delta_aic=delta_aic, verdict=verdict, n_levels=n,
                        ratio_21=ratio_21, ratio_21_err=ratio_21_err, note=note,
                        p_value=best.p_value,
                        ratio_21_corrected=ratio_c,
                        ratio_21_corrected_err=ratio_c_err)


def _ratio_about_offset(levels: np.ndarray, sigma: np.ndarray,
                        fit: Optional[PatternFit]) -> Tuple[float, float]:
    """``(E2 - c) / (E1 - c)`` with ``c`` the fitted band edge, and its error.

    The ranking fits an offset, so the ratio that belongs beside its verdict
    has to be measured from that same offset. Propagated for all three
    quantities, the offset treated as independent of the levels::

        dr/dE2 =  1 / (E1 - c)
        dr/dE1 = -(E2 - c) / (E1 - c)^2
        dr/dc  =  (E2 - E1) / (E1 - c)^2

    NaN when there is no fit, fewer than two levels, or the ground level sits
    at or below the edge — where the quotient has no meaning rather than a
    large value.
    """
    if fit is None or levels.size < 2:
        return float("nan"), float("nan")
    c = float(fit.offset_ev)
    e1 = float(levels[0]) - c
    e2 = float(levels[1]) - c
    if not (math.isfinite(e1) and math.isfinite(e2)) or e1 <= 0.0:
        return float("nan"), float("nan")

    s1, s2 = float(sigma[0]), float(sigma[1])
    sc = float(fit.offset_err_ev)
    if not math.isfinite(sc):
        sc = 0.0

    ratio = e2 / e1
    d_e2 = 1.0 / e1
    d_e1 = -e2 / (e1 * e1)
    d_c = (e2 - e1) / (e1 * e1)
    err = math.sqrt((d_e2 * s2) ** 2 + (d_e1 * s1) ** 2 + (d_c * sc) ** 2)
    return float(ratio), float(err)


# ---------------------------------------------------------------------------
# Turning the fitted scale back into a length
# ---------------------------------------------------------------------------

def _model_energies(key: str, size_nm: float, meff: float,
                    n_levels: int) -> List[float]:
    """Energies in **eV** for one geometry of a single characteristic length.

    Routed through the eV-returning entry points only. ``analytical`` is
    inconsistent about it — ``box_energies_1d`` and ``box_energies_3d`` return
    joules while ``disk_energies`` returns eV without an ``_eV`` suffix — and a
    joules ladder here would come back as a length wrong by ten orders of
    magnitude while still looking like a positive float.
    """
    from src.physics.analytical import (box_energies_1d_eV, box_energies_2d_eV,
                                        box_energies_3d_eV, disk_energies)
    from src.physics.quantum_dot import DOT_SPHERICAL, dot_energies

    if key == "box_1d":
        levels = box_energies_1d_eV(size_nm, meff, n_levels)
    elif key == "box_2d":
        levels = box_energies_2d_eV(size_nm, size_nm, meff, n_levels)
    elif key == "disk":
        levels = disk_energies(size_nm, meff, n_levels)
    elif key == "box_3d":
        levels = box_energies_3d_eV(size_nm, size_nm, size_nm, meff, n_levels)
    elif key == "sphere":
        levels = dot_energies(DOT_SPHERICAL, (size_nm,), meff, n_levels)
    else:
        raise ValueError(f"unknown geometry key {key!r}")
    return [float(E) for E, _qn in levels]


#: Geometries whose spectrum is fixed by ONE length, so a ground-state energy
#: inverts to a size. An anisotropic box or a cylinder needs two lengths and a
#: single scale cannot give them — those patterns get NaN, which is the point.
_ONE_LENGTH_GEOMETRIES = ("box_1d", "box_2d", "disk", "box_3d", "sphere")

#: How closely a geometry's own ratio ladder must reproduce the pattern's
#: before it is accepted as that pattern's geometry. Both come from the same
#: closed forms, so agreement should be at round-off; 1e-3 leaves room for a
#: pattern tabulated to a few decimals without admitting a wrong geometry
#: (the closest wrong pair, 2D box at 2.5 against the disk at 2.539, differs
#: by 1.5e-2).
_RATIO_MATCH_TOL = 1e-3

#: Reference length for the inversion. Every infinite well has E ~ 1/L^2, so
#: one evaluation at 1 nm fixes the constant and the inversion is closed-form.
_REFERENCE_NM = 1.0


def _unique_ratios(energies: Sequence[float], count: int,
                   rel_tol: float = 1e-6) -> np.ndarray:
    """Distinct level energies, as ratios to the ground level.

    Degenerate partners are collapsed: a pattern lists each energy once and
    carries the multiplicity separately in ``degeneracies``, so the ladder
    compared against it has to be the distinct energies, not the enumeration.
    """
    values = np.asarray(energies, dtype=np.float64)
    values = np.sort(values[np.isfinite(values) & (values > 0)])
    if values.size == 0:
        return np.empty(0, dtype=np.float64)
    unique = [values[0]]
    for value in values[1:]:
        if value - unique[-1] > rel_tol * unique[-1]:
            unique.append(value)
        if len(unique) >= count:
            break
    return np.asarray(unique, dtype=np.float64) / unique[0]


def _geometry_for(pattern: LevelPattern) -> Optional[str]:
    """Which single-length geometry produces this pattern's ratios, if any.

    Matched on the ratios rather than on ``pattern.name``, deliberately. The
    ratios *are* the pattern's physical content, they are what this module
    fits, and matching on them means a renamed or newly added pattern inverts
    correctly without this file having to be edited in step.
    """
    target = np.asarray(pattern.ratios, dtype=np.float64)
    n = int(target.size)
    if n < 2:
        return None

    best_key, best_dev = None, float("inf")
    for key in _ONE_LENGTH_GEOMETRIES:
        try:
            # Ask for extra levels: a degenerate ladder collapses to fewer
            # distinct energies than it has entries.
            energies = _model_energies(key, _REFERENCE_NM, 0.067, 6 * n + 12)
        except Exception:
            logger.debug("Geometry %r could not be evaluated", key, exc_info=True)
            continue
        ratios = _unique_ratios(energies, n)
        if ratios.size < n:
            continue
        deviation = float(np.max(np.abs(ratios[:n] - target) / target))
        if deviation < best_dev:
            best_key, best_dev = key, deviation

    if best_key is None or best_dev > _RATIO_MATCH_TOL:
        logger.debug("Pattern %r matches no single-length geometry "
                     "(closest %r, %.3g relative)", pattern.name,
                     best_key, best_dev)
        return None
    return best_key


def size_from_scale(scale_ev: float, pattern: LevelPattern,
                    meff: float) -> float:
    """The confinement length in **nm** implied by a fitted scale.

    ``scale`` is the ground level of the geometry, and every infinite well has
    E_1 = C(geometry, meff) / L^2, so one evaluation at a reference length
    fixes C and the inversion is exact rather than iterative.

    This is the only place the effective mass enters, and it enters *after* the
    geometry has been decided — which is the whole reason the ranking is done
    on ratios. A wrong mass moves the size and leaves the verdict alone.

    Returns NaN, never a number, when the size is not one length: an
    anisotropic box or a cylinder needs two, and a single scale cannot supply
    them. NaN also comes back for a non-positive scale or mass.
    """
    scale = float(scale_ev)
    mass = float(meff)
    if not math.isfinite(scale) or scale <= 0.0:
        return float("nan")
    if not math.isfinite(mass) or mass <= 0.0:
        return float("nan")

    key = _geometry_for(pattern)
    if key is None:
        return float("nan")

    try:
        reference = _model_energies(key, _REFERENCE_NM, mass, 1)
    except Exception:
        logger.debug("Inverting %r for pattern %r failed", key, pattern.name,
                     exc_info=True)
        return float("nan")
    if not reference:
        return float("nan")

    ground = float(reference[0])
    if not math.isfinite(ground) or ground <= 0.0:
        return float("nan")
    return float(_REFERENCE_NM * math.sqrt(ground / scale))


# ---------------------------------------------------------------------------
# The headline number
# ---------------------------------------------------------------------------

def ratio_with_error(levels_ev: Sequence[float], sigma_ev) -> Tuple[float, float]:
    """``(E2/E1, its 1-sigma error)`` from the two lowest measured levels.

    The number a user reads before anything else, because the textbook values
    are memorable: 4.0 for a 1D well, 2.5 for a square 2D one, 2.0 for a cube.
    It is exposed directly rather than being buried in a fit so that the
    headline and the ranking cannot silently disagree.

    Standard propagation for a quotient, the two levels treated as
    independent::

        dr/r = sqrt((s1/E1)^2 + (s2/E2)^2)

    Careful: this is the ratio of the levels **as given**, so they must already
    be referred to the band edge. Feed it raw bias positions with a band edge
    somewhere else and the answer is the ratio of two offsets, not of two
    confinement energies — that is what the fitted ``offset`` of
    :func:`fit_pattern` is for. NaN for fewer than two levels or a
    non-positive ground level.
    """
    levels, sigma = _levels_and_sigma(levels_ev, sigma_ev)
    if levels.size < 2:
        return float("nan"), float("nan")

    e1, e2 = float(levels[0]), float(levels[1])
    if e1 <= 0.0:
        return float("nan"), float("nan")

    s1, s2 = float(sigma[0]), float(sigma[1])

    ratio = e2 / e1
    if e2 == 0.0:
        # A level pinned exactly at the band edge: the ratio is zero and its
        # error is the first term alone rather than an undefined product.
        return 0.0, float(s2 / e1)
    error = abs(ratio) * math.sqrt((s1 / e1) ** 2 + (s2 / e2) ** 2)
    return float(ratio), float(error)
