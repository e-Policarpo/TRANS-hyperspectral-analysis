# ============================================================================
# T.R.A.N.S. version 1.0
# Tools for Research and Analysis for Nano Spectroscopy
#
# Created by Eduarda Policarpo, in November of 2025 with love.
#
# File: omicron_mtrx_loader.py
# Description: Loader for Omicron Matrix STS/STM files
#              Handles .I(V)_mtrx, .Aux2(V)_mtrx, .I_mtrx, .Z_mtrx,
#              .Z_flat, .I_flat, and _0001.mtrx header files.
#
# Based on previous work on Matrix file handling by Marek (June 2022)
# Original implementation: matrixFileHandling.py
# ============================================================================

"""
Omicron Matrix Data Loader

Comprehensive loader for Scanning Tunneling Microscopy data from Omicron/Scienta
Omicron Matrix microscopes. Supports:

- Spectroscopy data files: .I(V)_mtrx, .Aux2(V)_mtrx, .I(Z)_mtrx, .Z(V)_mtrx
- Scanning image data: .I_mtrx, .Z_mtrx
- Flat (processed) images: .Z_flat, .I_flat
- Session header files: _0001.mtrx

Data File Format (ONTMATRX0101):
- Magic number: ONTMATRX0101 (12 bytes)
- Block tags: TLKB (timestamp), CSED (description), ATAD (data)
- Data: 32-bit signed integers requiring scaling from header parameters

Header File Format (_0001.mtrx):
- Same magic number
- Block tags: ATEM, DPXE, APEE (parameters), YSCC (transfer functions),
              FERB (file references), KRAM (annotations)

Smart Import:
- Pick one data file OR a _0001.mtrx header
- Parse the header to discover all session files via FERB blocks
- Extract sample name, dataset name from KRAM annotations
- Load all matching files from the session directory
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from struct import unpack, unpack_from
from datetime import datetime
import logging
import re

from .base_loader import BaseDataLoader
from ..models.spectral_data import SpectralData, SpectralMetadata
from ..models.topography_data import TopographyData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Binary format helpers
# ---------------------------------------------------------------------------

def _read_utf16(data: bytes, pos: int) -> Tuple[str, int]:
    """Read a length-prefixed UTF-16LE string."""
    n = unpack_from('<I', data, pos)[0]
    pos += 4
    if n == 0:
        return "", pos
    if n > 50000 or pos + n * 2 > len(data):
        raise ValueError(f"Invalid string length {n} at 0x{pos - 4:x}")
    s = data[pos:pos + n * 2].decode('utf-16-le', errors='replace').rstrip('\x00')
    return s, pos + n * 2


def _read_typed_value(data: bytes, offset: int) -> Tuple[Any, int]:
    """Read a typed value (LOOB/GNOL/BUOD/GRTS) from an APEE/YSCC block."""
    tag = data[offset:offset + 4].decode('ascii', errors='replace')
    offset += 4
    if tag == 'LOOB':
        return bool(unpack_from('<I', data, offset)[0]), offset + 4
    elif tag == 'GNOL':
        return unpack_from('<i', data, offset)[0], offset + 4
    elif tag == 'BUOD':
        return unpack_from('<d', data, offset)[0], offset + 8
    elif tag == 'GRTS':
        s, offset = _read_utf16(data, offset)
        return s, offset
    return None, offset


# ---------------------------------------------------------------------------
# Header parser
# ---------------------------------------------------------------------------

class MatrixHeaderParser:
    """
    Parser for Omicron Matrix _0001.mtrx session header files.

    Extracts experiment parameters (APEE), transfer functions (YSCC),
    file references (FERB), and annotations (KRAM).
    """

    MAGIC = b'ONTMATRX0101'

    def __init__(self, header_path: Path):
        self.path = Path(header_path)
        self.parameters: Dict[str, Any] = {}
        self.xfer: Dict[str, Any] = {}
        self.file_refs: List[str] = []
        self.annotations: Dict[str, str] = {}
        self.timestamp: Optional[datetime] = None

    def parse(self):
        """Parse the full header file."""
        raw = self.path.read_bytes()
        if raw[:12] != self.MAGIC:
            raise ValueError(f"Not an Omicron Matrix header: {self.path}")

        pos = 12
        while pos < len(raw) - 16:
            tag = raw[pos:pos + 4]
            if not all(65 <= b <= 90 for b in tag):
                break
            tag_str = tag.decode('ascii')
            size = unpack_from('<I', raw, pos + 4)[0]
            ts = unpack_from('<I', raw, pos + 8)[0]
            data_start = pos + 16
            data_end = data_start + size
            if data_end > len(raw):
                break

            block_data = raw[data_start:data_end]

            if tag_str == 'APEE':
                self._parse_apee(block_data)
            elif tag_str == 'YSCC':
                self._parse_yscc(block_data)
            elif tag_str == 'FERB':
                self._parse_ferb(block_data)
            elif tag_str == 'KRAM':
                self._parse_kram(block_data)
            elif tag_str == 'ATEM' and self.timestamp is None:
                self.timestamp = datetime.fromtimestamp(ts) if ts else None

            pos = data_end

    def _parse_apee(self, data: bytes):
        """Parse APEE parameter block."""
        try:
            x = 4
            n_groups = unpack_from('<i', data, x)[0]; x += 4
            for _ in range(n_groups):
                if x >= len(data) - 4:
                    break
                group, x = _read_utf16(data, x)
                n_params = unpack_from('<i', data, x)[0]; x += 4
                for _ in range(n_params):
                    if x >= len(data) - 4:
                        break
                    param, x = _read_utf16(data, x)
                    unit, x = _read_utf16(data, x)
                    x += 4  # padding
                    val, x = _read_typed_value(data, x)
                    self.parameters[f"{group}.{param}"] = [val, unit]
        except Exception as e:
            logger.debug(f"APEE parse error: {e}")

    def _parse_yscc(self, data: bytes):
        """Parse YSCC channel/transfer-function block."""
        try:
            x = 4
            while x < len(data) - 8:
                sub_tag = data[x:x + 4].decode('ascii', errors='replace')
                x += 4
                sub_size = unpack_from('<i', data, x)[0]; x += 4
                x0 = x
                if sub_tag == 'REFX':
                    x += 4
                    group_num = unpack_from('<i', data, x)[0]; x += 4
                    name, x = _read_utf16(data, x)
                    unit, x = _read_utf16(data, x)
                    n_p = unpack_from('<i', data, x)[0]; x += 4
                    params = {}
                    for _ in range(n_p):
                        pname, x = _read_utf16(data, x)
                        val, x = _read_typed_value(data, x)
                        params[pname] = [val]
                    self.xfer[f"XFER_{group_num}"] = [name, unit, params]
                else:
                    x = x0 + sub_size
        except Exception as e:
            logger.debug(f"YSCC parse error: {e}")

    def _parse_ferb(self, data: bytes):
        """Parse FERB file reference block."""
        try:
            x = 4
            fname, x = _read_utf16(data, x)
            if fname:
                self.file_refs.append(fname)
        except Exception:
            pass

    def _parse_kram(self, data: bytes):
        """Parse KRAM annotation block (sample name, dataset, etc.)."""
        try:
            x = 0
            s, x = _read_utf16(data, x)
            if s and '-' in s:
                # Format: "MTRX$KEY-VALUE" or "MTRX$KEY-VALUE-"
                body = s.split('$', 1)[-1] if '$' in s else s
                if '-' in body:
                    key, val = body.split('-', 1)
                    val = val.rstrip('-').strip()
                    self.annotations[key] = val
        except Exception:
            pass

    def get_session_files(self) -> Dict[str, List[str]]:
        """Group file references by extension type."""
        groups: Dict[str, List[str]] = {}
        for fname in self.file_refs:
            m = re.search(r'\.(\w+(?:\(\w+\))?)_mtrx$', fname)
            if m:
                ext = m.group(1)
                groups.setdefault(ext, []).append(fname)
        return groups

    def get_voltage_range(self) -> Optional[Tuple[float, float]]:
        """Get spectroscopy voltage range from parameters."""
        v_start = self.parameters.get('Spectroscopy.Device_1_Start', [None])[0]
        v_end = self.parameters.get('Spectroscopy.Device_1_End', [None])[0]
        if v_start is not None and v_end is not None:
            return (v_start, v_end)
        return None

    def get_scan_dimensions(self) -> Optional[Tuple[int, int]]:
        """Get XY scanner point/line counts."""
        pts = self.parameters.get('XYScanner.Points', [None])[0]
        lines = self.parameters.get('XYScanner.Lines', [None])[0]
        if pts is not None and lines is not None:
            return (int(pts), int(lines))
        return None

    def get_sample_name(self) -> str:
        return self.annotations.get('SAMPLE_NAME', '')

    def get_dataset_name(self) -> str:
        return self.annotations.get('DATA_SET_NAME', '')


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

class OmicronMatrixSTSLoader(BaseDataLoader):
    """
    Comprehensive loader for Omicron Matrix STM data.

    Supports:
    - .I(V)_mtrx, .Aux2(V)_mtrx  — voltage spectroscopy (forward+backward)
    - .I(Z)_mtrx, .Z(V)_mtrx     — distance spectroscopy
    - .I_mtrx, .Z_mtrx            — scanning image lines
    - .Z_flat, .I_flat             — processed flat images (via OmicronFlatLoader)
    - _0001.mtrx                   — session headers (smart import)
    """

    MAGIC_NUMBER = b'ONTMATRX0101'

    # Extensions containing spectroscopy sweeps (forward + backward)
    SPECTROSCOPY_EXTENSIONS = [
        '.I(V)_mtrx', '.Aux2(V)_mtrx', '.Aux1(V)_mtrx',
        '.I(Z)_mtrx', '.Z(V)_mtrx', '.Aux2(Z)_mtrx', '.Aux1(Z)_mtrx',
    ]

    def __init__(self):
        super().__init__()
        self.supported_extensions = ['.I(V)_mtrx']
        self.loader_type = 'omicron_matrix_sts'

        self.parameter: Dict[str, Any] = {}
        self.timestamp: Optional[datetime] = None
        self.header_path: Optional[Path] = None
        self._header_parser: Optional[MatrixHeaderParser] = None

    # ------------------------------------------------------------------
    # Smart import
    # ------------------------------------------------------------------

    def smart_load_from_file(self, filepath: Path,
                             progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
        """
        Smart import: pick one file and discover the full session.

        Accepts either a _0001.mtrx header or any data file from the session.
        Parses the header, discovers all sibling files, and loads them.
        """
        filepath = Path(filepath)
        directory = filepath.parent

        # Find the header
        if filepath.name.endswith('_0001.mtrx'):
            header_path = filepath
        else:
            header_path = self._find_header(filepath)

        if header_path is None:
            logger.warning("No header found, falling back to directory import")
            return self.load_from_directory(directory, progress_callback)

        # Parse header
        parser = MatrixHeaderParser(header_path)
        parser.parse()
        self._header_parser = parser

        # Copy parameters for scaling
        self.parameter = dict(parser.parameters)
        self.parameter['XFER'] = dict(parser.xfer)

        session_files = parser.get_session_files()
        sample_name = parser.get_sample_name()
        dataset_name = parser.get_dataset_name()

        logger.info(f"Smart import: session has {sum(len(v) for v in session_files.values())} files "
                    f"across {list(session_files.keys())} types")
        if sample_name:
            logger.info(f"  Sample: {sample_name}")
        if dataset_name:
            logger.info(f"  Dataset: {dataset_name}")

        # Resolve which files exist on disk
        existing_files: Dict[str, List[Path]] = {}
        for ext, fnames in session_files.items():
            for fname in fnames:
                fpath = directory / fname
                if fpath.exists():
                    existing_files.setdefault(ext, []).append(fpath)

        if not existing_files:
            raise ValueError(f"No session data files found in {directory}")

        # Decide which extension group to load as primary spectroscopy
        # Priority: I(V) > Aux2(V) > I(Z) > Z(V)
        primary_ext = None
        for candidate in ['I(V)', 'Aux2(V)', 'Aux1(V)', 'I(Z)', 'Z(V)']:
            if candidate in existing_files:
                primary_ext = candidate
                break

        if primary_ext is None:
            logger.warning("No spectroscopy files found, trying directory import")
            return self.load_from_directory(directory, progress_callback)

        # Load all spectroscopy file types
        total_files = sum(len(v) for v in existing_files.items()
                          if any(v_name.name.endswith(f'.{ext}_mtrx')
                                 for ext in ['I(V)', 'Aux2(V)', 'Aux1(V)', 'I(Z)', 'Z(V)']
                                 for v_name in v))
        # Simpler: count all spec files
        spec_exts = {'I(V)', 'Aux2(V)', 'Aux1(V)', 'I(Z)', 'Z(V)', 'Aux2(Z)', 'Aux1(Z)'}
        spec_files = {ext: files for ext, files in existing_files.items() if ext in spec_exts}
        total_files = sum(len(f) for f in spec_files.values())

        channels: Dict[tuple, dict] = {}
        topography = None
        processed = 0

        for ext_type, files in spec_files.items():
            for fpath in sorted(files):
                try:
                    if progress_callback:
                        progress_callback(processed, total_files, f"Loading {fpath.name}")

                    parsed = self._parse_spectroscopy_file(fpath)
                    if parsed is not None:
                        V = parsed['V']
                        n_points = parsed['n_points']
                        key = (ext_type, n_points)

                        if key not in channels:
                            channels[key] = {
                                'V': V,
                                'forward': [], 'backward': [], 'mixed': [],
                                'files': [], 'ext_type': ext_type, 'n_points': n_points,
                            }

                        channels[key]['forward'].append(parsed['forward'])
                        channels[key]['backward'].append(parsed['backward'])
                        channels[key]['mixed'].append(parsed['mixed'])
                        channels[key]['files'].append(fpath.name)

                    processed += 1
                except Exception as e:
                    logger.error(f"Error processing {fpath.name}: {e}")
                    processed += 1

        if not channels:
            raise ValueError("No spectral data could be extracted from session")

        # Try to load topography from flat files
        topography = self._find_flat_topography(directory)

        # Build SpectralData from channels (same logic as load_from_directory)
        return self._build_spectral_data(channels, topography, directory,
                                          total_files, sample_name, dataset_name,
                                          progress_callback)

    # ------------------------------------------------------------------
    # Directory import (existing interface)
    # ------------------------------------------------------------------

    def load_from_directory(self, directory: Path,
                            progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
        """Load STS data from directory of spectroscopy files."""
        directory = Path(directory)
        if not self.validate_directory(directory):
            raise ValueError(f"Invalid directory: {directory}")

        # Try to find and parse a header first (for parameters/scaling)
        headers = list(directory.glob("*_0001.mtrx"))
        if headers:
            try:
                parser = MatrixHeaderParser(headers[0])
                parser.parse()
                self._header_parser = parser
                self.parameter = dict(parser.parameters)
                self.parameter['XFER'] = dict(parser.xfer)
            except Exception as e:
                logger.warning(f"Could not parse header: {e}")

        # Find all spectroscopy files
        file_types: Dict[str, List[Path]] = {}
        for ext in ['I(V)', 'I(Z)', 'Z(V)', 'Aux2(V)', 'Aux1(V)', 'Aux2(Z)', 'Aux1(Z)']:
            matches = [f for f in directory.iterdir() if f.name.endswith(f'.{ext}_mtrx')]
            if matches:
                file_types[ext] = matches

        if not file_types:
            raise ValueError(f"No supported .mtrx files found in {directory}")

        total_files = sum(len(files) for files in file_types.values())
        logger.info(f"Loading {total_files} matrix files from {directory}")
        logger.info(f"File types found: {list(file_types.keys())}")

        channels: Dict[tuple, dict] = {}
        topography = None
        processed = 0

        for ext_type, files in file_types.items():
            for filepath in sorted(files):
                try:
                    if progress_callback:
                        progress_callback(processed, total_files, f"Loading {filepath.name}")

                    parsed = self._parse_spectroscopy_file(filepath)
                    if parsed is not None:
                        V = parsed['V']
                        n_points = parsed['n_points']
                        key = (ext_type, n_points)

                        if key not in channels:
                            channels[key] = {
                                'V': V,
                                'forward': [], 'backward': [], 'mixed': [],
                                'files': [], 'ext_type': ext_type, 'n_points': n_points,
                            }

                        channels[key]['forward'].append(parsed['forward'])
                        channels[key]['backward'].append(parsed['backward'])
                        channels[key]['mixed'].append(parsed['mixed'])
                        channels[key]['files'].append(filepath.name)

                    processed += 1
                except Exception as e:
                    logger.error(f"Error processing {filepath.name}: {e}")
                    processed += 1

        if not channels:
            raise ValueError("No spectral data could be extracted")

        topography = self._find_flat_topography(directory)

        return self._build_spectral_data(channels, topography, directory,
                                          total_files, progress_callback=progress_callback)

    # ------------------------------------------------------------------
    # Single file import
    # ------------------------------------------------------------------

    def load_single_file(self, filepath: Path) -> SpectralData:
        """Load data from a single spectroscopy file."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        # Check that it's a supported spectroscopy extension
        is_spec = any(filepath.name.endswith(ext) for ext in self.SPECTROSCOPY_EXTENSIONS)
        if not is_spec:
            raise ValueError(f"Unsupported file type: {filepath.name}")

        logger.info(f"Loading single file: {filepath}")

        parsed = self._parse_spectroscopy_file(filepath)
        if parsed is None:
            raise ValueError(f"Could not parse data from {filepath}")

        V = parsed['V']
        forward = parsed['forward']
        backward = parsed['backward']
        mixed = parsed['mixed']

        df = pd.DataFrame({"V": V, "Forward": forward, "Backward": backward, "Mixed": mixed})

        forward_df = pd.DataFrame({"V": V, "Current": forward})
        backward_df = pd.DataFrame({"V": V, "Current": backward})
        mixed_df = pd.DataFrame({"V": V, "Current": mixed})

        metadata = self.create_metadata(
            dimensions=(1, 1),
            scan_mode="single",
            units={"independent": "V", "dependent": "A"},
            source_file=str(filepath),
            instrument="Omicron Matrix",
            timestamp=str(self.timestamp) if self.timestamp else None,
            sweep_channels={'Forward': forward_df, 'Backward': backward_df, 'Mixed': mixed_df}
        )

        spectral_data = SpectralData(df, metadata)
        self.last_loaded_path = filepath
        logger.info(f"Loaded single file with forward/backward/mixed channels: {spectral_data}")
        return spectral_data

    # ------------------------------------------------------------------
    # Core parsing
    # ------------------------------------------------------------------

    def _parse_spectroscopy_file(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """
        Parse any spectroscopy _mtrx file (I(V), Aux2(V), I(Z), etc.).

        Returns dict with V, forward, backward, mixed arrays and n_points.
        """
        # Try to find and parse header if not already done
        if not self.parameter.get('XFER'):
            header_path = self._find_header(filepath)
            if header_path:
                try:
                    self._parse_header_for_file(header_path, filepath)
                except Exception as e:
                    logger.warning(f"Could not parse header: {e}")

        try:
            with open(filepath, 'rb') as f:
                magic = f.read(12)
                if magic != self.MAGIC_NUMBER:
                    logger.error(f"Invalid magic number in {filepath}")
                    return None

                data = None
                datasize = 0

                while True:
                    tag = f.read(4)
                    if len(tag) < 4:
                        break
                    try:
                        tag_str = tag.decode('ascii')
                    except UnicodeDecodeError:
                        break

                    if tag_str == 'TLKB':
                        f.read(4)
                        ts_val = unpack('<L', f.read(4))[0]
                        self.timestamp = datetime.fromtimestamp(ts_val)
                        f.read(8)
                    elif tag_str == 'CSED':
                        blocksize = unpack('<i', f.read(4))[0]
                        f.read(blocksize)
                    elif tag_str == 'ATAD':
                        datasize = unpack('<i', f.read(4))[0]
                        data = f.read(datasize)
                        break
                    else:
                        try:
                            blocksize = unpack('<i', f.read(4))[0]
                            f.read(blocksize + 8)
                        except Exception:
                            break

                if data is None:
                    logger.error(f"No ATAD block found in {filepath}")
                    return None

                n_total = datasize // 4
                raw = np.array(unpack(f'<{n_total}i', data), dtype=np.float64)

                scaled = self._scale_data(raw)

                # Split into forward/backward (first half = forward, second = backward)
                n_half = n_total // 2
                if n_total % 2 != 0:
                    logger.warning(f"Odd point count ({n_total}), truncating")

                forward = scaled[:n_half]
                backward = scaled[n_half:n_half * 2][::-1]
                mixed = (forward + backward) / 2

                V = self._get_voltage_array(forward)

                return {
                    'V': V,
                    'forward': forward,
                    'backward': backward,
                    'mixed': mixed,
                    'n_points': n_half,
                }

        except Exception as e:
            logger.error(f"Error parsing {filepath}: {e}")
            return None

    # Keep old name as alias for backward compatibility
    _parse_iv_file = _parse_spectroscopy_file

    # ------------------------------------------------------------------
    # Header parsing
    # ------------------------------------------------------------------

    def _find_header(self, filepath: Path) -> Optional[Path]:
        """Find the associated _0001.mtrx header file."""
        filename = filepath.name
        base = filename.rsplit('--', 1)[0]
        header_name = f"{base}_0001.mtrx"
        header_path = filepath.parent / header_name

        if header_path.exists():
            return header_path

        # Try any header in the directory
        mtrx_files = list(filepath.parent.glob("*_0001.mtrx"))
        return mtrx_files[0] if mtrx_files else None

    def _parse_header_for_file(self, header_path: Path, target_file: Path):
        """Parse header to extract parameters relevant to the target file."""
        parser = MatrixHeaderParser(header_path)
        parser.parse()
        self._header_parser = parser
        self.parameter = dict(parser.parameters)
        self.parameter['XFER'] = dict(parser.xfer)
        self.parameter['BREF'] = ''

    def _parse_header(self, header_path: Path, target_file: Path):
        """Legacy header parser — reads sequentially looking for target BREF."""
        self.parameter = {'BREF': '', 'XFER': {}, 'DICT': {}}
        target_filename = target_file.name

        try:
            with open(header_path, 'rb') as f:
                magic = f.read(12)
                if magic != self.MAGIC_NUMBER:
                    return

                while self.parameter['BREF'] != target_filename:
                    tag = f.read(4)
                    if len(tag) < 4:
                        break
                    try:
                        tag_str = tag.decode('ascii')
                    except UnicodeDecodeError:
                        break

                    if tag_str == 'APEE':
                        block_size = unpack('<i', f.read(4))[0]
                        f.read(8)
                        apee = f.read(block_size)
                        self._parse_apee_block(apee)
                    elif tag_str == 'YSCC':
                        block_size = unpack('<i', f.read(4))[0]
                        f.read(8)
                        yscc = f.read(block_size)
                        self._parse_yscc_block(yscc)
                    elif tag_str == 'FERB':
                        block_size = unpack('<i', f.read(4))[0]
                        f.read(8)
                        ferb = f.read(block_size)
                        size = unpack('<i', ferb[4:8])[0]
                        self.parameter['BREF'] = ferb[8:8 + size * 2].decode('utf-16')
                    else:
                        try:
                            block_size = unpack('<i', f.read(4))[0]
                            f.read(8)
                            f.read(block_size)
                        except Exception:
                            break

        except Exception as e:
            logger.warning(f"Error parsing header {header_path}: {e}")

    def _parse_apee_block(self, apee: bytes):
        """Parse APEE parameter block (legacy path)."""
        try:
            n_groups = unpack('<i', apee[4:8])[0]
            x = 8
            for _ in range(n_groups):
                size = unpack('<i', apee[x:x + 4])[0]; x += 4
                groupname = apee[x:x + size * 2].decode('utf-16'); x += size * 2
                n_params = unpack('<i', apee[x:x + 4])[0]; x += 4
                for _ in range(n_params):
                    size = unpack('<i', apee[x:x + 4])[0]; x += 4
                    param = apee[x:x + size * 2].decode('utf-16'); x += size * 2
                    size = unpack('<i', apee[x:x + 4])[0]; x += 4
                    unit = apee[x:x + size * 2].decode('utf-16'); x += size * 2
                    x += 4
                    data, x = _read_typed_value(apee, x)
                    self.parameter[f"{groupname}.{param}"] = [data, unit]
        except Exception as e:
            logger.debug(f"APEE parse error: {e}")

    def _parse_yscc_block(self, yscc: bytes):
        """Parse YSCC block (legacy path)."""
        try:
            x = 4
            while x < len(yscc):
                tag = yscc[x:x + 4].decode('ascii'); x += 4
                blocksize = unpack('<i', yscc[x:x + 4])[0]; x += 4
                x0 = x
                if tag == 'REFX':
                    x += 4
                    gn = unpack('<i', yscc[x:x + 4])[0]; x += 4
                    size = unpack('<i', yscc[x:x + 4])[0]; x += 4
                    name = yscc[x:x + size * 2].decode('utf-16'); x += size * 2
                    size = unpack('<i', yscc[x:x + 4])[0]; x += 4
                    unit = yscc[x:x + size * 2].decode('utf-16'); x += size * 2
                    n_p = unpack('<i', yscc[x:x + 4])[0]; x += 4
                    params = {}
                    for _ in range(n_p):
                        size = unpack('<i', yscc[x:x + 4])[0]; x += 4
                        pname = yscc[x:x + size * 2].decode('utf-16'); x += size * 2
                        val, x = _read_typed_value(yscc, x)
                        params[pname] = [val]
                    self.parameter['XFER'][f"XFER_{gn}"] = [name, unit, params]
                else:
                    x = x0 + blocksize
        except Exception as e:
            logger.debug(f"YSCC parse error: {e}")

    # ------------------------------------------------------------------
    # Scaling
    # ------------------------------------------------------------------

    def _scale_data(self, raw_data: np.ndarray) -> np.ndarray:
        """Scale raw int32 data using the best available transfer function."""
        for key in self.parameter.get('XFER', {}):
            xfer = self.parameter['XFER'][key]
            if len(xfer) >= 3 and isinstance(xfer[2], dict):
                xfer_params = xfer[2]

                if xfer[0] == 'TFF_Linear1D':
                    offset = xfer_params.get('Offset', [0])[0]
                    factor = xfer_params.get('Factor', [1])[0]
                    if factor != 0:
                        return (raw_data - offset) / factor
                else:
                    raw_1 = xfer_params.get('Raw_1', [1])[0]
                    pre_offset = xfer_params.get('PreOffset', [0])[0]
                    offset = xfer_params.get('Offset', [0])[0]
                    nf = xfer_params.get('NeutralFactor', [1])[0]
                    pf = xfer_params.get('PreFactor', [1])[0]
                    denom = nf * pf
                    if denom != 0:
                        return (raw_1 - pre_offset) * (raw_data - offset) / denom

        logger.warning("No transfer function found, using default scaling (nA)")
        return raw_data * 1e-9

    def _get_voltage_array(self, current_data: np.ndarray) -> np.ndarray:
        """Generate voltage array from header parameters or defaults."""
        n = len(current_data)
        v_start = self.parameter.get('Spectroscopy.Device_1_Start', [None])[0]
        v_end = self.parameter.get('Spectroscopy.Device_1_End', [None])[0]

        if v_start is not None and v_end is not None:
            return np.linspace(v_start, v_end, n)

        logger.warning("Using default voltage range: -1V to +1V")
        return np.linspace(-1.0, 1.0, n)

    # ------------------------------------------------------------------
    # Topography helpers
    # ------------------------------------------------------------------

    def _find_flat_topography(self, directory: Path) -> Optional[TopographyData]:
        """Find and load topography from Z_flat files in directory."""
        flat_files = [f for f in directory.iterdir()
                      if f.name.endswith('.Z_flat') or f.name.endswith('.I_flat')]
        if not flat_files:
            return None
        try:
            from .omicron_flat_loader import OmicronFlatLoader
            return OmicronFlatLoader().load_topography(flat_files[0])
        except Exception as e:
            logger.warning(f"Could not load flat topography: {e}")
            return None

    def _find_topography(self, iv_filepath: Path) -> Optional[TopographyData]:
        """Find associated Z_mtrx topography file."""
        base = iv_filepath.name.rsplit('.', 1)[0]
        z_files = list(iv_filepath.parent.glob(f"{base.rsplit('.', 1)[0]}*.Z_mtrx"))
        if z_files:
            try:
                z_data = self._parse_z_mtrx(z_files[0])
                if z_data is not None:
                    return TopographyData.from_array(z_data)
            except Exception as e:
                logger.warning(f"Could not load topography: {e}")
        return None

    def _parse_z_mtrx(self, filepath: Path) -> Optional[np.ndarray]:
        """Parse Z_mtrx topography file (returns 2D images only)."""
        MIN_TOPO_SIZE = 16
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
                    elif tag_str == 'TLKB':
                        f.read(16)
                    elif tag_str == 'CSED':
                        blocksize = unpack('<i', f.read(4))[0]
                        f.read(blocksize)
                    else:
                        break
                if data:
                    n = datasize // 4
                    raw = np.array(unpack(f'<{n}i', data), dtype=np.float64)
                    side = int(np.sqrt(n))
                    if side * side == n and side >= MIN_TOPO_SIZE:
                        return raw.reshape(side, side)
        except Exception as e:
            logger.debug(f"Error parsing Z_mtrx: {e}")
        return None

    # ------------------------------------------------------------------
    # Build SpectralData from channel groups
    # ------------------------------------------------------------------

    def _build_spectral_data(self, channels, topography, directory,
                              total_files, sample_name='', dataset_name='',
                              progress_callback=None):
        """Build SpectralData + TopographyData from grouped channel dicts."""
        sorted_channels = sorted(channels.items(),
                                  key=lambda x: len(x[1]['mixed']), reverse=True)

        main_key, main_ch = sorted_channels[0]
        ext_type, n_points = main_key
        n_spectra = len(main_ch['mixed'])

        logger.info(f"Main channel: {ext_type} with {n_points} pts, {n_spectra} spectra")

        V = main_ch['V']
        mixed_stack = np.column_stack(main_ch['mixed'])
        fwd_stack = np.column_stack(main_ch['forward'])
        bwd_stack = np.column_stack(main_ch['backward'])

        col_names = [f"Point_{i + 1}" for i in range(n_spectra)]
        df = pd.DataFrame(mixed_stack, columns=col_names)
        df.insert(0, "V", V)

        dim_guess = int(np.sqrt(n_spectra))
        dimensions = (dim_guess, dim_guess) if dim_guess * dim_guess == n_spectra else (n_spectra, 1)

        sweep_channels = {}
        for name, stack in [('Forward', fwd_stack), ('Backward', bwd_stack), ('Mixed', mixed_stack)]:
            ch_df = pd.DataFrame(stack, columns=col_names)
            ch_df.insert(0, "V", V)
            sweep_channels[name] = ch_df

        additional_channels = {}
        for key, ch_data in sorted_channels[1:]:
            ch_ext, ch_pts = key
            ch_n = len(ch_data['mixed'])
            ch_cols = [f"Point_{i + 1}" for i in range(ch_n)]
            for sweep in ['forward', 'backward', 'mixed']:
                ch_name = f"{ch_ext}_{ch_pts}pts_{sweep.capitalize()}"
                ch_stack = np.column_stack(ch_data[sweep])
                ch_df = pd.DataFrame(ch_stack, columns=ch_cols)
                ch_df.insert(0, "V", ch_data['V'])
                additional_channels[ch_name] = ch_df

        extra_info = {}
        if sample_name:
            extra_info['sample_name'] = sample_name
        if dataset_name:
            extra_info['dataset_name'] = dataset_name

        metadata = self.create_metadata(
            dimensions=dimensions,
            scan_mode="single",
            units={"independent": "V", "dependent": "A", "x": "nm", "y": "nm"},
            n_files=total_files,
            source_directory=str(directory),
            instrument="Omicron Matrix",
            main_channel=f"{ext_type}_{n_points}pts_Mixed",
            sweep_channels=sweep_channels,
            additional_channels=additional_channels,
            **extra_info,
        )

        spectral_data = SpectralData(df, metadata,
                                      topography.data if topography else None)

        # Surface sidecar reference images (operator photos, optical preview
        # screenshots) sitting alongside the data files. Omicron's binary
        # format doesn't embed these — they live as loose .png/.jpg/.tif.
        try:
            sidecars = self.discover_sidecar_images(directory)
            if sidecars:
                spectral_data.metadata.additional_info['images'] = sidecars
                logger.info(
                    f"Attached {len(sidecars)} sidecar image(s) from {directory}"
                )
        except Exception as e:
            logger.debug(f"Sidecar image discovery failed: {e}")

        if progress_callback:
            progress_callback(total_files, total_files, "Complete!")

        self.last_loaded_path = directory
        logger.info(f"Loaded STS data: {spectral_data}")
        return spectral_data, topography
