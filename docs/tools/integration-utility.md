# Integration Utility

Integrates each spectrum over one or more bias intervals — the area under
dI/dV, which is the spectral weight in that energy window.

**Menu** Tools → Integration Utility · **Panel** `IntegrationTool.qml` ·
**Method** `integrate()`, `src/processing/integration.py`

## Input

A spectral dataset. Intervals can be typed, or loaded from a file with
`loadIntervalsFromFile()`.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `intervals` | — | list of `[lower, upper]` pairs in axis units |
| `positive_only` | **true** | integrate the positive part only |

## Output

A dataset of integrated values — one row per spectrum, one column per
interval. Its metadata carries the `intervals` key, which marks it as
integrated values rather than spectra; the Hyperspectral tab deliberately
skips such datasets.

## Method

Trapezoidal integration over the samples inside each interval.

With `positive_only` on — the default, and the right one for dI/dV — the
integral is `positive_integral()`, the area of the regions above zero. This is
**not** `np.trapz(np.maximum(y, 0))`: clipping first moves a zero crossing to
the end of its segment and over-counts the triangle beyond it, by a factor of
two on a curve that swings evenly about zero. The crossing is solved for, so
the answer does not depend on how coarse the bias grid is.

## Notes

- **Turn `positive_only` off for signed quantities.** Current in an I(V) sweep
  really is negative at negative bias, and so is a difference spectrum.
  Leaving it on would silently discard half of them.
- Excluding negatives on its own makes an *empty* interval read **higher**,
  not lower, because the two-sided noise no longer cancels itself. The Map
  Generator pairs this with a 1σ noise floor for exactly that reason; here
  there is no floor, so an interval with no states integrates a small positive
  number rather than zero.
