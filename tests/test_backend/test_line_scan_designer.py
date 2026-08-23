"""
Tests for the Line Scan Designer.

The tool of the whole integration: one confinement search per position, and
a map of where along the line the confinement actually is. The claims are
recovery (a well planted at some positions comes back at those positions)
and honesty (the rest come back empty, with the reason, and never as zero).

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

import re

import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import Mock

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.physics.analytical import box_energies_1d_eV


class MockTask:
    cancelled = False
    progress = 0


class CancellingTask:
    """Cancels once the run has started, the way the Cancel button does."""

    def __init__(self, after=2):
        self.after = after
        self.progress = 0
        self._seen = 0

    @property
    def cancelled(self):
        self._seen += 1
        return self._seen > self.after

    @cancelled.setter
    def cancelled(self, value):
        pass


STEP_M = 5e-9
BAND_EDGE = 0.30
WELL_NM = 8.0


def _line(n_points=5, well_at=(2, 3), well_nm=WELL_NM, with_positions=True):
    """A line scan with a well at some positions and nothing at the others."""
    V = np.linspace(-0.2, 1.6, 901)
    columns = {}
    for i in range(n_points):
        y = 0.01 * np.random.RandomState(5 + i).randn(V.size)
        y = y + 4 * np.exp((V - 1.3) * 5) * (V > BAND_EDGE)
        if i in well_at:
            for level in [E for E, _ in box_energies_1d_eV(well_nm, 0.067, 3)][:3]:
                y = y + 0.5 * np.exp(-((V - (BAND_EDGE + level)) / 0.015) ** 2)
        columns[f"P{i + 1}"] = y
    info = {'spatial_layout': 'line'}
    if with_positions:
        info['spectrum_meta'] = [{'location_m': [n * STEP_M, 0.0]}
                                 for n in range(n_points)]
    return SpectralData(pd.DataFrame({"V": V, **columns}), SpectralMetadata(
        source_type='sts', dimensions=(n_points, 1), scan_mode='line',
        units={'independent': 'V', 'dependent': 'A/V'}, additional_info=info))


@pytest.fixture
def tool_impl(tmp_path):
    from src.backend.tool_implementations import ToolImplementations

    class MockBackend(ToolImplementations):
        def __init__(self):
            self._datasets = {}
            self._output_base_dir = tmp_path / "outputs"
            self._output_base_dir.mkdir(exist_ok=True)
            self.errorOccurred = Mock()
            self.dataLoaded = Mock()
            self._workflow_mode = False

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

    return MockBackend()


def _run(tool_impl, dataset=None, name='line', **params):
    tool_impl._datasets[name] = dataset if dataset is not None else _line()
    return tool_impl.design_line_scan(
        MockTask(), name,
        {'height': 3.0, 'maxsol': 1, 'seed': 20260823, 'ndim': '1D',
         'coords': 'cartesian', 'match': 'delta_e', 'Lmax': 20.0, **params})


def _table(tool_impl, result):
    return tool_impl._datasets[result['dataset']].data


class TestFindingTheWellAlongTheLine:
    def test_it_finds_the_well_only_where_the_well_is(self, tool_impl):
        result = _run(tool_impl)
        table = _table(tool_impl, result)

        converged = table[table['size_nm'].notna()]
        assert set(converged['point_index']) == {2, 3}
        assert converged['size_nm'].tolist() == pytest.approx(
            [WELL_NM, WELL_NM], rel=0.02)

    def test_a_bare_position_is_empty_and_says_why(self, tool_impl):
        """Absence is a result: a map where every point has a size lies."""
        table = _table(tool_impl, _run(tool_impl))
        bare = table[table['size_nm'].isna()]

        assert len(bare) == 3
        assert all(reason for reason in bare['reason'])

    def test_nothing_that_failed_is_written_as_zero(self, tool_impl):
        """Zero would map as a very small well and read as a measurement."""
        table = _table(tool_impl, _run(tool_impl))
        bare = table[table['reason'] != '']

        for column in ('size_nm', 'rrmse_pct', 'group', 'meff', 'dim_1_nm'):
            assert bare[column].isna().all(), column

    def test_a_converged_position_has_no_reason(self, tool_impl):
        table = _table(tool_impl, _run(tool_impl))

        assert (table[table['size_nm'].notna()]['reason'] == '').all()

    def test_the_positions_come_out_in_metres(self, tool_impl):
        table = _table(tool_impl, _run(tool_impl))

        assert table['position_m'].tolist() == pytest.approx(
            [n * STEP_M for n in range(5)])

    def test_without_positions_the_column_is_empty_not_invented(self, tool_impl):
        table = _table(tool_impl, _run(tool_impl, _line(with_positions=False)))

        assert table['position_m'].isna().all()

    def test_the_same_size_at_several_positions_is_one_group(self, tool_impl):
        result = _run(tool_impl)

        assert len(result['groups']) == 1
        assert result['groups'][0]['points'] == [2, 3]
        assert result['groups'][0]['size_nm'] == pytest.approx(WELL_NM, rel=0.02)

    def test_the_group_column_is_numeric_so_it_can_be_mapped(self, tool_impl):
        """A categorical string cannot be plotted or mapped; an integer can."""
        table = _table(tool_impl, _run(tool_impl))

        assert table['group'].dtype.kind == 'f'
        assert set(table[table['group'].notna()]['group']) == {0.0}

    def test_the_line_reads_as_empty_domain_empty(self, tool_impl):
        result = _run(tool_impl)

        assert [s['group'] for s in result['segments']] == [-1, 0, -1]
        assert [s['count'] for s in result['segments']] == [2, 2, 1]

    def test_the_summary_counts_the_reasons(self, tool_impl):
        summary = _run(tool_impl)['summary']

        assert summary['total'] == 5 and summary['converged'] == 2
        assert sum(summary['reasons'].values()) == 3


class TestTheTableItRegisters:
    def test_it_is_registered_and_announced(self, tool_impl):
        result = _run(tool_impl)

        assert result['dataset'] in tool_impl._datasets
        emitted = [c[0][0] for c in tool_impl.dataLoaded.emit.call_args_list]
        assert result['dataset'] in emitted

    def test_it_is_flat_data_one_row_per_position(self, tool_impl):
        result = _run(tool_impl)
        dataset = tool_impl._datasets[result['dataset']]

        assert dataset.metadata.data_type == 'flat'
        assert len(dataset.data) == 5

    def test_the_columns_are_the_agreed_ones(self, tool_impl):
        table = _table(tool_impl, _run(tool_impl))
        from src.backend.tool_implementations import ToolImplementations

        for column in ToolImplementations.LINE_DESIGNER_COLUMNS:
            assert column in table.columns
        assert 'dim_1_nm' in table.columns
        assert 'reason' in table.columns

    def test_the_reason_is_the_only_text_column(self, tool_impl):
        """Everything else has to be a number, or it cannot be mapped."""
        table = _table(tool_impl, _run(tool_impl))
        text = [c for c in table.columns if table[c].dtype == object]

        assert text == ['reason']

    def test_it_records_where_it_came_from_and_how(self, tool_impl):
        result = _run(tool_impl)
        info = tool_impl._datasets[result['dataset']].metadata.additional_info

        assert info['created_from'] == 'line_scan_designer'
        assert info['source_dataset'] == 'line'
        assert info['match'] == 'delta_e'

    def test_the_spatial_keys_survive_so_it_can_be_mapped(self, tool_impl):
        """A derivative of a line scan is still that line scan's spectra."""
        result = _run(tool_impl)
        info = tool_impl._datasets[result['dataset']].metadata.additional_info

        assert info.get('spectrum_meta')
        assert info.get('spatial_layout') == 'line'

    def test_it_writes_the_table_as_a_csv(self, tool_impl):
        result = _run(tool_impl)
        written = list((tool_impl._output_base_dir / 'confinement').glob('*.csv'))

        assert len(written) == 1
        assert 'reason' in written[0].read_text().splitlines()[0]

    def test_a_position_with_no_confinement_is_an_empty_cell(self, tool_impl):
        """NaN writes as nothing, which is what a reader should see."""
        _run(tool_impl)
        written = list((tool_impl._output_base_dir / 'confinement').glob('*.csv'))
        rows = written[0].read_text().splitlines()

        assert any(',,' in row for row in rows[1:])


class TestTheMapItWrites:
    def test_the_size_goes_out_as_a_calibrated_map(self, tool_impl):
        result = _run(tool_impl)

        assert len(result['map_paths']) == 1
        assert Path(result['map_paths'][0]).exists()
        assert 'size_nm' in result['map_paths'][0]

    def test_the_map_states_the_line_s_real_length(self, tool_impl):
        """The export rule: metres when the loader knows them."""
        from src.utils.gsf_io import read_gsf

        result = _run(tool_impl)
        tiff = Path(result['map_paths'][0])
        header = read_gsf(tiff.parent.parent / 'gsf' / (tiff.stem + '.gsf'))[1]

        assert header['XYUnits'] == 'm'
        assert header['XReal'] == pytest.approx(5 * STEP_M)

    def test_the_map_is_one_row(self, tool_impl):
        result = _run(tool_impl)
        tiff = Path(result['map_paths'][0])
        values = np.loadtxt(tiff.parent.parent / 'csv' / (tiff.stem + '.csv'),
                            delimiter=',', ndmin=2)

        assert values.shape == (1, 5)

    def test_the_bare_positions_are_blank_in_the_map_too(self, tool_impl):
        result = _run(tool_impl)
        tiff = Path(result['map_paths'][0])
        values = np.loadtxt(tiff.parent.parent / 'csv' / (tiff.stem + '.csv'),
                            delimiter=',', ndmin=2)

        assert np.isnan(values).sum() == 3


class TestWhenItCannotRun:
    def test_a_missing_dataset_is_reported(self, tool_impl):
        result = tool_impl.design_line_scan(MockTask(), 'nope')

        assert result['ok'] is False
        assert result['error'] == "Dataset not found"

    def test_a_bad_mass_list_names_the_field(self, tool_impl):
        result = _run(tool_impl, meff_e='0.067, abc')

        assert 'm*_e' in result['error']
        assert result['ok'] is False

    def test_a_line_with_no_states_anywhere_is_an_answer(self, tool_impl):
        result = _run(tool_impl, _line(well_at=()))
        table = _table(tool_impl, result)

        assert result['ok'] is True
        assert table['size_nm'].isna().all()
        assert result['groups'] == []

    def test_cancelling_stops_the_run_and_marks_the_rest(self, tool_impl):
        tool_impl._datasets['line'] = _line(n_points=5)
        result = tool_impl.design_line_scan(
            CancellingTask(after=2), 'line',
            {'height': 3.0, 'maxsol': 1, 'seed': 1, 'match': 'delta_e'})

        assert result['ok'] is True          # what ran is still reported
        reasons = [p['reason'] for p in result['points']]
        assert 'cancelled' in reasons

    def test_progress_reaches_the_end(self, tool_impl):
        task = MockTask()
        tool_impl._datasets['line'] = _line(n_points=3, well_at=(1,))
        tool_impl.design_line_scan(task, 'line',
                                   {'height': 3.0, 'maxsol': 1, 'seed': 1,
                                    'match': 'delta_e'})

        assert task.progress == 1.0


class TestWhatCrossesToQml:
    def test_the_result_is_json_serialisable(self, tool_impl):
        import json

        json.dumps(_run(tool_impl))

    def test_a_point_row_carries_what_the_strip_needs(self, tool_impl):
        rows = _run(tool_impl)['points']

        assert len(rows) == 5
        for row in rows:
            assert {'point_index', 'position_nm', 'size_nm', 'group',
                    'converged', 'reason'} <= set(row)

    def test_a_position_with_no_group_reports_minus_one(self, tool_impl):
        """QML has no None; -1 is the sentinel the strip plot skips."""
        rows = _run(tool_impl)['points']

        assert {r['group'] for r in rows if not r['converged']} == {-1}


class TestItRunsOverSeveralLines:
    def test_it_is_registered_as_a_batch_tool(self):
        """One entry is all a tool needs to accept several datasets."""
        from src.backend.batch_tools import BATCH_TOOLS

        spec = BATCH_TOOLS['line_scan_designer']
        assert spec.method == 'design_line_scan'
        assert spec.takes_task and spec.params_as_dict
        assert spec.completion == '_on_line_scan_design_completed'

    def test_each_line_gets_its_own_table(self, tool_impl):
        from src.backend.batch_tools import run_dataset_batch

        tool_impl._datasets['line A'] = _line(well_at=(2,))
        tool_impl._datasets['line B'] = _line(well_at=(1, 2))
        results = run_dataset_batch(
            tool_impl, MockTask(), 'line_scan_designer', ['line A', 'line B'],
            {'height': 3.0, 'maxsol': 1, 'seed': 1, 'match': 'delta_e'})

        assert len(results) == 2
        assert 'line A - Confinement' in tool_impl._datasets
        assert 'line B - Confinement' in tool_impl._datasets
