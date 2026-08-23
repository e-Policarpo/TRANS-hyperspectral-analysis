"""
The interactive potential editor: features you can see and drag.

A 2D or 3D model is a handful of wells and barriers placed in a box, and
placing them by typing coordinates is how you end up with a potential nobody
can picture. This draws them — over the potential they make, and optionally
over the state that lives in it — and lets them be picked up and moved.

A 3D model is edited one plane at a time (XY, XZ, YZ). That is not a
compromise for the drawing's sake: dragging in a projection is exactly two
of the three coordinates, and the third stays where it was, which is what
makes the interaction unambiguous.

The mouse work is all here; the feature list itself belongs to the backend,
so this emits "the user moved feature 3 to here" and lets the owner decide
what that means.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
from PySide6.QtCore import Property, Qt, Signal, Slot

from src.physics.feature_specs import spec_extent, spec_position
from src.widgets.qml_figure_canvas import FigureCanvasItem

logger = logging.getLogger(__name__)


class PotentialCanvas(FigureCanvasItem):
    """Draws a model's features, and lets the mouse move them."""

    #: One colour per feature, cycled. Distinct rather than a gradient: they
    #: identify features in the list, they do not encode a quantity.
    FEATURE_COLOURS = ("#5BCEFA", "#F5A9B8", "#66ff66", "#FFD700", "#FF6B6B",
                       "#9B4F96", "#00BCD4", "#FF9800", "#E91E63", "#2ECC71")
    SELECTED_COLOUR = "#FFD700"

    #: How near a handle a click has to land, in screen pixels. In pixels and
    #: not nanometres because a handle is a fixed size on screen whatever the
    #: zoom.
    HANDLE_GRAB_PX = 9.0

    #: Which pairs of axes each projection shows.
    PROJECTIONS = {'xy': (0, 1), 'xz': (0, 2), 'yz': (1, 2)}
    AXIS_LABELS = {'xy': ("x (nm)", "y (nm)"),
                   'xz': ("x (nm)", "z (nm)"),
                   'yz': ("y (nm)", "z (nm)")}

    #: The user picked a feature (or -1 for empty space).
    featureSelected = Signal(int)
    #: A feature was dragged; the centre it should now have, in the plane
    #: being shown. The owner decides which of its coordinates that means.
    featureMoved = Signal(int, float, float)
    #: A handle was dragged; the half-size it should now have on each shown
    #: axis, in nm.
    featureResized = Signal(int, float, float)
    #: A double-click on empty space, in data coordinates.
    featureAdded = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(False)

        self._foreground = "#cccccc"
        self._grid = "#444444"
        self._features: List[dict] = []
        self._selected = -1
        self._projection = 'xy'
        self._domain = [20.0, 20.0, 20.0]
        self._potential = {}
        self._density = {}
        self._drag = None

    # ── what is being edited ─────────────────────────────────────────────

    featuresChanged = Signal()
    selectedIndexChanged = Signal()
    projectionChanged = Signal()
    domainChanged = Signal()
    foregroundColorChanged = Signal()

    def _get_foreground(self):
        return self._foreground

    def _set_foreground(self, colour):
        colour = str(colour or "").strip()
        if colour and colour != self._foreground:
            self._foreground = colour
            self.foregroundColorChanged.emit()
            self.redraw()

    foregroundColor = Property(str, _get_foreground, _set_foreground,
                               notify=foregroundColorChanged)

    def _get_projection(self):
        return self._projection

    def _set_projection(self, value):
        value = str(value or 'xy').lower()
        if value in self.PROJECTIONS and value != self._projection:
            self._projection = value
            self.projectionChanged.emit()
            self.redraw()

    #: Which plane of a 3D model is shown — and therefore which two
    #: coordinates a drag changes.
    projection = Property(str, _get_projection, _set_projection,
                          notify=projectionChanged)

    def _get_selected(self):
        return self._selected

    def _set_selected(self, index):
        index = int(index)
        if index != self._selected:
            self._selected = index
            self.selectedIndexChanged.emit()
            self.redraw()

    selectedIndex = Property(int, _get_selected, _set_selected,
                             notify=selectedIndexChanged)

    @Slot('QVariantList')
    def setFeatures(self, specs) -> None:
        """Replace the features being shown."""
        self._features = [dict(spec) for spec in (specs or [])]
        self.featuresChanged.emit()
        self.redraw()

    @Slot('QVariantList')
    def setDomain(self, domain) -> None:
        """The box the features live in: ``[Lx, Ly]`` or ``[Lx, Ly, Lz]``."""
        values = [float(v) for v in (domain or []) if float(v) > 0]
        if values:
            self._domain = (values + [values[-1], values[-1]])[:3]
            self.domainChanged.emit()
            self.redraw()

    @Slot('QVariantMap')
    def setPotential(self, potential) -> None:
        """The potential to draw underneath, as ``{x_nm, y_nm, V_eV}``.

        Optional: the outlines alone are enough to place features by, and on
        a coarse preview grid the image is the slower half of the redraw.
        """
        self._potential = dict(potential or {})
        self.redraw()

    @Slot('QVariantMap')
    def setDensity(self, density) -> None:
        """A state's |psi|² to contour over the model, or ``{}`` for none."""
        self._density = dict(density or {})
        self.redraw()

    # ── drawing ──────────────────────────────────────────────────────────

    def _axes(self):
        return self.figure.axes[0] if self.figure.axes else None

    def _shown_axes(self):
        """Which two of the model's axes the current projection shows."""
        return self.PROJECTIONS.get(self._projection, (0, 1))

    def _render(self) -> None:
        # Rebuilt on every render rather than kept: the figure is cheap at
        # this size, and a stale axes is how a drag ends up mapping to the
        # wrong data coordinates after a resize.
        self.figure.clf()
        ax = self.figure.add_subplot(111)
        axes = self._shown_axes()

        self._draw_potential(ax)
        self._draw_density(ax)
        for index, spec in enumerate(self._features):
            self._draw_feature(ax, index, spec, axes)
        if 0 <= self._selected < len(self._features):
            self._draw_handles(ax, self._features[self._selected], axes)

        labels = self.AXIS_LABELS.get(self._projection, ("x (nm)", "y (nm)"))
        ax.set_xlabel(labels[0])
        ax.set_ylabel(labels[1])
        ax.set_xlim(0, self._domain[axes[0]])
        ax.set_ylim(0, self._domain[axes[1]])
        ax.set_aspect('equal', adjustable='box')
        ax.set_facecolor(self._background)
        for spine in ax.spines.values():
            spine.set_color(self._grid)
        ax.tick_params(colors=self._foreground, labelsize=7)
        ax.xaxis.label.set_color(self._foreground)
        ax.yaxis.label.set_color(self._foreground)
        self.figure.tight_layout(pad=0.6)

        super()._render()

    def _draw_potential(self, ax) -> None:
        x = self._potential.get('x_nm')
        y = self._potential.get('y_nm')
        values = self._potential.get('V_eV')
        if not x or not y or not values:
            return
        grid = np.asarray(values, dtype=float)
        if grid.ndim != 2:
            return
        # Transposed because the potential is built as (x, y) and pcolormesh
        # wants (row, column) = (y, x). Getting this wrong mirrors the model
        # about its diagonal, which looks like a placement bug.
        ax.pcolormesh(np.asarray(x, dtype=float), np.asarray(y, dtype=float),
                      grid.T, cmap="viridis", shading="auto", alpha=0.85)

    def _draw_density(self, ax) -> None:
        x = self._density.get('x_nm')
        y = self._density.get('y_nm')
        values = self._density.get('values')
        if not x or not y or not values:
            return
        grid = np.asarray(values, dtype=float)
        if grid.ndim != 2 or not np.any(grid):
            return
        ax.contour(np.asarray(x, dtype=float), np.asarray(y, dtype=float),
                   grid.T, levels=6, colors=self.SELECTED_COLOUR,
                   linewidths=0.8, alpha=0.9)

    def _draw_feature(self, ax, index: int, spec: dict, axes) -> None:
        from matplotlib.patches import Circle, Ellipse, Rectangle, Wedge

        colour = (self.SELECTED_COLOUR if index == self._selected
                  else self.FEATURE_COLOURS[index % len(self.FEATURE_COLOURS)])
        selected = index == self._selected
        centre = spec_position(spec, axes)
        half = spec_extent(spec, axes)
        kind = str(spec.get('kind', ''))
        style = dict(facecolor=colour, edgecolor=self._foreground,
                     alpha=0.55 if selected else 0.35,
                     linewidth=2.0 if selected else 1.0)

        if kind in ('circle', 'sphere') and axes != (0, 1) or kind == 'circle':
            patch = Circle(centre, half[0], **style)
        elif kind == 'wedge' and axes == (0, 1):
            patch = Wedge(centre, float(spec.get('r_outer', 1.0)),
                          float(spec.get('theta_start', 0.0)),
                          float(spec.get('theta_start', 0.0))
                          + float(spec.get('theta_span', 90.0)),
                          width=(float(spec.get('r_outer', 1.0))
                                 - float(spec.get('r_inner', 0.0))), **style)
        elif kind in ('gaussian_2d', 'gaussian_3d'):
            # No edge to draw, so 3σ — the same place `contains` stops.
            patch = Ellipse(centre, 2 * half[0], 2 * half[1],
                            linestyle="--", **style)
        elif kind == 'sphere':
            patch = Circle(centre, half[0], **style)
        elif kind in ('cylinder', 'cone', 'lens') and axes == (0, 1):
            patch = Circle(centre, half[0], **style)
        else:
            # Everything else reads as its bounding rectangle in this plane —
            # a box, a prism seen from the side, a cylinder in XZ.
            patch = Rectangle((centre[0] - half[0], centre[1] - half[1]),
                              2 * half[0], 2 * half[1], **style)
        ax.add_patch(patch)

        ax.annotate(f"F{index}", centre, color=self._foreground, fontsize=7,
                    ha="center", va="center")

    def _draw_handles(self, ax, spec: dict, axes) -> None:
        """Corner markers on the selected feature, for resizing."""
        centre = spec_position(spec, axes)
        half = spec_extent(spec, axes)
        if half[0] <= 0 and half[1] <= 0:
            return
        corners = [(centre[0] + half[0], centre[1] + half[1])]
        ax.plot([c[0] for c in corners], [c[1] for c in corners], "s",
                color=self.SELECTED_COLOUR, markeredgecolor="#000000",
                markersize=6, zorder=5)

    # ── the mouse ────────────────────────────────────────────────────────

    def _hit(self, x: float, y: float):
        """What is under the point: ``('handle'|'feature', index)`` or None.

        Handles first, and features from the top down — the one drawn last is
        the one on top, and picking the one underneath is the classic way an
        editor feels broken.
        """
        ax = self._axes()
        data = self.data_at(x, y, ax)
        if data is None:
            return None
        axes = self._shown_axes()

        if 0 <= self._selected < len(self._features):
            spec = self._features[self._selected]
            centre = spec_position(spec, axes)
            half = spec_extent(spec, axes)
            corner = self.item_at(centre[0] + half[0], centre[1] + half[1], ax)
            if corner is not None:
                if (abs(corner[0] - x) <= self.HANDLE_GRAB_PX
                        and abs(corner[1] - y) <= self.HANDLE_GRAB_PX):
                    return ('handle', self._selected)

        for index in range(len(self._features) - 1, -1, -1):
            spec = self._features[index]
            centre = spec_position(spec, axes)
            half = spec_extent(spec, axes)
            if (abs(data[0] - centre[0]) <= max(half[0], 1e-9)
                    and abs(data[1] - centre[1]) <= max(half[1], 1e-9)):
                return ('feature', index)
        return None

    def mousePressEvent(self, event) -> None:
        x, y = event.position().x(), event.position().y()
        hit = self._hit(x, y)
        data = self.data_at(x, y)

        if hit is None:
            self._drag = None
            if self._selected != -1:
                self._set_selected(-1)
            self.featureSelected.emit(-1)
            event.accept()
            return

        what, index = hit
        if index != self._selected:
            self._set_selected(index)
            self.featureSelected.emit(index)

        axes = self._shown_axes()
        centre = spec_position(self._features[index], axes)
        self._drag = {'what': what, 'index': index,
                      'grab': data,
                      'offset': (centre[0] - data[0], centre[1] - data[1])
                      if data else (0.0, 0.0)}
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._drag:
            event.ignore()
            return
        data = self.data_at(event.position().x(), event.position().y())
        if data is None:
            event.accept()
            return

        index = self._drag['index']
        if self._drag['what'] == 'feature':
            offset = self._drag['offset']
            self.featureMoved.emit(index, data[0] + offset[0],
                                   data[1] + offset[1])
        else:
            centre = spec_position(self._features[index], self._shown_axes())
            # A handle sets the half-size directly: it is dragged to where the
            # corner should be, so the distance from the centre IS the answer.
            self.featureResized.emit(index, abs(data[0] - centre[0]),
                                     abs(data[1] - centre[1]))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        x, y = event.position().x(), event.position().y()
        if self._hit(x, y) is not None:
            event.accept()
            return
        data = self.data_at(x, y)
        if data is not None:
            self.featureAdded.emit(data[0], data[1])
        event.accept()
