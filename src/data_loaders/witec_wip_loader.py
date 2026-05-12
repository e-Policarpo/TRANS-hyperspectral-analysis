"""
WITec WIP Loader
Loads PL/Raman spectra (and embedded preview images) from WITec Project
``.wip`` files produced by ControlFIVE / ControlFOUR / Project FOUR.

The binary format is a tagged tree (magic ``WIT_PR06``) — see
``docs/WITEC_LOADER_AND_IMAGE_SUPPORT.md`` for the full spec, and
``src/data_loaders/witec_wip/wip_parser.py`` for the low-level parser.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: May 2026
License: GPL
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..models.image_data import ImageData, ImageMetadata, ImageMode
from ..models.spectral_data import SpectralData, SpectralMetadata
from ..models.topography_data import TopographyData
from .base_loader import BaseDataLoader, ProgressCallback
from .witec_wip.wip_parser import (
    WipBitmap,
    WipGraph,
    WipParseError,
    WipProject,
    WipSpectralTransformation,
    parse_wip,
)

logger = logging.getLogger(__name__)


class WitecWipLoader(BaseDataLoader):
    """Loader for WITec ControlFIVE / ControlFOUR ``.wip`` project files.

    A ``.wip`` file is a session container holding any number of spectra,
    optical previews and (sometimes) hyperspectral maps. The loader extracts:

    - **Single-point spectra** (``TDGraph`` with ``SizeX × SizeY == 1``) into
      a :class:`SpectralData`. Spectra that share an axis are merged into one
      DataFrame; spectra with different axes appear as additional channels via
      ``metadata.additional_info['channels']`` (the same convention used by
      :class:`ParkAFMLoader`).
    - **Hyperspectral maps** (``SizeX × SizeY > 1``) — collected into a
      ``map_geometry`` dict in ``metadata.additional_info`` so the backend's
      topography-overlay path can route them to the map editor. (No examples
      in the test file; the path is exercised by the synthetic test fixture.)
    - **Bitmaps** (``TDBitmap`` + the project thumbnail) wrapped as
      :class:`ImageData` entries and stashed in
      ``metadata.additional_info['images']`` for the backend to register.
    """

    def __init__(self) -> None:
        super().__init__()
        self.loader_type = "witec_pl_raman"
        self.supported_extensions = [".wip"]

    # =====================================================================
    # Public API
    # =====================================================================

    def load_single_file(self, filepath: Path) -> SpectralData:
        """Standard single-file load. Returns a :class:`SpectralData`.

        For files that contain more than one spectral axis, the primary
        :class:`SpectralData` is the first axis group (largest by default),
        and the rest are attached via ``additional_info['channels']``.
        """
        return self._load(filepath)[0]

    def load_from_directory(
        self, directory: Path,
    ) -> Tuple[SpectralData, Optional[TopographyData]]:
        """Aggregate every .wip in ``directory``.

        Each file's spectra appear as separate channels keyed by file stem.
        """
        files = sorted(directory.glob("*.wip"))
        if not files:
            raise ValueError(f"No .wip files found in {directory}")

        per_file_channels: Dict[str, SpectralData] = {}
        first_sd: Optional[SpectralData] = None
        for f in files:
            try:
                sd = self.load_single_file(f)
            except Exception as e:
                logger.warning("Skipping %s: %s", f, e)
                continue
            per_file_channels[f.stem] = sd
            if first_sd is None:
                first_sd = sd

        if first_sd is None:
            raise ValueError(f"No loadable .wip files in {directory}")

        # Merge channels across files.
        merged: Dict[str, SpectralData] = {}
        for stem, sd in per_file_channels.items():
            sub = sd.metadata.additional_info.get("channels") or {stem: sd}
            for ch_name, ch_sd in sub.items():
                key = f"{stem} · {ch_name}" if len(per_file_channels) > 1 else ch_name
                merged[key] = ch_sd
        first_sd.metadata.additional_info["channels"] = merged
        self.last_loaded_path = directory
        return first_sd, None

    def smart_load_from_file(
        self, filepath: Path,
        progress_callback: ProgressCallback = None,
    ) -> Tuple[SpectralData, Optional[TopographyData]]:
        """Smart-import entry point used by the dataset-import dialog.

        Functionally identical to :meth:`load_single_file` for now —
        WITec's session structure is already self-describing, so there are
        no sibling files to discover. Returns a ``(SpectralData, None)``
        tuple matching the contract of the other smart loaders.
        """
        sd = self._load(filepath, progress_callback)[0]
        return sd, None

    # =====================================================================
    # Internal: full-file load
    # =====================================================================

    def _load(
        self, filepath: Path,
        progress_callback: ProgressCallback = None,
    ) -> Tuple[SpectralData, WipProject]:
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(filepath)

        if progress_callback:
            progress_callback(0, 4, f"Parsing {filepath.name}")
        try:
            project = parse_wip(filepath)
        except WipParseError as e:
            raise ValueError(f"Could not parse {filepath}: {e}") from e

        if progress_callback:
            progress_callback(1, 4, "Extracting spectra")
        single_graphs = [g for g in project.graphs if g.is_single_spectrum]
        map_graphs = [g for g in project.graphs if not g.is_single_spectrum]

        if not single_graphs and not map_graphs:
            raise ValueError(
                f"{filepath.name}: no spectra or maps found in WIP file"
            )

        # ----- single-point spectra grouped by axis ---------------------
        channels: Dict[str, SpectralData] = {}
        if single_graphs:
            channels = self._group_single_spectra(project, single_graphs)

        # ----- hyperspectral maps ---------------------------------------
        map_geometries: List[Dict[str, Any]] = []
        for g in map_graphs:
            try:
                map_geometries.append(self._build_map_geometry(project, g))
            except Exception as e:
                logger.warning(
                    "Skipping hyperspectral map %r: %s", g.entry.caption, e
                )

        # ----- images ---------------------------------------------------
        if progress_callback:
            progress_callback(2, 4, "Extracting images")
        images = self._extract_images(project, filepath.stem)

        # ----- notes (TDText annotations) -------------------------------
        notes: List[Dict[str, Any]] = []
        for txt in project.texts:
            text_value = (txt.text or "").strip()
            caption = (txt.entry.caption or "").strip()
            if not text_value and not caption and not txt.rtf_bytes:
                continue
            note = {
                'name': caption or "Note",
                'text': text_value,
                'source': f"witec_wip:{filepath.name}",
            }
            # Hand over the raw RTF too — the backend can save it as ``.rtf``
            # so the OS opens a properly-formatted document, while the
            # embedded note window uses the stripped plain-text body.
            if txt.rtf_bytes:
                note['rtf_bytes'] = txt.rtf_bytes
            notes.append(note)

        if progress_callback:
            progress_callback(3, 4, "Building dataset")

        # Pick the primary SpectralData. Prefer the channel with the most
        # spectra (most informative for the user); fall back to a single-bin
        # placeholder when there are only maps.
        if channels:
            primary_name = max(
                channels.keys(), key=lambda k: channels[k].num_spectra
            )
            primary = channels[primary_name]
        else:
            primary = self._make_empty_spectral_placeholder(filepath)

        primary.metadata.additional_info.setdefault("channels", {})
        if channels:
            primary.metadata.additional_info["channels"] = channels
        if images:
            primary.metadata.additional_info["images"] = images
        if notes:
            primary.metadata.additional_info["notes"] = notes
        if map_geometries:
            primary.metadata.additional_info["map_geometries"] = map_geometries

        primary.metadata.additional_info["wip_version"] = project.version
        primary.metadata.additional_info["source_file"] = str(filepath)

        # Acquisition info, excitation wavelength, and spectral cursors —
        # all attached to the primary dataset's additional_info so the
        # backend / UI can find them via a single lookup.
        if project.system_info.application_versions:
            primary.metadata.additional_info['acquisition'] = {
                'software': project.system_info.application_versions[0],
                'license_ids': project.system_info.license_ids,
                'service_id': project.system_info.service_id,
                'system_id': project.system_info.system_id,
            }
        if project.excitation_wavelength_nm:
            primary.metadata.additional_info['excitation_wavelength_nm'] = (
                float(project.excitation_wavelength_nm)
            )
        if project.spectral_cursors:
            primary.metadata.additional_info['spectral_cursors'] = [
                {
                    'positions': list(c.positions),
                    'unit': c.standard_unit,
                    'label': (c.entry.caption or 'Cursor').strip(),
                }
                for c in project.spectral_cursors
            ]

        if progress_callback:
            progress_callback(4, 4, "Complete!")

        self.last_loaded_path = filepath
        return primary, project

    # =====================================================================
    # Helpers
    # =====================================================================

    def _group_single_spectra(
        self,
        project: WipProject,
        graphs: List[WipGraph],
    ) -> Dict[str, SpectralData]:
        """Bucket spectra by their resolved spectral axis.

        Returns a dict ``{channel_name: SpectralData}``. Channel names are
        based on the unit and the axis range, so ``"461-629nm"`` and
        ``"461-841nm"`` end up in different SpectralData objects.
        """
        # axis_signature → list of (graph, axis_array, unit)
        buckets: Dict[Tuple, List[Tuple[WipGraph, np.ndarray, str]]] = {}
        for g in graphs:
            xt = project.get_spectral_transformation(g.x_transformation_id)
            if xt is None:
                logger.warning(
                    "Spectrum %r references missing transformation id %d; "
                    "using bin-index axis",
                    g.entry.caption, g.x_transformation_id,
                )
                axis = np.arange(g.size_graph, dtype=np.float64)
                unit = "bin"
            else:
                axis = xt.axis(g.size_graph)
                unit = xt.standard_unit or "a.u."
            sig = self._axis_signature(axis, unit)
            buckets.setdefault(sig, []).append((g, axis, unit))

        channels: Dict[str, SpectralData] = {}
        used_names: Dict[str, int] = {}
        for sig, group in buckets.items():
            unit = group[0][2]
            axis = group[0][1]
            channel_name = self._channel_name_for_axis(axis, unit)
            channel_name = self._dedup(channel_name, used_names)
            df = self._build_dataframe(axis, unit, group)
            zint = project.get_interpretation(group[0][0].z_interpretation_id)
            y_unit = zint.standard_unit if zint else "counts"
            metadata = SpectralMetadata(
                source_type=self.loader_type,
                dimensions=(len(group), 1),
                scan_mode="point",
                units={
                    "x": unit,
                    "independent": unit,
                    "dependent": y_unit or "counts",
                },
                additional_info={
                    "captions": [g.entry.caption for g, _, _ in group],
                    "wip_data_ids": [g.entry.id for g, _, _ in group],
                    "axis_unit": unit,
                },
            )
            channels[channel_name] = SpectralData(df, metadata)
        return channels

    @staticmethod
    def _axis_signature(axis: np.ndarray, unit: str) -> Tuple:
        """Return a hashable signature that's identical for matching axes.

        Round to 6 significant figures to absorb float jitter. Different
        units never share a bucket.
        """
        if axis.size == 0:
            return (unit, 0)
        # Six-sig-fig round, sample-by-sample, with axis length to
        # disambiguate sub-arrays of the same start/end.
        sig = (
            unit,
            int(axis.size),
            float(np.round(axis[0], 6)),
            float(np.round(axis[-1], 6)),
            # spacing as a tiebreaker for non-linear axes
            float(np.round(axis[axis.size // 2], 6)) if axis.size > 1 else 0.0,
        )
        return sig

    @staticmethod
    def _channel_name_for_axis(axis: np.ndarray, unit: str) -> str:
        if axis.size == 0:
            return f"Empty ({unit})"
        return f"{int(round(axis[0]))}-{int(round(axis[-1]))} {unit}"

    @staticmethod
    def _dedup(name: str, used: Dict[str, int]) -> str:
        if name not in used:
            used[name] = 1
            return name
        used[name] += 1
        return f"{name} ({used[name]})"

    def _build_dataframe(
        self,
        axis: np.ndarray,
        unit: str,
        group: List[Tuple[WipGraph, np.ndarray, str]],
    ) -> pd.DataFrame:
        col_name = self._axis_column_name(unit)
        data = {col_name: axis}
        used: Dict[str, int] = {}
        for g, _ax, _u in group:
            raw_caption = g.entry.caption.strip() or f"Spectrum_{g.entry.id}"
            label = self._clean_caption(raw_caption) or raw_caption
            label = self._dedup(label, used)
            spectrum = g.get_spectrum(0, 0)
            # Shape match safety: trim/pad if SizeGraph != axis length.
            if spectrum.size != axis.size:
                m = min(spectrum.size, axis.size)
                spectrum = spectrum[:m]
                if m < axis.size:
                    pad = np.full(axis.size - m, np.nan, dtype=spectrum.dtype)
                    spectrum = np.concatenate([spectrum, pad])
            data[label] = spectrum.astype(np.float64, copy=False)
        return pd.DataFrame(data)

    @staticmethod
    def _clean_caption(caption: str) -> str:
        """Strip WITec boilerplate from a spectrum caption.

        WITec captions are typically a verbose descriptor + the meaningful
        sample/molecule name, e.g.

            "Stitched Spectrum (461->629nm) DtBuTPZ Toluene 150 uW"
            "Single Spectrum_107_Spec.Data 1"

        For column headers we want the trailing sample portion. This helper
        removes a leading ``Stitched Spectrum (...)``, ``Single Spectrum_*``,
        ``Spectrum (n)`` etc., collapses whitespace, and returns what's left.
        Returns an empty string if nothing meaningful remains — the caller
        falls back to the raw caption in that case.
        """
        import re
        text = caption.strip()
        # Match the longer/more-specific underscore form FIRST so it
        # consumes the trailing "_107_Spec.Data 1" in one shot, before
        # the generic ``(Stitched|Single) Spectrum`` rule eats just the
        # leading words and leaves the boilerplate behind.
        text = re.sub(
            r"^Single\s+Spectrum_\d+(?:_Spec\.Data\s*\d*)?\s*",
            "", text, flags=re.IGNORECASE,
        )
        # Generic "Stitched Spectrum (461->629nm)" / "Single Spectrum (...)" /
        # bare "Stitched Spectrum" prefixes.
        text = re.sub(
            r"^(Stitched|Single)\s+Spectrum\s*(\([^)]*\))?\s*",
            "", text, flags=re.IGNORECASE,
        )
        # Plain "Spectrum N" left over from a different acquisition path.
        text = re.sub(r"^Spectrum\s*\d*\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s{2,}", " ", text).strip()
        return text

    @staticmethod
    def _axis_column_name(unit: str) -> str:
        # Sanitize unit string for column naming.
        if not unit or unit == "a.u.":
            return "Variable"
        # "nm" → "Wavelength_nm", "cm-1" → "Raman_Shift_cm-1", etc.
        unit_stripped = unit.replace(" ", "_")
        prefix = {
            "nm": "Wavelength",
            "µm": "Wavelength",
            "um": "Wavelength",
            "cm-1": "Raman_Shift",
            "1/cm": "Raman_Shift",
            "eV": "Energy",
            "meV": "Energy",
            "Hz": "Frequency",
            "THz": "Frequency",
        }.get(unit_stripped, "X")
        return f"{prefix}_{unit_stripped}"

    # ----------------------------------------------------------- maps
    def _build_map_geometry(
        self, project: WipProject, graph: WipGraph,
    ) -> Dict[str, Any]:
        """Assemble a map-channel descriptor for a hyperspectral TDGraph.

        Stored verbatim in ``metadata.additional_info['map_geometries']`` so
        the backend (which knows how to construct ``MultiChannelMap``) can
        consume it without WITec-specific imports.
        """
        xt = project.get_spectral_transformation(graph.x_transformation_id)
        axis = xt.axis(graph.size_graph) if xt else np.arange(graph.size_graph)
        unit = xt.standard_unit if xt else "bin"
        # Spatial calibration: WITec stores it on TDSpaceTransformation,
        # which we expose as a raw dict for downstream consumption.
        space = project.space_transformations.get(graph.space_transformation_id)
        return {
            "caption": graph.entry.caption,
            "wip_data_id": graph.entry.id,
            "size_x": graph.size_x,
            "size_y": graph.size_y,
            "size_graph": graph.size_graph,
            "data": graph.data,  # shape (size_y, size_x, size_graph)
            "axis": axis,
            "axis_unit": unit,
            "space_transformation": space.raw if space is not None else {},
            "spatial_unit": space.standard_unit if space is not None else "",
        }

    # --------------------------------------------------------- images
    def _extract_images(
        self, project: WipProject, file_stem: str,
    ) -> List[Tuple[str, ImageData]]:
        """Wrap every WipBitmap (and the project thumbnail) as ImageData.

        For each bitmap, the loader resolves its ``SpaceTransformationID`` to
        the matching ``TDSpaceTransformation`` and stamps the image's
        metadata with the pixel size and world-coord bounds. Any global
        ``TDSpaceCursor`` whose position falls inside those bounds is
        attached as ``spatial_cursor`` so the viewer can draw a crosshair.
        """
        out: List[Tuple[str, ImageData]] = []
        cursors = project.space_cursors or []

        for bm in project.bitmaps:
            img = self._wip_bitmap_to_image(bm, file_stem)
            if img is None:
                continue
            self._attach_spatial_metadata(img, bm, project, cursors)
            out.append((img.name, img))

        if project.thumbnail is not None:
            img = self._wip_bitmap_to_image(project.thumbnail, file_stem)
            if img is not None:
                img.name = f"{file_stem} (thumbnail)"
                out.append((img.name, img))
        return out

    @staticmethod
    def _attach_spatial_metadata(
        img: ImageData, bm: WipBitmap, project: WipProject, cursors: list,
    ) -> None:
        """Stamp pixel-size, world-bounds, and any in-bounds cursor onto
        the image's metadata. No-op when no calibrated transformation
        exists for the bitmap."""
        st = project.get_space_transformation(bm.space_transformation_id)
        if st is None or not st.is_calibrated:
            return
        # Pixel-size in world units. WITec stores µm by default; pass the
        # unit through unchanged so callers know what they're looking at.
        dx, dy = st.pixel_size_world
        img.metadata.additional_info['pixel_size'] = {
            'dx': float(dx), 'dy': float(dy), 'unit': st.standard_unit or 'µm',
        }
        if st.standard_unit in ('µm', 'um', 'micron', 'microns'):
            img.metadata.pixel_size_nm = (float(dy) * 1000.0, float(dx) * 1000.0)
        # World-coord bounds of the image rectangle.
        wx0, wy0 = st.world_xy(0, 0)
        wx1, wy1 = st.world_xy(bm.width, bm.height)
        x_min, x_max = min(wx0, wx1), max(wx0, wx1)
        y_min, y_max = min(wy0, wy1), max(wy0, wy1)
        img.metadata.additional_info['world_bounds'] = {
            'x_min': x_min, 'x_max': x_max,
            'y_min': y_min, 'y_max': y_max,
            'unit': st.standard_unit or 'µm',
        }
        # Attach any TDSpaceCursor that falls inside this image.
        cursor_pts = []
        for c in cursors:
            for (wx, wy, _wz) in c.positions:
                if not (x_min <= wx <= x_max and y_min <= wy <= y_max):
                    continue
                px, py = st.pixel_xy(wx, wy)
                cursor_pts.append({
                    'x_world': float(wx), 'y_world': float(wy),
                    'x_pixel': float(px), 'y_pixel': float(py),
                    'label': (c.entry.caption or 'Cursor').strip(),
                    'unit': c.standard_unit or st.standard_unit,
                })
        if cursor_pts:
            img.metadata.additional_info['spatial_cursors'] = cursor_pts

    @staticmethod
    def _wip_bitmap_to_image(
        bm: WipBitmap, file_stem: str,
    ) -> Optional[ImageData]:
        if bm.array is None:
            return None
        arr = bm.array
        # Pick a sensible mode from the array shape and dtype.
        if arr.ndim == 3 and arr.shape[2] == 4:
            mode = ImageMode.RGBA
        elif arr.ndim == 3 and arr.shape[2] == 3:
            mode = ImageMode.RGB
        elif arr.ndim == 2 and arr.dtype == np.uint8:
            mode = ImageMode.GRAY_U8
        elif arr.ndim == 2 and arr.dtype == np.uint16:
            mode = ImageMode.GRAY_U16
        elif arr.ndim == 2:
            mode = ImageMode.SINGLE_FLOAT
            arr = arr.astype(np.float32, copy=False)
        else:
            logger.warning(
                "Skipping bitmap %r: unsupported shape %s",
                bm.entry.caption, arr.shape,
            )
            return None
        caption = bm.entry.caption.strip() or f"Bitmap {bm.entry.id}"
        return ImageData(
            array=arr, mode=mode,
            metadata=ImageMetadata(
                source="witec_wip_bitmap",
                original_filename=f"{file_stem}.wip",
                additional_info={
                    "wip_data_id": bm.entry.id,
                    "wip_class_name": bm.entry.class_name,
                    "wip_caption": bm.entry.caption,
                    "wip_source": bm.source,
                    "wip_data_type_code": bm.data_type_code,
                },
            ),
            name=caption,
        )

    # ------------------------------------------------- placeholder dataset
    def _make_empty_spectral_placeholder(
        self, filepath: Path,
    ) -> SpectralData:
        """Used when a .wip contains only maps (no single-point spectra)."""
        df = pd.DataFrame({"Variable": [0.0], "Empty": [0.0]})
        meta = SpectralMetadata(
            source_type=self.loader_type,
            dimensions=(0, 0),
            scan_mode="point",
            units={"independent": "a.u.", "dependent": "a.u."},
            additional_info={"placeholder": True},
        )
        return SpectralData(df, meta)
