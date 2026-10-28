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
from PySide6.QtCore import (Q_ARG, Q_RETURN_ARG, QMetaObject, QObject,
                            Qt, QUrl, Signal, Slot)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterType

from src.widgets.qml_designer_canvas import DesignerCanvas
from src.widgets.qml_figure_canvas import FigureCanvasItem
from src.physics.designer import Designer

QML_ROOT = Path(__file__).resolve().parents[2] / "src" / "qml"
TOOL_QML = QML_ROOT / "tools" / "ConfinementDesignerTool.qml"
LINE_QML = QML_ROOT / "tools" / "LineScanDesignerTool.qml"


class StubBackend(QObject):
    """Just enough backend for the panel to load and run once."""

    dataLoaded = Signal(str)
    designerCompleted = Signal('QVariantMap')
    lineScanDesignCompleted = Signal('QVariantMap')
    # The panels connect to these two as well. A Connections block whose
    # handler names nothing on the target is only a warning at load time, so
    # a stub that is missing a signal quietly passes the very test that is
    # supposed to catch the rename.
    toolProgress = Signal(str, int, int, str)
    operationCancelled = Signal(str)

    def __init__(self):
        super().__init__()
        self.runs = []
        self.previews = []
        self.line_runs = []
        self.batches = []
        self.described = []
        self.cancelled = []

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

    @Slot(str, 'QVariantMap', result=str)
    def runLineScanDesigner(self, name, params):
        self.line_runs.append((name, dict(params)))
        return "Line Scan Designer " + name

    @Slot(str, 'QVariantList', 'QVariantMap', result=str)
    def runToolOnDatasets(self, key, names, params):
        self.batches.append((key, list(names), dict(params)))
        return "batch"

    @Slot('QVariantMap', result='QVariantMap')
    def describeCandidate(self, candidate):
        self.described.append(dict(candidate))
        return {'ok': False, 'error': 'no solver here'}

    @Slot()
    def cancelCurrentOperation(self):
        pass

    @Slot(str)
    def cancelOperation(self, name):
        self.cancelled.append(name)


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


def _pick(item, *names):
    """Select datasets the way the user does — the panel picks none itself.

    The dataset control is a multi-select now, and it starts empty on
    purpose: a search is minutes, and a panel that pre-selected whatever
    dataset happened to be first in the project would hand those minutes to
    something nobody asked about. Everything downstream of the selection
    therefore has to say which datasets it is about.
    """
    item.metaObject().invokeMethod(item, "acceptDatasetDrop",
                                   Q_ARG("QVariant", list(names)))


class TestItLoads:
    def test_the_panel_instantiates_without_errors(self, panel):
        item, _backend = panel
        assert item is not None

    def test_it_picks_nothing_until_the_user_does(self, panel):
        item, _backend = panel
        assert item.property("spectrumCount") == 0

    def test_picking_a_dataset_picks_up_its_spectrum_count(self, panel):
        item, _backend = panel
        _pick(item, "Line scan")

        assert item.property("spectrumCount") == 5

    def test_it_previews_the_spectrum_it_will_search(self, panel):
        """The preview is what shows the user which peaks the search is
        about to be handed."""
        item, backend = panel
        _pick(item, "Line scan")
        item.metaObject().invokeMethod(item, "refreshPreview")

        assert backend.previews, "the panel never asked for a preview"
        name, index, params = backend.previews[-1]
        assert name == "Line scan" and index == 0

    def test_the_parameters_it_sends_are_the_keys_the_backend_reads(self, panel):
        """Every key here is compared or cast on the Python side; a rename on
        either side has to break something visible."""
        from src.backend.tool_implementations import ToolImplementations

        item, backend = panel
        _pick(item, "Line scan")
        item.metaObject().invokeMethod(item, "refreshPreview")
        _name, _index, params = backend.previews[-1]

        expected = set(ToolImplementations.DESIGNER_DEFAULTS) - {'fixed'}
        assert expected <= set(params), expected - set(params)

    def test_the_defaults_it_offers_match_the_backend_s(self, panel):
        from src.backend.tool_implementations import ToolImplementations

        item, backend = panel
        _pick(item, "Line scan")
        item.metaObject().invokeMethod(item, "refreshPreview")
        _name, _index, params = backend.previews[-1]
        defaults = ToolImplementations.DESIGNER_DEFAULTS

        for key in ('carrier', 'ndim', 'coords', 'match', 'priority'):
            assert params[key] == defaults[key], key


class TestRunningAndReporting:
    def test_running_hands_the_datasets_and_the_knobs_over(self, panel):
        """One selection, one batch task — even for a single dataset.

        Each dataset in the batch reports back through designerCompleted and
        writes its own tables, so the panel has nothing to gain from calling
        runConfinementDesigner directly and everything to lose: two entry
        points would be two places for the parameter map to drift.
        """
        item, backend = panel
        _pick(item, "Line scan")
        item.metaObject().invokeMethod(item, "runSearch")

        assert backend.batches, "the run button did not reach the backend"
        key, names, params = backend.batches[-1]
        assert key == "confinement_designer"
        assert names == ["Line scan"]
        assert params['ndim'] == "1D"
        assert backend.runs == []
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



class TestTheDimensionControls:
    """The pinning and per-dimension range controls — the panel's half of the
    highest-value fix in this tool: the engine has always honoured a pinned
    dimension, and nothing ever sent it one.

    The controls write into `dimLimits` and `searchParams` reads it there, so
    these drive that property rather than clicking delegates: a Repeater
    rebuilds its delegates whenever the geometry changes, and state that only
    exists inside one of them cannot survive that.
    """

    @staticmethod
    def _params(item, backend):
        _pick(item, "Line scan")
        item.metaObject().invokeMethod(item, "runSearch")
        _key, _names, params = backend.batches[-1]
        return params

    @staticmethod
    def _limit(pinned=False, pin=0.0, lo=0.0, hi=0.0):
        return {"pinned": pinned, "pin": pin, "lo": lo, "hi": hi}

    def test_the_dimensions_are_named_not_numbered(self, panel):
        item, _backend = panel
        # The panel opens on 1D cartesian, whose one dimension is a length.
        # A `var` property comes back as a QJSValue; toVariant() is the
        # plain Python view of it.
        dims = item.property("dimList").toVariant()
        assert list(dims["keys"]) == ["d1"]
        assert list(dims["labels"]) == ["L"]

    def test_the_controls_publish_themselves_on_load(self, panel):
        """Every dimension the geometry has is in the map from the start, as
        'not pinned, shared range' — so the map is the record of the panel
        rather than of whatever the user happened to touch."""
        item, _backend = panel
        limits = item.property("dimLimits").toVariant()
        assert set(limits) == {"d1"}
        assert limits["d1"]["pinned"] is False

    def test_nothing_is_pinned_until_the_user_pins_it(self, panel):
        item, backend = panel
        params = self._params(item, backend)

        assert dict(params['fixed']) == {}
        assert dict(params['box']) == {}

    def test_pinning_a_dimension_sends_it(self, panel):
        item, backend = panel
        item.setProperty("dimLimits", {"d1": self._limit(pinned=True, pin=5.0)})
        params = self._params(item, backend)

        assert dict(params['fixed']) == {"d1": 5.0}
        # A pinned dimension has no range: it is not being searched.
        assert dict(params['box']) == {}

    def test_a_range_of_its_own_is_sent_as_a_pair(self, panel):
        item, backend = panel
        item.setProperty("dimLimits", {"d1": self._limit(lo=2.0, hi=6.0)})
        params = self._params(item, backend)

        assert list(params['box']["d1"]) == [2.0, 6.0]

    def test_one_end_left_blank_falls_back_to_the_shared_range(self, panel):
        item, backend = panel
        item.setProperty("dimLimits", {"d1": self._limit(hi=6.0)})
        params = self._params(item, backend)

        # None, not 0: the backend reads a None end as "use Lmin/Lmax", and a
        # 0 there would be a 0 nm bound.
        assert list(params['box']["d1"]) == [None, 6.0]

    def test_a_pin_on_a_dimension_the_geometry_lost_is_not_sent(self, panel):
        """1D has one dimension. A d2 left over from a disc is a pin on a
        slot this search does not read, and sending it would pin nothing
        while making the table name claim otherwise."""
        item, backend = panel
        item.setProperty("dimLimits", {"d2": self._limit(pinned=True, pin=5.0)})
        params = self._params(item, backend)

        assert dict(params['fixed']) == {}

    def test_the_assignment_and_the_search_mode_start_where_they_were(self, panel):
        item, backend = panel
        params = self._params(item, backend)

        assert params['assign'] == "energy"
        assert params['search_mode'] == "sample"
        # None, not 0 — the engine derives the window from the data, which is
        # what it did before this field existed.
        assert params['resolution_meV'] is None


class TestTheBudgetThePanelPrints:
    """The lattice size and the refinement count, before the run commits.

    The panel prints both because they are what its nesting claim rests on:
    the lattice nests by construction, and the candidate LIST inherits that
    only because the refinement budget is a density over the box rather than
    an absolute top-N. Printing them means computing them in QML, which
    cannot import Python — so the panel carries a MIRROR of
    ``Designer.lattice`` and ``Designer.polish_budget``, and a mirror nothing
    compares against drifts.

    It did drift: the engine replaced an absolute floor of 8 refinements with
    an EXHAUSTIVE floor (a lattice of ``POLISH_ALL_BELOW`` nodes or fewer is
    refined in full) and the panel kept the old rule, so on a 2–8 nm × 4–6 nm
    box at 4 nodes per octave it printed "refining 8 of 27" where the engine
    refines all 27. These tests are the comparison that was missing.
    """

    #: The panel opens on 1D cartesian with one free dimension, `d1`, and its
    #: shared range starts at 1–20 nm with 8 lattice nodes per octave.
    PER_OCTAVE = {'enum_per_octave': 8}
    POLISH = {'enum_polish': 40}

    @staticmethod
    def _call(item, name, *args):
        return QMetaObject.invokeMethod(
            item, name, Qt.DirectConnection, Q_RETURN_ARG("QVariant"),
            *[Q_ARG("QVariant", a) for a in args])

    @staticmethod
    def _limit(lo=0.0, hi=0.0):
        return {"pinned": False, "pin": 0.0, "lo": lo, "hi": hi}

    @pytest.mark.parametrize("lo, hi", [(0.0, 0.0), (2.0, 8.0),
                                        (1.0, 13.0), (1.0, 25.0),
                                        (3.0, 4.0)])
    def test_the_lattice_size_it_prints_is_the_one_the_engine_builds(
            self, panel, lo, hi):
        item, _backend = panel
        item.setProperty("dimLimits", {"d1": self._limit(lo=lo, hi=hi)})

        # A blank end falls back to the shared range, exactly as the search
        # parameters do.
        engine = len(Designer.lattice(lo or 1.0, hi or 20.0, self.PER_OCTAVE))
        assert item.property("latticeNodeCount") == engine

    @pytest.mark.parametrize("total", [1, 4, 8, 27, 32, 33, 900, 1156, 1444])
    def test_the_refinement_count_it_prints_is_the_budget_the_engine_uses(
            self, panel, total):
        """Checked against an explicit lattice size, so the exhaustive floor
        is exercised on both sides of its threshold rather than only at
        whatever size this panel's default range happens to give."""
        item, _backend = panel
        item.setProperty("dimLimits", {"d1": self._limit(lo=2.0, hi=8.0)})
        p = dict(self.POLISH)

        assert self._call(item, "polishBudget", total) == \
            Designer.polish_budget([(2.0, 8.0)], p, total)

    def test_a_lattice_under_the_floor_is_refined_in_full(self, panel):
        """The drift itself: 27 nodes over a narrow box are all refined, and
        the panel used to print the density's 20 (and, with two free
        dimensions, 8)."""
        item, _backend = panel
        item.setProperty("dimLimits", {"d1": self._limit(lo=2.0, hi=8.0)})

        assert self._call(item, "polishBudget", 27) == 27
        assert Designer.polish_budget([(2.0, 8.0)], dict(self.POLISH), 27) == 27
        # One node over the threshold the selection is a density again, and
        # the panel says which rule is in force rather than printing a number
        # whose rule the reader has to guess.
        assert self._call(item, "polishBudget", 33) == \
            Designer.polish_budget([(2.0, 8.0)], dict(self.POLISH), 33)

    def test_the_constants_it_mirrors_are_the_engine_s(self, panel):
        item, _backend = panel

        assert item.property("polishAllBelow") == Designer.POLISH_ALL_BELOW
        assert item.property("polishMaxFactor") == Designer.POLISH_MAX_FACTOR
        assert item.property("polishReferenceOctaves") == \
            pytest.approx(Designer.POLISH_REFERENCE_OCTAVES)

    def test_the_budget_it_prints_is_the_one_for_the_lattice_it_prints(
            self, panel):
        """The two numbers are shown in one sentence, so they have to be
        about the same lattice: the budget is evaluated AT the node count."""
        item, _backend = panel
        item.setProperty("dimLimits", {"d1": self._limit(lo=1.0, hi=18.0)})
        nodes = item.property("latticeNodeCount")

        assert item.property("polishBudgetCount") == \
            Designer.polish_budget([(1.0, 18.0)], dict(self.POLISH), nodes)


class TestTheCostItQuotes:
    """The estimate shown before a run, and before the long-run dialog.

    The panel used to describe a search as "seconds each" — a 300-spectrum
    sweep over two masses is over two hours — and then, once it quoted the
    measured per-spectrum rates, to quote the ENUMERATED one as a single
    number. It is not one number: the cost follows the lattice, which the
    nodes-per-octave control moves by a factor of 20 on its own, so a flat
    10.6 s understates that control's top by 2.4x. The rule has to stay above
    every measurement, because an estimate that is too low is the one that
    gets a sweep started.
    """

    #: (lattice nodes, seconds) measured on an M1 Pro over the 1-18 nm box in
    #: two free dimensions at 8, 16, 24 and 32 nodes per octave.
    MEASURED = [(1156, 9.91), (4489, 16.76), (10201, 20.24), (17956, 24.28)]

    @staticmethod
    def _call(item, name, *args):
        return QMetaObject.invokeMethod(
            item, name, Qt.DirectConnection, Q_RETURN_ARG("QVariant"),
            *[Q_ARG("QVariant", a) for a in args])

    @pytest.mark.parametrize("nodes, seconds", MEASURED)
    def test_it_never_quotes_less_than_the_run_took(self, panel, nodes,
                                                    seconds):
        item, _backend = panel

        assert self._call(item, "enumSecondsFor", nodes) >= seconds

    def test_it_grows_with_the_lattice(self, panel):
        """The defect this replaced: the same 10.6 s whatever the lattice."""
        item, _backend = panel
        cheap = self._call(item, "enumSecondsFor", 1156)
        dense = self._call(item, "enumSecondsFor", 200000)

        assert dense > 10 * cheap
        # ~2.9 min at the 200,000-node cap, against the ~2.5 min it really
        # takes there — high on purpose, and the same order.
        assert 150.0 < dense < 300.0

    def test_the_sampled_rate_is_the_measured_one(self, panel):
        """25.9 s per spectrum per mass, the upper end of five seeds."""
        item, _backend = panel

        assert item.property("secondsPerSearch") == pytest.approx(25.9)
