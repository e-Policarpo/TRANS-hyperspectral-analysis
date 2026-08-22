"""
Tests for the Baseline Estimate node: the whole estimate_baseline family
exposed to a workflow, background and corrected spectra out of one pass.
"""

import re

import numpy as np
import pandas as pd
import pytest
from unittest.mock import Mock

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.backend.workflow_engine import (
    Workflow, Connection, TOOL_DEFINITIONS, create_node_from_tool,
    get_tool_categories,
)
from src.backend.workflow_manager import WorkflowExecutor
from src.processing.peak_detection import BASELINE_KINDS, estimate_baseline


class MockTask:
    """Mock task object for testing."""
    cancelled = False
    progress = 0


class CancelledTask:
    """A task the user has already cancelled."""
    cancelled = True
    progress = 0


@pytest.fixture
def sts_data():
    """STS-like spectra: exponential band edges plus small in-gap states."""
    x = np.linspace(-0.6, 0.6, 256)
    band_edges = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)
    columns = {}
    for n in range(4):
        y = band_edges.copy()
        for centre in (-0.25, 0.08):
            y = y + 1.2e-8 * np.exp(-0.5 * ((x - centre) / 0.008) ** 2)
        columns[f"R{n + 1}"] = y
    df = pd.DataFrame({"V": x, **columns})
    metadata = SpectralMetadata(
        source_type='sts', dimensions=(4, 1), scan_mode='line',
        units={'x': 'V', 'y': 'nA'},
        additional_info={'spatial_layout': 'line',
                         'position_m': [0.0, 1e-9, 2e-9, 3e-9],
                         'position_step_m': 1e-9})
    return SpectralData(data=df, metadata=metadata)


@pytest.fixture
def tool_impl(tmp_path):
    """A real ToolImplementations with the project plumbing stubbed out."""
    from src.backend.tool_implementations import ToolImplementations

    class MockBackend(ToolImplementations):
        def __init__(self):
            self._datasets = {}
            self._output_base_dir = tmp_path / "outputs"
            self._output_base_dir.mkdir(exist_ok=True)
            self.errorOccurred = Mock()
            self.dataLoaded = Mock()
            self._workflow_mode = False
            self._naming_convention = "[dataset_name]"
            self._naming_index_start = 1
            self._naming_date_format = "dd-mm-yyyy"
            self._current_file_index = 1

        def _ensure_output_dir(self, subdir):
            path = self._output_base_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            return path

        def _sanitize_filename(self, name):
            safe = "".join(c for c in name
                           if c.isalnum() or c in (' ', '-', '_', '.')).strip()
            return safe.replace(' ', '_') or "unnamed"

        def _extract_clean_base_name(self, name):
            wf_match = re.match(
                r'^_wf_(.+?)(?:_(?:integrate|derivative|smooth|truncate|baseline'
                r'|discretize))?_[a-f0-9]{6}$', name)
            if wf_match:
                name = wf_match.group(1)
            return ' '.join(name.replace('_', ' ').split())

        def _apply_naming_convention(self, dataset_name, operation="", preview=False):
            result = self._naming_convention.replace(
                "[dataset_name]", self._extract_clean_base_name(dataset_name))
            if operation:
                result = f"{result}_{operation}"
            return self._sanitize_filename(result)

    return MockBackend()


class TestBaselineEstimateNodeDefinition:
    """The node as the palette and the executor see it."""

    def test_node_is_registered_in_the_processing_category(self):
        node_def = TOOL_DEFINITIONS["BaselineEstimate"]
        assert node_def["category"] == "Processing"
        assert node_def["display_name"] == "Baseline Estimate"

    def test_takes_a_single_dataset_input(self):
        inputs = TOOL_DEFINITIONS["BaselineEstimate"]["inputs"]
        assert [i["id"] for i in inputs] == ["dataset"]
        assert inputs[0]["port_type"] == "dataset"
        assert inputs[0]["required"] is True

    def test_ports_match_what_the_dispatch_writes(self):
        outs = {o["id"]: o for o in TOOL_DEFINITIONS["BaselineEstimate"]["outputs"]}
        assert set(outs) == {"corrected", "baseline", "coefficients"}
        for port in ("corrected", "baseline"):
            assert outs[port]["port_type"] == "dataset", port
        # Coefficients are one row per spectrum, so they drive a Map Generator.
        assert outs["coefficients"]["port_type"] == "flat_data"

    def test_parameters_cover_the_estimate_baseline_signature(self):
        params = TOOL_DEFINITIONS["BaselineEstimate"]["parameters"]
        assert set(params) == {"method", "degree", "iterations", "direction",
                               "als_lambda", "als_p", "endpoint_points", "basis"}

    def test_parameter_names_match_the_engine(self):
        """They are handed to estimate_baseline as keyword arguments, so a
        typo here would be a TypeError at run time rather than a warning."""
        import inspect
        signature = inspect.signature(estimate_baseline)
        params = set(TOOL_DEFINITIONS["BaselineEstimate"]["parameters"])
        # 'method' is the node's name for the engine's 'kind'.
        assert (params - {"method"}) <= set(signature.parameters)

    def test_offers_every_method_the_engine_has(self):
        options = TOOL_DEFINITIONS["BaselineEstimate"]["parameters"]["method"]["options"]
        assert set(options) == set(BASELINE_KINDS)

    def test_defaults_match_confinement_analysis(self):
        """The point of the node is that a decomposed chain reproduces the
        composite, which it cannot do if the two start from different fits."""
        params = TOOL_DEFINITIONS["BaselineEstimate"]["parameters"]
        confinement = TOOL_DEFINITIONS["ConfinementAnalysis"]["parameters"]
        assert params["method"]["default"] == confinement["baseline"]["default"]
        assert params["degree"]["default"] == confinement["baseline_degree"]["default"]
        assert params["basis"]["default"] == confinement["baseline_basis"]["default"]
        assert params["iterations"]["default"] == confinement["baseline_iterations"]["default"]

    def test_sits_next_to_curve_fitting_in_the_palette(self):
        processing = next(c["tools"] for c in get_tool_categories()
                          if c["category"] == "Processing")
        assert abs(processing.index("BaselineEstimate")
                   - processing.index("CurveFitting")) == 1

    def test_created_node_carries_the_defaults(self):
        node = create_node_from_tool("BaselineEstimate", 0, 0)
        assert node.parameters["method"] == "arpls"
        assert node.parameters["basis"] == "power"

    def test_outputs_connect_to_the_matching_output_nodes(self):
        wf = Workflow(id="wf_be", name="Baseline WF")
        node = create_node_from_tool("BaselineEstimate", 0, 0)
        dataset_out = create_node_from_tool("DatasetOutput", 300, 0)
        map_gen = create_node_from_tool("MapGenerator", 300, 200)
        for n in (node, dataset_out, map_gen):
            wf.add_node(n)

        corrected = Connection(
            id="c1", source_node_id=node.id, source_port_id="corrected",
            target_node_id=dataset_out.id, target_port_id="dataset")
        assert wf.add_connection(corrected) is True

        coefficients = Connection(
            id="c2", source_node_id=node.id, source_port_id="coefficients",
            target_node_id=map_gen.id, target_port_id="flat_data")
        assert wf.validate_connection(coefficients) is True


class TestEstimateDatasetBaseline:
    """The backend method."""

    def test_corrected_is_the_raw_data_minus_the_background(self, tool_impl, sts_data):
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'arpls'})

        raw = sts_data.spectra.values
        corrected = result['corrected'].spectra.values
        background = result['baseline'].spectra.values
        assert np.allclose(corrected, raw - background)

    def test_registers_the_corrected_and_background_datasets(self, tool_impl, sts_data):
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'arpls'})

        assert result['dataset_names'] == {
            'Baseline Corrected': 'Source - Baseline Corrected',
            'Baseline': 'Source - Baseline',
        }
        for name in result['dataset_names'].values():
            assert name in tool_impl._datasets
            tool_impl.dataLoaded.emit.assert_any_call(name)

    def test_names_do_not_collide_with_confinement_analysis(self, tool_impl, sts_data):
        """Both tools subtract a background from the same dataset; if they
        registered the same names the second run would replace the first's
        results in the browser."""
        tool_impl._datasets['Source'] = sts_data

        tool_impl.estimate_dataset_baseline(MockTask(), 'Source', {'method': 'arpls'})
        confinement = tool_impl.analyze_confinement(
            MockTask(), 'Source', {'baseline': 'arpls'}, emit_matrix=False)

        assert not (set(confinement['dataset_names'].values())
                    & {'Source - Baseline Corrected', 'Source - Baseline'})

    def test_arpls_removes_the_band_edges_and_keeps_the_states(self, tool_impl, sts_data):
        """The reason arPLS is the default: it follows an exponential edge,
        which is what leaves an in-gap state an order of magnitude below the
        edges standing in the corrected curve."""
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'arpls'})

        x = np.asarray(sts_data.independent_var)
        raw = sts_data.spectra.values[:, 0]
        corrected = result['corrected'].spectra.values[:, 0]
        edge = np.argmin(np.abs(x - 0.6))
        in_gap = np.argmin(np.abs(x + 0.25))

        # The 3e-7 band edge is gone bar a few percent...
        assert abs(corrected[edge]) < 0.1 * raw[edge]
        # ...while the 1.2e-8 state planted on it is still there whole.
        assert corrected[in_gap] > 0.8 * 1.2e-8

    def test_none_returns_the_raw_spectra_unchanged(self, tool_impl, sts_data):
        """A chain can leave the node wired in and turn the correction off."""
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'none'})

        assert np.array_equal(result['corrected'].spectra.values, sts_data.spectra.values)
        assert np.all(result['baseline'].spectra.values == 0.0)

    def test_non_finite_samples_stay_non_finite(self, tool_impl, sts_data):
        """A gap in the sweep must stay a gap, not become a zero that the
        subtraction then keeps."""
        frame = sts_data.data.copy()
        frame.loc[5, 'R2'] = np.nan
        frame.loc[7, 'R2'] = np.nan
        tool_impl._datasets['Gappy'] = SpectralData(frame, sts_data.metadata)

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Gappy', {'method': 'poly-iter'})

        background = result['baseline'].spectra.values
        corrected = result['corrected'].spectra.values
        assert np.isnan(background[[5, 7], 1]).all()
        assert np.isnan(corrected[[5, 7], 1]).all()
        # Only the missing samples: the rest of that spectrum was still fitted.
        assert np.isfinite(np.delete(background[:, 1], [5, 7])).all()

    def test_an_all_nan_spectrum_does_not_take_the_run_down(self, tool_impl, sts_data):
        frame = sts_data.data.copy()
        frame['R3'] = np.nan
        tool_impl._datasets['Dead'] = SpectralData(frame, sts_data.metadata)

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Dead', {'method': 'arpls'})

        assert result['corrected'] is not None
        assert np.isnan(result['baseline'].spectra.values[:, 2]).all()
        assert np.isfinite(result['baseline'].spectra.values[:, 0]).all()
        tool_impl.errorOccurred.emit.assert_not_called()

    def test_coefficients_only_for_the_polynomial_methods(self, tool_impl, sts_data):
        tool_impl._datasets['Source'] = sts_data

        poly = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'poly', 'degree': 3})
        arpls = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'arpls', 'degree': 3})

        assert poly['coefficients'] is not None
        # arPLS is not a polynomial: refitting one to it would describe the
        # fit rather than the data.
        assert arpls['coefficients'] is None

    def test_coefficient_columns_follow_the_basis(self, tool_impl, sts_data):
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source',
            {'method': 'poly', 'degree': 2, 'basis': 'legendre'})

        coefficients = result['coefficients']
        assert list(coefficients.data.columns) == ['Spectrum_Index', 'P0', 'P1', 'P2']
        assert len(coefficients.data) == sts_data.spectra.shape[1]
        assert coefficients.metadata.data_type == 'flat'
        # A coefficient table is not a spectrum: it must not be overlaid on
        # the source's graph window.
        assert 'original' not in coefficients.metadata.additional_info

    def test_spatial_metadata_survives(self, tool_impl, sts_data):
        """A corrected line scan is still that line scan's spectra, so its
        maps must land in nanometres rather than point indices."""
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'arpls'})

        for port in ('corrected', 'baseline'):
            info = result[port].metadata.additional_info
            assert info['spatial_layout'] == 'line'
            assert info['position_m'] == [0.0, 1e-9, 2e-9, 3e-9]
            assert info['position_step_m'] == 1e-9
            assert info['original'] == 'Source'
        assert tool_impl._line_positions_m(result['corrected']) is not None

    def test_settings_are_recorded_on_every_output(self, tool_impl, sts_data):
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source',
            {'method': 'poly-iter', 'degree': 4, 'basis': 'chebyshev',
             'direction': 'negative'})

        for port in ('corrected', 'baseline', 'coefficients'):
            info = result[port].metadata.additional_info
            assert info['created_from'] == 'baseline_estimate'
            assert info['source_dataset'] == 'Source'
            assert info['baseline_method'] == 'poly-iter'
            assert info['degree'] == 4
            assert info['basis'] == 'chebyshev'
            assert info['direction'] == 'negative'

    def test_writes_the_corrected_and_background_csvs(self, tool_impl, sts_data):
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'arpls'})

        corrected_csv = pd.read_csv(result['corrected_path'])
        background_csv = pd.read_csv(result['baseline_path'])
        assert list(corrected_csv.columns) == ['V', 'R1', 'R2', 'R3', 'R4']
        assert len(corrected_csv) == len(sts_data.independent_var)
        assert np.allclose(background_csv['R1'].to_numpy(),
                           result['baseline'].spectra.values[:, 0])

    def test_float_parameters_from_qml_are_cast_back(self, tool_impl, sts_data):
        """QML and the workflow engine send every number as a float; degree
        and the iteration counts are indices, not measurements."""
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source',
            {'method': 'poly', 'degree': 3.0, 'iterations': 10.0,
             'endpoint_points': 8.0})

        assert result['corrected'] is not None
        assert list(result['coefficients'].data.columns) == \
            ['Spectrum_Index', 'c0', 'c1', 'c2', 'c3']

    def test_agrees_with_the_engine_spectrum_by_spectrum(self, tool_impl, sts_data):
        """Confinement Analysis runs the same call, so the two must agree."""
        tool_impl._datasets['Source'] = sts_data
        x = np.asarray(sts_data.independent_var, dtype=np.float64)

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'poly-iter', 'degree': 5})

        for i in range(sts_data.spectra.shape[1]):
            expected = estimate_baseline(x, sts_data.spectra.values[:, i],
                                         kind='poly-iter', degree=5)
            assert np.allclose(result['baseline'].spectra.values[:, i], expected)

    def test_missing_dataset_reports_rather_than_raising(self, tool_impl):
        result = tool_impl.estimate_dataset_baseline(MockTask(), 'Nope', {})

        assert result['corrected'] is None
        assert result['dataset_names'] == {}
        tool_impl.errorOccurred.emit.assert_called_once()

    def test_an_unknown_method_is_reported_by_name(self, tool_impl, sts_data):
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            MockTask(), 'Source', {'method': 'magic'})

        assert result['corrected'] is None
        title, message = tool_impl.errorOccurred.emit.call_args[0]
        assert title == "Baseline Estimate Error"
        assert 'magic' in message

    def test_cancelling_registers_nothing(self, tool_impl, sts_data):
        tool_impl._datasets['Source'] = sts_data

        result = tool_impl.estimate_dataset_baseline(
            CancelledTask(), 'Source', {'method': 'arpls'})

        assert result['corrected'] is None
        assert result['dataset_names'] == {}
        assert 'Source - Baseline Corrected' not in tool_impl._datasets
        tool_impl.dataLoaded.emit.assert_not_called()

    def test_progress_is_reported(self, tool_impl, sts_data):
        tool_impl._datasets['Source'] = sts_data
        task = MockTask()

        tool_impl.estimate_dataset_baseline(task, 'Source', {'method': 'arpls'})

        assert task.progress == 100


class TestBaselineEstimateExecution:
    """The node running headlessly through the workflow executor."""

    @pytest.fixture
    def executor(self, tmp_path, sts_data):
        from src.backend.tool_implementations import ToolImplementations

        class Backend(ToolImplementations):
            def __init__(self):
                self._datasets = {}
                self._output_base_dir = tmp_path / "outputs"
                self._output_base_dir.mkdir(exist_ok=True)
                self.errorOccurred = Mock()
                self.dataLoaded = Mock()
                self._workflow_mode = True

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

        backend = Backend()
        backend._datasets['Source'] = sts_data
        return WorkflowExecutor(backend), backend

    def _node(self, **params):
        node = create_node_from_tool("BaselineEstimate", 0, 0)
        node.parameters.update(params)
        return node

    def test_fills_the_dataset_ports(self, executor, sts_data):
        ex, _ = executor

        outputs = ex._execute_node(self._node(method='arpls'), {'dataset': sts_data})

        assert set(outputs) == {"corrected", "baseline", "coefficients"}
        assert isinstance(outputs['corrected'], SpectralData)
        assert isinstance(outputs['baseline'], SpectralData)
        assert outputs['coefficients'] is None

    def test_polynomial_run_fills_the_coefficient_port(self, executor, sts_data):
        ex, _ = executor

        outputs = ex._execute_node(self._node(method='poly', degree=3),
                                   {'dataset': sts_data})

        assert isinstance(outputs['coefficients'], SpectralData)
        assert outputs['coefficients'].metadata.data_type == 'flat'

    def test_parameters_reach_the_engine(self, executor, sts_data):
        ex, _ = executor

        arpls = ex._execute_node(self._node(method='arpls'), {'dataset': sts_data})
        none = ex._execute_node(self._node(method='none'), {'dataset': sts_data})

        assert np.any(arpls['baseline'].spectra.values != 0)
        assert np.all(none['baseline'].spectra.values == 0)

    def test_workflow_mode_keeps_intermediates_out_of_the_browser(self, executor, sts_data):
        ex, backend = executor
        ex._execute_node(self._node(), {'dataset': sts_data})
        backend.dataLoaded.emit.assert_not_called()

    def test_string_input_is_rejected_rather_than_crashing(self, executor):
        ex, _ = executor
        assert ex._execute_node(self._node(), {'dataset': 'not a dataset'}) == {}

    def test_missing_input_produces_no_outputs(self, executor):
        ex, _ = executor
        assert ex._execute_node(self._node(), {}) == {}

    def test_defaults_alone_run_without_error(self, executor, sts_data):
        """A node dropped on the canvas and executed untouched must work."""
        ex, backend = executor

        outputs = ex._execute_node(create_node_from_tool("BaselineEstimate", 0, 0),
                                   {'dataset': sts_data})

        assert outputs['corrected'] is not None
        backend.errorOccurred.emit.assert_not_called()
