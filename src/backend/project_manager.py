"""
Project Manager for .HRT (Hyperspectral Research Tool) project files
Handles save/load of complete project state including datasets and window configurations.

File Format v2.0 (QtiPlot-inspired):
- JSON header with metadata, window configurations, and small data
- Binary sections for large numpy arrays (base64 encoded for JSON compatibility)
- Efficient compression for repeated data patterns
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import json
import logging
import gzip
import io
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime
import numpy as np
import base64

logger = logging.getLogger(__name__)

# File format version
FORMAT_VERSION = "2.0"


class ProjectManager:
    """
    Manages .HRT project files with save/load functionality.

    Format Structure (v2.0):
    {
        "format_version": "2.0",
        "application": "TRANS-QML",
        "created": ISO datetime,
        "modified": ISO datetime,
        "metadata": {project name, description, etc.},
        "datasets": {
            "name": {
                "type": "SpectralData",
                "metadata": {...},
                "data_binary": base64-encoded compressed numpy array,
                "independent_var_binary": base64-encoded numpy array
            }
        },
        "windows": {
            "tables": [{id, title, geometry, data_source, columns, formulas}],
            "graphs": [{id, title, geometry, curves, axes_config}]
        },
        "workspace": {
            "main_window": {geometry, tab_index},
            "dock_layout": {...}
        }
    }
    """

    def __init__(self):
        self.current_project_path: Optional[Path] = None
        self.project_modified: bool = False
        # Gzip level for the save in progress (set per-save by save_project)
        self._save_compresslevel: int = 1

    def save_project(self, project_path: Path, project_data: Dict[str, Any],
                     fast: bool = False) -> bool:
        """
        Save project to .HRT file with optimized binary storage.

        Parameters:
        -----------
        project_path : Path
            Path to save project file
        project_data : Dict
            Dictionary containing:
            - datasets: Dict[str, SpectralData]
            - tables: List of table window states
            - graphs: List of graph window states
            - workspace: Main window and dock layout state
            - metadata: Project metadata
        fast : bool
            Speed over size: gzip level 0 (stored blocks) on both layers.
            Float64 spectral data barely compresses anyway (~5%), so this
            trades a modestly larger file for a several-times-faster save —
            right for autosaves of GB-scale projects. The byte format stays
            a valid HRT2 gzip stream, so the load path is unchanged.

        Returns:
        --------
        bool : Success status
        """
        try:
            logger.info(f"Saving project to {project_path} (fast={fast})")
            # Compression level used for this save (arrays + outer stream)
            self._save_compresslevel = 0 if fast else 1

            # Ensure .hrt extension
            if project_path.suffix.lower() != '.hrt':
                project_path = project_path.with_suffix('.hrt')

            # Ensure parent directory exists — newly-created projects defer
            # directory creation until first save, so the project folder may
            # not yet exist on disk.
            project_path.parent.mkdir(parents=True, exist_ok=True)

            # Create project structure
            project_json = {
                'format_version': FORMAT_VERSION,
                'application': 'TRANS-QML',
                'created': project_data.get('created', datetime.now().isoformat()),
                'modified': datetime.now().isoformat(),
                'metadata': project_data.get('metadata', {
                    'name': project_path.stem,
                    'description': ''
                }),
                'datasets': self._serialize_datasets(project_data.get('datasets', {})),
                'windows': {
                    'tables': project_data.get('tables', []),
                    'graphs': project_data.get('graphs', []),
                    'image_windows': project_data.get('image_windows', []),
                    'map_editor': project_data.get('map_editor', None)
                },
                'workspace': project_data.get('workspace', {}),
                'output_files': project_data.get('output_files', []),
                'maps': project_data.get('maps', []),
                'maps_inmem': self._serialize_maps_inmem(
                    project_data.get('maps_inmem', {})),
                'images': self._serialize_images(project_data.get('images', {})),
                'notes': self._serialize_notes(project_data.get('notes', {})),
                'naming_convention': project_data.get('naming_convention'),
                'browser_tree': project_data.get('browser_tree', {}),
            }

            # Save to file (compressed). The JSON is streamed straight into a
            # gzip stream instead of building one multi-GB string and
            # gzip.compress()-ing it: the bulk of the payload is base64 of
            # already-compressed arrays, so a high outer compression level
            # only burns minutes of CPU for zero size gain (this froze the
            # app on GB-scale projects). Level 1 + streaming keeps peak
            # memory flat and the byte format identical for the load path.
            with open(project_path, 'wb') as f:
                # Write magic header for format detection
                f.write(b'HRT2')  # Magic bytes for v2.0
                with gzip.GzipFile(fileobj=f, mode='wb',
                                   compresslevel=self._save_compresslevel) as gz:
                    with io.TextIOWrapper(gz, encoding='utf-8') as text_stream:
                        json.dump(project_json, text_stream, ensure_ascii=False)

            self.current_project_path = project_path
            self.project_modified = False

            # Log file size
            file_size = project_path.stat().st_size
            logger.info(f"Project saved successfully: {project_path} ({file_size / 1024:.1f} KB)")
            return True

        except Exception as e:
            logger.error(f"Error saving project: {e}", exc_info=True)
            return False

    def load_project(self, project_path: Path) -> Optional[Dict[str, Any]]:
        """
        Load project from .HRT file.

        Parameters:
        -----------
        project_path : Path
            Path to project file

        Returns:
        --------
        Dict or None : Project data dictionary or None if failed
        """
        try:
            logger.info(f"Loading project from {project_path}")

            if not project_path.exists():
                logger.error(f"Project file not found: {project_path}")
                return None

            with open(project_path, 'rb') as f:
                # Check magic header
                magic = f.read(4)

                if magic == b'HRT2':
                    # v2.0 format - compressed
                    compressed = f.read()
                    json_str = gzip.decompress(compressed).decode('utf-8')
                    project_json = json.loads(json_str)
                else:
                    # Legacy v1.0 format - plain JSON
                    f.seek(0)
                    project_json = json.load(f)

            # Validate version
            version = project_json.get('format_version', project_json.get('version', '1.0'))
            logger.info(f"Loading project format version: {version}")

            # Deserialize datasets
            datasets = self._deserialize_datasets(project_json.get('datasets', {}))

            # Build project data
            windows = project_json.get('windows', {})
            images = self._deserialize_images(project_json.get('images', []))
            notes = self._deserialize_notes(project_json.get('notes', []))
            project_data = {
                'created': project_json.get('created'),
                'modified': project_json.get('modified'),
                'metadata': project_json.get('metadata', {}),
                'datasets': datasets,
                'tables': windows.get('tables', project_json.get('tables', [])),
                'graphs': windows.get('graphs', project_json.get('plots', [])),
                'image_windows': windows.get('image_windows', []),
                'map_editor': windows.get('map_editor', None),
                'workspace': project_json.get('workspace', {}),
                'output_files': project_json.get('output_files', []),
                'maps': project_json.get('maps', []),
                'maps_inmem': self._deserialize_maps_inmem(
                    project_json.get('maps_inmem', [])),
                'images': images,
                'notes': notes,
                'naming_convention': project_json.get('naming_convention'),
                'browser_tree': project_json.get('browser_tree', {}),
            }

            self.current_project_path = project_path
            self.project_modified = False
            logger.info(f"Project loaded successfully: {project_path}")
            return project_data

        except Exception as e:
            logger.error(f"Error loading project: {e}", exc_info=True)
            return None

    def _serialize_datasets(self, datasets: Dict) -> Dict:
        """
        Serialize datasets with binary storage for large arrays.
        Uses numpy's efficient binary format with gzip compression.
        """
        serialized = {}
        for name, dataset in datasets.items():
            try:
                if hasattr(dataset, 'spectra') and hasattr(dataset, 'metadata'):
                    # SpectralData object - use binary format for data

                    # Serialize spectra DataFrame to numpy array
                    spectra_array = dataset.spectra.values
                    independent_var = dataset.independent_var

                    # Compress and encode as base64
                    spectra_binary = self._numpy_to_base64(spectra_array)
                    indep_binary = self._numpy_to_base64(independent_var)

                    # Get column names
                    column_names = dataset.spectra.columns.tolist()

                    # Safely serialize additional_info (filter out non-serializable items)
                    additional_info = self._make_json_serializable(
                        dataset.metadata.additional_info if dataset.metadata.additional_info else {}
                    )

                    # Safely serialize units
                    units = self._make_json_serializable(
                        dataset.metadata.units if dataset.metadata.units else {}
                    )

                    serialized[name] = {
                        'type': 'SpectralData',
                        'format': 'binary',
                        'shape': list(spectra_array.shape),
                        'columns': column_names,
                        'data_binary': spectra_binary,
                        'independent_var_binary': indep_binary,
                        'independent_var_name': dataset.independent_var_name,
                        'metadata': {
                            'source_type': dataset.metadata.source_type,
                            'dimensions': list(dataset.metadata.dimensions),
                            'scan_mode': dataset.metadata.scan_mode,
                            'units': units,
                            'acquisition_date': dataset.metadata.acquisition_date,
                            'additional_info': additional_info,
                            'data_type': getattr(dataset.metadata, 'data_type', 'spectral')
                        }
                    }
                    logger.debug(f"Serialized dataset {name}: shape={spectra_array.shape}")

                elif hasattr(dataset, 'to_dict'):
                    # DataFrame - convert to binary if large
                    values = dataset.values
                    if values.size > 1000:
                        serialized[name] = {
                            'type': 'DataFrame',
                            'format': 'binary',
                            'shape': list(values.shape),
                            'columns': dataset.columns.tolist(),
                            'data_binary': self._numpy_to_base64(values)
                        }
                    else:
                        serialized[name] = {
                            'type': 'DataFrame',
                            'format': 'json',
                            'data': dataset.to_dict('list')
                        }
                else:
                    logger.warning(f"Skipping unsupported dataset type: {type(dataset).__name__} for {name}")

            except Exception as e:
                logger.error(f"Error serializing dataset {name}: {e}", exc_info=True)

        return serialized

    def _serialize_images(self, images: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Serialize :class:`ImageData` entities for embedding in the project file.

        Each image is encoded as a dict with base64 bytes (PNG for RGB/RGBA/u8/u16,
        raw float32 buffer for SINGLE_FLOAT). See :meth:`ImageData.to_dict`.
        Returns ``[]`` when ``images`` is empty so the project file gracefully
        handles the no-images case.
        """
        if not images:
            return []
        out: List[Dict[str, Any]] = []
        for image_id, image in images.items():
            try:
                payload = image.to_dict() if hasattr(image, "to_dict") else None
                if payload is None:
                    logger.warning(
                        "Skipping image %s: no to_dict method", image_id,
                    )
                    continue
                payload["id"] = image_id  # ensure id stability
                out.append(payload)
            except Exception as e:
                logger.error(
                    "Could not serialize image %s: %s", image_id, e,
                    exc_info=True,
                )
        return out

    def _serialize_notes(self, notes: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Serialize note entities (plain dicts) for project storage."""
        if not notes:
            return []
        out: List[Dict[str, Any]] = []
        for note_id, note in notes.items():
            try:
                if isinstance(note, dict):
                    out.append({
                        'id': note.get('id', note_id),
                        'name': note.get('name', 'Note'),
                        'text': note.get('text', ''),
                        'source': note.get('source', 'unknown'),
                    })
            except Exception as e:
                logger.error("Could not serialize note %s: %s", note_id, e)
        return out

    def _deserialize_notes(self, payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Reconstruct note dicts from project payloads, keyed by id."""
        if not payloads:
            return {}
        out: Dict[str, Any] = {}
        for payload in payloads:
            note_id = payload.get('id')
            if not note_id:
                continue
            out[note_id] = {
                'id': note_id,
                'name': payload.get('name', 'Note'),
                'text': payload.get('text', ''),
                'source': payload.get('source', 'unknown'),
            }
        return out

    def _deserialize_images(self, payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Reconstruct :class:`ImageData` entities from project payloads."""
        if not payloads:
            return {}
        from src.models.image_data import ImageData
        out: Dict[str, Any] = {}
        for payload in payloads:
            try:
                image = ImageData.from_dict(payload)
                out[image.id] = image
            except Exception as e:
                logger.error(
                    "Could not deserialize image %s: %s",
                    payload.get("id", "?"), e, exc_info=True,
                )
        return out

    def _serialize_maps_inmem(self, maps_inmem: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Serialize in-memory :class:`MultiChannelMap` objects for the project.

        These maps (e.g. Omicron scan images) have no on-disk file, so their
        channel arrays (base64 float32) and metadata — including the STS
        locations + per-point average spectra used for the click-to-plot dots —
        are embedded in the .hrt so the Hyperspectral tab restores on reopen.
        """
        if not maps_inmem:
            return []
        out: List[Dict[str, Any]] = []
        for map_id, mcm in maps_inmem.items():
            try:
                channels = {}
                for name, ch in mcm.channels.items():
                    arr = np.ascontiguousarray(ch.data, dtype=np.float32)
                    ctype = getattr(getattr(ch.metadata, 'channel_type', None),
                                    'value', 'custom')
                    channels[name] = {
                        'shape': list(arr.shape),
                        'b64': base64.b64encode(arr.tobytes()).decode('ascii'),
                        'units': getattr(ch.metadata, 'units', 'a.u.'),
                        'channel_type': ctype,
                    }
                meta = mcm.metadata
                out.append({
                    'id': map_id,
                    'active_channel': mcm.active_channel_name,
                    'channels': channels,
                    'metadata': {
                        'dimensions': list(meta.dimensions) if meta and meta.dimensions else None,
                        'physical_size': list(meta.physical_size) if meta and meta.physical_size else None,
                        'physical_units': getattr(meta, 'physical_units', 'um') if meta else 'um',
                        'instrument': getattr(meta, 'instrument', '') if meta else '',
                        'extra': (getattr(meta, 'extra', {}) or {}) if meta else {},
                    },
                })
            except Exception as e:
                logger.warning("Could not serialize map %s: %s", map_id, e)
        return out

    def _deserialize_maps_inmem(self, payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Reconstruct in-memory :class:`MultiChannelMap` objects from payloads."""
        out: Dict[str, Any] = {}
        if not payloads:
            return out
        from src.models.map_channel import (
            MultiChannelMap, MapMetadata, ChannelType,
        )
        for p in payloads:
            try:
                mcm = MultiChannelMap()
                for name, cd in p.get('channels', {}).items():
                    arr = np.frombuffer(
                        base64.b64decode(cd['b64']), dtype=np.float32,
                    ).reshape(cd['shape']).astype(np.float64)
                    ctype = (ChannelType.HEIGHT if name.upper().startswith('Z')
                             else ChannelType.CUSTOM)
                    mcm.add_channel(name, arr, channel_type=ctype,
                                    units=cd.get('units', 'a.u.'))
                active = p.get('active_channel')
                if active in mcm.channels:
                    mcm.set_active_channel(active)
                md = p.get('metadata', {}) or {}
                mcm.metadata = MapMetadata(
                    dimensions=tuple(md['dimensions']) if md.get('dimensions')
                    else (mcm.shape or (0, 0)),
                    physical_size=tuple(md['physical_size']) if md.get('physical_size') else None,
                    physical_units=md.get('physical_units', 'um'),
                    instrument=md.get('instrument', ''),
                    extra=md.get('extra', {}) or {},
                )
                out[p['id']] = mcm
            except Exception as e:
                logger.warning("Could not deserialize map %s: %s",
                               p.get('id', '?'), e)
        return out

    def _make_json_serializable(self, obj):
        """
        Recursively convert an object to be JSON serializable.
        Handles numpy arrays, numpy scalars, and other common types.
        """
        if obj is None:
            return None
        elif isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        elif isinstance(obj, (np.bool_,)):
            return bool(obj)
        elif isinstance(obj, (str, int, float, bool)):
            return obj
        else:
            # For non-serializable objects, convert to string representation
            try:
                # Try to convert to a basic type
                return str(obj)
            except:
                logger.warning(f"Could not serialize object of type {type(obj).__name__}, skipping")
                return None

    def _deserialize_datasets(self, serialized: Dict) -> Dict:
        """
        Deserialize datasets from JSON/binary format.
        """
        import pandas as pd
        from src.models.spectral_data import SpectralData, SpectralMetadata

        datasets = {}
        for name, data in serialized.items():
            try:
                dtype = data.get('type', 'unknown')
                fmt = data.get('format', 'json')

                if dtype == 'SpectralData':
                    if fmt == 'binary':
                        # Reconstruct from binary
                        spectra_array = self._base64_to_numpy(data['data_binary'])
                        independent_var = self._base64_to_numpy(data['independent_var_binary'])
                        columns = data.get('columns', [f'Spectrum_{i}' for i in range(spectra_array.shape[1])])

                        # Create DataFrame
                        df = pd.DataFrame(spectra_array, columns=columns)
                        indep_name = data.get('independent_var_name', 'X')
                        df.insert(0, indep_name, independent_var)
                    else:
                        # Legacy JSON format
                        df = pd.DataFrame(data['data'])
                        independent_var = np.array(data['independent_var'])

                    metadata = SpectralMetadata(
                        source_type=data['metadata']['source_type'],
                        dimensions=tuple(data['metadata']['dimensions']),
                        scan_mode=data['metadata'].get('scan_mode', 'unknown'),
                        units=data['metadata'].get('units', {}),
                        acquisition_date=data['metadata'].get('acquisition_date'),
                        additional_info=data['metadata'].get('additional_info', {}),
                        data_type=data['metadata'].get('data_type', 'spectral')
                    )

                    spectral_data = SpectralData(data=df, metadata=metadata)
                    datasets[name] = spectral_data
                    logger.debug(f"Deserialized dataset {name}: {spectral_data.num_spectra} spectra")

                elif dtype == 'DataFrame':
                    if fmt == 'binary':
                        values = self._base64_to_numpy(data['data_binary'])
                        columns = data.get('columns', [f'Col_{i}' for i in range(values.shape[1])])
                        datasets[name] = pd.DataFrame(values, columns=columns)
                    else:
                        datasets[name] = pd.DataFrame(data['data'])

                else:
                    logger.warning(f"Unknown dataset type: {dtype} for {name}")

            except Exception as e:
                logger.error(f"Error deserializing dataset {name}: {e}")

        return datasets

    def _numpy_to_base64(self, arr: np.ndarray) -> str:
        """Convert numpy array to compressed base64 string.

        Uses the current save's compression level (0 for fast autosaves,
        1 otherwise). Float64 spectral data only compresses a few percent at
        ANY gzip level — the mantissa bits are effectively noise — so high
        levels just burn minutes at GB scale for no size gain.
        """
        buffer = io.BytesIO()
        np.save(buffer, arr, allow_pickle=False)
        compressed = gzip.compress(buffer.getvalue(),
                                   compresslevel=self._save_compresslevel)
        return base64.b64encode(compressed).decode('ascii')

    def _base64_to_numpy(self, b64_str: str) -> np.ndarray:
        """Convert base64 string back to numpy array."""
        compressed = base64.b64decode(b64_str)
        decompressed = gzip.decompress(compressed)
        buffer = io.BytesIO(decompressed)
        return np.load(buffer, allow_pickle=False)

    def mark_modified(self):
        """Mark project as modified"""
        self.project_modified = True

    def is_modified(self) -> bool:
        """Check if project has been modified"""
        return self.project_modified

    def get_current_project_path(self) -> Optional[Path]:
        """Get current project file path"""
        return self.current_project_path

    def close_project(self):
        """Close current project"""
        self.current_project_path = None
        self.project_modified = False


# ============================================================================
# Window State Serialization Helpers
# ============================================================================

def serialize_window_geometry(window) -> Dict:
    """
    Serialize a QWidget/QMainWindow geometry and state.

    Returns:
    --------
    Dict with x, y, width, height, maximized, visible
    """
    geometry = window.geometry()
    return {
        'x': geometry.x(),
        'y': geometry.y(),
        'width': geometry.width(),
        'height': geometry.height(),
        'maximized': window.isMaximized(),
        'visible': window.isVisible()
    }


def restore_window_geometry(window, geometry: Dict):
    """
    Restore a QWidget/QMainWindow geometry from serialized state.
    """
    if not geometry:
        return

    x = geometry.get('x', 100)
    y = geometry.get('y', 100)
    width = geometry.get('width', 800)
    height = geometry.get('height', 600)

    window.setGeometry(x, y, width, height)

    if geometry.get('maximized', False):
        window.showMaximized()
    elif geometry.get('visible', True):
        window.show()


def serialize_plot_state(plot_window) -> Dict:
    """
    Serialize a plot window's complete state.

    Captures:
    - Window geometry
    - All curves (data, labels, colors, styles)
    - Axes configuration (labels, limits, log scale)
    - Grid settings
    """
    state = {
        'geometry': serialize_window_geometry(plot_window),
        'title': plot_window.windowTitle(),
        'curves': [],
        'axes': {},
        'grid': False
    }

    # Get canvas if available
    if hasattr(plot_window, 'canvas'):
        canvas = plot_window.canvas

        # Serialize each curve
        for line_id, line_info in canvas.plot_lines.items():
            curve_state = {
                'id': line_id,
                'label': line_info.get('label', f'Curve {line_id}'),
                'color': line_info.get('color', '#ff66b2'),
                'marker': line_info.get('marker'),
                'linestyle': line_info.get('linestyle', '-'),
                'linewidth': line_info.get('linewidth', 2),
                'alpha': line_info.get('alpha', 1.0),
                'visible': line_info.get('visible', True),
                # Store data as binary if large
                'x_data': line_info['data'][0].tolist() if len(line_info['data'][0]) < 10000 else None,
                'y_data': line_info['data'][1].tolist() if len(line_info['data'][1]) < 10000 else None
            }
            state['curves'].append(curve_state)

        # Axes configuration
        ax = canvas.axes
        state['axes'] = {
            'xlabel': ax.get_xlabel(),
            'ylabel': ax.get_ylabel(),
            'title': ax.get_title(),
            'xlim': list(ax.get_xlim()),
            'ylim': list(ax.get_ylim()),
            'xscale': ax.get_xscale(),
            'yscale': ax.get_yscale()
        }

        # Grid
        state['grid'] = ax.xaxis.get_gridlines()[0].get_visible() if ax.xaxis.get_gridlines() else False

    return state


def serialize_table_state(table_window) -> Dict:
    """
    Serialize a table window's complete state.

    Captures:
    - Window geometry
    - Table data
    - Column headers
    - Formulas
    - Column widths
    """
    state = {
        'geometry': serialize_window_geometry(table_window),
        'title': table_window.windowTitle(),
        'data': [],
        'columns': [],
        'formulas': {},
        'column_widths': []
    }

    if hasattr(table_window, 'table'):
        table = table_window.table

        # Get dimensions
        rows = table.rowCount()
        cols = table.columnCount()

        # Get headers
        state['columns'] = []
        for c in range(cols):
            header = table.horizontalHeaderItem(c)
            state['columns'].append(header.text() if header else f'Col_{c}')

        # Get data
        for r in range(rows):
            row_data = []
            for c in range(cols):
                item = table.item(r, c)
                row_data.append(item.text() if item else '')
            state['data'].append(row_data)

        # Get column widths
        for c in range(cols):
            state['column_widths'].append(table.columnWidth(c))

        # Get formulas
        if hasattr(table_window, 'formulas'):
            state['formulas'] = {
                f"{r},{c}": formula
                for (r, c), formula in table_window.formulas.items()
            }

    return state
