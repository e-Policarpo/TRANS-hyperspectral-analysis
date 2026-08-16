"""
Background estimation and peak detection for spectral curves.

This is the shared engine behind the Confinement Analysis tool and the
baseline modes of the Curve Fitting tool. It is deliberately free of Qt, of
file I/O and of any TRANS data model: everything here takes plain ``x``/``y``
arrays, so it can be tested and reasoned about on its own.

Two halves:

**Background estimation** — ``estimate_baseline`` dispatches to six methods.
Three of them (``als``, ``rubberband``, ``endpoints``) were moved here
unchanged from ``backend.tool_implementations`` so both tools share one
implementation. Two are new (``poly``, ``poly-iter``), and ``none`` disables
the step.

**Peak detection** — ``analyze`` follows the QtiPlot "Localizar picos" model:
restrict to a search window, optionally smooth, optionally subtract a
background, optionally smooth the first derivative, then take the ``+ -> -``
sign changes of ``dy/dx`` as candidates and filter them by a percentage
height threshold. The threshold is measured on the background-corrected
curve inside the window, which is what lets small in-gap features clear it
without hand-picking a narrow range around them.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
import math
import warnings
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

import numpy as np
from scipy import signal as _signal

logger = logging.getLogger(__name__)


# =============================================================================
# Smoothing
# =============================================================================

SMOOTHER_KINDS = ("none", "average", "savgol")


def moving_average(y: np.ndarray, half_width: int) -> np.ndarray:
    """Centred moving average spanning ``2 * half_width + 1`` samples."""
    window = 2 * int(half_width) + 1
    if window < 3 or window > len(y):
        return y
    padded = np.pad(y, int(half_width), mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


def savgol(y: np.ndarray, half_width: int, polyorder: int = 2) -> np.ndarray:
    """Savitzky-Golay filter over ``2 * half_width + 1`` samples."""
    window = 2 * int(half_width) + 1
    if window < 3 or window > len(y):
        return y
    return _signal.savgol_filter(y, window_length=window, polyorder=min(polyorder, window - 1))


def smooth(y: np.ndarray, kind: str, half_width: int) -> np.ndarray:
    """Apply the named smoother. ``half_width < 1`` or ``none`` is a no-op."""
    if int(half_width) < 1 or kind == "none":
        return y
    if kind == "average":
        return moving_average(y, half_width)
    if kind == "savgol":
        return savgol(y, half_width)
    raise ValueError(f"Unknown smoother {kind!r}; expected one of {SMOOTHER_KINDS}")


# =============================================================================
# Background estimation
# =============================================================================

BASELINE_KINDS = ("none", "poly", "poly-iter", "als", "rubberband", "endpoints")

#: Methods that ignore ``degree``/``iterations`` and take their own parameters.
BASELINE_DESCRIPTIONS = {
    "none": "No background subtraction",
    "poly": "Least-squares polynomial through every point",
    "poly-iter": "Iterative peak stripping (ModPoly) — follows the background, ignores the peaks",
    "als": "Asymmetric Least Squares — smooth baseline pushed below the peaks",
    "rubberband": "Convex-hull rubber band under the spectrum",
    "endpoints": "Polynomial fitted to the spectrum endpoints only",
}


POLYNOMIAL_BASES = ("power", "legendre", "chebyshev")

#: Column-name prefix per basis, so a coefficient table says which one it is.
#: P_n and T_n are the usual symbols for Legendre and Chebyshev polynomials.
BASIS_PREFIX = {"power": "c", "legendre": "P", "chebyshev": "T"}

_BASIS_FIT = {
    "power": np.polynomial.polynomial.polyfit,
    "legendre": np.polynomial.legendre.legfit,
    "chebyshev": np.polynomial.chebyshev.chebfit,
}
_BASIS_EVAL = {
    "power": np.polynomial.polynomial.polyval,
    "legendre": np.polynomial.legendre.legval,
    "chebyshev": np.polynomial.chebyshev.chebval,
}


def normalized_axis(x: np.ndarray) -> np.ndarray:
    """Map ``x`` onto [-1, 1], where the orthogonal bases are orthogonal.

    Also what keeps the fit conditioned: an STS axis of +/-0.6 V against a
    y of ~1e-7 gives a Vandermonde matrix that degrades fast with degree.
    """
    x = np.asarray(x, dtype=np.float64)
    span = float(np.max(x) - np.min(x))
    centre = float(np.mean(x))
    return (x - centre) / (span / 2.0) if span > 0 else x - centre


def fit_polynomial(t: np.ndarray, y: np.ndarray, degree: int,
                   basis: str = "power") -> np.ndarray:
    """Least-squares polynomial fit in the given basis.

    Coefficients come back in **ascending order** (index 0 is the constant /
    zeroth-order term) for every basis, matching the ``c0..cN`` convention the
    Curve Fitting tool already exports.

    ``t`` should be on [-1, 1] (see :func:`normalized_axis`) for the
    orthogonal bases -- that is the interval on which they are orthogonal, and
    orthogonality is the point: it decorrelates the coefficients so they can
    be compared between spectra and fed to PCA. Monomial coefficients trade
    off against each other and shift wholesale when the fit window changes.
    """
    if basis not in POLYNOMIAL_BASES:
        raise ValueError(f"basis must be one of {POLYNOMIAL_BASES}, got {basis!r}")
    return np.asarray(_BASIS_FIT[basis](t, y, int(degree)), dtype=np.float64)


def eval_polynomial(coeffs: np.ndarray, t: np.ndarray, basis: str = "power") -> np.ndarray:
    """Evaluate ascending-order ``coeffs`` from :func:`fit_polynomial`."""
    if basis not in POLYNOMIAL_BASES:
        raise ValueError(f"basis must be one of {POLYNOMIAL_BASES}, got {basis!r}")
    return np.asarray(_BASIS_EVAL[basis](t, coeffs), dtype=np.float64)


def coefficient_names(degree: int, basis: str = "power") -> List[str]:
    """Column names for a coefficient table, e.g. ``P0..P4`` for Legendre."""
    prefix = BASIS_PREFIX.get(basis, "c")
    return [f"{prefix}{n}" for n in range(int(degree) + 1)]


def als_baseline(y: np.ndarray, lam: float = 1e5, p: float = 0.01, niter: int = 10) -> np.ndarray:
    """
    Asymmetric Least Squares baseline correction.

    This method iteratively fits a smooth baseline that stays below the peaks,
    making it ideal for spectroscopy data where you want to preserve peak features.

    Parameters:
    -----------
    y : array
        Input spectrum
    lam : float
        Smoothness parameter (larger = smoother baseline). Default 1e5.
    p : float
        Asymmetry parameter (smaller = baseline pushed below peaks). Default 0.01.
    niter : int
        Number of iterations. Default 10.

    Returns:
    --------
    baseline : array
        Estimated baseline
    """
    from scipy import sparse
    from scipy.sparse.linalg import spsolve

    L = len(y)
    D = sparse.diags([1, -2, 1], [0, -1, -2], shape=(L, L - 2))
    D = lam * D.dot(D.T)
    w = np.ones(L)

    for _ in range(niter):
        W = sparse.spdiags(w, 0, L, L)
        Z = W + D
        z = spsolve(Z, w * y)
        w = p * (y > z) + (1 - p) * (y < z)

    return z


def rubberband_baseline(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """
    Rubber band baseline correction using convex hull.

    Creates a baseline by stretching a "rubber band" under the spectrum,
    touching only the lowest points. Good for spectra with broad features.

    Parameters:
    -----------
    x : array
        Independent variable (e.g., voltage)
    y : array
        Spectrum values

    Only the LOWER boundary of the hull is used. ``ConvexHull.vertices``
    returns the whole closed polygon, and the largest ``y`` is by definition
    one of its vertices, so interpolating across all of them anchors the
    "baseline" on the peak apex: it comes out as a tent pitched over the peak,
    which erases the peak on subtraction and drives the flanks negative. Walk
    counter-clockwise from the leftmost point to the rightmost instead and you
    get the floor of the data, which is what a rubber band actually does.

    Returns:
    --------
    baseline : array
        Estimated baseline
    """
    from scipy.spatial import ConvexHull

    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    try:
        # Work on an ascending axis so hull-vertex order matches x order; STS
        # sweeps are sometimes stored descending.
        order = np.argsort(x)
        xs, ys = x[order], y[order]

        vertices = ConvexHull(np.column_stack([xs, ys])).vertices
        # scipy lists 2-D hull vertices counter-clockwise, so the run from the
        # leftmost point to the rightmost one is exactly the lower boundary.
        vertices = np.roll(vertices, -int(vertices.argmin()))
        vertices = vertices[: int(vertices.argmax()) + 1]

        baseline = np.empty_like(ys)
        baseline[order] = np.interp(xs, xs[vertices], ys[vertices])
    except Exception:
        # Fallback to linear if convex hull fails (collinear or degenerate input)
        baseline = np.linspace(y[0], y[-1], len(y))

    return baseline


def endpoint_baseline(x: np.ndarray, y: np.ndarray, n_points: int = 10, degree: int = 1,
                      basis: str = "power") -> np.ndarray:
    """
    Endpoint-based baseline correction.

    Fits a polynomial only to the endpoints of the spectrum, preserving
    features in the middle. Ideal for STS data where you want to remove
    a linear/polynomial trend but keep the peaks.

    Parameters:
    -----------
    x : array
        Independent variable
    y : array
        Spectrum values
    n_points : int
        Number of points to use from each end. Default 10.
    degree : int
        Polynomial degree for the fit. Default 1 (linear).

    Returns:
    --------
    baseline : array
        Estimated baseline
    """
    # Use points from both ends
    n = min(n_points, len(y) // 4)  # Don't use more than 25% from each end

    # Fit on the normalised axis so the orthogonal bases are orthogonal over
    # the spectrum's own range, not over whatever volts happen to be on it.
    t = normalized_axis(x)
    t_ends = np.concatenate([t[:n], t[-n:]])
    y_ends = np.concatenate([y[:n], y[-n:]])

    return eval_polynomial(fit_polynomial(t_ends, y_ends, degree, basis), t, basis)


def polynomial_baseline(
    x: np.ndarray,
    y: np.ndarray,
    kind: str = "poly-iter",
    degree: int = 3,
    iterations: int = 25,
    direction: str = "positive",
    tol: float = 1e-4,
    basis: str = "power",
) -> np.ndarray:
    """Polynomial background, either plain or by iterative peak stripping.

    ``poly``
        Plain least-squares polynomial through all the points. The peaks
        themselves pull the fit up, so it only suits gentle drift with few
        peaks.
    ``poly-iter``
        Iterative peak stripping (ModPoly, Lieber & Mahadevan-Jansen): fit,
        clip away everything that sticks out on the peak side, refit, repeat.
        The fit converges onto the background and ignores the peaks, which is
        what makes small in-gap features survive a percentage height threshold
        that the band edges would otherwise dominate.
    """
    if kind == "none" or degree < 0 or len(y) <= degree + 1:
        return np.zeros_like(y)

    # Condition the Vandermonde matrix: x is often ~1e-1 while y is ~1e-7.
    t = normalized_axis(x)

    scale = float(np.max(np.abs(y)))
    if scale == 0 or not math.isfinite(scale):
        return np.zeros_like(y)
    ys = y / scale

    with np.errstate(all="ignore"):
        def _fit(values):
            return eval_polynomial(fit_polynomial(t, values, degree, basis), t, basis)

        fit = _fit(ys)
        if kind == "poly":
            return fit * scale

        # poly-iter: clip on the side the peaks stick out of.
        #
        # The comparison is against the ORIGINAL spectrum each pass, per
        # Lieber & Mahadevan-Jansen. Clipping against the running result
        # instead lets the baseline creep away from the background in the
        # peak-free regions, and it gets worse with more iterations rather
        # than converging.
        clip = np.minimum if direction != "negative" else np.maximum
        for _ in range(max(1, int(iterations))):
            z = clip(ys, fit)
            new_fit = _fit(z)
            delta = float(np.max(np.abs(new_fit - fit)))
            fit = new_fit
            if delta <= tol * max(1e-12, float(np.max(np.abs(fit)))):
                break

    return fit * scale


def estimate_baseline(
    x: np.ndarray,
    y: np.ndarray,
    kind: str = "none",
    degree: int = 3,
    iterations: int = 25,
    direction: str = "positive",
    als_lambda: float = 1e5,
    als_p: float = 0.01,
    endpoint_points: int = 10,
    basis: str = "power",
) -> np.ndarray:
    """Dispatch to one of :data:`BASELINE_KINDS`, returning the background curve.

    Always returns an array the same shape as ``y``; ``none`` returns zeros so
    callers can subtract unconditionally.
    """
    if kind == "none":
        return np.zeros_like(y)
    if kind in ("poly", "poly-iter"):
        return polynomial_baseline(x, y, kind, degree, iterations, direction, basis=basis)
    if kind == "als":
        return np.asarray(als_baseline(y, lam=als_lambda, p=als_p), dtype=np.float64)
    if kind == "rubberband":
        return np.asarray(rubberband_baseline(x, y), dtype=np.float64)
    if kind == "endpoints":
        return np.asarray(
            endpoint_baseline(x, y, n_points=endpoint_points, degree=degree, basis=basis),
            dtype=np.float64)
    raise ValueError(f"Unknown background method {kind!r}; expected one of {BASELINE_KINDS}")


# =============================================================================
# Peak detection
# =============================================================================

DIRECTIONS = ("positive", "negative", "both")
HEIGHT_MODES = ("range", "prominence", "max")

#: Boltzmann constant in eV/K. An STS bias axis in volts is an energy axis in
#: eV, so k_B * T lands directly in x-axis units.
KB_EV_PER_K = 8.617333262e-5

#: Multiplier from eV to the x-axis unit.
ENERGY_UNITS = {"eV": 1.0, "meV": 1000.0}


def thermal_broadening(temperature_k: float, x_energy_unit: str = "eV") -> float:
    """k_B * T in x-axis units -- the resolution limit at that temperature.

    Two peaks closer together than this are not thermally distinguishable, so
    it doubles as the error bar on a peak position. 94 K gives 8.1 meV.
    Returns 0.0 when disabled, which callers read as "no grouping".
    """
    if not temperature_k or temperature_k <= 0:
        return 0.0
    try:
        scale = ENERGY_UNITS[x_energy_unit]
    except KeyError:
        raise ValueError(
            f"x_energy_unit must be one of {tuple(ENERGY_UNITS)}, got {x_energy_unit!r}")
    return KB_EV_PER_K * float(temperature_k) * scale


def energy_bins(x: np.ndarray, width: float) -> tuple:
    """Edges and centres of ``width``-wide bins spanning ``x``.

    The grid is anchored on zero rather than on the data, so the same
    temperature gives the same bins across datasets with different sweep
    ranges -- otherwise two measurements could not be compared bin by bin.
    """
    if width <= 0:
        raise ValueError(f"bin width must be positive, got {width}")
    lo, hi = float(np.min(x)), float(np.max(x))
    first = math.floor(lo / width)
    last = math.ceil(hi / width)
    edges = (np.arange(first, last + 1, dtype=np.float64)) * width
    if len(edges) < 2:
        edges = np.array([first * width, (first + 1) * width])
    return edges, edges[:-1] + width / 2.0


def assign_bins(values, edges: np.ndarray) -> np.ndarray:
    """Index of the bin each value falls in, clamped to the edge bins."""
    values = np.atleast_1d(np.asarray(values, dtype=np.float64))
    if values.size == 0:
        return np.empty(0, dtype=np.intp)
    idx = np.searchsorted(edges, values, side="right") - 1
    return np.clip(idx, 0, len(edges) - 2).astype(np.intp)


@dataclass
class Peak:
    """One detected peak, indexed against the full (unwindowed) spectrum."""

    index: int              # row index into the full spectrum
    x: float                # centre, on the grid unless interpolate_center
    y: float                # height on the raw curve
    y_corrected: float      # height with the background removed
    prominence: float


@dataclass
class Params:
    """Every knob the Confinement Analysis tool exposes.

    Mirrors the QtiPlot "Localizar picos" dialog, plus the background block.
    ``*_points`` values are half-widths: 2 means a 5-sample window.
    """

    # Dados
    xmin: Optional[float] = None
    xmax: Optional[float] = None
    # Fundo (background)
    baseline: str = "none"
    baseline_degree: int = 3
    baseline_iterations: int = 25
    als_lambda: float = 1e5
    als_p: float = 0.01
    endpoint_points: int = 10
    baseline_basis: str = "power"
    # Filtro
    direction: str = "positive"
    height: float = 5.0
    height_mode: str = "range"
    smooth_type: str = "average"
    smooth_points: int = 0
    # Suavizar derivada
    deriv_smooth_type: str = "none"
    deriv_smooth_points: int = 2
    # Selection
    max_peaks: Optional[int] = None
    min_distance: float = 0.0
    interpolate_center: bool = False
    # Thermal grouping: 0 K disables it and the raw sample grid is used.
    temperature_k: float = 0.0
    x_energy_unit: str = "eV"

    @property
    def bin_width(self) -> float:
        """k_B * T in x-axis units; 0.0 when thermal grouping is off."""
        return thermal_broadening(self.temperature_k, self.x_energy_unit)

    def validate(self) -> None:
        """Raise ValueError on any out-of-domain choice, naming the parameter."""
        if self.baseline not in BASELINE_KINDS:
            raise ValueError(f"baseline must be one of {BASELINE_KINDS}, got {self.baseline!r}")
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}, got {self.direction!r}")
        if self.height_mode not in HEIGHT_MODES:
            raise ValueError(f"height_mode must be one of {HEIGHT_MODES}, got {self.height_mode!r}")
        for name in ("smooth_type", "deriv_smooth_type"):
            value = getattr(self, name)
            if value not in SMOOTHER_KINDS:
                raise ValueError(f"{name} must be one of {SMOOTHER_KINDS}, got {value!r}")
        if self.xmin is not None and self.xmax is not None and self.xmin >= self.xmax:
            raise ValueError(f"xmin ({self.xmin}) must be below xmax ({self.xmax})")
        if self.baseline_basis not in POLYNOMIAL_BASES:
            raise ValueError(
                f"baseline_basis must be one of {POLYNOMIAL_BASES}, got {self.baseline_basis!r}")
        if self.x_energy_unit not in ENERGY_UNITS:
            raise ValueError(
                f"x_energy_unit must be one of {tuple(ENERGY_UNITS)}, got {self.x_energy_unit!r}")
        if self.temperature_k and self.temperature_k < 0:
            raise ValueError(f"temperature_k cannot be negative, got {self.temperature_k}")


#: Params fields that must survive a trip through QML or JSON as ints.
_INT_PARAM_FIELDS = ('baseline_degree', 'baseline_iterations', 'endpoint_points',
                     'smooth_points', 'deriv_smooth_points', 'max_peaks')


def params_from_dict(raw: Optional[dict]) -> Params:
    """Build :class:`Params` from a loose dict of QML/workflow values.

    Unknown keys are dropped, so a caller can hand over its whole parameter
    map. QML sends every number as a float and a JSON round-trip loses the
    distinction too, so the integer fields are cast back explicitly.
    ``max_peaks <= 0`` means "keep all", matching the spin box's special value.
    """
    params = Params()
    if not raw:
        return params

    for key, value in raw.items():
        if not hasattr(params, key) or value is None:
            continue
        current = getattr(params, key)
        if key in _INT_PARAM_FIELDS:
            value = int(value)
            if key == 'max_peaks' and value <= 0:
                value = None
        elif key in ('xmin', 'xmax'):
            value = float(value)
        elif isinstance(current, bool):
            value = bool(value)
        elif isinstance(current, float):
            value = float(value)
        setattr(params, key, value)
    return params


@dataclass
class Analysis:
    """Result of one spectrum, keeping the intermediates for previews/plots."""

    idx: np.ndarray             # indices into the full spectrum, in-window
    x: np.ndarray               # in-window x
    y_raw: np.ndarray           # in-window y, untouched
    y_smooth: np.ndarray        # after Params.smooth_*
    baseline: np.ndarray        # fitted background (zeros when disabled)
    y_corrected: np.ndarray     # y_smooth - baseline; peaks are found on this
    peaks: List[Peak] = field(default_factory=list)


def _local_maxima(y: np.ndarray, x: np.ndarray) -> List[int]:
    """Indices of local maxima, as ``+ -> -`` sign changes of dy/dx."""
    if len(y) < 3:
        return []
    d = np.gradient(y, x)

    rising = d[:-1]
    falling = d[1:]
    candidates = np.flatnonzero(((rising > 0) & (falling <= 0)) | ((rising == 0) & (falling < 0)))

    out: List[int] = []
    for i in candidates:
        i = int(i)
        # Between samples i and i+1: keep the taller one.
        out.append(i if (y[i] >= y[i + 1] or d[i] == 0) else i + 1)

    # A flat top can register twice; keep the taller of adjacent duplicates.
    deduped: List[int] = []
    for i in out:
        if deduped and i - deduped[-1] <= 1:
            if y[i] > y[deduped[-1]]:
                deduped[-1] = i
        else:
            deduped.append(i)
    return deduped


def _prominences(y: np.ndarray, indices: Sequence[int]) -> np.ndarray:
    """Peak prominences, vectorised.

    ``scipy.signal.peak_prominences`` is O(n) for the whole set rather than
    O(n) per peak, which matters when a hyperspectral map puts tens of
    thousands of spectra through this.
    """
    if len(indices) == 0:
        return np.empty(0, dtype=np.float64)
    try:
        with warnings.catch_warnings():
            # Flat stretches yield zero-prominence candidates by design; the
            # caller drops them. Left unmuted, scipy's PeakPropertyWarning
            # fires once per spectrum. Suppressed by breadth rather than by
            # class: the class lives in a private module whose path is not
            # stable across scipy versions.
            warnings.simplefilter("ignore")
            return _signal.peak_prominences(y, np.asarray(indices, dtype=np.intp))[0]
    except Exception:  # pragma: no cover - defensive, indices come from this module
        # Returning zeros drops every peak in this spectrum, so it must be
        # loud rather than silent.
        logger.exception("peak_prominences failed for %d candidates; dropping them", len(indices))
        return np.zeros(len(indices), dtype=np.float64)


def _parabolic_center(x: np.ndarray, y: np.ndarray, i: int) -> float:
    """Sub-sample peak centre by fitting a parabola to the three samples."""
    if i <= 0 or i >= len(y) - 1:
        return float(x[i])
    y0, y1, y2 = y[i - 1], y[i], y[i + 1]
    denom = y0 - 2 * y1 + y2
    if denom == 0:
        return float(x[i])
    delta = 0.5 * (y0 - y2) / denom
    if not -1 < delta < 1:
        return float(x[i])
    step = (x[i + 1] - x[i - 1]) / 2.0
    return float(x[i] + delta * step)


def analyze(x: np.ndarray, y: np.ndarray, params: Optional[Params] = None) -> Analysis:
    """Find the peaks in one spectrum, keeping the intermediates.

    ``x`` must be ascending. Non-finite samples are excluded from the search.
    """
    p = params or Params()
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    window = np.isfinite(x) & np.isfinite(y)
    if p.xmin is not None:
        window &= x >= p.xmin
    if p.xmax is not None:
        window &= x <= p.xmax
    idx = np.flatnonzero(window)

    if len(idx) < 3:
        empty = np.empty(0, dtype=np.float64)
        return Analysis(idx=idx, x=x[idx], y_raw=y[idx], y_smooth=y[idx],
                        baseline=empty, y_corrected=y[idx], peaks=[])

    xw, yw_raw = x[idx], y[idx]
    yw = smooth(yw_raw, p.smooth_type, p.smooth_points)

    baseline = estimate_baseline(
        xw, yw, p.baseline, p.baseline_degree, p.baseline_iterations, p.direction,
        p.als_lambda, p.als_p, p.endpoint_points, p.baseline_basis,
    )
    corrected = yw - baseline

    span = float(np.max(corrected) - np.min(corrected))
    if not math.isfinite(span) or span <= 0.0:
        # A dead, saturated or fully masked spectrum. np.gradient of constant
        # data returns +/-1e-14 rather than exact zeros, so without this guard
        # the sign-change search invents peaks out of floating-point dust.
        return Analysis(idx=idx, x=xw, y_raw=yw_raw, y_smooth=yw,
                        baseline=baseline, y_corrected=corrected, peaks=[])

    threshold = (p.height / 100.0) * span
    # Same dust, but on a flat stretch of an otherwise varying curve: those
    # candidates come back with a prominence of exactly 0 from scipy, while a
    # real peak is orders of magnitude above this floor.
    prominence_floor = 1e-12 * span

    found = {}
    for sign in {"positive": (1,), "negative": (-1,), "both": (1, -1)}[p.direction]:
        ys = corrected * sign
        yd = smooth(ys, p.deriv_smooth_type, p.deriv_smooth_points)
        candidates = _local_maxima(yd, xw)
        if not candidates:
            continue

        proms = _prominences(ys, candidates)
        base = float(np.min(ys))
        peak_max = float(np.max(ys))

        for i, prom in zip(candidates, proms):
            if prom <= prominence_floor:
                continue
            if p.height_mode == "range":
                if ys[i] - base < threshold:
                    continue
            elif p.height_mode == "prominence":
                if prom < threshold:
                    continue
            elif p.height_mode == "max":
                if peak_max <= 0 or ys[i] < (p.height / 100.0) * peak_max:
                    continue

            full_i = int(idx[i])
            centre = _parabolic_center(xw, ys, i) if p.interpolate_center else float(xw[i])
            previous = found.get(full_i)
            if previous is None or prom > previous.prominence:
                found[full_i] = Peak(
                    index=full_i,
                    x=centre,
                    y=float(yw_raw[i]),
                    y_corrected=float(corrected[i]),
                    prominence=float(prom),
                )

    peaks = sorted(found.values(), key=lambda pk: pk.x)

    if p.min_distance > 0:
        kept: List[Peak] = []
        for pk in sorted(peaks, key=lambda q: -q.prominence):
            if all(abs(pk.x - k.x) >= p.min_distance for k in kept):
                kept.append(pk)
        peaks = sorted(kept, key=lambda q: q.x)

    if p.max_peaks is not None and 0 < p.max_peaks < len(peaks):
        strongest = sorted(peaks, key=lambda q: -q.prominence)[: int(p.max_peaks)]
        peaks = sorted(strongest, key=lambda q: q.x)

    return Analysis(idx=idx, x=xw, y_raw=yw_raw, y_smooth=yw,
                    baseline=baseline, y_corrected=corrected, peaks=peaks)


def find_peaks(x: np.ndarray, y: np.ndarray, params: Optional[Params] = None) -> List[Peak]:
    """Peaks only, sorted by ascending x."""
    return analyze(x, y, params).peaks


def analyze_many(
    x: np.ndarray,
    spectra: np.ndarray,
    params: Optional[Params] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> List[Analysis]:
    """Run :func:`analyze` over every column of ``spectra`` (samples x spectra).

    ``should_cancel`` is polled per spectrum so a worker task can abort a
    hyperspectral run; the partial list is returned as-is when it fires.
    """
    p = params or Params()
    p.validate()

    spectra = np.asarray(spectra, dtype=np.float64)
    if spectra.ndim == 1:
        spectra = spectra[:, None]

    total = spectra.shape[1]
    results: List[Analysis] = []
    for i in range(total):
        if should_cancel is not None and should_cancel():
            logger.info("Peak detection cancelled after %d/%d spectra", i, total)
            break
        results.append(analyze(x, spectra[:, i], p))
        if on_progress is not None:
            on_progress(i + 1, total)
    return results


def occupancy_matrix(n_rows: int, per_spectrum_rows: Sequence[Sequence[int]],
                     blank: float = np.nan, mark: float = 1.0,
                     mark_by_column: bool = False) -> np.ndarray:
    """Occupancy table: ``mark`` where a spectrum has a peak, ``blank`` elsewhere.

    Shape is ``(n_rows, len(per_spectrum_rows))`` -- one column per spectrum.
    ``blank`` defaults to NaN so the exported CSV has empty cells rather than a
    field of zeros; float32 keeps a hyperspectral map's worth of columns
    affordable (a 128x128 map over 512 samples is ~33 MB).

    With ``mark_by_column`` each column is marked with its own 1-based number
    instead of a flat 1. Plotting every column of a 1/blank table draws every
    mark on the same line; numbering them offsets each spectrum onto its own
    row, which is what makes the columns distinguishable by eye.
    """
    matrix = np.full((int(n_rows), len(per_spectrum_rows)), blank, dtype=np.float32)
    for col, rows in enumerate(per_spectrum_rows):
        value = float(col + 1) if mark_by_column else mark
        for row in rows:
            if 0 <= row < n_rows:
                matrix[row, col] = value
    return matrix


def peak_rows(results: Sequence[Analysis]) -> List[List[int]]:
    """Sample indices of each spectrum's peaks."""
    return [[pk.index for pk in r.peaks] for r in results]


def binned_peak_rows(results: Sequence[Analysis], edges: np.ndarray) -> List:
    """Bin indices of each spectrum's peaks.

    Several peaks of one spectrum landing in the same bin collapse to a single
    entry: below the thermal resolution they are one feature, not several.
    """
    return [
        np.unique(assign_bins([pk.x for pk in r.peaks], edges)) if r.peaks else []
        for r in results
    ]


def peak_matrix(n_samples: int, results: Sequence[Analysis],
                blank: float = np.nan, mark_by_column: bool = False) -> np.ndarray:
    """Occupancy table on the raw sample grid, one column per spectrum."""
    return occupancy_matrix(n_samples, peak_rows(results),
                            blank=blank, mark_by_column=mark_by_column)


def binned_peak_matrix(results: Sequence[Analysis], edges: np.ndarray,
                       blank: float = np.nan,
                       mark_by_column: bool = False) -> np.ndarray:
    """Occupancy table on a binned axis, one column per spectrum."""
    return occupancy_matrix(len(edges) - 1, binned_peak_rows(results, edges),
                            blank=blank, mark_by_column=mark_by_column)


def group_peaks_by_bin(peaks: Sequence[Peak], edges: np.ndarray) -> List[tuple]:
    """Collapse peaks sharing a bin to the most prominent one.

    Returns ``(bin_index, representative_peak, merged_count)`` per occupied
    bin, in ascending x order. Peaks closer together than the bin width are
    not thermally distinguishable, so reporting them separately would be
    claiming precision the measurement does not have.
    """
    if not peaks:
        return []
    indices = assign_bins([pk.x for pk in peaks], edges)
    grouped: dict = {}
    for bin_index, peak in zip(indices, peaks):
        bin_index = int(bin_index)
        best, count = grouped.get(bin_index, (None, 0))
        if best is None or peak.prominence > best.prominence:
            best = peak
        grouped[bin_index] = (best, count + 1)
    return [(b, best, count) for b, (best, count) in sorted(grouped.items())]
