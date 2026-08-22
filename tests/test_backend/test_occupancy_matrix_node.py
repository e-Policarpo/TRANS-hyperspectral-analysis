"""
Tests for the Occupancy Matrix node: a peak table plus an axis turned into the
1/blank table Confinement Analysis emits.

The claim under test is reproduction. The engine builds these tables from
``Analysis`` objects, which only the tool that ran the search holds; the node
builds them from the peak table a wire can carry, and the two must land on the
same cells — otherwise a decomposed chain only resembles the composite.

The other claim is that blank is blank. A mark is 1, an unmarked cell is NaN in
memory and an empty cell on disk, and never a zero: zero is a measured value.
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

#: The detection knobs the composite is run with; pinning `height` keeps the
#: Map Generator's 3 sigma from differing from Confinement Analysis's 2.
DETECT = {'baseline': 'poly-iter', 'baseline_degree': 5, 'height': 5.0}


def _line_scan(n_spectra=6):
    """Spectra with sharp in-gap states on a steep band-edge background.

    Spectrum n carries the first ``n % 4 + 1`` states, so the columns differ
    from one another and a table that ignored the spectrum index would show it.
    """
    x = np.linspace(-0.6, 0.6, 1024)
    band_edges = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)
    columns = {}
    for n in range(n_spectra):
        y = band_edges.copy()
        for centre in CENTERS[:n % 4 + 1]:
            y = y + 1.2e-8 * np.exp(-0.5 * ((x - centre) / 0.004) ** 2)
        columns[f"P{n + 1}"] = y
    return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
        source_type='sts', dimensions=(n_spectra, 1), scan_mode='point',
        units={'independent': 'V'},
        additional_info={'spatial_layout': 'line', 'position_step_m': 1e-9}))


def _flat_source(n_spectra=3, points=101, lo=-0.5, hi=0.5, descending=False):
    """A featureless sweep — only its axis and column list are ever used."""
    x = np.linspace(hi, lo, points) if descending else np.linspace(lo, hi, points)
    columns = {chr(ord('A') + i): np.zeros_like(x) for i in range(n_spectra)}
    return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
        source_type='sts', dimensions=(n_spectra, 1), scan_mode='point',
        units={'independent': 'V'},
        additional_info={'spatial_layout': 'line', 'position_step_m': 2e-9}))


def _peak_table(rows, columns=('position_value', 'spectrum_index'), extra=None):
    """A minimal peak table in the shape find_peaks / analyze_confinement emit."""
    frame = pd.DataFrame(rows, columns=list(columns))
    for name, values in (extra or {}).items():
        frame[name] = values
    return SpectralData(frame, SpectralMetadata(
        source_type='peak_table', dimensions=(len(frame.columns) - 1, 1),
        scan_mode='peaks', units={'x': 'position'}, additional_info={}))


def _marks(dataset):
    """The mark columns of a registered matrix, without the axis column."""
    return dataset.data.iloc[:, 1:].to_numpy()


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


class TestOccupancyMatrixNodeDefinition:
    """The node as the palette and the executor see it."""

    def test_node_is_registered_in_the_analysis_category(self):
        node_def = TOOL_DEFINITIONS["OccupancyMatrix"]
        assert node_def["category"] == "Analysis"
        assert node_def["display_name"] == "Occupancy Matrix"

    def test_only_the_peak_table_is_required(self):
        inputs = {i["id"]: i for i in TOOL_DEFINITIONS["OccupancyMatrix"]["inputs"]}
        assert set(inputs) == {"peaks", "dataset", "intervals"}
        assert inputs["peaks"]["required"] is True
        assert inputs["dataset"].get("required") is False
        assert inputs["intervals"].get("required") is False

    def test_input_port_types_match_what_the_dispatch_reads(self):
        inputs = {i["id"]: i for i in TOOL_DEFINITIONS["OccupancyMatrix"]["inputs"]}
        assert inputs["peaks"]["port_type"] == "dataset"
        assert inputs["dataset"]["port_type"] == "dataset"
        assert inputs["intervals"]["port_type"] == "intervals"

    def test_output_port_types_match_what_the_dispatch_writes(self):
        outs = {o["id"]: o for o in TOOL_DEFINITIONS["OccupancyMatrix"]["outputs"]}
        assert set(outs) == {"matrix", "matrix_offset", "peak_count"}
        assert outs["matrix"]["port_type"] == "dataset"
        assert outs["matrix_offset"]["port_type"] == "dataset"
        assert outs["peak_count"]["port_type"] == "flat_data"

    def test_the_node_has_no_knobs(self):
        assert TOOL_DEFINITIONS["OccupancyMatrix"]["parameters"] == {}
        assert create_node_from_tool("OccupancyMatrix", 0, 0).parameters == {}

    def test_it_sits_next_to_energy_binning_in_the_palette(self):
        analysis = next(c["tools"] for c in get_tool_categories()
                        if c["category"] == "Analysis")
        assert (analysis.index("OccupancyMatrix")
                - analysis.index("EnergyBinning")) == 1

    def test_energy_binning_feeds_its_bins_and_the_spectra_feed_the_axis(self):
        wf = Workflow(id="wf_om", name="Occupancy WF")
        source = create_node_from_tool("DatasetInput", 0, 0)
        finder = create_node_from_tool("PeakFinder", 200, 0)
        binning = create_node_from_tool("EnergyBinning", 400, 0)
        matrix = create_node_from_tool("OccupancyMatrix", 600, 0)
        for node in (source, finder, binning, matrix):
            wf.add_node(node)

        for cid, src, port, target_port in (
                ("c1", finder, "peaks", "peaks"),
                ("c2", source, "dataset", "dataset")):
            assert wf.add_connection(Connection(
                id=cid, source_node_id=src.id, source_port_id=port,
                target_node_id=matrix.id, target_port_id=target_port)) is True

        assert wf.add_connection(Connection(
            id="c3", source_node_id=binning.id, source_port_id="all_bins",
            target_node_id=matrix.id, target_port_id="intervals")) is True

    def test_the_tables_can_be_captured_and_the_counts_mapped(self):
        wf = Workflow(id="wf_om2", name="Occupancy WF")
        matrix = create_node_from_tool("OccupancyMatrix", 0, 0)
        output = create_node_from_tool("DatasetOutput", 200, 0)
        maps = create_node_from_tool("MapGenerator", 200, 200)
        for node in (matrix, output, maps):
            wf.add_node(node)

        assert wf.validate_connection(Connection(
            id="c1", source_node_id=matrix.id, source_port_id="matrix",
            target_node_id=output.id, target_port_id="dataset")) is True
        assert wf.validate_connection(Connection(
            id="c2", source_node_id=matrix.id, source_port_id="peak_count",
            target_node_id=maps.id, target_port_id="flat_data")) is True


class TestRowsOnTheMeasuredAxis:
    """No bins connected: one row per sample of the source sweep."""

    def _run(self, tool_impl, peaks, source=None, **kwargs):
        tool_impl._datasets['peaks'] = peaks
        if source is not None:
            tool_impl._datasets['sts'] = source
        return tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks',
            source_dataset_name='sts' if source is not None else None, **kwargs)

    def test_the_marks_land_on_the_recorded_sample_index(self, tool_impl):
        source = _flat_source(points=51)
        peaks = _peak_table([(source.independent_var[7], 0),
                             (source.independent_var[30], 2)],
                            extra={'position_index': [7, 30]})

        result = self._run(tool_impl, peaks, source)

        marks = _marks(result['matrix'])
        assert marks.shape == (51, 3)
        assert marks[7, 0] == 1.0
        assert marks[30, 2] == 1.0
        assert np.isfinite(marks).sum() == 2

    def test_a_blank_cell_is_nan_and_never_zero(self, tool_impl):
        source = _flat_source(points=20)
        peaks = _peak_table([(source.independent_var[3], 1)],
                            extra={'position_index': [3]})

        result = self._run(tool_impl, peaks, source)

        marks = _marks(result['matrix'])
        assert np.isnan(marks[0, 0])
        assert not (marks == 0).any()

    def test_a_spectrum_with_no_peaks_still_gets_a_blank_column(self, tool_impl):
        source = _flat_source(n_spectra=3, points=20)
        peaks = _peak_table([(source.independent_var[3], 0)],
                            extra={'position_index': [3]})

        result = self._run(tool_impl, peaks, source)

        frame = result['matrix'].data
        assert list(frame.columns) == ['V', 'A', 'B', 'C']
        assert frame['C'].isna().all()

    def test_without_the_source_the_peakless_tail_has_no_column(self, tool_impl):
        # Documented consequence, not a bug: a spectrum with no peak has no row
        # in the peak table, so nothing but the source can say it existed.
        peaks = _peak_table([(0.1, 0), (0.2, 0)])

        result = self._run(tool_impl, peaks, intervals=[[0.0, 0.15], [0.15, 0.3]])

        assert list(result['matrix'].data.columns) == ['position_value', 'col0']

    def test_the_axis_column_is_the_source_sweep(self, tool_impl):
        source = _flat_source(points=31)
        peaks = _peak_table([(source.independent_var[5], 0)],
                            extra={'position_index': [5]})

        result = self._run(tool_impl, peaks, source)

        frame = result['matrix'].data
        assert frame.columns[0] == 'V'
        np.testing.assert_allclose(frame['V'].to_numpy(), source.independent_var)

    def test_several_peaks_of_one_spectrum_on_one_row_are_one_mark(self, tool_impl):
        source = _flat_source(points=20)
        peaks = _peak_table([(source.independent_var[4], 1),
                             (source.independent_var[4], 1)],
                            extra={'position_index': [4, 4]})

        result = self._run(tool_impl, peaks, source)

        assert np.isfinite(_marks(result['matrix'])).sum() == 1

    def test_a_missing_position_index_falls_back_to_the_nearest_sample(self, tool_impl):
        source = _flat_source(points=101)
        # Between samples 60 and 61, closer to 60.
        between = float(source.independent_var[60]) + 0.0004
        peaks = _peak_table([(between, 1)])

        result = self._run(tool_impl, peaks, source)

        assert _marks(result['matrix'])[60, 1] == 1.0

    def test_the_nearest_sample_search_survives_a_descending_sweep(self, tool_impl):
        source = _flat_source(points=101, descending=True)
        peaks = _peak_table([(float(source.independent_var[12]), 0)])

        result = self._run(tool_impl, peaks, source)

        assert _marks(result['matrix'])[12, 0] == 1.0

    def test_a_sample_index_off_the_axis_is_dropped_not_wrapped(self, tool_impl):
        source = _flat_source(points=10)
        peaks = _peak_table([(0.0, 0), (0.0, 1)],
                            extra={'position_index': [4, 99]})

        result = self._run(tool_impl, peaks, source)

        assert np.isfinite(_marks(result['matrix'])).sum() == 1

    def test_bins_alone_are_enough_when_there_is_no_source(self, tool_impl):
        peaks = _peak_table([(0.05, 0), (0.25, 1)])

        result = self._run(tool_impl, peaks, intervals=[[0.0, 0.1], [0.2, 0.3]])

        assert _marks(result['matrix']).shape == (2, 2)
        assert result['matrix'].data.columns[0] == 'position_value'

    def test_neither_a_source_nor_bins_is_an_error(self, tool_impl):
        peaks = _peak_table([(0.05, 0)])
        tool_impl._datasets['peaks'] = peaks

        result = tool_impl.build_occupancy_matrix(MockTask(), 'peaks')

        assert result['matrix'] is None
        assert tool_impl.errorOccurred.emit.called
        message = tool_impl.errorOccurred.emit.call_args[0][1]
        assert "spectra" in message and "bins" in message


class TestRowsOnBins:
    """Bins connected: one row per interval, in ascending order."""

    def _run(self, tool_impl, peaks, intervals, source=None):
        tool_impl._datasets['peaks'] = peaks
        if source is not None:
            tool_impl._datasets['sts'] = source
        return tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks',
            source_dataset_name='sts' if source is not None else None,
            intervals=intervals)

    def test_the_rows_are_the_interval_midpoints_in_ascending_order(self, tool_impl):
        peaks = _peak_table([(0.25, 0)])

        result = self._run(tool_impl, peaks, [[0.2, 0.3], [0.0, 0.1]])

        np.testing.assert_allclose(
            result['matrix'].data.iloc[:, 0].to_numpy(), [0.05, 0.25])

    def test_a_peak_marks_the_bin_that_contains_it(self, tool_impl):
        peaks = _peak_table([(0.05, 0), (0.25, 1)])

        result = self._run(tool_impl, peaks, [[0.0, 0.1], [0.1, 0.2], [0.2, 0.3]],
                           source=_flat_source(n_spectra=2))

        marks = _marks(result['matrix'])
        assert marks[0, 0] == 1.0
        assert marks[2, 1] == 1.0
        assert np.isnan(marks[1]).all()

    def test_the_lower_edge_belongs_to_its_own_bin(self, tool_impl):
        peaks = _peak_table([(0.1, 0)])

        result = self._run(tool_impl, peaks, [[0.0, 0.1], [0.1, 0.2]])

        marks = _marks(result['matrix'])
        assert np.isnan(marks[0, 0])
        assert marks[1, 0] == 1.0

    def test_the_very_top_edge_is_not_lost(self, tool_impl):
        # A state sitting exactly at the end of the sweep is where a band edge
        # usually is; a half-open rule all the way up would drop it.
        peaks = _peak_table([(0.2, 0)])

        result = self._run(tool_impl, peaks, [[0.0, 0.1], [0.1, 0.2]])

        assert _marks(result['matrix'])[1, 0] == 1.0

    def test_a_peak_in_a_gap_between_bins_marks_nothing(self, tool_impl):
        peaks = _peak_table([(0.15, 0)])

        result = self._run(tool_impl, peaks, [[0.0, 0.1], [0.2, 0.3]],
                           source=_flat_source(n_spectra=1))

        assert not np.isfinite(_marks(result['matrix'])).any()

    def test_a_peak_below_the_first_bin_marks_nothing(self, tool_impl):
        peaks = _peak_table([(-5.0, 0)])

        result = self._run(tool_impl, peaks, [[0.0, 0.1]],
                           source=_flat_source(n_spectra=1))

        assert not np.isfinite(_marks(result['matrix'])).any()

    def test_several_peaks_of_one_spectrum_in_one_bin_are_one_mark(self, tool_impl):
        peaks = _peak_table([(0.02, 0), (0.04, 0), (0.06, 0)])

        result = self._run(tool_impl, peaks, [[0.0, 0.1]],
                           source=_flat_source(n_spectra=1))

        assert np.isfinite(_marks(result['matrix'])).sum() == 1

    def test_the_bins_win_over_the_source_axis(self, tool_impl):
        peaks = _peak_table([(0.05, 0)], extra={'position_index': [3]})

        result = self._run(tool_impl, peaks, [[0.0, 0.1], [0.1, 0.2]],
                           source=_flat_source(points=101))

        assert _marks(result['matrix']).shape[0] == 2


class TestTheOffsetTableAndTheCounts:
    """The two companions of the matrix."""

    def _run(self, tool_impl):
        source = _flat_source(n_spectra=3, points=20)
        peaks = _peak_table([(source.independent_var[2], 0),
                             (source.independent_var[5], 2),
                             (source.independent_var[9], 2)],
                            extra={'position_index': [2, 5, 9]})
        tool_impl._datasets['sts'] = source
        tool_impl._datasets['peaks'] = peaks
        return tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts')

    def test_each_column_of_the_offset_table_carries_its_own_number(self, tool_impl):
        result = self._run(tool_impl)

        marks = _marks(result['matrix_offset'])
        assert marks[2, 0] == 1.0
        assert marks[5, 2] == 3.0
        assert marks[9, 2] == 3.0

    def test_the_offset_table_marks_exactly_the_same_cells(self, tool_impl):
        result = self._run(tool_impl)

        np.testing.assert_array_equal(np.isfinite(_marks(result['matrix'])),
                                      np.isfinite(_marks(result['matrix_offset'])))

    def test_the_peak_count_has_one_row_per_spectrum(self, tool_impl):
        result = self._run(tool_impl)

        frame = result['peak_count'].data
        assert list(frame.columns) == ['Spectrum_Index', 'Peak_Count']
        assert frame['Peak_Count'].tolist() == [1, 0, 2]

    def test_the_peak_count_is_flat_data(self, tool_impl):
        result = self._run(tool_impl)

        assert result['peak_count'].metadata.data_type == 'flat'

    def test_a_peak_off_the_grid_still_counts_for_its_spectrum(self, tool_impl):
        # The count answers "how many peaks does this spectrum have"; making it
        # disagree with the peak table would read as a bug in the search.
        peaks = _peak_table([(0.05, 0), (9.9, 0)])
        tool_impl._datasets['peaks'] = peaks
        tool_impl._datasets['sts'] = _flat_source(n_spectra=1)

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts',
            intervals=[[0.0, 0.1]])

        assert result['peak_count'].data['Peak_Count'].tolist() == [2]
        assert np.isfinite(_marks(result['matrix'])).sum() == 1


class TestTheWrittenCsv:
    """Exports: bare integers and empty cells, like the composite writes."""

    def _run(self, tool_impl):
        source = _flat_source(n_spectra=2, points=4)
        peaks = _peak_table([(source.independent_var[1], 0),
                             (source.independent_var[2], 1)],
                            extra={'position_index': [1, 2]})
        tool_impl._datasets['sts'] = source
        tool_impl._datasets['peaks'] = peaks
        return tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts')

    def test_marks_are_written_as_bare_integers(self, tool_impl):
        result = self._run(tool_impl)

        rows = open(result['matrix_path']).read().strip().splitlines()
        assert rows[0] == 'V,A,B'
        assert rows[2].endswith(',1,')
        assert '1.0' not in rows[2]

    def test_blanks_are_written_as_empty_cells(self, tool_impl):
        result = self._run(tool_impl)

        rows = open(result['matrix_path']).read().strip().splitlines()
        assert rows[1].split(',')[1:] == ['', '']
        assert '0' not in ','.join(rows[1].split(',')[1:])

    def test_the_offset_table_gets_its_own_file(self, tool_impl):
        result = self._run(tool_impl)

        assert result['offset_matrix_path'] != result['matrix_path']
        assert result['offset_matrix_path'].endswith('_OccupancyMatrix_offset.csv')

    def test_both_files_land_in_the_peaks_folder(self, tool_impl):
        from pathlib import Path

        result = self._run(tool_impl)

        assert Path(result['matrix_path']).parent.name == 'peaks'
        assert Path(result['offset_matrix_path']).parent.name == 'peaks'

    def test_the_energy_axis_keeps_its_precision(self, tool_impl):
        # Only the mark columns are stringified; a global float_format would
        # round the axis the states are reported at.
        result = self._run(tool_impl)

        rows = open(result['matrix_path']).read().strip().splitlines()
        axis = [float(row.split(',')[0]) for row in rows[1:]]
        np.testing.assert_allclose(axis, tool_impl._datasets['sts'].independent_var)


class TestRegistrationAndMetadata:
    """What lands in the project, and what it remembers."""

    def _run(self, tool_impl, **kwargs):
        source = _flat_source(n_spectra=2, points=20)
        peaks = _peak_table([(source.independent_var[4], 0)],
                            extra={'position_index': [4]})
        tool_impl._datasets['My Scan'] = source
        tool_impl._datasets['My Scan - Peaks'] = peaks
        return tool_impl.build_occupancy_matrix(
            MockTask(), 'My Scan - Peaks', source_dataset_name='My Scan', **kwargs)

    def test_three_datasets_are_registered_under_the_source_name(self, tool_impl):
        result = self._run(tool_impl)

        assert set(result['dataset_names'].values()) == {
            'My Scan - Occupancy Matrix',
            'My Scan - Occupancy Matrix (offset)',
            'My Scan - Peak Count'}
        for name in result['dataset_names'].values():
            assert name in tool_impl._datasets

    def test_the_browser_is_told_about_each_one(self, tool_impl):
        result = self._run(tool_impl)

        told = {call[0][0] for call in tool_impl.dataLoaded.emit.call_args_list}
        assert told == set(result['dataset_names'].values())

    def test_workflow_mode_registers_without_announcing(self, tool_impl):
        tool_impl._workflow_mode = True

        result = self._run(tool_impl)

        assert tool_impl.dataLoaded.emit.call_count == 0
        assert 'My Scan - Occupancy Matrix' in tool_impl._datasets

    def test_the_peaks_dataset_names_the_output_when_there_is_no_source(self, tool_impl):
        tool_impl._datasets['Loose Peaks'] = _peak_table([(0.05, 0)])

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'Loose Peaks', intervals=[[0.0, 0.1]])

        assert result['dataset_names']['Occupancy Matrix'] == \
            'Loose Peaks - Occupancy Matrix'

    def test_the_run_records_where_it_came_from(self, tool_impl):
        result = self._run(tool_impl)

        info = result['matrix'].metadata.additional_info
        assert info['created_from'] == 'occupancy_matrix'
        assert info['source_dataset'] == 'My Scan'
        assert info['peaks_dataset'] == 'My Scan - Peaks'
        assert info['binned'] is False
        assert info['n_rows'] == 20
        assert info['total_peaks'] == 1

    def test_a_binned_run_says_so(self, tool_impl):
        result = self._run(tool_impl, intervals=[[0.0, 0.1], [0.1, 0.2]])

        assert result['matrix'].metadata.additional_info['binned'] is True

    def test_the_offset_table_is_flagged_as_offset(self, tool_impl):
        result = self._run(tool_impl)

        assert result['matrix_offset'].metadata.additional_info['offset'] is True
        assert 'offset' not in result['matrix'].metadata.additional_info

    def test_the_spatial_keys_survive(self, tool_impl):
        result = self._run(tool_impl)

        info = result['matrix'].metadata.additional_info
        assert info['spatial_layout'] == 'line'
        assert info['position_step_m'] == 2e-9

    def test_a_table_of_marks_is_not_overlaid_on_the_source_graph(self, tool_impl):
        result = self._run(tool_impl)

        for name in ('matrix', 'matrix_offset', 'peak_count'):
            assert 'original' not in result[name].metadata.additional_info

    def test_the_flat_counts_do_not_pretend_to_be_spectra(self, tool_impl):
        result = self._run(tool_impl)

        info = result['peak_count'].metadata.additional_info
        assert 'spectrum_meta' not in info and 'position_m' not in info


class TestBadInput:
    """Faults report themselves instead of raising through the worker."""

    def test_a_missing_peak_table(self, tool_impl):
        result = tool_impl.build_occupancy_matrix(MockTask(), 'nope')

        assert result['matrix'] is None
        tool_impl.errorOccurred.emit.assert_called_with("Error", "Peak table not found")

    def test_a_missing_source_dataset(self, tool_impl):
        tool_impl._datasets['peaks'] = _peak_table([(0.05, 0)])

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='gone')

        assert result['matrix'] is None
        tool_impl.errorOccurred.emit.assert_called_with("Error", "Dataset not found")

    def test_a_table_without_the_columns_names_them(self, tool_impl):
        frame = pd.DataFrame({'x': [1.0, 2.0], 'height': [3.0, 4.0]})
        tool_impl._datasets['peaks'] = SpectralData(frame, SpectralMetadata(
            source_type='peak_table', dimensions=(1, 1), scan_mode='peaks', units={}))

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', intervals=[[0.0, 1.0]])

        assert result['matrix'] is None
        message = tool_impl.errorOccurred.emit.call_args[0][1]
        assert 'spectrum_index' in message and 'position_value' in message

    def test_the_flat_data_capitalisation_is_accepted(self, tool_impl):
        peaks = _peak_table([(0.05, 0)],
                            columns=('Position_Value', 'Spectrum_Index'))
        tool_impl._datasets['peaks'] = peaks

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', intervals=[[0.0, 0.1]])

        assert np.isfinite(_marks(result['matrix'])).sum() == 1

    def test_a_peak_with_no_position_is_dropped(self, tool_impl):
        peaks = _peak_table([(0.05, 0), (np.nan, 1), (0.05, np.nan)])
        tool_impl._datasets['peaks'] = peaks
        tool_impl._datasets['sts'] = _flat_source(n_spectra=3)

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts',
            intervals=[[0.0, 0.1]])

        assert result['peak_count'].data['Peak_Count'].tolist() == [1, 0, 0]

    def test_an_empty_table_over_real_spectra_is_an_all_blank_matrix(self, tool_impl):
        # A search that found nothing is a result, not a fault.
        tool_impl._datasets['peaks'] = _peak_table(
            np.empty((0, 2)), columns=('position_value', 'spectrum_index'))
        tool_impl._datasets['sts'] = _flat_source(n_spectra=2, points=10)

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts')

        assert not np.isfinite(_marks(result['matrix'])).any()
        assert result['peak_count'].data['Peak_Count'].tolist() == [0, 0]

    def test_an_empty_table_with_nothing_to_name_the_columns_gives_up(self, tool_impl):
        tool_impl._datasets['peaks'] = _peak_table(
            np.empty((0, 2)), columns=('position_value', 'spectrum_index'))

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', intervals=[[0.0, 0.1]])

        assert result['matrix'] is None
        assert result['dataset_names'] == {}

    def test_a_spectrum_index_beyond_the_source_is_ignored(self, tool_impl):
        peaks = _peak_table([(0.05, 0), (0.05, 7)])
        tool_impl._datasets['peaks'] = peaks
        tool_impl._datasets['sts'] = _flat_source(n_spectra=2)

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts',
            intervals=[[0.0, 0.1]])

        assert result['peak_count'].data['Peak_Count'].tolist() == [1, 0]

    def test_a_float_spectrum_index_is_cast(self, tool_impl):
        peaks = _peak_table([(0.05, 1.0)])
        tool_impl._datasets['peaks'] = peaks
        tool_impl._datasets['sts'] = _flat_source(n_spectra=2)

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts',
            intervals=[[0.0, 0.1]])

        assert _marks(result['matrix'])[0, 1] == 1.0

    def test_cancellation_registers_nothing(self, tool_impl):
        source = _flat_source(n_spectra=2, points=10)
        tool_impl._datasets['sts'] = source
        tool_impl._datasets['peaks'] = _peak_table(
            [(source.independent_var[3], 0)], extra={'position_index': [3]})

        result = tool_impl.build_occupancy_matrix(
            CancelledTask(), 'peaks', source_dataset_name='sts')

        assert result['matrix'] is None
        assert tool_impl._datasets.keys() == {'sts', 'peaks'}

    def test_progress_reaches_the_end(self, tool_impl):
        source = _flat_source(n_spectra=4, points=10)
        tool_impl._datasets['sts'] = source
        tool_impl._datasets['peaks'] = _peak_table(
            [(source.independent_var[3], 0)], extra={'position_index': [3]})
        task = MockTask()

        tool_impl.build_occupancy_matrix(task, 'peaks', source_dataset_name='sts')

        assert task.progress == 100


class TestAgreementWithConfinementAnalysis:
    """The node must rebuild the composite's tables from the composite's peaks.

    This is Phase 1's acceptance claim in miniature: the same peaks, put
    through the node, give the same occupancy table cell for cell.
    """

    def _analyse(self, tool_impl, **params):
        tool_impl._datasets['sts'] = _line_scan()
        return tool_impl.analyze_confinement(
            MockTask(), 'sts', params={**DETECT, **params})

    def test_it_rebuilds_the_full_resolution_peak_matrix(self, tool_impl):
        analysis = self._analyse(tool_impl)
        tool_impl._datasets['peaks'] = analysis['peaks']

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts')

        expected = _marks(analysis['peak_matrix'])
        got = _marks(result['matrix'])
        assert np.isfinite(expected).sum() > 0
        np.testing.assert_array_equal(np.isfinite(expected), np.isfinite(got))
        np.testing.assert_array_equal(np.nan_to_num(expected), np.nan_to_num(got))

    def test_it_rebuilds_the_offset_table_too(self, tool_impl):
        analysis = self._analyse(tool_impl)
        tool_impl._datasets['peaks'] = analysis['peaks']

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts')

        np.testing.assert_array_equal(
            np.nan_to_num(_marks(analysis['peak_matrix_offset'])),
            np.nan_to_num(_marks(result['matrix_offset'])))

    def test_it_rebuilds_the_peak_counts(self, tool_impl):
        analysis = self._analyse(tool_impl)
        tool_impl._datasets['peaks'] = analysis['peaks']

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts')

        assert (result['peak_count'].data['Peak_Count'].tolist()
                == analysis['peak_count'].data['Peak_Count'].tolist())

    def test_energy_binnings_bins_rebuild_the_binned_table(self, tool_impl):
        analysis = self._analyse(tool_impl, temperature_k=94.0)
        tool_impl._datasets['peaks'] = analysis['peaks']
        bins = tool_impl.bin_peak_energies(
            MockTask(), 'peaks', params={'temperature_k': 94.0},
            source_dataset_name='sts')

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts',
            intervals=bins['all_bins'])

        expected = analysis['peak_matrix_binned']
        np.testing.assert_allclose(result['matrix'].data.iloc[:, 0].to_numpy(),
                                   expected.data.iloc[:, 0].to_numpy())
        np.testing.assert_array_equal(np.nan_to_num(_marks(expected)),
                                      np.nan_to_num(_marks(result['matrix'])))

    def test_the_csv_matches_the_composites_byte_for_byte(self, tool_impl):
        analysis = self._analyse(tool_impl)
        tool_impl._datasets['peaks'] = analysis['peaks']

        result = tool_impl.build_occupancy_matrix(
            MockTask(), 'peaks', source_dataset_name='sts')

        assert (open(result['matrix_path']).read()
                == open(analysis['matrix_path']).read())


class TestOccupancyMatrixExecution:
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

    def _node(self):
        return create_node_from_tool("OccupancyMatrix", 0, 0)

    def test_fills_the_three_ports(self, executor):
        source = _flat_source(n_spectra=2, points=21)
        peaks = _peak_table([(source.independent_var[3], 0)],
                            extra={'position_index': [3]})

        outputs = executor._execute_node(
            self._node(), {'peaks': peaks, 'dataset': source})

        assert set(outputs) == {"matrix", "matrix_offset", "peak_count"}
        assert isinstance(outputs['matrix'], SpectralData)
        assert _marks(outputs['matrix']).shape == (21, 2)

    def test_the_bins_port_replaces_the_axis(self, executor):
        source = _flat_source(n_spectra=2, points=21)
        peaks = _peak_table([(0.05, 0)])

        outputs = executor._execute_node(
            self._node(),
            {'peaks': peaks, 'dataset': source,
             'intervals': [[0.0, 0.1], [0.1, 0.2]]})

        assert _marks(outputs['matrix']).shape == (2, 2)

    def test_runs_on_the_peak_table_and_bins_alone(self, executor):
        peaks = _peak_table([(0.05, 0), (0.15, 1)])

        outputs = executor._execute_node(
            self._node(), {'peaks': peaks, 'intervals': [[0.0, 0.1], [0.1, 0.2]]})

        assert _marks(outputs['matrix']).shape == (2, 2)

    def test_a_string_input_is_rejected(self, executor):
        outputs = executor._execute_node(self._node(), {'peaks': 'Some Dataset'})

        assert outputs == {}
