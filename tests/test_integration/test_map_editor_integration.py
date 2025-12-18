"""
Integration tests for Map Editor functionality
Tests end-to-end workflows and interactions between components
"""

import pytest
import numpy as np
from pathlib import Path
import tempfile
import shutil

from src.models.map_channel import (
    MultiChannelMap, MapChannel, MapMetadata, ChannelMetadata, ChannelType
)
from src.models.spectral_data import SpectralData, SpectralMetadata
from src.backend.map_editor_backend import MapEditorBackend


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def integration_output_dir(tmp_path):
    """Create a temporary output directory for integration tests"""
    output_dir = tmp_path / "map_editor_output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def sample_afm_like_data():
    """Create realistic AFM-like data with height channel"""
    # Create synthetic topography
    x = np.linspace(0, 10, 256)
    y = np.linspace(0, 10, 256)
    X, Y = np.meshgrid(x, y)

    # Simulate AFM topography with step features
    height = np.zeros((256, 256))
    height += 50 * (X > 5)  # Step at x=5
    height += np.exp(-((X-3)**2 + (Y-7)**2) / 1) * 20  # Bump
    height += np.random.normal(0, 0.5, height.shape)  # Noise

    # Create amplitude signal
    amplitude = np.abs(np.gradient(height, axis=0)) + np.abs(np.gradient(height, axis=1))
    amplitude += np.random.normal(0, 0.1, amplitude.shape)

    # Create phase signal
    phase = np.arctan2(np.gradient(height, axis=1), np.gradient(height, axis=0))
    phase = np.degrees(phase)

    return {
        'height': height,
        'amplitude': amplitude,
        'phase': phase
    }


@pytest.fixture
def sample_snom_like_data():
    """Create SNOM-like data with spectral cube"""
    # 10x10 spatial grid, 100 spectral points
    rows, cols = 10, 10
    n_spectral = 100
    wavenumbers = np.linspace(800, 1800, n_spectral)

    # Create spectral cube with spatial variation
    cube = np.zeros((n_spectral, rows, cols))
    for i in range(rows):
        for j in range(cols):
            # Base spectrum
            base = np.exp(-((wavenumbers - 1000)**2) / 10000)
            # Spatial variation
            shift = (i + j) * 5
            peak = np.exp(-((wavenumbers - (1200 + shift))**2) / 5000)
            cube[:, i, j] = base + 0.5 * peak + np.random.normal(0, 0.01, n_spectral)

    # Create integrated intensity map
    integrated = np.sum(cube, axis=0)

    return {
        'cube': cube,
        'wavenumbers': wavenumbers,
        'integrated_map': integrated
    }


# =============================================================================
# Map Channel Integration Tests
# =============================================================================

@pytest.mark.integration
class TestMapChannelIntegration:
    """Integration tests for MapChannel and MultiChannelMap"""

    def test_full_afm_workflow(self, sample_afm_like_data, integration_output_dir):
        """Test complete AFM data workflow: load, process, analyze, export"""
        # Create multi-channel map
        mcmap = MultiChannelMap.from_arrays(
            sample_afm_like_data,
            physical_size=(10.0, 10.0),
            units="um"
        )

        # Verify channels created
        assert len(mcmap) == 3
        assert mcmap.shape == (256, 256)
        assert "height" in mcmap
        assert "amplitude" in mcmap
        assert "phase" in mcmap

        # Get statistics
        stats = mcmap.get_combined_statistics()
        assert 'height' in stats
        assert stats['height']['range'] > 0

        # Extract line profile
        height_channel = mcmap.get_channel("height")
        distance, values = height_channel.extract_profile(
            start=(128, 0), end=(128, 255)
        )
        assert len(distance) > 0
        assert len(values) == len(distance)
        # Should show the step feature
        assert np.max(values) > 40

        # Apply processing (plane level)
        from scipy.ndimage import gaussian_filter
        processed_data = gaussian_filter(height_channel.data, sigma=2)
        mcmap.add_channel("height_filtered", processed_data, replace=False)

        assert "height_filtered" in mcmap
        assert len(mcmap) == 4

        # Export all channels
        mcmap.save_all_channels(integration_output_dir, prefix="afm_")

        expected_files = [
            "afm_height.png",
            "afm_amplitude.png",
            "afm_phase.png",
            "afm_height_filtered.png"
        ]
        for filename in expected_files:
            assert (integration_output_dir / filename).exists()

    def test_spectral_spatial_reconstruction_workflow(self, sample_snom_like_data):
        """Test SNOM spatial-spectral reconstruction workflow"""
        snom = sample_snom_like_data

        # Create map with integrated intensity
        mcmap = MultiChannelMap()
        mcmap.add_channel("Integrated", snom['integrated_map'], ChannelType.OPTICAL)

        # Link spectral cube
        mcmap.link_spectral_cube(
            snom['cube'],
            snom['wavenumbers'],
            "Wavenumber (cm-1)"
        )

        assert mcmap.has_spectral_link
        assert mcmap.spectral_points == 100

        # Get spectrum at specific position
        x, y = mcmap.get_spectrum_at(5, 5)
        assert len(x) == 100
        assert len(y) == 100
        assert x[0] == 800
        assert x[-1] == 1800

        # Get average spectrum from region
        x_region, y_region = mcmap.get_spectra_in_region(
            0, 5, 0, 5, mode='average'
        )
        assert len(x_region) == 100
        assert len(y_region) == 100

        # Compute integrated map in range
        int_channel = mcmap.compute_integrated_map(start_val=950, end_val=1050)
        assert isinstance(int_channel, MapChannel)
        assert int_channel.shape == (10, 10)

        # Add to map
        mcmap.channels[int_channel.name] = int_channel
        assert len(mcmap) == 2

    def test_mask_workflow(self, sample_afm_like_data):
        """Test masking workflow: create, apply, analyze"""
        mcmap = MultiChannelMap.from_arrays(sample_afm_like_data)

        height = mcmap.get_channel("height")

        # Create mask based on height threshold - mask=True means INVALID/EXCLUDED
        # So we invert: mask low regions to only analyze high regions
        mask = height.data < 30  # True = excluded (low regions)
        mcmap.add_mask("exclude_low", mask)

        assert "exclude_low" in mcmap.masks
        assert np.sum(mask) > 0

        # Apply mask to channel
        mcmap.apply_mask_to_channel("exclude_low", "height")
        assert height.mask is not None

        # Get statistics with mask (excludes masked/low regions)
        stats_masked = height.get_statistics(use_mask=True)
        stats_all = height.get_statistics(use_mask=False)

        # Masked stats should only include high regions (non-masked)
        # So masked mean should be higher than overall mean
        assert stats_masked['mean'] > stats_all['mean']

    def test_copy_and_modify_workflow(self, sample_afm_like_data):
        """Test copying map and modifying independently"""
        original = MultiChannelMap.from_arrays(sample_afm_like_data)
        copied = original.copy()

        # Modify original
        original.get_channel("height").data[0, 0] = 999999

        # Copy should be unchanged
        assert copied.get_channel("height").data[0, 0] != 999999

        # Add channel to original
        original.add_channel("new", np.zeros((256, 256)))

        # Copy should not have new channel
        assert "new" not in copied


# =============================================================================
# Backend Integration Tests
# =============================================================================

@pytest.mark.integration
class TestMapEditorBackendIntegration:
    """Integration tests for MapEditorBackend"""

    def test_full_backend_workflow(self, sample_afm_like_data, integration_output_dir):
        """Test complete backend workflow"""
        backend = MapEditorBackend()

        # Create and set map
        mcmap = MultiChannelMap.from_arrays(sample_afm_like_data)
        backend.setMultiChannelMap(mcmap)

        assert backend.hasMapData
        assert backend.mapRows == 256
        assert backend.mapCols == 256
        assert len(backend.channelNames) == 3

        # Switch channels
        backend.setActiveChannel("amplitude")
        assert backend.activeChannelName == "amplitude"

        # Get statistics
        stats = backend.getActiveChannelStatistics()
        assert 'mean' in stats
        assert 'std' in stats

        # Apply processing
        results = []
        backend.processingFinished.connect(
            lambda op, success, msg: results.append((op, success))
        )

        backend.applyProcessing("gaussian_filter", {"sigma": 2.0})
        assert len(results) == 1
        assert results[0][1] == True  # success

        # Apply more processing
        backend.applyProcessing("normalize", {})
        assert len(results) == 2

        # Export
        output_path = integration_output_dir / "processed.tif"
        backend.exportChannel("amplitude", str(output_path))
        assert output_path.exists()

    def test_backend_with_spectral_data(self, sample_snom_like_data):
        """Test backend with spectral-spatial reconstruction"""
        backend = MapEditorBackend()

        # Create map
        mcmap = MultiChannelMap()
        mcmap.add_channel("Intensity", sample_snom_like_data['integrated_map'])
        backend.setMultiChannelMap(mcmap)

        # Link spectral data
        backend.linkSpectralCube(
            sample_snom_like_data['cube'],
            sample_snom_like_data['wavenumbers'],
            "Wavenumber"
        )

        assert backend.hasSpectralData
        assert backend.spectralPoints == 100

        # Get spectrum at position
        result = backend.getSpectrumAt(5, 5)
        assert 'x' in result
        assert 'y' in result
        assert len(result['x']) == 100

        # Compute integrated map
        result = backend.computeIntegratedMap("900,1100")
        assert result.get('success') == True

    def test_backend_file_io_roundtrip(self, sample_afm_like_data, integration_output_dir):
        """Test saving and loading through backend"""
        # Create backend with data
        backend1 = MapEditorBackend()
        mcmap = MultiChannelMap.from_arrays(sample_afm_like_data)
        backend1.setMultiChannelMap(mcmap)

        # Export to files
        for name in backend1.channelNames:
            path = integration_output_dir / f"{name}.tif"
            backend1.exportChannel(name, str(path))

        # Create new backend and load
        backend2 = MapEditorBackend()
        tiff_path = integration_output_dir / "height.tif"
        backend2.loadMapFromFile(str(tiff_path))

        assert backend2.hasMapData
        assert backend2.mapRows == 256
        assert backend2.mapCols == 256

    def test_processing_chain(self, sample_afm_like_data):
        """Test applying multiple processing operations in sequence"""
        backend = MapEditorBackend()
        mcmap = MultiChannelMap.from_arrays(sample_afm_like_data)
        backend.setMultiChannelMap(mcmap)
        backend.setActiveChannel("height")

        # Track processing results
        results = []
        backend.processingFinished.connect(
            lambda op, success, msg: results.append((op, success))
        )

        # Apply chain of operations
        operations = [
            ("plane_level", {}),
            ("row_align", {}),
            ("gaussian_filter", {"sigma": 1.0}),
            ("normalize", {})
        ]

        for op_name, params in operations:
            backend.applyProcessing(op_name, params)

        # All should succeed
        assert len(results) == 4
        assert all(r[1] for r in results)

        # Final data should be normalized
        active = backend._multi_channel_map.active_channel
        assert active.data.min() >= 0.0
        assert active.data.max() <= 1.0

        # History should have all operations
        assert len(active.history) == 4


# =============================================================================
# Processing Operations Integration Tests
# =============================================================================

@pytest.mark.integration
class TestProcessingIntegration:
    """Integration tests for map processing operations"""

    def test_gaussian_filter_effect(self, sample_afm_like_data):
        """Test Gaussian filter actually smooths data"""
        backend = MapEditorBackend()
        mcmap = MultiChannelMap.from_arrays(sample_afm_like_data)
        backend.setMultiChannelMap(mcmap)
        backend.setActiveChannel("height")

        # Get original statistics
        original_std = backend.getActiveChannelStatistics()['std']

        # Apply strong Gaussian filter
        backend.applyProcessing("gaussian_filter", {"sigma": 5.0})

        # Check std decreased (data smoothed)
        new_std = backend.getActiveChannelStatistics()['std']
        assert new_std < original_std

    def test_plane_level_effect(self):
        """Test plane leveling removes tilt"""
        # Create data with known tilt
        x = np.arange(100)
        y = np.arange(100)
        X, Y = np.meshgrid(x, y)
        tilted_data = X * 0.5 + Y * 0.3 + np.random.normal(0, 0.1, (100, 100))

        backend = MapEditorBackend()
        mcmap = MultiChannelMap()
        mcmap.add_channel("tilted", tilted_data)
        backend.setMultiChannelMap(mcmap)

        # Check initial tilt
        original_data = backend._multi_channel_map.active_channel.data.copy()
        assert original_data[0, 0] != original_data[99, 99]
        tilt_range = original_data.max() - original_data.min()

        # Apply plane leveling
        backend.applyProcessing("plane_level", {})

        # Check tilt reduced
        leveled_data = backend._multi_channel_map.active_channel.data
        new_range = leveled_data.max() - leveled_data.min()
        assert new_range < tilt_range * 0.5  # Should reduce by at least 50%

    def test_row_align_effect(self):
        """Test row alignment removes row-by-row offset"""
        # Create data with row offsets
        data = np.random.rand(50, 50)
        for i in range(50):
            data[i, :] += i * 2  # Add offset per row

        backend = MapEditorBackend()
        mcmap = MultiChannelMap()
        mcmap.add_channel("striped", data)
        backend.setMultiChannelMap(mcmap)

        # Apply row alignment
        backend.applyProcessing("row_align", {})

        # Check rows now have similar medians
        aligned = backend._multi_channel_map.active_channel.data
        row_medians = [np.median(aligned[i, :]) for i in range(50)]
        # All row medians should be close to 0 after alignment
        assert all(abs(m) < 0.5 for m in row_medians)

    def test_normalize_effect(self, sample_afm_like_data):
        """Test normalization scales data to [0, 1]"""
        backend = MapEditorBackend()
        mcmap = MultiChannelMap.from_arrays(sample_afm_like_data)
        backend.setMultiChannelMap(mcmap)
        backend.setActiveChannel("height")

        # Apply normalization
        backend.applyProcessing("normalize", {})

        # Check range
        data = backend._multi_channel_map.active_channel.data
        assert data.min() >= 0.0
        assert data.max() <= 1.0
        # Should use full range
        assert abs(data.min() - 0.0) < 0.001
        assert abs(data.max() - 1.0) < 0.001


# =============================================================================
# Spectral-Spatial Integration Tests
# =============================================================================

@pytest.mark.integration
class TestSpectralSpatialIntegration:
    """Integration tests for spectral-spatial reconstruction"""

    def test_spectral_extraction_consistency(self, sample_snom_like_data):
        """Test spectrum extraction is consistent"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("Integrated", sample_snom_like_data['integrated_map'])
        mcmap.link_spectral_cube(
            sample_snom_like_data['cube'],
            sample_snom_like_data['wavenumbers'],
            "Wavenumber"
        )

        # Get spectrum at same position multiple times
        x1, y1 = mcmap.get_spectrum_at(3, 4)
        x2, y2 = mcmap.get_spectrum_at(3, 4)

        np.testing.assert_array_equal(x1, x2)
        np.testing.assert_array_equal(y1, y2)

    def test_region_average_vs_individual(self, sample_snom_like_data):
        """Test region average matches manual average"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("Integrated", sample_snom_like_data['integrated_map'])
        mcmap.link_spectral_cube(
            sample_snom_like_data['cube'],
            sample_snom_like_data['wavenumbers'],
            "Wavenumber"
        )

        # Get region average
        x_avg, y_avg = mcmap.get_spectra_in_region(0, 2, 0, 2, mode='average')

        # Calculate manually
        spectra = []
        for i in range(2):
            for j in range(2):
                _, y = mcmap.get_spectrum_at(i, j)
                spectra.append(y)

        manual_avg = np.mean(spectra, axis=0)

        np.testing.assert_array_almost_equal(y_avg, manual_avg)

    def test_integrated_map_value_consistency(self, sample_snom_like_data):
        """Test integrated map values match manual integration"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("Integrated", sample_snom_like_data['integrated_map'])
        mcmap.link_spectral_cube(
            sample_snom_like_data['cube'],
            sample_snom_like_data['wavenumbers'],
            "Wavenumber"
        )

        # Compute integrated map
        int_channel = mcmap.compute_integrated_map(start_val=900, end_val=1100)

        # Manual integration at one point
        x, y = mcmap.get_spectrum_at(5, 5)
        mask = (x >= 900) & (x <= 1100)
        manual_int = np.sum(y[mask])

        # Should match
        assert abs(int_channel.data[5, 5] - manual_int) < 0.01


# =============================================================================
# Error Handling Integration Tests
# =============================================================================

@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Integration tests for error handling"""

    def test_backend_handles_invalid_file(self, tmp_path):
        """Test backend handles invalid file gracefully"""
        backend = MapEditorBackend()

        errors = []
        backend.processingFinished.connect(
            lambda op, success, msg: errors.append((op, success, msg))
        )

        # Try to load non-existent file
        backend.loadMapFromFile(str(tmp_path / "nonexistent.tif"))

        assert len(errors) == 1
        assert errors[0][1] == False  # success = False

    def test_backend_handles_corrupted_file(self, tmp_path):
        """Test backend handles corrupted file gracefully"""
        backend = MapEditorBackend()

        # Create corrupted TIFF
        bad_file = tmp_path / "corrupted.tif"
        bad_file.write_bytes(b"This is not a valid TIFF file")

        errors = []
        backend.processingFinished.connect(
            lambda op, success, msg: errors.append((op, success, msg))
        )

        backend.loadMapFromFile(str(bad_file))

        assert len(errors) == 1
        assert errors[0][1] == False

    def test_processing_without_data(self):
        """Test processing without loaded data is handled"""
        backend = MapEditorBackend()

        errors = []
        backend.processingFinished.connect(
            lambda op, success, msg: errors.append((op, success, msg))
        )

        backend.applyProcessing("normalize", {})

        assert len(errors) == 1
        assert errors[0][1] == False
        assert "No data" in errors[0][2]

    def test_spectral_query_without_link(self, sample_afm_like_data):
        """Test spectral query without linked data is handled"""
        backend = MapEditorBackend()
        mcmap = MultiChannelMap.from_arrays(sample_afm_like_data)
        backend.setMultiChannelMap(mcmap)

        result = backend.getSpectrumAt(0, 0)
        assert 'error' in result


# =============================================================================
# Performance Integration Tests
# =============================================================================

@pytest.mark.integration
@pytest.mark.slow
class TestPerformanceIntegration:
    """Performance-related integration tests"""

    def test_large_map_processing(self):
        """Test processing large map doesn't crash"""
        # Create 1024x1024 map
        large_data = np.random.rand(1024, 1024)

        backend = MapEditorBackend()
        mcmap = MultiChannelMap()
        mcmap.add_channel("large", large_data)
        backend.setMultiChannelMap(mcmap)

        # Apply processing
        results = []
        backend.processingFinished.connect(
            lambda op, success, msg: results.append(success)
        )

        backend.applyProcessing("gaussian_filter", {"sigma": 2.0})
        backend.applyProcessing("normalize", {})

        assert all(results)

    def test_large_spectral_cube(self):
        """Test large spectral cube operations"""
        # 50x50 spatial, 500 spectral points
        cube = np.random.rand(500, 50, 50)
        wavenumbers = np.linspace(400, 4000, 500)

        mcmap = MultiChannelMap()
        mcmap.add_channel("Map", np.sum(cube, axis=0))
        mcmap.link_spectral_cube(cube, wavenumbers, "Wavenumber")

        # Query should work
        x, y = mcmap.get_spectrum_at(25, 25)
        assert len(x) == 500

        # Region average should work
        x, y = mcmap.get_spectra_in_region(0, 25, 0, 25, mode='average')
        assert len(x) == 500
