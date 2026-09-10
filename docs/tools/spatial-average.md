# Spatial Average

Averages neighbouring positions of a spectral map into blocks — trading
spatial resolution for signal.

**Menu** Tools → Spatial Average · **Panel** `SpatialAverageTool.qml` ·
**Method** `spatialAverage()` → `_do_spatial_average()`

## Input

A dataset with a grid layout: its `dimensions` must describe the map, since
the blocks are taken over that grid.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `discrete_x` | — | block width, in grid points |
| `discrete_y` | — | block height |
| `ignore_empty` | true | skip blocks with no usable spectra rather than emitting NaN |
| `save_intermediate` | false | also write the per-block intermediates |

## Output

A dataset with one spectrum per block, its `dimensions` reduced accordingly.

## Method

The grid is tiled into `discrete_x × discrete_y` blocks and the spectra in
each are averaged. Averaging *n* independent curves improves the
signal-to-noise ratio by √n, so a 2×2 block halves the noise at the cost of
four times the area.

A variant slot, `spatialAverageWithSelection`, averages an explicit selection
instead of a regular tiling.

## Notes

- The dataset must actually be a grid. On a line scan or an unordered point
  set the block geometry is meaningless.
- This averages across **different places on the sample**, which is only
  sensible when you accept the spatial blurring. To average repetitions *at*
  a place, see [Filter Bad Data](filter-bad-data.md)'s per-point averages.
