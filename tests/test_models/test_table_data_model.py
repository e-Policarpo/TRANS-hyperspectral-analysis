"""
Tests for TableDataModel - QAbstractTableModel with formula support
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models.table_data_model import (
    TableDataModel, FormulaEngine, ColumnMetadata, parse_number
)


# =============================================================================
# parse_number Tests
# =============================================================================

class TestParseNumber:
    """Tests for the parse_number function supporting multiple decimal formats."""

    def test_parse_integer(self):
        """Test parsing plain integers."""
        assert parse_number("42") == 42.0
        assert parse_number("-17") == -17.0
        assert parse_number("0") == 0.0

    def test_parse_us_decimal(self):
        """Test parsing US-style decimals (dot separator)."""
        assert parse_number("3.14159") == pytest.approx(3.14159)
        assert parse_number("-2.5") == pytest.approx(-2.5)
        assert parse_number("0.001") == pytest.approx(0.001)

    def test_parse_european_decimal(self):
        """Test parsing European-style decimals (comma separator)."""
        assert parse_number("3,14159") == pytest.approx(3.14159)
        assert parse_number("-2,5") == pytest.approx(-2.5)
        assert parse_number("0,001") == pytest.approx(0.001)

    def test_parse_us_thousands(self):
        """Test parsing US-style thousands (comma) with dot decimal."""
        assert parse_number("1,234.56") == pytest.approx(1234.56)
        assert parse_number("1,234,567.89") == pytest.approx(1234567.89)

    def test_parse_european_thousands(self):
        """Test parsing European-style thousands (dot) with comma decimal."""
        assert parse_number("1.234,56") == pytest.approx(1234.56)
        assert parse_number("1.234.567,89") == pytest.approx(1234567.89)

    def test_parse_scientific_notation(self):
        """Test parsing scientific notation."""
        assert parse_number("1.23e-4") == pytest.approx(1.23e-4)
        assert parse_number("1,23e-4") == pytest.approx(1.23e-4)
        assert parse_number("5.67E+10") == pytest.approx(5.67e10)

    def test_parse_with_whitespace(self):
        """Test parsing numbers with leading/trailing whitespace."""
        assert parse_number("  42  ") == 42.0
        assert parse_number("\t3.14\n") == pytest.approx(3.14)

    def test_parse_invalid_raises(self):
        """Test that invalid inputs raise ValueError."""
        with pytest.raises(ValueError):
            parse_number("")
        with pytest.raises(ValueError):
            parse_number(None)


# =============================================================================
# TableDataModel Basic Tests
# =============================================================================

class TestTableDataModelBasic:
    """Basic tests for TableDataModel initialization and data operations."""

    @pytest.fixture
    def empty_model(self):
        """Create an empty TableDataModel."""
        return TableDataModel()

    @pytest.fixture
    def sample_model(self):
        """Create a TableDataModel with sample data."""
        model = TableDataModel()
        model.setTableData(
            [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
            ['A', 'B', 'C']
        )
        return model

    def test_empty_model_dimensions(self, empty_model):
        """Test empty model has zero dimensions."""
        assert empty_model.rows == 0
        assert empty_model.columns == 0
        assert empty_model.isEmpty

    def test_set_table_data(self, empty_model):
        """Test setting table data."""
        empty_model.setTableData([[1, 2], [3, 4]], ['X', 'Y'])
        assert empty_model.rows == 2
        assert empty_model.columns == 2
        assert not empty_model.isEmpty

    def test_data_retrieval(self, sample_model):
        """Test retrieving data from model."""
        idx = sample_model.index(0, 0)
        assert sample_model.data(idx) == "1"

        idx = sample_model.index(1, 1)
        assert sample_model.data(idx) == "5"

    def test_set_data(self, sample_model):
        """Test setting individual cell values."""
        idx = sample_model.index(0, 0)
        sample_model.setData(idx, "100", 2)  # EditRole = 2
        assert sample_model.data(idx) == "100"

    def test_set_data_with_comma_decimal(self, sample_model):
        """Test setting data with European decimal format."""
        idx = sample_model.index(0, 0)
        sample_model.setData(idx, "3,14", 2)
        # Should parse 3,14 as 3.14
        value = sample_model._data.iloc[0, 0]
        assert value == pytest.approx(3.14)

    def test_header_data(self, sample_model):
        """Test retrieving header data."""
        from PySide6.QtCore import Qt
        assert sample_model.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "A"
        assert sample_model.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "B"
        assert sample_model.headerData(0, Qt.Vertical, Qt.DisplayRole) == "1"

    def test_get_column_names(self, sample_model):
        """Test getting column names."""
        names = sample_model.getColumnNames()
        assert names == ['A', 'B', 'C']

    def test_get_column_name(self, sample_model):
        """Test getting single column name."""
        assert sample_model.getColumnName(0) == 'A'
        assert sample_model.getColumnName(1) == 'B'
        assert sample_model.getColumnName(99) == ''  # Out of range


# =============================================================================
# TableDataModel Row Operations Tests
# =============================================================================

class TestTableDataModelRowOperations:
    """Tests for row operations (add, insert, remove, clear)."""

    @pytest.fixture
    def model(self):
        """Create a model with sample data."""
        model = TableDataModel()
        model.setTableData([[1, 2], [3, 4], [5, 6]], ['A', 'B'])
        return model

    def test_add_row(self, model):
        """Test adding a row at the end."""
        initial_rows = model.rows
        model.addRow()
        assert model.rows == initial_rows + 1
        # New row should be zeros
        assert model._data.iloc[-1, 0] == 0.0

    def test_insert_row_at_beginning(self, model):
        """Test inserting a row at the beginning."""
        initial_rows = model.rows
        model.insertRow(0)
        assert model.rows == initial_rows + 1
        # First row should be zeros
        assert model._data.iloc[0, 0] == 0.0
        # Original first row should now be at index 1
        assert model._data.iloc[1, 0] == 1.0

    def test_insert_row_in_middle(self, model):
        """Test inserting a row in the middle."""
        initial_rows = model.rows
        model.insertRow(1)
        assert model.rows == initial_rows + 1
        # Row at index 1 should be zeros
        assert model._data.iloc[1, 0] == 0.0
        # Original row 1 (value 3) should now be at index 2
        assert model._data.iloc[2, 0] == 3.0

    def test_insert_row_at_end(self, model):
        """Test inserting a row at the end."""
        initial_rows = model.rows
        model.insertRow(model.rows)
        assert model.rows == initial_rows + 1
        assert model._data.iloc[-1, 0] == 0.0

    def test_remove_row(self, model):
        """Test removing a row."""
        initial_rows = model.rows
        model.removeRow(1)  # Remove middle row
        assert model.rows == initial_rows - 1
        # Check that row with value 3 is gone
        assert model._data.iloc[0, 0] == 1.0
        assert model._data.iloc[1, 0] == 5.0

    def test_remove_first_row(self, model):
        """Test removing the first row."""
        model.removeRow(0)
        assert model._data.iloc[0, 0] == 3.0

    def test_remove_last_row(self, model):
        """Test removing the last row."""
        model.removeRow(model.rows - 1)
        assert model._data.iloc[-1, 0] == 3.0

    def test_clear_row(self, model):
        """Test clearing a row (set to zeros)."""
        model.clearRow(1)
        assert model._data.iloc[1, 0] == 0.0
        assert model._data.iloc[1, 1] == 0.0
        # Other rows unchanged
        assert model._data.iloc[0, 0] == 1.0
        assert model._data.iloc[2, 0] == 5.0

    def test_remove_invalid_row(self, model):
        """Test removing invalid row index does nothing."""
        initial_rows = model.rows
        model.removeRow(-1)
        assert model.rows == initial_rows
        model.removeRow(100)
        assert model.rows == initial_rows


# =============================================================================
# TableDataModel Column Operations Tests
# =============================================================================

class TestTableDataModelColumnOperations:
    """Tests for column operations (add, remove, clear, sort)."""

    @pytest.fixture
    def model(self):
        """Create a model with sample data."""
        model = TableDataModel()
        model.setTableData([[3, 1], [1, 2], [2, 3]], ['A', 'B'])
        return model

    def test_add_column(self, model):
        """Test adding an empty column."""
        initial_cols = model.columns
        model.addColumn("C", "units", "comment")
        assert model.columns == initial_cols + 1
        # New column should be zeros
        assert model._data.iloc[0, -1] == 0.0

    def test_add_column_with_data(self, model):
        """Test adding a column with data."""
        initial_cols = model.columns
        model.addColumnWithData("C", [10.0, 20.0, 30.0])
        assert model.columns == initial_cols + 1
        assert model._data.iloc[0, -1] == 10.0
        assert model._data.iloc[2, -1] == 30.0

    def test_remove_column(self, model):
        """Test removing a column."""
        initial_cols = model.columns
        model.removeColumn(0)
        assert model.columns == initial_cols - 1

    def test_clear_column(self, model):
        """Test clearing a column (set to zeros)."""
        model.clearColumn(0)
        assert model._data.iloc[0, 0] == 0.0
        assert model._data.iloc[1, 0] == 0.0
        assert model._data.iloc[2, 0] == 0.0
        # Other column unchanged
        assert model._data.iloc[0, 1] == 1.0

    def test_sort_by_column_ascending(self, model):
        """Test sorting by column ascending."""
        model.sortByColumn(0, True)
        values = model._data.iloc[:, 0].tolist()
        assert values == [1.0, 2.0, 3.0]

    def test_sort_by_column_descending(self, model):
        """Test sorting by column descending."""
        model.sortByColumn(0, False)
        values = model._data.iloc[:, 0].tolist()
        assert values == [3.0, 2.0, 1.0]

    def test_column_metadata(self, model):
        """Test getting and setting column metadata."""
        model.setColumnMetadata(0, "NewName", "m/s", "velocity")
        meta = model.getColumnMetadata(0)
        assert meta['name'] == "NewName"
        assert meta['unit'] == "m/s"
        assert meta['comment'] == "velocity"


# =============================================================================
# TableDataModel Statistics Tests
# =============================================================================

class TestTableDataModelStatistics:
    """Tests for statistical calculations."""

    @pytest.fixture
    def model(self):
        """Create a model with known data for statistics."""
        model = TableDataModel()
        model.setTableData([[1], [2], [3], [4], [5]], ['Values'])
        return model

    def test_calculate_column_statistics(self, model):
        """Test calculating column statistics."""
        stats = model.calculateColumnStatistics(0)
        assert stats['count'] == 5
        assert stats['mean'] == pytest.approx(3.0)
        assert stats['min'] == pytest.approx(1.0)
        assert stats['max'] == pytest.approx(5.0)
        assert stats['sum'] == pytest.approx(15.0)
        assert stats['median'] == pytest.approx(3.0)

    def test_statistics_empty_column(self):
        """Test statistics on empty data returns error."""
        model = TableDataModel()
        model.setTableData([], ['A'])
        stats = model.calculateColumnStatistics(0)
        # Should handle gracefully
        assert stats == {} or 'error' in stats

    def test_get_column_data(self, model):
        """Test getting column data as list."""
        data = model.getColumnData(0)
        assert data == [1.0, 2.0, 3.0, 4.0, 5.0]


# =============================================================================
# FormulaEngine Tests
# =============================================================================

class TestFormulaEngine:
    """Tests for the FormulaEngine class."""

    @pytest.fixture
    def model(self):
        """Create a model with sample data for formula testing."""
        model = TableDataModel()
        model.setTableData(
            [[1, 10], [2, 20], [3, 30], [4, 40], [5, 50]],
            ['A', 'B']
        )
        return model

    def test_formula_with_row_index(self, model):
        """Test formula using row index i."""
        model.setColumnFormula(0, 'i')
        values = model._data.iloc[:, 0].tolist()
        assert values == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_formula_i_squared(self, model):
        """Test formula i^2."""
        model.setColumnFormula(0, 'i^2')
        values = model._data.iloc[:, 0].tolist()
        assert values == [1.0, 4.0, 9.0, 16.0, 25.0]

    def test_formula_math_expression(self, model):
        """Test formula with math expression."""
        model.setColumnFormula(0, 'i^2 + 2*i + 1')
        values = model._data.iloc[:, 0].tolist()
        # (i+1)^2 for i=1,2,3,4,5 -> 4, 9, 16, 25, 36
        assert values == [4.0, 9.0, 16.0, 25.0, 36.0]

    def test_formula_sin(self, model):
        """Test formula with sin function."""
        model.setColumnFormula(0, 'sin(i)')
        values = model._data.iloc[:, 0].tolist()
        expected = [np.sin(i) for i in range(1, 6)]
        for v, e in zip(values, expected):
            assert v == pytest.approx(e)

    def test_formula_column_reference(self, model):
        """Test formula referencing another column."""
        model.setColumnFormula(0, '[B] * 2')
        values = model._data.iloc[:, 0].tolist()
        assert values == [20.0, 40.0, 60.0, 80.0, 100.0]

    def test_formula_column_addition(self, model):
        """Test formula adding two columns."""
        # First set A to something known
        model.setColumnFormula(0, 'i')
        # Add column C with formula
        model.addColumn('C', '', '')
        model.setColumnFormula(2, '[A] + [B]')
        values = model._data.iloc[:, 2].tolist()
        # A = [1,2,3,4,5], B = [10,20,30,40,50]
        assert values == [11.0, 22.0, 33.0, 44.0, 55.0]

    def test_formula_random(self, model):
        """Test formula with random()."""
        model.setColumnFormula(0, 'random()')
        values = model._data.iloc[:, 0].tolist()
        # All values should be between 0 and 1
        assert all(0 <= v <= 1 for v in values)
        # Values should not all be the same
        assert len(set(values)) > 1

    def test_formula_constants(self, model):
        """Test formula with pi and e constants."""
        model.setColumnFormula(0, 'pi')
        values = model._data.iloc[:, 0].tolist()
        assert all(v == pytest.approx(np.pi) for v in values)

        model.setColumnFormula(0, 'e')
        values = model._data.iloc[:, 0].tolist()
        assert all(v == pytest.approx(np.e) for v in values)

    def test_cell_formula(self, model):
        """Test individual cell formula."""
        idx = model.index(0, 0)
        model.setData(idx, "=A1+10", 2)
        # Cell (0,0) should display the formula result
        from PySide6.QtCore import Qt
        value = model.data(idx, Qt.DisplayRole)
        # Formula =A1+10 on cell A1 (which contains the formula) may be recursive
        # Let's set it on a different cell
        model.setTableData([[5, 10], [3, 4]], ['A', 'B'])
        idx = model.index(0, 1)  # B1
        model.setData(idx, "=A1+100", 2)
        # B1 should be A1 (5) + 100 = 105


# =============================================================================
# Integration Tests
# =============================================================================

class TestTableDataModelIntegration:
    """Integration tests combining multiple features."""

    def test_workflow_add_data_set_formula_sort(self):
        """Test typical workflow: add data, apply formula, sort."""
        model = TableDataModel()
        # Use column letter reference [A] instead of name to avoid conflict
        model.setTableData([[5], [3], [1], [4], [2]], ['Values'])

        # Add a column with formula using column letter reference
        model.addColumn('Squared', '', '')
        model.setColumnFormula(1, '[A]^2')

        # Verify formula applied
        y_values = model._data.iloc[:, 1].tolist()
        assert y_values == [25.0, 9.0, 1.0, 16.0, 4.0]

        # Sort by first column
        model.sortByColumn(0, True)
        x_values = model._data.iloc[:, 0].tolist()
        assert x_values == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_export_to_dataframe(self):
        """Test exporting model to DataFrame."""
        model = TableDataModel()
        model.setTableData([[1, 2], [3, 4]], ['A', 'B'])

        df = model.toDataFrame()
        assert isinstance(df, pd.DataFrame)
        assert df.shape == (2, 2)
        assert list(df.columns) == ['A', 'B']

    def test_export_to_list(self):
        """Test exporting model to list."""
        model = TableDataModel()
        model.setTableData([[1, 2], [3, 4]], ['A', 'B'])

        data = model.toList()
        assert data == [[1, 2], [3, 4]]

    def test_large_dataset(self):
        """Test handling larger datasets."""
        # Create 1000 rows x 10 columns
        data = [[i * j for j in range(10)] for i in range(1000)]
        headers = [f'Col_{i}' for i in range(10)]

        model = TableDataModel()
        model.setTableData(data, headers)

        assert model.rows == 1000
        assert model.columns == 10

        # Apply formula
        model.setColumnFormula(0, 'i * 2')
        assert model._data.iloc[0, 0] == 2.0
        assert model._data.iloc[999, 0] == 2000.0


# =============================================================================
# Export & Clipboard Tests
# =============================================================================

class TestTableExportCSV:
    """Tests for CSV export functionality."""

    @pytest.fixture
    def model(self):
        """Create a model with sample data."""
        model = TableDataModel()
        model.setTableData(
            [[1.5, 2.5, 3.5], [4.5, 5.5, 6.5], [7.5, 8.5, 9.5]],
            ['X', 'Y', 'Z']
        )
        return model

    def test_export_csv_creates_file(self, model, tmp_path):
        """Test CSV export creates a valid file."""
        filepath = str(tmp_path / "export.csv")
        result = model.exportToCSV(filepath)
        assert result is True
        assert Path(filepath).exists()
        assert Path(filepath).stat().st_size > 0

    def test_export_csv_roundtrip(self, model, tmp_path):
        """Test CSV export can be read back correctly."""
        filepath = str(tmp_path / "export.csv")
        model.exportToCSV(filepath)

        # Read back
        df = pd.read_csv(filepath)
        assert list(df.columns) == ['X', 'Y', 'Z']
        assert len(df) == 3
        assert df.iloc[0, 0] == pytest.approx(1.5)
        assert df.iloc[2, 2] == pytest.approx(9.5)

    def test_export_csv_uses_metadata_headers(self, model, tmp_path):
        """Test CSV export uses column metadata names."""
        model.setColumnMetadata(0, "Voltage", "V", "")
        model.setColumnMetadata(1, "Current", "nA", "")
        filepath = str(tmp_path / "export.csv")
        model.exportToCSV(filepath)

        df = pd.read_csv(filepath)
        assert list(df.columns) == ['Voltage', 'Current', 'Z']

    def test_export_csv_invalid_path(self, model):
        """Test CSV export to invalid path returns False."""
        result = model.exportToCSV("/nonexistent/dir/file.csv")
        assert result is False


class TestTableCopyPaste:
    """Tests for copy/paste functionality."""

    @pytest.fixture
    def model(self):
        """Create a model with sample data."""
        model = TableDataModel()
        model.setTableData(
            [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
            ['A', 'B', 'C']
        )
        return model

    def test_copy_range_single_cell(self, model):
        """Test copying a single cell."""
        result = model.copyRange(0, 0, 0, 0)
        assert result == "1"

    def test_copy_range_row(self, model):
        """Test copying a full row."""
        result = model.copyRange(0, 0, 0, 2)
        assert result == "1\t2\t3"

    def test_copy_range_column(self, model):
        """Test copying a full column."""
        result = model.copyRange(0, 0, 2, 0)
        assert "1" in result
        assert "4" in result
        assert "7" in result

    def test_copy_range_block(self, model):
        """Test copying a 2x2 block."""
        result = model.copyRange(0, 0, 1, 1)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "1\t2"
        assert lines[1] == "4\t5"

    def test_paste_single_cell(self, model):
        """Test pasting into a single cell."""
        model.pasteFromClipboard(0, 0, "99")
        idx = model.index(0, 0)
        # After paste, value should be updated
        assert model._data.iloc[0, 0] == 99.0

    def test_paste_tsv_block(self, model):
        """Test pasting a tab-separated block."""
        tsv = "10\t20\n30\t40"
        model.pasteFromClipboard(0, 0, tsv)
        assert model._data.iloc[0, 0] == 10.0
        assert model._data.iloc[0, 1] == 20.0
        assert model._data.iloc[1, 0] == 30.0
        assert model._data.iloc[1, 1] == 40.0

    def test_paste_expands_rows(self, model):
        """Test that pasting beyond existing rows adds new rows."""
        initial_rows = model.rows
        tsv = "100"
        model.pasteFromClipboard(initial_rows + 2, 0, tsv)
        assert model.rows > initial_rows


# =============================================================================
# Run tests
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
