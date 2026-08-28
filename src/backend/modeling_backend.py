"""
The Modeling workstation's backend: a model, and what it solves to.

A model here is a box and a list of features in it. This owns that list —
adding, moving, resizing, removing — builds the potential it describes, and
runs the solver over it. The canvas draws; the panels edit; nothing but this
holds the state, so a drag on the canvas and a number typed in a field are
the same edit arriving by different routes.

Solving goes to the worker. A 2-D grid is a fraction of a second and a 3-D
one is seconds to minutes — the cost is the grid **cubed** — so it is never
run on the GUI thread, and the count is reported before it starts.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
License: GPL
"""

from __future__ import annotations

import inspect
import json
import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
from PySide6.QtCore import Property, QObject, Signal, Slot

from src.physics import feature_specs as specs
from src.physics.features import build_potential_from_features
from src.physics.solvers import (MAX_STATES, density, grid_axis, solve_well_2d,
                                 solve_well_3d)

logger = logging.getLogger(__name__)


class ModelingBackend(QObject):
    """One model: a box, the features in it, and the states they hold."""

    #: A grid this big is refused rather than attempted. 3-D cost is the
    #: product of the three counts, and a mistyped zero turns a two-second
    #: solve into one that never finishes and cannot be cancelled cleanly.
    MAX_GRID_POINTS = 400_000

    #: Points per axis for the potential the canvas draws underneath. Coarse
    #: on purpose: it is a picture to place features against, redrawn on
    #: every drag, not the grid anything is solved on.
    #: Samples across a preview when the caller does not say. The canvas
    #: normally does say — it sizes the grid from its own pixels, because a
    #: fixed 120 stretched over a 900-pixel plot is one sample per seven and
    #: a half of them, and no amount of smoothing at the edges hides that.
    PREVIEW_POINTS = 240
    #: Sub-samples per cell per axis when building a potential. A round
    #: feature on a square grid is otherwise a staircase of whole cells:
    #: the preview draws it as blocks, and the energies jump as it is
    #: dragged — 2.7 meV across one cell at 80x80, against 0.5 meV here.
    #:
    #: The cost is (points x subsample) squared, so the two trade against
    #: each other — and points wins that trade, because it buys detail
    #: everywhere while sub-sampling only softens the boundary. Measured on
    #: four features: 120 points at 3 costs 9.9 ms, 240 at 2 costs 8.3 ms
    #: for twice the resolution. The solve pays this cubed in 3-D, which is
    #: why it takes less.
    PREVIEW_SUBSAMPLE = 2
    SOLVE_SUBSAMPLE_2D = 3
    SOLVE_SUBSAMPLE_3D = 2

    #: What counts as "the state is here" in the point cloud, as a fraction of
    #: its own maximum. The old app's number, kept so the same model draws the
    #: same cloud in both.
    SCATTER_THRESHOLD = 0.05
    #: How many of those points may cross the bridge. The old app drew them at
    #: s=2 and alpha=0.4, where a couple of thousand already read as solid — a
    #: 60³ solve can put 200 000 over the threshold, which is a long
    #: QVariantMap conversion for a picture that is no more informative.
    MAX_SCATTER_POINTS = 8_000

    #: Which grids a model can be solved on, by mode. The spelling is
    #: :mod:`~src.physics.solution_spec`'s, so the designer and the solvers
    #: name a shape the same way.
    COORDS_2D = ('cartesian', 'circular')
    COORDS_3D = ('cartesian', 'cylindrical', 'spherical')
    COORD_LABELS = {'cartesian': "Cartesian (x, y, z)",
                    'circular': "Polar (r, θ)",
                    'cylindrical': "Cylindrical (r, θ, z)",
                    'spherical': "Spherical (r, θ, φ)"}
    #: What each of the three counts means per system. Nx is a radius in a
    #: polar grid, and a panel that says otherwise is asking the user to set a
    #: grid they cannot see.
    COORD_AXIS_LABELS = {'cartesian': ("Nx", "Ny", "Nz"),
                         'circular': ("Nr", "Nθ"),
                         'cylindrical': ("Nr", "Nθ", "Nz"),
                         'spherical': ("Nr", "Nθ", "Nφ")}

    featuresChanged = Signal()
    selectedIndexChanged = Signal()
    domainChanged = Signal()
    modeChanged = Signal()
    statusChanged = Signal(str)
    #: Everything one solve produced, as plain numbers.
    solveCompleted = Signal('QVariantMap')
    solveStarted = Signal()
    #: The last solve no longer describes the model — a new mode, a cleared
    #: model, a loaded one. Without it the level list, the state selection
    #: and the states view keep advertising a result that has been thrown
    #: away, and clicking one of those levels does nothing.
    resultCleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._app_backend = None
        self._features: List[dict] = []
        self._selected = -1
        self._domain = [20.0, 20.0, 20.0]
        self._mode = "2d"
        self._status = "Ready"
        self._result: dict = {}

    def set_app_backend(self, app_backend) -> None:
        """Injected at startup — this is where the worker comes from."""
        self._app_backend = app_backend

    # ── the model ────────────────────────────────────────────────────────

    def _get_mode(self):
        return self._mode

    def _set_mode(self, value):
        value = str(value or "2d").lower()
        if value in ("2d", "3d") and value != self._mode:
            self._mode = value
            # A 2-D feature has no meaning in a 3-D box and vice versa, so
            # switching starts a new model rather than carrying nonsense over.
            self._features = []
            self._selected = -1
            self._result = {}
            self.modeChanged.emit()
            self.resultCleared.emit()
            self.featuresChanged.emit()
            self.selectedIndexChanged.emit()

    mode = Property(str, _get_mode, _set_mode, notify=modeChanged)

    def _get_selected(self):
        return self._selected

    def _set_selected(self, index):
        index = int(index)
        if index != self._selected:
            self._selected = index
            self.selectedIndexChanged.emit()

    selectedIndex = Property(int, _get_selected, _set_selected,
                             notify=selectedIndexChanged)

    def _get_status(self):
        return self._status

    status = Property(str, _get_status, notify=statusChanged)

    def _set_status(self, message: str) -> None:
        self._status = str(message)
        self.statusChanged.emit(self._status)

    @Slot(result='QVariantList')
    def getFeatures(self):
        return [dict(spec) for spec in self._features]

    @Slot(result='QVariantList')
    def getDomain(self):
        return list(self._domain)

    @Slot(float, float, float)
    def setDomain(self, Lx: float, Ly: float, Lz: float) -> None:
        domain = [max(0.1, float(Lx)), max(0.1, float(Ly)), max(0.1, float(Lz))]
        if domain != self._domain:
            self._domain = domain
            self.domainChanged.emit()

    @Slot(result='QVariantList')
    def availableKinds(self):
        """The shapes this model can hold, as ``{key, label}`` maps."""
        kinds = specs.KINDS_3D if self._mode == "3d" else specs.KINDS_2D
        return [{'key': kind, 'label': specs.KIND_LABELS.get(kind, kind)}
                for kind in kinds]

    @Slot(str, result='QVariantList')
    def fieldsFor(self, kind: str):
        """What a form should show for a kind: ``{name, label}`` in order."""
        try:
            names = specs.field_names(str(kind))
        except ValueError:
            return []
        return [{'name': name, 'label': specs.FIELD_LABELS.get(name, name)}
                for name in names]

    # ── editing ──────────────────────────────────────────────────────────

    @Slot(str, float, float, result=int)
    @Slot(str, float, float, str, result=int)
    def addFeature(self, kind: str, u: float = 0.0, v: float = 0.0,
                   projection: str = "xy") -> int:
        """Add a feature of ``kind``, centred where the user clicked.

        The click names two coordinates and the plane says which two — in XZ
        the second one is z, not y. The axis the plane hides lands in the
        middle of the box, the only place it can go that is not a guess about
        what the user meant. Taking the pair as x and y whatever the view, as
        this did, put every feature added from an XZ or YZ view somewhere the
        user could not see it.
        """
        kind = str(kind)
        allowed = specs.KINDS_3D if self._mode == "3d" else specs.KINDS_2D
        if kind not in allowed:
            self._set_status(f"{kind} is not a {self._mode.upper()} shape")
            return -1

        axes = self._axes_for(projection)
        position = [self._domain[i] / 2.0 for i in range(3)]
        position[axes[0]], position[axes[1]] = float(u), float(v)
        spec = specs.default_spec(kind, position=position)
        self._features.append(spec)
        self._selected = len(self._features) - 1
        self.featuresChanged.emit()
        self.selectedIndexChanged.emit()
        self._set_status(f"Added {specs.KIND_LABELS.get(kind, kind)}")
        return self._selected

    @Slot(int, 'QVariantMap')
    def updateFeature(self, index: int, values) -> None:
        """Write edited fields onto a feature, ignoring anything unknown."""
        index = int(index)
        if not 0 <= index < len(self._features):
            return
        spec = dict(self._features[index])
        editable = set(specs.field_names(spec['kind']))
        for name, value in dict(values or {}).items():
            if name not in editable:
                continue
            spec[name] = (int(value) if name == 'n_sides' else float(value))
        self._features[index] = spec
        self.featuresChanged.emit()

    @Slot(int, float, float, str)
    def moveFeature(self, index: int, u: float, v: float,
                    projection: str = "xy") -> None:
        """Put a feature's centre at ``(u, v)`` in the plane being shown."""
        index = int(index)
        if not 0 <= index < len(self._features):
            return
        axes = self._axes_for(projection)
        self._features[index] = specs.move_spec(self._features[index],
                                                (float(u), float(v)), axes)
        self.featuresChanged.emit()

    @Slot(int, float, float, str)
    def resizeFeature(self, index: int, du: float, dv: float,
                      projection: str = "xy") -> None:
        """Set a feature's half-size on the two axes being shown.

        Which fields that writes depends on the shape: a circle has one
        radius however it is dragged, a box has a size per axis.
        """
        index = int(index)
        if not 0 <= index < len(self._features):
            return
        spec = dict(self._features[index])
        kind = spec.get('kind', '')
        axes = self._axes_for(projection)
        du, dv = max(1e-3, abs(float(du))), max(1e-3, abs(float(dv)))

        if kind in ('circle', 'sphere'):
            spec['r' if kind == 'circle' else 'R'] = max(du, dv)
        elif kind in ('cylinder', 'cone', 'lens'):
            if axes == (0, 1):
                spec['R'] = max(du, dv)
            else:
                spec['R'], spec['H'] = du, 2 * dv
        elif kind in ('pyramid', 'prism'):
            # `base` is the polygon's diameter, not its circumradius — the
            # feature's own contains() uses base/2 — so a half-extent from
            # the handle has to be doubled going in.
            if axes == (0, 1):
                spec['base'] = 2 * max(du, dv)
            else:
                spec['base'], spec['H'] = 2 * du, 2 * dv
        elif kind == 'ellipse':
            spec['a'], spec['b'] = du, dv
        elif kind == 'wedge':
            spec['r_outer'] = max(du, dv)
        elif kind in ('gaussian_2d', 'gaussian_3d'):
            sizes = ('sx', 'sy', 'sz')
            spec[sizes[axes[0]]] = du / 3.0
            spec[sizes[axes[1]]] = dv / 3.0
        elif kind == 'triangle':
            # Centre-anchored, unlike rect, whose cx is derived from a corner
            # — so this one needs no move afterwards to hold it still.
            spec['w'], spec['h'] = 2 * du, 2 * dv
        elif kind == 'rect':
            centre = specs.spec_position(spec, (0, 1))
            spec['w'], spec['h'] = 2 * du, 2 * dv
            spec = specs.move_spec(spec, centre, (0, 1))
        elif kind == 'box':
            sizes = ('Lx', 'Ly', 'Lz')
            spec[sizes[axes[0]]] = 2 * du
            spec[sizes[axes[1]]] = 2 * dv
        else:
            return

        self._features[index] = spec
        self.featuresChanged.emit()

    @Slot(int)
    def removeFeature(self, index: int) -> None:
        index = int(index)
        if not 0 <= index < len(self._features):
            return
        self._features.pop(index)
        self._selected = min(self._selected, len(self._features) - 1)
        self.featuresChanged.emit()
        self.selectedIndexChanged.emit()

    @Slot(int, result=int)
    def duplicateFeature(self, index: int) -> int:
        """Copy a feature, offset so the copy is visible rather than hidden
        exactly underneath the original."""
        index = int(index)
        if not 0 <= index < len(self._features):
            return -1
        spec = dict(self._features[index])
        centre = specs.spec_position(spec, (0, 1))
        half = specs.spec_extent(spec, (0, 1))
        spec = specs.move_spec(spec, (centre[0] + max(half[0], 1.0),
                                      centre[1] + max(half[1], 1.0)), (0, 1))
        self._features.append(spec)
        self._selected = len(self._features) - 1
        self.featuresChanged.emit()
        self.selectedIndexChanged.emit()
        return self._selected

    @Slot()
    def clearFeatures(self) -> None:
        self._features = []
        self._selected = -1
        self._result = {}
        self.resultCleared.emit()
        self.featuresChanged.emit()
        self.selectedIndexChanged.emit()

    @staticmethod
    def _axes_for(projection: str):
        return {'xy': (0, 1), 'xz': (0, 2), 'yz': (1, 2)}.get(
            str(projection).lower(), (0, 1))

    # ── the potential, for the canvas ────────────────────────────────────

    @Slot(str, float, result='QVariantMap')
    @Slot(str, float, int, result='QVariantMap')
    def previewPotential(self, projection: str = "xy",
                         slice_at: float = -1.0, points: int = 0):
        """The potential in the plane being shown, on a coarse grid.

        A 3-D model is cut through ``slice_at`` on the hidden axis (the
        middle of the box when that is negative), because a projection cannot
        show a volume and averaging through it would hide exactly the
        structure a user is placing.
        """
        try:
            axes = self._axes_for(projection)
            features = specs.build_features(self._features)
            # The canvas asks for the resolution its own plot can show; the
            # default is for callers that have no plot, like a test.
            n = int(points) if int(points) > 0 else self.PREVIEW_POINTS
            n = int(np.clip(n, 32, 512))

            if self._mode == "2d":
                x, _dx = grid_axis(self._domain[0], n, "neumann")
                y, _dy = grid_axis(self._domain[1], n, "neumann")
                V, _ = build_potential_from_features(
                    features, (x, y), 0.0, self.PREVIEW_SUBSAMPLE)
                return {'x_nm': x.tolist(), 'y_nm': y.tolist(),
                        'V_eV': (V / 1.602176634e-19).tolist()}

            # 3-D: one plane of a coarse volume. The hidden axis is handed
            # over as the single sample the slice sits on — only one of its
            # slices is ever looked at, and cutting first is also what keeps
            # the sub-sampling in the plane rather than averaging through it.
            hidden = ({0, 1, 2} - set(axes)).pop()
            # Onto the solved axis when there is one. The density drawn over
            # this comes off the solver's own grid, so a preview cut anywhere
            # else is a potential and a |psi|² from two different planes with
            # one title over them — up to half a solver cell apart, which on
            # a small box is a fifth of it. The request goes through the same
            # index rule the density uses, negative "middle of the axis"
            # included, so the two land on the same sample and not merely
            # near one. Unsolved there is nothing to agree with, and the cut
            # is taken exactly where it was asked for.
            solved = self._solved_axis(hidden)
            if solved is not None:
                position = float(solved[self._slice_index(solved, slice_at)])
            else:
                position = (self._domain[hidden] / 2.0 if slice_at < 0
                            else float(slice_at))
                position = float(np.clip(position, 0.0,
                                         self._domain[hidden]))
            cut = [None, None, None]
            for i in axes:
                cut[i] = grid_axis(self._domain[i], n, "neumann")[0]
            cut[hidden] = np.array([position])
            V, _ = build_potential_from_features(
                features, tuple(cut), 0.0, self.PREVIEW_SUBSAMPLE)
            plane = np.take(V, 0, axis=hidden)
            if axes[0] > axes[1]:
                plane = plane.T
            return {'x_nm': cut[axes[0]].tolist(),
                    'y_nm': cut[axes[1]].tolist(),
                    'V_eV': (plane / 1.602176634e-19).tolist(),
                    'slice_at': position}
        except Exception as exc:
            logger.error("Potential preview failed: %s", exc, exc_info=True)
            return {}

    # ── curved grids, read back as pictures ──────────────────────────────
    #
    # A polar, cylindrical or spherical solve answers on its own grid — r and
    # angles, with the Cartesian node positions alongside — and the canvas
    # draws planes with two straight axes. Both slots below therefore read a
    # curved answer at Cartesian positions rather than handing the native
    # arrays over. It is a display step and nothing else: the physics stays on
    # the grid it was solved on, and a Cartesian solve never comes through
    # here at all.

    #: How many samples across a resampled plane. A curved grid has no
    #: Cartesian axis to inherit, so the picture's resolution is chosen here;
    #: 96² is a plane the canvas can show without inventing detail the solve
    #: does not have.
    CURVED_DISPLAY_POINTS = 96

    def _display_axes(self, points: int = 0):
        """The Cartesian axes a resampled picture is drawn on."""
        n = int(points) if int(points) > 0 else self.CURVED_DISPLAY_POINTS
        return [grid_axis(self._domain[i], n, "neumann")[0]
                for i in range(3)]

    @staticmethod
    def _pad_wall(axis, values, index: int, both: bool = False):
        """Add the Dirichlet wall the grid stops half a cell short of.

        The curved grids are cell-centred, so the outermost node sits half a
        step inside the rim. Interpolating only as far as that node and
        filling zero beyond it paints the last half-cell with the node's own
        value — a bright ring around the disc, or a bright cap on the ball,
        that is not in the answer. Padding with an explicit zero at the wall
        lets the interpolation run down to it instead. ``both`` is for an
        axis walled at each end, which the cylinder's z is and the radius,
        open at r = 0, is not.
        """
        step = (axis[1] - axis[0]) if len(axis) > 1 else axis[0] * 2.0
        zeros = np.zeros_like(np.take(values, [0], axis=index))
        axis = np.concatenate([axis, [axis[-1] + step / 2.0]])
        values = np.concatenate([values, zeros], axis=index)
        if both:
            axis = np.concatenate([[axis[0] - step / 2.0], axis])
            values = np.concatenate([zeros, values], axis=index)
        return axis, values

    @staticmethod
    def _wrap_angle(axis, values, index: int):
        """Repeat a periodic angular axis at both ends.

        theta runs over cell centres, so it covers neither 0 nor 2π and a
        query anywhere in the first or last half-cell would fall outside it.
        One copy of each end wall, a period away, closes the seam.
        """
        period = 2.0 * np.pi
        ext = np.concatenate([[axis[-1] - period], axis, [axis[0] + period]])
        lo = np.take(values, [-1], axis=index)
        hi = np.take(values, [0], axis=index)
        return ext, np.concatenate([lo, values, hi], axis=index)

    def _curved_sample(self, field, points):
        """Read a field solved on a curved grid at Cartesian ``points``.

        ``points`` are broadcast arrays in nm — (X, Y) for a 2-D solve, and
        (X, Y, Z) for a 3-D one. Anything outside the solved shape comes back
        as zero, which is what a Dirichlet wall means.
        """
        from scipy.interpolate import RegularGridInterpolator

        system = self._result.get('coords', 'cartesian')
        values = np.asarray(field, dtype=float)
        # The backend always centres a curved grid on the box's centre, which
        # is what solve_well_2d/3d pass through as ``centre_nm``.
        centre = [d / 2.0 for d in self._domain]
        dx = np.asarray(points[0], dtype=float) - centre[0]
        dy = np.asarray(points[1], dtype=float) - centre[1]

        r = np.asarray(self._result['r_nm'], dtype=float)
        theta = np.asarray(self._result['theta_rad'], dtype=float)
        r_ax, values = self._pad_wall(r, values, 0)

        if system == 'polar':
            th_ax, values = self._wrap_angle(theta, values, 1)
            axes = (r_ax, th_ax)
            query = (np.hypot(dx, dy),
                     np.mod(np.arctan2(dy, dx), 2.0 * np.pi))
        elif system == 'cylindrical':
            dz = np.asarray(points[2], dtype=float) - centre[2]
            th_ax, values = self._wrap_angle(theta, values, 1)
            # The cylinder's z is walled at both ends, unlike the radius.
            z_ax, values = self._pad_wall(
                np.asarray(self._result['z_nm'], dtype=float), values, 2,
                both=True)
            axes = (r_ax, th_ax, z_ax)
            query = (np.hypot(dx, dy),
                     np.mod(np.arctan2(dy, dx), 2.0 * np.pi), dz)
        else:
            dz = np.asarray(points[2], dtype=float) - centre[2]
            phi = np.asarray(self._result['phi_rad'], dtype=float)
            # The poles sit half a cell outside the theta grid. They are real
            # points of the ball, so they take the mean around the axis there
            # rather than being left to fill as though they were outside it.
            caps = [np.repeat(np.take(values, [i], axis=1).mean(
                        axis=2, keepdims=True), values.shape[2], axis=2)
                    for i in (0, -1)]
            th_ax = np.concatenate([[0.0], theta, [np.pi]])
            values = np.concatenate([caps[0], values, caps[1]], axis=1)
            ph_ax, values = self._wrap_angle(phi, values, 2)
            axes = (r_ax, th_ax, ph_ax)
            radius = np.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
            safe = np.maximum(radius, 1e-12)
            query = (radius, np.arccos(np.clip(dz / safe, -1.0, 1.0)),
                     np.mod(np.arctan2(dy, dx), 2.0 * np.pi))

        # Only the radius is clamped, and only at the bottom: the innermost
        # half-cell is a hole the grid never samples, while everything past
        # the rim is genuinely outside the shape and fills with zero.
        query = list(query)
        query[0] = np.maximum(query[0], r_ax[0])
        stacked = np.stack(np.broadcast_arrays(*query), axis=-1)
        return RegularGridInterpolator(axes, values, bounds_error=False,
                                       fill_value=0.0)(stacked)

    def _curved_density(self, grid, axes, slice_at: float) -> dict:
        """One plane of a curved solve, resampled onto the display grid."""
        display = self._display_axes()
        if grid.ndim == 2:
            # A disc has no third axis to cut along: the whole plane is the
            # answer, so slice_at has nothing to say about it.
            mesh = np.meshgrid(display[0], display[1], indexing='ij')
            return {'x_nm': display[0].tolist(), 'y_nm': display[1].tolist(),
                    'values': self._curved_sample(grid, mesh).tolist()}

        hidden = ({0, 1, 2} - set(axes)).pop()
        index = self._slice_index(display[hidden], slice_at)
        position = float(display[hidden][index])
        points = [None, None, None]
        points[axes[0]], points[axes[1]] = np.meshgrid(
            display[axes[0]], display[axes[1]], indexing='ij')
        points[hidden] = position
        return {'x_nm': display[axes[0]].tolist(),
                'y_nm': display[axes[1]].tolist(),
                'values': self._curved_sample(grid, points).tolist(),
                'slice_at': position}

    @Slot(int, str, float, result='QVariantMap')
    def densityFor(self, state_index: int, projection: str = "xy",
                   slice_at: float = -1.0):
        """|psi|² of one solved state, in the plane being shown."""
        if not self._result.get('ok'):
            return {}
        try:
            psi = self._result['psi']
            shape = tuple(self._result['shape'])
            grid = density(psi, shape, int(state_index))
            axes = self._axes_for(projection)

            if self._result.get('coords', 'cartesian') != 'cartesian':
                return self._curved_density(grid, axes, slice_at)

            if len(shape) == 2:
                # tolist() on the axes too: the solver hands back numpy
                # arrays, and one that crosses into QML arrives at the canvas
                # as an array rather than a list — where `if not x` raises
                # instead of answering, inside paint(), on every frame.
                return {'x_nm': np.asarray(self._result['x_nm']).tolist(),
                        'y_nm': np.asarray(self._result['y_nm']).tolist(),
                        'values': grid.tolist()}

            grids = [self._result['x_nm'], self._result['y_nm'],
                     self._result['z_nm']]
            hidden = ({0, 1, 2} - set(axes)).pop()
            axis_values = np.asarray(grids[hidden])
            index = self._slice_index(axis_values, slice_at)
            plane = np.take(grid, index, axis=hidden)
            if axes[0] > axes[1]:
                plane = plane.T
            # Where the cut actually landed, not where it was asked for: the
            # request is snapped to a grid line, and a slider that reports the
            # number it sent rather than the plane on screen drifts away from
            # it by up to half a step. previewPotential already answers this.
            return {'x_nm': np.asarray(grids[axes[0]]).tolist(),
                    'y_nm': np.asarray(grids[axes[1]]).tolist(),
                    'values': plane.tolist(),
                    'slice_at': float(axis_values[index])}
        except Exception as exc:
            logger.error("Density slice failed: %s", exc, exc_info=True)
            return {}

    def _solved_axis(self, axis: int):
        """The grid the density is cut on along one axis, or None when there
        is nothing to agree with — nothing solved yet, or a 2-D model.

        A curved solve has no separable x/y/z, so what it is cut on is the
        display grid its planes are resampled onto; that is the one the
        preview has to match.
        """
        if not self._result.get('ok') or len(self._result.get('shape', ())) != 3:
            return None
        if self._result.get('coords', 'cartesian') != 'cartesian':
            return self._display_axes()[axis]
        key = ('x_nm', 'y_nm', 'z_nm')[axis]
        if key not in self._result:
            return None
        return np.asarray(self._result[key], dtype=float)

    @staticmethod
    def _slice_index(axis_values, position: float) -> int:
        """Which sample on an axis a cut lands on.

        Negative means the middle of that axis — the convention every slicing
        call here answers to, so a caller with no opinion about where to cut
        does not have to invent one.
        """
        axis_values = np.asarray(axis_values, dtype=float)
        if position < 0:
            return len(axis_values) // 2
        return int(np.argmin(np.abs(axis_values - float(position))))

    @Slot(int, result='QVariantMap')
    @Slot(int, float, float, float, result='QVariantMap')
    def statePlots(self, state_index: int, slice_x: float = -1.0,
                   slice_y: float = -1.0, slice_z: float = -1.0):
        """One 3-D state as the four pictures that describe it.

        Three orthogonal cuts through |psi|² and a point cloud of where the
        state actually is. The old app steered only two of the cuts — its YZ
        panel was hardcoded to the middle of x, which is why it carried two
        sliders for three planes — and all three are steerable here.

        Small data only. The grid itself never crosses the bridge: a 60³ state
        is 216 000 numbers per cut if you send the volume, against a few
        thousand for the plane anyone is looking at.
        """
        if not self._result.get('ok'):
            return {'ok': False, 'error': "Solve the model first."}
        shape = tuple(self._result.get('shape', ()))
        if len(shape) != 3:
            return {'ok': False,
                    'error': "The state view draws a volume — this model is "
                             f"{len(shape)}-D."}
        energies = np.asarray(self._result['E_eV'], dtype=float)
        index = int(state_index)
        if not 0 <= index < len(energies):
            return {'ok': False,
                    'error': f"State {index} is not one of the "
                             f"{len(energies)} that were solved."}
        try:
            prob = density(self._result['psi'], shape, index)
            # The old app's normalisation, kept term for term: max to 1, with
            # the epsilon there so a column of zeros divides by something.
            prob = prob / (prob.max() + 1e-30)

            # A curved solve has no x/y/z of its own — its answer lives on
            # r and angles — so the pictures are drawn on a Cartesian grid of
            # this backend's choosing and read off the curved one.
            curved = self._result.get('coords', 'cartesian') != 'cartesian'
            if curved:
                x, y, z = self._display_axes()
            else:
                x = np.asarray(self._result['x_nm'], dtype=float)
                y = np.asarray(self._result['y_nm'], dtype=float)
                z = np.asarray(self._result['z_nm'], dtype=float)
            ix = self._slice_index(x, slice_x)
            iy = self._slice_index(y, slice_y)
            iz = self._slice_index(z, slice_z)

            def cut(pair, hidden, position):
                if not curved:
                    return np.take(prob, {2: iz, 1: iy, 0: ix}[hidden],
                                   axis=hidden)
                points = [None, None, None]
                points[pair[0]], points[pair[1]] = np.meshgrid(
                    (x, y, z)[pair[0]], (x, y, z)[pair[1]], indexing='ij')
                points[hidden] = position
                return self._curved_sample(prob, points)

            # Every array is listed, axes included: a numpy array that crosses
            # into QML arrives as an array rather than a list, and `if not x`
            # on one raises inside paint() on every frame.
            return {
                'ok': True, 'error': '',
                'state': index, 'E_eV': float(energies[index]),
                'x_nm': x.tolist(), 'y_nm': y.tolist(), 'z_nm': z.tolist(),
                'xy': {'values': cut((0, 1), 2, float(z[iz])).tolist(),
                       'slice_at': float(z[iz])},
                'xz': {'values': cut((0, 2), 1, float(y[iy])).tolist(),
                       'slice_at': float(y[iy])},
                'yz': {'values': cut((1, 2), 0, float(x[ix])).tolist(),
                       'slice_at': float(x[ix])},
                'scatter': self._scatter_cloud(prob, x, y, z),
                # The features come along so the view can outline them over
                # the state — a lobe is only interesting next to the well it
                # is or is not sitting in.
                'features': [dict(spec) for spec in self._features],
            }
        except Exception as exc:
            logger.error("State plots failed: %s", exc, exc_info=True)
            return {'ok': False, 'error': str(exc)}

    def _scatter_cloud(self, prob, x, y, z) -> dict:
        """The state as points, capped so a fine grid cannot flood the bridge.

        Above the cap the **brightest** points are kept rather than a random
        sample: the answer is then the same on every call, so the cloud does
        not shimmer between redraws as though the physics had moved, and what
        gets dropped is the faint rim instead of a thinning of the whole
        state. How many were dropped goes with it, because a state that fills
        the box can put ten times the cap over the threshold and the kept
        brightest tenth of it draws as a compact blob — the opposite answer to
        the one the panel exists to give.
        """
        selected = prob > self.SCATTER_THRESHOLD
        if self._result.get('coords', 'cartesian') != 'cartesian':
            # The curved solvers publish the Cartesian position of every node
            # they solved on, so the cloud needs no resampling at all — and it
            # is the one picture here that shows the grid's own shape.
            px, py, pz = (np.asarray(self._result[key], dtype=float)[selected]
                          for key in ('X_nm', 'Y_nm', 'Z_nm'))
        else:
            ix, iy, iz = np.nonzero(selected)
            px, py, pz = x[ix], y[iy], z[iz]
        values = prob[selected]

        total = int(values.size)
        if total > self.MAX_SCATTER_POINTS:
            keep = np.argsort(values, kind="stable")[::-1]
            keep = np.sort(keep[:self.MAX_SCATTER_POINTS])
            px, py, pz, values = px[keep], py[keep], pz[keep], values[keep]
        return {'x': px.tolist(), 'y': py.tolist(), 'z': pz.tolist(),
                'c': values.tolist(),
                'total': total, 'shown': int(values.size)}

    # ── solving ──────────────────────────────────────────────────────────

    @Slot(result='QVariantList')
    def availableCoords(self):
        """The coordinate systems this mode can be solved in.

        A box is not the only shape a grid can be. A disc solved on a polar
        grid puts samples where the state is instead of squaring off its rim,
        and the same for a cylinder or a sphere — the Laplacians for all three
        have been in :mod:`~src.physics.laplacian` since the port.
        """
        keys = self.COORDS_3D if self._mode == "3d" else self.COORDS_2D
        return [{'key': key,
                 # A plane has no z to name, and a combo that offers one in
                 # 2-D is describing a box the model does not have.
                 'label': ("Cartesian (x, y)"
                           if key == 'cartesian' and self._mode != "3d"
                           else self.COORD_LABELS[key])}
                for key in keys]

    @Slot('QVariantMap', result='QVariantMap')
    def gridCost(self, params):
        """How big the grid is, before anyone waits for it.

        A 3-D solve is the product of three counts, and the difference
        between 24³ and 60³ is seconds against minutes. Saying so up front is
        the difference between a wait and an app that looks hung.

        The count is the same product in a curved grid — the unknowns are
        cells either way — but the axes are not the same axes, so the names
        come back with it. A user coarsening "Ny" is coarsening the angle.
        """
        params = dict(params or {})
        coords = self._coords_for(params)
        counts = self._grid_counts(params)
        points = int(np.prod(counts))
        return {'counts': list(counts), 'points': points,
                'too_big': points > self.MAX_GRID_POINTS,
                'limit': self.MAX_GRID_POINTS,
                'coords': coords,
                'labels': list(self.COORD_AXIS_LABELS[coords][:len(counts)])}

    def _coords_for(self, params) -> str:
        """The requested coordinate system, or Cartesian if it makes no sense
        in this mode. A polar grid is a 2-D idea and a spherical one is not."""
        allowed = self.COORDS_3D if self._mode == "3d" else self.COORDS_2D
        coords = str(params.get('coords', 'cartesian') or 'cartesian').lower()
        return coords if coords in allowed else 'cartesian'

    def _grid_counts(self, params) -> tuple:
        # The counts are read under the curved names too, so a panel that has
        # relabelled its fields Nr/Nθ/Nz does not have to keep sending them
        # under Cartesian keys to be understood.
        def count(cartesian: str, curved: str, floor: int, default: int) -> int:
            value = params.get(curved, params.get(cartesian, default))
            return max(floor, int(value))

        if self._mode == "2d":
            return (count('Nx', 'Nr', 8, 80), count('Ny', 'Ntheta', 8, 80))
        return (count('Nx', 'Nr', 6, 24), count('Ny', 'Ntheta', 6, 24),
                count('Nz', 'Nphi', 6, 24))

    @Slot('QVariantMap')
    def solve(self, params) -> None:
        """Solve the model on the worker, and report when it lands."""
        params = dict(params or {})
        cost = self.gridCost(params)
        if cost['too_big']:
            self._set_status(
                f"{cost['points']:,} grid points is past the "
                f"{self.MAX_GRID_POINTS:,} limit — coarsen the grid.")
            self.solveCompleted.emit({'ok': False, 'error': self._status})
            return

        worker = getattr(self._app_backend, 'worker_manager', None)
        self._set_status(f"Solving on {'×'.join(str(c) for c in cost['counts'])} "
                         f"({cost['points']:,} points)…")
        self.solveStarted.emit()
        if worker is None:                      # tests, or a headless backend
            self._on_solved(self._solve_task(None, params))
            return
        worker.submit(name="Modeling solve", operation=self._solve_task,
                      params=params, on_finished=self._on_solved)

    @staticmethod
    def _coords_kwargs(solver, coords: str) -> dict:
        """``{'coords': …}`` for a solver that takes it, nothing for one that
        doesn't.

        The curved Laplacians reach the solvers through a ``coords=``
        parameter that defaults to Cartesian, so a solver built before it
        exists still runs every Cartesian model unchanged. What must not
        happen is a curved request quietly landing on a Cartesian grid — a
        box's levels under a sphere's label look like a physical result — so
        that case says so instead.
        """
        if coords == 'cartesian':
            return {}
        if 'coords' not in inspect.signature(solver).parameters:
            raise ValueError(
                f"{coords} coordinates need a solver that supports them; "
                "this build solves on a Cartesian grid only.")
        return {'coords': coords}

    def _solve_task(self, task, params) -> dict:
        """The solve itself. Runs on the worker; returns plain numbers plus
        the arrays the canvas needs, which stay Python-side."""
        try:
            features = specs.build_features(self._features)
            n_states = max(1, min(int(params.get('n_states', 6)), MAX_STATES))
            meff = float(params.get('meff', 0.067))
            background = float(params.get('V_background_eV', 0.0))
            bc = str(params.get('bc', 'dirichlet'))
            counts = self._grid_counts(params)
            coords = self._coords_for(params)

            if self._mode == "2d":
                result = solve_well_2d(
                    self._domain[0], self._domain[1], Nx=counts[0],
                    Ny=counts[1], n_states=n_states, meff=meff,
                    features=features, V_background_eV=background, bc=bc,
                    subsample=self.SOLVE_SUBSAMPLE_2D,
                    **self._coords_kwargs(solve_well_2d, coords))
            else:
                result = solve_well_3d(
                    self._domain[0], self._domain[1], self._domain[2],
                    Nx=counts[0], Ny=counts[1], Nz=counts[2],
                    n_states=n_states, meff=meff, features=features,
                    V_background_eV=background, bc=bc,
                    subsample=self.SOLVE_SUBSAMPLE_3D,
                    **self._coords_kwargs(solve_well_3d, coords))
            result['ok'] = True
            result['error'] = ''
            # The solver names the system it actually solved on, canonically
            # — "circular" asked for is "polar" answered — and overwriting
            # that with the request loses the spelling everything reading the
            # result back branches on.
            result.setdefault('coords', coords)
            return result
        except Exception as exc:
            logger.error("Modeling solve failed: %s", exc, exc_info=True)
            return {'ok': False, 'error': str(exc)}

    def _on_solved(self, result) -> None:
        result = result if isinstance(result, dict) else {}
        self._result = result
        if not result.get('ok'):
            self._set_status(result.get('error') or "The solve failed")
            self.solveCompleted.emit({'ok': False,
                                      'error': result.get('error', '')})
            return

        energies = [float(E) for E in result['E_eV']]
        self._set_status(f"{len(energies)} state(s), lowest "
                         f"{energies[0]:.5f} eV")
        # The wavefunctions stay here: a 3-D state is megabytes, and the
        # canvas only ever draws one plane of one of them.
        self.solveCompleted.emit({
            'ok': True,
            'E_eV': energies,
            'shape': list(result['shape']),
            'error': '',
        })

    @Slot(result='QVariantMap')
    def tunneling(self):
        """Which feature each state lives in, and how fast it leaks next door.

        Only meaningful with more than one feature: the rate is computed
        along the line between two features' centres, and a single well has
        nowhere to tunnel to. States that are not localised in any feature
        are reported as such rather than assigned to the nearest one.

        The rates are WKB and span many orders of magnitude, so they are
        reported as they come — a number to compare with another number, not
        one to read absolutely.
        """
        blank = {'ok': False, 'rates': [], 'assignments': [], 'error': ''}
        if not self._result.get('ok'):
            return {**blank, 'error': "Solve the model first."}
        if self._result.get('coords', 'cartesian') != 'cartesian':
            # The WKB integral runs along the straight line between two
            # centres and reads the barrier off a Cartesian grid. A curved
            # answer has none, and resampling one for it would put an
            # interpolation error inside an exponent.
            return {**blank,
                    'error': "Tunnelling is measured on a Cartesian grid — "
                             "this model was solved on a "
                             f"{self._result['coords']} one."}
        features = specs.build_features(self._features)
        if len(features) < 2:
            return {**blank,
                    'error': "Tunnelling needs at least two features — a "
                             "single well has nowhere to leak to."}
        try:
            from scipy.constants import e as _e

            from src.physics.tunneling import compute_tunneling_analysis

            grid = [np.asarray(self._result['x_nm']),
                    np.asarray(self._result['y_nm'])]
            if 'z_nm' in self._result:
                grid.append(np.asarray(self._result['z_nm']))

            rates, overlap, assignments = compute_tunneling_analysis(
                self._result['psi'],
                np.asarray(self._result['E_eV']) * _e,
                np.asarray(self._result['V_eV']) * _e,
                features, tuple(grid))

            listed = [{'from_state': int(i), 'to_state': int(j),
                       'rate_Hz': float(rate),
                       'from_feature': int(assignments[i]),
                       'to_feature': int(assignments[j])}
                      for (i, j), rate in sorted(rates.items(),
                                                 key=lambda kv: -kv[1])]
            # The overlap matrix and the levels come along because the view
            # draws all three together: a rate only means something against
            # the levels it connects, and the matrix is already computed
            # here — it was being thrown away, so the panel for it could
            # never draw. V_min_eV is what says which of those levels are
            # bound at all.
            return {'ok': True, 'rates': listed,
                    'assignments': [int(a) for a in assignments],
                    'unlocalised': sum(1 for a in assignments if a < 0),
                    'overlap': np.abs(np.asarray(overlap)).tolist(),
                    'E_eV': [float(E) for E in self._result['E_eV']],
                    'V_min_eV': float(np.min(self._result['V_eV'])),
                    'error': ''}
        except Exception as exc:
            logger.error("Tunnelling analysis failed: %s", exc, exc_info=True)
            return {**blank, 'error': str(exc)}

    # ── saving ───────────────────────────────────────────────────────────

    @Slot(result=str)
    def toJson(self) -> str:
        """The model as text: the box, the mode, and the features."""
        return json.dumps({'mode': self._mode, 'domain': list(self._domain),
                           'features': self._features}, indent=2)

    @Slot(str, result=bool)
    def fromJson(self, text: str) -> bool:
        """Load a model from text. Returns False rather than raising."""
        try:
            data = json.loads(text)
            mode = str(data.get('mode', '2d')).lower()
            self._mode = mode if mode in ('2d', '3d') else '2d'
            domain = [float(v) for v in data.get('domain', [20.0, 20.0, 20.0])]
            self._domain = (domain + [20.0, 20.0, 20.0])[:3]
            # Only features this mode can hold, and only kinds that exist:
            # a file from another version should load what it can rather than
            # nothing at all.
            allowed = specs.KINDS_3D if self._mode == "3d" else specs.KINDS_2D
            self._features = [dict(spec) for spec in data.get('features', [])
                              if str(spec.get('kind')) in allowed]
            self._selected = -1
            self._result = {}
            self.modeChanged.emit()
            self.resultCleared.emit()
            self.domainChanged.emit()
            self.featuresChanged.emit()
            self.selectedIndexChanged.emit()
            self._set_status(f"Loaded {len(self._features)} feature(s)")
            return True
        except Exception as exc:
            logger.error("Could not load model: %s", exc)
            self._set_status(f"Could not load: {exc}")
            return False

    @Slot(str, result=bool)
    def saveModel(self, file_path: str) -> bool:
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.toJson(), encoding="utf-8")
            self._set_status(f"Saved to {path.name}")
            return True
        except Exception as exc:
            logger.error("Could not save model: %s", exc)
            self._set_status(f"Could not save: {exc}")
            return False

    @Slot(str, result=bool)
    def loadModel(self, file_path: str) -> bool:
        try:
            return self.fromJson(Path(file_path).read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Could not read model: %s", exc)
            self._set_status(f"Could not read: {exc}")
            return False
