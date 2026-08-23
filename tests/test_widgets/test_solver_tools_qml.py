"""
Loads the two solver panels and drives them with a stub backend.

They are the receiving end of the designer's "Simulate": a window opens with
a geometry already in its fields and solves it. What has to hold is that the
handoff lands — the fields carry the candidate's numbers, not the defaults —
and that the parameter names the panels send are the ones the solvers read.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtQuick")
from PySide6.QtCore import Property, Q_ARG, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterType

from src.widgets.qml_figure_canvas import FigureCanvasItem
from src.widgets.qml_solver_canvas import SolverCanvas

QML_ROOT = Path(__file__).resolve().parents[2] / "src" / "qml"
WELL_QML = QML_ROOT / "tools" / "QuantumWellSolverTool.qml"
DOT_QML = QML_ROOT / "tools" / "QuantumDotSolverTool.qml"


class StubBackend(QObject):
    """Records what the panels ask for, and answers plausibly."""

    dataLoaded = Signal(str)

    def __init__(self):
        super().__init__()
        self.well_calls = []
        self.dot_calls = []

    @Slot('QVariantMap', result='QVariantMap')
    def solveQuantumWell(self, params):
        self.well_calls.append(dict(params))
        return {'ok': True, 'E_eV': [0.1, 0.4, 0.9], 'x_nm': [0.0, 1.0, 2.0],
                'V_eV': [0.0, 0.0, 0.0],
                'psi': [[0.0, 1.0, 0.0], [0.0, -1.0, 0.0], [1.0, 0.0, 1.0]],
                'bound': [0.1, 0.4, 0.9], 'L_box_nm': 8.0,
                'comparison': {'rrmse_pct': 0.5, 'covered': True,
                               'targets': [0.1, 0.4]},
                'error': ''}

    @Slot('QVariantMap', result='QVariantMap')
    def solveQuantumDot(self, params):
        self.dot_calls.append(dict(params))
        return {'ok': True,
                'levels': [{'index': 0, 'E_eV': 0.22, 'label': '1s',
                            'degeneracy': 1, 'occupancy': 2, 'channel': 0,
                            'qn': [1, 0]},
                           {'index': 1, 'E_eV': 0.46, 'label': '1p',
                            'degeneracy': 3, 'occupancy': 6, 'channel': 1,
                            'qn': [1, 1]}],
                'shells': [{'E_eV': 0.22, 'labels': ['1s'], 'degeneracy': 1,
                            'filled': 2}],
                'addition_eV': [0.0, 0.24],
                'dos': {'x': [0.0, 0.5], 'y': [1.0, 2.0]},
                'radial': {'r_nm': [0.0, 1.0], 'psi': [0.0, 1.0],
                           'label': '1s', 'index': 0},
                'comparison': {}, 'error': ''}


def _plain(value):
    """What QML sent, as Python.

    An array literal assigned from QML arrives as a ``QJSValue``, not a list;
    iterating it raises inside the setter and the write is silently dropped,
    which looks exactly like the QML never running.
    """
    return value.toVariant() if hasattr(value, "toVariant") else value


class StubWindow(QObject):
    """Stands in for the application window's handoff properties.

    Real Qt properties, not plain attributes: QML both reads these and
    clears them, and a bare Python attribute is invisible to it.
    """

    changed = Signal()

    def __init__(self, params=None, targets=None):
        super().__init__()
        self._params = params
        self._targets = list(targets or [])

    def _get_params(self):
        return self._params

    def _set_params(self, value):
        self._params = _plain(value)
        self.changed.emit()

    def _get_targets(self):
        return self._targets

    def _set_targets(self, value):
        self._targets = list(_plain(value) or [])
        self.changed.emit()

    pendingSolverParams = Property('QVariant', _get_params, _set_params,
                                   notify=changed)
    pendingSolverTargets = Property('QVariant', _get_targets, _set_targets,
                                    notify=changed)


@pytest.fixture(scope="module")
def app():
    application = QGuiApplication.instance() or QGuiApplication([])
    qmlRegisterType(FigureCanvasItem, "TransQML", 1, 0, "FigureCanvas")
    qmlRegisterType(SolverCanvas, "TransQML", 1, 0, "SolverCanvas")
    return application


#: Objects QML is holding a reference to. Letting one be collected while a
#: binding still points at it segfaults the interpreter, which is a confusing
#: way for a test to fail.
_KEEP_ALIVE = []


def _load(app, qml_path, pending=None, targets=None):
    engine = QQmlEngine()
    engine.addImportPath(str(QML_ROOT))
    backend = StubBackend()
    engine.rootContext().setContextProperty("backend", backend)

    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))
    assert component.status() == QQmlComponent.Ready, component.errorString()
    item = component.create()
    assert item is not None, component.errorString()

    # The component owns what it created, so it has to outlive the item; and
    # the item is reparented to the engine so nothing collects it mid-test.
    item.setParent(engine)
    _KEEP_ALIVE.extend([engine, backend, component, item])

    if pending is not None:
        # The window is created before the handoff in the real app; here the
        # panel is already up, so the pending values are applied by hand.
        window = StubWindow(pending, targets)
        _KEEP_ALIVE.append(window)
        item.setProperty("parentWindow", window)
        item.metaObject().invokeMethod(item, "applyPending")
        item.metaObject().invokeMethod(item, "solve")
    return item, backend


class TestTheWellSolverPanel:
    def test_it_loads_and_solves_on_open(self, app):
        """A solver window with nothing in it is a window that looks broken;
        it solves its defaults as it opens."""
        item, backend = _load(app, WELL_QML)

        assert item is not None
        assert backend.well_calls, "the panel never asked for a solve"

    def test_the_keys_it_sends_are_the_ones_the_solver_reads(self, app):
        from src.backend.tool_implementations import ToolImplementations

        _item, backend = _load(app, WELL_QML)
        known = set(ToolImplementations.WELL_SOLVER_DEFAULTS) | {'targets'}
        sent = set(backend.well_calls[-1])

        assert sent <= known, sent - known

    def test_a_candidate_lands_in_its_fields(self, app):
        """The handoff from the designer: the window opens on the geometry it
        found, not on the defaults."""
        item, backend = _load(app, WELL_QML,
                              pending={'L_nm': 12.5, 'meff': 0.045,
                                       'V0_eV': 0.3, 'n_states': 11},
                              targets=[0.1, 0.25])

        params = backend.well_calls[-1]
        assert params['L_nm'] == pytest.approx(12.5)
        assert params['meff'] == pytest.approx(0.045)
        assert params['V0_eV'] == pytest.approx(0.3)
        assert params['n_states'] == 11
        assert list(params['targets']) == pytest.approx([0.1, 0.25])

    def test_the_handoff_is_consumed_once(self, app):
        """Left in place, the next solver window would open on someone else's
        candidate."""
        window = StubWindow({'L_nm': 12.5}, [0.1])
        _KEEP_ALIVE.append(window)
        item, _backend = _load(app, WELL_QML)
        item.setProperty("parentWindow", window)
        item.metaObject().invokeMethod(item, "applyPending")

        assert window.pendingSolverParams is None
        assert list(window.pendingSolverTargets) == []

    def test_the_levels_it_gets_back_fill_the_list(self, app):
        item, _backend = _load(app, WELL_QML)

        assert item.property("result")['ok'] is True
        assert item.property("stateIndex") == 0


class TestTheDotSolverPanel:
    def test_it_loads_and_solves_on_open(self, app):
        item, backend = _load(app, DOT_QML)

        assert item is not None
        assert backend.dot_calls

    def test_the_keys_it_sends_are_the_ones_the_solver_reads(self, app):
        from src.backend.tool_implementations import ToolImplementations

        _item, backend = _load(app, DOT_QML)
        known = set(ToolImplementations.DOT_SOLVER_DEFAULTS) | {'targets'}
        sent = set(backend.dot_calls[-1])

        assert sent <= known, sent - known

    def test_a_dot_candidate_lands_in_its_fields(self, app):
        item, backend = _load(app, DOT_QML,
                              pending={'model': 'disc', 'R_nm': 6.0,
                                       'Lz_nm': 2.0, 'meff': 0.067,
                                       'channels': 4},
                              targets=[0.3])

        params = backend.dot_calls[-1]
        assert params['model'] == 'disc'
        assert params['R_nm'] == pytest.approx(6.0)
        assert params['Lz_nm'] == pytest.approx(2.0)
        assert params['channels'] == 4

    def test_choosing_a_state_asks_for_its_radial_function(self, app):
        """The radial function belongs to one level, so the solve is repeated
        for it — a dot is milliseconds."""
        item, backend = _load(app, DOT_QML)
        before = len(backend.dot_calls)
        item.metaObject().invokeMethod(item, "showState",
                                       Q_ARG("QVariant", 1))

        assert len(backend.dot_calls) > before
        assert backend.dot_calls[-1]['state_index'] == 1

    def test_the_model_key_is_the_coordinate_system(self, app):
        """A 0D candidate's `coords` names its model outright, which is why
        nothing has to be mapped between the designer and here."""
        item, backend = _load(app, DOT_QML)

        assert backend.dot_calls[-1]['model'] in ('spherical', 'disc',
                                                  'parabolic')
