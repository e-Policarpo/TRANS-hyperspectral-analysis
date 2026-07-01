"""
Tests for the unified project-browser folder tree (Phase D backend).

Covers AppBackend's folder slots (create/rename/delete/move + getBrowserTree)
and the .hrt persistence round-trip via ProjectManager.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.backend.project_manager import ProjectManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(qapp):
    be = AppBackend()
    yield be
    be.worker_manager.shutdown()


# --- folder CRUD + placements ------------------------------------------------

def test_create_folder_appears_in_tree(backend):
    fid = backend.createFolder("Experiment A", "")
    tree = backend.getBrowserTree()
    assert any(f["id"] == fid and f["name"] == "Experiment A" for f in tree["folders"])


def test_nested_folder_records_parent(backend):
    parent = backend.createFolder("Parent", "")
    child = backend.createFolder("Child", parent)
    tree = backend.getBrowserTree()
    rec = next(f for f in tree["folders"] if f["id"] == child)
    assert rec["parent"] == parent


def test_create_folder_with_bad_parent_goes_to_root(backend):
    fid = backend.createFolder("Orphan", "folder_does_not_exist")
    rec = next(f for f in backend.getBrowserTree()["folders"] if f["id"] == fid)
    assert rec["parent"] == ""


def test_move_item_places_and_unfiles(backend):
    fid = backend.createFolder("Bucket", "")
    backend.moveItem("dataset:Foo", fid)
    assert backend.getBrowserTree()["placements"].get("dataset:Foo") == fid
    # Moving to "" unfiles it.
    backend.moveItem("dataset:Foo", "")
    assert "dataset:Foo" not in backend.getBrowserTree()["placements"]


def test_move_item_to_missing_folder_is_ignored(backend):
    backend.moveItem("map:1", "nope")
    assert "map:1" not in backend.getBrowserTree()["placements"]


def test_rename_folder(backend):
    fid = backend.createFolder("Old", "")
    assert backend.renameFolder(fid, "New") is True
    rec = next(f for f in backend.getBrowserTree()["folders"] if f["id"] == fid)
    assert rec["name"] == "New"


def test_delete_folder_reparents_children_and_items(backend):
    parent = backend.createFolder("P", "")
    child = backend.createFolder("C", parent)
    backend.moveItem("dataset:D", child)
    # Delete the child: its item should move up to the parent.
    assert backend.deleteFolder(child) is True
    tree = backend.getBrowserTree()
    assert all(f["id"] != child for f in tree["folders"])
    assert tree["placements"].get("dataset:D") == parent


def test_delete_top_level_folder_unfiles_items(backend):
    fid = backend.createFolder("Top", "")
    backend.moveItem("note:7", fid)
    backend.deleteFolder(fid)
    assert "note:7" not in backend.getBrowserTree()["placements"]


def test_signal_emitted_on_changes(backend):
    seen = []
    backend.browserTreeChanged.connect(lambda: seen.append(1))
    fid = backend.createFolder("S", "")
    backend.moveItem("image:2", fid)
    backend.renameFolder(fid, "S2")
    backend.deleteFolder(fid)
    assert len(seen) == 4


# --- persistence round-trip --------------------------------------------------

def test_browser_tree_survives_save_load(tmp_path):
    pm = ProjectManager()
    tree = {
        "folders": [
            {"id": "folder_1", "name": "Exp", "parent": ""},
            {"id": "folder_2", "name": "PL", "parent": "folder_1"},
        ],
        "placements": {"dataset:A": "folder_2", "map:3": "folder_1"},
    }
    path = tmp_path / "proj.hrt"
    assert pm.save_project(path, {"datasets": {}, "browser_tree": tree}) is True

    loaded = pm.load_project(path)
    assert loaded is not None
    assert loaded["browser_tree"] == tree


# --- getOutputList must never blank the browser (peak-finder regression) -----

def test_get_output_list_survives_non_string_path(backend):
    """A tool that stored a dict (or None) as an output 'path' must not make
    getOutputList raise — that blanked the whole project browser."""
    backend.output_files.append(
        {'id': 'output_1', 'tool': 'Peak Finding',
         'path': {'peaks_path': '/x/y.csv', 'intervals': []}})
    backend.output_files.append(
        {'id': 'output_2', 'tool': 'X', 'path': None})
    backend.output_files.append(
        {'id': 'output_3', 'tool': 'Smoothing', 'path': '/a/b/c.csv'})
    out = backend.getOutputList()          # must not raise
    assert len(out) == 3
    assert out[2]['filename'] == 'c.csv'
    # The bad entries degrade gracefully to empty filenames.
    assert out[0]['filename'] == ''
    assert out[1]['path'] == ''
