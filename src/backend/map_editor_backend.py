"""
Map Editor Backend - QObject bridge for Map Editor Workstation
Connects QML UI to MultiChannelMap data model and processing operations.
Implements the TRANS_v3 interactive canvas paradigm in QML.
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import logging
import warnings

from PySide6.QtCore import (
    QObject, Signal, Slot, Property, QUrl
)
from PySide6.QtQml import QmlElement

from src.models.map_channel import (
    MultiChannelMap, MapChannel, MapMetadata, ChannelMetadata, ChannelType
)
from src.models.spectral_data import SpectralData

logger = logging.getLogger(__name__)

# QML registration
QML_IMPORT_NAME = "TransQML"
QML_IMPORT_MAJOR_VERSION = 1


@QmlElement
class MapEditorBackend(QObject):
    """
    Backend bridge for Map Editor Workstation.

    Manages:
    - Multi-channel map data (height, amplitude, phase, etc.)
    - Spectral-spatial reconstruction (linking spectral cube to map)
    - Block selection and averaging (TRANS_v3 style)
    - Processing operations (filters, leveling, etc.)

    Signals are emitted to QML for UI updates.
    """

    # Signals to QML
    mapDataChanged = Signal()
    channelListChanged = Signal()
    activeChannelChanged = Signal(str, arguments=['channelName'])
    spectralDataChanged = Signal()
    processingStarted = Signal(str, arguments=['operation'])
    processingFinished = Signal(str, bool, str, arguments=['operation', 'success', 'message'])
    selectionChanged = Signal(int, arguments=['blockCount'])
    statisticsUpdated = Signal('QVariantMap', arguments=['stats'])
    discretizationReady = Signal(int, int, arguments=['gridRows', 'gridCols'])

    # New signals for dataset linking and spectrum plotting
    linkedDatasetsChanged = Signal()
    spectrumReady = Signal(str, 'QVariantMap', arguments=['datasetName', 'spectrumData'])
    openPlotWindowRequested = Signal(str, 'QVariantList', arguments=['datasetName', 'spectra'])
    # Append spectra to an already-open plot window instead of resending every
    # curve it holds. Selecting the Nth STS point otherwise costs N curve
    # conversions across the QML bridge, so a long selection crawls.
    appendPlotCurvesRequested = Signal(str, 'QVariantList',
                                       arguments=['datasetName', 'spectra'])
    # Average (mixed) spectrum of the currently-selected STS dots, pushed to the
    # inline "Average Spectrum" panel. Empty map ({}) clears it.
    stsAverageUpdated = Signal('QVariantMap', arguments=['result'])
    # Line-scan / point-set viewing (non-area spatially-resolved spectra).
    lineScanModeChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Data
        self._multi_channel_map: Optional[MultiChannelMap] = None
        self._canvas = None  # Reference to QMLMapCanvas

        # Linked datasets for spectrum viewing (name -> SpectralData)
        self._linked_datasets: Dict[str, SpectralData] = {}
        self._active_dataset: Optional[str] = None
        # >0 while a beginLinkBatch/endLinkBatch pair is open: link/clear
        # calls mutate state but hold back linkedDatasetsChanged.
        self._link_batch_depth = 0

        # Cache for QML properties
        self._channel_names: List[str] = []
        self._active_channel_name: str = ""

        # Reference to the AppBackend (set by QML), used to look up
        # in-memory MultiChannelMap entities by id without disk I/O.
        self._app_backend = None

        # Line-scan / point-set mode: a non-area dataset shown as a 2-D
        # array where columns are positions (point index). Clicks resolve a
        # spectrum by column, not by the area-map ``row*cols+col``.
        self._line_scan_mode: bool = False
        self._line_scan_dataset: str = ""
        self._line_scan_view: str = "kymograph"  # "kymograph" | "strip"

    def set_app_backend(self, app_backend) -> None:
        """Inject the AppBackend reference (called from QML at startup).

        Enables ``loadMapById`` to retrieve in-memory maps without going
        through the filesystem, fixing the broken project-browser
        double-click for maps that were imported in-memory.
        """
        self._app_backend = app_backend

    # =========================================================================
    # Properties exposed to QML
    # =========================================================================

    @Property(bool, notify=mapDataChanged)
    def hasMapData(self) -> bool:
        return self._multi_channel_map is not None and len(self._multi_channel_map) > 0

    @Property('QVariantList', notify=channelListChanged)
    def channelNames(self) -> List[str]:
        if self._multi_channel_map is None:
            return []
        return self._multi_channel_map.channel_names

    @Property(str, notify=activeChannelChanged)
    def activeChannelName(self) -> str:
        if self._multi_channel_map is None:
            return ""
        return self._multi_channel_map.active_channel_name or ""

    @Property(int, notify=mapDataChanged)
    def mapRows(self) -> int:
        if self._multi_channel_map is None or self._multi_channel_map.shape is None:
            return 0
        return self._multi_channel_map.shape[0]

    @Property(int, notify=mapDataChanged)
    def mapCols(self) -> int:
        if self._multi_channel_map is None or self._multi_channel_map.shape is None:
            return 0
        return self._multi_channel_map.shape[1]

    @Property(bool, notify=spectralDataChanged)
    def hasSpectralData(self) -> bool:
        return (self._multi_channel_map is not None and
                self._multi_channel_map.has_spectral_link)

    @Property(int, notify=spectralDataChanged)
    def spectralPoints(self) -> int:
        if self._multi_channel_map is None:
            return 0
        return self._multi_channel_map.spectral_points

    @Property(bool, notify=lineScanModeChanged)
    def isLineScanMode(self) -> bool:
        """True when the tab is showing a line scan / point set (not an area map)."""
        return self._line_scan_mode

    @Property(str, notify=lineScanModeChanged)
    def lineScanView(self) -> str:
        """Current line-scan view: "kymograph" or "strip"."""
        return self._line_scan_view

    @Property(int, notify=lineScanModeChanged)
    def lineScanPoints(self) -> int:
        """Number of positions (spectra) in the active line scan."""
        if not self._line_scan_mode:
            return 0
        data = self._linked_datasets.get(self._line_scan_dataset)
        return int(data.num_spectra) if data is not None else 0

    @Property('QVariantList', notify=linkedDatasetsChanged)
    def linkedDatasetNames(self) -> List[str]:
        """Get list of linked dataset names"""
        return list(self._linked_datasets.keys())

    @Property(str, notify=linkedDatasetsChanged)
    def activeDataset(self) -> str:
        """Get currently active dataset for spectrum viewing"""
        return self._active_dataset or ""

    @Slot(result='QVariantMap')
    def getMapSpectraInfo(self) -> Dict:
        """Summary of the spectra associated with the current map (item 4).

        Feeds the map-metadata panel: how many STS points were taken on this
        scan, the bias sweep (range + points), which sweep directions exist,
        and the names of any linked spectral datasets.
        """
        info = {
            'sts_point_count': 0,
            'linked_datasets': list(self._linked_datasets.keys()),
            'sweeps': [],
            'bias_points': 0,
        }
        mcm = self._multi_channel_map
        if mcm is None:
            return info
        try:
            extra = getattr(mcm.metadata, 'extra', None) or {}
            locs = extra.get('sts_locations', []) or []
        except Exception:
            locs = []
        info['sts_point_count'] = len(locs)
        # Read the bias axis / available sweeps off the first point's average
        # (tolerant of the legacy single-spectrum schema).
        avg = (self._loc_avg_spectra(locs[0]) if locs else None) or {}
        V = avg.get('V')
        if V is not None and len(V) > 0:
            varr = np.asarray(V, dtype=float)
            info['bias_min'] = float(np.nanmin(varr))
            info['bias_max'] = float(np.nanmax(varr))
            info['bias_points'] = int(varr.size)
        info['sweeps'] = [s for s in ('Forward', 'Backward', 'Mixed')
                          if avg.get(s) is not None]
        return info

    # =========================================================================
    # Dataset Linking for Spectrum Viewing
    # =========================================================================

    @Slot()
    def beginLinkBatch(self):
        """Suppress ``linkedDatasetsChanged`` until :meth:`endLinkBatch`.

        The workstation relinks *every* dataset whenever new data loads, so
        without batching one import emitted one signal per dataset — each of
        which re-evaluates every binding on ``linkedDatasets``. With a few
        thousand imported Matrix datasets that alone is quadratic.
        """
        self._link_batch_depth += 1

    @Slot()
    def endLinkBatch(self):
        """End a batch opened by :meth:`beginLinkBatch` and emit once."""
        self._link_batch_depth = max(0, self._link_batch_depth - 1)
        if self._link_batch_depth == 0:
            self.linkedDatasetsChanged.emit()

    @Slot(str, 'QVariant')
    def linkDataset(self, name: str, spectral_data):
        """
        Link a SpectralData object for spectrum viewing.
        Each pixel maps to a column in the dataset.
        """
        if spectral_data is None:
            logger.warning(f"Cannot link None dataset: {name}")
            return

        self._linked_datasets[name] = spectral_data

        # Set as active if first dataset or if it has "truncated" in name
        if self._active_dataset is None or "truncated" in name.lower():
            self._active_dataset = name

        if not self._link_batch_depth:
            self.linkedDatasetsChanged.emit()
        logger.debug("Linked dataset '%s' with %s spectra",
                     name, spectral_data.num_spectra)

    # =========================================================================
    # Line-scan / point-set viewing (non-area spatially-resolved spectra)
    # =========================================================================

    @staticmethod
    def _build_line_scan_array(spectral_data, view: str) -> np.ndarray:
        """Build the 2-D array shown for a line/point dataset.

        - ``"kymograph"``: ``(P points × N positions)`` — column j is
          spectrum j. This is the ``spectra`` DataFrame as-is.
        - ``"strip"``: ``(1 × N)`` — a single summary value per position
          (mean over the spectral axis).
        """
        spectra = np.asarray(spectral_data.spectra.values, dtype=float)
        if view == "strip":
            with np.errstate(all="ignore"):
                strip = np.nanmean(spectra, axis=0)
            return strip.reshape(1, -1)
        return spectra  # kymograph (P × N)

    @Slot(str, str)
    def loadDatasetAsLineScan(self, name: str, view: str = "kymograph"):
        """Show a line-scan / point-set dataset in the tab.

        Builds the chosen 2-D view (kymograph or scalar strip), links the
        dataset for per-position spectrum inspection, and enters line-scan
        mode so clicks resolve a spectrum by column (position index).
        """
        if self._app_backend is None or not hasattr(self._app_backend, "_datasets"):
            logger.warning("loadDatasetAsLineScan: AppBackend not available")
            return
        spectral_data = self._app_backend._datasets.get(name)
        if spectral_data is None:
            logger.warning(f"loadDatasetAsLineScan: dataset not found: {name}")
            return

        view = view if view in ("kymograph", "strip") else "kymograph"
        self.linkDataset(name, spectral_data)
        self._active_dataset = name
        self._line_scan_mode = True
        self._line_scan_dataset = name
        self._line_scan_view = view

        arr = self._build_line_scan_array(spectral_data, view)
        # Fresh single-channel map (kymograph/strip differ in shape from any
        # previously-shown map, and MultiChannelMap pins a single shape).
        self._multi_channel_map = None
        self.setMapDataFromArray(arr, name)  # emits map/channel signals + sets canvas
        self._push_line_scan_axes(spectral_data, view)
        self.lineScanModeChanged.emit()
        logger.info(
            f"Loaded line scan '{name}' as {view}: "
            f"{spectral_data.num_spectra} positions, "
            f"{spectral_data.num_points} points"
        )

    @Slot(str)
    def setLineScanView(self, view: str):
        """Toggle the active line scan between "kymograph" and "strip"."""
        if not self._line_scan_mode or view not in ("kymograph", "strip"):
            return
        if view == self._line_scan_view:
            return
        spectral_data = self._linked_datasets.get(self._line_scan_dataset)
        if spectral_data is None:
            return
        self._line_scan_view = view
        arr = self._build_line_scan_array(spectral_data, view)
        # Kymograph (P×N) and strip (1×N) differ in shape — rebuild the map.
        self._multi_channel_map = None
        self.setMapDataFromArray(arr, self._line_scan_dataset)
        self._push_line_scan_axes(spectral_data, view)
        self.lineScanModeChanged.emit()

    def _exit_line_scan_mode(self):
        """Leave line-scan mode (called when a real area map is loaded)."""
        if self._line_scan_mode:
            self._line_scan_mode = False
            self._line_scan_dataset = ""
            self.lineScanModeChanged.emit()

    @Slot(str)
    def unlinkDataset(self, name: str):
        """Remove a linked dataset"""
        if name in self._linked_datasets:
            del self._linked_datasets[name]
            if self._active_dataset == name:
                self._active_dataset = next(iter(self._linked_datasets.keys()), None)
            self.linkedDatasetsChanged.emit()

    @Slot()
    def clearLinkedDatasets(self):
        """Clear all linked datasets"""
        self._linked_datasets.clear()
        self._active_dataset = None
        if not self._link_batch_depth:
            self.linkedDatasetsChanged.emit()

    @Slot(str)
    def setActiveDataset(self, name: str):
        """Set the active dataset for spectrum viewing"""
        if name in self._linked_datasets:
            self._active_dataset = name
            self.linkedDatasetsChanged.emit()
            logger.info(f"Active dataset set to: {name}")

    @Slot(str, int, int, result='QVariantMap')
    def getSpectrumFromDataset(self, dataset_name: str, row: int, col: int) -> Dict:
        """
        Get spectrum at (row, col) from a specific dataset.
        The spectrum index is calculated as: row * num_cols + col

        For integrated datasets, returns the integrated values across intervals.
        """
        if dataset_name not in self._linked_datasets:
            return {'error': f'Dataset not found: {dataset_name}'}

        spectral_data = self._linked_datasets[dataset_name]
        dims = spectral_data.metadata.dimensions

        if self._line_scan_mode and dataset_name == self._line_scan_dataset:
            # Line scan / point set: the displayed array's columns ARE the
            # positions (kymograph) or strip cells, so the spectrum is the
            # column index; ``row`` is the spectral sample and is ignored.
            spectrum_idx = max(0, min(int(col), spectral_data.num_spectra - 1))
        else:
            num_cols = dims[0]  # horizontal dimension
            spectrum_idx = row * num_cols + col

        if spectrum_idx >= spectral_data.num_spectra:
            return {'error': f'Index {spectrum_idx} out of range (max: {spectral_data.num_spectra - 1})'}

        try:
            # Check if this is an integrated dataset
            is_integrated = 'intervals' in spectral_data.metadata.additional_info

            if is_integrated:
                # For integrated datasets, the structure is different:
                # Each row is an interval, each column is a spatial position
                intervals = spectral_data.metadata.additional_info.get('intervals', [])

                # X values are interval indices or interval labels
                x = list(range(len(intervals)))
                # Y values are the integrated values for this position
                y = spectral_data.spectra.iloc[:, spectrum_idx].values.tolist()

                # Create interval labels for display
                interval_labels = []
                for iv in intervals:
                    if isinstance(iv, (list, tuple)) and len(iv) >= 2:
                        interval_labels.append(f"{iv[0]:.3f}-{iv[1]:.3f}")
                    else:
                        interval_labels.append(str(iv))

                return {
                    'x': x,
                    'y': y,
                    'x_name': 'Interval Index',
                    'y_name': 'Integrated Value',
                    'title': f'{dataset_name} at ({row}, {col})',
                    'row': row,
                    'col': col,
                    'dataset': dataset_name,
                    'is_integrated': True,
                    'interval_labels': interval_labels
                }
            else:
                # Regular spectral dataset
                x = spectral_data.independent_var.tolist()
                y = spectral_data.spectra.iloc[:, spectrum_idx].values.tolist()

                return {
                    'x': x,
                    'y': y,
                    'x_name': spectral_data.independent_var_name,
                    'y_name': dataset_name,
                    'title': f'{dataset_name} at ({row}, {col})',
                    'row': row,
                    'col': col,
                    'dataset': dataset_name,
                    'is_integrated': False
                }
        except Exception as e:
            logger.error(f"Error getting spectrum from {dataset_name}: {e}")
            return {'error': str(e)}

    @Slot(int, int)
    def requestPlotAtPosition(self, row: int, col: int):
        """
        Request to plot spectrum at position for the active dataset.
        Emits openPlotWindowRequested signal with spectrum data.
        """
        if not self._active_dataset:
            logger.warning("No active dataset for spectrum plotting")
            return

        spectrum = self.getSpectrumFromDataset(self._active_dataset, row, col)
        if 'error' not in spectrum:
            self.openPlotWindowRequested.emit(self._active_dataset, [spectrum])

    @Slot(str, int, int)
    def requestPlotFromDataset(self, dataset_name: str, row: int, col: int):
        """
        Request to plot spectrum at position from a specific dataset.
        Opens a new plot window.
        """
        spectrum = self.getSpectrumFromDataset(dataset_name, row, col)
        if 'error' not in spectrum:
            self.openPlotWindowRequested.emit(dataset_name, [spectrum])

    @Slot(str, result='QVariantList')
    def getSelectedSpectraFromDataset(self, dataset_name: str) -> List[Dict]:
        """Get spectra for all selected blocks from a dataset"""
        if dataset_name not in self._linked_datasets:
            return []

        if self._canvas is None:
            return []

        selected_blocks = self._canvas.getSelectedBlocks()
        spectra = []

        for block in selected_blocks:
            row, col = block['row'], block['col']
            spectrum = self.getSpectrumFromDataset(dataset_name, row, col)
            if 'error' not in spectrum:
                spectra.append(spectrum)

        return spectra

    @Slot(str)
    def openPlotForSelectedBlocks(self, dataset_name: str):
        """Open a plot window with all selected block spectra"""
        spectra = self.getSelectedSpectraFromDataset(dataset_name)
        if spectra:
            self.openPlotWindowRequested.emit(dataset_name, spectra)
        else:
            logger.warning(f"No spectra to plot for dataset: {dataset_name}")

    @Slot('QVariantList', int, int, result='QVariantList')
    def getSpectraFromMultipleDatasets(self, dataset_names: List[str], row: int, col: int) -> List[Dict]:
        """
        Get spectra at (row, col) from multiple datasets.
        Returns list of spectrum dicts for plotting together.
        """
        spectra = []
        for name in dataset_names:
            spectrum = self.getSpectrumFromDataset(name, row, col)
            if 'error' not in spectrum:
                spectra.append(spectrum)
        return spectra

    @Slot('QVariantList', int, int)
    def requestPlotFromMultipleDatasets(self, dataset_names: List[str], row: int, col: int):
        """
        Request to plot spectra at position from multiple datasets.
        Opens a combined plot window.
        """
        spectra = self.getSpectraFromMultipleDatasets(dataset_names, row, col)
        if spectra:
            combined_name = " + ".join(dataset_names)
            self.openPlotWindowRequested.emit(combined_name, spectra)

    # =========================================================================
    # Canvas binding
    # =========================================================================

    @Slot('QVariant')
    def setCanvas(self, canvas):
        """Bind to a QMLMapCanvas instance"""
        self._canvas = canvas
        if canvas:
            # Connect canvas signals
            canvas.spectralDataRequested.connect(self._onSpectrumRequested)
            canvas.blockSelectionChanged.connect(self._onBlockSelectionChanged)
            canvas.stsMarkerClicked.connect(self._on_sts_marker_clicked)

    # =========================================================================
    # Data Loading
    # =========================================================================

    @Slot(str)
    def loadMapById(self, map_id: str):
        """Load a map that's already in memory (no disk I/O).

        Resolves the id via the injected :class:`AppBackend` and replaces the
        currently displayed map. Falls back gracefully when the map is not
        in-memory — the caller (QML) should instead emit the path-based
        ``loadMapInEditor`` signal in that case.
        """
        if self._app_backend is None:
            logger.error(
                "loadMapById called but AppBackend reference not set"
            )
            return
        mcm = self._app_backend.getInMemoryMap(map_id)
        if mcm is None:
            logger.warning("loadMapById: no in-memory map for id %r", map_id)
            return

        logger.info(f"Loading in-memory map id={map_id}")
        self._exit_line_scan_mode()
        self._multi_channel_map = mcm
        if self._canvas:
            active = self._multi_channel_map.active_channel
            if active:
                self._canvas.setMapData(active.data)
            self._push_physical_extent(mcm)
            self._push_sts_markers(mcm)
        self.mapDataChanged.emit()
        self.channelListChanged.emit()
        self.activeChannelChanged.emit(self.activeChannelName)

    # Scan-size units seen on MapMetadata, as nanometres per unit.
    _UNITS_TO_NM = {'m': 1e9, 'mm': 1e6, 'um': 1e3, 'µm': 1e3, 'nm': 1.0}

    def _push_physical_extent(self, mcm):
        """Feed the canvas the map's physical scan size so its axes read in real
        units (nm / µm) instead of pixel indices.

        Reads ``metadata.physical_size`` (y, x) and ``physical_units``. Maps
        without calibration (size missing / non-positive) revert the canvas to
        pixel-index axes.
        """
        if self._canvas is None or not hasattr(self._canvas, 'setPhysicalExtent'):
            return
        size = getattr(mcm.metadata, 'physical_size', None)   # (y, x) in units
        units = getattr(mcm.metadata, 'physical_units', 'm') or 'm'
        if (not size or size[0] is None or size[1] is None
                or size[0] <= 0 or size[1] <= 0):
            self._canvas.clearPhysicalExtent()
            return
        if units not in self._UNITS_TO_NM:
            # Unrecognised unit: show the raw numbers under their own label
            # rather than silently mis-scaling them by up to 1e9.
            self._canvas.setPhysicalExtent(float(size[1]), float(size[0]), units)
            return
        to_nm = self._UNITS_TO_NM[units]
        x_nm, y_nm = float(size[1]) * to_nm, float(size[0]) * to_nm
        disp_unit = 'nm'
        if max(x_nm, y_nm) >= 1000.0:      # switch to µm for large scan windows
            x_nm, y_nm, disp_unit = x_nm / 1000.0, y_nm / 1000.0, 'µm'
        self._canvas.setPhysicalExtent(x_nm, y_nm, disp_unit)

    def _push_sts_markers(self, mcm):
        """Show, on the canvas, where spectra were taken on this scan image.

        Reads the STS locations carried on Omicron maps
        (``metadata.extra['sts_locations']``) and converts each to a data-grid
        marker (col = STS pixel x, row = STS pixel y). Clears any prior markers
        when the map has none.
        """
        if self._canvas is None:
            return
        self._sts_selected = {}   # new map → clear the point selection
        self._sts_didv_cache = {}
        locs = []
        try:
            extra = getattr(mcm.metadata, 'extra', None) or {}
            locs = extra.get('sts_locations', []) or []
        except Exception:
            locs = []
        grid = getattr(mcm, 'shape', None)
        markers, off_grid = [], 0
        for i, L in enumerate(locs):
            px = L.get('px')
            if not px:
                continue
            if not self._px_on_grid(px, grid):
                # Recorded against a differently sized scan: drawing it would
                # put a dot off the edge of this image.
                off_grid += 1
                continue
            # ``index`` is the position in sts_locations, so a click on the dot
            # maps back to this location (and its avg_spectrum) in
            # _on_sts_marker_clicked.
            markers.append({
                'col': int(px[0]), 'row': int(px[1]),
                'label': self._sts_marker_label(L), 'index': i,
            })
        if off_grid:
            logger.warning("%d STS point(s) fall outside this %s map and were "
                           "not drawn", off_grid, "x".join(map(str, grid or ())))
        self._canvas.setStsMarkers(markers)
        self._push_sts_lines(mcm)
        self.stsAverageUpdated.emit({})   # new map → clear the inline panel

    def _push_line_scan_axes(self, spectral_data, view: str):
        """Give a kymograph real axes: distance across, bias up.

        The columns are positions along the line — in metres when the loader
        recorded them — and the rows are the spectral axis. Without this the
        cursor read-out can only report column and row numbers, which say
        nothing about where on the sample the spectrum was taken.
        """
        if self._canvas is None or not hasattr(self._canvas, 'setAxisMetadata'):
            return

        info = getattr(getattr(spectral_data, 'metadata', None),
                       'additional_info', None) or {}
        units = getattr(getattr(spectral_data, 'metadata', None), 'units', None) or {}
        meta = {}

        positions = info.get('position_m')
        if not positions:
            # The per-spectrum locations a loader records, cumulative along
            # the line (the same source the map exports use).
            entries = info.get('spectrum_meta') or []
            points = [e.get('location_m') for e in entries if (e or {}).get('location_m')]
            if len(points) == len(entries) and len(points) > 1:
                arr = np.asarray(points, dtype=float)
                steps = np.hypot(np.diff(arr[:, 0]), np.diff(arr[:, 1]))
                positions = np.concatenate([[0.0], np.cumsum(steps)]).tolist()

        if positions and len(positions) > 1 and positions[-1] > 0:
            span = float(positions[-1]) - float(positions[0])
            n = len(positions)
            meta.update({'x_size': span * n / max(1, n - 1),
                         'x_unit': 'm', 'x_offset': float(positions[0])})

        if view == 'kymograph':
            axis = np.asarray(spectral_data.independent_var, dtype=float)
            if axis.size > 1:
                step = (axis[-1] - axis[0]) / (axis.size - 1)
                meta.update({'y_size': float(axis[-1] - axis[0] + step),
                             'y_unit': str(units.get('independent') or 'V'),
                             'y_offset': float(axis[0] - step / 2.0)})

        self._canvas.setAxisMetadata(meta)

    @staticmethod
    def _sts_marker_label(location: dict) -> str:
        """Label for one STS dot on a scan image.

        A point in a line scan reads ``203(01)``: the session-wide index it is
        known by everywhere else, then its position along its own line. On a
        62-point line the absolute indices alone say nothing about where along
        the line a dot sits, and they no longer match the ``P01``-style column
        names of the line's own dataset.
        """
        index = location.get('point_index')
        if index is None:
            return ''
        position = location.get('line_pos')
        if location.get('line_scan_id') is None or position is None:
            return str(index)
        return f"{index}({int(position) + 1:02d})"

    def _push_sts_lines(self, mcm):
        """Outline and tag each line scan taken on this scan image.

        A line scan is dozens of dots that look no different from isolated
        points; the outline plus its tag ('line1 · 57pts ×3 · pt20→pt76') is
        what makes 'which line was taken where' readable off the map.
        """
        if self._canvas is None or not hasattr(self._canvas, 'setStsLines'):
            return
        try:
            extra = getattr(mcm.metadata, 'extra', None) or {}
            lines = extra.get('sts_line_scans', []) or []
        except Exception:
            lines = []

        grid = getattr(mcm, 'shape', None)
        overlays = []
        for ls in lines:
            path = [pt for pt in (ls.get('px_path') or []) if pt]
            on_grid = [pt for pt in path if self._px_on_grid(pt, grid)]
            if len(on_grid) < len(path):
                logger.warning("%s: %d of %d points fall outside this map; "
                               "outlining only the part that is on it",
                               ls.get('label', 'line'),
                               len(path) - len(on_grid), len(path))
            if len(on_grid) < 2:
                # Nothing (or a single point) of this line is on this scan —
                # an outline would be a stray mark at the edge.
                continue
            overlays.append({
                'label': self._line_scan_tag(ls),
                # Canvas markers are (col, row) = (pixel x, pixel y).
                'path': [{'col': int(p[0]), 'row': int(p[1])} for p in on_grid],
            })
        self._canvas.setStsLines(overlays)

    @staticmethod
    def _px_on_grid(px, grid) -> bool:
        """Is this (x, y) pixel inside a (rows, cols) map?

        Half a pixel of tolerance, so a point measured on the boundary is not
        thrown away by rounding. Without a known grid nothing is rejected.
        """
        if not grid or len(grid) < 2:
            return True
        try:
            rows, cols = int(grid[0]), int(grid[1])
            x, y = float(px[0]), float(px[1])
        except (TypeError, ValueError, IndexError):
            return True
        if rows <= 0 or cols <= 0:
            return True
        return -0.5 <= x <= cols - 0.5 and -0.5 <= y <= rows - 0.5

    @staticmethod
    def _line_scan_tag(ls: dict) -> str:
        """Short label for a line outline, matching the dataset name."""
        parts = [str(ls.get('label') or f"line{ls.get('id', '?')}")]
        n = ls.get('n_points')
        if n:
            parts.append(f"{n}pts")
        reps = ls.get('reps')
        if reps:
            parts.append(f"×{reps}")
        first, last = ls.get('point_first'), ls.get('point_last')
        if first is not None and last is not None:
            parts.append(f"pt{first}→pt{last}")
        tag = " · ".join(parts)
        # A single-sweep pass over the same path is hidden rather than drawn
        # twice; say it is there so it isn't mistaken for missing data.
        presweeps = int(ls.get('presweeps') or 0)
        if presweeps:
            tag += f"  (+{presweeps} single sweep{'s' if presweeps > 1 else ''})"
        return tag

    @staticmethod
    def _loc_avg_spectra(loc: dict):
        """Per-sweep averages for an STS location, tolerant of the legacy schema.

        New Omicron maps store ``avg_spectra`` = {V, Mixed, Forward, Backward}.
        Projects saved before the multi-sweep rewrite stored a single
        ``avg_spectrum`` = {V, y}; upgrade those to a Mixed-only spectrum so old
        .hrt files still click-to-plot (Forward/Backward simply won't exist).
        """
        avg = loc.get('avg_spectra')
        if avg and avg.get('Mixed'):
            return avg
        legacy = loc.get('avg_spectrum')
        if legacy and legacy.get('y'):
            return {'V': legacy.get('V'), 'Mixed': legacy.get('y'),
                    'Forward': None, 'Backward': None}
        return None

    @Slot(int)
    def _on_sts_marker_clicked(self, index: int):
        """Toggle the clicked STS point in the plot.

        Clicking a dot adds its average spectrum to the plot (and highlights the
        dot); clicking it again removes it. All currently-selected points are
        overlaid in one graph window, so several points can be compared.
        """
        mcm = self._multi_channel_map
        if mcm is None:
            return
        try:
            locs = (getattr(mcm.metadata, 'extra', None) or {}).get(
                'sts_locations', []) or []
        except Exception:
            return
        if not (0 <= index < len(locs)):
            return
        loc = locs[index]
        avg = self._loc_avg_spectra(loc)
        if not avg or not avg.get('Mixed'):
            logger.info("STS dot %s has no stored spectra to plot", index)
            return

        pi = loc.get('point_index', index)
        sel = getattr(self, '_sts_selected', None)
        if sel is None:
            sel = {}
            self._sts_selected = sel
        deselected = pi in sel
        if deselected:
            del sel[pi]                       # toggle off
        else:
            sel[pi] = avg                     # {'V', 'Mixed', 'Forward', 'Backward'}

        # Selecting appends only the new point's curves; deselecting is the
        # only case that has to resend the window's whole contents. Rebuilding
        # everything on every click made the Nth selection cost N curve
        # conversions over the QML bridge — quadratic, and the reason a long
        # selection ground to a halt.
        show_didv = self._is_stm_source(mcm)
        if deselected:
            spectra, didv = [], []
            for p_i in sel:
                spectra.extend(self._point_curves(p_i, sel[p_i]))
                didv.extend(self._point_didv(p_i, sel[p_i]))
            self.openPlotWindowRequested.emit("STS points", spectra)
            if show_didv:
                self.openPlotWindowRequested.emit("STS points · dI/dV", didv)
        else:
            spectra = self._point_curves(pi, avg)
            if spectra:
                self.appendPlotCurvesRequested.emit("STS points", spectra)
            if show_didv:
                didv = self._point_didv(pi, avg)
                if didv:
                    self.appendPlotCurvesRequested.emit(
                        "STS points · dI/dV", didv)

        # Highlight the selected dots on the canvas (instant click feedback).
        if self._canvas is not None:
            selected_idx = [i for i, L in enumerate(locs)
                            if L.get('point_index', i) in sel]
            self._canvas.setSelectedStsMarkers(selected_idx)

        # Push the average (mixed) of every selected dot to the inline panel.
        self.stsAverageUpdated.emit(self._sts_average_result(sel))

    @staticmethod
    def _is_stm_source(mcm) -> bool:
        """True when this map came from an STM/STS loader.

        Projects saved before the marker was stamped fall back to the
        instrument name, so they keep the dI/dV plot.
        """
        try:
            extra = getattr(mcm.metadata, 'extra', None) or {}
        except Exception:
            extra = {}
        if str(extra.get('sts_technique', '')).upper() == 'STM':
            return True
        instrument = str(getattr(getattr(mcm, 'metadata', None),
                                 'instrument', '') or '').lower()
        return any(key in instrument for key in ('matrix', 'omicron', 'stm'))

    @staticmethod
    def _point_curves(p_i, avg: dict) -> list:
        """Plot payload for one STS point: its two sweep directions.

        ONE window holds both directions — forward and backward of the same
        point belong side by side, that comparison is the whole reason both
        are kept. Mixed is plotted only when the directions were not recorded
        separately, otherwise it is just their mean redrawn.
        """
        directions = [(d, avg.get(d)) for d in ('Forward', 'Backward')]
        directions = [(d, y) for d, y in directions if y is not None]
        if not directions:
            directions = [('Mixed', avg.get('Mixed'))] if avg.get('Mixed') else []
        return [{
            'x': avg.get('V'), 'y': y,
            'title': f"Point {p_i} · {label}",
            'x_name': 'V', 'y_name': 'Current',
        } for label, y in directions]

    def _point_didv(self, p_i, avg: dict) -> list:
        """dI/dV of one point's averaged sweep, computed once per point.

        Memoised: a deselect rebuilds the window from every remaining point,
        and differentiating them all again on each click is work already done.
        """
        cache = getattr(self, '_sts_didv_cache', None)
        if cache is None:
            cache = {}
            self._sts_didv_cache = cache
        if p_i not in cache:
            cache[p_i] = self._didv_spectra({p_i: avg})
        return cache[p_i]

    @staticmethod
    def _didv_spectra(sel: dict) -> list:
        """dI/dV of each selected point's averaged sweep.

        Averaged over the directions that exist, then differentiated — the
        average of many repetitions is what the derivative should be taken
        of, not one noisy sweep.
        """
        out = []
        for p_i, a in sel.items():
            v = a.get('V')
            if not v:
                continue
            x = np.asarray(v, dtype=float)
            stack = [np.asarray(a[d], dtype=float)
                     for d in ('Forward', 'Backward', 'Mixed')
                     if a.get(d) is not None
                     and len(a[d]) == x.size]
            # Prefer the two directions; fall back to Mixed alone.
            directional = stack[:2] if len(stack) > 2 else stack
            if not directional or x.size < 2:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                mean_i = np.nanmean(np.vstack(directional), axis=0)
                didv = np.gradient(mean_i, x)
            out.append({
                'x': x.tolist(), 'y': np.nan_to_num(didv, nan=0.0).tolist(),
                'title': f"Point {p_i} · dI/dV",
                'x_name': 'V', 'y_name': 'dI/dV',
            })
        return out

    def _sts_average_result(self, sel: dict) -> Dict:
        """Build the inline-panel payload: NaN-aware mean of the selected dots'
        Mixed spectra. Returns {} when nothing usable is selected."""
        if not sel:
            return {}
        x_ref = None
        stack = []
        for a in sel.values():
            y = a.get('Mixed')
            v = a.get('V')
            if y is None or v is None:
                continue
            arr = np.asarray(y, dtype=float)
            if x_ref is None:
                x_ref = np.asarray(v, dtype=float)
            # Only stack rows matching the reference length (share the V grid).
            if arr.shape == x_ref.shape:
                stack.append(arr)
        if not stack or x_ref is None:
            return {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            mean_y = np.nanmean(np.vstack(stack), axis=0)
        n = len(stack)
        return {
            'x': x_ref.tolist(),
            'y': mean_y.tolist(),
            'title': f"Avg of {n} STS point{'s' if n != 1 else ''} · Mixed",
            'x_name': 'V', 'y_name': 'Current',
            'point_count': n,
        }

    @Slot(str)
    def loadMapFromFile(self, file_path: str):
        """Load map data from a file (TIFF, GSF, etc.)"""
        try:
            path = Path(file_path.replace("file://", ""))
            logger.info(f"Loading map from: {path}")

            self._exit_line_scan_mode()
            # Create new multi-channel map
            self._multi_channel_map = MultiChannelMap()

            # Load based on extension
            if path.suffix.lower() in ['.tif', '.tiff']:
                import tifffile
                data = tifffile.imread(str(path))

                if data.ndim == 2:
                    # Single channel
                    self._multi_channel_map.add_channel(
                        path.stem, data, ChannelType.HEIGHT
                    )
                elif data.ndim == 3:
                    # Multi-page TIFF - each page is a channel
                    for i in range(data.shape[0]):
                        self._multi_channel_map.add_channel(
                            f"Channel_{i}", data[i], ChannelType.CUSTOM
                        )

            elif path.suffix.lower() == '.npy':
                data = np.load(str(path))
                self._multi_channel_map.add_channel(
                    path.stem, data, ChannelType.CUSTOM
                )

            else:
                raise ValueError(f"Unsupported file format: {path.suffix}")

            # Update canvas
            if self._canvas:
                active = self._multi_channel_map.active_channel
                if active:
                    self._canvas.setMapData(active.data)

            self.mapDataChanged.emit()
            self.channelListChanged.emit()
            self.activeChannelChanged.emit(self.activeChannelName)

            logger.info(f"Loaded map: {self._multi_channel_map}")

        except Exception as e:
            logger.error(f"Failed to load map: {e}")
            self.processingFinished.emit("load", False, str(e))

    def loadTopographyWithOverlay(self, topo_data: np.ndarray,
                                  map_geometry: dict, topo_geometry: dict,
                                  channel_name: str = "Topography"):
        """
        Load topography as a map channel with an STS grid region overlay.

        Parameters
        ----------
        topo_data : np.ndarray
            2D topography array
        map_geometry : dict
            STS grid bounds: x_start, y_start, x_end, y_end (meters)
        topo_geometry : dict
            Topography scan bounds: x_min, x_max, y_min, y_max (meters)
        channel_name : str
            Name for the topography channel
        """
        if self._multi_channel_map is None:
            self._multi_channel_map = MultiChannelMap()

        self._multi_channel_map.add_channel(
            channel_name, topo_data, ChannelType.HEIGHT, replace=True
        )

        if self._canvas:
            self._canvas.setMapData(topo_data)

            # Compute fractional coordinates for the STS region rectangle
            topo_xrange = topo_geometry['x_max'] - topo_geometry['x_min']
            topo_yrange = topo_geometry['y_max'] - topo_geometry['y_min']

            if topo_xrange > 0 and topo_yrange > 0:
                # Map0 coordinates to fractional position on topography
                fx0 = (map_geometry['x_start'] - topo_geometry['x_min']) / topo_xrange
                fy0 = (map_geometry['y_start'] - topo_geometry['y_min']) / topo_yrange
                fx1 = (map_geometry['x_end'] - topo_geometry['x_min']) / topo_xrange
                fy1 = (map_geometry['y_end'] - topo_geometry['y_min']) / topo_yrange

                # Invert Y axis (image convention: top=0, bottom=1)
                fy0 = 1.0 - fy0
                fy1 = 1.0 - fy1

                self._canvas.setStsRegionRect(fx0, fy0, fx1, fy1)
                logger.info(
                    f"STS grid overlay set: frac ({fx0:.3f},{fy0:.3f})-({fx1:.3f},{fy1:.3f})"
                )

        self.mapDataChanged.emit()
        self.channelListChanged.emit()
        self.activeChannelChanged.emit(channel_name)

    def setMultiChannelMap(self, mcmap: MultiChannelMap):
        """Set map data programmatically from Python"""
        self._exit_line_scan_mode()
        self._multi_channel_map = mcmap

        # Update canvas
        if self._canvas and mcmap.active_channel:
            self._canvas.setMapData(mcmap.active_channel.data)
            # Refresh the axis calibration too, so a map set this way doesn't
            # inherit the previously loaded map's physical extent.
            self._push_physical_extent(mcmap)

            # Link spectral data if available
            if mcmap.has_spectral_link:
                self._canvas.linkSpectralCube(
                    mcmap._spectral_cube,
                    mcmap._independent_var,
                    mcmap._independent_var_name
                )

        self.mapDataChanged.emit()
        self.channelListChanged.emit()
        self.activeChannelChanged.emit(self.activeChannelName)
        if mcmap.has_spectral_link:
            self.spectralDataChanged.emit()

    def setMapDataFromArray(self, data: np.ndarray, name: str = "Map"):
        """Set map data from numpy array"""
        if self._multi_channel_map is None:
            self._multi_channel_map = MultiChannelMap()

        self._multi_channel_map.add_channel(name, data, replace=True)

        if self._canvas:
            self._canvas.setMapData(data)

        self.mapDataChanged.emit()
        self.channelListChanged.emit()
        self.activeChannelChanged.emit(name)

    # =========================================================================
    # Channel Management
    # =========================================================================

    @Slot(str)
    def setActiveChannel(self, channel_name: str):
        """Set the active channel for display"""
        if self._multi_channel_map is None:
            return

        try:
            self._multi_channel_map.set_active_channel(channel_name)
            active = self._multi_channel_map.active_channel

            if self._canvas and active:
                self._canvas.setMapData(active.data)

            self.activeChannelChanged.emit(channel_name)

        except KeyError as e:
            logger.warning(f"Channel not found: {e}")

    @Slot(str, result='QVariantMap')
    def getChannelStatistics(self, channel_name: str) -> Dict:
        """Get statistics for a channel"""
        if self._multi_channel_map is None:
            return {}

        try:
            channel = self._multi_channel_map.get_channel(channel_name)
            stats = channel.get_statistics()
            self.statisticsUpdated.emit(stats)
            return stats
        except KeyError:
            return {}

    @Slot(result='QVariantMap')
    def getActiveChannelStatistics(self) -> Dict:
        """Get statistics for the active channel"""
        if self._multi_channel_map is None or self._multi_channel_map.active_channel is None:
            return {}
        return self._multi_channel_map.active_channel.get_statistics()

    # =========================================================================
    # Spectral-Spatial Linking (TRANS_v3 core feature)
    # =========================================================================

    def linkSpectralData(self, spectral_data: SpectralData, var_name: str = None):
        """
        Link SpectralData for spatial-spectral reconstruction.
        This enables clicking on the map to show the spectrum at that position.
        """
        if self._multi_channel_map is None:
            logger.warning("No map data to link spectral data to")
            return

        self._multi_channel_map.link_spectral_data(spectral_data, var_name)

        if self._canvas:
            self._canvas.linkSpectralCube(
                self._multi_channel_map._spectral_cube,
                self._multi_channel_map._independent_var,
                self._multi_channel_map._independent_var_name
            )

        self.spectralDataChanged.emit()
        logger.info("Linked spectral data for spatial reconstruction")

    def linkSpectralCube(self, cube: np.ndarray, independent_var: np.ndarray,
                         var_name: str = "x"):
        """Link a spectral cube directly"""
        if self._multi_channel_map is None:
            logger.warning("No map data to link spectral cube to")
            return

        self._multi_channel_map.link_spectral_cube(cube, independent_var, var_name)

        if self._canvas:
            self._canvas.linkSpectralCube(cube, independent_var, var_name)

        self.spectralDataChanged.emit()

    @Slot(int, int, result='QVariantMap')
    def getSpectrumAt(self, row: int, col: int) -> Dict:
        """Get spectrum at a spatial position"""
        if self._multi_channel_map is None or not self._multi_channel_map.has_spectral_link:
            return {'error': 'No spectral data linked'}

        try:
            x, y = self._multi_channel_map.get_spectrum_at(row, col)
            return {
                'x': x.tolist(),
                'y': y.tolist(),
                'x_name': self._multi_channel_map.independent_var_name,
                'y_name': 'Intensity',
                'title': f'Spectrum at ({row}, {col})'
            }
        except Exception as e:
            return {'error': str(e)}

    @Slot(result='QVariantMap')
    def getAverageSpectrumFromSelection(self) -> Dict:
        """Get average spectrum from selected blocks"""
        if self._canvas is None:
            return {'error': 'No canvas'}

        return self._canvas.getAverageSpectrumFromSelection()

    # =========================================================================
    # Block Selection (TRANS_v3 style)
    # =========================================================================

    @Slot()
    def clearSelection(self):
        """Clear every selection on the map.

        "Clear" means nothing stays selected: the block selection AND the
        selected STS marker dots, whose highlight and averaged spectrum
        otherwise survived the button and left the inline panel showing an
        average of points the user had just deselected.
        """
        if self._canvas:
            self._canvas.clearBlockSelection()
            self._canvas.setSelectedStsMarkers([])
        self._sts_selected = {}
        self._sts_didv_cache = {}
        self.stsAverageUpdated.emit({})
        # The point plots showed the now-deselected spectra otherwise.
        self.openPlotWindowRequested.emit("STS points", [])
        self.openPlotWindowRequested.emit("STS points · dI/dV", [])

    @Slot()
    def selectAllBlocks(self):
        """Select all blocks"""
        if self._canvas:
            self._canvas.selectAllBlocks()

    @Slot(result='QVariantList')
    def getSelectedBlocks(self) -> List[Dict]:
        """Get list of selected blocks"""
        if self._canvas:
            return self._canvas.getSelectedBlocks()
        return []

    @Slot(result=int)
    def getSelectedBlockCount(self) -> int:
        """Get number of selected blocks"""
        if self._canvas:
            return self._canvas.getSelectedBlockCount()
        return 0

    def getSelectionMask(self) -> np.ndarray:
        """Get 2D boolean mask from selection"""
        if self._canvas:
            return self._canvas.getSelectionMask()
        return np.array([])

    def _onBlockSelectionChanged(self):
        """Handle block selection changes from canvas"""
        count = self.getSelectedBlockCount()
        self.selectionChanged.emit(count)

    def _onSpectrumRequested(self, row: int, col: int):
        """Handle spectrum request from canvas click"""
        # This signal can be connected in QML to update a spectrum viewer
        pass

    # =========================================================================
    # Discretization Grid (Hyperspectral tab integration)
    # =========================================================================

    @Slot(int, int)
    def setDiscretizationGrid(self, block_h: int, block_v: int):
        """
        Set up discretization grid on the map canvas.
        Enables block selection mode with grid overlay.

        Parameters:
            block_h: Horizontal block size (in original pixels)
            block_v: Vertical block size (in original pixels)
        """
        if self._canvas is None or self._multi_channel_map is None:
            return

        rows = self._multi_channel_map.shape[0] if self._multi_channel_map.shape else 0
        cols = self._multi_channel_map.shape[1] if self._multi_channel_map.shape else 0

        if rows == 0 or cols == 0:
            return

        # Configure canvas grid overlay and block selection
        self._canvas.setGridBlockSize(block_h, block_v)
        self._canvas.setTool("block_select")

        import math
        grid_rows = math.ceil(rows / block_v)
        grid_cols = math.ceil(cols / block_h)

        self.discretizationReady.emit(grid_rows, grid_cols)
        logger.info(f"Discretization grid set: {block_h}x{block_v} blocks, "
                     f"grid {grid_cols}x{grid_rows}")

    @Slot()
    def invertSelection(self):
        """Invert the set of selected blocks"""
        if self._canvas is None or self._canvas._map_data is None:
            return

        rows = self._canvas._map_data.shape[0]
        cols = self._canvas._map_data.shape[1]

        # If grid overlay is active, use grid block coordinates. Must match
        # the canvas's own block/pixel decision (block_h > 1 OR block_v > 1) —
        # checking only block_h treated a 1×N (tall) grid as pixel coords and
        # inverted the wrong set.
        if self._canvas._show_grid_overlay and (
            self._canvas._grid_block_h > 1 or self._canvas._grid_block_v > 1
        ):
            import math
            grid_rows = math.ceil(rows / self._canvas._grid_block_v)
            grid_cols = math.ceil(cols / self._canvas._grid_block_h)
            all_blocks = {(r, c) for r in range(grid_rows) for c in range(grid_cols)}
        else:
            all_blocks = {(r, c) for r in range(rows) for c in range(cols)}

        self._canvas._selected_blocks = all_blocks - self._canvas._selected_blocks
        self._canvas.blockSelectionChanged.emit()
        self._canvas.update()

    @Slot(result='QVariantMap')
    def getAverageSpectrumForSelectedBlocks(self) -> Dict:
        """
        Average spectra from all selected blocks in the active linked dataset.
        Returns {x, y, x_name, y_name, title, block_count}.
        """
        if not self._active_dataset or self._active_dataset not in self._linked_datasets:
            return {'error': 'No active dataset'}

        if self._canvas is None:
            return {'error': 'No canvas'}

        selected = self._canvas._selected_blocks
        if not selected:
            return {'error': 'No blocks selected'}

        spectral_data = self._linked_datasets[self._active_dataset]
        dims = spectral_data.metadata.dimensions
        num_cols = dims[0]  # horizontal dimension

        accumulated = None
        count = 0

        for row, col in selected:
            # If grid overlay active, translate grid block to original pixel
            # For grid blocks, we average all spectra within the block.
            # Guard must match the canvas (block_h > 1 OR block_v > 1): with a
            # 1×N grid the canvas stores grid-block coords, so the old
            # block_h-only check mis-read them as pixel coords and averaged
            # the wrong (and wrong number of) spectra.
            if self._canvas._show_grid_overlay and (
                self._canvas._grid_block_h > 1 or self._canvas._grid_block_v > 1
            ):
                block_h = self._canvas._grid_block_h
                block_v = self._canvas._grid_block_v
                orig_rows = self._canvas._map_data.shape[0] if self._canvas._map_data is not None else 0
                orig_cols = self._canvas._map_data.shape[1] if self._canvas._map_data is not None else 0

                for pr in range(row * block_v, min((row + 1) * block_v, orig_rows)):
                    for pc in range(col * block_h, min((col + 1) * block_h, orig_cols)):
                        idx = pr * num_cols + pc
                        if idx < spectral_data.num_spectra:
                            y_vals = spectral_data.spectra.iloc[:, idx].values
                            if not np.all(np.isnan(y_vals)):
                                if accumulated is None:
                                    accumulated = np.zeros_like(y_vals, dtype=float)
                                accumulated += y_vals
                                count += 1
            else:
                idx = row * num_cols + col
                if idx < spectral_data.num_spectra:
                    y_vals = spectral_data.spectra.iloc[:, idx].values
                    if not np.all(np.isnan(y_vals)):
                        if accumulated is None:
                            accumulated = np.zeros_like(y_vals, dtype=float)
                        accumulated += y_vals
                        count += 1

        if count == 0 or accumulated is None:
            return {'error': 'No valid spectra in selection'}

        averaged = accumulated / count
        x = spectral_data.independent_var.tolist()

        return {
            'x': x,
            'y': averaged.tolist(),
            'x_name': spectral_data.independent_var_name,
            'y_name': 'Intensity',
            'title': f'Average spectrum ({count} spectra from {len(selected)} blocks)',
            'block_count': count
        }

    @Slot(str, result='QVariantMap')
    def exportSelectionSpectra(self, dataset_name: str) -> Dict:
        """
        Get all individual spectra for selected blocks, ready for CSV export.
        Returns {x, x_name, columns: [[y1], [y2], ...], labels: ["Block(r,c)", ...]}.
        """
        if dataset_name not in self._linked_datasets:
            return {'error': f'Dataset not found: {dataset_name}'}

        if self._canvas is None:
            return {'error': 'No canvas'}

        selected = sorted(self._canvas._selected_blocks)
        if not selected:
            return {'error': 'No blocks selected'}

        spectral_data = self._linked_datasets[dataset_name]
        dims = spectral_data.metadata.dimensions
        num_cols = dims[0]

        x = spectral_data.independent_var.tolist()
        columns = []
        labels = []

        for row, col in selected:
            idx = row * num_cols + col
            if idx < spectral_data.num_spectra:
                y_vals = spectral_data.spectra.iloc[:, idx].values.tolist()
                columns.append(y_vals)
                labels.append(f"Block({row},{col})")

        return {
            'x': x,
            'x_name': spectral_data.independent_var_name,
            'columns': columns,
            'labels': labels
        }

    @Slot('QVariant')
    def autoLinkMatchingDatasets(self, app_backend):
        """
        Auto-link datasets whose spatial dimensions match the current map.
        Compare map dimensions to each dataset's metadata.dimensions.
        """
        if self._multi_channel_map is None or self._multi_channel_map.shape is None:
            return

        map_rows, map_cols = self._multi_channel_map.shape
        map_total = map_rows * map_cols

        if not hasattr(app_backend, '_datasets'):
            return

        linked_count = 0
        for name, dataset in app_backend._datasets.items():
            if name in self._linked_datasets:
                continue  # Already linked

            if hasattr(dataset, 'metadata') and hasattr(dataset.metadata, 'dimensions'):
                dims = dataset.metadata.dimensions
                if dims and len(dims) >= 2:
                    ds_total = dims[0] * dims[1]
                    if ds_total == map_total:
                        self.linkDataset(name, dataset)
                        linked_count += 1
                        logger.info(f"Auto-linked dataset '{name}' "
                                    f"(dims {dims[0]}x{dims[1]} matches map {map_cols}x{map_rows})")

        if linked_count > 0:
            self.linkedDatasetsChanged.emit()

    # =========================================================================
    # Processing Operations
    # =========================================================================

    @Slot(str, 'QVariantMap')
    def applyProcessing(self, operation: str, params: Dict):
        """Apply a processing operation to the active channel"""
        if self._multi_channel_map is None or self._multi_channel_map.active_channel is None:
            self.processingFinished.emit(operation, False, "No data loaded")
            return

        self.processingStarted.emit(operation)

        try:
            channel = self._multi_channel_map.active_channel
            data = channel.data.copy()

            if operation == "gaussian_filter":
                from scipy.ndimage import gaussian_filter
                sigma = params.get('sigma', 1.0)
                data = gaussian_filter(data, sigma=sigma)

            elif operation == "median_filter":
                from scipy.ndimage import median_filter
                size = params.get('size', 3)
                data = median_filter(data, size=size)

            elif operation == "plane_level":
                # Least-squares plane (order-1 polynomial), NaN-aware.
                from src.processing.plane_correction import polynomial_level
                data = polynomial_level(data, order=1)

            elif operation == "poly_level":
                # Polynomial plane correction of configurable order.
                from src.processing.plane_correction import polynomial_level
                data = polynomial_level(data, order=int(params.get('order', 2)))

            elif operation == "facet_level":
                # Facet reorientation: level the dominant facet to horizontal.
                from src.processing.plane_correction import facet_level
                data = facet_level(
                    data, iterations=int(params.get('iterations', 6)))

            elif operation == "row_align":
                # Subtract row medians
                for i in range(data.shape[0]):
                    data[i] -= np.nanmedian(data[i])

            elif operation == "normalize":
                vmin = np.nanmin(data)
                vmax = np.nanmax(data)
                if vmax > vmin:
                    data = (data - vmin) / (vmax - vmin)

            else:
                self.processingFinished.emit(operation, False, f"Unknown operation: {operation}")
                return

            # Update channel data
            channel.data = data
            channel.add_history(operation, params)

            # Update canvas
            if self._canvas:
                self._canvas.setMapData(data)

            self.processingFinished.emit(operation, True, "Success")
            self.mapDataChanged.emit()

        except Exception as e:
            logger.error(f"Processing failed: {e}")
            self.processingFinished.emit(operation, False, str(e))

    # =========================================================================
    # Export
    # =========================================================================

    def _channel_pixel_scale(self, data_shape):
        """Physical pixel size ``(dx, dy, unit)`` for the current map, or Nones.

        Derives per-pixel size from the map's ``physical_size`` (y, x) and the
        channel's pixel dimensions, so exported TIFFs carry a real spatial
        scale instead of pixel indices.
        """
        meta = getattr(self._multi_channel_map, 'metadata', None)
        size = getattr(meta, 'physical_size', None)   # (y, x) in units
        unit = getattr(meta, 'physical_units', 'nm') or 'nm'
        if (not size or size[0] is None or size[1] is None
                or size[0] <= 0 or size[1] <= 0):
            return None, None, None
        rows, cols = data_shape
        if not rows or not cols:
            return None, None, None
        return float(size[1]) / cols, float(size[0]) / rows, unit

    @Slot(str, str)
    def exportChannel(self, channel_name: str, file_path: str):
        """Export a channel to file (TIFF and CSV formats only).

        TIFFs keep the real float32 values and embed the physical pixel scale
        plus an ImageJ display range, so they open calibrated and with contrast
        (not black) in Fiji / Gwyddion.
        """
        if self._multi_channel_map is None:
            return

        def _write_tiff(target: Path, arr: np.ndarray):
            import tifffile
            from src.utils.tiff_io import imagej_tiff_kwargs
            data = arr.astype(np.float32)
            dx, dy, unit = self._channel_pixel_scale(data.shape)
            tifffile.imwrite(str(target), data,
                             **imagej_tiff_kwargs(data, dx=dx, dy=dy, unit=unit))

        try:
            path = Path(file_path.replace("file://", ""))
            channel = self._multi_channel_map.get_channel(channel_name)

            if path.suffix.lower() in ['.tif', '.tiff']:
                _write_tiff(path, channel.data)
            elif path.suffix.lower() == '.csv':
                np.savetxt(str(path), channel.data, delimiter=',', fmt='%.6e')
            elif path.suffix.lower() == '.png':
                # PNG format is no longer supported - save as TIFF instead
                logger.warning(f"PNG format no longer supported. Saving as TIFF instead.")
                path = path.with_suffix('.tiff')
                _write_tiff(path, channel.data)
            else:
                logger.warning(f"Unsupported format {path.suffix}. Use .tiff or .csv")
                return

            logger.info(f"Exported {channel_name} to {path}")

        except Exception as e:
            logger.error(f"Export failed: {e}")

    @Slot(str, result='QVariantMap')
    def computeIntegratedMap(self, range_str: str) -> Dict:
        """
        Compute integrated intensity map from spectral data.

        Parameters:
            range_str: "start,end" string for integration range
        """
        if self._multi_channel_map is None or not self._multi_channel_map.has_spectral_link:
            return {'error': 'No spectral data linked'}

        try:
            parts = range_str.split(',')
            start_val = float(parts[0])
            end_val = float(parts[1])

            channel = self._multi_channel_map.compute_integrated_map(
                start_val=start_val, end_val=end_val
            )

            # Add to map
            self._multi_channel_map.channels[channel.name] = channel

            self.channelListChanged.emit()

            return {
                'channel_name': channel.name,
                'success': True
            }

        except Exception as e:
            return {'error': str(e)}

    # =========================================================================
    # Profile Extraction
    # =========================================================================

    @Slot(int, int, int, int, result='QVariantMap')
    def extractProfile(self, start_row: int, start_col: int,
                       end_row: int, end_col: int) -> Dict:
        """
        Extract a line profile from the active channel.

        Parameters:
            start_row, start_col: Start position
            end_row, end_col: End position

        Returns:
            Dict with 'distance' and 'values' arrays, plus 'stats'
        """
        if self._multi_channel_map is None or self._multi_channel_map.active_channel is None:
            return {'error': 'No data loaded'}

        try:
            channel = self._multi_channel_map.active_channel
            distance, values = channel.extract_profile(
                start=(start_row, start_col),
                end=(end_row, end_col)
            )

            # Compute statistics
            stats = {
                'min': float(np.nanmin(values)),
                'max': float(np.nanmax(values)),
                'mean': float(np.nanmean(values)),
                'std': float(np.nanstd(values)),
                'length': len(values)
            }

            return {
                'distance': distance.tolist(),
                'values': values.tolist(),
                'stats': stats,
                'start': {'row': start_row, 'col': start_col},
                'end': {'row': end_row, 'col': end_col}
            }

        except Exception as e:
            logger.error(f"Profile extraction failed: {e}")
            return {'error': str(e)}

    # =========================================================================
    # State Persistence (for project save/load)
    # =========================================================================

    @Slot(result='QVariantMap')
    def getState(self) -> Dict:
        """
        Get the current state of the map editor for persistence.
        This allows restoring the map editor when loading a project.

        Returns:
            Dict with map_path, active_channel, linked_datasets (names only)
        """
        # Get active channel from the map object, not the cached property
        active_channel = ''
        if self._multi_channel_map is not None:
            active_channel = self._multi_channel_map.active_channel_name or ''

        state = {
            'has_map': self._multi_channel_map is not None,
            'map_path': '',
            'active_channel': active_channel,
            'linked_dataset_names': list(self._linked_datasets.keys()),
            'active_dataset': self._active_dataset or ''
        }

        # Get map path if available
        if self._multi_channel_map is not None:
            metadata = self._multi_channel_map.metadata
            if metadata and hasattr(metadata, 'source_path'):
                state['map_path'] = str(metadata.source_path) if metadata.source_path else ''

        return state

    @Slot('QVariantMap')
    def restoreState(self, state: Dict):
        """
        Restore the map editor state from a saved state dictionary.
        The actual map data and linked datasets must be loaded separately.

        Args:
            state: Dict from getState()
        """
        if not state:
            return

        # Restore active channel if we have map data
        if self._multi_channel_map is not None:
            active_channel = state.get('active_channel', '')
            if active_channel and active_channel in self._multi_channel_map.channel_names:
                self.setActiveChannel(active_channel)

        # Restore active dataset selection
        active_ds = state.get('active_dataset', '')
        if active_ds and active_ds in self._linked_datasets:
            self._active_dataset = active_ds
            self.linkedDatasetsChanged.emit()

        logger.info(f"Map editor state restored: {state}")
