# Line Scan Designer

Runs a confinement search at **every position along a line scan**, then groups
the positions by the size it found.

**Menu** Tools → Composite tools → Line Scan Designer · **Panel**
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
where nothing fits well enough is `NaN`, never 0. `group` is numeric.

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
