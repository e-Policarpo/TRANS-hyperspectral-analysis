"""
Loads the two designer panels and drives them with a stub backend.

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
LINE_QML = QML_ROOT / "tools" / "LineScanDesignerTool.qml"


class StubBackend(QObject):
    """Just enough backend for the panel to load and run once."""

    dataLoaded = Signal(str)
    designerCompleted = Signal('QVariantMap')
    lineScanDesignCompleted = Signal('QVariantMap')

    def __init__(self):
        super().__init__()
        self.runs = []
        self.previews = []
        self.line_runs = []
        self.batches = []

    @Slot(result='QVariantList')
    def getDatasetList(self):
        return ["Line scan", "Other"]

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

    @Slot(str, 'QVariantMap')
    def runLineScanDesigner(self, name, params):
        self.line_runs.append((name, dict(params)))

    @Slot(str, 'QVariantList', 'QVariantMap')
    def runToolOnDatasets(self, key, names, params):
        self.batches.append((key, list(names), dict(params)))

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


@pytest.fixture
def line_panel(app):
    """The line-scan panel, instantiated against the same stub."""
    engine = QQmlEngine()
    engine.addImportPath(str(QML_ROOT))
    backend = StubBackend()
    engine.rootContext().setContextProperty("backend", backend)

    component = QQmlComponent(engine, QUrl.fromLocalFile(str(LINE_QML)))
    assert component.status() == QQmlComponent.Ready, component.errorString()
    item = component.create()
    assert item is not None, component.errorString()

    yield item, backend

    item.deleteLater()


def _line_result(points, groups=(), segments=(), summary=None, error=""):
    return {'ok': bool(points), 'dataset': 'line - Confinement',
            'map_paths': [], 'groups': list(groups), 'segments': list(segments),
            'summary': summary or {'total': len(points), 'converged': 0,
                                   'reasons': {}},
            'points': points, 'error': error}


def _point(index, size=float('nan'), group=-1, converged=False, reason=""):
    return {'point_index': index, 'position_nm': index * 5.0, 'size_nm': size,
            'rrmse_pct': float('nan'), 'group': group, 'n_peaks': 3,
            'reason': reason, 'converged': converged}


class TestTheLineScanPanel:
    def test_it_instantiates(self, line_panel):
        item, _backend = line_panel
        assert item is not None

    def test_picking_one_line_runs_the_tool_directly(self, line_panel):
        item, backend = line_panel
        item.metaObject().invokeMethod(item, "acceptDatasetDrop",
                                       Q_ARG("QVariant", ["Line scan"]))
        item.metaObject().invokeMethod(item, "runSearch")

        assert backend.line_runs, "the run button did not reach the backend"
        assert backend.line_runs[-1][0] == "Line scan"
        assert backend.batches == []
        assert item.property("running") is True

    def test_picking_several_lines_runs_them_as_a_batch(self, line_panel):
        """One entry in BATCH_TOOLS is all it takes; the panel just has to
        route to the batch slot rather than the single-dataset one."""
        item, backend = line_panel
        item.metaObject().invokeMethod(item, "acceptDatasetDrop",
                                       Q_ARG("QVariant", ["Line scan", "Other"]))
        item.metaObject().invokeMethod(item, "runSearch")

        assert backend.batches, "a multi-selection did not go through the batch"
        key, names, _params = backend.batches[-1]
        assert key == "line_scan_designer"
        assert names == ["Line scan", "Other"]
        assert backend.line_runs == []

    def test_nothing_selected_runs_nothing(self, line_panel):
        item, backend = line_panel
        item.metaObject().invokeMethod(item, "runSearch")

        assert backend.line_runs == [] and backend.batches == []

    def test_the_backend_understands_every_key_the_panel_sends(self, line_panel):
        """The panel's map and the backend's defaults have to name the same
        knobs; a rename on either side breaks here rather than silently."""
        from src.backend.tool_implementations import ToolImplementations

        item, backend = line_panel
        item.metaObject().invokeMethod(item, "acceptDatasetDrop",
                                       Q_ARG("QVariant", ["Line scan"]))
        item.metaObject().invokeMethod(item, "runSearch")

        # The detection knobs are not in the defaults maps: they belong to
        # the peak engine, which the search hands the whole map to.
        from src.processing.peak_detection import Params

        known = (set(ToolImplementations.DESIGNER_DEFAULTS)
                 | set(ToolImplementations.LINE_DESIGNER_DEFAULTS)
                 | set(vars(Params())))
        assert backend.line_runs
        _name, params = backend.line_runs[-1]
        assert set(params) <= known, set(params) - known
        # And the ones that decide the search are actually there.
        assert {'ndim', 'coords', 'match', 'carrier', 'max_rrmse',
                'group_tol_nm'} <= set(params)

    def test_a_finished_run_draws_the_strip_and_names_the_table(self, line_panel):
        item, backend = line_panel
        backend.lineScanDesignCompleted.emit(_line_result(
            [_point(0), _point(1, 8.0, 0, True), _point(2)],
            groups=[{'index': 0, 'size_nm': 8.0, 'count': 1, 'points': [1]}],
            segments=[{'group': -1, 'start': 0.0, 'end': 0.0, 'count': 1},
                      {'group': 0, 'start': 5.0, 'end': 5.0, 'count': 1},
                      {'group': -1, 'start': 10.0, 'end': 10.0, 'count': 1}],
            summary={'total': 3, 'converged': 1, 'reasons': {'no_peaks': 2}}))

        assert item.property("running") is False
        assert item.property("tableName") == "line - Confinement"

    def test_a_run_that_found_nothing_says_so(self, line_panel):
        item, backend = line_panel
        backend.lineScanDesignCompleted.emit(
            _line_result([], error="Dataset not found"))

        assert item.property("tableName") == ""

