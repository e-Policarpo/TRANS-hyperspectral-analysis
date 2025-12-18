"""
Tests for MapChannel and MultiChannelMap classes
Target coverage: 95%
"""

import pytest
import numpy as np
from pathlib import Path
import copy

from src.models.map_channel import (
    MapChannel, MultiChannelMap, MapMetadata, ChannelMetadata, ChannelType
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_2d_data():
    """Create sample 2D map data (100x100)"""
    # Create synthetic height map with features
    x = np.linspace(-5, 5, 100)
    y = np.linspace(-5, 5, 100)
    X, Y = np.meshgrid(x, y)
    # Gaussian features
    data = np.exp(-X**2/2 - Y**2/2) * 10
    # Add some noise
    data += np.random.normal(0, 0.1, data.shape)
    return data


@pytest.fixture
def sample_small_data():
    """Create small 2D data (10x10) for fast tests"""
    return np.random.rand(10, 10) * 100


@pytest.fixture
def sample_channel_metadata():
    """Create sample channel metadata"""
    return ChannelMetadata(
        name="Height",
        channel_type=ChannelType.HEIGHT,
        units="nm",
        physical_min=0.0,
        physical_max=100.0,
        description="Topography channel"
    )


@pytest.fixture
def sample_map_metadata():
    """Create sample map metadata"""
    return MapMetadata(
        dimensions=(100, 100),
        physical_size=(10.0, 10.0),
        physical_units="um",
        scan_direction="forward",
        scan_mode="contact",
        source_file="test_file.tif",
        instrument="Test AFM"
    )


@pytest.fixture
def sample_channel(sample_small_data, sample_channel_metadata):
    """Create sample MapChannel"""
    return MapChannel(data=sample_small_data, metadata=sample_channel_metadata)


@pytest.fixture
def sample_multi_channel_map(sample_small_data):
    """Create sample MultiChannelMap with multiple channels"""
    mcmap = MultiChannelMap()
    mcmap.add_channel("Height", sample_small_data, ChannelType.HEIGHT, "nm")
    mcmap.add_channel("Amplitude", sample_small_data * 0.5, ChannelType.AMPLITUDE, "V")
    mcmap.add_channel("Phase", sample_small_data * 2 - 50, ChannelType.PHASE, "deg")
    return mcmap


# =============================================================================
# ChannelMetadata Tests
# =============================================================================

class TestChannelMetadata:
    """Tests for ChannelMetadata dataclass"""

    def test_creation_with_all_fields(self, sample_channel_metadata):
        """Test creating metadata with all fields"""
        assert sample_channel_metadata.name == "Height"
        assert sample_channel_metadata.channel_type == ChannelType.HEIGHT
        assert sample_channel_metadata.units == "nm"
        assert sample_channel_metadata.physical_min == 0.0
        assert sample_channel_metadata.physical_max == 100.0

    def test_creation_with_defaults(self):
        """Test creating metadata with default values"""
        metadata = ChannelMetadata(name="Test")
        assert metadata.channel_type == ChannelType.CUSTOM
        assert metadata.units == "a.u."
        assert metadata.physical_min is None
        assert metadata.physical_max is None

    def test_auto_detect_height_from_name(self):
        """Test auto-detection of HEIGHT type from name"""
        metadata = ChannelMetadata(name="topography_data")
        assert metadata.channel_type == ChannelType.HEIGHT
        assert metadata.units == "nm"

    def test_auto_detect_amplitude_from_name(self):
        """Test auto-detection of AMPLITUDE type from name"""
        metadata = ChannelMetadata(name="amplitude signal")
        assert metadata.channel_type == ChannelType.AMPLITUDE

    def test_auto_detect_phase_from_name(self):
        """Test auto-detection of PHASE type from name"""
        metadata = ChannelMetadata(name="phase_channel")
        assert metadata.channel_type == ChannelType.PHASE
        assert metadata.units == "deg"

    def test_auto_detect_optical_from_name(self):
        """Test auto-detection of OPTICAL type from name"""
        metadata = ChannelMetadata(name="SNOM_optical")
        assert metadata.channel_type == ChannelType.OPTICAL

    def test_auto_detect_error_from_name(self):
        """Test auto-detection of ERROR type from name"""
        metadata = ChannelMetadata(name="error_signal")
        assert metadata.channel_type == ChannelType.ERROR

    def test_explicit_type_overrides_auto_detect(self):
        """Test that explicit channel_type is not overwritten"""
        metadata = ChannelMetadata(
            name="height_data",
            channel_type=ChannelType.AMPLITUDE  # Explicit, despite name
        )
        # Auto-detect only runs if type is CUSTOM
        assert metadata.channel_type == ChannelType.AMPLITUDE


# =============================================================================
# MapMetadata Tests
# =============================================================================

class TestMapMetadata:
    """Tests for MapMetadata dataclass"""

    def test_creation_with_all_fields(self, sample_map_metadata):
        """Test creating metadata with all fields"""
        assert sample_map_metadata.dimensions == (100, 100)
        assert sample_map_metadata.physical_size == (10.0, 10.0)
        assert sample_map_metadata.physical_units == "um"
        assert sample_map_metadata.scan_direction == "forward"

    def test_pixel_size_property(self, sample_map_metadata):
        """Test pixel_size calculation"""
        pixel_size = sample_map_metadata.pixel_size
        assert pixel_size is not None
        assert pixel_size == (0.1, 0.1)  # 10um / 100 pixels

    def test_pixel_size_none_when_no_physical_size(self):
        """Test pixel_size returns None when no physical size"""
        metadata = MapMetadata(dimensions=(50, 50))
        assert metadata.pixel_size is None

    def test_aspect_ratio_property(self, sample_map_metadata):
        """Test aspect_ratio calculation"""
        assert sample_map_metadata.aspect_ratio == 1.0

    def test_aspect_ratio_non_square(self):
        """Test aspect_ratio for non-square map"""
        metadata = MapMetadata(dimensions=(100, 200))  # height, width
        assert metadata.aspect_ratio == 2.0  # width/height


# =============================================================================
# MapChannel Tests
# =============================================================================

class TestMapChannelCreation:
    """Tests for MapChannel creation and initialization"""

    def test_create_from_2d_array(self, sample_small_data):
        """Test creating channel from 2D array"""
        channel = MapChannel(data=sample_small_data)
        assert channel.data is not None
        assert channel.shape == (10, 10)
        assert channel.data.dtype == np.float64

    def test_create_with_metadata(self, sample_small_data, sample_channel_metadata):
        """Test creating channel with metadata"""
        channel = MapChannel(data=sample_small_data, metadata=sample_channel_metadata)
        assert channel.metadata.name == "Height"
        assert channel.metadata.channel_type == ChannelType.HEIGHT

    def test_create_with_mask(self, sample_small_data):
        """Test creating channel with mask"""
        mask = np.zeros((10, 10), dtype=bool)
        mask[0:2, 0:2] = True  # Mask top-left corner
        channel = MapChannel(data=sample_small_data, mask=mask)
        assert channel.mask is not None
        assert np.sum(channel.mask) == 4

    def test_reject_non_2d_data(self):
        """Test that 1D data raises error"""
        with pytest.raises(ValueError, match="must be 2D"):
            MapChannel(data=np.array([1, 2, 3]))

    def test_reject_3d_data(self):
        """Test that 3D data raises error"""
        with pytest.raises(ValueError, match="must be 2D"):
            MapChannel(data=np.random.rand(10, 10, 10))

    def test_default_metadata_created(self, sample_small_data):
        """Test that default metadata is created when not provided"""
        channel = MapChannel(data=sample_small_data)
        assert channel.metadata is not None
        assert channel.metadata.name == "Untitled"


class TestMapChannelProperties:
    """Tests for MapChannel properties"""

    def test_shape_property(self, sample_channel):
        """Test shape property"""
        assert sample_channel.shape == (10, 10)

    def test_name_property(self, sample_channel):
        """Test name property getter"""
        assert sample_channel.name == "Height"

    def test_name_property_setter(self, sample_channel):
        """Test name property setter"""
        sample_channel.name = "New Name"
        assert sample_channel.name == "New Name"
        assert sample_channel.metadata.name == "New Name"

    def test_valid_data_without_mask(self, sample_channel):
        """Test valid_data without mask returns original data"""
        valid = sample_channel.valid_data
        np.testing.assert_array_equal(valid, sample_channel.data)

    def test_valid_data_with_mask(self, sample_small_data):
        """Test valid_data with mask sets masked values to NaN"""
        mask = np.zeros((10, 10), dtype=bool)
        mask[0, 0] = True
        channel = MapChannel(data=sample_small_data, mask=mask)
        valid = channel.valid_data
        assert np.isnan(valid[0, 0])
        assert not np.isnan(valid[1, 1])


class TestMapChannelOperations:
    """Tests for MapChannel operations"""

    def test_normalize_default(self, sample_channel):
        """Test normalize with default parameters"""
        normalized = sample_channel.normalize()
        assert normalized.min() >= 0.0
        assert normalized.max() <= 1.0

    def test_normalize_with_vmin_vmax(self, sample_small_data):
        """Test normalize with explicit min/max"""
        channel = MapChannel(data=sample_small_data)
        normalized = channel.normalize(vmin=20, vmax=80)
        # Values outside range should be clipped to [0, 1]
        assert normalized.min() >= 0.0
        assert normalized.max() <= 1.0

    def test_normalize_with_percentile(self, sample_channel):
        """Test normalize with percentile"""
        normalized = sample_channel.normalize(percentile=(2, 98))
        assert normalized.min() >= 0.0
        assert normalized.max() <= 1.0

    def test_normalize_constant_data(self):
        """Test normalize with constant data returns zeros"""
        channel = MapChannel(data=np.ones((10, 10)) * 5)
        normalized = channel.normalize()
        assert np.allclose(normalized, 0)

    def test_get_statistics(self, sample_channel):
        """Test get_statistics returns expected keys"""
        stats = sample_channel.get_statistics()
        expected_keys = ['min', 'max', 'mean', 'std', 'median', 'rms', 'range']
        for key in expected_keys:
            assert key in stats
            assert isinstance(stats[key], float)

    def test_get_statistics_with_mask(self, sample_small_data):
        """Test get_statistics respects mask"""
        mask = np.ones((10, 10), dtype=bool)
        mask[5, 5] = False  # Only one valid pixel
        sample_small_data[5, 5] = 42.0  # Known value
        channel = MapChannel(data=sample_small_data, mask=mask)
        stats = channel.get_statistics(use_mask=True)
        assert stats['mean'] == 42.0
        assert stats['min'] == 42.0
        assert stats['max'] == 42.0

    def test_extract_profile_horizontal(self, sample_small_data):
        """Test extracting horizontal line profile"""
        channel = MapChannel(data=sample_small_data)
        distance, values = channel.extract_profile(start=(5, 0), end=(5, 9))
        assert len(distance) > 0
        assert len(values) == len(distance)
        assert distance[0] == 0

    def test_extract_profile_vertical(self, sample_small_data):
        """Test extracting vertical line profile"""
        channel = MapChannel(data=sample_small_data)
        distance, values = channel.extract_profile(start=(0, 5), end=(9, 5))
        assert len(distance) > 0
        assert len(values) == len(distance)

    def test_extract_profile_diagonal(self, sample_small_data):
        """Test extracting diagonal line profile"""
        channel = MapChannel(data=sample_small_data)
        distance, values = channel.extract_profile(start=(0, 0), end=(9, 9))
        assert len(distance) > 0
        assert len(values) == len(distance)

    def test_extract_profile_single_point(self, sample_small_data):
        """Test extracting profile from single point"""
        channel = MapChannel(data=sample_small_data)
        distance, values = channel.extract_profile(start=(5, 5), end=(5, 5))
        assert len(distance) == 1
        assert len(values) == 1
        assert distance[0] == 0

    def test_extract_profile_with_width(self, sample_small_data):
        """Test extracting profile with averaging width"""
        channel = MapChannel(data=sample_small_data)
        distance, values = channel.extract_profile(start=(5, 0), end=(5, 9), width=3)
        assert len(distance) > 0
        assert len(values) == len(distance)

    def test_add_history(self, sample_channel):
        """Test adding history entry"""
        sample_channel.add_history("gaussian_filter", {"sigma": 1.0})
        assert len(sample_channel.history) == 1
        assert sample_channel.history[0]['operation'] == "gaussian_filter"
        assert sample_channel.history[0]['parameters']['sigma'] == 1.0

    def test_copy_creates_independent_copy(self, sample_channel):
        """Test copy creates deep copy"""
        copied = sample_channel.copy()

        # Modify original
        original_value = sample_channel.data[0, 0]
        copied.data[0, 0] = 999999

        # Original should be unchanged
        assert sample_channel.data[0, 0] == original_value
        assert copied.data[0, 0] == 999999

    def test_copy_preserves_history(self, sample_channel):
        """Test copy preserves history"""
        sample_channel.add_history("test_op", {"param": 1})
        copied = sample_channel.copy()
        assert len(copied.history) == 1
        assert copied.history[0]['operation'] == "test_op"

    def test_repr(self, sample_channel):
        """Test string representation"""
        repr_str = repr(sample_channel)
        assert "MapChannel" in repr_str
        assert "Height" in repr_str
        assert "(10, 10)" in repr_str


# =============================================================================
# MultiChannelMap Tests
# =============================================================================

class TestMultiChannelMapCreation:
    """Tests for MultiChannelMap creation"""

    def test_create_empty(self):
        """Test creating empty map"""
        mcmap = MultiChannelMap()
        assert len(mcmap) == 0
        assert mcmap.shape is None

    def test_create_with_metadata(self, sample_map_metadata):
        """Test creating with metadata"""
        mcmap = MultiChannelMap(metadata=sample_map_metadata)
        assert mcmap.metadata.dimensions == (100, 100)

    def test_from_arrays(self, sample_small_data):
        """Test from_arrays class method"""
        arrays = {
            "Height": sample_small_data,
            "Phase": sample_small_data * 2
        }
        mcmap = MultiChannelMap.from_arrays(arrays, physical_size=(10, 10), units="um")
        assert len(mcmap) == 2
        assert "Height" in mcmap
        assert "Phase" in mcmap
        assert mcmap.metadata.physical_size == (10, 10)

    def test_from_arrays_empty_raises(self):
        """Test from_arrays with empty dict raises error"""
        with pytest.raises(ValueError, match="At least one array required"):
            MultiChannelMap.from_arrays({})


class TestMultiChannelMapChannelManagement:
    """Tests for channel management in MultiChannelMap"""

    def test_add_channel(self, sample_small_data):
        """Test adding a channel"""
        mcmap = MultiChannelMap()
        channel = mcmap.add_channel("Test", sample_small_data)
        assert "Test" in mcmap
        assert len(mcmap) == 1
        assert isinstance(channel, MapChannel)

    def test_add_channel_sets_active(self, sample_small_data):
        """Test first added channel becomes active"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("First", sample_small_data)
        assert mcmap.active_channel_name == "First"

    def test_add_channel_dimension_mismatch(self, sample_small_data):
        """Test adding channel with wrong dimensions raises error"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("First", sample_small_data)

        with pytest.raises(ValueError, match="doesn't match"):
            mcmap.add_channel("Second", np.random.rand(20, 20))

    def test_add_channel_duplicate_without_replace(self, sample_small_data):
        """Test adding duplicate channel without replace raises error"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("Test", sample_small_data)

        with pytest.raises(ValueError, match="already exists"):
            mcmap.add_channel("Test", sample_small_data)

    def test_add_channel_duplicate_with_replace(self, sample_small_data):
        """Test adding duplicate channel with replace=True"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("Test", sample_small_data)
        new_data = sample_small_data * 2
        mcmap.add_channel("Test", new_data, replace=True)

        assert len(mcmap) == 1
        np.testing.assert_array_almost_equal(mcmap["Test"].data, new_data)

    def test_remove_channel(self, sample_multi_channel_map):
        """Test removing a channel"""
        sample_multi_channel_map.remove_channel("Phase")
        assert "Phase" not in sample_multi_channel_map
        assert len(sample_multi_channel_map) == 2

    def test_remove_channel_updates_active(self, sample_small_data):
        """Test removing active channel updates active"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("First", sample_small_data)
        mcmap.add_channel("Second", sample_small_data)
        mcmap.set_active_channel("First")

        mcmap.remove_channel("First")
        assert mcmap.active_channel_name == "Second"

    def test_remove_nonexistent_channel(self, sample_multi_channel_map):
        """Test removing nonexistent channel raises error"""
        with pytest.raises(KeyError):
            sample_multi_channel_map.remove_channel("NonExistent")

    def test_get_channel(self, sample_multi_channel_map):
        """Test getting channel by name"""
        channel = sample_multi_channel_map.get_channel("Height")
        assert isinstance(channel, MapChannel)
        assert channel.name == "Height"

    def test_get_channel_not_found(self, sample_multi_channel_map):
        """Test getting nonexistent channel raises error"""
        with pytest.raises(KeyError):
            sample_multi_channel_map.get_channel("NonExistent")

    def test_duplicate_channel(self, sample_multi_channel_map):
        """Test duplicating a channel"""
        original = sample_multi_channel_map.get_channel("Height")
        duplicated = sample_multi_channel_map.duplicate_channel("Height", "Height_Copy")

        assert "Height_Copy" in sample_multi_channel_map
        assert duplicated.name == "Height_Copy"
        np.testing.assert_array_equal(original.data, duplicated.data)


class TestMultiChannelMapProperties:
    """Tests for MultiChannelMap properties"""

    def test_shape_property(self, sample_multi_channel_map):
        """Test shape property"""
        assert sample_multi_channel_map.shape == (10, 10)

    def test_shape_empty_map(self):
        """Test shape of empty map returns None"""
        mcmap = MultiChannelMap()
        assert mcmap.shape is None

    def test_channel_names_property(self, sample_multi_channel_map):
        """Test channel_names property"""
        names = sample_multi_channel_map.channel_names
        assert "Height" in names
        assert "Amplitude" in names
        assert "Phase" in names
        assert len(names) == 3

    def test_active_channel_property(self, sample_multi_channel_map):
        """Test active_channel property"""
        active = sample_multi_channel_map.active_channel
        assert isinstance(active, MapChannel)

    def test_active_channel_empty_map(self):
        """Test active_channel returns None for empty map"""
        mcmap = MultiChannelMap()
        assert mcmap.active_channel is None

    def test_set_active_channel(self, sample_multi_channel_map):
        """Test setting active channel"""
        sample_multi_channel_map.set_active_channel("Phase")
        assert sample_multi_channel_map.active_channel_name == "Phase"

    def test_set_active_channel_not_found(self, sample_multi_channel_map):
        """Test setting nonexistent active channel raises error"""
        with pytest.raises(KeyError):
            sample_multi_channel_map.set_active_channel("NonExistent")


class TestMultiChannelMapMasks:
    """Tests for mask management in MultiChannelMap"""

    def test_add_mask(self, sample_multi_channel_map):
        """Test adding a mask"""
        mask = np.zeros((10, 10), dtype=bool)
        mask[0:5, 0:5] = True
        sample_multi_channel_map.add_mask("top_left", mask)

        assert "top_left" in sample_multi_channel_map.masks
        assert np.sum(sample_multi_channel_map.masks["top_left"]) == 25

    def test_add_mask_wrong_shape(self, sample_multi_channel_map):
        """Test adding mask with wrong shape raises error"""
        with pytest.raises(ValueError, match="doesn't match"):
            sample_multi_channel_map.add_mask("bad", np.zeros((5, 5), dtype=bool))

    def test_remove_mask(self, sample_multi_channel_map):
        """Test removing a mask"""
        mask = np.zeros((10, 10), dtype=bool)
        sample_multi_channel_map.add_mask("test", mask)
        sample_multi_channel_map.remove_mask("test")

        assert "test" not in sample_multi_channel_map.masks

    def test_apply_mask_to_channel(self, sample_multi_channel_map):
        """Test applying mask to channel"""
        mask = np.zeros((10, 10), dtype=bool)
        mask[0, 0] = True
        sample_multi_channel_map.add_mask("test", mask)
        sample_multi_channel_map.apply_mask_to_channel("test", "Height")

        channel = sample_multi_channel_map.get_channel("Height")
        assert channel.mask is not None
        assert channel.mask[0, 0] == True


class TestMultiChannelMapStatistics:
    """Tests for statistics in MultiChannelMap"""

    def test_get_combined_statistics(self, sample_multi_channel_map):
        """Test getting statistics for all channels"""
        stats = sample_multi_channel_map.get_combined_statistics()

        assert "Height" in stats
        assert "Amplitude" in stats
        assert "Phase" in stats

        for channel_stats in stats.values():
            assert 'mean' in channel_stats
            assert 'std' in channel_stats


class TestMultiChannelMapCopy:
    """Tests for copying MultiChannelMap"""

    def test_copy_creates_independent_copy(self, sample_multi_channel_map):
        """Test copy creates deep copy"""
        copied = sample_multi_channel_map.copy()

        # Modify original
        sample_multi_channel_map["Height"].data[0, 0] = 999999

        # Copy should be unchanged
        assert copied["Height"].data[0, 0] != 999999

    def test_copy_preserves_metadata(self, sample_multi_channel_map):
        """Test copy preserves metadata"""
        sample_multi_channel_map.metadata = MapMetadata(
            dimensions=(10, 10),
            physical_size=(5, 5)
        )
        copied = sample_multi_channel_map.copy()

        assert copied.metadata.physical_size == (5, 5)

    def test_copy_preserves_masks(self, sample_multi_channel_map):
        """Test copy preserves masks"""
        mask = np.zeros((10, 10), dtype=bool)
        mask[0, 0] = True
        sample_multi_channel_map.add_mask("test", mask)

        copied = sample_multi_channel_map.copy()
        assert "test" in copied.masks
        assert copied.masks["test"][0, 0] == True


class TestMultiChannelMapContainerMethods:
    """Tests for container protocol methods"""

    def test_len(self, sample_multi_channel_map):
        """Test __len__"""
        assert len(sample_multi_channel_map) == 3

    def test_contains(self, sample_multi_channel_map):
        """Test __contains__"""
        assert "Height" in sample_multi_channel_map
        assert "NonExistent" not in sample_multi_channel_map

    def test_getitem(self, sample_multi_channel_map):
        """Test __getitem__"""
        channel = sample_multi_channel_map["Height"]
        assert isinstance(channel, MapChannel)

    def test_iter(self, sample_multi_channel_map):
        """Test __iter__"""
        channels = list(sample_multi_channel_map)
        assert len(channels) == 3
        assert all(isinstance(c, MapChannel) for c in channels)

    def test_repr(self, sample_multi_channel_map):
        """Test __repr__"""
        repr_str = repr(sample_multi_channel_map)
        assert "MultiChannelMap" in repr_str
        assert "channels=3" in repr_str


# =============================================================================
# Spectral-Spatial Linking Tests
# =============================================================================

class TestSpectralSpatialLinking:
    """Tests for spectral-spatial reconstruction features"""

    @pytest.fixture
    def map_with_spectral(self, sample_small_data):
        """Create map with linked spectral cube"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("Height", sample_small_data)

        # Create spectral cube: 50 spectral points, 10x10 spatial
        cube = np.random.rand(50, 10, 10)
        independent_var = np.linspace(800, 1800, 50)  # Wavenumbers

        mcmap.link_spectral_cube(cube, independent_var, "Wavenumber (cm-1)")
        return mcmap

    def test_link_spectral_cube(self, sample_small_data):
        """Test linking spectral cube"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("Height", sample_small_data)

        cube = np.random.rand(100, 10, 10)
        x = np.linspace(0, 10, 100)

        mcmap.link_spectral_cube(cube, x, "Energy")

        assert mcmap.has_spectral_link
        assert mcmap.spectral_points == 100
        assert mcmap.independent_var_name == "Energy"

    def test_link_spectral_cube_dimension_mismatch(self, sample_small_data):
        """Test error when cube dimensions don't match var length"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("Height", sample_small_data)

        cube = np.random.rand(100, 10, 10)
        x = np.linspace(0, 10, 50)  # Wrong length

        with pytest.raises(ValueError, match="doesn't match"):
            mcmap.link_spectral_cube(cube, x, "x")

    def test_link_spectral_cube_non_3d(self, sample_small_data):
        """Test error when cube is not 3D"""
        mcmap = MultiChannelMap()
        mcmap.add_channel("Height", sample_small_data)

        with pytest.raises(ValueError, match="must be 3D"):
            mcmap.link_spectral_cube(np.random.rand(10, 10), np.linspace(0, 1, 10), "x")

    def test_unlink_spectral_data(self, map_with_spectral):
        """Test unlinking spectral data"""
        assert map_with_spectral.has_spectral_link
        map_with_spectral.unlink_spectral_data()
        assert not map_with_spectral.has_spectral_link
        assert map_with_spectral.spectral_points == 0

    def test_get_spectrum_at(self, map_with_spectral):
        """Test getting spectrum at position"""
        x, y = map_with_spectral.get_spectrum_at(5, 5)
        assert len(x) == 50
        assert len(y) == 50

    def test_get_spectrum_at_out_of_bounds(self, map_with_spectral):
        """Test get_spectrum_at with out of bounds position"""
        with pytest.raises(IndexError):
            map_with_spectral.get_spectrum_at(100, 100)

    def test_get_spectrum_at_no_link(self, sample_multi_channel_map):
        """Test get_spectrum_at without spectral link"""
        with pytest.raises(ValueError, match="No spectral data linked"):
            sample_multi_channel_map.get_spectrum_at(0, 0)

    def test_get_spectra_in_region_average(self, map_with_spectral):
        """Test getting average spectrum from region"""
        x, y = map_with_spectral.get_spectra_in_region(0, 5, 0, 5, mode='average')
        assert len(x) == 50
        assert len(y) == 50

    def test_get_spectra_in_region_all(self, map_with_spectral):
        """Test getting all spectra from region"""
        x, y = map_with_spectral.get_spectra_in_region(0, 5, 0, 5, mode='all')
        assert len(x) == 50
        assert y.shape == (50, 25)  # 5x5 region = 25 spectra

    def test_get_spectra_by_mask(self, map_with_spectral):
        """Test getting spectra by mask"""
        mask = np.zeros((10, 10), dtype=bool)
        mask[0:2, 0:2] = True  # Select 4 pixels

        x, y = map_with_spectral.get_spectra_by_mask(mask, mode='average')
        assert len(x) == 50
        assert len(y) == 50

    def test_compute_integrated_map_by_value(self, map_with_spectral):
        """Test computing integrated map by value range"""
        channel = map_with_spectral.compute_integrated_map(start_val=900, end_val=1000)
        assert isinstance(channel, MapChannel)
        assert channel.shape == (10, 10)
        assert "Integrated" in channel.name

    def test_compute_integrated_map_by_index(self, map_with_spectral):
        """Test computing integrated map by index range"""
        channel = map_with_spectral.compute_integrated_map(start_idx=10, end_idx=20)
        assert isinstance(channel, MapChannel)

    def test_compute_value_at_map(self, map_with_spectral):
        """Test computing map at specific spectral index"""
        channel = map_with_spectral.compute_value_at_map(index=25)
        assert isinstance(channel, MapChannel)
        assert channel.shape == (10, 10)
        assert "Value_at" in channel.name

    def test_compute_value_at_map_out_of_bounds(self, map_with_spectral):
        """Test compute_value_at_map with out of bounds index"""
        with pytest.raises(IndexError):
            map_with_spectral.compute_value_at_map(index=1000)


# =============================================================================
# IO Tests
# =============================================================================

class TestMultiChannelMapIO:
    """Tests for saving/loading MultiChannelMap"""

    def test_save_channel_image(self, sample_multi_channel_map, tmp_path):
        """Test saving channel as image"""
        output_path = tmp_path / "test_height.png"
        sample_multi_channel_map.save_channel_image("Height", output_path)
        assert output_path.exists()

    def test_save_all_channels(self, sample_multi_channel_map, tmp_path):
        """Test saving all channels"""
        sample_multi_channel_map.save_all_channels(tmp_path, prefix="test_")

        expected_files = ["test_Height.png", "test_Amplitude.png", "test_Phase.png"]
        for filename in expected_files:
            assert (tmp_path / filename).exists()

    def test_from_gsf_not_implemented(self, tmp_path):
        """Test from_gsf raises NotImplementedError"""
        # Create dummy file
        gsf_path = tmp_path / "test.gsf"
        gsf_path.write_bytes(b"NotGwyd")

        with pytest.raises(ValueError):
            MultiChannelMap.from_gsf(gsf_path)
