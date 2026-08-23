"""
Loads the Confinement Designer panel and drives it with a stub backend.

qmllint parses the file; it does not catch a property the backend does not
have, a signal handler whose name no longer matches, or a result map whose
keys the panel reads under different names. Those only show up when the QML
is actually instantiated — which is what this does, offscreen, without a
window or a real project.

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

from src.widgets.qml_designer_canvas import DesignerCanvas
from src.widgets.qml_figure_canvas import FigureCanvasItem

QML_ROOT = Path(__file__).resolve().parents[2] / "src" / "qml"
TOOL_QML = QML_ROOT / "tools" / "ConfinementDesignerTool.qml"


class StubBackend(QObject):
    """Just enough backend for the panel to load and run once."""

    dataLoaded = Signal(str)
    designerCompleted = Signal('QVariantMap')

    def __init__(self):
        super().__init__()
        self.runs = []
        self.previews = []

    @Slot(result='QVariantList')
    def getDatasetList(self):
        return ["Line scan"]

    @Slot(str, result='QVariantMap')
    def getDatasetInfo(self, name):
        return {'name': name, 'num_spectra': 5, 'num_points': 512}

    @Slot(str, int, 'QVariantMap', result='QVariantMap')
    def previewDesignerTargets(self, name, index, params):
        self.previews.append((name, index, dict(params)))
        return {'ok': True, 'x': [0.0, 0.5, 1.0], 'raw': [0.0, 1.0, 0.0],
                'baseline': [], 'corrected': [], 'peaks_V': [0.5],
                'electron_eV': [0.5], 'hole_eV': [], 'in_gap_V': [],
                'column': 'P1', 'split_e': 0.0, 'split_h': 0.0, 'error': ''}

    @Slot(str, 'QVariantMap')
    def runConfinementDesigner(self, name, params):
        self.runs.append((name, dict(params)))

    @Slot()
    def cancelCurrentOperation(self):
        pass


def _result(candidates, pairs=0, error="", edges=None):
    return {'ok': bool(candidates), 'candidates': candidates, 'pairs': pairs,
            'edges': edges, 'peaks': {}, 'error': error,
            'dataset': 'Line scan', 'spectrum_index': 0}


def _candidate(index=0, dims=(8.001,), rrmse=1.4, **over):
    candidate = {
        'index': index, 'dims_nm': list(dims), 'size_nm': dims[0],
        'rrmse': rrmse, 'rrmse_de': rrmse, 'meff': 0.067, 'carrier': 'e',
        'offset_eV': -0.3, 'ndim': '1D', 'coords': 'cartesian', 'sym': '',
        'targets': [0.1, 0.2, 0.4], 'computed': [0.101, 0.199, 0.41],
        'errors_pct': [1.0, -0.5, 2.5], 'qn': [[1], [2], [3]],
    }
    candidate.update(over)
    return candidate


@pytest.fixture(scope="module")
def app():
    application = QGuiApplication.instance() or QGuiApplication([])
    qmlRegisterType(FigureCanvasItem, "TransQML", 1, 0, "FigureCanvas")
    qmlRegisterType(DesignerCanvas, "TransQML", 1, 0, "DesignerCanvas")
    return application


@pytest.fixture
def panel(app):
    """The tool, instantiated against a stub backend."""
    engine = QQmlEngine()
    engine.addImportPath(str(QML_ROOT))
    backend = StubBackend()
    engine.rootContext().setContextProperty("backend", backend)

    component = QQmlComponent(engine, QUrl.fromLocalFile(str(TOOL_QML)))
    assert component.status() == QQmlComponent.Ready, component.errorString()
    item = component.create()
    assert item is not None, component.errorString()

    yield item, backend

    item.deleteLater()


class TestItLoads:
    def test_the_panel_instantiates_without_errors(self, panel):
        item, _backend = panel
        assert item is not None

    def test_it_picks_up_the_datasets_on_load(self, panel):
        item, _backend = panel
        assert item.property("spectrumCount") == 5

    def test_it_previews_the_spectrum_it_will_search(self, panel):
        """The preview is what shows the user which peaks the search is
        about to be handed."""
        item, backend = panel
        item.metaObject().invokeMethod(item, "refreshPreview")

        assert backend.previews, "the panel never asked for a preview"
        name, index, params = backend.previews[-1]
        assert name == "Line scan" and index == 0

    def test_the_parameters_it_sends_are_the_keys_the_backend_reads(self, panel):
        """Every key here is compared or cast on the Python side; a rename on
        either side has to break something visible."""
        from src.backend.tool_implementations import ToolImplementations

        item, backend = panel
        item.metaObject().invokeMethod(item, "refreshPreview")
        _name, _index, params = backend.previews[-1]

        expected = set(ToolImplementations.DESIGNER_DEFAULTS) - {'fixed'}
        assert expected <= set(params), expected - set(params)

    def test_the_defaults_it_offers_match_the_backend_s(self, panel):
        from src.backend.tool_implementations import ToolImplementations

        item, backend = panel
        item.metaObject().invokeMethod(item, "refreshPreview")
        _name, _index, params = backend.previews[-1]
        defaults = ToolImplementations.DESIGNER_DEFAULTS

        for key in ('carrier', 'ndim', 'coords', 'match', 'priority'):
            assert params[key] == defaults[key], key


class TestRunningAndReporting:
    def test_running_hands_the_dataset_and_the_knobs_over(self, panel):
        item, backend = panel
        item.metaObject().invokeMethod(item, "runSearch")

        assert backend.runs, "the run button did not reach the backend"
        name, params = backend.runs[-1]
        assert name == "Line scan"
        assert params['ndim'] == "1D"
        assert item.property("running") is True

    def test_a_finished_run_fills_the_candidate_list(self, panel):
        item, backend = panel
        backend.designerCompleted.emit(_result([_candidate(), _candidate(1, (16.0,), 2.0)]))

        assert item.property("running") is False
        assert len(item.property("candidates")) == 2
        assert item.property("selectedCandidate") == 0

    def test_an_empty_run_says_why(self, panel):
        item, backend = panel
        backend.designerCompleted.emit(
            _result([], error="No candidate fits within the tolerance."))

        assert item.property("candidates") == []
        assert item.property("selectedCandidate") == -1

    def test_the_gap_is_reported_when_both_edges_are_known(self, panel):
        item, backend = panel
        backend.designerCompleted.emit(
            _result([_candidate()], pairs=1,
                    edges={'E_c': 0.30, 'E_v': -0.35, 'gap': 0.65}))

        assert len(item.property("candidates")) == 1

    def test_selecting_a_candidate_moves_the_plot(self, panel):
        item, backend = panel
        backend.designerCompleted.emit(_result([_candidate(), _candidate(1, (16.0,))]))
        item.metaObject().invokeMethod(item, "showCandidate",
                                       Q_ARG("QVariant", 1))

        assert item.property("selectedCandidate") == 1
