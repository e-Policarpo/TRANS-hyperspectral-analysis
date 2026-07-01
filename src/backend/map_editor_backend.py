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

    # =========================================================================
    # Dataset Linking for Spectrum Viewing
    # =========================================================================

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

        self.linkedDatasetsChanged.emit()
        logger.info(f"Linked dataset '{name}' with {spectral_data.num_spectra} spectra")

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
            self._push_sts_markers(mcm)
        self.mapDataChanged.emit()
        self.channelListChanged.emit()
        self.activeChannelChanged.emit(self.activeChannelName)

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
        locs = []
        try:
            extra = getattr(mcm.metadata, 'extra', None) or {}
            locs = extra.get('sts_locations', []) or []
        except Exception:
            locs = []
        markers = []
        for i, L in enumerate(locs):
            px = L.get('px')
            if not px:
                continue
            # ``index`` is the position in sts_locations, so a click on the dot
            # maps back to this location (and its avg_spectrum) in
            # _on_sts_marker_clicked.
            markers.append({
                'col': int(px[0]), 'row': int(px[1]),
                'label': str(L.get('point_index', '')), 'index': i,
            })
        self._canvas.setStsMarkers(markers)

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
        avg = loc.get('avg_spectrum')
        if not avg or not avg.get('y'):
            logger.info("STS dot %s has no stored spectrum to plot", index)
            return

        pi = loc.get('point_index', index)
        sel = getattr(self, '_sts_selected', None)
        if sel is None:
            sel = {}
            self._sts_selected = sel
        if pi in sel:
            del sel[pi]                       # toggle off
        else:
            sel[pi] = {
                'x': avg['V'], 'y': avg['y'], 'title': f"Point {pi}",
                'x_name': 'V', 'y_name': 'Current',
            }

        spectra = list(sel.values())
        if spectra:
            self.openPlotWindowRequested.emit("STS points", spectra)
        # Highlight the selected dots on the canvas (instant click feedback).
        if self._canvas is not None:
            selected_idx = [i for i, L in enumerate(locs)
                            if L.get('point_index', i) in sel]
            self._canvas.setSelectedStsMarkers(selected_idx)

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
        """Clear block selection"""
        if self._canvas:
            self._canvas.clearBlockSelection()

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
                # Subtract a fitted plane
                rows, cols = data.shape
                x = np.arange(cols)
                y = np.arange(rows)
                X, Y = np.meshgrid(x, y)

                # Fit plane: z = ax + by + c
                A = np.column_stack([X.ravel(), Y.ravel(), np.ones(X.size)])
                coeffs, _, _, _ = np.linalg.lstsq(A, data.ravel(), rcond=None)
                plane = (coeffs[0] * X + coeffs[1] * Y + coeffs[2])
                data = data - plane

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

    @Slot(str, str)
    def exportChannel(self, channel_name: str, file_path: str):
        """Export a channel to file (TIFF and CSV formats only)"""
        if self._multi_channel_map is None:
            return

        try:
            path = Path(file_path.replace("file://", ""))
            channel = self._multi_channel_map.get_channel(channel_name)

            if path.suffix.lower() in ['.tif', '.tiff']:
                import tifffile
                tifffile.imwrite(str(path), channel.data.astype(np.float32))
            elif path.suffix.lower() == '.csv':
                np.savetxt(str(path), channel.data, delimiter=',', fmt='%.6e')
            elif path.suffix.lower() == '.png':
                # PNG format is no longer supported - save as TIFF instead
                logger.warning(f"PNG format no longer supported. Saving as TIFF instead.")
                tiff_path = path.with_suffix('.tiff')
                import tifffile
                tifffile.imwrite(str(tiff_path), channel.data.astype(np.float32))
                path = tiff_path
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
