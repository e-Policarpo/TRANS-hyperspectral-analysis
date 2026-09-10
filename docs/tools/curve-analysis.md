# Curve Analysis

Inspect the curves in a dataset. **A viewer: it writes nothing.**

**Menu** Tools → Curve Analysis · **Panel** `CurveAnalysisTool.qml`

## Input

Any spectral dataset.

## Parameters

None. The panel lists the dataset's curves and plots the ones you select.

## Output

None. No dataset is created and no file is written.

## Method

Reads `getDatasetInfo()` for the curve list and plots the selection. There is
no backend tool method behind this panel — it is the one entry in the Tools
menu that is purely a view.

## Notes

- Use it to see what you have before choosing a tool: how many curves, how
  they are named, whether they overlap.
- For statistics rather than a picture, see [Spectral
  Features](spectral-features.md), which emits a per-spectrum table.
