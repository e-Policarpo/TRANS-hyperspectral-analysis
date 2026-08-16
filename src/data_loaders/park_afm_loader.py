# ============================================================================
# T.R.A.N.S. version 1.0
# Tools for Research and Analysis for Nano Spectroscopy
#
# Created by Eduarda Policarpo, in April of 2026 with love.
#
# File: park_afm_loader.py
# Description: Loader for Park Systems AFM PinPoint spectroscopy files
#              and associated TIFF property maps.
#
# Handles:
#   .ps-ppt   — PinPoint force-distance curves (PS-PPT/v1 format)
#   .tiff     — Derived channel maps (Z Height, Modulus, Adhesion, etc.)
#
# PS-PPT/v1 format:
#   Magic "PS-PPT/v1\n" (10 bytes), then a segment index of 8-byte
#   big-endian entries pointing into a newline-delimited JSON event stream.
#   Events: scan.start, ppt.param, ppt.rtfd (one per pixel), scan.stop.
#   Each ppt.rtfd carries base64-encoded float32 arrays per channel.
#
# Park TIFF format:
#   Standard TIFF with Park-specific tags:
#     50434 — raw float32 image data (width × height × 4 bytes)
#     50435 — binary metadata (channel name, scan mode, dimensions, etc.)
# ============================================================================

"""
Park Systems AFM PinPoint Loader

Loader for PinPoint spectroscopy data from Park Systems NX-series AFMs.
Supports .ps-ppt force curve files and companion .tiff property maps.

The loader builds hyperspectral datasets suitable for the Map Editor:
  - TIFF maps → topography / property layers
  - ps-ppt Force channel → spectra at each (x, y) pixel
"""

import base64
import json
import logging
import re
import numpy as np
import pandas as pd
from pathlib import Path
from struct import unpack_from
from typing import Optional, Tuple, List, Dict, Any

from .base_loader import BaseDataLoader
from ..utils.naming import padded_series
from ..models.spectral_data import SpectralData, SpectralMetadata
from ..models.topography_data import TopographyData, TopographyMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Naming convention helpers
# ---------------------------------------------------------------------------

# Pattern: {Sample}_{Date}_{Channel}_{Direction}_{ScanNum}.ext
_PARK_FILENAME_RE = re.compile(
    r'^(?P<sample>.+?)_(?P<date>\d{6})_(?P<channel>.+?)_'
    r'(?P<direction>Forward|Backward)_(?P<scan>\d+)$'
)


def parse_park_filename(stem: str) -> Optional[Dict[str, str]]:
    """Parse a Park AFM filename stem into its components."""
    m = _PARK_FILENAME_RE.match(stem)
    if m:
        return m.groupdict()
    return None


def session_key(stem: str) -> Optional[str]:
    """Return 'Sample_Date_ScanNum' for grouping sibling files."""
    p = parse_park_filename(stem)
    if p:
        return f"{p['sample']}_{p['date']}_{p['scan']}"
    return None


# ---------------------------------------------------------------------------
# Park TIFF helpers
# ---------------------------------------------------------------------------

PARK_TAG_DATA = 50434       # float32 raw image data
PARK_TAG_META = 50435       # binary metadata blob


def load_park_tiff(filepath: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Load a Park Systems TIFF file returning (float32_image, metadata_dict).

    The visible 8-bit image is a colormapped thumbnail; the real data
    lives in custom TIFF tag 50434 as a flat float32 buffer.
    """
    from PIL import Image

    img = Image.open(str(filepath))
    tags = img.tag_v2

    width = tags.get(256, img.size[0])
    height = tags.get(257, img.size[1])

    meta: Dict[str, Any] = {
        'width': width,
        'height': height,
        'software': tags.get(305, ''),
        'datetime': tags.get(306, ''),
    }

    # Extract real float32 data from tag 50434
    if PARK_TAG_DATA in tags:
        raw = tags[PARK_TAG_DATA]
        if isinstance(raw, bytes) and len(raw) == width * height * 4:
            data = np.frombuffer(raw, dtype='<f4').reshape(height, width).copy()
        else:
            logger.warning(f"Tag 50434 size mismatch in {filepath.name}, "
                           f"expected {width*height*4}, got {len(raw)}")
            data = np.array(img, dtype=np.float64)
    else:
        data = np.array(img, dtype=np.float64)

    # Extract channel name and scan parameters from tag 50435
    if PARK_TAG_META in tags:
        blob = tags[PARK_TAG_META]
        if isinstance(blob, bytes) and len(blob) >= 0x44:
            channel_name = blob[0x04:0x44].decode('utf-16-le', errors='replace').rstrip('\x00').strip()
            meta['channel'] = channel_name

            scan_mode = blob[0x44:0x64].decode('utf-16-le', errors='replace').rstrip('\x00').strip()
            meta['scan_mode'] = scan_mode

            if len(blob) >= 0x9c:
                meta['scan_width_um'] = unpack_from('<d', blob, 0x8c)[0]
                meta['scan_height_um'] = unpack_from('<d', blob, 0x94)[0]

    # Also parse from filename
    parsed = parse_park_filename(filepath.stem)
    if parsed:
        meta['direction'] = parsed['direction']
        if 'channel' not in meta:
            meta['channel'] = parsed['channel']

    return data, meta


# ---------------------------------------------------------------------------
# PS-PPT parser
# ---------------------------------------------------------------------------

class PsPptParser:
    """
    Parser for Park Systems .ps-ppt PinPoint spectroscopy files.

    The PS-PPT/v1 binary format stores a segment index followed by
    a newline-delimited JSON event stream.  Each pixel is a ppt.rtfd
    event containing base64-encoded float32 arrays for each channel.
    """

    MAGIC = b'PS-PPT/v1\n'

    def __init__(self, filepath: Path):
        self.path = Path(filepath)
        self.scan_info: Dict[str, Any] = {}
        self.param_info: Dict[str, Any] = {}
        self.channels: List[Dict[str, str]] = []   # [{'id': 'Force', 'unit': 'volt'}, ...]
        self.pixel_width: int = 0
        self.pixel_height: int = 0
        self.scan_width_um: float = 0.0
        self.scan_height_um: float = 0.0
        self.is_forward: Optional[bool] = None
        self._data_offset: int = 0

    # ── Index parsing ─────────────────────────────────────────────────

    def _parse_index(self, raw: bytes) -> List[int]:
        """Parse the segment index returning a list of file offsets."""
        offsets: List[int] = []
        pos = 0x1e  # index starts after 30-byte header
        prev_table_id = -1

        while pos + 8 <= len(raw):
            table_id = raw[pos]
            if table_id > 0x30 or table_id <= prev_table_id:
                break
            # Read all entries for this table
            while pos + 8 <= len(raw) and raw[pos] == table_id:
                off = unpack_from('>I', raw, pos)[0]
                offsets.append(off)
                pos += 8
            prev_table_id = table_id

        return offsets

    # ── Metadata-only parse (fast) ────────────────────────────────────

    def parse_metadata(self) -> Dict[str, Any]:
        """
        Quick parse: read only scan.start and ppt.param (first ~64 KB of
        the event stream).  Does NOT load pixel data.
        """
        with open(self.path, 'rb') as f:
            header = f.read(0x220000)  # ~2.1 MB covers index + first events

        if header[:10] != self.MAGIC:
            raise ValueError(f"Not a PS-PPT file: {self.path}")

        offsets = self._parse_index(header)
        if not offsets:
            raise ValueError(f"Empty index in {self.path}")

        self._data_offset = offsets[0]

        # Read first few events
        with open(self.path, 'rb') as f:
            f.seek(self._data_offset)
            chunk = f.read(200_000)

        for line in chunk.split(b'\n'):
            line = line.strip()
            if not line or not line.startswith(b'{'):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            ev_type = ev.get('type')

            if ev_type == 'scan.start':
                self.scan_info = ev
                geom = ev.get('geometry', {})
                self.pixel_width = geom.get('pixelWidth', 256)
                self.pixel_height = geom.get('pixelHeight', 256)
                self.scan_width_um = geom.get('width', 0)
                self.scan_height_um = geom.get('height', 0)

            elif ev_type == 'ppt.param':
                self.param_info = ev

            elif ev_type == 'ppt.rtfd':
                info = ev.get('info', {})
                self.channels = info.get('channels', [])
                self.is_forward = info.get('forward')
                break  # Got everything we need

        return {
            'pixel_width': self.pixel_width,
            'pixel_height': self.pixel_height,
            'scan_width_um': self.scan_width_um,
            'scan_height_um': self.scan_height_um,
            'channels': self.channels,
            'is_forward': self.is_forward,
            'cantilever': self.param_info.get('cantilever', {}),
            'time': self.scan_info.get('time', ''),
        }

    # ── Full data load ────────────────────────────────────────────────

    def load_force_map(self, target_channel: str = 'Force',
                       progress_callback=None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Load force curves from all pixels for the given channel.

        Returns
        -------
        curves : np.ndarray, shape (n_pixels, max_points)
            Force (or other channel) values.  Shorter curves are NaN-padded.
        z_curves : np.ndarray, shape (n_pixels, max_points)
            Corresponding ZHeight values (the independent variable).
            NaN-padded to the same length.
        """
        if not self.channels:
            self.parse_metadata()

        # Find channel indices
        ch_names = [c['id'] for c in self.channels]
        if target_channel not in ch_names:
            raise ValueError(
                f"Channel '{target_channel}' not found. Available: {ch_names}")

        target_idx = ch_names.index(target_channel)
        z_idx = ch_names.index('ZHeight') if 'ZHeight' in ch_names else None

        n_pixels = self.pixel_width * self.pixel_height

        # First pass: collect all curves and track max length
        pixel_curves: List[Optional[np.ndarray]] = [None] * n_pixels
        z_pixel_curves: List[Optional[np.ndarray]] = [None] * n_pixels
        max_len = 0
        loaded = 0

        with open(self.path, 'rb') as f:
            f.seek(self._data_offset)

            buf = b''
            chunk_size = 16 * 1024 * 1024  # 16 MB reads

            while True:
                new_data = f.read(chunk_size)
                if not new_data and not buf:
                    break
                buf += new_data

                lines = buf.split(b'\n')
                # Keep last incomplete line in buffer
                buf = lines[-1]
                lines = lines[:-1]

                for line in lines:
                    line = line.strip()
                    if not line or not line.startswith(b'{'):
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if ev.get('type') != 'ppt.rtfd':
                        continue

                    info = ev['info']
                    fast = info['index']['fast']
                    slow = info['index']['slow']
                    pixel_idx = slow * self.pixel_width + fast

                    numbers = ev.get('numbers', [])
                    if target_idx < len(numbers):
                        decoded = base64.b64decode(numbers[target_idx])
                        arr = np.frombuffer(decoded, dtype='<f4').copy()
                        pixel_curves[pixel_idx] = arr
                        if len(arr) > max_len:
                            max_len = len(arr)

                    if z_idx is not None and z_idx < len(numbers):
                        decoded = base64.b64decode(numbers[z_idx])
                        z_pixel_curves[pixel_idx] = np.frombuffer(
                            decoded, dtype='<f4').copy()

                    loaded += 1
                    if progress_callback and loaded % 1000 == 0:
                        progress_callback(loaded, n_pixels,
                                          f"Loading curves: {loaded}/{n_pixels}")

                if not new_data:
                    break

        if progress_callback:
            progress_callback(n_pixels, n_pixels, "Assembling data cube...")

        # Build padded arrays
        curves = np.full((n_pixels, max_len), np.nan, dtype=np.float32)
        z_curves = np.full((n_pixels, max_len), np.nan, dtype=np.float32)

        for i in range(n_pixels):
            if pixel_curves[i] is not None:
                n = len(pixel_curves[i])
                curves[i, :n] = pixel_curves[i]
            if z_pixel_curves[i] is not None:
                n = len(z_pixel_curves[i])
                z_curves[i, :n] = z_pixel_curves[i]

        logger.info(f"Loaded {loaded} curves from {self.path.name}: "
                    f"{self.pixel_width}x{self.pixel_height}, "
                    f"max {max_len} pts/curve, channel='{target_channel}'")

        return curves, z_curves


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

class ParkAFMLoader(BaseDataLoader):
    """
    Loader for Park Systems AFM PinPoint data.

    Handles:
    - .ps-ppt files  — PinPoint force curves (hyperspectral)
    - .tiff files     — Derived property maps (topography layers)
    - Smart import    — pick one file, discover session siblings by naming
    """

    def __init__(self):
        super().__init__()
        self.supported_extensions = ['.ps-ppt', '.tiff']
        self.loader_type = 'park_afm'

    # ── BaseDataLoader interface ──────────────────────────────────────

    def load_from_directory(self, directory: Path,
                            progress_callback=None
                            ) -> Tuple[SpectralData, Optional[TopographyData]]:
        """Load Park AFM data from a directory."""
        directory = Path(directory)

        ppt_files = sorted(directory.glob('*.ps-ppt'))
        tiff_files = sorted(directory.glob('*.tiff'))

        if not ppt_files and not tiff_files:
            raise ValueError(f"No .ps-ppt or .tiff files in {directory}")

        topography = None
        spectral_data = None

        # Load TIFFs as property maps
        tiff_maps: Dict[str, Tuple[np.ndarray, Dict]] = {}
        for tf in tiff_files:
            try:
                data, meta = load_park_tiff(tf)
                ch_name = meta.get('channel', tf.stem)
                tiff_maps[ch_name] = (data, meta)
                # Use Z Height as primary topography
                if 'z height' in ch_name.lower() and topography is None:
                    topo_meta = TopographyMetadata(
                        dimensions=data.shape,
                        physical_size=(meta.get('scan_height_um', 0),
                                       meta.get('scan_width_um', 0)),
                        units='um',
                    )
                    topography = TopographyData(data, topo_meta)
            except Exception as e:
                logger.warning(f"Could not load TIFF {tf.name}: {e}")

        # Load first ps-ppt as spectral data
        if ppt_files:
            spectral_data = self._load_ppt_as_spectral(
                ppt_files[0], tiff_maps, progress_callback)
        else:
            # TIFF-only: create dummy spectral data
            first_map = next(iter(tiff_maps.values()))
            dummy_df = pd.DataFrame({'X': [0], 'Y': [0]})
            meta = self.create_metadata(
                dimensions=first_map[0].shape,
                scan_mode='pinpoint',
                units={'x': 'um', 'y': 'um'},
                source_directory=str(directory),
                instrument='Park AFM',
            )
            spectral_data = SpectralData(
                dummy_df, meta,
                topography.data if topography else None)

        self.last_loaded_path = directory
        return spectral_data, topography

    def load_single_file(self, filepath: Path) -> SpectralData:
        """Load a single Park file (.ps-ppt or .tiff)."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        if filepath.suffix == '.ps-ppt':
            return self._load_ppt_as_spectral(filepath)
        elif filepath.suffix in ('.tiff', '.tif'):
            return self._load_tiff_as_spectral(filepath)
        else:
            raise ValueError(f"Unsupported file: {filepath.suffix}")

    # ── Smart import ──────────────────────────────────────────────────

    def smart_load_from_file(self, filepath: Path,
                             progress_callback=None
                             ) -> Tuple[SpectralData, Optional[TopographyData]]:
        """
        Smart import: pick any file from a session and auto-discover
        all siblings by naming convention (Sample_Date_ScanNum match).
        """
        filepath = Path(filepath)
        key = session_key(filepath.stem)
        if not key:
            # Fallback: just load the single file
            logger.warning(f"Cannot parse session key from {filepath.name}, "
                           "loading single file")
            sd = self.load_single_file(filepath)
            return sd, None

        # Discover siblings
        parent = filepath.parent
        siblings_ppt: List[Path] = []
        siblings_tiff: List[Path] = []

        for f in sorted(parent.iterdir()):
            if session_key(f.stem) == key:
                if f.suffix == '.ps-ppt':
                    siblings_ppt.append(f)
                elif f.suffix in ('.tiff', '.tif'):
                    siblings_tiff.append(f)

        logger.info(f"Smart import session '{key}': "
                    f"{len(siblings_ppt)} ps-ppt, {len(siblings_tiff)} tiff")

        # Load TIFFs → property maps + topography
        topography = None
        tiff_maps: Dict[str, Tuple[np.ndarray, Dict]] = {}
        tiff_channels: Dict[str, SpectralData] = {}
        # Optional preview images surfaced as first-class image entities
        # (the visible 8-bit colormapped thumbnail living inside each Park
        # .tiff alongside the float32 data tag — used to be silently dropped).
        preview_images: List[Tuple[str, "ImageData"]] = []
        # {pixel_shape: {channel_name: rgb_array}} plus the geometry of the
        # first TIFF seen at that shape. Assembled into multi-channel images
        # after the loop.
        preview_channels: Dict[Tuple[int, ...], Dict[str, np.ndarray]] = {}
        preview_geometry: Dict[Tuple[int, ...], Tuple[Any, str]] = {}

        for i, tf in enumerate(siblings_tiff):
            if progress_callback:
                progress_callback(i, len(siblings_tiff) + len(siblings_ppt),
                                  f"Loading {tf.name}")
            try:
                data, meta = load_park_tiff(tf)
                ch_name = meta.get('channel', tf.stem)
                direction = meta.get('direction', '')
                full_name = f"{ch_name} {direction}".strip()
                tiff_maps[full_name] = (data, meta)

                # Surface the 8-bit colormapped thumbnail as an Image entity.
                # The visible TIFF view is what AFM operators have been seeing
                # in their file browsers — keeping it ensures parity.
                try:
                    from PIL import Image as _PILImage
                    from src.models.image_data import (
                        ImageData as _ImageData,
                        ImageMetadata as _ImageMetadata,
                    )
                    with _PILImage.open(str(tf)) as _im:
                        _im.load()
                        thumb_arr = np.asarray(_im.convert("RGB"))
                    px_h = meta.get('scan_height_um', 0) or 0
                    px_w = meta.get('scan_width_um', 0) or 0
                    pixel_size_nm = None
                    if px_w and px_h and data.shape[0] and data.shape[1]:
                        pixel_size_nm = (
                            float(px_h) * 1000.0 / data.shape[0],
                            float(px_w) * 1000.0 / data.shape[1],
                        )
                    # Collect rather than emit: every TIFF in a Park scan is
                    # one channel/direction of the SAME scan, so they become a
                    # single multi-channel image with a selector instead of one
                    # browser row each. Bucketed by pixel shape because
                    # ImageData requires its channels to share one shape.
                    preview_channels.setdefault(thumb_arr.shape, {})[
                        full_name or tf.stem] = thumb_arr
                    preview_geometry.setdefault(
                        thumb_arr.shape, (pixel_size_nm, tf.name))
                except Exception as e:
                    logger.debug(
                        "Could not extract preview from %s: %s", tf.name, e
                    )

                # Use Z Height Backward (or any Z Height) as primary topography
                if 'z height' in ch_name.lower() and topography is None:
                    topo_meta = TopographyMetadata(
                        dimensions=data.shape,
                        physical_size=(meta.get('scan_height_um', 0),
                                       meta.get('scan_width_um', 0)),
                        units='um',
                    )
                    topography = TopographyData(data, topo_meta)

                # Create SpectralData wrapper for each TIFF channel
                tiff_meta = self.create_metadata(
                    dimensions=data.shape,
                    scan_mode='pinpoint',
                    units={'x': 'um', 'y': 'um', 'z': meta.get('channel', '')},
                    source_file=str(tf),
                    instrument='Park AFM',
                    channel=full_name,
                )
                dummy_df = pd.DataFrame({'X': [0], 'Y': [0]})
                tiff_channels[full_name] = SpectralData(
                    dummy_df, tiff_meta, data)

            except Exception as e:
                logger.warning(f"Could not load TIFF {tf.name}: {e}")

        # Load ps-ppt files → hyperspectral force curves
        ppt_offset = len(siblings_tiff)
        spectral_data = None
        ppt_channels: Dict[str, SpectralData] = {}

        for i, pf in enumerate(siblings_ppt):
            if progress_callback:
                progress_callback(ppt_offset + i,
                                  len(siblings_tiff) + len(siblings_ppt),
                                  f"Loading {pf.name}")
            try:
                sd = self._load_ppt_as_spectral(pf, tiff_maps, progress_callback)
                parsed = parse_park_filename(pf.stem)
                direction = parsed['direction'] if parsed else 'Unknown'
                ppt_channels[f"Force {direction}"] = sd
                if spectral_data is None:
                    spectral_data = sd
            except Exception as e:
                logger.warning(f"Could not load ps-ppt {pf.name}: {e}")

        if spectral_data is None and tiff_channels:
            spectral_data = next(iter(tiff_channels.values()))

        if spectral_data is None:
            raise ValueError(f"No loadable files found for session '{key}'")

        # Store all channels in metadata for the backend to unpack
        all_channels = {}
        all_channels.update(tiff_channels)
        all_channels.update(ppt_channels)
        spectral_data.metadata.additional_info['channels'] = all_channels

        # Assemble the collected per-TIFF previews into multi-channel images —
        # one per pixel geometry, so a scan's channels/directions ride in a
        # single browser entity with a channel selector. The scan's physical
        # pixel size travels with it so the viewer can draw a real scale bar.
        if preview_channels:
            try:
                from src.models.image_data import (
                    ImageData as _ImageData,
                    ImageMetadata as _ImageMetadata,
                )
                session = Path(key).stem if key else filepath.stem
                buckets = sorted(preview_channels.items(),
                                 key=lambda kv: -len(kv[1]))
                for idx, (shape, channels) in enumerate(buckets):
                    pixel_size_nm, first_file = preview_geometry.get(
                        shape, (None, None))
                    name = f"{session} (preview)"
                    if idx > 0:
                        name = f"{session} (preview {shape[1]}×{shape[0]})"
                    preview_images.append((name, _ImageData.from_channels(
                        channels, name=name,
                        metadata=_ImageMetadata(
                            source="park_tiff_preview",
                            original_filename=first_file,
                            pixel_size_nm=pixel_size_nm,
                            additional_info={'session_label': session},
                        ),
                        active_channel=self._pick_park_channel(channels),
                    )))
            except Exception as e:
                logger.debug("Could not assemble Park preview images: %s", e)

        # Surface preview images so the browser's "Images" category picks them up.
        if preview_images:
            spectral_data.metadata.additional_info['images'] = preview_images

        if progress_callback:
            total = len(siblings_tiff) + len(siblings_ppt)
            progress_callback(total, total, "Complete!")

        self.last_loaded_path = filepath
        return spectral_data, topography

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _pick_park_channel(names) -> Optional[str]:
        """Default channel for a Park scan: height topography if present."""
        if not names:
            return None
        for n in names:
            if 'height' in n.lower() and 'forward' in n.lower():
                return n
        for n in names:
            if 'height' in n.lower():
                return n
        return next(iter(names))

    def _load_ppt_as_spectral(self, filepath: Path,
                               tiff_maps: Optional[Dict] = None,
                               progress_callback=None) -> SpectralData:
        """
        Load a .ps-ppt file as a SpectralData object.

        The Force channel becomes the spectral data (rows = Z displacement,
        columns = pixel spectra).
        """
        parser = PsPptParser(filepath)
        meta = parser.parse_metadata()

        curves, z_curves = parser.load_force_map(
            target_channel='Force', progress_callback=progress_callback)

        n_pixels = parser.pixel_width * parser.pixel_height

        # Build a common Z axis (use the median-length curve as reference)
        # All curves should have roughly the same Z range
        valid_lens = [np.sum(~np.isnan(z_curves[i]))
                      for i in range(n_pixels) if z_curves[i] is not None
                      and not np.all(np.isnan(z_curves[i]))]

        if valid_lens:
            median_len = int(np.median(valid_lens))
        else:
            median_len = curves.shape[1]

        # Find a representative Z axis
        ref_idx = 0
        for i in range(n_pixels):
            n_valid = np.sum(~np.isnan(z_curves[i]))
            if n_valid == median_len:
                ref_idx = i
                break

        z_axis = z_curves[ref_idx, :median_len]

        # Truncate/interpolate all curves to median length
        spectra = np.full((median_len, n_pixels), np.nan, dtype=np.float32)
        for i in range(n_pixels):
            n_valid = int(np.sum(~np.isnan(curves[i])))
            if n_valid == 0:
                continue
            if n_valid >= median_len:
                spectra[:, i] = curves[i, :median_len]
            else:
                spectra[:n_valid, i] = curves[i, :n_valid]

        # Build DataFrame: first column = Z displacement, rest = pixel spectra
        col_names = padded_series("Px", n_pixels, start=0)
        df = pd.DataFrame(spectra, columns=col_names)
        df.insert(0, 'Z_um', z_axis)

        # Topography from TIFF if available
        topo_arr = None
        if tiff_maps:
            for name, (data, _meta) in tiff_maps.items():
                if 'z height' in name.lower():
                    topo_arr = data
                    break

        spectral_meta = self.create_metadata(
            dimensions=(parser.pixel_width, parser.pixel_height),
            scan_mode='pinpoint',
            units={
                'x': 'um', 'y': 'um',
                'independent': 'um',
                'dependent': 'V',
            },
            source_file=str(filepath),
            instrument='Park AFM',
            cantilever=meta.get('cantilever', {}),
            scan_width_um=parser.scan_width_um,
            scan_height_um=parser.scan_height_um,
            is_forward=parser.is_forward,
            acquisition_time=meta.get('time', ''),
        )

        return SpectralData(df, spectral_meta, topo_arr)

    def _load_tiff_as_spectral(self, filepath: Path) -> SpectralData:
        """Load a single Park TIFF as SpectralData with topography."""
        data, meta = load_park_tiff(filepath)

        dummy_df = pd.DataFrame({'X': [0], 'Y': [0]})
        spectral_meta = self.create_metadata(
            dimensions=data.shape,
            scan_mode='pinpoint',
            units={'x': 'um', 'y': 'um', 'z': meta.get('channel', '')},
            source_file=str(filepath),
            instrument='Park AFM',
            channel=meta.get('channel', filepath.stem),
        )

        return SpectralData(dummy_df, spectral_meta, data)
