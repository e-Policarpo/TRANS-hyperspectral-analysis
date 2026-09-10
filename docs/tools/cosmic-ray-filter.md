# Cosmic Ray Filter

Removes single-sample spikes — cosmic rays on a CCD, or an electrical glitch.

**Menu** Tools → Cosmic Ray Filter · **Panel** `CosmicRayFilterTool.qml` ·
**Method** `remove_cosmic_rays()`, `src/processing/cosmic_ray.py`

## Input

Any spectral dataset. Most useful on PL/Raman, where cosmic rays are a real
and frequent artifact.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `threshold_sigmas` | 5.0 | how far above the local median a sample must sit |
| `window` | 5 | median-filter width, in samples |
| `max_width` | 3 | widest run of samples treated as a spike |

## Output

| output | where |
|---|---|
| `<dataset> - CR Cleaned` | browser |
| `<name>_CR_Cleaned.csv` | `<project>_outputs/cosmic_ray/` |

## Method

Median-filter the spectrum, take the residual, and flag samples more than
`threshold_sigmas × 1.4826 × MAD` above it. Runs no wider than `max_width` are
replaced by interpolation across the gap; anything wider is left alone, on the
grounds that a real peak is wider than a cosmic ray.

## Notes

- **The default is marginal, knowingly.** The residual of a running median is
  not Gaussian — it has heavier tails than the MAD-derived σ describes — so a
  nominal 5σ is really about 4.3σ, and roughly one sample per thousand of pure
  noise crosses it. On a 2000-sample spectrum expect an occasional false
  positive. Raise `threshold_sigmas` if that matters more than catching every
  spike.
- `max_width` is what protects narrow real peaks. Do not raise it much.
