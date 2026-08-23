"""
The Tools menu's three groups, checked against the code they point at.

The menu is hand-written QML: a tool can be listed with no file behind it, or
have a file and never appear, and neither shows up until someone clicks. This
reads Main.qml and holds the list to the tool map, the palette, and the
taxonomy the grouping is claiming.

Also loads the saved-workflow runner, which the menu's third group opens.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QML_ROOT = Path(__file__).resolve().parents[2] / "src" / "qml"
MAIN_QML = QML_ROOT / "main" / "Main.qml"
RUNNER_QML = QML_ROOT / "tools" / "SavedWorkflowRunner.qml"


@pytest.fixture(scope="module")
def main_qml():
    return MAIN_QML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tools_menu(main_qml):
    """Just the Tools menu, from its id to the next Menu block."""
    start = main_qml.index("id: toolsMenu")
    end = main_qml.index("id: workflowsMenu")
    return main_qml[start:end]


def _menu_entries(text):
    """Every clickable tool entry, in menu order.

    Comment lines between the text and the visibility are allowed: several
    entries carry a line saying why they appear on a second tab, and a
    parser that ignored them would quietly report the entry as missing.
    """
    return re.findall(r'text: "([^"]+)"\n(?:\s*//[^\n]*\n)*'
                      r'\s*visible: [^\n]+\n\s*height: '
                      r'visible \? implicitHeight : 0\n\s*onTriggered: '
                      r'openToolWindow\(text\)', text)


def _group(text, title):
    """The entries between one group header and the next separator."""
    start = text.index(f'text: "— {title} —"')
    rest = text[start:]
    end = rest.find("MenuSeparator")
    return _menu_entries(rest if end < 0 else rest[:end])


def _tool_map(text):
    block = text[text.index("var toolMap = {"):]
    block = block[:block.index("}")]
    return dict(re.findall(r'"([^"]+)": "([^"]+)"', block))


def _current_tools(text):
    block = text[text.index("property var currentTools:"):]
    block = block[:block.index("return []")]
    return set(re.findall(r'"([^"]+)"', block))


class TestTheThreeGroups:
    def test_the_menu_is_split_into_three_labelled_groups(self, tools_menu):
        for title in ("Tools", "Composite tools", "Saved workflows"):
            assert f'text: "— {title} —"' in tools_menu, title

    def test_the_headers_are_disabled_entries_not_submenus(self, tools_menu):
        """Keeping one flat list is what preserves the per-tab visibility on
        every entry; submenus would have to re-implement it."""
        header = tools_menu[tools_menu.index('text: "Composite tools"'):]
        assert "enabled: false" in header[:200]

    def test_the_composite_group_is_the_composite_tools(self, tools_menu):
        assert set(_group(tools_menu, "Composite tools")) == {
            "Map Generator", "Confinement Analysis", "Spectral Features",
            "Confinement Designer", "Line Scan Designer",
            "Quantum Well Solver", "Quantum Dot Solver", "Multi-Peak Fitting",
            "Detect Bandgap & Doping", "Dirac Point Estimator"}

    def test_the_solvers_are_composite_too(self, tools_menu):
        """Each does several things in one pass — build the potential, solve
        it, group the levels into shells, compare with the measurement."""
        composite = set(_group(tools_menu, "Composite tools"))

        assert {"Quantum Well Solver", "Quantum Dot Solver"} <= composite

    def test_a_simple_tool_is_in_the_first_group(self, tools_menu):
        simple = set(_group(tools_menu, "Tools"))

        assert {"Curve Smoothing", "Derivative Calculator", "Integration Utility",
                "Truncate Data"} <= simple
        assert "Map Generator" not in simple

    def test_the_designer_tools_are_composite(self, tools_menu):
        """They find peaks, split branches, search and pair in one pass —
        several operations with decisions between them."""
        composite = set(_group(tools_menu, "Composite tools"))

        assert {"Confinement Designer", "Line Scan Designer"} <= composite

    def test_the_groups_are_the_whole_menu(self, tools_menu):
        entries = _menu_entries(tools_menu)
        grouped = (_group(tools_menu, "Tools")
                   + _group(tools_menu, "Composite tools"))

        assert sorted(entries) == sorted(grouped)

    def test_no_tool_is_in_both_groups(self, tools_menu):
        simple = _group(tools_menu, "Tools")
        composite = _group(tools_menu, "Composite tools")

        assert set(simple).isdisjoint(composite)


class TestTheMenuMatchesTheCode:
    def test_every_entry_has_a_tool_behind_it(self, main_qml, tools_menu):
        """A menu entry with no file opens the generic placeholder, which
        looks like a broken tool rather than a missing one."""
        tool_map = _tool_map(main_qml)
        missing = [name for name in _menu_entries(tools_menu)
                   if name not in tool_map]

        assert missing == []

    def test_every_tool_file_the_menu_names_exists(self, main_qml, tools_menu):
        tool_map = _tool_map(main_qml)
        for name in _menu_entries(tools_menu):
            path = (MAIN_QML.parent / tool_map[name]).resolve()
            assert path.exists(), f"{name} -> {tool_map[name]}"

    def test_every_tool_in_the_palette_list_is_in_the_menu(self, main_qml,
                                                           tools_menu):
        """`currentTools` feeds the tool palette panel; a tool in one and not
        the other is reachable from only half the app."""
        listed = _current_tools(main_qml)
        entries = set(_menu_entries(tools_menu))

        assert listed - entries == set()

    def test_the_composite_tools_that_are_also_nodes_are_flagged(self):
        """The menu grouping and the palette badge have to agree about which
        tools are composite, or the taxonomy means nothing."""
        from src.backend.workflow_engine import TOOL_DEFINITIONS

        # Menu name -> node name, for the composites that have a node.
        pairs = {"Map Generator": "MapGenerator",
                 "Confinement Analysis": "ConfinementAnalysis",
                 "Spectral Features": "SpectralFeatures",
                 "Line Scan Designer": "ConfinementDesign",
                 "Detect Bandgap & Doping": "DetectBandgapDoping",
                 "Dirac Point Estimator": "DiracPointEstimator"}
        for menu_name, node_name in pairs.items():
            assert TOOL_DEFINITIONS[node_name].get('composite'), menu_name


class TestTheSavedWorkflowsGroup:
    def test_the_group_is_filled_from_the_saved_workflows(self, main_qml):
        assert "savedWorkflowsModel" in main_qml
        assert "getSavedWorkflows()" in main_qml

    def test_clicking_one_opens_the_runner(self, main_qml, tools_menu):
        assert "openSavedWorkflowRunner" in tools_menu
        assert "SavedWorkflowRunner.qml" in main_qml

    def test_an_empty_project_says_so(self, tools_menu):
        assert "none yet" in tools_menu

    def test_both_menus_are_refreshed_together(self, main_qml):
        """The same list appears under Workflows (opens the editor) and under
        Tools (runs it); one refresh has to fill both."""
        refresh = main_qml[main_qml.index("function refreshProjectWorkflows"):]
        refresh = refresh[:refresh.index("\n    }")]

        assert "projectWorkflowsModel.append" in refresh
        assert "savedWorkflowsModel.append" in refresh


class TestTheRunnerLoads:
    def test_it_instantiates_against_a_stub_backend(self):
        """The runner is opened from a menu entry, so a broken binding in it
        would only show up on a click."""
        pytest.importorskip("PySide6.QtQuick")
        from PySide6.QtCore import QObject, QUrl, Signal, Slot
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlComponent, QQmlEngine

        class StubWorkflowManager(QObject):
            workflowExecutionStarted = Signal(str)
            workflowExecutionProgress = Signal(int, int, str)
            workflowExecutionCompleted = Signal(str, bool, 'QVariantList')

            def __init__(self):
                super().__init__()
                self.runs = []

            @Slot(str, 'QVariantList')
            def runSavedWorkflow(self, path, names):
                self.runs.append((path, list(names)))

            @Slot()
            def cancelExecution(self):
                pass

        class StubBackend(QObject):
            dataLoaded = Signal(str)

            def __init__(self):
                super().__init__()
                self._manager = StubWorkflowManager()

            @Slot(result='QVariantList')
            def getDatasetList(self):
                return ["A", "B"]

            def get_manager(self):
                return self._manager

            workflowManager = property(get_manager)

        QGuiApplication.instance() or QGuiApplication([])
        engine = QQmlEngine()
        engine.addImportPath(str(QML_ROOT))
        backend = StubBackend()
        engine.rootContext().setContextProperty("backend", backend)

        component = QQmlComponent(engine, QUrl.fromLocalFile(str(RUNNER_QML)))
        assert component.status() == QQmlComponent.Ready, component.errorString()
        item = component.create()
        assert item is not None, component.errorString()

        # Nothing selected: Run must not fire.
        item.setProperty("workflowPath", "/tmp/whatever.flow")
        item.metaObject().invokeMethod(item, "run")
        assert backend._manager.runs == []

        item.deleteLater()
