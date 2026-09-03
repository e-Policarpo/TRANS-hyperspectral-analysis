"""
Band edges, tails, and the question of whether a feature is real.

Every sharp feature in a dI/dV curve is convolved with two things the sample
knows nothing about: the Fermi-Dirac derivative of the tip at the measurement
temperature, and the lock-in modulation used to acquire the derivative. Both
are instrument, not physics. This module measures how much of what is on
screen could be either, so a band edge and a band tail can be reported with
the honest caveat attached.

Three questions, three answers:

1. **How sharp can anything possibly be?** :func:`resolution_fwhm` combines
   the thermal kernel (FWHM ``3.5251 k_B T / e`` volts) with the lock-in
   semi-ellipse (FWHM ``sqrt(3) V_mod`` zero-to-peak) in quadrature. Any
   structure narrower than that was drawn by the instrument.
2. **How steeply can a log-conductance rise?** :func:`thermal_slope_ceiling`
   returns ``1 / (k_B T)`` per volt: for a step-function density of states,
   thermal smearing alone gives ``d ln(dI/dV)/dV = 1/k_B T`` and nothing can
   be steeper. A measured slope sitting at the ceiling is a thermometer
   reading, and the "decay energy" derived from it is ``k_B T`` restated --
   it carries no sample information whatsoever. This is the single most
   common way an Urbach tail is over-interpreted.
3. **Where is the edge, and how disordered is it?**
   :func:`fit_two_regime` finds the one identifiable feature of an
   exponential band tail: the breakpoint between the steep in-gap decay and
   the shallower regime outside it.

**A single exponential branch cannot locate a band edge.** The model
``ln g = c - |V - V0| / E0`` is exactly degenerate in ``(c, V0)``: moving
``V0`` by ``d`` and ``c`` by ``d / E0`` reproduces the same curve sample for
sample. No fit, however well conditioned, can separate them. Only the
*breakpoint between two regimes* is identifiable, which is why the only
edge-position estimator here is a segmented one and why there is deliberately
no single-branch ``V0`` fit to be tempted by.

Like :mod:`src.processing.peak_detection` and
:mod:`src.processing.spectral_features`, this module is free of Qt, of file
I/O and of any TRANS data model: everything takes plain ``v``/``g`` arrays.

References
    Klein, Léger, Belin, Défourneau & Sangster, *Inelastic-electron-tunneling
    spectroscopy of metal-insulator-metal junctions*, Phys. Rev. B **7**, 2336
    (1973) -- the thermal and modulation broadening widths.

    Feenstra, Stroscio & Fein, *Tunneling spectroscopy of the Si(111)2x1
    surface*, Surf. Sci. **181**, 295 (1987) -- normalised conductance.

    Mårtensson & Feenstra, *Geometric and electronic structure of antimony on
    the GaAs(110) surface studied by scanning tunneling microscopy*,
    Phys. Rev. B **39**, 7744 (1989) -- broadening ``I/V`` to tame the
    divergence at zero bias.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
from scipy.ndimage import gaussian_filter1d
from scipy.signal import savgol_filter

from src.processing.peak_detection import thermal_broadening
from src.processing.positivity import positive_mask

logger = logging.getLogger(__name__)

#: Significance a breakpoint must reach before an edge position is reported.
#: A segmented fit ALWAYS returns a best split, including on a curve that is
#: one straight line in log space — the minimum of the SSE profile exists
#: whether or not there is anything there. Without this gate the function
#: reports a signed band edge, with an error bar, for a featureless spectrum,
#: and a map of it reads as structure. The two regimes must first be shown to
#: differ. See :func:`fit_two_regime` for the caveat on the test itself.
EDGE_P_THRESHOLD = 0.01

#: Smallest share of the branch's variance a breakpoint must explain before
#: the F-test is even consulted, as a fraction of the total sum of squares.
#: The F statistic is a RATIO of residuals, so on a curve the single line
#: already fits to machine precision both sums of squares are round-off and
#: their ratio is arbitrarily large: a noiseless pure exponential comes back
#: with p ~ 1e-147 and a confidently reported band edge in the middle of a
#: featureless curve. Requiring the improvement to be real in absolute terms
#: first closes that, and cannot suppress a genuine break — one line through
#: two regimes leaves a residual far above this floor.
MIN_BREAK_IMPROVEMENT = 1e-6

#: Fractional departure from the median step above which a bias axis counts
#: as non-uniform and the slopes are taken on a resampled grid instead.
GRID_UNIFORMITY_TOL = 1e-3


# ---------------------------------------------------------------------------
# Instrumental resolution
# ---------------------------------------------------------------------------

#: FWHM of ``-df/dE`` in units of ``k_B T``. The Fermi-Dirac derivative is
#: ``sech^2(x/2) / 4k_BT``; its half-maximum sits at ``x = 2 arccosh(sqrt 2)``,
#: so the full width is ``4 arccosh(sqrt 2) = 2 ln(3 + 2 sqrt 2) = 3.52549...``
#: -- quoted as 3.5251 by Klein et al. (1973) and kept at that value so numbers
#: here match the literature the caller is comparing against.
#: Kept as the exact closed form rather than the rounded 3.5251 usually
#: quoted: the literature value is low by 1.1e-4 relative, which costs
#: nothing physically but leaves an arbitrary constant in a module whose
#: whole job is to say what is resolvable and what is not.
THERMAL_FWHM_FACTOR = 4.0 * math.log(1.0 + math.sqrt(2.0))  # 3.5254943...

#: How a lock-in modulation amplitude is quoted, and the factor taking it to
#: the FWHM of the first-harmonic kernel. The kernel is the semi-ellipse
#: ``K(u) = (2 / pi V^2) sqrt(V^2 - u^2)``, half maximum at
#: ``u = sqrt(3)/2 V``, so the width is ``sqrt(3) V`` for ``V`` zero-to-peak.
#: An r.m.s. amplitude is ``V / sqrt 2`` and a peak-to-peak one is ``2 V``.
MODULATION_CONVENTIONS = {
    "zero_to_peak": math.sqrt(3.0),
    "rms": math.sqrt(6.0),
    "peak_to_peak": math.sqrt(3.0) / 2.0,
}


#: FWHM of a Savitzky-Golay derivative's response to a step, as a fraction of
#: the window length. **Measured, not a rule of thumb**: a step in I(V) is a
#: delta in dI/dV, so pushing one through the filter and reading the width of
#: what comes out gives the instrument function directly, exactly as the
#: lock-in semi-ellipse is one. The value depends only on the polynomial
#: order, and only through whether it is quadratic or cubic -- orders 1 and 2
#: share a filter, as do 3 and 4.
#:
#:     N       poly 1-2      poly 3-4
#:     11      0.727         0.364
#:     21      0.667         0.381
#:     51      0.706         0.431
#:     101     0.713         0.416
DERIVATIVE_FWHM_FRACTION = {1: 0.71, 2: 0.71, 3: 0.41, 4: 0.41}

#: The same measurement for a *smooth -> gradient -> smooth* pipeline, which
#: is what :meth:`ToolImplementations.calculate_derivative` runs and what most
#: hand-rolled dI/dV scripts do. Measured across N = 11 to 101: 0.55 N with
#: one smoothing pass, 0.50 N with two, against 0.41 N for a single-pass
#: Savitzky-Golay derivative at the same window and order.
#:
#: **A one-pass SG derivative is about 30 % sharper for the same window**, and
#: for the same reason: it differentiates the fitted polynomial instead of
#: filtering twice around a bare gradient. Worth knowing before choosing how
#: to make a dI/dV, though it is not something this module can fix after the
#: fact.
#:
#: 0.55 is the conservative end of the measured range. Erring toward a wider
#: instrument function means declaring fewer states resolved, which is the
#: safe direction for a number whose job is to say what may be believed.
PIPELINE_FWHM_FRACTION = 0.55

#: FWHM of a bare two-point gradient, in grid steps. Independent of any
#: window, because there is none.
GRADIENT_FWHM_STEPS = 2.0

DERIVATIVE_KINDS = ("savgol_deriv", "smooth_gradient")


def differentiation_fwhm(window_v: float, polyorder: int = 2,
                         kind: str = "savgol_deriv") -> float:
    """Resolution cost of computing dI/dV by differentiating I(V), in volts.

    A measurement taken **without a lock-in** has no modulation kernel, but it
    is not therefore thermally limited: the derivative has to be smoothed or
    it is pure noise, and that smoothing is an instrument function like any
    other. Its width is what this returns, so it can go into the resolution
    budget beside the thermal term instead of being quietly omitted.

    ``window_v`` is the differentiation window in volts (the Savitzky-Golay
    window length times the bias step). A higher ``polyorder`` follows the
    curve more closely and costs roughly half as much width, which is the one
    free improvement available here.

``kind`` says how the derivative was taken, because the two routes cost
    different amounts at the same window:

    * ``'savgol_deriv'`` -- one Savitzky-Golay pass with ``deriv=1``, which
      differentiates the fitted polynomial. 0.41 N at order 3.
    * ``'smooth_gradient'`` -- smooth, take a bare gradient, smooth again.
      What :meth:`ToolImplementations.calculate_derivative` does, and what
      most hand-rolled dI/dV scripts do. 0.55 N, about 30 % wider.

    Returns ``0.0`` for a non-positive window -- an exact analytic derivative,
    which no real measurement has.
    """
    if kind not in DERIVATIVE_KINDS:
        raise ValueError(
            f"kind must be one of {DERIVATIVE_KINDS}, got {kind!r}")
    window_v = abs(float(window_v))
    if window_v <= 0.0:
        return 0.0
    if kind == "smooth_gradient":
        return float(PIPELINE_FWHM_FRACTION * window_v)
    order = int(polyorder)
    try:
        fraction = DERIVATIVE_FWHM_FRACTION[order]
    except KeyError:
        raise ValueError(
            f"polyorder must be one of {tuple(DERIVATIVE_FWHM_FRACTION)}, "
            f"got {polyorder!r}")
    return float(fraction * window_v)


def resolution_fwhm(temperature_k: float, v_mod: float = 0.0,
                    convention: str = "zero_to_peak",
                    deriv_window_v: float = 0.0,
                    deriv_polyorder: int = 2,
                    deriv_kind: str = "savgol_deriv") -> float:
    """Narrowest feature the instrument can draw, in volts.

    Three independent widths, combined in quadrature:

    * **Thermal.** ``4 ln(1 + sqrt 2) k_B T``, always present.
    * **Lock-in modulation.** ``v_mod`` in whichever ``convention`` the
      acquisition software quotes. Zero for a measurement taken without one.
    * **Numerical differentiation.** ``deriv_window_v``, the window used to
      get dI/dV out of I(V). Zero when a lock-in supplied dI/dV directly.

    The last two are alternatives in practice: dI/dV is either detected at the
    modulation frequency or computed from I(V), never both. Passing both is
    allowed and simply adds their widths, but it usually means one of them was
    filled in by mistake.

    **Not having a lock-in does not make a measurement thermally limited.**
    That is the trap this argument exists to close: with no ``v_mod`` to quote,
    the modulation term is zero and the resolution looks like the thermal one
    alone -- while the differentiation window that actually produced the curve,
    often wider than ``3.5 k_B T``, goes unrecorded. At 94 K the thermal width
    is 28.6 mV, so a 50 mV window contributes 36 mV and *dominates* it.

    **This is an approximation**: none of the three kernels is Gaussian -- the
    thermal one is ``sech^2``, the modulation one a semi-ellipse -- and
    quadrature addition is exact only for Gaussians. Accurate to a few percent
    when one term dominates, optimistic by roughly 5 % when two are
    comparable. Use it as the resolution *scale*, not as a deconvolution
    kernel.

    A non-positive temperature contributes nothing, matching
    :func:`~src.processing.peak_detection.thermal_broadening`, so
    ``resolution_fwhm(0, 0)`` is ``0.0`` -- "no known limit", not "perfect".

    Klein et al., Phys. Rev. B 7, 2336 (1973).
    """
    try:
        factor = MODULATION_CONVENTIONS[convention]
    except KeyError:
        raise ValueError(
            f"convention must be one of {tuple(MODULATION_CONVENTIONS)}, "
            f"got {convention!r}")

    # A bias axis in volts is an energy axis in eV, so k_B * T needs no
    # conversion on the way out of thermal_broadening.
    # Deliberately the pure formula: a non-positive temperature contributes no
    # thermal term and the modulation kernel is returned on its own, which is
    # the only way to measure that kernel in isolation. Whether an unrecorded
    # temperature may be reported AS a resolution is a different question, and
    # it is answered one layer up in :func:`edge_summary`.
    thermal = THERMAL_FWHM_FACTOR * thermal_broadening(temperature_k, "eV")
    modulation = factor * abs(float(v_mod)) if v_mod else 0.0
    numerical = differentiation_fwhm(deriv_window_v, deriv_polyorder,
                                     deriv_kind)
    return float(math.sqrt(thermal ** 2 + modulation ** 2 + numerical ** 2))


def thermal_slope_ceiling(temperature_k: float) -> Tuple[float, float]:
    """Steepest possible ``d ln(dI/dV)/dV``, per volt and in decades per volt.

    A step in the density of states, convolved with ``-df/dE``, has
    exponential tails of decay energy exactly ``k_B T``. Nothing measured at
    that temperature can be steeper, so a fitted slope at the ceiling means
    the feature is resolution-limited and the decay energy read off it is the
    temperature restated -- not disorder, not an Urbach energy, not a band
    tail.

    Worth memorising, because it decides which experiments are worth doing::

        300 K ->    38.7 /V,    16.8 decades/V
         94 K ->   123.5 /V,    53.6 decades/V
         77 K ->   150.7 /V,    65.5 decades/V
        4.2 K ->  2763   /V,  1200   decades/V

    Returns ``(nan, nan)`` when the temperature is unknown or non-positive: an
    unmeasurable ceiling is undetermined, not infinite, and callers must not
    read it as "nothing is thermally limited".
    """
    kt_ev = thermal_broadening(temperature_k, "eV")
    if kt_ev <= 0 or not math.isfinite(kt_ev):
        return float("nan"), float("nan")
    per_volt = 1.0 / kt_ev
    return float(per_volt), float(per_volt / math.log(10.0))


# ---------------------------------------------------------------------------
# Local log-slopes
# ---------------------------------------------------------------------------

@dataclass
class LocalSlopes:
    """Point-by-point log-derivatives of a conductance curve.

    All four arrays are the same length as the input bias axis and stay
    aligned with it -- a sample that could not be used is NaN in place, never
    removed. Reindexing would break every downstream map, and a contiguous
    grid is what the derivative needs anyway.
    """

    s_exp: np.ndarray       # d ln(g) / dV, per volt
    s_pow: np.ndarray       # d ln(g) / d ln|V|, dimensionless
    ln_g: np.ndarray        # natural log of the conductance, NaN where unusable
    valid: np.ndarray       # bool: the sample carried a usable slope
    #: False when the bias axis was not uniformly spaced and the slopes had to
    #: be taken on a resampled grid. Recorded rather than hidden: the
    #: resampling is correct but it is interpolation, so a caller comparing
    #: two datasets should know which one needed it.
    uniform_grid: bool = True


def local_log_slopes(v: np.ndarray, g: np.ndarray,
                     window_v: Optional[float] = None,
                     polyorder: int = 2) -> LocalSlopes:
    """Exponential and power-law log-slopes at every bias.

    Two readings of the same derivative, and which one is flat tells you which
    law the curve obeys:

    ``s_exp = d ln(g) / dV``
        Flat over a stretch means ``g ~ exp(V / E0)``, an exponential tail of
        decay energy ``E0 = 1 / s_exp``. Compare its value against
        :func:`thermal_slope_ceiling` before believing it.
    ``s_pow = d ln(g) / d ln|V|``
        Flat means a power law ``g ~ |V|^p``, and the value *is* the exponent
        -- 1/2, 1 and 3/2 being the usual band-edge shapes.

    The two are the same measurement seen twice, related by
    ``s_pow = V * s_exp`` (which holds on the negative branch as well, since
    ``d ln|V| / dV = 1 / V`` for either sign). It is computed that way rather
    than by a second differentiation, so the identity is exact by
    construction. At ``V = 0`` the power-law slope is undefined and reported
    as NaN.

    The derivative is a Savitzky-Golay one taken on ``ln(g)``.  ``window_v``
    is a width in **volts**, converted to an odd sample count from the median
    grid spacing; ``None`` uses the narrowest honest window, which is noisy --
    a width comparable to :func:`resolution_fwhm` is usually what you want.
    A descending sweep is handled correctly (the spacing comes out negative
    and the sign follows).

    Samples where ``g`` is non-positive or non-finite cannot be logged. They
    are marked invalid and returned as NaN, but they are *not* dropped: the
    grid is bridged by interpolation so the filter still sees a contiguous
    axis, exactly as peak detection runs on the whole curve rather than on a
    re-indexed subset.
    """
    v = np.asarray(v, dtype=np.float64)
    g = np.asarray(g, dtype=np.float64)
    if v.shape != g.shape:
        raise ValueError(f"v has {v.size} samples but g has {g.size}")
    polyorder = int(polyorder)
    if polyorder < 1:
        raise ValueError(f"polyorder must be at least 1, got {polyorder}")

    n = v.size
    nan = np.full(n, np.nan, dtype=np.float64)
    blank = LocalSlopes(s_exp=nan.copy(), s_pow=nan.copy(), ln_g=nan.copy(),
                        valid=np.zeros(n, dtype=bool))

    # positive_mask keeps zero -- a real "no states here" reading -- but a
    # logarithm cannot, so zero is excluded here and only here.
    usable = positive_mask(g) & (g > 0.0) & np.isfinite(v)
    if usable.sum() < 2:
        return blank

    ln_g = np.full(n, np.nan, dtype=np.float64)
    ln_g[usable] = np.log(g[usable])

    steps = np.diff(v)
    dv = float(np.median(steps))
    if not math.isfinite(dv) or dv == 0.0:
        logger.debug("Degenerate bias axis: median spacing %r", dv)
        return blank

    # A Savitzky-Golay derivative reads the samples in the order they are
    # given. Hand it a shuffled sweep and it differentiates the shuffling:
    # measured on a pure |V|^2.7 curve, the recovered exponent came back as
    # -1.17 with no error raised anywhere. That is a caller bug, not data, so
    # it is refused rather than patched over by sorting -- the outputs are
    # aligned to the input samples and re-sorting them would be a silent
    # reordering of somebody's spectrum.
    if not (np.all(steps > 0) or np.all(steps < 0)):
        raise ValueError(
            "bias axis must be monotonic; local_log_slopes differentiates in "
            "sample order and cannot be given an unsorted sweep")

    # Uniform spacing is the other half of that assumption, and violating it
    # fails quietly rather than loudly: a single ``delta`` is right only where
    # the local step matches the median. On a geometric sweep the same 2.7
    # exponent came back spread over 0.70 to 10.46 while its *median* stayed
    # at 2.700, so a spot check cannot catch it. Resample instead of guessing.
    uniform = True
    if np.any(np.abs(steps - dv) > GRID_UNIFORMITY_TOL * abs(dv)):
        uniform = False
        logger.info("Non-uniform bias axis (spacing spread %.3g of the "
                    "median); taking slopes on a resampled grid",
                    float(np.max(np.abs(steps - dv)) / abs(dv)))

    window = _window_samples(window_v, dv, n, polyorder)
    if window is None:
        return blank

    # Bridge the unusable samples so the filter sees a contiguous curve. The
    # bridged values are thrown away below; they exist only so a single bad
    # sample does not blank out a whole window of good ones.
    bridged = np.interp(np.arange(n, dtype=np.float64),
                        np.flatnonzero(usable).astype(np.float64), ln_g[usable])

    try:
        if uniform:
            s_exp = savgol_filter(bridged, window, polyorder, deriv=1,
                                  delta=dv, mode="interp")
        else:
            # Uniform grid over the same span, differentiate there, and map
            # the slopes back onto the samples the caller handed in. np.interp
            # needs ascending x, so a descending sweep is flipped both ways.
            asc = dv > 0
            v_a = v if asc else v[::-1]
            b_a = bridged if asc else bridged[::-1]
            v_u = np.linspace(float(v_a[0]), float(v_a[-1]), n)
            du = float(v_u[1] - v_u[0])
            s_u = savgol_filter(np.interp(v_u, v_a, b_a), window, polyorder,
                                deriv=1, delta=du, mode="interp")
            s_a = np.interp(v_a, v_u, s_u)
            s_exp = s_a if asc else s_a[::-1]
    except Exception:
        logger.debug("Savitzky-Golay derivative failed", exc_info=True)
        return blank

    s_exp = np.where(usable, s_exp, np.nan)
    # The identity, encoded rather than re-derived.
    with np.errstate(all="ignore"):
        s_pow = np.where(v != 0.0, v * s_exp, np.nan)

    valid = usable & np.isfinite(s_exp)
    return LocalSlopes(s_exp=s_exp, s_pow=s_pow, ln_g=ln_g, valid=valid,
                       uniform_grid=uniform)


def _window_samples(window_v: Optional[float], dv: float, n: int,
                    polyorder: int) -> Optional[int]:
    """Odd Savitzky-Golay window in samples, or ``None`` if none will fit.

    ``polyorder + 2`` is the shortest window that still smooths rather than
    interpolates; anything longer than the curve cannot be used at all.
    """
    shortest = polyorder + 2
    if shortest % 2 == 0:
        shortest += 1
    if window_v is None:
        window = shortest
    else:
        window_v = float(window_v)
        if not math.isfinite(window_v) or window_v <= 0:
            raise ValueError(f"window_v must be positive, got {window_v!r}")
        window = int(round(window_v / abs(dv)))
        window = max(window, shortest)
        if window % 2 == 0:
            window += 1
    if window > n:
        # Fall back to the longest odd window the curve can carry.
        window = n if n % 2 else n - 1
    if window <= polyorder:
        logger.debug("Curve too short for a degree-%d derivative (%d samples)",
                     polyorder, n)
        return None
    return int(window)


# ---------------------------------------------------------------------------
# Normalised conductance
# ---------------------------------------------------------------------------

def feenstra_normalize(v: np.ndarray, current: np.ndarray, didv: np.ndarray,
                       broadening_v: float = 0.0) -> np.ndarray:
    """Normalised conductance ``(dI/dV) / (I/V)``.

    The tunnel current carries an exponential transmission factor that grows
    with bias and with the tip-sample separation the feedback happened to
    settle at. Raw dI/dV therefore compares two points on a surface partly by
    their density of states and partly by how far away the tip was; dividing
    by ``I/V`` cancels both the transmission factor and the constant-current
    setpoint to first order, which is what makes spectra from different
    positions comparable at all.

    ``I/V`` is ``0/0`` at zero bias and small either side of it, so the ratio
    diverges through the gap -- the well-known artefact of the method. Pass
    ``broadening_v > 0`` to smooth ``I/V`` with a Gaussian of that FWHM (in
    volts) before dividing, following Mårtensson & Feenstra: the smoothed
    denominator stays finite across the gap and the gap edges keep their
    positions. A value of order the gap width, or of the thermal resolution,
    is the usual choice.

    Wherever ``I/V`` comes out zero or non-finite the result is NaN, never a
    number: an infinity here would otherwise propagate into every fit and map
    downstream.

    Feenstra, Stroscio & Fein, Surf. Sci. 181, 295 (1987).
    """
    v = np.asarray(v, dtype=np.float64)
    current = np.asarray(current, dtype=np.float64)
    didv = np.asarray(didv, dtype=np.float64)
    if not (v.shape == current.shape == didv.shape):
        raise ValueError(
            f"v, current and didv must match: got {v.size}, {current.size}, "
            f"{didv.size} samples")

    with np.errstate(all="ignore"):
        ratio = np.where(v != 0.0, current / v, np.nan)

    broadening_v = float(broadening_v)
    if broadening_v > 0:
        ratio = _gaussian_smooth(v, ratio, broadening_v)

    with np.errstate(all="ignore"):
        out = didv / ratio
    return np.where(np.isfinite(ratio) & (ratio != 0.0) & np.isfinite(out),
                    out, np.nan)


def _gaussian_smooth(v: np.ndarray, y: np.ndarray, fwhm_v: float) -> np.ndarray:
    """Gaussian smoothing of ``y`` with a FWHM given in volts.

    NaN samples (the zero-bias hole in ``I/V``) are bridged by interpolation
    first: ``gaussian_filter1d`` would otherwise smear a single NaN across the
    whole kernel and take the gap interior with it.
    """
    finite = np.isfinite(y)
    if finite.sum() < 2:
        return y
    dv = float(np.median(np.diff(v)))
    if not math.isfinite(dv) or dv == 0.0:
        return y
    sigma_samples = (fwhm_v / (2.0 * math.sqrt(2.0 * math.log(2.0)))) / abs(dv)
    if not math.isfinite(sigma_samples) or sigma_samples <= 0:
        return y
    idx = np.arange(y.size, dtype=np.float64)
    bridged = np.interp(idx, idx[finite], y[finite])
    return gaussian_filter1d(bridged, sigma_samples, mode="nearest")


# ---------------------------------------------------------------------------
# Two-regime (band tail / band edge) fit
# ---------------------------------------------------------------------------

BRANCHES = ("neg", "pos")

#: Free parameters of the segmented model: two slopes and two intercepts. It
#: sets the dof used for the breakpoint's error bar.
_SEGMENT_DOF = 4


@dataclass
class TwoRegimeFit:
    """One branch's segmented fit of ``ln(g)`` against ``|V|``.

    Fitting against ``|V|`` rather than signed ``V`` makes the two branches
    read the same way: the first segment is always the small-``|V|`` one, i.e.
    the tail reaching into the gap, and the second is always the shallower
    regime outside the edge. ``slope_in`` and ``slope_out`` are therefore
    ``d ln(g) / d|V|``; only their magnitudes are used for the decay energies,
    which is the quantity that has a sign-independent meaning.

    ``v_edge`` is handed back **signed**, on the branch it came from, so it
    can be plotted straight onto the spectrum.
    """

    v_edge: float = float("nan")        # breakpoint bias, signed, volts
    v_edge_err: float = float("nan")    # half-width of the 1-sigma SSE basin
    e_in_ev: float = float("nan")       # 1/|slope_in|: the in-gap decay energy
    e_out_ev: float = float("nan")      # 1/|slope_out|: outside the edge
    slope_in: float = float("nan")      # d ln(g)/d|V|, small |V| side
    slope_out: float = float("nan")     # d ln(g)/d|V|, large |V| side
    r2: float = float("nan")
    f_stat: float = float("nan")        # segmented vs one line
    p_value: float = float("nan")       # of f_stat; see the caveat below
    edge_significant: bool = False      # p_value < EDGE_P_THRESHOLD
    n_points: int = 0
    thermally_limited: bool = False
    valid: bool = False
    reason: str = ""


def fit_two_regime(v: np.ndarray, g: np.ndarray, branch: str,
                   temperature_k: float, n_kt: float = 3.0,
                   min_points: int = 8) -> TwoRegimeFit:
    """Locate the band edge as the breakpoint between two exponential regimes.

    **The band-edge position is only identifiable because there are two
    regimes.** A single exponential branch cannot give it: in
    ``ln g = c - |V - V0| / E0`` the pair ``(c, V0)`` is exactly degenerate,
    since moving ``V0`` by ``d`` and ``c`` by ``d / E0`` reproduces the curve
    sample for sample. Any "edge position" from a one-segment fit is whatever
    the initial guess was. The breakpoint between a steep in-gap tail and a
    shallower outside regime *is* identifiable, and it is the only edge
    estimator offered here.

    ``branch`` selects ``"neg"`` (``V < 0``) or ``"pos"`` (``V > 0``). Samples
    with ``|V| < n_kt * k_B T / e`` are excluded: inside that window the curve
    is rounded by the resolution rather than shaped by the sample, and
    including it drags the in-gap slope towards the thermal ceiling and
    invents disorder that is not there. With an unknown temperature nothing is
    excluded and the ceiling test cannot fire.

    The breakpoint is grid-searched over every interior sample leaving at
    least ``min_points`` on each side; each side is a least-squares line and
    the winner is the smallest total SSE. ``v_edge_err`` is read off the SSE
    profile -- the span over which SSE stays within its one-parameter
    ``1 sigma`` rise, ``SSE_min * (1 + 1/(n - 4))`` -- and is NaN when that
    basin runs to the end of the search range, i.e. when the breakpoint is not
    bounded by the data at all.

    ``thermally_limited`` is set when ``|slope_in|`` reaches 90 % of
    :func:`thermal_slope_ceiling`. When it is true, ``e_in_ev`` is still
    reported but means ``k_B T``, not an Urbach energy. It stays ``False`` for
    an unknown temperature, where the claim cannot be made either way.
    """
    if branch not in BRANCHES:
        raise ValueError(f"branch must be one of {BRANCHES}, got {branch!r}")
    min_points = int(min_points)
    if min_points < 2:
        raise ValueError(f"min_points must be at least 2, got {min_points}")

    v = np.asarray(v, dtype=np.float64)
    g = np.asarray(g, dtype=np.float64)
    if v.shape != g.shape:
        raise ValueError(f"v has {v.size} samples but g has {g.size}")

    kt_ev = thermal_broadening(temperature_k, "eV")
    cutoff = float(n_kt) * kt_ev if kt_ev > 0 else 0.0

    on_branch = (v < 0.0) if branch == "neg" else (v > 0.0)
    usable = on_branch & positive_mask(g) & (g > 0.0) & (np.abs(v) >= cutoff)
    n = int(usable.sum())
    if n < 2 * min_points:
        return TwoRegimeFit(n_points=n, reason="too few usable samples")

    # |V| ascending, so index 0 is deepest inside the gap on either branch.
    u = np.abs(v[usable])
    order = np.argsort(u, kind="stable")
    u = u[order]
    ln_g = np.log(g[usable][order])

    best = _best_breakpoint(u, ln_g, min_points)
    if best is None:
        return TwoRegimeFit(n_points=n, reason="no admissible breakpoint")
    k, sse, sse_profile, candidates = best

    slope_in, _ = _line(u[:k], ln_g[:k])
    slope_out, _ = _line(u[k:], ln_g[k:])
    if not (math.isfinite(slope_in) and math.isfinite(slope_out)):
        return TwoRegimeFit(n_points=n, reason="degenerate segment")

    ss_tot = float(np.sum((ln_g - ln_g.mean()) ** 2))
    r2 = 1.0 - sse / ss_tot if ss_tot > 0 else float("nan")

    # Does the break earn its two extra parameters? Compare the segmented fit
    # against one line over the whole branch. Without this the minimum of the
    # SSE profile is reported as an edge even when the curve is featureless.
    sse_single = _sse(u, ln_g)
    f_stat = float("nan")
    p_value = float("nan")
    gain = ((sse_single - sse) / ss_tot
            if ss_tot > 0 and math.isfinite(sse_single) else 0.0)
    worth_testing = math.isfinite(gain) and gain > MIN_BREAK_IMPROVEMENT
    if worth_testing and n > 4 and sse > 0.0:
        f_stat = ((sse_single - sse) / 2.0) / (sse / (n - 4))
        if math.isfinite(f_stat) and f_stat >= 0.0:
            p_value = float(stats.f.sf(f_stat, 2, n - 4))
    significant = bool(worth_testing and math.isfinite(p_value)
                       and p_value < EDGE_P_THRESHOLD)

    edge_u = 0.5 * (u[k - 1] + u[k])
    err = _breakpoint_error(u, candidates, sse_profile, sse, n)
    reason = ""
    if not significant:
        # The slopes are still reported — on a single-regime curve they are two
        # estimates of the same decay energy, which is a real reading. Only the
        # edge is withheld, because there is no evidence of one.
        edge_u = float("nan")
        err = float("nan")
        reason = ("the two regimes are not distinguishable "
                  f"(p = {p_value:.3g}); no band edge reported")

    ceiling, _ = thermal_slope_ceiling(temperature_k)
    limited = bool(math.isfinite(ceiling) and abs(slope_in) >= 0.9 * ceiling)

    sign = -1.0 if branch == "neg" else 1.0
    return TwoRegimeFit(
        v_edge=float(sign * edge_u) if math.isfinite(edge_u) else float("nan"),
        v_edge_err=float(err),
        f_stat=float(f_stat),
        p_value=float(p_value),
        edge_significant=significant,
        reason=reason,
        e_in_ev=1.0 / abs(slope_in) if slope_in else float("nan"),
        e_out_ev=1.0 / abs(slope_out) if slope_out else float("nan"),
        slope_in=float(slope_in),
        slope_out=float(slope_out),
        r2=float(r2),
        n_points=n,
        thermally_limited=limited,
        valid=True,
    )


def _line(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """Least-squares slope and intercept, ``(nan, nan)`` on a degenerate fit."""
    if x.size < 2:
        return float("nan"), float("nan")
    span = float(np.max(x) - np.min(x))
    if not math.isfinite(span) or span == 0.0:
        return float("nan"), float("nan")
    try:
        with np.errstate(all="ignore"):
            slope, intercept = np.polyfit(x, y, 1)
    except Exception:
        logger.debug("Segment fit failed", exc_info=True)
        return float("nan"), float("nan")
    return float(slope), float(intercept)


def _best_breakpoint(u: np.ndarray, ln_g: np.ndarray, min_points: int):
    """Grid-search the split minimising the summed SSE of the two lines.

    Returns ``(k, sse, sse_profile, candidates)`` where the split puts
    ``u[:k]`` inside and ``u[k:]`` outside, or ``None`` when no split leaves
    ``min_points`` on both sides.
    """
    n = u.size
    candidates = np.arange(min_points, n - min_points + 1, dtype=np.intp)
    if candidates.size == 0:
        return None

    sse_profile = np.full(candidates.size, np.inf, dtype=np.float64)
    for j, k in enumerate(candidates):
        left = _sse(u[:k], ln_g[:k])
        right = _sse(u[k:], ln_g[k:])
        if math.isfinite(left) and math.isfinite(right):
            sse_profile[j] = left + right

    if not np.isfinite(sse_profile).any():
        return None
    j = int(np.argmin(sse_profile))
    return int(candidates[j]), float(sse_profile[j]), sse_profile, candidates


def _sse(x: np.ndarray, y: np.ndarray) -> float:
    """Residual sum of squares of a straight line through ``(x, y)``."""
    slope, intercept = _line(x, y)
    if not math.isfinite(slope):
        return float("inf")
    resid = y - (slope * x + intercept)
    return float(np.dot(resid, resid))


def _breakpoint_error(u: np.ndarray, candidates: np.ndarray,
                      sse_profile: np.ndarray, sse_min: float, n: int) -> float:
    """Half-width of the SSE basin around the chosen breakpoint, in volts.

    The one-parameter ``1 sigma`` rise of a sum of squares is
    ``SSE_min * (1 + 1/(n - p))`` with ``p`` the number of fitted parameters.
    The basin is the contiguous run of breakpoints staying under that. If it
    reaches either end of the search range the breakpoint is not bounded by
    the data and the error is NaN -- reporting the half-range instead would
    dress an unconstrained fit up as a measurement.
    """
    if not math.isfinite(sse_min) or sse_min <= 0 or candidates.size < 2:
        return float("nan")
    dof = max(n - _SEGMENT_DOF, 1)
    threshold = sse_min * (1.0 + 1.0 / dof)

    j = int(np.argmin(sse_profile))
    lo = j
    while lo > 0 and sse_profile[lo - 1] <= threshold:
        lo -= 1
    hi = j
    while hi < candidates.size - 1 and sse_profile[hi + 1] <= threshold:
        hi += 1
    if lo == 0 or hi == candidates.size - 1:
        return float("nan")

    edges = np.array([0.5 * (u[k - 1] + u[k]) for k in candidates[[lo, hi]]])
    half = 0.5 * float(edges[1] - edges[0])
    if half > 0:
        return half
    # A basin one candidate wide is still a bound: the grid itself.
    step = float(np.median(np.diff(u)))
    return 0.5 * abs(step) if math.isfinite(step) and step else float("nan")


# ---------------------------------------------------------------------------
# One flat row per spectrum
# ---------------------------------------------------------------------------

def edge_columns() -> List[str]:
    """Column order of :func:`edge_summary`. Stable, so tables line up.

    Deliberately shaped like
    :func:`src.processing.spectral_features.feature_columns` so the two rows
    can be merged later without renaming anything. ``Spectrum_Index`` is not
    included: it belongs to whichever batch loop owns the table, exactly as it
    does there.
    """
    return [
        "valid",
        "e0_neg", "e0_pos",
        "e_out_neg", "e_out_pos",
        "v_edge_neg", "v_edge_pos",
        "v_edge_err_neg", "v_edge_err_pos",
        "thermally_limited_neg", "thermally_limited_pos",
        "resolution_fwhm", "slope_ceiling", "slope_ceiling_decades",
        "feenstra_normalized",
    ]


def edge_summary(v: np.ndarray, g: np.ndarray, temperature_k: float,
                 v_mod: float = 0.0, current: Optional[np.ndarray] = None,
                 convention: str = "zero_to_peak",
                 broadening_v: float = 0.0, n_kt: float = 3.0,
                 min_points: int = 8, deriv_window_v: float = 0.0,
                 deriv_polyorder: int = 2,
                 deriv_kind: str = "savgol_deriv") -> Dict[str, float]:
    """Both branches' edge and tail numbers as one flat row.

    Every value is a scalar, so the row drops straight into a feature table
    and therefore into a spatial map: ``e0_neg`` across a scan is a map of
    valence-tail disorder, ``v_edge_pos`` a map of the conduction edge, and
    ``thermally_limited_*`` the map that says which of the other two you are
    allowed to believe.

    Pass ``current`` to run the fits on the Feenstra-normalised conductance
    instead of the raw one -- worth doing whenever spectra from different
    positions are being compared, since raw dI/dV carries the tip height. The
    returned ``feenstra_normalized`` flag records which curve was actually
    fitted, so a table never silently mixes the two.

    Anything that could not be determined is NaN. ``valid`` is 1.0 when at
    least one branch produced a fit -- one good branch is a real, if partial,
    measurement, and dropping the row would throw it away.
    """
    v = np.asarray(v, dtype=np.float64)
    g = np.asarray(g, dtype=np.float64)

    normalized = False
    curve = g
    if current is not None:
        try:
            curve = feenstra_normalize(v, current, g, broadening_v)
            normalized = True
        except Exception:
            logger.warning("Feenstra normalisation failed; fitting raw dI/dV",
                           exc_info=True)
            curve = g

    ceiling, decades = thermal_slope_ceiling(temperature_k)
    row: Dict[str, float] = dict.fromkeys(edge_columns(), float("nan"))
    row.update({
        # NaN, not the modulation term alone, when nobody recorded the
        # temperature: a row saying "resolution = 17 meV" for a measurement
        # whose thermal kernel is unknown is a confident number standing in
        # for a missing one, and this row is what a map is coloured by.
        "resolution_fwhm": (resolution_fwhm(temperature_k, v_mod, convention,
                                            deriv_window_v, deriv_polyorder,
                                            deriv_kind)
                            if temperature_k and temperature_k > 0
                            else float("nan")),
        "slope_ceiling": ceiling,
        "slope_ceiling_decades": decades,
        "feenstra_normalized": 1.0 if normalized else 0.0,
    })

    any_valid = False
    for branch, suffix in (("neg", "neg"), ("pos", "pos")):
        try:
            fit = fit_two_regime(v, curve, branch, temperature_k,
                                 n_kt=n_kt, min_points=min_points)
        except Exception:
            logger.warning("Two-regime fit failed on the %s branch", branch,
                           exc_info=True)
            continue
        if not fit.valid:
            logger.debug("No %s-branch edge fit: %s", branch, fit.reason)
            continue
        any_valid = True
        row[f"e0_{suffix}"] = fit.e_in_ev
        row[f"e_out_{suffix}"] = fit.e_out_ev
        row[f"v_edge_{suffix}"] = fit.v_edge
        row[f"v_edge_err_{suffix}"] = fit.v_edge_err
        # An unknown ceiling leaves this undetermined, not 0.0: on a map,
        # zero reads as "confirmed not limited", which is exactly the claim
        # thermal_slope_ceiling refuses to make without a temperature.
        row[f"thermally_limited_{suffix}"] = (
            1.0 if fit.thermally_limited else
            0.0 if math.isfinite(ceiling) else float("nan"))

    row["valid"] = 1.0 if any_valid else 0.0
    return row
