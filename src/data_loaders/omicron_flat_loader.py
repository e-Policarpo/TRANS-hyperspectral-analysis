# ============================================================================
# T.R.A.N.S. version 1.0
# Tools for Research and Analysis for Nano Spectroscopy
#
# Created by Eduarda Policarpo, in November of 2025 with love.
#
# File: omicron_flat_loader.py
# Description: Loader for Omicron Matrix STM images (.Z_flat / .I_flat files)
#
# Based on previous work on Matrix file handling by Marek (June 2022)
# Original implementation: matrixFileHandling.py
# ============================================================================

"""
Omicron Matrix Flat File Loader

Loader for STM topography images from Omicron Matrix microscopes.
Handles .Z_flat and .I_flat files which contain processed (flattened) STM images.

File Format (FLAT0100):
- Magic: "FLAT0100" (8 bytes)
- Axis descriptors (trigger, mirror, unit, points, physical range)
- Channel name + transfer function (TFF_MultiLinear1D or TFF_Linear1D)
- Creation metadata (timestamp, sample name, dataset name)
- Data counts (forward points, backward points)
- Raw image data as signed 32-bit integers
- Footer with experiment definition
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from struct import unpack, unpack_from
from datetime import datetime
import logging

from .base_loader import BaseDataLoader
from ..models.spectral_data import SpectralData, SpectralMetadata
from ..models.topography_data import TopographyData

logger = logging.getLogger(__name__)


def _read_utf16(data: bytes, pos: int) -> Tuple[str, int]:
    """Read a length-prefixed UTF-16LE string from binary data."""
    n = unpack_from('<I', data, pos)[0]
    pos += 4
    if n == 0:
        return "", pos
    if n > 50000 or pos + n * 2 > len(data):
        raise ValueError(f"Invalid string length {n} at offset 0x{pos - 4:x}")
    s = data[pos:pos + n * 2].decode('utf-16-le', errors='replace').rstrip('\x00')
    return s, pos + n * 2


class OmicronFlatLoader(BaseDataLoader):
    """
    Loader for Omicron Matrix Flat STM images.

    Handles .Z_flat and .I_flat files with proper structural parsing of the
    FLAT0100 binary format: axis descriptors, transfer functions, metadata,
    and raw int32 image data.
    """

    MAGIC_NUMBER = b'FLAT0100'

    def __init__(self):
        super().__init__()
        self.supported_extensions = ['.Z_flat', '.I_flat']
        self.loader_type = 'omicron_flat'

    def load_from_directory(self, directory: Path, progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
        """Load STM images from directory of flat files."""
        directory = Path(directory)
        flat_files = list(directory.glob("*.Z_flat")) + list(directory.glob("*.I_flat"))

        if not flat_files:
            raise ValueError(f"No .Z_flat or .I_flat files found in {directory}")

        logger.info(f"Loading {len(flat_files)} flat files from {directory}")

        if progress_callback:
            progress_callback(0, len(flat_files), f"Loading {flat_files[0].name}")

        topography = self._load_flat_file(flat_files[0])

        if progress_callback:
            progress_callback(len(flat_files), len(flat_files), "Complete!")

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
        """Load data from a single flat file."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        logger.info(f"Loading single file: {filepath}")
        topography = self._load_flat_file(filepath)

        if topography is None:
            raise ValueError(f"Could not load topography from {filepath}")

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
        """Load topography directly from a flat file."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        topography = self._load_flat_file(filepath)
        if topography is None:
            raise ValueError(f"Could not load topography from {filepath}")
        return topography

    def _load_flat_file(self, filepath: Path) -> Optional[TopographyData]:
        """Parse a FLAT0100 file and return TopographyData."""
        try:
            content = filepath.read_bytes()

            if content[:8] != self.MAGIC_NUMBER:
                logger.error(f"Invalid magic number in {filepath}: {content[:8]}")
                return None

            parsed = self._parse_flat_header(content)
            if parsed is None:
                return None

            axes = parsed['axes']
            xfer = parsed['transfer_function']
            data_offset = parsed['data_offset']
            data_count = parsed['data_count']

            # Read raw int32 data
            raw = np.frombuffer(
                content[data_offset:data_offset + data_count * 4],
                dtype='<i4'
            ).astype(np.float64)

            # Apply transfer function
            scaled = self._apply_transfer_function(raw, xfer)

            # Reshape: X axis has n_points (includes fwd+bwd), Y axis has n_lines
            nx = axes[0]['n_points']
            ny = axes[1]['n_points']

            if len(scaled) != nx * ny:
                logger.warning(f"Data size mismatch: {len(scaled)} != {nx}*{ny}={nx * ny}")
                # Try to use data_count directly
                if data_count == nx * ny:
                    pass
                else:
                    return None

            image = scaled.reshape(ny, nx)

            # If X axis is mirrored (forward+backward), extract forward half
            if axes[0].get('mirrored'):
                half = nx // 2
                image = image[:, :half]
                logger.info(f"Extracted forward scan: {ny}x{half} from {ny}x{nx}")

            logger.info(f"Loaded flat image: {image.shape}, "
                        f"Z range: [{image.min():.3e}, {image.max():.3e}] "
                        f"({(image.max() - image.min()) * 1e9:.1f} nm)")

            return TopographyData(image)

        except Exception as e:
            logger.error(f"Error loading flat file {filepath}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

    def _parse_flat_header(self, content: bytes) -> Optional[Dict[str, Any]]:
        """
        Parse the FLAT0100 header structure.

        Returns dict with keys: axes, channel, transfer_function, metadata,
                                data_offset, data_count
        """
        try:
            pos = 8  # after magic

            # Axis count
            n_axes = unpack_from('<I', content, pos)[0]
            pos += 4

            axes = []
            for _ in range(n_axes):
                trigger, pos = _read_utf16(content, pos)
                mirror, pos = _read_utf16(content, pos)
                unit, pos = _read_utf16(content, pos)
                n_points = unpack_from('<I', content, pos)[0]; pos += 4
                start = unpack_from('<d', content, pos)[0]; pos += 8
                increment = unpack_from('<d', content, pos)[0]; pos += 8
                end = unpack_from('<d', content, pos)[0]; pos += 8
                mirrored = unpack_from('<I', content, pos)[0]; pos += 4
                _reserved = unpack_from('<I', content, pos)[0]; pos += 4

                axes.append({
                    'trigger': trigger,
                    'mirror': mirror,
                    'unit': unit,
                    'n_points': n_points,
                    'start': start,
                    'increment': increment,
                    'end': end,
                    'mirrored': bool(mirrored),
                })

            # Channel info
            channel_name, pos = _read_utf16(content, pos)
            xfer_name, pos = _read_utf16(content, pos)
            channel_unit, pos = _read_utf16(content, pos)
            n_params = unpack_from('<I', content, pos)[0]; pos += 4

            xfer_params = {}
            for _ in range(n_params):
                pname, pos = _read_utf16(content, pos)
                pval = unpack_from('<d', content, pos)[0]; pos += 8
                xfer_params[pname] = pval

            transfer_function = {
                'name': xfer_name,
                'unit': channel_unit,
                'params': xfer_params,
            }

            # Creation metadata
            field1 = unpack_from('<I', content, pos)[0]; pos += 4
            field2 = unpack_from('<I', content, pos)[0]; pos += 4
            timestamp = unpack_from('<I', content, pos)[0]; pos += 4
            field4 = unpack_from('<I', content, pos)[0]; pos += 4
            comment, pos = _read_utf16(content, pos)

            # Parse comment key-value pairs (e.g. "Sample=MBT Duda;DataSet=...")
            meta = {}
            if comment:
                for pair in comment.split(';'):
                    if '=' in pair:
                        k, v = pair.split('=', 1)
                        meta[k.strip()] = v.strip()

            # Data counts
            data_count = unpack_from('<I', content, pos)[0]; pos += 4
            _data_count2 = unpack_from('<I', content, pos)[0]; pos += 4

            data_offset = pos

            logger.info(f"FLAT header: {n_axes} axes, channel='{channel_name}', "
                        f"xfer='{xfer_name}', data={data_count} points, "
                        f"comment='{comment}'")

            return {
                'axes': axes,
                'channel': channel_name,
                'transfer_function': transfer_function,
                'metadata': meta,
                'timestamp': datetime.fromtimestamp(timestamp) if timestamp else None,
                'data_offset': data_offset,
                'data_count': data_count,
            }

        except Exception as e:
            logger.error(f"Error parsing FLAT header: {e}")
            return None

    def _apply_transfer_function(self, raw_data: np.ndarray,
                                  xfer: Dict[str, Any]) -> np.ndarray:
        """Apply the embedded transfer function to scale raw int32 data."""
        params = xfer.get('params', {})
        name = xfer.get('name', '')

        if 'Linear1D' in name and 'Multi' not in name:
            # TFF_Linear1D: scaled = (raw - Offset) / Factor
            offset = params.get('Offset', 0.0)
            factor = params.get('Factor', 1.0)
            if factor != 0:
                return (raw_data - offset) / factor
            return raw_data

        # TFF_MultiLinear1D: scaled = (Raw_1 - PreOffset) * (raw - Offset)
        #                              / (NeutralFactor * PreFactor)
        raw_1 = params.get('Raw_1', 1.0)
        pre_offset = params.get('PreOffset', 0.0)
        offset = params.get('Offset', 0.0)
        neutral_factor = params.get('NeutralFactor', 1.0)
        pre_factor = params.get('PreFactor', 1.0)

        denom = neutral_factor * pre_factor
        if denom != 0:
            return (raw_1 - pre_offset) * (raw_data - offset) / denom

        logger.warning("Transfer function denominator is zero, returning raw data")
        return raw_data


class OmicronImageLoader(OmicronFlatLoader):
    """Convenience alias for OmicronFlatLoader."""
    pass
