"""
Loads the Spectral Features panel against a stub backend and checks that it
picks several datasets and hands them to the batch runner in order.

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

from src.widgets.qml_figure_canvas import FigureCanvasItem
from src.widgets.qml_graph_canvas import QMLGraphCanvas

QML_ROOT = Path(__file__).resolve().parents[2] / "src" / "qml"
TOOL_QML = QML_ROOT / "tools" / "SpectralFeaturesTool.qml"


class StubBackend(QObject):
    dataLoaded = Signal(str)
    toolCompleted = Signal(str, str)
    errorOccurred = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.previews = []
        self.batches = []

    @Slot(result='QVariantList')
    def getDatasetList(self):
        return ["A", "B", "C"]

    @Slot(str, result='QVariantMap')
    def getDatasetInfo(self, name):
        return {'name': name, 'num_spectra': {'A': 4, 'B': 7, 'C': 2}[name]}

    @Slot(str, int, 'QVariantMap', result='QVariantMap')
    def previewSpectralFeatures(self, name, index, params):
        self.previews.append((name, index, dict(params)))
        return {'ok': True, 'x': [0.0, 1.0], 'y': [0.0, 1.0],
                'gapLeft': 0.2, 'gapRight': 0.8, 'stateX': [], 'stateY': [],
                'names': ['gap'], 'values': ['0.6'], 'name': name,
                'valid': True, 'error': '', 'diracLineX': [], 'diracLineY': []}

    @Slot(str, 'QVariantList', 'QVariantMap', result=str)
    def runToolOnDatasets(self, key, names, params):
        self.batches.append((key, list(names), dict(params)))
        return "batch"


@pytest.fixture(scope="module")
def app():
    application = QGuiApplication.instance() or QGuiApplication([])
    qmlRegisterType(FigureCanvasItem, "TransQML", 1, 0, "FigureCanvas")
    qmlRegisterType(QMLGraphCanvas, "TransQML", 1, 0, "GraphCanvas")
    return application


@pytest.fixture
def panel(app):
    engine = QQmlEngine()
    engine.addImportPath(str(QML_ROOT))
    backend = StubBackend()
    engine.rootContext().setContextProperty("backend", backend)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(TOOL_QML)))
    assert component.status() == QQmlComponent.Ready, component.errorString()
    item = component.create()
    assert item is not None, component.errorString()
    yield item, backend, engine
    item.deleteLater()


def _pick(item, *names):
    item.metaObject().invokeMethod(item, "acceptDatasetDrop",
                                   Q_ARG("QVariant", list(names)))


def _call(item, method):
    item.metaObject().invokeMethod(item, method)


def test_it_picks_nothing_until_the_user_does(panel):
    item, backend, _ = panel
    assert item.property("spectrumCount") == 0
    _call(item, "runExtraction")
    assert backend.batches == []


def test_the_preview_follows_the_first_pick(panel):
    item, backend, _ = panel
    _pick(item, "B", "A")
    assert item.property("previewDataset") == "B"
    assert item.property("spectrumCount") == 7
    _call(item, "updatePreview")
    assert backend.previews[-1][0] == "B"


def test_extraction_runs_every_pick_in_order_through_the_batch_runner(panel):
    item, backend, _ = panel
    _pick(item, "C", "A")
    _call(item, "runExtraction")

    assert len(backend.batches) == 1
    key, names, params = backend.batches[0]
    assert key == "spectral_features"
    assert names == ["C", "A"]
    assert {'normalize', 'gap_delta', 'positive_only'} <= set(params)
    assert item.property("running") is True


def test_the_run_ends_when_every_dataset_has_reported(panel):
    item, backend, _ = panel
    _pick(item, "A", "B")
    _call(item, "runExtraction")

    backend.toolCompleted.emit("Spectral Features", "/a.csv")
    assert item.property("running") is True
    backend.toolCompleted.emit("Spectral Features", "/b.csv")
    assert item.property("running") is False


def test_a_failed_batch_does_not_leave_it_running(panel):
    item, backend, _ = panel
    _pick(item, "A", "B")
    _call(item, "runExtraction")
    backend.errorOccurred.emit("Spectral Features Error", "1 dataset(s) failed")
    assert item.property("running") is False


def test_the_batch_spec_routes_the_result_dict_to_a_path():
    from src.backend.batch_tools import get_spec
    from src.backend.app_backend import AppBackend

    spec = get_spec("spectral_features")
    assert spec.method == "extract_spectral_features" and spec.params_as_dict
    assert hasattr(AppBackend, spec.completion)
