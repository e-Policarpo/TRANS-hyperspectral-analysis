"""
Tests for the Confinement Design workflow node.

The line-scan designer as a node: a line scan in, a flat table out that Map
Assembly can lay on the sample. The claims are the node's contract — the
ports the dispatch fills, the parameters the backend actually reads — and
that a chain ending in Map Assembly works, which is what makes the tool a
step rather than a destination.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
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
from src.physics.analytical import box_energies_1d_eV

STEP_M = 5e-9
BAND_EDGE = 0.30


def _line(n_points=4, well_at=(1, 2)):
    V = np.linspace(-0.2, 1.6, 901)
    columns = {}
    for i in range(n_points):
        y = 0.01 * np.random.RandomState(5 + i).randn(V.size)
        y = y + 4 * np.exp((V - 1.3) * 5) * (V > BAND_EDGE)
        if i in well_at:
            for level in [E for E, _ in box_energies_1d_eV(8.0, 0.067, 3)][:3]:
                y = y + 0.5 * np.exp(-((V - (BAND_EDGE + level)) / 0.015) ** 2)
        columns[f"P{i + 1}"] = y
    return SpectralData(pd.DataFrame({"V": V, **columns}), SpectralMetadata(
        source_type='sts', dimensions=(n_points, 1), scan_mode='line',
        units={'independent': 'V', 'dependent': 'A/V'},
        additional_info={'spatial_layout': 'line',
                         'spectrum_meta': [{'location_m': [n * STEP_M, 0.0]}
                                           for n in range(n_points)]}))


class TestTheNodeDefinition:
    def test_it_is_registered_in_the_analysis_category(self):
        node_def = TOOL_DEFINITIONS["ConfinementDesign"]
        assert node_def["category"] == "Analysis"
        assert node_def["display_name"] == "Confinement Design"

    def test_it_takes_a_dataset_and_returns_a_table_and_a_map(self):
        node_def = TOOL_DEFINITIONS["ConfinementDesign"]
        inputs = {i["id"]: i for i in node_def["inputs"]}
        outputs = {o["id"]: o for o in node_def["outputs"]}

        assert set(inputs) == {"dataset"} and inputs["dataset"]["required"]
        assert set(outputs) == {"table", "maps"}
        assert outputs["table"]["port_type"] == "flat_data"
        assert outputs["maps"]["port_type"] == "map"

    def test_every_parameter_is_one_the_tool_reads(self):
        """A knob the backend ignores is a knob that lies to the user."""
        from src.backend.tool_implementations import ToolImplementations
        from src.processing.peak_detection import Params

        known = (set(ToolImplementations.DESIGNER_DEFAULTS)
                 | set(ToolImplementations.LINE_DESIGNER_DEFAULTS)
                 | set(vars(Params())))
        params = set(TOOL_DEFINITIONS["ConfinementDesign"]["parameters"])

        assert params <= known, params - known

    def test_the_defaults_agree_with_the_tool_s(self):
        from src.backend.tool_implementations import ToolImplementations

        defaults = {**ToolImplementations.DESIGNER_DEFAULTS,
                    **ToolImplementations.LINE_DESIGNER_DEFAULTS}
        params = TOOL_DEFINITIONS["ConfinementDesign"]["parameters"]

        for key in ('carrier', 'ndim', 'coords', 'match', 'priority',
                    'maxsol', 'max_rrmse', 'group_tol_nm'):
            assert params[key]["default"] == defaults[key], key

    def test_the_match_modes_are_the_engine_s(self):
        from src.physics.designer import MATCHES

        options = TOOL_DEFINITIONS["ConfinementDesign"]["parameters"]["match"]["options"]
        assert set(options) == set(MATCHES)

    def test_it_sits_after_the_occupancy_matrix_in_the_palette(self):
        analysis = next(c["tools"] for c in get_tool_categories()
                        if c["category"] == "Analysis")
        assert (analysis.index("ConfinementDesign")
                - analysis.index("OccupancyMatrix")) == 1

    def test_its_table_feeds_map_assembly(self):
        """The point of a flat table: every column is a map away."""
        wf = Workflow(id="wf_cd", name="Design WF")
        design = create_node_from_tool("ConfinementDesign", 0, 0)
        assembly = create_node_from_tool("MapAssembly", 200, 0)
        for node in (design, assembly):
            wf.add_node(node)

        assert wf.add_connection(Connection(
            id="c1", source_node_id=design.id, source_port_id="table",
            target_node_id=assembly.id, target_port_id="flat_data")) is True

    def test_its_map_can_be_captured(self):
        wf = Workflow(id="wf_cd2", name="Design WF")
        design = create_node_from_tool("ConfinementDesign", 0, 0)
        output = create_node_from_tool("MapOutput", 200, 0)
        for node in (design, output):
            wf.add_node(node)

        assert wf.validate_connection(Connection(
            id="c1", source_node_id=design.id, source_port_id="maps",
            target_node_id=output.id, target_port_id="map")) is True


class TestTheNodeRunning:
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
        node = create_node_from_tool("ConfinementDesign", 0, 0)
        node.parameters.update({'height': 3.0, 'maxsol': 1, 'Lmax': 20.0,
                                **params})
        return node

    def test_it_fills_both_ports(self, executor):
        outputs = executor._execute_node(self._node(), {'dataset': _line()})

        assert set(outputs) == {"table", "maps"}
        assert isinstance(outputs['table'], SpectralData)
        assert len(outputs['maps']) == 1

    def test_the_table_is_one_row_per_position(self, executor):
        outputs = executor._execute_node(self._node(), {'dataset': _line()})
        table = outputs['table'].data

        assert len(table) == 4
        assert table['size_nm'].notna().sum() == 2

    def test_the_table_map_assembles_in_metres(self, executor):
        """The chain that makes the tool a step: design, then lay it out."""
        from src.utils.gsf_io import read_gsf

        design = executor._execute_node(self._node(), {'dataset': _line()})
        assembled = executor._execute_node(
            create_node_from_tool("MapAssembly", 0, 0),
            {'flat_data': design['table']})

        assert assembled['maps']
        tiff = Path(assembled['maps'][0])
        header = read_gsf(tiff.parent.parent / 'gsf' / (tiff.stem + '.gsf'))[1]
        assert header['XYUnits'] == 'm'

    def test_a_string_input_is_rejected(self, executor):
        assert executor._execute_node(self._node(), {'dataset': 'A name'}) == {}

    def test_nothing_happens_without_a_dataset(self, executor):
        assert executor._execute_node(self._node(), {}) == {}
