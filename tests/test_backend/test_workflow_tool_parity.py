"""
A workflow node must be able to reproduce the tool it stands for: the same
knobs, the same choices, the same defaults.

Found by the 2026-11-13 audit: the Confinement Designer node exposed 12 of
the panel's ~37 settings (no 0D, no disc, no delta_e_ratios, no tolerance),
and Background Flattening started from a different method than the panel.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

import re
from pathlib import Path

import pytest

from src.backend.batch_tools import BATCH_TOOLS
from src.backend.tool_implementations import ToolImplementations
from src.backend.workflow_engine import TOOL_DEFINITIONS, create_node_from_tool
from src.backend.workflow_manager import WorkflowExecutor

VOCAB = (Path(__file__).resolve().parents[2] / "src" / "qml" / "tools"
         / "DesignerVocabulary.js").read_text()

# The panel leaves these empty to mean "the engine decides"; a node field
# cannot be empty, so it shows them as 0 / "".
UNSET = {'seed': '', 'resolution_meV': 0.0, 'enum_max_nodes': 0, 'dup_rel': 0.0}
# Set through the per-dimension controls, which a node has no equivalent of.
PANEL_ONLY = {'fixed', 'box'}


def _keys(var):
    match = re.search(rf"var {var} = \[([^\]]*)\]", VOCAB)
    assert match, var
    return re.findall(r'"([^"]*)"', match.group(1))


def _coords():
    keys = set()
    for block in re.findall(r"keys: \[([^\]]*)\]", VOCAB.split("function coordsFor")[1]
                            .split("function symsFor")[0]):
        keys |= set(re.findall(r'"([^"]*)"', block))
    return keys


def _syms():
    keys = set()
    # Stop at the comment above dimsFor: it quotes a {keys: [...]} example.
    for block in re.findall(r"keys: \[([^\]]*)\]", VOCAB.split("function symsFor")[1]
                            .split("// The dimensions a geometry")[0]):
        keys |= set(re.findall(r'"([^"]*)"', block))
    return keys


class TestConfinementDesignerNode:
    params = TOOL_DEFINITIONS["ConfinementDesigner"]["parameters"]

    def test_every_tool_setting_is_a_node_parameter(self):
        missing = set(ToolImplementations.DESIGNER_DEFAULTS) - PANEL_ONLY - set(self.params)
        assert not missing, sorted(missing)

    def test_defaults_are_the_tool_s(self):
        for name, value in ToolImplementations.DESIGNER_DEFAULTS.items():
            if name in PANEL_ONLY:
                continue
            expected = UNSET.get(name, value) if value is None else value
            assert self.params[name]["default"] == expected, name

    @pytest.mark.parametrize("param, choices", [
        ("ndim", lambda: set(_keys("ndimKeys"))),
        ("carrier", lambda: set(_keys("carrierKeys"))),
        ("match", lambda: set(_keys("matchKeys"))),
        ("priority", lambda: set(_keys("priorityKeys"))),
        ("assign", lambda: set(_keys("assignKeys"))),
        ("search_mode", lambda: set(_keys("searchModeKeys"))),
        ("sort", lambda: set(_keys("sortKeys"))),
        ("coords", _coords),
        ("sym", _syms),
    ])
    def test_it_offers_every_choice_the_panel_does(self, param, choices):
        offered = set(self.params[param]["options"])
        assert choices() <= offered, choices() - offered

    def test_empty_knobs_reach_the_tool_as_none(self, monkeypatch):
        seen = {}

        class Backend:
            _datasets = {}

            def design_confinement(self, task, name, params):
                seen.update(params)
                return {'tables': []}

        executor = WorkflowExecutor(Backend())
        monkeypatch.setattr(executor, "_stage_dataset", lambda ds, op="": "staged")
        node = create_node_from_tool("ConfinementDesigner")
        node.parameters.update(ndim="0D", coords="disc", match="delta_e_ratios", tol=12.5)
        executor._execute_node(node, {'dataset': object()})

        assert seen['ndim'] == "0D" and seen['coords'] == "disc" and seen['tol'] == 12.5
        for key in ('seed', 'resolution_meV', 'enum_max_nodes', 'dup_rel'):
            assert seen[key] is None, key


def test_background_flattening_starts_where_the_panel_does():
    spec = BATCH_TOOLS['curve_background_flattening']
    node = TOOL_DEFINITIONS["CurveFitting"]["parameters"]
    for name in ('fit_type', 'degree', 'basis'):
        assert node[name]["default"] == spec.defaults[name], name
