# Line Scan Designer

The [Confinement Designer](confinement-designer.md) run at **every position
along a line scan**. Where the Designer asks *which well gives this spectrum
its ladder of levels?* — one spectrum, every candidate geometry ranked for
inspection — this tool asks that at every point along the line and reports
how the answer changes with position: one best size per point, positions
grouped by the size they share, and a strip map of size along the line.

Tune the search on one spectrum in the Designer first, then run it here
along the whole line: the parameters are the same.

**Menu** Tools → Confinement → Line Scan Designer · **Panel**
`LineScanDesignerTool.qml` · **Method** `design_line_scan()` ·
**Batch key** `line_scan_designer`

## Input

A line-scan dataset — the ordered positions along the line, one spectrum each.

## Parameters

The designer parameters (see [Confinement
Designer](confinement-designer.md)) — `ndim`, `coords`, `sym`, `meff_e`,
`meff_h`, `carrier`, `split_e`, `split_h`, `pair_tol_nm`, `match`, `maxsol`,
`priority`, `baseline`, `height` — plus:

| parameter | default | meaning |
|---|---|---|
| `points` | all | which positions to analyse |
| `segments` | — | split the line into segments |
| `groups` | — | grouping of results |
| `group_tol_nm` | — | how close two sizes must be to count as the same |
| `max_rrmse` | — | reject a fit worse than this |
| `position_label` | — | how positions are labelled in the output |

## Output

| output | contents |
|---|---|
| flat table | one row per position: the best candidate, its size, its error, its group |
| strip map | the size along the line, as a map |

**"No confinement" is a real answer** and is recorded as such — a position
where nothing fits well enough is `NaN`, never 0. `group` is numeric. The
`reason` column says why: `no_peaks` (the detector found nothing),
`no_peaks_in_branch` (peaks were found — `n_peaks` says how many — but none
on the searched carrier's side of the electron/hole edges or outside the
neutral band; `n_targets` is the count that was left to fit, so 11 peaks
and 0 targets means the split, not the detector, is what to change),
`too_few_peaks`, `no_candidate`, `error_above_limit`, `no_carrier_pair`.

## Method

One independent search per position, then positions whose sizes agree within
`group_tol_nm` are collected into groups — which is how a terrace of constant
width shows up as one group spanning a stretch of the line.

## Notes

- `NaN` and 0 mean different things here. 0 nm would be a measurement; `NaN`
  is the absence of one, and plotting them the same way would invent a
  feature.
- This is much slower than a single search — it is one full search per
  position — so it runs on the worker and is cancellable.
