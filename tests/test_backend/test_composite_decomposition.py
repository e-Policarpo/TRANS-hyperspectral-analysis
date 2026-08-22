"""
Phase-1 acceptance: today's composite tools, rebuilt out of workflow nodes.

The governing principle behind the node inventory is that every composite
tool should be expressible as a workflow of simple nodes — where it is not,
that is a missing node, and the missing node is usually the reusable piece
hiding inside the composite. These tests are that claim executed: a real
``Workflow``, run through ``WorkflowExecutor``, against the composite it
decomposes.

Two chains reproduce their composite exactly. The third deliberately does
not claim to: the Peak Finder node is scipy's prominence search, not the
confinement engine, so a chain that goes through it finds its own peaks.
There the equality is claimed from the composite's own peaks — which is the
part that matters, since it is the tables the nodes rebuild — and what the
full chain is tested for is that it runs: every port carries what the next
node needs, and nothing is starved on the way through.
"""

import re

import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import Mock

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.backend.workflow_engine import (
    Workflow, Connection, create_node_from_tool,
)
from src.backend.workflow_manager import WorkflowExecutor


class MockTask:
    cancelled = False
    progress = 0


#: Spacing between the line scan's positions, in metres.
STEP_M = 5e-9

#: Wide enough that the Map Generator does not widen them to the sweep's
#: resolution, so the composite and the chain integrate the same samples.
INTERVALS = [[-0.30, -0.20], [0.15, 0.25]]

#: Where the synthetic states sit, in volts.
CENTERS = (-0.25, -0.10, 0.08, 0.22)

#: Detection knobs shared by the composite and the chain.
DETECT = {'baseline': 'poly-iter', 'baseline_degree': 5, 'height': 5.0}


def _line_scan(n_spectra=6, n_points=512):
    """A line scan with states on a steep band edge, at known positions.

    Spectrum n carries the first ``n % 4 + 1`` states, so the columns differ
    and a table that ignored the spectrum index would show it.
    """
    x = np.linspace(-0.6, 0.6, n_points)
    band_edges = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)
    columns = {}
    for n in range(n_spectra):
        y = band_edges.copy()
        for centre in CENTERS[:n % 4 + 1]:
            y = y + 1.2e-8 * np.exp(-0.5 * ((x - centre) / 0.006) ** 2)
        columns[f"P{n + 1}"] = y
    return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
        source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
        units={'independent': 'V', 'dependent': 'A/V'},
        additional_info={'spatial_layout': 'line',
                         'spectrum_meta': [{'location_m': [n * STEP_M, 0.0]}
                                           for n in range(n_spectra)]}))


def _marks(dataset):
    """The mark columns of a registered matrix, without the axis column."""
    return dataset.data.iloc[:, 1:].to_numpy()


def _csv_of(tiff_path):
    path = Path(tiff_path)
    return np.loadtxt(path.parent.parent / 'csv' / (path.stem + '.csv'),
                      delimiter=',', ndmin=2)


def _gsf(tiff_path):
    from src.utils.gsf_io import read_gsf
    path = Path(tiff_path)
    return read_gsf(path.parent.parent / 'gsf' / (path.stem + '.gsf'))[1]


@pytest.fixture
def backend(tmp_path):
    """A real ToolImplementations with the project plumbing stubbed out."""
    from src.backend.app_backend import AppBackend
    from src.backend.tool_implementations import ToolImplementations

    class MockBackend(ToolImplementations):
        # The Integration node reaches for AppBackend's half of the backend;
        # the real app has both on one object.
        _do_integrate = AppBackend._do_integrate

        def __init__(self):
            self._datasets = {'line': _line_scan()}
            self._output_base_dir = tmp_path / "outputs"
            self._output_base_dir.mkdir(exist_ok=True)
            self.errorOccurred = Mock()
            self.dataLoaded = Mock()
            self._workflow_mode = False
            self._suppress_auto_open = False
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


@pytest.fixture
def executor(backend):
    return WorkflowExecutor(backend)


class Chain:
    """A workflow under construction, wired by node handle rather than by id."""

    def __init__(self, name="Decomposition"):
        self.workflow = Workflow(id=f"wf_{name}", name=name)
        self._connections = 0

    def node(self, tool, **params):
        node = create_node_from_tool(tool, 0, 0)
        node.parameters.update(params)
        self.workflow.add_node(node)
        return node

    def wire(self, source, source_port, target, target_port):
        self._connections += 1
        added = self.workflow.add_connection(Connection(
            id=f"c{self._connections}",
            source_node_id=source.id, source_port_id=source_port,
            target_node_id=target.id, target_port_id=target_port))
        assert added, f"{source.tool_name}.{source_port} -> {target.tool_name}.{target_port}"
        return self

    def run(self, executor):
        result = executor.execute(self.workflow)
        assert result['success'], result['errors']
        return result

    def outputs_of(self, executor, node):
        return executor.node_outputs.get(node.id, {})


class TestTheMapGeneratorDecomposes:
    """DatasetInput -> Integration -> Map Assembly, against the composite.

    Exact, because nothing in the chain guesses: the intervals are given, the
    integration is the same trapezoid over the same mask, and Map Assembly
    only lays the numbers out.
    """

    @pytest.fixture
    def composite(self, backend):
        return backend.generate_maps_from_spectra(
            MockTask(), 'line',
            {'baseline': 'none', 'interval_source': 'manual', 'scan_type': 'line',
             'intervals': INTERVALS, 'noise_floor': 0.0})

    @pytest.fixture
    def chain(self, executor, backend):
        chain = Chain("map_generator")
        source = chain.node("DatasetInput", dataset_name='line')
        integrate = chain.node("Integration", intervals=[
            {'lower': lo, 'upper': hi} for lo, hi in INTERVALS])
        assembly = chain.node("MapAssembly", scan_type='line')
        output = chain.node("DatasetOutput", output_name='Interval Map')

        chain.wire(source, 'dataset', integrate, 'dataset')
        chain.wire(integrate, 'flat_data', assembly, 'flat_data')
        chain.wire(integrate, 'intervals_out', assembly, 'intervals')
        chain.wire(source, 'dataset', assembly, 'source')
        chain.wire(assembly, 'interval_map', output, 'dataset')

        chain.run(executor)
        return chain.outputs_of(executor, assembly)

    def test_the_joined_map_holds_the_same_numbers(self, chain, composite, backend):
        theirs = backend._datasets[composite['interval_map']]

        np.testing.assert_allclose(chain['interval_map'].spectra.to_numpy(),
                                   theirs.spectra.to_numpy())

    def test_the_joined_map_is_on_the_same_energy_axis(self, chain, composite, backend):
        theirs = backend._datasets[composite['interval_map']]

        np.testing.assert_allclose(chain['interval_map'].independent_var,
                                   theirs.independent_var)

    def test_the_per_interval_maps_hold_the_same_numbers(self, chain, composite):
        assert len(chain['maps']) == len(composite['map_paths'])
        for mine, theirs in zip(chain['maps'], composite['map_paths']):
            np.testing.assert_allclose(_csv_of(mine), _csv_of(theirs))

    def test_the_maps_go_out_in_metres(self, chain, composite):
        """The export rule survives the decomposition: the chain never saw
        the spectra's positions except through the ports."""
        mine = _gsf(chain['maps'][0])
        theirs = _gsf(composite['map_paths'][0])

        assert mine['XYUnits'] == 'm'
        assert mine['XReal'] == pytest.approx(theirs['XReal'])

    def test_the_joined_map_survives_the_cleanup_pass(self, chain, executor, backend):
        """A workflow deletes its intermediates; what an output node named
        has to still be there."""
        assert executor.produced_output_names
        for name in executor.produced_output_names:
            assert name in backend._datasets


class TestConfinementAnalysisDecomposes:
    """The occupancy tables, rebuilt from the composite's own peaks inside a
    real graph — the composite's peak search is the one thing no simple node
    reproduces, so it is what feeds the chain."""

    @pytest.fixture
    def composite(self, backend):
        return backend.analyze_confinement(
            MockTask(), 'line', params={**DETECT, 'temperature_k': 94.0})

    @pytest.fixture
    def chain(self, executor):
        chain = Chain("confinement")
        source = chain.node("DatasetInput", dataset_name='line')
        analysis = chain.node("ConfinementAnalysis", **DETECT, temperature_k=94.0)
        binning = chain.node("EnergyBinning", temperature_k=94.0)
        matrix = chain.node("OccupancyMatrix")
        binned = chain.node("OccupancyMatrix")

        chain.wire(source, 'dataset', analysis, 'dataset')
        chain.wire(analysis, 'peaks', matrix, 'peaks')
        chain.wire(source, 'dataset', matrix, 'dataset')
        chain.wire(analysis, 'peaks', binning, 'peaks')
        chain.wire(source, 'dataset', binning, 'dataset')
        chain.wire(analysis, 'peaks', binned, 'peaks')
        chain.wire(source, 'dataset', binned, 'dataset')
        chain.wire(binning, 'all_bins', binned, 'intervals')

        chain.run(executor)
        return {'matrix': chain.outputs_of(executor, matrix),
                'binned': chain.outputs_of(executor, binned),
                'bins': chain.outputs_of(executor, binning)}

    def test_the_chain_rebuilds_the_peak_matrix(self, chain, composite):
        expected = _marks(composite['peak_matrix'])
        got = _marks(chain['matrix']['matrix'])

        assert np.isfinite(expected).sum() > 0
        np.testing.assert_array_equal(np.isfinite(expected), np.isfinite(got))
        np.testing.assert_array_equal(np.nan_to_num(expected), np.nan_to_num(got))

    def test_it_rebuilds_the_offset_table(self, chain, composite):
        np.testing.assert_array_equal(
            np.nan_to_num(_marks(composite['peak_matrix_offset'])),
            np.nan_to_num(_marks(chain['matrix']['matrix_offset'])))

    def test_the_energy_grid_reproduces_the_binned_table(self, chain, composite):
        expected = composite['peak_matrix_binned']
        got = chain['binned']['matrix']

        np.testing.assert_allclose(got.data.iloc[:, 0].to_numpy(),
                                   expected.data.iloc[:, 0].to_numpy())
        np.testing.assert_array_equal(np.nan_to_num(_marks(expected)),
                                      np.nan_to_num(_marks(got)))

    def test_it_rebuilds_the_peak_counts(self, chain, composite):
        assert (chain['matrix']['peak_count'].data['Peak_Count'].tolist()
                == composite['peak_count'].data['Peak_Count'].tolist())

    def test_the_occupied_bins_are_the_rows_the_binned_table_marks(
            self, chain, composite):
        """Not the composite's own ``intervals``: those are FWHM-merged, and
        the energy bins are deliberately a different rule. What must agree is
        the grid — the bins the node calls occupied are the rows the
        composite's binned table put a mark on."""
        binned = composite['peak_matrix_binned']
        axis = binned.data.iloc[:, 0].to_numpy()
        marked = axis[np.isfinite(_marks(binned)).any(axis=1)]
        found = sorted((lo + hi) / 2 for lo, hi in chain['bins']['intervals'])

        assert len(marked) > 0
        np.testing.assert_allclose(found, sorted(marked), rtol=1e-6)


class TestTheWholeChainRuns:
    """Baseline Estimate -> Peak Finder -> Energy Binning -> the two ends.

    No equality claim: the Peak Finder node is scipy's prominence search, so
    the peaks are its own. What must hold is that the chain executes with
    every port satisfied and produces coherent results at both ends — the
    thing that decides whether a user can actually wire this up.
    """

    @pytest.fixture
    def chain(self, executor, backend):
        chain = Chain("full")
        source = chain.node("DatasetInput", dataset_name='line')
        baseline = chain.node("BaselineEstimate", method='arpls')
        finder = chain.node("PeakFinder")
        binning = chain.node("EnergyBinning", temperature_k=94.0)
        matrix = chain.node("OccupancyMatrix")
        integrate = chain.node("Integration")
        assembly = chain.node("MapAssembly", scan_type='line')
        table = chain.node("DatasetOutput", output_name='Occupancy')

        chain.wire(source, 'dataset', baseline, 'dataset')
        chain.wire(baseline, 'corrected', finder, 'dataset')
        chain.wire(finder, 'peaks', binning, 'peaks')
        chain.wire(source, 'dataset', binning, 'dataset')
        chain.wire(finder, 'peaks', matrix, 'peaks')
        chain.wire(source, 'dataset', matrix, 'dataset')
        chain.wire(binning, 'all_bins', matrix, 'intervals')
        chain.wire(baseline, 'corrected', integrate, 'dataset')
        chain.wire(binning, 'intervals', integrate, 'intervals')
        chain.wire(integrate, 'flat_data', assembly, 'flat_data')
        chain.wire(integrate, 'intervals_out', assembly, 'intervals')
        chain.wire(source, 'dataset', assembly, 'source')
        chain.wire(matrix, 'matrix', table, 'dataset')

        result = chain.run(executor)
        return {'result': result,
                'baseline': chain.outputs_of(executor, baseline),
                'binning': chain.outputs_of(executor, binning),
                'matrix': chain.outputs_of(executor, matrix),
                'assembly': chain.outputs_of(executor, assembly)}

    def test_it_runs_with_every_port_satisfied(self, chain):
        assert chain['result']['errors'] == []

    def test_the_background_comes_off_first(self, chain):
        """arPLS is the reason this node had to exist: no workflow could do
        it before, and the chain's peaks depend on it."""
        corrected = chain['baseline']['corrected']
        assert corrected is not None
        assert np.nanmax(np.abs(corrected.spectra.to_numpy())) < 3e-7

    def test_the_peaks_land_in_bins(self, chain):
        assert len(chain['binning']['intervals']) > 0
        assert len(chain['binning']['all_bins']) >= len(chain['binning']['intervals'])

    def test_the_table_has_one_column_per_spectrum(self, chain):
        matrix = chain['matrix']['matrix']
        assert list(matrix.data.columns)[1:] == [f"P{n + 1}" for n in range(6)]

    def test_a_blank_cell_is_never_a_zero(self, chain):
        """A zero would read as a measured absence; a blank is a blank."""
        marks = _marks(chain['matrix']['matrix'])
        assert np.nanmin(marks) == 1.0

    def test_the_states_the_chain_found_are_the_planted_ones(self, chain):
        """Not an equality claim against the composite — a sanity one: the
        chain's own bins have to sit on the states that are actually there."""
        found = [(lo + hi) / 2 for lo, hi in chain['binning']['intervals']]
        for centre in CENTERS:
            assert any(abs(centre - value) < 0.02 for value in found), centre

    def test_the_far_end_writes_maps_in_metres(self, chain):
        assembly = chain['assembly']
        assert len(assembly['maps']) == len(chain['binning']['intervals'])
        for path in assembly['maps']:
            assert Path(path).exists()
        assert _gsf(assembly['maps'][0])['XYUnits'] == 'm'

    def test_the_occupancy_table_survives_the_cleanup_pass(self, chain, executor, backend):
        assert executor.produced_output_names
        for name in executor.produced_output_names:
            assert name in backend._datasets
        assert not any(str(name).startswith('_wf_') for name in backend._datasets)
