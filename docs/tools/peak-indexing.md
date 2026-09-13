# Peak Indexing — sunset

Removed from the Tools menu in the tool rework. It ran `find_peaks` on
data that had to be background-corrected beforehand, and three tools now
find peaks with a baseline built in: [Spectral
Features](spectral-features.md) (gated search on the corrected curve, per
spectrum), [Multi-Peak Fitting](multi-peak-fitting.md) (peaks and baseline
fitted together, per spectrum, with the fitted curves) and [Confinement
Analysis](confinement-analysis.md) (the full engine, with the occupancy
table).

The engine (`find_peaks()` in the backend, `adaptive_prominence()`) is
unchanged and still drives the **Peak Finder workflow node**, so saved
workflows keep running.
