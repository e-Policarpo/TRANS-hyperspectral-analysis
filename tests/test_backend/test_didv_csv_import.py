"""A CSV that already follows the dataset convention becomes a dI/dV dataset.

The confinement tools let a user refine a simulation against a curve they
already have. The file is taken at its word: bias in volts down the first
column, one spectrum per further column, no detection or processing.
"""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PySide6.QtCore")
from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(qt_app):
    return AppBackend()


def _write_csv(path, n_spectra=3, n_points=50, header=True):
    V = np.linspace(-1.0, 1.0, n_points)
    frame = pd.DataFrame({"Bias (V)": V})
    for i in range(n_spectra):
        frame[f"P{i + 1:02d}"] = np.exp(-((V - 0.2 * i) ** 2) / 0.05) + 0.1
    frame.to_csv(path, index=False, header=header)
    return frame


def test_a_conforming_csv_becomes_a_first_derivative_dataset(backend, tmp_path):
    csv = tmp_path / "line3_didv.csv"
    frame = _write_csv(csv)
    loaded = []
    backend.dataLoaded.connect(loaded.append)

    name = backend.importDidvCsv(str(csv))

    assert name == "line3_didv - 1st Derivative"
    assert name in backend._datasets and loaded == [name]
    ds = backend._datasets[name]
    assert ds.num_spectra == 3 and ds.num_points == 50
    np.testing.assert_allclose(ds.independent_var, frame["Bias (V)"].to_numpy())
    np.testing.assert_allclose(ds.spectra["P02"].to_numpy(), frame["P02"].to_numpy())
    info = ds.metadata.additional_info
    assert info["derivative_order"] == 1          # nothing will differentiate it again
    assert info["imported_as"] == "dI/dV"
    assert info["source_file"] == str(csv)
    assert ds.metadata.units == {"independent": "V", "dependent": "a.u."}


def test_it_accepts_a_file_url(backend, tmp_path):
    csv = tmp_path / "curve.csv"
    _write_csv(csv, n_spectra=1)
    assert backend.importDidvCsv("file://" + str(csv)) == "curve - 1st Derivative"


def test_importing_the_same_file_twice_keeps_both(backend, tmp_path):
    csv = tmp_path / "curve.csv"
    _write_csv(csv, n_spectra=1)
    first = backend.importDidvCsv(str(csv))
    second = backend.importDidvCsv(str(csv))
    assert first != second and second.startswith("curve - 1st Derivative")


def test_the_confinement_tools_can_see_it(backend, tmp_path):
    csv = tmp_path / "curve.csv"
    _write_csv(csv, n_spectra=2)
    name = backend.importDidvCsv(str(csv))
    assert name in backend.getDatasetList()
    info = backend.getDatasetInfo(name)
    assert info["num_spectra"] == 2


@pytest.mark.parametrize("content, why", [
    ("just one column\n1\n2\n3\n", "one column"),
    ("a,b\nx,1\ny,2\n", "non-numeric bias"),
    ("", "empty"),
])
def test_a_file_that_is_not_a_dataset_is_refused_by_name(backend, tmp_path, content, why):
    csv = tmp_path / "bad.csv"
    csv.write_text(content)
    errors = []
    backend.errorOccurred.connect(lambda t, m: errors.append((t, m)))

    assert backend.importDidvCsv(str(csv)) == "", why
    assert "bad.csv" not in " ".join(backend._datasets)
    assert errors and errors[-1][0] == "Import dI/dV CSV"


def test_a_missing_file_is_refused(backend, tmp_path):
    errors = []
    backend.errorOccurred.connect(lambda t, m: errors.append(m))
    assert backend.importDidvCsv(str(tmp_path / "nope.csv")) == ""
    assert errors and "Not a file" in errors[-1]


# The dialect is not presumed. A curve that went through a pt-BR spreadsheet
# on its way here — quoted numbers, decimal comma, no header — is the normal
# case, and it used to import as an EMPTY dataset without a word.

def test_a_pt_br_spreadsheet_export_reads_correctly(backend, tmp_path):
    csv = tmp_path / "Line 3 p04 rep31.csv"
    csv.write_text('"-0,6","2,174049307512E-08"\n'
                   '"-0,5952941182223","8,166315505344E-08"\n'
                   '"-0,5905882364446","1,257343609765E-07"\n'
                   '"-0,5858823546669","1,546813447327E-07"\n')
    name = backend.importDidvCsv(str(csv))
    assert name == "Line 3 p04 rep31 - 1st Derivative"
    ds = backend._datasets[name]
    assert ds.num_spectra == 1 and ds.num_points == 4
    np.testing.assert_allclose(ds.independent_var[:2], [-0.6, -0.5952941182223])
    np.testing.assert_allclose(ds.spectra.iloc[:2, 0], [2.174049307512e-08, 8.166315505344e-08])
    assert list(ds.spectra.columns) == ["S01"]        # headerless: named for it


def test_a_semicolon_decimal_comma_file_with_a_header_reads_correctly(backend, tmp_path):
    csv = tmp_path / "excel_ptbr.csv"
    csv.write_text("Bias;P01;P02\n-0,5;1,5E-09;2,0E-09\n0,0;3,0E-09;1,0E-09\n0,5;2,5E-09;4,0E-09\n")
    name = backend.importDidvCsv(str(csv))
    ds = backend._datasets[name]
    assert ds.num_spectra == 2 and ds.num_points == 3
    assert list(ds.spectra.columns) == ["P01", "P02"]
    np.testing.assert_allclose(ds.spectra["P02"], [2.0e-09, 1.0e-09, 4.0e-09])


def test_a_file_that_parses_to_nothing_is_refused_not_registered_empty(backend, tmp_path):
    csv = tmp_path / "words.csv"
    csv.write_text("a,b\nfoo,bar\nbaz,qux\n")
    errors = []
    backend.errorOccurred.connect(lambda t, m: errors.append(m))
    assert backend.importDidvCsv(str(csv)) == ""
    assert not [n for n in backend._datasets if n.startswith("words")]
    assert errors and "no numbers" in errors[-1]


def test_the_curve_is_saved_into_the_project_in_the_project_dialect(backend, tmp_path):
    """The original may be a pt-BR spreadsheet export anywhere on disk; the
    project keeps its own copy, '.' decimals and a header, under imported/."""
    backend._output_base_dir = tmp_path / "proj_outputs"
    csv = tmp_path / "Line 3 p04 rep31.csv"
    csv.write_text('"-0,6","2,174049307512E-08"\n"-0,5","8,166315505344E-08"\n')

    name = backend.importDidvCsv(str(csv))

    saved = backend._datasets[name].metadata.additional_info["saved_as"]
    assert saved.startswith(str(tmp_path / "proj_outputs" / "imported"))
    copy = pd.read_csv(saved)                        # plain read: TRANS dialect
    assert list(copy.columns) == ["V", "S01"]
    np.testing.assert_allclose(copy["V"], [-0.6, -0.5])
    # And the copy re-imports without the sniffing ever mattering.
    again = backend.importDidvCsv(saved)
    assert again and backend._datasets[again].num_points == 2


def test_without_a_project_the_dataset_still_loads_but_nothing_is_written(backend, tmp_path):
    backend._output_base_dir = None
    csv = tmp_path / "c.csv"
    _write_csv(csv, n_spectra=1)
    name = backend.importDidvCsv(str(csv))
    assert name and "saved_as" not in backend._datasets[name].metadata.additional_info
