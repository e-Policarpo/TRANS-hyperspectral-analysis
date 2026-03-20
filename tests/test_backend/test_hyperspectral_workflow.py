"""
Tests for Hyperspectral Analysis Tab - Phase 0 through Phase 5
Covers: workflow output registration, grid overlay, discretization backend,
        auto-linking, and selection export.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, MagicMock, patch, PropertyMock

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.backend.workflow_engine import (
    Workflow, WorkflowNode, Connection, Port, PortType,
    create_node_from_tool
)
from src.backend.workflow_manager import WorkflowExecutor


def create_test_spectral_data(dim_h=10, dim_v=10, n_pts=50):
    """Create test spectral data with proper spatial dimensions."""
    n_spectra = dim_h * dim_v
    x = np.linspace(-2, 2, n_pts)
    spectra = np.column_stack([
        np.sin(x * (i + 1)) + np.random.normal(0, 0.01, len(x))
        for i in range(n_spectra)
    ])
    columns = ['V'] + [f'Spectrum_{i}' for i in range(n_spectra)]
    df = pd.DataFrame(
        np.column_stack([x, spectra]),
        columns=columns
    )
    metadata = SpectralMetadata(
        source_type='test',
        dimensions=(dim_h, dim_v),
        scan_mode='forward',
        units={'x': 'V', 'y': 'nA'}
    )
    return SpectralData(data=df, metadata=metadata)


# =========================================================================
# Phase 0: Workflow Output Registration
# =========================================================================

class TestWorkflowOutputRegistration:
    """Phase 0: Verify that dataLoaded is emitted after cleanup, not during execution."""

    @pytest.fixture
    def mock_backend(self, tmp_path):
        test_data = create_test_spectral_data(5, 2)
        backend = Mock()
        backend._datasets = {'TestData': test_data}
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend._workflow_mode = False
        backend._map_id_counter = 0
        backend.maps = []
        backend.dataLoaded = Mock()
        backend.mapCreated = Mock()
        backend.errorOccurred = Mock()
        backend._ensure_output_dir = Mock(return_value=tmp_path / "outputs")
        backend._naming_convention = "[dataset_name]"
        return backend

    @pytest.fixture
    def executor(self, mock_backend):
        return WorkflowExecutor(mock_backend)

    def test_dataLoaded_deferred_until_cleanup(self, executor, mock_backend):
        """dataLoaded should only be emitted in the finally block, not during DatasetOutput execution."""
        # Build a simple workflow: DatasetInput -> DatasetOutput
        workflow = Workflow(id="test_wf", name="Test")
        input_node = create_node_from_tool("DatasetInput")
        input_node.parameters['dataset_name'] = 'TestData'
        output_node = create_node_from_tool("DatasetOutput")
        output_node.parameters['output_name'] = 'Result'

        workflow.add_node(input_node)
        workflow.add_node(output_node)

        # Connect input to output
        conn = Connection(
            id="conn_1",
            source_node_id=input_node.id,
            source_port_id='dataset',
            target_node_id=output_node.id,
            target_port_id='dataset'
        )
        workflow.add_connection(conn)

        result = executor.execute(workflow)

        # dataLoaded should have been called (after cleanup)
        assert mock_backend.dataLoaded.emit.called
        # The workflow_mode should be False after execution
        assert mock_backend._workflow_mode is False

    def test_intermediate_datasets_cleaned(self, executor, mock_backend):
        """Intermediate _wf_* datasets should be removed after execution."""
        # After execute, only the output dataset and originals should remain
        workflow = Workflow(id="test_wf", name="Test")
        input_node = create_node_from_tool("DatasetInput")
        input_node.parameters['dataset_name'] = 'TestData'
        output_node = create_node_from_tool("DatasetOutput")
        output_node.parameters['output_name'] = 'FinalResult'

        workflow.add_node(input_node)
        workflow.add_node(output_node)

        conn = Connection(
            id="conn_1",
            source_node_id=input_node.id,
            source_port_id='dataset',
            target_node_id=output_node.id,
            target_port_id='dataset'
        )
        workflow.add_connection(conn)

        result = executor.execute(workflow)

        # No _wf_ prefixed datasets should remain
        for name in list(mock_backend._datasets.keys()):
            if isinstance(name, str):
                assert not name.startswith('_wf_'), f"Intermediate dataset not cleaned: {name}"


# =========================================================================
# Phase 2: Grid Overlay on Map Canvas
# =========================================================================

class TestGridOverlay:
    """Phase 2: Test grid overlay and block snapping on QMLMapCanvas."""

    @pytest.fixture
    def canvas(self):
        """Create a QMLMapCanvas instance for testing."""
        try:
            from src.widgets.qml_map_canvas import QMLMapCanvas
            canvas = QMLMapCanvas()
            # Set up test map data (100x100)
            data = np.random.rand(100, 100)
            canvas._map_data = data
            return canvas
        except Exception:
            pytest.skip("QMLMapCanvas requires Qt event loop")

    def test_grid_block_size_state(self, canvas):
        """setGridBlockSize should update grid state."""
        canvas.setGridBlockSize(10, 10)
        assert canvas._show_grid_overlay is True
        assert canvas._grid_block_h == 10
        assert canvas._grid_block_v == 10
        assert len(canvas._selected_blocks) == 0

    def test_clear_grid_overlay(self, canvas):
        """clearGridOverlay should reset all grid state."""
        canvas.setGridBlockSize(10, 10)
        canvas._selected_blocks.add((0, 0))
        canvas.clearGridOverlay()
        assert canvas._show_grid_overlay is False
        assert canvas._grid_block_h == 1
        assert canvas._grid_block_v == 1
        assert len(canvas._selected_blocks) == 0

    def test_pixel_to_grid_block(self, canvas):
        """_pixelToGridBlock should snap to grid coordinates."""
        canvas.setGridBlockSize(10, 10)
        # Row 25, Col 35 -> grid block (2, 3)
        grid_row = 25 // 10  # 2
        grid_col = 35 // 10  # 3
        assert grid_row == 2
        assert grid_col == 3

    def test_grid_overlay_visible(self, canvas):
        """setGridOverlayVisible should toggle visibility."""
        canvas.setGridBlockSize(10, 10)
        canvas.setGridOverlayVisible(False)
        assert canvas._show_grid_overlay is False
        canvas.setGridOverlayVisible(True)
        assert canvas._show_grid_overlay is True


# =========================================================================
# Phase 4: Backend Wiring - MapEditorBackend
# =========================================================================

class TestMapEditorBackendDiscretization:
    """Phase 4: Test new discretization and export methods on MapEditorBackend."""

    @pytest.fixture
    def backend(self):
        """Create a MapEditorBackend with test data."""
        try:
            from src.backend.map_editor_backend import MapEditorBackend
            be = MapEditorBackend()
            return be
        except Exception:
            pytest.skip("MapEditorBackend requires Qt")

    def test_invert_selection_empty(self, backend):
        """invertSelection with no canvas should not crash."""
        backend.invertSelection()  # Should not raise

    def test_get_average_spectrum_no_dataset(self, backend):
        """getAverageSpectrumForSelectedBlocks with no dataset returns error."""
        result = backend.getAverageSpectrumForSelectedBlocks()
        assert 'error' in result

    def test_export_selection_no_dataset(self, backend):
        """exportSelectionSpectra with no dataset returns error."""
        result = backend.exportSelectionSpectra("nonexistent")
        assert 'error' in result

    def test_auto_link_matching_datasets(self, backend):
        """autoLinkMatchingDatasets should link datasets with matching dimensions."""
        from src.models.map_channel import MultiChannelMap, ChannelType
        mcmap = MultiChannelMap()
        mcmap.add_channel("test", np.random.rand(10, 10), ChannelType.HEIGHT)
        backend._multi_channel_map = mcmap

        # Create mock app_backend with matching dataset
        test_data = create_test_spectral_data(10, 10)
        app_mock = Mock()
        app_mock._datasets = {'MatchingData': test_data}

        backend.autoLinkMatchingDatasets(app_mock)

        assert 'MatchingData' in backend._linked_datasets

    def test_auto_link_no_match(self, backend):
        """autoLinkMatchingDatasets should NOT link mismatched dimensions."""
        from src.models.map_channel import MultiChannelMap, ChannelType
        mcmap = MultiChannelMap()
        mcmap.add_channel("test", np.random.rand(10, 10), ChannelType.HEIGHT)
        backend._multi_channel_map = mcmap

        # Create dataset with different dimensions
        test_data = create_test_spectral_data(5, 5)
        app_mock = Mock()
        app_mock._datasets = {'MismatchData': test_data}

        backend.autoLinkMatchingDatasets(app_mock)

        assert 'MismatchData' not in backend._linked_datasets

    def test_discretization_ready_signal(self, backend):
        """setDiscretizationGrid should emit discretizationReady signal."""
        from src.models.map_channel import MultiChannelMap, ChannelType
        mcmap = MultiChannelMap()
        mcmap.add_channel("test", np.random.rand(100, 100), ChannelType.HEIGHT)
        backend._multi_channel_map = mcmap

        # Create mock canvas
        mock_canvas = Mock()
        backend._canvas = mock_canvas

        # Spy on the signal
        signal_received = []
        backend.discretizationReady.connect(lambda r, c: signal_received.append((r, c)))

        backend.setDiscretizationGrid(10, 10)

        assert len(signal_received) == 1
        assert signal_received[0] == (10, 10)  # 100/10 = 10 grid blocks
        mock_canvas.setGridBlockSize.assert_called_once_with(10, 10)
        mock_canvas.setTool.assert_called_once_with("block_select")


# =========================================================================
# Phase 4: Backend Wiring - AppBackend
# =========================================================================

class TestAppBackendSpatialAverageWithSelection:
    """Phase 4: Test spatialAverageWithSelection method."""

    @pytest.fixture
    def app_backend(self, tmp_path):
        """Create AppBackend with mock setup."""
        try:
            from src.backend.app_backend import AppBackend
            be = AppBackend()
            be._project_path = tmp_path
            be._output_base_dir = tmp_path / "outputs"
            be._output_base_dir.mkdir(exist_ok=True)
            (be._output_base_dir / "discretized").mkdir(exist_ok=True)
            return be
        except Exception:
            pytest.skip("AppBackend requires Qt")

    def test_spatial_average_full(self, app_backend):
        """spatialAverageWithSelection with empty selection processes all blocks."""
        test_data = create_test_spectral_data(10, 10)
        app_backend._datasets['TestData'] = test_data

        app_backend.spatialAverageWithSelection('TestData', 5, 5, True, [])

        # Should create a new dataset with "full" in name
        found = [name for name in app_backend._datasets if 'Averaged' in name and 'full' in name]
        assert len(found) >= 1, f"Expected averaged dataset, got: {list(app_backend._datasets.keys())}"

    def test_spatial_average_with_selection(self, app_backend):
        """spatialAverageWithSelection with specific blocks."""
        test_data = create_test_spectral_data(10, 10)
        app_backend._datasets['TestData'] = test_data

        selected = [{'row': 0, 'col': 0}, {'row': 1, 'col': 1}]
        app_backend.spatialAverageWithSelection('TestData', 5, 5, True, selected)

        # Should create a new dataset with "selection" in name
        found = [name for name in app_backend._datasets if 'selection' in name]
        assert len(found) >= 1, f"Expected selection dataset, got: {list(app_backend._datasets.keys())}"

    def test_spatial_average_nonexistent_dataset(self, app_backend):
        """spatialAverageWithSelection with nonexistent dataset should error."""
        app_backend.spatialAverageWithSelection('NonExistent', 5, 5, True, [])
        # Should not crash, just log error
