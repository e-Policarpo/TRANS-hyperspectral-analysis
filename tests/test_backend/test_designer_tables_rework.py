"""
Designer output tables after the rework: a paired row says e+h, a sweep
lists the spectra that found nothing, skipped quantum numbers are visible,
a line scan says when the peaks were all on the other branch, and a table
with text columns survives a project save.
"""

import pathlib

import numpy as np
import pandas as pd
import pytest

from src.backend.project_manager import ProjectManager
from src.backend.tool_implementations import ToolImplementations
from src.models.spectral_data import SpectralData, SpectralMetadata
from src.physics.line_scan import NO_BRANCH_PEAKS, NO_PEAKS, PointResult, analyze_line_scan, LineScan


class TestCandidateRows:
    def _rows(self, runs, params=None):
        class Stub(ToolImplementations):
            def __init__(self):
                self._datasets = {}
                self._workflow_mode = True
                self.dataLoaded = type("S", (), {"emit": lambda *a: None})()
            def _ensure_output_dir(self, sub):
                import tempfile, pathlib
                d = pathlib.Path(tempfile.mkdtemp()) / sub; d.mkdir(); return d
            def _sanitize_filename(self, n): return "x"
            def _extract_clean_base_name(self, n): return n
        stub = Stub()
        ds = SpectralData(pd.DataFrame({"V": [0.0, 1.0], "P1": [0.0, 1.0]}),
                          SpectralMetadata(source_type='t', dimensions=(1, 1), scan_mode='point',
                                           units={}, additional_info={}))
        names, _ = stub._register_designer_tables(runs, "d", ds, params or {})
        table = next((v for k, v in stub._datasets.items() if k.startswith("d - Designer Candidates")), None)
        return table.data if table is not None else None

    @staticmethod
    def cand(index=0, carrier='e', qn=((3,), (4,), (5,)), hole=None):
        c = {'index': index, 'carrier': carrier, 'dims_nm': (10.0,), 'size_nm': 10.0,
             'meff': 0.1, 'offset_eV': 0.0, 'rrmse': 1.0, 'rrmse_de': 1.0,
             'targets': [0.1] * len(qn), 'qn': [list(q) for q in qn]}
        if hole:
            c['hole'] = hole; c['pair_mismatch_nm'] = 0.2
        return c

    def test_a_paired_row_says_both_carriers(self):
        hole = self.cand(carrier='h', qn=((1,), (2,)))
        rows = self._rows([{'spectrum_index': 0, 'column': 'P1', 'peaks': {'peaks_V': [1, 2, 3]},
                            'candidates': [self.cand(hole=hole)], 'error': ''}])
        assert rows.loc[0, 'carrier'] == 'e+h'
        assert rows.loc[0, 'hole_qn_min'] == 1 and rows.loc[0, 'hole_qn_max'] == 2

    def test_an_unpaired_row_keeps_its_carrier(self):
        rows = self._rows([{'spectrum_index': 0, 'column': 'P1', 'peaks': {},
                            'candidates': [self.cand(carrier='h')], 'error': ''}])
        assert rows.loc[0, 'carrier'] == 'h'

    def test_skipped_levels_are_counted(self):
        rows = self._rows([{'spectrum_index': 0, 'column': 'P1', 'peaks': {},
                            'candidates': [self.cand(qn=((8,), (15,), (17,), (18,), (20,)))], 'error': ''}])
        assert (rows.loc[0, 'qn_min'], rows.loc[0, 'qn_max'], rows.loc[0, 'levels_skipped']) == (8, 20, 8)

    def test_consecutive_levels_skip_nothing(self):
        rows = self._rows([{'spectrum_index': 0, 'column': 'P1', 'peaks': {},
                            'candidates': [self.cand(qn=((1,), (2,), (3,)))], 'error': ''}])
        assert rows.loc[0, 'levels_skipped'] == 0

    def test_a_sweep_lists_the_spectra_that_found_nothing(self):
        rows = self._rows([
            {'spectrum_index': 0, 'column': 'P1', 'peaks': {'peaks_V': [1, 2]},
             'candidates': [self.cand()], 'error': ''},
            {'spectrum_index': 1, 'column': 'P2', 'peaks': {'peaks_V': [1, 2, 3, 4]},
             'candidates': [], 'error': 'No candidate fits within the tolerance.'},
        ])
        assert list(rows['spectrum_index']) == [0, 1]
        assert rows.loc[1, 'candidate'] == -1
        assert np.isnan(rows.loc[1, 'size_nm'])
        assert rows.loc[1, 'n_peaks'] == 4
        assert rows.loc[1, 'reason'].startswith('No candidate')
        assert rows.loc[0, 'reason'] == ''

    def test_a_single_spectrum_with_nothing_writes_no_table(self):
        assert self._rows([{'spectrum_index': 0, 'column': 'P1', 'peaks': {},
                            'candidates': [], 'error': 'x'}]) is None


class TestLineScanReason:
    def _scan(self):
        x = np.linspace(-1, 1, 50)
        return LineScan(x=x, ys=np.zeros((50, 2)), names=['a', 'b'], step_nm=1.0)

    def test_peaks_on_the_other_branch_is_its_own_reason(self):
        scan = self._scan()
        found = {'targets': [], 'n_peaks': 11}
        results = analyze_line_scan(scan, lambda c: found, lambda f: [], lambda c: 0.0, min_peaks=2)
        assert [r.reason for r in results] == [NO_BRANCH_PEAKS, NO_BRANCH_PEAKS]
        assert results[0].n_peaks == 11 and results[0].n_targets == 0

    def test_no_peaks_at_all_stays_no_peaks(self):
        scan = self._scan()
        results = analyze_line_scan(scan, lambda c: {'targets': [], 'n_peaks': 0},
                                    lambda f: [], lambda c: 0.0, min_peaks=2)
        assert results[0].reason == NO_PEAKS


class TestTextColumnsSurviveASave:
    def test_round_trip(self, tmp_path):
        pm = ProjectManager()
        frame = pd.DataFrame({'Spectrum_Index': [0.0, 1.0, 2.0], 'size_nm': [3.0, np.nan, 5.0],
                              'group': [1.0, -1.0, 1.0], 'reason': ['', 'no_carrier_pair', '']})
        ds = SpectralData(frame, SpectralMetadata(source_type='line_scan', dimensions=(3, 1),
                                                  scan_mode='line', units={'independent': 'Index'},
                                                  additional_info={}, data_type='flat'))
        blob = pm._serialize_datasets({'t': ds})
        assert 't' in blob, "the dataset must not be dropped"
        assert blob['t']['text_columns'] == {'reason': ['', 'no_carrier_pair', '']}
        back = pm._deserialize_datasets(blob)['t']
        assert list(back.data.columns) == ['Spectrum_Index', 'size_nm', 'group', 'reason']
        assert list(back.data['reason']) == ['', 'no_carrier_pair', '']
        np.testing.assert_allclose(back.data['group'], [1, -1, 1])
        assert np.isnan(back.data['size_nm'][1])


class TestRunsDoNotOverwriteEachOther:
    def test_two_symmetries_give_two_tables_and_two_files(self, tmp_path):
        class Stub(ToolImplementations):
            def __init__(self):
                self._datasets = {}
                self._workflow_mode = True
                self.dataLoaded = type("S", (), {"emit": lambda *a: None})()
                self.out = tmp_path
            def _ensure_output_dir(self, sub):
                d = self.out / sub; d.mkdir(exist_ok=True); return d
            def _sanitize_filename(self, n):
                import re; return re.sub(r'[^A-Za-z0-9_.()+, -]+', '_', n)
            def _extract_clean_base_name(self, n): return n
        stub = Stub()
        ds = SpectralData(pd.DataFrame({"V": [0.0, 1.0], "P1": [0.0, 1.0]}),
                          SpectralMetadata(source_type='t', dimensions=(1, 1), scan_mode='point',
                                           units={}, additional_info={}))
        run = [{'spectrum_index': 0, 'column': 'P1', 'peaks': {}, 'candidates': [TestCandidateRows.cand()], 'error': ''}]
        base = {'ndim': '2D', 'coords': 'cartesian', 'carrier': 'both', 'match': 'delta_e'}
        n1, p1 = stub._register_designer_tables(run, "d", ds, {**base, 'sym': 'tetragonal'})
        n2, p2 = stub._register_designer_tables(run, "d", ds, {**base, 'sym': 'orthorhombic'})
        n3, p3 = stub._register_designer_tables(run, "d", ds, {**base, 'sym': 'orthorhombic'})
        assert n1[0] != n2[0] and 'tetragonal' in n1[0] and 'orthorhombic' in n2[0]
        assert n3[0] == n2[0] + ' (2)'                       # a repeat keeps both
        assert len({p1[0], p2[0], p3[0]}) == 3
        assert all(pathlib.Path(p).exists() for p in (p1[0], p2[0], p3[0]))
        assert len(stub._datasets) == 12          # three runs, four tables each


class TestRowsSayWhereTheyCameFrom:
    def test_dataset_and_search_columns(self, tmp_path):
        class Stub(ToolImplementations):
            def __init__(self):
                self._datasets = {}
                self._workflow_mode = True
                self.dataLoaded = type("S", (), {"emit": lambda *a: None})()
                self.out = tmp_path
            def _ensure_output_dir(self, sub):
                d = self.out / sub; d.mkdir(exist_ok=True); return d
            def _sanitize_filename(self, n):
                import re; return re.sub(r'[^A-Za-z0-9_.()+, -]+', '_', n)
            def _extract_clean_base_name(self, n): return n
        stub = Stub()
        ds = SpectralData(pd.DataFrame({"V": [0.0, 1.0], "P1": [0.0, 1.0]}),
                          SpectralMetadata(source_type='t', dimensions=(1, 1), scan_mode='point',
                                           units={}, additional_info={}))
        run = [{'spectrum_index': 0, 'column': 'P1', 'peaks': {},
                'candidates': [TestCandidateRows.cand(hole=TestCandidateRows.cand(carrier='h'))], 'error': ''}]
        names, _ = stub._register_designer_tables(run, "lineA", ds,
                                                  {'ndim': '2D', 'coords': 'cartesian', 'sym': 'tetragonal',
                                                   'carrier': 'both', 'match': 'delta_e'})
        cand = stub._datasets[names[0]].data
        lev = stub._datasets[names[1]].data
        assert list(cand.columns[-2:]) == ['dataset', 'search'] and list(lev.columns[-2:]) == ['dataset', 'search']
        assert cand.loc[0, 'dataset'] == 'lineA' and lev.loc[0, 'dataset'] == 'lineA'
        assert cand.loc[0, 'search'] == '2D, cartesian, tetragonal, e+h, ΔE'
        assert stub._datasets[names[0]].metadata.additional_info['sym'] == 'tetragonal'

    def test_the_designer_is_a_batch_tool(self):
        from src.backend import batch_tools
        spec = batch_tools.get_spec('confinement_designer')
        assert spec.method == 'design_confinement' and spec.params_as_dict
        assert spec.completion == '_on_designer_completed'


class TestSizesAreGrouped:
    def test_candidates_within_the_tolerance_share_a_group(self, tmp_path):
        class Stub(ToolImplementations):
            def __init__(self):
                self._datasets = {}
                self._workflow_mode = True
                self.dataLoaded = type("S", (), {"emit": lambda *a: None})()
                self.out = tmp_path
            def _ensure_output_dir(self, sub):
                d = self.out / sub; d.mkdir(exist_ok=True); return d
            def _sanitize_filename(self, n):
                import re; return re.sub(r'[^A-Za-z0-9_.()+, -]+', '_', n)
            def _extract_clean_base_name(self, n): return n
        stub = Stub()
        ds = SpectralData(pd.DataFrame({"V": [0.0, 1.0], "P1": [0.0, 1.0]}),
                          SpectralMetadata(source_type='t', dimensions=(1, 1), scan_mode='point',
                                           units={}, additional_info={}))
        def cand(size, index=0):
            c = TestCandidateRows.cand(index=index); c['size_nm'] = size; c['dims_nm'] = (size,); return c
        runs = [
            {'spectrum_index': 0, 'column': 'P1', 'peaks': {}, 'candidates': [cand(30.2), cand(24.0, 1)], 'error': ''},
            {'spectrum_index': 1, 'column': 'P2', 'peaks': {}, 'candidates': [cand(30.9)], 'error': ''},
            {'spectrum_index': 2, 'column': 'P3', 'peaks': {'peaks_V': [1]}, 'candidates': [], 'error': 'nothing'},
            {'spectrum_index': 3, 'column': 'P4', 'peaks': {}, 'candidates': [cand(24.6)], 'error': ''},
        ]
        names, _ = stub._register_designer_tables(runs, "d", ds, {'ndim': '1D', 'group_tol_nm': 1.0})
        t = stub._datasets[names[0]].data
        by_size = {round(r.size_nm, 1): r.group for r in t.itertuples() if r.candidate >= 0}
        assert by_size[30.2] == by_size[30.9] and by_size[24.0] == by_size[24.6]
        assert by_size[24.0] != by_size[30.2]
        assert by_size[24.0] == 0                      # groups are numbered by size
        assert t.loc[t['candidate'] == -1, 'group'].tolist() == [-1]
        g30 = t[t['group'] == by_size[30.2]]
        assert g30['group_size_nm'].round(2).unique().tolist() == [30.55]
        assert stub._datasets[names[0]].metadata.additional_info['n_groups'] == 2
