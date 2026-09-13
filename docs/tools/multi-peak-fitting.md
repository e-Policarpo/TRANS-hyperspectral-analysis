# Multi-Peak Fitting

Fits a sum of Gaussian / Lorentzian / pseudo-Voigt peaks plus a polynomial
baseline to **every spectrum** of every selected dataset, and previews the
fit on one spectrum first.

**Menu** Tools → Fit and features → Multi-Peak Fitting · **Panel**
`MultiPeakFitTool.qml` · **Methods** `fit_multipeak_dataset()` (the run),
`multiPeakFit()` (the preview), `src/backend/peak_fitting.py` ·
**Batch key** `multi_peak_fit`

## Input

Any spectral datasets — a multi-dataset selection, fitted one after another.
The preview fits the `spectrum_index`-th spectrum of the first selection and
draws data, fit, baseline, each component and the peak centres, so a wrong
baseline degree or a runaway peak count is visible before 2000 spectra are
fitted.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `peak_shape` | `gaussian` | `gaussian`, `lorentzian` or `pseudo_voigt` |
| `n_peaks_auto` | 0 | 0 = detect automatically; otherwise at most this many |
| `baseline_degree` | 1 | polynomial degree fitted together with the peaks; -1 = none |
| `positive_only` | true | fit only the non-negative part of each curve |

## Output

| output | contents |
|---|---|
| `<dataset> - Peak Fit` | flat table, one row per spectrum: `n_peaks`, `rsq`, `rss`, `success`, then `peak<k>_center` / `_amplitude` / `_fwhm` up to the largest count found (NaN where a spectrum has fewer). Every column is a map via the Map Generator. |
| `<dataset> - Fitted` | the fitted curves on the source axis, one per spectrum, carrying the source's spatial keys |
| `<name>_PeakFit.csv` | long format, one row per peak, with shape, width and pseudo-Voigt η |
| `<name>_PeakFit_summary.csv` | the table above |

Both land under `<project>_outputs/peaks/`. Peaks are sorted by centre, so
`peak1` is always the lowest.

## Method

Peaks are detected to seed the fit (`detect_peaks` with `adaptive_prominence`,
capped at 10 when asked for "all"), then **everything is fitted together** —
all peaks plus the baseline in one non-linear least squares. Fitting peaks one
at a time gets overlapping peaks wrong, because each one absorbs part of its
neighbour. Because the baseline is part of the model, the data need not be
flattened first.

The three shapes describe different physics: **Gaussian** for inhomogeneous
broadening, **Lorentzian** for lifetime broadening, **pseudo-Voigt** — a
weighted sum of the two — when both are present, with the mixing as a fitted
parameter.

With `positive_only` the fit takes `positive_mask`: a density of states
cannot be negative, so anything below zero is noise or an over-subtracted
background and should not pull the fit. Peaks are still *detected* on the
whole curve. Clear it for a signed quantity (current, a difference
spectrum).

## Notes

- A spectrum whose fit fails keeps its row, with `success = 0` and NaN
  parameters; the run is not lost to one bad curve.
- There is a wall-clock guard: the fitter has a time budget, and one timing
  test sits right on it and flips between runs.
