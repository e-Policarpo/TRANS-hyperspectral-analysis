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
from src.widgets.qml_states_canvas import StatesCanvas

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
    # StatesView.qml instantiates this; without it the workstation itself
    # fails to resolve, so every test in the file errors in setup.
    qmlRegisterType(StatesCanvas, "TransQML", 1, 0, "StatesCanvas")
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


# --------------------------------------------------------------------------
# The parameter column is a fixed width, and the controls in it have to fit.
#
# They twice have not. `width: parent.width` inside a ScrollView bound to the
# flickable's content item, which sizes itself from its child, so the column
# grew to its widest label and clip cut the rest away (fixed in b9319b0); then
# the Basic style's Button, which is 100 px wide whatever its text says, made
# a row of three 310 px wide in a 291 px column — and a row is never narrower
# than the sum of the children that do not fill, so the third was clipped.
#
# Geometry is only computed once the item is in a window, which is why these
# use a QQuickView rather than the component fixture above.

from PySide6.QtCore import QPointF                       # noqa: E402
from PySide6.QtQuick import QQuickItem, QQuickView       # noqa: E402


@pytest.fixture
def shown(app):
    view = QQuickView()
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.resize(1000, 800)
    view.setSource(QUrl.fromLocalFile(str(WORKSTATION_QML)))
    assert view.status() == QQuickView.Ready, [e.toString() for e in view.errors()]
    view.show()
    app.processEvents()
    root = view.rootObject()
    model = root.findChild(ModelingBackend)
    _KEEP_ALIVE.extend([view, root])
    yield root, model, app
    view.setSource(QUrl())
    view.close()


def _overflowing(column):
    """Every visible descendant that sticks out past the column's edges."""
    out = []

    def walk(item):
        for child in item.childItems():
            if not child.isVisible() or child.width() <= 0:
                continue
            left = child.mapToItem(column, QPointF(0, 0)).x()
            if left < -0.5 or left + child.width() > column.width() + 0.5:
                out.append((child.metaObject().className(),
                            left, child.width(), column.width()))
            walk(child)

    walk(column)
    return out


class TestTheParameterColumnFits:
    def test_nothing_sticks_out_of_it(self, shown):
        root, _model, _app = shown
        column = root.findChild(QQuickItem, "parameterColumn")

        assert column.width() > 0
        assert _overflowing(column) == []

    def test_nothing_sticks_out_with_every_section_open(self, shown):
        root, model, app = shown
        # 3-D brings up the projection row and the note under it; a selected
        # feature brings up its field form; two features bring up tunnelling.
        model.mode = "3d"
        model.addFeature("box", 6.0, 6.0)
        model.addFeature("box", 14.0, 14.0)
        model.selectedIndex = 0
        root.metaObject().invokeMethod(root, "refreshTunneling")
        app.processEvents()
        column = root.findChild(QQuickItem, "parameterColumn")

        assert _overflowing(column) == []

    def test_the_actions_stay_out_of_the_scroll(self, shown):
        """Solve is what the panel is for: a long parameter list must not be
        able to push it out of reach."""
        root, model, app = shown
        model.mode = "3d"
        model.addFeature("box", 6.0, 6.0)
        app.processEvents()

        column = root.findChild(QQuickItem, "parameterColumn")
        actions = root.findChild(QQuickItem, "modelActions")
        top = actions.mapToItem(column, QPointF(0, 0)).y()

        assert top + actions.height() <= column.height() + 0.5
        # and it is a sibling of the scroll area, not something inside it
        assert actions.parentItem() is column



# --------------------------------------------------------------------------
# QML fails softly. A misspelled id, a property that no longer exists, a
# binding that cannot resolve — none of them stop a component loading, they
# just log and leave that one thing dead. Every test above would pass with
# the whole plane picker inert, so what follows watches the engine's warnings
# rather than only its status, and then drives the controls themselves.
#
# Not every warning is one of ours: the native macOS style logs that it
# "does not support customization" for the controls this app styles by hand,
# on every run and harmlessly. So the filter is on what a message says went
# wrong, not on there being no messages.

from PySide6.QtQml import QQmlExpression, qmlContext          # noqa: E402

BROKEN = ("is not a type", "unavailable", "ReferenceError",
          "Unable to assign", "Cannot assign", "is not defined",
          "Binding loop", "Invalid property")


def _ev(item, source):
    """Run an expression in the item's own scope, and give back its value.

    Its ids are only resolvable from inside that scope, and PySide's
    invokeMethod cannot carry a return value out of a QML function — so this
    is how a `sliceAt()` is read at all. `evaluate()` answers
    (value, undefined).
    """
    value, undefined = QQmlExpression(qmlContext(item), item,
                                      source).evaluate()
    assert not undefined, source
    return value


def _run(item, source):
    """Same, for a call made for its effect. A QML function that returns
    nothing evaluates to undefined, which `_ev` refuses on purpose."""
    QQmlExpression(qmlContext(item), item, source).evaluate()


def _set_plane(item, plane):
    """Click the plane picker, which is what `projection()` reads."""
    _run(item, "planeSegmented.currentIndex = %d"
         % ["xy", "xz", "yz"].index(plane))


@pytest.fixture
def loud(app):
    """An engine that keeps every warning it emitted."""
    engine = QQmlEngine()
    engine.addImportPath(str(QML_ROOT))
    engine.rootContext().setContextProperty("backend", StubBackend())
    heard = []
    engine.warnings.connect(heard.extend)
    _KEEP_ALIVE.append(engine)
    return engine, heard


def _load(engine, path):
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
    assert component.status() == QQmlComponent.Ready, component.errorString()
    item = component.create()
    assert item is not None, component.errorString()
    _KEEP_ALIVE.extend([component, item])
    return item


def _complaints(heard):
    return [warning.toString() for warning in heard
            if any(word in warning.toString() for word in BROKEN)]


class TestNothingIsQuietlyDead:
    def test_the_workstation_loads_without_a_broken_binding(self, loud, app):
        engine, heard = loud
        _load(engine, WORKSTATION_QML)
        app.processEvents()

        assert _complaints(heard) == []

    def test_the_states_view_it_mounts_resolves(self, loud):
        """A new file in a new directory: an import path that does not reach
        it fails here and nowhere else, because the workstation loads
        perfectly well with the view left out."""
        engine, heard = loud
        _load(engine, QML_ROOT / "modeling" / "StatesView.qml")

        assert _complaints(heard) == []

    @pytest.mark.parametrize("name", ["ToolSegmented", "ToolSlider",
                                      "ToolButton"])
    def test_the_shared_controls_load_on_their_own(self, loud, name):
        """They resolve their palette through ToolTheme, which reads an
        attached property off a window — so a control that behaves inside the
        workstation can still be broken as a component."""
        engine, heard = loud
        _load(engine, QML_ROOT / "components" / f"{name}.qml")

        assert _complaints(heard) == []


class TestChoosingThePlaneAndTheCut:
    """A 3-D model is shown one plane at a time, and cut anywhere along the
    axis that plane hides."""

    def test_a_flat_model_has_no_cut_to_take(self, workstation):
        """-1 is how the backend is told there is no hidden axis — the same
        value it reads as "put it in the middle", which is the same answer
        here."""
        item, _model = workstation

        assert item.property("threeD") is False
        assert _ev(item, "sliceAt()") == -1.0

    def test_a_volume_starts_cut_through_its_middle(self, workstation):
        item, model = workstation
        model.mode = "3d"
        model.setDomain(20.0, 20.0, 12.0)

        assert item.property("threeD") is True
        assert _ev(item, "projection()") == "xy"
        assert _ev(item, "sliceAt()") == pytest.approx(6.0)

    @pytest.mark.parametrize("plane,axis,middle", [
        ("xy", 2, 5.0), ("xz", 1, 10.0), ("yz", 0, 15.0)])
    def test_each_plane_cuts_along_the_axis_it_hides(self, workstation,
                                                     plane, axis, middle):
        item, model = workstation
        model.mode = "3d"
        model.setDomain(30.0, 20.0, 10.0)
        _set_plane(item, plane)

        assert _ev(item, "projection()") == plane
        assert _ev(item, "hiddenAxis()") == axis
        assert _ev(item, "sliceAt()") == pytest.approx(middle)

    def test_the_picker_is_ignored_while_the_model_is_flat(self, workstation):
        """A 2-D model has one plane, and offering a cut of it would be
        offering a cut of nothing."""
        item, _model = workstation
        _set_plane(item, "yz")

        assert _ev(item, "projection()") == "xy"

    def test_each_axis_remembers_where_it_was_last_cut(self, workstation):
        """Switching plane and coming back is how a volume gets read, and a
        cut that reset to the middle each time would lose the plane the user
        was actually looking at."""
        item, model = workstation
        model.mode = "3d"
        model.setDomain(20.0, 20.0, 20.0)

        _run(item, "sliceMoved(4.0)")             # z
        _set_plane(item, "xz")
        _run(item, "sliceMoved(7.0)")             # y
        _set_plane(item, "xy")

        assert _ev(item, "sliceAt()") == pytest.approx(4.0)
        assert _plain(item.property("slicePos")) == [-1, 7, 4]

    def test_a_cut_the_box_no_longer_holds_is_dropped(self, workstation):
        """Not clamped: once the walls have moved, 7 nm in a 3 nm box is not
        "the same place a bit further in" — the middle is the only position
        that means the same thing in every box."""
        item, model = workstation
        model.mode = "3d"
        model.setDomain(20.0, 20.0, 20.0)
        _run(item, "sliceMoved(7.0)")

        model.setDomain(20.0, 20.0, 3.0)
        _run(item, "retuneSlice()")

        assert _plain(item.property("slicePos"))[2] == -1
        assert _ev(item, "sliceAt()") == pytest.approx(1.5)

    def test_the_readout_names_a_length(self, workstation):
        item, model = workstation
        model.mode = "3d"
        model.setDomain(20.0, 20.0, 20.0)
        _run(item, "sliceMoved(4.0)")

        assert item.property("sliceText") == "4.00 nm"


class TestSwitchingToTheStateView:
    def test_it_starts_on_the_editor(self, workstation):
        item, _model = workstation

        assert item.property("viewMode") == 0

    def test_the_editor_is_not_torn_down_to_show_the_states(self, workstation):
        """They swap by `visible` inside the same Item, so the canvas keeps
        its features, its selection and its zoom across a switch."""
        item, model = workstation
        model.mode = "3d"
        model.addFeature("box", 6.0, 6.0)
        _run(item, "setViewMode(1)")

        assert item.property("viewMode") == 1
        assert len(model.getFeatures()) == 1

    def test_going_flat_puts_the_editor_back(self, workstation):
        """There is no volume to cut three ways any more, so the switch that
        got you here is gone — and leaving the view behind it on screen would
        strand the model out of reach."""
        item, model = workstation
        model.mode = "3d"
        _run(item, "setViewMode(1)")
        model.mode = "2d"

        assert item.property("viewMode") == 0

    def test_asking_for_no_state_at_all_is_survivable(self, workstation):
        """-1 is what the workstation holds before a solve, and the state
        view is refreshed on every selection change."""
        item, model = workstation
        model.mode = "3d"
        item.metaObject().invokeMethod(item, "showState", Q_ARG("QVariant", -1))

        assert item.property("stateIndex") == -1
