"""
Tests for the Confinement Designer tool.

The inverse of every other tool here: instead of describing a spectrum it
asks which well would produce one. The claim under test is recovery — a
spectrum built from a known well has to come back as that well — and the
honesty around it: what happens when there is nothing to fit, and that
everything crossing to QML is a plain number.
"""

import re

import numpy as np
import pandas as pd
import pytest
from unittest.mock import Mock

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.physics.analytical import box_energies_1d_eV


class MockTask:
    cancelled = False
    progress = 0


class CancelledTask:
    cancelled = True
    progress = 0


#: Where the conduction edge sits in the synthetic spectra, in volts. The
#: levels are measured from E_F, so every target carries this offset — which
#: is exactly what the delta-E match has to find and undo.
BAND_EDGE = 0.30

#: The well the spectra were built from.
WELL_NM = 8.0
MEFF_E = 0.067
MEFF_H = 0.45


def _levels(L_nm=WELL_NM, meff=MEFF_E, n=3):
    return [E for E, _ in box_energies_1d_eV(L_nm, meff, n)][:n]


def _spectrum(V, states, seed=5, edge=BAND_EDGE):
    """A dI/dV with an exponential band edge and states planted on it."""
    y = 0.01 * np.random.RandomState(seed).randn(V.size)
    y = y + 4 * np.exp((V - 1.3) * 5) * (V > edge)
    for centre in states:
        y = y + 0.5 * np.exp(-((V - centre) / 0.015) ** 2)
    return y


def _dataset(n_spectra=1, well_nm=WELL_NM, holes=False):
    """One or more spectra of the same well, as a dataset."""
    V = np.linspace(-1.4, 1.6, 1201) if holes else np.linspace(-0.2, 1.6, 901)
    states = [BAND_EDGE + lv for lv in _levels(well_nm, MEFF_E)]
    if holes:
        states = states + [-0.60 - lv for lv in _levels(well_nm, MEFF_H)]
    columns = {f"P{i + 1}": _spectrum(V, states, seed=5 + i)
               for i in range(n_spectra)}
    return SpectralData(pd.DataFrame({"V": V, **columns}), SpectralMetadata(
        source_type='sts', dimensions=(n_spectra, 1), scan_mode='point',
        units={'independent': 'V', 'dependent': 'A/V'},
        additional_info={'spatial_layout': 'line'}))


def _one_peak_dataset():
    """A spectrum with a single state and no band edge.

    A band edge is itself a feature the search can latch onto, so a curve
    that has one has more than one target — this is the case where there is
    genuinely nothing but one level.
    """
    V = np.linspace(-0.2, 1.6, 901)
    y = 0.01 * np.random.RandomState(11).randn(V.size)
    y = y + 0.5 * np.exp(-((V - 0.6) / 0.015) ** 2)
    return SpectralData(pd.DataFrame({"V": V, "P1": y}), SpectralMetadata(
        source_type='sts', dimensions=(1, 1), scan_mode='point',
        units={'independent': 'V'}, additional_info={}))


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

        def _ensure_output_dir(self, subdir):
            path = self._output_base_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            return path

        def _sanitize_filename(self, name):
            return re.sub(r'\W+', '_', name) or "unnamed"

        def _extract_clean_base_name(self, name):
            return name

    return MockBackend()


def _run(tool_impl, dataset=None, name='sts', **params):
    tool_impl._datasets[name] = dataset if dataset is not None else _dataset()
    return tool_impl.design_confinement(
        MockTask(), name,
        {'height': 3.0, 'maxsol': 3, 'seed': 20260822, 'ndim': '1D',
         'coords': 'cartesian', 'match': 'delta_e', 'Lmax': 20.0, **params})


class TestRecoveringTheWell:
    """A spectrum built from a known well comes back as that well."""

    def test_it_finds_the_geometry_the_spectrum_was_built_from(self, tool_impl):
        result = _run(tool_impl)

        assert result['ok'], result['error']
        best = result['candidates'][0]
        assert best['dims_nm'][0] == pytest.approx(WELL_NM, rel=0.02)

    def test_the_offset_it_finds_is_the_band_edge(self, tool_impl):
        """The nuisance parameter IS the measurement: the energies are read
        from E_F and the model counts from the bottom of the well, so the
        difference is where the band edge sits."""
        result = _run(tool_impl)

        assert result['edges']['E_c'] == pytest.approx(BAND_EDGE, abs=0.01)
        assert result['candidates'][0]['offset_eV'] == pytest.approx(
            -BAND_EDGE, abs=0.01)

    def test_absolute_matching_cannot_find_it(self, tool_impl):
        """The same spectrum with the origin left alone: the well is wrong,
        which is the reason delta-E is the default."""
        result = _run(tool_impl, match='absolute')

        assert all(abs(c['dims_nm'][0] - WELL_NM) > 0.5
                   for c in result['candidates'])

    def test_the_primary_alias_is_what_is_reported(self, tool_impl):
        """A well k times larger matches the same targets with the quantum
        numbers multiplied by k; the list must not be those."""
        result = _run(tool_impl, maxsol=4)
        sizes = [c['dims_nm'][0] for c in result['candidates']]

        assert min(sizes) == pytest.approx(WELL_NM, rel=0.02)

    def test_a_candidate_is_not_reported_twice(self, tool_impl):
        """Alias reduction collapses different search results onto one well,
        and the list showed it once per collapse before it was deduplicated."""
        result = _run(tool_impl, maxsol=6)
        sizes = [round(c['dims_nm'][0], 3) for c in result['candidates']]

        assert len(sizes) == len(set(sizes))

    def test_the_quantum_numbers_come_back_with_the_levels(self, tool_impl):
        """n = 1, 2, 3 is what makes it the primary solution rather than an
        alias, so the numbers travel with the answer."""
        best = _run(tool_impl)['candidates'][0]

        assert [qn[0] for qn in best['qn']] == [1, 2, 3]

    def test_it_reports_which_spectrum_it_searched(self, tool_impl):
        result = _run(tool_impl, _dataset(n_spectra=3), spectrum_index=2)

        assert result['spectrum_index'] == 2
        assert result['peaks']['column'] == 'P3'

    def test_a_spectrum_index_past_the_end_is_clamped(self, tool_impl):
        result = _run(tool_impl, _dataset(n_spectra=2), spectrum_index=99)

        assert result['spectrum_index'] == 1


class TestTheTwoCarriers:
    """One well confines both, and the geometry is what ties them together."""

    def test_holes_are_searched_with_the_hole_mass(self, tool_impl):
        result = _run(tool_impl, _dataset(holes=True), carrier='holes',
                      meff_h='0.45', split_h=-0.55, split_e=0.25)

        assert result['ok'], result['error']
        assert all(c['carrier'] == 'h' for c in result['candidates'])
        assert result['candidates'][0]['meff'] == pytest.approx(MEFF_H)

    def test_both_carriers_are_paired_by_geometry(self, tool_impl):
        result = _run(tool_impl, _dataset(holes=True), carrier='both',
                      meff_e='0.067', meff_h='0.45', split_e=0.25,
                      split_h=-0.55, pair_tol_nm=2.0)

        assert result['pairs'] >= 1
        best = result['candidates'][0]
        assert 'hole' in best
        assert best['hole']['dims_nm'][0] == pytest.approx(
            best['dims_nm'][0], abs=2.0)
        assert best['pair_score'] >= 0

    def test_a_mass_list_is_a_list_of_searches(self, tool_impl):
        result = _run(tool_impl, meff_e='0.060, 0.067', maxsol=6)
        masses = {round(c['meff'], 4) for c in result['candidates']}

        assert masses == {0.060, 0.067}


class TestWhenThereIsNothingToFit:
    """Absence is an answer; inventing a geometry for it is not."""

    def test_a_branch_with_one_peak_is_refused_by_name(self, tool_impl):
        """One level is explained by any size at all — the fit would be a
        tautology, so it does not run."""
        result = _run(tool_impl, _one_peak_dataset())

        assert result['ok'] is False
        assert 'electron' in result['error'] and 'single level' in result['error']
        assert result['candidates'] == []

    def test_the_peaks_it_did_find_are_still_reported(self, tool_impl):
        """Even when the search cannot run, what was found has to be visible
        — otherwise the user cannot tell a bad threshold from a bare point."""
        result = _run(tool_impl, _one_peak_dataset())

        assert result['peaks']['total'] >= 1

    def test_an_impossible_tolerance_returns_no_candidates(self, tool_impl):
        result = _run(tool_impl, tol=1e-9)

        assert result['candidates'] == []
        assert 'tolerance' in result['error']

    def test_a_missing_dataset_is_reported(self, tool_impl):
        result = tool_impl.design_confinement(MockTask(), 'nope')

        assert result['ok'] is False
        assert result['error'] == "Dataset not found"

    def test_a_bad_mass_list_names_the_field(self, tool_impl):
        """The user's to fix, so the message says which box."""
        result = _run(tool_impl, meff_e='0.067, abc')

        assert 'm*_e' in result['error']
        assert result['candidates'] == []

    def test_cancelling_returns_nothing(self, tool_impl):
        tool_impl._datasets['sts'] = _dataset()
        result = tool_impl.design_confinement(
            CancelledTask(), 'sts', {'height': 3.0, 'maxsol': 2})

        assert result['ok'] is False
        assert result['candidates'] == []

    def test_progress_reaches_the_end(self, tool_impl):
        task = MockTask()
        tool_impl._datasets['sts'] = _dataset()
        tool_impl.design_confinement(
            task, 'sts', {'height': 3.0, 'maxsol': 2, 'seed': 1,
                          'match': 'delta_e'})

        assert task.progress == 1.0


class TestWhatCrossesToQml:
    """Everything in the result map has to survive the bridge."""

    def _plain(self, value):
        return isinstance(value, (bool, int, float, str, type(None)))

    def test_every_number_is_a_plain_python_number(self, tool_impl):
        """A numpy scalar on a QVariantMap arrives as an opaque object, and
        the panel's toFixed() then fails silently."""
        result = _run(tool_impl)

        for candidate in result['candidates']:
            for key, value in candidate.items():
                if isinstance(value, list):
                    for item in value:
                        assert self._plain(item) or isinstance(item, list), key
                elif isinstance(value, dict):
                    continue                     # the paired hole, checked below
                else:
                    assert self._plain(value), f"{key} is {type(value)}"

    def test_it_is_json_serialisable_end_to_end(self, tool_impl):
        import json

        result = _run(tool_impl)
        json.dumps(result)                       # raises if anything is numpy

    def test_the_candidate_carries_what_the_plot_needs(self, tool_impl):
        best = _run(tool_impl)['candidates'][0]

        assert len(best['targets']) == len(best['computed'])
        assert len(best['errors_pct']) == len(best['targets'])
        assert best['size_nm'] > 0

    def test_the_relative_error_matches_the_two_energies(self, tool_impl):
        best = _run(tool_impl)['candidates'][0]

        for target, computed, error in zip(best['targets'], best['computed'],
                                           best['errors_pct']):
            assert error == pytest.approx((computed - target) / target * 100)

    def test_the_defaults_are_applied_under_the_caller(self, tool_impl):
        """The panel sends what it has; the rest comes from DESIGNER_DEFAULTS."""
        from src.backend.tool_implementations import ToolImplementations

        tool_impl._datasets['sts'] = _dataset()
        result = tool_impl.design_confinement(MockTask(), 'sts',
                                              {'height': 3.0, 'maxsol': 1,
                                               'seed': 1})
        assert result['dataset'] == 'sts'
        assert ToolImplementations.DESIGNER_DEFAULTS['match'] == 'delta_e'
        assert ToolImplementations.DESIGNER_DEFAULTS['carrier'] == 'electrons'
