# ============================================================================
# T.R.A.N.S. version 1.0
# Tools for Research and Analysis for Nano Spectroscopy
#
# Created by Eduarda Policarpo, in November of 2025 with love.
#
# File: omicron_mtrx_loader.py
# Description: Loader for Omicron / Scienta Omicron MATRIX result files.
#
# This loader uses the battle-tested ``access2theMatrix`` library
# (Stephan Zevenhuizen) as its binary-parsing engine and builds T.R.A.N.S.
# data structures on top of it:
#
#   - Spectroscopy curves (.I(V)_mtrx, .Aux2(V)_mtrx, .I(Z)_mtrx, ...) are
#     grouped into BATCHES by STS location. A batch = all repetitions taken at
#     one physical point. A session with several points is an ordered point set
#     / line scan ("repetitions done at N points").
#   - Every spectrum carries its acquisition TIMESTAMP, its STS LOCATION
#     (pixel + metres), and a link to the topography IMAGE it was taken on.
#   - Scan images (.Z_mtrx, .I_mtrx) are read as geometry-aware maps AND as
#     browsable pictures, so the user can see WHERE each spectrum was taken.
# ============================================================================

"""Omicron MATRIX data loader (access2theMatrix-backed).

The public entry points return ``(SpectralData, Optional[TopographyData])``
to keep the loader interface uniform, but the rich, structured payload that
the backend needs to build per-session folders, per-point datasets, maps and
images lives in ``SpectralData.metadata.additional_info`` under the keys
``matrix_import``, ``sessions`` and ``images`` (see :meth:`smart_load_from_file`).
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from struct import unpack_from
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base_loader import BaseDataLoader
from ..models.spectral_data import SpectralData
from ..models.topography_data import TopographyData

logger = logging.getLogger(__name__)

# access2theMatrix is the parsing engine. Imported lazily/guarded so the
# module still imports (e.g. for unit tests of the pure helpers) when the
# library is absent.
try:  # pragma: no cover - import guard
    import access2thematrix as _a2m
except Exception:  # pragma: no cover
    _a2m = None


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------

def _read_tlkb_seconds(path: Path) -> Optional[datetime]:
    """Read the acquisition timestamp from a MATRIX result file.

    Every ONTMATRX result file opens with a ``TLKB`` block whose first 8 bytes
    (after the 8-byte tag+size) are the acquisition time as Unix seconds
    (uint64 LE). access2theMatrix formats this as a string and discards the raw
    value, so we read it straight from the bytes to get a real ``datetime``.
    """
    try:
        raw = path.read_bytes()
        idx = raw.find(b'TLKB')
        if idx < 0:
            return None
        secs = unpack_from('<Q', raw, idx + 8)[0]
        if not secs:
            return None
        return datetime.fromtimestamp(secs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not read TLKB timestamp from %s: %s", path, exc)
        return None


def _session_label(base: str) -> str:
    """Short, human-friendly session label from a result-file base name.

    ``default_2026Jun15-203637_STM-STM_Spectroscopy`` -> ``2026Jun15-203637``.
    Falls back to the whole base name when the convention doesn't match.
    """
    m = re.search(r'default_([0-9A-Za-z-]+?)_', base)
    return m.group(1) if m else base


def _parse_run_scan(filename: str) -> Tuple[int, int]:
    """Extract (run, scan) cycle indices from ``...--<run>_<scan>.<chan>_mtrx``.

    The run index identifies a physical point / experiment; the scan index is
    the repetition at that point. Returns ``(0, 0)`` when the name doesn't
    match (keeps callers crash-free for odd inputs).
    """
    try:
        after = filename.split('--', 1)[1]
        ax = after.split('.', 1)[0]
        run_s, scan_s = ax.split('_', 1)
        return int(run_s), int(scan_s)
    except Exception:
        return 0, 0


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class OmicronMatrixSTSLoader(BaseDataLoader):
    """Loader for Omicron MATRIX spectroscopy + scan-image data.

    Spectroscopy curves are grouped into batches (by STS location), each batch
    holding the repetitions at one point; scan images are surfaced as
    geometry-aware maps and as pictures.
    """

    MAGIC_NUMBER = b'ONTMATRX0101'

    # Spectroscopy sweep extensions (forward + backward traces).
    SPECTROSCOPY_EXTENSIONS = [
        '.I(V)_mtrx', '.Aux2(V)_mtrx', '.Aux1(V)_mtrx',
        '.I(Z)_mtrx', '.Z(V)_mtrx', '.Aux2(Z)_mtrx', '.Aux1(Z)_mtrx',
    ]
    # Scan-image channels (2-D topography / current maps).
    IMAGE_EXTENSIONS = ['.Z_mtrx', '.I_mtrx']

    # Spectroscopy channels preferred as the "primary" curve, best first.
    _PRIMARY_PRIORITY = ['I(V)', 'Aux2(V)', 'Aux1(V)', 'I(Z)', 'Z(V)']

    # ADC saturation-rail codes. The current ADC is 16-bit, stored in the high
    # word of each int32, so a saturated sample pegs at 0x80000000 (negative
    # rail) or 0x7FFF0000 (positive rail); 0x7FFFFFFF is treated as a rail too.
    # These exact integer codes are representable in float64, so equality
    # masking is reliable. Railed samples carry no real current and are set to
    # NaN so the rendered curve breaks at saturation instead of plotting flat
    # ±full-scale plateaus that dominate range / dI/dV / auto-scale.
    _ADC_RAIL_CODES = (-2147483648.0, 2147418112.0, 2147483647.0)

    def __init__(self):
        super().__init__()
        self.supported_extensions = ['.I(V)_mtrx']
        self.loader_type = 'omicron_matrix_sts'

    @staticmethod
    def _new_md():
        """A fast :class:`access2thematrix.MtrxData` instance.

        ``MtrxData._get_ref_by`` resolves each spectrum's exact parent scan
        file by listing the whole session directory and regex-matching every
        file — O(directory) per curve, which dominates load time for big
        sessions (thousands of files → minutes). We only need the spectrum's
        **Run Cycle** (still present in ``referenced_by``) to associate it with
        a scan image, so the costly per-file resolution is disabled. This cut a
        2000-curve session from ~3 min to ~20 s with no loss of the metadata we
        use (run cycle, STS pixel/metre location, timestamp).
        """
        md = _a2m.MtrxData()
        md._get_ref_by = lambda *args, **kwargs: (None, None)
        return md

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def smart_load_from_file(self, filepath: Path, progress_callback=None
                             ) -> Tuple[SpectralData, Optional[TopographyData]]:
        """Import the full session that ``filepath`` belongs to.

        ``filepath`` may be a ``_0001.mtrx`` header or any session data file.
        Returns an overview :class:`SpectralData` whose ``additional_info``
        carries the structured session payload (``sessions``, ``images``).
        """
        filepath = Path(filepath)
        header = filepath if filepath.name.endswith('_0001.mtrx') \
            else self._find_header(filepath)
        if header is None:
            raise ValueError(
                f"No _0001.mtrx session header found for {filepath.name}")

        session = self._build_session(header, progress_callback)
        if session is None or not session['batches']:
            raise ValueError(
                f"No spectroscopy data found in session {header.name}")

        primary = self._build_primary(
            [session], session.get('images', []), str(header.parent))
        if progress_callback:
            progress_callback(1, 1, "Complete!")
        self.last_loaded_path = filepath
        return primary, None

    def load_from_directory(self, directory: Path, progress_callback=None
                            ) -> Tuple[SpectralData, Optional[TopographyData]]:
        """Import every MATRIX session found in ``directory``."""
        directory = Path(directory)
        headers = sorted(directory.glob("*_0001.mtrx"))
        if not headers:
            raise ValueError(f"No _0001.mtrx session headers in {directory}")

        sessions: List[dict] = []
        images: List[Tuple[str, Any]] = []
        for i, header in enumerate(headers):
            if progress_callback:
                progress_callback(i, len(headers), f"Reading {header.name}")
            session = self._build_session(header, None)
            if session and session['batches']:
                sessions.append(session)
                images.extend(session.get('images', []))

        if not sessions:
            raise ValueError(f"No spectroscopy data found in {directory}")

        primary = self._build_primary(sessions, images, str(directory))
        if progress_callback:
            progress_callback(len(headers), len(headers), "Complete!")
        self.last_loaded_path = directory
        return primary, None

    def load_single_file(self, filepath: Path) -> SpectralData:
        """Load a single spectroscopy file into a Forward/Backward/Mixed frame.

        Uses access2theMatrix when the session header is present (full scaling
        + metadata); falls back to a minimal raw reader for a lone file with no
        header (default nA scaling).
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        if not any(filepath.name.endswith(e) for e in self.SPECTROSCOPY_EXTENSIONS):
            raise ValueError(f"Unsupported file type: {filepath.name}")

        parsed = self._parse_spectroscopy_file(filepath)
        if parsed is None:
            raise ValueError(f"Could not parse data from {filepath}")

        V = parsed['V']
        df = pd.DataFrame({
            "V": V,
            "Forward": parsed['forward'],
            "Backward": parsed['backward'],
            "Mixed": parsed['mixed'],
        })
        sweep_channels = {
            'Forward': pd.DataFrame({"V": V, "Current": parsed['forward']}),
            'Backward': pd.DataFrame({"V": V, "Current": parsed['backward']}),
            'Mixed': pd.DataFrame({"V": V, "Current": parsed['mixed']}),
        }
        ts = parsed.get('timestamp')
        metadata = self.create_metadata(
            dimensions=(1, 1),
            scan_mode="point",
            units={"independent": "V", "dependent": "A"},
            source_file=str(filepath),
            instrument="Omicron Matrix",
            timestamp=ts.isoformat() if ts else None,
            location_px=parsed.get('location_px'),
            location_m=parsed.get('location_m'),
            parent_image=parsed.get('parent_image'),
            sweep_channels=sweep_channels,
        )
        spectral_data = SpectralData(df, metadata)
        self.last_loaded_path = filepath
        return spectral_data

    # ------------------------------------------------------------------
    # Session building
    # ------------------------------------------------------------------

    def _session_files(self, header: Path) -> Tuple[List[Path], List[Path]]:
        """Enumerate (spectroscopy, image) data files for a session header."""
        base = header.name[:-len('_0001.mtrx')]  # e.g. default_..._Spectroscopy
        directory = header.parent
        prefix = f"{base}--"
        spec, imgs = [], []
        for f in directory.iterdir():
            if not f.is_file() or not f.name.startswith(prefix):
                continue
            if any(f.name.endswith(e) for e in self.SPECTROSCOPY_EXTENSIONS):
                spec.append(f)
            elif any(f.name.endswith(e) for e in self.IMAGE_EXTENSIONS):
                imgs.append(f)
        return spec, imgs

    def _build_session(self, header: Path, progress_callback
                       ) -> Optional[dict]:
        """Parse one session into a structured dict (batches, maps, images)."""
        if _a2m is None:
            logger.error("access2theMatrix not installed; cannot read %s", header)
            return None

        base = header.name[:-len('_0001.mtrx')]
        label = _session_label(base)
        spec_files, image_files = self._session_files(header)
        if not spec_files:
            return None

        # Pick the primary spectroscopy channel present in this session.
        present = {self._ext_channel(f) for f in spec_files}
        primary_channel = next(
            (c for c in self._PRIMARY_PRIORITY if c in present),
            next(iter(present), None))

        md = self._new_md()
        sample_name = dataset_name = ''
        # batches keyed by STS pixel location (fallback: run index)
        batches: Dict[Any, dict] = {}
        total = len([f for f in spec_files
                     if self._ext_channel(f) == primary_channel])
        done = 0
        for f in sorted(spec_files, key=lambda p: _parse_run_scan(p.name)):
            if self._ext_channel(f) != primary_channel:
                continue
            if progress_callback:
                progress_callback(done, total, f"Reading {f.name}")
            done += 1
            curve = self._curve_via_a2m(md, f)
            if curve is None:
                continue
            sample_name = sample_name or curve.get('sample_name', '')
            dataset_name = dataset_name or curve.get('dataset_name', '')
            run, scan = _parse_run_scan(f.name)
            key = curve['location_px'] if curve['location_px'] else ('run', run)
            batch = batches.get(key)
            if batch is None:
                batch = {
                    'location_px': curve['location_px'],
                    'location_m': curve['location_m'],
                    'parent_image': curve['parent_image'],
                    'parent_run': curve['parent_run'],
                    'channel': curve['channel'],
                    'V': curve['V'],
                    'first_run': run,
                    'forward': [], 'backward': [], 'mixed': [], 'rep_V': [],
                    'rep_timestamps': [], 'rep_files': [], 'rep_runscan': [],
                }
                batches[key] = batch
            batch['forward'].append(curve['forward'])
            batch['backward'].append(curve['backward'])
            batch['mixed'].append(curve['mixed'])
            batch['rep_V'].append(curve['V'])
            batch['rep_timestamps'].append(curve['timestamp'])
            batch['rep_files'].append(f.name)
            batch['rep_runscan'].append((run, scan))

        if not batches:
            return None

        # Order points by acquisition order (first run index) and index them.
        ordered = sorted(batches.values(), key=lambda b: b['first_run'])
        for i, b in enumerate(ordered, start=1):
            b['point_index'] = i
            b['first_timestamp'] = next(
                (t for t in b['rep_timestamps'] if t is not None), None)

        # Scan images -> maps + pictures; tag each map with the spectra on it.
        maps, images = self._build_images(md, image_files, label, ordered)

        n_points = len(ordered)
        spatial_layout = 'point' if n_points <= 1 else 'line'

        return {
            'label': label,
            'base': base,
            'header': str(header),
            'source_dir': str(header.parent),
            'sample_name': sample_name,
            'dataset_name': dataset_name,
            'channel': primary_channel,
            'channels_present': sorted(present),
            'spatial_layout': spatial_layout,
            'batches': ordered,
            'maps': maps,
            'images': images,
        }

    def _ext_channel(self, f: Path) -> str:
        """Channel token for a spectroscopy file, e.g. 'I(V)' or 'Aux2(V)'."""
        m = re.search(r'\.([A-Za-z0-9()]+)_mtrx$', f.name)
        return m.group(1) if m else ''

    # ------------------------------------------------------------------
    # Curve extraction (access2theMatrix)
    # ------------------------------------------------------------------

    def _curve_via_a2m(self, md, filepath: Path) -> Optional[dict]:
        """Extract one spectroscopy curve (+ metadata) via access2theMatrix."""
        try:
            traces, _msg = md.open(str(filepath))
        except Exception as exc:
            logger.warning("a2m could not open %s: %s", filepath.name, exc)
            return None
        if not traces or md.object_type != 'curve':
            return None
        try:
            cu_f, _ = md.select_curve(traces[0])
        except Exception as exc:
            logger.warning("a2m select_curve failed for %s: %s", filepath.name, exc)
            return None
        if cu_f.data is None or cu_f.data.size == 0:
            return None

        x = np.asarray(cu_f.data[0], dtype=np.float64)
        fwd = np.asarray(cu_f.data[1], dtype=np.float64)
        xp = x.size
        bwd: Optional[np.ndarray] = None
        if len(traces) > 1:
            try:
                cu_b, _ = md.select_curve(traces[1])
                if cu_b.data is not None and cu_b.data.shape[1] == xp:
                    bwd = np.asarray(cu_b.data[1], dtype=np.float64)
            except Exception:
                bwd = None

        # Best-effort ADC-rail masking using the raw int samples.
        raw = np.asarray(md.data, dtype=np.float64)
        if raw.size >= xp:
            fwd = self._apply_rail_mask(fwd, raw[:xp])
        if bwd is not None and raw.size >= 2 * xp:
            bwd = self._apply_rail_mask(bwd, raw[xp:2 * xp][::-1])

        mixed = (fwd + bwd) / 2.0 if bwd is not None else fwd.copy()
        if bwd is None:
            bwd = fwd.copy()

        loc = md.param.get('MARK::MTRX.STS_LOCATION')
        location_px = (int(loc[0]), int(loc[1])) if loc else None
        location_m = (float(loc[2]), float(loc[3])) if loc else None

        # The spectrum's parent scan is identified by its Run Cycle (the exact
        # file name is skipped for speed — see _new_md). location_px is the
        # pixel coordinate within that scan image.
        parent_image = None
        parent_run = None
        rb = getattr(cu_f, 'referenced_by', None)
        if isinstance(rb, dict):
            parent_image = rb.get('Data File Name') or None
            parent_run = rb.get('Run Cycle')

        return {
            'V': x,
            'forward': fwd,
            'backward': bwd,
            'mixed': mixed,
            'n_points': xp,
            'timestamp': _read_tlkb_seconds(filepath),
            'location_px': location_px,
            'location_m': location_m,
            'parent_image': parent_image,
            'parent_run': parent_run,
            'channel': md.channel_name or self._ext_channel(filepath),
            'sample_name': getattr(md, 'sample_name', '') or '',
            'dataset_name': getattr(md, 'data_set_name', '') or '',
        }

    def _apply_rail_mask(self, scaled: np.ndarray, raw_segment: np.ndarray
                         ) -> np.ndarray:
        """Set scaled samples whose raw int code is an ADC rail to NaN."""
        if scaled.shape != raw_segment.shape:
            return scaled
        rail = np.isin(raw_segment, self._ADC_RAIL_CODES)
        if rail.any():
            scaled = scaled.copy()
            scaled[rail] = np.nan
        return scaled

    # ------------------------------------------------------------------
    # Image / map extraction (access2theMatrix)
    # ------------------------------------------------------------------

    def _build_images(self, md, image_files: List[Path], label: str,
                      batches: List[dict]
                      ) -> Tuple[List[dict], List[Tuple[str, Any]]]:
        """Read .Z_mtrx/.I_mtrx scans as map dicts and ImageData pictures.

        The Z and I channels of the *same* scan (same run_scan) are combined
        into a single multi-channel map. Each map is tagged with the STS
        locations (``locations``) of the batches taken on it, so the UI can
        overlay where spectra were measured. Each scan channel also becomes a
        browsable picture.
        """
        from ..models.image_data import ImageData, ImageMetadata, ImageMode

        # Index batches by the Run Cycle of the scan they were taken on, so the
        # scan images can be tagged with the spectra measured on them.
        by_run: Dict[int, List[dict]] = {}
        for b in batches:
            run = b.get('parent_run')
            if run is not None:
                by_run.setdefault(int(run), []).append(b)

        # Group scan files by (run, scan): one physical scan, several channels.
        groups: Dict[Tuple[int, int], Dict[str, Tuple[Path, dict]]] = {}
        for f in sorted(image_files, key=lambda p: _parse_run_scan(p.name)):
            info = self._image_via_a2m(md, f)
            if info is None:
                continue
            groups.setdefault(_parse_run_scan(f.name), {})[info['channel_name']] = (f, info)

        maps: List[dict] = []
        images: List[Tuple[str, Any]] = []
        for (run, scan), chans in sorted(groups.items()):
            geom = next(iter(chans.values()))[1]  # shapes/geometry are shared
            title = f"{label} {run}_{scan}"
            parent_files = {f.name for f, _ in chans.values()}

            seen, locations = set(), []
            for b in by_run.get(run, []):
                if b['point_index'] in seen:
                    continue
                seen.add(b['point_index'])
                locations.append({
                    'point_index': b['point_index'],
                    'px': list(b['location_px']) if b['location_px'] else None,
                    'm': list(b['location_m']) if b['location_m'] else None,
                    'reps': len(b['mixed']),
                })
            locations.sort(key=lambda d: d['point_index'])

            ts = geom['timestamp']
            maps.append({
                'title': title,
                'channels': {cn: info['data'] for cn, (f, info) in chans.items()},
                'channel_units': {cn: info['unit'] for cn, (f, info) in chans.items()},
                'active_channel': 'Z' if 'Z' in chans else next(iter(chans)),
                'width_m': geom['width_m'],
                'height_m': geom['height_m'],
                'x_offset_m': geom['x_offset_m'],
                'y_offset_m': geom['y_offset_m'],
                'angle': geom['angle'],
                'timestamp': ts.isoformat() if ts else None,
                'source_files': sorted(parent_files),
                'locations': locations,
            })

            # Browsable pictures (one per channel): float single-channel; the
            # image viewer applies a colormap + range controls, so the raw
            # scaled array travels untouched (no colormap baked in).
            for cn, (f, info) in chans.items():
                try:
                    # Physical pixel size (dy, dx) in nm, for the viewer ruler.
                    rows, cols = info['data'].shape
                    px_nm = None
                    if rows and cols and geom['width_m'] and geom['height_m']:
                        px_nm = (geom['height_m'] / rows * 1e9,
                                 geom['width_m'] / cols * 1e9)
                    meta = ImageMetadata(
                        source="omicron_matrix_scan",
                        original_filename=f.name,
                        pixel_size_nm=px_nm,
                        additional_info={'channel': cn, 'unit': info['unit'],
                                         'session_label': label},
                    )
                    img = ImageData.from_array(
                        info['data'].astype(np.float32),
                        mode=ImageMode.SINGLE_FLOAT, metadata=meta,
                        name=f"{title} {cn}")
                    images.append((f"{title} {cn}", img))
                except Exception as exc:
                    logger.debug("Could not wrap scan %s as image: %s", f.name, exc)

        return maps, images

    def _image_via_a2m(self, md, filepath: Path) -> Optional[dict]:
        """Read a single scan image (forward/up trace) via access2theMatrix."""
        try:
            traces, _msg = md.open(str(filepath))
        except Exception as exc:
            logger.warning("a2m could not open image %s: %s", filepath.name, exc)
            return None
        if not traces or md.axis is None:
            return None
        try:
            im, _ = md.select_image(traces[0])
        except Exception as exc:
            logger.warning("a2m select_image failed for %s: %s", filepath.name, exc)
            return None
        data = np.asarray(im.data, dtype=np.float64)
        if data.size == 0 or data.ndim != 2 or min(data.shape) < 1:
            return None
        name_unit = getattr(im, 'channel_name_and_unit', ['', '']) or ['', '']
        return {
            'data': data,
            'channel_name': name_unit[0] or md.channel_name or 'Z',
            'unit': name_unit[1] or 'm',
            'width_m': float(getattr(im, 'width', 0.0) or 0.0),
            'height_m': float(getattr(im, 'height', 0.0) or 0.0),
            'x_offset_m': float(getattr(im, 'x_offset', 0.0) or 0.0),
            'y_offset_m': float(getattr(im, 'y_offset', 0.0) or 0.0),
            'angle': float(getattr(im, 'angle', 0.0) or 0.0),
            'timestamp': _read_tlkb_seconds(filepath),
        }

    # ------------------------------------------------------------------
    # Dataset builders (consumed by the backend, per session)
    # ------------------------------------------------------------------

    _UNITS = {"independent": "V", "dependent": "A", "x": "nm", "y": "nm"}

    @staticmethod
    def _sweep_df(V: np.ndarray, columns: Dict[str, np.ndarray]) -> pd.DataFrame:
        df = pd.DataFrame(columns)
        df.insert(0, "V", V)
        return df

    def build_overview_dataset(self, session: dict, name: str) -> SpectralData:
        """One dataset overlaying every spectrum of a session.

        A session can mix bias setups (different point counts per location), so
        the overview overlays only the dominant-length group on a shared V axis;
        odd-length points remain available as per-point datasets.
        """
        batches = session['batches']
        lengths = [len(b['V']) for b in batches]
        modal_len = max(set(lengths), key=lengths.count)
        modal = [b for b in batches if len(b['V']) == modal_len]
        V = modal[0]['V']

        mix_cols: Dict[str, np.ndarray] = {}
        fwd_cols: Dict[str, np.ndarray] = {}
        bwd_cols: Dict[str, np.ndarray] = {}
        spectrum_meta: List[dict] = []
        for b in modal:
            for r in range(len(b['mixed'])):
                spec = b['mixed'][r]
                if len(spec) != modal_len:
                    continue
                col = f"P{b['point_index']}R{r + 1}"
                mix_cols[col] = spec
                fwd_cols[col] = b['forward'][r]
                bwd_cols[col] = b['backward'][r]
                ts = b['rep_timestamps'][r]
                spectrum_meta.append({
                    'column': col,
                    'point_index': b['point_index'],
                    'rep': r + 1,
                    'location_px': list(b['location_px']) if b['location_px'] else None,
                    'location_m': list(b['location_m']) if b['location_m'] else None,
                    'timestamp': ts.isoformat() if ts else None,
                    'parent_image': b['parent_image'],
                    'file': b['rep_files'][r],
                })
        df = self._sweep_df(V, mix_cols)
        sweep_channels = {
            'Forward': self._sweep_df(V, fwd_cols),
            'Backward': self._sweep_df(V, bwd_cols),
            'Mixed': self._sweep_df(V, mix_cols),
        }
        metadata = self.create_metadata(
            dimensions=(len(modal), 1),
            scan_mode=session['spatial_layout'],
            units=dict(self._UNITS),
            source_directory=session['source_dir'],
            instrument="Omicron Matrix",
            sample_name=session['sample_name'],
            dataset_name=session['dataset_name'],
            session_label=session['label'],
            matrix_kind='overview',
            spectrum_meta=spectrum_meta,
            sweep_channels=sweep_channels,
        )
        return SpectralData(df, metadata)

    def build_point_dataset(self, session: dict, batch: dict, name: str
                            ) -> SpectralData:
        """One dataset = the repetitions taken at a single STS location.

        Repetitions can occasionally differ in point count (aborted sweeps,
        ramp-reversal edge cases), so the dataset keeps the dominant-length
        repetitions on a shared V axis and drops the odd ones.
        """
        lengths = [len(s) for s in batch['mixed']]
        modal_len = max(set(lengths), key=lengths.count)
        keep = [r for r, s in enumerate(batch['mixed']) if len(s) == modal_len]
        rep_V = batch.get('rep_V') or [batch['V']] * len(batch['mixed'])
        V = rep_V[keep[0]]
        mix_cols = {f"Rep_{i + 1}": batch['mixed'][r] for i, r in enumerate(keep)}
        fwd_cols = {f"Rep_{i + 1}": batch['forward'][r] for i, r in enumerate(keep)}
        bwd_cols = {f"Rep_{i + 1}": batch['backward'][r] for i, r in enumerate(keep)}
        df = self._sweep_df(V, mix_cols)
        sweep_channels = {
            'Forward': self._sweep_df(V, fwd_cols),
            'Backward': self._sweep_df(V, bwd_cols),
            'Mixed': self._sweep_df(V, mix_cols),
        }
        ts = batch['first_timestamp']
        metadata = self.create_metadata(
            dimensions=(len(batch['mixed']), 1),
            scan_mode="point",
            units=dict(self._UNITS),
            source_directory=session['source_dir'],
            instrument="Omicron Matrix",
            sample_name=session['sample_name'],
            session_label=session['label'],
            matrix_kind='point',
            point_index=batch['point_index'],
            location_px=list(batch['location_px']) if batch['location_px'] else None,
            location_m=list(batch['location_m']) if batch['location_m'] else None,
            parent_image=batch['parent_image'],
            timestamp=ts.isoformat() if ts else None,
            rep_timestamps=[t.isoformat() if t else None
                            for t in batch['rep_timestamps']],
            rep_files=list(batch['rep_files']),
            sweep_channels=sweep_channels,
        )
        return SpectralData(df, metadata)

    def _build_primary(self, sessions: List[dict],
                       images: List[Tuple[str, Any]], source: str
                       ) -> SpectralData:
        """Overview of the first session, with the full structured payload
        (``sessions``, ``images``) attached for the backend to expand."""
        primary = self.build_overview_dataset(sessions[0], sessions[0]['label'])
        ai = primary.metadata.additional_info
        ai['matrix_import'] = True
        ai['sessions'] = sessions
        ai['images'] = images
        ai['source_directory'] = source
        return primary

    # ------------------------------------------------------------------
    # Header discovery
    # ------------------------------------------------------------------

    def _find_header(self, filepath: Path) -> Optional[Path]:
        """Find the ``_0001.mtrx`` session header for a data file."""
        base = filepath.name.rsplit('--', 1)[0]
        candidate = filepath.parent / f"{base}_0001.mtrx"
        if candidate.exists():
            return candidate
        headers = sorted(filepath.parent.glob("*_0001.mtrx"))
        return headers[0] if headers else None

    # ------------------------------------------------------------------
    # Single-file parsing (a2m when header present, raw fallback otherwise)
    # ------------------------------------------------------------------

    def _parse_spectroscopy_file(self, filepath: Path) -> Optional[dict]:
        """Parse one spectroscopy file to V/forward/backward/mixed + metadata.

        Prefers access2theMatrix (needs the session header for scaling); if no
        header is present, falls back to a minimal raw reader with default
        nanoamp scaling.
        """
        header = self._find_header(filepath)
        if _a2m is not None and header is not None:
            md = self._new_md()
            curve = self._curve_via_a2m(md, filepath)
            if curve is not None:
                return curve
        return self._read_raw_curve(filepath)

    # Backward-compatible alias.
    _parse_iv_file = _parse_spectroscopy_file

    def _read_raw_curve(self, filepath: Path) -> Optional[dict]:
        """Minimal reader for a lone file with no session header.

        Reads the TLKB timestamp and ATAD int32 block, masks ADC rails, applies
        default nanoamp scaling, and splits into forward/backward halves.
        """
        try:
            raw_bytes = filepath.read_bytes()
        except Exception as exc:
            logger.error("Could not read %s: %s", filepath, exc)
            return None
        if raw_bytes[:12] != self.MAGIC_NUMBER:
            logger.error("Invalid magic number in %s", filepath)
            return None

        ts = _read_tlkb_seconds(filepath)
        idx = raw_bytes.find(b'ATAD')
        if idx < 0:
            logger.error("No ATAD block in %s", filepath)
            return None
        datasize = unpack_from('<i', raw_bytes, idx + 4)[0]
        start = idx + 8
        n_total = datasize // 4
        if n_total <= 0 or start + datasize > len(raw_bytes):
            return None
        raw = np.frombuffer(
            raw_bytes[start:start + n_total * 4], dtype='<i4').astype(np.float64)
        raw = self._mask_adc_rails(raw)
        scaled = self._scale_data(raw)

        n_half = n_total // 2
        forward = scaled[:n_half]
        backward = scaled[n_half:n_half * 2][::-1]
        mixed = (forward + backward) / 2.0
        V = self._get_voltage_array(forward)
        return {
            'V': V, 'forward': forward, 'backward': backward, 'mixed': mixed,
            'n_points': n_half, 'timestamp': ts,
            'location_px': None, 'location_m': None, 'parent_image': None,
            'channel': self._ext_channel(filepath),
        }

    def _mask_adc_rails(self, raw: np.ndarray) -> np.ndarray:
        """Set ADC saturation-rail samples to NaN (see :attr:`_ADC_RAIL_CODES`)."""
        raw = np.asarray(raw, dtype=np.float64)
        rail = np.isin(raw, self._ADC_RAIL_CODES)
        if rail.any():
            raw = raw.copy()
            raw[rail] = np.nan
        return raw

    def _scale_data(self, raw_data: np.ndarray) -> np.ndarray:
        """Default nanoamp scaling for the headerless fallback path.

        Real sessions are scaled by access2theMatrix's transfer functions; this
        is only used when no ``_0001.mtrx`` header is available.
        """
        return np.asarray(raw_data, dtype=np.float64) * 1e-9

    def _get_voltage_array(self, current_data: np.ndarray) -> np.ndarray:
        """Default symmetric voltage axis for the headerless fallback path."""
        return np.linspace(-1.0, 1.0, len(current_data))
