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
from typing import Optional, Tuple, List, Dict
import logging
import re

from .base_loader import BaseDataLoader
from ..models.spectral_data import SpectralData, SpectralMetadata
from ..models.topography_data import TopographyData

try:
    from NSFopen.read import read as nid_read
    NSFOPEN_AVAILABLE = True
except ImportError:
    NSFOPEN_AVAILABLE = False
    logging.warning("NSFopen library not available. Install it to use Nanosurf loader.")

logger = logging.getLogger(__name__)


class NanosurfSTSEnhancedLoader(BaseDataLoader):
    """
    Enhanced Nanosurf STS loader with improved metadata parsing.

    Extracts dimensions from [DataSet\\SpecInfos\\SpecMapTable] section:
    Map0=-5.05339e-007;-1.46048e-008;-5.57349e-007;-6.85389e-008;100;100;0;1

    Where positions 5 and 6 (100;100 in this example) are map_i and map_j dimensions.
    """

    def __init__(self, patch_nsfopen: bool = True):
        super().__init__()
        self.supported_extensions = ['.nid']
        self.loader_type = 'nanosurf_sts'
        self.patch_nsfopen = patch_nsfopen

        if not NSFOPEN_AVAILABLE:
            raise ImportError("NSFopen library is required for Nanosurf loader")

        if self.patch_nsfopen:
            self._apply_nsfopen_patches()

    def _apply_nsfopen_patches(self):
        """Apply runtime patches to NSFopen for STM compatibility"""
        try:
            import NSFopen.read
            original_read = NSFopen.read.read.__init__

            def patched_init(self, *args, **kwargs):
                try:
                    original_read(self, *args, **kwargs)
                except KeyError as e:
                    if 'cantilever' in str(e).lower():
                        logger.debug("Ignoring cantilever-related error (STM mode)")
                    else:
                        raise

            NSFopen.read.read.__init__ = patched_init
            logger.debug("Applied NSFopen patches for STM compatibility")
        except Exception as e:
            logger.warning(f"Could not apply NSFopen patches: {e}")

    def parse_nid_metadata(self, nid_obj) -> Dict:
        """
        Parse metadata from NID object, extracting grid dimensions.

        Parameters:
        -----------
        nid_obj : NSFopen object
            Loaded NID file object

        Returns:
        --------
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
                        content = f.read()

                        # Look for Map0 line
                        map0_match = re.search(r'Map0=([\d.e+-]+;)+[\d.e+-]+', content)
                        if map0_match:
                            map0_str = map0_match.group(0).split('=')[1]
                            dimensions = self._parse_map0_line(map0_str)
                            if dimensions:
                                metadata['dimensions'] = dimensions
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

        Format: Map0=-5.05339e-007;-1.46048e-008;-5.57349e-007;-6.85389e-008;100;100;0;1
        Positions: 0;1;2;3;4;5;6;7
        We want positions 4 and 5 (map_i, map_j)

        Parameters:
        -----------
        map0_str : str
            Map0 value string

        Returns:
        --------
        dimensions : Tuple[int, int] or None
            (map_i, map_j) dimensions
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

    def load_from_directory(self, directory: Path,
                           progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
        """
        Load STS data from directory of .nid files with zigzag correction.

        Parameters:
        -----------
        directory : Path
            Directory containing .nid files
        progress_callback : callable, optional
            Callback function(current, total, message) for progress updates

        Returns:
        --------
        spectral_data : SpectralData
            Concatenated spectral data with zigzag correction
        topography : TopographyData or None
            Average topography from first file
        """
        directory = Path(directory)

        if not self.validate_directory(directory):
            raise ValueError(f"Invalid directory: {directory}")

        # Find all .nid files (sorted alphabetically as specified)
        nid_files = sorted(self.find_files(directory), key=lambda x: x.name)

        if not nid_files:
            raise ValueError(f"No .nid files found in {directory}")

        logger.info(f"Loading {len(nid_files)} .nid files from {directory}")

        # Storage for concatenated data
        all_spectra_forward = []
        all_spectra_backward = []
        all_spectra_mixed = []
        V_common = None
        topography = None
        dimensions = None

        # Process each file in alphabetical order
        for i, filepath in enumerate(nid_files):
            try:
                if progress_callback:
                    progress_callback(i, len(nid_files), f"Loading {filepath.name}")

                logger.debug(f"Processing file {i+1}/{len(nid_files)}: {filepath.name}")

                # Read .nid file
                stm_nid = nid_read(str(filepath))

                # Parse metadata to get dimensions
                if dimensions is None:
                    metadata_dict = self.parse_nid_metadata(stm_nid)
                    if metadata_dict['dimensions']:
                        dimensions = metadata_dict['dimensions']
                        logger.info(f"Grid dimensions: {dimensions}")

                # Extract spectroscopy data
                if hasattr(stm_nid.data, 'Spec'):
                    # Forward and backward I-V curves
                    I_forward = np.array(stm_nid.data.Spec.Forward.get("Tip Current",
                                                                      stm_nid.data.Spec.Forward.get("Current")))
                    I_backward = np.array(stm_nid.data.Spec.Backward.get("Tip Current",
                                                                        stm_nid.data.Spec.Backward.get("Current")))

                    # Average over repetitions
                    I_mean_forward = np.mean(I_forward, axis=0)
                    I_mean_backward = np.mean(I_backward, axis=0)
                    I_mean_mixed = (I_mean_forward + I_mean_backward) / 2

                    # Store all three versions
                    all_spectra_forward.append(I_mean_forward)
                    all_spectra_backward.append(I_mean_backward)
                    all_spectra_mixed.append(I_mean_mixed)

                    # Get voltage array
                    try:
                        V = np.array(stm_nid.data.Spec.Forward.get("Tip voltage",
                                                                  stm_nid.data.Spec.Forward.get("Voltage")))[0, :]
                    except (IndexError, TypeError, AttributeError):
                        V = self._generate_voltage_array_from_metadata(stm_nid)

                    if V_common is None:
                        V_common = V
                        logger.info(f"Voltage range: [{V_common.min():.3f}, {V_common.max():.3f}] V ({len(V_common)} points)")

                # Extract topography from first file
                if topography is None and hasattr(stm_nid.data, 'Image'):
                    try:
                        z_forward = np.array(stm_nid.data.Image.Forward.get("Z-Axis",
                                                                           stm_nid.data.Image.Forward.get("Height")))
                        z_backward = np.array(stm_nid.data.Image.Backward.get("Z-Axis",
                                                                             stm_nid.data.Image.Backward.get("Height")))

                        topography = TopographyData.from_forward_backward(
                            z_forward, z_backward, flip_vertical=True
                        )
                        logger.info(f"Extracted topography with dimensions {topography.data.shape}")
                    except Exception as e:
                        logger.warning(f"Could not extract topography: {e}")

            except Exception as e:
                logger.error(f"Error processing {filepath.name}: {e}")
                continue

        if not all_spectra_mixed:
            raise ValueError("No spectral data could be extracted")

        # Infer dimensions if not from metadata
        if dimensions is None:
            n_spectra = len(all_spectra_mixed)
            if topography is not None:
                dimensions = (topography.width, topography.height)
            else:
                # Guess square grid
                dim_guess = int(np.sqrt(n_spectra))
                if dim_guess * dim_guess == n_spectra:
                    dimensions = (dim_guess, dim_guess)
                else:
                    dimensions = (n_spectra, 1)
            logger.info(f"Inferred dimensions: {dimensions}")

        # Create DataFrames for all three channel types
        results = {}

        for channel_name, spectra_list in [
            ('Forward', all_spectra_forward),
            ('Backward', all_spectra_backward),
            ('Mixed', all_spectra_mixed)
        ]:
            df = self.concatenate_spectra(
                spectra_list,
                V_common,
                column_names=[f"Point_{i+1}" for i in range(len(spectra_list))]
            )
            df = df.rename(columns={"Variable": "V"})

            # Create metadata
            metadata = self.create_metadata(
                dimensions=dimensions,
                scan_mode="meander",
                units={"independent": "V", "dependent": "A", "x": "nm", "y": "nm"},
                n_files=len(nid_files),
                source_directory=str(directory),
                channel=channel_name
            )

            # Create SpectralData object
            spectral_data = SpectralData(df, metadata, topography.data if topography else None)

            # Apply zigzag (meander) correction
            spectral_data.correct_meander()

            results[channel_name] = spectral_data

        if progress_callback:
            progress_callback(len(nid_files), len(nid_files), "Complete!")

        self.last_loaded_path = directory
        logger.info(f"Successfully loaded STS data: {len(results)} channels")

        # Return the mixed channel as primary, but store others in metadata
        primary_data = results['Mixed']
        primary_data.metadata.additional_info['channels'] = results

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
