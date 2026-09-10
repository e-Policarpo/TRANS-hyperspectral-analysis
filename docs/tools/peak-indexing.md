# Peak Indexing

Finds peaks in each spectrum and emits them as a dataset.

**Menu** Tools → Peak Indexing · **Panel** `PeakIndexingTool.qml` ·
**Method** `find_peaks()`

## Input

Any spectral dataset.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `prominence` | adaptive | minimum prominence; ignored when `adaptive` is on |
| `min_distance` | — | minimum separation between peaks, in samples |
| `adaptive` | true | derive the threshold from each spectrum instead of using a fixed number |

## Output

| output | where |
|---|---|
| `<dataset> - Peaks` | a dataset, so peaks can be captured by a workflow's dataset-output node |
| `<name>_Peaks.csv` | `<project>_outputs/peaks/` |

## Method

`scipy.signal.find_peaks` on each column. With `adaptive` on, the threshold is
`adaptive_prominence()`:

```
max(span_fraction × (max − min),  noise_sigmas × σ_noise)
```

— the larger of 5% of the curve's span and 3σ of its own noise. One term
protects flat, noisy spectra (where the noise term dominates) and the other
well-resolved ones (where the span term does), which is what makes a single
setting work across a dataset instead of needing a number per measurement.

σ is estimated from the MAD of first differences, which is robust to the peaks
themselves.

## Notes

- The result is a **dataset**, not a table. That was deliberate: a table could
  not be captured by workflow dataset-output nodes.
- For peaks on a curved background — a band edge — this is the wrong tool,
  because it does not remove one. Use [Confinement
  Analysis](confinement-analysis.md), which fits the background and searches in
  the same pass.
