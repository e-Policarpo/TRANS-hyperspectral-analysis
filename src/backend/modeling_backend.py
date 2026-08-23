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
    PREVIEW_POINTS = 120

    featuresChanged = Signal()
    selectedIndexChanged = Signal()
    domainChanged = Signal()
    modeChanged = Signal()
    statusChanged = Signal(str)
    #: Everything one solve produced, as plain numbers.
    solveCompleted = Signal('QVariantMap')
    solveStarted = Signal()

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
    def addFeature(self, kind: str, u: float = 0.0, v: float = 0.0) -> int:
        """Add a feature of ``kind``, centred where the user clicked.

        The click is in the plane being shown, so the third coordinate lands
        in the middle of the box — the only place it can go that is not a
        guess about what the user meant.
        """
        kind = str(kind)
        allowed = specs.KINDS_3D if self._mode == "3d" else specs.KINDS_2D
        if kind not in allowed:
            self._set_status(f"{kind} is not a {self._mode.upper()} shape")
            return -1

        position = [float(u), float(v), self._domain[2] / 2.0]
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
            if axes == (0, 1):
                spec['base'] = max(du, dv)
            else:
                spec['base'], spec['H'] = du, 2 * dv
        elif kind == 'ellipse':
            spec['a'], spec['b'] = du, dv
        elif kind == 'wedge':
            spec['r_outer'] = max(du, dv)
        elif kind in ('gaussian_2d', 'gaussian_3d'):
            sizes = ('sx', 'sy', 'sz')
            spec[sizes[axes[0]]] = du / 3.0
            spec[sizes[axes[1]]] = dv / 3.0
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
        self.featuresChanged.emit()
        self.selectedIndexChanged.emit()

    @staticmethod
    def _axes_for(projection: str):
        return {'xy': (0, 1), 'xz': (0, 2), 'yz': (1, 2)}.get(
            str(projection).lower(), (0, 1))

    # ── the potential, for the canvas ────────────────────────────────────

    @Slot(str, float, result='QVariantMap')
    def previewPotential(self, projection: str = "xy",
                         slice_at: float = -1.0):
        """The potential in the plane being shown, on a coarse grid.

        A 3-D model is cut through ``slice_at`` on the hidden axis (the
        middle of the box when that is negative), because a projection cannot
        show a volume and averaging through it would hide exactly the
        structure a user is placing.
        """
        try:
            axes = self._axes_for(projection)
            features = specs.build_features(self._features)
            n = self.PREVIEW_POINTS

            if self._mode == "2d":
                x, _dx = grid_axis(self._domain[0], n, "neumann")
                y, _dy = grid_axis(self._domain[1], n, "neumann")
                V, _ = build_potential_from_features(features, (x, y), 0.0)
                return {'x_nm': x.tolist(), 'y_nm': y.tolist(),
                        'V_eV': (V / 1.602176634e-19).tolist()}

            # 3-D: one plane of a coarse volume. Coarse on the hidden axis
            # too — only one of its slices is ever looked at.
            grids = [grid_axis(self._domain[i], n if i in axes else 24,
                               "neumann")[0] for i in range(3)]
            V, _ = build_potential_from_features(features, tuple(grids), 0.0)
            hidden = ({0, 1, 2} - set(axes)).pop()
            position = (self._domain[hidden] / 2.0 if slice_at < 0
                        else float(slice_at))
            index = int(np.argmin(np.abs(grids[hidden] - position)))
            plane = np.take(V, index, axis=hidden)
            if axes[0] > axes[1]:
                plane = plane.T
            return {'x_nm': grids[axes[0]].tolist(),
                    'y_nm': grids[axes[1]].tolist(),
                    'V_eV': (plane / 1.602176634e-19).tolist(),
                    'slice_at': float(grids[hidden][index])}
        except Exception as exc:
            logger.error("Potential preview failed: %s", exc, exc_info=True)
            return {}

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

            if len(shape) == 2:
                return {'x_nm': self._result['x_nm'],
                        'y_nm': self._result['y_nm'],
                        'values': grid.tolist()}

            grids = [self._result['x_nm'], self._result['y_nm'],
                     self._result['z_nm']]
            hidden = ({0, 1, 2} - set(axes)).pop()
            axis_values = np.asarray(grids[hidden])
            position = (float(axis_values[len(axis_values) // 2])
                        if slice_at < 0 else float(slice_at))
            index = int(np.argmin(np.abs(axis_values - position)))
            plane = np.take(grid, index, axis=hidden)
            if axes[0] > axes[1]:
                plane = plane.T
            return {'x_nm': list(grids[axes[0]]), 'y_nm': list(grids[axes[1]]),
                    'values': plane.tolist()}
        except Exception as exc:
            logger.error("Density slice failed: %s", exc, exc_info=True)
            return {}

    # ── solving ──────────────────────────────────────────────────────────

    @Slot('QVariantMap', result='QVariantMap')
    def gridCost(self, params):
        """How big the grid is, before anyone waits for it.

        A 3-D solve is the product of three counts, and the difference
        between 24³ and 60³ is seconds against minutes. Saying so up front is
        the difference between a wait and an app that looks hung.
        """
        params = dict(params or {})
        counts = self._grid_counts(params)
        points = int(np.prod(counts))
        return {'counts': list(counts), 'points': points,
                'too_big': points > self.MAX_GRID_POINTS,
                'limit': self.MAX_GRID_POINTS}

    def _grid_counts(self, params) -> tuple:
        if self._mode == "2d":
            return (max(8, int(params.get('Nx', 80))),
                    max(8, int(params.get('Ny', 80))))
        return (max(6, int(params.get('Nx', 24))),
                max(6, int(params.get('Ny', 24))),
                max(6, int(params.get('Nz', 24))))

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

            if self._mode == "2d":
                result = solve_well_2d(
                    self._domain[0], self._domain[1], Nx=counts[0],
                    Ny=counts[1], n_states=n_states, meff=meff,
                    features=features, V_background_eV=background, bc=bc)
            else:
                result = solve_well_3d(
                    self._domain[0], self._domain[1], self._domain[2],
                    Nx=counts[0], Ny=counts[1], Nz=counts[2],
                    n_states=n_states, meff=meff, features=features,
                    V_background_eV=background, bc=bc)
            result['ok'] = True
            result['error'] = ''
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
            return {'ok': True, 'rates': listed,
                    'assignments': [int(a) for a in assignments],
                    'unlocalised': sum(1 for a in assignments if a < 0),
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
