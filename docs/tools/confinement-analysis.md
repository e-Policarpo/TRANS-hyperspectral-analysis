# Confinement Analysis

Finds the states in each spectrum — peak search and background removal in one
pass — and emits the occupancy table: which states exist at which bias.

**Menu** Tools → Composite tools → Confinement Analysis · **Panel**
`ConfinementAnalysisTool.qml` · **Method** `analyze_confinement()`,
`build_occupancy_matrix()`, engine in `src/processing/peak_detection.py`

## Input

dI/dV spectra. The panel previews the selected spectrum live
(`previewConfinementAnalysis`) while you turn the knobs; the run
(`runConfinementAnalysis`) then processes every spectrum.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `baseline` | **`arpls`** | `arpls`, `als`, `snip`, `rubberband`, `endpoint`, `polynomial` |
| `baseline_degree` | — | polynomial degree |
| `baseline_basis` | `power` | `power`, `legendre`, `chebyshev` |
| `baseline_iterations` | — | iterations for the asymmetric baselines |
| `height_mode` | **`noise`** | `noise` = multiples of the spectrum's own σ; otherwise a fraction of the span |
| `height` | **2.0** | threshold, in σ |
| `min_distance` | — | minimum peak separation |
| `max_peaks` | — | cap on peaks per spectrum |
| `smooth_type` / `smooth_points` | — | pre-search smoothing |
| `deriv_smooth_type` / `deriv_smooth_points` | — | smoothing for the derivative path |
| `interpolate_center` | — | refine each peak's centre by interpolation |
| `temperature_k` | — | sets the k_BT/2 binning grid |
| `x_energy_unit` | — | axis unit |
| `direction` | — | sweep direction |
| `all` | — | run over every spectrum rather than the previewed one |

## Output

| output | contents |
|---|---|
| occupancy table | 1 where a spectrum has a peak in a bin, blank elsewhere |
| `<dataset> - Energy Bins` | the bin grid |
| files | `<project>_outputs/peaks/` |

## Method

Per spectrum: estimate the noise σ from the **raw** curve, fit the background,
subtract it, then `find_peaks` with a threshold of `height × σ`.

**arPLS is the default, and it was measured.** Against planted states at ~1%
of the band-edge height, ModPoly found **0%** at any threshold while arPLS
found **100%** with no false peaks. ModPoly cannot follow an exponential band
edge, so the weak states are gone before the search even runs. arPLS
(Baek et al., *Analyst* 2015) derives its asymmetry weights from the
residual's own negative-side statistics each iteration, so it adapts to
varying peak density instead of needing `p` guessed in advance. It can fit in
log space, which is what makes it usable on a tunnelling edge that rises by
orders of magnitude.

`height_mode='noise'` makes `height` a multiple of the spectrum's **own**
noise, estimated from the raw curve and never the smoothed one — smoothing
would make every spectrum look quiet and the threshold meaningless.

Peaks are binned at the coarser of **k_BT/2** and the sweep's own step: two
states closer than the thermal broadening are not resolved, so reporting them
separately would be a fiction.

## Notes

- Model fits take `positive_mask` — finite and ≥ 0, with zero kept, since zero
  is a real reading of "no states here". Peaks are still **detected** on the
  whole curve, because a detector needs a contiguous grid to measure width and
  prominence on.
- The background fit deliberately sees negatives; that is the documented
  exception to the positivity rule.
- The Map Generator shares this engine but uses **3σ** — see
  [Map Generator](map-generator.md).
