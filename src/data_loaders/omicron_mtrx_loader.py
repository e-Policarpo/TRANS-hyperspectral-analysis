# ============================================================================
# T.R.A.N.S. version 1.0
# Tools for Research and Analysis for Nano Spectroscopy
#
# Created by Eduarda Policarpo, in November of 2025 with love.
#
# File: omicron_mtrx_loader.py
# Description: Loader for Omicron Matrix STS (I(V)_mtrx) files
#
# Based on previous work on Matrix file handling by Marek (June 2022)
# Original implementation: matrixFileHandling.py
# ============================================================================

"""
Omicron Matrix STS Data Loader

Loader for Scanning Tunneling Spectroscopy data from Omicron Matrix microscopes.
Handles .I(V)_mtrx files and associated .mtrx header files.

File Format Details:
- Magic number: ONTMATRX0101 (12 bytes)
- Block tags: TLKB (timestamp), CSED (description), ATAD (data)
- Data: 32-bit signed integers requiring scaling from header parameters
- Header file (.mtrx) contains scaling parameters and voltage range
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from struct import unpack
from datetime import datetime
import logging
import os
import re

from .base_loader import BaseDataLoader
from ..models.spectral_data import SpectralData, SpectralMetadata
from ..models.topography_data import TopographyData

logger = logging.getLogger(__name__)


class OmicronMatrixSTSLoader(BaseDataLoader):
    """
    Loader for Omicron Matrix STS (Scanning Tunneling Spectroscopy) data.

    This loader handles .I(V)_mtrx files from Omicron Matrix STM systems and creates
    standardized SpectralData objects. It parses the binary file format and
    associated .mtrx header files for parameter extraction.

    File Format:
    - Magic number: ONTMATRX0101
    - Tags: TLKB (timestamp), CSED (description), ATAD (data)
    - Data: 32-bit signed integers requiring scaling from header parameters
    """

    MAGIC_NUMBER = b'ONTMATRX0101'

    def __init__(self):
        """Initialize Omicron Matrix STS loader."""
        super().__init__()
        self.supported_extensions = ['.I(V)_mtrx']
        self.loader_type = 'omicron_matrix_sts'

        # Storage for parsed parameters
        self.parameter: Dict[str, Any] = {}
        self.timestamp: Optional[datetime] = None
        self.header_path: Optional[Path] = None

    def load_from_directory(self, directory: Path, progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
        """
        Load STS data from directory of .I(V)_mtrx files.

        Each file contains forward and backward voltage sweeps. This method:
        1. Splits each file into forward/backward/mixed
        2. Groups spectra by voltage point count
        3. Returns Mixed as main dataset, Forward/Backward as additional channels

        Parameters:
        -----------
        directory : Path
            Directory containing .I(V)_mtrx files
        progress_callback : callable, optional
            Callback function(current, total, message) for progress updates

        Returns:
        --------
        spectral_data : SpectralData
            Concatenated spectral data (Mixed channel as main data)
        topography : TopographyData or None
            Associated topography if Z_flat file found
        """
        directory = Path(directory)

        if not self.validate_directory(directory):
            raise ValueError(f"Invalid directory: {directory}")

        # Find all matrix files by extension type
        file_types = {}

        # I(V) spectroscopy files
        iv_files = [f for f in directory.iterdir() if f.name.endswith('.I(V)_mtrx')]
        if iv_files:
            file_types['I(V)'] = iv_files

        # I(Z) spectroscopy files
        iz_files = [f for f in directory.iterdir() if f.name.endswith('.I(Z)_mtrx')]
        if iz_files:
            file_types['I(Z)'] = iz_files

        # Z(V) spectroscopy files
        zv_files = [f for f in directory.iterdir() if f.name.endswith('.Z(V)_mtrx')]
        if zv_files:
            file_types['Z(V)'] = zv_files

        if not file_types:
            raise ValueError(f"No supported .mtrx files found in {directory}")

        total_files = sum(len(files) for files in file_types.values())
        logger.info(f"Loading {total_files} matrix files from {directory}")
        logger.info(f"File types found: {list(file_types.keys())}")

        # Storage for channels - group by (extension, n_points, sweep_direction)
        # {(ext, n_points): {'V': array, 'forward': [], 'backward': [], 'mixed': [], 'files': []}}
        channels = {}
        topography = None
        processed = 0

        # Process each file type
        for ext_type, files in file_types.items():
            for filepath in sorted(files):
                try:
                    if progress_callback:
                        progress_callback(processed, total_files, f"Loading {filepath.name}")

                    logger.debug(f"Processing {ext_type} file: {filepath.name}")

                    # Parse the file (now returns dict with forward/backward/mixed)
                    parsed = self._parse_iv_file(filepath)

                    if parsed is not None:
                        V = parsed['V']
                        n_points = parsed['n_points']
                        key = (ext_type, n_points)

                        if key not in channels:
                            channels[key] = {
                                'V': V,
                                'forward': [],
                                'backward': [],
                                'mixed': [],
                                'files': [],
                                'ext_type': ext_type,
                                'n_points': n_points
                            }

                        channels[key]['forward'].append(parsed['forward'])
                        channels[key]['backward'].append(parsed['backward'])
                        channels[key]['mixed'].append(parsed['mixed'])
                        channels[key]['files'].append(filepath.name)

                    processed += 1

                except Exception as e:
                    logger.error(f"Error processing {filepath.name}: {e}")
                    processed += 1
                    continue

        if not channels:
            raise ValueError("No spectral data could be extracted")

        # Find topography from Z_flat files (not Z_mtrx which are 1D during spectroscopy)
        topography = self._find_flat_topography(directory)

        # Create SpectralData from the largest channel group
        # Sort channels by number of spectra (descending)
        sorted_channels = sorted(channels.items(), key=lambda x: len(x[1]['mixed']), reverse=True)

        # Use the channel with most spectra as the main dataset
        main_key, main_channel = sorted_channels[0]
        ext_type, n_points = main_key
        n_spectra = len(main_channel['mixed'])

        logger.info(f"Main channel: {ext_type} with {n_points} points, {n_spectra} spectra")
        logger.info(f"Each spectrum has Forward, Backward, and Mixed channels")

        # Stack spectra for main channel (use Mixed as the main data)
        V_common = main_channel['V']
        mixed_stacked = np.column_stack(main_channel['mixed'])
        forward_stacked = np.column_stack(main_channel['forward'])
        backward_stacked = np.column_stack(main_channel['backward'])

        # Create main DataFrame with Mixed data
        column_names = [f"Point_{i+1}" for i in range(n_spectra)]
        df = pd.DataFrame(mixed_stacked, columns=column_names)
        df.insert(0, "V", V_common)

        # Infer dimensions
        dim_guess = int(np.sqrt(n_spectra))
        if dim_guess * dim_guess == n_spectra:
            dimensions = (dim_guess, dim_guess)
        else:
            dimensions = (n_spectra, 1)

        # Build sweep direction channels (Forward, Backward)
        sweep_channels = {}

        # Forward channel
        forward_df = pd.DataFrame(forward_stacked, columns=column_names)
        forward_df.insert(0, "V", V_common)
        sweep_channels['Forward'] = forward_df

        # Backward channel
        backward_df = pd.DataFrame(backward_stacked, columns=column_names)
        backward_df.insert(0, "V", V_common)
        sweep_channels['Backward'] = backward_df

        # Mixed channel (same as main df, but stored for consistency)
        mixed_df = pd.DataFrame(mixed_stacked, columns=column_names)
        mixed_df.insert(0, "V", V_common)
        sweep_channels['Mixed'] = mixed_df

        # Build additional channels info (for different point counts or file types)
        additional_channels = {}
        for key, channel_data in sorted_channels[1:]:
            ch_ext, ch_points = key
            ch_n_spectra = len(channel_data['mixed'])
            ch_col_names = [f"Point_{i+1}" for i in range(ch_n_spectra)]

            # Store all three sweep directions for additional channels
            for sweep_name in ['forward', 'backward', 'mixed']:
                ch_name = f"{ch_ext}_{ch_points}pts_{sweep_name.capitalize()}"
                ch_spectra = np.column_stack(channel_data[sweep_name])
                ch_df = pd.DataFrame(ch_spectra, columns=ch_col_names)
                ch_df.insert(0, "V", channel_data['V'])
                additional_channels[ch_name] = ch_df

            logger.info(f"Additional channel group: {ch_ext}_{ch_points}pts with {ch_n_spectra} spectra")

        # Log if some files had different point counts
        if len(sorted_channels) > 1:
            logger.warning(f"Found {len(sorted_channels)} different spectrum lengths. "
                          f"Main channel uses {n_points} points. "
                          f"Other groups stored as additional channels.")

        # Create metadata
        metadata = self.create_metadata(
            dimensions=dimensions,
            scan_mode="single",
            units={"independent": "V", "dependent": "A", "x": "nm", "y": "nm"},
            n_files=total_files,
            source_directory=str(directory),
            instrument="Omicron Matrix",
            main_channel=f"{ext_type}_{n_points}pts_Mixed",
            sweep_channels=sweep_channels,
            additional_channels=additional_channels
        )

        # Create SpectralData object (Mixed data as main)
        spectral_data = SpectralData(df, metadata,
                                     topography.data if topography else None)

        if progress_callback:
            progress_callback(total_files, total_files, "Complete!")

        self.last_loaded_path = directory
        logger.info(f"Successfully loaded STS data with Forward/Backward/Mixed channels: {spectral_data}")

        return spectral_data, topography

    def _find_flat_topography(self, directory: Path) -> Optional[TopographyData]:
        """Find and load topography from Z_flat files in directory."""
        flat_files = [f for f in directory.iterdir()
                      if f.name.endswith('.Z_flat') or f.name.endswith('.I_flat')]

        if not flat_files:
            return None

        # Try to load the first flat file
        try:
            from .omicron_flat_loader import OmicronFlatLoader
            flat_loader = OmicronFlatLoader()
            return flat_loader.load_topography(flat_files[0])
        except Exception as e:
            logger.warning(f"Could not load flat topography: {e}")
            return None

    def load_single_file(self, filepath: Path) -> SpectralData:
        """
        Load data from a single .I(V)_mtrx file.

        Returns the mixed (forward+backward average) data as the main dataset,
        with forward and backward channels stored in metadata.

        Parameters:
        -----------
        filepath : Path
            Path to .I(V)_mtrx file

        Returns:
        --------
        spectral_data : SpectralData
            Spectral data from the file (mixed channel as main data)
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        if not filepath.name.endswith('.I(V)_mtrx'):
            raise ValueError(f"Expected .I(V)_mtrx file, got {filepath.suffix}")

        logger.info(f"Loading single file: {filepath}")

        # Parse the file
        parsed = self._parse_iv_file(filepath)

        if parsed is None:
            raise ValueError(f"Could not parse I-V data from {filepath}")

        V = parsed['V']
        forward_data = parsed['forward']
        backward_data = parsed['backward']
        mixed_data = parsed['mixed']

        # Create main DataFrame with mixed data
        df = pd.DataFrame({
            "V": V,
            "Forward": forward_data,
            "Backward": backward_data,
            "Mixed": mixed_data
        })

        dimensions = (1, 1)

        # Create separate DataFrames for channels (stored in metadata)
        forward_df = pd.DataFrame({"V": V, "Current": forward_data})
        backward_df = pd.DataFrame({"V": V, "Current": backward_data})
        mixed_df = pd.DataFrame({"V": V, "Current": mixed_data})

        # Create metadata
        metadata = self.create_metadata(
            dimensions=dimensions,
            scan_mode="single",
            units={"independent": "V", "dependent": "A"},
            source_file=str(filepath),
            instrument="Omicron Matrix",
            timestamp=str(self.timestamp) if self.timestamp else None,
            sweep_channels={
                'Forward': forward_df,
                'Backward': backward_df,
                'Mixed': mixed_df
            }
        )

        spectral_data = SpectralData(df, metadata)

        self.last_loaded_path = filepath
        logger.info(f"Successfully loaded single file with forward/backward/mixed channels: {spectral_data}")

        return spectral_data

    def _parse_iv_file(self, filepath: Path) -> Dict[str, Any]:
        """
        Parse I(V)_mtrx file to extract voltage and current data.

        Each file contains a forward and backward voltage sweep concatenated.
        This method splits them and returns three channels: forward, backward, and mixed.

        Parameters:
        -----------
        filepath : Path
            Path to .I(V)_mtrx file

        Returns:
        --------
        result : Dict or None
            Dictionary with keys:
            - 'V': voltage array (for the half-sweep)
            - 'forward': forward sweep current data
            - 'backward': backward sweep current data (reordered to match forward direction)
            - 'mixed': average of forward and backward
            Returns None if parsing fails.
        """
        # First, try to find and parse the header file
        header_path = self._find_header(filepath)
        if header_path:
            try:
                self._parse_header(header_path, filepath)
            except Exception as e:
                logger.warning(f"Could not parse header file: {e}")

        # Now parse the data file
        try:
            with open(filepath, 'rb') as f:
                # Check magic number
                magic = f.read(12)
                if magic != self.MAGIC_NUMBER:
                    logger.error(f"Invalid magic number in {filepath}")
                    return None

                data = None
                datasize = 0

                # Read tags
                while True:
                    tag = f.read(4)
                    if len(tag) < 4:
                        break

                    try:
                        tag_str = tag.decode('ascii')
                    except UnicodeDecodeError:
                        break

                    if tag_str == 'TLKB':
                        f.read(4)  # filesize
                        timestamp_val = unpack('<L', f.read(4))[0]
                        self.timestamp = datetime.fromtimestamp(timestamp_val)
                        f.read(8)  # padding

                    elif tag_str == 'CSED':
                        blocksize = unpack('<i', f.read(4))[0]
                        f.read(blocksize)  # description

                    elif tag_str == 'ATAD':
                        datasize = unpack('<i', f.read(4))[0]
                        data = f.read(datasize)
                        break

                    else:
                        # Unknown tag, try to skip
                        try:
                            blocksize = unpack('<i', f.read(4))[0]
                            f.read(blocksize + 8)
                        except:
                            break

                if data is None:
                    logger.error(f"No data block found in {filepath}")
                    return None

                # Unpack data as 32-bit integers
                n_points_total = datasize // 4
                dataformat = f'<{n_points_total}i'
                raw_data = np.array(unpack(dataformat, data), dtype=np.float64)

                # Scale data if we have parameters
                scaled_data = self._scale_data(raw_data)

                # Split into forward and backward sweeps
                # First half is forward sweep, second half is backward sweep
                n_points = n_points_total // 2

                if n_points_total % 2 != 0:
                    logger.warning(f"Odd number of points ({n_points_total}), truncating last point")

                forward_data = scaled_data[:n_points]
                backward_data_raw = scaled_data[n_points:n_points * 2]

                # Reverse backward data to align with forward direction
                # (backward sweep goes from V_end to V_start, so we flip it)
                backward_data = backward_data_raw[::-1]

                # Calculate mixed (average of forward and backward)
                mixed_data = (forward_data + backward_data) / 2

                # Determine voltage array (for the half-sweep, not full)
                V = self._get_voltage_array(forward_data)

                logger.debug(f"Split {n_points_total} points into forward/backward "
                           f"({n_points} points each)")

                return {
                    'V': V,
                    'forward': forward_data,
                    'backward': backward_data,
                    'mixed': mixed_data,
                    'n_points': n_points
                }

        except Exception as e:
            logger.error(f"Error parsing {filepath}: {e}")
            return None

    def _find_header(self, filepath: Path) -> Optional[Path]:
        """Find the associated .mtrx header file."""
        # Header filename pattern: base_0001.mtrx
        filename = filepath.name
        # Extract base name (before --N_M.I(V)_mtrx)
        base = filename.rsplit('--', 1)[0]
        header_name = f"{base}_0001.mtrx"
        header_path = filepath.parent / header_name

        if header_path.exists():
            return header_path

        # Try to find any .mtrx file in the directory
        mtrx_files = list(filepath.parent.glob("*_0001.mtrx"))
        if mtrx_files:
            return mtrx_files[0]

        return None

    def _parse_header(self, header_path: Path, target_file: Path):
        """
        Parse .mtrx header file to extract parameters.

        Parameters:
        -----------
        header_path : Path
            Path to .mtrx header file
        target_file : Path
            Path to the target data file
        """
        self.parameter = {'BREF': '', 'XFER': {}, 'DICT': {}}
        target_filename = target_file.name

        try:
            with open(header_path, 'rb') as f:
                # Check magic number
                magic = f.read(12)
                if magic != self.MAGIC_NUMBER:
                    logger.error(f"Invalid magic number in header {header_path}")
                    return

                # Read tags until we find the right BREF
                while self.parameter['BREF'] != target_filename:
                    tag = f.read(4)
                    if len(tag) < 4:
                        break

                    try:
                        tag_str = tag.decode('ascii')
                    except UnicodeDecodeError:
                        break

                    if tag_str == 'APEE':
                        # Parameter block
                        block_size = unpack('<i', f.read(4))[0]
                        f.read(4)  # date
                        f.read(4)  # padding
                        apee = f.read(block_size)
                        self._parse_apee_block(apee)

                    elif tag_str == 'YSCC':
                        # Channel configuration
                        block_size = unpack('<i', f.read(4))[0]
                        f.read(4)  # date
                        f.read(4)  # padding
                        yscc = f.read(block_size)
                        self._parse_yscc_block(yscc)

                    elif tag_str == 'FERB':
                        # File reference
                        block_size = unpack('<i', f.read(4))[0]
                        f.read(4)  # date
                        f.read(4)  # padding
                        ferb = f.read(block_size)
                        size = unpack('<i', ferb[4:8])[0]
                        self.parameter['BREF'] = ferb[8:8 + size * 2].decode('utf-16')

                    else:
                        # Skip unknown blocks
                        try:
                            block_size = unpack('<i', f.read(4))[0]
                            f.read(8)  # date + padding
                            f.read(block_size)
                        except:
                            break

        except Exception as e:
            logger.warning(f"Error parsing header {header_path}: {e}")

    def _parse_apee_block(self, apee: bytes):
        """Parse APEE (parameter) block."""
        try:
            num_groups = unpack('<i', apee[4:8])[0]
            x = 8

            for _ in range(num_groups):
                size = unpack('<i', apee[x:x + 4])[0]
                x += 4
                groupname = apee[x:x + size * 2].decode('utf-16')
                x += size * 2
                num_params = unpack('<i', apee[x:x + 4])[0]
                x += 4

                for _ in range(num_params):
                    size = unpack('<i', apee[x:x + 4])[0]
                    x += 4
                    param = apee[x:x + size * 2].decode('utf-16')
                    x += size * 2
                    size = unpack('<i', apee[x:x + 4])[0]
                    x += 4
                    unit = apee[x:x + size * 2].decode('utf-16')
                    x += size * 2
                    x += 4  # padding
                    data, x = self._read_data_value(apee, x)
                    name = f"{groupname}.{param}"
                    self.parameter[name] = [data, unit]

        except Exception as e:
            logger.debug(f"Error parsing APEE block: {e}")

    def _parse_yscc_block(self, yscc: bytes):
        """Parse YSCC (channel configuration) block."""
        try:
            x = 4
            while x < len(yscc):
                tag = yscc[x:x + 4].decode('ascii')
                x += 4
                blocksize = unpack('<i', yscc[x:x + 4])[0]
                x += 4
                x0 = x

                if tag == 'REFX':
                    # Transfer function
                    x += 4  # skip
                    group_number = unpack('<i', yscc[x:x + 4])[0]
                    x += 4
                    size = unpack('<i', yscc[x:x + 4])[0]
                    x += 4
                    groupname = yscc[x:x + size * 2].decode('utf-16')
                    x += size * 2
                    size = unpack('<i', yscc[x:x + 4])[0]
                    x += 4
                    unit = yscc[x:x + size * 2].decode('utf-16')
                    x += size * 2
                    num_params = unpack('<i', yscc[x:x + 4])[0]
                    x += 4

                    xfer_data = {}
                    for _ in range(num_params):
                        size = unpack('<i', yscc[x:x + 4])[0]
                        x += 4
                        param = yscc[x:x + size * 2].decode('utf-16')
                        x += size * 2
                        data, x = self._read_data_value(yscc, x)
                        xfer_data[param] = [data]

                    self.parameter["XFER"][f"XFER_{group_number}"] = [groupname, unit, xfer_data]
                else:
                    x = x0 + blocksize

        except Exception as e:
            logger.debug(f"Error parsing YSCC block: {e}")

    def _read_data_value(self, data: bytes, offset: int) -> Tuple[Any, int]:
        """Read a typed data value from binary data."""
        try:
            type_tag = data[offset:offset + 4].decode('ascii')
            offset += 4

            if type_tag == 'LOOB':
                val = bool(unpack('<L', data[offset:offset + 4])[0])
                offset += 4
            elif type_tag == 'GNOL':
                val = unpack('<l', data[offset:offset + 4])[0]
                offset += 4
            elif type_tag == 'BUOD':
                val = unpack('<d', data[offset:offset + 8])[0]
                offset += 8
            elif type_tag == 'GRTS':
                size = unpack('<i', data[offset:offset + 4])[0]
                offset += 4
                val = data[offset:offset + size * 2].decode('utf-16')
                offset += size * 2
            else:
                val = None

            return val, offset
        except:
            return None, offset

    def _scale_data(self, raw_data: np.ndarray) -> np.ndarray:
        """Scale raw data using transfer function parameters."""
        # Try to find the I(V) transfer function
        for key in self.parameter.get('XFER', {}):
            xfer = self.parameter['XFER'][key]
            if len(xfer) >= 3 and isinstance(xfer[2], dict):
                xfer_params = xfer[2]

                if xfer[0] == 'TFF_Linear1D':
                    # Linear scaling: (data - offset) / factor
                    offset = xfer_params.get('Offset', [0])[0] if 'Offset' in xfer_params else 0
                    factor = xfer_params.get('Factor', [1])[0] if 'Factor' in xfer_params else 1
                    if factor != 0:
                        return (raw_data - offset) / factor
                else:
                    # MultiLinear scaling
                    raw_1 = xfer_params.get('Raw_1', [1])[0] if 'Raw_1' in xfer_params else 1
                    pre_offset = xfer_params.get('PreOffset', [0])[0] if 'PreOffset' in xfer_params else 0
                    offset = xfer_params.get('Offset', [0])[0] if 'Offset' in xfer_params else 0
                    neutral_factor = xfer_params.get('NeutralFactor', [1])[0] if 'NeutralFactor' in xfer_params else 1
                    pre_factor = xfer_params.get('PreFactor', [1])[0] if 'PreFactor' in xfer_params else 1

                    denominator = neutral_factor * pre_factor
                    if denominator != 0:
                        return (raw_1 - pre_offset) * (raw_data - offset) / denominator

        # If no transfer function found, apply default scaling
        # Typical current values are in nA range
        logger.warning("No transfer function found, using default scaling (nA)")
        return raw_data * 1e-9

    def _get_voltage_array(self, current_data: np.ndarray) -> np.ndarray:
        """Get or generate voltage array based on parameters."""
        n_points = len(current_data)

        # Try to get from parameters
        v_start = self.parameter.get('Spectroscopy.Device_1_Start', [None])[0]
        v_end = self.parameter.get('Spectroscopy.Device_1_End', [None])[0]

        if v_start is not None and v_end is not None:
            return np.linspace(v_start, v_end, n_points)

        # Default voltage range for typical STS measurements
        logger.warning("Using default voltage range: -1V to +1V")
        return np.linspace(-1.0, 1.0, n_points)

    def _find_topography(self, iv_filepath: Path) -> Optional[TopographyData]:
        """Find associated topography file (.Z_mtrx)."""
        # Try to find Z_mtrx file with same base name
        base = iv_filepath.name.rsplit('.', 1)[0]  # Remove .I(V)_mtrx
        z_files = list(iv_filepath.parent.glob(f"{base.rsplit('.', 1)[0]}*.Z_mtrx"))

        if z_files:
            try:
                z_data = self._parse_z_mtrx(z_files[0])
                if z_data is not None:
                    return TopographyData.from_array(z_data)
            except Exception as e:
                logger.warning(f"Could not load topography from {z_files[0]}: {e}")

        return None

    def _parse_z_mtrx(self, filepath: Path) -> Optional[np.ndarray]:
        """
        Parse Z_mtrx topography file.

        Returns 2D topography data only. Returns None for:
        - 1D spectroscopy Z position data (not a topography image)
        - Files that cannot be reshaped to a valid 2D image
        - Images smaller than minimum size (16x16)
        """
        MIN_TOPO_SIZE = 16  # Minimum pixels per side for valid topography

        try:
            with open(filepath, 'rb') as f:
                magic = f.read(12)
                if magic != self.MAGIC_NUMBER:
                    return None

                data = None
                datasize = 0

                while True:
                    tag = f.read(4)
                    if len(tag) < 4:
                        break

                    tag_str = tag.decode('ascii', errors='ignore')

                    if tag_str == 'ATAD':
                        datasize = unpack('<i', f.read(4))[0]
                        data = f.read(datasize)
                        break
                    elif tag_str in ['TLKB', 'CSED']:
                        if tag_str == 'TLKB':
                            f.read(16)
                        else:
                            blocksize = unpack('<i', f.read(4))[0]
                            f.read(blocksize)
                    else:
                        break

                if data:
                    n_points = datasize // 4
                    raw = np.array(unpack(f'<{n_points}i', data), dtype=np.float64)

                    # Only return 2D data that forms a valid topography image
                    side = int(np.sqrt(n_points))
                    if side * side == n_points and side >= MIN_TOPO_SIZE:
                        logger.debug(f"Valid topography: {side}x{side} from {filepath.name}")
                        return raw.reshape(side, side)
                    else:
                        # This is likely 1D spectroscopy Z data, not a topography image
                        logger.debug(f"Skipping non-topography Z_mtrx: {n_points} points "
                                   f"(not a valid {MIN_TOPO_SIZE}x{MIN_TOPO_SIZE}+ image)")
                        return None

        except Exception as e:
            logger.debug(f"Error parsing Z_mtrx: {e}")

        return None
