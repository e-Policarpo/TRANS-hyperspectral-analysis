"""
Saving, opening and importing .flow files.

Each test pins a way a workflow file used to be lost or misread:
an external .flow deleted by the rename cleanup, two same-named workflows
overwriting each other, a percent-encoded file URL that never opened, stale
saved ports, and two copies of one file sharing an id.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QUrl

from src.backend.workflow_manager import WorkflowManager
from src.backend.workflow_engine import TOOL_DEFINITIONS, Workflow


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "my project"           # a space, as in real projects
    root.mkdir()
    return root


@pytest.fixture
def manager(project):
    return WorkflowManager(SimpleNamespace(_project_path=project, _datasets={}))


def _two_node_flow(manager, name="Chain"):
    wid = manager.createWorkflow(name)
    a = manager.addNode(wid, "DatasetInput", 0, 0)
    b = manager.addNode(wid, "Derivative", 0, 200)
    assert manager.addConnection(wid, a, "dataset", b, "dataset")
    return wid


def _write_external(tmp_path, manager, name="Shared chain"):
    wid = _two_node_flow(manager, name)
    data = manager.workflows[wid].to_dict()
    outside = tmp_path / "elsewhere with spaces"
    outside.mkdir()
    path = outside / f"{name}.flow"
    path.write_text(json.dumps(data))
    manager.workflows.clear()
    manager._workflow_paths.clear()
    return path, data


class TestSave:
    def test_round_trip_keeps_nodes_connections_and_parameters(self, manager):
        wid = _two_node_flow(manager)
        deriv = [n for n in manager.workflows[wid].nodes if n.tool_name == "Derivative"][0]
        manager.setNodeParameter(wid, deriv.id, "order", 2)
        path = manager.saveWorkflow(wid)

        manager.workflows.clear()
        manager._workflow_paths.clear()
        again = manager.loadWorkflow(path)
        wf = manager.workflows[again]
        assert len(wf.nodes) == 2 and len(wf.connections) == 1
        assert [n for n in wf.nodes if n.tool_name == "Derivative"][0].parameters["order"] == 2

    def test_two_workflows_with_one_name_get_two_files(self, manager):
        first = manager.saveWorkflow(_two_node_flow(manager, "Same"))
        second = manager.saveWorkflow(_two_node_flow(manager, "Same"))
        assert first != second
        assert Path(first).exists() and Path(second).exists()
        assert Path(second).name == "Same (2).flow"

    def test_saving_twice_reuses_the_file(self, manager):
        wid = _two_node_flow(manager, "Again")
        assert manager.saveWorkflow(wid) == manager.saveWorkflow(wid)

    def test_a_rename_replaces_the_old_project_file(self, manager, project):
        wid = _two_node_flow(manager, "Old")
        old = Path(manager.saveWorkflow(wid))
        manager.setWorkflowName(wid, "New")
        new = Path(manager.saveWorkflow(wid))
        assert new.name == "New.flow" and not old.exists()

    def test_an_empty_name_still_saves(self, manager):
        path = manager.saveWorkflow(_two_node_flow(manager, ""))
        assert Path(path).name == "Untitled Workflow.flow"

    def test_saving_an_external_flow_never_deletes_it(self, manager, tmp_path, project):
        external, _ = _write_external(tmp_path, manager)
        wid = manager.loadWorkflow(str(external))
        manager.setWorkflowName(wid, "Renamed")
        saved = Path(manager.saveWorkflow(wid))

        assert external.exists(), "the user's own file was deleted"
        assert saved.parent == project / "workflows"


class TestOpen:
    def test_a_percent_encoded_file_url_opens(self, manager, tmp_path):
        external, _ = _write_external(tmp_path, manager)
        # What a QML FileDialog's `file` gives as a string.
        url = QUrl.fromLocalFile(str(external)).toString(QUrl.FullyEncoded)
        assert "%20" in url
        assert manager.loadWorkflow(url)

    def test_a_bad_file_reports_why(self, manager, tmp_path):
        errors = []
        manager.workflowError.connect(lambda t, m: errors.append(m))
        bad = tmp_path / "bad.flow"
        bad.write_text("{not json")
        assert manager.loadWorkflow(str(bad)) == ""
        assert manager.loadWorkflow(str(tmp_path / "missing.flow")) == ""
        assert len(errors) == 2 and "missing.flow" in errors[1]

    def test_ports_come_from_the_current_definition(self, manager, tmp_path):
        """An FFT node saved before the rework had a single `fft_result`
        port; the current node has magnitude and phase."""
        wid = manager.createWorkflow("Old FFT")
        manager.addNode(wid, "FFT1D", 0, 0)
        data = manager.workflows[wid].to_dict()
        data["nodes"][0]["outputs"] = [{
            "id": "legacy_out", "name": "Legacy", "port_type": "dataset",
            "is_input": False}]
        data["nodes"][0]["display_name"] = "Old name"
        path = tmp_path / "old.flow"
        path.write_text(json.dumps(data))

        node = manager.workflows[manager.loadWorkflow(str(path))].nodes[0]
        current = {p["id"] for p in TOOL_DEFINITIONS["FFT1D"]["outputs"]}
        ids = [p.id for p in node.outputs]
        assert current <= set(ids)
        assert ids[-1] == "legacy_out"          # legacy kept, after the current ones
        assert node.display_name == TOOL_DEFINITIONS["FFT1D"]["display_name"]

    def test_a_wire_to_a_vanished_port_is_dropped_not_fatal(self):
        data = {"id": "w", "name": "w", "nodes": [
            {"id": "a", "tool_name": "DatasetInput", "display_name": "x"},
            {"id": "b", "tool_name": "Derivative", "display_name": "x"}],
            "connections": [
                {"id": "c1", "source_node_id": "a", "source_port_id": "dataset",
                 "target_node_id": "b", "target_port_id": "dataset"},
                {"id": "c2", "source_node_id": "a", "source_port_id": "nope",
                 "target_node_id": "b", "target_port_id": "dataset"}]}
        wf = Workflow.from_dict(data)
        assert [c.id for c in wf.connections] == ["c1"]

    def test_two_copies_of_one_file_open_side_by_side(self, manager, tmp_path):
        external, _ = _write_external(tmp_path, manager)
        copy = external.with_name("copy.flow")
        copy.write_text(external.read_text())
        a = manager.loadWorkflow(str(external))
        b = manager.loadWorkflow(str(copy))
        assert a != b and a in manager.workflows and b in manager.workflows


class TestImport:
    def test_import_copies_into_the_project_and_leaves_the_original(self, manager, tmp_path, project):
        external, original = _write_external(tmp_path, manager)
        wid = manager.importWorkflow(
            QUrl.fromLocalFile(str(external)).toString(QUrl.FullyEncoded))

        assert wid
        listed = manager.getSavedWorkflows()
        assert [w["name"] for w in listed] == ["Shared chain"]
        assert Path(listed[0]["path"]).parent == project / "workflows"
        assert json.loads(external.read_text()) == original

        manager.setWorkflowName(wid, "Mine now")
        manager.saveWorkflow(wid)
        assert external.exists()

    def test_importing_twice_makes_two_project_workflows(self, manager, tmp_path):
        external, _ = _write_external(tmp_path, manager)
        a = manager.importWorkflow(str(external))
        b = manager.importWorkflow(str(external))
        assert a != b
        assert len(manager.getSavedWorkflows()) == 2

    def test_a_file_already_in_the_project_is_just_opened(self, manager, project):
        path = manager.saveWorkflow(_two_node_flow(manager, "Here"))
        manager.workflows.clear()
        manager._workflow_paths.clear()
        assert manager.importWorkflow(path)
        assert len(manager.getSavedWorkflows()) == 1


class TestProjectPermanence:
    """Workflows live in the .hrt as well as in <project>/workflows."""

    def test_the_project_file_round_trips_every_workflow(self, manager, project):
        from src.backend.project_manager import ProjectManager

        wid = _two_node_flow(manager, "Kept")
        manager.createWorkflow("Empty placeholder")          # no nodes: not kept
        pm = ProjectManager()
        hrt = project / "p.hrt"
        assert pm.save_project(hrt, {'datasets': {}, 'workflows': manager.export_workflows()})

        loaded = pm.load_project(hrt)
        assert [w['name'] for w in loaded['workflows']] == ["Kept"]
        assert loaded['workflows'][0]['id'] == wid

    def test_reopening_restores_them_and_rewrites_a_lost_flow(self, manager, project):
        _two_node_flow(manager, "Lost file")
        entries = manager.export_workflows()

        # The project moved without its workflows folder.
        fresh = WorkflowManager(SimpleNamespace(_project_path=project / "moved", _datasets={}))
        (project / "moved").mkdir()
        assert fresh.restore_workflows(entries) == 1

        listed = fresh.getProjectWorkflows()
        assert [(w['name'], w['loaded']) for w in listed] == [("Lost file", True)]
        assert Path(listed[0]['path']).exists()
        assert len(fresh.workflows[listed[0]['id']].connections) == 1

    def test_restoring_does_not_duplicate_an_existing_flow(self, manager, project):
        wid = _two_node_flow(manager, "On disk")
        manager.saveWorkflow(wid)
        entries = manager.export_workflows()
        fresh = WorkflowManager(SimpleNamespace(_project_path=project, _datasets={}))
        fresh.restore_workflows(entries)
        assert len(list((project / "workflows").glob("*.flow"))) == 1

    def test_the_menu_lists_loaded_workflows_and_unloaded_files(self, manager, project):
        on_disk = manager.saveWorkflow(_two_node_flow(manager, "File only"))
        manager.workflows.clear()
        manager._workflow_paths.clear()
        live = _two_node_flow(manager, "Loaded, never saved")

        listed = manager.getProjectWorkflows()
        assert [(w['name'], w['loaded']) for w in listed] == [
            ("Loaded, never saved", True), ("File only", False)]
        assert listed[0]['id'] == live and listed[1]['path'] == on_disk
