# Average Curves

Collapses a dataset to a single mean curve.

**Menu** Tools → Average Curves · **Panel** `AverageCurvesTool.qml` ·
**Method** `average_curves()`

## Input

Any spectral dataset. Only meaningful when the curves are repetitions of the
same measurement — averaging across positions averages across the sample.

## Parameters

None.

## Output

| output | where |
|---|---|
| `<dataset> - Average` | browser |
| `<name>_Average.csv` | `<project>_outputs/averaged/` |

## Method

`np.nanmean` across columns, so a NaN at one bias step in one curve does not
wipe out that step of the average — partial spectra still contribute
everywhere they have data.

Stamps `original` in the metadata, so the result overlays onto the source's
open graph window rather than opening a separate one.

## Notes

- For an overview dataset with many points, this averages **everything into
  one curve**. If you want one curve per point, use
  [Filter Bad Data](filter-bad-data.md) with outlier filtering, which writes
  a per-point average that also excludes the curves that would drag it.
