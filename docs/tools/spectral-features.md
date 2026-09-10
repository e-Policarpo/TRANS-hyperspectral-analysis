# Spectral Features

Reduces every spectrum to a row of numbers — gap, doping, metallicity,
confinement — so a dataset becomes a table you can sort and plot.

**Menu** Tools → Composite tools → Spectral Features · **Panel**
`SpectralFeaturesTool.qml` · **Method** `extract_spectral_features()`,
`src/processing/spectral_features.py`

## Input

dI/dV spectra. The panel previews one spectrum's features live
(`previewSpectralFeatures`).

## Parameters

| parameter | default | meaning |
|---|---|---|
| `feature` | — | which feature group to extract |
| `normalize` | — | normalise each spectrum before measuring |
| `gap_delta` | — | threshold defining the gap edges |
| `edge_fraction` | — | fraction of the edge used in the fit |
| `state_noise_sigmas` | **4.0** | a state must exceed this many σ of the in-gap noise |
| `state_width_samples` | — | narrower peaks than this are suppressed |
| `poly_degree` | — | degree for the metallicity fit |
| `poly_basis` | `power` | `power`, `legendre`, `chebyshev` |
| `positive_only` | **true** | fit only the non-negative part |

## Output

| output | where |
|---|---|
| `<dataset> - Features` | one row per spectrum, one column per feature |
| `<name>_Features.csv` | `<project>_outputs/peaks/` |

## Method

Four groups, each answering a different question:

- **gap** — where the conductance drops below threshold and comes back;
  reports the gap and its edges.
- **doping** — where the gap sits relative to zero bias: N-type, P-type or
  neutral.
- **metallicity** — a polynomial fit through the in-gap region; a metal has
  finite conductance at zero bias, a semiconductor does not.
- **confinement** — states inside the gap.

A state counts only if it exceeds `state_noise_sigmas × σ` of the **in-gap**
noise — measured where there should be nothing, which is the right place to
measure it. `suppress_narrow_peaks` then removes anything narrower than
`state_width_samples`, since a peak one or two samples wide is noise.

## Notes

- `positive_only` defaults to **true** because these are fits to a density of
  states. Turn it off only for a signed quantity.
- The metallicity fit's coefficients are basis-dependent — see [Curve
  Fitting](curve-fitting.md) on why Legendre is the one to use if you intend
  to compare coefficients between spectra.
