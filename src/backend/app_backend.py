"""
Application Backend Bridge
Connects QML UI to Python data processing logic with full tool implementations
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import json
import logging
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
import tempfile
from PySide6.QtCore import QObject, Signal, Slot, Property, QUrl
from PySide6.QtWidgets import QFileDialog, QApplication
from PySide6.QtGui import QDesktopServices

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.models.table_data_model import TableDataModel
from src.models.topography_data import TopographyData
from src.models.discretizer import Discretizer
from src.models.image_data import ImageData, ImageMode
from src.backend.spectral_axis import (
    AxisUnit,
    convert_dataframe_axis,
    default_column_name,
    parse_unit,
)
from src.backend.peak_fitting import (
    PeakShape,
    detect_peaks,
    fit_multipeak,
)
from src.data_loaders.nanosurf_sts_enhanced import NanosurfSTSEnhancedLoader
from src.data_loaders.neaspec_snom_enhanced import NeaSpecSNOMEnhancedLoader
from src.data_loaders.omicron_mtrx_loader import OmicronMatrixSTSLoader
from src.data_loaders.omicron_flat_loader import OmicronFlatLoader
from src.data_loaders.park_afm_loader import ParkAFMLoader
from src.data_loaders.witec_wip_loader import WitecWipLoader
from src.backend.tool_implementations import ToolImplementations
from src.backend.worker import WorkerManager
from src.backend.project_manager import ProjectManager
from src.backend.dock_manager import DockManager
from src.backend.workflow_manager import WorkflowManager
from src.backend.preferences_manager import PreferencesManager
from src.backend.undo_manager import UndoManager, UndoCommand
from src.backend.autosave_manager import AutosaveManager

logger = logging.getLogger(__name__)


class AppBackend(ToolImplementations, QObject):
    """
    Main application backend that bridges QML UI to Python logic.
    Includes full implementation of all analysis tools.
    """

    # Signals
    statusChanged = Signal(str)
    progressChanged = Signal(int, int, str)
    dataLoaded = Signal(str)
    errorOccurred = Signal(str, str)
    toolOpened = Signal(str)
    toolCompleted = Signal(str, str)  # tool_name, output_path
    projectLoaded = Signal(str)  # project_path
    projectSaved = Signal(str)  # project_path
    projectModifiedChanged = Signal(bool)  # is_modified
    projectReadyChanged = Signal(bool)  # project is set up and ready
    mapCreated = Signal(str, str)  # map_id, map_title
    mapDeleted = Signal(str)  # map_path - emitted when a map is deleted
    imageImported = Signal(str, str, str)  # map_name, file_path, map_id - opens in Map Editor tab
    windowClosed = Signal(str, str)  # window_type, window_id
    outputCreated = Signal(str, str, str)  # output_id, tool_name, file_path
    isBusyChanged = Signal(bool)  # worker is processing tasks
    applicationClosing = Signal()  # emitted when main window is closing - all windows should close
    largeDatasetConfirmation = Signal(str, int, int)  # dataset_name, num_spectra, num_points - prompt user before opening large dataset
    datasetDeleted = Signal(str)  # dataset_name - emitted when a dataset is deleted
    datasetRenamed = Signal(str, str)  # old_name, new_name - emitted when a dataset is renamed
    activeDatasetChanged = Signal(str)  # active dataset name changed
    projectPathChanged = Signal(str)  # project path changed
    namingConventionChanged = Signal(str)  # naming convention pattern changed
    loadMapInEditor = Signal(str)  # map_path - request to load map in the map editor (file-based path)
    loadMapInEditorById = Signal(str)  # map_id - request to load an in-memory map by ID
    projectStateRestored = Signal(str)  # stateJson - emitted after loading project to restore tables/graphs/workspace
    openDatasetEmbedded = Signal(str, 'QVariantList', str, str)  # name, curves, xLabel, yLabel
    openTableEmbedded = Signal(str, QObject)  # title, TableDataModel
    openImageEmbedded = Signal(str, str)  # title, image_id (canvas pulls QImage via image:// URL provider)
    openNoteEmbedded = Signal(str, str, str)  # title, body_text, source_label
    collectWindowStatesRequested = Signal()  # ask QML for embedded window states before saving
    imageAdded = Signal(str, str)  # image_id, name
    imageDeleted = Signal(str)  # image_id
    imageRenamed = Signal(str, str)  # image_id, new_name
    noteAdded = Signal(str, str)  # note_id, name
    noteDeleted = Signal(str)  # note_id
    noteRenamed = Signal(str, str)  # note_id, new_name

    def __init__(self, parent=None):
        super().__init__(parent)

        # Application state
        self._status = "Ready"
        self._current_tab = 0
        self._project_ready = False
        self._project_name = ""
        self._project_path: Optional[Path] = None
        self._outputs_created = False  # Track if any outputs have been saved

        # Naming convention for output files
        # Default: "[dataset_name]" (required token)
        self._naming_convention = "[dataset_name]"
        self._naming_index_start = 1  # Starting index for [index] token
        self._naming_date_format = "dd-mm-yyyy"  # Date format: "dd-mm-yyyy" or "mm-dd-yyyy"
        self._current_file_index = 1  # Current index counter for this session

        # Data storage
        self._datasets: Dict[str, SpectralData] = {}
        self._active_dataset: Optional[str] = None
        self._workflow_mode: bool = False  # When True, suppress dataLoaded emission for intermediate results

        # Imported map data (for Map Editor)
        self._imported_map_data: Optional[np.ndarray] = None
        self._imported_map_name: str = ""
        self._imported_map_path: str = ""

        # Output management - will be set when project is created/opened
        self._output_base_dir: Optional[Path] = None
        self._recent_projects: List[Dict] = []
        self._load_recent_projects()

        # Initialize loaders
        try:
            self.nanosurf_loader = NanosurfSTSEnhancedLoader()
            logger.info("Nanosurf loader initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Nanosurf loader: {e}")
            self.nanosurf_loader = None

        try:
            self.neaspec_loader = NeaSpecSNOMEnhancedLoader()
            logger.info("NeaSpec loader initialized")
        except Exception as e:
            logger.warning(f"Could not initialize NeaSpec loader: {e}")
            self.neaspec_loader = None

        # Initialize Omicron loaders
        try:
            self.omicron_sts_loader = OmicronMatrixSTSLoader()
            logger.info("Omicron Matrix STS loader initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Omicron STS loader: {e}")
            self.omicron_sts_loader = None

        try:
            self.omicron_flat_loader = OmicronFlatLoader()
            logger.info("Omicron Flat image loader initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Omicron Flat loader: {e}")
            self.omicron_flat_loader = None

        # Initialize Park AFM loader
        try:
            self.park_loader = ParkAFMLoader()
            logger.info("Park AFM loader initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Park AFM loader: {e}")
            self.park_loader = None

        # Initialize WITec WIP loader (PL/Raman)
        try:
            self.witec_loader = WitecWipLoader()
            logger.info("WITec WIP loader initialized")
        except Exception as e:
            logger.warning(f"Could not initialize WITec WIP loader: {e}")
            self.witec_loader = None

        # Initialize discretizer for spatial averaging
        self.discretizer = Discretizer()

        # Initialize worker manager for multithreading
        self.worker_manager = WorkerManager(max_concurrent=3)
        self.worker_manager.worker_started.connect(self._on_worker_started)
        self.worker_manager.worker_completed.connect(self._on_worker_completed)
        self.worker_manager.worker_failed.connect(self._on_worker_failed)
        self.worker_manager.worker_cancelled.connect(self._on_worker_cancelled)

        # Initialize project manager
        self.project_manager = ProjectManager()

        # Initialize dock manager
        self.dock_manager = DockManager()

        # Initialize workflow manager
        self.workflow_manager = WorkflowManager(self)

        # Initialize preferences manager
        self._preferences_manager = PreferencesManager(self)

        # Initialize undo manager
        self._undo_manager = UndoManager(parent=self)

        # Initialize autosave manager
        self._autosave_manager = AutosaveManager(self, parent=self)

        # Flag to suppress undo registration during undo/redo operations
        self._suppress_undo = False

        # Map editor backend reference (set from QML)
        self._map_editor_backend = None

        # Embedded window states for persistence (collected from QML before save)
        self._embedded_window_states = []

        # Keep references to open OS windows (map visualization only)
        self.open_windows = []
        self.open_map_windows = []  # List of {'window': MapWindow, 'title': str, 'id': str, 'path': str}
        self._table_models = []  # Keep references to prevent GC
        self._window_id_counter = 0

        # Track maps and output files from tools
        self.maps = []  # List of {'id': str, 'title': str, 'path': str, 'timestamp': str}
        self._map_id_counter = 0
        # In-memory map registry — populated when a loader returns a
        # MultiChannelMap directly (no on-disk TIFF). Used by openMap to
        # route the map to the editor without going through the filesystem.
        # Keyed by map_id; values are MultiChannelMap-shaped objects (the
        # map editor consumes them via loadMapById).
        self._maps_inmem: Dict[str, Any] = {}
        self.output_files = []  # List of {'id': str, 'tool': str, 'path': str, 'timestamp': str}
        self._output_id_counter = 0

        # Image entities (first-class, alongside datasets and maps)
        self._images: Dict[str, ImageData] = {}

        # Note entities — text annotations surfaced from measurement files
        # (e.g. WITec ``TDText`` blocks) plus user-added notes. Stored as a
        # plain dict so the browser can list them by id without round-tripping
        # through a richer model class.
        self._notes: Dict[str, Dict[str, Any]] = {}
        self._note_id_counter = 0

        logger.info("AppBackend initialized with all tools")

    def _create_output_directories(self):
        """Create organized output directory structure (lazy - only when needed)."""
        if self._output_base_dir is None:
            logger.warning("Cannot create output directories: no project set")
            return

        subdirs = ['curves', 'derivatives', 'fft', 'integrated', 'maps',
                   'smoothed', 'fitted', 'peaks', 'discretized', 'workflows']
        for subdir in subdirs:
            (self._output_base_dir / subdir).mkdir(parents=True, exist_ok=True)

        self._outputs_created = True
        logger.info(f"Output directories created in {self._output_base_dir}")

    def _ensure_output_dir(self, subdir: str) -> Path:
        """
        Ensure output subdirectory exists, creating project structure if needed.
        This implements lazy directory creation - only create when actually saving.
        """
        if self._output_base_dir is None:
            raise ValueError("No project set. Please create or open a project first.")

        # Create the project directory and subdirectory only when needed
        output_path = self._output_base_dir / subdir
        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)
            self._outputs_created = True
            logger.info(f"Created output directory: {output_path}")

        return output_path

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a string for use as a filename.
        Removes/replaces special characters that are problematic in file paths.
        """
        import re
        # Replace spaces with underscores
        safe = name.replace(" ", "_")
        # Remove or replace problematic characters
        safe = re.sub(r'[<>:"/\\|?*]', '', safe)
        # Remove parentheses and brackets
        safe = re.sub(r'[\(\)\[\]\{\}]', '', safe)
        # Collapse multiple underscores
        safe = re.sub(r'_+', '_', safe)
        # Remove leading/trailing underscores
        safe = safe.strip('_')
        # Limit length
        if len(safe) > 50:
            safe = safe[:50]
        return safe

    def _format_user_friendly_name(self, base_name: str, operation: str,
                                    source_dataset: str = None) -> str:
        """
        Format a user-friendly output name.

        Examples:
            - "STS_Sample1_Smoothed" -> "STS Sample1 - Smoothed"
            - "_wf_STS_hyperspec_MnBi2Te4_abc123" -> "STS hyperspec MnBi2Te4 - <operation>"
        """
        # Use the clean base name helper
        display_name = self._extract_clean_base_name(base_name)

        # Format as "Source - Operation"
        if operation:
            return f"{display_name} - {operation}"
        return display_name

    def _load_recent_projects(self):
        """Load recent projects from settings file."""
        import json
        settings_path = Path.home() / ".trans_qml" / "recent_projects.json"

        if settings_path.exists():
            try:
                with open(settings_path, 'r') as f:
                    self._recent_projects = json.load(f)
                logger.info(f"Loaded {len(self._recent_projects)} recent projects")
            except Exception as e:
                logger.warning(f"Could not load recent projects: {e}")
                self._recent_projects = []
        else:
            self._recent_projects = []

    def _save_recent_projects(self):
        """Save recent projects to settings file."""
        import json
        settings_dir = Path.home() / ".trans_qml"
        settings_dir.mkdir(exist_ok=True)
        settings_path = settings_dir / "recent_projects.json"

        try:
            # Keep only last 10 projects
            self._recent_projects = self._recent_projects[:10]
            with open(settings_path, 'w') as f:
                json.dump(self._recent_projects, f, indent=2)
            logger.info(f"Saved {len(self._recent_projects)} recent projects")
        except Exception as e:
            logger.warning(f"Could not save recent projects: {e}")

    def _add_to_recent_projects(self, project_path: str, project_name: str):
        """Add a project to the recent projects list."""
        from datetime import datetime

        # Remove if already exists
        self._recent_projects = [p for p in self._recent_projects
                                  if p.get('path') != project_path]

        # Add to front
        self._recent_projects.insert(0, {
            'name': project_name,
            'path': project_path,
            'lastOpened': datetime.now().strftime("%Y-%m-%d %H:%M")
        })

        self._save_recent_projects()

    # Properties
    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if self._status != value:
            self._status = value
            self.statusChanged.emit(value)

    @Property(int)
    def currentTab(self):
        return self._current_tab

    @currentTab.setter
    def currentTab(self, value):
        self._current_tab = value

    @Property(str, notify=activeDatasetChanged)
    def activeDataset(self):
        return self._active_dataset or ""

    @Property(QObject, constant=True)
    def dockManager(self):
        """Expose dock manager to QML."""
        return self.dock_manager

    @Property(QObject, constant=True)
    def workflowManager(self):
        """Expose workflow manager to QML."""
        return self.workflow_manager

    @Property(QObject, constant=True)
    def preferencesManager(self):
        """Expose preferences manager to QML."""
        return self._preferences_manager

    @Property(QObject, constant=True)
    def undoManager(self):
        """Expose undo manager to QML."""
        return self._undo_manager

    @Property(QObject, constant=True)
    def autosaveManager(self):
        """Expose autosave manager to QML."""
        return self._autosave_manager

    @Slot(QObject)
    def setMapEditorBackend(self, backend):
        """Store reference to map editor backend (called from QML).

        Also installs the reverse reference so the map editor can resolve
        in-memory ``MultiChannelMap`` entities by id without disk I/O —
        this is the backbone of the project-browser map double-click fix.
        """
        self._map_editor_backend = backend
        if backend is not None and hasattr(backend, "set_app_backend"):
            backend.set_app_backend(self)
        logger.info("Map editor backend registered with app backend")

    @Slot('QVariantList')
    def setEmbeddedWindowStates(self, states):
        """Receive embedded window states from QML (called before project save)."""
        self._embedded_window_states = list(states) if states else []
        logger.debug(f"Received {len(self._embedded_window_states)} embedded window states")

    @Property(bool, notify=projectReadyChanged)
    def projectReady(self):
        """Whether a project is set up and ready for use."""
        return self._project_ready

    @Property(str)
    def projectName(self):
        """Current project name."""
        return self._project_name

    @Property(str, notify=projectPathChanged)
    def projectPath(self):
        """Current project path."""
        return str(self._project_path) if self._project_path else ""

    @Property(str, notify=namingConventionChanged)
    def namingConvention(self):
        """Get current naming convention pattern."""
        return self._naming_convention

    @Slot(str, result=bool)
    def setNamingConvention(self, pattern: str) -> bool:
        """
        Set the naming convention pattern.

        Available tokens:
        - [dataset_name] - Required. The name of the dataset being processed.
        - [index] - Auto-incrementing index (001, 002, etc.)
        - [date] - Current date in the configured format
        - [time] - Current time (HH-MM-SS)
        - [string:text] - Custom string (e.g., [string:MyExperiment])

        Returns True if pattern is valid (contains [dataset_name]), False otherwise.
        """
        # Validate that pattern contains required [dataset_name] token
        if "[dataset_name]" not in pattern.lower():
            logger.warning(f"Naming convention must contain [dataset_name] token: {pattern}")
            self.errorOccurred.emit("Invalid Pattern",
                "The naming convention must include [dataset_name] token.")
            return False

        # Normalize the pattern
        normalized = pattern.replace("[dataset_name]", "[dataset_name]")
        normalized = normalized.replace("[DATASET_NAME]", "[dataset_name]")

        self._naming_convention = normalized
        self.namingConventionChanged.emit(normalized)
        logger.info(f"Naming convention set to: {normalized}")
        return True

    @Slot(int)
    def setNamingIndexStart(self, start: int):
        """Set the starting index for the [index] token."""
        self._naming_index_start = max(0, start)
        self._current_file_index = self._naming_index_start
        logger.info(f"Naming index start set to: {self._naming_index_start}")

    @Slot(str)
    def setNamingDateFormat(self, format_str: str):
        """Set the date format: 'dd-mm-yyyy' or 'mm-dd-yyyy'."""
        if format_str in ["dd-mm-yyyy", "mm-dd-yyyy"]:
            self._naming_date_format = format_str
            logger.info(f"Naming date format set to: {format_str}")

    @Slot(result=int)
    def getNamingIndexStart(self) -> int:
        """Get the starting index for the [index] token."""
        return self._naming_index_start

    @Slot(result=str)
    def getNamingDateFormat(self) -> str:
        """Get the current date format."""
        return self._naming_date_format

    @Slot()
    def resetNamingIndex(self):
        """Reset the file index counter to the starting value."""
        self._current_file_index = self._naming_index_start
        logger.info(f"Naming index reset to: {self._current_file_index}")

    @Slot(str, result=str)
    def previewNamingConvention(self, dataset_name: str) -> str:
        """
        Preview what a filename would look like with the current naming convention.

        Parameters:
        -----------
        dataset_name : str
            Sample dataset name to use in preview

        Returns:
        --------
        str : Formatted filename preview
        """
        return self._apply_naming_convention(dataset_name, preview=True)

    def _apply_naming_convention(self, dataset_name: str, operation: str = "",
                                  preview: bool = False) -> str:
        """
        Apply the naming convention to create a filename.

        Parameters:
        -----------
        dataset_name : str
            The dataset name to use
        operation : str
            Optional operation suffix (e.g., "Smoothed", "Integrated")
        preview : bool
            If True, don't increment the index counter

        Returns:
        --------
        str : Formatted filename (without extension)
        """
        from datetime import datetime

        pattern = self._naming_convention

        # Clean the dataset name using the helper
        clean_name = self._extract_clean_base_name(dataset_name)

        # Replace [dataset_name] token
        result = pattern.replace("[dataset_name]", clean_name)

        # Replace [index] token with zero-padded number
        if "[index]" in result:
            index_str = f"{self._current_file_index:03d}"
            result = result.replace("[index]", index_str)
            if not preview:
                self._current_file_index += 1

        # Replace [date] token
        if "[date]" in result:
            now = datetime.now()
            if self._naming_date_format == "dd-mm-yyyy":
                date_str = now.strftime("%d-%m-%Y")
            else:
                date_str = now.strftime("%m-%d-%Y")
            result = result.replace("[date]", date_str)

        # Replace [time] token
        if "[time]" in result:
            time_str = datetime.now().strftime("%H-%M-%S")
            result = result.replace("[time]", time_str)

        # Replace [string:xxx] tokens
        import re
        string_pattern = r'\[string:([^\]]+)\]'
        result = re.sub(string_pattern, r'\1', result)

        # Add operation suffix if provided
        if operation:
            result = f"{result}_{operation}"

        # Sanitize for filesystem
        result = self._sanitize_filename(result)

        return result

    @Slot(result=str)
    def getDefaultProjectsPath(self):
        """Get the default location for new projects."""
        default_path = Path.home() / "Documents" / "TRANS_QML_Projects"
        return str(default_path)

    @Slot(result='QVariantList')
    def getRecentProjects(self):
        """Get list of recent projects for QML."""
        return self._recent_projects

    @Slot(str, str)
    def createProject(self, project_path: str, project_name: str):
        """
        Create a new project. Writes an initial .hrt so the project exists on
        disk from the moment it is created — without this, importing data and
        quitting before a manual save would lose everything because
        openProject() would find no .hrt to load.
        """
        logger.info(f"Creating project: {project_name} at {project_path}")

        self._project_path = Path(project_path)
        self._project_name = project_name
        # Create project-specific output folder using sanitized project name
        safe_project_name = self._sanitize_filename(project_name)
        self._output_base_dir = self._project_path / f"{safe_project_name}_outputs"
        self._outputs_created = False

        # Clear any existing data
        self._datasets.clear()
        self._active_dataset = None
        self.maps.clear()
        self._maps_inmem.clear()
        self.output_files.clear()
        self._images.clear()
        self._notes.clear()

        # Add to recent projects
        self._add_to_recent_projects(project_path, project_name)

        # Mark project as ready
        self._project_ready = True
        self.projectReadyChanged.emit(True)
        self.projectPathChanged.emit(project_path)
        self.projectLoaded.emit(project_path)

        # Write an initial empty .hrt so reopening the project folder finds it,
        # and register it as the current project file so subsequent saves and
        # autosaves target the right path.
        try:
            self._project_path.mkdir(parents=True, exist_ok=True)
            initial_hrt = self._project_path / f"{project_name}.hrt"
            project_data = {
                'metadata': {'name': project_name, 'description': 'TRANS-QML Project'},
                'datasets': {},
                'tables': [],
                'graphs': [],
                'image_windows': [],
                'workspace': {},
                'output_files': [],
                'maps': [],
                'images': {},
                'notes': {},
                'naming_convention': self._naming_convention,
                'map_editor': {},
            }
            if self.project_manager.save_project(initial_hrt, project_data):
                logger.info(f"Initial project file written: {initial_hrt}")
            else:
                logger.warning(f"Could not write initial project file: {initial_hrt}")
        except Exception as e:
            logger.warning(f"Could not write initial project file for {project_name}: {e}")

        # Start autosave so any imports done before the next manual save are
        # still persisted within the autosave interval.
        self._autosave_manager.start()

        self.status = f"Project '{project_name}' created"
        logger.info(f"Project created: {project_name}")

    @Slot(str, str)
    def openProject(self, project_path: str, project_name: str):
        """
        Open an existing project by folder path.
        If a .hrt file exists in the folder, it will be loaded to restore datasets.
        """
        logger.info(f"Opening project: {project_name} at {project_path}")

        project_path = Path(project_path)

        # Check if there's a .hrt file in the project folder
        hrt_file = project_path / f"{project_name}.hrt"
        if not hrt_file.exists():
            # Try to find any .hrt file in the folder
            hrt_files = list(project_path.glob("*.hrt"))
            if hrt_files:
                hrt_file = hrt_files[0]  # Use the first one found

        # If a .hrt file exists, use openProjectFile to load complete state
        if hrt_file.exists():
            logger.info(f"Found .hrt file: {hrt_file}, loading project data")
            self.openProjectFile(str(hrt_file))
            return

        # No .hrt file found - open as empty project folder
        logger.info(f"No .hrt file found, opening as folder-based project")

        self._project_path = project_path
        self._project_name = project_name
        # Create project-specific output folder using sanitized project name
        safe_project_name = self._sanitize_filename(project_name)
        self._output_base_dir = self._project_path / f"{safe_project_name}_outputs"

        # Check if outputs directory exists (also check legacy "outputs" folder)
        self._outputs_created = self._output_base_dir.exists()
        if not self._outputs_created:
            # Check for legacy "outputs" folder and migrate if found
            legacy_outputs = self._project_path / "outputs"
            if legacy_outputs.exists():
                self._output_base_dir = legacy_outputs
                self._outputs_created = True
                logger.info(f"Using legacy outputs folder: {legacy_outputs}")

        # Clear any existing data
        self._datasets.clear()
        self._active_dataset = None
        self.maps.clear()
        self._maps_inmem.clear()
        self.output_files.clear()
        self._images.clear()
        self._notes.clear()

        # Scan for existing outputs if the project has them
        if self._outputs_created:
            self._scan_existing_outputs()

        # Add to recent projects
        self._add_to_recent_projects(str(project_path), project_name)

        # Mark project as ready
        self._project_ready = True
        self.projectReadyChanged.emit(True)
        self.projectPathChanged.emit(str(project_path))
        self.projectLoaded.emit(str(project_path))

        # Start autosave so imports done into this folder-based project are
        # persisted even if the user never invokes Save manually. The autosave
        # path is derived from _project_path / _project_name.
        self._autosave_manager.start()

        self.status = f"Project '{project_name}' opened"
        logger.info(f"Project opened: {project_name}")

    def _scan_existing_outputs(self):
        """Scan for existing output files in the project."""
        if not self._output_base_dir or not self._output_base_dir.exists():
            return

        # Scan for maps
        maps_dir = self._output_base_dir / "maps"
        if maps_dir.exists():
            for file in maps_dir.glob("*.png"):
                if "_colormap" not in file.name:
                    self._map_id_counter += 1
                    self.maps.append({
                        'id': f"map_{self._map_id_counter}",
                        'title': file.stem,
                        'path': str(file),
                        'timestamp': ""
                    })

        logger.info(f"Scanned existing outputs: {len(self.maps)} maps found")

    @Slot()
    def closeProject(self):
        """Close the current project."""
        if not self._project_ready:
            return

        logger.info(f"Closing project: {self._project_name}")

        # Clear project state
        self._project_path = None
        self._project_name = ""
        self._output_base_dir = None
        self._outputs_created = False
        self._project_ready = False

        # Clear data
        self._datasets.clear()
        self._active_dataset = None
        self.maps.clear()
        self._maps_inmem.clear()
        self.output_files.clear()
        self._images.clear()
        self._notes.clear()

        self.projectReadyChanged.emit(False)
        self.status = "No project open"

    @Slot(result=str)
    def getProjectOutputPath(self):
        """Get the current project's output path."""
        if self._output_base_dir:
            return str(self._output_base_dir)
        return ""

    @Slot(str, result=bool)
    def openProjectFile(self, file_path: str) -> bool:
        """
        Open a project from a .hrt file using the ProjectManager.
        This loads the complete project state including datasets and window configurations.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            logger.error(f"Project file not found: {file_path}")
            self.errorOccurred.emit("Open Error", f"Project file not found: {file_path}")
            return False

        if file_path.suffix.lower() != '.hrt':
            logger.error(f"Invalid project file: {file_path}")
            self.errorOccurred.emit("Open Error", "Invalid project file. Expected .hrt extension.")
            return False

        try:
            # Use ProjectManager to load the project
            project_data = self.project_manager.load_project(file_path)

            if project_data is None:
                self.errorOccurred.emit("Open Error", "Failed to load project file")
                return False

            # Extract project info from metadata
            metadata = project_data.get('metadata', {})
            project_name = metadata.get('name', file_path.stem)

            # Use the directory containing the .hrt file as project path
            actual_project_path = file_path.parent

            logger.info(f"Opening project from file: {project_name} at {actual_project_path}")

            # Set up project state
            self._project_path = actual_project_path
            self._project_name = project_name
            # Create project-specific output folder using sanitized project name
            safe_project_name = self._sanitize_filename(project_name)
            self._output_base_dir = actual_project_path / f"{safe_project_name}_outputs"
            self._outputs_created = self._output_base_dir.exists()

            # Check for legacy "outputs" folder and use if new folder doesn't exist
            if not self._outputs_created:
                legacy_outputs = actual_project_path / "outputs"
                if legacy_outputs.exists():
                    self._output_base_dir = legacy_outputs
                    self._outputs_created = True
                    logger.info(f"Using legacy outputs folder: {legacy_outputs}")

            # Clear any existing data and load from project file
            self._datasets.clear()
            self._active_dataset = None
            self.maps.clear()
            self.output_files.clear()

            # Load datasets from project file
            loaded_datasets = project_data.get('datasets', {})
            for name, dataset in loaded_datasets.items():
                self._datasets[name] = dataset
                logger.info(f"Loaded dataset: {name}")

            # Set first dataset as active if any
            if self._datasets:
                self._active_dataset = list(self._datasets.keys())[0]

            # Restore workspace state
            workspace = project_data.get('workspace', {})
            if workspace.get('active_dataset') and workspace['active_dataset'] in self._datasets:
                self._active_dataset = workspace['active_dataset']
            if 'current_tab' in workspace:
                self._current_tab = workspace['current_tab']
            if 'window_counter' in workspace:
                self._window_id_counter = workspace['window_counter']

            # Restore naming convention
            naming = project_data.get('naming_convention')
            if naming:
                self._naming_convention = naming

            # Restore maps and output files
            loaded_maps = project_data.get('maps', [])
            for m in loaded_maps:
                self.maps.append(m)

            loaded_outputs = project_data.get('output_files', [])
            for o in loaded_outputs:
                self.output_files.append(o)

            # Restore image entities (embedded as bytes in the .hrt file)
            loaded_images = project_data.get('images', {}) or {}
            for image_id, image in loaded_images.items():
                self._images[image_id] = image
                self.imageAdded.emit(image_id, image.name)
            logger.info(f"Restored {len(loaded_images)} images from project")

            # Restore note entities (text annotations from measurement files
            # and user-added notes).
            loaded_notes = project_data.get('notes', {}) or {}
            for note_id, note in loaded_notes.items():
                self._notes[note_id] = note
                # Keep the counter ahead of any restored ids so future
                # auto-generated ids don't collide.
                try:
                    n = int(str(note_id).split('_', 1)[1])
                    self._note_id_counter = max(self._note_id_counter, n)
                except Exception:
                    pass
                self.noteAdded.emit(note_id, note.get('name', 'Note'))
            logger.info(f"Restored {len(loaded_notes)} notes from project")

            # Scan for additional outputs in the outputs directory
            if self._outputs_created:
                self._scan_existing_outputs()

            # Add to recent projects
            self._add_to_recent_projects(str(actual_project_path), project_name)

            # Mark project as ready
            self._project_ready = True
            self.projectReadyChanged.emit(True)
            self.projectPathChanged.emit(str(actual_project_path))
            self.projectLoaded.emit(str(actual_project_path))

            # Emit dataLoaded AFTER all state is restored (maps, outputs, etc.)
            # so that refreshBrowser() sees the complete project state
            if self._datasets:
                self.dataLoaded.emit(self._active_dataset)

            # Restore map editor state
            map_editor_state = project_data.get('map_editor', {})
            if map_editor_state and self._map_editor_backend is not None:
                map_path = map_editor_state.get('map_path', '')
                if map_path:
                    try:
                        self._map_editor_backend.loadMapFromFile(map_path)
                        self._map_editor_backend.restoreState(map_editor_state)
                    except Exception as e:
                        logger.warning(f"Could not restore map editor state: {e}")

            # Emit signal for tables, graphs, and image windows to be restored by QML
            tables = project_data.get('tables', [])
            graphs = project_data.get('graphs', [])
            image_windows = project_data.get('image_windows', [])
            if tables or graphs or image_windows:
                self.projectStateRestored.emit(json.dumps({
                    'tables': tables,
                    'graphs': graphs,
                    'image_windows': image_windows,
                    'workspace': workspace
                }))

            # Check for autosave recovery and start autosave timer
            self._autosave_manager.check_recovery(file_path)
            self._autosave_manager.start()

            self.status = f"Project '{project_name}' opened with {len(self._datasets)} dataset(s)"
            logger.info(f"Project opened from file: {project_name}")
            return True

        except Exception as e:
            logger.error(f"Error opening project: {e}", exc_info=True)
            self.errorOccurred.emit("Open Error", f"Could not open project: {e}")
            return False

    @Slot(str, result=bool)
    def saveProjectFile(self, file_path: str = "") -> bool:
        """
        Save project to a .hrt file using the full save path (worker-based).
        If file_path is not provided, saves to the project directory.
        """
        if not self._project_ready or not self._project_path:
            logger.warning("Cannot save project: no project is open")
            return False

        save_path = Path(file_path) if file_path else self._project_path / f"{self._project_name}.hrt"
        self.status = "Saving project..."

        # Ask QML to collect embedded window states before we save
        self.collectWindowStatesRequested.emit()

        self.worker_manager.submit(
            name="Save Project",
            operation=self._do_save_project,
            project_path=save_path,
            on_finished=lambda _: self._on_project_saved(save_path)
        )
        return True

    @Slot(result=str)
    def getProjectFilePath(self) -> str:
        """Get the path to the current project's .hrt file."""
        if self._project_path and self._project_name:
            return str(self._project_path / f"{self._project_name}.hrt")
        return ""

    @Property(bool, notify=isBusyChanged)
    def isBusy(self):
        """Check if worker is currently processing tasks."""
        return self.worker_manager.is_busy()

    # File Operations
    @Slot()
    def importMeasurement(self):
        """Open custom import dialog (handled in QML)."""
        logger.info(f"Import measurement requested for tab {self._current_tab}")
        # Dialog will be opened from QML, which will call importFromFiles or importFromFolder

    @Slot('QVariantList')
    def importFromFiles(self, file_paths):
        """Import from a list of file paths."""
        logger.info(f"Importing {len(file_paths)} file(s)")
        self.status = f"Importing {len(file_paths)} file(s)..."

        for file_path in file_paths:
            filepath = Path(str(file_path))
            self._import_single_file_path(filepath)

    @Slot(str)
    def importFromFolder(self, folder_path):
        """Import from a folder path."""
        logger.info(f"Importing folder: {folder_path}")
        self.status = f"Importing folder: {Path(folder_path).name}..."
        self._import_folder_path(Path(folder_path))

    @Slot(str)
    def importSmartMap(self, file_path):
        """
        Smart map import: pick one file and auto-discover siblings
        from the same measurement session.

        Supports:
        - .nid files (Nanosurf) — discovers sibling .nid files
        - .mtrx / .I(V)_mtrx / etc (Omicron Matrix) — reads _0001.mtrx header
          to enumerate all session files via FERB blocks
        - .ps-ppt / .tiff (Park AFM) — discovers siblings by naming convention
        """
        filepath = Path(str(file_path))
        logger.info(f"Smart map import from: {filepath}")
        self.status = f"Smart import: scanning for siblings of {filepath.name}..."

        self.worker_manager.submit(
            name=f"Smart Load {filepath.name}",
            operation=self._do_smart_load,
            filepath=filepath,
            on_finished=self._on_file_loaded,
            on_error=None,
            on_progress=self._progress_callback
        )

    def _do_smart_load(self, task, filepath: Path, progress_callback=None):
        """Smart map loading in background thread — dispatches by file type."""
        if task.cancelled:
            return None

        # Determine file type and dispatch
        name = filepath.name.lower()

        if name.endswith('.nid'):
            return self._do_smart_load_nanosurf(filepath, progress_callback)
        elif name.endswith('_mtrx') or name.endswith('.mtrx'):
            return self._do_smart_load_matrix(filepath, progress_callback)
        elif name.endswith('.ps-ppt') or name.endswith('.tiff'):
            return self._do_smart_load_park(filepath, progress_callback)
        elif name.endswith('.wip'):
            return self._do_smart_load_witec(filepath, progress_callback)
        else:
            raise ValueError(f"Smart import not supported for: {filepath.name}")

    def _do_smart_load_nanosurf(self, filepath: Path, progress_callback=None):
        """Smart load for Nanosurf .nid files."""
        if not self.nanosurf_loader:
            raise RuntimeError("Nanosurf loader not available")

        spectral_data, topography = self.nanosurf_loader.smart_load_from_file(
            filepath, progress_callback=progress_callback
        )

        result = {'datasets': {}, 'active_dataset': None}
        folder_name = filepath.parent.name
        channels = spectral_data.metadata.additional_info.get('channels', {})
        for channel_name, channel_data in channels.items():
            dataset_name = f"{folder_name}_{channel_name}"
            result['datasets'][dataset_name] = channel_data
            logger.info(f"Loaded dataset: {dataset_name}")

        result['active_dataset'] = f"{folder_name}_Mixed"
        return result

    def _do_smart_load_matrix(self, filepath: Path, progress_callback=None):
        """Smart load for Omicron Matrix files — uses header FERB enumeration."""
        if not self.omicron_sts_loader:
            raise RuntimeError("Omicron STS loader not available")

        spectral_data, topography = self.omicron_sts_loader.smart_load_from_file(
            filepath, progress_callback=progress_callback
        )

        result = {'datasets': {}, 'active_dataset': None}
        folder_name = filepath.parent.name

        sweep_channels = spectral_data.metadata.additional_info.get('sweep_channels', {})
        if sweep_channels:
            base_name = self._apply_naming_convention(folder_name, 'IV')
            for sweep_name, sweep_df in sweep_channels.items():
                dataset_name = f"{base_name}_{sweep_name}"
                channel_metadata = self.omicron_sts_loader.create_metadata(
                    dimensions=spectral_data.metadata.dimensions,
                    scan_mode=spectral_data.metadata.scan_mode,
                    units=spectral_data.metadata.units,
                    source_directory=str(filepath.parent),
                    instrument="Omicron Matrix",
                    sweep_direction=sweep_name
                )
                channel_data = SpectralData(sweep_df, channel_metadata)
                result['datasets'][dataset_name] = channel_data
                logger.info(f"Smart-loaded Omicron {sweep_name}: {dataset_name}")

            result['active_dataset'] = f"{base_name}_Mixed"
        else:
            dataset_name = self._apply_naming_convention(folder_name, 'IV')
            result['datasets'][dataset_name] = spectral_data
            result['active_dataset'] = dataset_name

        return result

    def _do_smart_load_witec(self, filepath: Path, progress_callback=None):
        """Smart load for WITec WIP files (PL/Raman session containers)."""
        if not self.witec_loader:
            raise RuntimeError("WITec WIP loader not available")

        spectral_data, _topography = self.witec_loader.smart_load_from_file(
            filepath, progress_callback=progress_callback
        )

        result = {'datasets': {}, 'active_dataset': None}
        stem = filepath.stem
        channels = spectral_data.metadata.additional_info.get('channels', {}) or {}
        if channels:
            for channel_name, channel_data in channels.items():
                tag = channel_data.metadata.additional_info.get('channel_tag', '')
                base = f"{stem} · {channel_name}" if len(channels) > 1 else stem
                dataset_name = f"{base} · {tag}" if tag else base
                result['datasets'][dataset_name] = channel_data
                logger.info(f"Smart-loaded WITec channel: {dataset_name}")
            result['active_dataset'] = next(iter(result['datasets']))
        else:
            result['datasets'][stem] = spectral_data
            result['active_dataset'] = stem

        # Carry the additional_info forward on the active dataset so the
        # post-load hooks can pull images and map geometries from it.
        active = result['datasets'][result['active_dataset']]
        active.metadata.additional_info.update(
            spectral_data.metadata.additional_info
        )
        return result

    def _do_smart_load_park(self, filepath: Path, progress_callback=None):
        """Smart load for Park AFM files (.ps-ppt / .tiff)."""
        if not self.park_loader:
            raise RuntimeError("Park AFM loader not available")

        spectral_data, topography = self.park_loader.smart_load_from_file(
            filepath, progress_callback=progress_callback
        )

        result = {'datasets': {}, 'active_dataset': None}
        folder_name = filepath.parent.name

        channels = spectral_data.metadata.additional_info.get('channels', {})
        if channels:
            for channel_name, channel_data in channels.items():
                dataset_name = f"{folder_name}_{channel_name}"
                result['datasets'][dataset_name] = channel_data
                logger.info(f"Smart-loaded Park channel: {dataset_name}")

            result['active_dataset'] = f"{folder_name}_Force Backward"
            # If that key doesn't exist, pick the first Force channel or first overall
            if result['active_dataset'] not in result['datasets']:
                force_keys = [k for k in result['datasets'] if 'Force' in k]
                if force_keys:
                    result['active_dataset'] = force_keys[0]
                else:
                    result['active_dataset'] = next(iter(result['datasets']))
        else:
            dataset_name = f"{folder_name}_{filepath.stem}"
            result['datasets'][dataset_name] = spectral_data
            result['active_dataset'] = dataset_name

        return result

    def _import_single_file_path(self, filepath: Path):
        """Import a single data file from given path (submits to worker)."""
        logger.info(f"Importing file: {filepath}")

        # Submit to worker for background loading
        self.worker_manager.submit(
            name=f"Load {filepath.name}",
            operation=self._do_load_file,
            filepath=filepath,
            on_finished=self._on_file_loaded,
            on_error=None,  # Will use default worker_failed handler
            on_progress=self._progress_callback
        )

    def _do_load_file(self, task, filepath: Path, progress_callback=None):
        """
        Actual file loading logic executed in background thread.

        Parameters:
        -----------
        task : Task
            Task object for cancellation checking

        Returns:
        --------
        dict with 'datasets' and 'active_dataset' keys
        """
        result = {'datasets': {}, 'active_dataset': None}

        # Check if cancelled before starting
        if task.cancelled:
            logger.info("File load cancelled before starting")
            return None

        if filepath.suffix == '.nid':
            if not self.nanosurf_loader:
                raise RuntimeError("Nanosurf loader not available")

            spectral_data, topography = self.nanosurf_loader.load_from_directory(
                filepath.parent,
                progress_callback=progress_callback
            )

            channels = spectral_data.metadata.additional_info.get('channels', {})
            for channel_name, channel_data in channels.items():
                dataset_name = f"{filepath.stem}_{channel_name}"
                result['datasets'][dataset_name] = channel_data
                logger.info(f"Loaded dataset: {dataset_name}")

            result['active_dataset'] = f"{filepath.stem}_Mixed"

        elif filepath.suffix in ['.txt', '.dat']:
            if not self.neaspec_loader:
                raise RuntimeError("NeaSpec loader not available")

            spectral_data_dict = self.neaspec_loader.load_single_file(filepath)

            for key, data in spectral_data_dict.items():
                dataset_name = f"{filepath.stem}_{key}"
                result['datasets'][dataset_name] = data
                logger.info(f"Loaded dataset: {dataset_name}")

            first_key = list(spectral_data_dict.keys())[0]
            result['active_dataset'] = f"{filepath.stem}_{first_key}"

        elif any(filepath.name.endswith(ext) for ext in
                 ['.I(V)_mtrx', '.Aux2(V)_mtrx', '.Aux1(V)_mtrx',
                  '.I(Z)_mtrx', '.Z(V)_mtrx', '.Aux2(Z)_mtrx', '.Aux1(Z)_mtrx']):
            # Omicron Matrix spectroscopy file
            if not self.omicron_sts_loader:
                raise RuntimeError("Omicron STS loader not available")

            spectral_data = self.omicron_sts_loader.load_single_file(filepath)

            # Create three separate datasets from sweep channels (Forward, Backward, Mixed)
            base_name = self._apply_naming_convention(
                filepath.stem.replace('.I(V)', ''), 'IV')

            sweep_channels = spectral_data.metadata.additional_info.get('sweep_channels', {})

            if sweep_channels:
                # Create individual datasets for each sweep direction
                for sweep_name, sweep_df in sweep_channels.items():
                    dataset_name = f"{base_name}_{sweep_name}"
                    # Create new SpectralData for each channel
                    channel_metadata = self.omicron_sts_loader.create_metadata(
                        dimensions=spectral_data.metadata.dimensions,
                        scan_mode=spectral_data.metadata.scan_mode,
                        units=spectral_data.metadata.units,
                        source_file=str(filepath),
                        instrument="Omicron Matrix",
                        sweep_direction=sweep_name
                    )
                    channel_data = SpectralData(sweep_df, channel_metadata)
                    result['datasets'][dataset_name] = channel_data
                    logger.info(f"Loaded Omicron I(V) {sweep_name} dataset: {dataset_name}")

                # Set Mixed as active by default
                result['active_dataset'] = f"{base_name}_Mixed"
            else:
                # Fallback: no sweep channels, use original data
                result['datasets'][base_name] = spectral_data
                result['active_dataset'] = base_name
                logger.info(f"Loaded Omicron I(V) dataset: {base_name}")

        elif filepath.name.endswith('.Z_flat') or filepath.name.endswith('.I_flat'):
            # Omicron Matrix flat (image) file
            if not self.omicron_flat_loader:
                raise RuntimeError("Omicron Flat loader not available")

            topography = self.omicron_flat_loader.load_topography(filepath)

            # Store topography as a map
            map_name = self._apply_naming_convention(
                filepath.stem.replace('.Z_flat', '').replace('.I_flat', ''), 'topo')
            self._store_map(map_name, topography.data, 'topography')
            logger.info(f"Loaded Omicron flat image as map: {map_name}")

            # No spectral data for pure image files
            result['active_dataset'] = None

        elif filepath.suffix == '.ps-ppt':
            # Park AFM PinPoint spectroscopy file
            if not self.park_loader:
                raise RuntimeError("Park AFM loader not available")

            spectral_data = self.park_loader.load_single_file(filepath)
            dataset_name = self._apply_naming_convention(filepath.stem, 'Force')
            result['datasets'][dataset_name] = spectral_data
            result['active_dataset'] = dataset_name
            logger.info(f"Loaded Park ps-ppt: {dataset_name}")

        elif filepath.suffix.lower() == '.wip':
            # WITec PL/Raman project file
            if not self.witec_loader:
                raise RuntimeError("WITec WIP loader not available")

            spectral_data = self.witec_loader.load_single_file(filepath)
            channels = spectral_data.metadata.additional_info.get('channels', {}) or {}
            stem = filepath.stem
            if channels:
                for channel_name, channel_data in channels.items():
                    tag = channel_data.metadata.additional_info.get('channel_tag', '')
                    base = (
                        f"{stem} · {channel_name}" if len(channels) > 1 else stem
                    )
                    dataset_name = f"{base} · {tag}" if tag else base
                    result['datasets'][dataset_name] = channel_data
                    logger.info(f"Loaded WITec channel: {dataset_name}")
                result['active_dataset'] = next(iter(result['datasets']))
                # Forward images / map_geometries via the active dataset's metadata
                active = result['datasets'][result['active_dataset']]
                active.metadata.additional_info.update(
                    spectral_data.metadata.additional_info
                )
            else:
                result['datasets'][stem] = spectral_data
                result['active_dataset'] = stem

        else:
            raise ValueError(f"Cannot load {filepath.suffix} files")

        return result

    def _on_file_loaded(self, result: dict):
        """Handle file loading completion in main thread.

        Order matters here: image / note absorption must happen BEFORE the
        ``dataLoaded`` signal fires so that the browser's
        ``onDataLoaded → refreshBrowser`` cycle sees a populated registry.
        Otherwise refreshBrowser clears ``imagesModel`` / ``notesModel``,
        queries an empty ``getImageList`` / ``getNotesList``, and the
        subsequently-fired per-entity ``imageAdded`` / ``noteAdded`` signals
        end up appending to a model that the next refresh wipes again.
        """
        # Add datasets to application state
        self._datasets.update(result['datasets'])

        # Surface images and notes attached by loaders BEFORE the broadcast
        # signal so the subsequent browser refresh sees them.
        self._absorb_dataset_images(result)
        self._absorb_dataset_notes(result)

        # Set active dataset (browser's onDataLoaded will refresh and now
        # find the registered images/notes via getImageList / getNotesList).
        if result['active_dataset']:
            self._active_dataset = result['active_dataset']
            self.dataLoaded.emit(self._active_dataset)

        # Auto-load topography overlay if Nanosurf data has map geometry
        self._try_load_topo_overlay(result)

        # Imports create state that needs to be saved. Flag the project dirty
        # so the UI surfaces the unsaved-changes indicator and so the autosave
        # timer's next tick has a clear "needs persisting" signal.
        if result.get('datasets'):
            self.project_manager.mark_modified()
            self.projectModifiedChanged.emit(True)

        self.status = f"Loaded {len(result['datasets'])} datasets"
        logger.info(
            f"File loading complete: {len(result['datasets'])} datasets, "
            f"{len(self._images)} images total, {len(self._notes)} notes total"
        )

        # Process events to keep UI responsive during batch imports
        app = QApplication.instance()
        if app:
            app.processEvents()

    def _try_load_topo_overlay(self, result: dict):
        """If loaded data has topography + map geometry, send to map editor."""
        if self._map_editor_backend is None:
            return

        for name, spectral_data in result.get('datasets', {}).items():
            if not hasattr(spectral_data, 'metadata'):
                continue
            info = spectral_data.metadata.additional_info
            map_geom = info.get('map_geometry')
            topo_geom = info.get('topo_geometry')
            topo_data = getattr(spectral_data, 'topography', None)

            if map_geom and topo_geom and topo_data is not None:
                try:
                    self._map_editor_backend.loadTopographyWithOverlay(
                        topo_data, map_geom, topo_geom,
                        channel_name=f"{name}_Topography"
                    )
                    # Also link the spectral data for spectrum viewing
                    self._map_editor_backend.linkDataset(name, spectral_data)
                    logger.info(f"Auto-loaded topography overlay for {name}")
                except Exception as e:
                    logger.warning(f"Could not load topography overlay: {e}")
                return  # Only load once (from first dataset with topo)

    def _import_folder_path(self, dirpath: Path):
        """Import all files from a folder path (submits to worker)."""
        logger.info(f"Importing folder: {dirpath}")

        # Submit to worker for background loading
        self.worker_manager.submit(
            name=f"Load {dirpath.name}",
            operation=self._do_load_folder,
            dirpath=dirpath,
            on_finished=self._on_folder_loaded,
            on_error=None,  # Will use default worker_failed handler
            on_progress=self._progress_callback
        )

    def _do_load_folder(self, task, dirpath: Path, progress_callback=None):
        """
        Actual folder loading logic executed in background thread.

        Parameters:
        -----------
        task : Task
            Task object for cancellation checking

        Returns:
        --------
        dict with 'datasets' and 'active_dataset' keys
        """
        result = {'datasets': {}, 'active_dataset': None}

        # Check if cancelled before starting
        if task.cancelled:
            logger.info("Folder load cancelled before starting")
            return None

        nid_files = list(dirpath.glob("*.nid"))
        txt_files = list(dirpath.glob("*.txt"))
        iv_mtrx_files = [f for f in dirpath.iterdir() if f.name.endswith('.I(V)_mtrx')]
        flat_files = [f for f in dirpath.iterdir()
                      if f.name.endswith('.Z_flat') or f.name.endswith('.I_flat')]

        if nid_files:
            if not self.nanosurf_loader:
                raise RuntimeError("Nanosurf loader not available")

            spectral_data, topography = self.nanosurf_loader.load_from_directory(
                dirpath,
                progress_callback=progress_callback
            )

            channels = spectral_data.metadata.additional_info.get('channels', {})
            for channel_name, channel_data in channels.items():
                dataset_name = f"{dirpath.name}_{channel_name}"
                result['datasets'][dataset_name] = channel_data
                logger.info(f"Loaded dataset: {dataset_name}")

            result['active_dataset'] = f"{dirpath.name}_Mixed"

        elif txt_files:
            if not self.neaspec_loader:
                raise RuntimeError("NeaSpec loader not available")

            spectral_data_dict, topography = self.neaspec_loader.load_from_directory(
                dirpath,
                progress_callback=progress_callback
            )

            for key, data in spectral_data_dict.items():
                dataset_name = f"{dirpath.name}_{key}"
                result['datasets'][dataset_name] = data
                logger.info(f"Loaded dataset: {dataset_name}")

            first_key = list(spectral_data_dict.keys())[0]
            result['active_dataset'] = f"{dirpath.name}_{first_key}"

        elif iv_mtrx_files:
            # Omicron Matrix I(V) files
            if not self.omicron_sts_loader:
                raise RuntimeError("Omicron STS loader not available")

            spectral_data, topography = self.omicron_sts_loader.load_from_directory(
                dirpath,
                progress_callback=progress_callback
            )

            # Create three separate datasets from sweep channels (Forward, Backward, Mixed)
            base_name = self._apply_naming_convention(dirpath.name, 'IV')

            sweep_channels = spectral_data.metadata.additional_info.get('sweep_channels', {})

            if sweep_channels:
                # Create individual datasets for each sweep direction
                for sweep_name, sweep_df in sweep_channels.items():
                    dataset_name = f"{base_name}_{sweep_name}"
                    # Create new SpectralData for each channel
                    channel_metadata = self.omicron_sts_loader.create_metadata(
                        dimensions=spectral_data.metadata.dimensions,
                        scan_mode=spectral_data.metadata.scan_mode,
                        units=spectral_data.metadata.units,
                        source_directory=str(dirpath),
                        instrument="Omicron Matrix",
                        sweep_direction=sweep_name,
                        n_files=spectral_data.metadata.additional_info.get('n_files', 0)
                    )
                    channel_data = SpectralData(
                        sweep_df, channel_metadata,
                        topography.data if topography else None
                    )
                    result['datasets'][dataset_name] = channel_data
                    logger.info(f"Loaded Omicron I(V) {sweep_name} dataset: {dataset_name}")

                # Set Mixed as active by default
                result['active_dataset'] = f"{base_name}_Mixed"
            else:
                # Fallback: no sweep channels, use original data
                result['datasets'][base_name] = spectral_data
                result['active_dataset'] = base_name
                logger.info(f"Loaded Omicron I(V) dataset: {base_name}")

        elif flat_files:
            # Omicron Matrix flat (image) files
            if not self.omicron_flat_loader:
                raise RuntimeError("Omicron Flat loader not available")

            # Load each flat file as a map
            for flat_file in flat_files:
                topography = self.omicron_flat_loader.load_topography(flat_file)
                map_name = self._apply_naming_convention(
                    flat_file.stem.replace('.Z_flat', '').replace('.I_flat', ''), 'topo')
                self._store_map(map_name, topography.data, 'topography')
                logger.info(f"Loaded Omicron flat image as map: {map_name}")

            # No spectral data for pure image files
            result['active_dataset'] = None

        else:
            raise ValueError("No supported data files found in directory")

        return result

    def _on_folder_loaded(self, result: dict):
        """Handle folder loading completion in main thread."""
        # Add datasets to application state
        self._datasets.update(result['datasets'])

        # Set active dataset
        if result['active_dataset']:
            self._active_dataset = result['active_dataset']
            self.dataLoaded.emit(self._active_dataset)

        self.status = f"Loaded {len(result['datasets'])} datasets"
        logger.info(f"Folder loading complete: {len(result['datasets'])} datasets")

        # Process events to keep UI responsive
        app = QApplication.instance()
        if app:
            app.processEvents()

    def _progress_callback(self, current: int, total: int, message: str):
        """Progress callback for data loading."""
        self.progressChanged.emit(current, total, message)

    # Worker callbacks
    def _on_worker_started(self, operation_name: str):
        """Called when a worker starts."""
        self.status = f"Running: {operation_name}..."
        logger.info(f"Worker started: {operation_name}")
        self.isBusyChanged.emit(True)

    def _on_worker_completed(self, operation_name: str):
        """Called when a worker completes."""
        self.status = f"Completed: {operation_name}"
        logger.info(f"Worker completed: {operation_name}")
        self.isBusyChanged.emit(self.worker_manager.is_busy())

    def _on_worker_failed(self, operation_name: str, error_message: str):
        """Called when a worker fails."""
        self.status = f"Failed: {operation_name}"
        self.errorOccurred.emit(f"{operation_name} Error", error_message)
        logger.error(f"Worker failed: {operation_name} - {error_message}")
        self.isBusyChanged.emit(self.worker_manager.is_busy())

    def _on_worker_cancelled(self, operation_name: str):
        """Called when a worker is cancelled."""
        self.status = f"Cancelled: {operation_name}"
        logger.info(f"Worker cancelled: {operation_name}")
        self.isBusyChanged.emit(self.worker_manager.is_busy())

    @Slot()
    def cancelCurrentOperation(self):
        """Cancel the currently running operation."""
        if self.worker_manager.cancel_current():
            logger.info("Current operation cancelled by user")
        else:
            logger.info("No operation to cancel")

    @Slot()
    def cancelAllOperations(self):
        """Cancel the running operation and discard any queued ones.

        Used by the close-while-busy flow so the app can quit without
        waiting for the full queue to drain.
        """
        self.worker_manager.cancel_all()
        if self.worker_manager.cancel_current():
            logger.info("All operations cancelled by user")
        else:
            logger.info("No running operation; pending queue cleared")

    @Slot(result=str)
    def getCurrentOperation(self):
        """Get the name of the currently running operation."""
        return self.worker_manager.get_current_operation()

    # Dataset Management
    @Slot(result='QVariantList')
    def getDatasetList(self):
        """Get list of loaded datasets."""
        dataset_list = list(self._datasets.keys())
        logger.debug(f"getDatasetList() called, returning {len(dataset_list)} datasets: {dataset_list}")
        return dataset_list

    @Slot(result='QVariantList')
    def getFlatDatasetList(self):
        """Get list of datasets with flat data structure (metadata-driven, not name-driven)."""
        flat_datasets = []
        for name, data in self._datasets.items():
            if hasattr(data, 'metadata') and getattr(data.metadata, 'data_type', 'spectral') == 'flat':
                flat_datasets.append(name)
        return flat_datasets

    @Slot(result='QVariantList')
    def getMapList(self):
        """Get list of generated maps with metadata."""
        return [{'id': m['id'], 'title': m['title'], 'path': m['path']} for m in self.maps]

    @Slot(str, result='QVariant')
    def getDataset(self, dataset_name: str):
        """Get a dataset by name for use in Map Editor linking."""
        if dataset_name in self._datasets:
            return self._datasets[dataset_name]
        return None

    @Slot(result='QVariantList')
    def getDatasetListWithInfo(self):
        """
        Get list of datasets with additional info for Map Editor dropdown.
        Prioritizes truncated datasets, then regular spectral datasets.
        Excludes integrated datasets since they don't contain actual spectra (just datapoints).
        Includes discretized datasets.
        """
        dataset_info = []
        for name, data in self._datasets.items():
            # Check if this is an integrated dataset (has intervals in additional_info)
            # These don't contain actual spectra, just integrated values - exclude them
            is_integrated = 'intervals' in data.metadata.additional_info
            if is_integrated:
                continue  # Skip integrated datasets - they don't have spectra to display

            # Check for discretized datasets
            is_discretized = 'discretized' in name.lower() or 'Discretized' in name

            info = {
                'name': name,
                'num_spectra': data.num_spectra,
                'num_points': data.num_points,
                'independent_var': data.independent_var_name,
                'is_truncated': 'truncated' in name.lower() or 'T_' in name,
                'is_discretized': is_discretized,
                'is_integrated': False,  # We've excluded integrated datasets
                'dimensions': list(data.metadata.dimensions)
            }
            dataset_info.append(info)

        # Sort: truncated first, then discretized, then regular, then alphabetically
        # Priority: truncated spectral > discretized > regular spectral
        dataset_info.sort(key=lambda x: (
            not x['is_truncated'],  # Truncated first
            not x['is_discretized'],  # Discretized second
            x['name']
        ))
        return dataset_info

    @Slot(result='QVariantList')
    def getOutputList(self):
        """Get list of output files with metadata."""
        return [{'id': o['id'], 'tool': o['tool'], 'path': o['path'], 'filename': Path(o['path']).name}
                for o in self.output_files]

    @Slot(str, result='QVariantList')
    def loadIntervalsFromFile(self, file_path: str) -> list:
        """
        Load intervals from a Peak Finder JSON file.

        Parameters:
        -----------
        file_path : str
            Path to Intervals_*.json file from Peak Finder

        Returns:
        --------
        list of [start, end] intervals
        """
        try:
            import json
            with open(file_path, 'r') as f:
                data = json.load(f)

            intervals = data.get('intervals', [])
            logger.info(f"Loaded {len(intervals)} intervals from {file_path}")
            return intervals

        except Exception as e:
            logger.error(f"Error loading intervals from {file_path}: {e}")
            self.errorOccurred.emit("Load Error", f"Could not load intervals: {e}")
            return []

    @Slot(str)
    def openMap(self, map_id: str):
        """Load a map into the Map Editor tab.

        Three resolution paths, in order:

        1. **In-memory map** (``self._maps_inmem``) — preferred when present.
           Emits :attr:`loadMapInEditorById` so the editor consumes the
           ``MultiChannelMap`` directly without disk I/O.

        2. **On-disk path** (``self.maps[map_id].path``) — when the file
           actually exists at one of the supported extensions, emits the
           legacy :attr:`loadMapInEditor` signal with the resolved path.

        3. **Failure** — neither available: emit :attr:`errorOccurred` so
           the user gets a toast (replaces the previous silent
           ``logger.warning`` that caused the broken double-click).
        """
        if map_id in self._maps_inmem:
            self.loadMapInEditorById.emit(map_id)
            logger.info(f"Requested in-memory map load in editor: {map_id}")
            return

        for map_info in self.maps:
            if map_info['id'] == map_id:
                map_path = Path(map_info['path'])
                for ext in ['.tiff', '.tif', '.png', '.gsf', '']:
                    check_path = map_path.with_suffix(ext) if ext else map_path
                    if check_path.exists():
                        self.loadMapInEditor.emit(str(check_path))
                        logger.info(f"Requested map load in editor: {check_path}")
                        return
                msg = (f"Map '{map_info['title']}' has no on-disk file "
                       f"and no in-memory backing.")
                logger.warning(msg)
                self.errorOccurred.emit("Map Open Failed", msg)
                return

        msg = f"Map id not found: {map_id}"
        logger.warning(msg)
        self.errorOccurred.emit("Map Open Failed", msg)

    @Slot(str)
    def requestLoadMapInEditor(self, map_path: str):
        """Request to load a map file in the Map Editor (callable from QML)."""
        self.loadMapInEditor.emit(map_path)
        logger.info(f"Requested map load in editor: {map_path}")

    @Slot(str, result='QVariant')
    def getInMemoryMap(self, map_id: str):
        """Return the in-memory MultiChannelMap for ``map_id``, or ``None``.

        Used by :class:`MapEditorBackend.loadMapById` to pull the map data
        directly without touching disk.
        """
        return self._maps_inmem.get(map_id)

    # ------------------------------------------------------------------
    # Image entity slots (open / list / convert / persist)
    # ------------------------------------------------------------------

    def _images_dir(self) -> Path:
        """Return the directory where image entities are saved as TIFFs.

        Prefers ``<project_outputs>/images/`` so images travel with the
        project. Falls back to a per-process temp directory when no
        project is open yet (still openable by the OS).
        """
        if self._output_base_dir is not None:
            d = Path(self._output_base_dir) / "images"
        else:
            if not hasattr(self, "_tmp_images_dir") or self._tmp_images_dir is None:
                self._tmp_images_dir = Path(
                    tempfile.mkdtemp(prefix="trans_images_")
                )
            d = self._tmp_images_dir
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _pixel_scale_tiff_kwargs(image: "ImageData") -> Dict[str, Any]:
        """Build tifffile kwargs for writing a viewer-friendly TIFF.

        Three things are bundled here so every TIFF we emit is openable
        by macOS Preview / Adobe / Fiji without modification:

        1. **Pixel-scale tags** (when the image carries calibration):
           ``XResolution`` / ``YResolution`` as pixels-per-unit, with
           ``ResolutionUnit=NONE`` and an ImageJ-style ``description``
           carrying ``unit=…`` so Fiji picks up the physical scale.
           The rational is encoded with a fixed denominator (1e6) so we
           don't saturate the uint32 numerator on small pixel sizes
           (~0.12 µm/px would otherwise blow up to 4 294 967 295 / N
           and trip strict TIFF parsers).
        2. **Multi-strip layout** (``rowsperstrip=64``): single-strip
           TIFFs covering tens of megabytes break macOS Preview, which
           tries to read the whole strip into memory in one go.
        3. **``metadata=None``** suppresses tifffile's auto
           ``{"shape": [...]}`` tag — that tag duplicates
           ``ImageDescription`` (resulting in two tag-270 entries),
           which is non-standard and confuses some viewers.

        Returns the kwargs dict; safe to ``**``-splat into
        ``tifffile.imwrite``.
        """
        kwargs: Dict[str, Any] = {
            "metadata": None,
            "rowsperstrip": 64,
        }
        meta = getattr(image, "metadata", None)
        ai = getattr(meta, "additional_info", None) or {}
        ps = ai.get("pixel_size")
        if not isinstance(ps, dict):
            return kwargs
        try:
            dx = float(ps.get("dx") or 0.0)
            dy = float(ps.get("dy") or 0.0)
        except (TypeError, ValueError):
            return kwargs
        if dx <= 0 or dy <= 0:
            return kwargs
        unit = str(ps.get("unit") or "µm").strip()
        ij_unit = {
            "µm": "micron", "um": "micron", "micron": "micron",
            "microns": "micron",
            "nm": "nm", "mm": "mm", "cm": "cm", "m": "meter",
        }.get(unit, unit)

        # Fixed-denominator rational keeps the encoding readable on any
        # parser (and avoids tifffile's saturation behaviour on tiny
        # pixel sizes).
        denom = 1_000_000
        x_num = int(round((1.0 / dx) * denom))
        y_num = int(round((1.0 / dy) * denom))

        kwargs.update({
            "resolution": ((x_num, denom), (y_num, denom)),
            "resolutionunit": "NONE",
            "description": f"ImageJ=1.54p\nunit={ij_unit}\n",
        })
        return kwargs

    def _save_image_to_tiff(self, image: "ImageData") -> Optional[str]:
        """Persist ``image`` as a TIFF on disk and return its absolute path.

        Returns the existing ``image.file_path`` when one is already set
        (avoids re-writing the same data when an image is registered twice).
        """
        if getattr(image, "file_path", None):
            try:
                if Path(image.file_path).exists():
                    return image.file_path
            except Exception:
                pass
        try:
            import tifffile
        except ImportError:
            logger.error("tifffile is required to save image entities")
            return None
        safe = self._sanitize_filename(image.name or image.id) or image.id
        target = self._images_dir() / f"{image.id}_{safe}.tiff"
        try:
            tifffile.imwrite(
                str(target), image.array,
                **self._pixel_scale_tiff_kwargs(image),
            )
        except Exception as e:
            logger.error("Could not write %s: %s", target, e)
            return None
        image.file_path = str(target)
        return image.file_path

    def _absorb_dataset_images(self, result: dict):
        """Pull images out of any loaded dataset's metadata into the registry.

        Each absorbed image is saved as a TIFF under
        ``<project_outputs>/images/`` so the project browser's double-click
        handler can hand the file straight to the OS image viewer.
        """
        seen_ids = set()
        for ds_name, sd in result.get('datasets', {}).items():
            if not hasattr(sd, 'metadata'):
                continue
            entries = sd.metadata.additional_info.get('images') or []
            for name, image in entries:
                if not isinstance(image, ImageData):
                    continue
                if image.id in seen_ids:
                    continue  # same image referenced from multiple datasets
                seen_ids.add(image.id)
                if image.id in self._images:
                    continue
                if name and name != image.name:
                    image.name = name
                # Persist to disk so the OS can open it directly.
                self._save_image_to_tiff(image)
                self._images[image.id] = image
                self.imageAdded.emit(image.id, image.name)
                logger.info(
                    "Registered image %s (%r) from dataset %r → %s",
                    image.id, image.name, ds_name, image.file_path,
                )

    @Slot(str)
    def openImage(self, image_id: str):
        """Open an embedded image-viewer window for ``image_id``.

        Default action — emits ``openImageEmbedded`` so QML opens an
        embedded ``ImageWindowContent`` window that pulls the QImage from
        the registered ``image://trans/<id>`` provider. The image is also
        written to disk as a TIFF so :meth:`openImageInOS` is available
        from the right-click menu when the user prefers Preview / external
        viewers.
        """
        image = self._images.get(image_id)
        if image is None:
            logger.warning("openImage: unknown image_id %r", image_id)
            self.errorOccurred.emit(
                "Image Open Failed", f"Image not found: {image_id}",
            )
            return
        # Save to TIFF eagerly so the file is ready when the user picks
        # "Open in OS viewer" later (and so projects persist nicely).
        if not image.file_path or not Path(image.file_path).exists():
            self._save_image_to_tiff(image)
        title = image.name or "Image"
        self.openImageEmbedded.emit(title, image_id)
        logger.info("Requested image open: %s (%r)", image_id, title)

    @Slot(str)
    def openImageInOS(self, image_id: str):
        """Open ``image_id`` with the OS default image viewer (fallback)."""
        image = self._images.get(image_id)
        if image is None:
            self.errorOccurred.emit(
                "Image Open Failed", f"Image not found: {image_id}",
            )
            return
        path = image.file_path
        if not path or not Path(path).exists():
            path = self._save_image_to_tiff(image)
        if not path:
            self.errorOccurred.emit(
                "Image Open Failed",
                f"Could not write image '{image.name}' to disk.",
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self.errorOccurred.emit(
                "Image Open Failed", f"OS could not open {path}",
            )
            return
        logger.info("Opened image %s via OS: %s", image_id, path)

    @Slot(result='QVariantList')
    def getImageList(self):
        """Get list of image entities for the project browser."""
        out: List[Dict[str, Any]] = []
        for image_id, img in self._images.items():
            out.append({
                'id': image_id,
                'name': img.name,
                'mode': img.mode.value,
                'width': img.width,
                'height': img.height,
                'source': img.metadata.source,
            })
        return out

    @Slot(str, result='QVariant')
    def getImage(self, image_id: str):
        """Return the :class:`ImageData` for the given id, or ``None``."""
        return self._images.get(image_id)

    @Slot(str)
    def addImageFromFile(self, file_path: str):
        """Load an image from disk and register it as a project entity.

        ``ImageData.from_file`` already records the source path in
        ``image.file_path``, so opening the entity later just re-opens
        the original file with the OS viewer.
        """
        path = Path(str(file_path).replace("file://", ""))
        try:
            image = ImageData.from_file(path)
        except Exception as e:
            logger.error("Could not load image %s: %s", path, e)
            self.errorOccurred.emit(
                "Image Load Failed", f"Could not load {path.name}: {e}",
            )
            return
        self._images[image.id] = image
        self.imageAdded.emit(image.id, image.name)
        logger.info("Loaded image from file: %s (%s)", path, image.id)

    @Slot(str)
    def deleteImage(self, image_id: str):
        """Remove an image entity from the project."""
        if image_id in self._images:
            deleted_image = self._images[image_id]
            del self._images[image_id]
            self.imageDeleted.emit(image_id)
            logger.info("Deleted image %s", image_id)

            # Register undo command (image entities live in memory).
            if not self._suppress_undo:
                def undo_delete():
                    self._images[image_id] = deleted_image
                    self.imageAdded.emit(image_id, deleted_image.name)
                    self.projectModifiedChanged.emit(True)

                def redo_delete():
                    self._suppress_undo = True
                    try:
                        self.deleteImage(image_id)
                    finally:
                        self._suppress_undo = False

                self._undo_manager.push(UndoCommand(
                    description=f"Delete image '{deleted_image.name}'",
                    undo_fn=undo_delete,
                    redo_fn=redo_delete,
                ))

    @Slot(str, str)
    def renameImage(self, image_id: str, new_name: str):
        """Rename an image entity."""
        image = self._images.get(image_id)
        if image is None:
            return
        image.name = new_name
        self.imageRenamed.emit(image_id, new_name)

    @Slot(str, int, result='QVariantList')
    def getImageHistogram(self, image_id: str, bins: int = 64):
        """Return histogram counts for ``image_id`` as a flat list.

        Computed on the Python side via :meth:`ImageData.histogram`. QML
        renders the bars in the side panel. Returns empty list when the
        image isn't found.
        """
        image = self._images.get(image_id)
        if image is None:
            return []
        try:
            counts, _edges = image.histogram(bins=int(bins))
        except Exception as e:
            logger.warning("getImageHistogram failed for %s: %s", image_id, e)
            return []
        return [int(c) for c in counts]

    @Slot(str, int, result='QVariantMap')
    def getImageHistogramFull(self, image_id: str, bins: int = 64):
        """Phase 7.4b — richer histogram payload used by the
        interactive level-handle widget.

        Returns ``{counts, dataMin, dataMax}`` so the QML widget can
        map handle pixel positions back to data values. ``counts`` is
        a list of length ``bins``; ``dataMin`` / ``dataMax`` are the
        histogram window. Empty payload when the image isn't found.
        """
        image = self._images.get(image_id)
        if image is None:
            return {}
        try:
            counts, edges = image.histogram(bins=int(bins))
        except Exception as e:
            logger.warning(
                "getImageHistogramFull failed for %s: %s", image_id, e,
            )
            return {}
        return {
            "counts": [int(c) for c in counts],
            "dataMin": float(edges[0]) if len(edges) else 0.0,
            "dataMax": float(edges[-1]) if len(edges) else 1.0,
        }

    @Slot(str, result='QVariantMap')
    def getImageInfo(self, image_id: str):
        """Return image-info record used by the side-panel readout.

        Includes any spatial cursors and pixel calibration the loader
        attached to ``image.metadata.additional_info`` — the viewer uses
        these to render crosshair overlays and a scale-bar legend.
        """
        image = self._images.get(image_id)
        if image is None:
            return {}
        try:
            lo, hi = image.auto_range()
        except Exception:
            lo, hi = 0.0, 1.0
        ai = image.metadata.additional_info or {}
        result = {
            'id': image_id,
            'name': image.name,
            'mode': image.mode.value,
            'width': image.width,
            'height': image.height,
            'is_rgb': image.mode.is_rgb,
            'is_single_channel': image.mode.is_single_channel,
            'auto_min': float(lo),
            'auto_max': float(hi),
            'data_min': float(np.min(image.array)) if image.array.ndim < 3 else 0.0,
            'data_max': float(np.max(image.array)) if image.array.ndim < 3 else 255.0,
        }
        if 'pixel_size' in ai:
            result['pixel_size'] = ai['pixel_size']
        if 'world_bounds' in ai:
            result['world_bounds'] = ai['world_bounds']
        if 'spatial_cursors' in ai:
            result['spatial_cursors'] = ai['spatial_cursors']
        return result

    @staticmethod
    def _apply_affine_inverse(
        affine: Dict[str, Any], wx: float, wy: float,
    ) -> Optional[Tuple[float, float]]:
        """World ``(wx, wy)`` → pixel ``(px, py)`` using a stashed affine."""
        if not isinstance(affine, dict):
            return None
        try:
            wox, woy = affine["world_origin_xy"]
            mox, moy = affine["model_origin_xy"]
            fwd = np.asarray(affine["forward_2x2"], dtype=np.float64)
            inv = np.linalg.inv(fwd)
        except (KeyError, ValueError, TypeError, np.linalg.LinAlgError):
            return None
        local = inv @ np.array([wx - wox, wy - woy], dtype=np.float64)
        return float(local[0] + mox), float(local[1] + moy)

    @staticmethod
    def _apply_affine_forward(
        affine: Dict[str, Any], px: float, py: float,
    ) -> Optional[Tuple[float, float]]:
        """Pixel ``(px, py)`` → world ``(wx, wy)`` using a stashed affine."""
        if not isinstance(affine, dict):
            return None
        try:
            wox, woy = affine["world_origin_xy"]
            mox, moy = affine["model_origin_xy"]
            fwd = np.asarray(affine["forward_2x2"], dtype=np.float64)
        except (KeyError, ValueError, TypeError):
            return None
        world = fwd @ np.array([px - mox, py - moy], dtype=np.float64)
        return float(world[0] + wox), float(world[1] + woy)

    @staticmethod
    def _image_pixel_xy_for_world(
        image: "ImageData", wx: float, wy: float,
    ) -> Optional[Tuple[float, float]]:
        """Map ``(wx, wy)`` world coords → image pixel coords.

        Uses the ``space_transformation_affine`` stashed by the WITec
        loader. Returns ``None`` when the image carries no calibration.
        """
        ai = (image.metadata.additional_info or {}) if image.metadata else {}
        return AppBackend._apply_affine_inverse(
            ai.get("space_transformation_affine"), wx, wy,
        )

    @Slot(str, result='QVariantList')
    def getDatasetOverlaysForImage(self, image_id: str):
        """Find every single-point spectrum compatible with ``image_id``.

        A spectrum is *compatible* when:
        - it shares the same WITec source file stem as ``image_id``,
        - and its acquisition coord, mapped through the image's affine,
          lands inside the image's pixel bounds.

        We deliberately do *not* restrict spectra to a single parent
        image: a single WITec session may produce several images that
        share a stage frame, and the user wants to see overlapping
        spectra on each of them. The dataset-rezero detection happens
        further upstream (datasets get split by stage frame in the
        loader).
        """
        image = self._images.get(image_id)
        if image is None:
            return []
        ai = image.metadata.additional_info or {}
        if "space_transformation_affine" not in ai:
            return []
        orig = getattr(image.metadata, "original_filename", "") or ""
        img_stem = Path(orig).stem if orig else None
        if not img_stem:
            return []

        # WITec-only probe-vs-video calibration: each spectrum's stored
        # ``WorldOrigin`` is actually the *video-cursor / image-center*
        # position in absolute stage µm at the moment of acquisition
        # (not the laser focus). The laser fires at a fixed mechanical
        # offset from the camera optical axis, recorded here as
        # ``(probe_dx, probe_dy) = (X_laser - X_center, Y_laser - Y_center)``.
        # So to display the crosshair at the actual laser hit point we
        # *add* the offset to the wip-stored centre coord. Only WITec
        # data reaches this slot (the ``wip_source_stem`` match guards
        # the loop), so other instruments are untouched.
        try:
            probe_dx = float(self._preferences_manager.getProbeOffsetX())
            probe_dy = float(self._preferences_manager.getProbeOffsetY())
        except Exception:
            probe_dx = probe_dy = 0.0

        w, h = image.width, image.height
        out: List[Dict[str, Any]] = []
        for ds_name, sd in self._datasets.items():
            ds_ai = getattr(sd.metadata, "additional_info", None) or {}
            if ds_ai.get("wip_source_stem") != img_stem:
                continue
            positions = ds_ai.get("acquisition_positions") or []
            captions = ds_ai.get("captions") or []
            for idx, pos in enumerate(positions):
                if not isinstance(pos, dict):
                    continue
                try:
                    # WITec stores the video-cursor (image centre) here.
                    wx_center = float(pos["x_world"])
                    wy_center = float(pos["y_world"])
                except (KeyError, TypeError, ValueError):
                    continue
                # Pixel for the raw wip-stored centre (no offset) — kept
                # so QML can draw a secondary marker for debugging.
                center_pxy = self._image_pixel_xy_for_world(
                    image, wx_center, wy_center,
                )
                # Add the configured laser-vs-centre offset to get the
                # actual laser hit world coord.
                wx = wx_center + probe_dx
                wy = wy_center + probe_dy
                pxy = self._image_pixel_xy_for_world(image, wx, wy)
                if pxy is None:
                    continue
                px, py = pxy
                if not (0.0 <= px <= w and 0.0 <= py <= h):
                    continue
                if center_pxy is None:
                    center_px, center_py = px, py
                else:
                    center_px, center_py = center_pxy
                caption = (
                    captions[idx] if idx < len(captions)
                    else f"spectrum {idx}"
                )
                # Per-spectrum info — when present, prepend ``HH:MM`` to
                # the label so the user can read acquisition order off
                # the legend directly.
                info_list = ds_ai.get("acquisition_info_per_spectrum") or []
                info = info_list[idx] if idx < len(info_list) else None
                start_time = info.get("start_time") if isinstance(info, dict) else None
                label = (
                    f"{start_time} · {caption}" if start_time else caption
                )
                out.append({
                    "type": "crosshair",
                    "dataset_name": ds_name,
                    "spectrum_index": idx,
                    "label": label,
                    "caption": caption,
                    "start_time": start_time,
                    # Primary crosshair = laser-focus pixel (after the
                    # probe-offset correction is added to the stored
                    # image-centre coord).
                    "x_pixel": px,
                    "y_pixel": py,
                    # Wip-stored centre pixel — QML draws a secondary
                    # marker here so the user can see both positions and
                    # debug the offset calibration. Field name kept as
                    # ``x_pixel_laser`` for QML compatibility, but it's
                    # really the *video-centre* pixel now.
                    "x_pixel_laser": center_px,
                    "y_pixel_laser": center_py,
                    # World coords: ``x_world`` is the displayed laser
                    # hit point; ``x_laser_world`` (legacy name) holds
                    # the wip-stored video-centre coord.
                    "x_world": wx,
                    "y_world": wy,
                    "x_laser_world": wx_center,
                    "y_laser_world": wy_center,
                    "unit": pos.get("unit", "µm"),
                })
        return out

    @Slot(str, result='QVariantList')
    def getZoomRegionsForImage(self, image_id: str):
        """Find sibling images that share this image's coordinate frame.

        Two WITec images are only safe to overlay when their stage frame
        is the same. WITec typically rezeros each time it captures a new
        image, but the physical stage often hasn't been moved — so a
        rezero between two images produces *identical* world origins.
        We use that signature: an image B is a valid zoom region of A
        iff B's affine ``world_origin_xy`` matches A's within ~1 µm.

        Each returned entry is the sibling's pixel rectangle on *this*
        image (computed by mapping the sibling's 4 corners through its
        own affine into world coords, then through this image's inverse
        affine into pixel coords). Non-overlapping rectangles are
        dropped.
        """
        parent = self._images.get(image_id)
        if parent is None:
            return []
        p_ai = parent.metadata.additional_info or {}
        p_aff = p_ai.get("space_transformation_affine")
        if not isinstance(p_aff, dict):
            return []
        p_orig = getattr(parent.metadata, "original_filename", "") or ""
        p_stem = Path(p_orig).stem if p_orig else None
        if not p_stem:
            return []
        try:
            p_origin = (float(p_aff["world_origin_xy"][0]),
                        float(p_aff["world_origin_xy"][1]))
        except (KeyError, TypeError, ValueError, IndexError):
            return []
        pw, ph = parent.width, parent.height
        # Tolerance: 1 µm is generous for WITec stages but well below
        # any meaningful image-to-image translation.
        ORIGIN_TOL = 1.0

        out: List[Dict[str, Any]] = []
        for other_id, other in self._images.items():
            if other_id == image_id:
                continue
            o_ai = other.metadata.additional_info or {}
            o_aff = o_ai.get("space_transformation_affine")
            if not isinstance(o_aff, dict):
                continue
            o_orig = getattr(other.metadata, "original_filename", "") or ""
            if Path(o_orig).stem != p_stem:
                continue
            # Same physical stage point? Mismatched world origins mean a
            # rezero happened and the affines are not in the same frame.
            try:
                o_origin = (float(o_aff["world_origin_xy"][0]),
                            float(o_aff["world_origin_xy"][1]))
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            if (abs(o_origin[0] - p_origin[0]) > ORIGIN_TOL
                    or abs(o_origin[1] - p_origin[1]) > ORIGIN_TOL):
                continue
            # Map the other image's 4 corners (its own pixel space) →
            # world → this image's pixel space. A non-skewed affine sends
            # corners to corners, so the bounding box of those 4 points
            # is the zoom rectangle on the parent.
            cw, ch = other.width, other.height
            corners_px = [(0.0, 0.0), (cw, 0.0), (0.0, ch), (cw, ch)]
            mapped: List[Tuple[float, float]] = []
            for (cpx, cpy) in corners_px:
                wxy = self._apply_affine_forward(o_aff, cpx, cpy)
                if wxy is None:
                    mapped = []
                    break
                pxy = self._apply_affine_inverse(p_aff, *wxy)
                if pxy is None:
                    mapped = []
                    break
                mapped.append(pxy)
            if len(mapped) != 4:
                continue
            xs = [m[0] for m in mapped]
            ys = [m[1] for m in mapped]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            # Skip non-overlapping siblings (zoom is entirely outside
            # this image's pixel bounds).
            if x_max < 0 or x_min > pw or y_max < 0 or y_min > ph:
                continue
            # Precise world-space extent of the other image (from its
            # own affine). Width / height in µm via the magnitude of the
            # forward matrix columns × pixel count.
            try:
                fwd = np.asarray(o_aff["forward_2x2"], dtype=np.float64)
                w_um = float(np.linalg.norm(fwd[:, 0])) * cw
                h_um = float(np.linalg.norm(fwd[:, 1])) * ch
            except (KeyError, TypeError, ValueError):
                w_um = h_um = 0.0
            # Image names already carry "name · HH:MM · lens" — just
            # append the precise dimensions for the rect-overlay label.
            o_info = o_ai.get("acquisition_info") or {}
            start_time = o_info.get("start_time") if isinstance(o_info, dict) else None
            base_label = other.name
            dims = (
                f"{w_um:.0f}×{h_um:.0f} µm" if w_um and h_um else ""
            )
            label = f"{base_label} · {dims}" if dims else base_label
            out.append({
                "type": "rect",
                "image_id": other_id,
                "label": label,
                "name": base_label,
                "start_time": start_time,
                "x_min_pixel": x_min,
                "y_min_pixel": y_min,
                "x_max_pixel": x_max,
                "y_max_pixel": y_max,
                "width_um": w_um,
                "height_um": h_um,
                "corner_pixels": mapped,
            })
        return out

    @Slot(str, 'QVariantList', str, str, result=str)
    def exportImageWithOverlays(
        self,
        image_id: str,
        overlays,
        file_path: str,
        fmt: str = "tiff",
    ) -> str:
        """Save ``image_id`` with crosshair overlays baked into pixels.

        ``overlays`` is a list of dicts with ``x_pixel``, ``y_pixel``,
        ``label``, and a CSS-style ``color`` string. ``fmt`` is ``"tiff"``
        or ``"png"``. TIFF output carries the pixel-scale tags from
        :meth:`_pixel_scale_tiff_kwargs`. Returns the saved path, or empty
        string on failure.
        """
        image = self._images.get(image_id)
        if image is None:
            self.errorOccurred.emit(
                "Export Failed", f"Image not found: {image_id}",
            )
            return ""
        try:
            from PIL import Image as PILImage, ImageDraw, ImageFont
        except ImportError:
            self.errorOccurred.emit(
                "Export Failed", "Pillow is required for image export.",
            )
            return ""

        # Convert array → PIL RGB so we can draw coloured overlays even on
        # single-channel sources. The display range mirrors auto_range so
        # the saved frame looks like what the user sees.
        if image.mode.is_rgb:
            pil = PILImage.fromarray(image.array[..., :3].astype(np.uint8), "RGB")
        else:
            lo, hi = image.auto_range()
            arr = np.clip(
                (image.array.astype(np.float32) - lo) / max(hi - lo, 1e-9),
                0.0, 1.0,
            )
            pil = PILImage.fromarray((arr * 255).astype(np.uint8), "L").convert("RGB")

        draw = ImageDraw.Draw(pil)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        arm = 20  # px arm length, mirrors the QML overlay
        for ov in (overlays or []):
            color = ov.get("color") or "#5BCEFA"
            label = (ov.get("label") or "").strip()
            kind = (ov.get("type") or "crosshair").lower()
            if kind == "rect":
                try:
                    x0 = float(ov.get("x_min_pixel"))
                    y0 = float(ov.get("y_min_pixel"))
                    x1 = float(ov.get("x_max_pixel"))
                    y1 = float(ov.get("y_max_pixel"))
                except (TypeError, ValueError):
                    continue
                draw.rectangle(
                    [(x0, y0), (x1, y1)],
                    outline=color, width=2,
                )
                if label and font is not None:
                    draw.text(
                        (x0 + 4, y0 + 4),
                        label, fill=color, font=font,
                    )
                continue
            try:
                px = float(ov.get("x_pixel"))
                py = float(ov.get("y_pixel"))
            except (TypeError, ValueError):
                continue
            draw.line([(px - arm, py), (px + arm, py)], fill=color, width=2)
            draw.line([(px, py - arm), (px, py + arm)], fill=color, width=2)
            draw.ellipse(
                [(px - 3, py - 3), (px + 3, py + 3)],
                outline=color, width=2,
            )
            if label and font is not None:
                draw.text(
                    (px + arm + 4, py - arm),
                    label, fill=color, font=font,
                )

        out = Path(str(file_path).replace("file://", ""))
        out.parent.mkdir(parents=True, exist_ok=True)
        fmt_norm = (fmt or "tiff").lower().lstrip(".")
        try:
            if fmt_norm in ("tif", "tiff"):
                # Save via tifffile so the pixel-scale tags survive.
                import tifffile
                tifffile.imwrite(
                    str(out), np.array(pil),
                    **self._pixel_scale_tiff_kwargs(image),
                )
            else:
                pil.save(str(out), format=fmt_norm.upper())
        except Exception as e:
            logger.error("Export with overlays failed: %s", e)
            self.errorOccurred.emit(
                "Export Failed", f"Could not write {out.name}: {e}",
            )
            return ""
        logger.info(
            "Exported %s with %d overlays → %s",
            image_id, len(overlays or []), out,
        )
        return str(out)

    @Slot(str, int, int, int, int, result=str)
    def cropImage(self, image_id: str, x0: int, y0: int, x1: int, y1: int) -> str:
        """Crop ``image_id`` to ``[x0..x1, y0..y1)`` and register the result.

        The new entity has its own id; the original is left untouched.
        Returns the new id, or empty string on failure.
        """
        image = self._images.get(image_id)
        if image is None:
            self.errorOccurred.emit(
                "Crop Failed", f"Image not found: {image_id}",
            )
            return ""
        try:
            cropped = image.crop(int(x0), int(y0), int(x1), int(y1))
        except ValueError as e:
            self.errorOccurred.emit("Crop Failed", str(e))
            return ""
        # Persist to disk and register.
        self._save_image_to_tiff(cropped)
        self._images[cropped.id] = cropped
        self.imageAdded.emit(cropped.id, cropped.name)
        logger.info(
            "Cropped image %s → %s (%d×%d, file=%s)",
            image_id, cropped.id, cropped.width, cropped.height,
            cropped.file_path,
        )
        return cropped.id

    # ------------------------------------------------------------------
    # Note entity slots
    # ------------------------------------------------------------------

    def _notes_dir(self) -> Path:
        """Where note entities are saved as ``.txt`` files."""
        if self._output_base_dir is not None:
            d = Path(self._output_base_dir) / "notes"
        else:
            if not hasattr(self, "_tmp_notes_dir") or self._tmp_notes_dir is None:
                self._tmp_notes_dir = Path(
                    tempfile.mkdtemp(prefix="trans_notes_")
                )
            d = self._tmp_notes_dir
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _save_note_to_txt(self, note: dict) -> Optional[str]:
        """Persist ``note`` to disk. Returns the absolute path.

        When the note carries a raw RTF blob (``rtf_bytes``, set by the
        WITec loader for ``TDText`` entries), write a ``.rtf`` so the OS
        opens TextEdit / WordPad with proper formatting. Otherwise fall
        back to a ``.txt`` with a small caption + source header.
        """
        existing = note.get('file_path')
        if existing and Path(existing).exists():
            return existing
        safe = self._sanitize_filename(note.get('name', 'note')) or note.get('id', 'note')
        rtf_bytes = note.get('rtf_bytes') or b''
        if rtf_bytes:
            target = self._notes_dir() / f"{note.get('id', 'note')}_{safe}.rtf"
            try:
                target.write_bytes(rtf_bytes)
            except Exception as e:
                logger.error("Could not write RTF note %s: %s", target, e)
                return None
        else:
            target = self._notes_dir() / f"{note.get('id', 'note')}_{safe}.txt"
            body = note.get('text', '') or ''
            header = (
                f"# {note.get('name', 'Note')}\n"
                f"# Source: {note.get('source', 'unknown')}\n\n"
            )
            try:
                target.write_text(header + body, encoding='utf-8')
            except Exception as e:
                logger.error("Could not write note %s: %s", target, e)
                return None
        note['file_path'] = str(target)
        return note['file_path']

    def _absorb_dataset_notes(self, result: dict):
        """Pull notes out of any loaded dataset's metadata into the registry.

        Each absorbed note is saved as a ``.txt`` file under
        ``<project_outputs>/notes/`` so double-click opens it in the OS
        default text editor (TextEdit on macOS, Notepad on Windows).
        """
        seen = set()
        for ds_name, sd in result.get('datasets', {}).items():
            if not hasattr(sd, 'metadata'):
                continue
            entries = sd.metadata.additional_info.get('notes') or []
            for entry in entries:
                if isinstance(entry, str):
                    entry = {'name': 'Note', 'text': entry, 'source': 'unknown'}
                if not isinstance(entry, dict):
                    continue
                if not entry.get('name') and not entry.get('text'):
                    continue
                key = (entry.get('name', ''), entry.get('text', ''))
                if key in seen:
                    continue
                seen.add(key)
                self._note_id_counter += 1
                note_id = f"note_{self._note_id_counter}"
                note = {
                    'id': note_id,
                    'name': entry.get('name', 'Note'),
                    'text': entry.get('text', ''),
                    'source': entry.get('source', 'unknown'),
                }
                if entry.get('rtf_bytes'):
                    note['rtf_bytes'] = entry['rtf_bytes']
                self._save_note_to_txt(note)
                self._notes[note_id] = note
                self.noteAdded.emit(note_id, note['name'])
                logger.info(
                    "Registered note %s (%r) from dataset %r → %s",
                    note_id, note['name'], ds_name, note.get('file_path'),
                )

    @Slot(result='QVariantList')
    def getNotesList(self):
        """Get list of note entities for the project browser."""
        return [
            {
                'id': n['id'],
                'name': n['name'],
                'source': n.get('source', ''),
                'preview': (n.get('text', '')[:60]
                            + ('…' if len(n.get('text', '')) > 60 else '')),
            }
            for n in self._notes.values()
        ]

    @Slot(str, result='QVariantMap')
    def getNote(self, note_id: str):
        """Return the full note record for ``note_id`` (with full text)."""
        return self._notes.get(note_id, {})

    @Slot(str, str, str)
    def addNote(self, name: str, text: str, source: str = "user"):
        """Register a new note entity."""
        self._note_id_counter += 1
        note_id = f"note_{self._note_id_counter}"
        self._notes[note_id] = {
            'id': note_id, 'name': name, 'text': text, 'source': source,
        }
        self.noteAdded.emit(note_id, name)

    @Slot(str)
    def deleteNote(self, note_id: str):
        """Remove a note entity."""
        if note_id in self._notes:
            deleted_note = self._notes[note_id]
            del self._notes[note_id]
            self.noteDeleted.emit(note_id)

            # Register undo command (note entities live in memory).
            if not self._suppress_undo:
                def undo_delete():
                    self._notes[note_id] = deleted_note
                    self.noteAdded.emit(note_id, deleted_note.get('name', 'Note'))
                    self.projectModifiedChanged.emit(True)

                def redo_delete():
                    self._suppress_undo = True
                    try:
                        self.deleteNote(note_id)
                    finally:
                        self._suppress_undo = False

                self._undo_manager.push(UndoCommand(
                    description=f"Delete note '{deleted_note.get('name', 'Note')}'",
                    undo_fn=undo_delete,
                    redo_fn=redo_delete,
                ))

    @Slot(str, str)
    def renameNote(self, note_id: str, new_name: str):
        """Rename a note entity."""
        if note_id in self._notes:
            self._notes[note_id]['name'] = new_name
            self.noteRenamed.emit(note_id, new_name)

    @Slot(str)
    def openNote(self, note_id: str):
        """Open an embedded note-viewer window for ``note_id``.

        Default action — emits ``openNoteEmbedded`` so QML pops a small
        read-only text window. The note is also persisted as ``.txt`` so
        :meth:`openNoteInOS` is available as a fallback (TextEdit / Notepad).
        """
        note = self._notes.get(note_id)
        if note is None:
            self.errorOccurred.emit(
                "Note Open Failed", f"Note not found: {note_id}",
            )
            return
        # Eagerly persist for the OS fallback / project portability.
        if not note.get('file_path') or not Path(note['file_path']).exists():
            self._save_note_to_txt(note)
        title = note.get('name', 'Note')
        body = note.get('text', '') or ''
        if not body.strip():
            body = (
                f"(No body text in this annotation.)\n\n"
                f"Caption: {title}\n"
                f"Source:  {note.get('source', 'unknown')}"
            )
        self.openNoteEmbedded.emit(title, body, note.get('source', ''))
        logger.info("Requested note open: %s (%r)", note_id, title)

    @Slot(str)
    def openNoteInOS(self, note_id: str):
        """Open ``note_id`` with the OS default text editor (fallback)."""
        note = self._notes.get(note_id)
        if note is None:
            self.errorOccurred.emit(
                "Note Open Failed", f"Note not found: {note_id}",
            )
            return
        path = note.get('file_path')
        if not path or not Path(path).exists():
            path = self._save_note_to_txt(note)
        if not path:
            self.errorOccurred.emit(
                "Note Open Failed",
                f"Could not write note '{note.get('name')}' to disk.",
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self.errorOccurred.emit(
                "Note Open Failed", f"OS could not open {path}",
            )
            return
        logger.info("Opened note %s via OS: %s", note_id, path)

    # ------------------------------------------------------------------
    # Spectral-axis unit conversion
    # ------------------------------------------------------------------

    @Slot(str, str, float, str, result=str)
    def convertDatasetAxis(
        self, dataset_name: str, target_unit: str,
        excitation_nm: float = 0.0, new_dataset_name: str = "",
    ) -> str:
        """Create a new dataset with the spectral axis converted to ``target_unit``.

        Parameters
        ----------
        dataset_name
            Existing dataset key in ``self._datasets``.
        target_unit
            Any string accepted by :func:`spectral_axis.parse_unit`
            (``"nm"``, ``"eV"``, ``"cm-1"``, ``"raman_cm-1"``, plus aliases).
        excitation_nm
            Laser excitation wavelength in nm. Required when the source or
            target is Raman-shift; ignored otherwise. Pass ``0`` (or omit)
            for non-Raman conversions.
        new_dataset_name
            Override for the resulting dataset name. Defaults to
            ``f"{source} ({target_unit})"``.

        Returns
        -------
        str
            The name of the newly created dataset, or empty string on
            failure (an ``errorOccurred`` toast is emitted in that case).
        """
        if dataset_name not in self._datasets:
            self.errorOccurred.emit(
                "Conversion Failed", f"Dataset {dataset_name!r} not found.",
            )
            return ""
        sd = self._datasets[dataset_name]

        # Infer the source unit from the metadata (preferred) or the
        # first column's name (fallback).
        info = sd.metadata.additional_info or {}
        source_unit_str = info.get("axis_unit") or sd.metadata.units.get("x") \
            or sd.metadata.units.get("independent")
        if not source_unit_str:
            # Last-ditch: parse the column header (e.g. "Wavelength_nm").
            col = sd.independent_var_name
            if col.endswith("_nm"):
                source_unit_str = "nm"
            elif col.endswith("_eV"):
                source_unit_str = "eV"
            elif col.endswith("_cm-1") and "Raman" in col:
                source_unit_str = "raman_cm-1"
            elif col.endswith("_cm-1"):
                source_unit_str = "cm-1"
            else:
                self.errorOccurred.emit(
                    "Conversion Failed",
                    f"Could not infer the source unit of {dataset_name!r}.",
                )
                return ""

        try:
            source = parse_unit(source_unit_str)
            target = parse_unit(target_unit)
        except ValueError as e:
            self.errorOccurred.emit("Conversion Failed", str(e))
            return ""

        try:
            new_df = convert_dataframe_axis(
                sd.data, source, target,
                excitation_nm=(excitation_nm if excitation_nm > 0 else None),
            )
        except ValueError as e:
            self.errorOccurred.emit("Conversion Failed", str(e))
            return ""

        # Carry forward existing metadata, replacing only what the
        # conversion changed.
        new_meta = SpectralMetadata(
            source_type=sd.metadata.source_type,
            dimensions=sd.metadata.dimensions,
            scan_mode=sd.metadata.scan_mode,
            units={
                **dict(sd.metadata.units or {}),
                "x": target.value,
                "independent": target.value,
            },
            acquisition_date=sd.metadata.acquisition_date,
            additional_info={
                **dict(sd.metadata.additional_info or {}),
                "axis_unit": target.value,
                "converted_from": dataset_name,
                "source_axis_unit": source.value,
                **({"excitation_nm": excitation_nm} if excitation_nm > 0 else {}),
            },
        )
        new_sd = SpectralData(new_df, new_meta, sd.topography)

        out_name = new_dataset_name or f"{dataset_name} ({target.value})"
        self._datasets[out_name] = new_sd
        self._active_dataset = out_name
        self.dataLoaded.emit(out_name)
        logger.info(
            "Converted %s (%s) → %s (%s) — excitation=%s nm",
            dataset_name, source.value, out_name, target.value,
            excitation_nm or "n/a",
        )
        return out_name

    # ------------------------------------------------------------------
    # Multi-peak Gaussian / Lorentzian / pseudo-Voigt fitting
    # ------------------------------------------------------------------

    @Slot(str, str, int, int, int, result='QVariantMap')
    def multiPeakFit(
        self, dataset_name: str, peak_shape: str = "gaussian",
        n_peaks_auto: int = 0, baseline_degree: int = 1,
        spectrum_index: int = 0,
    ):
        """Fit a sum of peaks + polynomial baseline to one column of a dataset.

        Parameters
        ----------
        dataset_name
            Existing dataset key in ``self._datasets``.
        peak_shape
            ``"gaussian"`` / ``"lorentzian"`` / ``"pseudo_voigt"``.
        n_peaks_auto
            Maximum number of peaks for the auto-detector. ``0`` = unlimited.
        baseline_degree
            Polynomial degree for the simultaneously-fitted baseline. ``-1``
            disables the baseline term.
        spectrum_index
            Which spectrum column to fit (0-based, defaults to the first).

        Returns
        -------
        dict
            QVariantMap suitable for QML consumption with keys ``success``,
            ``message``, ``rsq``, ``rss``, ``peaks`` (list of per-peak dicts:
            ``shape``, ``amplitude``, ``center``, ``width``, ``fwhm``, ``eta``),
            ``baseline_coeffs``, ``x``, ``y``, ``fitted``, ``baseline``,
            ``components`` (one curve per peak).
        """
        if dataset_name not in self._datasets:
            self.errorOccurred.emit(
                "Fit Failed", f"Dataset {dataset_name!r} not found.",
            )
            return {"success": False, "message": "Dataset not found"}

        sd = self._datasets[dataset_name]
        if sd.num_spectra == 0:
            return {"success": False, "message": "Dataset has no spectra"}
        idx = max(0, min(spectrum_index, sd.num_spectra - 1))
        x = np.asarray(sd.independent_var, dtype=np.float64)
        y = np.asarray(sd.spectra.values[:, idx], dtype=np.float64)

        try:
            shape = PeakShape(peak_shape)
        except ValueError:
            self.errorOccurred.emit(
                "Fit Failed", f"Unknown peak shape: {peak_shape!r}",
            )
            return {"success": False, "message": f"Unknown peak shape {peak_shape!r}"}

        try:
            res = fit_multipeak(
                x, y, shape=shape, baseline_degree=baseline_degree,
                n_peaks_auto=(n_peaks_auto if n_peaks_auto > 0 else None),
            )
        except Exception as e:
            logger.exception("multiPeakFit failed: %s", e)
            self.errorOccurred.emit("Fit Failed", str(e))
            return {"success": False, "message": str(e)}

        # Optionally surface the fit as a new dataset so the user can plot
        # the fitted curve / residuals alongside the source data. We store
        # everything on a fresh DataFrame (axis + each component + sum).
        try:
            cols = {sd.independent_var_name: x, "Data": y, "Fit": res.fitted_curve,
                    "Baseline": res.baseline_curve, "Residuals": res.residuals}
            for i, comp in enumerate(res.components):
                cols[f"Peak {i+1}"] = comp
            df = pd.DataFrame(cols)
            new_meta = SpectralMetadata(
                source_type=sd.metadata.source_type,
                dimensions=sd.metadata.dimensions,
                scan_mode=sd.metadata.scan_mode,
                units=dict(sd.metadata.units or {}),
                additional_info={
                    **dict(sd.metadata.additional_info or {}),
                    "fit_source": dataset_name,
                    "fit_shape": shape.value,
                    "fit_baseline_degree": baseline_degree,
                    "fit_peak_count": len(res.peaks),
                    "fit_rsq": res.rsq,
                },
            )
            out_name = f"{dataset_name} · fit ({shape.value}, {len(res.peaks)} peaks)"
            self._datasets[out_name] = SpectralData(df, new_meta)
            self.dataLoaded.emit(out_name)
        except Exception as e:
            logger.warning("Could not create fit-result dataset: %s", e)

        return {
            "success": bool(res.success),
            "message": res.message,
            "rsq": float(res.rsq),
            "rss": float(res.rss),
            "peaks": [
                {
                    "shape": p.shape.value,
                    "amplitude": p.amplitude,
                    "center": p.center,
                    "width": p.width,
                    "fwhm": p.fwhm,
                    "eta": p.eta if p.eta is not None else -1.0,
                }
                for p in res.peaks
            ],
            "baseline_coeffs": res.baseline_coeffs.tolist(),
            "x": x.tolist(),
            "y": y.tolist(),
            "fitted": res.fitted_curve.tolist(),
            "baseline": res.baseline_curve.tolist(),
            "components": [c.tolist() for c in res.components],
        }

    @Slot(str, str)
    def convertMapChannelToImage(self, map_id: str, channel_name: str = ""):
        """Right-click "Convert to Image (raw)" — copy a map channel as float image.

        Uses the active channel when ``channel_name`` is empty. The new
        :class:`ImageData` is in :attr:`ImageMode.SINGLE_FLOAT`, so the
        image-viewer's range and colormap controls drive display.

        Resolution order:

        1. ``self._maps_inmem[map_id]`` — preferred, no disk I/O.
        2. The map's on-disk TIFF (``self.maps[*].path``) loaded via
           ``tifffile``. This makes converted-back maps and project-loaded
           maps round-trippable without going through the map editor first.
        """
        title = next(
            (m['title'] for m in self.maps if m['id'] == map_id),
            f"Map {map_id}",
        )

        # ----- Path 1: in-memory MultiChannelMap ------------------------
        mcm = self._maps_inmem.get(map_id)
        if mcm is not None:
            channel = None
            if channel_name and hasattr(mcm, 'channels'):
                ch_dict = mcm.channels
                channel = ch_dict.get(channel_name) if hasattr(ch_dict, 'get') else None
            if channel is None:
                channel = getattr(mcm, 'active_channel', None)
            if channel is None or not hasattr(channel, 'data'):
                self.errorOccurred.emit(
                    "Conversion Failed", "Map has no readable channel."
                )
                return
            image = ImageData.from_map_channel(
                channel.data, map_name=title,
                channel_name=getattr(channel, 'name', channel_name or "channel"),
            )
            self._save_image_to_tiff(image)
            self._images[image.id] = image
            self.imageAdded.emit(image.id, image.name)
            logger.info("Converted in-memory map %s → image %s (%s)",
                        map_id, image.id, image.file_path)
            return

        # ----- Path 2: on-disk TIFF -------------------------------------
        map_info = next((m for m in self.maps if m['id'] == map_id), None)
        if map_info is None:
            self.errorOccurred.emit(
                "Conversion Failed", f"Map {map_id} is unknown.",
            )
            return
        path = Path(map_info.get('path', ''))
        if not path.exists():
            for ext in ['.tiff', '.tif', '.png', '.gsf']:
                candidate = path.with_suffix(ext)
                if candidate.exists():
                    path = candidate
                    break
        if not path.exists():
            self.errorOccurred.emit(
                "Conversion Failed",
                f"Map '{title}' has no on-disk file at {map_info.get('path', '<unknown>')}.",
            )
            return
        try:
            import tifffile
            data = tifffile.imread(str(path))
        except Exception as e:
            self.errorOccurred.emit(
                "Conversion Failed",
                f"Could not read map file {path.name}: {e}",
            )
            return
        if data.ndim == 3:
            # Multi-page TIFF: pick the named page if requested, else the first.
            data = data[0]
        if data.ndim != 2:
            self.errorOccurred.emit(
                "Conversion Failed",
                f"Map {path.name} has unexpected shape {data.shape}.",
            )
            return
        image = ImageData.from_map_channel(
            data, map_name=title,
            channel_name=channel_name or path.stem,
        )
        self._save_image_to_tiff(image)
        self._images[image.id] = image
        self.imageAdded.emit(image.id, image.name)
        logger.info("Converted on-disk map %s → image %s (from %s, saved %s)",
                    map_id, image.id, path, image.file_path)

    @Slot(str)
    def convertImageToMap(self, image_id: str):
        """Right-click "Convert to Map (TIFF)".

        Writes the image as a single-channel TIFF inside the project's
        ``_converted_maps`` directory and registers it as a regular map.

        - Single-channel images (GRAY_U8 / GRAY_U16 / SINGLE_FLOAT) round-trip
          as-is (pixel-exact).
        - RGB / RGBA images are converted to grayscale via the standard
          luminance formula (``0.299·R + 0.587·G + 0.114·B``) so the map
          editor — which only displays single-channel maps — can show them.
          Alpha is ignored.

        Spatial metadata (``pixel_size``, ``world_bounds``,
        ``spatial_cursors``) is also persisted to a sidecar JSON next to
        the TIFF so the map editor can render the WITec-saved crosshair on
        top of the map.
        """
        image = self._images.get(image_id)
        if image is None:
            self.errorOccurred.emit(
                "Conversion Failed", f"Image not found: {image_id}",
            )
            return
        try:
            import tifffile
        except ImportError:
            self.errorOccurred.emit(
                "Conversion Failed", "tifffile is required to write TIFF maps.",
            )
            return

        if self._output_base_dir is None:
            self.errorOccurred.emit(
                "Conversion Failed",
                "No project is open; create or open a project first.",
            )
            return

        # ----- Pixel-data conversion -----------------------------------
        arr = image.array
        if image.mode.is_single_channel:
            map_data = arr
        elif image.mode.is_rgb:
            # Convert to grayscale via Rec. 601 luminance. Result is uint8
            # for RGB(A) inputs to mirror the original dynamic range; the
            # WITec optical frames are typically 8-bit per channel.
            rgb = arr[..., :3].astype(np.float32)
            luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
                    + 0.114 * rgb[..., 2])
            map_data = np.clip(luma, 0, 255).astype(np.uint8)
        else:
            self.errorOccurred.emit(
                "Conversion Failed",
                f"Image mode {image.mode.value!r} not convertible to a map.",
            )
            return

        out_dir = self._output_base_dir / "_converted_maps"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = self._sanitize_filename(image.name) or image_id
        out_path = out_dir / f"{safe}.tiff"
        tifffile.imwrite(
            str(out_path), map_data,
            **self._pixel_scale_tiff_kwargs(image),
        )

        # ----- Spatial sidecar -----------------------------------------
        # Persist pixel_size / world_bounds / spatial_cursors so the map
        # editor can show the WITec crosshair next to the converted map.
        sidecar = {}
        ai = image.metadata.additional_info or {}
        for key in ("pixel_size", "world_bounds", "spatial_cursors"):
            if key in ai:
                sidecar[key] = ai[key]
        if image.metadata.pixel_size_nm:
            sidecar.setdefault(
                "pixel_size_nm",
                list(image.metadata.pixel_size_nm),
            )
        sidecar_path = out_path.with_suffix(".meta.json")
        if sidecar:
            try:
                import json
                sidecar_path.write_text(
                    json.dumps(sidecar, indent=2), encoding="utf-8",
                )
            except Exception as e:
                logger.warning(
                    "Could not write map sidecar %s: %s", sidecar_path, e,
                )

        from datetime import datetime
        self._map_id_counter += 1
        map_id = f"map_{self._map_id_counter}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.maps.append({
            'id': map_id,
            'title': image.name,
            'path': str(out_path),
            'timestamp': timestamp,
            'sidecar': str(sidecar_path) if sidecar else "",
            'source_image_id': image_id,
        })
        self.mapCreated.emit(map_id, image.name)
        logger.info(
            "Converted image %s → map %s (%s)%s",
            image_id, map_id, out_path,
            f" + sidecar with {list(sidecar)}" if sidecar else "",
        )

    @Slot(str)
    def setActiveDataset(self, dataset_name: str):
        """Set the active dataset."""
        if dataset_name in self._datasets:
            old_value = self._active_dataset
            self._active_dataset = dataset_name
            if old_value != dataset_name:
                self.activeDatasetChanged.emit(dataset_name)
            logger.info(f"Active dataset: {dataset_name}")
        else:
            logger.warning(f"Dataset not found: {dataset_name}")

    @Slot(str, result='QVariantMap')
    def getDatasetInfo(self, dataset_name: str):
        """Get information about a dataset."""
        if dataset_name not in self._datasets:
            logger.warning(f"getDatasetInfo() called for non-existent dataset: {dataset_name}")
            return {}

        data = self._datasets[dataset_name]
        info = {
            'name': dataset_name,
            'type': data.metadata.source_type,
            'dimensions': list(data.metadata.dimensions),
            'num_spectra': data.num_spectra,
            'num_points': data.num_points,
            'independent_var': data.independent_var_name
        }
        logger.debug(f"getDatasetInfo({dataset_name}): {info}")
        return info

    @Slot(str, result=bool)
    def deleteDataset(self, dataset_name: str) -> bool:
        """Delete a dataset from the project.

        Args:
            dataset_name: Name of the dataset to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        if dataset_name not in self._datasets:
            logger.warning(f"Cannot delete: dataset '{dataset_name}' not found")
            return False

        # Capture state for undo before deleting
        deleted_data = self._datasets[dataset_name]
        was_active = self._active_dataset == dataset_name

        # Remove from datasets
        del self._datasets[dataset_name]
        logger.info(f"Deleted dataset: {dataset_name}")

        # If this was the active dataset, clear it
        if self._active_dataset == dataset_name:
            self._active_dataset = None

        # Emit signal for UI update
        self.datasetDeleted.emit(dataset_name)
        self.projectModifiedChanged.emit(True)

        # Register undo command
        if not self._suppress_undo:
            def undo_delete():
                self._datasets[dataset_name] = deleted_data
                if was_active:
                    self._active_dataset = dataset_name
                self.dataLoaded.emit(dataset_name)
                self.projectModifiedChanged.emit(True)

            def redo_delete():
                self._suppress_undo = True
                try:
                    self.deleteDataset(dataset_name)
                finally:
                    self._suppress_undo = False

            self._undo_manager.push(UndoCommand(
                description=f"Delete '{dataset_name}'",
                undo_fn=undo_delete,
                redo_fn=redo_delete
            ))

        return True

    @Slot(str, str, result=bool)
    def renameDataset(self, old_name: str, new_name: str) -> bool:
        """Rename a dataset in the project.

        Args:
            old_name: Current name of the dataset
            new_name: New name for the dataset

        Returns:
            True if renamed successfully, False otherwise
        """
        # Validate inputs
        if not old_name or not new_name:
            logger.warning("Cannot rename: empty name provided")
            return False

        if old_name not in self._datasets:
            logger.warning(f"Cannot rename: dataset '{old_name}' not found")
            return False

        if new_name in self._datasets:
            logger.warning(f"Cannot rename: dataset '{new_name}' already exists")
            return False

        # Perform the rename
        self._datasets[new_name] = self._datasets.pop(old_name)
        logger.info(f"Renamed dataset: {old_name} -> {new_name}")

        # Update active dataset if it was renamed
        if self._active_dataset == old_name:
            self._active_dataset = new_name

        # Emit signal for UI update
        self.datasetRenamed.emit(old_name, new_name)
        self.projectModifiedChanged.emit(True)

        # Register undo command
        if not self._suppress_undo:
            def undo_rename():
                if new_name in self._datasets:
                    self._datasets[old_name] = self._datasets.pop(new_name)
                    if self._active_dataset == new_name:
                        self._active_dataset = old_name
                    self.datasetRenamed.emit(new_name, old_name)
                    self.projectModifiedChanged.emit(True)

            def redo_rename():
                if old_name in self._datasets:
                    self._suppress_undo = True
                    try:
                        self.renameDataset(old_name, new_name)
                    finally:
                        self._suppress_undo = False

            self._undo_manager.push(UndoCommand(
                description=f"Rename '{old_name}' \u2192 '{new_name}'",
                undo_fn=undo_rename,
                redo_fn=redo_rename
            ))

        return True

    # ========================================================================
    # Delete/Rename for Maps, Tables, Graphs, Outputs
    # ========================================================================

    @Slot(str, result=bool)
    def deleteMap(self, map_path: str) -> bool:
        """Delete a map file and its associated datasets.

        Args:
            map_path: Path to the map file to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            path = Path(map_path)
            map_name = path.stem  # Get map name without extension

            if path.exists():
                path.unlink()
                logger.info(f"Deleted map: {map_path}")

                # Also delete related files (colormap, CSV, TIFF variants)
                related_patterns = [
                    f"{map_name}_colormap.png",
                    f"{map_name}.csv",
                    f"{map_name}.tiff",
                    f"{map_name}.tif",
                ]
                for pattern in related_patterns:
                    related_path = path.with_name(pattern)
                    if related_path.exists():
                        related_path.unlink()
                        logger.info(f"Deleted related file: {related_path}")

                # Remove from internal maps dict if present
                for map_id, stored_path in list(self.maps.items()):
                    if stored_path == map_path or str(stored_path) == map_path:
                        del self.maps[map_id]
                        break

                # Clean up associated datasets
                # Look for datasets that reference this map in their name
                datasets_to_delete = []
                for dataset_name in list(self._datasets.keys()):
                    # Check if dataset name contains map name pattern
                    if map_name in dataset_name:
                        datasets_to_delete.append(dataset_name)
                        logger.info(f"Found associated dataset: {dataset_name}")

                # Delete the associated datasets
                for dataset_name in datasets_to_delete:
                    del self._datasets[dataset_name]
                    self.datasetDeleted.emit(dataset_name)
                    logger.info(f"Deleted associated dataset: {dataset_name}")

                self.mapDeleted.emit(map_path)
                self.projectModifiedChanged.emit(True)
                return True
            else:
                logger.warning(f"Map file not found: {map_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting map: {e}")
            return False

    @Slot(str, str, result=bool)
    def renameMap(self, old_path: str, new_name: str) -> bool:
        """Rename a map file.

        Args:
            old_path: Current path to the map file
            new_name: New name for the map (without extension)

        Returns:
            True if renamed successfully, False otherwise
        """
        try:
            old_file = Path(old_path)
            if not old_file.exists():
                logger.warning(f"Map file not found: {old_path}")
                return False

            new_file = old_file.parent / f"{new_name}{old_file.suffix}"
            if new_file.exists():
                logger.warning(f"Cannot rename: target file already exists: {new_file}")
                return False

            old_file.rename(new_file)
            logger.info(f"Renamed map: {old_path} -> {new_file}")

            # Also rename related files (colormap, etc.)
            old_colormap = old_file.with_name(f"{old_file.stem}_colormap.png")
            if old_colormap.exists():
                new_colormap = new_file.with_name(f"{new_name}_colormap.png")
                old_colormap.rename(new_colormap)

            self.projectModifiedChanged.emit(True)
            return True
        except Exception as e:
            logger.error(f"Error renaming map: {e}")
            return False

    @Slot(str, result=bool)
    def deleteTable(self, table_path: str) -> bool:
        """Delete a table file.

        Args:
            table_path: Path to the table file to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            path = Path(table_path)
            if path.exists():
                path.unlink()
                logger.info(f"Deleted table: {table_path}")
                self.projectModifiedChanged.emit(True)
                return True
            else:
                logger.warning(f"Table file not found: {table_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting table: {e}")
            return False

    @Slot(str, str, result=bool)
    def renameTable(self, old_path: str, new_name: str) -> bool:
        """Rename a table file.

        Args:
            old_path: Current path to the table file
            new_name: New name for the table (without extension)

        Returns:
            True if renamed successfully, False otherwise
        """
        try:
            old_file = Path(old_path)
            if not old_file.exists():
                logger.warning(f"Table file not found: {old_path}")
                return False

            new_file = old_file.parent / f"{new_name}{old_file.suffix}"
            if new_file.exists():
                logger.warning(f"Cannot rename: target file already exists: {new_file}")
                return False

            old_file.rename(new_file)
            logger.info(f"Renamed table: {old_path} -> {new_file}")
            self.projectModifiedChanged.emit(True)
            return True
        except Exception as e:
            logger.error(f"Error renaming table: {e}")
            return False

    @Slot(str, result=bool)
    def deleteGraph(self, graph_path: str) -> bool:
        """Delete a graph file.

        Args:
            graph_path: Path to the graph file to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            path = Path(graph_path)
            if path.exists():
                path.unlink()
                logger.info(f"Deleted graph: {graph_path}")
                self.projectModifiedChanged.emit(True)
                return True
            else:
                logger.warning(f"Graph file not found: {graph_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting graph: {e}")
            return False

    @Slot(str, str, result=bool)
    def renameGraph(self, old_path: str, new_name: str) -> bool:
        """Rename a graph file.

        Args:
            old_path: Current path to the graph file
            new_name: New name for the graph (without extension)

        Returns:
            True if renamed successfully, False otherwise
        """
        try:
            old_file = Path(old_path)
            if not old_file.exists():
                logger.warning(f"Graph file not found: {old_path}")
                return False

            new_file = old_file.parent / f"{new_name}{old_file.suffix}"
            if new_file.exists():
                logger.warning(f"Cannot rename: target file already exists: {new_file}")
                return False

            old_file.rename(new_file)
            logger.info(f"Renamed graph: {old_path} -> {new_file}")
            self.projectModifiedChanged.emit(True)
            return True
        except Exception as e:
            logger.error(f"Error renaming graph: {e}")
            return False

    @Slot(str, result=bool)
    def deleteOutput(self, output_path: str) -> bool:
        """Delete an output file.

        Args:
            output_path: Path to the output file to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            path = Path(output_path)
            if path.exists():
                path.unlink()
                logger.info(f"Deleted output: {output_path}")
                self.projectModifiedChanged.emit(True)
                return True
            else:
                logger.warning(f"Output file not found: {output_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting output: {e}")
            return False

    @Slot(result=str)
    def getOutputDirectory(self):
        """Get the output base directory."""
        return str(self._output_base_dir.absolute())

    # Project Management
    @Slot()
    def newProject(self):
        """Create a new project (clears current state)."""
        logger.info("Creating new project")
        # TODO: Prompt to save if current project is modified
        self._datasets.clear()
        self._active_dataset = None
        self.project_manager.close_project()
        self.status = "New project created"
        self.projectModifiedChanged.emit(False)

    def _get_projects_directory(self) -> str:
        """Get the default projects directory path."""
        # Get the application root directory (where run.py is)
        app_dir = Path(__file__).parent.parent.parent
        projects_dir = app_dir / "projects"
        # Create if it doesn't exist
        projects_dir.mkdir(exist_ok=True)
        return str(projects_dir)


    @Slot()
    def saveProject(self):
        """Save current project to existing .HRT file."""
        project_path = self.project_manager.get_current_project_path()

        if not project_path:
            # No current project, use Save As
            self.saveProjectAs()
            return

        logger.info(f"Submitting project save to worker: {project_path}")
        self.status = "Saving project..."
        self.worker_manager.submit(
            name=f"Save Project",
            operation=self._do_save_project,
            project_path=project_path,
            on_finished=lambda _: self._on_project_saved(project_path)
        )

    @Slot()
    def saveProjectAs(self):
        """Save current project to new .HRT file."""
        logger.info("saveProjectAs() called")

        file_path, _ = QFileDialog.getSaveFileName(
            None,
            "Save Project As",
            self._get_projects_directory(),
            "TRANS Project Files (*.hrt);;All Files (*)"
        )

        if not file_path:
            logger.info("Save cancelled by user")
            return

        project_path = Path(file_path)
        logger.info(f"Submitting project save to worker: {project_path}")
        self.status = "Saving project..."
        self.worker_manager.submit(
            name=f"Save Project",
            operation=self._do_save_project,
            project_path=project_path,
            on_finished=lambda _: self._on_project_saved(project_path)
        )

    def _do_save_project(self, task, project_path: Path):
        """Internal method to save project (runs in worker thread)."""
        from datetime import datetime

        # Check if cancelled
        if task.cancelled:
            logger.info("Project save cancelled")
            return None

        # Use embedded window states collected from QML
        embedded_states = self._embedded_window_states or []
        graph_states = [s for s in embedded_states if s.get('type') == 'graph']
        table_states = [s for s in embedded_states if s.get('type') == 'table']
        image_window_states = [s for s in embedded_states if s.get('type') == 'image']

        # Get map editor state
        map_editor_state = {}
        if self._map_editor_backend is not None:
            try:
                map_editor_state = self._map_editor_backend.getState()
            except Exception as e:
                logger.warning(f"Could not get map editor state: {e}")

        # Gather project data
        project_data = {
            'created': datetime.now().isoformat(),
            'metadata': {
                'name': project_path.stem,
                'description': 'TRANS-QML Project'
            },
            'datasets': self._datasets,
            'tables': table_states,
            'graphs': graph_states,
            'image_windows': image_window_states,
            'workspace': {
                'active_dataset': self._active_dataset,
                'current_tab': self._current_tab,
                'window_counter': self._window_id_counter
            },
            'output_files': self.output_files,
            'maps': self.maps,
            'images': self._images,
            'notes': self._notes,
            'naming_convention': self._naming_convention,
            'map_editor': map_editor_state,
        }

        success = self.project_manager.save_project(project_path, project_data)

        if not success:
            raise Exception(f"Failed to save project: {project_path}")

        logger.info(f"Project saved: {project_path}")
        return str(project_path)

    def _on_project_saved(self, project_path: Path):
        """Called when project save completes."""
        self.status = f"Project saved: {project_path.name}"
        self.projectSaved.emit(str(project_path))
        self.projectModifiedChanged.emit(False)
        logger.info(f"Project save completed: {project_path}")

    @Slot(result=bool)
    def hasProject(self):
        """Check if a project is currently loaded."""
        return self.project_manager.get_current_project_path() is not None

    @Slot(result=bool)
    def hasDatasets(self):
        """Check if any datasets are loaded."""
        return len(self._datasets) > 0

    # Tool Opening
    @Slot(str)
    def openTool(self, tool_name: str):
        """Open a specific tool window."""
        logger.info(f"Opening tool: {tool_name}")
        self.toolOpened.emit(tool_name)

    @Slot()
    def newPlot(self):
        """Create a new embedded graph window."""
        logger.info("Creating new embedded plot window")
        self._window_id_counter += 1
        graph_title = f"Graph {self._window_id_counter}"

        # Emit signal for QML to create an embedded graph window (empty)
        self.openDatasetEmbedded.emit(graph_title, [], "", "")
        self.status = f"{graph_title} created"
        logger.info(f"Embedded plot window requested: {graph_title}")

    @Slot()
    def newTable(self):
        """Create a new embedded table window with initial blank grid."""
        logger.info("Creating new embedded table window")
        self._window_id_counter += 1
        table_title = f"Table {self._window_id_counter}"

        # Create model with initial blank rows and columns
        model = TableDataModel(self)
        initial_rows = [[0.0] * 5 for _ in range(20)]
        initial_headers = ['A', 'B', 'C', 'D', 'E']
        model.setTableData(initial_rows, initial_headers)
        self._table_models.append(model)
        logger.info(f"Table model created: {model.rows} rows x {model.columns} cols")
        self.openTableEmbedded.emit(table_title, model)
        self.status = f"{table_title} created"
        logger.info(f"Embedded table window requested: {table_title}")

    @Slot(str, list, list)
    def restoreTableFromState(self, title: str, data: list, headers: list):
        """Restore a table from saved project state by creating a TableDataModel."""
        model = TableDataModel(self)
        if data:
            model.setTableData(data, headers)
        self._table_models.append(model)
        self.openTableEmbedded.emit(title, model)

    @Slot(str)
    def openWorkflow(self, workflow_name: str):
        """Open a workflow editor window."""
        from PySide6.QtQml import QQmlComponent, QQmlEngine
        from PySide6.QtCore import QUrl

        logger.info(f"Opening workflow: {workflow_name}")

        # Create workflow using the workflow manager
        workflow_id = self.workflow_manager.createWorkflow(workflow_name)

        # The workflow window will be created from QML
        # This slot triggers the QML to create a WorkflowWindow
        self.status = f"Workflow '{workflow_name}' opened"
        logger.info(f"Workflow created with ID: {workflow_id}")

        # Return the workflow_id so QML can use it
        return workflow_id

    def _open_map_window(self, map_path: str, map_id: str, map_title: str):
        """Open a map visualization window."""
        from src.widgets.map_window import MapVisualizationWindow

        try:
            logger.info(f"Opening map visualization window: {map_title}")

            map_window = MapVisualizationWindow(map_path=map_path, title=map_title)

            # Track window
            self.open_windows.append(map_window)
            map_info = {
                'window': map_window,
                'id': map_id,
                'title': map_title,
                'path': map_path
            }
            self.open_map_windows.append(map_info)

            # Connect close signal
            map_window.closed.connect(lambda mid=map_id: self._remove_map_window(mid))

            map_window.show()
            logger.info(f"Map window opened: {map_title}")

        except Exception as e:
            logger.error(f"Error opening map window: {e}", exc_info=True)
            self.errorOccurred.emit("Map Error", f"Could not open map: {e}")

    def _remove_map_window(self, map_id: str):
        """Remove map window from tracking lists."""
        for map_info in self.open_map_windows:
            if map_info['id'] == map_id:
                window = map_info['window']
                if window in self.open_windows:
                    self.open_windows.remove(window)
                self.open_map_windows.remove(map_info)
                self.windowClosed.emit('map', map_id)
                logger.info(f"Map window closed: {map_id}")
                break

    @Slot(str)
    def openMapFromPath(self, map_path: str):
        """Open a map visualization window from a file path (for ProjectBrowser)."""
        from pathlib import Path
        self._map_id_counter += 1
        map_id = f"map_{self._map_id_counter}"
        map_title = Path(map_path).stem
        self._open_map_window(map_path, map_id, map_title)

    @Slot()
    def closeAllWindows(self):
        """Close all open tool, graph, and table windows. Called when main window closes."""
        logger.info(f"Closing all windows ({len(self.open_windows)} open)")

        # Emit signal so windows can prepare for closing
        self.applicationClosing.emit()

        # Close all windows - iterate over a copy since list will be modified
        windows_to_close = list(self.open_windows)
        for window in windows_to_close:
            try:
                if hasattr(window, 'close'):
                    window.close()
            except Exception as e:
                logger.warning(f"Error closing window: {e}")

        # Clear tracking lists
        self.open_windows.clear()
        self.open_map_windows.clear()
        logger.info("All windows closed")

    # ========================================================================
    # TOOL IMPLEMENTATIONS - Integration Utility
    # ========================================================================

    @Slot(str, 'QVariantList')
    def integrate(self, dataset_name: str, intervals: List):
        """QML wrapper for integration - runs in background thread."""
        logger.info(f"Submitting integration for {dataset_name} to worker")
        self.status = f"Integrating {dataset_name}..."
        self.worker_manager.submit(
            name=f"Integrate {dataset_name}",
            operation=self._do_integrate,
            dataset_name=dataset_name,
            intervals=intervals,
            on_finished=lambda path: self._on_tool_completed("Integration Utility", path)
        )

    def _do_integrate(self, task, dataset_name: str, intervals: List):
        """
        Perform integration over specified intervals.

        Parameters:
        -----------
        task : Task
            Task object for cancellation checking
        dataset_name : str
            Name of dataset to integrate
        intervals : List[Dict]
            List of intervals with 'lower' and 'upper' keys

        Returns:
        --------
        output_path : str
            Path to saved results
        """
        try:
            # Check if cancelled
            if task.cancelled:
                logger.info("Integration cancelled")
                return None

            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            logger.info(f"Integrating {dataset_name} over {len(intervals)} intervals")

            # Get independent variable and spectra
            independent_var = spectral_data.independent_var
            spectra = spectral_data.spectra.values

            # Integrate over each interval
            integration_results = []
            for i, interval in enumerate(intervals):
                # Check cancellation during loop
                if task.cancelled:
                    logger.info(f"Integration cancelled at interval {i+1}/{len(intervals)}")
                    return None

                # Update progress
                task.progress = i / len(intervals)
                start_v = float(interval['lower'])
                end_v = float(interval['upper'])

                # Create mask for interval
                mask = (independent_var >= start_v) & (independent_var <= end_v)

                if not np.any(mask):
                    logger.warning(f"No data in interval [{start_v}, {end_v}]")
                    continue

                # Extract data in interval
                interval_var = independent_var[mask]
                interval_spectra = spectra[mask, :]

                # Perform trapezoidal integration
                try:
                    # Use np.trapezoid if available (NumPy 2.0+), otherwise np.trapz
                    if hasattr(np, 'trapezoid'):
                        integrated = np.trapezoid(interval_spectra, x=interval_var, axis=0)
                    else:
                        integrated = np.trapz(interval_spectra, x=interval_var, axis=0)
                except:
                    integrated = np.trapz(interval_spectra, x=interval_var, axis=0)

                integration_results.append({
                    'interval': f"{start_v:.3f}_{end_v:.3f}",
                    'interval_tuple': (start_v, end_v),  # Store numeric tuple
                    'integrated_values': integrated
                })

            # Create output DataFrame with one column per interval
            num_spectra = spectra.shape[1]
            # First column should be spectrum index (as independent variable for integrated data)
            output_df = pd.DataFrame({'Spectrum_Index': range(num_spectra)})

            for result in integration_results:
                col_name = f"Interval_{result['interval']}"
                output_df[col_name] = result['integrated_values']

            # Create user-friendly names using naming convention
            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(dataset_name, operation="Integrated")

            # Save to file with convention-based filename
            output_path = self._ensure_output_dir('integrated') / f"{convention_name}.csv"
            output_df.to_csv(output_path, index=False)

            # Create new SpectralData object with clean base name (convention only for file path)
            friendly_name = f"{base_name} - Integrated"
            legacy_result_name = f"Integrated_{dataset_name}"

            # Create metadata for the integrated data (preserve dimensions from original)
            integrated_metadata = SpectralMetadata(
                source_type="integrated_flat",
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units={'independent': 'Index', 'dependent': 'Integrated Value'},
                additional_info={
                    'original_dataset': dataset_name,
                    'original_source_type': spectral_data.metadata.source_type,
                    'num_intervals': len(integration_results),
                    'intervals': [r['interval_tuple'] for r in integration_results]  # Store numeric tuples
                },
                data_type='flat'
            )

            # Create SpectralData object
            integrated_spectral_data = SpectralData(
                data=output_df,
                metadata=integrated_metadata,
                topography=spectral_data.topography  # Preserve topography if available
            )

            # Store only with friendly name (no duplicates)
            self._datasets[friendly_name] = integrated_spectral_data
            # Only emit to browser when not in workflow mode (intermediate results shouldn't appear)
            if not self._workflow_mode:
                self.dataLoaded.emit(friendly_name)

            # Status update will be handled by callback in main thread
            logger.info(f"Integration results saved to {output_path}: {len(integration_results)} intervals")

            return str(output_path)

        except Exception as e:
            logger.error(f"Integration error: {e}", exc_info=True)
            self.errorOccurred.emit("Integration Error", str(e))
            return ""

    # ========================================================================
    # TOOL IMPLEMENTATIONS - Spatial Average / Discretization
    # ========================================================================

    @Slot(str, int, int, bool, bool)
    def spatialAverage(self, dataset_name: str, discrete_x: int, discrete_y: int,
                      ignore_empty: bool, save_intermediate: bool):
        """QML wrapper for spatial averaging - runs in background thread."""
        logger.info(f"Submitting spatial averaging for {dataset_name} to worker")
        self.status = f"Spatial averaging {dataset_name}..."
        self.worker_manager.submit(
            name=f"Spatial Average {dataset_name}",
            operation=self._do_spatial_average,
            dataset_name=dataset_name,
            discrete_x=discrete_x,
            discrete_y=discrete_y,
            ignore_empty=ignore_empty,
            save_intermediate=save_intermediate,
            on_finished=lambda path: self._on_tool_completed("Spatial Average", path)
        )

    def _do_spatial_average(self, task, dataset_name: str, discrete_x: int, discrete_y: int,
                      ignore_empty: bool, save_intermediate: bool):
        """
        Perform spatial averaging/discretization.

        Parameters:
        -----------
        task : Task
            Task object for cancellation checking
        dataset_name : str
            Dataset to discretize
        discrete_x : int
            Horizontal blocks
        discrete_y : int
            Vertical blocks
        ignore_empty : bool
            Skip empty blocks
        save_intermediate : bool
            Save intermediate results

        Returns:
        --------
        output_path : str
            Path to final results
        """
        try:
            # Check if cancelled
            if task.cancelled:
                logger.info("Spatial averaging cancelled")
                return None

            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            dim_h, dim_v = spectral_data.metadata.dimensions

            # Calculate block sizes
            block_h = int(np.ceil(dim_h / discrete_x))
            block_v = int(np.ceil(dim_v / discrete_y))

            logger.info(f"Discretizing {dataset_name}: {dim_h}x{dim_v} -> {discrete_x}x{discrete_y}")
            logger.info(f"Block size: {block_h}x{block_v}")

            # Perform discretization
            results = self.discretizer.discretize_spectral_data(
                spectral_data=spectral_data,
                block_h=block_h,
                block_v=block_v,
                ignore_empty_blocks=ignore_empty,
                data_type='spectral'
            )

            # Create user-friendly names using naming convention
            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(dataset_name, operation="Averaged")

            # Save final results with convention-based filename
            final_data = results['final']
            output_path = self._ensure_output_dir('discretized') / f"{convention_name}.csv"
            final_data.save(str(output_path))

            # Add to datasets with clean base name (convention only for file path)
            friendly_name = f"{base_name} - Spatially Averaged ({discrete_x}x{discrete_y})"
            self._datasets[friendly_name] = final_data

            # Save intermediate if requested
            if save_intermediate:
                intermediate_data = results['intermediate']
                intermediate_path = self._ensure_output_dir('discretized') / f"{file_safe_name}_intermediate_{discrete_x}x{discrete_y}.csv"
                intermediate_data.save(str(intermediate_path))

            # Status update will be handled by callback in main thread
            logger.info(f"Discretization saved to {output_path}: {final_data.num_spectra} blocks")

            return str(output_path)

        except Exception as e:
            logger.error(f"Spatial average error: {e}", exc_info=True)
            self.errorOccurred.emit("Spatial Average Error", str(e))
            return ""

    @Slot(str, int, int, bool, 'QVariantList')
    def spatialAverageWithSelection(self, dataset_name: str, discrete_x: int, discrete_y: int,
                                     ignore_empty: bool, selected_blocks_list: list):
        """
        Spatial averaging restricted to selected blocks.
        Uses Discretizer with selection mask support.

        Parameters:
            dataset_name: Name of dataset to discretize
            discrete_x: Number of horizontal blocks
            discrete_y: Number of vertical blocks
            ignore_empty: Skip empty blocks
            selected_blocks_list: List of {row, col} dicts for selected blocks.
                                  Empty list means process all blocks.
        """
        if dataset_name not in self._datasets:
            self.errorOccurred.emit("Error", f"Dataset not found: {dataset_name}")
            return

        try:
            spectral_data = self._datasets[dataset_name]
            dim_h, dim_v = spectral_data.metadata.dimensions

            block_h = int(np.ceil(dim_h / discrete_x))
            block_v = int(np.ceil(dim_v / discrete_y))

            # Convert selected blocks list to tuples
            selected_blocks = None
            suffix = "full"
            if selected_blocks_list and len(selected_blocks_list) > 0:
                selected_blocks = [(b['row'], b['col']) for b in selected_blocks_list
                                    if isinstance(b, dict) and 'row' in b and 'col' in b]
                if not selected_blocks:
                    selected_blocks = None
                else:
                    suffix = "selection"

            logger.info(f"Discretizing {dataset_name}: {dim_h}x{dim_v} -> {discrete_x}x{discrete_y}"
                         f" ({suffix}, {len(selected_blocks) if selected_blocks else 'all'} blocks)")

            # If selected_blocks provided, mask out unselected spectra before discretization
            data_to_process = spectral_data
            if selected_blocks:
                import math
                selected_set = set(selected_blocks)
                # Create a copy with NaN for unselected block positions
                masked_df = spectral_data.spectra.copy()
                for spec_idx in range(spectral_data.num_spectra):
                    r = spec_idx // dim_h
                    c = spec_idx % dim_h
                    grid_r = r // block_v
                    grid_c = c // block_h
                    if (grid_r, grid_c) not in selected_set:
                        masked_df.iloc[:, spec_idx] = np.nan

                data_to_process = SpectralData(
                    data=pd.concat([spectral_data.data.iloc[:, :1], masked_df], axis=1),
                    metadata=spectral_data.metadata
                )

            results = self.discretizer.discretize_spectral_data(
                spectral_data=data_to_process,
                block_h=block_h,
                block_v=block_v,
                ignore_empty_blocks=ignore_empty,
                data_type='spectral'
            )

            final_data = results['final']
            base_name = self._extract_clean_base_name(dataset_name)
            friendly_name = f"{base_name} - Averaged [{suffix}] ({discrete_x}x{discrete_y})"

            self._datasets[friendly_name] = final_data
            self.dataLoaded.emit(friendly_name)

            # Save to disk
            file_safe_name = self._sanitize_filename(base_name)
            output_path = self._ensure_output_dir('discretized') / f"{file_safe_name}_averaged_{suffix}_{discrete_x}x{discrete_y}.csv"
            final_data.save(str(output_path))

            self.status = f"Spatial averaging complete: {final_data.num_spectra} blocks"
            self.toolCompleted.emit("Spatial Average", str(output_path))
            logger.info(f"Spatial average with selection saved: {output_path}")

        except Exception as e:
            logger.error(f"Spatial average with selection error: {e}", exc_info=True)
            self.errorOccurred.emit("Spatial Average Error", str(e))

    # ========================================================================
    # TOOL IMPLEMENTATIONS - 1D FFT
    # ========================================================================

    @Slot(str)
    def fft1D(self, dataset_name: str):
        """QML wrapper for 1D FFT - runs in background thread."""
        logger.info(f"Submitting 1D FFT for {dataset_name} to worker")
        self.status = f"Computing 1D FFT for {dataset_name}..."
        self.worker_manager.submit(
            name=f"1D FFT {dataset_name}",
            operation=self._do_fft1D,
            dataset_name=dataset_name,
            on_finished=lambda path: self._on_tool_completed("1D FFT", path)
        )

    def _do_fft1D(self, task, dataset_name: str):
        """
        Perform 1D FFT on spectral data.

        Parameters:
        -----------
        task : Task
            Task object for cancellation checking
        dataset_name : str
            Dataset to transform

        Returns:
        --------
        output_path : str
            Path to FFT results
        """
        try:
            # Check if cancelled
            if task.cancelled:
                logger.info("1D FFT cancelled")
                return None

            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            logger.info(f"Performing 1D FFT on {dataset_name}")

            # Get spectral data
            spectra = spectral_data.spectra.values  # (n_points, n_spectra)
            independent_var = spectral_data.independent_var

            # Perform FFT on each spectrum
            fft_results = np.fft.fft(spectra, axis=0)
            fft_magnitude = np.abs(fft_results)
            fft_phase = np.angle(fft_results)

            # Create frequency axis
            n_points = len(independent_var)
            d = np.mean(np.diff(independent_var))  # Average spacing
            frequencies = np.fft.fftfreq(n_points, d)

            # Create DataFrames for magnitude and phase
            mag_df = pd.DataFrame(fft_magnitude, columns=spectral_data.spectra.columns)
            mag_df.insert(0, 'Frequency', frequencies)

            phase_df = pd.DataFrame(fft_phase, columns=spectral_data.spectra.columns)
            phase_df.insert(0, 'Frequency', frequencies)

            # Create user-friendly names using naming convention
            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(dataset_name, operation="FFT")
            file_safe_name = self._sanitize_filename(base_name)

            # Save results using _ensure_output_dir for proper project structure
            mag_path = self._ensure_output_dir('fft') / f"{convention_name}_Magnitude.csv"
            phase_path = self._ensure_output_dir('fft') / f"{file_safe_name}_FFT_Phase.csv"

            mag_df.to_csv(mag_path, index=False)
            phase_df.to_csv(phase_path, index=False)

            # Create new datasets with clean base name (convention only for file path)
            friendly_name = f"{base_name} - FFT Magnitude"
            mag_metadata = SpectralMetadata(
                source_type=spectral_data.metadata.source_type,
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units={'independent': 'Hz', 'dependent': 'a.u.'},
                additional_info={'transform': 'FFT_magnitude', 'original': dataset_name}
            )
            mag_spectral_data = SpectralData(mag_df, mag_metadata)
            # Store only with friendly name (no duplicates)
            self._datasets[friendly_name] = mag_spectral_data

            # Status update will be handled by callback in main thread
            logger.info(f"FFT results saved to {mag_path} and {phase_path}")

            return str(mag_path)

        except Exception as e:
            logger.error(f"1D FFT error: {e}", exc_info=True)
            self.errorOccurred.emit("FFT Error", str(e))
            return ""

    # ========================================================================
    # TOOL IMPLEMENTATIONS - 2D FFT (for maps)
    # ========================================================================

    @Slot(str)
    def fft2D(self, image_path: str):
        """QML wrapper for 2D FFT - runs in background thread."""
        logger.info(f"Submitting 2D FFT to worker")
        self.status = "Computing 2D FFT..."
        self.worker_manager.submit(
            name="2D FFT",
            operation=self._do_fft2D,
            image_path=image_path,
            on_finished=lambda path: self._on_tool_completed("2D FFT", path)
        )

    def _do_fft2D(self, task, image_path: str):
        """
        Perform 2D FFT on image/map data.

        Parameters:
        -----------
        task : Task
            Task object for cancellation checking
        image_path : str
            Path to image file

        Returns:
        --------
        output_path : str
            Path to FFT result image
        """
        try:
            # Check if cancelled
            if task.cancelled:
                logger.info("2D FFT cancelled")
                return None

            from PIL import Image

            logger.info(f"Performing 2D FFT on {image_path}")

            # Load image
            img = Image.open(image_path).convert('L')  # Convert to grayscale
            img_array = np.array(img)

            # Perform 2D FFT
            fft_result = np.fft.fft2(img_array)
            fft_shifted = np.fft.fftshift(fft_result)
            magnitude = np.abs(fft_shifted)
            phase = np.angle(fft_shifted)

            # Log scale for better visualization
            magnitude_log = np.log(1 + magnitude)

            # Normalize to 0-255
            magnitude_norm = ((magnitude_log - magnitude_log.min()) /
                            (magnitude_log.max() - magnitude_log.min()) * 255).astype(np.uint8)

            # Save results using _ensure_output_dir for proper project structure
            output_path = self._ensure_output_dir('fft') / f"FFT2D_{Path(image_path).stem}.png"
            result_img = Image.fromarray(magnitude_norm)
            result_img.save(output_path)

            # Status update will be handled by callback in main thread
            logger.info(f"2D FFT saved to {output_path}")

            return str(output_path)

        except Exception as e:
            logger.error(f"2D FFT error: {e}", exc_info=True)
            self.errorOccurred.emit("2D FFT Error", str(e))
            return ""

    # ========================================================================
    # TOOL WRAPPERS - Exposing Tool Implementations to QML
    # ========================================================================

    @Slot(str, int, int, str)
    def smoothCurves(self, dataset_name: str, window_size: int, poly_order: int,
                     smoothing_type: str):
        """QML wrapper for curve smoothing - runs in background thread."""
        logger.info(f"Submitting curve smoothing for {dataset_name} to worker")
        self.status = f"Smoothing curves for {dataset_name}..."
        self.worker_manager.submit(
            name=f"Smooth Curves {dataset_name}",
            operation=self.smooth_curves,
            dataset_name=dataset_name,
            window_size=window_size,
            poly_order=poly_order,
            smoothing_type=smoothing_type,
            on_finished=lambda path: self._on_tool_completed("Curve Smoothing", path)
        )

    @Slot('QStringList', str)
    def subtractBackground(self, signal_names, background_name: str):
        """QML wrapper for N-dataset background subtraction.

        ``signal_names`` is a QStringList of N dataset keys; ``background_name``
        is the dataset to subtract from each. One ``- BgSub`` dataset is
        produced per input; axes that don't fully overlap the background are
        truncated to the overlap interval.
        """
        names = [str(n) for n in signal_names]
        logger.info(
            f"Submitting background subtraction: {len(names)} signal(s) "
            f"minus {background_name!r}"
        )
        self.status = f"Subtracting background from {len(names)} dataset(s)..."
        self.worker_manager.submit(
            name=f"Subtract Background ({len(names)})",
            operation=self.subtract_background_datasets,
            signal_names=names,
            background_name=background_name,
            on_finished=lambda path: self._on_tool_completed("Background Subtraction", path),
        )

    @Slot(str, float, int, int)
    def cosmicRayFilter(self, dataset_name: str, threshold_sigmas: float,
                        window: int, max_width: int):
        """QML wrapper for cosmic-ray / hot-pixel removal.

        Runs in the background worker. Defaults (5σ, 5-sample median window,
        max 2-sample run width) are appropriate for typical PL / Raman CCD
        data; widen ``max_width`` only if real lines are 1 px wide.
        """
        logger.info(f"Submitting cosmic-ray filter for {dataset_name} to worker")
        self.status = f"Filtering cosmic rays in {dataset_name}..."
        self.worker_manager.submit(
            name=f"Cosmic Ray Filter {dataset_name}",
            operation=self.remove_cosmic_rays,
            dataset_name=dataset_name,
            threshold_sigmas=threshold_sigmas,
            window=window,
            max_width=max_width,
            on_finished=lambda path: self._on_tool_completed("Cosmic Ray Filter", path),
        )

    @Slot(str, str, int)
    def smoothImage(self, image_path: str, filter_type: str, kernel_size: int):
        """QML wrapper for image smoothing - runs in background thread."""
        logger.info(f"Submitting image smoothing to worker")
        self.status = "Smoothing image..."
        self.worker_manager.submit(
            name="Smooth Image",
            operation=self.smooth_image,
            image_path=image_path,
            filter_type=filter_type,
            kernel_size=kernel_size,
            on_finished=lambda path: self._on_tool_completed("Image Smoothing", path)
        )

    @Slot(str, str, str, 'QVariantMap')
    def processMap(self, input_path: str, input_type: str, operation: str, params: Dict):
        """
        Process a map/image with various operations.

        Parameters:
            input_path: Path to file or name of dataset
            input_type: 'file' or 'dataset'
            operation: Operation name (gaussian_filter, median_filter, plane_level, row_align, normalize)
            params: Operation parameters
        """
        logger.info(f"Processing map: {input_path}, operation: {operation}")
        self.status = f"Processing map: {operation}..."

        self.worker_manager.submit(
            name=f"Map {operation}",
            operation=self._do_process_map,
            input_path=input_path,
            input_type=input_type,
            #operation=operation,
            params=params,
            on_finished=lambda path: self._on_map_processing_completed(operation, path, params)
        )

    def _do_process_map(self, task, input_path: str, input_type: str, operation: str, params: Dict):
        """Background worker for map processing."""
        from scipy import ndimage

        if task.cancelled:
            return None

        try:
            # Load the data
            if input_type == 'file':
                data = self._load_map_file(input_path)
                base_name = Path(input_path).stem
            else:
                # Load from maps directory
                maps_dir = self._output_base_dir / "maps"
                # Find matching file
                map_path = None
                for ext in ['.tif', '.tiff', '.npy', '.png']:
                    candidate = maps_dir / f"{input_path}{ext}"
                    if candidate.exists():
                        map_path = candidate
                        break

                if map_path is None:
                    raise FileNotFoundError(f"Map not found: {input_path}")

                data = self._load_map_file(str(map_path))
                base_name = input_path

            if task.cancelled:
                return None

            # Apply operation
            if operation == 'gaussian_filter':
                sigma = params.get('sigma', 1.0)
                result = ndimage.gaussian_filter(data, sigma=sigma)
                op_suffix = f"gaussian_s{sigma}"

            elif operation == 'median_filter':
                size = params.get('size', 3)
                result = ndimage.median_filter(data, size=size)
                op_suffix = f"median_k{size}"

            elif operation == 'plane_level':
                # Fit and subtract a plane
                rows, cols = data.shape
                x = np.arange(cols)
                y = np.arange(rows)
                X, Y = np.meshgrid(x, y)

                A = np.column_stack([X.ravel(), Y.ravel(), np.ones(X.size)])
                coeffs, _, _, _ = np.linalg.lstsq(A, data.ravel(), rcond=None)
                plane = (coeffs[0] * X + coeffs[1] * Y + coeffs[2])
                result = data - plane
                op_suffix = "planelevel"

            elif operation == 'row_align':
                # Subtract row medians
                result = data.copy()
                for i in range(result.shape[0]):
                    result[i] -= np.nanmedian(result[i])
                op_suffix = "rowalign"

            elif operation == 'normalize':
                vmin = np.nanmin(data)
                vmax = np.nanmax(data)
                if vmax > vmin:
                    result = (data - vmin) / (vmax - vmin)
                else:
                    result = np.zeros_like(data)
                op_suffix = "norm"

            elif operation == 'polynomial_bg_removal':
                order = params.get('order', 2)
                # Fit 2D polynomial and subtract
                rows, cols = data.shape
                x = np.arange(cols)
                y = np.arange(rows)
                X, Y = np.meshgrid(x, y)

                # Build polynomial terms up to given order
                terms = []
                for i in range(order + 1):
                    for j in range(order + 1 - i):
                        terms.append((X**i * Y**j).ravel())

                A = np.column_stack(terms)
                coeffs, _, _, _ = np.linalg.lstsq(A, data.ravel(), rcond=None)

                background = np.zeros_like(data)
                idx = 0
                for i in range(order + 1):
                    for j in range(order + 1 - i):
                        background += coeffs[idx] * (X**i * Y**j)
                        idx += 1

                result = data - background
                op_suffix = f"polybg_o{order}"

            else:
                logger.error(f"Unknown operation: {operation}")
                return None

            if task.cancelled:
                return None

            # Save results
            output_name = f"{base_name}_{op_suffix}"
            maps_dir = self._output_base_dir / "maps"
            maps_dir.mkdir(parents=True, exist_ok=True)

            output_path = None

            if params.get('save_tiff', True):
                import tifffile
                tiff_path = maps_dir / f"{output_name}.tif"
                tifffile.imwrite(str(tiff_path), result.astype(np.float32))
                output_path = str(tiff_path)
                logger.info(f"Saved processed map: {tiff_path}")

            if params.get('save_png', False):
                import matplotlib.cm as cm
                # Normalize for colormap
                vmin = np.nanpercentile(result, 2)
                vmax = np.nanpercentile(result, 98)
                if vmax > vmin:
                    normalized = (result - vmin) / (vmax - vmin)
                else:
                    normalized = np.zeros_like(result)
                normalized = np.clip(normalized, 0, 1)

                cmap = cm.get_cmap('viridis')
                colored = cmap(normalized)
                img_data = (colored[:, :, :3] * 255).astype(np.uint8)

                png_path = maps_dir / f"{output_name}.png"
                Image.fromarray(img_data, mode='RGB').save(png_path)
                if output_path is None:
                    output_path = str(png_path)
                logger.info(f"Saved PNG: {png_path}")

            return output_path

        except Exception as e:
            logger.error(f"Map processing error: {e}", exc_info=True)
            return None

    def _load_map_file(self, file_path: str) -> np.ndarray:
        """Load a map/image file and return as 2D numpy array."""
        path = Path(file_path)
        extension = path.suffix.lower()

        if extension in ['.tif', '.tiff']:
            import tifffile
            data = tifffile.imread(str(path))
        elif extension in ['.png', '.jpg', '.jpeg', '.bmp']:
            img = Image.open(str(path))
            if img.mode == 'RGB' or img.mode == 'RGBA':
                img = img.convert('L')
            data = np.array(img, dtype=np.float64)
        elif extension == '.npy':
            data = np.load(str(path))
        else:
            raise ValueError(f"Unsupported format: {extension}")

        # Ensure 2D
        if data.ndim == 3:
            if data.shape[2] <= 4:
                data = np.mean(data, axis=2)
            else:
                data = data[0]

        return data.astype(np.float64)

    def _on_map_processing_completed(self, operation: str, output_path: str, params: Dict):
        """Called when map processing completes."""
        if output_path:
            logger.info(f"Map processing ({operation}) completed: {output_path}")
            self.status = f"Map {operation} complete"
            self.toolCompleted.emit(f"Map Processing: {operation}", output_path)

            # Register output
            self._output_id_counter += 1
            output_id = f"output_{self._output_id_counter}"
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            output_info = {
                'id': output_id,
                'tool': f"Map {operation}",
                'path': output_path,
                'timestamp': timestamp
            }
            self.output_files.append(output_info)
            self.outputCreated.emit(output_id, f"Map {operation}", output_path)

            # Emit map created signal
            map_name = Path(output_path).stem
            self._window_id_counter += 1
            map_id = f"map_{self._window_id_counter}"
            self.mapCreated.emit(map_id, map_name)

            # Open result if requested
            if params.get('open_result', False):
                self._open_map_result(output_path)
        else:
            self.status = f"Map {operation} failed"
            self.errorOccurred.emit("Processing Error", f"Map {operation} failed")

    def _open_map_result(self, output_path: str):
        """Open processed map in map viewer."""
        try:
            from src.widgets.map_window import MapVisualizationWindow

            data = self._load_map_file(output_path)
            title = Path(output_path).stem

            map_window = MapVisualizationWindow(
                data={'values': data},
                title=title,
                colormap='viridis'
            )
            map_window.show()
            self.open_windows.append(map_window)

        except Exception as e:
            logger.error(f"Error opening map result: {e}")

    @Slot(str, int, bool, bool)
    def calculateDerivative(self, dataset_name: str, order: int,
                           smooth_before: bool, smooth_after: bool):
        """QML wrapper for derivative calculation - runs in background thread."""
        logger.info(f"Submitting derivative calculation for {dataset_name} to worker")
        self.status = f"Calculating derivative for {dataset_name}..."

        # Submit to worker for background processing
        self.worker_manager.submit(
            name=f"Derivative {dataset_name}",
            operation=self._do_calculate_derivative,
            dataset_name=dataset_name,
            order=order,
            smooth_before=smooth_before,
            smooth_after=smooth_after,
            on_finished=self._on_derivative_completed,
            on_error=None  # Will use default worker_failed handler
        )

    def _do_calculate_derivative(self, task, dataset_name: str, order: int,
                                 smooth_before: bool, smooth_after: bool):
        """Background worker function for derivative calculation."""
        # Check if cancelled
        if task.cancelled:
            logger.info("Derivative calculation cancelled")
            return None

        return self.calculate_derivative(dataset_name, order, smooth_before, smooth_after)

    def _on_derivative_completed(self, output_path: str):
        """Called when derivative calculation completes."""
        logger.info(f"Derivative calculation completed: {output_path}")
        self.status = "Derivative calculation complete"
        self.toolCompleted.emit("Derivative Calculator", output_path)

    def _on_tool_completed(self, tool_name: str, output_path: str):
        """Generic completion callback for tools."""
        logger.info(f"{tool_name} completed: {output_path}")
        self.status = f"{tool_name} complete"
        self.toolCompleted.emit(tool_name, output_path)

        # Track output file
        if output_path:
            self._output_id_counter += 1
            output_id = f"output_{self._output_id_counter}"
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            output_info = {
                'id': output_id,
                'tool': tool_name,
                'path': output_path,
                'timestamp': timestamp
            }
            self.output_files.append(output_info)
            self.outputCreated.emit(output_id, tool_name, output_path)
            logger.info(f"Registered output file: {output_id} from {tool_name}")

        # Register undo for tool results that created new datasets
        if output_path and not self._suppress_undo:
            # Find any newly created dataset that matches this tool output
            # Tool results typically create datasets with names derived from the tool
            self._register_tool_result_undo(tool_name, output_path)

    def _register_tool_result_undo(self, tool_name: str, output_path: str):
        """Register an undo command for a tool that created a new dataset."""
        # Find the most recently added dataset (the one this tool just created)
        if not self._datasets:
            return
        created_dataset_name = list(self._datasets.keys())[-1]
        created_data = self._datasets.get(created_dataset_name)
        if not created_data:
            return

        def undo_tool():
            if created_dataset_name in self._datasets:
                del self._datasets[created_dataset_name]
                self.datasetDeleted.emit(created_dataset_name)
                self.projectModifiedChanged.emit(True)

        def redo_tool():
            # Cannot re-execute tool, just restore the dataset
            if created_data and created_dataset_name not in self._datasets:
                self._datasets[created_dataset_name] = created_data
                self.dataLoaded.emit(created_dataset_name)
                self.projectModifiedChanged.emit(True)

        self._undo_manager.push(UndoCommand(
            description=f"{tool_name}",
            undo_fn=undo_tool,
            redo_fn=redo_tool
        ))

    def _generate_multiple_maps(self, task, flat_dataset_name: str, value_indices: list):
        """Generate maps for multiple values from flat data (runs in worker thread)."""
        output_paths = []
        for idx in value_indices:
            if task.cancelled:
                break
            try:
                base_path = self.generate_map(task, flat_dataset_name, idx)
                # generate_map returns base path without extension - use PNG for viewing
                if base_path:
                    png_path = f"{base_path}.png"
                    output_paths.append(png_path)
                    logger.info(f"Generated map for value {idx}: {png_path}")
            except Exception as e:
                logger.error(f"Failed to generate map for value {idx}: {e}")
                # Continue with other values

        return output_paths

    def _on_maps_completed(self, output_paths: list):
        """Called when multiple map generation completes."""
        num_maps = len(output_paths)
        logger.info(f"Map generation completed: {num_maps} maps created")
        self.status = f"{num_maps} maps generated successfully"

        # Register each map and open visualization window
        from datetime import datetime
        from pathlib import Path
        for path in output_paths:
            if path:
                self._map_id_counter += 1
                map_id = f"map_{self._map_id_counter}"
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Extract filename for title
                map_filename = Path(path).stem  # Get filename without extension

                map_info = {
                    'id': map_id,
                    'title': map_filename,
                    'path': path,
                    'timestamp': timestamp
                }
                self.maps.append(map_info)
                self.mapCreated.emit(map_id, map_filename)
                logger.info(f"Registered map: {map_id} - {map_filename}")

                # Open visualization window for this map
                self._open_map_window(path, map_id, map_filename)

        self.toolCompleted.emit("Map Generator", f"{num_maps} maps")

    @Slot(str, str)
    def applyGradientFilter(self, image_path: str, method: str):
        """QML wrapper for gradient filter - runs in background thread."""
        logger.info(f"Submitting gradient filter to worker")
        self.status = "Applying gradient filter..."
        self.worker_manager.submit(
            name="Gradient Filter",
            operation=self.apply_gradient_filter,
            image_path=image_path,
            method=method,
            on_finished=lambda path: self._on_tool_completed("Gradient Filter", path)
        )

    @Slot(str, str, int)
    def fitCurves(self, dataset_name: str, fit_type: str, degree: int):
        """QML wrapper for curve fitting - runs in background thread."""
        logger.info(f"Submitting curve fitting for {dataset_name} to worker")
        self.status = f"Fitting curves for {dataset_name}..."
        self.worker_manager.submit(
            name=f"Fit Curves {dataset_name}",
            operation=self.fit_curves,
            dataset_name=dataset_name,
            fit_type=fit_type,
            degree=degree,
            on_finished=lambda path: self._on_tool_completed("Curve Fitting", path)
        )

    @Slot(str, result='QVariantList')
    def getIntegrationIntervals(self, dataset_name: str):
        """Get list of integration intervals from an integrated dataset."""
        if dataset_name not in self._datasets:
            return []

        spectral_data = self._datasets[dataset_name]

        # Check if this is an integrated dataset
        if 'intervals' not in spectral_data.metadata.additional_info:
            logger.warning(f"{dataset_name} does not have interval information")
            return []

        # Get intervals - could be tuples or strings
        intervals = spectral_data.metadata.additional_info['intervals']

        result = []
        for iv in intervals:
            if isinstance(iv, (list, tuple)) and len(iv) == 2:
                # Numeric tuple format
                result.append(f"{iv[0]:.3f} to {iv[1]:.3f}")
            elif isinstance(iv, str):
                # String format like "0.100_0.200" - convert to display format
                parts = iv.split('_')
                if len(parts) == 2:
                    result.append(f"{parts[0]} to {parts[1]}")
                else:
                    result.append(iv)
            else:
                result.append(str(iv))

        return result

    @Slot(str, result='QVariantList')
    def getFlatDataValues(self, dataset_name: str):
        """
        Get list of value columns from a flat dataset.

        Flat data has one value per spatial point (e.g., integrated data, peak heights).
        Returns a list of value column descriptions for display.
        """
        if dataset_name not in self._datasets:
            return []

        spectral_data = self._datasets[dataset_name]
        data_df = spectral_data.data

        # Get value columns (skip index column)
        value_columns = [col for col in data_df.columns if col != 'Spectrum_Index']

        # Check if this has interval information (integrated data)
        if 'intervals' in spectral_data.metadata.additional_info:
            intervals = spectral_data.metadata.additional_info['intervals']
            result = []
            for i, iv in enumerate(intervals):
                if isinstance(iv, (list, tuple)) and len(iv) == 2:
                    result.append(f"Interval {iv[0]:.3f} to {iv[1]:.3f}")
                elif isinstance(iv, str):
                    parts = iv.split('_')
                    if len(parts) == 2:
                        result.append(f"Interval {parts[0]} to {parts[1]}")
                    else:
                        result.append(f"Value: {iv}")
                else:
                    result.append(f"Value {i+1}")
            return result

        # For other flat data, use column names
        result = []
        for col in value_columns:
            result.append(str(col))

        return result if result else ["No values available"]

    @Slot(str, 'QVariantList')
    def generateMaps(self, flat_dataset_name: str, value_indices: list):
        """QML wrapper for generating multiple maps from flat data - runs in background thread."""
        logger.info(f"Submitting map generation for {len(value_indices)} values")
        self.status = f"Generating {len(value_indices)} maps..."
        self.worker_manager.submit(
            name="Generate Maps",
            operation=self._generate_multiple_maps,
            flat_dataset_name=flat_dataset_name,
            value_indices=value_indices,
            on_finished=lambda paths: self._on_maps_completed(paths)
        )

    @Slot(str, int)
    def generateMap(self, flat_dataset_name: str, value_index: int):
        """QML wrapper for map generation from flat data - runs in background thread."""
        logger.info(f"Submitting map generation to worker")
        self.status = "Generating map..."
        self.worker_manager.submit(
            name="Generate Map",
            operation=self.generate_map,
            flat_dataset_name=flat_dataset_name,
            value_index=value_index,
            on_finished=lambda path: self._on_tool_completed("Map Generator", path)
        )

    @Slot(str, float, int)
    def findPeaks(self, dataset_name: str, prominence: float, min_distance: int):
        """QML wrapper for peak finding - runs in background thread.

        Pass ``prominence <= 0`` to use a noise-aware adaptive threshold
        computed per spectrum. The QML PeakIndexingTool "Adaptive" checkbox
        wires this sentinel through.
        """
        logger.info(f"Submitting peak finding for {dataset_name} to worker")
        self.status = f"Finding peaks in {dataset_name}..."
        self.worker_manager.submit(
            name=f"Find Peaks {dataset_name}",
            operation=self.find_peaks,
            dataset_name=dataset_name,
            prominence=prominence,
            min_distance=min_distance,
            on_finished=lambda path: self._on_tool_completed("Peak Finding", path)
        )

    @Slot(str, int, int)
    def discretizeMap(self, image_path: str, target_x: int, target_y: int):
        """QML wrapper for map discretization - runs in background thread."""
        logger.info(f"Submitting map discretization to worker")
        self.status = "Discretizing map..."
        self.worker_manager.submit(
            name="Discretize Map",
            operation=self.discretize_map,
            image_path=image_path,
            target_x=target_x,
            target_y=target_y,
            on_finished=lambda path: self._on_tool_completed("Map Discretizer", path)
        )

    # ========================================================================
    # TOOL IMPLEMENTATIONS - Data Truncation
    # ========================================================================

    @Slot(str, float, float)
    def truncateData(self, dataset_name: str, min_val: float, max_val: float):
        """QML wrapper for data truncation - runs in background thread."""
        logger.info(f"Submitting truncation for {dataset_name} to worker")
        self.status = f"Truncating {dataset_name}..."
        self.worker_manager.submit(
            name=f"Truncate {dataset_name}",
            operation=self._do_truncate_data,
            dataset_name=dataset_name,
            min_val=min_val,
            max_val=max_val,
            on_finished=lambda path: self._on_tool_completed("Truncate Data", path)
        )

    def _do_truncate_data(self, task, dataset_name: str, min_val: float, max_val: float):
        """
        Truncate dataset to specified range of independent variable.

        Parameters:
        -----------
        task : Task
            Task object for cancellation checking
        dataset_name : str
            Dataset to truncate
        min_val : float
            Minimum value of independent variable
        max_val : float
            Maximum value of independent variable

        Returns:
        --------
        output_path : str
            Path to truncated data
        """
        try:
            # Check if cancelled
            if task.cancelled:
                logger.info("Data truncation cancelled")
                return None

            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]

            # Ensure min < max (swap if needed)
            if min_val > max_val:
                min_val, max_val = max_val, min_val
                logger.info(f"Swapped min/max values to ensure correct order")

            # Validate range is meaningful
            if min_val == max_val:
                error_msg = f"Invalid range: min ({min_val}) equals max ({max_val}). Please specify different values."
                logger.error(error_msg)
                self.errorOccurred.emit("Truncation Error", error_msg)
                return ""

            logger.info(f"Truncating {dataset_name} to range [{min_val}, {max_val}]")

            # Use the truncate_range method from SpectralData
            truncated_data = spectral_data.truncate_range(min_val, max_val)

            # Validate result has data
            if truncated_data.num_points < 2:
                error_msg = f"Truncation resulted in only {truncated_data.num_points} points. Adjust the range to include more data."
                logger.error(error_msg)
                self.errorOccurred.emit("Truncation Error", error_msg)
                return ""

            # Create user-friendly names using naming convention
            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(dataset_name, operation="Truncated")

            # Save truncated data with convention-based filename
            output_path = self._ensure_output_dir('curves') / f"{convention_name}.csv"
            truncated_data.save(str(output_path))

            # Add to datasets with clean base name (convention only for file path)
            friendly_name = f"{base_name} - Truncated ({min_val:.1f} to {max_val:.1f})"
            self._datasets[friendly_name] = truncated_data
            # Only emit to browser when not in workflow mode (intermediate results shouldn't appear)
            if not self._workflow_mode:
                self.dataLoaded.emit(friendly_name)

            logger.info(f"Truncated data saved to {output_path}")
            logger.info(f"Original points: {spectral_data.num_points}, Truncated points: {truncated_data.num_points}")

            return str(output_path)

        except Exception as e:
            logger.error(f"Truncation error: {e}", exc_info=True)
            self.errorOccurred.emit("Truncation Error", str(e))
            return ""
    # ========================================================================
    # FILE/DATASET OPENING - Drag & Drop Support
    # ========================================================================

    @Slot(str)
    def openItem(self, item_name: str):
        """
        Open an item from the project browser in appropriate viewer.

        Handles:
        - Datasets (SpectralData) -> Enhanced Plot Window
        - CSV/Excel files -> Enhanced Table Window
        - Images (PNG, TIFF, etc.) -> System image viewer
        - Text files -> System text editor
        """
        try:
            # Check if it's a dataset
            if item_name in self._datasets:
                self._open_dataset_in_plot(item_name)
                return

            # Check if it's a file path
            from pathlib import Path
            item_path = Path(item_name)

            if item_path.exists() and item_path.is_file():
                self._open_file_by_type(item_path)
                return

            # Try to find it in outputs
            output_path = self._output_base_dir / item_name
            if output_path.exists() and output_path.is_file():
                self._open_file_by_type(output_path)
                return

            # Search in all subdirectories
            for subdir in ['curves', 'maps', 'smoothed', 'derivatives', 'discretized', 'fft', 'peaks']:
                search_path = self._output_base_dir / subdir / item_name
                if search_path.exists() and search_path.is_file():
                    self._open_file_by_type(search_path)
                    return

            logger.warning(f"Could not find item to open: {item_name}")
            self.errorOccurred.emit("Not Found", f"Item not found: {item_name}")

        except Exception as e:
            logger.error(f"Error opening item: {e}", exc_info=True)
            self.errorOccurred.emit("Open Error", str(e))

    # Large dataset threshold - prompt user before opening
    LARGE_DATASET_THRESHOLD = 500  # spectra count

    def _open_dataset_in_plot(self, dataset_name: str):
        """Open a dataset in both enhanced plot and table windows"""
        logger.info(f"Opening dataset in plot and table: {dataset_name}")

        dataset = self._datasets[dataset_name]

        # Check if dataset is large - prompt user first
        num_spectra = dataset.num_spectra if hasattr(dataset, 'num_spectra') else 0
        num_points = len(dataset.independent_var) if hasattr(dataset, 'independent_var') else 0

        if num_spectra > self.LARGE_DATASET_THRESHOLD:
            logger.info(f"Large dataset detected: {num_spectra} spectra, {num_points} points - prompting user")
            self.largeDatasetConfirmation.emit(dataset_name, num_spectra, num_points)
            return

        # Proceed with opening
        self._do_open_dataset_in_plot(dataset_name)

    @Slot(str)
    def confirmOpenLargeDataset(self, dataset_name: str):
        """Called when user confirms they want to open a large dataset"""
        logger.info(f"User confirmed opening large dataset: {dataset_name}")
        self._do_open_dataset_in_plot(dataset_name)

    @Slot(str)
    def cancelOpenLargeDataset(self, dataset_name: str):
        """Called when user cancels opening a large dataset"""
        logger.info(f"User cancelled opening large dataset: {dataset_name}")
        self.status = "Ready"

    def _do_open_dataset_in_plot(self, dataset_name: str):
        """Open a dataset in embedded graph and table windows via QML signals"""
        dataset = self._datasets[dataset_name]

        # Build curves list for embedded graph
        curves = []
        if hasattr(dataset, 'independent_var'):
            try:
                x = dataset.independent_var.tolist()
                y = dataset.spectra.iloc[:, 0].values.tolist() if dataset.num_spectra > 0 else []
                if len(y) > 0:
                    curves.append({
                        'x': x,
                        'y': y,
                        'label': dataset_name
                    })
            except Exception as e:
                logger.error(f"Error building curves: {e}")

        x_label = getattr(dataset, 'independent_var_name', 'x')
        y_label = 'Intensity'
        self.openDatasetEmbedded.emit(dataset_name, curves, x_label, y_label)

        # Build table data for embedded table
        self._emit_table_data(dataset_name, dataset)

        logger.info(f"Opened dataset {dataset_name} in embedded windows")

    def _emit_table_data(self, dataset_name: str, dataset):
        """Build and emit table data for embedded table window"""
        try:
            headers = []
            rows = []

            if hasattr(dataset, 'independent_var') and hasattr(dataset, 'spectra'):
                x_name = getattr(dataset, 'independent_var_name', 'x')
                headers.append(x_name)

                # Pull the real spectrum captions out of the DataFrame
                # column names (loaders stamp them there). Fall back to
                # ``Spectrum N`` only when the column name is missing —
                # processing/analysis is much easier when the headers
                # actually identify each spectrum.
                num_cols = dataset.num_spectra
                spectra_columns = list(dataset.spectra.columns)
                for i in range(num_cols):
                    name = (
                        str(spectra_columns[i]).strip()
                        if i < len(spectra_columns) and spectra_columns[i]
                        else ""
                    )
                    headers.append(name or f"Spectrum {i+1}")

                # Build rows
                x = dataset.independent_var
                num_rows = len(x)
                for r in range(num_rows):
                    row = [float(x[r])]
                    for c in range(num_cols):
                        row.append(float(dataset.spectra.iloc[r, c]))
                    rows.append(row)

            model = TableDataModel(self)
            model.setTableData(rows, headers)
            self._table_models.append(model)
            self.openTableEmbedded.emit(f"Table: {dataset_name}", model)
        except Exception as e:
            logger.error(f"Error building table data: {e}")

    @Slot(str, 'QVariantList')
    def openDatasetWithCurves(self, dataset_name: str, curve_indices: List):
        """Open a dataset in embedded windows with specific curves selected"""
        logger.info(f"Opening dataset with selected curves: {dataset_name}, curves: {curve_indices}")

        if dataset_name not in self._datasets:
            self.errorOccurred.emit("Error", f"Dataset not found: {dataset_name}")
            return

        dataset = self._datasets[dataset_name]

        # Build curves list for embedded graph
        curves = []
        if hasattr(dataset, 'independent_var'):
            try:
                x = dataset.independent_var.tolist()
                for idx in curve_indices:
                    if 0 <= idx < dataset.num_spectra:
                        y = dataset.spectra.iloc[:, idx].values.tolist()
                        if len(y) > 0:
                            curves.append({
                                'x': x,
                                'y': y,
                                'label': f"{dataset_name} - Curve {idx + 1}"
                            })
            except Exception as e:
                logger.error(f"Error building curves: {e}")

        x_label = getattr(dataset, 'independent_var_name', 'x')
        y_label = 'Intensity'
        self.openDatasetEmbedded.emit(dataset_name, curves, x_label, y_label)

        # Build table data
        self._emit_table_data(dataset_name, dataset)

        logger.info(f"Opened dataset {dataset_name} with {len(curve_indices)} curves in embedded windows")

    def _open_file_by_type(self, file_path: Path):
        """Open file in appropriate viewer based on extension"""
        extension = file_path.suffix.lower()

        # CSV/Excel -> Table
        if extension in ['.csv', '.xlsx', '.xls']:
            self._open_file_in_table(file_path)

        # Images -> System image viewer
        elif extension in ['.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.gif']:
            self._open_with_system_viewer(file_path)

        # Text files -> System text editor
        elif extension in ['.txt', '.log', '.md', '.json', '.xml', '.yaml', '.yml']:
            self._open_with_system_viewer(file_path)

        else:
            # Try to open with system default
            self._open_with_system_viewer(file_path)

    def _open_file_in_table(self, file_path: Path):
        """Open CSV/Excel file in embedded table"""
        import pandas as pd

        try:
            if file_path.suffix.lower() == '.csv':
                data = pd.read_csv(file_path)
            elif file_path.suffix.lower() in ['.xlsx', '.xls']:
                data = pd.read_excel(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_path.suffix}")

            headers = list(data.columns)
            max_cols = min(len(headers), 50)
            max_rows = min(len(data), 500)
            headers = headers[:max_cols]

            rows = []
            for r in range(max_rows):
                row = []
                for c in range(max_cols):
                    val = data.iloc[r, c]
                    row.append(float(val) if isinstance(val, (int, float)) else str(val))
                rows.append(row)

            model = TableDataModel(self)
            model.setTableData(rows, headers)
            self._table_models.append(model)
            self.openTableEmbedded.emit(f"Table: {file_path.name}", model)
            logger.info(f"Opened file in embedded table: {file_path}")

        except Exception as e:
            logger.error(f"Error opening file in table: {e}", exc_info=True)
            self.errorOccurred.emit("Open Error", f"Failed to open file:\n{e}")

    def _open_with_system_viewer(self, file_path: Path):
        """Open file with system default application"""
        import subprocess
        import platform

        try:
            system = platform.system()

            if system == 'Darwin':  # macOS
                subprocess.run(['open', str(file_path)], check=True)
            elif system == 'Windows':
                subprocess.run(['start', '', str(file_path)], shell=True, check=True)
            else:  # Linux
                subprocess.run(['xdg-open', str(file_path)], check=True)

            logger.info(f"Opened with system viewer: {file_path}")

        except Exception as e:
            logger.error(f"Error opening with system viewer: {e}", exc_info=True)
            self.errorOccurred.emit("Open Error", f"Failed to open file:\n{e}")

    # ========================================================================
    # IMAGE IMPORT - For Map Editor
    # ========================================================================

    @Slot(str)
    def importImage(self, file_path: str):
        """
        Import an image file (TIFF, PNG, NPY, etc.) and open it in the Map Editor.

        Parameters:
            file_path: Path to the image file
        """
        try:
            path = Path(file_path)
            if not path.exists():
                self.errorOccurred.emit("File Not Found", f"File not found: {file_path}")
                return

            logger.info(f"Importing image: {path}")
            self.status = f"Importing {path.name}..."

            extension = path.suffix.lower()

            # Load image based on format
            if extension in ['.tif', '.tiff']:
                import tifffile
                data = tifffile.imread(str(path))
            elif extension in ['.png', '.jpg', '.jpeg', '.bmp']:
                from PIL import Image
                img = Image.open(str(path))
                # Convert to grayscale if RGB
                if img.mode == 'RGB' or img.mode == 'RGBA':
                    img = img.convert('L')
                data = np.array(img, dtype=np.float64)
            elif extension == '.npy':
                data = np.load(str(path))
            elif extension == '.gsf':
                # Gwyddion Simple Field format - basic parser
                data = self._load_gsf(path)
            else:
                self.errorOccurred.emit("Unsupported Format", f"Unsupported image format: {extension}")
                return

            # Ensure 2D
            if data.ndim == 3:
                # Multi-channel image - take first channel or average
                if data.shape[2] <= 4:  # RGB(A)
                    data = np.mean(data, axis=2)
                elif data.shape[0] <= 4:  # Channel-first format
                    data = np.mean(data, axis=0)
                else:
                    data = data[0]  # Take first slice

            if data.ndim != 2:
                self.errorOccurred.emit("Invalid Image", f"Could not convert to 2D image: shape={data.shape}")
                return

            # Create a dataset name
            dataset_name = f"Image_{path.stem}"
            counter = 1
            while dataset_name in self._datasets:
                dataset_name = f"Image_{path.stem}_{counter}"
                counter += 1

            # Store as map data in Maps list
            self._window_id_counter += 1
            map_id = f"map_{self._window_id_counter}"

            # Copy to maps directory
            if self._output_base_dir:
                maps_dir = self._output_base_dir / "maps"
                maps_dir.mkdir(parents=True, exist_ok=True)
                dest_path = maps_dir / f"{dataset_name}{extension}"

                # Save data
                if extension in ['.tif', '.tiff']:
                    import tifffile
                    tifffile.imwrite(str(dest_path), data.astype(np.float32))
                else:
                    np.save(str(maps_dir / f"{dataset_name}.npy"), data)
                    dest_path = maps_dir / f"{dataset_name}.npy"

                # Emit map created signal
                self.mapCreated.emit(map_id, dataset_name)

            # Store map data for the Map Editor to access
            self._imported_map_data = data
            self._imported_map_name = dataset_name
            self._imported_map_path = str(path)

            # Emit signal to open in Map Editor tab (docked, not separate window)
            self.imageImported.emit(dataset_name, str(path), map_id)

            self.status = f"Imported: {dataset_name}"
            logger.info(f"Image imported: {dataset_name}, shape={data.shape}")

        except Exception as e:
            logger.error(f"Error importing image: {e}", exc_info=True)
            self.errorOccurred.emit("Import Error", f"Failed to import image:\n{e}")
            self.status = "Ready"

    @Slot(result='QVariantMap')
    def getImportedMapData(self) -> Dict:
        """
        Get the most recently imported map data for the Map Editor.

        Returns:
            Dict with 'data' (as list of lists), 'name', 'path', 'rows', 'cols'
        """
        if self._imported_map_data is None:
            return {'error': 'No map data available'}

        return {
            'data': self._imported_map_data.tolist(),
            'name': self._imported_map_name,
            'path': self._imported_map_path,
            'rows': self._imported_map_data.shape[0],
            'cols': self._imported_map_data.shape[1]
        }

    @Slot()
    def clearImportedMapData(self):
        """Clear the imported map data after it has been consumed."""
        self._imported_map_data = None
        self._imported_map_name = ""
        self._imported_map_path = ""

    def _load_gsf(self, path: Path) -> np.ndarray:
        """
        Load Gwyddion Simple Field (.gsf) format.
        Basic implementation - extend as needed.
        """
        with open(path, 'rb') as f:
            # Check magic
            magic = f.read(4)
            if magic != b'Gwyd':
                raise ValueError("Not a valid GSF file")

            # Read header
            header = {}
            while True:
                line = b''
                while True:
                    char = f.read(1)
                    if char == b'\n' or char == b'\x00':
                        break
                    line += char

                line = line.decode('utf-8').strip()
                if not line:
                    break

                if '=' in line:
                    key, value = line.split('=', 1)
                    header[key.strip()] = value.strip()

            # Read data
            xres = int(header.get('XRes', 256))
            yres = int(header.get('YRes', 256))

            # Skip to data (after null byte)
            f.read(1)

            # Read binary data
            data = np.frombuffer(f.read(), dtype=np.float32)
            data = data[:xres * yres].reshape((yres, xres))

            return data

    # ========================================================================
    # TOOL IMPLEMENTATIONS - Filter Bad Data
    # Algorithms adapted from ststools by Rafael Reis
    # (https://github.com/rafinhareis/ststools)
    # ========================================================================

    @Slot(str, float, float, float, float, float, float, bool)
    def filterBadData(self, dataset_name: str, weight_saturation: float,
                      weight_noise: float, weight_linear: float,
                      weight_periodic: float, weight_partial_noise: float,
                      threshold: float, correct_periodic: bool):
        """QML wrapper for filter bad data - runs in background thread."""
        logger.info(f"Submitting filter bad data for {dataset_name} to worker")
        self.status = f"Filtering bad data for {dataset_name}..."
        self.worker_manager.submit(
            name=f"Filter Bad Data {dataset_name}",
            operation=self.filter_bad_data,
            dataset_name=dataset_name,
            weight_saturation=weight_saturation,
            weight_noise=weight_noise,
            weight_linear=weight_linear,
            weight_periodic=weight_periodic,
            weight_partial_noise=weight_partial_noise,
            threshold=threshold,
            correct_periodic=correct_periodic,
            on_finished=lambda path: self._on_tool_completed("Filter Bad Data", path)
        )

    # ========================================================================
    # TOOL IMPLEMENTATIONS - Detect Bandgap & Doping
    # Algorithms adapted from ststools by Rafael Reis
    # (https://github.com/rafinhareis/ststools)
    # ========================================================================

    @Slot(str, float, float, float, str)
    def detectBandgapDoping(self, dataset_name: str, smoothing: float,
                            delta: float, resolution: float,
                            smoothing_method: str):
        """QML wrapper for bandgap/doping detection - runs in background thread."""
        logger.info(f"Submitting bandgap/doping detection for {dataset_name} to worker")
        self.status = f"Detecting bandgap/doping for {dataset_name}..."
        self.worker_manager.submit(
            name=f"Bandgap/Doping {dataset_name}",
            operation=self.detect_bandgap_doping,
            dataset_name=dataset_name,
            smoothing=smoothing,
            delta=delta,
            resolution=resolution,
            smoothing_method=smoothing_method,
            on_finished=lambda path: self._on_tool_completed("Detect Bandgap & Doping", path)
        )

    # ========================================================================
    # TOOL IMPLEMENTATIONS - Dirac Point Estimator
    # Algorithms adapted from ststools by Rafael Reis
    # (https://github.com/rafinhareis/ststools)
    # ========================================================================

    @Slot(str, float, float, float, float, float, str, bool)
    def estimateDiracPoint(self, dataset_name: str, left_min: float,
                           left_max: float, right_min: float, right_max: float,
                           smoothing: float, smoothing_method: str,
                           auto_detect: bool = False):
        """QML wrapper for Dirac point estimation - runs in background thread."""
        logger.info(f"Submitting Dirac point estimation for {dataset_name} to worker (auto_detect={auto_detect})")
        self.status = f"Estimating Dirac point for {dataset_name}..."
        self.worker_manager.submit(
            name=f"Dirac Point {dataset_name}",
            operation=self.estimate_dirac_point,
            dataset_name=dataset_name,
            left_min=left_min,
            left_max=left_max,
            right_min=right_min,
            right_max=right_max,
            smoothing=smoothing,
            smoothing_method=smoothing_method,
            auto_detect=auto_detect,
            on_finished=lambda path: self._on_tool_completed("Dirac Point Estimator", path)
        )
