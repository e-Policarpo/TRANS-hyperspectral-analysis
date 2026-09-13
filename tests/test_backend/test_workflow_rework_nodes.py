"""
The workflow nodes added or reworked for tool parity (docs/WORKFLOW_INVENTORY.md):
every node has an executor branch, the palette matches the Tools menu's
sections, and the new nodes carry datasets — not paths — down their ports.
"""

import re
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from src.backend.app_backend import AppBackend
from src.backend.tool_implementations import ToolImplementations
from src.backend.workflow_engine import TOOL_DEFINITIONS, create_node_from_tool, get_tool_categories
from src.backend.workflow_manager import WorkflowExecutor
from src.models.spectral_data import SpectralData, SpectralMetadata

MANAGER_SRC = (Path(__file__).resolve().parents[2] / "src" / "backend" / "workflow_manager.py").read_text()


def make_dataset(n_spectra=4, x_unit='V'):
    x = np.linspace(-1, 1, 200)
    cols = {f"S{i}": np.exp(-(x - 0.3) ** 2 / 0.01) + 0.5 * np.exp(-(x + 0.4) ** 2 / 0.01) + 0.01 * i
            for i in range(n_spectra)}
    df = pd.DataFrame({"Bias": x, **cols})
    return SpectralData(df, SpectralMetadata(
        source_type='test', dimensions=(n_spectra, 1), scan_mode='line',
        units={'independent': x_unit, 'dependent': 'A'}, additional_info={}))


@pytest.fixture
def executor(tmp_path):
    """A real executor over a backend that has the tool engines plus the
    AppBackend methods the new nodes route through."""
    class Backend(ToolImplementations):
        _do_fft1D = AppBackend._do_fft1D
        relabelDatasets = AppBackend.relabelDatasets
        apply_formula_dataset = AppBackend.apply_formula_dataset
        convertDatasetAxis = AppBackend.convertDatasetAxis
        convert_axis_dataset = AppBackend.convert_axis_dataset

        def __init__(self):
            self._datasets = {}
            self._output_base_dir = tmp_path / "outputs"
            self._output_base_dir.mkdir(exist_ok=True)
            self.errorOccurred = Mock()
            self.dataLoaded = Mock()
            self._mark_project_modified = Mock()
            self._workflow_mode = True
            self.status = ""

        def _ensure_output_dir(self, subdir):
            path = self._output_base_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            return path

        def _sanitize_filename(self, name):
            return re.sub(r'\W+', '_', name) or "unnamed"

        def _apply_naming_convention(self, dataset_name, operation="", preview=False):
            return self._sanitize_filename(f"{self._extract_clean_base_name(dataset_name)}_{operation}")

    backend = Backend()
    return WorkflowExecutor(backend), backend


def run(executor, key, inputs, **params):
    node = create_node_from_tool(key, 0, 0)
    node.parameters.update(params)
    return executor._execute_node(node, inputs)


class TestEveryNodeIsExecutable:
    def test_every_definition_has_an_executor_branch(self):
        dispatched = set(re.findall(r'tool_name == "([A-Za-z0-9_]+)"', MANAGER_SRC))
        missing = [k for k in TOOL_DEFINITIONS if k not in dispatched]
        assert missing == []

    def test_every_executor_branch_has_a_definition(self):
        dispatched = set(re.findall(r'tool_name == "([A-Za-z0-9_]+)"', MANAGER_SRC))
        assert dispatched - set(TOOL_DEFINITIONS) == set()

    def test_palette_sections_are_the_tools_menu_sections(self):
        assert [c["category"] for c in get_tool_categories()] == [
            "Input", "Output", "Annotations", "Prepare", "Transform",
            "Fit and features", "Maps", "Confinement"]

    def test_deprecated_nodes_still_instantiate(self):
        """Saved workflows built on them must still load."""
        for key in ("DetectBandgapDoping", "DiracPointEstimator"):
            node = create_node_from_tool(key, 0, 0)
            assert node is not None and node.tool_name == key


class TestAverageCurves:
    def test_one_mean_curve(self, executor):
        ex, _ = executor
        out = run(ex, "AverageCurves", {'dataset': make_dataset()})
        avg = out['average']
        assert avg is not None and avg.num_spectra == 1
        np.testing.assert_allclose(avg.spectra.values[:, 0],
                                   make_dataset().spectra.values.mean(axis=1), atol=1e-9)


class TestSetUnits:
    def test_relabels_a_copy_not_the_input(self, executor):
        ex, _ = executor
        src = make_dataset()
        out = run(ex, "SetUnits", {'dataset': src}, x_unit='mV', y_unit='nA', x_name='Sample bias')
        ds = out['dataset']
        assert ds.metadata.units['independent'] == 'mV'
        assert ds.independent_var_name == 'Sample bias'
        assert src.metadata.units['independent'] == 'V'      # untouched
        assert src.independent_var_name == 'Bias'


class TestAxisConvert:
    def test_nm_to_ev(self, executor):
        ex, _ = executor
        src = make_dataset(x_unit='nm')
        src.data['Bias'] = np.linspace(400, 800, 200)
        out = run(ex, "AxisConvert", {'dataset': src}, target_unit='eV')
        ds = out['converted']
        assert ds is not None
        assert ds.metadata.units['independent'] == 'eV'
        assert ds.independent_var.min() == pytest.approx(1239.84 / 800, rel=1e-3)

    def test_unknown_source_unit_yields_nothing_not_an_exception(self, executor):
        ex, backend = executor
        out = run(ex, "AxisConvert", {'dataset': make_dataset(x_unit='V')}, target_unit='eV')
        assert out.get('converted') is None
        backend.errorOccurred.emit.assert_called()


class TestSetValues:
    def test_formulas_and_units(self, executor):
        ex, _ = executor
        src = make_dataset()
        out = run(ex, "SetValues", {'dataset': src}, x_formula='x * 1e3', y_formula='y / 1e-9',
                  x_unit='mV', y_unit='nA')
        ds = out['result']
        np.testing.assert_allclose(ds.independent_var, src.independent_var * 1e3)
        np.testing.assert_allclose(ds.spectra.values, src.spectra.values / 1e-9)
        assert ds.metadata.units == {'independent': 'mV', 'dependent': 'nA', 'x': 'mV', 'y': 'nA'}

    def test_a_bad_formula_is_an_error_not_a_string_on_the_port(self, executor):
        ex, _ = executor
        with pytest.raises(Exception):
            run(ex, "SetValues", {'dataset': make_dataset()}, x_formula='open("x")')


class TestFFT1D:
    def test_ports_carry_datasets_not_paths(self, executor):
        ex, _ = executor
        out = run(ex, "FFT1D", {'dataset': make_dataset()}, window='hann', detrend=True)
        mag, phase = out['fft_result'], out['phase']
        assert hasattr(mag, 'spectra') and hasattr(phase, 'spectra')
        assert mag.metadata.units['independent'] == '1/V'
        assert phase.metadata.units['dependent'] == 'rad'

    def test_the_parameters_are_read(self, executor):
        ex, _ = executor
        two_sided = run(ex, "FFT1D", {'dataset': make_dataset()}, one_sided=False)['fft_result']
        one_sided = run(ex, "FFT1D", {'dataset': make_dataset()}, one_sided=True)['fft_result']
        assert two_sided.num_points > one_sided.num_points
        power = run(ex, "FFT1D", {'dataset': make_dataset()}, power_spectrum=True)['fft_result']
        assert power.metadata.additional_info['transform'] == 'FFT_power'


class TestMultiPeakFit:
    def test_peak_table_and_fitted_curves(self, executor):
        ex, _ = executor
        out = run(ex, "MultiPeakFit", {'dataset': make_dataset(3)}, n_peaks_auto=2, baseline_degree=0)
        table, fitted = out['peak_table'], out['fitted']
        assert table.metadata.data_type == 'flat'
        assert list(table.data['n_peaks']) == [2, 2, 2]
        assert fitted.num_spectra == 3


class TestMapGenerator:
    def test_spectra_path_runs_the_tool_engine(self, executor):
        ex, _ = executor
        ds = make_dataset(8)
        ds.metadata.dimensions = (4, 2)
        ds.metadata.scan_mode = 'raster'
        out = run(ex, "MapGenerator", {'dataset': ds}, scan_type='map_raster', bin_x=2, bin_y=1,
                  interval_source='manual', intervals=[[0.2, 0.4], [-0.5, -0.3]], baseline='none')
        assert len(out['maps']) == 2 and all(p.endswith('.tiff') for p in out['maps'])
        assert out['interval_map'].endswith('.tiff')
        assert out['values'].metadata.data_type == 'flat'
        assert list(out['values'].spectra.columns) == ['Interval_0.200_0.400', 'Interval_-0.500_-0.300']
        assert out['intervals_used'] == [[0.2, 0.4], [-0.5, -0.3]]
        assert out['binned'].num_spectra == 4          # 8 positions in 2x1 blocks

    def test_the_intervals_port_overrides_detection(self, executor):
        ex, _ = executor
        out = run(ex, "MapGenerator", {'dataset': make_dataset(4),
                                       'intervals': [{'lower': 0.25, 'upper': 0.35}]},
                  scan_type='line', baseline='none')
        assert out['intervals_used'] == [[0.25, 0.35]]
        assert len(out['maps']) == 1

    def test_flat_data_path_still_works(self, executor):
        ex, _ = executor
        flat = pd.DataFrame({'Spectrum_Index': range(4), 'Interval_0.100_0.200': [1.0, 2.0, 3.0, 4.0]})
        flat_ds = SpectralData(flat, SpectralMetadata(
            source_type='integrated_flat', dimensions=(4, 1), scan_mode='line',
            units={'independent': 'Index'}, additional_info={'intervals': [(0.1, 0.2)]},
            data_type='flat'))
        out = run(ex, "MapGenerator", {'flat_data': flat_ds}, scan_type='line')
        assert len(out['maps']) == 1
        assert out['values'] is flat_ds
