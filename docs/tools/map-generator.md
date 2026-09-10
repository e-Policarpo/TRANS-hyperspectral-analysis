# Map Generator

Turns spectra into spatial maps: removes the background, integrates over bias
intervals and assembles the maps, in one pass. Accepts a **multi-dataset
selection**.

**Menu** Tools → Composite tools → Map Generator · **Panel**
`MapGeneratorTool.qml` · **Method** `generate_maps_from_spectra()` ·
**Batch key** `map_generator`

## Input

**Spectra, not a hand-corrected flat dataset.** The tool does the background
removal itself, reusing the Confinement Analysis engine, so the input is the
raw dI/dV.

Intervals come from one of three places: a fresh peak search, a previous
analysis's datasets (published as `integration_intervals`), or typed by hand.
Not from a JSON file — that path was removed.

## Parameters

### Intervals

| parameter | default | meaning |
|---|---|---|
| `lower` / `upper` | — | a hand-typed interval |
| `min_spectra_per_bin` | 1 | drop bins holding fewer spectra than this |

### Peak search (shared with Confinement Analysis)

| parameter | default | meaning |
|---|---|---|
| `baseline` | `arpls` | background model |
| `baseline_degree` | — | polynomial degree, for polynomial baselines |
| `baseline_basis` | `power` | `power`, `legendre`, `chebyshev` |
| `baseline_iterations` | — | iterations for the asymmetric baselines |
| `height_mode` | `noise` | `noise` = multiples of the spectrum's own σ |
| `height` | **3.0** | threshold, in σ |
| `min_distance` | — | minimum peak separation |
| `smooth_type` / `smooth_points` | — | pre-search smoothing |
| `temperature_k` | — | sets the k_BT/2 binning grid |
| `x_energy_unit` | — | axis unit |
| `direction` | — | which sweep direction to use |

### Layout

| parameter | default | meaning |
|---|---|---|
| `scan_type` | `auto` | `map_meander` reverses alternate rows, `map_raster` does not, `line` gives a single row, `auto` reads the dataset's metadata |

## Output

Filed as `maps/<dataset>/<format>/` — `gsf`, `tiff`, `csv`:

- one calibrated map **per interval**
- a **joined interval map** when the run covers several intervals: position
  across, interval up, indexed by midpoint. Registered as a line-scan dataset
  (`<base> - Interval Map`) so the Hyperspectral tab opens it as a kymograph.
- `<dataset> - Map Values`

**Only the joined map is opened** on completion. The per-interval maps are
registered in the browser but not shown — dozens of windows lock the
workspace up.

## Method

For each spectrum: fit and subtract the background, then integrate over each
interval with `positive_integral`. The value becomes one cell of that
interval's map; the cells are laid out according to `scan_type`.

A detected run's intervals are the **occupied bins**, binned at the coarser of
k_BT/2 and the sweep's own step — the same grid Confinement Analysis reports
on, so both tools find the same states.

`MAP_DEFAULTS` differs from the peak-analysis defaults deliberately: **3σ**
and a **1σ noise floor**. Maps use 3σ for the same sensitivity but far more of
the map's weight in real states; peak analysis keeps 2σ because 3σ costs ~8%
of weak states. The floor is what stops a map reading as a fit diagnostic —
a bin with no state integrates pure noise, negative half the time; flooring at
1σ zeroes 39% of cells while keeping 99.4% of the signal.

## Notes

- **There is deliberately no FWHM-merging fallback.** It fused everything into
  two or three bands tens of mV wide — 2 intervals where 216 states had been
  detected — which is what "the map generator finds almost no peaks" was.
- `min_spectra_per_bin` drops thinly-populated bins **without widening the
  rest**.
- The interval map's metadata must not use the `intervals` key: that marks a
  dataset as integrated values, which the Hyperspectral tab skips. It uses
  `interval_bounds` / `interval_midpoints`.
- Positivity is **unconditional** here — the engine runs on dI/dV only, so
  there is nothing signed to be wrong about.
