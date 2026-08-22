"""
Tests for the Map Assembly node: one value per spectrum, laid out on the
sample with its real physical scale.

The claim under test is agreement. Map Assembly is the generic half of the
Map Generator — nothing here searches, corrects or integrates — so a chain
that ends in it must write the maps the composite writes, byte for byte and
with the same metres on disk. That is what makes the Map Generator
decomposable, and it is the node every other per-spectrum result (peak
counts, background coefficients, confinement sizes) reaches the sample
through.
"""

import re

import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import Mock

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.backend.workflow_engine import (
    Workflow, Connection, TOOL_DEFINITIONS, create_node_from_tool,
    get_tool_categories,
)
from src.backend.workflow_manager import WorkflowExecutor


class MockTask:
    """Mock task object for testing."""
    cancelled = False
    progress = 0


class CancelledTask:
    """A task the user has already cancelled."""
    cancelled = True
    progress = 0


#: Spacing between the synthetic line scan's positions, in metres.
STEP_M = 5e-9

#: The two intervals the hand-wired runs integrate over. Both are far wider
#: than the sweep step, so the Map Generator does not widen them and the
#: chain integrates exactly the same samples.
INTERVALS = [[-0.30, -0.20], [0.15, 0.25]]


def _line_scan(n_spectra=8, n_points=256, with_positions=True):
    """A line scan with one state per spectrum, growing along the line."""
    x = np.linspace(-0.6, 0.6, n_points)
    columns = {}
    for n in range(n_spectra):
        y = 1e-12 + 1e-11 * (n + 1) * np.exp(-0.5 * ((x - 0.20) / 0.01) ** 2)
        y = y + 4e-12 * np.exp(-0.5 * ((x + 0.25) / 0.01) ** 2)
        columns[f"P{n + 1}"] = y
    info = {}
    if with_positions:
        info['spectrum_meta'] = [{'location_m': [n * STEP_M, 0.0]}
                                 for n in range(n_spectra)]
    return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
        source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
        units={'independent': 'V', 'dependent': 'A/V'}, additional_info=info))


def _flat(values, columns=None, info=None, dimensions=None, scan_mode='line'):
    """A flat table: one row per spectrum, one column per value.

    ``values`` is ``{column name: [one value per spectrum]}`` — the shape
    every tool that returns a number per spectrum emits.
    """
    frame = pd.DataFrame({'Spectrum_Index': np.arange(len(next(iter(values.values())))),
                          **{name: np.asarray(v, dtype=float)
                             for name, v in values.items()}})
    n_rows = len(frame)
    return SpectralData(frame, SpectralMetadata(
        source_type='integrated_flat', dimensions=dimensions or (n_rows, 1),
        scan_mode=scan_mode,
        units={'independent': 'Index', 'dependent': 'Integrated Value'},
        additional_info=info or {},
        data_type='flat'))


def _gsf(tiff_path):
    """The GSF header written beside a map, in the run's gsf/ folder."""
    from src.utils.gsf_io import read_gsf
    path = Path(tiff_path)
    return read_gsf(path.parent.parent / 'gsf' / (path.stem + '.gsf'))[1]


def _csv_of(tiff_path):
    """The raw numbers written beside a map, in the run's csv/ folder."""
    path = Path(tiff_path)
    return np.loadtxt(path.parent.parent / 'csv' / (path.stem + '.csv'),
                      delimiter=',', ndmin=2)


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


class TestMapAssemblyNodeDefinition:
    """The node as the palette and the executor see it."""

    def test_node_is_registered_in_the_visualization_category(self):
        node_def = TOOL_DEFINITIONS["MapAssembly"]
        assert node_def["category"] == "Visualization"
        assert node_def["display_name"] == "Map Assembly"

    def test_only_the_values_are_required(self):
        inputs = {i["id"]: i for i in TOOL_DEFINITIONS["MapAssembly"]["inputs"]}
        assert set(inputs) == {"flat_data", "intervals", "source"}
        assert inputs["flat_data"]["required"] is True
        assert inputs["intervals"]["required"] is False
        assert inputs["source"]["required"] is False

    def test_input_port_types_match_what_the_dispatch_reads(self):
        inputs = {i["id"]: i for i in TOOL_DEFINITIONS["MapAssembly"]["inputs"]}
        assert inputs["flat_data"]["port_type"] == "flat_data"
        assert inputs["intervals"]["port_type"] == "intervals"
        assert inputs["source"]["port_type"] == "dataset"

    def test_output_port_types_match_what_the_dispatch_writes(self):
        outs = {o["id"]: o for o in TOOL_DEFINITIONS["MapAssembly"]["outputs"]}
        assert set(outs) == {"maps", "interval_map", "interval_map_path"}
        assert outs["maps"]["port_type"] == "map"
        assert outs["interval_map"]["port_type"] == "dataset"
        assert outs["interval_map_path"]["port_type"] == "map"

    def test_the_parameters_are_the_three_layout_knobs(self):
        params = TOOL_DEFINITIONS["MapAssembly"]["parameters"]
        assert set(params) == {"scan_type", "columns", "joined_map"}
        assert params["scan_type"]["default"] == "auto"
        assert params["columns"]["default"] == ""
        assert params["joined_map"]["default"] is True

    def test_the_scan_types_are_the_ones_the_engine_resolves(self):
        from src.backend.tool_implementations import ToolImplementations
        options = TOOL_DEFINITIONS["MapAssembly"]["parameters"]["scan_type"]["options"]
        assert set(options) == set(ToolImplementations.SCAN_TYPES)

    def test_it_sits_next_to_the_map_generator_in_the_palette(self):
        """They lay the same values out; one finds them first."""
        visualization = next(c["tools"] for c in get_tool_categories()
                             if c["category"] == "Visualization")
        assert (visualization.index("MapAssembly")
                - visualization.index("MapGenerator")) == 1

    def test_created_node_carries_the_defaults(self):
        node = create_node_from_tool("MapAssembly", 0, 0)
        assert node.parameters["scan_type"] == "auto"
        assert node.parameters["joined_map"] is True

    def test_integration_feeds_it_and_energy_binning_names_the_rows(self):
        wf = Workflow(id="wf_ma", name="Assembly WF")
        binning = create_node_from_tool("EnergyBinning", 0, 0)
        integration = create_node_from_tool("Integration", 200, 0)
        assembly = create_node_from_tool("MapAssembly", 400, 0)
        for node in (binning, integration, assembly):
            wf.add_node(node)

        assert wf.add_connection(Connection(
            id="c1", source_node_id=integration.id, source_port_id="flat_data",
            target_node_id=assembly.id, target_port_id="flat_data")) is True
        assert wf.add_connection(Connection(
            id="c2", source_node_id=binning.id, source_port_id="intervals",
            target_node_id=assembly.id, target_port_id="intervals")) is True

    def test_the_spectra_can_be_wired_in_for_their_positions(self):
        wf = Workflow(id="wf_ma2", name="Assembly WF")
        source = create_node_from_tool("DatasetInput", 0, 0)
        assembly = create_node_from_tool("MapAssembly", 200, 0)
        for node in (source, assembly):
            wf.add_node(node)

        assert wf.validate_connection(Connection(
            id="c1", source_node_id=source.id, source_port_id="dataset",
            target_node_id=assembly.id, target_port_id="source")) is True

    def test_the_maps_and_the_joined_map_can_both_be_captured(self):
        wf = Workflow(id="wf_ma3", name="Assembly WF")
        assembly = create_node_from_tool("MapAssembly", 0, 0)
        map_out = create_node_from_tool("MapOutput", 200, 0)
        data_out = create_node_from_tool("DatasetOutput", 200, 120)
        for node in (assembly, map_out, data_out):
            wf.add_node(node)

        assert wf.validate_connection(Connection(
            id="c1", source_node_id=assembly.id, source_port_id="maps",
            target_node_id=map_out.id, target_port_id="map")) is True
        assert wf.validate_connection(Connection(
            id="c2", source_node_id=assembly.id, source_port_id="interval_map",
            target_node_id=data_out.id, target_port_id="dataset")) is True


class TestTheMapsItWrites:
    """One file per value column, named after the state it belongs to."""

    def _run(self, tool_impl, values=None, intervals=None, source=None, **params):
        tool_impl._datasets['values'] = _flat(values or {
            'Interval_-0.300_-0.200': np.arange(8.0),
            'Interval_0.150_0.250': np.arange(8.0) * 2,
        })
        if source is not None:
            tool_impl._datasets['line'] = source
        return tool_impl.assemble_maps(
            MockTask(), 'values', params={'scan_type': 'line', **params},
            source_dataset_name='line' if source is not None else None,
            intervals=intervals)

    def test_one_map_per_value_column(self, tool_impl):
        result = self._run(tool_impl)

        assert result['n_maps'] == 2
        for path in result['map_paths']:
            assert path.endswith('.tiff')
            assert Path(path).exists()

    def test_the_gsf_and_csv_ride_along(self, tool_impl):
        """The export contract is the Map Generator's: TIFF + GSF + CSV."""
        result = self._run(tool_impl)
        tiff = Path(result['map_paths'][0])

        assert (tiff.parent.parent / 'gsf' / (tiff.stem + '.gsf')).exists()
        assert (tiff.parent.parent / 'csv' / (tiff.stem + '.csv')).exists()

    def test_a_map_holds_the_values_it_was_given(self, tool_impl):
        result = self._run(tool_impl, intervals=INTERVALS)
        low = next(p for p in result['map_paths'] if '-0.300_-0.200' in p)

        np.testing.assert_allclose(_csv_of(low), [np.arange(8.0)])

    def test_a_column_with_an_interval_is_named_after_it(self, tool_impl):
        result = self._run(tool_impl, intervals=INTERVALS)

        assert result['columns'] == ['-0.300_-0.200', '0.150_0.250']

    def test_a_column_with_no_interval_is_named_after_itself(self, tool_impl):
        result = self._run(tool_impl, values={'peak_count': np.arange(8.0),
                                              'size_nm': np.arange(8.0)})

        assert result['columns'] == ['peak_count', 'size_nm']

    def test_a_line_scan_becomes_a_single_row(self, tool_impl):
        result = self._run(tool_impl)

        assert _csv_of(result['map_paths'][0]).shape == (1, 8)

    def test_a_grid_is_folded_into_rows(self, tool_impl):
        tool_impl._datasets['values'] = _flat(
            {'peak_count': np.arange(16.0)}, dimensions=(4, 4), scan_mode='point')
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         params={'scan_type': 'map_raster'})

        assert _csv_of(result['map_paths'][0]).shape == (4, 4)

    def test_a_meander_reverses_alternate_rows(self, tool_impl):
        # Two names, so the second run does not write over the first's files.
        for name in ('raster', 'meander'):
            tool_impl._datasets[name] = _flat(
                {'peak_count': np.arange(16.0)}, dimensions=(4, 4),
                scan_mode='point')
        raster = tool_impl.assemble_maps(MockTask(), 'raster',
                                         params={'scan_type': 'map_raster'})
        meander = tool_impl.assemble_maps(MockTask(), 'meander',
                                          params={'scan_type': 'map_meander'})

        np.testing.assert_allclose(_csv_of(meander['map_paths'][0])[0],
                                   _csv_of(raster['map_paths'][0])[0][::-1])

    def test_the_named_columns_are_the_only_ones_mapped(self, tool_impl):
        result = self._run(tool_impl, values={'a': np.arange(8.0),
                                              'b': np.arange(8.0),
                                              'c': np.arange(8.0)},
                           columns='a, c')

        assert result['columns'] == ['a', 'c']
        assert result['n_maps'] == 2

    def test_the_column_filter_ignores_case(self, tool_impl):
        result = self._run(tool_impl, values={'Size_nm': np.arange(8.0),
                                              'other': np.arange(8.0)},
                           columns='size_nm')

        assert result['columns'] == ['Size_nm']

    def test_a_column_that_is_not_there_is_named_in_the_error(self, tool_impl):
        result = self._run(tool_impl, values={'a': np.arange(8.0)},
                           columns='nope')

        assert result['n_maps'] == 0
        assert 'nope' in tool_impl.errorOccurred.emit.call_args[0][1]

    def test_a_column_of_text_maps_as_blanks_rather_than_failing(self, tool_impl):
        """``reason`` rides along in a designer's table; it is not a value,
        and it must not take the run down with it."""
        tool_impl._datasets['values'] = _flat({'size_nm': np.arange(8.0)})
        tool_impl._datasets['values'].data['reason'] = ['no_peaks'] * 8
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         params={'scan_type': 'line'})

        assert result['n_maps'] == 2
        text_map = next(p for p in result['map_paths'] if 'reason' in p)
        assert np.all(np.isnan(_csv_of(text_map)))


class TestTheScaleOnDisk:
    """The export rule: a map carries the real dimensions whenever they exist,
    and never claims metres it does not have."""

    def _run(self, tool_impl, *, with_positions=True, flat_info=None,
             source=True, **params):
        tool_impl._datasets['values'] = _flat(
            {'Interval_-0.300_-0.200': np.arange(8.0),
             'Interval_0.150_0.250': np.arange(8.0) * 2},
            info=flat_info)
        if source:
            tool_impl._datasets['line'] = _line_scan(with_positions=with_positions)
        return tool_impl.assemble_maps(
            MockTask(), 'values', params={'scan_type': 'line', **params},
            source_dataset_name='line' if source else None)

    def test_a_map_states_its_width_in_metres(self, tool_impl):
        header = _gsf(self._run(tool_impl)['map_paths'][0])

        assert header['XYUnits'] == 'm'
        assert header['XReal'] == pytest.approx(8 * STEP_M)

    def test_the_positions_come_from_the_spectra_the_values_were_measured_on(
            self, tool_impl):
        """A flat table of integrals knows nothing about the sample."""
        result = self._run(tool_impl)
        assert _gsf(result['map_paths'][0])['XYUnits'] == 'm'

        without = self._run(tool_impl, source=False)
        assert _gsf(without['map_paths'][0]).get('XYUnits', '') == ''

    def test_a_table_that_carries_its_own_positions_needs_no_source(self, tool_impl):
        result = self._run(tool_impl, source=False,
                           flat_info={'position_m': [n * STEP_M for n in range(8)],
                                      'spatial_layout': 'line'})
        header = _gsf(result['map_paths'][0])

        assert header['XYUnits'] == 'm'
        assert header['XReal'] == pytest.approx(8 * STEP_M)

    def test_an_integration_result_finds_them_through_its_recorded_source(
            self, tool_impl):
        """The chain the Map Generator decomposes into: Integration records
        only ``original_dataset``, and that is enough."""
        tool_impl._datasets['line'] = _line_scan()
        result = self._run(tool_impl, source=False,
                           flat_info={'original_dataset': 'line'})

        assert _gsf(result['map_paths'][0])['XReal'] == pytest.approx(8 * STEP_M)

    def test_without_positions_the_point_index_is_the_axis(self, tool_impl):
        """Re-imported from CSV: the index is a real axis; metres are not to
        be invented."""
        result = self._run(tool_impl, with_positions=False)
        header = _gsf(result['map_paths'][0])

        assert header['XReal'] == pytest.approx(8)
        assert header.get('XYUnits', '') == ''
        assert 'point index' in header['Title']

    def test_the_joined_map_states_the_energy_axis(self, tool_impl):
        header = _gsf(self._run(tool_impl)['interval_map_path'])

        assert header['YOffset'] == pytest.approx(-0.30)
        assert header['YReal'] == pytest.approx(0.55)

    def test_the_joined_map_states_the_position_axis(self, tool_impl):
        header = _gsf(self._run(tool_impl)['interval_map_path'])
        assert header['XReal'] == pytest.approx(8 * STEP_M)

    def test_the_joined_map_names_both_axes(self, tool_impl):
        header = _gsf(self._run(tool_impl)['interval_map_path'])
        assert 'x=position' in header['Title'] and 'y=energy' in header['Title']

    def test_the_value_unit_follows_the_spectra(self, tool_impl):
        header = _gsf(self._run(tool_impl)['map_paths'][0])
        assert header.get('ZUnits') == 'A/V'


class TestTheIntervalMapDataset:
    """Position across, interval up — the joined map, registered so the
    Hyperspectral tab opens it as a kymograph."""

    def _run(self, tool_impl, values=None, intervals=None, **params):
        tool_impl._datasets['line'] = _line_scan()
        tool_impl._datasets['values'] = _flat(values or {
            'Interval_-0.300_-0.200': np.arange(8.0),
            'Interval_0.150_0.250': np.arange(8.0) * 2,
        })
        return tool_impl.assemble_maps(
            MockTask(), 'values', params={'scan_type': 'line', **params},
            source_dataset_name='line', intervals=intervals)

    def test_it_is_registered_and_returned(self, tool_impl):
        result = self._run(tool_impl)

        assert result['interval_map'] in tool_impl._datasets
        assert result['interval_map_dataset'] is not None
        assert result['interval_map'].endswith(' - Interval Map')

    def test_the_rows_are_the_intervals_and_the_columns_the_positions(self, tool_impl):
        result = self._run(tool_impl)
        dataset = tool_impl._datasets[result['interval_map']]

        assert dataset.spectra.shape == (2, 8)

    def test_the_rows_are_ordered_by_midpoint(self, tool_impl):
        result = self._run(tool_impl, values={
            'Interval_0.150_0.250': np.full(8, 2.0),
            'Interval_-0.300_-0.200': np.full(8, 1.0),
        })
        dataset = tool_impl._datasets[result['interval_map']]

        np.testing.assert_allclose(dataset.independent_var, [-0.25, 0.20])
        np.testing.assert_allclose(dataset.spectra.to_numpy()[:, 0], [1.0, 2.0])

    def test_the_columns_are_named_after_the_spectra(self, tool_impl):
        result = self._run(tool_impl)
        dataset = tool_impl._datasets[result['interval_map']]

        assert list(dataset.spectra.columns) == [f"P{n + 1}" for n in range(8)]

    def test_a_recorded_column_list_names_them_when_there_is_no_source(self, tool_impl):
        tool_impl._datasets['values'] = _flat(
            {'Interval_-0.300_-0.200': np.arange(8.0),
             'Interval_0.150_0.250': np.arange(8.0)},
            info={'spectrum_columns': [f"S{n}" for n in range(8)]})
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         params={'scan_type': 'line'})
        dataset = tool_impl._datasets[result['interval_map']]

        assert list(dataset.spectra.columns) == [f"S{n}" for n in range(8)]

    def test_it_reads_as_a_line_scan(self, tool_impl):
        result = self._run(tool_impl)
        metadata = tool_impl._datasets[result['interval_map']].metadata

        assert metadata.scan_mode == 'line'
        assert metadata.dimensions == (8, 1)
        assert metadata.additional_info['spatial_layout'] == 'line'

    def test_it_never_claims_to_hold_integrated_values(self, tool_impl):
        """``intervals`` marks a dataset as integrated values, which the
        Hyperspectral tab skips — the bounds go out under their own key."""
        result = self._run(tool_impl)
        info = tool_impl._datasets[result['interval_map']].metadata.additional_info

        assert 'intervals' not in info
        assert info['interval_bounds'] == [[-0.30, -0.20], [0.15, 0.25]]
        assert info['interval_midpoints'] == pytest.approx([-0.25, 0.20])

    def test_it_carries_the_positions_so_the_kymograph_has_an_x_axis(self, tool_impl):
        result = self._run(tool_impl)
        info = tool_impl._datasets[result['interval_map']].metadata.additional_info

        assert info['position_step_m'] == pytest.approx(STEP_M)
        assert info['position_m'] == pytest.approx([n * STEP_M for n in range(8)])

    def test_it_records_where_it_came_from(self, tool_impl):
        result = self._run(tool_impl)
        info = tool_impl._datasets[result['interval_map']].metadata.additional_info

        assert info['created_from'] == 'map_assembly'
        assert info['flat_dataset'] == 'values'
        assert info['source_dataset'] == 'line'

    def test_the_browser_is_told_about_it(self, tool_impl):
        result = self._run(tool_impl)
        emitted = [call[0][0] for call in tool_impl.dataLoaded.emit.call_args_list]

        assert result['interval_map'] in emitted

    def test_turning_the_joined_map_off_still_writes_the_per_column_maps(self, tool_impl):
        result = self._run(tool_impl, joined_map=False)

        assert result['n_maps'] == 2
        assert result['interval_map'] == ''
        assert result['interval_map_path'] == ''

    def test_one_column_is_not_a_stack(self, tool_impl):
        result = self._run(tool_impl,
                           values={'Interval_0.150_0.250': np.arange(8.0)})

        assert result['n_maps'] == 1
        assert result['interval_map'] == ''

    def test_bins_on_a_grid_keep_their_gaps_as_empty_rows(self, tool_impl):
        """Occupied bins need not be adjacent; the rows must still sit at
        their true bias, so the axis stays linear."""
        result = self._run(tool_impl, values={
            'a': np.full(8, 1.0), 'b': np.full(8, 2.0)},
            intervals=[[0.10, 0.11], [0.14, 0.15]])
        info = tool_impl._datasets[result['interval_map']].metadata.additional_info

        assert info['empty_bins'] == 3
        midpoints = np.asarray(info['interval_midpoints'])
        np.testing.assert_allclose(np.diff(midpoints), 0.01, rtol=1e-6)

    def test_hand_picked_intervals_are_not_forced_onto_a_grid(self, tool_impl):
        result = self._run(tool_impl, intervals=INTERVALS)
        assert tool_impl._datasets[result['interval_map']].num_points == 2


class TestWhereTheIntervalsComeFrom:
    """Three sources, in order: the port, the table's own metadata, its
    column names."""

    def _values(self):
        return {'Interval_-0.300_-0.200': np.arange(8.0),
                'Interval_0.150_0.250': np.arange(8.0)}

    def test_the_port_wins(self, tool_impl):
        tool_impl._datasets['values'] = _flat(
            self._values(), info={'intervals': [[0.0, 0.1], [0.2, 0.3]]})
        result = tool_impl.assemble_maps(
            MockTask(), 'values', params={'scan_type': 'line'},
            intervals=[[-0.5, -0.4], [0.5, 0.6]])

        assert result['columns'] == ['-0.500_-0.400', '0.500_0.600']

    def test_intervals_that_arrive_as_dicts_are_understood(self, tool_impl):
        """A wire carries whatever the node upstream had, and the Integration
        node passes hand-typed intervals through as ``{'lower', 'upper'}``
        dicts — which used to take the run down on the format string."""
        tool_impl._datasets['values'] = _flat(self._values())
        result = tool_impl.assemble_maps(
            MockTask(), 'values', params={'scan_type': 'line'},
            intervals=[{'lower': 0.0, 'upper': 0.1},
                       {'lower': 0.2, 'upper': 0.3}])

        assert result['columns'] == ['0.000_0.100', '0.200_0.300']

    def test_an_interval_given_backwards_is_put_the_right_way_round(self, tool_impl):
        tool_impl._datasets['values'] = _flat(self._values())
        result = tool_impl.assemble_maps(
            MockTask(), 'values', params={'scan_type': 'line'},
            intervals=[[0.1, 0.0], [0.3, 0.2]])

        assert result['columns'] == ['0.000_0.100', '0.200_0.300']

    def test_the_table_s_own_metadata_is_next(self, tool_impl):
        tool_impl._datasets['values'] = _flat(
            self._values(),
            info={'integration_intervals': [[0.0, 0.1], [0.2, 0.3]]})
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         params={'scan_type': 'line'})

        assert result['columns'] == ['0.000_0.100', '0.200_0.300']

    def test_the_column_names_are_the_last_resort(self, tool_impl):
        """A table round-tripped through CSV has lost its metadata; the names
        still say what each column was integrated over."""
        tool_impl._datasets['values'] = _flat(self._values())
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         params={'scan_type': 'line'})

        assert result['columns'] == ['-0.300_-0.200', '0.150_0.250']
        assert result['interval_map'] != ''

    def test_the_map_generator_s_own_naming_is_read_too(self, tool_impl):
        tool_impl._datasets['values'] = _flat({'-0.300_-0.200': np.arange(8.0),
                                               '0.150_0.250': np.arange(8.0)})
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         params={'scan_type': 'line'})

        assert result['columns'] == ['-0.300_-0.200', '0.150_0.250']

    def test_a_count_that_does_not_match_is_not_trusted(self, tool_impl):
        """Intervals pair with columns by position; three against two would
        put the wrong energy on every map."""
        tool_impl._datasets['values'] = _flat(self._values())
        result = tool_impl.assemble_maps(
            MockTask(), 'values', params={'scan_type': 'line'},
            intervals=[[0.0, 0.1], [0.2, 0.3], [0.4, 0.5]])

        assert result['columns'] == ['-0.300_-0.200', '0.150_0.250']

    def test_names_that_are_not_intervals_leave_the_run_without_an_axis(self, tool_impl):
        tool_impl._datasets['values'] = _flat({'size_nm': np.arange(8.0),
                                               'rrmse_pct': np.arange(8.0)})
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         params={'scan_type': 'line'})

        assert result['n_maps'] == 2
        assert result['interval_map'] == ''

    def test_a_partial_parse_is_no_parse(self, tool_impl):
        """Pairing half the columns with energies is worse than pairing none."""
        tool_impl._datasets['values'] = _flat({'Interval_0.150_0.250': np.arange(8.0),
                                               'size_nm': np.arange(8.0)})
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         params={'scan_type': 'line'})

        assert result['columns'] == ['Interval_0.150_0.250', 'size_nm']
        assert result['interval_map'] == ''


class TestAgreementWithTheMapGenerator:
    """Phase-1 acceptance: a hand-wired chain reproduces the composite."""

    @staticmethod
    def _generator(tool_impl, **params):
        tool_impl._datasets['line'] = _line_scan()
        return tool_impl.generate_maps_from_spectra(
            MockTask(), 'line',
            {'baseline': 'none', 'interval_source': 'manual', 'scan_type': 'line',
             'intervals': INTERVALS, 'noise_floor': 0.0, **params})

    def _reassembled(self, tool_impl, generated, **params):
        """Map Assembly over the numbers the Map Generator published."""
        return tool_impl.assemble_maps(
            MockTask(), generated['values_dataset'],
            params={'scan_type': 'line', **params},
            source_dataset_name='line')

    def test_the_joined_map_holds_the_same_numbers(self, tool_impl):
        generated = self._generator(tool_impl)
        reassembled = self._reassembled(tool_impl, generated)

        np.testing.assert_allclose(
            tool_impl._datasets[reassembled['interval_map']].spectra.to_numpy(),
            tool_impl._datasets[generated['interval_map']].spectra.to_numpy())

    def test_the_joined_map_is_on_the_same_energy_axis(self, tool_impl):
        generated = self._generator(tool_impl)
        reassembled = self._reassembled(tool_impl, generated)

        np.testing.assert_allclose(
            tool_impl._datasets[reassembled['interval_map']].independent_var,
            tool_impl._datasets[generated['interval_map']].independent_var)

    def test_the_per_interval_maps_are_identical(self, tool_impl):
        generated = self._generator(tool_impl)
        reassembled = self._reassembled(tool_impl, generated)

        assert len(reassembled['map_paths']) == len(generated['map_paths'])
        for mine, theirs in zip(reassembled['map_paths'], generated['map_paths']):
            # Named after the interval either way; only the dataset the name
            # is prefixed with differs, and the folders are separate.
            assert (Path(mine).stem.rsplit('_Map_', 1)[1]
                    == Path(theirs).stem.rsplit('_Map_', 1)[1])
            np.testing.assert_allclose(_csv_of(mine), _csv_of(theirs))

    def test_the_scale_on_disk_is_identical(self, tool_impl):
        generated = self._generator(tool_impl)
        reassembled = self._reassembled(tool_impl, generated)

        mine = _gsf(reassembled['interval_map_path'])
        theirs = _gsf(generated['interval_map_path'])

        # Everything the file says about the axes, not a chosen few keys.
        # Only the title differs, and only by the dataset it is named after.
        assert set(mine) == set(theirs)
        for key, value in theirs.items():
            if key == 'Title':
                continue
            if isinstance(value, (int, float)):
                assert mine[key] == pytest.approx(value), key
            else:
                assert mine[key] == value, key
        assert (mine['Title'].split('_IntervalMap')[-1]
                == theirs['Title'].split('_IntervalMap')[-1])

    def test_the_detected_run_reproduces_too(self, tool_impl):
        """Not just hand-typed intervals: the bins a peak search found, with
        their empty rows, come back the same way."""
        tool_impl._datasets['line'] = _line_scan()
        generated = tool_impl.generate_maps_from_spectra(
            MockTask(), 'line', {'scan_type': 'line'})
        assert generated['n_maps'] > 1

        reassembled = self._reassembled(tool_impl, generated)
        mine = tool_impl._datasets[reassembled['interval_map']]
        theirs = tool_impl._datasets[generated['interval_map']]

        np.testing.assert_allclose(mine.spectra.to_numpy(), theirs.spectra.to_numpy())
        np.testing.assert_allclose(mine.independent_var, theirs.independent_var)
        assert (mine.metadata.additional_info['empty_bins']
                == theirs.metadata.additional_info['empty_bins'])

    def test_an_integration_result_assembles_into_the_same_maps(self, tool_impl):
        """The whole decomposition, end to end: Integration writes the flat
        table, Map Assembly lays it out, and the composite is reproduced."""
        from src.backend.app_backend import AppBackend

        generated = self._generator(tool_impl)
        AppBackend._do_integrate(
            tool_impl, MockTask(), 'line',
            [{'lower': lo, 'upper': hi} for lo, hi in INTERVALS])
        assembled = tool_impl.assemble_maps(
            MockTask(), 'line - Integrated', params={'scan_type': 'line'},
            source_dataset_name='line')

        np.testing.assert_allclose(
            tool_impl._datasets[assembled['interval_map']].spectra.to_numpy(),
            tool_impl._datasets[generated['interval_map']].spectra.to_numpy())

    def test_the_chain_does_not_need_the_spectra_wired_in(self, tool_impl):
        """Integration records its source, so the positions survive a chain
        that only carries the flat table forward."""
        from src.backend.app_backend import AppBackend

        generated = self._generator(tool_impl)
        AppBackend._do_integrate(
            tool_impl, MockTask(), 'line',
            [{'lower': lo, 'upper': hi} for lo, hi in INTERVALS])
        assembled = tool_impl.assemble_maps(
            MockTask(), 'line - Integrated', params={'scan_type': 'line'})

        assert (_gsf(assembled['map_paths'][0])['XReal']
                == pytest.approx(_gsf(generated['map_paths'][0])['XReal']))


class TestBadInput:
    """What it does instead of raising."""

    def test_a_missing_table_is_reported(self, tool_impl):
        result = tool_impl.assemble_maps(MockTask(), 'nope')

        assert result['n_maps'] == 0
        tool_impl.errorOccurred.emit.assert_called_once()

    def test_a_missing_source_is_reported(self, tool_impl):
        tool_impl._datasets['values'] = _flat({'a': np.arange(8.0)})
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         source_dataset_name='nope')

        assert result['n_maps'] == 0
        tool_impl.errorOccurred.emit.assert_called_once()

    def test_a_table_of_nothing_but_the_index_is_reported(self, tool_impl):
        index_only = _flat({'a': np.arange(8.0)})
        index_only.data.drop(columns=['a'], inplace=True)
        tool_impl._datasets['values'] = index_only
        result = tool_impl.assemble_maps(MockTask(), 'values')

        assert result['n_maps'] == 0
        assert 'value column' in tool_impl.errorOccurred.emit.call_args[0][1]

    def test_cancelling_writes_nothing_back(self, tool_impl):
        tool_impl._datasets['values'] = _flat({'a': np.arange(8.0),
                                               'b': np.arange(8.0)})
        result = tool_impl.assemble_maps(CancelledTask(), 'values',
                                         params={'scan_type': 'line'})

        assert result['n_maps'] == 0
        assert result['interval_map'] == ''
        assert not any(name.endswith('Interval Map') for name in tool_impl._datasets)

    def test_progress_reaches_the_end(self, tool_impl):
        task = MockTask()
        tool_impl._datasets['values'] = _flat({'a': np.arange(8.0)})
        tool_impl.assemble_maps(task, 'values', params={'scan_type': 'line'})

        assert task.progress == 1.0

    def test_workflow_mode_registers_without_announcing(self, tool_impl):
        tool_impl._workflow_mode = True
        tool_impl._datasets['line'] = _line_scan()
        tool_impl._datasets['values'] = _flat(
            {'Interval_-0.300_-0.200': np.arange(8.0),
             'Interval_0.150_0.250': np.arange(8.0)})
        result = tool_impl.assemble_maps(MockTask(), 'values',
                                         params={'scan_type': 'line'},
                                         source_dataset_name='line')

        assert result['interval_map'] in tool_impl._datasets
        tool_impl.dataLoaded.emit.assert_not_called()


class TestMapAssemblyExecution:
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
        node = create_node_from_tool("MapAssembly", 0, 0)
        node.parameters.update(params)
        return node

    def _flat_input(self):
        return _flat({'Interval_-0.300_-0.200': np.arange(8.0),
                      'Interval_0.150_0.250': np.arange(8.0) * 2})

    def test_fills_the_three_ports(self, executor):
        outputs = executor._execute_node(self._node(scan_type='line'),
                                         {'flat_data': self._flat_input()})

        assert set(outputs) == {"maps", "interval_map", "interval_map_path"}
        assert len(outputs['maps']) == 2
        assert isinstance(outputs['interval_map'], SpectralData)
        assert outputs['interval_map_path'].endswith('_IntervalMap.tiff')

    def test_the_intervals_port_names_the_rows(self, executor):
        outputs = executor._execute_node(
            self._node(scan_type='line'),
            {'flat_data': _flat({'a': np.arange(8.0), 'b': np.arange(8.0)}),
             'intervals': [[0.0, 0.1], [0.2, 0.3]]})

        # A grid of 0.1-wide bins: the unoccupied one between them stays a
        # row, so the energy axis is linear.
        np.testing.assert_allclose(outputs['interval_map'].independent_var,
                                   [0.05, 0.15, 0.25])

    def test_the_source_port_supplies_the_positions(self, executor):
        outputs = executor._execute_node(
            self._node(scan_type='line'),
            {'flat_data': self._flat_input(), 'source': _line_scan()})

        assert (outputs['interval_map'].metadata.additional_info['position_step_m']
                == pytest.approx(STEP_M))

    def test_the_joined_map_can_be_turned_off(self, executor):
        outputs = executor._execute_node(self._node(scan_type='line',
                                                    joined_map=False),
                                         {'flat_data': self._flat_input()})

        assert len(outputs['maps']) == 2
        assert outputs['interval_map'] is None

    def test_a_string_input_is_rejected(self, executor):
        assert executor._execute_node(self._node(),
                                      {'flat_data': 'Some Dataset'}) == {}

    def test_nothing_happens_without_the_values(self, executor):
        assert executor._execute_node(self._node(),
                                      {'source': _line_scan()}) == {}
