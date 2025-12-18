"""
Multi-Channel Map Data Model
Structure for handling SNOM/AFM multi-channel data (height, amplitude, phase, etc.)
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
from typing import Optional, Tuple, List, Dict, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import logging
from PIL import Image
import copy

logger = logging.getLogger(__name__)


class ChannelType(Enum):
    """Standard channel types for SNOM/AFM data"""
    HEIGHT = "height"
    AMPLITUDE = "amplitude"
    PHASE = "phase"
    OPTICAL = "optical"
    ERROR = "error"
    CUSTOM = "custom"


@dataclass
class ChannelMetadata:
    """Metadata for a single channel"""
    name: str
    channel_type: ChannelType = ChannelType.CUSTOM
    units: str = "a.u."
    physical_min: Optional[float] = None
    physical_max: Optional[float] = None
    description: str = ""

    def __post_init__(self):
        """Auto-detect channel type from name if custom"""
        if self.channel_type == ChannelType.CUSTOM:
            name_lower = self.name.lower()
            if "height" in name_lower or "topo" in name_lower or "z" == name_lower:
                self.channel_type = ChannelType.HEIGHT
                if not self.units or self.units == "a.u.":
                    self.units = "nm"
            elif "amp" in name_lower or "amplitude" in name_lower:
                self.channel_type = ChannelType.AMPLITUDE
            elif "phase" in name_lower or "phi" in name_lower:
                self.channel_type = ChannelType.PHASE
                if not self.units or self.units == "a.u.":
                    self.units = "deg"
            elif "optical" in name_lower or "nsom" in name_lower or "snom" in name_lower:
                self.channel_type = ChannelType.OPTICAL
            elif "error" in name_lower:
                self.channel_type = ChannelType.ERROR


@dataclass
class MapMetadata:
    """Metadata for the entire multi-channel map"""
    dimensions: Tuple[int, int]  # (height, width) in pixels
    physical_size: Optional[Tuple[float, float]] = None  # (y_size, x_size) in units
    physical_units: str = "um"  # Physical size units (um, nm, mm)
    scan_direction: str = "forward"  # forward, backward, average
    scan_mode: str = "contact"  # contact, tapping, non-contact
    source_file: Optional[str] = None
    creation_date: Optional[str] = None
    instrument: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def pixel_size(self) -> Optional[Tuple[float, float]]:
        """Calculate pixel size in physical units (y_pixel, x_pixel)"""
        if self.physical_size is None:
            return None
        return (
            self.physical_size[0] / self.dimensions[0],
            self.physical_size[1] / self.dimensions[1]
        )

    @property
    def aspect_ratio(self) -> float:
        """Get width/height aspect ratio"""
        return self.dimensions[1] / self.dimensions[0]


class MapChannel:
    """
    Single channel of map data with processing history.

    Attributes:
        data: 2D numpy array of channel values
        metadata: Channel metadata (name, type, units)
        mask: Optional boolean mask for invalid/excluded pixels
        history: List of processing operations applied
    """

    def __init__(self,
                 data: np.ndarray,
                 metadata: Optional[ChannelMetadata] = None,
                 mask: Optional[np.ndarray] = None):
        """
        Initialize MapChannel.

        Parameters:
            data: 2D numpy array of values
            metadata: Channel metadata
            mask: Boolean mask (True = masked/invalid)
        """
        if data.ndim != 2:
            raise ValueError(f"Channel data must be 2D, got {data.ndim}D")

        self.data = data.astype(np.float64)
        self.metadata = metadata or ChannelMetadata(name="Untitled")
        self.mask = mask
        self.history: List[Dict[str, Any]] = []

        # Cache for visualization
        self._display_cache: Optional[np.ndarray] = None
        self._display_params: Dict[str, Any] = {}

    @property
    def shape(self) -> Tuple[int, int]:
        return self.data.shape

    @property
    def name(self) -> str:
        return self.metadata.name

    @name.setter
    def name(self, value: str):
        self.metadata.name = value

    @property
    def valid_data(self) -> np.ndarray:
        """Get data with masked values set to NaN"""
        if self.mask is None:
            return self.data
        result = self.data.copy()
        result[self.mask] = np.nan
        return result

    def normalize(self,
                  vmin: Optional[float] = None,
                  vmax: Optional[float] = None,
                  percentile: Optional[Tuple[float, float]] = None) -> np.ndarray:
        """
        Normalize channel data to [0, 1] range.

        Parameters:
            vmin: Minimum value (default: data min)
            vmax: Maximum value (default: data max)
            percentile: Use percentiles instead of min/max, e.g., (2, 98)

        Returns:
            Normalized array in [0, 1] range
        """
        valid = self.valid_data

        if percentile is not None:
            vmin = np.nanpercentile(valid, percentile[0])
            vmax = np.nanpercentile(valid, percentile[1])
        else:
            if vmin is None:
                vmin = np.nanmin(valid)
            if vmax is None:
                vmax = np.nanmax(valid)

        if vmax == vmin:
            logger.warning(f"Channel '{self.name}': vmin equals vmax, returning zeros")
            return np.zeros_like(self.data)

        normalized = (self.data - vmin) / (vmax - vmin)
        return np.clip(normalized, 0, 1)

    def get_statistics(self, use_mask: bool = True) -> Dict[str, float]:
        """
        Calculate channel statistics.

        Parameters:
            use_mask: Whether to exclude masked pixels

        Returns:
            Dictionary with min, max, mean, std, median, rms
        """
        data = self.valid_data if use_mask else self.data

        return {
            'min': float(np.nanmin(data)),
            'max': float(np.nanmax(data)),
            'mean': float(np.nanmean(data)),
            'std': float(np.nanstd(data)),
            'median': float(np.nanmedian(data)),
            'rms': float(np.sqrt(np.nanmean(data**2))),
            'range': float(np.nanmax(data) - np.nanmin(data)),
        }

    def extract_profile(self,
                        start: Tuple[int, int],
                        end: Tuple[int, int],
                        width: int = 1) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract line profile between two points.

        Parameters:
            start: Starting point (row, col)
            end: Ending point (row, col)
            width: Profile averaging width in pixels

        Returns:
            Tuple of (distance array, values array)
        """
        from scipy import ndimage

        # Calculate profile length
        length = int(np.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2))
        if length == 0:
            return np.array([0]), np.array([self.data[start[0], start[1]]])

        # Generate coordinates along the line
        rows = np.linspace(start[0], end[0], length)
        cols = np.linspace(start[1], end[1], length)

        # Extract values using interpolation
        if width == 1:
            values = ndimage.map_coordinates(self.data, [rows, cols], order=1)
        else:
            # Average over width perpendicular to line
            # Direction perpendicular to line
            dx = end[1] - start[1]
            dy = end[0] - start[0]
            norm = np.sqrt(dx**2 + dy**2)
            perp_x = -dy / norm
            perp_y = dx / norm

            values = np.zeros(length)
            for offset in range(-width//2, width//2 + 1):
                r = rows + offset * perp_x
                c = cols + offset * perp_y
                # Clip to valid range
                r = np.clip(r, 0, self.shape[0] - 1)
                c = np.clip(c, 0, self.shape[1] - 1)
                values += ndimage.map_coordinates(self.data, [r, c], order=1)
            values /= width

        # Distance array
        distance = np.linspace(0, length, length)

        return distance, values

    def add_history(self, operation: str, parameters: Dict[str, Any]):
        """Record a processing operation in history"""
        self.history.append({
            'operation': operation,
            'parameters': parameters.copy()
        })
        # Invalidate display cache
        self._display_cache = None

    def copy(self) -> 'MapChannel':
        """Create a deep copy of this channel"""
        new_channel = MapChannel(
            data=self.data.copy(),
            metadata=copy.deepcopy(self.metadata),
            mask=self.mask.copy() if self.mask is not None else None
        )
        new_channel.history = copy.deepcopy(self.history)
        return new_channel

    def __repr__(self) -> str:
        return (f"MapChannel(name='{self.name}', shape={self.shape}, "
                f"type={self.metadata.channel_type.value})")


class MultiChannelMap:
    """
    Container for multi-channel map data (SNOM/AFM).

    Supports multiple channels (height, amplitude, phase, etc.) with
    shared spatial coordinates and metadata. Can be linked to spectral
    data for spatial-spectral reconstruction (clicking on map shows spectrum).

    Attributes:
        channels: Dictionary mapping channel names to MapChannel objects
        metadata: Map-level metadata (dimensions, physical size, etc.)
        masks: Named boolean masks for region selection
        spectral_link: Optional reference to linked SpectralData for reconstruction
    """

    def __init__(self,
                 metadata: Optional[MapMetadata] = None):
        """
        Initialize empty MultiChannelMap.

        Parameters:
            metadata: Map-level metadata
        """
        self.channels: Dict[str, MapChannel] = {}
        self.metadata = metadata
        self.masks: Dict[str, np.ndarray] = {}
        self._active_channel: Optional[str] = None

        # Spectral-spatial linking
        self._spectral_data = None  # Reference to linked SpectralData
        self._spectral_cube: Optional[np.ndarray] = None  # Cached 3D cube (n_pts, rows, cols)
        self._independent_var: Optional[np.ndarray] = None  # Wavenumber/voltage axis
        self._independent_var_name: str = "x"

    @property
    def shape(self) -> Optional[Tuple[int, int]]:
        """Get common shape of all channels"""
        if not self.channels:
            return None
        return next(iter(self.channels.values())).shape

    @property
    def channel_names(self) -> List[str]:
        """Get list of channel names in order"""
        return list(self.channels.keys())

    @property
    def active_channel(self) -> Optional[MapChannel]:
        """Get currently active channel"""
        if self._active_channel and self._active_channel in self.channels:
            return self.channels[self._active_channel]
        if self.channels:
            return next(iter(self.channels.values()))
        return None

    @property
    def active_channel_name(self) -> Optional[str]:
        """Get name of currently active channel"""
        if self._active_channel and self._active_channel in self.channels:
            return self._active_channel
        if self.channels:
            return next(iter(self.channels.keys()))
        return None

    def set_active_channel(self, name: str):
        """Set active channel by name"""
        if name not in self.channels:
            raise KeyError(f"Channel '{name}' not found")
        self._active_channel = name

    def add_channel(self,
                    name: str,
                    data: np.ndarray,
                    channel_type: ChannelType = ChannelType.CUSTOM,
                    units: str = "a.u.",
                    replace: bool = False) -> MapChannel:
        """
        Add a channel to the map.

        Parameters:
            name: Channel name
            data: 2D numpy array
            channel_type: Type of channel data
            units: Physical units
            replace: If True, replace existing channel with same name

        Returns:
            The created MapChannel
        """
        if name in self.channels and not replace:
            raise ValueError(f"Channel '{name}' already exists. Use replace=True to overwrite.")

        # Validate dimensions match
        if self.shape is not None and data.shape != self.shape:
            raise ValueError(f"Channel shape {data.shape} doesn't match map shape {self.shape}")

        metadata = ChannelMetadata(
            name=name,
            channel_type=channel_type,
            units=units
        )

        channel = MapChannel(data, metadata)
        self.channels[name] = channel

        # Update map metadata if first channel
        if self.metadata is None:
            self.metadata = MapMetadata(dimensions=data.shape)

        # Set as active if first channel
        if self._active_channel is None:
            self._active_channel = name

        logger.info(f"Added channel '{name}' ({channel_type.value}) to map")
        return channel

    def remove_channel(self, name: str):
        """Remove a channel from the map"""
        if name not in self.channels:
            raise KeyError(f"Channel '{name}' not found")

        del self.channels[name]

        # Update active channel if needed
        if self._active_channel == name:
            self._active_channel = next(iter(self.channels.keys()), None)

        logger.info(f"Removed channel '{name}' from map")

    def get_channel(self, name: str) -> MapChannel:
        """Get channel by name"""
        if name not in self.channels:
            raise KeyError(f"Channel '{name}' not found. Available: {self.channel_names}")
        return self.channels[name]

    def duplicate_channel(self, source_name: str, new_name: str) -> MapChannel:
        """Create a copy of an existing channel"""
        source = self.get_channel(source_name)
        new_channel = source.copy()
        new_channel.metadata.name = new_name
        self.channels[new_name] = new_channel
        logger.info(f"Duplicated channel '{source_name}' to '{new_name}'")
        return new_channel

    def add_mask(self, name: str, mask: np.ndarray):
        """Add a named mask to the map"""
        if mask.shape != self.shape:
            raise ValueError(f"Mask shape {mask.shape} doesn't match map shape {self.shape}")
        self.masks[name] = mask.astype(bool)
        logger.info(f"Added mask '{name}' to map")

    def remove_mask(self, name: str):
        """Remove a named mask"""
        if name in self.masks:
            del self.masks[name]
            logger.info(f"Removed mask '{name}' from map")

    def apply_mask_to_channel(self, mask_name: str, channel_name: str):
        """Apply a named mask to a channel"""
        if mask_name not in self.masks:
            raise KeyError(f"Mask '{mask_name}' not found")
        channel = self.get_channel(channel_name)
        channel.mask = self.masks[mask_name].copy()

    def get_combined_statistics(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all channels"""
        return {name: ch.get_statistics() for name, ch in self.channels.items()}

    def copy(self) -> 'MultiChannelMap':
        """Create a deep copy of this map"""
        new_map = MultiChannelMap(
            metadata=copy.deepcopy(self.metadata)
        )
        for name, channel in self.channels.items():
            new_map.channels[name] = channel.copy()
        for name, mask in self.masks.items():
            new_map.masks[name] = mask.copy()
        new_map._active_channel = self._active_channel
        return new_map

    @classmethod
    def from_arrays(cls,
                    arrays: Dict[str, np.ndarray],
                    physical_size: Optional[Tuple[float, float]] = None,
                    units: str = "um") -> 'MultiChannelMap':
        """
        Create MultiChannelMap from dictionary of arrays.

        Parameters:
            arrays: Dictionary mapping channel names to 2D arrays
            physical_size: Physical dimensions (y, x)
            units: Physical units

        Returns:
            New MultiChannelMap
        """
        if not arrays:
            raise ValueError("At least one array required")

        # Get dimensions from first array
        first_key = next(iter(arrays))
        shape = arrays[first_key].shape

        metadata = MapMetadata(
            dimensions=shape,
            physical_size=physical_size,
            physical_units=units
        )

        mmap = cls(metadata=metadata)
        for name, data in arrays.items():
            mmap.add_channel(name, data)

        return mmap

    @classmethod
    def from_gsf(cls, filepath: Union[str, Path]) -> 'MultiChannelMap':
        """
        Load from Gwyddion Simple Field format.

        Parameters:
            filepath: Path to .gsf file

        Returns:
            Loaded MultiChannelMap
        """
        # Basic GSF parser - extend as needed
        filepath = Path(filepath)

        with open(filepath, 'rb') as f:
            # Read header
            magic = f.read(4)
            if magic != b'Gwyd':
                raise ValueError("Not a valid GSF file")

            # This is a simplified loader - full GSF has more complexity
            # For now, read as raw binary
            raise NotImplementedError("Full GSF loading not yet implemented")

    def save_channel_image(self,
                           channel_name: str,
                           filepath: Union[str, Path],
                           colormap: str = 'viridis',
                           percentile: Tuple[float, float] = (2, 98)):
        """
        Save a channel as an image file.

        Parameters:
            channel_name: Name of channel to save
            filepath: Output path
            colormap: Matplotlib colormap name
            percentile: Contrast percentiles for normalization
        """
        import matplotlib.cm as cm

        channel = self.get_channel(channel_name)
        normalized = channel.normalize(percentile=percentile)

        cmap = cm.get_cmap(colormap)
        colored = cmap(normalized)
        img_data = (colored[:, :, :3] * 255).astype(np.uint8)

        Image.fromarray(img_data, mode='RGB').save(filepath)
        logger.info(f"Saved channel '{channel_name}' to {filepath}")

    def save_all_channels(self,
                          output_dir: Union[str, Path],
                          prefix: str = "",
                          format: str = "png",
                          colormap: str = 'viridis'):
        """Save all channels as separate image files"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for name in self.channel_names:
            safe_name = name.replace("/", "_").replace("\\", "_")
            filename = f"{prefix}{safe_name}.{format}" if prefix else f"{safe_name}.{format}"
            self.save_channel_image(name, output_dir / filename, colormap=colormap)

    # =========================================================================
    # Spectral-Spatial Reconstruction (trans_v3.py paradigm)
    # =========================================================================

    @property
    def has_spectral_link(self) -> bool:
        """Check if spectral data is linked for spatial reconstruction"""
        return self._spectral_cube is not None

    @property
    def spectral_points(self) -> int:
        """Number of points in linked spectral data"""
        if self._spectral_cube is None:
            return 0
        return self._spectral_cube.shape[0]

    @property
    def independent_var(self) -> Optional[np.ndarray]:
        """Get independent variable (wavenumber, voltage, etc.)"""
        return self._independent_var

    @property
    def independent_var_name(self) -> str:
        """Get name of independent variable"""
        return self._independent_var_name

    def link_spectral_data(self,
                           spectral_data,
                           independent_var_name: Optional[str] = None):
        """
        Link SpectralData object for spatial-spectral reconstruction.

        This enables clicking on the map to retrieve the spectrum at that point.

        Parameters:
            spectral_data: SpectralData object with spatial spectra
            independent_var_name: Override name of independent variable
        """
        # Import here to avoid circular dependency
        from src.models.spectral_data import SpectralData

        if not isinstance(spectral_data, SpectralData):
            raise TypeError("spectral_data must be a SpectralData object")

        # Cache the 3D cube for fast access
        try:
            self._spectral_cube = spectral_data.to_3d_cube()
            self._independent_var = spectral_data.independent_var
            self._independent_var_name = independent_var_name or spectral_data.independent_var_name
            self._spectral_data = spectral_data

            # Verify dimensions match
            cube_shape = (self._spectral_cube.shape[1], self._spectral_cube.shape[2])
            if self.shape is not None and cube_shape != self.shape:
                logger.warning(f"Spectral cube shape {cube_shape} differs from map shape {self.shape}")

            logger.info(f"Linked spectral data: {self._spectral_cube.shape[0]} points, "
                       f"{cube_shape[0]}x{cube_shape[1]} spatial grid")

        except Exception as e:
            logger.error(f"Failed to link spectral data: {e}")
            raise

    def link_spectral_cube(self,
                           cube: np.ndarray,
                           independent_var: np.ndarray,
                           independent_var_name: str = "x"):
        """
        Link a pre-computed spectral cube for spatial-spectral reconstruction.

        Parameters:
            cube: 3D array with shape (n_spectral_points, rows, cols)
            independent_var: 1D array of independent variable values
            independent_var_name: Name of independent variable (e.g., 'Wavenumber', 'Voltage')
        """
        if cube.ndim != 3:
            raise ValueError(f"Spectral cube must be 3D, got {cube.ndim}D")

        if len(independent_var) != cube.shape[0]:
            raise ValueError(f"Independent var length {len(independent_var)} doesn't match "
                           f"cube first dimension {cube.shape[0]}")

        self._spectral_cube = cube
        self._independent_var = independent_var
        self._independent_var_name = independent_var_name

        # Verify dimensions match
        cube_shape = (cube.shape[1], cube.shape[2])
        if self.shape is not None and cube_shape != self.shape:
            logger.warning(f"Spectral cube shape {cube_shape} differs from map shape {self.shape}")

        logger.info(f"Linked spectral cube: {cube.shape[0]} points, "
                   f"{cube_shape[0]}x{cube_shape[1]} spatial grid")

    def unlink_spectral_data(self):
        """Remove spectral data link"""
        self._spectral_data = None
        self._spectral_cube = None
        self._independent_var = None
        self._independent_var_name = "x"
        logger.info("Unlinked spectral data from map")

    def get_spectrum_at(self, row: int, col: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get spectrum at a specific spatial position.

        This is the core spatial-spectral reconstruction feature.

        Parameters:
            row: Row index (0-based)
            col: Column index (0-based)

        Returns:
            Tuple of (independent_var, values) arrays
        """
        if self._spectral_cube is None:
            raise ValueError("No spectral data linked. Use link_spectral_data() first.")

        n_pts, n_rows, n_cols = self._spectral_cube.shape

        if not (0 <= row < n_rows and 0 <= col < n_cols):
            raise IndexError(f"Position ({row}, {col}) out of bounds for "
                           f"grid ({n_rows}, {n_cols})")

        values = self._spectral_cube[:, row, col]
        return self._independent_var.copy(), values.copy()

    def get_spectra_in_region(self,
                              row_start: int, row_end: int,
                              col_start: int, col_end: int,
                              mode: str = 'average') -> Tuple[np.ndarray, np.ndarray]:
        """
        Get spectrum from a rectangular region.

        Parameters:
            row_start, row_end: Row range (exclusive end)
            col_start, col_end: Column range (exclusive end)
            mode: 'average' for mean spectrum, 'all' for array of all spectra

        Returns:
            If mode='average': Tuple of (independent_var, averaged_values)
            If mode='all': Tuple of (independent_var, 2D array of shape (n_pts, n_spectra))
        """
        if self._spectral_cube is None:
            raise ValueError("No spectral data linked. Use link_spectral_data() first.")

        # Extract region
        region = self._spectral_cube[:, row_start:row_end, col_start:col_end]

        if mode == 'average':
            # Average over spatial dimensions
            values = np.mean(region, axis=(1, 2))
            return self._independent_var.copy(), values
        elif mode == 'all':
            # Flatten spatial dimensions
            n_pts = region.shape[0]
            values = region.reshape(n_pts, -1)
            return self._independent_var.copy(), values
        else:
            raise ValueError(f"Unknown mode: {mode}. Use 'average' or 'all'.")

    def get_spectra_by_mask(self,
                            mask: np.ndarray,
                            mode: str = 'average') -> Tuple[np.ndarray, np.ndarray]:
        """
        Get spectra from masked region.

        Parameters:
            mask: Boolean 2D array (True = include pixel)
            mode: 'average' for mean spectrum, 'all' for array

        Returns:
            Tuple of (independent_var, values)
        """
        if self._spectral_cube is None:
            raise ValueError("No spectral data linked. Use link_spectral_data() first.")

        if mask.shape != (self._spectral_cube.shape[1], self._spectral_cube.shape[2]):
            raise ValueError(f"Mask shape {mask.shape} doesn't match cube shape "
                           f"{self._spectral_cube.shape[1:]}")

        n_pts = self._spectral_cube.shape[0]

        # Get all spectra where mask is True
        masked_spectra = self._spectral_cube[:, mask]  # Shape: (n_pts, n_selected)

        if mode == 'average':
            values = np.mean(masked_spectra, axis=1)
            return self._independent_var.copy(), values
        elif mode == 'all':
            return self._independent_var.copy(), masked_spectra
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def compute_integrated_map(self,
                               start_idx: Optional[int] = None,
                               end_idx: Optional[int] = None,
                               start_val: Optional[float] = None,
                               end_val: Optional[float] = None) -> MapChannel:
        """
        Compute integrated intensity map from spectral data.

        Parameters:
            start_idx, end_idx: Integration range by index
            start_val, end_val: Integration range by value (takes precedence)

        Returns:
            MapChannel with integrated values
        """
        if self._spectral_cube is None:
            raise ValueError("No spectral data linked")

        # Determine integration range
        if start_val is not None and end_val is not None:
            mask = (self._independent_var >= start_val) & (self._independent_var <= end_val)
            indices = np.where(mask)[0]
            if len(indices) == 0:
                raise ValueError(f"No data in range [{start_val}, {end_val}]")
            start_idx = indices[0]
            end_idx = indices[-1] + 1
        else:
            start_idx = start_idx or 0
            end_idx = end_idx or self._spectral_cube.shape[0]

        # Integrate (simple sum, could use trapz for more accuracy)
        integrated = np.sum(self._spectral_cube[start_idx:end_idx], axis=0)

        # Create channel metadata
        range_str = f"{self._independent_var[start_idx]:.2f}-{self._independent_var[end_idx-1]:.2f}"
        metadata = ChannelMetadata(
            name=f"Integrated_{range_str}",
            channel_type=ChannelType.OPTICAL,
            units="a.u.",
            description=f"Integrated {self._independent_var_name} [{range_str}]"
        )

        return MapChannel(integrated, metadata)

    def compute_value_at_map(self, index: int) -> MapChannel:
        """
        Get map of values at a specific spectral index.

        Parameters:
            index: Index in spectral dimension

        Returns:
            MapChannel with values at that spectral point
        """
        if self._spectral_cube is None:
            raise ValueError("No spectral data linked")

        if not (0 <= index < self._spectral_cube.shape[0]):
            raise IndexError(f"Index {index} out of range [0, {self._spectral_cube.shape[0]})")

        data = self._spectral_cube[index]
        val = self._independent_var[index]

        metadata = ChannelMetadata(
            name=f"Value_at_{val:.2f}",
            channel_type=ChannelType.OPTICAL,
            units="a.u.",
            description=f"Value at {self._independent_var_name}={val:.2f}"
        )

        return MapChannel(data, metadata)

    # =========================================================================
    # Standard container methods
    # =========================================================================

    def __len__(self) -> int:
        return len(self.channels)

    def __contains__(self, name: str) -> bool:
        return name in self.channels

    def __getitem__(self, name: str) -> MapChannel:
        return self.get_channel(name)

    def __iter__(self):
        return iter(self.channels.values())

    def __repr__(self) -> str:
        spectral_info = f", spectral_link={self.has_spectral_link}" if self.has_spectral_link else ""
        return (f"MultiChannelMap(channels={len(self.channels)}, "
                f"shape={self.shape}, names={self.channel_names}{spectral_info})")
