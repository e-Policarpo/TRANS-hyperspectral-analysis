"""
The Tools menu's sections, checked against the code they point at.

The menu and the tool palette are generated from components/ToolCatalog.js:
a tool can be listed there with no file behind it, or have a file and never
appear, and neither shows up until someone clicks. This reads the catalog and
Main.qml and holds them to each other and to the taxonomy the sections claim.

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


CATALOG_JS = QML_ROOT / "components" / "ToolCatalog.js"

LEVEL_RANK = {"basic": 0, "intermediate": 1, "advanced": 2}


def _catalog():
    """The sections of ToolCatalog.js: [(title, level, [(tool, tabs)])].

    The menu and the palette are both generated from this file, so it is
    the thing to hold to the code — a hand-written entry no longer exists.
    """
    text = CATALOG_JS.read_text(encoding="utf-8")
    text = text[text.index("var SECTIONS = ["):text.index("// Sections with only the tools")]
    sections = []
    for block in re.split(r"\n    \{\n", text)[1:]:
        title = re.search(r'title: "([^"]+)"', block).group(1)
        level = re.search(r'level: "([^"]+)"', block).group(1)
        tools = [(name, [int(t) for t in tabs.split(",")])
                 for name, tabs in re.findall(r'\{ name: "([^"]+)",\s*tabs: \[([0-9, ]+)\] \}', block)]
        sections.append((title, level, tools))
    return sections


def _catalog_tools():
    return [name for _, _, tools in _catalog() for name, _ in tools]


def _tool_map(text):
    block = text[text.index("var toolMap = {"):]
    block = block[:block.index("}")]
    return dict(re.findall(r'"([^"]+)": "([^"]+)"', block))


class TestTheSections:
    def test_the_menu_and_the_palette_are_built_from_the_catalog(self, main_qml, tools_menu):
        """One list, two views: a tool in the menu and not the palette (or
        the reverse) is reachable from only half the app."""
        assert "ToolCatalog.menuRows()" in tools_menu
        assert "ToolCatalog.toolsForTab(currentTabIndex)" in main_qml
        assert "ToolCatalog.sectionsForTab(currentTabIndex)" in main_qml
        assert 'sections: currentToolSections' in main_qml

    def test_the_headers_are_disabled_entries_not_submenus(self, tools_menu):
        """Keeping one flat list is what preserves the per-tab visibility on
        every entry; submenus would have to re-implement it."""
        assert "enabled: !isHeader" in tools_menu
        assert "visible: modelData.tabs.indexOf(currentTabIndex) >= 0" in tools_menu

    def test_the_sections_are_ordered_by_complexity(self):
        levels = [LEVEL_RANK[level] for _, level, _ in _catalog()]
        assert levels == sorted(levels)
        assert levels[0] == 0 and levels[-1] == 2

    def test_the_sections_group_by_type(self):
        titles = [title for title, _, _ in _catalog()]
        assert titles == ["Prepare", "Transform", "View", "Fit and features",
                          "Maps", "Confinement"]

    def test_no_tool_is_in_two_sections(self):
        tools = _catalog_tools()
        assert len(tools) == len(set(tools))

    def test_a_simple_tool_is_in_a_basic_section(self):
        by_tool = {name: level for _, level, tools in _catalog() for name, _ in tools}
        for name in ("Curve Smoothing", "Derivative Calculator", "Integration Utility",
                     "Truncate Data", "Unit Converter"):
            assert by_tool[name] == "basic", name

    def test_the_composite_analyses_are_advanced(self):
        """Background, peak search, a fit and a model selection in one pass —
        several operations with decisions between them."""
        by_tool = {name: level for _, level, tools in _catalog() for name, _ in tools}
        for name in ("Confinement Analysis", "Confinement Dimensionality",
                     "Confinement Designer", "Line Scan Designer",
                     "Quantum Well Solver", "Quantum Dot Solver"):
            assert by_tool[name] == "advanced", name

    def test_the_sunset_tools_are_gone(self):
        tools = set(_catalog_tools())
        for name in ("Image Smoothing", "Peak Indexing", "Spatial Average",
                     "Detect Bandgap & Doping", "Dirac Point Estimator",
                     "Spectral Axis Converter", "Curve Fitting", "Curve Analysis",
                     "Background Subtraction"):
            assert name not in tools, name

    def test_every_tool_is_listed_on_a_tab(self):
        for _, _, tools in _catalog():
            for name, tabs in tools:
                assert tabs and set(tabs) <= {0, 1}, name


class TestTheMenuMatchesTheCode:
    def test_every_entry_has_a_tool_behind_it(self, main_qml):
        """A menu entry with no file opens the generic placeholder, which
        looks like a broken tool rather than a missing one."""
        tool_map = _tool_map(main_qml)
        missing = [name for name in _catalog_tools() if name not in tool_map]

        assert missing == []

    def test_every_tool_file_the_catalog_names_exists(self, main_qml):
        tool_map = _tool_map(main_qml)
        for name in _catalog_tools():
            path = (MAIN_QML.parent / tool_map[name]).resolve()
            assert path.exists(), f"{name} -> {tool_map[name]}"

    def test_every_tool_file_is_in_the_catalog(self, main_qml):
        """The reverse: a file the map knows but the catalog does not list is
        unreachable from the UI."""
        tool_map = _tool_map(main_qml)
        assert set(tool_map) - set(_catalog_tools()) == set()

    def test_the_composite_tools_that_are_also_nodes_are_flagged(self):
        """The menu grouping and the palette badge have to agree about which
        tools are composite, or the taxonomy means nothing."""
        from src.backend.workflow_engine import TOOL_DEFINITIONS

        # Menu name -> node name, for the composites that have a node.
        pairs = {"Map Generator": "MapGenerator",
                 "Confinement Analysis": "ConfinementAnalysis",
                 "Spectral Features": "SpectralFeatures",
                 "Line Scan Designer": "ConfinementDesign"}
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
