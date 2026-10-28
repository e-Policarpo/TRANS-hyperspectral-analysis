"""What the Confinement Designer's panel promises, and what the backend does
about it.

Four claims are under test here, each of which was measurably false:

* the resolution window had a default that fired on nothing, so the
  ``unresolvable`` column was silent on exactly the geometries the runaway
  diagnosis blames;
* a per-dimension range typed the wrong way round was dropped and logged at
  INFO, and the search then ran over the WHOLE shared range — the opposite of
  the request, with nothing on screen saying so;
* a search the settings make impossible (a lattice over ``enum_max_nodes``)
  aborted the entire sweep on its first spectrum instead of reporting itself
  per spectrum;
* a match with no quantum numbers came back as a degeneracy of 1, which reads
  as "this peak is a singlet" rather than as "we never found out".

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
from src.physics.designer import Designer
from src.models.spectral_data import SpectralData, SpectralMetadata
from src.physics.quantum_dot import dot_energies


class Stub(ToolImplementations):
    """Enough of the tool to run a search and register its tables."""

    def __init__(self):
        self._datasets = {}
        self._workflow_mode = True
        self.dataLoaded = type("S", (), {"emit": lambda *a: None})()
        self.errors = []
        self.errorOccurred = type(
            "S", (), {"emit": lambda _s, *a: self.errors.append(a)})()

    def _ensure_output_dir(self, sub):
        d = pathlib.Path(tempfile.mkdtemp()) / sub
        d.mkdir()
        return d

    def _sanitize_filename(self, n):
        return "x"

    def _extract_clean_base_name(self, n):
        return n

    def _report_tool_progress(self, *a, **k):
        return None


class Task:
    cancelled = False
    progress = 0.0


DIMS = (4.0, 5.0)
MEFF = 0.322
#: The four geometries the runaway walks through: L_z runs to the ceiling and
#: R collapses with it. Their level spacings are 26.3, 21.5, 16.9 and 25.8 meV
#: — every one of them below the 3.5 k_B T window this measurement really has.
RUNAWAY = [(3.75, 5.0), (3.2, 10.0), (2.9, 14.5), (2.1, 18.0)]


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


def annotated(dims, resolution_meV):
    """One geometry scored and annotated at one resolution window."""
    Et = np.array([E for E, _ in dot_energies("disc", DIMS, MEFF, 6)])
    p = {'Et': Et, 'meff': MEFF, 'ndim': '0D', 'coords': 'disc', 'sym': '',
         'fixed': {'d1': None, 'd2': None, 'd3': None},
         'Lmin': 1.0, 'Lmax': 18.0, 'tol': 5.0, 'maxsol': 6,
         'priority': 'uniform', 'match': 'delta_e', 'carrier': 'e',
         'resolution_meV': resolution_meV}
    d = Designer()
    n = max(len(Et) * 3, 20)
    Ec = d.compute_energies(dims, MEFF, n, p)
    matches, offset, err = d.match_and_score(Ec, Et, p)
    sol = {'dims': list(dims), 'matches': matches, 'meff': MEFF,
           'offset': offset, 'RRMSE': err, 'Ec': Ec, 'ndim': '0D',
           'coords': 'disc', 'sym': '', 'match': 'delta_e'}
    d.annotate(sol, p)
    return sol


class TestTheWindowHasABasisAndSaysWhatItIs:
    """The window is stated or it is absent — it is never inferred.

    Half the smallest measured gap, the old fallback, is a LOWER BOUND on the
    resolution rather than the resolution: 6.07 meV against a real 27 meV at
    90 K, and at that window every runaway geometry reports itself resolved.
    A guess that reads as a clean bill of health is worse than an empty cell,
    so with nothing stated the diagnostic columns stay empty.
    """

    def test_nothing_is_assumed_about_the_measurement(self):
        """No shipped temperature: she has data at 90 K and at 300 K.

        3.5 k_B T is 27 meV at one and 91 at the other, so any default is
        wrong for most runs — and wrong without saying so, which is the part
        that matters.
        """
        window, basis = ToolImplementations._designer_resolution(
            ToolImplementations.DESIGNER_DEFAULTS)
        assert window is None
        assert "not set" in basis

    def test_a_temperature_gives_the_quoted_windows(self):
        for kelvin, meV in ((90.0, 27.3), (300.0, 91.1)):
            window, basis = ToolImplementations._designer_resolution(
                params(temperature_K=kelvin))
            assert window == pytest.approx(meV, abs=0.15), kelvin
            assert f"at {kelvin:g} K" in basis

    def test_a_measured_resolution_beats_a_derived_one(self):
        window, basis = ToolImplementations._designer_resolution(
            params(resolution_meV=27.0, temperature_K=300.0))
        assert window == 27.0 and "as given" in basis

    def test_no_temperature_hands_back_nothing_and_says_so(self):
        window, basis = ToolImplementations._designer_resolution(
            params(temperature_K=0))
        assert window is None
        # The words matter as much as the None: an empty cell has to read as
        # "not measured", never as "measured and fine".
        assert "not set" in basis

    def test_nonsense_is_refused_rather_than_used(self):
        """A resolution that is not a number falls through to the temperature,
        and with no temperature either there is simply no window."""
        window, basis = ToolImplementations._designer_resolution(
            params(resolution_meV="wide"))
        assert window is None and "not set" in basis
        window, basis = ToolImplementations._designer_resolution(
            params(resolution_meV="wide", temperature_K=90.0))
        assert window == pytest.approx(27.3, abs=0.15)
        assert basis == "3.5 k_B T at 90 K"

    @pytest.mark.parametrize("dims", RUNAWAY)
    def test_the_runaway_is_unjudged_until_a_window_is_given(self, dims):
        """The defect, in one assertion per geometry.

        At the old derived window all four of these reported
        ``unresolvable = False`` — levels 17 to 26 meV apart, window 6.07 meV.
        Now an unstated window returns no verdict at all, and at the window
        this measurement really has, all four are True.
        """
        unset = annotated(dims, None)
        thermal = annotated(dims, 27.3)
        assert unset['resolution_eV'] is None
        assert unset.get('unresolvable') is None
        assert unset.get('n_tied') is None
        assert thermal['unresolvable'] is True
        # The mean spacing is a property of the model alone, so it is recorded
        # either way — it is what the window gets compared against.
        assert unset['mean_spacing_eV'] == thermal['mean_spacing_eV']
        # Diagnostic only: the geometry and its error are untouched.
        assert unset['RRMSE'] == thermal['RRMSE']

    def test_the_basis_rides_on_every_candidate(self, spectrum):
        run = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(fixed={'d2': 5.0}, temperature_K=90.0))
        assert run['candidates'], run['error']
        for candidate in run['candidates']:
            assert candidate['resolution_basis'] == "3.5 k_B T at 90 K"
            assert candidate['resolution_meV'] == pytest.approx(27.3, abs=0.15)

    def test_the_basis_reaches_the_candidate_table(self, spectrum):
        stub = Stub()
        stub._datasets['d'] = spectrum
        stub.design_confinement(
            Task(), 'd', params(fixed={'d2': 5.0}, temperature_K=90.0))
        table = next(v for k, v in stub._datasets.items()
                     if 'Designer Candidates' in k)
        assert 'resolution_basis' in table.data.columns
        assert set(table.data['resolution_basis']) == {"3.5 k_B T at 90 K"}
        # And beside the number it explains, not somewhere else.
        columns = list(ToolImplementations.DESIGNER_CANDIDATE_COLUMNS)
        assert (columns.index('resolution_basis')
                == columns.index('resolution_meV') + 1)


class TestABackwardsRangeIsRefused:
    """"From 10, to 3" for R is a request to search a narrow band. Dropping it
    searches the whole of [Lmin, Lmax] — the opposite of the request, in the
    control whose only purpose is to stop a dimension wandering."""

    def test_the_backwards_range_is_named(self):
        assert ToolImplementations._designer_inverted_ranges(
            {'box': {'d1': (10.0, 3.0)}}) == [('d1', 10.0, 3.0)]

    def test_an_ordinary_range_is_not_a_problem(self):
        assert ToolImplementations._designer_inverted_ranges(
            {'box': {'d1': (3.0, 10.0), 'd2': (None, 6.0)}}) == []

    def test_the_run_refuses_and_says_which_dimension(self, spectrum):
        stub = Stub()
        stub._datasets['d'] = spectrum
        result = stub.design_confinement(
            Task(), 'd', params(box={'d1': (10.0, 3.0)}))
        assert result['ok'] is False
        # Her name for it, never 'd1', and the numbers she typed.
        assert 'R from 10 to 3 nm' in result['error']
        assert 'wrong way round' in result['error']
        # Nothing written: a refused run must not leave a table behind that
        # searched the opposite of what was asked.
        assert not [k for k in stub._datasets if 'Designer' in k]


class TestTheBoxAndTheSharedRangeAgree:
    """``bounds()`` reads the per-dimension box; the analytical-seed gate and
    ``primary_alias`` still read the shared pair. Left unreconciled a boxed
    dimension costs the run the seeds it should have started from."""

    def test_an_untouched_panel_changes_nothing(self):
        p = params()
        assert ToolImplementations._designer_box_resolved(
            p, ('d1', 'd2', 'd3')) == {}
        assert ToolImplementations._designer_shared_range(p) == (1.0, 13.0)

    def test_a_box_past_the_ceiling_lifts_the_gate(self):
        p = params(box={'d2': (13.0, 25.0)})
        assert ToolImplementations._designer_shared_range(p) == (1.0, 25.0)

    def test_but_not_for_the_dimensions_nobody_boxed(self):
        """The reconciliation must not widen R because L_z was boxed wide."""
        p = params(box={'d2': (13.0, 25.0)})
        resolved = ToolImplementations._designer_box_resolved(
            p, ('d1', 'd2', 'd3'))
        assert resolved['d1'] == (1.0, 13.0)
        assert resolved['d2'] == (13.0, 25.0)
        # And that is what the engine searches, not the widened pair.
        lo, hi = ToolImplementations._designer_shared_range(p)
        engine = {'ndim': '0D', 'coords': 'disc', 'sym': '',
                  'fixed': {'d1': None, 'd2': None, 'd3': None},
                  'Lmin': lo, 'Lmax': hi, 'box': resolved}
        assert Designer().bounds(engine) == [(1.0, 13.0), (13.0, 25.0)]

    def test_the_seed_gate_can_reach_a_boxed_geometry(self, spectrum):
        run = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(box={'d2': (13.0, 25.0)}))
        assert run['candidates'], run['error']
        assert all(13.0 <= c['dims_nm'][1] <= 25.0 for c in run['candidates'])


class TestAnImpossibleSearchDoesNotAbortTheSweep:
    """A lattice over the node cap is the same refusal for every spectrum. It
    used to propagate out of the first one and take the whole run with it."""

    def test_the_cap_reaches_the_engine(self, spectrum):
        run = Stub()._design_one_spectrum(
            Task(), spectrum, 0,
            params(search_mode='enumerate', enum_max_nodes=4))
        assert not run['candidates']
        assert 'exceed 4 nodes' in run['error']

    def test_the_sweep_survives_it(self, spectrum):
        """Three spectra, every one of them impossible: three reasons, not one
        traceback."""
        frame = pd.DataFrame({"V": spectrum.spectra.index
                              if False else spectrum.independent_var})
        for name in ("P1", "P2", "P3"):
            frame[name] = spectrum.spectra["P1"].values
        data = SpectralData(
            frame, SpectralMetadata(source_type="t", dimensions=(1, 3),
                                    scan_mode="line", units={},
                                    additional_info={}))
        stub = Stub()
        stub._datasets['d'] = data
        result = stub.design_confinement(
            Task(), 'd', params(all_spectra=True, search_mode='enumerate',
                                enum_max_nodes=4))
        # Every spectrum was asked, and every one of them reported.
        assert result['spectra_searched'] == 3
        assert 'exceed 4 nodes' in result['error']
        # And it is not an exception that reached the caller as a string.
        assert stub.errors == []

    def test_a_workable_cap_still_enumerates(self, spectrum):
        run = Stub()._design_one_spectrum(
            Task(), spectrum, 0,
            params(search_mode='enumerate', enum_per_octave=3,
                   enum_polish=4, enum_max_nodes=200000))
        assert run['candidates'], run['error']


class TestAMissingDegeneracyIsNotASinglet:
    """"A wrong degeneracy is worse than none": 1 on a level whose quantum
    numbers never reached the annotation reads as a measurement."""

    @staticmethod
    def solution(matches):
        return {'dims': (4.0, 5.0), 'matches': matches, 'meff': 0.322,
                'ndim': '0D', 'coords': 'disc', 'sym': '', 'RRMSE': 1.0}

    def test_a_gap_in_the_annotation_stays_a_gap(self):
        out = ToolImplementations._designer_candidate(self.solution([
            {'target_E': 0.1, 'computed_E': 0.1, 'qn': (1, 0, 1),
             'degeneracy': 2},
            {'target_E': 0.2, 'computed_E': 0.2, 'qn': (1, 1, 1)},
        ]), 0)
        assert out['degeneracy'][0] == 2
        assert math.isnan(out['degeneracy'][1])

    def test_no_annotation_at_all_is_still_an_empty_list(self):
        out = ToolImplementations._designer_candidate(self.solution([
            {'target_E': 0.1, 'computed_E': 0.1, 'qn': (1, 0, 1)}]), 0)
        assert out['degeneracy'] == []

    def test_the_gap_reaches_the_level_table_as_NaN(self):
        stub = Stub()
        ds = SpectralData(
            pd.DataFrame({"V": [0.0, 1.0], "P1": [0.0, 1.0]}),
            SpectralMetadata(source_type='t', dimensions=(1, 1),
                             scan_mode='point', units={}, additional_info={}))
        stub._register_designer_tables(
            [{'spectrum_index': 0, 'column': 'P1', 'peaks': {}, 'error': '',
              'candidates': [{'index': 0, 'carrier': 'e', 'dims_nm': (4.0, 5.0),
                              'size_nm': 4.5, 'meff': 0.322, 'offset_eV': 0.0,
                              'rrmse': 1.0, 'rrmse_de': 1.0,
                              'targets': [0.1, 0.2], 'qn': [[1, 0, 1], [1, 1, 1]],
                              'degeneracy': [2.0, float('nan')]}]}],
            "d", ds, {})
        rows = next(v for k, v in stub._datasets.items()
                    if 'Designer Levels' in k).data
        assert rows.loc[0, 'degeneracy'] == 2
        assert math.isnan(rows.loc[1, 'degeneracy'])


class TestTheEngineKnobsAreReachable:
    """``enum_max_nodes`` and ``dup_rel`` were read by the engine and set by
    nobody. None on both is the engine's own default, so a default run is
    unchanged."""

    def test_the_defaults_are_the_old_search(self):
        assert ToolImplementations.DESIGNER_DEFAULTS['enum_max_nodes'] is None
        assert ToolImplementations.DESIGNER_DEFAULTS['dup_rel'] is None

    def test_a_relative_duplicate_tolerance_collapses_a_plateau(self, spectrum):
        """Thirteen nodes along an axis the fit cannot see are thirteen rows
        describing one well."""
        tight = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(search_mode='enumerate',
                                        enum_per_octave=4, enum_polish=20))
        loose = Stub()._design_one_spectrum(
            Task(), spectrum, 0, params(search_mode='enumerate',
                                        enum_per_octave=4, enum_polish=20,
                                        dup_rel=0.5))
        assert tight['candidates'] and loose['candidates']
        assert len(loose['candidates']) <= len(tight['candidates'])
