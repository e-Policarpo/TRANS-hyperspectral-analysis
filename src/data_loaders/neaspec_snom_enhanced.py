"""
Enhanced NeaSpec SNOM Data Loader
Improved loader with proper multi-channel data splitting as specified
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

logger = logging.getLogger(__name__)


class NeaSpecSNOMEnhancedLoader(BaseDataLoader):
    """
    Enhanced NeaSpec SNOM loader with proper multi-channel handling.

    Parses header for: # Pixel Area (X, Y, Z):    [px]    20    10    1024
    Where 20, 10 are grid dimensions (map_x, map_y) and 1024 is datapoints per spectrum.

    Creates separate SpectralData objects for each channel (O0A, O0P, O1A, O1P, etc.)
    with both Wavenumber and Omega as independent variables.
    """

    def __init__(self):
        super().__init__()
        self.supported_extensions = ['.txt', '.dat']
        self.loader_type = 'neaspec_snom'

    def parse_header(self, lines: List[str]) -> Dict:
        """
        Parse NeaSpec file header to extract metadata.

        Parameters:
        -----------
        lines : List[str]
            Header lines from file

        Returns:
        --------
        metadata : Dict
            Parsed metadata including pixel_area (grid dimensions and z-points)
        """
        metadata = {
            'project': '',
            'description': '',
            'date': '',
            'scan_area': None,
            'pixel_area': None,  # (X, Y, Z) where X,Y are grid, Z is datapoints
            'demodulation': 'Fourier',
            'parameters': {}
        }

        for line in lines:
            if line.startswith('#'):
                line = line.strip('# \n')

                if 'neaspec.com' in line:
                    continue

                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        values = parts[1].strip()

                        if 'Project' in key:
                            metadata['project'] = values
                        elif 'Description' in key:
                            metadata['description'] = values
                        elif 'Date' in key:
                            metadata['date'] = values
                        elif 'Scan Area' in key:
                            match = re.search(r'\[.*?\]\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)', values)
                            if match:
                                metadata['scan_area'] = (float(match.group(1)),
                                                        float(match.group(2)),
                                                        float(match.group(3)))
                        elif 'Pixel Area' in key:
                            # This is the key line: # Pixel Area (X, Y, Z):    [px]    20    10    1024
                            match = re.search(r'\[.*?\]\s*(\d+)\s+(\d+)\s+(\d+)', values)
                            if match:
                                pixel_x = int(match.group(1))
                                pixel_y = int(match.group(2))
                                pixel_z = int(match.group(3))
                                metadata['pixel_area'] = (pixel_x, pixel_y, pixel_z)
                                logger.info(f"Extracted pixel area: Grid={pixel_x}x{pixel_y}, Datapoints={pixel_z}")
                        elif 'Demodulation Mode' in key:
                            metadata['demodulation'] = values
                        else:
                            metadata['parameters'][key] = values

        return metadata

    def parse_data_columns(self, header_line: str) -> List[str]:
        """Parse column names from data header line."""
        columns = header_line.strip().split('\t')
        return [col.strip() for col in columns]

    def load_single_file(self, filepath: Path) -> Dict[str, SpectralData]:
        """
        Load SNOM data from a single text file.

        Returns a dictionary of SpectralData objects, one for each channel and independent variable.

        Parameters:
        -----------
        filepath : Path
            Path to text file

        Returns:
        --------
        spectral_data_dict : Dict[str, SpectralData]
            Dictionary mapping channel names to SpectralData objects
            Keys: 'Wavenumber_O0A', 'Wavenumber_O0P', 'Omega_O0A', 'Omega_O0P', etc.
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        logger.info(f"Loading NeaSpec SNOM file: {filepath}")

        # Read file
        with open(filepath, 'r') as f:
            lines = f.readlines()

        # Separate header and data
        header_lines = []
        data_start_idx = 0
        column_line_idx = None

        for i, line in enumerate(lines):
            if line.startswith('#'):
                header_lines.append(line)
            elif not line.strip():
                continue
            else:
                # Check if this is the column header line
                if 'Row' in line and 'Column' in line:
                    column_line_idx = i
                    data_start_idx = i + 1
                    break

        if column_line_idx is None:
            raise ValueError("Could not find column header line in file")

        # Parse header
        metadata_dict = self.parse_header(header_lines)

        # Parse columns
        columns = self.parse_data_columns(lines[column_line_idx])

        # Read data
        data_lines = []
        for line in lines[data_start_idx:]:
            if line.strip() and not line.startswith('#'):
                data_lines.append(line.strip().split('\t'))

        # Convert to numpy array
        data_array = np.array(data_lines, dtype=float)

        # Create DataFrame
        df = pd.DataFrame(data_array, columns=columns)

        # Get dimensions
        if metadata_dict['pixel_area']:
            x_pixels, y_pixels, z_pixels = metadata_dict['pixel_area']
            dimensions = (x_pixels, y_pixels)
            n_datapoints = z_pixels
        else:
            unique_rows = len(df['Row'].unique())
            unique_cols = len(df['Column'].unique())
            dimensions = (unique_cols, unique_rows)
            n_datapoints = len(df) // (unique_rows * unique_cols)

        logger.info(f"Grid dimensions: {dimensions}, Datapoints per spectrum: {n_datapoints}")

        # Identify harmonic columns (O0A, O0P, O1A, O1P, O2A, O2P, etc.)
        harmonic_columns = [col for col in columns if re.match(r'O\d+[AP]', col)]

        if not harmonic_columns:
            raise ValueError("No harmonic columns (O0A, O0P, etc.) found in data")

        logger.info(f"Found harmonic channels: {harmonic_columns}")

        # Split data into blocks per measurement point
        total_rows = len(df)
        n_positions = total_rows // n_datapoints

        if total_rows % n_datapoints != 0:
            logger.warning(f"Data rows ({total_rows}) not evenly divisible by datapoints ({n_datapoints})")

        logger.info(f"Splitting {total_rows} rows into {n_positions} measurement points of {n_datapoints} datapoints each")

        # Create SpectralData objects for each channel and independent variable combination
        results = {}

        # Process both Wavenumber and Omega as independent variables
        for indep_var_name in ['Wavenumber', 'Omega']:
            if indep_var_name not in df.columns:
                logger.warning(f"{indep_var_name} not found in data columns")
                continue

            for harmonic in harmonic_columns:
                # Collect spectra for this channel
                spectra_list = []
                column_names = []

                for pos_idx in range(n_positions):
                    start_row = pos_idx * n_datapoints
                    end_row = start_row + n_datapoints

                    # Extract block for this position
                    pos_data = df.iloc[start_row:end_row]

                    # Get independent variable and dependent variable
                    indep_values = pos_data[indep_var_name].values
                    dep_values = pos_data[harmonic].values

                    if len(dep_values) != n_datapoints:
                        logger.warning(f"Position {pos_idx} has {len(dep_values)} points, expected {n_datapoints}")
                        continue

                    spectra_list.append(dep_values)

                    # Use position index for column name
                    row_idx = pos_idx // dimensions[0]
                    col_idx = pos_idx % dimensions[0]
                    column_names.append(f"r{row_idx}_c{col_idx}")

                if not spectra_list:
                    logger.warning(f"No spectra collected for {indep_var_name}_{harmonic}")
                    continue

                # Get independent variable array (should be same for all positions)
                first_block = df.iloc[:n_datapoints]
                indep_array = first_block[indep_var_name].values

                # Create DataFrame
                spectral_df = self.concatenate_spectra(
                    spectra_list,
                    indep_array,
                    column_names=column_names
                )

                # Rename independent variable
                spectral_df = spectral_df.rename(columns={"Variable": indep_var_name})

                # Create metadata
                metadata = self.create_metadata(
                    dimensions=dimensions,
                    scan_mode="raster",
                    units={"independent": "cm^-1" if indep_var_name == "Wavenumber" else "Hz",
                           "dependent": "a.u.",
                           "x": "um", "y": "um"},
                    channel=harmonic,
                    independent_var=indep_var_name,
                    n_datapoints=n_datapoints,
                    source_file=str(filepath),
                    **metadata_dict
                )

                # Create SpectralData
                spectral_data = SpectralData(spectral_df, metadata)

                # Store in results
                key = f"{indep_var_name}_{harmonic}"
                results[key] = spectral_data

                logger.info(f"Created SpectralData for {key}: {spectral_data.num_spectra} spectra")

        self.last_loaded_path = filepath
        logger.info(f"Successfully loaded NeaSpec SNOM data: {len(results)} channel combinations")

        return results

    def load_from_directory(self, directory: Path,
                           progress_callback=None) -> Tuple[Dict[str, SpectralData], Optional[TopographyData]]:
        """
        Load SNOM data from directory.

        For NeaSpec SNOM, typically there's one file per measurement.

        Parameters:
        -----------
        directory : Path
            Directory containing data files
        progress_callback : callable, optional
            Callback function(current, total, message) for progress updates

        Returns:
        --------
        spectral_data_dict : Dict[str, SpectralData]
            Dictionary of loaded spectral data
        topography : None
            NeaSpec SNOM files don't typically include topography
        """
        directory = Path(directory)

        if not self.validate_directory(directory):
            raise ValueError(f"Invalid directory: {directory}")

        # Find suitable files
        data_files = self.find_files(directory)

        if not data_files:
            raise ValueError(f"No suitable files found in {directory}")

        # Filter for NeaSpec files
        neaspec_files = []
        for filepath in data_files:
            try:
                with open(filepath, 'r') as f:
                    first_line = f.readline()
                    if 'neaspec' in first_line.lower():
                        neaspec_files.append(filepath)
            except Exception:
                continue

        if not neaspec_files:
            logger.warning("No NeaSpec formatted files found, trying first file")
            neaspec_files = [data_files[0]]

        if progress_callback:
            progress_callback(0, 1, f"Loading {neaspec_files[0].name}")

        # Load first file
        spectral_data_dict = self.load_single_file(neaspec_files[0])

        if progress_callback:
            progress_callback(1, 1, "Complete!")

        # No topography data in NeaSpec files
        topography = None

        return spectral_data_dict, topography
