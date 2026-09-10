# Curve Smoothing

Smooths every spectrum in a dataset. Mostly used before differentiation,
which amplifies noise badly enough that a raw dI/dV is often unusable.

**Menu** Tools → Curve Smoothing · **Panel** `CurveSmoothingTool.qml` ·
**Method** `smooth_curves()` in `tool_implementations.py`

## Input

Any spectral dataset. Every column is smoothed independently against the
shared axis.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `smoothing_type` | Savitzky-Golay | `Savitzky-Golay`, `Gaussian` or `Moving Average` |
| `window_size` | 11 | samples in the window. Forced odd for Savitzky–Golay |
| `poly_order` | 3 | polynomial order, Savitzky–Golay only; must be < `window_size` |

## Output

| output | where |
|---|---|
| `<dataset> - Smoothed` | project browser, beside the source |
| `<name>_Smoothed.csv` | `<project>_outputs/smoothed/` |

## Method

**Savitzky–Golay** (`scipy.signal.savgol_filter`) fits a polynomial over a
sliding window and takes its value at the centre. It preserves peak height and
width far better than a moving average, which is why it is the default: a
box filter of the same width flattens a narrow state noticeably.

**Gaussian** convolves with a Gaussian kernel — smoother in the frequency
domain, no ringing, but it does broaden peaks.

**Moving average** is the plain box filter. Cheap, and fine when you only want
the trend.

## Notes

- Smoothing is an **instrument function** in everything downstream: it decides
  what counts as resolved. The Derivative Calculator records the window it
  used for exactly this reason.
- The window is in **samples, not volts**. The same window is a different
  energy resolution on a 128-point and a 512-point sweep.
