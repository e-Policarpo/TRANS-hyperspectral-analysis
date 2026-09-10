# Multi-Peak Fitting

Fits several overlapping peaks at once, with a baseline, and reports each
peak's parameters with uncertainties.

**Menu** Tools → Composite tools → Multi-Peak Fitting · **Panel**
`MultiPeakFitTool.qml` · **Method** `multiPeakFit()`,
`src/backend/peak_fitting.py`

## Input

One spectrum from a dataset, chosen by `spectrum_index`.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `peak_shape` | `gaussian` | `gaussian`, `lorentzian` or `pseudo_voigt` |
| `n_peaks_auto` | 0 | 0 = detect automatically; otherwise fit this many |
| `baseline_degree` | 1 | polynomial degree fitted together with the peaks |
| `spectrum_index` | 0 | which spectrum |

## Output

A `MultiPeakFitResult`: the fitted curve, the baseline, and a `FittedPeak` per
peak — centre, amplitude, width and the uncertainty on each.

## Method

Peaks are detected to seed the fit (`detect_peaks` with `adaptive_prominence`,
capped at 10 when asked for "all"), then **everything is fitted together** —
all peaks plus the baseline in one non-linear least squares. Fitting peaks one
at a time gets overlapping peaks wrong, because each one absorbs part of its
neighbour.

The three shapes describe different physics: **Gaussian** for inhomogeneous
broadening, **Lorentzian** for lifetime broadening, **pseudo-Voigt** — a
weighted sum of the two — when both are present, with the mixing as a fitted
parameter.

Model fits take `positive_mask` by default: a peak fitted to a density of
states should not be fitted to the part of the curve that is an artifact of
the background correction.

## Notes

- **Uncertainties come from the covariance of the fit**, so they are only as
  meaningful as the model. A Gaussian forced onto a Lorentzian peak gives
  tight, wrong error bars.
- There is a wall-clock guard: the fitter has a time budget, and one timing
  test sits right on it and flips between runs.
