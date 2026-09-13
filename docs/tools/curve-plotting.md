# Curve Plotting

Overlay curves from one or more datasets in a single graph window to compare
them. **A viewer: it writes nothing.** (Until the tool rework this was
*Curve Analysis*, a panel that listed curves and plotted none; the panel
file keeps that name.)

**Menu** Tools → View → Curve Plotting · **Panel** `CurveAnalysisTool.qml` ·
**Method** `plotDatasetCurves()`

## Input

Any spectral datasets — a multi-dataset selection, so spectra from
different acquisitions can be laid over each other.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `mode` | all | which curves of each dataset: `all`, `first` N, `every` Nth, index `range` |
| `count` / `step` | 10 | N for `first` / `every` |
| `start` / `stop` | 1 / last | 1-based inclusive bounds for `range` (0 = last) |
| `normalize` | false | divide each curve by its own maximum |
| `offset` | 0 | vertical spacing between successive curves — a waterfall view |

## Output

One embedded graph window. No dataset is created and no file is written.
Curves are labelled `<dataset> - <spectrum>` so the legend still says where
each came from once datasets are mixed; with several datasets the window is
titled `Plot: <first> (+n)`.

## Method

Reads the selected columns straight out of each dataset and emits them as
one `openDatasetEmbedded` — the same signal a double-click in the browser
uses, minus the table window.

## Notes

- Plotting hundreds of curves is slow; pick *Every Nth* for a large map.
- For numbers rather than a picture, see [Spectral
  Features](spectral-features.md).
