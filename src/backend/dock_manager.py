"""
Dock Manager for Window Layout System
Handles docking, tabbing, split views, and workspace presets
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from PySide6.QtCore import QObject, Signal, Slot, Property

logger = logging.getLogger(__name__)


class DockManager(QObject):
    """
    Manages window docking, layouts, and workspace presets.

    Features:
    - Dock windows to left, right, top, bottom
    - Tabbed interfaces within dock areas
    - Split views (horizontal/vertical)
    - Save/load workspace layouts
    - Preset management
    """

    # Signals
    layoutChanged = Signal()
    presetLoaded = Signal(str)  # preset_name
    presetSaved = Signal(str)  # preset_name

    def __init__(self, config_dir: Path = None):
        super().__init__()

        # Configuration directory for presets
        self.config_dir = config_dir or (Path.home() / ".trans_qml")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.presets_dir = self.config_dir / "layouts"
        self.presets_dir.mkdir(exist_ok=True)

        # Default layout file
        self.default_layout_file = self.config_dir / "default_layout.json"

        # Current layout state
        self.layout = {
            'version': '1.0',
            'dock_areas': {
                'left': {'windows': [], 'splits': [], 'width': 300},
                'right': {'windows': [], 'splits': [], 'width': 300},
                'top': {'windows': [], 'splits': [], 'height': 200},
                'bottom': {'windows': [], 'splits': [], 'height': 200},
                'center': {'windows': [], 'splits': []},
                'floating': []  # Floating windows
            },
            'active_tabs': {},  # dock_area -> active_window_id
            'window_states': {}  # window_id -> {title, type, geometry, ...}
        }

        logger.info(f"DockManager initialized. Config dir: {self.config_dir}")

    @Slot(str, str)
    def dockWindow(self, window_id: str, dock_position: str):
        """
        Dock a window to a specific position.

        Parameters:
        -----------
        window_id : str
            Unique identifier for the window
        dock_position : str
            One of: 'left', 'right', 'top', 'bottom', 'center', 'float'
        """
        dock_position = dock_position.lower()

        # Remove window from current position
        self._removeWindowFromAllDocks(window_id)

        # Add to new position
        if dock_position == 'float':
            if window_id not in self.layout['dock_areas']['floating']:
                self.layout['dock_areas']['floating'].append(window_id)
        elif dock_position in ['left', 'right', 'top', 'bottom', 'center']:
            windows = self.layout['dock_areas'][dock_position]['windows']
            if window_id not in windows:
                windows.append(window_id)
                # Set as active tab
                self.layout['active_tabs'][dock_position] = window_id
        else:
            logger.warning(f"Invalid dock position: {dock_position}")
            return

        self.layoutChanged.emit()
        logger.info(f"Docked window {window_id} to {dock_position}")

    @Slot(str)
    def undockWindow(self, window_id: str):
        """Float a currently docked window."""
        self.dockWindow(window_id, 'float')

    @Slot(str)
    def closeWindow(self, window_id: str):
        """Remove window from layout."""
        self._removeWindowFromAllDocks(window_id)
        if window_id in self.layout['window_states']:
            del self.layout['window_states'][window_id]
        self.layoutChanged.emit()
        logger.info(f"Closed window {window_id}")

    @Slot(str, 'QVariantMap')
    def registerWindow(self, window_id: str, window_info: Dict):
        """
        Register a window with the dock manager.

        Parameters:
        -----------
        window_id : str
            Unique window identifier
        window_info : dict
            Window metadata: {title, type, geometry, ...}
        """
        self.layout['window_states'][window_id] = window_info
        logger.info(f"Registered window: {window_id} - {window_info.get('title', '')}")

    @Slot(str, str)
    def setActiveTab(self, dock_area: str, window_id: str):
        """Set the active tab in a dock area."""
        self.layout['active_tabs'][dock_area] = window_id
        self.layoutChanged.emit()

    @Slot(str, result=str)
    def getActiveTab(self, dock_area: str) -> str:
        """Get the active tab in a dock area."""
        return self.layout['active_tabs'].get(dock_area, '')

    @Slot(str, result='QVariantList')
    def getDockedWindows(self, dock_area: str) -> List[str]:
        """Get list of windows in a dock area."""
        if dock_area in self.layout['dock_areas']:
            return self.layout['dock_areas'][dock_area]['windows']
        return []

    @Slot(result='QVariantList')
    def getFloatingWindows(self) -> List[str]:
        """Get list of floating windows."""
        return self.layout['dock_areas']['floating']

    @Slot(str, result='QVariantMap')
    def getWindowState(self, window_id: str) -> Dict:
        """Get window state information."""
        return self.layout['window_states'].get(window_id, {})

    @Slot(str, result='QVariantMap')
    def saveLayout(self, layout_name: str = "") -> Dict:
        """
        Save current layout to file.

        Parameters:
        -----------
        layout_name : str, optional
            Name for the layout. If empty, saves to default.

        Returns:
        --------
        dict with {'success': bool, 'path': str, 'message': str}
        """
        try:
            if layout_name:
                layout_file = self.presets_dir / f"{layout_name}.json"
            else:
                layout_file = self.default_layout_file

            with open(layout_file, 'w', encoding='utf-8') as f:
                json.dump(self.layout, f, indent=2)

            if layout_name:
                self.presetSaved.emit(layout_name)

            logger.info(f"Layout saved: {layout_file}")
            return {
                'success': True,
                'path': str(layout_file),
                'message': f"Layout saved as {layout_name or 'default'}"
            }

        except Exception as e:
            logger.error(f"Failed to save layout: {e}", exc_info=True)
            return {
                'success': False,
                'path': '',
                'message': f"Error: {str(e)}"
            }

    @Slot(str, result='QVariantMap')
    def loadLayout(self, layout_name: str = "") -> Dict:
        """
        Load layout from file.

        Parameters:
        -----------
        layout_name : str, optional
            Name of the layout to load. If empty, loads default.

        Returns:
        --------
        dict with {'success': bool, 'layout': dict, 'message': str}
        """
        try:
            if layout_name:
                layout_file = self.presets_dir / f"{layout_name}.json"
            else:
                layout_file = self.default_layout_file

            if not layout_file.exists():
                return {
                    'success': False,
                    'layout': {},
                    'message': f"Layout not found: {layout_name or 'default'}"
                }

            with open(layout_file, 'r', encoding='utf-8') as f:
                loaded_layout = json.load(f)

            # Validate layout structure
            if 'dock_areas' not in loaded_layout:
                raise ValueError("Invalid layout file structure")

            self.layout = loaded_layout
            self.layoutChanged.emit()

            if layout_name:
                self.presetLoaded.emit(layout_name)

            logger.info(f"Layout loaded: {layout_file}")
            return {
                'success': True,
                'layout': self.layout,
                'message': f"Layout '{layout_name or 'default'}' loaded"
            }

        except Exception as e:
            logger.error(f"Failed to load layout: {e}", exc_info=True)
            return {
                'success': False,
                'layout': {},
                'message': f"Error: {str(e)}"
            }

    @Slot(str)
    def setAsDefaultLayout(self, layout_name: str):
        """Save a preset as the default layout."""
        try:
            preset_file = self.presets_dir / f"{layout_name}.json"
            if preset_file.exists():
                # Copy preset to default
                with open(preset_file, 'r') as src:
                    layout_data = src.read()
                with open(self.default_layout_file, 'w') as dst:
                    dst.write(layout_data)
                logger.info(f"Set {layout_name} as default layout")
            else:
                logger.warning(f"Preset not found: {layout_name}")
        except Exception as e:
            logger.error(f"Failed to set default layout: {e}")

    @Slot(result='QVariantList')
    def getAvailablePresets(self) -> List[str]:
        """Get list of available layout presets."""
        try:
            presets = []
            for file in self.presets_dir.glob("*.json"):
                presets.append(file.stem)
            return sorted(presets)
        except Exception as e:
            logger.error(f"Failed to get presets: {e}")
            return []

    @Slot(str, result=bool)
    def deletePreset(self, layout_name: str) -> bool:
        """Delete a layout preset."""
        try:
            preset_file = self.presets_dir / f"{layout_name}.json"
            if preset_file.exists():
                preset_file.unlink()
                logger.info(f"Deleted preset: {layout_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete preset: {e}")
            return False

    @Slot()
    def resetLayout(self):
        """Reset to empty layout."""
        self.layout = {
            'version': '1.0',
            'dock_areas': {
                'left': {'windows': [], 'splits': [], 'width': 300},
                'right': {'windows': [], 'splits': [], 'width': 300},
                'top': {'windows': [], 'splits': [], 'height': 200},
                'bottom': {'windows': [], 'splits': [], 'height': 200},
                'center': {'windows': [], 'splits': []},
                'floating': []
            },
            'active_tabs': {},
            'window_states': {}
        }
        self.layoutChanged.emit()
        logger.info("Layout reset")

    @Slot(result='QVariantMap')
    def getCurrentLayout(self) -> Dict:
        """Get the current layout state."""
        return self.layout

    def _removeWindowFromAllDocks(self, window_id: str):
        """Remove window from all dock areas."""
        for dock_name, dock_data in self.layout['dock_areas'].items():
            if dock_name == 'floating':
                if window_id in dock_data:
                    dock_data.remove(window_id)
            elif 'windows' in dock_data and window_id in dock_data['windows']:
                dock_data['windows'].remove(window_id)

        # Remove from active tabs
        for dock_area, active_id in list(self.layout['active_tabs'].items()):
            if active_id == window_id:
                # Set next tab as active if available
                windows = self.layout['dock_areas'][dock_area]['windows']
                if windows:
                    self.layout['active_tabs'][dock_area] = windows[0]
                else:
                    del self.layout['active_tabs'][dock_area]
