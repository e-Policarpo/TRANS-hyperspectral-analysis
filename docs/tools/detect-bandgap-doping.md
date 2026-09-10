# Detect Bandgap & Doping

Per spectrum: how wide the gap is, and whether the material is N-type,
P-type or neutral.

**Menu** Tools → Composite tools → Detect Bandgap & Doping · **Panel**
`DetectBandgapDopingTool.qml` · **Method** `detect_bandgap_doping()`,
`detect_bandgap()` / `classify_doping()` in `src/backend/sts_algorithms.py`

## Input

dI/dV spectra from a semiconductor — a curve with a recognisable gap.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `smoothing` | 1.0 | smoothing strength, as a percentage |
| `smoothing_method` | `Savgol` | `Savgol`, `Moving Avg` or `None` |
| `delta` | 5.0 | threshold defining the gap edge, as a percentage |
| `resolution` | 0.01 V | how far from zero the gap centre may sit and still count as neutral |

## Output

| output | contents |
|---|---|
| bandgap table | per spectrum: gap width, both edges, and whether the result is valid |
| doping table | per spectrum: type, offset from zero bias, valid flag |
| files | `<project>_outputs/curves/` |

Both are emitted as separate datasets, so the workflow node has two outputs.

## Method

Smooth, then walk out from the conductance minimum until the signal exceeds
`delta` percent of the curve's range — those crossings are the band edges and
their separation is the gap.

Doping is the **position of the gap centre relative to zero bias**: the Fermi
level sits at 0 V by construction, so a gap centred above it means the Fermi
level is nearer the valence band (P-type) and vice versa. Within
`resolution` of zero, the material is called neutral.

Every row carries a **valid** flag. `validate_ldos` rejects curves that cannot
answer the question — too few points, negligible variation, no identifiable
minimum — instead of returning a number that looks like a measurement.

## Notes

- `delta` is the parameter that matters. Too small and noise defines the edge;
  too large and the gap is systematically underestimated.
- A metallic spectrum has no gap. The valid flag is how that is reported —
  check it before averaging a column of gap widths.
