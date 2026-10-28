"""
The Confinement Designer's panel-to-engine plumbing: pinned dimensions,
per-dimension search ranges, the assignment rule, and the honesty columns.

The engine has always honoured ``p['fixed']``; nothing ever sent it one, so
pinning a dimension — the only answer there is for a length the data does not
determine — was unreachable from the panel. These tests cover that path and
the two properties that make it worth having: a pinned run returns geometries
that all AGREE on the pinned length, and it returns the same ones whatever the
upper bound and whatever the seed.

Every test here also pins the other direction: the defaults must come out as
the search the tool ran before any of these knobs existed.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import math
import pathlib
import tempfile

import numpy as np
import pandas as pd
import pytest

from src.backend.tool_implementations import ToolImplementations
from src.models.spectral_data import SpectralData, SpectralMetadata
from src.physics.designer import Designer
from src.physics.quantum_dot import dot_energies


class Stub(ToolImplementations):
    """Enough of the tool to run a search and register its tables."""

    def __init__(self):
        self._datasets = {}
        self._workflow_mode = True
        self.dataLoaded = type("S", (), {"emit": lambda *a: None})()

    def _ensure_output_dir(self, sub):
        d = pathlib.Path(tempfile.mkdtemp()) / sub
        d.mkdir()
        return d

    def _sanitize_filename(self, n):
        return "x"

    def _extract_clean_base_name(self, n):
        return n


class Task:
    cancelled = False


# A lens whose levels are the six lowest of a 4 nm × 5 nm disc, drawn as
# Gaussians on both bias branches. Narrow enough in bias that the detector
# resolves them one by one, which is what makes this a test of the plumbing
# rather than of peak finding.
DIMS = (4.0, 5.0)
MEFF = 0.322


@pytest.fixture(scope="module")
def spectrum():
    levels = [E for E, _ in dot_energies("disc", DIMS, MEFF, 6)]
    V = np.linspace(-0.5, 0.5, 1201)
    y = np.full_like(V, 0.05)
    for E in levels:
        y += np.exp(-0.5 * ((V - E) / 0.010) ** 2)
        y += 0.8 * np.exp(-0.5 * ((V + E) / 0.010) ** 2)
    return SpectralData(
        pd.DataFrame({"V": V, "P1": y}),
        SpectralMetadata(source_type="t", dimensions=(1, 1),
                         scan_mode="point", units={}, additional_info={}))


def params(**over):
    return {**ToolImplementations.DESIGNER_DEFAULTS,
            "ndim": "0D", "coords": "disc", "sym": "", "meff_e": str(MEFF),
            "Lmin": 1.0, "Lmax": 13.0, "match": "delta_e", "seed": 1, **over}


class TestTheDefaultsAreTheOldSearch:
    """Every new control has to mean "as before" until it is touched."""

    def test_nothing_is_pinned_by_default(self):
        assert ToolImplementations._designer_fixed(params()) == {
            'd1': None, 'd2': None, 'd3': None}

    def test_no_dimension_has_a_range_of_its_own_by_default(self):
        # Empty, not {'d1': (Lmin, Lmax)}: Designer._box resolves an absent
        # entry to the shared range, so an empty map IS the old behaviour
        # rather than a restatement of it.
        assert ToolImplementations._designer_box(params()) == {}

    def test_the_table_name_does_not_change(self):
        assert (ToolImplementations._search_signature(
            params(carrier='electrons')) == "0D, disc, e, ΔE")

    def test_the_defaults_name_a_search_mode_and_an_assignment(self):
        # Present so the panel has something to send and the backend
        # something to compare; both are the behaviour that was there before.
        assert ToolImplementations.DESIGNER_DEFAULTS['search_mode'] == 'sample'
        assert ToolImplementations.DESIGNER_DEFAULTS['assign'] == 'energy'
        assert ToolImplementations.DESIGNER_DEFAULTS['resolution_meV'] is None


class TestPinningIsNormalised:
    """The panel sends what a panel can send; the engine indexes ``fixed``
    directly and a missing key is a KeyError in the middle of a search."""

    def test_a_partial_map_is_filled_out(self):
        assert ToolImplementations._designer_fixed({'fixed': {'d2': 5.0}}) == {
            'd1': None, 'd2': 5.0, 'd3': None}

    def test_a_blank_is_not_a_pin(self):
        assert ToolImplementations._designer_fixed(
            {'fixed': {'d1': '', 'd2': None}}) == {
                'd1': None, 'd2': None, 'd3': None}

    def test_nonsense_is_searched_rather_than_pinned(self):
        # Never raises: a bad number in one field must not take the run down
        # for every spectrum after it.
        assert ToolImplementations._designer_fixed(
            {'fixed': {'d1': 'wide', 'd2': -3.0, 'd3': float('nan')}}) == {
                'd1': None, 'd2': None, 'd3': None}

    def test_a_pin_is_named_in_the_table_name(self):
        # A run at L_z = 5 nm is not a run that searched L_z, and the two
        # must not write to the same table.
        name = ToolImplementations._search_signature(
            params(carrier='electrons', fixed={'d2': 5.0}))
        assert name.endswith("L_z=5nm")


class TestRangesAreNormalised:
    def test_zero_ends_mean_the_shared_range(self):
        assert ToolImplementations._designer_box({'box': {'d1': (0, 0)}}) == {}

    def test_one_end_can_be_left_open(self):
        assert ToolImplementations._designer_box(
            {'box': {'d2': (None, 6.0)}}) == {'d2': (None, 6.0)}

    def test_a_backwards_range_falls_back_rather_than_searching_nothing(self):
        assert ToolImplementations._designer_box({'box': {'d1': (9.0, 2.0)}}) == {}


class TestDimensionsAreNamedInHerTerms:
    """'L_z is unconstrained' is about her lens; 'd2 is unconstrained' is
    about an array index."""

    def test_a_lens_has_an_R_and_an_L_z(self):
        assert ToolImplementations._designer_dim_names('0D', 'disc', '') == {
            'd1': 'R', 'd2': 'L_z'}

    def test_a_sphere_has_only_an_R(self):
        assert ToolImplementations._designer_dim_names('0D', 'spherical', '') == {
            'd1': 'R'}

    def test_a_square_is_one_length_not_two(self):
        assert ToolImplementations._designer_dim_names(
            '2D', 'cartesian', 'square') == {'d1': 'L'}

    def test_a_tetragonal_cell_skips_d2(self):
        # The engine's own free_keys does; a panel that drew a d2 control
        # here would draw one the search cannot reach.
        assert ToolImplementations._designer_dim_names(
            '3D', 'cartesian', 'tetragonal') == {'d1': 'Lx', 'd3': 'Lz'}

    def test_the_names_are_the_keys_the_engine_searches(self):
        for ndim, coords, sym in (('0D', 'disc', ''), ('1D', 'cartesian', ''),
                                  ('2D', 'cartesian', 'square'),
                                  ('3D', 'cartesian', 'tetragonal'),
                                  ('3D', 'cylindrical', '')):
            names = ToolImplementations._designer_dim_names(ndim, coords, sym)
            free = Designer().free_keys(
                {'ndim': ndim, 'coords': coords, 'sym': sym,
                 'fixed': {'d1': None, 'd2': None, 'd3': None}})
            assert set(free) == set(names), (ndim, coords, sym)


class TestAPinnedSearchReachesTheEngine:
    def test_every_candidate_agrees_on_the_pinned_length(self, spectrum):
        run = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(fixed={'d2': 5.0}))
        assert run['candidates'], run['error']
        # Exactly, not nearly: a pinned dimension is not searched at all, so
        # the number that comes back is the number that went in.
        assert all(c['dims_nm'][1] == 5.0 for c in run['candidates'])

    def test_the_answer_does_not_move_when_the_upper_bound_does(self, spectrum):
        """The whole complaint, in one assertion.

        Free, this disc's candidates run from R = 2.7 to 8.7 nm and L_z from
        4.6 to 12.6, and which six come back is a draw. With L_z pinned the
        radii found inside a 13 nm box are still found inside an 18 nm one —
        a wider box adds candidates instead of replacing them.
        """
        narrow = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(Lmax=13.0, fixed={'d2': 5.0}))
        wide = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(Lmax=18.0, seed=2, fixed={'d2': 5.0}))

        def radii(run):
            return {round(c['dims_nm'][0], 2) for c in run['candidates']}

        assert radii(narrow), narrow['error']
        assert radii(narrow) <= radii(wide)

    def test_a_pin_takes_the_dimension_out_of_the_search(self):
        p = {'ndim': '0D', 'coords': 'disc', 'sym': '',
             'fixed': ToolImplementations._designer_fixed({'fixed': {'d2': 5.0}}),
             'Lmin': 1.0, 'Lmax': 13.0}
        assert Designer().free_keys(p) == ['d1']
        assert Designer().bounds(p) == [(1.0, 13.0)]

    def test_a_range_of_its_own_reaches_the_engine(self):
        p = {'ndim': '0D', 'coords': 'disc', 'sym': '',
             'fixed': ToolImplementations._designer_fixed({}),
             'box': ToolImplementations._designer_box(
                 {'box': {'d2': (4.0, 6.0)}}),
             'Lmin': 1.0, 'Lmax': 13.0}
        # R keeps the shared range; only L_z is narrowed.
        assert Designer().bounds(p) == [(1.0, 13.0), (4.0, 6.0)]


class TestTheHonestyColumns:
    """A column that says a dimension is unconstrained is worth more than a
    third decimal place on it."""

    @staticmethod
    def _rows(candidate, table='Candidates'):
        stub = Stub()
        ds = SpectralData(
            pd.DataFrame({"V": [0.0, 1.0], "P1": [0.0, 1.0]}),
            SpectralMetadata(source_type='t', dimensions=(1, 1),
                             scan_mode='point', units={}, additional_info={}))
        stub._register_designer_tables(
            [{'spectrum_index': 0, 'column': 'P1', 'peaks': {},
              'candidates': [candidate], 'error': ''}], "d", ds, {})
        found = next((v for k, v in stub._datasets.items()
                      if k.startswith(f"d - Designer {table}")), None)
        return None if found is None else found.data

    @staticmethod
    def candidate(**over):
        c = {'index': 0, 'carrier': 'e', 'dims_nm': (4.0, 5.0),
             'size_nm': 4.5, 'meff': 0.322, 'offset_eV': 0.0,
             'rrmse': 1.0, 'rrmse_de': 1.0, 'targets': [0.1, 0.2],
             'qn': [[1, 0, 1], [1, 1, 1]]}
        c.update(over)
        return c

    def test_a_flat_dimension_is_named_not_numbered(self):
        rows = self._rows(self.candidate(flat_dims=['L_z']))
        assert rows.loc[0, 'flat_dims'] == 'L_z'

    def test_nothing_flat_says_nothing(self):
        # The good case must not shout: an empty cell, not the word "none".
        rows = self._rows(self.candidate(flat_dims=[]))
        assert rows.loc[0, 'flat_dims'] == ''

    def test_the_tie_count_travels_with_the_window_it_was_counted_in(self):
        rows = self._rows(self.candidate(n_tied=18.0, resolution_meV=27.0,
                                         unresolvable=1.0))
        assert rows.loc[0, 'n_tied'] == 18
        assert rows.loc[0, 'resolution_meV'] == pytest.approx(27.0)
        assert rows.loc[0, 'unresolvable'] == 1

    def test_the_degeneracies_reach_the_candidate_row(self):
        rows = self._rows(self.candidate(g_sum=13.0, g_max=4.0,
                                         n_distinct=2.0, qn_sum=6.0))
        for column, value in (('g_sum', 13), ('g_max', 4),
                              ('n_distinct', 2), ('qn_sum', 6)):
            assert rows.loc[0, column] == value, column

    def test_a_candidate_without_annotations_leaves_them_blank(self):
        # annotate() is allowed to fail without taking the search with it, so
        # a missing fact has to read as missing rather than as zero.
        rows = self._rows(self.candidate())
        assert math.isnan(rows.loc[0, 'n_tied'])
        assert math.isnan(rows.loc[0, 'g_sum'])

    def test_a_level_row_says_how_many_states_it_stands_for(self):
        rows = self._rows(self.candidate(degeneracy=[1, 4]), table='Levels')
        assert list(rows['degeneracy']) == [1, 4]

    def test_a_level_row_without_a_level_table_says_nothing(self):
        rows = self._rows(self.candidate(), table='Levels')
        assert rows['degeneracy'].isna().all()


class TestTheFactsSurviveARealSearch:
    def test_a_searched_candidate_carries_its_diagnostics(self, spectrum):
        run = Stub()._design_one_spectrum(
            Task(), spectrum, 0,
            params(fixed={'d2': 5.0}, temperature_K=90.0))
        assert run['candidates'], run['error']
        first = run['candidates'][0]
        # n_tied is a count of assignments the measurement cannot rule out,
        # so it is at least the one that was made.
        assert first['n_tied'] >= 1
        assert first['resolution_meV'] > 0
        # Named dimensions, never keys — this is the column she reads.
        assert all(name in ('R', 'L_z') for name in first['flat_dims'])

    def test_without_a_stated_resolution_there_is_no_tie_count(self, spectrum):
        """The window is the measurement's, not the model's.

        Nothing in a peak list says how finely the spectrum resolves, so with
        no temperature and no explicit window these two columns come back
        empty rather than computed against a guess. ``flat_dims`` is
        unaffected — whether the fit can see a dimension at all is a property
        of the model and the match, not of the resolution.
        """
        run = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(fixed={'d2': 5.0}))
        assert run['candidates'], run['error']
        first = run['candidates'][0]
        assert math.isnan(first['n_tied'])
        assert math.isnan(first['resolution_meV'])
        assert math.isnan(first['unresolvable'])
        assert 'not set' in first['resolution_basis']
        assert all(name in ('R', 'L_z') for name in first['flat_dims'])

    def test_a_widened_resolution_ties_more_levels_together(self, spectrum):
        """The measurement's resolution is what decides whether a lower error
        means anything, so it has to be hers to set."""
        fine = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(fixed={'d2': 5.0}, resolution_meV=1.0))
        coarse = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(fixed={'d2': 5.0}, resolution_meV=91.0))
        assert fine['candidates'] and coarse['candidates']
        assert (coarse['candidates'][0]['n_tied']
                > fine['candidates'][0]['n_tied'])
        # The geometry is untouched: this is a diagnostic, never a score.
        assert (fine['candidates'][0]['dims_nm']
                == coarse['candidates'][0]['dims_nm'])
