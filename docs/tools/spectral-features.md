# Spectral Features

Reduces every spectrum to a row of numbers — gap, doping, metallicity,
confinement — so a dataset becomes a table you can sort and plot.

**Menu** Tools → Fit and features → Spectral Features · **Panel**
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
| `dirac_mode` | `auto` | Dirac branch windows: `auto` (from the gap edges), `manual`, `off` |
| `dirac_edge_trim` | 0.10 | fraction of each branch's outer span left out, `auto` only |
| `dirac_left_min` / `dirac_left_max` | — | left branch window, `manual` only |
| `dirac_right_min` / `dirac_right_max` | — | right branch window, `manual` only |

## Output

| output | where |
|---|---|
| `<dataset> - Features` | one row per spectrum, one column per feature |
| `<name>_Features.csv` | `<project>_outputs/peaks/` |

## Method

Six groups, each answering a different question:

- **gap** — where the conductance drops below threshold and comes back;
  reports the gap and its edges.
- **doping** — where the gap sits relative to zero bias: N-type, P-type or
  neutral.
- **metallicity** — a polynomial fit through the in-gap region; a metal has
  finite conductance at zero bias, a semiconductor does not.
- **confinement** — states inside the gap.
- **states by side** — how many states sit at negative bias and how many at
  positive, counting the whole sweep rather than the gap alone.
- **Dirac point** — where the two linear branches of a V-shaped spectrum
  meet; folded in from the old Dirac Point Estimator tool.

A state counts only if it exceeds `state_noise_sigmas × σ` of the **in-gap**
noise — measured where there should be nothing, which is the right place to
measure it. `suppress_narrow_peaks` then removes anything narrower than
`state_width_samples`, since a peak one or two samples wide is noise.

### States by the side of the bias

`n_states` counts the gap interior only, which leaves the question a doped or
asymmetric sample actually raises: are the states on the empty side or the
filled one? Four columns answer it:

| column | meaning |
|---|---|
| `nstates_negative` | states at negative bias, **in the gap and outside it** |
| `nstates_positive` | the same at positive bias (a state exactly at 0 V counts here) |
| `nstates_negative_in_gap` | the in-gap part of `nstates_negative` |
| `nstates_positive_in_gap` | the in-gap part of `nstates_positive` |

The in-gap pair adds up to `n_states`, and the out-of-gap count is
`nstates_negative − nstates_negative_in_gap`.

Two searches feed them, because the two regions need different backgrounds:
the gap interior is flat and takes none (the same pass that produces
`n_states`, so the parts agree), while outside it the band edge dominates and
takes the arPLS background. Outside the gap a state must also be a **local
maximum of the curve itself** — the band edge's knee survives arPLS as a
residual bump as tall as a real state (prominence 0.09 against 0.07–0.20 for
planted states), so without that test every gapped spectrum would report one
invented state per side. The cost is a state sitting exactly on the knee,
which is not counted; nothing on this curve can separate the two.

### Dirac point

For graphene and other Dirac materials the conductance is V-shaped, and the
quantity of interest is where the two branches cross — the Dirac point — and
how steep each branch is. A straight line is fitted to each branch inside its
window and the two are intersected (`fit_dirac_point`, the same engine as
the sunset tool):

| column | meaning |
|---|---|
| `dirac_point` | bias of the crossing |
| `dirac_conductance` | conductance there |
| `dirac_slope_left` / `dirac_slope_right` | the two slopes |
| `dirac_r2_left` / `dirac_r2_right` | R² of each line — whether the branch was linear at all |
| `dirac_slope_asymmetry` | \|right\| / \|left\|, the electron–hole asymmetry |

With `dirac_mode = auto` the branches run from each end of the sweep to the
gap edge **this table has already found**, trimmed at the outer end by
`dirac_edge_trim` of their span to stay clear of the sweep's turnaround
artefacts. Reusing the gap is what makes the branches and the gap agree with
each other; the old tool ran its own gap detection with its own threshold.
`manual` takes the four bias limits; `off` leaves the columns NaN.

**Check `dirac_r2_*` first.** On a gapped spectrum the branches are not lines
— they are band edges — and the crossing is the meaningless intersection of
two nearly parallel fits. A low R² says so. The panel draws the two fitted
lines and the crossing in orange for the same reason.

## Notes

- `positive_only` defaults to **true** because these are fits to a density of
  states. Turn it off only for a signed quantity.
- The metallicity fit's coefficients are basis-dependent — see [Curve Background
  Flattening](curve-background-flattening.md) on why Legendre is the one to use if you intend
  to compare coefficients between spectra.
