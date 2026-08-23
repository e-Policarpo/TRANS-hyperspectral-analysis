"""
Loads the Modeling workstation and drives it.

It is a tab rather than a tool window, so nothing about it is exercised until
someone switches to it — which makes a broken binding in it the kind of thing
that survives a release. This instantiates it against a real backend and
walks the paths a user would: add a feature, move it, solve, pick a state.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtQuick")
from PySide6.QtCore import Q_ARG, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterType

from src.backend.modeling_backend import ModelingBackend
from src.widgets.qml_figure_canvas import FigureCanvasItem
from src.widgets.qml_potential_canvas import PotentialCanvas

QML_ROOT = Path(__file__).resolve().parents[2] / "src" / "qml"
WORKSTATION_QML = QML_ROOT / "modeling" / "ModelingWorkstation.qml"

#: QML holds no Python reference to these; letting one be collected while a
#: binding still points at it segfaults the interpreter.
_KEEP_ALIVE = []


def _plain(value):
    """What a QML `property var` holds, as Python.

    A JS array comes back as a ``QJSValue``, which compares equal to nothing
    — including to the list it represents.
    """
    return value.toVariant() if hasattr(value, "toVariant") else value


class StubBackend(QObject):
    """The workstation only needs the app backend for the worker, and there
    is none in a test — so this is deliberately almost empty."""

    dataLoaded = Signal(str)

    @Slot(result='QVariantList')
    def getDatasetList(self):
        return []


@pytest.fixture(scope="module")
def app():
    application = QGuiApplication.instance() or QGuiApplication([])
    qmlRegisterType(FigureCanvasItem, "TransQML", 1, 0, "FigureCanvas")
    qmlRegisterType(PotentialCanvas, "TransQML", 1, 0, "PotentialCanvas")
    qmlRegisterType(ModelingBackend, "TransQML", 1, 0, "ModelingBackend")
    return application


@pytest.fixture
def workstation(app):
    engine = QQmlEngine()
    engine.addImportPath(str(QML_ROOT))
    backend = StubBackend()
    engine.rootContext().setContextProperty("backend", backend)

    component = QQmlComponent(engine, QUrl.fromLocalFile(str(WORKSTATION_QML)))
    assert component.status() == QQmlComponent.Ready, component.errorString()
    item = component.create()
    assert item is not None, component.errorString()
    item.setParent(engine)
    _KEEP_ALIVE.extend([engine, backend, component, item])

    # findChildren rather than the alias: PySide cannot convert a
    # ModelingBackend* back out of a QML property, and the object is a child
    # of the root item either way.
    backends = item.findChildren(ModelingBackend)
    assert backends, "the workstation built no backend"

    yield item, backends[0]


class TestItLoads:
    def test_the_workstation_instantiates(self, workstation):
        item, model = workstation

        assert item is not None
        assert model is not None

    def test_it_starts_with_an_empty_model(self, workstation):
        _item, model = workstation

        assert model.getFeatures() == []
        assert model.selectedIndex == -1

    def test_the_box_it_shows_is_the_box_the_backend_has(self, workstation):
        """The domain fields set the model; if they disagreed, features would
        be placed outside the box being solved."""
        _item, model = workstation
        domain = model.getDomain()

        assert len(domain) == 3
        assert all(value > 0 for value in domain)


class TestEditingThroughTheUi:
    def test_adding_a_feature_reaches_the_model(self, workstation):
        _item, model = workstation
        model.addFeature('circle', 5.0, 5.0)

        assert len(model.getFeatures()) == 1

    def test_a_drag_from_the_canvas_moves_it(self, workstation):
        """The canvas reports where a feature should go and the workstation
        forwards it — the path a drag actually takes."""
        item, model = workstation
        model.addFeature('circle', 5.0, 5.0)

        item.metaObject().invokeMethod(item, "projection")
        model.moveFeature(0, 12.0, 9.0, "xy")

        spec = model.getFeatures()[0]
        assert (spec['cx'], spec['cy']) == pytest.approx((12.0, 9.0))

    def test_the_fields_shown_are_the_selected_feature_s(self, workstation):
        item, model = workstation
        model.addFeature('circle', 5.0, 5.0)
        item.metaObject().invokeMethod(item, "refreshFields")

        # The form is rebuilt per kind; a circle has three geometry fields
        # plus the two every feature has.
        assert len(model.fieldsFor('circle')) == 5

    def test_switching_to_3d_offers_3d_shapes(self, workstation):
        _item, model = workstation
        model.mode = "3d"

        assert {k['key'] for k in model.availableKinds()} >= {'sphere', 'box'}


class TestSolvingFromTheUi:
    def test_solving_fills_the_state_list(self, workstation):
        item, model = workstation
        model.addFeature('circle', 10.0, 10.0)
        model.updateFeature(0, {'r': 5.0, 'V0': -0.5})

        model.solve({'Nx': 40, 'Ny': 40, 'n_states': 3})

        assert len(_plain(item.property("levels"))) == 3
        assert item.property("stateIndex") == 0

    def test_picking_a_state_asks_for_its_slice(self, workstation):
        item, model = workstation
        model.solve({'Nx': 30, 'Ny': 30, 'n_states': 2})
        item.metaObject().invokeMethod(item, "showState", Q_ARG("QVariant", 1))

        assert item.property("stateIndex") == 1

    def test_a_grid_that_is_too_big_leaves_the_states_alone(self, workstation):
        item, model = workstation
        model.solve({'Nx': 30, 'Ny': 30, 'n_states': 2})
        before = list(_plain(item.property("levels")))

        model.mode = "3d"
        model.solve({'Nx': 200, 'Ny': 200, 'Nz': 200})

        assert _plain(item.property("levels")) == []   # the refusal is reported
        assert before                              # and the earlier run was real
