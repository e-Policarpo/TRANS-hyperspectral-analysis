"""
A workflow run leaves each result once: one file per table on disk, and the
browser told only about the outputs that survive the run.

Found 2026-11-13: the Flat Data output node rewrote tables the tool had
already saved (peaks/<base> - Features.csv AND integrated/<base>___features.csv),
and FFT / Convert Axis / Set Units announced intermediates the executor then
deleted.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from src.backend.workflow_engine import Connection, Workflow, create_node_from_tool
from tests.test_backend.test_workflow_rework_nodes import executor, make_dataset  # noqa: F401


def _chain(source_name, tool, port_out, output_tool, **params):
    wf = Workflow(id="w", name="Dup check")
    src = create_node_from_tool("DatasetInput")
    src.parameters["dataset_name"] = source_name
    node = create_node_from_tool(tool)
    node.parameters.update(params)
    out = create_node_from_tool(output_tool)
    out.parameters["output_name"] = port_out
    for n in (src, node, out):
        wf.add_node(n)
    in_port = node.inputs[0].id
    out_port = out.inputs[0].id
    assert wf.add_connection(Connection("c1", src.id, "dataset", node.id, in_port))
    assert wf.add_connection(Connection("c2", node.id, port_out, out.id, out_port))
    return wf


def _files(backend):
    root = backend._output_base_dir
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def _announced(backend):
    return [c.args[0] for c in backend.dataLoaded.emit.call_args_list]


def test_a_table_the_tool_saved_is_not_written_again(executor):
    ex, backend = executor
    backend._datasets["Src"] = make_dataset()
    result = ex.execute(_chain("Src", "SpectralFeatures", "features", "FlatDataOutput"))
    assert result["success"], result["errors"]

    csvs = [f for f in _files(backend) if f.endswith(".csv")]
    assert len(csvs) == 1, csvs


def test_a_table_no_tool_saved_is_still_written(executor):
    """Confinement Analysis builds its peak count without saving it, so the
    output node's CSV is the only copy and must stay."""
    ex, backend = executor
    backend._datasets["Src"] = make_dataset()
    result = ex.execute(_chain("Src", "ConfinementAnalysis", "peak_count", "FlatDataOutput"))
    assert result["success"], result["errors"]
    assert any("peak_count" in f for f in _files(backend)), _files(backend)


def test_only_surviving_outputs_are_announced(executor):
    ex, backend = executor
    backend._datasets["Src"] = make_dataset()
    result = ex.execute(_chain("Src", "FFT1D", "phase", "DatasetOutput"))
    assert result["success"], result["errors"]

    announced = _announced(backend)
    assert announced, "the output was never announced"
    assert all(name in backend._datasets for name in announced), announced
    assert len(announced) == len(set(announced))
    assert not any(name.startswith("_wf_") for name in announced)


def test_set_units_never_announces_the_executor_s_copy(executor):
    ex, backend = executor
    backend._datasets["Src"] = make_dataset()
    result = ex.execute(_chain("Src", "SetUnits", "dataset", "DatasetOutput",
                               x_unit="mV"))
    assert result["success"], result["errors"]
    assert all(name in backend._datasets for name in _announced(backend)), _announced(backend)
