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

    def test_applyProcessing_poly_level(self, backend_with_map):
        """Polynomial plane correction removes a bowed background."""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )
        chan = backend_with_map._multi_channel_map.active_channel
        rows, cols = chan.data.shape
        Y, X = np.mgrid[0:rows, 0:cols].astype(float)
        chan.data = ((X - cols / 2) / (cols / 2)) ** 2 * 500.0

        backend_with_map.applyProcessing("poly_level", {"order": 2})

        assert signal_emitted == [("poly_level", True, "")] or \
            signal_emitted[0][:2] == ("poly_level", True)
        assert np.abs(
            backend_with_map._multi_channel_map.active_channel.data
        ).max() < 1e-6, "order-2 bowing should be fully removed"

    def test_applyProcessing_poly_level_defaults_order(self, backend_with_map):
        """A missing order must not raise — it defaults to 2."""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )
        backend_with_map.applyProcessing("poly_level", {})
        assert signal_emitted[0][1] is True

    def test_applyProcessing_poly_level_accepts_float_order(self, backend_with_map):
        """QML hands numeric params through as floats; order must be cast."""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )
        backend_with_map.applyProcessing("poly_level", {"order": 3.0})
        assert signal_emitted[0][1] is True

    def test_applyProcessing_facet_level(self, backend_with_map):
        """Facet reorientation flattens the dominant facet."""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )
        chan = backend_with_map._multi_channel_map.active_channel
        rows, cols = chan.data.shape
        Y, X = np.mgrid[0:rows, 0:cols].astype(float)
        chan.data = 0.5 * X + 0.25 * Y

        backend_with_map.applyProcessing("facet_level", {})

        assert signal_emitted[0][1] is True
        assert np.ptp(
            backend_with_map._multi_channel_map.active_channel.data) < 1e-6

    def test_applyProcessing_plane_level_is_nan_aware(self, backend_with_map):
        """The old inline plane fit produced an all-NaN result when a single
        pixel was NaN; the shared implementation ignores them."""
        signal_emitted = []
        backend_with_map.processingFinished.connect(
            lambda op, success, msg: signal_emitted.append((op, success, msg))
        )
        chan = backend_with_map._multi_channel_map.active_channel
        rows, cols = chan.data.shape
        Y, X = np.mgrid[0:rows, 0:cols].astype(float)
        chan.data = 3.0 * X + 2.0 * Y + 7.0
        chan.data[0, 0] = np.nan

        backend_with_map.applyProcessing("plane_level", {})

        out = backend_with_map._multi_channel_map.active_channel.data
        assert signal_emitted[0][1] is True
        assert np.isnan(out[0, 0])
        assert np.isfinite(out[1:, 1:]).all(), "NaN must not poison the fit"
        assert np.nanmax(np.abs(out)) < 1e-9

    def test_leveling_operations_are_recorded_in_history(self, backend_with_map):
        backend_with_map.applyProcessing("facet_level", {})
        chan = backend_with_map._multi_channel_map.active_channel
        assert any(h['operation'] == "facet_level" for h in chan.history)

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
            {'point_index': 3, 'px': [5, 5], 'avg_spectra': {
                'V': V, 'Mixed': [0.1, 0.2, 0.3],
                'Forward': [0.4, 0.5, 0.6], 'Backward': [0.7, 0.8, 0.9]}},
            {'point_index': 7, 'px': [8, 2], 'avg_spectra': {
                'V': V, 'Mixed': [1.0, 2.0, 3.0],
                'Forward': [4.0, 5.0, 6.0], 'Backward': [7.0, 8.0, 9.0]}},
        ]}
        return mcm, V

    def test_clicking_dot_plots_both_sweeps_in_one_window(self, backend):
        """Forward and backward belong side by side — that comparison is why
        both are kept — so one window carries them, not one window each."""
        mcm, V = self._map_with_locations()
        backend._multi_channel_map = mcm
        by_name = {}
        backend.openPlotWindowRequested.connect(
            lambda name, spectra: by_name.__setitem__(name, spectra))
        backend._on_sts_marker_clicked(1)          # point 7

        assert "STS points" in by_name
        curves = {c['title']: c['y'] for c in by_name["STS points"]}
        assert curves["Point 7 · Forward"] == [4.0, 5.0, 6.0]
        assert curves["Point 7 · Backward"] == [7.0, 8.0, 9.0]
        # Mixed is their mean redrawn, so it is not plotted a third time.
        assert not any("Mixed" in title for title in curves)

    def test_mixed_is_plotted_when_the_directions_were_not_recorded(self, backend):
        mcm = MultiChannelMap()
        mcm.add_channel("Z", np.zeros((8, 8)), ChannelType.HEIGHT, "m")
        mcm.metadata.extra = {'sts_locations': [
            {'point_index': 2, 'px': [1, 1], 'avg_spectra': {
                'V': [-1.0, 0.0, 1.0], 'Mixed': [0.5, 0.6, 0.7],
                'Forward': None, 'Backward': None}}]}
        backend._multi_channel_map = mcm
        by_name = {}
        backend.openPlotWindowRequested.connect(
            lambda name, spectra: by_name.__setitem__(name, spectra))
        backend._on_sts_marker_clicked(0)

        curves = {c['title']: c['y'] for c in by_name["STS points"]}
        assert curves["Point 2 · Mixed"] == [0.5, 0.6, 0.7]

    def test_stm_data_also_gets_a_didv_window(self, backend):
        mcm, V = self._map_with_locations()
        mcm.metadata.extra['sts_technique'] = 'STM'
        backend._multi_channel_map = mcm
        by_name = {}
        backend.openPlotWindowRequested.connect(
            lambda name, spectra: by_name.__setitem__(name, spectra))
        backend._on_sts_marker_clicked(1)

        assert "STS points · dI/dV" in by_name
        curve = by_name["STS points · dI/dV"][0]
        assert curve['y_name'] == 'dI/dV'
        # The mean of Forward [4,5,6] and Backward [7,8,9] is [5.5, 6.5, 7.5];
        # over V = [-1, 0, 1] its derivative is a constant 1.
        np.testing.assert_allclose(curve['y'], [1.0, 1.0, 1.0])

    def test_non_stm_data_gets_no_didv_window(self, backend):
        mcm, V = self._map_with_locations()
        mcm.metadata.extra['sts_technique'] = 'AFM'
        mcm.metadata.instrument = 'Park NX7'
        backend._multi_channel_map = mcm
        by_name = {}
        backend.openPlotWindowRequested.connect(
            lambda name, spectra: by_name.__setitem__(name, spectra))
        backend._on_sts_marker_clicked(1)

        assert "STS points · dI/dV" not in by_name

    def test_an_older_project_is_recognised_by_its_instrument(self, backend):
        """Projects saved before the marker existed must keep the dI/dV plot."""
        mcm, V = self._map_with_locations()
        mcm.metadata.instrument = 'Omicron Matrix'
        assert backend._is_stm_source(mcm) is True

    def test_clicking_dots_overlays_then_toggles_off(self, backend):
        mcm, _ = self._map_with_locations()
        backend._multi_channel_map = mcm
        mixed = []
        backend.openPlotWindowRequested.connect(
            lambda name, spectra: mixed.append([s['title'] for s in spectra])
            if name == "STS points" else None)
        backend._on_sts_marker_clicked(0)          # Point 3
        backend._on_sts_marker_clicked(1)          # + Point 7 (overlay)
        assert mixed[-1] == ["Point 3 · Forward", "Point 3 · Backward",
                             "Point 7 · Forward", "Point 7 · Backward"]
        backend._on_sts_marker_clicked(0)          # toggle Point 3 off
        assert mixed[-1] == ["Point 7 · Forward", "Point 7 · Backward"]

    def test_marker_click_is_safe_without_spectrum_or_out_of_range(self, backend):
        mcm = MultiChannelMap()
        mcm.add_channel("Z", np.zeros((4, 4)), ChannelType.HEIGHT, "m")
        mcm.metadata.extra = {'sts_locations': [
            {'point_index': 1, 'px': [0, 0], 'avg_spectra': None}]}
        backend._multi_channel_map = mcm
        fired = []
        backend.openPlotWindowRequested.connect(lambda n, s: fired.append(1))
        backend._on_sts_marker_clicked(0)    # no spectrum → no plot
        backend._on_sts_marker_clicked(99)   # out of range → safe
        backend._multi_channel_map = None
        backend._on_sts_marker_clicked(0)    # no map → safe
        assert fired == []

    def test_sts_average_pushed_to_inline_panel(self, backend):
        mcm, V = self._map_with_locations()
        backend._multi_channel_map = mcm
        avg = []
        backend.stsAverageUpdated.connect(lambda r: avg.append(r))
        backend._on_sts_marker_clicked(0)          # Point 3 alone
        assert avg[-1]['point_count'] == 1
        assert avg[-1]['x'] == V
        assert avg[-1]['y'] == [0.1, 0.2, 0.3]
        backend._on_sts_marker_clicked(1)          # + Point 7 → mean of both
        assert avg[-1]['point_count'] == 2
        assert avg[-1]['y'] == pytest.approx([0.55, 1.1, 1.65])
        backend._on_sts_marker_clicked(0)          # toggle Point 3 off
        assert avg[-1]['point_count'] == 1
        assert avg[-1]['y'] == [1.0, 2.0, 3.0]
        backend._on_sts_marker_clicked(1)          # toggle Point 7 off → empty
        assert avg[-1] == {}

    def test_sts_average_result_empty_when_nothing_selected(self, backend):
        assert backend._sts_average_result({}) == {}

    def test_get_map_spectra_info(self, backend):
        mcm, V = self._map_with_locations()
        backend._multi_channel_map = mcm
        info = backend.getMapSpectraInfo()
        assert info['sts_point_count'] == 2
        assert info['bias_points'] == len(V)
        assert info['bias_min'] == min(V)
        assert info['bias_max'] == max(V)
        assert set(info['sweeps']) == {'Forward', 'Backward', 'Mixed'}

    def test_get_map_spectra_info_no_map(self, backend):
        backend._multi_channel_map = None
        info = backend.getMapSpectraInfo()
        assert info['sts_point_count'] == 0
        assert info['sweeps'] == []

    def test_legacy_avg_spectrum_schema_still_plots(self, backend):
        # Projects saved before the multi-sweep rewrite stored a single
        # 'avg_spectrum' = {V, y}; the reader must upgrade it to Mixed-only.
        mcm = MultiChannelMap()
        mcm.add_channel("Z", np.zeros((8, 8)), ChannelType.HEIGHT, "m")
        V = [-0.4, 0.0, 0.4]
        mcm.metadata.extra = {'sts_locations': [
            {'point_index': 1, 'px': [2, 2], 'reps': 10,
             'avg_spectrum': {'V': V, 'y': [1e-8, 2e-8, 3e-8]}},
        ]}
        backend._multi_channel_map = mcm
        by_name = {}
        backend.openPlotWindowRequested.connect(
            lambda name, spectra: by_name.__setitem__(name, spectra))
        backend._on_sts_marker_clicked(0)
        # The old schema has no directions, so Mixed is what gets plotted —
        # in the one spectra window (dI/dV rides alongside for STM data).
        assert "STS points" in by_name
        curve = by_name["STS points"][0]
        assert curve['title'] == "Point 1 · Mixed"
        assert curve['y'] == [1e-8, 2e-8, 3e-8]
        # Metadata reads the legacy spectrum too.
        info = backend.getMapSpectraInfo()
        assert info['sts_point_count'] == 1
        assert info['bias_points'] == 3
        assert info['sweeps'] == ['Mixed']

    def test_loc_avg_spectra_prefers_new_over_legacy(self, backend):
        loc = {'avg_spectra': {'V': [0], 'Mixed': [9]},
               'avg_spectrum': {'V': [0], 'y': [1]}}
        assert backend._loc_avg_spectra(loc)['Mixed'] == [9]
        assert backend._loc_avg_spectra({}) is None


# =============================================================================
# Line-scan outlines on the map view
# =============================================================================

class TestLineScanOutlines:
    """A line scan is tagged and outlined, so 'which line went where' is
    readable off the scan image instead of being a fog of identical dots."""

    class FakeCanvas:
        def __init__(self):
            self.markers = None
            self.lines = None

        def setStsMarkers(self, markers):
            self.markers = markers

        def setStsLines(self, lines):
            self.lines = lines

    @staticmethod
    def _map_with_line():
        mcm = MultiChannelMap()
        mcm.add_channel("Z", np.zeros((64, 64)), ChannelType.HEIGHT, "m")
        mcm.metadata.extra = {
            'sts_locations': [
                {'point_index': 20 + i, 'px': [10 + i * 5, 30],
                 'line_scan_id': 1, 'line_pos': i, 'reps': 3}
                for i in range(4)
            ],
            'sts_line_scans': [{
                'id': 1, 'label': 'line1', 'n_points': 4, 'reps': 3,
                'point_indices': [20, 21, 22, 23],
                'point_first': 20, 'point_last': 23,
                'px_path': [[10, 30], [15, 30], [20, 30], [25, 30]],
                'px_start': [10, 30], 'px_end': [25, 30],
            }],
        }
        return mcm

    def test_line_is_pushed_to_the_canvas_as_a_path(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_sts_markers(self._map_with_line())

        assert len(canvas.lines) == 1
        path = canvas.lines[0]['path']
        assert len(path) == 4
        # Canvas coordinates are (col, row) = (pixel x, pixel y).
        assert path[0] == {'col': 10, 'row': 30}
        assert path[-1] == {'col': 25, 'row': 30}

    def test_tag_names_the_line_its_points_and_its_span(self, backend):
        tag = backend._line_scan_tag({
            'label': 'line1', 'n_points': 57, 'reps': 3,
            'point_first': 20, 'point_last': 76})
        assert 'line1' in tag
        assert '57pts' in tag
        assert '×3' in tag
        assert 'pt20→pt76' in tag

    def test_dots_are_still_pushed_alongside_the_outline(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_sts_markers(self._map_with_line())
        assert len(canvas.markers) == 4

    def test_map_without_line_scans_clears_the_outlines(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_sts_markers(self._map_with_line())
        assert canvas.lines

        plain = MultiChannelMap()
        plain.add_channel("Z", np.zeros((8, 8)), ChannelType.HEIGHT, "m")
        plain.metadata.extra = {'sts_locations': [
            {'point_index': 1, 'px': [2, 2]}]}
        backend._push_sts_markers(plain)
        assert canvas.lines == []

    def test_a_canvas_without_the_slot_is_tolerated(self, backend):
        class OldCanvas:
            def __init__(self): self.markers = None
            def setStsMarkers(self, markers): self.markers = markers

        backend._canvas = OldCanvas()
        backend._push_sts_markers(self._map_with_line())   # must not raise
        assert backend._canvas.markers is not None

    def test_tag_notes_a_hidden_single_sweep(self, backend):
        """The pre-sweep is off the map, so the tag says it exists — otherwise
        it looks like data went missing."""
        tag = backend._line_scan_tag({
            'label': 'line1', 'n_points': 57, 'reps': 511,
            'point_first': 73, 'point_last': 193, 'presweeps': 1})
        assert 'line1' in tag and '×511' in tag
        assert '+1 single sweep' in tag

    def test_tag_is_unchanged_without_a_hidden_sweep(self, backend):
        tag = backend._line_scan_tag({
            'label': 'line2', 'n_points': 57, 'reps': 1,
            'point_first': 74, 'point_last': 194, 'presweeps': 0})
        assert 'single sweep' not in tag


class TestOutOfBoundsLocations:
    """STS_LOCATION is a pixel in the scan the spectrum was taken on, so a
    spectrum bound to a differently sized scan can point off this image."""

    class FakeCanvas:
        def __init__(self):
            self.markers = None
            self.lines = None

        def setStsMarkers(self, markers):
            self.markers = markers

        def setStsLines(self, lines):
            self.lines = lines

    @staticmethod
    def _map(locations, lines=None, size=(32, 32)):
        mcm = MultiChannelMap()
        mcm.add_channel("Z", np.zeros(size), ChannelType.HEIGHT, "m")
        mcm.metadata.extra = {'sts_locations': locations,
                              'sts_line_scans': lines or []}
        return mcm

    def test_a_dot_outside_the_map_is_not_drawn(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_sts_markers(self._map([
            {'point_index': 1, 'px': [5, 5]},        # inside
            {'point_index': 2, 'px': [40, 5]},       # past the right edge
            {'point_index': 3, 'px': [5, -3]},       # above the top
        ]))

        assert [m['label'] for m in canvas.markers] == ['1']

    def test_a_point_on_the_boundary_survives_rounding(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_sts_markers(self._map([
            {'point_index': 1, 'px': [0, 0]},
            {'point_index': 2, 'px': [31, 31]},      # last valid pixel
        ]))

        assert len(canvas.markers) == 2

    def test_a_line_running_off_the_image_is_clipped_to_it(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_sts_markers(self._map(
            [], [{'id': 3, 'label': 'line3', 'n_points': 4, 'reps': 63,
                  'point_first': 203, 'point_last': 326,
                  'px_path': [[4, 4], [8, 8], [40, 40], [60, 60]]}]))

        assert len(canvas.lines) == 1
        assert canvas.lines[0]['path'] == [{'col': 4, 'row': 4},
                                           {'col': 8, 'row': 8}]

    def test_a_line_entirely_off_the_image_is_not_outlined(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_sts_markers(self._map(
            [], [{'id': 3, 'label': 'line3', 'n_points': 3, 'reps': 1,
                  'point_first': 1, 'point_last': 3,
                  'px_path': [[80, 80], [90, 90], [100, 100]]}]))

        assert canvas.lines == []

    def test_a_map_of_unknown_size_rejects_nothing(self, backend):
        assert backend._px_on_grid([999, 999], None) is True
        assert backend._px_on_grid([999, 999], ()) is True

    def test_malformed_coordinates_are_not_rejected_on_a_guess(self, backend):
        assert backend._px_on_grid(['x', None], (32, 32)) is True


class TestLineScanAxes:
    """A kymograph opened in the Hyperspectral tab gets real axes."""

    class FakeCanvas:
        def __init__(self):
            self.axes = None
        def setAxisMetadata(self, meta):
            self.axes = dict(meta) if meta else {}
        # The rest of the canvas API the load path touches.
        def __getattr__(self, name):
            return lambda *a, **k: None

    @staticmethod
    def _dataset(n_positions=8, n_points=64, step_m=5e-9, with_positions=True):
        import pandas as pd
        from src.models.spectral_data import SpectralData, SpectralMetadata

        x = np.linspace(-0.6, 0.6, n_points)
        columns = {f"P{i + 1}": np.sin(x * (i + 1)) for i in range(n_positions)}
        info = {}
        if with_positions:
            info['spectrum_meta'] = [{'location_m': [i * step_m, 0.0]}
                                     for i in range(n_positions)]
        return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
            source_type='sts', dimensions=(n_positions, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A'}, additional_info=info))

    def test_positions_become_the_x_axis(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_line_scan_axes(self._dataset(), 'kymograph')

        assert canvas.axes['x_unit'] == 'm'
        # 8 positions, 5 nm apart -> the map spans 8 pixels of 5 nm.
        assert canvas.axes['x_size'] == pytest.approx(8 * 5e-9)
        assert canvas.axes['x_offset'] == pytest.approx(0.0)

    def test_the_spectral_axis_becomes_the_y_axis(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_line_scan_axes(self._dataset(), 'kymograph')

        assert canvas.axes['y_unit'] == 'V'
        assert canvas.axes['y_size'] == pytest.approx(1.2, rel=0.05)
        assert canvas.axes['y_offset'] == pytest.approx(-0.6, abs=0.02)

    def test_a_strip_view_has_no_spectral_axis(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_line_scan_axes(self._dataset(), 'strip')

        assert 'y_unit' not in canvas.axes
        assert canvas.axes['x_unit'] == 'm'

    def test_positions_are_not_invented(self, backend):
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        backend._push_line_scan_axes(self._dataset(with_positions=False),
                                     'kymograph')

        assert 'x_unit' not in canvas.axes      # no metres claimed
        assert canvas.axes['y_unit'] == 'V'     # the bias axis is still known

    def test_a_stored_position_list_is_used(self, backend):
        """The interval map carries its positions directly."""
        canvas = self.FakeCanvas()
        backend._canvas = canvas
        dataset = self._dataset(with_positions=False)
        dataset.metadata.additional_info['position_m'] = [0.0, 1e-9, 2e-9, 3e-9,
                                                          4e-9, 5e-9, 6e-9, 7e-9]
        backend._push_line_scan_axes(dataset, 'kymograph')

        assert canvas.axes['x_unit'] == 'm'
        assert canvas.axes['x_size'] == pytest.approx(8e-9)

    def test_an_old_canvas_without_the_slot_is_tolerated(self, backend):
        class OldCanvas:
            pass

        backend._canvas = OldCanvas()
        backend._push_line_scan_axes(self._dataset(), 'kymograph')   # no raise
