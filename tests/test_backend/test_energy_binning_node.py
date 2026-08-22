"""
Tests for the Energy Binning node: peaks that were already found, binned onto
the k_B*T/2 grid, with the occupied bins as the integration intervals.

The claim under test is agreement — the node must land on exactly the bins
``detect_map_intervals`` lands on, because that is what lets a hand-wired
chain reproduce the Map Generator and read the same states Confinement
Analysis reports.
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
from src.processing.peak_detection import thermal_broadening


class MockTask:
    """Mock task object for testing."""
    cancelled = False
    progress = 0


class CancelledTask:
    """A task the user has already cancelled."""
    cancelled = True
    progress = 0


#: Where the synthetic states are planted, in volts.
CENTERS = (-0.25, -0.10, 0.08, 0.22)

#: The detection knobs both the composite and the chain are run with, so the
#: two see the same peaks; without pinning `height` the Map Generator's 3
#: sigma would differ from Confinement Analysis's 2.
DETECT = {'baseline': 'poly-iter', 'baseline_degree': 5, 'height': 5.0}


def _line_scan(n_spectra=6, present=None):
    """Spectra with sharp in-gap states on a steep band-edge background."""
    x = np.linspace(-0.6, 0.6, 1024)
    band_edges = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)
    columns = {}
    for n in range(n_spectra):
        y = band_edges.copy()
        for centre in (CENTERS if present is None else present(n)):
            y = y + 1.2e-8 * np.exp(-0.5 * ((x - centre) / 0.004) ** 2)
        columns[f"P{n + 1}"] = y
    df = pd.DataFrame({"V": x, **columns})
    return SpectralData(df, SpectralMetadata(
        source_type='sts', dimensions=(n_spectra, 1), scan_mode='point',
        units={'independent': 'V'},
        additional_info={'spatial_layout': 'line',
                         'position_step_m': 1e-9}))


def _peak_table(rows, extra_columns=None):
    """A minimal peak table in the shape find_peaks / analyze_confinement emit."""
    frame = pd.DataFrame(rows, columns=['position_value', 'spectrum_index'])
    for name, values in (extra_columns or {}).items():
        frame[name] = values
    return SpectralData(frame, SpectralMetadata(
        source_type='peak_table', dimensions=(len(frame.columns) - 1, 1),
        scan_mode='peaks', units={'x': 'position'}, additional_info={}))


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


class TestEnergyBinningNodeDefinition:
    """The node as the palette and the executor see it."""

    def test_node_is_registered_in_the_analysis_category(self):
        node_def = TOOL_DEFINITIONS["EnergyBinning"]
        assert node_def["category"] == "Analysis"
        assert node_def["display_name"] == "Energy Binning"

    def test_the_peaks_input_is_required_and_the_spectra_are_not(self):
        inputs = {i["id"]: i for i in TOOL_DEFINITIONS["EnergyBinning"]["inputs"]}
        assert set(inputs) == {"peaks", "dataset"}
        assert inputs["peaks"]["required"] is True
        assert inputs["dataset"]["required"] is False
        assert inputs["peaks"]["port_type"] == "dataset"
        assert inputs["dataset"]["port_type"] == "dataset"

    def test_ports_match_what_the_dispatch_writes(self):
        outs = {o["id"]: o for o in TOOL_DEFINITIONS["EnergyBinning"]["outputs"]}
        assert set(outs) == {"intervals", "all_bins", "bins"}
        assert outs["intervals"]["port_type"] == "intervals"
        assert outs["all_bins"]["port_type"] == "intervals"
        assert outs["bins"]["port_type"] == "dataset"

    def test_parameters_are_the_four_knobs_of_the_rule(self):
        params = TOOL_DEFINITIONS["EnergyBinning"]["parameters"]
        assert set(params) == {"temperature_k", "x_energy_unit",
                               "bin_width", "min_spectra_per_bin"}
        assert params["temperature_k"]["default"] == 0.0
        assert params["bin_width"]["default"] == 0.0
        assert params["min_spectra_per_bin"]["default"] == 1

    def test_the_energy_unit_options_match_the_engine(self):
        from src.processing.peak_detection import ENERGY_UNITS
        options = TOOL_DEFINITIONS["EnergyBinning"]["parameters"]["x_energy_unit"]["options"]
        assert set(options) == set(ENERGY_UNITS)

    def test_it_sits_after_peak_finder_in_the_palette(self):
        """The two are read as a pair: find the peaks, then bin them."""
        analysis = next(c["tools"] for c in get_tool_categories()
                        if c["category"] == "Analysis")
        assert (analysis.index("EnergyBinning")
                - analysis.index("PeakFinder")) == 1

    def test_created_node_carries_the_defaults(self):
        node = create_node_from_tool("EnergyBinning", 0, 0)
        assert node.parameters["temperature_k"] == 0.0
        assert node.parameters["x_energy_unit"] == "eV"
        assert node.parameters["min_spectra_per_bin"] == 1

    def test_peak_finder_feeds_it_and_integration_takes_its_intervals(self):
        wf = Workflow(id="wf_eb", name="Binning WF")
        finder = create_node_from_tool("PeakFinder", 0, 0)
        binning = create_node_from_tool("EnergyBinning", 200, 0)
        integration = create_node_from_tool("Integration", 400, 0)
        for node in (finder, binning, integration):
            wf.add_node(node)

        peaks = Connection(
            id="c1", source_node_id=finder.id, source_port_id="peaks",
            target_node_id=binning.id, target_port_id="peaks")
        assert wf.add_connection(peaks) is True

        intervals = Connection(
            id="c2", source_node_id=binning.id, source_port_id="intervals",
            target_node_id=integration.id, target_port_id="intervals")
        assert wf.add_connection(intervals) is True

    def test_the_bin_table_can_be_captured(self):
        wf = Workflow(id="wf_eb2", name="Binning WF")
        binning = create_node_from_tool("EnergyBinning", 0, 0)
        output = create_node_from_tool("DatasetOutput", 200, 0)
        for node in (binning, output):
            wf.add_node(node)

        assert wf.validate_connection(Connection(
            id="c1", source_node_id=binning.id, source_port_id="bins",
            target_node_id=output.id, target_port_id="dataset")) is True


class TestAgreementWithTheMapGenerator:
    """The node must find the states the composite finds, on the same grid."""

    def _analyse(self, tool_impl, dataset, **params):
        tool_impl._datasets['sts'] = dataset
        return tool_impl.analyze_confinement(
            MockTask(), 'sts', params={**DETECT, **params})

    def test_bins_are_the_ones_detect_map_intervals_finds(self, tool_impl):
        dataset = _line_scan()
        analysis = self._analyse(tool_impl, dataset, temperature_k=94.0)
        expected = tool_impl.detect_map_intervals(
            MockTask(), 'sts', {**DETECT, 'temperature_k': 94.0})

        result = tool_impl.bin_peak_energies(
            MockTask(), 'sts - Peaks',
            {'temperature_k': 94.0}, source_dataset_name='sts')

        assert expected, "the composite found no intervals to compare against"
        np.testing.assert_allclose(result['intervals'], expected)
        assert analysis['peaks'] is not None

    def test_they_agree_without_a_temperature_too(self, tool_impl):
        """With no temperature both fall back to the sweep's own step."""
        dataset = _line_scan()
        self._analyse(tool_impl, dataset)
        expected = tool_impl.detect_map_intervals(MockTask(), 'sts', dict(DETECT))

        result = tool_impl.bin_peak_energies(
            MockTask(), 'sts - Peaks', {}, source_dataset_name='sts')

        assert expected
        np.testing.assert_allclose(result['intervals'], expected)

    def test_the_intervals_are_exactly_one_bin_wide(self, tool_impl):
        dataset = _line_scan()
        self._analyse(tool_impl, dataset, temperature_k=94.0)

        result = tool_impl.bin_peak_energies(
            MockTask(), 'sts - Peaks',
            {'temperature_k': 94.0}, source_dataset_name='sts')

        expected = thermal_broadening(94.0, 'eV') / 2
        assert result['bin_width'] == pytest.approx(expected, rel=1e-9)
        for lo, hi in result['intervals']:
            assert hi - lo == pytest.approx(expected, rel=1e-9)

    def test_every_planted_state_falls_in_an_interval(self, tool_impl):
        dataset = _line_scan()
        self._analyse(tool_impl, dataset, temperature_k=94.0)

        result = tool_impl.bin_peak_energies(
            MockTask(), 'sts - Peaks',
            {'temperature_k': 94.0}, source_dataset_name='sts')

        for centre in CENTERS:
            assert any(lo <= centre <= hi for lo, hi in result['intervals']), centre

    def test_all_bins_is_the_axis_the_binned_table_is_reported_on(self, tool_impl):
        """Confinement Analysis's binned occupancy table has one row per bin
        of the whole sweep, not per occupied bin."""
        dataset = _line_scan()
        analysis = self._analyse(tool_impl, dataset, temperature_k=94.0)

        result = tool_impl.bin_peak_energies(
            MockTask(), 'sts - Peaks',
            {'temperature_k': 94.0}, source_dataset_name='sts')

        binned = analysis['peak_matrix_binned']
        assert len(result['all_bins']) == len(binned.independent_var)
        midpoints = [(lo + hi) / 2 for lo, hi in result['all_bins']]
        assert midpoints == pytest.approx(list(binned.independent_var))


class TestBinPeakEnergies:
    """The backend method on its own."""

    def _source(self, tool_impl, x=None):
        x = np.linspace(0.0, 1.0, 101) if x is None else x
        frame = pd.DataFrame({'V': x, 'A': np.zeros_like(x), 'B': np.zeros_like(x)})
        dataset = SpectralData(frame, SpectralMetadata(
            source_type='sts', dimensions=(2, 1), scan_mode='point',
            units={'independent': 'V'}, additional_info={}))
        tool_impl._datasets['Source'] = dataset
        return dataset

    def test_one_interval_per_occupied_bin(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table(
            [(0.205, 0), (0.505, 0), (0.205, 1)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')

        np.testing.assert_allclose(result['intervals'],
                                   [[0.20, 0.21], [0.50, 0.51]])

    def test_several_peaks_of_one_spectrum_in_a_bin_count_once(self, tool_impl):
        """Otherwise a single noisy spectrum out-votes its neighbours in the
        min_spectra_per_bin filter — the same collapse group_peaks_by_bin
        performs for the composite."""
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table(
            [(0.501, 0), (0.504, 0), (0.508, 0)])

        loose = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')
        strict = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01, 'min_spectra_per_bin': 2},
            source_dataset_name='Source')

        assert len(loose['intervals']) == 1
        assert strict['intervals'] == []
        row = loose['bins'].data.iloc[0]
        assert row['n_spectra'] == 1
        assert row['n_peaks'] == 3

    def test_the_filter_drops_bins_without_widening_the_rest(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table(
            [(0.205, 0), (0.205, 1), (0.505, 0)])

        loose = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')
        strict = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01, 'min_spectra_per_bin': 2},
            source_dataset_name='Source')

        assert len(strict['intervals']) < len(loose['intervals'])
        widths = {round(hi - lo, 12)
                  for lo, hi in loose['intervals'] + strict['intervals']}
        assert widths == {0.01}

    def test_a_bin_the_filter_dropped_is_still_reported_as_unoccupied(self, tool_impl):
        """The table has to say which bins were dropped, or the threshold is
        an invisible knob."""
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table(
            [(0.205, 0), (0.205, 1), (0.505, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01, 'min_spectra_per_bin': 2},
            source_dataset_name='Source')

        table = result['bins'].data
        assert list(table['occupied']) == [1, 0]
        assert list(table['n_spectra']) == [2, 1]

    def test_an_explicit_width_overrides_the_temperature(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'temperature_k': 94.0, 'bin_width': 0.05},
            source_dataset_name='Source')

        assert result['bin_width'] == pytest.approx(0.05)
        assert result['bin_width_reason'] == "the requested bin width"

    def test_a_width_finer_than_the_sweep_step_is_floored(self, tool_impl):
        """Two bins over the same two samples are duplicate maps, not extra
        information — the floor applies to a typed-in width as well."""
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.0001},
            source_dataset_name='Source')

        assert result['bin_width'] == pytest.approx(0.01)
        assert "finer than the sweep step" in result['bin_width_reason']

    def test_without_a_temperature_the_bins_are_the_sweep_step(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0), (0.505, 1)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {}, source_dataset_name='Source')

        assert result['bin_width'] == pytest.approx(0.01)
        assert result['bin_width_reason'] == \
            "no temperature set — using the sweep's own step"

    def test_without_the_spectra_the_grid_is_anchored_on_the_peaks(self, tool_impl):
        """No sweep means no span and no step: the grid reaches no further
        than the outermost state."""
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0), (0.505, 1)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.05})

        assert result['edges'][0] <= 0.205
        assert result['edges'][-1] >= 0.505
        assert result['edges'][-1] - result['edges'][0] < 0.5
        assert result['bin_width'] == pytest.approx(0.05)

    def test_no_temperature_and_no_spectra_leave_nothing_to_bin_on(self, tool_impl):
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0)])

        result = tool_impl.bin_peak_energies(MockTask(), 'Peaks', {})

        assert result['intervals'] == []
        assert result['bins'] is None
        assert not [n for n in tool_impl._datasets if n.endswith('Energy Bins')]
        tool_impl.errorOccurred.emit.assert_not_called()

    def test_all_bins_tiles_the_whole_sweep(self, tool_impl):
        source = self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.505, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.05},
            source_dataset_name='Source')

        bins = result['all_bins']
        assert bins[0][0] <= float(source.independent_var.min())
        assert bins[-1][1] >= float(source.independent_var.max())
        for (lo, hi), (next_lo, _) in zip(bins, bins[1:]):
            assert hi == pytest.approx(next_lo)
            assert hi - lo == pytest.approx(0.05)

    def test_registers_the_bin_table_indexed_by_centre(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0), (0.505, 1)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')

        assert result['bins_name'] == 'Source - Energy Bins'
        assert result['bins_name'] in tool_impl._datasets
        tool_impl.dataLoaded.emit.assert_any_call('Source - Energy Bins')
        table = result['bins']
        assert table.independent_var_name == 'bin_center'
        assert list(table.data.columns) == ['bin_center', 'bin_index', 'bin_low',
                                            'bin_high', 'n_spectra', 'n_peaks',
                                            'occupied']
        assert list(table.independent_var) == pytest.approx([0.205, 0.505])

    def test_the_table_is_named_after_the_peaks_when_there_is_no_source(self, tool_impl):
        tool_impl._datasets['Run Peaks'] = _peak_table([(0.205, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Run Peaks', {'bin_width': 0.05})

        assert result['bins_name'] == 'Run Peaks - Energy Bins'

    def test_the_intervals_are_published_where_a_map_run_looks_for_them(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0), (0.505, 1)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')

        np.testing.assert_allclose(tool_impl.dataset_intervals(result['bins_name']),
                                   result['intervals'])

    def test_the_table_never_claims_to_hold_integrated_values(self, tool_impl):
        """'intervals' marks a dataset as integrated values, and the
        Hyperspectral tab skips those — this one is a table of bins."""
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')

        info = result['bins'].metadata.additional_info
        assert 'intervals' not in info
        assert 'original' not in info

    def test_the_settings_are_recorded_on_the_table(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks',
            {'temperature_k': 94.0, 'x_energy_unit': 'eV',
             'min_spectra_per_bin': 1},
            source_dataset_name='Source')

        info = result['bins'].metadata.additional_info
        assert info['created_from'] == 'energy_binning'
        assert info['source_dataset'] == 'Source'
        assert info['peaks_dataset'] == 'Peaks'
        assert info['temperature_k'] == 94.0
        assert info['x_energy_unit'] == 'eV'
        assert info['min_spectra_per_bin'] == 1
        assert info['bin_edges'] == pytest.approx(result['edges'])
        assert info['bin_width_reason'] == result['bin_width_reason']

    def test_a_capitalised_peak_table_still_binds(self, tool_impl):
        """A table that has been through a flat-data tool comes back as
        Spectrum_Index rather than snake_case."""
        self._source(tool_impl)
        frame = pd.DataFrame({'Position_Value': [0.205, 0.505],
                              'Spectrum_Index': [0, 1]})
        tool_impl._datasets['Peaks'] = SpectralData(frame, SpectralMetadata(
            source_type='peak_table', dimensions=(1, 1), scan_mode='peaks',
            units={}, additional_info={}))

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')

        assert len(result['intervals']) == 2

    def test_peaks_with_no_position_are_skipped(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table(
            [(0.205, 0), (np.nan, 1), (0.505, 1)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')

        np.testing.assert_allclose(result['intervals'],
                                   [[0.20, 0.21], [0.50, 0.51]])
        assert list(result['bins'].data['n_peaks']) == [1, 1]

    def test_a_table_with_no_peaks_is_an_answer_not_a_fault(self, tool_impl):
        self._source(tool_impl)
        frame = pd.DataFrame({'position_value': pd.Series(dtype=float),
                              'spectrum_index': pd.Series(dtype=float)})
        tool_impl._datasets['Peaks'] = SpectralData(frame, SpectralMetadata(
            source_type='peak_table', dimensions=(1, 1), scan_mode='peaks',
            units={}, additional_info={}))

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')

        assert result['intervals'] == []
        assert result['bins'] is None
        tool_impl.errorOccurred.emit.assert_not_called()

    def test_a_missing_peak_table_is_reported(self, tool_impl):
        result = tool_impl.bin_peak_energies(MockTask(), 'nope', {})

        assert result['intervals'] == []
        tool_impl.errorOccurred.emit.assert_called_once()

    def test_a_missing_source_dataset_is_reported(self, tool_impl):
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='nope')

        assert result['bins'] is None
        tool_impl.errorOccurred.emit.assert_called_once()

    def test_a_table_without_the_required_columns_is_reported(self, tool_impl):
        frame = pd.DataFrame({'x': [0.1, 0.2], 'height': [1.0, 2.0]})
        tool_impl._datasets['Peaks'] = SpectralData(frame, SpectralMetadata(
            source_type='peak_table', dimensions=(1, 1), scan_mode='peaks',
            units={}, additional_info={}))

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01})

        assert result['intervals'] == []
        title, message = tool_impl.errorOccurred.emit.call_args[0]
        assert title == "Energy Binning Error"
        assert 'spectrum_index' in message and 'position_value' in message

    def test_an_unknown_energy_unit_is_named_in_the_error(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'x_energy_unit': 'joule'},
            source_dataset_name='Source')

        assert result['intervals'] == []
        _title, message = tool_impl.errorOccurred.emit.call_args[0]
        assert 'joule' in message

    def test_cancelling_registers_nothing(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0), (0.505, 1)])

        result = tool_impl.bin_peak_energies(
            CancelledTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')

        assert result['intervals'] == []
        assert result['bins'] is None
        assert 'Source - Energy Bins' not in tool_impl._datasets

    def test_progress_reaches_the_end(self, tool_impl):
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0), (0.505, 1)])
        task = MockTask()

        tool_impl.bin_peak_energies(
            task, 'Peaks', {'bin_width': 0.01}, source_dataset_name='Source')

        assert task.progress == 100

    def test_the_workflow_mode_keeps_quiet(self, tool_impl):
        tool_impl._workflow_mode = True
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks', {'bin_width': 0.01},
            source_dataset_name='Source')

        assert result['bins_name'] in tool_impl._datasets
        tool_impl.dataLoaded.emit.assert_not_called()

    def test_float_parameters_from_qml_are_cast(self, tool_impl):
        """QML sends every number as a float, min_spectra_per_bin included."""
        self._source(tool_impl)
        tool_impl._datasets['Peaks'] = _peak_table([(0.205, 0), (0.205, 1)])

        result = tool_impl.bin_peak_energies(
            MockTask(), 'Peaks',
            {'bin_width': 0.01, 'min_spectra_per_bin': 2.0},
            source_dataset_name='Source')

        assert result['bins'].metadata.additional_info['min_spectra_per_bin'] == 2
        assert len(result['intervals']) == 1


class TestEnergyBinningExecution:
    """The node running headlessly through the workflow executor."""

    @pytest.fixture
    def executor(self, tmp_path):
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

        return WorkflowExecutor(Backend())

    def _node(self, **params):
        node = create_node_from_tool("EnergyBinning", 0, 0)
        node.parameters.update(params)
        return node

    def _source(self, points=101):
        x = np.linspace(0.0, 1.0, points)
        return SpectralData(
            pd.DataFrame({'V': x, 'A': np.zeros_like(x), 'B': np.zeros_like(x)}),
            SpectralMetadata(source_type='sts', dimensions=(2, 1),
                             scan_mode='point', units={'independent': 'V'},
                             additional_info={}))

    def test_fills_the_three_ports(self, executor):
        peaks = _peak_table([(0.205, 0), (0.505, 1)])

        outputs = executor._execute_node(
            self._node(bin_width=0.01),
            {'peaks': peaks, 'dataset': self._source()})

        assert set(outputs) == {"intervals", "all_bins", "bins"}
        np.testing.assert_allclose(outputs['intervals'],
                                   [[0.20, 0.21], [0.50, 0.51]])
        assert len(outputs['all_bins']) > len(outputs['intervals'])
        assert isinstance(outputs['bins'], SpectralData)

    def test_runs_without_the_optional_spectra(self, executor):
        peaks = _peak_table([(0.205, 0), (0.505, 1)])

        outputs = executor._execute_node(self._node(bin_width=0.05),
                                         {'peaks': peaks})

        assert len(outputs['intervals']) == 2

    def test_the_temperature_reaches_the_grid(self, executor):
        peaks = _peak_table([(0.205, 0)])

        outputs = executor._execute_node(
            self._node(temperature_k=94.0),
            {'peaks': peaks, 'dataset': self._source(points=10001)})

        lo, hi = outputs['intervals'][0]
        assert hi - lo == pytest.approx(thermal_broadening(94.0, 'eV') / 2, rel=1e-9)

    def test_a_string_input_is_rejected(self, executor):
        outputs = executor._execute_node(self._node(), {'peaks': 'Some Dataset'})

        assert outputs == {}

    def test_nothing_happens_without_peaks(self, executor):
        outputs = executor._execute_node(self._node(), {'dataset': self._source()})

        assert outputs == {}
