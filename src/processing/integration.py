"""
Integration Processing Module
Handles integration of spectral data over specified intervals
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
import logging
from typing import List, Tuple, Dict

from ..models.spectral_data import SpectralData
from .positivity import positive_integral

logger = logging.getLogger(__name__)


class IntegrationProcessor:
    """
    Processes spectral data integration over voltage intervals.
    """
    
    def __init__(self, positive_only: bool = True):
        self.intervals: List[Tuple[float, float]] = []
        #: Integrate only where the spectrum is above zero. dI/dV is a
        #: density of states and cannot be negative, so a dip below zero is
        #: noise and must not cancel the weight of a real state in the same
        #: interval. Clear it for a signed quantity such as I(V).
        self.positive_only = bool(positive_only)
    
    def set_intervals(self, intervals: List[Tuple[float, float]]):
        """Set integration intervals."""
        self.intervals = intervals
    
    def integrate_spectral_data(self, spectral_data: SpectralData) -> Dict[str, np.ndarray]:
        """
        Integrate spectral data over all configured intervals.

        Parameters:
        -----------
        spectral_data : SpectralData
            Spectral data to integrate

        Returns:
        --------
        results : Dict[str, np.ndarray]
            Integration results for each interval
        """
        voltage = spectral_data.independent_var
        spectra = spectral_data.spectra.values

        results = {}

        for start_v, end_v in self.intervals:
            # Create mask for interval
            mask = (voltage >= start_v) & (voltage <= end_v)

            if not np.any(mask):
                logger.warning(f"No data in interval [{start_v}, {end_v}]")
                continue

            # Extract data in interval
            interval_voltage = voltage[mask]
            interval_spectra = spectra[mask, :]

            # Perform integration
            integrated = self._integrate(interval_spectra, interval_voltage)

            # Store result
            interval_key = f"{start_v:.3f}_{end_v:.3f}"
            results[interval_key] = integrated

        logger.info(f"Integrated over {len(results)} intervals")
        return results

    def _integrate(self, block: np.ndarray, axis_values: np.ndarray) -> np.ndarray:
        """Trapezoidal integral along the spectral axis, honouring the switch."""
        if self.positive_only:
            return positive_integral(block, axis_values, axis=0)
        _trapz = getattr(np, 'trapezoid', None) or np.trapz
        return _trapz(block, x=axis_values, axis=0)

    def integrate_single_interval(self, spectral_data: SpectralData, v_min: float, v_max: float,
                                   grid_shape: Tuple[int, int]) -> np.ndarray:
        """
        Integrate spectral data over a single interval and reshape to grid.

        Parameters:
        -----------
        spectral_data : SpectralData
            Spectral data to integrate
        v_min : float
            Minimum voltage for integration
        v_max : float
            Maximum voltage for integration
        grid_shape : Tuple[int, int]
            Grid dimensions (vertical, horizontal) for reshaping

        Returns:
        --------
        map_data : np.ndarray
            2D array of integrated values
        """
        voltage = spectral_data.independent_var

        # Get all spectra columns (skip first column which is voltage)
        data_array = spectral_data.data.iloc[:, 1:].values

        # Create mask for interval
        mask = (voltage >= v_min) & (voltage <= v_max)

        if not np.any(mask):
            logger.warning(f"No data in interval [{v_min}, {v_max}]")
            return np.zeros(grid_shape)

        # Extract data in interval
        interval_voltage = voltage[mask]
        interval_data = data_array[mask, :]

        # Perform integration for each spectrum (column)
        integrated = self._integrate(interval_data, interval_voltage)

        # Reshape to grid
        n_v, n_h = grid_shape
        expected_size = n_v * n_h

        if len(integrated) != expected_size:
            logger.warning(f"Data size {len(integrated)} doesn't match grid size {expected_size}")
            # Pad or trim as needed
            if len(integrated) < expected_size:
                integrated = np.pad(integrated, (0, expected_size - len(integrated)), mode='constant')
            else:
                integrated = integrated[:expected_size]

        # Reshape: data is in column-major order (H->V)
        # So we need to reshape and potentially transpose
        map_data = integrated.reshape(n_h, n_v).T

        logger.info(f"Integrated over [{v_min}, {v_max}] V, created {map_data.shape} map")
        return map_data