# Unit Converter

Three things, all over a whole selection of datasets at once. It replaces the
*Spectral Axis Converter*, whose conversion is the second of them.

**Menu** Tools → Prepare → Unit Converter · **Panel** `UnitConverterTool.qml` ·
**Methods** `relabelDatasets()`, `convertDatasetAxis()` /
`convert_axis_dataset()`, `previewFormula()`, `apply_formula_dataset()`;
formula engine `src/processing/formula.py` · **Batch keys** `axis_convert`,
`unit_formula`

## Input

Any spectral datasets — a multi-dataset selection (Ctrl/Cmd-click,
Shift-click, or a drag from the project browser). The panel shows the first
selection's axis name, units and range, and the formula preview is computed
on it.

## 1. Relabel — data unchanged, in place

Say what the numbers already are. A loader that recorded the wrong unit, or
none, is corrected here rather than by copying the data.

| parameter | meaning |
|---|---|
| `x_unit` | unit of the independent axis (`V`, `mV`, `nm`, `eV`, `cm-1`, …) |
| `x_name` | caption of the axis column (`Bias`, `Wavelength`, …) |
| `y_unit` | unit of the spectra (`A`, `nA`, `S`, `a.u.`, …) |
| `y_name` | what the spectra measure (`dI/dV`, `Current`, `Intensity`) |

Blank fields are left as they are. Every selected dataset is edited **in
place** — no copy, no value changes — and exports, axis labels and the axis
conversion read the new units immediately. This is the only tool in TRANS
that edits an input; it can, because it never touches a number.

## 2. Convert axis — new dataset per input

nm ↔ eV ↔ cm⁻¹ ↔ Raman shift. The source unit is read from each dataset's
metadata (set it with *Relabel* if missing); Raman shift needs the laser
excitation wavelength.

| parameter | default | meaning |
|---|---|---|
| `target_unit` | eV | `nm`, `eV`, `cm-1`, `raman_cm-1` |
| `excitation_nm` | 532 | laser line, Raman only |

Output: `<dataset> (<unit>)`, the axis recomputed and the spectra reordered
so the axis stays increasing. The values themselves are unchanged.

## 3. Set values by formula — previewed first

What qtiplot and Origin call *Set Column Values*, aware of the spectral
layout: one formula for the axis, one for every spectrum, applied across the
whole selection rather than column by column.

| parameter | meaning |
|---|---|
| `x_formula` | new axis, e.g. `x * 1e3` (V → mV); blank keeps it |
| `y_formula` | new spectra, e.g. `y / 1e-9` (A → nA), `y - min(y)`, `log10(abs(y))` |
| `x_unit`, `x_name`, `y_unit`, `y_name` | labels stamped on the result; blank keeps the current ones |
| `replace` | false | overwrite the originals in place instead of creating `<name> · x=…, y=…` |

In a formula `x` is the axis (a column, so it broadcasts against `y`), `y`
is the whole spectra matrix, `i` the sample index. **Both formulas see the
original x and y**, so changing the axis unit does not silently change what
`y / x` means. `^` works as power. Functions: `sqrt log log10 exp abs sign
sin cos tan clip where min max mean median std sum cumsum gradient …` — the
reductions are per spectrum, so `y - min(y)` shifts every spectrum by its
own minimum. Constants: `pi e h hbar c kB q hc_eVnm`.

The preview table shows evenly spaced samples of the axis and the first
spectrum, before and after, plus the new ranges and a count of values that
come out NaN or infinite — so a formula is seen to be right before it runs
over 2000 spectra.

## Method

The formula is parsed to an AST and every node is checked against a
whitelist before it is evaluated with NumPy: arithmetic, comparisons, the
listed functions and names, numeric literals — nothing else. Attribute
access, subscripts, lambdas, strings and any other call are refused with a
message naming the offender. This is what makes a free-text formula safe to
offer.

## Notes

- Relabel and the axis conversion agree by construction: the conversion
  reads the unit Relabel wrote (`units.independent`, `additional_info.axis_unit`).
- A result of *Set values* carries `x_formula` / `y_formula` in its metadata,
  so a dataset says how it was derived.
