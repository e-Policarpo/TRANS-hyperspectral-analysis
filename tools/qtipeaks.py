#!/usr/bin/env python3
"""qtipeaks -- QtiPlot-style batch peak finding over a multi-curve CSV.

Input
-----
One CSV with the X values in the first column and one column per curve
(dI/dV, PL, whatever) in the remaining columns.  Delimiter (``,`` ``;`` tab)
and decimal separator (``.`` or ``,``) are auto-detected, so files exported
from QtiPlot in a pt_BR locale load without pre-editing.

Outputs
-------
1. ``<stem>_peak_matrix.csv``  -- the occupancy table: first column X (the
   full input grid), then one column per curve holding 1 on the rows where
   that curve has a peak centre and 0 everywhere else.
2. ``<stem>_peak_list.csv``    -- the flat list of every peak found
   (curve, peak number, centre, height, row index).

Optionally ``--plot DIR`` writes one PNG per curve with the detected peaks
marked, which is the quickest way to sanity-check parameters against what
QtiPlot gives you by hand.

Algorithm
---------
Mirrors the QtiPlot "Localizar picos" dialog:

    Dados   -> --xmin / --xmax          (search range, default: full range)
    Filtro  -> --direction              positive | negative | both
               --height                 threshold in %          (default 5)
               --smooth                 smoothing of the data   (default 0)
    Suavizar Derivada
            -> --deriv-smooth-type      none | average | savgol (default none)
               --deriv-smooth-points    (default 2)
    Picos   -> --max-peaks              keep only the N tallest (default: all)

Beyond QtiPlot, ``--baseline poly-iter --baseline-degree 3`` removes a
polynomial background first, so the small in-gap features are measured against
a flat zero instead of against the band edges.

Peaks are located as sign changes (+ -> -) of the first derivative of the
(optionally smoothed, optionally background-corrected) curve, then filtered by
the height threshold.

There is a Qt front-end for all of this: ``python qtipeaks_gui.py``.

`points` is always a HALF-WIDTH: a smoother with ``points = 2`` spans
2*2+1 = 5 samples.

Examples
--------
    python qtipeaks.py linescan30.csv
    python qtipeaks.py linescan30.csv --xmin -0.3 --xmax 0.3 --height 5
    python qtipeaks.py linescan30.csv --x-scale 1000 --transpose --plot checks/
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
from dataclasses import dataclass

import numpy as np

try:
    from scipy.signal import savgol_filter
except ImportError:  # pragma: no cover - scipy is optional
    savgol_filter = None


# --------------------------------------------------------------------------
# CSV input
# --------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eEdD][+-]?\d+)?$")


@dataclass
class Table:
    """A parsed CSV: X vector, curve names and one y vector per curve."""

    x: np.ndarray
    names: list[str]
    ys: list[np.ndarray]
    delimiter: str
    decimal: str


# Sentinel for "any run of whitespace", which csv.reader cannot express.
WHITESPACE = " "

DELIMITER_NAMES = {
    ",": "comma ,",
    ";": "semicolon ;",
    "\t": "tab",
    WHITESPACE: "whitespace",
}

DELIMITER_CANDIDATES = (";", "\t", ",", WHITESPACE)

_DECIMAL_COMMA_RE = re.compile(r"\d,\d")
_DECIMAL_DOT_RE = re.compile(r"\d\.\d")


def split_rows(lines, delimiter: str) -> list[list[str]]:
    if delimiter == WHITESPACE:
        return [re.split(r"\s+", ln.strip()) for ln in lines if ln.strip()]
    return [r for r in csv.reader(lines, delimiter=delimiter) if any(c.strip() for c in r)]


def _score_format(lines: list[str], delimiter: str, decimal: str) -> float:
    """How well does this (delimiter, decimal) pair explain the text?

    Rewards a consistent column count and, decisively, cells that actually
    parse as numbers -- which is what separates ``1,23;4,56`` (semicolon +
    decimal comma) from the same text read with a comma delimiter.
    """
    rows = split_rows(lines, delimiter)
    if not rows:
        return -1.0

    widths: dict[int, int] = {}
    for row in rows:
        widths[len(row)] = widths.get(len(row), 0) + 1
    width, hits = max(widths.items(), key=lambda kv: (kv[1], kv[0]))
    if width < 2:
        return -1.0

    body = [r for r in rows if len(r) == width]
    if len(body) > 1:
        body = body[1:]  # the first row is usually a header

    cells = [c for row in body for c in row]
    if not cells:
        return -1.0
    parsed = sum(1 for c in cells if not math.isnan(_to_float(c, decimal, lenient=False)))

    consistency = hits / len(rows)
    numeric = parsed / len(cells)
    # numeric is squared so a pair that merely splits evenly cannot beat one
    # that also yields numbers; the width term breaks ties toward more columns.
    return consistency * (numeric ** 2) * (1.0 + 0.001 * width)


def _vote_decimal(rows: list[list[str]]) -> str:
    """Majority vote over the cells: is the decimal mark a comma or a period?

    A vote rather than a score, so one stray ``2,5`` in a file of periods
    cannot flip the whole file -- and with it the format of the output.
    """
    body = rows[1:] if len(rows) > 1 else rows
    commas = dots = 0
    for row in body:
        for cell in row:
            if _DECIMAL_COMMA_RE.search(cell):
                commas += 1
            if _DECIMAL_DOT_RE.search(cell):
                dots += 1
    return "," if commas > dots else "."


def sniff_format(sample: str) -> tuple[str, str]:
    """Guess (delimiter, decimal separator) from raw text."""
    lines = [ln for ln in sample.splitlines() if ln.strip()][:200]
    if not lines:
        return ",", "."

    best, best_score = ",", -1.0
    for delimiter in DELIMITER_CANDIDATES:
        # A comma delimiter with a comma decimal mark is undecodable, so that
        # reading is never even considered.
        decimals = (".",) if delimiter == "," else (".", ",")
        score = max(_score_format(lines, delimiter, decimal) for decimal in decimals)
        if score > best_score:
            best, best_score = delimiter, score

    return best, _vote_decimal(split_rows(lines, best))


def _to_float(token: str, decimal: str, lenient: bool = True) -> float:
    token = token.strip().strip('"').strip()
    if not token:
        return math.nan

    if decimal == ",":
        if "." in token and "," in token:
            token = token.replace(".", "")  # thousands separator
        token = token.replace(",", ".")
    elif lenient and "," in token and "." not in token:
        # Detection said period, but this cell can only be a decimal comma
        # (the comma is not the delimiter or the field would have split).
        token = token.replace(",", ".")

    token = token.replace("D", "E").replace("d", "e")
    try:
        return float(token)
    except ValueError:
        return math.nan


def effective_output_format(delimiter: str, decimal: str) -> tuple[str, str]:
    """Resolve a writable (delimiter, decimal) pair.

    Whitespace is not a delimiter you can write unambiguously, and a comma
    cannot be both the delimiter and the decimal mark; both fall back to tab
    and semicolon respectively so the file still reopens correctly.
    """
    if delimiter == WHITESPACE:
        delimiter = "\t"
    if delimiter == "," and decimal == ",":
        delimiter = ";"
    return delimiter, decimal


def _is_number(token: str) -> bool:
    return bool(_NUMBER_RE.match(token.strip().strip('"').strip().replace("D", "E").replace("d", "e")))


def read_table(path: str, delimiter: str | None, decimal: str | None) -> Table:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        text = fh.read()

    sniffed_delim, sniffed_dec = sniff_format(text[:65536])
    delimiter = delimiter or sniffed_delim
    decimal = decimal or sniffed_dec

    rows = split_rows(text.splitlines(), delimiter)
    if not rows:
        raise SystemExit(f"{path}: no data rows found")

    header = rows[0]
    has_header = not all(_is_number(c) for c in header if c.strip())
    if has_header:
        names = [c.strip().strip('"') or f"col{i}" for i, c in enumerate(header)]
        body = rows[1:]
    else:
        names = [f"col{i}" for i in range(len(header))]
        body = rows

    if not body:
        raise SystemExit(f"{path}: header found but no data rows")

    width = max(len(r) for r in body)
    if width < 2:
        raise SystemExit(
            f"{path}: splitting on {DELIMITER_NAMES.get(delimiter, repr(delimiter))} gives a single "
            f"column -- the file most likely uses a different delimiter")
    if len(names) < width:
        names += [f"col{i}" for i in range(len(names), width)]

    data = np.full((len(body), width), np.nan)
    for i, row in enumerate(body):
        for j, tok in enumerate(row[:width]):
            data[i, j] = _to_float(tok, decimal)

    x = data[:, 0]
    if np.all(np.isnan(x)):
        raise SystemExit(f"{path}: first column holds no numbers -- is it really the X column?")

    keep = ~np.isnan(x)
    data, x = data[keep], x[keep]

    order = np.argsort(x, kind="stable")
    if not np.all(order == np.arange(len(x))):
        data, x = data[order], x[order]

    ys = [data[:, j] for j in range(1, width)]
    return Table(x=x, names=names[1:width], ys=ys, delimiter=delimiter, decimal=decimal)


# --------------------------------------------------------------------------
# Smoothing
# --------------------------------------------------------------------------

def _moving_average(y: np.ndarray, half: int) -> np.ndarray:
    window = 2 * half + 1
    if window < 3 or window > len(y):
        return y
    padded = np.pad(y, half, mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


def _savgol(y: np.ndarray, half: int, polyorder: int = 2) -> np.ndarray:
    window = 2 * half + 1
    if window < 3 or window > len(y):
        return y
    if savgol_filter is None:
        print("warning: scipy unavailable, falling back to moving average", file=sys.stderr)
        return _moving_average(y, half)
    return savgol_filter(y, window_length=window, polyorder=min(polyorder, window - 1))


def smooth(y: np.ndarray, kind: str, half: int) -> np.ndarray:
    if half < 1 or kind == "none":
        return y
    if kind == "average":
        return _moving_average(y, half)
    if kind == "savgol":
        return _savgol(y, half)
    raise ValueError(f"unknown smoother {kind!r}")


# --------------------------------------------------------------------------
# Polynomial background
# --------------------------------------------------------------------------

BASELINE_KINDS = ("none", "poly", "poly-iter")


def polynomial_baseline(
    x: np.ndarray,
    y: np.ndarray,
    kind: str,
    degree: int,
    iterations: int = 25,
    direction: str = "positive",
    tol: float = 1e-4,
) -> np.ndarray:
    """Background curve to subtract before peak finding.

    ``poly``      plain least-squares polynomial through all the points; the
                  peaks themselves pull the fit up, so it only suits gentle
                  drift with few peaks.
    ``poly-iter`` iterative peak stripping (ModPoly, Lieber &
                  Mahadevan-Jansen): fit, clip away everything that sticks out
                  on the peak side, refit, repeat.  The fit converges onto the
                  background and ignores the peaks, which is what makes small
                  in-gap features survive a percentage height threshold that
                  the band edges would otherwise dominate.
    """
    if kind == "none" or degree < 0 or len(y) <= degree + 1:
        return np.zeros_like(y)

    # Condition the Vandermonde matrix: x is often ~1e-1 with y ~1e-7.
    span = float(np.max(x) - np.min(x))
    t = (x - float(np.mean(x))) / (span / 2.0) if span > 0 else x - float(np.mean(x))

    scale = float(np.max(np.abs(y)))
    if scale == 0 or not math.isfinite(scale):
        return np.zeros_like(y)
    ys = y / scale

    with np.errstate(all="ignore"):
        fit = np.polyval(np.polyfit(t, ys, degree), t)
        if kind == "poly":
            return fit * scale

        # poly-iter: clip on the side the peaks stick out of. The comparison
        # is against the ORIGINAL spectrum each pass, per Lieber &
        # Mahadevan-Jansen -- clipping against the running result lets the
        # baseline drift off the background as iterations increase.
        clip = np.minimum if direction != "negative" else np.maximum
        for _ in range(max(1, iterations)):
            z = clip(ys, fit)
            new_fit = np.polyval(np.polyfit(t, z, degree), t)
            delta = float(np.max(np.abs(new_fit - fit)))
            fit = new_fit
            if delta <= tol * max(1e-12, float(np.max(np.abs(fit)))):
                break

    return fit * scale


# --------------------------------------------------------------------------
# Peak finding
# --------------------------------------------------------------------------

@dataclass
class Peak:
    index: int          # row index into the FULL input grid
    x: float            # centre (grid x, or interpolated if --interpolate-center)
    y: float            # height at the centre, on the raw curve
    y_corrected: float  # height at the centre, background removed
    prominence: float


@dataclass
class Params:
    xmin: float | None = None
    xmax: float | None = None
    direction: str = "positive"
    height: float = 5.0
    height_mode: str = "range"
    smooth_type: str = "average"
    smooth_points: int = 0
    deriv_smooth_type: str = "none"
    deriv_smooth_points: int = 2
    baseline: str = "none"
    baseline_degree: int = 3
    baseline_iterations: int = 25
    max_peaks: int | None = None
    min_distance: float = 0.0
    interpolate_center: bool = False


@dataclass
class Analysis:
    """Everything the search computed, so previews and plots can show it."""

    idx: np.ndarray          # indices into the full grid, in-window
    x: np.ndarray            # in-window x
    y_raw: np.ndarray        # in-window y, untouched
    y_smooth: np.ndarray     # after --smooth
    baseline: np.ndarray     # fitted background (zeros when disabled)
    y_corrected: np.ndarray  # y_smooth - baseline, what peaks are found on
    peaks: list[Peak]


def _local_maxima(y: np.ndarray, x: np.ndarray) -> list[int]:
    """Indices of local maxima, found as + -> - sign changes of dy/dx."""
    if len(y) < 3:
        return []
    d = np.gradient(y, x)
    out: list[int] = []
    for i in range(len(d) - 1):
        a, b = d[i], d[i + 1]
        if a > 0 and b <= 0:
            out.append(i if y[i] >= y[i + 1] else i + 1)
        elif a == 0 and b < 0:
            out.append(i)
    # A flat top can register twice; keep the taller of adjacent duplicates.
    deduped: list[int] = []
    for i in out:
        if deduped and i - deduped[-1] <= 1:
            if y[i] > y[deduped[-1]]:
                deduped[-1] = i
        else:
            deduped.append(i)
    return deduped


def _prominence(y: np.ndarray, i: int) -> float:
    """Drop from the peak to the higher of the two neighbouring valleys."""
    peak = y[i]

    j = i
    left_min = peak
    while j > 0:
        j -= 1
        if y[j] > peak:
            break
        left_min = min(left_min, y[j])

    j = i
    right_min = peak
    while j < len(y) - 1:
        j += 1
        if y[j] > peak:
            break
        right_min = min(right_min, y[j])

    return peak - max(left_min, right_min)


def _parabolic_center(x: np.ndarray, y: np.ndarray, i: int) -> float:
    if i <= 0 or i >= len(y) - 1:
        return float(x[i])
    y0, y1, y2 = y[i - 1], y[i], y[i + 1]
    denom = y0 - 2 * y1 + y2
    if denom == 0:
        return float(x[i])
    delta = 0.5 * (y0 - y2) / denom
    if not -1 < delta < 1:
        return float(x[i])
    step = (x[i + 1] - x[i - 1]) / 2.0
    return float(x[i] + delta * step)


def analyze(x: np.ndarray, y: np.ndarray, p: Params) -> Analysis:
    """QtiPlot-style peak search, keeping the intermediates for display."""
    finite = np.isfinite(x) & np.isfinite(y)
    window = finite.copy()
    if p.xmin is not None:
        window &= x >= p.xmin
    if p.xmax is not None:
        window &= x <= p.xmax
    idx = np.flatnonzero(window)
    if len(idx) < 3:
        empty = np.empty(0)
        return Analysis(idx, x[idx], y[idx], y[idx], empty[:0], y[idx], [])

    xw, yw_raw = x[idx], y[idx]
    yw = smooth(yw_raw, p.smooth_type, p.smooth_points)

    baseline = polynomial_baseline(
        xw, yw, p.baseline, p.baseline_degree, p.baseline_iterations, p.direction
    )
    corrected = yw - baseline

    directions = {"positive": [1], "negative": [-1], "both": [1, -1]}[p.direction]

    span = float(np.max(corrected) - np.min(corrected))
    threshold = (p.height / 100.0) * span

    found: dict[int, Peak] = {}
    for sign in directions:
        ys = corrected * sign
        yd = smooth(ys, p.deriv_smooth_type, p.deriv_smooth_points)
        base = float(np.min(ys))
        peak_max = float(np.max(ys))

        for i in _local_maxima(yd, xw):
            height_above_base = ys[i] - base
            prom = _prominence(ys, i)

            if p.height_mode == "range":
                if height_above_base < threshold:
                    continue
            elif p.height_mode == "prominence":
                if prom < threshold:
                    continue
            elif p.height_mode == "max":
                if peak_max <= 0 or ys[i] < (p.height / 100.0) * peak_max:
                    continue

            full_i = int(idx[i])
            centre = _parabolic_center(xw, ys, i) if p.interpolate_center else float(xw[i])
            candidate = Peak(
                index=full_i,
                x=centre,
                y=float(yw_raw[i]),
                y_corrected=float(corrected[i]),
                prominence=float(prom),
            )
            previous = found.get(full_i)
            if previous is None or prom > previous.prominence:
                found[full_i] = candidate

    peaks = sorted(found.values(), key=lambda pk: pk.x)

    if p.min_distance > 0:
        kept: list[Peak] = []
        for pk in sorted(peaks, key=lambda q: -q.prominence):
            if all(abs(pk.x - k.x) >= p.min_distance for k in kept):
                kept.append(pk)
        peaks = sorted(kept, key=lambda q: q.x)

    if p.max_peaks is not None and len(peaks) > p.max_peaks:
        strongest = sorted(peaks, key=lambda q: -q.prominence)[: p.max_peaks]
        peaks = sorted(strongest, key=lambda q: q.x)

    return Analysis(
        idx=idx, x=xw, y_raw=yw_raw, y_smooth=yw,
        baseline=baseline, y_corrected=corrected, peaks=peaks,
    )


def find_peaks(x: np.ndarray, y: np.ndarray, p: Params) -> list[Peak]:
    """Peaks only, sorted by ascending x."""
    return analyze(x, y, p).peaks


# --------------------------------------------------------------------------
# CSV output
# --------------------------------------------------------------------------

def _fmt(value: float, decimal: str, precision: int) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return ""
    text = f"{value:.{precision}g}"
    return text.replace(".", ",") if decimal == "," else text


def write_matrix(
    path: str,
    x: np.ndarray,
    names: list[str],
    peaks_per_curve: list[list[Peak]],
    delimiter: str,
    decimal: str,
    precision: int,
    x_scale: float,
    transpose: bool,
) -> None:
    flags = np.zeros((len(x), len(names)), dtype=int)
    for col, peaks in enumerate(peaks_per_curve):
        for pk in peaks:
            flags[pk.index, col] = 1

    xs = [_fmt(float(v) * x_scale, decimal, precision) for v in x]

    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=delimiter, lineterminator="\n")
        if transpose:
            # Rows = curves, columns = X -- the layout of the by-hand sheet.
            w.writerow(["curve"] + xs)
            for col, name in enumerate(names):
                w.writerow([name] + [str(v) for v in flags[:, col]])
        else:
            w.writerow(["x"] + names)
            for row, xv in enumerate(xs):
                w.writerow([xv] + [str(v) for v in flags[row]])


def write_peak_list(
    path: str,
    names: list[str],
    peaks_per_curve: list[list[Peak]],
    delimiter: str,
    decimal: str,
    precision: int,
    x_scale: float,
) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=delimiter, lineterminator="\n")
        w.writerow(["curve", "peak", "x_center", "y_height", "y_corrected", "prominence", "x_index"])
        for name, peaks in zip(names, peaks_per_curve):
            for n, pk in enumerate(peaks, start=1):
                w.writerow([
                    name,
                    n,
                    _fmt(pk.x * x_scale, decimal, precision),
                    _fmt(pk.y, decimal, precision),
                    _fmt(pk.y_corrected, decimal, precision),
                    _fmt(pk.prominence, decimal, precision),
                    pk.index,
                ])


# --------------------------------------------------------------------------
# Optional plots
# --------------------------------------------------------------------------

def draw_curve(ax, x: np.ndarray, y: np.ndarray, name: str, result: Analysis, p: Params) -> None:
    """Render one curve with its background and peaks. Shared by PNG export and the GUI."""
    show_baseline = p.baseline != "none" and result.baseline.size == result.x.size

    ax.plot(x, y, "-", color="0.55" if show_baseline else "k", lw=0.8, label=name)
    if show_baseline:
        ax.plot(result.x, result.baseline, "b--", lw=0.9, label="background")
        ax.plot(result.x, result.y_corrected, "k-", lw=0.9, label="corrected")
        ax.axhline(0.0, color="0.8", lw=0.6)

    peaks = result.peaks
    if peaks:
        py = [pk.y_corrected if show_baseline else pk.y for pk in peaks]
        ax.plot([pk.x for pk in peaks], py, "rv", ms=6)
        for pk in peaks:
            ax.axvline(pk.x, color="r", lw=0.5, alpha=0.4)
    for bound in (p.xmin, p.xmax):
        if bound is not None:
            ax.axvline(bound, color="b", ls=":", lw=0.8)

    if show_baseline and result.y_corrected.size:
        # Autoscaling on the raw curve would squash the corrected one flat
        # against the axis, which is exactly the part being judged.
        lo = min(0.0, float(np.min(result.y_corrected)))
        hi = max(0.0, float(np.max(result.y_corrected)))
        if math.isfinite(lo) and math.isfinite(hi) and hi > lo:
            pad = 0.08 * (hi - lo)
            ax.set_ylim(lo - pad, hi + pad)

    ax.set_title(f"{name} -- {len(peaks)} peaks")
    ax.set_xlabel("x")
    ax.set_ylabel(name)
    ax.legend(loc="best", fontsize=8)


def write_plots(directory: str, x: np.ndarray, names: list[str], ys, results, p: Params) -> None:
    # Deliberately not pyplot: it is neither thread-safe nor willing to share a
    # process with the GUI's live canvas.
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    os.makedirs(directory, exist_ok=True)
    for name, y, result in zip(names, ys, results):
        fig = Figure(figsize=(8, 5))
        FigureCanvasAgg(fig)
        draw_curve(fig.subplots(), x, y, name, result, p)
        fig.tight_layout()
        safe = re.sub(r"[^\w.-]+", "_", name) or "curve"
        fig.savefig(os.path.join(directory, f"{safe}.png"), dpi=110)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="qtipeaks",
        description="QtiPlot-style peak finding over every curve of a CSV, "
                    "emitting a 1/0 occupancy table and a peak list.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("input", help="CSV with X in the first column, one curve per further column")
    ap.add_argument("-o", "--outdir", default=None, help="output directory (default: next to the input)")
    ap.add_argument("--prefix", default=None, help="output file stem (default: input file stem)")

    g = ap.add_argument_group("Dados")
    g.add_argument("--xmin", type=float, default=None, help="search from this X (QtiPlot 'A partir de Xmin')")
    g.add_argument("--xmax", type=float, default=None, help="search up to this X (QtiPlot 'Ate Xmax')")

    g = ap.add_argument_group("Filtro")
    g.add_argument("--direction", choices=["positive", "negative", "both"], default="positive")
    g.add_argument("--height", type=float, default=5.0, help="height threshold, in %% (QtiPlot 'Altura')")
    g.add_argument("--height-mode", choices=["range", "prominence", "max"], default="range",
                   help="range: height above the window minimum must exceed height%% of the window span; "
                        "prominence: the peak's prominence must; max: the peak must reach height%% of the window maximum")
    g.add_argument("--smooth", dest="smooth_points", type=int, default=0,
                   help="smooth the data first, half-width in points (QtiPlot 'Suavizar'); 0 = off")
    g.add_argument("--smooth-type", choices=["average", "savgol"], default="average")

    g = ap.add_argument_group("Fundo (polynomial background)")
    g.add_argument("--baseline", choices=list(BASELINE_KINDS), default="none",
                   help="subtract a polynomial background before searching; poly-iter strips the "
                        "peaks out of the fit so small features survive the height threshold")
    g.add_argument("--baseline-degree", type=int, default=3, help="polynomial degree")
    g.add_argument("--baseline-iterations", type=int, default=25, help="poly-iter refit passes")

    g = ap.add_argument_group("Suavizar Derivada")
    g.add_argument("--deriv-smooth-type", choices=["none", "average", "savgol"], default="none")
    g.add_argument("--deriv-smooth-points", type=int, default=2, help="half-width in points")

    g = ap.add_argument_group("Selection")
    g.add_argument("--max-peaks", type=int, default=None, help="keep only the N most prominent peaks per curve")
    g.add_argument("--min-distance", type=float, default=0.0, help="minimum spacing between peaks, in X units")
    g.add_argument("--interpolate-center", action="store_true",
                   help="refine centres by parabolic interpolation (the 1/0 table still snaps to the grid)")

    g = ap.add_argument_group("Curve selection")
    g.add_argument("--curves", default=None,
                   help="comma-separated curve names or 1-based column numbers to process (default: all)")

    g = ap.add_argument_group("Formatting")
    g.add_argument("--delimiter", default=None,
                   help="input delimiter: comma, semicolon, tab, whitespace, or the character "
                        "itself (default: auto-detect)")
    g.add_argument("--decimal", choices=[".", ","], default=None,
                   help="input decimal mark, '.' or ',' (default: auto-detect)")
    g.add_argument("--out-delimiter", default=None, help="output delimiter (default: same as input)")
    g.add_argument("--out-decimal", choices=[".", ","], default=None, help="output decimal mark (default: same as input)")
    g.add_argument("--precision", type=int, default=10, help="significant digits in the output")
    g.add_argument("--x-scale", type=float, default=1.0, help="multiply X in the outputs, e.g. 1000 for V -> meV")
    g.add_argument("--transpose", action="store_true",
                   help="write the matrix with curves as rows and X as columns")

    ap.add_argument("--plot", metavar="DIR", default=None, help="also write one PNG per curve into DIR")
    ap.add_argument("-q", "--quiet", action="store_true")
    return ap


def parse_delimiter(text: str | None) -> str | None:
    """Accept 'comma', 'tab', '\\t' or the raw character."""
    if text is None:
        return None
    named = {
        "comma": ",", "semicolon": ";", "tab": "\t", "\\t": "\t",
        "space": WHITESPACE, "spaces": WHITESPACE, "whitespace": WHITESPACE, "ws": WHITESPACE,
    }
    key = text.strip().lower()
    if key in named:
        return named[key]
    if len(text) == 1:
        return text
    raise SystemExit(f"unrecognised delimiter {text!r}; use comma, semicolon, tab, whitespace or one character")


def select_curves(table: Table, spec: str | None) -> tuple[list[str], list[np.ndarray]]:
    if not spec:
        return table.names, table.ys
    wanted = [s.strip() for s in spec.split(",") if s.strip()]
    names: list[str] = []
    ys: list[np.ndarray] = []
    for item in wanted:
        if item in table.names:
            j = table.names.index(item)
        elif item.isdigit():
            j = int(item) - 1
            if not 0 <= j < len(table.names):
                raise SystemExit(f"--curves: column {item} out of range (1..{len(table.names)})")
        else:
            raise SystemExit(f"--curves: no curve named {item!r}. Available: {', '.join(table.names)}")
        names.append(table.names[j])
        ys.append(table.ys[j])
    return names, ys


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    table = read_table(args.input, parse_delimiter(args.delimiter), args.decimal)
    names, ys = select_curves(table, args.curves)
    if not names:
        raise SystemExit(f"{args.input}: no curve columns found next to the X column")

    params = Params(
        xmin=args.xmin,
        xmax=args.xmax,
        direction=args.direction,
        height=args.height,
        height_mode=args.height_mode,
        smooth_type=args.smooth_type,
        smooth_points=max(0, args.smooth_points),
        deriv_smooth_type=args.deriv_smooth_type,
        deriv_smooth_points=max(0, args.deriv_smooth_points),
        baseline=args.baseline,
        baseline_degree=args.baseline_degree,
        baseline_iterations=args.baseline_iterations,
        max_peaks=args.max_peaks,
        min_distance=args.min_distance,
        interpolate_center=args.interpolate_center,
    )

    results = [analyze(table.x, y, params) for y in ys]
    peaks_per_curve = [r.peaks for r in results]

    out_delim, out_dec = effective_output_format(
        parse_delimiter(args.out_delimiter) or table.delimiter,
        args.out_decimal or table.decimal,
    )

    outdir = args.outdir or os.path.dirname(os.path.abspath(args.input))
    os.makedirs(outdir, exist_ok=True)
    stem = args.prefix or os.path.splitext(os.path.basename(args.input))[0]
    matrix_path = os.path.join(outdir, f"{stem}_peak_matrix.csv")
    list_path = os.path.join(outdir, f"{stem}_peak_list.csv")

    write_matrix(matrix_path, table.x, names, peaks_per_curve, out_delim, out_dec,
                 args.precision, args.x_scale, args.transpose)
    write_peak_list(list_path, names, peaks_per_curve, out_delim, out_dec,
                    args.precision, args.x_scale)

    if args.plot:
        write_plots(args.plot, table.x, names, ys, results, params)

    if not args.quiet:
        total = sum(len(p) for p in peaks_per_curve)
        print(f"read {args.input}: {len(table.x)} x-values, {len(names)} curves "
              f"(delimiter {DELIMITER_NAMES.get(table.delimiter, table.delimiter)!s}, "
              f"decimal {table.decimal!r})")
        for name, peaks in zip(names, peaks_per_curve):
            print(f"  {name}: {len(peaks)} peaks")
        print(f"{total} peaks total")
        print(f"wrote {matrix_path}")
        print(f"wrote {list_path}")
        if args.plot:
            print(f"wrote plots to {args.plot}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
