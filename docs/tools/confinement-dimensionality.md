# Confinement Dimensionality

Decides whether the states in a spectrum are confined in 0, 1 or 2
dimensions — from the **ratios between levels**, not from their absolute
positions. Accepts a **multi-dataset selection**.

**Menu** Tools → Composite tools → Confinement Dimensionality · **Panel**
`ConfinementDimensionalityTool.qml` · **Method**
`analyze_confinement_dimensionality()` · **Batch key**
`confinement_dimensionality`

## Input

dI/dV spectra with resolvable states.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `temperature_k` | — | sets the thermal resolution limit |
| `v_mod` | — | lock-in modulation amplitude |
| `mod_convention` | — | whether `v_mod` is amplitude or RMS |
| `deriv_kind` | — | how the derivative is taken |
| `deriv_window_v` | — | differentiation window **in volts** |
| `deriv_polyorder` | — | polynomial order for the derivative |
| `smooth_gradient` | — | smooth the gradient |
| `use_edge_as_offset` | — | measure levels from the band edge rather than from zero bias |
| `n_kt` | — | how many k_BT count as resolved |
| `max_skips` | — | levels allowed to be missing from the ladder |
| `height`, `height_mode`, `baseline` | as Confinement Analysis | the peak search |

## Output

| output | contents |
|---|---|
| `<dataset> - Dimensionality` | the verdict per spectrum, with the ranking behind it |
| files | `<project>_outputs/peaks/` |

## Method

A particle in a box has a level ladder whose **ratios** are fixed by the
geometry and independent of size and effective mass: 1, 4, 9 … for a 1D box,
a different signature for a 2D square, another for a 3D cube.
`src/physics/level_patterns.py` holds these; `level_ratio_fit.py` fits each
pattern to the measured ladder and ranks them by AIC, returning a
`RatioVerdict`.

**Levels are measured from the band edge, not from V ≈ 0.** The confinement
sits on top of the band structure, so zero bias is not where the ladder
starts; using it gives a systematically wrong first level and the ratios come
out meaningless.

The **thermal slope ceiling** `e/k_BT` bounds how sharply a real edge can
rise. A measured slope steeper than that is instrumental, not physical, and is
rejected rather than fitted.

## Notes

- The verdict can be **ambiguous**, and says so: when two geometries fit
  within ΔAIC of about 2, the data does not distinguish them. That is a real
  answer, not a failure.
- The tool refuses to answer in four situations rather than guess — too few
  levels, levels that are not resolved at the stated temperature and
  modulation, no identifiable band edge, and a slope above the thermal
  ceiling.
- Resolution needs the **modulation** as much as the temperature; without
  `v_mod` a spectrum's energy resolution cannot be stated, which is why the
  loaders record the lock-in settings.
