"""
Tests for promoting a table (TableDataModel) into a SpectralData dataset.

Covers TableDataModel.to_dataframe()/canBeDataset() and
AppBackend.createDatasetFromTable() — the table↔dataset unification path.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.models.table_data_model import TableDataModel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(qapp):
    be = AppBackend()
    yield be
    be.worker_manager.shutdown()


def _table(rows, headers):
    m = TableDataModel()
    m.setTableData(rows, headers)
    return m


# --- TableDataModel accessors ------------------------------------------------

def test_to_dataframe_uses_header_names():
    m = _table([[0.0, 1.0], [1.0, 2.0]], ["Wavelength", "Intensity"])
    df = m.to_dataframe()
    assert list(df.columns) == ["Wavelength", "Intensity"]
    assert df.shape == (2, 2)


def test_can_be_dataset_true_for_numeric_two_columns():
    m = _table([[0.0, 1.0], [1.0, 2.0]], ["X", "Y"])
    assert m.canBeDataset() is True


def test_can_be_dataset_false_for_single_column():
    m = _table([[1.0], [2.0]], ["X"])
    assert m.canBeDataset() is False


def test_can_be_dataset_false_for_text_first_column():
    m = _table([["a", 1.0], ["b", 2.0]], ["X", "Y"])
    assert m.canBeDataset() is False


# --- AppBackend.createDatasetFromTable ---------------------------------------

def test_create_dataset_happy_path(backend):
    m = _table([[0.0, 10.0], [1.0, 20.0], [2.0, 30.0]], ["V", "Current"])
    loaded = []
    backend.dataLoaded.connect(lambda n: loaded.append(n))

    name = backend.createDatasetFromTable(m, "MyTable")

    assert name == "MyTable"
    assert "MyTable" in backend._datasets
    assert loaded == ["MyTable"]
    sd = backend._datasets["MyTable"]
    assert sd.num_spectra == 1
    assert sd.num_points == 3
    assert sd.independent_var_name == "V"


def test_create_dataset_rejects_single_column(backend):
    m = _table([[1.0], [2.0]], ["X"])
    errors = []
    backend.errorOccurred.connect(lambda title, msg: errors.append((title, msg)))

    name = backend.createDatasetFromTable(m, "Solo")

    assert name == ""
    assert "Solo" not in backend._datasets
    assert len(errors) == 1


def test_create_dataset_rejects_text_first_column(backend):
    m = _table([["a", 1.0], ["b", 2.0]], ["X", "Y"])
    errors = []
    backend.errorOccurred.connect(lambda title, msg: errors.append((title, msg)))

    name = backend.createDatasetFromTable(m, "Texty")

    assert name == ""
    assert "Texty" not in backend._datasets
    assert len(errors) == 1


def test_create_dataset_dedups_names(backend):
    m1 = _table([[0.0, 1.0], [1.0, 2.0]], ["X", "Y"])
    m2 = _table([[0.0, 3.0], [1.0, 4.0]], ["X", "Y"])

    n1 = backend.createDatasetFromTable(m1, "Data")
    n2 = backend.createDatasetFromTable(m2, "Data")

    assert n1 == "Data"
    assert n2 == "Data (1)"
    assert {"Data", "Data (1)"} <= set(backend._datasets)


def test_create_dataset_blank_name_gets_default(backend):
    m = _table([[0.0, 1.0], [1.0, 2.0]], ["X", "Y"])
    name = backend.createDatasetFromTable(m, "")
    assert name == "Table dataset"
    assert "Table dataset" in backend._datasets


def test_create_dataset_is_undoable(backend):
    m = _table([[0.0, 1.0], [1.0, 2.0]], ["X", "Y"])
    name = backend.createDatasetFromTable(m, "Undoable")
    assert name in backend._datasets
    assert backend._undo_manager.canUndo

    backend._undo_manager.undo()
    assert name not in backend._datasets

    backend._undo_manager.redo()
    assert name in backend._datasets
