# Background Subtraction

Subtracts one dataset from one or more others — a measured background rather
than a fitted one.

**Menu** Tools → Background Subtraction · **Panel**
`BackgroundSubtractionTool.qml` · **Method**
`subtract_background_datasets()`, `src/processing/background_subtraction.py`

## Input

Two selections: the **signal** datasets, and the single **background**
dataset. They must share a compatible independent axis.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `signal_names` | — | one or more datasets to correct |
| `background_name` | — | the dataset subtracted from each |

## Output

| output | where |
|---|---|
| `<dataset> - BgSub` | one per signal dataset |
| `<name>_BgSub.csv` | `<project>_outputs/background_subtracted/` |

## Method

Column-wise subtraction on the shared axis. When the background holds a single
curve it is subtracted from every column of the signal; when the shapes match
it is subtracted column for column.

`BackgroundSubtractionResult` records what was actually done — how the two
axes were reconciled and how many columns were matched — so a silent
mismatch does not pass for a result.

## Notes

- This is the right tool for a **measured** background: a spectrum taken off
  the feature, a dark reference, a substrate curve. For a background that has
  to be *inferred* from the curve itself, use [Curve
  Fitting](curve-fitting.md) or the arPLS baseline in [Confinement
  Analysis](confinement-analysis.md).
- The result can go negative; that is expected for a signed quantity and the
  positivity rule does not apply to the subtraction itself.
