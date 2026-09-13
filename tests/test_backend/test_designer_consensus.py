"""
Tests for the revamped designer grouping: the consensus over a line.

The sibling file (test_confinement_designer.py) asks one question — does a
spectrum built from a known well come back as that well. This one asks the
question the grouping was written for: given a line of spectra, **how many
distinct wells are there and which spectrum sits on each**, and can the
method say "none" when the answer is none.

So the generator here plants GROUPS rather than one well, and it is
parametrised by the physics that actually decides whether the grouping can
work:

``temperature_K``
    sets the peak width, because the dI/dV thermal resolution is ~3.5 kT —
    27 meV at 90 K, 91 meV at 300 K. Two rungs closer together than that are
    not two measurable levels, whatever the model says.
``bias_window``
    sets which rungs were measured at all. Together with the width this is
    what generates the 300 K case where the ladder starts at the *second*
    rung — the lowest level is unresolvable against the one above it and is
    swallowed by the band edge — which is a known generator of wrong quantum
    number assignments and therefore of wrong sizes.
``noise``
    the baseline amplitude the peak finder has to work through.
``ambiguous``
    plants a spectrum that is genuinely consistent with two of the wells, to
    the same fit error. The grouping is not allowed to pick one.

Everything is synthetic. No measured spectrum is read from disk and no
tests/data corpus is created here — that is being assembled separately.
"""

import math
import re
from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np
import pandas as pd
import pytest
from unittest.mock import Mock

from src.backend.tool_implementations import ToolImplementations
from src.models.spectral_data import SpectralData, SpectralMetadata
from src.physics.analytical import box_energies_1d_eV


class MockTask:
    cancelled = False
    progress = 0


#: Boltzmann's constant in eV/K — the whole temperature dependence of this
#: file goes through it.
KB_EV = 8.617333262e-5

#: Where the conduction edge sits in the synthetic spectra, in volts. The
#: levels are measured from E_F and the model counts from the bottom of the
#: well, so every planted energy carries this offset — which delta-E
#: matching is there to cancel.
BAND_EDGE = 0.30

MEFF_E = 0.067


def thermal_fwhm_eV(temperature_K: float) -> float:
    """The width a dI/dV peak cannot be narrower than, at this temperature.

    The tip's Fermi distribution smears every feature by ~3.5 kT, which is
    27 meV at 90 K and 91 meV at 300 K. It is the resolution limit of the
    measurement: two levels closer than this are one bump on the curve, and
    a generator that plants them as two peaks is generating data no cryostat
    would produce.
    """
    return 3.5 * KB_EV * float(temperature_K)


@dataclass(frozen=True)
class Plan:
    """The physics one synthetic line is generated from.

    ``wells_nm`` are the K planted wells and ``assignment`` says which of
    them each of the N spectra was drawn from: that pair IS the answer the
    grouping has to return, so every test here states its expectation as the
    plan rather than as a number copied into an assertion.

    ``ambiguous`` appends further spectra after the assigned ones, one per
    ``(a, b)`` pair of well indices, each planted to be consistent with both
    of those wells to the same error (see :func:`_ambiguous_levels`).
    """

    wells_nm: Tuple[float, ...]
    assignment: Tuple[int, ...]
    temperature_K: float = 90.0
    bias_window: Tuple[float, float] = (-0.2, 1.6)
    noise: float = 0.01
    ambiguous: Tuple[Tuple[int, int], ...] = ()
    edge: float = BAND_EDGE
    #: Which rung each ambiguous spectrum's two readings start from. The
    #: default pairs "this well read from n = 1" against "that well read
    #: from n = 2", which is the misassignment the 300 K regime produces.
    ambiguous_rungs: Tuple[int, int] = (1, 2)

    @property
    def n_spectra(self) -> int:
        return len(self.assignment) + len(self.ambiguous)

    @property
    def fwhm_eV(self) -> float:
        return thermal_fwhm_eV(self.temperature_K)


def _levels(L_nm: float, n: int = 8) -> list:
    """The first ``n`` rungs of a 1D box, in eV from the bottom of the well."""
    return [E for E, _ in box_energies_1d_eV(L_nm, MEFF_E, n)]


def _visible_levels(L_nm: float, plan: Plan, n_max: int = 8) -> list:
    """The rungs this well shows on the curve, as biases.

    Two things remove a rung. It can fall outside the swept bias window,
    which is bookkeeping. Or it can sit closer than the thermal width to the
    rung above it, which is physics: the pair is one broadened feature, and
    the one that is lost is the LOWER of the two — it is the one riding on
    the rising band edge, where a peak that wide is absorbed by the
    background rather than standing out of it.

    That second rule is what makes the 300 K case interesting. Level spacing
    in a box grows with n, so it is always the bottom of the ladder that
    goes first: the observed ladder starts at n = 2, the search is handed
    three or four rungs whose spacings are those of 2, 3, 4… and whether it
    notices is the whole question.
    """
    width = plan.fwhm_eV
    lo, hi = plan.bias_window
    biases = [plan.edge + E for E in _levels(L_nm, n_max)]
    resolved = [V for k, V in enumerate(biases)
                if k + 1 >= len(biases) or biases[k + 1] - V >= width]
    return [V for V in resolved if lo <= V <= hi]


def _partner_well(L_nm: float, rung_a: int = 1, rung_b: int = 2) -> float:
    """The well whose ``rung_b`` spacing is this well's ``rung_a`` spacing.

    In a box E_n ∝ n², so the first spacing of a ladder read from rung n is
    (2n + 1) times the well's scale. Matching those two spacings is what
    makes a ladder ambiguous rather than merely badly fitted: both readings
    reproduce its lowest spacing exactly and disagree only about how fast
    the ladder opens up after it.
    """
    return float(L_nm) * math.sqrt((2 * rung_b + 1) / (2 * rung_a + 1))


def _ambiguous_levels(plan: Plan, pair: Tuple[int, int], n: int = 3) -> list:
    """A ladder consistent with two wells at once, to the same error.

    Well *a* read from rung ``rung_a`` and well *b* read from rung ``rung_b``
    predict two ladders of level differences; this plants the geometric mean
    of them. Delta-E matching sees only differences, so a geometric mean is
    equidistant from both readings in exactly the quantity being fitted —
    neither well can be preferred, and a grouping that picks one has decided
    something the data did not.

    Three rungs, not more: every further rung separates the two readings a
    little further, and at four the ambiguity is gone.
    """
    rung_a, rung_b = plan.ambiguous_rungs
    a, b = (plan.wells_nm[i] for i in pair)
    ladder_a = _levels(a, rung_a + n)[rung_a - 1:rung_a - 1 + n]
    ladder_b = _levels(b, rung_b + n)[rung_b - 1:rung_b - 1 + n]
    start = plan.edge + ladder_a[0]
    return [start + math.sqrt((ladder_a[k] - ladder_a[0]) *
                              (ladder_b[k] - ladder_b[0])) for k in range(n)]


def _spectrum(V: np.ndarray, centres: Sequence[float], plan: Plan,
              seed: int) -> np.ndarray:
    """A dI/dV with an exponential band edge and states planted on it.

    The peak width is the thermal resolution and nothing else: sigma =
    3.5 kT / 2.355, so the 90 K and 300 K spectra differ in the one way two
    measurements of the same dot at two temperatures actually differ.
    """
    sigma = plan.fwhm_eV / 2.3548
    y = plan.noise * np.random.RandomState(seed).randn(V.size)
    y = y + 4 * np.exp((V - 1.3) * 5) * (V > plan.edge)
    for centre in centres:
        y = y + 0.5 * np.exp(-((V - centre) / sigma) ** 2)
    return y


def _dataset(plan: Plan) -> SpectralData:
    """The whole line as one dataset: N spectra, K planted wells."""
    lo, hi = plan.bias_window
    V = np.linspace(lo, hi, 1201)
    columns = {}
    for i, well in enumerate(plan.assignment):
        columns[f"P{i + 1}"] = _spectrum(
            V, _visible_levels(plan.wells_nm[well], plan), plan, seed=5 + i)
    for j, pair in enumerate(plan.ambiguous):
        index = len(plan.assignment) + j
        columns[f"P{index + 1}"] = _spectrum(
            V, _ambiguous_levels(plan, pair), plan, seed=5 + index)
    return SpectralData(pd.DataFrame({"V": V, **columns}), SpectralMetadata(
        source_type='sts', dimensions=(plan.n_spectra, 1), scan_mode='point',
        units={'independent': 'V', 'dependent': 'A/V'},
        additional_info={'spatial_layout': 'line'}))


def _backend(directory):
    """A real ToolImplementations with the project plumbing stubbed out."""

    class MockBackend(ToolImplementations):
        def __init__(self):
            self._datasets = {}
            self._output_base_dir = directory
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

    return MockBackend()


#: One search for the whole file: a 1D box, delta-E matched, seeded. 1D is
#: the cheapest geometry that has the degeneracies this is about, and with
#: ndim = 1D the consensus groups in d1 — the only length there is.
SEARCH = {'height': 3.0, 'maxsol': 3, 'seed': 20260913, 'ndim': '1D',
          'coords': 'cartesian', 'sym': 'orthorhombic', 'match': 'delta_e',
          'Lmax': 30.0, 'all_spectra': True}


def _run(directory, plan: Plan, **params):
    """Search every spectrum of ``plan`` and hand back the backend and result."""
    tool = _backend(directory)
    tool._datasets['sts'] = _dataset(plan)
    return tool, tool.design_confinement(MockTask(), 'sts', {**SEARCH, **params})


def _table(tool, suffix: str) -> pd.DataFrame:
    """The registered table whose name starts ``sts - Designer <suffix>``."""
    prefix = f"sts - Designer {suffix}"
    return next(v for k, v in tool._datasets.items()
                if k.startswith(prefix)).data


def _modes(result) -> list:
    return result['consensus']['modes']


def _per_spectrum(result) -> list:
    return result['consensus']['per_spectrum']


def _same(rows: Sequence[dict], other: Sequence[dict]) -> bool:
    """Are two table row lists the same, NaN included?

    ``nan != nan``, so two runs that agree down to the bit compare unequal
    as plain dicts wherever a column is legitimately empty — L_z is nan on
    every 1D mode. Comparing the reprs asks the question that was meant:
    did the run write the same number, or the same absence of one.
    """
    return ([sorted((k, repr(v)) for k, v in row.items()) for row in rows]
            == [sorted((k, repr(v)) for k, v in row.items()) for row in other])


def _dominant(result) -> dict:
    """The mode the most spectra landed on."""
    return max(_modes(result), key=lambda m: m['support_spectra'])


@pytest.fixture(scope='module')
def outputs(tmp_path_factory):
    return tmp_path_factory.mktemp('designer_consensus')


# ── the plans ─────────────────────────────────────────────────────────────
#
# Two wells far enough apart to be told apart (ln 15/8 = 0.63, well past any
# bandwidth the density picks), three spectra each, at 90 K where every rung
# of both is resolved.
TWO_WELLS = Plan(wells_nm=(8.0, 15.0), assignment=(0, 0, 0, 1, 1, 1))

#: The same well at 300 K, where the first spacing is below the thermal
#: width and the measured ladder therefore starts one rung up.
HOT = Plan(wells_nm=(14.0,), assignment=(0, 0, 0, 0), temperature_K=300.0)
COLD = Plan(wells_nm=(14.0,), assignment=(0, 0, 0, 0), temperature_K=90.0)

#: Eight spectra, eight different wells drawn at random across the range
#: where a 1D box shows three or more rungs in this window. Nothing is
#: shared, so there is nothing to find.
_DRAW = np.random.RandomState(3).uniform(8.0, 20.0, 8)
NOTHING = Plan(wells_nm=tuple(round(float(L), 2) for L in _DRAW),
               assignment=tuple(range(8)))

#: Three spectra of an 8 nm well, three of the well whose n = 2 → 3 spacing
#: is 8 nm's n = 1 → 2 spacing, and one spectrum planted between the two
#: readings.
AMBIGUOUS = Plan(wells_nm=(8.0, _partner_well(8.0)),
                 assignment=(0, 0, 0, 1, 1, 1), ambiguous=((0, 1),))


@pytest.fixture(scope='module')
def two_wells(outputs):
    return _run(outputs, TWO_WELLS)


@pytest.fixture(scope='module')
def two_wells_again(outputs):
    """The same plan, the same settings, a second time."""
    return _run(outputs, TWO_WELLS)


@pytest.fixture(scope='module')
def nothing(outputs):
    return _run(outputs, NOTHING)


@pytest.fixture(scope='module')
def ambiguous(outputs):
    # Lmax is pulled in to the planted range on purpose. A three-rung ladder
    # with a free offset is fitted BETTER by a high quantum number ladder in
    # a much larger well (n = 4…10 in 26 nm, here) than by either well it
    # was built from — the spacings of a high ladder are nearly linear and
    # fit almost anything. That is a real degeneracy of the search and not
    # of the grouping, and letting it in would replace the ambiguity under
    # test with a different one. `admissible_rel` is widened to 0.2 because
    # the two readings come out at 4.0% and 4.7% error: a 0.7 pp difference
    # on a three-peak ladder is not a ranking, and the band has to be wide
    # enough to say so.
    return _run(outputs, AMBIGUOUS, Lmax=12.0, tol=10.0, maxsol=4,
                group_tol_nm=1.0, admissible_rel=0.2)


class TestThePlantedWellsComeBack:
    """K wells in, K modes out, and every spectrum on the one it came from."""

    def test_the_number_of_modes_is_the_number_of_wells(self, two_wells):
        _, result = two_wells

        assert result['ok'], result['error']
        assert len(_modes(result)) == len(TWO_WELLS.wells_nm)

    def test_each_mode_sits_on_a_planted_well(self, two_wells):
        _, result = two_wells
        found = sorted(m['R_nm'] for m in _modes(result))

        assert found == pytest.approx(sorted(TWO_WELLS.wells_nm), rel=0.02)

    def test_every_spectrum_lands_on_its_own_well(self, two_wells):
        """The assignment, not just the sizes: a grouping that finds both
        wells and then puts the spectra on the wrong ones has found
        nothing."""
        _, result = two_wells
        modes = _modes(result)

        for row in _per_spectrum(result):
            planted = TWO_WELLS.wells_nm[TWO_WELLS.assignment[row['spectrum_index']]]
            assert modes[row['mode']]['R_nm'] == pytest.approx(planted, rel=0.02)
            assert row['R_consensus_nm'] == pytest.approx(planted, rel=0.02)

    def test_the_support_is_the_planted_count(self, two_wells):
        _, result = two_wells

        assert sorted(m['support_spectra'] for m in _modes(result)) == [3, 3]
        assert all(m['support_frac'] == pytest.approx(0.5) for m in _modes(result))

    def test_an_unambiguous_spectrum_is_reported_as_certain(self, two_wells):
        """Entropy is the undecidedness channel, so it has to read zero when
        there is nothing to be undecided about — otherwise the ambiguous
        case below means nothing."""
        _, result = two_wells

        assert all(row['mode_prob'] == 1.0 for row in _per_spectrum(result))
        assert all(row['mode_entropy'] == 0.0 for row in _per_spectrum(result))

    def test_the_quantum_numbers_start_at_the_first_rung(self, two_wells):
        """At 90 K every rung of both wells is resolved, so the ladders are
        read from n = 1 and no level is claimed that was not measured."""
        _, result = two_wells

        assert all(m['qn_min'] == 1 for m in _modes(result))
        assert all(m['levels_skipped_mean'] == 0 for m in _modes(result))


class TestTheLadderThatStartsOneRungUp:
    """300 K: the lowest spacing is below the resolution, so the ladder the
    search is handed is not the ladder the model counts from."""

    def test_the_regime_is_what_it_claims_to_be(self):
        """The premise of the test, checked before the test: at 300 K the
        first spacing of this well really is inside the thermal width, and
        at 90 K it really is not."""
        first_spacing = _levels(14.0, 2)[1] - _levels(14.0, 2)[0]

        assert first_spacing < thermal_fwhm_eV(300.0)
        assert first_spacing > thermal_fwhm_eV(90.0)

    def test_the_hot_spectrum_loses_its_lowest_rung(self):
        hot = _visible_levels(14.0, HOT)
        cold = _visible_levels(14.0, COLD)

        assert cold[0] == pytest.approx(BAND_EDGE + _levels(14.0, 1)[0])
        assert hot[0] == pytest.approx(cold[1])
        assert len(hot) == len(cold) - 1

    def test_it_still_finds_the_well_and_says_where_the_ladder_starts(self, outputs):
        """The honest outcome. The size is recovered because delta-E
        matching can absorb the missing rung into the quantum number
        assignment — and the assignment is then reported as starting at
        n = 2, which is the only thing that tells a reader the bottom of the
        ladder was never measured."""
        _, result = _run(outputs, HOT)

        best = _dominant(result)
        assert best['R_nm'] == pytest.approx(14.0, rel=0.05)
        assert best['qn_min'] == 2

    def test_the_same_well_at_90_K_is_read_from_the_bottom(self, outputs):
        """The control: nothing but the temperature changed, and the ladder
        comes back complete."""
        _, result = _run(outputs, COLD)

        best = _dominant(result)
        assert best['R_nm'] == pytest.approx(14.0, rel=0.05)
        assert best['qn_min'] == 1


class TestASpectrumTheDataCannotPlace:
    """Planted consistent with two wells; it has to say so."""

    def test_the_unambiguous_spectra_still_separate(self, ambiguous):
        """The two wells are found first — the split below is a statement
        about one spectrum, not about a grouping that failed."""
        _, result = ambiguous

        assert len(_modes(result)) == 2
        assert sorted(m['R_nm'] for m in _modes(result)) == pytest.approx(
            sorted(AMBIGUOUS.wells_nm), rel=0.05)

    def test_it_keeps_both_readings(self, ambiguous):
        _, result = ambiguous
        index = len(AMBIGUOUS.assignment)
        row = next(r for r in _per_spectrum(result)
                   if r['spectrum_index'] == index)

        assert row['n_admissible'] == 2

    def test_its_membership_is_split(self, ambiguous):
        """Half and half, not a coin flip recorded as a fact."""
        _, result = ambiguous
        index = len(AMBIGUOUS.assignment)
        row = next(r for r in _per_spectrum(result)
                   if r['spectrum_index'] == index)

        assert row['mode_prob'] == pytest.approx(0.5, abs=0.1)
        assert row['mode_2nd'] >= 0
        assert row['mode_2nd_prob'] == pytest.approx(0.5, abs=0.1)
        assert {row['mode'], row['mode_2nd']} == {0, 1}

    def test_its_entropy_is_high_and_everyone_else_is_at_zero(self, ambiguous):
        """ln 2 is the whole entropy two modes can carry, and that is the
        number an evenly split spectrum has to report. The column is only
        readable as "is this position undecided?" if the decided ones sit at
        zero in the same run."""
        _, result = ambiguous
        index = len(AMBIGUOUS.assignment)
        by_index = {r['spectrum_index']: r for r in _per_spectrum(result)}

        assert by_index[index]['mode_entropy'] == pytest.approx(math.log(2), rel=0.05)
        assert all(by_index[i]['mode_entropy'] == 0.0
                   for i in range(len(AMBIGUOUS.assignment)))

    def test_the_two_readings_differ_in_their_quantum_numbers(self, ambiguous):
        """What makes the two candidates two answers rather than one answer
        twice: the same three peaks read as n = 1, 2, 3 of the small well
        and as n = 2, 3, 4 of the large one."""
        tool, result = ambiguous
        table = _table(tool, 'Candidates')
        rows = table[(table['spectrum_index'] == len(AMBIGUOUS.assignment))
                     & (table['admissible'] == 1.0)]

        assert sorted(rows['qn_min']) == list(AMBIGUOUS.ambiguous_rungs)
        assert len(set(rows['group'])) == 2


class TestWhenThereIsNoSharedWell:
    """The null test. Every spectrum comes from a different random well, so
    the only honest answer is that the line has no shared structure — and a
    density will hand back modes regardless, which is why the contrast
    against the random-selection null is the thing that has to be read."""

    def test_no_mode_is_tight(self, nothing, two_wells):
        """A mode here is a bin of unrelated sizes, not a well: the
        candidates inside it span tens of percent, where a planted well's
        span is a rounding error."""
        _, null_result = nothing
        _, planted = two_wells

        assert _modes(null_result), "a density always returns something"
        spans = [m['R_hi_nm'] / m['R_lo_nm'] - 1.0 for m in _modes(null_result)]
        assert min(spans) > 0.15
        assert max(m['R_hi_nm'] / m['R_lo_nm'] - 1.0
                   for m in _modes(planted)) < 0.01

    def test_the_line_does_not_sit_on_its_own_modes(self, nothing, two_wells):
        """One number for the whole line: the RMS distance from each
        spectrum to the nearest mode. An order of magnitude between the two
        runs, in a quantity that is a relative spread and therefore
        comparable across them."""
        _, null_result = nothing
        _, planted = two_wells

        assert null_result['consensus']['meta']['spread_pct'] > 5.0
        assert (null_result['consensus']['meta']['spread_pct']
                > 10 * planted['consensus']['meta']['spread_pct'])

    def test_the_consensus_is_no_tighter_than_chance(self, nothing):
        """The assertion that matters. Drawing one admissible candidate per
        spectrum at random and re-measuring the spread is the null of "these
        sets share no well"; if the consensus is real, the observed spread
        lands in the left tail of that distribution. Here it must not."""
        null = nothing[1]['diagnostics']['null_contrast']

        assert null['n_draws'] == 200
        assert null['tighter_than_chance'] is False
        assert null['p_value'] > 0.05
        assert null['observed_spread'] >= null['spread_p05']

    def test_the_null_says_so_the_way_it_documents(self, nothing):
        """Every spectrum here found exactly one admissible geometry, so the
        draws reproduce the data and the p-value is 1 by construction. That
        is the documented "this test has nothing to say" case, and it is
        worth pinning: it is not a bug report, it is the reason the spread
        and the mode spans above are the evidence."""
        null = nothing[1]['diagnostics']['null_contrast']

        assert null['mean_set_size'] == pytest.approx(1.0)
        assert null['observed_spread'] == pytest.approx(null['spread_median'])


class TestTheSameRunTwice:
    """Without a seed the differential_evolution search is free to land
    somewhere else, which is why the seed was exposed at all."""

    def test_the_seed_is_a_documented_knob(self):
        assert 'seed' in ToolImplementations.DESIGNER_DEFAULTS
        assert ToolImplementations.DESIGNER_DEFAULTS['seed'] is None

    def test_two_seeded_runs_give_the_same_modes(self, two_wells, two_wells_again):
        _, first = two_wells
        _, second = two_wells_again

        assert _same(_modes(second), _modes(first))

    def test_and_the_same_assignment(self, two_wells, two_wells_again):
        _, first = two_wells
        _, second = two_wells_again

        assert _same(_per_spectrum(second), _per_spectrum(first))

    def test_and_the_same_null_contrast(self, two_wells, two_wells_again):
        """The draws are seeded from the same key, so a reported p-value can
        be reproduced rather than merely re-rolled."""
        _, first = two_wells
        _, second = two_wells_again

        assert (second['diagnostics']['null_contrast']['p_value']
                == first['diagnostics']['null_contrast']['p_value'])


class TestWhatTheGroupingMustNotDependOn:
    """A line is a set of spectra. Which order they were written in, and
    whether one of them was measured twice, are not physics."""

    def test_permuting_the_spectra_does_not_change_the_grouping(self, outputs,
                                                                two_wells):
        tool, first = two_wells
        permutation = [3, 0, 4, 1, 5, 2]
        frame = tool._datasets['sts'].data
        shuffled = SpectralData(
            frame[['V'] + [f"P{i + 1}" for i in permutation]].copy(),
            tool._datasets['sts'].metadata)
        other = _backend(outputs)
        other._datasets['sts'] = shuffled
        second = other.design_confinement(MockTask(), 'sts', dict(SEARCH))

        # To the last bit but one: the density is a sum over the
        # candidates, and a permuted line sums the same terms in another
        # order. Anything larger than that would be the order changing the
        # answer.
        assert ([m['R_nm'] for m in _modes(second)]
                == pytest.approx([m['R_nm'] for m in _modes(first)], rel=1e-9))
        was = {row['spectrum_index']: row['R_consensus_nm']
               for row in _per_spectrum(first)}
        now = {row['spectrum_index']: row['R_consensus_nm']
               for row in _per_spectrum(second)}
        assert [now[k] for k in range(6)] == pytest.approx(
            [was[p] for p in permutation], rel=1e-9)

    def test_duplicating_a_spectrum_does_not_invent_a_well(self, outputs,
                                                           two_wells):
        """The same measurement counted twice is one more vote for a well
        that is already there — never a well of its own."""
        tool, first = two_wells
        frame = tool._datasets['sts'].data.copy()
        frame['P7'] = frame['P1']
        other = _backend(outputs)
        other._datasets['sts'] = SpectralData(frame, tool._datasets['sts'].metadata)
        second = other.design_confinement(MockTask(), 'sts', dict(SEARCH))

        assert len(_modes(second)) == len(_modes(first))
        assert ([m['R_nm'] for m in _modes(second)]
                == pytest.approx([m['R_nm'] for m in _modes(first)], rel=0.02))
        # The duplicate votes with the well it was copied from, so that
        # mode gains exactly one spectrum and the other keeps its own.
        assert (sorted(m['support_spectra'] for m in _modes(second))
                == [3, 4])


class TestTheTablesTheGroupingWrites:
    """Three tables answering three questions — what wells are there, where
    is this spectrum, why did this candidate land there — and a column order
    fixed so that two runs concatenate as they stand."""

    def test_all_three_are_registered(self, two_wells):
        tool, result = two_wells
        written = [name.split(' (')[0] for name in result['tables']]

        for suffix in ('Candidates', 'Modes', 'Consensus'):
            assert f"sts - Designer {suffix}" in written
            assert _table(tool, suffix) is not None

    def test_the_columns_are_the_documented_tuples_in_order(self, two_wells):
        tool, _ = two_wells

        assert tuple(_table(tool, 'Candidates').columns) == \
            ToolImplementations.DESIGNER_CANDIDATE_COLUMNS
        assert tuple(_table(tool, 'Modes').columns) == \
            ToolImplementations.DESIGNER_MODE_COLUMNS
        assert tuple(_table(tool, 'Consensus').columns) == \
            ToolImplementations.DESIGNER_CONSENSUS_COLUMNS

    def test_one_row_per_well_and_one_row_per_spectrum(self, two_wells):
        tool, result = two_wells

        assert len(_table(tool, 'Modes')) == len(_modes(result))
        assert len(_table(tool, 'Consensus')) == TWO_WELLS.n_spectra
        assert list(_table(tool, 'Consensus')['column']) == [
            f"P{i + 1}" for i in range(TWO_WELLS.n_spectra)]

    def test_every_row_says_which_run_it_came_from(self, two_wells):
        """Two runs in one table are only readable if a row carries its own
        provenance — which is also what makes the concatenation below worth
        doing."""
        tool, _ = two_wells

        for suffix in ('Candidates', 'Modes', 'Consensus'):
            table = _table(tool, suffix)
            assert list(table.columns[-2:]) == ['dataset', 'search']
            assert set(table['dataset']) == {'sts'}
            assert set(table['search']) == {'1D, cartesian, e, ΔE'}

    def test_two_runs_concatenate_without_realignment(self, outputs, two_wells):
        """The point of a fixed column tuple: pd.concat of two runs adds
        rows and nothing else. A column that moved or went missing would
        show up here as a NaN that neither run wrote."""
        tool, _ = two_wells
        other, _ = _run(outputs, TWO_WELLS, sym='tetragonal')

        for suffix in ('Candidates', 'Modes', 'Consensus'):
            first, second = _table(tool, suffix), _table(other, suffix)
            stacked = pd.concat([first, second], ignore_index=True)
            assert list(stacked.columns) == list(first.columns)
            assert len(stacked) == len(first) + len(second)
            assert (int(stacked.notna().sum().sum())
                    == int(first.notna().sum().sum()) + int(second.notna().sum().sum()))
