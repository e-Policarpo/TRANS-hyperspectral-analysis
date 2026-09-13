# Curve Background Flattening

Fits a smooth background to every spectrum and subtracts it, leaving the
features on a flat baseline. The standard way to remove a background before
looking for states. (Until the tool rework this was called *Curve Fitting*;
the panel file keeps that name.)

**Menu** Tools → Transform → Curve Background Flattening · **Panel** `CurveFittingTool.qml` ·
**Method** `fit_curves()` · **Batch key** `curve_background_flattening`

## Input

Any spectral dataset — or several: the panel takes a multi-dataset selection
and flattens them one after another, each producing its own outputs.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `fit_type` | polynomial | `polynomial`, `linear` or `exponential` |
| `degree` | 2 | polynomial degree |
| `basis` | `power` | `power`, `legendre` or `chebyshev` |

## Output

| output | where |
|---|---|
| `<dataset> - Baseline Corrected` | the data minus the fit |
| `<dataset> - Fit Coefficients` | one row per spectrum: `spectrum_index`, then `c0` (constant) … `c{degree}`, ascending power |
| `<name>.csv` for each | `<project>_outputs/fitted/` |

## Method

Least squares in the chosen basis. The **basis matters for the
coefficients**, not for the fitted curve: on a uniform grid a
**Legendre** basis decorrelates the coefficients, so `c2` means "how much
curvature" independently of `c0` and `c1`. In the **power** basis the
coefficients are strongly correlated and comparing `c2` between spectra is
close to meaningless. Chebyshev does *not* decorrelate on a uniform grid.

Use Legendre if you intend to analyse the coefficients — the coefficients
dataset exists for metallicity work, where the low-order terms are the
quantity of interest.

## Notes

- Background fitting deliberately sees the **whole curve, negatives
  included**. That is the documented exception to the negative-LDOS rule:
  asymmetric baselines work by sitting below the data, and dropping the
  samples underneath them biases the baseline upward.
- For a band edge spanning orders of magnitude, a polynomial cannot follow it.
  Use the arPLS baseline in [Confinement Analysis](confinement-analysis.md)
  instead.
