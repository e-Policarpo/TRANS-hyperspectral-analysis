# ============================================================================
# T.R.A.N.S. version 1.0
# Tools for Research and Analysis for Nano Spectroscopy
#
# Created by Eduarda Policarpo, in November of 2025 with love.
#
# File: omicron_flat_loader.py
# Description: Loader for Omicron Matrix STM images (.Z_flat files)
#
# Based on previous work on Matrix file handling by Marek (June 2022)
# Original implementation: matrixFileHandling.py
# ============================================================================

"""
Omicron Matrix Flat File Loader

Loader for STM topography images from Omicron Matrix microscopes.
Handles .Z_flat files which contain processed (flattened) STM images.

File Format Details:
- Magic number: FLAT0100 (8 bytes)
- Self-contained metadata in UTF-16 format
- Transfer function for data scaling
- Image data as 32-bit signed integers
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from struct import unpack
from datetime import datetime
import logging

from .base_loader import BaseDataLoader
from ..models.spectral_data import SpectralData, SpectralMetadata
from ..models.topography_data import TopographyData

logger = logging.getLogger(__name__)


class OmicronFlatLoader(BaseDataLoader):
    """
    Loader for Omicron Matrix Flat STM images.

    This loader handles .Z_flat files from Omicron Matrix STM systems which
    contain processed (flattened) STM topography images with embedded metadata.

    File Format:
    - Magic number: FLAT0100
    - Metadata blocks with transfer function parameters
    - Image data as 32-bit signed integers
    """

    MAGIC_NUMBER = b'FLAT0100'

    def __init__(self):
        """Initialize Omicron Flat loader."""
        super().__init__()
        self.supported_extensions = ['.Z_flat', '.I_flat']
        self.loader_type = 'omicron_flat'

        # Storage for parsed metadata
        self.metadata_dict: Dict[str, Any] = {}
        self.transfer_function: Dict[str, float] = {}
        self.dimensions: Optional[Tuple[int, int]] = None

    def load_from_directory(self, directory: Path, progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
        """
        Load STM images from directory of .Z_flat files.

        Parameters:
        -----------
        directory : Path
            Directory containing .Z_flat files
        progress_callback : callable, optional
            Callback function(current, total, message) for progress updates

        Returns:
        --------
        spectral_data : SpectralData
            Dummy spectral data (not applicable for images)
        topography : TopographyData
            Loaded topography data
        """
        directory = Path(directory)

        # Find all flat files
        flat_files = list(directory.glob("*.Z_flat")) + list(directory.glob("*.I_flat"))

        if not flat_files:
            raise ValueError(f"No .Z_flat or .I_flat files found in {directory}")

        logger.info(f"Loading {len(flat_files)} flat files from {directory}")

        # Load the first file as main topography
        if progress_callback:
            progress_callback(0, len(flat_files), f"Loading {flat_files[0].name}")

        topography = self._load_flat_file(flat_files[0])

        if progress_callback:
            progress_callback(len(flat_files), len(flat_files), "Complete!")

        # Create dummy spectral data (not applicable for pure image files)
        dummy_df = pd.DataFrame({"X": [0], "Y": [0]})
        dummy_metadata = self.create_metadata(
            dimensions=(1, 1),
            scan_mode="image",
            units={"x": "nm", "y": "nm", "z": "m"},
            source_directory=str(directory),
            instrument="Omicron Matrix"
        )
        spectral_data = SpectralData(dummy_df, dummy_metadata,
                                     topography.data if topography else None)

        self.last_loaded_path = directory
        return spectral_data, topography

    def load_single_file(self, filepath: Path) -> SpectralData:
        """
        Load data from a single .Z_flat file.

        Parameters:
        -----------
        filepath : Path
            Path to .Z_flat file

        Returns:
        --------
        spectral_data : SpectralData
            Contains topography data
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        logger.info(f"Loading single file: {filepath}")

        topography = self._load_flat_file(filepath)

        if topography is None:
            raise ValueError(f"Could not load topography from {filepath}")

        # Create spectral data with topography
        dummy_df = pd.DataFrame({"X": [0], "Y": [0]})
        metadata = self.create_metadata(
            dimensions=topography.data.shape if topography else (1, 1),
            scan_mode="image",
            units={"x": "nm", "y": "nm", "z": "m"},
            source_file=str(filepath),
            instrument="Omicron Matrix"
        )
        spectral_data = SpectralData(dummy_df, metadata, topography.data)

        self.last_loaded_path = filepath
        return spectral_data

    def load_topography(self, filepath: Path) -> TopographyData:
        """
        Load topography directly from a .Z_flat file.

        Parameters:
        -----------
        filepath : Path
            Path to .Z_flat file

        Returns:
        --------
        topography : TopographyData
            Loaded topography data
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        topography = self._load_flat_file(filepath)

        if topography is None:
            raise ValueError(f"Could not load topography from {filepath}")

        return topography

    def _load_flat_file(self, filepath: Path) -> Optional[TopographyData]:
        """
        Load and parse a .Z_flat or .I_flat file.

        Parameters:
        -----------
        filepath : Path
            Path to flat file

        Returns:
        --------
        topography : TopographyData or None
            Parsed topography data
        """
        try:
            with open(filepath, 'rb') as f:
                # Check magic number
                magic = f.read(8)
                if magic != self.MAGIC_NUMBER:
                    logger.error(f"Invalid magic number in {filepath}: {magic}")
                    return None

                # Read file content for parsing
                f.seek(0)
                content = f.read()

            # Parse metadata and extract transfer function
            self._parse_flat_metadata(content)

            # Extract image dimensions from metadata
            width, height = self._get_image_dimensions(content)

            if width is None or height is None:
                # Try to guess from file size
                file_size = len(content)
                # Estimate metadata size ~1KB, rest is image data
                data_size = file_size - 2000
                n_pixels = data_size // 4  # 32-bit data
                side = int(np.sqrt(n_pixels))
                if side * side == n_pixels:
                    width = height = side
                else:
                    # Try common sizes
                    for dim in [512, 256, 1024, 128, 2048]:
                        if dim * dim * 4 <= data_size:
                            width = height = dim
                            break
                    if width is None:
                        width = height = 512  # Default

                logger.info(f"Estimated image dimensions: {width}x{height}")
            else:
                logger.info(f"Image dimensions from metadata: {width}x{height}")

            self.dimensions = (width, height)

            # Find and extract image data
            image_data = self._extract_image_data(content, width, height)

            if image_data is None:
                logger.error(f"Could not extract image data from {filepath}")
                return None

            # Apply scaling using transfer function
            scaled_data = self._scale_image_data(image_data)

            # Create TopographyData directly - metadata is created automatically
            return TopographyData(scaled_data)

        except Exception as e:
            logger.error(f"Error loading flat file {filepath}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

    def _parse_flat_metadata(self, content: bytes):
        """
        Parse metadata from flat file content.

        Parameters:
        -----------
        content : bytes
            File content
        """
        self.metadata_dict = {}
        self.transfer_function = {}

        try:
            # Look for UTF-16 encoded metadata strings
            # The file has sections marked with length-prefixed UTF-16 strings

            # Find axis labels
            pos = 8  # Skip magic number
            while pos < min(len(content), 10000):  # Search first 10KB for metadata
                # Look for length prefix (2 bytes)
                if pos + 2 > len(content):
                    break

                # Try to read a length-prefixed UTF-16 string
                try:
                    length = unpack('<H', content[pos:pos+2])[0]
                    if 0 < length < 200 and pos + 2 + length * 2 <= len(content):
                        try:
                            string = content[pos+2:pos+2+length*2].decode('utf-16-le')
                            if string.isprintable() and len(string) > 2:
                                # Parse key-value pairs
                                if '=' in string:
                                    key, value = string.split('=', 1)
                                    self.metadata_dict[key.strip()] = value.strip()
                                elif '::' in string:
                                    # Axis reference like "XYScanner::X"
                                    self.metadata_dict[f'axis_{len(self.metadata_dict)}'] = string
                        except:
                            pass
                except:
                    pass

                pos += 1

            # Look for transfer function parameters
            # Pattern: TFF_MultiLinear1D followed by parameters
            tff_patterns = [
                b'T\x00F\x00F\x00_\x00M\x00u\x00l\x00t\x00i\x00L\x00i\x00n\x00e\x00a\x00r\x00',
                b'T\x00F\x00F\x00_\x00L\x00i\x00n\x00e\x00a\x00r\x001\x00D\x00'
            ]

            for pattern in tff_patterns:
                tff_pos = content.find(pattern)
                if tff_pos > 0:
                    # Parse transfer function parameters after this position
                    self._parse_transfer_function(content, tff_pos)
                    break

            # Look for Sample info
            sample_match = content.find(b'S\x00a\x00m\x00p\x00l\x00e\x00=\x00')
            if sample_match > 0:
                # Extract sample name
                end_pos = content.find(b';', sample_match)
                if end_pos > sample_match:
                    try:
                        sample_str = content[sample_match:end_pos].decode('utf-16-le', errors='ignore')
                        if '=' in sample_str:
                            self.metadata_dict['Sample'] = sample_str.split('=', 1)[1]
                    except:
                        pass

            logger.debug(f"Parsed metadata: {list(self.metadata_dict.keys())}")

        except Exception as e:
            logger.warning(f"Error parsing metadata: {e}")

    def _parse_transfer_function(self, content: bytes, start_pos: int):
        """
        Parse transfer function parameters from file content.

        Parameters:
        -----------
        content : bytes
            File content
        start_pos : int
            Starting position of transfer function block
        """
        try:
            # Search for double values after the transfer function identifier
            # Look for parameter names like "NeutralFactor", "Offset", "PreFactor", etc.

            param_names = ['NeutralFactor', 'Offset', 'PreFactor', 'PreOffset', 'Raw_1', 'Factor']

            for name in param_names:
                # Search for parameter name in UTF-16
                name_utf16 = name.encode('utf-16-le')
                pos = content.find(name_utf16, start_pos)

                if pos > 0 and pos < start_pos + 2000:
                    # Look for a double value after the parameter name
                    # Skip the name and look for 8-byte double
                    search_start = pos + len(name_utf16)

                    for offset in range(0, 50, 2):  # Search nearby
                        try:
                            if search_start + offset + 8 <= len(content):
                                value = unpack('<d', content[search_start+offset:search_start+offset+8])[0]
                                # Check if it's a reasonable value
                                if abs(value) < 1e20 and (abs(value) > 1e-20 or value == 0):
                                    self.transfer_function[name] = value
                                    logger.debug(f"Transfer function {name} = {value}")
                                    break
                        except:
                            continue

        except Exception as e:
            logger.debug(f"Error parsing transfer function: {e}")

    def _get_image_dimensions(self, content: bytes) -> Tuple[Optional[int], Optional[int]]:
        """
        Extract image dimensions from file content.

        Parameters:
        -----------
        content : bytes
            File content

        Returns:
        --------
        width, height : Tuple[int, int] or (None, None)
            Image dimensions
        """
        try:
            # Look for axis information in metadata
            # Common patterns: "Points=512", "Lines=512"

            # Search for Points and Lines in metadata
            points_pattern = b'P\x00o\x00i\x00n\x00t\x00s\x00'
            lines_pattern = b'L\x00i\x00n\x00e\x00s\x00'

            width = None
            height = None

            # Method 1: Look for specific byte patterns after magic number
            # At position 0x66-0x6A, there's often dimension info
            pos = 8
            while pos < min(len(content), 500):
                if content[pos:pos+4] == b'\x00\x02\x00\x00':  # Axis indicator
                    # Read following integers for dimensions
                    try:
                        # Look for dimension values nearby
                        for offset in range(4, 20, 4):
                            val = unpack('<I', content[pos+offset:pos+offset+4])[0]
                            if 64 <= val <= 4096:  # Reasonable image dimension
                                if width is None:
                                    width = val
                                elif height is None:
                                    height = val
                                    break
                    except:
                        pass
                pos += 1

            # Method 2: Search for dimension markers
            if width is None:
                # Look for a sequence of two identical or similar integers (typical for square images)
                for pos in range(8, min(len(content), 300), 2):
                    try:
                        val1 = unpack('<I', content[pos:pos+4])[0]
                        val2 = unpack('<I', content[pos+4:pos+8])[0]
                        if 64 <= val1 <= 4096 and 64 <= val2 <= 4096:
                            # These could be dimensions
                            # Check if the product makes sense with file size
                            expected_data = val1 * val2 * 4
                            if len(content) - 2000 < expected_data < len(content):
                                width = val1
                                height = val2
                                break
                    except:
                        continue

            return width, height

        except Exception as e:
            logger.debug(f"Error getting image dimensions: {e}")
            return None, None

    def _extract_image_data(self, content: bytes, width: int, height: int) -> Optional[np.ndarray]:
        """
        Extract raw image data from file content.

        Parameters:
        -----------
        content : bytes
            File content
        width : int
            Image width
        height : int
            Image height

        Returns:
        --------
        data : np.ndarray or None
            Raw image data
        """
        try:
            expected_size = width * height * 4  # 32-bit data

            # The image data is typically at the end of the file
            # Look backwards from the end for the data block

            # Try finding where metadata ends and data begins
            # Data typically starts after a specific marker or at a known offset

            # Method 1: Calculate offset from file size
            data_start = len(content) - expected_size

            if data_start > 0:
                data_bytes = content[data_start:]
                n_values = len(data_bytes) // 4

                if n_values >= width * height:
                    # Read as signed 32-bit integers
                    raw_data = np.frombuffer(data_bytes[:expected_size], dtype='<i4')
                    return raw_data.reshape(height, width).astype(np.float64)

            # Method 2: Search for data marker patterns
            # Some files have a specific pattern before the data block
            markers = [b'\x00\x00\x00\x00\x08\x00\x00\x00', b'\x00\x08\x00\x00']

            for marker in markers:
                marker_pos = content.rfind(marker)
                if marker_pos > 0 and marker_pos + len(marker) + expected_size <= len(content):
                    data_start = marker_pos + len(marker)
                    if len(content) - data_start >= expected_size:
                        data_bytes = content[data_start:data_start + expected_size]
                        raw_data = np.frombuffer(data_bytes, dtype='<i4')
                        return raw_data.reshape(height, width).astype(np.float64)

            logger.warning(f"Could not locate image data block")
            return None

        except Exception as e:
            logger.error(f"Error extracting image data: {e}")
            return None

    def _scale_image_data(self, raw_data: np.ndarray) -> np.ndarray:
        """
        Apply transfer function scaling to raw image data.

        Parameters:
        -----------
        raw_data : np.ndarray
            Raw integer data

        Returns:
        --------
        scaled : np.ndarray
            Scaled data in physical units
        """
        if not self.transfer_function:
            # Default scaling: assume data is in picometers -> convert to meters
            logger.warning("No transfer function found, using default scaling")
            return raw_data * 1e-12  # pm to m

        # Apply MultiLinear transfer function
        # Formula: (Raw_1 - PreOffset) * (data - Offset) / (NeutralFactor * PreFactor)

        raw_1 = self.transfer_function.get('Raw_1', 1.0)
        pre_offset = self.transfer_function.get('PreOffset', 0.0)
        offset = self.transfer_function.get('Offset', 0.0)
        neutral_factor = self.transfer_function.get('NeutralFactor', 1.0)
        pre_factor = self.transfer_function.get('PreFactor', 1.0)
        factor = self.transfer_function.get('Factor', 1.0)

        # Check for linear (simpler) scaling
        if 'Factor' in self.transfer_function and 'NeutralFactor' not in self.transfer_function:
            # TFF_Linear1D: (data - offset) / factor
            if factor != 0:
                scaled = (raw_data - offset) / factor
            else:
                scaled = raw_data
        else:
            # TFF_MultiLinear1D
            denominator = neutral_factor * pre_factor
            if denominator != 0:
                scaled = (raw_1 - pre_offset) * (raw_data - offset) / denominator
            else:
                scaled = raw_data

        logger.info(f"Applied transfer function scaling, range: [{scaled.min():.3e}, {scaled.max():.3e}]")
        return scaled


class OmicronImageLoader(OmicronFlatLoader):
    """
    Convenience alias for loading Omicron STM images.
    Identical to OmicronFlatLoader but with a more intuitive name.
    """
    pass
