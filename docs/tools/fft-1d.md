# 1D FFT

Frequency content of every spectrum of a dataset — a beating in a bias
sweep, a fringe period in a wavelength scan, mains pickup.

**Menu** Tools → Transform → 1D FFT · **Panel** `FFT1DTool.qml` ·
**Method** `_do_fft1D()` · **Batch key** `fft_1d`

## Input

Any spectral datasets — a multi-dataset selection, transformed one after
another.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `window` | `hann` | taper before the transform: `none` (rectangular), `hann`, `hamming`, `blackman` |
| `detrend` | true | remove each spectrum's mean first |
| `one_sided` | true | keep the non-negative frequencies only |
| `power_spectrum` | false | emit \|F\|² instead of \|F\| |

## Output

| output | where |
|---|---|
| `<dataset> - FFT Magnitude` (or `- FFT Power`) | axis `Frequency (1/<unit>)`, one column per spectrum |
| `<dataset> - FFT Phase` | same axis, phase in radians |
| `<name>_FFT_Magnitude.csv`, `<name>_FFT_Phase.csv` | `<project>_outputs/fft/` |

Both datasets carry the source's spatial keys, so the FFT of a line scan is
still that line scan's positions and maps as such.

## Method

`np.fft.fft` per column after the window and the detrend, frequencies from
`np.fft.fftfreq(n, d)` with `d` the mean axis step, so the frequency unit is
the reciprocal of the axis unit — `1/V` for a bias sweep. A windowed
transform is rescaled by the window's mean so its amplitudes compare with an
unwindowed one. Non-finite samples are zeroed before the transform.

**Detrend** matters: a curve that never crosses zero has a DC term that
dwarfs every other frequency, and the plot shows nothing else. The **window**
matters for the same reason at the ends of the sweep: a rectangular window
leaks the step at each end into every frequency.

## Notes

- The usual reason to look at this is **periodic pickup**: mains hum or a
  piezo resonance shows as a sharp line well above the smooth low-frequency
  content of the spectrum itself.
- [Filter Bad Data](filter-bad-data.md) does this automatically, writes the
  FFT of every spectrum as a dataset, and can interpolate the offending lines
  out of the curves it keeps.
