"""
The direct solvers' plots.

A well and a dot are read differently. For a well what matters is where the
states sit inside the potential and what their wavefunctions look like — the
picture is the potential with the levels drawn as lines across it. For a dot
the spectrum is discrete and atom-like, so what matters is the shells, how
they fill, and the addition energy that peaks when one closes.

Drawn with ordinary matplotlib into
:class:`~src.widgets.qml_figure_canvas.FigureCanvasItem`'s figure, like the
designer's plots.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Property, Signal, Slot

from src.widgets.qml_figure_canvas import FigureCanvasItem

logger = logging.getLogger(__name__)


class SolverCanvas(FigureCanvasItem):
    """A figure that knows how to draw a solved well or dot."""

    POTENTIAL_COLOUR = "#9B4F96"
    LEVEL_COLOUR = "#5BCEFA"
    SELECTED_COLOUR = "#F5A9B8"
    TARGET_COLOUR = "#FFD700"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._foreground = "#cccccc"
        self._grid = "#444444"

    foregroundColorChanged = Signal()

    def _get_foreground(self) -> str:
        return self._foreground

    def _set_foreground(self, colour: str) -> None:
        colour = str(colour or "").strip()
        if colour and colour != self._foreground:
            self._foreground = colour
            self.foregroundColorChanged.emit()

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

    def _legend(self, ax, **kwargs) -> None:
        legend = ax.legend(fontsize=7, facecolor=self._background,
                           edgecolor=self._grid, **kwargs)
        if legend is None:
            return
        for text in legend.get_texts():
            text.set_color(self._foreground)
        if legend.get_title() is not None:
            legend.get_title().set_color(self._foreground)

    # ── a solved well ────────────────────────────────────────────────────

    @Slot('QVariantMap', int)
    def showWell(self, result, state_index=0) -> None:
        """The potential with its levels, and the chosen state's density.

        One picture, two axes sharing the position: a level is only
        meaningful against the well it sits in, and the wavefunction only
        against the level.
        """
        result = dict(result or {})
        self.figure.clf()
        energies = list(result.get('E_eV') or [])
        x = list(result.get('x_nm') or [])
        if not energies or not x:
            self._draw_message(result.get('error') or "Nothing solved yet")
            return

        well_ax = self.figure.add_subplot(211)
        density_ax = self.figure.add_subplot(212, sharex=well_ax)

        potential = list(result.get('V_eV') or [])
        if len(potential) == len(x):
            well_ax.plot(x, potential, color=self.POTENTIAL_COLOUR, lw=1.5,
                         label="Potential")

        index = max(0, min(int(state_index), len(energies) - 1))
        for i, energy in enumerate(energies):
            chosen = (i == index)
            well_ax.axhline(energy,
                            color=self.SELECTED_COLOUR if chosen
                            else self.LEVEL_COLOUR,
                            lw=1.6 if chosen else 0.9,
                            alpha=1.0 if chosen else 0.65)
        well_ax.axhline(energies[index], color=self.SELECTED_COLOUR, lw=1.6,
                        label=f"E{index + 1} = {energies[index]:.4f} eV")

        # The measured energies the candidate was fitted to, if there were
        # any: the whole point of simulating a candidate is seeing whether
        # the numerical levels land on them.
        comparison = dict(result.get('comparison') or {})
        for target in (comparison.get('targets') or []):
            well_ax.axhline(float(target), color=self.TARGET_COLOUR, lw=0.8,
                            ls="--", alpha=0.9)
        if comparison.get('targets'):
            well_ax.axhline(float(comparison['targets'][0]),
                            color=self.TARGET_COLOUR, lw=0.8, ls="--",
                            label="Measured")

        well_ax.set_ylabel("Energy (eV)")
        well_ax.set_title(self._well_title(result, comparison), fontsize=9)
        self._legend(well_ax)

        densities = result.get('psi') or []
        if index < len(densities):
            density = list(densities[index])
            if len(density) == len(x):
                density_ax.fill_between(x, density, color=self.SELECTED_COLOUR,
                                        alpha=0.35)
                density_ax.plot(x, density, color=self.SELECTED_COLOUR, lw=1.2)
        density_ax.set_xlabel("Position (nm)")
        density_ax.set_ylabel("|ψ|²")

        for ax in (well_ax, density_ax):
            self._style(ax)
        self.figure.tight_layout(pad=0.6)
        self.redraw()

    @staticmethod
    def _well_title(result: dict, comparison: dict) -> str:
        levels = len(result.get('E_eV') or [])
        title = f"{levels} state(s)"
        if comparison.get('rrmse_pct') == comparison.get('rrmse_pct'):  # not NaN
            title += f" — {comparison['rrmse_pct']:.3f}% against the measured levels"
            if comparison.get('covered') is False:
                title += " (targets above the last level solved)"
        return title

    # ── a solved dot ─────────────────────────────────────────────────────

    @Slot('QVariantMap', int)
    def showDot(self, result, state_index=0) -> None:
        """Shells, density of states, addition energies, and one radial state.

        The four pictures a dot is read through: which levels there are, what
        a dI/dV would see, where a shell closes, and what the chosen state
        looks like in radius.
        """
        result = dict(result or {})
        self.figure.clf()
        levels = list(result.get('levels') or [])
        if not levels:
            self._draw_message(result.get('error') or "Nothing solved yet")
            return

        shells_ax = self.figure.add_subplot(221)
        dos_ax = self.figure.add_subplot(222)
        addition_ax = self.figure.add_subplot(223)
        radial_ax = self.figure.add_subplot(224)

        index = max(0, min(int(state_index), len(levels) - 1))

        # Shells: one bar per level, height = how many electrons it holds,
        # which is what makes a closed shell visible at a glance.
        energies = [level['E_eV'] for level in levels]
        occupancies = [level['occupancy'] for level in levels]
        colours = [self.SELECTED_COLOUR if i == index else self.LEVEL_COLOUR
                   for i in range(len(levels))]
        width = (max(0.01, (max(energies) - min(energies)) / max(1, len(levels)))
                 * 0.6)
        shells_ax.bar(energies, occupancies, width=width, color=colours,
                      alpha=0.9)
        for level in levels[:12]:
            shells_ax.annotate(level['label'], (level['E_eV'], level['occupancy']),
                               fontsize=6, ha="center", va="bottom",
                               color=self._foreground)
        shells_ax.set_xlabel("Energy (eV)")
        shells_ax.set_ylabel("Electrons")
        shells_ax.set_title(self._dot_title(result), fontsize=9)

        dos = dict(result.get('dos') or {})
        if dos.get('x') and dos.get('y'):
            dos_ax.plot(dos['x'], dos['y'], color=self.LEVEL_COLOUR, lw=1.2)
            dos_ax.fill_between(dos['x'], dos['y'], color=self.LEVEL_COLOUR,
                                alpha=0.25)
        comparison = dict(result.get('comparison') or {})
        for target in (comparison.get('targets') or []):
            dos_ax.axvline(float(target), color=self.TARGET_COLOUR, lw=0.8,
                           ls="--", alpha=0.9)
        dos_ax.set_xlabel("Energy (eV)")
        dos_ax.set_ylabel("Density of states")
        dos_ax.set_title("What a dI/dV would see", fontsize=9)

        addition = list(result.get('addition_eV') or [])
        if addition:
            electrons = np.arange(1, len(addition) + 1)
            addition_ax.plot(electrons, addition, "o-", ms=3, lw=1.0,
                             color=self.SELECTED_COLOUR)
            # A filled shell is where the next electron costs most.
            for shell in (result.get('shells') or []):
                filled = int(shell.get('filled', 0))
                if 0 < filled <= len(addition):
                    addition_ax.axvline(filled, color=self._grid, lw=0.8,
                                        ls=":")
        addition_ax.set_xlabel("Electrons in the dot")
        addition_ax.set_ylabel("Addition energy (eV)")
        addition_ax.set_title("Peaks where a shell closes", fontsize=9)

        radial = dict(result.get('radial') or {})
        if radial.get('r_nm') and radial.get('psi'):
            radial_ax.plot(radial['r_nm'], radial['psi'],
                           color=self.SELECTED_COLOUR, lw=1.2)
            radial_ax.fill_between(radial['r_nm'], radial['psi'],
                                   color=self.SELECTED_COLOUR, alpha=0.3)
            radial_ax.set_title(f"State {radial.get('label', '')}", fontsize=9)
        else:
            radial_ax.set_title("No radial function for this model", fontsize=9)
        radial_ax.set_xlabel("r (nm)")
        radial_ax.set_ylabel("|u(r)|²")

        for ax in (shells_ax, dos_ax, addition_ax, radial_ax):
            self._style(ax)
        self.figure.tight_layout(pad=0.6)
        self.redraw()

    @staticmethod
    def _dot_title(result: dict) -> str:
        levels = result.get('levels') or []
        shells = result.get('shells') or []
        title = f"{len(levels)} level(s) in {len(shells)} shell(s)"
        comparison = dict(result.get('comparison') or {})
        if comparison.get('rrmse_pct') == comparison.get('rrmse_pct'):
            title += f" — {comparison['rrmse_pct']:.3f}% vs measured"
        return title

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
        """Put a line of text where a plot would be."""
        self.figure.clf()
        self._draw_message(message)
