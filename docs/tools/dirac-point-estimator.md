# Dirac Point Estimator — sunset

Folded into [Spectral Features](spectral-features.md) in the tool rework
as the **Dirac point** feature group: `dirac_point`, `dirac_conductance`,
`dirac_slope_left`, `dirac_slope_right`, `dirac_r2_left`, `dirac_r2_right`,
`dirac_slope_asymmetry`, one row per spectrum, previewed on the panel's plot
as the two fitted branches and their crossing.

The branch windows are `auto` (from each end of the sweep to the gap edge
the table has already found, trimmed at the outer end — the same recipe as
`auto_detect_dirac_ranges`, but reusing the gap so the branches and the gap
always agree), `manual` (four bias limits) or `off`.

The engine (`fit_dirac_point()` in `src/backend/sts_algorithms.py`,
`estimate_dirac_point()` in the backend) is unchanged and still drives the
**Dirac Point Estimator workflow node**.

Use: Tools → Fit and features → Spectral Features → *Dirac point*.
