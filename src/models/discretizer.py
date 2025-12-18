"""
Discretizer for spatial averaging of spectral data
Implements two-stage discretization (horizontal then vertical)
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple
from src.models.spectral_data import SpectralData, SpectralMetadata

logger = logging.getLogger(__name__)


class Discretizer:
    """
    Handles spatial discretization of hyperspectral data.

    Performs block averaging in two stages:
    1. Horizontal: Average along x-axis in blocks
    2. Vertical: Average along y-axis in blocks
    """

    def discretize_spectral_data(
        self,
        spectral_data: SpectralData,
        block_h: int,
        block_v: int,
        ignore_empty_blocks: bool = True,
        data_type: str = 'spectral'
    ) -> Dict[str, SpectralData]:
        """
        Discretize spectral data by averaging in spatial blocks.

        Parameters:
        -----------
        spectral_data : SpectralData
            Input spectral data
        block_h : int
            Horizontal block size
        block_v : int
            Vertical block size
        ignore_empty_blocks : bool
            Skip blocks with all NaN values
        data_type : str
            Type of data (for metadata)

        Returns:
        --------
        results : dict
            Dictionary with 'intermediate' and 'final' SpectralData objects
        """
        try:
            dim_h, dim_v = spectral_data.metadata.dimensions
            num_points = spectral_data.num_points

            logger.info(f"Starting discretization: {dim_h}x{dim_v} grid, blocks {block_h}x{block_v}")

            # Calculate output dimensions
            n_blocks_h = dim_h // block_h
            n_blocks_v = dim_v // block_v

            logger.info(f"Output grid will be {n_blocks_h}x{n_blocks_v}")

            # Reshape data to grid
            spectra_2d = spectral_data.spectra.values.T.reshape(dim_v, dim_h, num_points)

            # Stage 1: Horizontal averaging
            intermediate = np.zeros((dim_v, n_blocks_h, num_points))

            for v in range(dim_v):
                for h_block in range(n_blocks_h):
                    h_start = h_block * block_h
                    h_end = h_start + block_h

                    block_data = spectra_2d[v, h_start:h_end, :]

                    if ignore_empty_blocks and np.all(np.isnan(block_data)):
                        intermediate[v, h_block, :] = np.nan
                    else:
                        intermediate[v, h_block, :] = np.nanmean(block_data, axis=0)

            # Stage 2: Vertical averaging
            final = np.zeros((n_blocks_v, n_blocks_h, num_points))

            for h_block in range(n_blocks_h):
                for v_block in range(n_blocks_v):
                    v_start = v_block * block_v
                    v_end = v_start + block_v

                    block_data = intermediate[v_start:v_end, h_block, :]

                    if ignore_empty_blocks and np.all(np.isnan(block_data)):
                        final[v_block, h_block, :] = np.nan
                    else:
                        final[v_block, h_block, :] = np.nanmean(block_data, axis=0)

            # Flatten back to (num_spectra, num_points)
            intermediate_flat = intermediate.reshape(-1, num_points).T
            final_flat = final.reshape(-1, num_points).T

            # Create DataFrames
            independent_var = spectral_data.independent_var

            intermediate_df = pd.DataFrame(
                intermediate_flat,
                columns=[f'spectrum_{i}' for i in range(intermediate_flat.shape[1])]
            )
            intermediate_df.insert(0, spectral_data.independent_var_name, independent_var)

            final_df = pd.DataFrame(
                final_flat,
                columns=[f'spectrum_{i}' for i in range(final_flat.shape[1])]
            )
            final_df.insert(0, spectral_data.independent_var_name, independent_var)

            # Create metadata
            intermediate_metadata = SpectralMetadata(
                source_type=spectral_data.metadata.source_type,
                dimensions=(n_blocks_h, dim_v),
                scan_mode=spectral_data.metadata.scan_mode,
                units=spectral_data.metadata.units,
                acquisition_date=spectral_data.metadata.acquisition_date,
                additional_info={'stage': 'horizontal_averaging'}
            )

            final_metadata = SpectralMetadata(
                source_type=spectral_data.metadata.source_type,
                dimensions=(n_blocks_h, n_blocks_v),
                scan_mode=spectral_data.metadata.scan_mode,
                units=spectral_data.metadata.units,
                acquisition_date=spectral_data.metadata.acquisition_date,
                additional_info={'stage': 'final_averaging'}
            )

            # Create SpectralData objects
            intermediate_data = SpectralData(
                data=intermediate_df,
                metadata=intermediate_metadata
            )

            final_data = SpectralData(
                data=final_df,
                metadata=final_metadata
            )

            logger.info(f"Discretization complete: {final_data.num_spectra} output spectra")

            return {
                'intermediate': intermediate_data,
                'final': final_data
            }

        except Exception as e:
            logger.error(f"Discretization error: {e}", exc_info=True)
            raise
