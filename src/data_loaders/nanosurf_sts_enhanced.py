"""
Enhanced Nanosurf STS Data Loader
Improved loader with proper metadata parsing and zigzag correction as specified
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any, Optional, Tuple, List, Dict
import logging
import re

from .base_loader import BaseDataLoader
from ..utils.naming import padded_series
from ..models.spectral_data import SpectralData, SpectralMetadata
from ..models.topography_data import TopographyData

# NID file reading powered by NSFopen (vendored, MIT licensed)
# Original library by Nanosurf AG (nelson@nanosurf.com)
# See src/data_loaders/nsfopen/LICENSE for full license text
from .nsfopen import read as nid_read

logger = logging.getLogger(__name__)


class NanosurfSTSEnhancedLoader(BaseDataLoader):
    """
    Enhanced Nanosurf STS loader with support for both repetition modes.

    Nanosurf STM supports two spectroscopy mapping modes:

    1. **Repeat each position** — measurements at one grid position at a time,
       doing all N repetitions before moving to the next point. Each .nid file
       represents one grid position with shape (reps, data_points). An MxM grid
       produces M^2 files.

    2. **Repeat position list** — measurements sweep the full grid in sequence,
       then repeat. Each .nid file contains one full pass over the grid with
       shape (M^2, data_points). N repetitions produce N files.

    Grid dimensions are extracted from [DataSet\\SpecInfos\\SpecMapTable]:
    Map0=-5.05339e-007;-1.46048e-008;-5.57349e-007;-6.85389e-008;100;100;0;1
    Where positions 4 and 5 (100;100) are map_i and map_j dimensions.
    """

    def __init__(self):
        super().__init__()
        self.supported_extensions = ['.nid']
        self.loader_type = 'nanosurf_sts'

    # ── Header Parsing ──────────────────────────────────────────────────

    def _parse_repetition_mode(self, filepath: Path) -> str:
        """
        Parse the Repetition Mode from a raw NID file header.

        Returns
        -------
        'repeat_each_position' or 'repeat_position_list'
        """
        try:
            with open(filepath, 'rb') as f:
                # Read only the first 8KB — the header is always at the start
                raw = f.read(8192)
            text = raw.decode('ISO-8859-1', errors='replace')
            match = re.search(r'Repetition Mode\s*=\s*(.+)', text)
            if match:
                mode_str = match.group(1).strip()
                if 'position list' in mode_str.lower():
                    return 'repeat_position_list'
        except Exception as e:
            logger.debug(f"Could not parse repetition mode: {e}")

        # Default to the classic mode
        return 'repeat_each_position'

    def _parse_repetition_count(self, filepath: Path) -> int:
        """Parse the Repetition count from a raw NID file header."""
        try:
            with open(filepath, 'rb') as f:
                raw = f.read(8192)
            text = raw.decode('ISO-8859-1', errors='replace')
            match = re.search(r'Repetition\s*=\s*(\d+)', text)
            if match:
                return int(match.group(1))
        except Exception as e:
            logger.debug(f"Could not parse repetition count: {e}")
        return 1

    def _parse_file_fingerprint(self, filepath: Path) -> Optional[Dict]:
        """
        Parse a session fingerprint from an NID file header.

        The fingerprint identifies which measurement session a file belongs to.
        Files from the same session share the same repetition mode, data points,
        modulation time, modulation output, and grid size (nx, ny from Map0).

        Note: Absolute grid positions (x/y coordinates) drift between passes,
        so only the grid dimensions are used for grouping.

        Returns None if the file has no spectroscopy data (e.g. pure topography).
        """
        try:
            with open(filepath, 'rb') as f:
                # Read 32KB — Map0/SpecMapTable is typically at ~15KB
                raw = f.read(32768)
            text = raw.decode('ISO-8859-1', errors='replace')

            # Must have spectroscopy data
            if 'Spec forward' not in text:
                return None

            fp = {'filepath': filepath}
            patterns = {
                'repetition_mode': r'Repetition Mode\s*=\s*(.+)',
                'data_points': r'Data points\s*=\s*(\d+)',
                'modulation_time': r'Modulation time\s*=\s*(.+)',
                'mod_output': r'Mod\. output\s*=\s*(.+)',
                'spec_mode': r'SpecMode\s*=\s*(.+)',  # Map, Point, or Line
                'date': r'Date\s*=\s*([\d-]+)',
                'time': r'Time\s*=\s*([\d:]+)',
            }
            for key, pattern in patterns.items():
                match = re.search(pattern, text)
                fp[key] = match.group(1).strip() if match else None

            # Parse Map0 line — extract grid dimensions (nx, ny) for grouping
            # and full line for geometry metadata
            # Format: x_start;y_start;x_end;y_end;nx;ny;0;0
            map_match = re.search(r'Map0\s*=\s*(.+)', text)
            if map_match:
                fp['map0'] = map_match.group(1).strip()
                try:
                    vals = fp['map0'].split(';')
                    if len(vals) >= 6:
                        fp['map_dims'] = f"{int(float(vals[4]))};{int(float(vals[5]))}"
                except (ValueError, IndexError):
                    fp['map_dims'] = None
            else:
                fp['map0'] = None
                fp['map_dims'] = None

            # Parse timestamp for temporal clustering
            if fp.get('date') and fp.get('time'):
                try:
                    from datetime import datetime
                    fp['timestamp'] = datetime.strptime(
                        f"{fp['date']} {fp['time']}", "%d-%m-%Y %H:%M:%S"
                    )
                except ValueError:
                    fp['timestamp'] = None
            else:
                fp['timestamp'] = None

            # Must have at least data points to be useful
            if fp.get('data_points') is None:
                return None

            return fp
        except Exception as e:
            logger.debug(f"Could not parse fingerprint from {filepath}: {e}")
            return None

    @staticmethod
    def _fingerprint_key(fp: Dict) -> tuple:
        """Extract the grouping key from a fingerprint dict."""
        return (
            fp.get('spec_mode'),
            fp.get('repetition_mode'),
            fp.get('data_points'),
            fp.get('modulation_time'),
            fp.get('mod_output'),
            fp.get('map_dims'),
        )

    def _cluster_by_time(self, fingerprints: List[Dict],
                         max_gap_minutes: float = 15.0) -> List[List[Dict]]:
        """
        Split a list of fingerprints into temporal clusters.

        Files are sorted by timestamp. A new cluster starts when the gap
        between consecutive files exceeds max_gap_minutes.

        Default 15 minutes: STS map passes can have multi-minute gaps
        due to scanner overhead, user pauses, or drift correction.
        """
        from datetime import timedelta

        # Sort by timestamp, putting None timestamps at the end
        with_ts = [fp for fp in fingerprints if fp.get('timestamp')]
        without_ts = [fp for fp in fingerprints if not fp.get('timestamp')]
        with_ts.sort(key=lambda fp: fp['timestamp'])

        if not with_ts:
            return [fingerprints] if fingerprints else []

        clusters = []
        current = [with_ts[0]]
        for fp in with_ts[1:]:
            gap = (fp['timestamp'] - current[-1]['timestamp']).total_seconds() / 60.0
            if gap > max_gap_minutes:
                clusters.append(current)
                current = [fp]
            else:
                current.append(fp)
        clusters.append(current)

        # Attach files without timestamps to the largest cluster
        if without_ts:
            largest = max(clusters, key=len)
            largest.extend(without_ts)

        return clusters

    def _find_sibling_files(self, reference_fp: Dict,
                            directory: Path) -> List[Path]:
        """
        Find all .nid files in directory that belong to the same measurement
        session as the reference file.

        Matching criteria: same fingerprint key (rep_mode, data_points,
        mod_time, mod_output, map_dims) AND temporal proximity.
        """
        ref_key = self._fingerprint_key(reference_fp)

        nid_files = sorted(directory.glob('*.nid'), key=lambda x: x.name)
        matching_fps = []

        for fp_path in nid_files:
            fp = self._parse_file_fingerprint(fp_path)
            if fp is None:
                continue  # Skip non-STS files (topography only, etc.)

            candidate_key = self._fingerprint_key(fp)
            if candidate_key == ref_key:
                matching_fps.append(fp)

        if not matching_fps:
            return []

        # Cluster by temporal proximity
        clusters = self._cluster_by_time(matching_fps)

        # Find the cluster containing the reference file
        ref_path = reference_fp['filepath']
        for cluster in clusters:
            paths = [fp['filepath'] for fp in cluster]
            if ref_path in paths:
                logger.info(
                    f"Smart import: found {len(cluster)} files in session "
                    f"(out of {len(matching_fps)} with same parameters, "
                    f"{len(clusters)} session(s))"
                )
                return sorted(paths, key=lambda x: x.name)

        # Fallback: return all matching files
        return sorted([fp['filepath'] for fp in matching_fps], key=lambda x: x.name)

    # ── Smart Import (single-file entry point) ──────────────────────────

    def smart_load_from_file(self, filepath: Path,
                             progress_callback=None):
        """
        Smart map import: the user picks ONE .nid file and the loader finds
        all sibling files from the same measurement session automatically.

        This handles directories where multiple sessions (or non-STS files)
        are mixed together.

        Parameters
        ----------
        filepath : Path
            A single .nid file from the target measurement session.
        progress_callback : callable, optional
            Callback function(current, total, message) for progress updates.

        Returns
        -------
        spectral_data : SpectralData
        topography : TopographyData or None

        Raises
        ------
        ValueError
            If siblings cannot be found or the dataset is incomplete.
        """
        filepath = Path(filepath)
        directory = filepath.parent

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        # Parse the reference file's fingerprint
        ref_fp = self._parse_file_fingerprint(filepath)
        if ref_fp is None:
            raise ValueError(
                f"{filepath.name} does not contain spectroscopy data. "
                "Please select a file from a spectroscopy map measurement."
            )

        logger.info(
            f"Smart import: reference file {filepath.name} — "
            f"mode={ref_fp.get('repetition_mode')}, "
            f"data_points={ref_fp.get('data_points')}, "
            f"mod_time={ref_fp.get('modulation_time')}"
        )

        if progress_callback:
            progress_callback(0, 1, "Scanning directory for sibling files...")

        # Find all matching files
        siblings = self._find_sibling_files(ref_fp, directory)
        logger.info(f"Found {len(siblings)} matching files in {directory}")

        if not siblings:
            raise ValueError(
                f"No matching files found in {directory}. "
                "Could not assemble a dataset."
            )

        # Now delegate to the standard loading pipeline
        rep_mode = self._parse_repetition_mode(siblings[0])
        spec_mode = ref_fp.get('spec_mode', 'Map')
        logger.info(f"Repetition mode: {rep_mode}, spec mode: {spec_mode}, "
                    f"loading {len(siblings)} files")

        if rep_mode == 'repeat_position_list':
            return self._load_repeat_position_list(siblings, directory, progress_callback,
                                                   spec_mode=spec_mode)
        else:
            return self._load_repeat_each_position(siblings, directory, progress_callback,
                                                   spec_mode=spec_mode)

    def parse_nid_metadata(self, nid_obj) -> Dict:
        """
        Parse metadata from NID object, extracting grid dimensions.

        Parameters
        ----------
        nid_obj : NSFopen object
            Loaded NID file object

        Returns
        -------
        metadata : Dict
            Parsed metadata including dimensions
        """
        metadata = {
            'dimensions': None,
            'scan_area': None,
            'data_points': None,
            'parameters': {}
        }

        # Try to get parameters from param attribute
        if hasattr(nid_obj, 'param'):
            params = nid_obj.param
            metadata['parameters'] = params

            # Look for SpecMapTable
            if 'SpecMapTable' in params or hasattr(nid_obj, 'SpecMapTable'):
                map_table = params.get('SpecMapTable', getattr(nid_obj, 'SpecMapTable', None))

                if map_table and 'Map0' in str(map_table):
                    # Parse Map0 line
                    map0_str = str(map_table.get('Map0', ''))
                    dimensions = self._parse_map0_line(map0_str)
                    if dimensions:
                        metadata['dimensions'] = dimensions

        # Alternative: Try direct text parsing if NSFopen doesn't expose it properly
        if metadata['dimensions'] is None:
            try:
                # Read raw file content
                if hasattr(nid_obj, 'filename'):
                    with open(nid_obj.filename, 'r', errors='ignore') as f:
                        content = f.read(32768)  # Map0 can be at ~15KB

                    # Look for Map0 line
                    map0_match = re.search(r'Map0=([\d.e+-]+;)+[\d.e+-]+', content)
                    if map0_match:
                        map0_str = map0_match.group(0).split('=')[1]
                        dimensions = self._parse_map0_line(map0_str)
                        if dimensions:
                            metadata['dimensions'] = dimensions
                        map_geometry = self._parse_map0_full(map0_str)
                        if map_geometry:
                            metadata['map_geometry'] = map_geometry
            except Exception as e:
                logger.debug(f"Could not parse dimensions from raw file: {e}")

        # Get data points from spectroscopy parameters
        if hasattr(nid_obj.data, 'Spec') and hasattr(nid_obj.data.Spec, 'Forward'):
            try:
                I_forward = np.array(nid_obj.data.Spec.Forward.get("Tip Current",
                                                                   nid_obj.data.Spec.Forward.get("Current")))
                metadata['data_points'] = I_forward.shape[-1]
            except Exception as e:
                logger.debug(f"Could not extract data points: {e}")

        return metadata

    def _parse_map0_line(self, map0_str: str) -> Optional[Tuple[int, int]]:
        """
        Parse Map0 line to extract grid dimensions.

        Format: Map0=x_start;y_start;x_end;y_end;nx;ny;0;0
        Positions 4 and 5 are (nx, ny) grid dimensions.
        """
        try:
            values = map0_str.split(';')
            if len(values) >= 6:
                map_i = int(float(values[4]))
                map_j = int(float(values[5]))
                logger.info(f"Extracted dimensions from Map0: {map_i} x {map_j}")
                return (map_i, map_j)
        except (ValueError, IndexError) as e:
            logger.warning(f"Could not parse Map0 line '{map0_str}': {e}")

        return None

    def _parse_map0_full(self, map0_str: str) -> Optional[Dict]:
        """
        Parse Map0 line to extract full map geometry.

        Format: Map0=x_start;y_start;x_end;y_end;nx;ny;0;0
        Returns dict with x_start, y_start, x_end, y_end (meters), nx, ny.
        """
        try:
            values = map0_str.split(';')
            if len(values) >= 6:
                return {
                    'x_start': float(values[0]),
                    'y_start': float(values[1]),
                    'x_end': float(values[2]),
                    'y_end': float(values[3]),
                    'nx': int(float(values[4])),
                    'ny': int(float(values[5])),
                }
        except (ValueError, IndexError) as e:
            logger.warning(f"Could not parse Map0 geometry '{map0_str}': {e}")
        return None

    # ── Topography & Voltage Helpers ────────────────────────────────────

    def _extract_topography(self, stm_nid) -> Optional[TopographyData]:
        """Extract topography from an NID object, if available."""
        if not hasattr(stm_nid.data, 'Image'):
            return None
        try:
            z_forward = np.array(stm_nid.data.Image.Forward.get("Z-Axis",
                                                                 stm_nid.data.Image.Forward.get("Height")))
            z_backward = np.array(stm_nid.data.Image.Backward.get("Z-Axis",
                                                                   stm_nid.data.Image.Backward.get("Height")))
            topo = TopographyData.from_forward_backward(
                z_forward, z_backward, flip_vertical=True
            )
            logger.info(f"Extracted topography with dimensions {topo.data.shape}")
            return topo
        except Exception as e:
            logger.warning(f"Could not extract topography: {e}")
            return None

    def _extract_image_channels(self, stm_nid, file_label: str) -> List[Tuple[str, "Any"]]:
        """Surface every Nanosurf Image channel as an :class:`ImageData`.

        Each ``.nid`` file may contain forward / backward scans of multiple
        channels (Z-Axis / Amplitude / Phase / Z-Axis Sensor, …). The legacy
        loader keeps Z-Axis as topography and silently drops the rest;
        this helper turns each (direction, channel) into a SINGLE_FLOAT
        :class:`ImageData` so the user can browse them under the new
        Images category.

        Z-Axis channels are returned as well — useful when the file is
        image-only (no spectra) and the topography path doesn't run.
        """
        out: List[Tuple[str, Any]] = []
        if not hasattr(stm_nid.data, "Image"):
            return out
        # Local imports to avoid pulling Qt-optional ImageData when this
        # loader runs in a headless context that doesn't need it.
        try:
            from src.models.image_data import ImageData, ImageMode, ImageMetadata
        except Exception:
            return out

        # ``stm_nid.data`` is a pandas Series indexed by (category, direction,
        # channel). Iterate the Image rows directly so we don't depend on the
        # ``.Image.Forward`` accessor working when only one direction is present.
        try:
            entries = list(stm_nid.data.items())
        except Exception:
            return out

        # Collect every (channel, direction) plane first. They are all views of
        # the same physical scan, so they become ONE image entity with a
        # channel selector rather than one browser row per plane. Planes are
        # bucketed by pixel shape because ``ImageData`` requires its channels
        # to share a shape — a NID that mixes resolutions still loads, it just
        # yields one entity per resolution.
        by_shape: Dict[Tuple[int, int], Dict[str, np.ndarray]] = {}
        channel_meta: Dict[str, Dict[str, str]] = {}
        for key, value in entries:
            try:
                category, direction, channel = key
            except Exception:
                continue
            if category != "Image":
                continue
            try:
                arr = np.asarray(value)
            except Exception:
                continue
            if arr.ndim != 2 or arr.size == 0:
                continue
            cname = f"{channel} ({direction})".strip()
            by_shape.setdefault(arr.shape, {})[cname] = \
                arr.astype(np.float32, copy=False)
            channel_meta[cname] = {"nid_category": category,
                                   "nid_direction": direction,
                                   "nid_channel": channel}

        if not by_shape:
            return out

        source_file = (Path(stm_nid.filename).name
                       if getattr(stm_nid, "filename", None) else None)
        # Largest bucket first, so the main scan resolution keeps the plain
        # label and any odd-sized extras get the disambiguating suffix.
        buckets = sorted(by_shape.items(), key=lambda kv: -len(kv[1]))
        for idx, (shape, channels) in enumerate(buckets):
            name = file_label.strip()
            if idx > 0:
                name = f"{name} [{shape[1]}×{shape[0]}]"
            try:
                img = ImageData.from_channels(
                    channels, name=name, mode=ImageMode.SINGLE_FLOAT,
                    metadata=ImageMetadata(
                        source="nanosurf_nid_image",
                        original_filename=source_file,
                        additional_info={
                            "channel_meta": {c: channel_meta[c]
                                             for c in channels},
                        },
                    ),
                    active_channel=self._pick_nid_channel(channels),
                )
                out.append((name, img))
            except Exception as e:
                logger.debug("Skipping NID image group %s: %s", shape, e)
        return out

    @staticmethod
    def _pick_nid_channel(names) -> Optional[str]:
        """Default channel for a NID scan: forward topography when present."""
        if not names:
            return None
        for n in names:
            if n.startswith("Z-Axis") and "Forward" in n:
                return n
        for n in names:
            if n.startswith("Z-Axis"):
                return n
        return next(iter(names))

    def _extract_scan_geometry(self, filepath: Path) -> Optional[Dict]:
        """
        Extract the topography scan geometry from an NID file header.

        Returns dict with scan_range_x, scan_range_y, offset_x, offset_y (meters),
        and the derived image bounds (x_min, x_max, y_min, y_max).
        """
        try:
            with open(filepath, 'rb') as f:
                raw = f.read(32768)
            text = raw.decode('ISO-8859-1', errors='replace')

            # ScanRange=V[1e-07,1e-07,0]*[m,m,m]
            sr = re.search(r'ScanRange\s*=\s*V\[([\d.e+-]+),([\d.e+-]+)', text)
            # ScanOffset=V[0,0,0]*[m,m,m]
            so = re.search(r'ScanOffset\s*=\s*V\[([\d.e+-]+),([\d.e+-]+)', text)

            if sr:
                range_x = float(sr.group(1))
                range_y = float(sr.group(2))
                offset_x = float(so.group(1)) if so else 0.0
                offset_y = float(so.group(2)) if so else 0.0

                return {
                    'scan_range_x': range_x,
                    'scan_range_y': range_y,
                    'offset_x': offset_x,
                    'offset_y': offset_y,
                    'x_min': offset_x - range_x / 2,
                    'x_max': offset_x + range_x / 2,
                    'y_min': offset_y - range_y / 2,
                    'y_max': offset_y + range_y / 2,
                }
        except Exception as e:
            logger.debug(f"Could not extract scan geometry: {e}")
        return None

    def _extract_voltage(self, stm_nid) -> Optional[np.ndarray]:
        """Extract the voltage array from an NID object."""
        try:
            V = np.array(stm_nid.data.Spec.Forward.get("Tip voltage",
                                                        stm_nid.data.Spec.Forward.get("Voltage")))
            # V may be (reps, n_pts) or (M^2, n_pts) — first row is fine
            if V.ndim == 2:
                return V[0, :]
            return V
        except (IndexError, TypeError, AttributeError):
            return self._generate_voltage_array_from_metadata(stm_nid)

    # ── Main Entry Point ────────────────────────────────────────────────

    def load_from_directory(self, directory: Path,
                           progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
        """
        Load STS data from directory of .nid files with zigzag correction.

        Automatically detects the repetition mode from the first file's header
        and delegates to the appropriate loading strategy.

        Parameters
        ----------
        directory : Path
            Directory containing .nid files
        progress_callback : callable, optional
            Callback function(current, total, message) for progress updates

        Returns
        -------
        spectral_data : SpectralData
            Concatenated spectral data with zigzag correction
        topography : TopographyData or None
            Average topography from first file
        """
        directory = Path(directory)

        if not self.validate_directory(directory):
            raise ValueError(f"Invalid directory: {directory}")

        # Find all .nid files (sorted alphabetically)
        all_nid = sorted(self.find_files(directory), key=lambda x: x.name)

        if not all_nid:
            raise ValueError(f"No .nid files found in {directory}")

        # Parse fingerprints and group by session key + temporal proximity
        param_groups = {}
        all_fps = []
        for f in all_nid:
            fp = self._parse_file_fingerprint(f)
            if fp is None:
                continue  # Skip topo-only files
            all_fps.append(fp)
            key = self._fingerprint_key(fp)
            param_groups.setdefault(key, []).append(fp)

        if not param_groups:
            raise ValueError(
                f"No spectroscopy .nid files found in {directory} "
                f"({len(all_nid)} files scanned, all appear to be topography-only)"
            )

        # For each parameter group, split by temporal clustering
        all_sessions = []
        for key, fps in param_groups.items():
            clusters = self._cluster_by_time(fps)
            for cluster in clusters:
                all_sessions.append(cluster)

        # Use the largest temporal cluster
        best = max(all_sessions, key=len)
        nid_files = sorted([fp['filepath'] for fp in best], key=lambda x: x.name)

        skipped = len(all_nid) - len(nid_files)
        if skipped > 0:
            logger.info(
                f"Found {len(all_sessions)} session(s) across "
                f"{len(param_groups)} parameter group(s); using largest with "
                f"{len(nid_files)} files (skipped {skipped} others)"
            )

        # Detect repetition mode and spec mode from the session
        rep_mode = self._parse_repetition_mode(nid_files[0])
        spec_mode = best[0].get('spec_mode', 'Map')
        logger.info(f"Detected repetition mode: {rep_mode}, spec mode: {spec_mode} "
                    f"({len(nid_files)} STS files)")

        if rep_mode == 'repeat_position_list':
            return self._load_repeat_position_list(nid_files, directory, progress_callback,
                                                   spec_mode=spec_mode)
        else:
            return self._load_repeat_each_position(nid_files, directory, progress_callback,
                                                   spec_mode=spec_mode)

    # ── Repeat Each Position ────────────────────────────────────────────

    def _load_repeat_each_position(self, nid_files: List[Path], directory: Path,
                                   progress_callback=None, spec_mode='Map'):
        """
        Load STS data in "Repeat each position" mode.

        Each file = one grid position with N repetitions: shape (reps, data_pts).
        Average over repetitions → 1 spectrum per file.
        """
        logger.info(f"Loading {len(nid_files)} .nid files (repeat each position)")

        all_spectra_forward = []
        all_spectra_backward = []
        all_spectra_mixed = []
        V_common = None
        topography = None
        dimensions = None
        map_geometry = None
        topo_geometry = None

        for i, filepath in enumerate(nid_files):
            try:
                if progress_callback:
                    progress_callback(i, len(nid_files), f"Loading {filepath.name}")

                stm_nid = nid_read(str(filepath))

                # Parse metadata: dimensions from first file, map geometry updated per file
                metadata_dict = self.parse_nid_metadata(stm_nid)
                if dimensions is None:
                    if metadata_dict['dimensions']:
                        dimensions = metadata_dict['dimensions']
                        logger.info(f"Grid dimensions: {dimensions}")
                if metadata_dict.get('map_geometry'):
                    mg = metadata_dict['map_geometry']
                    w = abs(mg['x_end'] - mg['x_start'])
                    h = abs(mg['y_end'] - mg['y_start'])
                    if w > 1e-12 and h > 1e-12:
                        map_geometry = mg

                # Extract spectroscopy data
                if hasattr(stm_nid.data, 'Spec'):
                    I_forward = np.array(stm_nid.data.Spec.Forward.get("Tip Current",
                                                                       stm_nid.data.Spec.Forward.get("Current")))
                    I_backward = np.array(stm_nid.data.Spec.Backward.get("Tip Current",
                                                                         stm_nid.data.Spec.Backward.get("Current")))

                    # Average over repetitions (axis=0): (reps, data_pts) → (data_pts,)
                    I_mean_forward = np.mean(I_forward, axis=0)
                    I_mean_backward = np.mean(I_backward, axis=0)
                    I_mean_mixed = (I_mean_forward + I_mean_backward) / 2

                    all_spectra_forward.append(I_mean_forward)
                    all_spectra_backward.append(I_mean_backward)
                    all_spectra_mixed.append(I_mean_mixed)

                    # Get voltage array
                    if V_common is None:
                        V_common = self._extract_voltage(stm_nid)
                        if V_common is not None:
                            logger.info(f"Voltage range: [{V_common.min():.3f}, {V_common.max():.3f}] V "
                                        f"({len(V_common)} points)")

                # Extract topography and scan geometry from first file
                if topography is None:
                    topography = self._extract_topography(stm_nid)
                    if topography is not None and topo_geometry is None:
                        topo_geometry = self._extract_scan_geometry(filepath)

            except Exception as e:
                logger.error(f"Error processing {filepath.name}: {e}")
                continue

        if not all_spectra_mixed:
            # Image-only NID files (no Spec channels) take this branch.
            # Build a placeholder dataset that just carries the images so
            # the user can browse them under the Images category. The
            # loader contract still returns a SpectralData; a stub
            # 1-point DataFrame keeps existing callers from blowing up.
            return self._build_image_only_result(
                nid_files, directory, progress_callback,
            )

        # Check file count vs expected grid size
        if dimensions is not None:
            expected = dimensions[0] * dimensions[1]
            actual = len(all_spectra_mixed)
            if actual != expected:
                logger.warning(
                    f"File count mismatch: expected {expected} files for "
                    f"{dimensions[0]}x{dimensions[1]} grid, got {actual}"
                )

        # Infer dimensions if not from metadata
        if dimensions is None:
            dimensions = self._infer_dimensions(len(all_spectra_mixed), topography)

        return self._build_result(
            all_spectra_forward, all_spectra_backward, all_spectra_mixed,
            V_common, dimensions, topography, nid_files, directory, progress_callback,
            map_geometry=map_geometry, topo_geometry=topo_geometry,
            spec_mode=spec_mode
        )

    # ── Repeat Position List ────────────────────────────────────────────

    def _load_repeat_position_list(self, nid_files: List[Path], directory: Path,
                                   progress_callback=None, spec_mode='Map'):
        """
        Load STS data in "Repeat position list" mode.

        Each file = one full pass over the grid: shape (M^2, data_pts).
        Average across files (same grid position) → M^2 spectra total.
        """
        logger.info(f"Loading {len(nid_files)} .nid files (repeat position list)")

        # We accumulate running sums for averaging across files
        sum_forward = None
        sum_backward = None
        n_files_loaded = 0
        V_common = None
        topography = None
        dimensions = None
        map_geometry = None
        topo_geometry = None
        n_spectra_per_file = None

        for i, filepath in enumerate(nid_files):
            try:
                if progress_callback:
                    progress_callback(i, len(nid_files), f"Loading {filepath.name}")

                stm_nid = nid_read(str(filepath))

                # Parse metadata: dimensions from first file, map geometry updated per file
                metadata_dict = self.parse_nid_metadata(stm_nid)
                if dimensions is None:
                    if metadata_dict['dimensions']:
                        dimensions = metadata_dict['dimensions']
                        logger.info(f"Grid dimensions: {dimensions}")
                # Keep updating map_geometry — last file gives most current positions
                if metadata_dict.get('map_geometry'):
                    mg = metadata_dict['map_geometry']
                    # Skip degenerate entries (near-zero area)
                    w = abs(mg['x_end'] - mg['x_start'])
                    h = abs(mg['y_end'] - mg['y_start'])
                    if w > 1e-12 and h > 1e-12:
                        map_geometry = mg

                if not hasattr(stm_nid.data, 'Spec'):
                    logger.warning(f"No spectroscopy data in {filepath.name}, skipping")
                    continue

                I_forward = np.array(stm_nid.data.Spec.Forward.get("Tip Current",
                                                                    stm_nid.data.Spec.Forward.get("Current")))
                I_backward = np.array(stm_nid.data.Spec.Backward.get("Tip Current",
                                                                      stm_nid.data.Spec.Backward.get("Current")))

                # Shape should be (M^2, data_pts)
                if I_forward.ndim != 2:
                    logger.warning(f"Unexpected data shape {I_forward.shape} in {filepath.name}, skipping")
                    continue

                n_spectra = I_forward.shape[0]
                n_data_pts = I_forward.shape[1]

                # Validate consistency across files (both spectra count AND data points)
                if n_spectra_per_file is None:
                    n_spectra_per_file = n_spectra
                    n_data_pts_expected = n_data_pts
                    logger.info(f"Spectra per file: {n_spectra}, data points: {n_data_pts}")
                else:
                    if n_spectra != n_spectra_per_file:
                        logger.warning(
                            f"Spectrum count mismatch in {filepath.name}: expected "
                            f"{n_spectra_per_file}, got {n_spectra} — skipping"
                        )
                        continue
                    if n_data_pts != n_data_pts_expected:
                        logger.warning(
                            f"Data points mismatch in {filepath.name}: expected "
                            f"{n_data_pts_expected}, got {n_data_pts} — skipping"
                        )
                        continue

                # Accumulate running sum for each grid position
                if sum_forward is None:
                    sum_forward = I_forward.copy()
                    sum_backward = I_backward.copy()
                else:
                    sum_forward += I_forward
                    sum_backward += I_backward

                n_files_loaded += 1

                # Get voltage array
                if V_common is None:
                    V_common = self._extract_voltage(stm_nid)
                    if V_common is not None:
                        logger.info(f"Voltage range: [{V_common.min():.3f}, {V_common.max():.3f}] V "
                                    f"({len(V_common)} points)")

                # Extract topography and scan geometry from first file
                if topography is None:
                    topography = self._extract_topography(stm_nid)
                    if topography is not None and topo_geometry is None:
                        topo_geometry = self._extract_scan_geometry(filepath)

            except Exception as e:
                logger.error(f"Error processing {filepath.name}: {e}")
                continue

        if sum_forward is None or n_files_loaded == 0:
            raise ValueError("No spectral data could be extracted")

        logger.info(f"Averaging {n_files_loaded} repetition files for {n_spectra_per_file} grid positions")

        # Average across files: sum / n_files → (M^2, data_pts)
        avg_forward = sum_forward / n_files_loaded
        avg_backward = sum_backward / n_files_loaded
        avg_mixed = (avg_forward + avg_backward) / 2

        # Convert (M^2, data_pts) matrices → list of 1D spectra
        all_spectra_forward = [avg_forward[j, :] for j in range(n_spectra_per_file)]
        all_spectra_backward = [avg_backward[j, :] for j in range(n_spectra_per_file)]
        all_spectra_mixed = [avg_mixed[j, :] for j in range(n_spectra_per_file)]

        # Infer dimensions if not from metadata
        if dimensions is None:
            dimensions = self._infer_dimensions(n_spectra_per_file, topography)

        # Validate spectra count vs grid
        if dimensions is not None:
            expected = dimensions[0] * dimensions[1]
            if n_spectra_per_file != expected:
                logger.warning(
                    f"Spectra count mismatch: each file has {n_spectra_per_file} spectra "
                    f"but grid is {dimensions[0]}x{dimensions[1]} = {expected}"
                )

        return self._build_result(
            all_spectra_forward, all_spectra_backward, all_spectra_mixed,
            V_common, dimensions, topography, nid_files, directory, progress_callback,
            n_repetitions=n_files_loaded, map_geometry=map_geometry,
            topo_geometry=topo_geometry, spec_mode=spec_mode
        )

    # ── Shared Helpers ──────────────────────────────────────────────────

    def _infer_dimensions(self, n_spectra: int,
                          topography: Optional[TopographyData]) -> Tuple[int, int]:
        """Infer grid dimensions from spectra count or topography."""
        if topography is not None:
            dims = (topography.width, topography.height)
            logger.info(f"Inferred dimensions from topography: {dims}")
            return dims

        # Guess square grid
        dim_guess = int(np.sqrt(n_spectra))
        if dim_guess * dim_guess == n_spectra:
            dims = (dim_guess, dim_guess)
        else:
            dims = (n_spectra, 1)
        logger.info(f"Inferred dimensions: {dims}")
        return dims

    def _build_image_only_result(
        self, nid_files: List[Path], directory: Path, progress_callback,
    ) -> Tuple[SpectralData, Optional[TopographyData]]:
        """Return a placeholder dataset carrying images-only Nanosurf data.

        Used when ``.nid`` files contain just AFM image channels (no Spec
        section) — for example, a topography-only scan. Each image channel
        is surfaced via ``additional_info['images']`` so it appears under
        the Images browser category. The "primary" SpectralData is a
        1-point stub so the existing dispatcher contract still holds.
        """
        session_images: List[Tuple[str, Any]] = []
        topography: Optional[TopographyData] = None
        topo_geometry: Optional[Dict] = None
        for filepath in nid_files:
            try:
                stm_nid = nid_read(str(filepath))
            except Exception as e:
                logger.debug(f"Could not read {filepath.name}: {e}")
                continue
            session_images.extend(self._extract_image_channels(stm_nid, filepath.stem))
            if topography is None:
                topography = self._extract_topography(stm_nid)
                if topography is not None:
                    topo_geometry = self._extract_scan_geometry(filepath)

        if not session_images and topography is None:
            raise ValueError(
                "No spectroscopy and no image channels could be extracted "
                f"from {directory}"
            )

        df = pd.DataFrame({"V": [0.0], "Empty": [0.0]})
        meta = SpectralMetadata(
            source_type="nanosurf_sts",
            dimensions=(0, 0),
            scan_mode="image-only",
            units={"independent": "n/a", "dependent": "n/a"},
            additional_info={
                "placeholder": True,
                "n_files": len(nid_files),
                "source_directory": str(directory),
            },
        )
        sd = SpectralData(df, meta, topography.data if topography else None)
        if session_images:
            sd.metadata.additional_info["images"] = session_images
            logger.info(
                f"Image-only NID load: surfaced {len(session_images)} channel(s) "
                f"from {len(nid_files)} file(s)"
            )
        if topo_geometry is not None:
            sd.metadata.additional_info["topo_geometry"] = topo_geometry
        if progress_callback:
            progress_callback(len(nid_files), len(nid_files), "Complete!")
        self.last_loaded_path = directory
        return sd, topography

    def _build_result(self, all_fwd, all_bwd, all_mix, V_common,
                      dimensions, topography, nid_files, directory,
                      progress_callback, n_repetitions=None,
                      map_geometry=None, topo_geometry=None,
                      spec_mode='Map'):
        """Build SpectralData results for all three channels."""
        results = {}

        # Only Map mode uses meander scan pattern; Point/Line are sequential
        scan_mode = "meander" if spec_mode == 'Map' else "sequential"

        for channel_name, spectra_list in [
            ('Forward', all_fwd),
            ('Backward', all_bwd),
            ('Mixed', all_mix)
        ]:
            df = self.concatenate_spectra(
                spectra_list,
                V_common,
                column_names=padded_series("Point", len(spectra_list))
            )
            df = df.rename(columns={"Variable": "V"})

            additional = {
                'n_files': len(nid_files),
                'source_directory': str(directory),
                'channel': channel_name,
                'spec_mode': spec_mode,
            }
            if n_repetitions is not None:
                additional['n_repetitions_averaged'] = n_repetitions
            if map_geometry is not None:
                additional['map_geometry'] = map_geometry
            if topo_geometry is not None:
                additional['topo_geometry'] = topo_geometry

            metadata = self.create_metadata(
                dimensions=dimensions,
                scan_mode=scan_mode,
                units={"independent": "V", "dependent": "A", "x": "nm", "y": "nm"},
                **additional
            )

            spectral_data = SpectralData(df, metadata, topography.data if topography else None)
            spectral_data.correct_meander()
            results[channel_name] = spectral_data

        if progress_callback:
            progress_callback(len(nid_files), len(nid_files), "Complete!")

        self.last_loaded_path = directory
        logger.info(f"Successfully loaded STS data: {len(results)} channels")

        # Return the mixed channel as primary, but store others in metadata
        primary_data = results['Mixed']
        primary_data.metadata.additional_info['channels'] = results

        # Surface every Image channel (Z-Axis / Amplitude / Phase / Sensor,
        # forward + backward) as ImageData entries so the browser's Images
        # category shows them. Cheap second pass over the .nid headers — the
        # raw arrays are already cached by NSFopen on first read.
        try:
            session_images = []
            for filepath in nid_files:
                try:
                    stm_nid = nid_read(str(filepath))
                except Exception:
                    continue
                session_images.extend(
                    self._extract_image_channels(stm_nid, filepath.stem)
                )
            if session_images:
                primary_data.metadata.additional_info['images'] = session_images
                logger.info(
                    f"Surfaced {len(session_images)} Nanosurf image channel(s)"
                )
        except Exception as e:
            logger.debug(f"Nanosurf image-channel surfacing failed: {e}")

        return primary_data, topography

    def load_single_file(self, filepath: Path) -> SpectralData:
        """Load data from a single .nid file (delegates to load_from_directory)."""
        return self.load_from_directory(filepath.parent)[0]

    def _generate_voltage_array_from_metadata(self, stm_nid) -> np.ndarray:
        """Generate voltage array from metadata when direct extraction fails."""
        try:
            if hasattr(stm_nid.data, 'Spec') and hasattr(stm_nid.data.Spec, 'Forward'):
                I_data = np.array(stm_nid.data.Spec.Forward.get("Tip Current",
                                                                stm_nid.data.Spec.Forward.get("Current")))
                n_points = I_data.shape[-1]

                if hasattr(stm_nid, 'param'):
                    params = stm_nid.param
                    v_min, v_max = None, None

                    for min_key in ['V_min', 'Vmin', 'VoltageMin', 'StartVoltage']:
                        if min_key in params:
                            v_min = float(params[min_key])
                            break

                    for max_key in ['V_max', 'Vmax', 'VoltageMax', 'EndVoltage']:
                        if max_key in params:
                            v_max = float(params[max_key])
                            break

                    if v_min is not None and v_max is not None:
                        V = np.linspace(v_min, v_max, n_points)
                        logger.info(f"Generated voltage array: [{v_min}, {v_max}] V ({n_points} points)")
                        return V

            logger.warning("Could not find voltage range in metadata, using generic array")
            return np.arange(n_points) if 'n_points' in locals() else np.arange(100)

        except Exception as e:
            logger.error(f"Error generating voltage array from metadata: {e}")
            return np.arange(100)
