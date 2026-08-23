"""
The Confinement Designer's plots, drawn with matplotlib into a QML item.

Two pictures answer the two questions a candidate raises. *Does it explain
the measurement?* — the levels it produces beside the levels that were
measured, and the relative error of each. *What was it fitted to?* — the
spectrum with its peaks and the branch boundaries that split them into
carriers.

Both are ordinary matplotlib drawn into
:class:`~src.widgets.qml_figure_canvas.FigureCanvasItem`'s figure. That is
the whole point of the host: the plots came across from the standalone app's
Tk canvas unchanged apart from their labels.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Property, Signal, Slot

from src.widgets.qml_figure_canvas import FigureCanvasItem

logger = logging.getLogger(__name__)


class DesignerCanvas(FigureCanvasItem):
    """A figure that knows how to draw a designer candidate."""

    #: Error bands, in percent, and the colour each gets. Green is "as good
    #: as the measurement"; red is a candidate that does not explain a level.
    ERROR_BANDS = ((2.0, "#2ECC71"), (5.0, "#FF9800"))
    ERROR_BAD = "#FF6B6B"

    ELECTRON_COLOUR = "#5BCEFA"
    HOLE_COLOUR = "#F5A9B8"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._foreground = "#cccccc"
        self._grid = "#444444"

    # ── palette ──────────────────────────────────────────────────────────

    foregroundColorChanged = Signal()

    def _get_foreground(self) -> str:
        return self._foreground

    def _set_foreground(self, colour: str) -> None:
        colour = str(colour or "").strip()
        if colour and colour != self._foreground:
            self._foreground = colour
            self.foregroundColorChanged.emit()

    #: Text and axis colour, so the figure follows the theme instead of
    #: painting light grey onto a light panel.
    foregroundColor = Property(str, _get_foreground, _set_foreground,
                               notify=foregroundColorChanged)

    def _style(self, ax) -> None:
        ax.set_facecolor(self._background)
        for spine in ax.spines.values():
            spine.set_color(self._grid)
        ax.tick_params(colors=self._foreground, labelsize=7)
        ax.xaxis.label.set_color(self._foreground)
        ax.yaxis.label.set_color(self._foreground)
        ax.title.set_color(self._foreground)
        ax.grid(True, color=self._grid, alpha=0.3, linewidth=0.5)

    # ── the candidate ────────────────────────────────────────────────────

    @Slot('QVariantMap')
    def showCandidate(self, candidate) -> None:
        """Draw one candidate: its levels against the targets, and the error.

        ``candidate`` is what ``ToolImplementations._designer_candidate``
        produced — plain numbers, so nothing here reaches back into a search
        result that a second run has already replaced.
        """
        candidate = dict(candidate or {})
        self.figure.clf()
        if not candidate.get('targets'):
            self._draw_message("No candidate selected")
            return

        hole = candidate.get('hole') or None
        levels_ax = self.figure.add_subplot(121)
        error_ax = self.figure.add_subplot(122)

        def _bars(ax, data, offset, label, colour):
            targets = list(data.get('targets') or [])
            computed = list(data.get('computed') or [])
            x = np.arange(len(targets)) + offset
            width = 0.2 if hole else 0.35
            ax.bar(x - width / 2, targets, width, label=f"Measured ({label})",
                   color=colour, alpha=0.45)
            ax.bar(x + width / 2, computed, width, label=f"Model ({label})",
                   color=colour, alpha=0.9)
            return list(data.get('errors_pct') or [])

        errors = _bars(levels_ax, candidate, 0.0,
                       "electron" if hole else "target", self.ELECTRON_COLOUR)
        hole_errors = (_bars(levels_ax, hole, 0.45, "hole", self.HOLE_COLOUR)
                       if hole else [])

        levels_ax.set_xlabel("Level")
        levels_ax.set_ylabel("Energy (eV)")
        levels_ax.set_title(self._dimension_label(candidate) if not hole
                            else (f"e⁻: {self._dimension_label(candidate)}\n"
                                  f"h⁺: {self._dimension_label(hole)}"),
                            fontsize=9)
        legend = levels_ax.legend(fontsize=7, facecolor=self._background,
                                  edgecolor=self._grid)
        for text in legend.get_texts():
            text.set_color(self._foreground)

        self._error_bars(error_ax, errors, 0.0)
        if hole:
            self._error_bars(error_ax, hole_errors, 0.4, hatch="//")
            error_ax.set_title(
                f"pair error {candidate.get('pair_score', float('nan')):.2f}%  |  "
                f"geometries differ by "
                f"{candidate.get('pair_mismatch_nm', 0.0):.3f} nm", fontsize=9)
        else:
            error_ax.set_title(f"RRMSE = {candidate.get('rrmse', float('nan')):.2f}%",
                               fontsize=9)
        error_ax.axhline(0, color=self._foreground, lw=0.5)
        error_ax.set_ylabel("Relative error (%)")
        error_ax.set_xlabel("Level")

        for ax in (levels_ax, error_ax):
            self._style(ax)
        self.figure.tight_layout(pad=0.6)
        self.redraw()

    def _error_bars(self, ax, values, offset, hatch=None) -> None:
        colours = [self._error_colour(v) for v in values]
        ax.bar(np.arange(len(values)) + offset, values, 0.35,
               color=colours, alpha=0.8, hatch=hatch)

    def _error_colour(self, value: float) -> str:
        for limit, colour in self.ERROR_BANDS:
            if abs(value) < limit:
                return colour
        return self.ERROR_BAD

    @staticmethod
    def _dimension_label(candidate: dict) -> str:
        """``L = 8.001 nm`` and friends, from the candidate's own geometry."""
        names = {
            ("0D", "spherical"): ("R",),
            ("0D", "disc"): ("R", "L_z"),
            ("0D", "parabolic"): ("ħω_xy", "ħω_z"),
            ("1D", "cartesian"): ("L",),
            ("2D", "circular"): ("R",),
            ("2D", "cartesian"): ("Lx", "Ly"),
            ("3D", "cylindrical"): ("R", "H"),
            ("3D", "cartesian"): ("Lx", "Ly", "Lz"),
        }.get((candidate.get('ndim', ''), candidate.get('coords', '')))
        dims = list(candidate.get('dims_nm') or [])
        if not names or len(names) != len(dims):
            names = tuple(f"d{i + 1}" for i in range(len(dims)))
        unit = ("meV" if (candidate.get('ndim') == "0D"
                          and candidate.get('coords') == "parabolic") else "nm")
        body = ", ".join(f"{n} = {v:.3f}" for n, v in zip(names, dims))
        return f"{body} {unit}"

    # ── the spectrum the search was given ────────────────────────────────

    @Slot('QVariantMap')
    def showSpectrum(self, preview) -> None:
        """Draw the spectrum, its peaks, and the branch boundaries.

        The boundaries are the point: a split at V = 0 tears a charged well's
        electron ladder in half, and seeing where the line falls is how a
        user notices before the search reports nonsense.
        """
        preview = dict(preview or {})
        self.figure.clf()
        x = list(preview.get('x') or [])
        if not x:
            self._draw_message(preview.get('error') or "No spectrum")
            return

        ax = self.figure.add_subplot(111)
        raw = list(preview.get('raw') or [])
        corrected = list(preview.get('corrected') or [])
        baseline = list(preview.get('baseline') or [])

        ax.plot(x, raw, color=self._foreground, lw=1.0, alpha=0.5, label="Raw")
        if len(baseline) == len(x):
            ax.plot(x, baseline, color="#FFD700", lw=1.0, ls="--",
                    label="Background")
        if len(corrected) == len(x):
            ax.plot(x, corrected, color=self.ELECTRON_COLOUR, lw=1.2,
                    label="Corrected")

        peaks = list(preview.get('peaks_V') or [])
        if peaks:
            reference = corrected if len(corrected) == len(x) else raw
            heights = np.interp(peaks, x, reference)
            ax.plot(peaks, heights, "v", color=self.HOLE_COLOUR, ms=5,
                    ls="none", label=f"{len(peaks)} peak(s)")

        for value, label in ((preview.get('split_e'), "split e⁻"),
                             (preview.get('split_h'), "split h⁺")):
            if value is None:
                continue
            ax.axvline(float(value), color="#9B4F96", lw=0.8, ls=":")
            ax.annotate(label, (float(value), 0.98), xycoords=("data", "axes fraction"),
                        color=self._foreground, fontsize=7, ha="left", va="top")

        ax.set_xlabel("Sample bias (V)")
        ax.set_ylabel("dI/dV")
        ax.set_title(preview.get('column') or "", fontsize=9)
        legend = ax.legend(fontsize=7, facecolor=self._background,
                           edgecolor=self._grid)
        for text in legend.get_texts():
            text.set_color(self._foreground)
        self._style(ax)
        self.figure.tight_layout(pad=0.6)
        self.redraw()

    # ── the line, position by position ───────────────────────────────────

    #: What a position with no confinement is painted. Deliberately not a
    #: colour from the scale: absence is a result, and giving it one would be
    #: inventing a size for it.
    NO_CONFINEMENT_GREY = "0.82"

    @Slot('QVariantMap')
    def showLineScan(self, run) -> None:
        """A colour strip along the line, and the sizes under it by group.

        The strip is a ``pcolormesh`` and not an ``imshow``: with a single
        row of cells imshow resamples and blurs the boundary between one
        domain and its neighbour, which is exactly what the map is read for.
        """
        import matplotlib

        run = dict(run or {})
        points = list(run.get('points') or [])
        self.figure.clf()
        if not points:
            self._draw_message(run.get('error') or "No line scan yet")
            return

        positions = np.array([float(p.get('position_nm', i))
                              for i, p in enumerate(points)], dtype=float)
        sizes = np.array([float(p.get('size_nm', float('nan')))
                          if p.get('converged') else float('nan')
                          for p in points], dtype=float)
        masked = np.ma.masked_invalid(sizes)

        strip_ax = self.figure.add_subplot(211)
        profile_ax = self.figure.add_subplot(212, sharex=strip_ax)

        half = ((positions[1] - positions[0]) / 2.0 if positions.size > 1
                else 0.5)
        edges = np.concatenate([positions - half, [positions[-1] + half]])
        cmap = matplotlib.colormaps.get_cmap("viridis").copy()
        cmap.set_bad(self.NO_CONFINEMENT_GREY)
        # A masked cell is not drawn at all: the grey comes from the axes
        # background, so "no confinement" reads as outside the scale.
        strip_ax.set_facecolor(self.NO_CONFINEMENT_GREY)
        image = strip_ax.pcolormesh(edges, np.array([0.0, 1.0]),
                                    masked.reshape(1, -1), cmap=cmap,
                                    shading="flat")
        strip_ax.set_yticks([])
        strip_ax.set_title("Confinement along the line "
                           "(grey = none found)", fontsize=9)
        bar = self.figure.colorbar(image, ax=strip_ax, pad=0.01)
        bar.set_label("size (nm)", fontsize=8, color=self._foreground)
        bar.ax.tick_params(colors=self._foreground, labelsize=7)

        # The profile, coloured by group, with the empty stretches shaded.
        for segment in (run.get('segments') or []):
            if segment.get('group') is None or segment.get('group') < 0:
                profile_ax.axvspan(float(segment.get('start', 0.0)) - half,
                                   float(segment.get('end', 0.0)) + half,
                                   color="#3a3a4e", alpha=0.35, zorder=0)

        groups = list(run.get('groups') or [])
        if groups:
            palette = matplotlib.colormaps.get_cmap("tab10")
            for group in groups:
                index = int(group.get('index', 0))
                rows = [i for i, p in enumerate(points)
                        if int(p.get('group', -1)) == index]
                profile_ax.plot(positions[rows], sizes[rows], "o", ms=4,
                                color=palette(index % 10),
                                label=f"{float(group.get('size_nm', 0)):.2f} nm "
                                      f"({int(group.get('count', len(rows)))})")
            legend = profile_ax.legend(fontsize=7, title="groups",
                                       title_fontsize=7,
                                       facecolor=self._background,
                                       edgecolor=self._grid)
            for text in legend.get_texts():
                text.set_color(self._foreground)
            legend.get_title().set_color(self._foreground)

        profile_ax.set_xlabel(run.get('position_label') or "Position (nm)")
        profile_ax.set_ylabel("Confinement (nm)")
        for ax in (strip_ax, profile_ax):
            self._style(ax)
        # Set last, because _style paints the theme background: the strip's
        # missing cells must NOT be the panel colour. Viridis runs to nearly
        # black at its low end, so on a dark background "no confinement" and
        # "the smallest well on the line" would look the same.
        strip_ax.set_facecolor(self.NO_CONFINEMENT_GREY)
        self.figure.tight_layout(pad=0.6)
        self.redraw()

    # ── nothing to draw ──────────────────────────────────────────────────

    def _draw_message(self, message: str) -> None:
        ax = self.figure.add_subplot(111)
        ax.axis("off")
        ax.text(0.5, 0.5, message, ha="center", va="center",
                color=self._foreground, fontsize=10, transform=ax.transAxes)
        ax.set_facecolor(self._background)
        self.redraw()

    @Slot(str)
    def showMessage(self, message: str) -> None:
        """Put a line of text where a plot would be — an empty result, or why."""
        self.figure.clf()
        self._draw_message(message)
