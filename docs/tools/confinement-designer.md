# Confinement Designer

The inverse problem: given the levels you measured in **one spectrum**,
search for a geometry whose eigenstates match, and rank every candidate for
inspection. To run the same search at every position of a line scan and see
how the size varies along it, use the [Line Scan
Designer](line-scan-designer.md).

**Menu** Tools → Confinement → Confinement Designer · **Panel**
`ConfinementDesignerTool.qml` · **Method** `design_confinement()`,
engine in `src/physics/designer.py` · **Batch key** `confinement_designer`

## Input

A multi-dataset selection — every dataset is searched in turn with the
same settings and writes its own tables (named after the dataset and the
search settings); the preview and the candidate list are the first
selection's. Per dataset, either a spectrum — whose peaks are found by the same engine as
[Confinement Analysis](confinement-analysis.md), previewed live by
`previewDesignerTargets` — or target energies typed by hand.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `ndim` | — | 1, 2 or 3 (`0D` for a dot) |
| `coords` | — | cartesian, polar, cylindrical, spherical, disc, disk, parabolic |
| `sym` | — | symmetry constraint on the box |
| `dims` | — | which dimensions are free to vary |
| `size` (`Lmin`, `Lmax`) | 1–20 nm | the range shared by every dimension that has no range of its own |
| `meff`, `meff_e`, `meff_h` | — | effective mass; separate electron and hole masses when paired. A comma-separated list is several searches |
| `carrier` | electrons | electron, hole, or both |
| `paired` | — | fit electron and hole ladders together |
| `split_e` / `split_h` | 0 | branch split for each carrier |
| `pair_tol_nm` | 1.0 | how closely the two carriers' sizes must agree |
| `match` | `delta_e` | matching criterion |
| `tol` | 5 % | tolerance on a match |
| `rrmse` | — | relative RMS error accepted |
| `maxsol` | 6 | how many candidates to return — a **display quota**, ignored by `search_mode = enumerate` |
| `priority`, `sort` | uniform, rrmse | how targets are weighted and candidates ranked |
| `baseline`, `height` | as Confinement Analysis | the peak search feeding the targets |
| `spectrum_index` | 0 | which spectrum to read targets from |
| `all_spectra` | false | search every spectrum in the dataset in turn instead of just that one |
| `seed` | none | pins the sampled search's RNG so a run can be reproduced |

### Which geometry the search may reach

One slider pair for every dimension is only right when the dimensions are
equally determined. On a lens matched by level **spacings** they are not: the
energy origin cancels in a difference and the axial ladder goes with it, so
`R` is pinned to about a hundred picometres by the data and `L_z` is not
measured at all. Sharing one range lets `L_z` run to whatever ceiling was
picked for `R`, and `R` collapses to compensate — which is exactly what "it
converges at 13 nm but diverges at 18" is.

| parameter | default | meaning |
|---|---|---|
| `fixed` | none | `{'d2': 5.0}` pins a dimension **out** of the search. The highest-value knob on a lens under ΔE: pinned, the search returns one candidate, the same one at `Lmax` 13 and 18 and whatever the seed |
| `box` | none | `{'d1': (lo, hi), …}`, a range per dimension. An absent entry, or a `None` at either end, falls back to `Lmin`/`Lmax`. Ends the wrong way round are **refused**, not quietly widened to the shared range |
| `assign` | `energy` | which model level each measured one is compared to: `energy` (nearest, always the behaviour), `sequential`, `low_qn`, `mixed`. Orthogonal to `priority`, which decides how much each target counts once that is settled |

A `box` entry that reaches outside `Lmin`/`Lmax` widens the shared pair the
analytical-seed gate reads, so a boxed dimension does not silently cost the
run its starting points; the dimensions that were **not** boxed keep the
shared range as it stood.

### How the search is run

| parameter | default | meaning |
|---|---|---|
| `search_mode` | `sample` | `sample` is random restarts, a few good geometries, capped at `maxsol`. `enumerate` is the deterministic lattice pass: no RNG, and the full population instead of a podium |
| `enum_per_octave` | 8 | lattice nodes per octave of size. E goes as 1/L², so equal *ratios* of L are equal steps in the quantity being fitted |
| `enum_polish` | 40 | how many of the ranked nodes are refined, as a **density**: this many per 1–18 nm box per free dimension, scaled by how many such boxes the range actually is, capped at ten times the number given, and overridden by an exhaustive pass on a lattice of ≤ 32 nodes. A node is far too coarse to *be* an answer — the acceptable intervals along R are 26–108 pm wide and the nodes are ~1 nm apart |
| `enum_max_nodes` | 200 000 | the lattice size the enumeration refuses at rather than running for a quarter of an hour. The panel prints the lattice size beside it and compares against whatever cap is set |
| `dup_rel` | none | how close two geometries must be to count as one candidate, **relative** to size. Absolute (0.1 nm per dimension) when unset — which on this disc is both too coarse (the sub-tolerance intervals along R are 26–108 pm) and the wrong unit for a parabolic dot, whose dimensions are energies in meV. The panel asks for it as a percentage and it applies to both search modes |

**Widening the range adds candidates and moves none of the ones already
found.** Three things make that true, and it was false until all three were:

* the **lattice** is anchored at `Lmin`, truncated only at the top, and each
  node computed from its index — so the lattice at 13 nm is a strict subset of
  the one at 18, node for node and bit for bit;
* the **budget** (`Designer.polish_budget`) is a density over the box in
  octaves, so the refined *fraction* does not depend on the ceiling: 32 / 40 /
  50 refinements at `Lmax` 13 / 18 / 25 nm, and the node set selected at each
  ceiling is a strict subset of the next;
* each **refinement** (`Designer.refinement_box`) is confined to one lattice
  step around its own node, so the same node lands on the same point whatever
  the ceiling. Given the whole box instead, L-BFGS-B's trajectory on a valley
  that is flat along `L_z` depends on the bounds it was handed.

Before those: an absolute top-40 over a growing lattice gave 900 nodes / 17
candidates at 13 nm, 1156 / 19 at 18 and 1444 / 16 at 25 — `R = 6.4681 nm`
existed at 13 and was gone at 18, and widening 18 → 25 *reduced* the count.
After them it is 21 → 23 → 24, every earlier geometry reproduced exactly.

It lapses honestly in three places. The panel's explainer names all three, and
the line under it says which rule the lattice you have actually selected is
being refined by:

* past **ten times** the `enum_polish` you typed the budget stops scaling and
  the selection is an absolute top-N again;
* a node within **one lattice step of the top** of the range has its cell
  clipped by the ceiling, which is the range genuinely ending rather than an
  artefact;
* a lattice of **32 nodes or fewer** (`Designer.POLISH_ALL_BELOW`) is refined
  in full, because a tightly boxed search has few basins and the density alone
  would send it to a single descent. Widening such a box past 32 nodes hands
  the selection back to the density, which can refine *fewer* nodes than the
  small box did: 27 of 27 over 2–8 nm × 4–6 nm at 4 per octave, 4 of 33 once
  `R` reaches 13 nm.

The panel prints the lattice size and the budget beside the control, and
mirrors `Designer.polish_budget` value for value — a test compares the two,
because that mirror drifted once and printed "refining 8 of 27" where the
engine refines all 27.

### What the data could have seen

| parameter | default | meaning |
|---|---|---|
| `temperature_K` | 94 | the measurement temperature, and so the resolution window: 3.5·k_B·T — 27 meV at 90 K, 28.6 at 94, 91 at 300. 0 means "not known", which hands the window back to the data-derived lower bound. The default is the temperature *these* spectra were taken at — the by-hand sheet they were checked against reads "T = 94 K, k_B T = 8 meV", the same number the dI/dV resolution code takes its 28.6 mV thermal kernel from — and it is never applied silently: `resolution_basis` on every row says which temperature the window came from |
| `resolution_meV` | none | an explicit window. Wins over the temperature: a measured resolution beats a derived one |

The window never enters the score. It is the yardstick `n_tied` is counted in
and `unresolvable` is decided against, and those are the two columns that say
whether a lower RRMSE means anything at all.

It is derived from a temperature because the alternative fires on nothing.
With neither a temperature nor an explicit number the engine falls back to
half the smallest gap the spectrum itself resolved — a **lower bound** on the
resolution rather than the resolution. On the 4 × 5 nm lens's six targets that
is 6.07 meV, four times finer than the measurement, and at that window every
runaway geometry reports `unresolvable = False`: (3.75, 5.0) nm with its
levels 26.3 meV apart, (3.2, 10.0) at 21.5 meV, (2.9, 14.5) at 16.9 meV,
(2.1, 18.0) at 25.8 meV. At 3.5·k_B·T (94 K) all four are `True`, with
`n_tied` 4, 4, 5 and 4.

Whichever basis was used is never silent: the panel prints it live under the
control, the run logs it, the status line repeats it beside the candidate
list, and every candidate row carries it in `resolution_basis`.

`n_tied` is counted inside a **finite** ladder — the model is solved to
`max(3 × n_levels, 20)` states — so it reads "at least this many", and its
ceiling rises when more peaks are fed in.

### The consensus

| parameter | default | meaning |
|---|---|---|
| `admissible_abs_pct` | 0.05 | a candidate votes when its ΔE error is within this many percentage points of its spectrum's best… |
| `admissible_rel` | 0.1 | …or within this fraction of it, whichever is larger |
| `min_support_frac` | 0.15 | a mode backed by fewer than this fraction of the searched spectra is not reported |
| `group_tol_nm` | 0 (auto) | pins the KDE bandwidth at `ln(1 + tol / median R)`; 0 lets it follow the data |

## Output

A ranked list of candidate geometries with their predicted level ladders and
the error against your targets. `describeCandidate()` renders one in full, and
a candidate can be handed straight to the [Quantum Well](quantum-well-solver.md)
or [Quantum Dot](quantum-dot-solver.md) solver via `SolutionSpec`.

Every run writes **four** tables — datasets in the project and CSVs under
`<project>_outputs/confinement/` — because a list that only exists on screen
cannot be read after the window closes. All four carry `dataset` and `search`
as their last two columns, and all have a fixed column order, so two runs
concatenate.

| table | contents |
|---|---|
| `<dataset> - Designer Candidates` | **one row per candidate** — see below |
| `<dataset> - Designer Levels` | **one row per level of each candidate**: `measured_eV` against `simulated_eV` with `error_pct`, plus `measured_V`/`simulated_V` (the same two energies put back on the bias axis) and `degeneracy`, how many states that one row stands for. NaN, never 1, when the level table could not be built |
| `<dataset> - Designer Modes` | **one row per well the run's consensus believes in**: `R_nm` and the range of radii (`R_lo_nm`…`R_max_nm`) and of `L_z` (`Lz_lo_nm`, `Lz_hi_nm`) its supporters spanned, how many spectra voted (`support_spectra`, `support_frac`), and how good their fits were. L_z is a **range and never a value**: with the offset cancelled the vertical size is not determined by the data, and a single number there would be the optimiser's seed dressed as a measurement |
| `<dataset> - Designer Consensus` | **one row per spectrum**, and the only one of the four that maps — every column is a number that can be laid out along the line. `R_consensus_nm`, which `mode` the position belongs to, `mode_prob` and `mode_entropy` (nats; 0 where one mode owns the position), and how wide its own admissible band was |

### The candidate table

The geometry first: `d1_nm`/`d2_nm`/`d3_nm`, `size_nm`, `meff`, `offset_eV`,
`rrmse_pct`, `rrmse_de_pct`, the geometry (`ndim`, `coords`, `sym`), the
branch edges it was fitted under, and the paired hole (`hole_size_nm`,
`pair_mismatch_nm`, `hole_qn_*`) where there is one. On a paired run a row
**is** an electron–hole pair and `carrier` reads `e+h`.

`qn_min` / `qn_max` are the quantum numbers the measured levels were assigned
to and `levels_skipped` how many predicted levels between them were *not*
measured — five peaks matched to n = 8, 15, 17, 18, 20 skip eight levels the
model says should be there, a weak match however low its RRMSE (the matcher
pairs each measured level with the nearest predicted one and does not require
consecutive levels).

Then what the fit could and could not see. A column that says a dimension is
unconstrained is worth more than a third decimal place on it:

| column | meaning |
|---|---|
| `flat_dims` | the dimensions the objective is literally insensitive to — moved by ±2 % the error does not change, so the number printed for them is one arbitrary point of a plateau. Named in the geometry's own terms (`L_z`, not `d2`), `+`-joined, empty when the fit saw every dimension |
| `n_tied` | how many model levels lie within one resolution window of a matched one: the count of assignments this measurement cannot rule out, 1 on a resolved ladder. Bounded by the `max(3 × n_levels, 20)`-state basis |
| `resolution_meV` | the window `n_tied` was counted in |
| `resolution_basis` | where that window came from: `3.5 k_B T at 94 K`, `27 meV as given`, or `half the smallest measured gap (a lower bound)` |
| `unresolvable` | 1 when the model's mean level spacing across the fitted window is below that window — the state in which the error has stopped discriminating between geometries and a lower RRMSE means nothing at all |
| `g_sum`, `g_max` | the degeneracies behind the matched levels: their sum, and the largest single one. A peak assigned to a doublet and a peak assigned to a singlet used to be reported identically |
| `n_distinct`, `qn_sum` | `n_distinct` below `n_levels` means two measured levels were assigned to the **same** model level, which nearest-in-energy matching allows. `qn_sum` is how high up the ladder the assignment sits |

And where the row landed in the run's consensus:

| column | meaning |
|---|---|
| `group` | the mode index — the well the run decided this row belongs to; −1 when the row carries no vote (a placeholder, or a candidate too far behind its own spectrum's best to be admissible) |
| `group_R_nm` | **the number to trust**: the mode's consensus R |
| `group_size_nm` | the mean `size_nm` inside the mode, kept so plots built on the old gap clustering still read. It is the mode's R, not its size, that the consensus actually decided |
| `admissible` | 1 inside the spectrum's admissible band, 0 searched and rejected, NaN on a placeholder |
| `band_de_pct`, `weight`, `dist_nm` | how wide that band was, the row's vote, and how far it sits from its mode |

On an all-spectra sweep every spectrum that found nothing gets a placeholder
row (`candidate = -1`, its `n_peaks`, the `reason`), so the table says which
positions converged and which did not. Every spectrum is searched **on its
own** — its own peaks, its own search, its own candidates; nothing is fitted
across spectra, and the consensus is the only step that looks at the run as a
whole.

Both the candidate and the level table carry `spectrum_index` and `column`, so
a sweep's rows say which spectrum they came from.

### Measured against simulated, and the branch edges

The energies fitted are measured **from the branch edge**, not from E_F:
`split_e` cuts the electron branch and `split_h` the hole branch, so a peak at
bias *V* becomes `V - split_e` for an electron and `split_h - V` for a hole.
The level table gives both readings — `measured_eV` is what was fitted,
`measured_V = measured_eV + split_e` (electrons) or `split_h - measured_eV`
(holes) is where to find it again on the curve — and repeats `split_e_V` /
`split_h_V` on every row, so the table means the same thing on its own as it
does next to the panel that produced it.

### Searching every spectrum

`all_spectra` turns the tool from one question into a sweep: each spectrum is
searched in turn, the tables collect every candidate from all of them, and the
panel's list shows one spectrum's — the one selected, or the first that found
anything when the selected one found nothing. A spectrum with too few peaks on
a branch is an ordinary outcome and does not end the run, and neither does a
search the settings make impossible (a lattice over `enum_max_nodes`): it
becomes that spectrum's `reason` rather than aborting the sweep on spectrum 1.
Cancel stops it between spectra.

## Budget the time

Measured on an M1 Pro — 0D disc under ΔE, six targets, two free dimensions,
1–18 nm, one mass:

| search | per spectrum per mass | 300 spectra, one mass, one carrier |
|---|---|---|
| `sample` (default) | **25.9 s** | ~129 min |
| `enumerate` | **10.6 s** | ~53 min |

The sampled figure is seed-dependent — `find_solutions` stops once `maxsol`
candidates are in — so it varies: 13.1, 13.4, 16.2, 19.6 and 25.1 s over five
seeds on this disc. The panel estimates from the upper end, because an
estimate that is too low is worse than one that is too high. The enumerated
figure re-measured at 9.6 s on an idle machine once refinements were confined
to one lattice cell each.

The enumerated figure is **one lattice's**, not the mode's. The cost follows
the node count, and `enum_per_octave` moves that by two orders of magnitude on
its own — measured over the same 1–18 nm box:

| nodes per octave | lattice | seconds |
|---|---|---|
| 8 (default) | 1 156 | 9.9 |
| 16 | 4 489 | 16.8 |
| 24 | 10 201 | 20.2 |
| 32 | 17 956 | 24.3 |
| 64 (the control's maximum) | 71 289 | ~70 (extrapolated) |
| — | 200 000 (the cap) | ~150 (the ~2.5 min/spectrum measured for the cap) |

So the panel does not quote a single enumerated rate: it estimates
`max(10.6, 13.4 s + 0.79 ms × nodes)`, the line that stays above all four
measurements, and prints the lattice size it used. At the default lattice that
reads ~14 s against a real 10, and at the cap ~2.9 min against a real ~2.5 —
high on purpose. A flat 10.6 s understated the top of the nodes-per-octave
control by 2.4×, which is the same factor "seconds each" understated the
sweep by.

`dup_rel` and `enum_max_nodes` have controls of their own — *Merge candidates
within (% of size)* and *Refuse a lattice over (nodes)* — because the search
read both and nothing set either, so a lattice the settings made too big was a
refusal with no control to answer it, and a plateau sampled thirteen times
along an unmeasurable axis stayed thirteen rows. Both are relative to the
engine's own defaults: 0 on the first is the absolute 0.1 nm test every
existing candidate list was deduplicated with, 0 on the second the 200 000-node
cap. `reject_unresolvable` and `seed_aspect` deliberately have neither: rejecting the
unresolvable would delete the very population the `unresolvable` column exists
to show (at a thermal window most of this disc's candidates are unresolved,
the correct 4 nm well included), and `seed_aspect` says in ratios what `box`
already says in nanometres.

It multiplies: every effective mass in the list is its own search, and so is
every carrier, and so is every selected dataset. The panel shows the estimate
live beside the run button and asks before committing to anything over ten
minutes. Cancel stops the sweep **between** spectra, so the shortest way out
of a running sweep is one spectrum long.

(Earlier revisions of this page and of the engine's docstrings quoted
"seconds each", "~0.25 s per candidate" and "about 4.4 s … against 10.5 s for
the default search". All three were low — the first two by orders of
magnitude.)

`enum_per_octave` reaches the 200 000-node cap at its own maximum with two
free dimensions (~2.5 min/spectrum before the cap, and a refusal past it), so
the panel prints the lattice size beside the control and scales its estimate
with it.

## Method

The search sweeps geometry and size, solves each candidate analytically where
a closed form exists (`src/physics/analytical.py`) and numerically otherwise,
and scores the predicted ladder against the targets.

**Paired** mode fits an electron and a hole ladder at once and requires the
two to agree on a size within `pair_tol_nm` — a much stronger constraint than
either alone, because a wrong geometry rarely fits both carriers at the same
size.

Reproduces the reference Tk implementation's candidates to 1e-8 nm.

## Notes

- Targets are only as good as the peak search that produced them. Preview the
  spectrum and check the peaks before trusting a candidate.
- A candidate is a **hypothesis**, not a measurement: several geometries can
  fit the same few levels. More levels discriminate far better than tighter
  tolerances.
- Under ΔE matching on a lens, `L_z` is unmeasurable **by construction** — the
  energy offset cancels and the axial ladder goes with it. Read `flat_dims`
  before reading the third decimal of a dimension, pin `L_z` rather than
  searching it, and take `group_R_nm` as the run's answer.
