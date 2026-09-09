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
import math
import re
import warnings
from datetime import datetime
from pathlib import Path
from struct import unpack_from
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base_loader import BaseDataLoader
from ..models.spectral_data import SpectralData
from ..utils.naming import pad as _pad
from ..utils.naming import strip_acquisition_time as _strip_time
from .session_organization import disambiguate_labels
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

def _tlkb_seconds_from_bytes(raw: bytes) -> Optional[datetime]:
    """Acquisition timestamp from already-read result-file bytes.

    Every ONTMATRX result file opens with a ``TLKB`` block whose first 8 bytes
    (after the 8-byte tag+size) are the acquisition time as Unix seconds
    (uint64 LE). access2theMatrix formats this as a string and discards the raw
    value, so we read it straight from the bytes to get a real ``datetime``.
    """
    try:
        idx = raw.find(b'TLKB')
        if idx < 0:
            return None
        secs = unpack_from('<Q', raw, idx + 8)[0]
        return datetime.fromtimestamp(secs) if secs else None
    except Exception:
        return None


def _read_tlkb_seconds(path: Path) -> Optional[datetime]:
    """Acquisition timestamp from a MATRIX result file on disk."""
    try:
        return _tlkb_seconds_from_bytes(path.read_bytes())
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not read TLKB timestamp from %s: %s", path, exc)
        return None


def _session_label(base: str, keep_time: bool = False) -> str:
    """Short, human-friendly session label from a result-file base name.

    ``default_2026Jun15-203637_STM-STM_Spectroscopy`` -> ``2026Jun15``.
    Falls back to the whole base name when the convention doesn't match.

    The acquisition time is dropped because it makes browser rows and exported
    filenames hard to scan. Pass ``keep_time=True`` to retain it — see
    :func:`_session_labels`, which does exactly that for the one case where the
    date alone is ambiguous.
    """
    m = re.search(r'default_([0-9A-Za-z-]+?)_', base)
    label = m.group(1) if m else base
    return label if keep_time else _strip_time(label)


def _session_labels(bases) -> Dict[str, str]:
    """Map each result-file base name to its display label.

    Times are stripped, **except** where two sessions share a date — dropping it
    there would merge two distinct measurement sessions into one browser folder
    and collide their scan names. Those keep the full date-time.

    The rule itself lives in :mod:`session_organization` so every loader
    labels its sessions the same way.
    """
    return disambiguate_labels(
        list(bases),
        lambda base: _session_label(base),
        lambda base: _session_label(base, keep_time=True),
    )


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
        The session is identified by the *data file's* own base name, so a
        session whose ``_0001.mtrx`` header is missing still loads: a compatible
        header from another session in the directory is borrowed for scaling
        (see :meth:`_resolve_header`). Returns an overview :class:`SpectralData`
        whose ``additional_info`` carries the structured session payload.
        """
        filepath = Path(filepath)
        base = self._session_base(filepath)

        session = self._build_session(base, filepath.parent, progress_callback)
        if session is None or not session['batches']:
            raise ValueError(
                f"No spectroscopy data found for session {base}")

        primary = self._build_primary(
            [session], session.get('images', []), str(filepath.parent))
        if progress_callback:
            progress_callback(1, 1, "Complete!")
        self.last_loaded_path = filepath
        return primary, None

    def load_from_directory(self, directory: Path, progress_callback=None,
                            should_cancel=None
                            ) -> Tuple[Optional[SpectralData],
                                       Optional[TopographyData]]:
        """Import every MATRIX session found in ``directory``.

        Sessions are discovered from the *data files* present (grouped by base
        name), not from ``_0001.mtrx`` headers, so a directory whose header
        files are missing still loads — each session borrows a compatible
        header for scaling when its own is absent.

        ``progress_callback(done, total, message)`` is forwarded down to the
        per-curve loop — a single session can hold tens of thousands of
        curves, so per-session progress alone leaves the UI looking frozen.
        ``should_cancel()`` is polled in that loop; when it returns True the
        load aborts and ``(None, None)`` is returned.
        """
        directory = Path(directory)
        found = self._scan_session_bases(directory)
        if not found:
            raise ValueError(f"No Omicron MATRIX data files in {directory}")
        # Image-only sessions (aborted runs) carry no spectra and are dropped.
        # They must be dropped *before* labelling, not just before loading: a
        # stub sharing its date with a real session would otherwise count as a
        # clash and force the real one to keep its acquisition time — leaving
        # one folder named "2026Jun24-124501" with nothing to disambiguate
        # against, while single-session days read plainly as "2026Jun16".
        bases = sorted(b for b, has_spectra in found.items() if has_spectra)
        if not bases:
            raise ValueError(f"No spectroscopy data found in {directory}")

        sessions: List[dict] = []
        images: List[Tuple[str, Any]] = []
        # Labels are resolved together: the acquisition time is dropped unless
        # two sessions share a date, where it is the only thing telling them
        # apart.
        _labels = _session_labels(bases)
        for i, base in enumerate(bases):
            if should_cancel is not None and should_cancel():
                logger.info("MATRIX load of %s cancelled", directory)
                return None, None
            # Scope each session's curve progress into its slice of the whole,
            # so the bar advances smoothly across a multi-session folder.
            def _prog(done, total, msg, _i=i, _n=len(bases), _b=base):
                if progress_callback and total:
                    progress_callback(_i * 100 + int(100 * done / total),
                                      _n * 100, f"{_b}: {msg}")
            session = self._build_session(base, directory, _prog, should_cancel,
                                          label=_labels.get(base))
            if session is None and should_cancel is not None and should_cancel():
                return None, None
            if session and session['batches']:
                sessions.append(session)
                images.extend(session.get('images', []))

        if not sessions:
            raise ValueError(f"No spectroscopy data found in {directory}")

        primary = self._build_primary(sessions, images, str(directory))
        if progress_callback:
            progress_callback(len(bases), len(bases), "Complete!")
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

    @staticmethod
    def _session_base(filepath: Path) -> str:
        """Session base name for any file that belongs to a session.

        A data file ``default_..._Spectroscopy--3_1.I(V)_mtrx`` and a header
        ``default_..._Spectroscopy_0001.mtrx`` both map to the same base
        ``default_..._Spectroscopy``. The base — not the header — is the
        session's identity, so a session with a missing header still resolves.
        """
        name = filepath.name
        if '--' in name:
            return name.rsplit('--', 1)[0]
        m = re.match(r'(.*?)_\d{4}\.mtrx$', name)
        return m.group(1) if m else name

    def _scan_session_bases(self, directory: Path) -> Dict[str, bool]:
        """Map each session base in ``directory`` to whether it has spectra.

        ``True`` means the session has at least one spectroscopy file; ``False``
        that it holds nothing but scan images — typically an aborted run that
        got a topography frame and was stopped before any curve. Such sessions
        yield no data, so callers filter them out.

        One directory pass answers both questions: a session folder can hold
        hundreds of thousands of files, so re-scanning is not free.
        """
        spec_exts = tuple(self.SPECTROSCOPY_EXTENSIONS)
        img_exts = tuple(self.IMAGE_EXTENSIONS)
        found: Dict[str, bool] = {}
        try:
            for f in directory.iterdir():
                n = f.name
                if '--' not in n or not f.is_file():
                    continue
                if n.endswith(spec_exts):
                    found[n.rsplit('--', 1)[0]] = True
                elif n.endswith(img_exts):
                    found.setdefault(n.rsplit('--', 1)[0], False)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Could not scan %s for sessions: %s", directory, exc)
        return found

    def _discover_session_bases(self, directory: Path) -> List[str]:
        """Distinct session base names present as data files in ``directory``."""
        return sorted(self._scan_session_bases(directory))

    @staticmethod
    def _first_header_in(directory: Path) -> Optional[Path]:
        """First ``*_0001.mtrx`` in ``directory`` (non-recursive), or None."""
        try:
            hs = sorted(directory.glob("*_0001.mtrx"))
        except Exception:
            hs = []
        return hs[0] if hs else None

    def _resolve_header(self, base: str, directory: Path
                        ) -> Tuple[Optional[Path], bool]:
        """Locate the parameter header to scale ``base``'s data files.

        Returns ``(header_path, is_own)``. Search order:

        1. The session's own ``{base}_0001.mtrx`` (``is_own=True``).
        2. Any ``*_0001.mtrx`` in the same folder (borrowed).
        3. Any ``*_0001.mtrx`` in the parent folder or a sibling folder
           (borrowed, one level only — the day-folder layout keeps all
           sessions of an instrument under one parent).

        MATRIX transfer functions are shared across sessions on the same
        instrument setup, so a borrowed header scales spectra correctly
        (verified); the per-spectrum STS location and the scan-window geometry,
        however, are only right with the session's own header — see
        :meth:`_build_session`. A borrowed header only scales correctly when the
        sweep configuration matched, which is normal within one instrument setup
        but not guaranteed across very different experiments.
        """
        own = directory / f"{base}_0001.mtrx"
        if own.exists():
            return own, True

        # Same folder.
        h = self._first_header_in(directory)
        if h is not None:
            return h, False

        # Parent folder, then sibling folders (one level, deterministic order).
        parent = directory.parent
        search_dirs: List[Path] = []
        if parent != directory:
            search_dirs.append(parent)
            try:
                search_dirs.extend(
                    sorted(p for p in parent.iterdir()
                           if p.is_dir() and p != directory))
            except Exception:
                pass
        for d in search_dirs:
            h = self._first_header_in(d)
            if h is not None:
                return h, False
        return None, False

    def _session_files(self, base: str, directory: Path
                       ) -> Tuple[List[Path], List[Path]]:
        """Enumerate (spectroscopy, image) data files for a session base."""
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

    def _build_session(self, base: str, directory: Path, progress_callback,
                       should_cancel=None,
                       label: Optional[str] = None) -> Optional[dict]:
        """Parse one session into a structured dict (batches, maps, images).

        ``base`` identifies the session by its data-file base name; the header
        is resolved separately (own or borrowed). With a borrowed header,
        spectra are scaled from the shared transfer functions but STS locations
        and scan maps are unavailable (a borrowed header's scan geometry does
        not match these bricklets), so image parsing is skipped.
        """
        if _a2m is None:
            logger.error("access2theMatrix not installed; cannot read %s", base)
            return None

        header, header_is_own = self._resolve_header(base, directory)
        if label is None:
            label = _session_label(base)
        spec_files, image_files = self._session_files(base, directory)
        if not spec_files:
            return None
        if header is None:
            logger.warning(
                "Session %s has no _0001.mtrx header and none is available to "
                "borrow in %s; cannot scale — skipping.", base, directory)
            return None
        if not header_is_own:
            where = ("this folder" if header.parent == directory
                     else f"folder '{header.parent.name}'")
            logger.warning(
                "Session %s has no _0001.mtrx header; borrowing '%s' from %s. "
                "The bias axis is reliable, but CURRENT VALUES MAY BE MIS-SCALED "
                "by a constant gain factor if the preamp range differed between "
                "the two runs (observed ×101 between real sessions) — treat "
                "absolute I as unverified. STS locations and scan maps are "
                "unavailable without the session's own header.",
                base, header.name, where)

        # Pick the primary spectroscopy channel present in this session.
        present = {self._ext_channel(f) for f in spec_files}
        primary_channel = next(
            (c for c in self._PRIMARY_PRIORITY if c in present),
            next(iter(present), None))

        primary_files = sorted(
            (f for f in spec_files if self._ext_channel(f) == primary_channel),
            key=lambda p: _parse_run_scan(p.name))

        # Parse the session header ONCE and scan it forward per file. a2m's
        # open() re-reads + re-parses the whole header on every call (O(N) per
        # file → O(N²) per session: a 16 MB / 16k-file session took *hours*).
        # The incremental cursor makes it O(N); any file not reached in header
        # order falls back to a from-scratch open().
        md = self._new_md()
        raw_param = b''
        header_ok = False
        borrowed = None
        if header_is_own:
            raw_param = self._read_header_chain(header)
            header_ok = raw_param[:len(self.MAGIC_NUMBER)] == self.MAGIC_NUMBER
            if header_ok:
                md.raw_param = raw_param
                md.param = {'BREF': ''}
                md.channel_id = {}
        else:
            # Borrowed header: pre-parse its param stream once for injection.
            borrowed = self._borrowed_template(header)
            if borrowed is None:
                logger.warning(
                    "Borrowed header '%s' is unreadable; skipping %s.",
                    header.name, base)
                return None
        cursor = [12]

        sample_name = dataset_name = ''
        batches: Dict[Any, dict] = {}
        total = len(primary_files)
        for done, f in enumerate(primary_files):
            if done % 64 == 0:
                if should_cancel is not None and should_cancel():
                    logger.info("Session %s cancelled after %d/%d curves",
                                base, done, total)
                    return None
                if progress_callback:
                    progress_callback(done, total,
                                      f"{done}/{total} curves")
            curve = None
            if header_ok:
                curve = self._curve_incremental(md, raw_param, cursor, f)
            if curve is None and borrowed is not None:
                curve = self._curve_borrowed(borrowed, f)
            if curve is None and header_is_own:
                curve = self._curve_via_a2m(self._new_md(), f)
            if curve is None:
                continue
            sample_name = sample_name or curve.get('sample_name', '')
            dataset_name = dataset_name or curve.get('dataset_name', '')
            run, scan = _parse_run_scan(f.name)
            # A "point" = one spectroscopy experiment = one run cycle. Key on
            # (run, location) NOT location alone: revisiting an already-measured
            # spot in a later run is a distinct experiment/point and must not be
            # merged (location alone collapses revisits and loses points). The
            # location is included so a rare single-run multi-point line scan
            # still splits per position.
            key = (run, curve['location_px'])
            batch = batches.get(key)
            if batch is None:
                batch = {
                    'location_px': curve['location_px'],
                    'location_m': curve['location_m'],
                    'parent_image': curve['parent_image'],
                    'parent_run': curve['parent_run'],
                    'channel': curve['channel'],
                    'lockin': curve.get('lockin') or {},
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

        # Detect line scans (contiguous straight, evenly-spaced runs of
        # same-rep points) and tag each batch with line_scan_id / line_pos.
        line_scans = self._detect_line_scans(ordered)

        # Scan images -> maps + pictures; tag each map with the spectra on it.
        # Only with the session's own header: a borrowed header's scan geometry
        # (Width/Height/Points/Lines) does not match these bricklets, so the
        # maps would be mis-scaled or reshaped wrongly. Spectra still load.
        if header_is_own:
            maps, images = self._build_images(md, image_files, label, ordered)
        else:
            maps, images = [], []

        n_points = len(ordered)
        spatial_layout = 'point' if n_points <= 1 else 'line'

        return {
            'label': label,
            'base': base,
            'header': str(header),
            # The session's own folder — not the header's, which may have been
            # borrowed from a sibling directory.
            'source_dir': str(directory),
            # True when scaling came from another session's header: the bias
            # axis is reliable but absolute current may be off by a constant
            # preamp-gain factor, and STS locations/maps are unavailable.
            'header_borrowed': not header_is_own,
            'sample_name': sample_name,
            'dataset_name': dataset_name,
            'channel': primary_channel,
            'channels_present': sorted(present),
            'spatial_layout': spatial_layout,
            'batches': ordered,
            'line_scans': line_scans,
            'maps': maps,
            'images': images,
        }

    # ------------------------------------------------------------------
    # Line-scan detection
    # ------------------------------------------------------------------

    # Tunables. A line scan is a run of >= _LINE_MIN_POINTS same-rep points
    # whose pixel locations lie on a straight (perpendicular deviation
    # < _LINE_PERP_TOL_PX), monotone, roughly evenly-spaced (largest/smallest
    # step < _LINE_EVEN_RATIO) line.
    _LINE_MIN_POINTS = 4
    _LINE_PERP_TOL_PX = 6.0
    _LINE_EVEN_RATIO = 3.0

    def _detect_line_scans(self, batches: List[dict]) -> List[dict]:
        """Identify line scans among the session's points.

        A line scan is acquired continuously along a line with the same number
        of repetitions at every point. Because a parallel single-sweep can
        interleave point-for-point with the multi-rep scan (and other
        acquisitions sit between unrelated points), detection runs WITHIN each
        rep-count group, in acquisition order, so each line pops out cleanly.

        Tags each batch with ``line_scan_id`` (or None) and ``line_pos`` (index
        along the line), and returns a list of line-scan descriptors.
        """
        from collections import defaultdict
        for b in batches:
            b['line_scan_id'] = None
            b['line_pos'] = None

        groups: Dict[int, List[dict]] = defaultdict(list)
        for b in batches:
            if b.get('location_px') is not None:
                groups[len(b['mixed'])].append(b)

        line_scans: List[dict] = []
        next_id = 1
        for reps, group in groups.items():
            group.sort(key=lambda b: b['point_index'])
            i, n = 0, len(group)
            while i < n:
                run = [group[i]]
                while i + len(run) < n:
                    cand = group[i + len(run)]
                    if self._is_line([b['location_px'] for b in run]
                                     + [cand['location_px']]):
                        run.append(cand)
                    else:
                        break
                if len(run) >= self._LINE_MIN_POINTS:
                    lid = next_id
                    next_id += 1
                    for pos, b in enumerate(run):
                        b['line_scan_id'] = lid
                        b['line_pos'] = pos
                    line_scans.append({
                        'id': lid,
                        'reps': reps,
                        'n_points': len(run),
                        'point_indices': [b['point_index'] for b in run],
                        'px_start': list(run[0]['location_px']),
                        'px_end': list(run[-1]['location_px']),
                        'm_start': list(run[0]['location_m']) if run[0]['location_m'] else None,
                        'm_end': list(run[-1]['location_m']) if run[-1]['location_m'] else None,
                    })
                    i += len(run)
                else:
                    i += 1

        line_scans.sort(key=lambda d: d['point_indices'][0])
        return line_scans

    @staticmethod
    def _line_overlays(locations: List[dict]) -> List[dict]:
        """Group a scan's STS locations into per-line-scan outlines.

        One entry per line scan present on this image, ordered along the line,
        carrying the pixel path plus the numbers that identify it in the map
        view (``line1 · 57pts ×3 · pt20→pt76``).
        """
        by_line: Dict[int, List[dict]] = {}
        for loc in locations:
            lid = loc.get('line_scan_id')
            if lid is None or not loc.get('px'):
                continue
            by_line.setdefault(int(lid), []).append(loc)

        overlays = []
        for lid in sorted(by_line):
            pts = sorted(by_line[lid], key=lambda d: (d.get('line_pos') if d.get('line_pos') is not None else 0))
            indices = [int(p['point_index']) for p in pts]
            overlays.append({
                'id': lid,
                'label': f"line{lid}",
                'n_points': len(pts),
                'reps': int(pts[0].get('reps') or 0),
                'presweeps': 0,
                'point_indices': indices,
                'point_first': indices[0],
                'point_last': indices[-1],
                'px_path': [[int(p['px'][0]), int(p['px'][1])] for p in pts],
                'px_start': [int(pts[0]['px'][0]), int(pts[0]['px'][1])],
                'px_end': [int(pts[-1]['px'][0]), int(pts[-1]['px'][1])],
            })

        return OmicronMatrixSTSLoader._hide_presweeps(overlays)

    @staticmethod
    def _locations_on_grid(locations: List[dict], grid, title: str = '') -> List[dict]:
        """Keep only the STS points that fall inside this scan's pixel grid.

        A point outside it belongs to another scan (MATRIX records the pixel
        coordinate relative to the image the spectrum was taken on), and
        drawing it anyway puts dots and line outlines off the edge of the
        map. Half a pixel of tolerance is allowed so a point measured exactly
        on the boundary survives rounding.
        """
        if not grid or len(grid) < 2:
            return locations
        rows, cols = int(grid[0]), int(grid[1])
        if rows <= 0 or cols <= 0:
            return locations

        kept, dropped = [], 0
        for loc in locations:
            px = loc.get('px')
            if not px:
                kept.append(loc)          # no position: nothing to validate
                continue
            x, y = float(px[0]), float(px[1])
            if -0.5 <= x <= cols - 0.5 and -0.5 <= y <= rows - 0.5:
                kept.append(loc)
            else:
                dropped += 1

        if dropped:
            logger.warning("%s: %d of %d STS point(s) fall outside the %dx%d "
                           "scan grid and were not placed on it",
                           title or 'scan', dropped, len(locations), cols, rows)
        return kept

    @staticmethod
    def _paths_coincide(a: dict, b: dict) -> bool:
        """Do two line scans run over the same path?

        Endpoints are compared with a tolerance of one point spacing: an
        interleaved single sweep sits between the multi-rep points, so its
        ends land up to a spacing away rather than exactly on top.
        """
        def _spacing(ov):
            (x0, y0), (x1, y1) = ov['px_start'], ov['px_end']
            steps = max(1, ov['n_points'] - 1)
            return math.hypot(x1 - x0, y1 - y0) / steps

        tol = max(3.0, _spacing(a), _spacing(b))

        def _near(p, q):
            return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol

        return ((_near(a['px_start'], b['px_start']) and _near(a['px_end'], b['px_end']))
                or (_near(a['px_start'], b['px_end']) and _near(a['px_end'], b['px_start'])))

    @staticmethod
    def _hide_presweeps(overlays: List[dict]) -> List[dict]:
        """Drop single-sweep lines that shadow a multi-rep line's path.

        MATRIX interleaves a one-sweep pass with the real, many-times-averaged
        measurement over the same positions. Both are kept as datasets, but
        outlining both puts two tags on one line for what is, to the eye, a
        single acquisition — so the pre-sweep is left off the map and counted
        on the line it belongs to.
        """
        visible = []
        for overlay in overlays:
            if overlay['reps'] <= 1:
                host = next((other for other in overlays
                             if other is not overlay and other['reps'] > 1
                             and OmicronMatrixSTSLoader._paths_coincide(other, overlay)),
                            None)
                if host is not None:
                    host['presweeps'] += 1
                    logger.info("line%s is a single sweep over line%s's path — "
                                "kept as data, hidden on the map",
                                overlay['id'], host['id'])
                    continue
            visible.append(overlay)
        return visible

    def _is_line(self, pxs: List) -> bool:
        """True if pixel locations ``pxs`` form a straight, monotone,
        roughly-evenly-spaced line. Runs of < 3 points are trivially
        collinear (so a candidate run can grow before the test bites)."""
        if len(pxs) < 3:
            return True
        P = np.asarray(pxs, dtype=float)
        d = P[-1] - P[0]
        L = float(np.hypot(d[0], d[1]))
        if L < 1.0:
            return False
        d = d / L
        rel = P - P[0]
        proj = rel @ d
        perp = np.abs(rel[:, 0] * d[1] - rel[:, 1] * d[0])
        if perp.max() > self._LINE_PERP_TOL_PX:
            return False
        steps = np.diff(proj)
        if np.any(steps <= 0):                       # must advance monotonically
            return False
        if steps.max() / max(steps.min(), 1e-6) > self._LINE_EVEN_RATIO:
            return False
        return True

    def _ext_channel(self, f: Path) -> str:
        """Channel token for a spectroscopy file, e.g. 'I(V)' or 'Aux2(V)'."""
        m = re.search(r'\.([A-Za-z0-9()]+)_mtrx$', f.name)
        return m.group(1) if m else ''

    # ------------------------------------------------------------------
    # Curve extraction (access2theMatrix)
    # ------------------------------------------------------------------

    def _read_header_chain(self, header: Path) -> bytes:
        """Read the session header chain (``_0001.mtrx`` + any ``_0002…``) once.

        Mirrors access2theMatrix's chaining: the magic prefix is stripped from
        every link after the first. Reading this 16 MB+ blob once and scanning
        it forward (see :meth:`_curve_incremental`) replaces a2m's per-file
        re-read+re-parse, turning a session import from O(N²) into O(N)."""
        base = str(header)[:-len('_0001.mtrx')]
        raw = b''
        i = 1
        while True:
            link = Path(f"{base}_{i:04d}.mtrx")
            if not link.exists():
                break
            data = link.read_bytes()
            raw += data if i == 1 else data[len(self.MAGIC_NUMBER):]
            i += 1
        return raw

    def _curve_incremental(self, md, raw_param: bytes, cursor: list,
                           filepath: Path) -> Optional[dict]:
        """Extract a curve by advancing the shared header-parse cursor to this
        file's entry — no per-file header re-read/re-parse.

        ``md`` keeps the running parser state; ``cursor`` is a 1-element list
        holding the parse offset. Files must be visited in header order (the
        loader sorts by (run, scan), which is acquisition order). Returns None
        if the file isn't reached going forward, so the caller can fall back to
        a from-scratch :meth:`_curve_via_a2m`.
        """
        fn = filepath.name
        n = len(raw_param)
        dp = cursor[0]
        while dp < n and md.param.get('BREF') != fn:
            dp = md._scan_raw_param(dp, raw_param)
        cursor[0] = dp
        if md.param.get('BREF') != fn:
            return None
        try:
            md.raw_data = filepath.read_bytes()
        except Exception:
            return None
        if md.raw_data[:len(self.MAGIC_NUMBER)] != self.MAGIC_NUMBER:
            return None
        md.data = np.array([])
        md.data_item_count = 0
        md.bricklet_size = 0
        try:
            md._scan_raw_data(len(self.MAGIC_NUMBER), md.raw_data)
        except Exception:
            return None
        md.channel_name = self._ext_channel(filepath)
        md.result_data_file = str(filepath)
        md.axis = None
        try:
            scan = md._cu_data()
        except Exception:
            return None
        if md.object_type != 'curve':
            return None
        md.scan = scan
        md.traces = (['trace', 'retrace']
                     if getattr(scan, 'ndim', 0) == 2 and scan.shape[0] == 3
                     else ['trace'])
        return self._extract_curve(md, filepath)

    def _curve_via_a2m(self, md, filepath: Path) -> Optional[dict]:
        """Fallback: open one spectroscopy file from scratch (re-reads the
        header). Used when the fast incremental pass can't reach the file in
        header order."""
        try:
            traces, _msg = md.open(str(filepath))
        except Exception as exc:
            logger.warning("a2m could not open %s: %s", filepath.name, exc)
            return None
        if not traces or md.object_type != 'curve':
            return None
        return self._extract_curve(md, filepath)

    def _borrowed_template(self, header: Path) -> Optional[dict]:
        """Pre-parse a *borrowed* header's param stream once, for injection.

        When a session's own ``_0001.mtrx`` is missing, another session's
        header supplies the (shared) transfer functions and channel dictionary
        needed to scale raw ADC samples. Its ``BREF`` entries never match this
        session's files, so scanning the whole stream simply leaves the
        experiment configuration in ``param`` — exactly the state a2m's
        ``open()`` reaches before reading a bricklet. The parsed state is
        snapshotted so each file reuses it without re-scanning the header.
        """
        raw = self._read_header_chain(header)
        if raw[:len(self.MAGIC_NUMBER)] != self.MAGIC_NUMBER:
            return None
        md = self._new_md()
        md.raw_param = raw
        md.param = {'BREF': ''}
        md.channel_id = {}
        dp, n = 12, len(raw)
        try:
            while dp < n:
                dp = md._scan_raw_param(dp, raw)
        except Exception as exc:
            logger.debug("Could not parse borrowed header %s: %s", header, exc)
            return None
        return {'raw_param': raw,
                'param': dict(md.param),
                'channel_id': dict(md.channel_id)}

    def _curve_borrowed(self, template: dict, filepath: Path) -> Optional[dict]:
        """Extract a spectroscopy curve using a borrowed header ``template``.

        Mirrors the tail of a2m's ``open()``: inject the pre-parsed param
        state, read this file's bricklet, and let ``_cu_data`` scale it with the
        borrowed transfer functions.

        Two caveats, both handled here:

        * **The STS location belongs to the borrowed header's session**, not to
          this file, so it is a plausible-looking but wrong coordinate. It is
          cleared to ``None`` rather than passed on.
        * **The current scaling is only right if the preamp gain matched.**
          Verified against real sessions: two runs recorded on the same
          instrument an hour apart differed by an exact ×101 gain factor, so a
          borrowed header can silently mis-scale I by orders of magnitude.
          Nothing in the bricklet lets us detect this — the session's own
          header is precisely what is missing — so the curve is tagged
          ``scaling_borrowed`` and the caller surfaces it.
        """
        md = self._new_md()
        md.raw_param = template['raw_param']
        md.param = dict(template['param'])
        md.channel_id = dict(template['channel_id'])
        if not self._open_injected_data(md, filepath, is_curve=True):
            return None
        curve = self._extract_curve(md, filepath)
        if curve is not None:
            curve['location_px'] = None
            curve['location_m'] = None
            curve['parent_image'] = None
            curve['scaling_borrowed'] = True
        return curve

    def _open_injected_data(self, md, filepath: Path, is_curve: bool) -> bool:
        """Read one bricklet into ``md`` whose ``param`` is already populated.

        Replicates the data-reading half of a2m's ``open()`` (the param half
        having been supplied by a borrowed :meth:`_borrowed_template`). Returns
        True when a usable ``md.scan`` was produced.
        """
        try:
            md.raw_data = filepath.read_bytes()
        except Exception:
            return False
        if md.raw_data[:len(self.MAGIC_NUMBER)] != self.MAGIC_NUMBER:
            return False
        md.channel_name = self._ext_channel(filepath)
        md.result_data_file = str(filepath)
        md.data = np.array([])
        md.data_item_count = 0
        md.bricklet_size = 0
        md.axis = None
        try:
            md._scan_raw_data(len(self.MAGIC_NUMBER), md.raw_data)
            if is_curve:
                scan = md._cu_data()
                if md.object_type != 'curve':
                    return False
                md.scan = scan
                md.traces = (['trace', 'retrace']
                             if getattr(scan, 'ndim', 0) == 2
                             and scan.shape[0] == 3 else ['trace'])
            else:
                md.scan, md.axis = md._im_data()
                md.traces = [md.ALL_2D_TRACES[0]]
        except Exception:
            return False
        return getattr(md.scan, 'size', 0) > 0

    def _extract_curve(self, md, filepath: Path) -> Optional[dict]:
        """Build the curve dict from an ``MtrxData`` whose header+data are
        already parsed for ``filepath`` (``md.scan``/``traces``/``param`` set)."""
        traces = md.traces
        if not traces:
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
            'timestamp': _tlkb_seconds_from_bytes(getattr(md, 'raw_data', b'')),
            'location_px': location_px,
            'location_m': location_m,
            'parent_image': parent_image,
            'parent_run': parent_run,
            'channel': md.channel_name or self._ext_channel(filepath),
            'lockin': self._lockin_settings(md.param),
            'sample_name': getattr(md, 'sample_name', '') or '',
            'dataset_name': getattr(md, 'data_set_name', '') or '',
        }

    # Parameter-name fragments that identify a lock-in amplitude. MATRIX
    # names parameters "<Device>.<Property>", and the device name for the
    # lock-in is not fixed across MATRIX versions and instrument
    # configurations -- which is why this matches on fragments and records
    # the key it actually used, instead of hard-coding a name that would
    # silently find nothing on the next machine.
    _LOCKIN_DEVICE_HINTS = ('lockin', 'lock_in', 'lock-in', 'modulation')
    _LOCKIN_AMPLITUDE_HINTS = ('amplitude', 'ampl', 'deviation')
    _LOCKIN_FREQUENCY_HINTS = ('frequency', 'freq')

    @classmethod
    def _lockin_settings(cls, param: dict) -> dict:
        """Lock-in amplitude and frequency out of the MATRIX parameter tree.

        The whole tree is parsed into ``md.param`` already and only the STS
        location was ever read out of it. The modulation amplitude matters
        because it sets the energy resolution alongside temperature: the
        lock-in convolves dI/dV with a semi-ellipse of FWHM ``sqrt(3) V_mod``,
        so without it the resolution of a spectrum cannot be stated.

        **The convention is recorded as an assumption, not as a fact.** MATRIX
        does not say whether its amplitude is zero-to-peak, RMS or
        peak-to-peak, and the three differ by up to 40% in the resolution they
        imply. ``v_mod_convention_assumed`` is therefore True whenever a value
        was found, so a caller can see that the number needs confirming rather
        than reading a default as a measurement.

        Returns an empty dict when nothing matched -- never a zero, which
        would read as "no modulation" rather than "not recorded".
        """
        if not isinstance(param, dict):
            return {}

        def _number(value):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            if isinstance(value, (tuple, list)) and value:
                return _number(value[0])
            if isinstance(value, str):
                try:
                    return float(value.strip().split()[0])
                except (ValueError, IndexError):
                    return None
            return None

        found = {}
        for key, value in param.items():
            low = str(key).lower()
            if not any(h in low for h in cls._LOCKIN_DEVICE_HINTS):
                continue
            number = _number(value)
            if number is None:
                continue
            if any(h in low for h in cls._LOCKIN_AMPLITUDE_HINTS):
                found.setdefault('v_mod', number)
                found.setdefault('v_mod_source_key', str(key))
            elif any(h in low for h in cls._LOCKIN_FREQUENCY_HINTS):
                found.setdefault('lockin_frequency_hz', number)
                found.setdefault('lockin_frequency_source_key', str(key))

        if 'v_mod' in found:
            found['v_mod_convention'] = 'zero_to_peak'
            found['v_mod_convention_assumed'] = True
            logger.info("MATRIX lock-in: V_mod = %.6g V from %r (convention "
                        "assumed zero-to-peak)", found['v_mod'],
                        found['v_mod_source_key'])
        else:
            # Only worth a debug line: plenty of MATRIX experiments are run
            # with no lock-in at all, and this is not a fault.
            logger.debug("MATRIX lock-in: no modulation amplitude in %d "
                         "parameters", len(param))
        return found

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

    # Area-matching tolerances. Two scans are the "same area" when their scan
    # size matches within _AREA_SIZE_RTOL, their probe offset within
    # _AREA_OFFSET_FRAC of the scan size (with a small absolute floor for tiny
    # scans, to absorb sub-nm thermal drift between re-scans), and their scan
    # angle within _AREA_ANGLE_TOL degrees.
    _AREA_SIZE_RTOL = 0.03
    _AREA_OFFSET_FRAC = 0.08
    _AREA_OFFSET_FLOOR_M = 2e-9
    _AREA_ANGLE_TOL = 1.5

    def _same_area(self, g1: dict, g2: dict) -> bool:
        """True if two scan geometries cover the same physical area."""
        w1, h1 = g1['width_m'], g1['height_m']
        w2, h2 = g2['width_m'], g2['height_m']
        if not (w1 and h1 and w2 and h2):
            return False

        def _rclose(a, b):
            return abs(a - b) <= self._AREA_SIZE_RTOL * max(abs(a), abs(b), 1e-12)

        if not (_rclose(w1, w2) and _rclose(h1, h2)):
            return False
        tol = max(self._AREA_OFFSET_FRAC * max(w1, h1, w2, h2),
                  self._AREA_OFFSET_FLOOR_M)
        if abs(g1['x_offset_m'] - g2['x_offset_m']) > tol:
            return False
        if abs(g1['y_offset_m'] - g2['y_offset_m']) > tol:
            return False
        if abs((g1.get('angle') or 0.0) - (g2.get('angle') or 0.0)) \
                > self._AREA_ANGLE_TOL:
            return False
        return True

    def _assign_spectra_to_areas(self, groups: dict, batches: List[dict]
                                 ) -> Tuple[dict, dict]:
        """Map each scan to an area, and each spectrum-batch to an area.

        Returns ``(area_of_rs, by_area)`` where ``area_of_rs[(run, scan)]`` is a
        scan's area key and ``by_area[area_key]`` is the list of batches to show
        on every map of that area. Binding is purely by timestamp + geometry;
        the acquisition-time ordering is what separates spectra taken over one
        area from a later, different area at the same run cycle.

        Falls back to Run-Cycle binding only when timestamps are unavailable
        (older exports / borrowed headers), so behaviour degrades gracefully.
        """
        from bisect import bisect_right

        scans = []
        for rs, chans in groups.items():
            geom = next(iter(chans.values()))[1]
            scans.append({'rs': rs, 'ts': geom.get('timestamp'), 'geom': geom})

        # Scan timestamps are required to cluster/order areas; individual
        # spectra missing a timestamp are handled per-item below, so one bad
        # spectrum doesn't force the whole session onto the legacy path.
        have_ts = bool(scans) and all(s['ts'] is not None for s in scans)

        area_of_rs: Dict[Tuple[int, int], Any] = {}
        by_area: Dict[Any, List[dict]] = {}

        if not have_ts:
            # Legacy fallback: bind by Run Cycle, each scan its own key.
            for rs in groups:
                area_of_rs[rs] = rs
            for b in batches:
                run = b.get('parent_run')
                if run is None:
                    continue
                for rs in groups:
                    if rs[0] == int(run):
                        by_area.setdefault(rs, []).append(b)
            return area_of_rs, by_area

        # Time-order the scans and cluster them into areas (greedy: match each
        # scan against the representative geometry of every known area).
        scans.sort(key=lambda s: s['ts'])
        reps: List[dict] = []
        for s in scans:
            aid = next((i for i, rep in enumerate(reps)
                        if self._same_area(rep, s['geom'])), None)
            if aid is None:
                reps.append(s['geom'])
                aid = len(reps) - 1
            s['area'] = aid
            area_of_rs[s['rs']] = aid

        # Each spectrum → the area of the scan it was actually taken on.
        #
        # The Run Cycle the file records (``referenced_by``) is that scan,
        # stated by MATRIX itself, so it is used whenever it is available.
        # The timestamp heuristic below is only a fallback, because it is
        # wrong whenever a spectrum was taken *during* a scan: an image is
        # stamped when it FINISHES, so "the last scan starting before this
        # spectrum" resolves to the previous scan. That put line scans on the
        # preceding image — often a 6-row strip they could not fit on.
        area_by_run: Dict[int, Any] = {}
        for s in scans:
            area_by_run.setdefault(int(s['rs'][0]), s['area'])

        scan_ts = [s['ts'] for s in scans]
        unmatched_runs = set()
        for b in batches:
            run = b.get('parent_run')
            if run is not None:
                try:
                    area = area_by_run.get(int(run))
                except (TypeError, ValueError):
                    area = None
                if area is not None:
                    by_area.setdefault(area, []).append(b)
                    continue
                unmatched_runs.add(run)

            ts = b.get('first_timestamp')
            if ts is not None:
                i = max(bisect_right(scan_ts, ts) - 1, 0)
                by_area.setdefault(scans[i]['area'], []).append(b)

        if unmatched_runs:
            # The referenced scan is not in this session (e.g. its image files
            # were not exported); those spectra fell back to the timestamp.
            logger.info("Spectra reference run cycle(s) %s with no scan in this "
                        "session; placed by timestamp instead",
                        sorted(unmatched_runs))
        return area_of_rs, by_area

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

        # Group scan files by (run, scan): one physical scan, several channels.
        groups: Dict[Tuple[int, int], Dict[str, Tuple[Path, dict]]] = {}
        for f in sorted(image_files, key=lambda p: _parse_run_scan(p.name)):
            info = self._image_via_a2m(md, f)
            if info is None:
                continue
            groups.setdefault(_parse_run_scan(f.name), {})[info['channel_name']] = (f, info)

        # Bind each spectrum to the scan it belongs to *by acquisition time and
        # scan area* — not by Run Cycle. Scans are clustered into physical AREAS
        # by geometry (probe offset + scan size + angle); a spectrum belongs to
        # the area of the most-recent scan taken before it, and shows on every
        # scan-map of that area (re-scans of the same spot inherit its spectra).
        # A spectrum taken over a *different* area is never inherited across.
        # See :meth:`_assign_spectra_to_areas`.
        area_of_rs, by_area = self._assign_spectra_to_areas(groups, batches)

        maps: List[dict] = []
        images: List[Tuple[str, Any]] = []
        # Zero-pad run/scan so the browser's alphabetical ordering matches
        # acquisition order (…_09, _10, _11 rather than _1, _10, _11, _2).
        # Widths come from the largest index in this session, so a 9-scan
        # session stays two digits.
        max_run = max((rs[0] for rs in groups), default=1)
        max_scan = max((rs[1] for rs in groups), default=1)
        for (run, scan), chans in sorted(groups.items()):
            geom = next(iter(chans.values()))[1]  # shapes/geometry are shared
            title = f"{label} {_pad(run, max_run)}_{_pad(scan, max_scan)}"
            parent_files = {f.name for f, _ in chans.values()}

            seen, locations = set(), []
            for b in by_area.get(area_of_rs.get((run, scan)), []):
                if b['point_index'] in seen:
                    continue
                seen.add(b['point_index'])
                # Average spectrum at this point (NaN-aware mean over reps) for
                # each sweep, so clicking the dot plots that point's Forward /
                # Backward / Mixed spectra (each into its own window).
                n = len(b['V'])

                def _avg(specs):
                    good = [s for s in specs if len(s) == n]
                    if not good:
                        return None
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore', category=RuntimeWarning)
                        return np.nanmean(np.column_stack(good), axis=1).tolist()

                mix = _avg(b['mixed'])
                avg_spectra = None
                if mix is not None:
                    avg_spectra = {
                        'V': b['V'].tolist(),
                        'Mixed': mix,
                        'Forward': _avg(b['forward']),
                        'Backward': _avg(b['backward']),
                    }
                locations.append({
                    'point_index': b['point_index'],
                    'px': list(b['location_px']) if b['location_px'] else None,
                    'm': list(b['location_m']) if b['location_m'] else None,
                    'reps': len(b['mixed']),
                    # Which line scan this point belongs to (None = isolated),
                    # and its position along that line. Lets the map view
                    # outline and tag each line instead of showing a fog of
                    # identical dots.
                    'line_scan_id': b.get('line_scan_id'),
                    'line_pos': b.get('line_pos'),
                    'avg_spectra': avg_spectra,
                })
            locations.sort(key=lambda d: d['point_index'])

            # Expand every scan channel (Z, I) into one map channel per scan
            # direction — e.g. "Z fwd/up", "Z bwd/up", "Z fwd/down",
            # "Z bwd/down". A channel with a single trace keeps its bare name
            # ("Z") so single-pass scans are unchanged.
            channels: Dict[str, np.ndarray] = {}
            channel_units: Dict[str, str] = {}
            for cn, (f, info) in chans.items():
                tr = info.get('traces') or {'': info.get('data')}
                multi = len(tr) > 1
                for tlabel, data in tr.items():
                    name = f"{cn} {tlabel}" if (multi and tlabel) else cn
                    channels[name] = data
                    channel_units[name] = info['unit']

            # STS_LOCATION is a pixel coordinate in the scan the spectrum was
            # taken on, so a spectrum bound to a *differently sized* scan can
            # land outside this grid. Those points are not on this image and
            # are dropped before anything is drawn from them.
            grid = next(iter(channels.values())).shape if channels else None
            locations = self._locations_on_grid(locations, grid, title)

            # Per-line descriptors for the points that actually landed on this
            # scan — a line acquired on another area must not be outlined here.
            map_lines = self._line_overlays(locations)

            ts = geom['timestamp']
            maps.append({
                'title': title,
                'channels': channels,
                'channel_units': channel_units,
                'active_channel': self._pick_active_channel(channels),
                'width_m': geom['width_m'],
                'height_m': geom['height_m'],
                'x_offset_m': geom['x_offset_m'],
                'y_offset_m': geom['y_offset_m'],
                'angle': geom['angle'],
                'timestamp': ts.isoformat() if ts else None,
                'source_files': sorted(parent_files),
                'locations': locations,
                'line_scans': map_lines,
            })

            # ONE browsable picture per physical scan, carrying every channel ×
            # trace direction (Z fwd/up, Z bwd/up, I fwd/up, …) so the viewer
            # offers a channel selector instead of the project browser filling
            # up with near-identical "… Z" / "… I" entities.
            #
            # Channels are float single-channel: the image viewer applies the
            # colormap and range, so the raw scaled array travels untouched.
            try:
                img_channels = {
                    cn: data.astype(np.float32)
                    for cn, data in channels.items()
                }
                if img_channels:
                    rows, cols = next(iter(img_channels.values())).shape
                    # Physical pixel size (dy, dx) in nm — drives the viewer's
                    # scale bar and axis ticks.
                    px_nm = None
                    if rows and cols and geom['width_m'] and geom['height_m']:
                        px_nm = (geom['height_m'] / rows * 1e9,
                                 geom['width_m'] / cols * 1e9)
                    active = self._pick_active_channel(img_channels)
                    meta = ImageMetadata(
                        source="omicron_matrix_scan",
                        original_filename=sorted(parent_files)[0]
                            if parent_files else None,
                        pixel_size_nm=px_nm,
                        additional_info={
                            'channel': active,
                            'channel_units': dict(channel_units),
                            'session_label': label,
                            'source_files': sorted(parent_files),
                        },
                    )
                    img = ImageData.from_channels(
                        img_channels, name=title,
                        mode=ImageMode.SINGLE_FLOAT, metadata=meta,
                        active_channel=active)
                    images.append((title, img))
            except Exception as exc:
                logger.debug("Could not wrap scan %s as image: %s", title, exc)

        return maps, images

    # Short, stable labels for the four scan directions a2m exposes
    # (trace/retrace × up/down). ``forward`` is the trace, ``backward`` the
    # retrace; ``up``/``down`` is the slow (Y) scan direction.
    _TRACE_LABELS = {
        'forward/up': 'fwd/up', 'backward/up': 'bwd/up',
        'forward/down': 'fwd/down', 'backward/down': 'bwd/down',
    }

    @staticmethod
    def _pick_active_channel(names) -> Optional[str]:
        """Default channel for a map: prefer the Z forward/up topography."""
        if not names:
            return None
        for pref in ('Z fwd/up', 'Z'):
            if pref in names:
                return pref
        zs = [n for n in names if n.upper().startswith('Z')]
        return zs[0] if zs else next(iter(names))

    def _image_via_a2m(self, md, filepath: Path) -> Optional[dict]:
        """Read a scan image via access2theMatrix, with *all* available traces.

        A MATRIX scan can hold up to four directions — trace/retrace (forward /
        backward, the fast X pass) crossed with up/down (the slow Y pass). All
        that are present are returned under ``traces`` keyed by a short label
        (``fwd/up`` …); geometry/timestamp are shared. Traces whose pixel shape
        differs from the first (e.g. an interrupted down pass) are dropped so
        every trace can share one multi-channel map.
        """
        try:
            avail, _msg = md.open(str(filepath))
        except Exception as exc:
            logger.warning("a2m could not open image %s: %s", filepath.name, exc)
            return None
        if not avail or md.axis is None:
            return None

        traces: Dict[str, np.ndarray] = {}
        geom: Optional[dict] = None
        primary_shape: Optional[Tuple[int, int]] = None
        # ``avail`` is ``{index: 'forward/up', …}`` enumerated in
        # ``ALL_2D_TRACES`` order, so sorting by index puts forward/up first.
        for _idx, tname in sorted(avail.items()):
            try:
                im, _ = md.select_image(tname)
            except Exception as exc:
                logger.debug("select_image(%s) failed for %s: %s",
                             tname, filepath.name, exc)
                continue
            data = np.asarray(im.data, dtype=np.float64)
            if data.size == 0 or data.ndim != 2 or min(data.shape) < 1:
                continue
            if primary_shape is None:
                primary_shape = data.shape
            elif data.shape != primary_shape:
                logger.debug("Skipping trace %s of %s: shape %s != %s",
                             tname, filepath.name, data.shape, primary_shape)
                continue
            # NB: the down (Y-retrace) pass starts where the up pass ended, so
            # its raw rows run the other way — but access2theMatrix already
            # reverses them (``select_image`` returns the down passes in the same
            # spatial frame as the up passes). Verified against real scans: the
            # topography lines up vertically as-is; an extra flip would
            # re-mirror it. So the trace is stored exactly as a2m returns it.
            traces[self._TRACE_LABELS.get(str(tname), str(tname))] = data
            if geom is None:
                name_unit = getattr(im, 'channel_name_and_unit',
                                    ['', '']) or ['', '']
                geom = {
                    'channel_name': name_unit[0] or md.channel_name or 'Z',
                    'unit': name_unit[1] or 'm',
                    'width_m': float(getattr(im, 'width', 0.0) or 0.0),
                    'height_m': float(getattr(im, 'height', 0.0) or 0.0),
                    'x_offset_m': float(getattr(im, 'x_offset', 0.0) or 0.0),
                    'y_offset_m': float(getattr(im, 'y_offset', 0.0) or 0.0),
                    'angle': float(getattr(im, 'angle', 0.0) or 0.0),
                    'timestamp': _read_tlkb_seconds(filepath),
                }
        if geom is None or not traces:
            return None
        geom['traces'] = traces
        # Primary trace, for the browsable-picture path: forward/up when it was
        # acquired, else whichever direction came first.
        geom['data'] = traces.get('fwd/up', next(iter(traces.values())))
        return geom

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
        # Zero-padded so the overview's columns sort in acquisition order in
        # tables and graph legends (P01R1 … P10R1, not P1R1, P10R1, P2R1).
        max_point = max((b['point_index'] for b in modal), default=1)
        max_rep = max((len(b['mixed']) for b in modal), default=1)
        for b in modal:
            for r in range(len(b['mixed'])):
                spec = b['mixed'][r]
                if len(spec) != modal_len:
                    continue
                col = (f"P{_pad(b['point_index'], max_point)}"
                       f"R{_pad(r + 1, max_rep)}")
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
            # Resolution needs the modulation as much as the temperature;
            # without it a spectrum's energy resolution cannot be stated.
            **next((b['lockin'] for b in batches if b.get('lockin')), {}),
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
        n_reps = len(keep)
        rep_name = [f"Rep_{_pad(i + 1, n_reps)}" for i in range(n_reps)]
        mix_cols = {rep_name[i]: batch['mixed'][r] for i, r in enumerate(keep)}
        fwd_cols = {rep_name[i]: batch['forward'][r] for i, r in enumerate(keep)}
        bwd_cols = {rep_name[i]: batch['backward'][r] for i, r in enumerate(keep)}
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
            **(batch.get('lockin') or {}),
        )
        return SpectralData(df, metadata)

    # Sweep name → batch key.
    _SWEEPS = {'Forward': 'forward', 'Backward': 'backward', 'Mixed': 'mixed'}

    def build_line_scan_dataset(self, session: dict, line_scan: dict,
                                name: str, sweep: str = 'Mixed') -> SpectralData:
        """One dataset for a detected line scan, for the given ``sweep``
        ('Forward' / 'Backward' / 'Mixed'): one column per line position, each
        column = the **average** of that position's repetitions (NaN-aware mean)
        for that sweep direction.

        This is the kymograph the Hyperspectral tab shows (a dot per position),
        so a click on a position returns that column = its average. It's a
        single, exportable CSV (V + one averaged spectrum per position).
        """
        key = self._SWEEPS.get(sweep, 'mixed')
        by_idx = {b['point_index']: b for b in session['batches']}
        pts = [by_idx[pi] for pi in line_scan['point_indices'] if pi in by_idx]
        pts.sort(key=lambda b: b.get('line_pos') or 0)

        lengths = [len(b['V']) for b in pts]
        modal = max(set(lengths), key=lengths.count)
        pts = [b for b in pts if len(b['V']) == modal]
        V = pts[0]['V']

        def _avg(specs):
            good = [s for s in specs if len(s) == modal]
            if not good:
                return np.full(modal, np.nan)
            with warnings.catch_warnings():  # quiet all-NaN (railed) positions
                warnings.simplefilter('ignore', category=RuntimeWarning)
                return np.nanmean(np.column_stack(good), axis=1)

        cols: Dict[str, np.ndarray] = {}
        spectrum_meta: List[dict] = []
        for pos, b in enumerate(pts):
            col = f"P{pos + 1}"
            cols[col] = _avg(b[key])
            ts = b.get('first_timestamp')
            spectrum_meta.append({
                'column': col, 'point_index': b['point_index'], 'line_pos': pos,
                'location_px': list(b['location_px']) if b['location_px'] else None,
                'location_m': list(b['location_m']) if b['location_m'] else None,
                'n_reps': len(b['mixed']),
                'timestamp': ts.isoformat() if ts else None,
            })
        df = self._sweep_df(V, cols)
        metadata = self.create_metadata(
            dimensions=(len(cols), 1),
            scan_mode='line',
            units=dict(self._UNITS),
            source_directory=session['source_dir'],
            instrument='Omicron Matrix',
            sample_name=session['sample_name'],
            dataset_name=session['dataset_name'],
            session_label=session['label'],
            matrix_kind='line_scan',
            line_scan_id=line_scan['id'],
            line_scan_reps=line_scan['reps'],
            sweep_direction=sweep,
            averaged_over_reps=True,
            spectrum_meta=spectrum_meta,
        )
        return SpectralData(df, metadata)

    def build_line_scan_overview_dataset(self, session: dict, line_scan: dict,
                                         name: str, sweep: str = 'Mixed'
                                         ) -> SpectralData:
        """Every individual spectrum of one line scan, for the given ``sweep``.

        The companion to :meth:`build_line_scan_dataset`, which averages each
        position's repetitions into a single column. This one keeps them all —
        one column per (position, repetition), named ``P1R1``, ``P1R2``, … —
        so the repetitions at a position can be compared, a drifting or
        unstable one spotted, and the raw curves exported.

        Columns are numbered by **position along the line**, not by the
        session-wide point index, so ``P1`` is where the line starts. The true
        point index stays in ``spectrum_meta``.
        """
        key = self._SWEEPS.get(sweep, 'mixed')
        by_idx = {b['point_index']: b for b in session['batches']}
        pts = [by_idx[pi] for pi in line_scan['point_indices'] if pi in by_idx]
        pts.sort(key=lambda b: b.get('line_pos') or 0)

        # Same modal-length rule as everywhere else here: a session can mix
        # bias setups and a single aborted sweep can come back short, and a
        # shared V axis cannot hold both.
        lengths = [len(b['V']) for b in pts]
        modal = max(set(lengths), key=lengths.count)
        pts = [b for b in pts if len(b['V']) == modal]
        V = pts[0]['V']

        cols: Dict[str, np.ndarray] = {}
        spectrum_meta: List[dict] = []
        max_pos = len(pts)
        max_rep = max((len(b['mixed']) for b in pts), default=1)
        for pos, b in enumerate(pts, start=1):
            # A batch built by an older path may not carry the per-rep
            # timestamp/file lists; the spectra are still worth having.
            stamps = b.get('rep_timestamps') or []
            files = b.get('rep_files') or []
            for r, spec in enumerate(b[key], start=1):
                if len(spec) != modal:
                    continue
                col = f"P{_pad(pos, max_pos)}R{_pad(r, max_rep)}"
                cols[col] = spec
                ts = stamps[r - 1] if r - 1 < len(stamps) else None
                spectrum_meta.append({
                    'column': col,
                    'point_index': b['point_index'],
                    'line_pos': pos - 1,
                    'rep': r,
                    'location_px': list(b['location_px']) if b['location_px'] else None,
                    'location_m': list(b['location_m']) if b['location_m'] else None,
                    'timestamp': ts.isoformat() if ts else None,
                    'parent_image': b.get('parent_image'),
                    'file': files[r - 1] if r - 1 < len(files) else None,
                })

        df = self._sweep_df(V, cols)
        metadata = self.create_metadata(
            # Every spectrum is its own column here, so this is an ordered set
            # of curves rather than the line's N positions: the Hyperspectral
            # tab should not read it as a kymograph of the line.
            dimensions=(len(cols), 1),
            scan_mode='line',
            units=dict(self._UNITS),
            source_directory=session['source_dir'],
            instrument='Omicron Matrix',
            sample_name=session['sample_name'],
            dataset_name=session['dataset_name'],
            session_label=session['label'],
            matrix_kind='line_scan_overview',
            line_scan_id=line_scan['id'],
            line_scan_reps=line_scan['reps'],
            line_scan_points=len(pts),
            sweep_direction=sweep,
            averaged_over_reps=False,
            spectrum_meta=spectrum_meta,
            **next((b['lockin'] for b in pts if b.get('lockin')), {}),
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
            'channel': self._ext_channel(filepath), 'lockin': {},
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
