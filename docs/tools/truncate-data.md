# Truncate Data

Cuts every spectrum down to a bias window.

**Menu** Tools → Truncate Data · **Panel** `TruncateTool.qml` ·
**Method** `truncateData()` → `_do_truncate_data()`

## Input

Any spectral dataset.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `min_val` | axis minimum | lower bound, in the axis's own units |
| `max_val` | axis maximum | upper bound |

## Output

A truncated dataset in the browser, with the axis and every spectrum cut to
the window.

## Method

Boolean mask on the independent axis; rows outside the window are dropped
from the frame. Samples are kept or dropped whole — nothing is interpolated
onto the new endpoints.

## Notes

- Useful before background fitting, to keep a polynomial from being dragged by
  a region you do not care about.
- Truncating away part of a sweep changes what later tools see as the band
  edge, which is what Confinement Dimensionality reads the dimensionality off.
