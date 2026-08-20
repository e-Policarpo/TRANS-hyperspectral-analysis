"""
Tests for running a workflow once per selected dataset.

A DatasetInput node holding several datasets makes the executor run the
whole graph one pass per dataset, in the order picked, with each pass's
outputs named after its own input.
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import Mock

from src.backend.workflow_manager import WorkflowManager, WorkflowExecutor
from src.models.spectral_data import SpectralData, SpectralMetadata


def make_dataset(offset: float = 0.0) -> SpectralData:
    x = np.linspace(-1, 1, 25)
    df = pd.DataFrame({'V': x, 'S0': np.sin(x) + offset, 'S1': np.cos(x) + offset})
    meta = SpectralMetadata(source_type='test', dimensions=(1, 2),
                            scan_mode='forward',
                            units={'independent': 'V', 'dependent': 'nA'})
    return SpectralData(df, meta)


class StubBackend:
    """Backend stand-in with the naming helpers the executor relies on."""

    def __init__(self, tmp_path):
        self._datasets = {
            'Alpha': make_dataset(0.0),
            'Beta': make_dataset(1.0),
            'Gamma': make_dataset(2.0),
        }
        self._output_base_dir = tmp_path / "outputs"
        self._output_base_dir.mkdir(exist_ok=True)
        self._workflow_mode = False
        self._suppress_auto_open = False
        self._naming_convention = "[dataset_name]"
        self.dataLoaded = Mock()
        self.errorOccurred = Mock()
        self.derivative_calls = []

    # -- naming helpers (same contract as AppBackend) ----------------------
    def _extract_clean_base_name(self, name: str) -> str:
        import re
        m = re.match(r'^_wf_(.+?)_[a-f0-9]{6}$', name)
        if m:
            name = m.group(1)
        for suffix in ('_derivative', '_smooth', '_integrate'):
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name

    def _apply_naming_convention(self, dataset_name: str, operation: str = "",
                                 preview: bool = False) -> str:
        base = self._extract_clean_base_name(dataset_name)
        return f"{base}_{operation}" if operation else base

    def _ensure_output_dir(self, subdir):
        path = self._output_base_dir / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- the one tool these workflows use ----------------------------------
    def calculate_derivative(self, dataset_name, order=1,
                             smooth_before=True, smooth_after=True):
        self.derivative_calls.append(dataset_name)
        source = self._datasets[dataset_name]
        base = self._extract_clean_base_name(dataset_name)
        label = "1st Derivative" if order == 1 else "2nd Derivative"
        self._datasets[f"{base} - {label}"] = source
        return str(self._output_base_dir / f"{base}_deriv.csv")


@pytest.fixture
def backend(tmp_path):
    return StubBackend(tmp_path)


@pytest.fixture
def manager(backend):
    return WorkflowManager(backend)


def build_pipeline(manager, datasets, output_name="Result"):
    """DatasetInput -> Derivative -> DatasetOutput over `datasets`."""
    wf_id = manager.createWorkflow("Batch Test")
    src = manager.addNode(wf_id, "DatasetInput", 0, 0)
    manager.setNodeParameter(wf_id, src, "dataset_names", list(datasets))
    manager.setNodeParameter(wf_id, src, "dataset_name", datasets[0])

    deriv = manager.addNode(wf_id, "Derivative", 200, 0)
    out = manager.addNode(wf_id, "DatasetOutput", 400, 0)
    manager.setNodeParameter(wf_id, out, "output_name", output_name)

    manager.addConnection(wf_id, src, "dataset", deriv, "dataset")
    manager.addConnection(wf_id, deriv, "derivative", out, "dataset")
    return wf_id, src


class TestBatchPlan:
    def test_single_dataset_is_one_pass(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha"])
        executor = WorkflowExecutor(backend)
        plan = executor._dataset_batches(manager.workflows[wf_id])
        assert len(plan) == 1

    def test_one_pass_per_selected_dataset_in_order(self, manager, backend):
        wf_id, src = build_pipeline(manager, ["Gamma", "Alpha", "Beta"])
        executor = WorkflowExecutor(backend)
        plan = executor._dataset_batches(manager.workflows[wf_id])
        assert [p[src] for p in plan] == ["Gamma", "Alpha", "Beta"]

    def test_legacy_single_dataset_name_still_works(self, manager, backend):
        """Workflows saved before multi-select carry only 'dataset_name'."""
        wf_id = manager.createWorkflow("Legacy")
        src = manager.addNode(wf_id, "DatasetInput", 0, 0)
        manager.setNodeParameter(wf_id, src, "dataset_name", "Beta")

        executor = WorkflowExecutor(backend)
        plan = executor._dataset_batches(manager.workflows[wf_id])
        assert plan == [{src: "Beta"}]

    def test_single_selection_input_feeds_every_pass(self, manager, backend):
        wf_id, multi = build_pipeline(manager, ["Alpha", "Beta"])
        other = manager.addNode(wf_id, "DatasetInput", 0, 300)
        manager.setNodeParameter(wf_id, other, "dataset_name", "Gamma")

        executor = WorkflowExecutor(backend)
        plan = executor._dataset_batches(manager.workflows[wf_id])
        assert [p[multi] for p in plan] == ["Alpha", "Beta"]
        assert [p[other] for p in plan] == ["Gamma", "Gamma"]


class TestBatchExecution:
    def test_runs_once_per_selected_dataset(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta"])
        result = WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        assert result['success'], result['errors']
        assert len(backend.derivative_calls) == 2

    def test_passes_run_in_selection_order(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Gamma", "Alpha"])
        WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        # The temp dataset name carries its source, so the call order shows
        # which dataset each pass worked on.
        sources = [backend._extract_clean_base_name(n) for n in backend.derivative_calls]
        assert sources == ["Gamma", "Alpha"]

    def test_outputs_are_named_after_their_input(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta"], output_name="Result")
        WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        assert "Alpha_Result" in backend._datasets
        assert "Beta_Result" in backend._datasets

    def test_outputs_hold_their_own_input_data(self, manager, backend):
        """Pass 2 must not overwrite pass 1's result."""
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta"])
        WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        alpha = backend._datasets["Alpha_Result"].data['S0'].values
        beta = backend._datasets["Beta_Result"].data['S0'].values
        assert not np.allclose(alpha, beta)

    def test_results_are_keyed_per_dataset(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta"])
        result = WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        assert len(result['results']) == 2
        assert any("Alpha" in k for k in result['results'])
        assert any("Beta" in k for k in result['results'])

    def test_intermediates_are_cleaned_up_after_all_passes(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta"])
        WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        leftovers = [n for n in backend._datasets if n.startswith('_wf_')]
        assert leftovers == []
        assert "Alpha - 1st Derivative" not in backend._datasets

    def test_every_output_reaches_the_project_browser(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta"])
        WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        emitted = {call.args[0] for call in backend.dataLoaded.emit.call_args_list}
        assert {"Alpha_Result", "Beta_Result"} <= emitted

    def test_single_dataset_behaves_as_before(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha"])
        result = WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        assert result['success'], result['errors']
        assert len(backend.derivative_calls) == 1
        assert "Alpha_Result" in backend._datasets
        # No batch suffix on the results key for a single-dataset run
        assert list(result['results']) == ["Result"]

    def test_progress_covers_every_pass(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta", "Gamma"])
        seen = []
        WorkflowExecutor(backend).execute(
            manager.workflows[wf_id],
            progress_callback=lambda cur, total, msg: seen.append((cur, total)))

        totals = {t for _, t in seen}
        assert totals == {9}          # 3 nodes x 3 datasets
        assert seen[-1][0] == 9

    def test_fixed_output_name_still_yields_one_dataset_per_input(self, manager, backend):
        """A naming convention without [dataset_name] must not collapse the
        passes onto a single output."""
        backend._apply_naming_convention = lambda name, operation="", preview=False: "Fixed"
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta"])
        WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        produced = [n for n in backend._datasets if n.startswith("Fixed")]
        assert len(produced) == 2


class TestBatchCancellation:
    def test_cancelling_stops_the_remaining_datasets(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta", "Gamma"])
        executor = WorkflowExecutor(backend)

        # Cancel as soon as the first dataset has been through the tool.
        original = backend.calculate_derivative

        def cancel_after_first(*args, **kwargs):
            result = original(*args, **kwargs)
            executor.cancel()
            return result

        backend.calculate_derivative = cancel_after_first
        result = executor.execute(manager.workflows[wf_id])

        assert len(backend.derivative_calls) == 1
        assert not result['success']
        assert any('cancel' in e.lower() for e in result['errors'])


class TestNoAutoOpenAcrossPasses:
    """A workflow run over several datasets registers its outputs without
    opening a window per pass."""

    def test_multi_dataset_run_suppresses_auto_open(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta"])
        seen = []
        original = backend.calculate_derivative
        backend.calculate_derivative = lambda *a, **k: (
            seen.append(backend._suppress_auto_open) or original(*a, **k))

        WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        assert seen == [True, True]
        assert backend._suppress_auto_open is False   # cleared at the end

    def test_single_dataset_run_leaves_auto_open_alone(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha"])
        seen = []
        original = backend.calculate_derivative
        backend.calculate_derivative = lambda *a, **k: (
            seen.append(backend._suppress_auto_open) or original(*a, **k))

        WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        assert seen == [False]

    def test_the_flag_is_cleared_when_a_pass_fails(self, manager, backend):
        wf_id, _ = build_pipeline(manager, ["Alpha", "Beta"])

        def explode(*a, **k):
            raise RuntimeError("tool failed")

        backend.calculate_derivative = explode
        WorkflowExecutor(backend).execute(manager.workflows[wf_id])

        assert backend._suppress_auto_open is False
