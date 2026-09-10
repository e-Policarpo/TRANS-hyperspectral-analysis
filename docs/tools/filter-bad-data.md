# Filter Bad Data

Separates usable spectra from junk, and — optionally — removes the curves
that are individually sound but would distort an average. Accepts a
**multi-dataset selection**.

**Menu** Tools → Filter Bad Data · **Panel** `FilterBadDataTool.qml` ·
**Method** `filter_bad_data()` · **Batch key** `filter_bad_data`

## Input

Any spectral dataset. **Outlier filtering is for overview datasets** — sets of
repetitions of the same measurement. On a line scan, where every position is
supposed to differ, it will report the ends of the line as outliers. The panel
warns about this and then lets you do it anyway.

## Parameters

### Detector weights

A spectrum is bad when its **highest** weighted score reaches the threshold,
so any single detector firing is enough. Set a weight to 0 to switch that
detector off.

| parameter | default | detector |
|---|---|---|
| `weight_saturation` | 1.0 | signal railed and the noise died with it |
| `weight_noise` | 1.0 | no signal above the noise |
| `weight_linear` | 1.0 | a straight line — a contact artifact |
| `weight_periodic` | 1.0 | a sharp line in the FFT |
| `weight_partial_noise` | 1.0 | part of the sweep broke down |
| `weight_featureless` | 1.0 | no structure at all |
| `threshold` | 0.5 | score at which a spectrum is called bad |

### Featureless detector

| parameter | default | meaning |
|---|---|---|
| `min_structure_ratio` | 3.0 | amplitude, in units of what the noise alone would produce, above which the curve is definitely real |
| `min_coherence` | 0.12 | coherence above which it is definitely real; the score is 1.0 at half this |

### Outliers — opt-in, per kind

| parameter | default | meaning |
|---|---|---|
| `filter_offset_outliers` | false | remove curves displaced across the whole sweep |
| `filter_bandgap_outliers` | false | remove curves departing over part of it |
| `filter_saturation_outliers` | false | remove curves covering too little bias range |
| `max_*_outliers` | 5 | **per group.** Find more than this and *nothing* is removed |
| `outlier_group_by` | `point` | `point` = each point's repetitions; `dataset` = all curves as one population |
| `outlier_intervals` | 8 | bias sub-intervals the sweep is split into |
| `outlier_z` | 3.5 | robust z above which an interval counts as departing |

### Other

| parameter | default | meaning |
|---|---|---|
| `correct_periodic` | false | interpolate sharp FFT lines out of the spectra kept as good |
| `min_finite_fraction` | 0.5 | below this share of finite samples a spectrum is rejected outright |

## Output

| output | contents |
|---|---|
| `<dataset> - Good Data` | the spectra that passed |
| `<dataset> - Bad Data` | the ones that did not |
| `<dataset> - Outliers Removed` | **one curve per point**, each the average of that point's surviving repetitions. Written only when outlier filtering is on |
| `<dataset> - FFT Spectra` | frequency content of each spectrum |
| `<name>_filter_report.txt` | every spectrum's scores and diagnostics |

All in `<project>_outputs/curves/<name>_Filtered/`.

## Method

### The empty gate

A spectrum with fewer than `min_finite_fraction` finite samples is rejected
**before scoring**. Every detector returns 0 for a curve it cannot measure and
the combination is a maximum, so an all-NaN column used to score 0 across the
board and land in *Good Data*. On the calibration dataset, **103 of 167
"good" spectra were entirely empty.**

### The six detectors

**Featureless** is the one that catches a dI/dV sitting flat above the noise
floor — it passes every other test. Two independent tests, either enough:

- *Amplitude*: the smoothed, detrended curve does not depart from a straight
  line by more than the noise could manage (`ratio` near 1).
- *Coherence*: `span / total variation` of the smoothed curve. A band edge
  rises once and scores ~0.45; 1/f noise wanders up and down dozens of times
  and scores ~0.05. **This is the half that works on real data**, where the
  noise is 1/f and dead spectra sit 10–30× above the white-noise expectation
  while holding no shape. Measured: kept curves min 0.091, rejected max 0.084.

**Saturation** is the longest run at a rail *whose scatter collapses below
0.25σ*. A gap floor is a plateau too; what a railed converter loses and a gap
keeps is its own noise. Counting samples near an extreme flagged every
low-noise gap spectrum.

**Noise** is smoothed peak-to-peak ÷ robust MAD σ. The raw peak-to-peak
measures the noise twice over on a featureless curve.

**Periodic** is power *concentration* — the peaks' share of the analysed band
divided by their fair share. Real STS measures 4.5–8.5×; a 1%-amplitude sine
artifact 26–58×. Scoring the raw power share instead marked **91.5%** of real
spectra as periodic, because on a smooth spectrum nearly all power sits at low
frequency and any flagged bin saturates the score.

**Partial noise** needs a window with no structure **and** noise ≥3× the
sweep's quietest stretch. Both, or every gapped spectrum is condemned.

### Outliers

Area per bias sub-interval, median/MAD z-scored across the curves **taken at
the same point** — grouping read from `spectrum_meta`, so a line scan's
overview compares each position with itself. Offset departs in ≥75% of
intervals; band gap in a contiguous run of ≥2 (a single interval is what noise
produces: 3.6% of clean curves at a run of 1, 0.0% at 2); saturation covers
<0.8× the median bias range.

**Past the limit, nothing is removed.** If a fifth of the curves are
"outlying", what has been found is a distribution, not a few bad
acquisitions — and the report says so.

## Notes

- Removed outliers are marked GOOD in the per-spectrum table, because they
  pass every individual test. They move to Bad Data as a decision about the
  **population**.
- The per-point averages record four counts that add up: `n_input`,
  `n_averaged`, `n_outliers_removed`, `n_rejected_by_tests`.
