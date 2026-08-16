"""
Per-spectrum feature extraction for dI/dV classification.

Turns a hyperspectral dataset into a table with one row per spectrum and one
column per physical quantity -- gap width, doping offset, band-edge steepness,
confined-state count and so on. That table is the input to PCA / clustering,
and because it is emitted as flat data every column is also a spatial map for
free.

Why the features and not the raw spectra: PCA on raw dI/dV is dominated by
whatever varies most, which is usually tip-sample distance rather than
sample physics. Reducing each spectrum to interpretable scalars first means
the components mean something, and a surprising loading points at a physical
quantity instead of at an instrument artefact.

Three things decide whether the table is usable, and all three are handled
here rather than left to the caller:

1. **Normalisation.** Raw dI/dV scales with the setpoint and the tip height.
   Without a per-spectrum normalisation the first principal component is
   "how close was the tip". :func:`normalize_spectrum` runs by default.
2. **The gap defines the other features.** Metallicity is the steepness
   *outside* the gap and confinement is the states *inside* it, so the gap
   edges are found first and everything else is measured relative to them.
3. **Validity.** A spectrum where the gap search fails is not silently given
   a gap of zero -- it is flagged, so the row can be dropped before PCA
   rather than defining a component.

Note that features are left in their own physical units. Standardising them
is the classifier's job (they span ~1e-7 to small integers, so PCA on raw
units would be decided entirely by the largest column).

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
import math
import warnings
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np

from src.backend.peak_fitting import estimate_noise_sigma
from src.backend.sts_algorithms import detect_bandgap, classify_doping, validate_ldos
from src.processing.peak_detection import (
    Params,
    analyze,
    coefficient_names,
    fit_polynomial,
    normalized_axis,
    smooth,
)

logger = logging.getLogger(__name__)


NORMALIZATIONS = ("none", "max", "band-edge", "area")


@dataclass
class FeatureConfig:
    """Knobs for :func:`spectrum_features`.

    The defaults are the ones argued for when planning the classifier:
    normalise first, Legendre coefficients (the only basis that actually
    decorrelates on a uniformly sampled sweep), and a gap threshold matching
    the existing Detect Bandgap & Doping tool.
    """

    normalize: str = "max"
    gap_delta: float = 0.05
    #: Fraction of the sweep at each end treated as "band edge" for the
    #: steepness and asymmetry scalars.
    edge_fraction: float = 0.15
    poly_degree: int = 4
    poly_basis: str = "legendre"
    #: Smoothing half-width used only for the doping minimum, which is
    #: otherwise chasing noise in a near-zero signal.
    doping_smooth_points: int = 5
    #: Peak search used for the confined states. Restricted to the gap.
    confinement: Optional[Params] = None
    #: In-gap states must clear this many noise sigmas to count.
    state_noise_sigmas: float = 4.0
    #: Features narrower than this many samples are suppressed before gap
    #: detection, so a confined state cannot be mistaken for a band edge.
    state_width_samples: int = 11

    def validate(self) -> None:
        if self.normalize not in NORMALIZATIONS:
            raise ValueError(
                f"normalize must be one of {NORMALIZATIONS}, got {self.normalize!r}")
        if not 0 < self.edge_fraction < 0.5:
            raise ValueError(
                f"edge_fraction must lie in (0, 0.5), got {self.edge_fraction}")
        if self.poly_degree < 0:
            raise ValueError(f"poly_degree cannot be negative, got {self.poly_degree}")
        # Delegates basis / peak-search validation to the engine.
        Params(baseline_degree=self.poly_degree,
               baseline_basis=self.poly_basis).validate()
        if self.confinement is not None:
            self.confinement.validate()

    def confinement_params(self) -> Params:
        """Peak-search settings for the in-gap states."""
        if self.confinement is not None:
            return self.confinement
        # No background subtraction: the gap interior is already flat, and a
        # polynomial fitted across it would eat the very states being counted.
        return Params(baseline="none", height=5.0, smooth_points=2)


def feature_columns(config: Optional[FeatureConfig] = None) -> List[str]:
    """Column order of the emitted table. Stable, so PCA inputs line up."""
    cfg = config or FeatureConfig()
    return (
        ["Spectrum_Index", "valid"]
        + ["gap_width", "gap_left", "gap_right"]
        + ["doping_offset", "doping_argmin", "doping_disagreement"]
        + coefficient_names(cfg.poly_degree, cfg.poly_basis)
        + ["ldos_left", "ldos_right", "asymmetry", "zero_bias_conductance",
           "in_gap_weight"]
        + ["n_states", "state_spacing_mean", "lowest_state", "state_weight"]
    )


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def normalize_spectrum(x: np.ndarray, y: np.ndarray, method: str = "max",
                       edge_fraction: float = 0.15) -> np.ndarray:
    """Put a spectrum on a comparable scale.

    dI/dV magnitude depends on the tunnelling setpoint and the tip height, so
    two spectra of identical physics can differ by an order of magnitude.
    Every method here is per-spectrum and divides by a positive scalar, so
    shape is preserved and only the scale changes.

    ``max``        divide by the maximum (matches the existing STS tools)
    ``band-edge``  divide by the mean over the outer ``edge_fraction`` of the
                   sweep -- more robust than ``max`` when a single spike
                   survives filtering, and ties the scale to the band edges
                   rather than to whatever the largest sample happens to be
    ``area``       divide by the mean over the whole sweep
    ``none``       leave it alone
    """
    y = np.asarray(y, dtype=np.float64)
    if method == "none":
        return y

    finite = y[np.isfinite(y)]
    if finite.size == 0:
        return y

    if method == "max":
        scale = float(np.max(np.abs(finite)))
    elif method == "area":
        scale = float(np.mean(np.abs(finite)))
    elif method == "band-edge":
        n = max(1, int(len(y) * edge_fraction))
        edges = np.concatenate([y[:n], y[-n:]])
        edges = edges[np.isfinite(edges)]
        scale = float(np.mean(np.abs(edges))) if edges.size else 0.0
    else:
        raise ValueError(f"normalize must be one of {NORMALIZATIONS}, got {method!r}")

    return y / scale if scale > 0 and math.isfinite(scale) else y


def suppress_narrow_peaks(y: np.ndarray, width: int = 11) -> np.ndarray:
    """Remove narrow positive features, keeping the broad shape.

    Morphological opening (erosion then dilation). Used before gap detection:
    the detector walks outward from V = 0 and stops at the first sample above
    the threshold, so a bright confined state *inside* the gap stops it at the
    state and the spectrum is reported as gapless. On a sample with in-gap
    states -- the whole point of this analysis -- that silently corrupts the
    gap, the doping and everything measured relative to them.

    A gap edge is the broad background LDOS rising, not a narrow resonance,
    so opening away features narrower than ``width`` samples is the right
    distinction to draw.
    """
    from scipy.ndimage import grey_opening

    y = np.asarray(y, dtype=np.float64)
    width = int(width)
    if width < 3 or width >= y.size:
        return y
    return grey_opening(y, size=width, mode="nearest")


def gap_features(x: np.ndarray, y: np.ndarray, delta: float = 0.05,
                 state_width: int = 11) -> Dict[str, float]:
    """Gap width and edges, via the same detector the STS tool uses.

    Both edges are kept, not just the width: their positions carry the doping,
    and they bound every other feature.

    In-gap states are suppressed first (see :func:`suppress_narrow_peaks`);
    without that a confined state collapses the measured gap to zero.
    """
    y = suppress_narrow_peaks(np.asarray(y, dtype=np.float64), state_width)
    gap, centre, left, right = detect_bandgap(np.asarray(x, dtype=np.float64),
                                              y, float(delta))
    return {"gap_width": float(gap), "gap_left": float(left),
            "gap_right": float(right), "gap_center": float(centre)}


def doping_features(x: np.ndarray, y: np.ndarray, gap: Dict[str, float],
                    smooth_points: int = 5,
                    resolution: float = 0.01) -> Dict[str, float]:
    """Where the LDOS minimum sits relative to V = 0.

    Two independent estimates, deliberately. The midpoint of the gap edges is
    the stable one. ``argmin`` of a near-zero noisy signal wanders, so it is
    reported alongside rather than trusted -- when the two disagree the
    spectrum is worth a second look, which is what ``doping_disagreement``
    is for.
    """
    x = np.asarray(x, dtype=np.float64)
    midpoint = float(gap["gap_center"])

    inside = (x >= gap["gap_left"]) & (x <= gap["gap_right"])
    if inside.sum() >= 3:
        smoothed = smooth(np.asarray(y, dtype=np.float64)[inside], "average", smooth_points)
        argmin = float(x[inside][int(np.argmin(np.abs(smoothed)))])
    else:
        argmin = float("nan")

    disagreement = abs(midpoint - argmin) if math.isfinite(argmin) else float("nan")
    return {"doping_offset": midpoint,
            "doping_argmin": argmin,
            "doping_disagreement": disagreement,
            "doping_type": classify_doping(midpoint, resolution)}


def metallicity_features(x: np.ndarray, y: np.ndarray, gap: Dict[str, float],
                         degree: int = 4, basis: str = "legendre",
                         edge_fraction: float = 0.15) -> Dict[str, float]:
    """How steeply the LDOS rises outside the gap.

    The polynomial is fitted to the band-edge regions only -- the union of
    ``V < gap_left`` and ``V > gap_right`` -- because including the flat gap
    interior would dilute exactly the steepness being measured. The fit runs
    on the normalised axis so an orthogonal basis is orthogonal over this
    spectrum's own range and the coefficients compare across spectra.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    names = coefficient_names(degree, basis)

    outside = ((x < gap["gap_left"]) | (x > gap["gap_right"])) & np.isfinite(y)
    features: Dict[str, float] = dict.fromkeys(names, float("nan"))

    # A degree-n fit through n+2 points is an interpolation, not a
    # measurement: when the detected gap swallows nearly the whole sweep the
    # coefficients explode by orders of magnitude and would dominate any
    # subsequent PCA. Demand real over-determination or report nothing.
    if outside.sum() >= 3 * (degree + 1):
        try:
            with np.errstate(all="ignore"):
                coeffs = fit_polynomial(normalized_axis(x)[outside], y[outside],
                                        degree, basis)
            features.update(dict(zip(names, (float(c) for c in coeffs))))
        except Exception:
            logger.debug("Metallicity fit failed", exc_info=True)

    n = max(1, int(len(x) * edge_fraction))
    inside = (x >= gap["gap_left"]) & (x <= gap["gap_right"]) & np.isfinite(y)
    with warnings.catch_warnings():
        # An all-NaN window is a bad spectrum, not a bug: it propagates to a
        # NaN feature and the row is flagged invalid. Unmuted this fires four
        # times per bad spectrum.
        warnings.simplefilter("ignore", RuntimeWarning)
        left = float(np.nanmean(y[:n]))
        right = float(np.nanmean(y[-n:]))
        outside_mean = float(np.nanmean(np.abs(y[outside]))) if outside.any() else float("nan")
        inside_mean = float(np.nanmean(np.abs(y[inside]))) if inside.any() else float("nan")
    total = abs(left) + abs(right)

    features.update({
        "ldos_left": left,
        "ldos_right": right,
        # Electron-hole asymmetry, bounded to [-1, 1] so it is comparable
        # between spectra of very different magnitude.
        "asymmetry": (right - left) / total if total > 0 else float("nan"),
        "zero_bias_conductance": float(np.interp(0.0, x, y)) if x.size else float("nan"),
        "in_gap_weight": (inside_mean / outside_mean
                          if outside_mean and math.isfinite(outside_mean)
                          and outside_mean > 0 else float("nan")),
    })
    return features


def confinement_features(x: np.ndarray, y: np.ndarray, gap: Dict[str, float],
                         params: Optional[Params] = None,
                         noise_sigmas: float = 4.0) -> Dict[str, float]:
    """Confined states inside the gap.

    A bare count is a weak feature, so the spacing and the position of the
    lowest state come too: two spectra with three states each are physically
    different if one has them bunched at an edge and the other evenly spread.

    The gap interior is flat and near zero, so a *percentage-of-span*
    threshold there is measuring the noise and will happily report a dozen
    states in an empty gap. Candidates are therefore gated on an absolute
    height of ``noise_sigmas`` times the MAD noise estimate of the in-gap
    region -- a criterion that does not care how flat the span is.
    """
    blank = {"n_states": 0.0, "state_spacing_mean": float("nan"),
             "lowest_state": float("nan"), "state_weight": float("nan")}

    left, right = gap["gap_left"], gap["gap_right"]
    if not (math.isfinite(left) and math.isfinite(right) and right > left):
        return blank

    search = Params(**{**vars(params or Params()), "xmin": left, "xmax": right})
    try:
        result = analyze(x, y, search)
    except Exception:
        logger.debug("In-gap peak search failed", exc_info=True)
        return blank

    sigma = estimate_noise_sigma(result.y_corrected)
    floor = noise_sigmas * sigma
    peaks = [pk for pk in result.peaks if pk.prominence > floor] if floor > 0 else result.peaks
    if not peaks:
        return blank

    positions = np.array([pk.x for pk in peaks], dtype=np.float64)
    heights = np.array([pk.y_corrected for pk in peaks], dtype=np.float64)
    return {
        "n_states": float(len(peaks)),
        "state_spacing_mean": (float(np.mean(np.diff(positions)))
                               if len(positions) > 1 else float("nan")),
        # Measured from the nearer gap edge, so it is comparable between
        # spectra whose gaps sit at different absolute biases.
        "lowest_state": float(np.min(np.abs(positions - left))),
        "state_weight": float(np.sum(np.abs(heights))),
    }


# ---------------------------------------------------------------------------
# Per-spectrum and batch entry points
# ---------------------------------------------------------------------------

def spectrum_features(x: np.ndarray, y: np.ndarray,
                      config: Optional[FeatureConfig] = None) -> Dict[str, float]:
    """Every feature for one spectrum, keyed by column name."""
    cfg = config or FeatureConfig()
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    is_valid, reason = validate_ldos(x, y)
    normalized = normalize_spectrum(x, y, cfg.normalize, cfg.edge_fraction)

    gap = gap_features(x, normalized, cfg.gap_delta, cfg.state_width_samples)
    row: Dict[str, float] = {"valid": 1.0 if is_valid else 0.0}
    row.update({k: v for k, v in gap.items() if k != "gap_center"})
    row.update(doping_features(x, normalized, gap, cfg.doping_smooth_points))
    row.update(metallicity_features(x, normalized, gap, cfg.poly_degree,
                                    cfg.poly_basis, cfg.edge_fraction))
    row.update(confinement_features(x, normalized, gap, cfg.confinement_params(),
                                    cfg.state_noise_sigmas))
    if not is_valid:
        row["invalid_reason"] = reason
    return row


def feature_table(x: np.ndarray, spectra: np.ndarray,
                  config: Optional[FeatureConfig] = None,
                  should_cancel: Optional[Callable[[], bool]] = None,
                  on_progress: Optional[Callable[[int, int], None]] = None
                  ) -> List[Dict[str, float]]:
    """One feature row per column of ``spectra`` (samples x spectra).

    ``should_cancel`` is polled per spectrum so a worker task can abort a
    hyperspectral run; the partial list is returned as-is when it fires.
    """
    cfg = config or FeatureConfig()
    cfg.validate()

    spectra = np.asarray(spectra, dtype=np.float64)
    if spectra.ndim == 1:
        spectra = spectra[:, None]

    total = spectra.shape[1]
    rows: List[Dict[str, float]] = []
    for i in range(total):
        if should_cancel is not None and should_cancel():
            logger.info("Feature extraction cancelled after %d/%d spectra", i, total)
            break
        row = {"Spectrum_Index": float(i)}
        try:
            row.update(spectrum_features(x, spectra[:, i], cfg))
        except Exception:
            logger.warning("Feature extraction failed for spectrum %d", i, exc_info=True)
            row["valid"] = 0.0
        rows.append(row)
        if on_progress is not None:
            on_progress(i + 1, total)
    return rows
