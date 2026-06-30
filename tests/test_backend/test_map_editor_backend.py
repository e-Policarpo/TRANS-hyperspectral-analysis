"""
Tests for MapEditorBackend
Target coverage: 90%
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from src.backend.map_editor_backend import MapEditorBackend
from src.models.map_channel import (
    MultiChannelMap, MapChannel, MapMetadata, ChannelMetadata, ChannelType
)
from src.models.spectral_data import SpectralData, SpectralMetadata


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def backend():
    """Create a MapEditorBackend instance"""
    return MapEditorBackend()


@pytest.fixture
def sample_map_data():
    """Create sample 2D map data"""
    return np.random.rand(50, 50) * 100


@pytest.fixture
def sample_multi_channel_map(sample_map_data):
    """Create sample MultiChannelMap"""
    mcmap = MultiChannelMap()
    mcmap.add_channel("Height", sample_map_data, ChannelType.HEIGHT, "nm")
    mcmap.add_channel("Phase", sample_map_data * 0.5, ChannelType.PHASE, "deg")
    return mcmap


@pytest.fixture
def mock_canvas():
    """Create a mock canvas object"""
    canvas = Mock()
    canvas.setMapData = Mock()
    canvas.spectralDataRequested = Mock()
    canvas.spectralDataRequested.connect = Mock()
    canvas.blockSelectionChanged = Mock()
    canvas.blockSelectionChanged.connect = Mock()
    canvas.clearBlockSelection = Mock()
    canvas.selectAllBlocks = Mock()
    canvas.getSelectedBlocks = Mock(return_value=[])
    canvas.getSelectedBlockCount = Mock(return_value=0)
    canvas.getSelectionMask = Mock(return_value=np.zeros((10, 10), dtype=bool))
    canvas.getAverageSpectrumFromSelection = Mock(return_value={})
    canvas.linkSpectralCube = Mock()
    return canvas


@pytest.fixture
def backend_with_map(backend, sample_multi_channel_map):
    """Create backend with map data"""
    backend.setMultiChannelMap(sample_multi_channel_map)
    return backend


@pytest.fixture
def tiff_file(tmp_path, sample_map_data):
    """Create a temporary TIFF file"""
    import tifffile
    tiff_path = tmp_path / "test_map.tif"
    tifffile.imwrite(str(tiff_path), sample_map_data.astype(np.float32))
    return tiff_path


@pytest.fixture
def npy_file(tmp_path, sample_map_data):
    """Create a temporary NPY file"""
    npy_path = tmp_path / "test_map.npy"
    np.save(str(npy_path), sample_map_data)
    return npy_path


# =============================================================================
# Backend Creation Tests
# =============================================================================

class TestMapEditorBackendCreation:
    """Tests for MapEditorBackend initialization"""

    def test_creation(self, backend):
        """Test backend creation"""
        assert backend._multi_channel_map is None
        assert backend._canvas is None
        assert backend._channel_names == []

    def test_initial_properties(self, backend):
        """Test initial property values"""
        assert backend.hasMapData == False
        assert backend.channelNames == []
        assert backend.activeChannelName == ""
        assert backend.mapRows == 0
        assert backend.mapCols == 0
        assert backend.hasSpectralData == False
        assert backend.spectralPoints == 0


# =============================================================================
# Property Tests
# =============================================================================

class TestMapEditorBackendProperties:
    """Tests for QML properties"""

    def test_hasMapData_true(self, backend_with_map):
        """Test hasMapData when map is loaded"""
        assert backend_with_map.hasMapData == True

    def test_hasMapData_empty_map(self, backend):
        """Test hasMapData with empty map"""
        backend._multi_channel_map = MultiChannelMap()
        assert backend.hasMapData == False

    def test_channelNames(self, backend_with_map):
        """Test channelNames property"""
        names = backend_with_map.channelNames
        assert "Height" in names
        assert "Phase" in names

    def test_activeChannelName(self, backend_with_map):
        """Test activeChannelName property"""
        assert backend_with_map.activeChannelName in ["Height", "Phase"]

    def test_mapRows(self, backend_with_map):
        """Test mapRows property"""
        assert backend_with_map.mapRows == 50

    def test_mapCols(self, backend_with_map):
        """Test mapCols property"""
        assert backend_with_map.mapCols == 50

    def test_hasSpectralData_false(self, backend_with_map):
        """Test hasSpectralData when no spectral data"""
        assert backend_with_map.hasSpectralData == False

    def test_spectralPoints_zero(self, backend_with_map):
        """Test spectralPoints when no spectral data"""
        assert backend_with_map.spectralPoints == 0


# =============================================================================
# Canvas Binding Tests
# =============================================================================

class TestCanvasBinding:
    """Tests for canvas binding"""

    def test_setCanvas(self, backend, mock_canvas):
        """Test setting canvas"""
        backend.setCanvas(mock_canvas)
        assert backend._canvas == mock_canvas
        mock_canvas.spectralDataRequested.connect.assert_called()
        mock_canvas.blockSelectionChanged.connect.assert_called()

    def test_setCanvas_none(self, backend):
        """Test setting canvas to None"""
        backend.setCanvas(None)
        assert backend._canvas is None


# =============================================================================
# Data Loading Tests
# =============================================================================

class TestDataLoading:
    """Tests for loading map data"""

    def test_loadMapFromFile_tiff(self, backend, tiff_file):
        """Test loading TIFF file"""
        backend.loadMapFromFile(str(tiff_file))
        assert backend.hasMapData == True
        assert backend.mapRows == 50
        assert backend.mapCols == 50

    def test_loadMapFromFile_tiff_with_file_prefix(self, backend, tiff_file):
        """Test loading TIFF file with file:// prefix"""
        backend.loadMapFromFile(f"file://{tiff_file}")
        assert backend.hasMapData == True

    def test_loadMapFromFile_npy(self, backend, npy_file):
        """Test loading NPY file"""
        backend.loadMapFromFile(str(npy_file))
        assert backend.hasMapData == True

    def test_loadMapFromFile_unsupported(self, backend, tmp_path):
        """Test loading unsupported file format"""
        bad_file = tmp_path / "test.xyz"
        bad_file.write_text("invalid")

        # Signal spy to check error emission
        signal_emitted = []
        backend.processingFinished.connect(lambda op, success, msg: signal_emitted.append((op, success, msg)))

        backend.loadMapFromFile(str(bad_file))
        assert len(signal_emitted) == 1
        assert signal_emitted[0][1] == False  # success = False

    def test_loadMapFromFile_multipage_tiff(self, backend, tmp_path, sample_map_data):
        """Test loading multi-page TIFF"""
        import tifffile
        # Create multi-page TIFF
        multi_data = np.stack([sample_map_data, sample_map_data * 0.5])
        tiff_path = tmp_path / "multi.tif"
        tifffile.imwrite(str(tiff_path), multi_data.astype(np.float32))

        backend.loadMapFromFile(str(tiff_path))
        assert backend.hasMapData == True
        assert len(backend.channelNames) == 2

    def test_setMultiChannelMap(self, backend, sample_multi_channel_map):
        """Test setting MultiChannelMap directly"""
        backend.setMultiChannelMap(sample_multi_channel_map)
        assert backend.hasMapData == True
        assert backend.channelNames == sample_multi_channel_map.channel_names

    def test_setMultiChannelMap_updates_canvas(self, backend, sample_multi_channel_map, mock_canvas):
        """Test setMultiChannelMap updates canvas"""
        backend.setCanvas(mock_canvas)
        backend.setMultiChannelMap(sample_multi_channel_map)
        mock_canvas.setMapData.assert_called()

    def test_setMapDataFromArray(self, backend, sample_map_data):
        """Test setting map from numpy array"""
        backend.setMapDataFromArray(sample_map_data, "TestMap")
        assert backend.hasMapData == True
        assert "TestMap" in backend.channelNames

    def test_setMapDataFromArray_updates_existing(self, backend_with_map, sample_map_data):
        """Test setMapDataFromArray with existing map"""
        initial_channels = len(backend_with_map.channelNames)
        backend_with_map.setMapDataFromArray(sample_map_data * 2, "NewChannel")
        assert len(backend_with_map.channelNames) == initial_channels + 1


# =============================================================================
# Channel Management Tests
# =============================================================================

class TestChannelManagement:
    """Tests for channel management"""

    def test_setActiveChannel(self, backend_with_map):
        """Test setting active channel"""
        backend_with_map.setActiveChannel("Phase")
        assert backend_with_map.activeChannelName == "Phase"

    def test_setActiveChannel_not_found(self, backend_with_map):
        """Test setting nonexistent channel (should not crash)"""
        backend_with_map.setActiveChannel("NonExistent")
        # Should not change active channel
        assert backend_with_map.activeChannelName in ["Height", "Phase"]

    def test_setActiveChannel_no_map(self, backend):
        """Test setting channel with no map loaded"""
        backend.setActiveChannel("Test")
        # Should not crash

    def test_setActiveChannel_updates_canvas(self, backend_with_map, mock_canvas):
        """Test setActiveChannel updates canvas"""
        backend_with_map.setCanvas(mock_canvas)
        backend_with_map.setActiveChannel("Phase")
        mock_canvas.setMapData.assert_called()

    def test_getChannelStatistics(self, backend_with_map):
        """Test getting channel statistics"""
        stats = backend_with_map.getChannelStatistics("Height")
        assert 'mean' in stats
        assert 'std' in stats
        assert 'min' in stats
        assert 'max' in stats

    def test_getChannelStatistics_not_found(self, backend_with_map):
        """Test getting statistics for nonexistent channel"""
        stats = backend_with_map.getChannelStatistics("NonExistent")
        assert stats == {}

    def test_getChannelStatistics_no_map(self, backend):
        """Test getting statistics with no map"""
        stats = backend.getChannelStatistics("Test")
        assert stats == {}

    def test_getActiveChannelStatistics(self, backend_with_map):
        """Test getting active channel statistics"""
        stats = backend_with_map.getActiveChannelStatistics()
        assert 'mean' in stats

    def test_getActiveChannelStatistics_no_map(self, backend):
        """Test getting active stats with no map"""
        stats = backend.getActiveChannelStatistics()
        assert stats == {}


# =============================================================================
# Spectral-Spatial Linking Tests
# =============================================================================

class TestSpectralSpatialLinking:
    """Tests for spectral-spatial reconstruction"""

    @pytest.fixture
    def sample_spectral_data(self, backend_with_map):
        """Create sample SpectralData for linking"""
        import pandas as pd
        # Create spectral data matching map dimensions (50x50 = 2500 spectra)
        x = np.linspace(0, 10, 100)
        n_spectra = 50 * 50
        spectra = np.random.rand(100, n_spectra)
        columns = ['V'] + [f'Spectrum_{i}' for i in range(n_spectra)]
        df = pd.DataFrame(np.column_stack([x, spectra]), columns=columns)
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(50, 50),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        return SpectralData(data=df, metadata=metadata)

    def test_linkSpectralCube(self, backend_with_map):
        """Test linking spectral cube directly"""
        cube = np.random.rand(100, 50, 50)
        x = np.linspace(0, 10, 100)

        backend_with_map.linkSpectralCube(cube, x, "Energy")

        assert backend_with_map.hasSpectralData == True
        assert backend_with_map.spectralPoints == 100

    def test_linkSpectralCube_no_map(self, backend):
        """Test linking cube without map"""
        cube = np.random.rand(100, 10, 10)
        x = np.linspace(0, 10, 100)

        backend.linkSpectralCube(cube, x, "x")
        # Should log warning but not crash

    def test_linkSpectralCube_updates_canvas(self, backend_with_map, mock_canvas):
        """Test linkSpectralCube updates canvas"""
        backend_with_map.setCanvas(mock_canvas)
        cube = np.random.rand(100, 50, 50)
        x = np.linspace(0, 10, 100)

        backend_with_map.linkSpectralCube(cube, x, "Energy")
        mock_canvas.linkSpectralCube.assert_called()

    def test_getSpectrumAt(self, backend_with_map):
        """Test getting spectrum at position"""
        cube = np.random.rand(100, 50, 50)
        x = np.linspace(0, 10, 100)
        backend_with_map.linkSpectralCube(cube, x, "Energy")

        result = backend_with_map.getSpectrumAt(25, 25)
        assert 'x' in result
        assert 'y' in result
        assert len(result['x']) == 100
        assert len(result['y']) == 100

    def test_getSpectrumAt_no_spectral(self, backend_with_map):
        """Test getSpectrumAt without spectral data"""
        result = backend_with_map.getSpectrumAt(0, 0)
        assert 'error' in result

    def test_getSpectrumAt_out_of_bounds(self, backend_with_map):
        """Test getSpectrumAt with out of bounds position"""
        cube = np.random.rand(100, 50, 50)
        x = np.linspace(0, 10, 100)
        backend_with_map.linkSpectralCube(cube, x, "Energy")

        result = backend_with_map.getSpectrumAt(100, 100)
        assert 'error' in result

    def test_getAverageSpectrumFromSelection(self, backend, mock_canvas):
        """Test getting average spectrum from selection"""
        backend.setCanvas(mock_canvas)
        mock_canvas.getAverageSpectrumFromSelection.return_value = {'x': [1, 2, 3], 'y': [4, 5, 6]}

        result = backend.getAverageSpectrumFromSelection()
        assert result == {'x': [1, 2, 3], 'y': [4, 5, 6]}

    def test_getAverageSpectrumFromSelection_no_canvas(self, backend):
        """Test getAverageSpectrumFromSelection without canvas"""
        result = backend.getAverageSpectrumFromSelection()
        assert 'error' in result


# =============================================================================
# Block Selection Tests
# =============================================================================

class TestBlockSelection:
    """Tests for block selection operations"""

    def test_clearSelection(self, backend, mock_canvas):
        """Test clearing selection"""
        backend.setCanvas(mock_canvas)
        backend.clearSelection()
        mock_canvas.clearBlockSelection.assert_called_once()

    def test_clearSelection_no_canvas(self, backend):
        """Test clearSelection without canvas"""
        backend.clearSelection()  # Should not crash

    def test_selectAllBlocks(self, backend, mock_canvas):
        """Test selecting all blocks"""
        backend.setCanvas(mock_canvas)
        backend.selectAllBlocks()
        mock_canvas.selectAllBlocks.assert_called_once()

    def test_selectAllBlocks_no_canvas(self, backend):
        """Test selectAllBlocks without canvas"""
        backend.selectAllBlocks()  # Should not crash

    def test_getSelectedBlocks(self, backend, mock_canvas):
        """Test getting selected blocks"""
        backend.setCanvas(mock_canvas)
        mock_canvas.getSelectedBlocks.return_value = [{'row': 0, 'col': 0}]

        result = backend.getSelectedBlocks()
        assert result == [{'row': 0, 'col': 0}]

    def test_getSelectedBlocks_no_canvas(self, backend):
        """Test getSelectedBlocks without canvas"""
        result = backend.getSelectedBlocks()
        assert result == []

    def test_getSelectedBlockCount(self, backend, mock_canvas):
        """Test getting selected block count"""
        backend.setCanvas(mock_canvas)
        mock_canvas.getSelectedBlockCount.return_value = 5

        count = backend.getSelectedBlockCount()
        assert count == 5

    def test_getSelectedBlockCount_no_canvas(self, backend):
        """Test getSelectedBlockCount without canvas"""
        count = backend.getSelectedBlockCount()
        assert count == 0

    def test_getSelectionMask(self, backend, mock_canvas):
        """Test getting selection mask"""
        expected_mask = np.ones((10, 10), dtype=bool)
        mock_canvas.getSelectionMask.return_value = expected_mask

        backend.setCanvas(mock_canvas)
        mask = backend.getSelectionMask()
        np.testing.assert_array_equal(mask, expected_mask)

    def test_getSelectionMask_no_canvas(self, backend):
        """Test getSelectionMask without canvas"""
        mask = backend.getSelectionMask()
        assert len(mask) == 0


# =============================================================================
# Processing Operations Tests
# =============================================================================

class TestProcessingOperations:
    """Tests for map processing operations"""

    def test_applyProcessing_gaussian_filter(self, backend_with_map):
        """Test applying Gaussian filter"""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )

        backend_with_map.applyProcessing("gaussian_filter", {"sigma": 2.0})

        assert len(signal_emitted) == 1
        assert signal_emitted[0][0] == "gaussian_filter"
        assert signal_emitted[0][1] == True  # success

    def test_applyProcessing_median_filter(self, backend_with_map):
        """Test applying median filter"""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )

        backend_with_map.applyProcessing("median_filter", {"size": 3})

        assert len(signal_emitted) == 1
        assert signal_emitted[0][1] == True

    def test_applyProcessing_plane_level(self, backend_with_map):
        """Test applying plane leveling"""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )

        backend_with_map.applyProcessing("plane_level", {})

        assert len(signal_emitted) == 1
        assert signal_emitted[0][1] == True

    def test_applyProcessing_row_align(self, backend_with_map):
        """Test applying row alignment"""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )

        backend_with_map.applyProcessing("row_align", {})

        assert len(signal_emitted) == 1
        assert signal_emitted[0][1] == True

    def test_applyProcessing_normalize(self, backend_with_map):
        """Test applying normalization"""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )

        backend_with_map.applyProcessing("normalize", {})

        assert len(signal_emitted) == 1
        assert signal_emitted[0][1] == True

        # Check data is normalized
        active = backend_with_map._multi_channel_map.active_channel
        assert active.data.min() >= 0.0
        assert active.data.max() <= 1.0

    def test_applyProcessing_unknown_operation(self, backend_with_map):
        """Test applying unknown operation"""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )

        backend_with_map.applyProcessing("unknown_op", {})

        assert len(signal_emitted) == 1
        assert signal_emitted[0][1] == False  # failure

    def test_applyProcessing_no_map(self, backend):
        """Test applying processing without map"""
        signal_emitted = []
        backend.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )

        backend.applyProcessing("gaussian_filter", {"sigma": 1.0})

        assert len(signal_emitted) == 1
        assert signal_emitted[0][1] == False

    def test_applyProcessing_updates_canvas(self, backend_with_map, mock_canvas):
        """Test processing updates canvas"""
        backend_with_map.setCanvas(mock_canvas)
        backend_with_map.applyProcessing("normalize", {})
        mock_canvas.setMapData.assert_called()

    def test_applyProcessing_adds_history(self, backend_with_map):
        """Test processing adds to channel history"""
        backend_with_map.applyProcessing("gaussian_filter", {"sigma": 2.0})

        active = backend_with_map._multi_channel_map.active_channel
        assert len(active.history) > 0
        assert active.history[-1]['operation'] == "gaussian_filter"


# =============================================================================
# Export Tests
# =============================================================================

class TestExport:
    """Tests for export functionality"""

    def test_exportChannel_tiff(self, backend_with_map, tmp_path):
        """Test exporting channel as TIFF"""
        output_path = tmp_path / "export.tif"
        backend_with_map.exportChannel("Height", str(output_path))
        assert output_path.exists()

    def test_exportChannel_png(self, backend_with_map, tmp_path):
        """Test exporting channel as PNG - should fallback to TIFF"""
        output_path = tmp_path / "export.png"
        tiff_path = tmp_path / "export.tiff"
        backend_with_map.exportChannel("Height", str(output_path))
        # PNG format no longer supported, should save as TIFF instead
        assert tiff_path.exists() or output_path.with_suffix('.tiff').exists()

    def test_exportChannel_csv(self, backend_with_map, tmp_path):
        """Test exporting channel as CSV"""
        output_path = tmp_path / "export.csv"
        backend_with_map.exportChannel("Height", str(output_path))
        assert output_path.exists()

    def test_exportChannel_npy(self, backend_with_map, tmp_path):
        """Test exporting channel as NPY - unsupported format"""
        output_path = tmp_path / "export.npy"
        backend_with_map.exportChannel("Height", str(output_path))
        # NPY format is not supported, file should not be created
        assert not output_path.exists()

    def test_exportChannel_no_map(self, backend, tmp_path):
        """Test export without map (should not crash)"""
        output_path = tmp_path / "export.tif"
        backend.exportChannel("Test", str(output_path))
        assert not output_path.exists()

    def test_exportChannel_with_file_prefix(self, backend_with_map, tmp_path):
        """Test export with file:// prefix"""
        output_path = tmp_path / "export.tif"
        backend_with_map.exportChannel("Height", f"file://{output_path}")
        assert output_path.exists()


# =============================================================================
# Integrated Map Computation Tests
# =============================================================================

class TestIntegratedMapComputation:
    """Tests for integrated map computation"""

    @pytest.fixture
    def backend_with_spectral(self, backend_with_map):
        """Backend with spectral data linked"""
        cube = np.random.rand(100, 50, 50)
        x = np.linspace(800, 1800, 100)
        backend_with_map.linkSpectralCube(cube, x, "Wavenumber")
        return backend_with_map

    def test_computeIntegratedMap(self, backend_with_spectral):
        """Test computing integrated map"""
        result = backend_with_spectral.computeIntegratedMap("900,1000")

        assert 'success' in result
        assert result['success'] == True
        assert 'channel_name' in result

        # Check channel was added
        assert any("Integrated" in name for name in backend_with_spectral.channelNames)

    def test_computeIntegratedMap_no_spectral(self, backend_with_map):
        """Test computeIntegratedMap without spectral data"""
        result = backend_with_map.computeIntegratedMap("0,10")
        assert 'error' in result

    def test_computeIntegratedMap_invalid_range(self, backend_with_spectral):
        """Test computeIntegratedMap with invalid range string"""
        result = backend_with_spectral.computeIntegratedMap("invalid")
        assert 'error' in result


# =============================================================================
# Signal Emission Tests
# =============================================================================

class TestSignalEmission:
    """Tests for signal emission"""

    def test_mapDataChanged_signal(self, backend, sample_multi_channel_map):
        """Test mapDataChanged signal is emitted"""
        signal_emitted = []
        backend.mapDataChanged.connect(lambda: signal_emitted.append(True))

        backend.setMultiChannelMap(sample_multi_channel_map)
        assert len(signal_emitted) == 1

    def test_channelListChanged_signal(self, backend, sample_multi_channel_map):
        """Test channelListChanged signal is emitted"""
        signal_emitted = []
        backend.channelListChanged.connect(lambda: signal_emitted.append(True))

        backend.setMultiChannelMap(sample_multi_channel_map)
        assert len(signal_emitted) == 1

    def test_activeChannelChanged_signal(self, backend_with_map):
        """Test activeChannelChanged signal is emitted"""
        signal_emitted = []
        backend_with_map.activeChannelChanged.connect(lambda name: signal_emitted.append(name))

        backend_with_map.setActiveChannel("Phase")
        assert "Phase" in signal_emitted

    def test_processingStarted_signal(self, backend_with_map):
        """Test processingStarted signal is emitted"""
        signal_emitted = []
        backend_with_map.processingStarted.connect(lambda op: signal_emitted.append(op))

        backend_with_map.applyProcessing("normalize", {})
        assert "normalize" in signal_emitted

    def test_spectralDataChanged_signal(self, backend_with_map):
        """Test spectralDataChanged signal is emitted"""
        signal_emitted = []
        backend_with_map.spectralDataChanged.connect(lambda: signal_emitted.append(True))

        cube = np.random.rand(100, 50, 50)
        x = np.linspace(0, 10, 100)
        backend_with_map.linkSpectralCube(cube, x, "x")

        assert len(signal_emitted) == 1



# =============================================================================
# State Persistence Tests
# =============================================================================

class TestStatePersistence:
    """Tests for state persistence (getState/restoreState)"""

    def test_getState_empty_backend(self, backend):
        """Test getState on empty backend returns valid dict"""
        state = backend.getState()

        assert isinstance(state, dict)
        assert state['has_map'] is False
        assert state['map_path'] == ''
        assert state['active_channel'] == ''
        assert state['linked_dataset_names'] == []
        assert state['active_dataset'] == ''

    def test_getState_with_map(self, backend_with_map):
        """Test getState with loaded map"""
        state = backend_with_map.getState()

        assert state['has_map'] is True
        assert state['active_channel'] == 'Height'  # First channel

    def test_getState_with_linked_datasets(self, backend_with_map, sample_spectral_data):
        """Test getState includes linked dataset names"""
        backend_with_map.linkDataset("TestDataset", sample_spectral_data)
        state = backend_with_map.getState()

        assert 'TestDataset' in state['linked_dataset_names']
        assert state['active_dataset'] == 'TestDataset'

    def test_restoreState_empty(self, backend):
        """Test restoreState with empty/None state"""
        # Should not raise
        backend.restoreState(None)
        backend.restoreState({})

    def test_restoreState_active_channel(self, backend_with_map):
        """Test restoreState restores active channel"""
        # Set to Phase
        backend_with_map.setActiveChannel("Phase")

        # Get state
        state = backend_with_map.getState()
        assert state['active_channel'] == 'Phase'

        # Reset to Height
        backend_with_map.setActiveChannel("Height")
        assert backend_with_map.activeChannelName == 'Height'

        # Restore state
        backend_with_map.restoreState(state)
        assert backend_with_map.activeChannelName == 'Phase'

    def test_restoreState_active_dataset(self, backend_with_map, sample_spectral_data):
        """Test restoreState restores active dataset selection"""
        # Link two datasets
        backend_with_map.linkDataset("Dataset1", sample_spectral_data)
        backend_with_map.linkDataset("Dataset2", sample_spectral_data)

        # Set active to Dataset2
        backend_with_map.setActiveDataset("Dataset2")
        state = backend_with_map.getState()
        assert state['active_dataset'] == 'Dataset2'

        # Change active
        backend_with_map.setActiveDataset("Dataset1")
        assert backend_with_map.activeDataset == 'Dataset1'

        # Restore
        backend_with_map.restoreState(state)
        assert backend_with_map.activeDataset == 'Dataset2'


# =============================================================================
# STS marker (dot) click → plot average spectrum
# =============================================================================

class TestStsMarkerClick:
    """Clicking a 'where spectra were taken' dot plots that point's average."""

    @staticmethod
    def _map_with_locations():
        mcm = MultiChannelMap()
        mcm.add_channel("Z", np.zeros((10, 10)), ChannelType.HEIGHT, "m")
        V = [-1.0, 0.0, 1.0]
        mcm.metadata.extra = {'sts_locations': [
            {'point_index': 3, 'px': [5, 5],
             'avg_spectrum': {'V': V, 'y': [0.1, 0.2, 0.3]}},
            {'point_index': 7, 'px': [8, 2],
             'avg_spectrum': {'V': V, 'y': [1.0, 2.0, 3.0]}},
        ]}
        return mcm, V

    def test_clicking_dot_plots_its_average_spectrum(self, backend):
        mcm, V = self._map_with_locations()
        backend._multi_channel_map = mcm
        captured = {}
        backend.openPlotWindowRequested.connect(
            lambda name, spectra: captured.update(name=name, spectra=spectra))
        backend._on_sts_marker_clicked(1)
        assert 'name' in captured and 'Point 7' in captured['name']
        sp = captured['spectra'][0]
        assert sp['x'] == V and sp['y'] == [1.0, 2.0, 3.0]

    def test_marker_click_is_safe_without_spectrum_or_out_of_range(self, backend):
        mcm = MultiChannelMap()
        mcm.add_channel("Z", np.zeros((4, 4)), ChannelType.HEIGHT, "m")
        mcm.metadata.extra = {'sts_locations': [
            {'point_index': 1, 'px': [0, 0], 'avg_spectrum': None}]}
        backend._multi_channel_map = mcm
        fired = []
        backend.openPlotWindowRequested.connect(lambda n, s: fired.append(1))
        backend._on_sts_marker_clicked(0)    # no spectrum → no plot
        backend._on_sts_marker_clicked(99)   # out of range → safe
        backend._multi_channel_map = None
        backend._on_sts_marker_clicked(0)    # no map → safe
        assert fired == []
