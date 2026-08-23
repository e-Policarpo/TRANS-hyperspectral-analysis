"""
Tests for running a saved workflow as a tool.

A saved workflow is a composite tool nobody had to code; the runner is what
makes it one. What has to hold: the chain runs with the parameters it was
saved with, only the datasets are asked for, and a workflow that will not
load says so instead of raising into the UI.

Also covers the ``composite`` flag the palette badges tools with — the flag
that makes "you could rebuild this from the simple nodes" a claim a user can
check rather than a slogan.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import json
import os
import re

import numpy as np
import pandas as pd
import pytest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.backend.workflow_engine import (
    TOOL_DEFINITIONS, Connection, Workflow, create_node_from_tool,
    get_tool_categories,
)
from src.backend.workflow_manager import WorkflowManager


def _dataset(n_spectra=3):
    x = np.linspace(-1.0, 1.0, 64)
    columns = {f"S{i}": np.sin(x * (i + 1)) for i in range(n_spectra)}
    return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
        source_type='sts', dimensions=(n_spectra, 1), scan_mode='point',
        units={'independent': 'V'}, additional_info={}))


@pytest.fixture
def backend(tmp_path):
    """A backend with just enough for the executor to run against."""
    from src.backend.tool_implementations import ToolImplementations

    class Backend(ToolImplementations):
        def __init__(self):
            self._datasets = {'A': _dataset(), 'B': _dataset()}
            self._output_base_dir = tmp_path / "outputs"
            self._output_base_dir.mkdir(exist_ok=True)
            self.errorOccurred = Mock()
            self.dataLoaded = Mock()
            self._workflow_mode = False
            self._suppress_auto_open = False

        def _ensure_output_dir(self, subdir):
            path = self._output_base_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            return path

        def _sanitize_filename(self, name):
            return re.sub(r'\W+', '_', name) or "unnamed"

        def _extract_clean_base_name(self, name):
            return name

        def _apply_naming_convention(self, dataset_name, operation="", preview=False):
            return self._sanitize_filename(f"{dataset_name}_{operation}")

    return Backend()


@pytest.fixture
def manager(backend, tmp_path, monkeypatch):
    manager = WorkflowManager(backend)
    monkeypatch.setattr(manager, "_get_workflows_dir", lambda: tmp_path / "workflows")
    (tmp_path / "workflows").mkdir(exist_ok=True)
    return manager


def _saved_chain(tmp_path, name="Smooth it", dataset="A"):
    """A two-node .flow on disk: a dataset in, a smoothed dataset out."""
    workflow = Workflow(id="wf_saved", name=name)
    source = create_node_from_tool("DatasetInput", 0, 0)
    source.parameters['dataset_name'] = dataset
    smooth = create_node_from_tool("CurveSmoothing", 200, 0)
    output = create_node_from_tool("DatasetOutput", 400, 0)
    output.parameters['output_name'] = "Smoothed"
    for node in (source, smooth, output):
        workflow.add_node(node)
    workflow.add_connection(Connection(
        id="c1", source_node_id=source.id, source_port_id="dataset",
        target_node_id=smooth.id, target_port_id="dataset"))
    workflow.add_connection(Connection(
        id="c2", source_node_id=smooth.id, source_port_id="smoothed",
        target_node_id=output.id, target_port_id="dataset"))

    path = tmp_path / "workflows" / "saved.flow"
    path.write_text(json.dumps(workflow.to_dict()), encoding="utf-8")
    return path


class TestTheCompositeFlag:
    """One flag, both consumers: the menu grouping and the palette badge."""

    def test_the_composite_tools_are_marked(self):
        expected = {"MapGenerator", "ConfinementAnalysis", "SpectralFeatures",
                    "ConfinementDesign", "DetectBandgapDoping",
                    "DiracPointEstimator"}
        marked = {name for name, node in TOOL_DEFINITIONS.items()
                  if node.get('composite')}

        assert marked == expected

    def test_a_simple_node_is_not_marked(self):
        """The distinction is only worth drawing if it excludes something."""
        for name in ("CurveSmoothing", "Derivative", "Integration",
                     "PeakFinder", "MapAssembly", "BaselineEstimate"):
            assert not TOOL_DEFINITIONS[name].get('composite'), name

    def test_the_categories_carry_it_to_the_palette(self):
        categories = {c['category']: c for c in get_tool_categories()}

        assert "ConfinementAnalysis" in categories['Analysis']['composite']
        assert "MapGenerator" in categories['Visualization']['composite']
        assert categories['Processing']['composite'] == []

    def test_every_category_answers_the_question(self):
        """The palette reads the key unconditionally; a missing one would be
        `undefined` in QML and badge nothing, silently."""
        for category in get_tool_categories():
            assert 'composite' in category, category['category']
            assert set(category['composite']) <= set(category['tools'])

    def test_compositeness_is_not_a_category(self):
        """Category means domain; being composite is orthogonal to it, and
        moving these into a category of their own would lose the domain."""
        categories = {c['category'] for c in get_tool_categories()}

        assert "Composite" not in categories


class TestPointingAWorkflowAtDatasets:
    def test_it_sets_both_dataset_keys(self, manager):
        """``dataset_names`` is the selection; ``dataset_name`` is the first
        pick, which older workflows and the validator still read."""
        workflow = Workflow(id="wf", name="W")
        node = create_node_from_tool("DatasetInput", 0, 0)
        workflow.add_node(node)

        assert manager._set_workflow_datasets(workflow, ["A", "B"]) == 1
        assert node.parameters['dataset_names'] == ["A", "B"]
        assert node.parameters['dataset_name'] == "A"

    def test_every_input_node_is_pointed_at_them(self, manager):
        workflow = Workflow(id="wf", name="W")
        for _ in range(3):
            workflow.add_node(create_node_from_tool("DatasetInput", 0, 0))
        workflow.add_node(create_node_from_tool("CurveSmoothing", 0, 0))

        assert manager._set_workflow_datasets(workflow, ["A"]) == 3

    def test_a_workflow_with_no_input_node_is_left_alone(self, manager):
        workflow = Workflow(id="wf", name="W")
        workflow.add_node(create_node_from_tool("CurveSmoothing", 0, 0))

        assert manager._set_workflow_datasets(workflow, ["A"]) == 0


class TestRunningASavedWorkflow:
    def test_it_runs_the_chain_and_reports_success(self, manager, backend, tmp_path):
        finished = []
        manager.workflowExecutionCompleted.connect(
            lambda name, ok, errors: finished.append((name, ok, list(errors))))

        manager.runSavedWorkflow(str(_saved_chain(tmp_path)), ["A"])

        assert finished, "the run never reported"
        name, ok, errors = finished[-1]
        assert name == "Smooth it"
        assert ok is True, errors

    def test_the_result_lands_in_the_project(self, manager, backend, tmp_path):
        before = set(backend._datasets)
        manager.runSavedWorkflow(str(_saved_chain(tmp_path)), ["A"])

        produced = set(backend._datasets) - before
        assert produced, "the workflow produced nothing"
        assert not any(str(n).startswith('_wf_') for n in backend._datasets)

    def test_it_runs_over_the_datasets_that_were_picked(self, manager, backend,
                                                        tmp_path):
        """The saved chain names one dataset; the runner's selection wins."""
        path = _saved_chain(tmp_path, dataset="A")
        before = set(backend._datasets)
        manager.runSavedWorkflow(str(path), ["B"])

        produced = {str(n) for n in set(backend._datasets) - before}
        assert any("B" in name for name in produced), produced

    def test_several_datasets_each_get_a_pass(self, manager, backend, tmp_path):
        before = set(backend._datasets)
        manager.runSavedWorkflow(str(_saved_chain(tmp_path)), ["A", "B"])

        produced = {str(n) for n in set(backend._datasets) - before}
        assert len(produced) >= 2, produced

    def test_it_announces_the_start(self, manager, tmp_path):
        started = []
        manager.workflowExecutionStarted.connect(started.append)

        manager.runSavedWorkflow(str(_saved_chain(tmp_path)), ["A"])

        assert started == ["Smooth it"]

    def test_running_one_does_not_disturb_the_editor(self, manager, tmp_path):
        """The user's open workflow must survive someone running a saved one."""
        open_id = manager.createWorkflow("Being edited")
        manager.runSavedWorkflow(str(_saved_chain(tmp_path)), ["A"])

        assert manager.current_workflow.id == open_id
        assert set(manager.workflows) == {open_id}

    def test_a_missing_file_is_reported_not_raised(self, manager):
        finished = []
        manager.workflowExecutionCompleted.connect(
            lambda name, ok, errors: finished.append((name, ok, list(errors))))

        manager.runSavedWorkflow("/nowhere/at/all.flow", ["A"])

        assert finished and finished[-1][1] is False
        assert "Could not load" in finished[-1][2][0]

    def test_a_corrupt_file_is_reported_not_raised(self, manager, tmp_path):
        path = tmp_path / "workflows" / "broken.flow"
        path.write_text("{not json", encoding="utf-8")
        finished = []
        manager.workflowExecutionCompleted.connect(
            lambda name, ok, errors: finished.append((name, ok, list(errors))))

        manager.runSavedWorkflow(str(path), ["A"])

        assert finished and finished[-1][1] is False

    def test_it_goes_to_the_worker_when_there_is_one(self, manager, backend,
                                                     tmp_path):
        """A chain ending in a per-spectrum search is minutes: it must not
        run on the GUI thread."""
        submitted = []

        class Worker:
            def submit(self, **kwargs):
                submitted.append(kwargs)

        backend.worker_manager = Worker()
        manager.runSavedWorkflow(str(_saved_chain(tmp_path)), ["A"])

        assert submitted, "the run stayed on the calling thread"
        assert submitted[-1]['operation'] == manager._run_workflow_object
        assert submitted[-1]['workflow'].name == "Smooth it"

    def test_the_saved_workflows_list_is_what_the_menu_shows(self, manager,
                                                             tmp_path):
        _saved_chain(tmp_path)
        listed = manager.getSavedWorkflows()

        assert [w['name'] for w in listed] == ["Smooth it"]
        assert listed[0]['path'].endswith("saved.flow")
