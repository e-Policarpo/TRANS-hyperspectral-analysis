# 1D FFT

Frequency content of each spectrum.

**Menu** Tools → 1D FFT · **Panel** `FFT1DTool.qml` ·
**Method** `fft1D()` → `_do_fft1D()`

## Input

Any spectral dataset.

## Parameters

None.

## Output

A dataset whose axis is frequency (`1/<axis unit>`) and whose columns are the
magnitude of each spectrum's real FFT.

## Method

`np.fft.rfft` per column, magnitude taken. The frequency axis is
`np.fft.rfftfreq(n, d)` where `d` is the mean axis step, so the units are the
reciprocal of the input axis.

## Notes

- The usual reason to look at this is **periodic pickup**: mains hum or a
  piezo resonance shows as a sharp line well above the smooth low-frequency
  content of the spectrum itself.
- [Filter Bad Data](filter-bad-data.md) does this automatically, writes the
  FFT of every spectrum as a dataset, and can interpolate the offending lines
  out of the curves it keeps.
- A spectrum with NaNs (railed samples) is transformed on its finite part, so
  its frequency axis may be shorter than the others'.
