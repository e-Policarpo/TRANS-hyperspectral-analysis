# Tool pages

One page per tool: what it takes, every parameter with its default, what it
writes, and the method behind it. The parameter tables are generated from the
QML panels and the backend signatures, so they say what the program actually
does.

For the wider picture — data model, formats, heuristics, architecture — see
[`../TRANS_REFERENCE.md`](../TRANS_REFERENCE.md).

## Tools

Single operations. Several accept a multi-dataset selection and process the
datasets one after another; those are marked **batch**.

| tool | does | page |
|---|---|---|
| 1D FFT | frequency content of each spectrum | [fft-1d](fft-1d.md) |
| Average Curves | one mean curve from a dataset | [average-curves](average-curves.md) |
| Background Subtraction | subtract one dataset from others | [background-subtraction](background-subtraction.md) |
| Cosmic Ray Filter | remove single-sample spikes | [cosmic-ray-filter](cosmic-ray-filter.md) |
| Curve Analysis | inspect curves; a viewer, writes nothing | [curve-analysis](curve-analysis.md) |
| Curve Fitting | polynomial fit + coefficients | [curve-fitting](curve-fitting.md) |
| Curve Smoothing | Savitzky–Golay, Gaussian, moving average | [curve-smoothing](curve-smoothing.md) |
| Derivative Calculator | dI/dV and d²I/dV² — **batch** | [derivative-calculator](derivative-calculator.md) |
| Filter Bad Data | separate usable spectra from junk — **batch** | [filter-bad-data](filter-bad-data.md) |
| Gradient Filter | edge filters on an image | [gradient-filter](gradient-filter.md) |
| Image Smoothing | smooth an image channel | [image-smoothing](image-smoothing.md) |
| Integration Utility | area under curves over bias intervals | [integration-utility](integration-utility.md) |
| Map Discretizer | reduce a map's spatial resolution | [map-discretizer](map-discretizer.md) |
| Map Processing | operations on map channels | [map-processing](map-processing.md) |
| Peak Indexing | find and index peaks | [peak-indexing](peak-indexing.md) |
| Spatial Average | average neighbouring positions | [spatial-average](spatial-average.md) |
| Spectral Axis Converter | nm ↔ eV ↔ cm⁻¹ | [spectral-axis-converter](spectral-axis-converter.md) |
| Truncate Data | cut the sweep to a bias window | [truncate-data](truncate-data.md) |

## Composite tools

A whole analysis in one run.

| tool | does | page |
|---|---|---|
| Confinement Analysis | peaks + background in one pass; occupancy table | [confinement-analysis](confinement-analysis.md) |
| Confinement Designer | find the geometry matching measured levels | [confinement-designer](confinement-designer.md) |
| Confinement Dimensionality | 0D/1D/2D from level ratios — **batch** | [confinement-dimensionality](confinement-dimensionality.md) |
| Detect Bandgap & Doping | gap size and N/P/neutral per spectrum | [detect-bandgap-doping](detect-bandgap-doping.md) |
| Dirac Point Estimator | Dirac point from slope intersections | [dirac-point-estimator](dirac-point-estimator.md) |
| Line Scan Designer | one confinement search per position — **batch** | [line-scan-designer](line-scan-designer.md) |
| Map Generator | background + intervals + maps in one pass — **batch** | [map-generator](map-generator.md) |
| Multi-Peak Fitting | Gaussian / Lorentzian / pseudo-Voigt | [multi-peak-fitting](multi-peak-fitting.md) |
| Quantum Dot Solver | solve a 0D dot | [quantum-dot-solver](quantum-dot-solver.md) |
| Quantum Well Solver | solve a 1D well | [quantum-well-solver](quantum-well-solver.md) |
| Spectral Features | per-spectrum feature table | [spectral-features](spectral-features.md) |

## Reading a page

**Input** says what kind of dataset the tool expects — and where that matters
physically, why. **Parameters** lists every knob the panel exposes with its
default. **Output** says what appears in the browser and what lands in
`<project>_outputs/`. **Method** is the algorithm, including the measurements
behind any default that was calibrated rather than chosen.
