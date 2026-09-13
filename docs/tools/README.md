# Tool pages

One page per tool: what it takes, every parameter with its default, what it
writes, and the method behind it. The parameter tables are generated from the
QML panels and the backend signatures, so they say what the program actually
does.

For the wider picture — data model, formats, heuristics, architecture — see
[`../TRANS_REFERENCE.md`](../TRANS_REFERENCE.md).

## Tools

Single operations. Every one takes a multi-dataset selection (Ctrl/Cmd-click,
Shift-click, or a drag from the project browser) and processes the datasets
one after another.

| tool | does | page |
|---|---|---|
| 1D FFT | magnitude and phase of every spectrum | [fft-1d](fft-1d.md) |
| Average Curves | one mean curve per dataset | [average-curves](average-curves.md) |
| Cosmic Ray Filter | remove single-sample spikes | [cosmic-ray-filter](cosmic-ray-filter.md) |
| Curve Background Flattening | fit a background and subtract it | [curve-background-flattening](curve-background-flattening.md) |
| Curve Plotting | overlay curves from several datasets; a viewer, writes nothing | [curve-plotting](curve-plotting.md) |
| Curve Smoothing | Savitzky–Golay, Gaussian, moving average | [curve-smoothing](curve-smoothing.md) |
| Derivative Calculator | dI/dV and d²I/dV² | [derivative-calculator](derivative-calculator.md) |
| Filter Bad Data | separate usable spectra from junk | [filter-bad-data](filter-bad-data.md) |
| Gradient Filter | gradient magnitude of a browser map or image, calibrated | [gradient-filter](gradient-filter.md) |
| Integration Utility | area under curves over bias intervals | [integration-utility](integration-utility.md) |
| Map Discretizer | reduce a map's spatial resolution | [map-discretizer](map-discretizer.md) |
| Map Processing | operations on map channels | [map-processing](map-processing.md) |
| Subtract Detector Background | subtract a measured reference from others | [subtract-detector-background](subtract-detector-background.md) |
| Truncate Data | cut the sweep to a bias window | [truncate-data](truncate-data.md) |
| Unit Converter | relabel in place, nm ↔ eV ↔ cm⁻¹, set x / y by formula with a preview | [unit-converter](unit-converter.md) |

## Composite tools

A whole analysis in one run.

| tool | does | page |
|---|---|---|
| Confinement Analysis | peaks + background in one pass; occupancy table | [confinement-analysis](confinement-analysis.md) |
| Confinement Designer | find the geometry matching one spectrum's levels | [confinement-designer](confinement-designer.md) |
| Confinement Dimensionality | 0D/1D/2D from level ratios | [confinement-dimensionality](confinement-dimensionality.md) |
| Line Scan Designer | the Designer at every position of a line | [line-scan-designer](line-scan-designer.md) |
| Map Generator | spatial averaging + background + intervals + maps in one pass; integrals as dataset and CSV | [map-generator](map-generator.md) |
| Multi-Peak Fitting | Gaussian / Lorentzian / pseudo-Voigt on every spectrum; peak table + fitted curves | [multi-peak-fitting](multi-peak-fitting.md) |
| Quantum Dot Solver | solve a 0D dot | [quantum-dot-solver](quantum-dot-solver.md) |
| Quantum Well Solver | solve a 1D well | [quantum-well-solver](quantum-well-solver.md) |
| Spectral Features | per-spectrum table: gap, doping, metallicity, states, Dirac point | [spectral-features](spectral-features.md) |

## Sunset

Removed from the Tools menu in the tool rework; each page says where the
function went. The engines live on as workflow nodes.

| tool | went to | page |
|---|---|---|
| Detect Bandgap & Doping | Spectral Features (gap and doping groups) | [detect-bandgap-doping](detect-bandgap-doping.md) |
| Dirac Point Estimator | Spectral Features (Dirac point group) | [dirac-point-estimator](dirac-point-estimator.md) |
| Image Smoothing | Map Processing; workflow node | [image-smoothing](image-smoothing.md) |
| Peak Indexing | Spectral Features, Multi-Peak Fitting, Confinement Analysis; Peak Finder node | [peak-indexing](peak-indexing.md) |
| Spatial Average | Map Generator (spatial averaging step) | [spatial-average](spatial-average.md) |
| Spectral Axis Converter | Unit Converter (convert axis) | [unit-converter](unit-converter.md) |

## Reading a page

**Input** says what kind of dataset the tool expects — and where that matters
physically, why. **Parameters** lists every knob the panel exposes with its
default. **Output** says what appears in the browser and what lands in
`<project>_outputs/`. **Method** is the algorithm, including the measurements
behind any default that was calibrated rather than chosen.
