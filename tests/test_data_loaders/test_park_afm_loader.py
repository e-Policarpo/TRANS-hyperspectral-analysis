"""
Tests for Park AFM PinPoint Loader
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy

Tests the Park AFM loader for:
- TIFF loading with Park custom tags
- PS-PPT file parsing (magic, index, JSON events)
- Naming convention parsing and session grouping
- Smart import sibling discovery
"""

import json
import base64
import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from struct import pack
from unittest.mock import patch, MagicMock

from src.data_loaders.park_afm_loader import (
    ParkAFMLoader,
    PsPptParser,
    parse_park_filename,
    session_key,
    load_park_tiff,
    PARK_TAG_DATA,
    PARK_TAG_META,
)
from src.models.spectral_data import SpectralData
from src.models.topography_data import TopographyData


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def loader():
    """Create a ParkAFMLoader instance."""
    return ParkAFMLoader()


@pytest.fixture
def sample_tiff_file(tmp_path):
    """Create a minimal Park-style TIFF with custom tags."""
    from PIL import Image

    width, height = 32, 32
    # Create a grayscale image
    img = Image.new('L', (width, height), 128)

    # Build tag 50434: float32 raw data
    raw_data = np.random.rand(height, width).astype(np.float32) * 1e-6
    raw_bytes = raw_data.tobytes()

    # Build tag 50435: minimal metadata
    meta = bytearray(580)
    # Channel name at 0x04 (UTF-16LE, 64 bytes)
    channel = 'Z Height'.encode('utf-16-le')
    meta[0x04:0x04 + len(channel)] = channel
    # Scan mode at 0x44 (UTF-16LE, 32 bytes)
    mode = 'Contact'.encode('utf-16-le')
    meta[0x44:0x44 + len(mode)] = mode
    # Scan dimensions as doubles at 0x8c and 0x94
    meta[0x8c:0x94] = pack('<d', 5.0)  # scan width um
    meta[0x94:0x9c] = pack('<d', 5.0)  # scan height um

    filepath = tmp_path / "Termico-1_250924_Z Height_Backward_021.tiff"

    # Save with custom tags
    img.save(str(filepath), tiffinfo={
        50434: raw_bytes,
        50435: bytes(meta),
        305: 'Park Systems SmartScan',
        306: '2025:09:24 14:25:19',
    })

    return filepath, raw_data


@pytest.fixture
def sample_ppt_file(tmp_path):
    """Create a minimal PS-PPT file with a few pixel events."""
    pixel_w, pixel_h = 4, 4
    n_points = 50

    # Build the event stream
    events = []

    # scan.start
    events.append(json.dumps({
        "type": "scan.start",
        "geometry": {
            "pixelWidth": pixel_w,
            "pixelHeight": pixel_h,
            "width": 5, "height": 5,
            "direction": "forward",
            "offsetX": 0, "offsetY": 0, "rotation": 0,
        },
        "time": "2025/09/24 15:43:05",
    }))

    # ppt.param
    events.append(json.dumps({
        "type": "ppt.param",
        "cantilever": {
            "name": "Scout 350",
            "cal": {"forceConstant": 39.26, "forceSlope": 0.03785},
        },
        "pinpoint": {"basic": {"approachSpeed": 30, "retractSpeed": 30}},
    }))

    # ppt.rtfd events for each pixel
    for slow in range(pixel_h):
        for fast in range(pixel_w):
            force = np.random.rand(n_points).astype(np.float32)
            z_height = np.linspace(1.0, 2.0, n_points).astype(np.float32)
            lfm = np.random.rand(n_points).astype(np.float32) * 0.1

            events.append(json.dumps({
                "type": "ppt.rtfd",
                "info": {
                    "channels": [
                        {"id": "Lfm", "unit": "volt"},
                        {"id": "Force", "unit": "volt"},
                        {"id": "ZHeight", "unit": "micrometer"},
                    ],
                    "forward": True,
                    "index": {"fast": fast, "slow": slow},
                    "elapsed_sec": 0.02,
                    "padding": False,
                },
                "numbers": [
                    base64.b64encode(lfm.tobytes()).decode(),
                    base64.b64encode(force.tobytes()).decode(),
                    base64.b64encode(z_height.tobytes()).decode(),
                ],
            }))

    # scan.stop
    events.append(json.dumps({
        "type": "scan.stop",
        "time": "2025/09/24 16:36:05",
    }))

    event_stream = '\n'.join(events).encode('utf-8')

    # Build the file: magic + header + index + padding + events
    magic = b'PS-PPT/v1\n'
    header_bytes = bytes([1, 4, 16, 0]) + b'\x00' * 16  # 20 bytes after magic

    # Data offset: we need index + padding to get to a reasonable offset
    # For simplicity, put data right after the index
    # Index: one table with (n_events) entries, each 8 bytes
    n_events = len(events)
    index_start = 0x1e  # 30
    index_size = n_events * 8
    data_start = index_start + index_size + 256  # small padding

    # Build index entries (table ID 0x00, big-endian offsets)
    index = bytearray()
    offset = data_start
    for i, ev_bytes in enumerate(events):
        ev_encoded = ev_bytes.encode('utf-8') if isinstance(ev_bytes, str) else ev_bytes
        entry = pack('>I', offset)
        entry += bytes([0x10 if i < 2 else 0x11, 0, 0, 0])
        index += entry
        offset += len(ev_encoded) + 1  # +1 for newline

    # Pad to data_start
    header_total = magic + header_bytes
    padding_needed = data_start - len(header_total) - len(index)
    if padding_needed < 0:
        data_start = len(header_total) + len(index) + 16
        padding_needed = 16
        # Rebuild index with corrected offsets
        index = bytearray()
        offset = data_start
        for i, ev_bytes in enumerate(events):
            ev_encoded = ev_bytes.encode('utf-8') if isinstance(ev_bytes, str) else ev_bytes
            entry = pack('>I', offset)
            entry += bytes([0x10 if i < 2 else 0x11, 0, 0, 0])
            index += entry
            offset += len(ev_encoded) + 1

    file_data = header_total + bytes(index) + b'\x00' * padding_needed + event_stream

    filepath = tmp_path / "Test_250924_PinPoint_Forward_001.ps-ppt"
    filepath.write_bytes(file_data)

    return filepath, pixel_w, pixel_h, n_points


# =============================================================================
# Naming Convention Tests
# =============================================================================

class TestParkNamingConvention:
    """Tests for Park AFM filename parsing."""

    def test_parse_standard_tiff_name(self):
        """PARK-01: Parse standard TIFF filename."""
        result = parse_park_filename("Termico-1_250924_Z Height_Backward_021")
        assert result is not None
        assert result['sample'] == 'Termico-1'
        assert result['date'] == '250924'
        assert result['channel'] == 'Z Height'
        assert result['direction'] == 'Backward'
        assert result['scan'] == '021'

    def test_parse_ppt_name(self):
        """PARK-02: Parse ps-ppt filename."""
        result = parse_park_filename("Termico-2-B_250924_PinPoint_Backward_027")
        assert result is not None
        assert result['sample'] == 'Termico-2-B'
        assert result['channel'] == 'PinPoint'
        assert result['direction'] == 'Backward'

    def test_parse_multi_word_channel(self):
        """PARK-03: Parse filename with multi-word channel."""
        result = parse_park_filename("Termico-1_250924_Adhesion Energy_Forward_021")
        assert result is not None
        assert result['channel'] == 'Adhesion Energy'

    def test_session_key_groups_siblings(self):
        """PARK-04: Session key groups files from same scan."""
        key1 = session_key("Termico-1_250924_Z Height_Backward_021")
        key2 = session_key("Termico-1_250924_Modulus_Forward_021")
        key3 = session_key("Termico-1_250924_PinPoint_Backward_021")
        assert key1 == key2 == key3 == "Termico-1_250924_021"

    def test_session_key_separates_scans(self):
        """PARK-05: Different scan numbers produce different keys."""
        key1 = session_key("Termico-1_250924_Z Height_Backward_021")
        key2 = session_key("Termico-1_250924_Z Height_Backward_022")
        assert key1 != key2

    def test_parse_invalid_name_returns_none(self):
        """PARK-06: Invalid filename returns None."""
        assert parse_park_filename("random_file") is None
        assert session_key("random_file") is None


# =============================================================================
# Loader Basic Tests
# =============================================================================

class TestParkAFMLoaderBasic:
    """Basic tests for ParkAFMLoader."""

    def test_loader_creation(self, loader):
        """PARK-07: Can create loader instance."""
        assert loader is not None
        assert loader.loader_type == 'park_afm'

    def test_supported_extensions(self, loader):
        """PARK-08: Loader has correct extensions."""
        assert '.ps-ppt' in loader.supported_extensions
        assert '.tiff' in loader.supported_extensions

    def test_load_nonexistent_raises(self, loader, tmp_path):
        """PARK-09: Loading nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            loader.load_single_file(tmp_path / "nonexistent.ps-ppt")


# =============================================================================
# TIFF Loading Tests
# =============================================================================

class TestParkTIFFLoading:
    """Tests for Park TIFF loading."""

    def test_load_park_tiff_data(self, sample_tiff_file):
        """PARK-10: Load float32 data from Park TIFF tag 50434."""
        filepath, expected_data = sample_tiff_file
        data, meta = load_park_tiff(filepath)

        assert data.shape == (32, 32)
        assert data.dtype == np.float32
        np.testing.assert_array_almost_equal(data, expected_data, decimal=5)

    def test_load_park_tiff_metadata(self, sample_tiff_file):
        """PARK-11: Extract metadata from Park TIFF tag 50435."""
        filepath, _ = sample_tiff_file
        data, meta = load_park_tiff(filepath)

        assert meta['channel'] == 'Z Height'
        assert meta['scan_mode'] == 'Contact'
        assert meta['scan_width_um'] == pytest.approx(5.0)
        assert meta['scan_height_um'] == pytest.approx(5.0)
        assert meta['direction'] == 'Backward'

    def test_load_tiff_as_spectral(self, loader, sample_tiff_file):
        """PARK-12: load_single_file for TIFF returns SpectralData."""
        filepath, _ = sample_tiff_file
        result = loader.load_single_file(filepath)

        assert isinstance(result, SpectralData)
        assert result.topography is not None
        assert result.topography.shape == (32, 32)


# =============================================================================
# PS-PPT Parser Tests
# =============================================================================

class TestPsPptParser:
    """Tests for PS-PPT file parsing."""

    def test_parse_metadata(self, sample_ppt_file):
        """PARK-13: Parse metadata from ps-ppt file."""
        filepath, pw, ph, _ = sample_ppt_file
        parser = PsPptParser(filepath)
        meta = parser.parse_metadata()

        assert meta['pixel_width'] == pw
        assert meta['pixel_height'] == ph
        assert meta['scan_width_um'] == 5
        assert meta['scan_height_um'] == 5
        assert meta['is_forward'] is True
        assert len(meta['channels']) == 3
        assert meta['channels'][1]['id'] == 'Force'

    def test_load_force_map(self, sample_ppt_file):
        """PARK-14: Load force curves from ps-ppt file."""
        filepath, pw, ph, n_pts = sample_ppt_file
        parser = PsPptParser(filepath)
        parser.parse_metadata()

        curves, z_curves = parser.load_force_map(target_channel='Force')

        n_pixels = pw * ph
        assert curves.shape[0] == n_pixels
        assert curves.shape[1] == n_pts
        assert z_curves.shape[0] == n_pixels

        # Check Z axis is monotonic (linspace 1.0 to 2.0)
        z_first_pixel = z_curves[0, :n_pts]
        assert z_first_pixel[0] == pytest.approx(1.0, abs=0.01)
        assert z_first_pixel[-1] == pytest.approx(2.0, abs=0.01)

    def test_load_force_map_invalid_channel(self, sample_ppt_file):
        """PARK-15: Requesting missing channel raises ValueError."""
        filepath, _, _, _ = sample_ppt_file
        parser = PsPptParser(filepath)
        parser.parse_metadata()

        with pytest.raises(ValueError, match="not found"):
            parser.load_force_map(target_channel='NonExistent')

    def test_invalid_magic_raises(self, tmp_path):
        """PARK-16: Invalid magic number raises ValueError."""
        bad_file = tmp_path / "bad.ps-ppt"
        bad_file.write_bytes(b'NOT-A-PPT\n' + b'\x00' * 200)

        parser = PsPptParser(bad_file)
        with pytest.raises(ValueError, match="Not a PS-PPT"):
            parser.parse_metadata()


# =============================================================================
# SpectralData Integration Tests
# =============================================================================

class TestParkSpectralData:
    """Tests for loading ps-ppt as SpectralData."""

    def test_load_ppt_as_spectral(self, loader, sample_ppt_file):
        """PARK-17: load_single_file for ps-ppt returns SpectralData."""
        filepath, pw, ph, n_pts = sample_ppt_file
        result = loader.load_single_file(filepath)

        assert isinstance(result, SpectralData)
        # DataFrame: Z_um column + pixel columns
        assert result._data.shape[0] == n_pts
        assert result._data.shape[1] == pw * ph + 1  # +1 for Z_um column
        assert result._data.columns[0] == 'Z_um'

    def test_spectral_metadata(self, loader, sample_ppt_file):
        """PARK-18: SpectralData has correct metadata."""
        filepath, pw, ph, _ = sample_ppt_file
        result = loader.load_single_file(filepath)

        assert result.metadata.source_type == 'park_afm'
        assert result.metadata.dimensions == (pw, ph)
        assert result.metadata.scan_mode == 'pinpoint'
        assert result.metadata.units['independent'] == 'um'


# =============================================================================
# Smart Import Tests
# =============================================================================

class TestParkSmartImport:
    """Tests for smart import sibling discovery."""

    def test_smart_import_discovers_siblings(self, loader, tmp_path,
                                             sample_tiff_file, sample_ppt_file):
        """PARK-19: Smart import finds TIFF and ps-ppt siblings."""
        # Create sibling files with matching session key
        ppt_path, _, _, _ = sample_ppt_file

        # Create a matching TIFF in the same directory
        tiff_src, _ = sample_tiff_file
        # Copy with matching session key
        import shutil
        tiff_dst = tmp_path / "Test_250924_Z Height_Backward_001.tiff"
        shutil.copy(tiff_src, tiff_dst)

        result, topo = loader.smart_load_from_file(ppt_path)

        assert isinstance(result, SpectralData)
        # Should have channels from both ps-ppt and tiff
        channels = result.metadata.additional_info.get('channels', {})
        assert len(channels) >= 1  # At least the Force channel

    def test_smart_import_fallback_single(self, loader, tmp_path):
        """PARK-20: Smart import falls back to single file for unparseable names."""
        # Create a file with non-standard name
        filepath = tmp_path / "weirdname.ps-ppt"

        # Build a minimal valid ps-ppt
        events = [
            json.dumps({"type": "scan.start", "geometry": {
                "pixelWidth": 2, "pixelHeight": 2,
                "width": 1, "height": 1,
                "direction": "forward", "offsetX": 0, "offsetY": 0, "rotation": 0,
            }, "time": "2025/01/01 00:00:00"}),
            json.dumps({"type": "ppt.param", "cantilever": {"name": "test"}}),
        ]
        for slow in range(2):
            for fast in range(2):
                force = np.zeros(10, dtype=np.float32)
                z = np.linspace(0, 1, 10, dtype=np.float32)
                events.append(json.dumps({
                    "type": "ppt.rtfd",
                    "info": {
                        "channels": [
                            {"id": "Force", "unit": "volt"},
                            {"id": "ZHeight", "unit": "micrometer"},
                        ],
                        "forward": True,
                        "index": {"fast": fast, "slow": slow},
                    },
                    "numbers": [
                        base64.b64encode(force.tobytes()).decode(),
                        base64.b64encode(z.tobytes()).decode(),
                    ],
                }))
        events.append(json.dumps({"type": "scan.stop"}))

        event_stream = '\n'.join(events).encode('utf-8')
        magic = b'PS-PPT/v1\n'
        header = bytes([1, 4, 16, 0]) + b'\x00' * 16

        n_events = len(events)
        data_start = 30 + n_events * 8 + 16

        index = bytearray()
        offset = data_start
        for i, ev in enumerate(events):
            index += pack('>I', offset)
            index += bytes([0x10 if i < 2 else 0x11, 0, 0, 0])
            offset += len(ev.encode('utf-8')) + 1

        padding = data_start - len(magic) - len(header) - len(index)
        filepath.write_bytes(magic + header + bytes(index) + b'\x00' * max(0, padding) + event_stream)

        result, topo = loader.smart_load_from_file(filepath)
        assert isinstance(result, SpectralData)


# =============================================================================
# Directory Loading Tests
# =============================================================================

class TestParkDirectoryLoading:
    """Tests for directory loading."""

    def test_load_from_directory_tiff_only(self, loader, sample_tiff_file):
        """PARK-21: load_from_directory works with TIFF-only folder."""
        filepath, _ = sample_tiff_file
        sd, topo = loader.load_from_directory(filepath.parent)

        assert isinstance(sd, SpectralData)
        # Z Height TIFF should produce topography
        assert topo is not None
        assert isinstance(topo, TopographyData)

    def test_load_empty_directory_raises(self, loader, tmp_path):
        """PARK-22: Empty directory raises ValueError."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(ValueError, match="No .ps-ppt or .tiff"):
            loader.load_from_directory(empty_dir)
