# qtipeaks

Batch peak finding over a multi-curve CSV, in the style of QtiPlot's
**Localizar picos** dialog — replaces doing it one curve at a time by hand.

Qt front-end:

```
python tools/qtipeaks_gui.py            # or ... qtipeaks_gui.py file.csv
```

Command line:

```
python tools/qtipeaks.py linescan30.csv --xmin -0.3 --xmax 0.3
```

## The window

Left panel: input CSV picker, output folder picker and file-name prefix, then
the file-format overrides and every parameter grouped the way the QtiPlot
dialog groups them. Right panel:
the selected curve with its fitted background, the background-corrected curve
and the peaks found, redrawn as you change any parameter, with the peak count
in the corner. Pick a curve from the combo to check another one.

Tune against a curve you have already done by hand, then **Run and write CSVs**
processes *every* curve in the file and writes both outputs (plus, optionally,
one PNG per curve into `<prefix>_plots/`). The batch runs off the UI thread, so
a few hundred curves will not freeze the window.

Everything in the GUI is the same code the CLI calls — `qtipeaks_gui.py` is
only widgets.

## Input

One CSV, X in the first column, one curve per remaining column:

| V     | P1        | P2        | … |
|-------|-----------|-----------|---|
| -0.6  | 3.0E-07   | 2.8E-07   | … |
| …     | …         | …         | … |

A header row is optional; without one the curves are named `col1`, `col2`…
Blank cells and non-numeric junk become NaN and are skipped. Rows are sorted by
ascending X, so a descending sweep comes out ascending in the results.

### Delimiters and decimal commas

Both are auto-detected, so a file exported from QtiPlot in a pt-BR locale
(`-0,6;1,339224585931E-07`) loads as is, and so does the same file with periods
and commas. Detection covers:

| delimiter | decimal `.` | decimal `,` |
|---|---|---|
| comma `,` | yes | impossible — a comma cannot be both |
| semicolon `;` | yes | yes |
| tab | yes | yes |
| whitespace | yes | yes |

Delimiters are chosen by which one splits the file into a consistent number of
columns *whose cells actually parse as numbers*, so a stray `;` inside a header
of a comma-delimited file does not derail it. The decimal mark is then a
majority vote over the data cells, so one odd `2,5` in a file of periods cannot
flip the whole file. `1.234,5` (thousands separator) is understood, and a cell
that can only be a decimal comma is read as one even when the rest of the file
uses periods.

**The outputs are written in the same format as the input**, so they reopen in
the same locale and spreadsheet without a text-import dance. Comma-delimited
input with comma decimals is impossible to write, so that combination falls
back to semicolons; whitespace falls back to tabs.

Override any of it when the guess is wrong: `--delimiter` (`comma`,
`semicolon`, `tab`, `whitespace`, or the character itself), `--decimal`,
`--out-delimiter`, `--out-decimal`. In the GUI these are the four combos in
**File format**, all defaulting to auto/same-as-input; changing one re-reads
the file immediately, and the status bar and the grey line under the output
folder tell you what was detected and what will be written.

## Outputs

Written next to the input (or into `-o DIR`):

**`<stem>_peak_matrix.csv`** — the occupancy table. First column is X (the full
input grid), then one column per curve: `1` on the row where that curve has a
peak centre, `0` everywhere else. Widths are ignored, only the centre is
marked. `--transpose` flips it to curves-as-rows / X-as-columns, which is the
layout of the by-hand spreadsheet.

**`<stem>_peak_list.csv`** — one row per peak:
`curve, peak, x_center, y_height, y_corrected, prominence, x_index`, where
`y_height` is on the raw curve and `y_corrected` has the background removed
(they are equal when no background is subtracted).

`--plot DIR` additionally writes one PNG per curve with the peaks marked — the
fastest way to check parameters against what you'd have picked by hand.

## Parameters ↔ QtiPlot dialog

| QtiPlot | flag | default |
|---|---|---|
| A partir de Xmin / Até Xmax | `--xmin` / `--xmax` | full range |
| Direção | `--direction positive\|negative\|both` | `positive` |
| Altura | `--height` (percent) | `5` |
| Suavizar (pontos) | `--smooth` (+ `--smooth-type average\|savgol`) | `0` (off) |
| Suavizar Derivada / Tipo | `--deriv-smooth-type none\|average\|savgol` | `none` |
| Suavizar Derivada / Pontos | `--deriv-smooth-points` | `2` |
| Picos (count) | `--max-peaks` | all |
| *(no equivalent)* | `--baseline none\|poly\|poly-iter` | `none` |

Extras with no QtiPlot equivalent: `--baseline` (below), `--min-distance`
(minimum spacing between peaks, in X units), `--interpolate-center` (parabolic
sub-sample centres in the peak list; the 1/0 table still snaps to the grid),
`--curves` (process only some columns), `--x-scale` (e.g. `1000` to report
volts as meV), `--height-mode`.

`points` is always a **half-width**: `--deriv-smooth-points 2` means a 5-sample
window.

## Polynomial background subtraction

```
--baseline poly-iter --baseline-degree 5
```

The dI/dV band edges are ~4e-7 while the in-gap states are ~1e-8, so a 5%
height threshold over the full sweep sees nothing but the edges. Subtracting a
polynomial background flattens that out and the small features clear the
threshold across the whole sweep at once, instead of needing a hand-picked
narrow window.

- `poly` — plain least-squares fit. The peaks pull the fit upwards, so this
  only suits gentle drift with few peaks.
- `poly-iter` — iterative peak stripping (ModPoly): fit, clip away everything
  sticking out on the peak side, refit, repeat until it converges. The fit
  settles onto the background and ignores the peaks. **Use this one.**

Degree is the usual trade-off: too low and the background is not followed, too
high and the polynomial starts eating the peaks. A polynomial cannot perfectly
track the exponential rise at the band edges, so leftover humps just inside the
edges are normal — either raise the degree, or keep a search range that stops
short of them. The preview draws the fitted background, so this is quick to
judge by eye.

Peak heights are reported both ways: `y_height` on the raw curve,
`y_corrected` after subtraction.

## How peaks are found

1. Restrict to `[xmin, xmax]`.
2. Optionally smooth the data (`--smooth`).
3. Optionally fit and subtract a polynomial background (`--baseline`).
4. Optionally smooth the first derivative (`--deriv-smooth-*`).
5. Take every `+ → −` sign change of `dy/dx` as a candidate.
6. Keep candidates that clear the height threshold.
7. Apply `--min-distance`, then keep the `--max-peaks` most prominent.

The threshold is computed **inside the search window**, on the corrected curve.
So narrowing `--xmin/--xmax` rescales it automatically — over the full sweep 5%
of the band edges buries the in-gap states, but over `-0.3 … 0.3` the same 5%
resolves them. That is why the QtiPlot workflow sets the range first, and why
background subtraction is the alternative to doing so.

`--height-mode` picks what the percentage is measured against:

- `range` (default) — height above the window minimum ≥ height% of the window's
  peak-to-peak span.
- `prominence` — the peak's prominence (drop to the higher neighbouring valley)
  ≥ height% of that span. More robust on a sloping background.
- `max` — the peak's absolute value ≥ height% of the window maximum.

QtiPlot's exact filter is not documented; `range` reproduces its behaviour
closely on the STS curves tested. Compare one curve against QtiPlot with
`--plot` and adjust `--height` / `--height-mode` before running the batch.

## Notes

- The CLI defaults to `--baseline none`, i.e. faithful to QtiPlot. The GUI
  starts with `poly-iter` selected, since that is the point of having it.
- Needs `numpy`; `scipy` only for `savgol` smoothing, `matplotlib` for plots
  and the preview, `PySide6` for the GUI. All are in the `trans` virtualenv,
  so `workon trans` first.
- 200 curves × 2048 points runs in ~5 s.
