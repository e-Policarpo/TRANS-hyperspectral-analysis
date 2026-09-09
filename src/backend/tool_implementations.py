"""
Additional Tool Implementations
Extension of AppBackend with remaining analysis tools
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import math

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from scipy import signal, interpolate, optimize
from PIL import Image
import logging
import warnings

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.processing.spectral_features import (
    FeatureConfig,
    feature_columns,
    feature_table,
)
from src.processing.positivity import positive_integral, positive_mask
from src.utils.naming import pad as _pad
from src.processing.edge_analysis import (
    edge_summary,
    edge_columns,
    resolution_fwhm,
)
from src.processing.spatial_coherence import coherence_summary
from src.physics.level_patterns import all_patterns
from src.physics.level_ratio_fit import (
    CONCLUSIVE,
    AMBIGUOUS,
    REJECTED,
    UNDERDETERMINED,
    rank_patterns,
)
from src.processing.peak_detection import (
    Analysis,
    analyze,
    noise_sigma,
    BASELINE_KINDS,
    POLYNOMIAL_BASES,
    als_baseline,
    analyze_many,
    assign_bins,
    binned_peak_matrix,
    coefficient_names,
    endpoint_baseline,
    energy_bins,
    estimate_baseline,
    eval_polynomial,
    fit_polynomial,
    CONFINEMENT_DEFAULTS,
    normalized_axis,
    group_peaks_by_bin,
    occupancy_matrix,
    params_from_dict,
    peak_matrix,
    rubberband_baseline,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Confinement Analysis helpers
# =============================================================================

#: Product defaults for Confinement Analysis. They live with the engine
#: they were measured against (:mod:`src.processing.peak_detection`), so
#: the physics package can read them without importing the Qt backend;
#: re-exported here because this is where callers have always found them.


#: Map Generator defaults, on top of CONFINEMENT_DEFAULTS. Measured on
#: synthetic dI/dV line scans with planted states (3 states, known spatial
#: profiles) and checked against real 4.5 K data.
#:
#: ``height`` 3σ rather than the 2σ used for peak analysis: both find states
#: down to an amplitude of 2σ, but 3σ carries 40% more of the map's weight in
#: the real states and reports 2.6x fewer bins (20 vs 53 on isolated states);
#: 5σ starts missing the weakest ones. On dense real data the three are within
#: a few percent, so the stricter one costs nothing there.
#:
#: ``noise_floor`` 1σ: it zeroes the 39% of cells that were pure noise while
#: keeping 99.4% of the signal weight. Higher floors buy little and start
#: eating real weight (96.3% at 3σ).
#:
#: ``min_spectra_per_bin`` stays 1: a state living at a single position along
#: the line is exactly what these maps are for, and 2 would hide it.
MAP_DEFAULTS = {
    'height': 3.0,
    'noise_floor': 1.0,
    'min_spectra_per_bin': 1,
}


#: FeatureConfig fields that must survive QML/JSON as ints.
_INT_FEATURE_FIELDS = ('poly_degree', 'doping_smooth_points', 'state_width_samples')


def _feature_config(raw: Optional[dict]) -> FeatureConfig:
    """Build a FeatureConfig from a loose dict of QML/workflow values.

    Same contract as :func:`params_from_dict`: unknown keys are dropped and
    the integer fields are cast back, because QML sends every number as a
    float.
    """
    config = FeatureConfig()
    if not raw:
        return config
    for key, value in raw.items():
        if not hasattr(config, key) or value is None or key == 'confinement':
            continue
        if key in _INT_FEATURE_FIELDS:
            value = int(value)
        elif isinstance(getattr(config, key), float):
            value = float(value)
        setattr(config, key, value)
    return config


def _expand(values: np.ndarray, idx: np.ndarray, n_samples: int) -> np.ndarray:
    """Scatter in-window values back onto the full axis, NaN outside it."""
    full = np.full(n_samples, np.nan)
    if len(idx):
        full[idx] = values
    return full


def _write_occupancy_csv(frame: pd.DataFrame, columns, path) -> None:
    """Write an occupancy table as bare integers with empty cells.

    A float column would render as "1.0", and a global ``float_format`` would
    round the energy axis, so only the mark columns are stringified -- the
    in-memory dataset stays numeric (value / NaN). The blanks have to reach
    the file as empty cells rather than zeros: zero is a measured value, and a
    reader that sees a field of them cannot tell "no state here" from "a state
    of size zero".
    """
    export_df = frame.copy()
    for column in columns:
        values = frame[column].to_numpy()
        as_int = np.nan_to_num(values, nan=0.0).astype(np.int64).astype(str)
        export_df[column] = np.where(np.isfinite(values), as_int, '')
    export_df.to_csv(path, index=False)


def _peak_fwhm(result: Analysis, full_indices) -> np.ndarray:
    """Peak widths at half prominence, in samples, on the corrected curve."""
    if not len(full_indices):
        return np.empty(0)
    # result.idx maps window position -> full position; invert for peak_widths.
    lookup = {int(f): int(w) for w, f in enumerate(result.idx)}
    window_positions = [lookup[int(i)] for i in full_indices if int(i) in lookup]
    if not window_positions:
        return np.zeros(len(full_indices))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            widths = signal.peak_widths(result.y_corrected,
                                        np.asarray(window_positions, dtype=np.intp),
                                        rel_height=0.5)[0]
        return np.asarray(widths, dtype=np.float64)
    except Exception:
        logger.debug("peak_widths failed; reporting zero FWHM", exc_info=True)
        return np.zeros(len(window_positions))


def _baseline_coefficients(x: np.ndarray, baseline: np.ndarray, degree: int,
                           basis: str = "power") -> np.ndarray:
    """Ascending-order coefficients of a fitted background curve.

    Refits the background that was actually subtracted rather than
    re-deriving it, so the numbers describe exactly what came off the
    spectrum. Index 0 is the constant term, matching the Curve Fitting tool's
    convention.

    The fit runs on the normalised axis, so an orthogonal basis is orthogonal
    over the spectrum's own range and the coefficients are comparable between
    spectra -- which is what makes them usable as classification features.

    A background that could not be fitted (too few points for the degree, a
    singular fit) reports zeros rather than raising: one unusable spectrum
    must not lose the whole run's coefficient table.
    """
    x = np.asarray(x, dtype=np.float64)
    baseline = np.asarray(baseline, dtype=np.float64)
    if baseline.size != x.size or x.size <= degree + 1:
        return np.zeros(degree + 1)
    try:
        with np.errstate(all="ignore"):
            return fit_polynomial(normalized_axis(x), baseline, degree, basis)
    except Exception:
        logger.debug("Background coefficient refit failed", exc_info=True)
        return np.zeros(degree + 1)


def _fit_coefficients(result: Analysis, degree: int, basis: str = "power") -> np.ndarray:
    """Background coefficients of one :class:`Analysis`, on its own axis."""
    return _baseline_coefficients(result.x, result.baseline, degree, basis)


class ToolImplementations:
    """Mixin class with all tool implementations."""

    def _extract_clean_base_name(self, dataset_name: str) -> str:
        """
        Extract a clean, user-friendly base name from a dataset name.

        Handles workflow temp names like:
        - '_wf_STS_hyperspec_MnBi2Te4_1_Mixed_4f0e73'
        - '_wf_STS_hyperspec_MnBi2Te4_1_Mixed_integrate_2e2476'

        Returns just 'STS hyperspec MnBi2Te4 1 Mixed'.
        """
        import re

        name = dataset_name

        # Remove workflow prefix with optional operation suffix and UUID:
        # Pattern: _wf_<basename>_<optional_operation>_<6char_hex>
        # The operation can be: integrate, derivative, smooth, truncate, etc.
        wf_match = re.match(r'^_wf_(.+?)(?:_(?:integrate|derivative|smooth|truncate|baseline|discretize))?_[a-f0-9]{6}$', name)
        if wf_match:
            name = wf_match.group(1)
        else:
            # Try simpler pattern without operation
            wf_match = re.match(r'^_wf_(.+?)_[a-f0-9]{6}$', name)
            if wf_match:
                name = wf_match.group(1)

        # Remove operation prefixes that might have been added
        operation_prefixes = [
            'NoBaseline_', 'Smoothed_', 'Integrated_', 'Truncated_',
            'dIdV_', 'd2IdV2_', 'Discretized_', 'Averaged_', 'FFT_'
        ]
        for prefix in operation_prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]

        # Remove operation suffixes that might still be there
        operation_suffixes = [
            '_integrate', '_derivative', '_smooth', '_truncate',
            '_baseline', '_discretize', '_average'
        ]
        for suffix in operation_suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]

        # Remove any remaining _wf_ prefixes (nested cases)
        while '_wf_' in name:
            wf_match = re.search(r'_wf_(.+?)(?:_(?:integrate|derivative|smooth|truncate|baseline|discretize))?_[a-f0-9]{6}', name)
            if wf_match:
                name = wf_match.group(1)
            else:
                name = name.replace('_wf_', '')
                break

        # Replace underscores with spaces for display
        name = name.replace('_', ' ')

        # Remove extra spaces
        name = ' '.join(name.split())

        # If we end up with nothing meaningful, use a default
        if not name or name.lower() in ['temp', 'data']:
            name = 'Data'

        return name

    # ========================================================================
    # Curve Smoothing
    # ========================================================================

    def smooth_curves(self, task, dataset_name: str, window_size: int, poly_order: int,
                     smoothing_type: str = 'savgol') -> str:
        """
        Smooth spectral curves using various algorithms.

        Parameters:
        -----------
        dataset_name : str
            Dataset to smooth
        window_size : int
            Window size for smoothing (must be odd)
        poly_order : int
            Polynomial order for Savitzky-Golay
        smoothing_type : str
            'savgol', 'moving_average', or 'gaussian'

        Returns:
        --------
        output_path : str
            Path to smoothed data
        """
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            logger.info(f"Smoothing {dataset_name} with {smoothing_type}, window={window_size}")

            # Workflow/QML node params may arrive as floats (e.g. 11.0, 4.0);
            # scipy.savgol_filter requires plain ints.
            window_size = int(window_size)
            poly_order = int(poly_order)

            # Ensure window size is odd
            if window_size % 2 == 0:
                window_size += 1

            # Get data
            independent_var = spectral_data.independent_var
            spectra = spectral_data.spectra.values

            # Apply smoothing
            if smoothing_type == 'savgol':
                smoothed = signal.savgol_filter(spectra, window_size, poly_order, axis=0)
            elif smoothing_type == 'moving_average':
                smoothed = np.apply_along_axis(
                    lambda x: np.convolve(x, np.ones(window_size)/window_size, mode='same'),
                    0, spectra
                )
            elif smoothing_type == 'gaussian':
                from scipy.ndimage import gaussian_filter1d
                sigma = window_size / 6.0
                smoothed = gaussian_filter1d(spectra, sigma=sigma, axis=0)
            else:
                raise ValueError(f"Unknown smoothing type: {smoothing_type}")

            # Create DataFrame
            smoothed_df = pd.DataFrame(smoothed, columns=spectral_data.spectra.columns)
            smoothed_df.insert(0, spectral_data.independent_var_name, independent_var)

            # Create user-friendly names using naming convention
            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(dataset_name, operation="Smoothed")

            # Save with convention-based filename
            output_path = self._ensure_output_dir('smoothed') / f"{convention_name}.csv"
            smoothed_df.to_csv(output_path, index=False)

            # Create new dataset with clean base name (convention only for file path)
            friendly_name = f"{base_name} - Smoothed"
            metadata = SpectralMetadata(
                source_type=spectral_data.metadata.source_type,
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units=spectral_data.metadata.units.copy(),
                additional_info={
                    **self._carry_spatial_info(spectral_data.metadata),
                    'smoothing': smoothing_type,
                    'window_size': window_size,
                    'original': dataset_name
                }
            )
            smoothed_spectral_data = SpectralData(smoothed_df, metadata)
            # Store only with friendly name (no duplicates)
            self._datasets[friendly_name] = smoothed_spectral_data
            # Only emit to browser when not in workflow mode (intermediate results shouldn't appear)
            if not self._workflow_mode:
                self.dataLoaded.emit(friendly_name)

            # Status update will be handled by callback in main thread
            logger.info(f"Smoothed data saved to {output_path}")

            return str(output_path)

        except Exception as e:
            logger.error(f"Smoothing error: {e}", exc_info=True)
            self.errorOccurred.emit("Smoothing Error", str(e))
            return ""

    # ========================================================================
    # Average Curves
    # ========================================================================

    def average_curves(self, task, dataset_name: str) -> str:
        """Compute the arithmetic mean of all spectra in a dataset.

        Produces a single averaged spectrum as a new one-column dataset
        suffixed ``- Average``. NaNs are ignored column-wise (``nanmean``)
        so partial spectra still contribute. Stamps ``original`` in the
        metadata so the result overlays onto the source's graph window.
        """
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            spectra = spectral_data.spectra.values
            logger.info(f"Averaging {dataset_name}: shape={spectra.shape}")

            mean_curve = np.nanmean(spectra, axis=1)

            averaged_df = pd.DataFrame({'Average': mean_curve})
            averaged_df.insert(0, spectral_data.independent_var_name,
                               np.asarray(spectral_data.independent_var))

            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(dataset_name, operation="Average")
            output_path = self._ensure_output_dir('averaged') / f"{convention_name}.csv"
            averaged_df.to_csv(output_path, index=False)

            friendly_name = f"{base_name} - Average"
            metadata = SpectralMetadata(
                source_type=spectral_data.metadata.source_type,
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units=spectral_data.metadata.units.copy(),
                additional_info={
                    'operation': 'average',
                    'n_averaged': int(spectra.shape[1]),
                    'original': dataset_name,
                }
            )
            averaged_spectral_data = SpectralData(averaged_df, metadata)
            self._datasets[friendly_name] = averaged_spectral_data
            if not self._workflow_mode:
                self.dataLoaded.emit(friendly_name)

            logger.info(f"Averaged data saved to {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Averaging error: {e}", exc_info=True)
            self.errorOccurred.emit("Average Curves Error", str(e))
            return ""

    # ========================================================================
    # Cosmic Ray / Hot Pixel Filter (CCD spikes)
    # ========================================================================

    def remove_cosmic_rays(self, task, dataset_name: str,
                           threshold_sigmas: float = 5.0,
                           window: int = 5,
                           max_width: int = 2) -> str:
        """Remove narrow CCD spikes (cosmic rays / hot pixels) from spectra.

        See :func:`src.processing.cosmic_ray.remove_cosmic_rays` for the
        detection model. Produces a new dataset suffixed ``- CR Cleaned``
        and a small report logging how many samples were replaced per
        spectrum.
        """
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            from src.processing.cosmic_ray import remove_cosmic_rays_2d

            spectral_data = self._datasets[dataset_name]
            spectra = spectral_data.spectra.values
            logger.info(
                f"Cosmic-ray filter on {dataset_name}: "
                f"shape={spectra.shape}, threshold={threshold_sigmas}σ, "
                f"window={window}, max_width={max_width}"
            )

            cleaned, mask = remove_cosmic_rays_2d(
                spectra,
                threshold_sigmas=threshold_sigmas,
                window=window,
                max_width=max_width,
            )

            total_replaced = int(mask.sum())
            spectra_hit = int((mask.any(axis=0)).sum())
            logger.info(
                f"Cosmic-ray filter: replaced {total_replaced} samples "
                f"across {spectra_hit}/{spectra.shape[1]} spectra"
            )

            cleaned_df = pd.DataFrame(cleaned, columns=spectral_data.spectra.columns)
            cleaned_df.insert(
                0, spectral_data.independent_var_name, spectral_data.independent_var,
            )

            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(
                dataset_name, operation="CRCleaned",
            )
            output_path = self._ensure_output_dir('cosmic_ray') / f"{convention_name}.csv"
            cleaned_df.to_csv(output_path, index=False)

            friendly_name = f"{base_name} - CR Cleaned"
            metadata = SpectralMetadata(
                source_type=spectral_data.metadata.source_type,
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units=spectral_data.metadata.units.copy(),
                additional_info={
                    **dict(spectral_data.metadata.additional_info or {}),
                    'cosmic_ray_filter': {
                        'threshold_sigmas': threshold_sigmas,
                        'window': window,
                        'max_width': max_width,
                        'samples_replaced': total_replaced,
                        'spectra_hit': spectra_hit,
                    },
                    'original': dataset_name,
                },
            )
            cleaned_spectral_data = SpectralData(cleaned_df, metadata)
            self._datasets[friendly_name] = cleaned_spectral_data
            if not self._workflow_mode:
                self.dataLoaded.emit(friendly_name)

            return str(output_path)

        except Exception as e:
            logger.error(f"Cosmic-ray filter error: {e}", exc_info=True)
            self.errorOccurred.emit("Cosmic-Ray Filter Error", str(e))
            return ""

    # ========================================================================
    # Background Subtraction (luminescence / Raman)
    # ========================================================================

    def subtract_background_datasets(self, task, signal_names: list,
                                      background_name: str) -> str:
        """Subtract one background dataset from N signal datasets.

        Creates one ``- BgSub`` dataset per input. When a signal's axis
        does not fully overlap the background's, the corrected output is
        truncated to the overlap interval (the helper handles this and
        records it in the new dataset's metadata).
        """
        try:
            from src.processing.background_subtraction import subtract_background

            if background_name not in self._datasets:
                self.errorOccurred.emit(
                    "Background Subtraction Error",
                    f"Background dataset {background_name!r} not found",
                )
                return ""
            background = self._datasets[background_name]

            missing = [n for n in signal_names if n not in self._datasets]
            if missing:
                self.errorOccurred.emit(
                    "Background Subtraction Error",
                    f"Datasets not found: {', '.join(missing)}",
                )
                return ""

            last_output_path = ""
            truncated_any = False
            for signal_name in signal_names:
                if task.cancelled:
                    return last_output_path
                signal = self._datasets[signal_name]
                try:
                    result = subtract_background(signal, background)
                except Exception as e:
                    logger.warning(
                        "Background subtraction skipped %s: %s",
                        signal_name, e,
                    )
                    self.errorOccurred.emit(
                        "Background Subtraction",
                        f"{signal_name}: {e}",
                    )
                    continue

                truncated_any = truncated_any or result.truncated

                base_name = self._extract_clean_base_name(signal_name)
                friendly_name = f"{base_name} - BgSub"
                convention_name = self._apply_naming_convention(
                    signal_name, operation="BgSubtracted",
                )
                output_path = (
                    self._ensure_output_dir('background_subtracted')
                    / f"{convention_name}.csv"
                )
                corrected_df = result.corrected.spectra.copy()
                corrected_df.insert(
                    0, result.corrected.independent_var_name,
                    result.corrected.independent_var,
                )
                corrected_df.to_csv(output_path, index=False)

                self._datasets[friendly_name] = result.corrected
                if not self._workflow_mode:
                    self.dataLoaded.emit(friendly_name)
                last_output_path = str(output_path)
                logger.info(
                    "Background subtracted from %s → %s%s",
                    signal_name, friendly_name,
                    " (truncated)" if result.truncated else "",
                )

            if truncated_any:
                self.status = (
                    "Background subtraction complete. Some outputs were "
                    "truncated to the overlap with the background."
                )

            return last_output_path

        except Exception as e:
            logger.error(f"Background subtraction error: {e}", exc_info=True)
            self.errorOccurred.emit("Background Subtraction Error", str(e))
            return ""

    # ========================================================================
    # Image Smoothing
    # ========================================================================

    def smooth_image(self, task, image_path: str, filter_type: str, kernel_size: int) -> str:
        """
        Smooth image using various filters.

        Parameters:
        -----------
        image_path : str
            Path to image
        filter_type : str
            'gaussian', 'median', or 'bilateral'
        kernel_size : int
            Size of filter kernel

        Returns:
        --------
        output_path : str
            Path to smoothed image
        """
        try:
            from scipy.ndimage import gaussian_filter, median_filter

            logger.info(f"Smoothing image {image_path} with {filter_type}")

            # Load image
            img = Image.open(image_path).convert('L')
            img_array = np.array(img, dtype=float)

            # Apply filter
            if filter_type == 'gaussian':
                sigma = kernel_size / 6.0
                smoothed = gaussian_filter(img_array, sigma=sigma)
            elif filter_type == 'median':
                smoothed = median_filter(img_array, size=kernel_size)
            elif filter_type == 'bilateral':
                # Simplified bilateral filter
                from scipy.ndimage import gaussian_filter
                smoothed = gaussian_filter(img_array, sigma=kernel_size/4.0)
            else:
                raise ValueError(f"Unknown filter type: {filter_type}")

            # Convert back to uint8
            smoothed = np.clip(smoothed, 0, 255).astype(np.uint8)

            # Save
            output_path = self._ensure_output_dir('smoothed') / f"Smoothed_{filter_type}_{Path(image_path).stem}.png"
            result_img = Image.fromarray(smoothed)
            result_img.save(output_path)

            # Status update will be handled by callback in main thread
            logger.info(f"Smoothed image saved to {output_path}")

            return str(output_path)

        except Exception as e:
            logger.error(f"Image smoothing error: {e}", exc_info=True)
            self.errorOccurred.emit("Image Smoothing Error", str(e))
            return ""

    # ========================================================================
    # Derivative Calculator
    # ========================================================================

    def calculate_derivative(self, dataset_name: str, order: int = 1,
                           smooth_before: bool = True, smooth_after: bool = True) -> str:
        """
        Calculate numerical derivatives of spectral data.

        Parameters:
        -----------
        dataset_name : str
            Dataset to differentiate
        order : int
            Derivative order (1 or 2)
        smooth_before : bool
            Smooth before differentiation
        smooth_after : bool
            Smooth after differentiation

        Returns:
        --------
        output_path : str
            Path to derivative data
        """
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            logger.info(f"Calculating {order}-order derivative of {dataset_name}")
            logger.info(f"Dataset shape: {spectral_data.data.shape}, columns: {list(spectral_data.data.columns[:5])}...")

            independent_var = spectral_data.independent_var
            spectra = spectral_data.spectra.values.copy()
            n_points = spectra.shape[0]
            n_spectra = spectra.shape[1] if len(spectra.shape) > 1 else 1

            logger.info(f"Independent var length: {len(independent_var)}, spectra shape: {spectra.shape}")

            # Validate data has enough points
            if n_points < 2:
                error_msg = f"Dataset has insufficient points ({n_points}) for derivative calculation. Need at least 2 points."
                logger.error(error_msg)
                self.errorOccurred.emit("Derivative Error", error_msg)
                return ""

            if len(independent_var) == 0:
                error_msg = "Dataset has empty independent variable (x-axis). Cannot calculate derivative."
                logger.error(error_msg)
                self.errorOccurred.emit("Derivative Error", error_msg)
                return ""

            # Determine adaptive window length for Savitzky-Golay filter
            # Window must be odd and <= number of points, and > polyorder (3)
            default_window = 11
            if n_points < default_window:
                # Use largest odd number <= n_points that's > 3
                window_length = max(5, n_points if n_points % 2 == 1 else n_points - 1)
                if window_length <= 3:
                    # Data too small for smoothing, skip it
                    logger.warning(f"Data has only {n_points} points, skipping Savitzky-Golay smoothing")
                    smooth_before = False
                    smooth_after = False
            else:
                window_length = default_window

            # Bias step, for turning the window from samples into volts. The
            # median absorbs the odd duplicated or missing point without
            # letting it decide the answer.
            steps = np.abs(np.diff(np.asarray(independent_var, dtype=np.float64)))
            step_v = float(np.median(steps)) if steps.size else 0.0

            # Smooth before if requested
            if smooth_before and n_points > 3:
                spectra = signal.savgol_filter(spectra, window_length, 3, axis=0)

            # Calculate derivative
            if order == 1:
                derivative = np.gradient(spectra, independent_var, axis=0)
                prefix = "dIdV"
            elif order == 2:
                first_deriv = np.gradient(spectra, independent_var, axis=0)
                derivative = np.gradient(first_deriv, independent_var, axis=0)
                prefix = "d2IdV2"
            else:
                raise ValueError("Order must be 1 or 2")

            # Smooth after if requested
            if smooth_after and n_points > 3:
                derivative = signal.savgol_filter(derivative, window_length, 3, axis=0)

            # Create DataFrame
            deriv_df = pd.DataFrame(derivative, columns=spectral_data.spectra.columns)
            deriv_df.insert(0, spectral_data.independent_var_name, independent_var)

            # Create user-friendly names using naming convention
            base_name = self._extract_clean_base_name(dataset_name)
            friendly_order = "1st_Derivative" if order == 1 else "2nd_Derivative"
            convention_name = self._apply_naming_convention(dataset_name, operation=friendly_order)

            # Save with convention-based filename
            output_path = self._ensure_output_dir('derivatives') / f"{convention_name}.csv"
            deriv_df.to_csv(output_path, index=False)

            # Create new dataset with clean base name (convention only for file path)
            friendly_name = f"{base_name} - {friendly_order.replace('_', ' ')}"

            metadata = SpectralMetadata(
                source_type=spectral_data.metadata.source_type,
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units={'independent': spectral_data.metadata.units.get('independent', 'V'),
                      'dependent': 'a.u.'},
                additional_info={
                    **self._carry_spatial_info(spectral_data.metadata),
                    'derivative_order': order,
                    # The smoothing that made this curve differentiable is an
                    # instrument function, and downstream it decides what
                    # counts as resolved. Recording it here means a tool that
                    # needs the resolution can read it instead of asking the
                    # user to remember. The pipeline is smooth -> gradient ->
                    # smooth, which is ~0.55 * window wide; a single-pass
                    # Savitzky-Golay derivative would be ~0.41 * window.
                    **({'deriv_window_points': int(window_length),
                        'deriv_window_v': float(window_length) * float(step_v),
                        'deriv_polyorder': 3,
                        'deriv_kind': 'smooth_gradient'}
                       if (smooth_before or smooth_after) and step_v > 0 else
                       {'deriv_window_points': 2,
                        'deriv_window_v': 2.0 * float(step_v),
                        'deriv_polyorder': 1,
                        'deriv_kind': 'smooth_gradient'} if step_v > 0 else {}),
                    'original': dataset_name
                }
            )
            deriv_spectral_data = SpectralData(deriv_df, metadata)
            # Store only with friendly name (no duplicates)
            self._datasets[friendly_name] = deriv_spectral_data
            # Only emit to browser when not in workflow mode (intermediate results shouldn't appear)
            if not self._workflow_mode:
                self.dataLoaded.emit(friendly_name)

            # Status update will be handled by callback in main thread
            logger.info(f"Derivative saved to {output_path}")

            return str(output_path)

        except Exception as e:
            logger.error(f"Derivative error: {e}", exc_info=True)
            self.errorOccurred.emit("Derivative Error", str(e))
            return ""

    # ========================================================================
    # Gradient Filter (for images)
    # ========================================================================

    def apply_gradient_filter(self, task, image_path: str, method: str = 'sobel') -> str:
        """
        Apply gradient filter to image.

        Parameters:
        -----------
        image_path : str
            Path to image
        method : str
            'sobel', 'prewitt', or 'scharr'

        Returns:
        --------
        output_path : str
            Path to gradient image
        """
        try:
            from scipy.ndimage import sobel, prewitt, generic_gradient_magnitude

            logger.info(f"Applying {method} gradient filter to {image_path}")

            # Load image
            img = Image.open(image_path).convert('L')
            img_array = np.array(img, dtype=float)

            # Apply gradient
            if method == 'sobel':
                gradient_x = sobel(img_array, axis=1)
                gradient_y = sobel(img_array, axis=0)
            elif method == 'prewitt':
                gradient_x = prewitt(img_array, axis=1)
                gradient_y = prewitt(img_array, axis=0)
            elif method == 'scharr':
                # Scharr operator
                scharr_x = np.array([[-3, 0, 3], [-10, 0, 10], [-3, 0, 3]])
                scharr_y = np.array([[-3, -10, -3], [0, 0, 0], [3, 10, 3]])
                from scipy.ndimage import convolve
                gradient_x = convolve(img_array, scharr_x)
                gradient_y = convolve(img_array, scharr_y)
            else:
                raise ValueError(f"Unknown method: {method}")

            # Calculate magnitude
            gradient_magnitude = np.sqrt(gradient_x**2 + gradient_y**2)

            # Normalize
            gradient_norm = ((gradient_magnitude - gradient_magnitude.min()) /
                           (gradient_magnitude.max() - gradient_magnitude.min()) * 255).astype(np.uint8)

            # Save
            output_path = self._ensure_output_dir('maps') / f"Gradient_{method}_{Path(image_path).stem}.png"
            result_img = Image.fromarray(gradient_norm)
            result_img.save(output_path)

            # Status update will be handled by callback in main thread
            logger.info(f"Gradient image saved to {output_path}")

            return str(output_path)

        except Exception as e:
            logger.error(f"Gradient filter error: {e}", exc_info=True)
            self.errorOccurred.emit("Gradient Error", str(e))
            return ""

    # ========================================================================
    # Image Discretizer
    # ========================================================================

    def discretize_image(self, task, image_path: str, method: str = 'uniform',
                        n_bins: int = 5, output_type: str = 'centroids') -> dict:
        """
        Discretize image values into bins.

        Parameters:
        -----------
        image_path : str
            Path to input image
        method : str
            'uniform' (equal width bins), 'quantile' (equal count), or 'kmeans' (clustering)
        n_bins : int
            Number of discrete levels (default 5)
        output_type : str
            'labels' (0, 1, 2, ...) or 'centroids' (bin center values)

        Returns:
        --------
        dict with 'image_path' (str) and 'labels' (pandas DataFrame)
        """
        try:
            import pandas as pd
            from sklearn.cluster import KMeans

            logger.info(f"Discretizing image {image_path} with {n_bins} bins using {method}")

            # Load image
            img = Image.open(image_path).convert('L')
            img_array = np.array(img, dtype=float)
            flat = img_array.flatten()

            # Calculate bin edges and labels
            if method == 'uniform':
                # Equal width bins
                bin_edges = np.linspace(flat.min(), flat.max(), n_bins + 1)
                bin_labels = np.digitize(flat, bin_edges[1:-1])
                bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

            elif method == 'quantile':
                # Equal count bins (quantiles)
                percentiles = np.linspace(0, 100, n_bins + 1)
                bin_edges = np.percentile(flat, percentiles)
                bin_labels = np.digitize(flat, bin_edges[1:-1])
                bin_centers = np.array([flat[(flat >= bin_edges[i]) & (flat < bin_edges[i+1])].mean()
                                       if i < len(bin_edges) - 1 else flat[flat >= bin_edges[-2]].mean()
                                       for i in range(n_bins)])
                # Handle NaN in bin centers
                bin_centers = np.nan_to_num(bin_centers, nan=np.nanmean(flat))

            elif method == 'kmeans':
                # K-means clustering
                kmeans = KMeans(n_clusters=n_bins, random_state=42, n_init=10)
                bin_labels = kmeans.fit_predict(flat.reshape(-1, 1))
                bin_centers = kmeans.cluster_centers_.flatten()
                # Sort by center value for consistent ordering
                sort_idx = np.argsort(bin_centers)
                label_map = {old: new for new, old in enumerate(sort_idx)}
                bin_labels = np.array([label_map[l] for l in bin_labels])
                bin_centers = bin_centers[sort_idx]
                bin_edges = None  # K-means doesn't have edges

            else:
                raise ValueError(f"Unknown discretization method: {method}")

            # Create output image
            if output_type == 'labels':
                # Output as bin indices (0, 1, 2, ...)
                result_array = bin_labels.reshape(img_array.shape)
                # Scale to 0-255 for visualization
                if n_bins > 1:
                    result_scaled = (result_array / (n_bins - 1) * 255).astype(np.uint8)
                else:
                    result_scaled = np.zeros_like(result_array, dtype=np.uint8)
            else:
                # Output as bin centroid values
                result_array = bin_centers[bin_labels].reshape(img_array.shape)
                # Normalize to 0-255
                result_min, result_max = result_array.min(), result_array.max()
                if result_max > result_min:
                    result_scaled = ((result_array - result_min) / (result_max - result_min) * 255).astype(np.uint8)
                else:
                    result_scaled = np.zeros_like(result_array, dtype=np.uint8)

            # Save discretized image
            output_path = self._ensure_output_dir('maps') / f"Discretized_{method}_{n_bins}bins_{Path(image_path).stem}.png"
            result_img = Image.fromarray(result_scaled)
            result_img.save(output_path)

            # Create labels DataFrame
            if bin_edges is not None:
                labels_df = pd.DataFrame({
                    'Bin': range(n_bins),
                    'Min': bin_edges[:-1],
                    'Max': bin_edges[1:],
                    'Center': bin_centers
                })
            else:
                labels_df = pd.DataFrame({
                    'Bin': range(n_bins),
                    'Center': bin_centers
                })

            logger.info(f"Discretized image saved to {output_path}")

            return {
                'image_path': str(output_path),
                'labels': labels_df
            }

        except Exception as e:
            logger.error(f"Image discretization error: {e}", exc_info=True)
            self.errorOccurred.emit("Discretization Error", str(e))
            return {}

    # ========================================================================
    # Curve Fitting / Baseline Correction
    # ========================================================================

    # The baseline estimators live in src.processing.peak_detection so that
    # this tool and Confinement Analysis share one implementation.

    def fit_curves(self, task, dataset_name: str, fit_type: str, degree: int = 2,
                   als_lambda: float = 1e5, als_p: float = 0.01,
                   basis: str = 'power') -> str:
        """
        Fit curves to spectral data and subtract baseline.

        Parameters:
        -----------
        dataset_name : str
            Dataset to fit
        fit_type : str
            Baseline correction method:
            - 'polynomial': Fit polynomial to entire spectrum (can remove all features!)
            - 'linear': Fit linear baseline to entire spectrum
            - 'exponential': Fit exponential baseline
            - 'als': Asymmetric Least Squares (recommended for peak preservation)
            - 'rubberband': Convex hull rubber band method
            - 'endpoints': Fit only to spectrum endpoints (good for STS)
        degree : int
            Polynomial degree (for polynomial/endpoints fit). Default 2.
        als_lambda : float
            ALS smoothness parameter (larger = smoother). Default 1e5.
        als_p : float
            ALS asymmetry parameter (smaller = baseline below peaks). Default 0.01.
        basis : str
            Polynomial basis for the 'polynomial' and 'endpoints' fits:
            'power' (monomials, the historical behaviour), 'legendre' or
            'chebyshev'. The orthogonal bases fit the same curve but return
            decorrelated coefficients on a normalised axis, which is what
            makes them comparable between spectra and usable as features.

        Returns:
        --------
        output_path : str
            Path to fit parameters and corrected data
        """
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            logger.info(f"Fitting {fit_type} to {dataset_name}")

            # QML / workflow params can arrive as floats (e.g. 3.0); np.polyfit
            # and the range()/f-strings below need a plain int.
            degree = int(degree)
            if basis not in POLYNOMIAL_BASES:
                raise ValueError(
                    f"basis must be one of {POLYNOMIAL_BASES}, got {basis!r}")

            independent_var = spectral_data.independent_var
            spectra = spectral_data.spectra.values

            # Debug logging
            logger.info(f"BaselineCorrection: Input data range: min={np.nanmin(spectra):.6e}, max={np.nanmax(spectra):.6e}")
            logger.info(f"BaselineCorrection: Shape: {spectra.shape[0]} points, {spectra.shape[1]} spectra")

            # Storage for fit parameters and corrected spectra
            fit_params_list = []
            corrected_spectra = []

            # Storage for baseline diagnostics
            baseline_values = []

            # Fit each spectrum
            for i, spectrum in enumerate(spectra.T):
                if task.cancelled:
                    return ""

                if fit_type == 'polynomial':
                    if basis == 'power':
                        # Untouched historical path: monomials on the raw axis,
                        # so previously exported coefficient maps stay valid.
                        coeffs = np.polyfit(independent_var, spectrum, degree)
                        baseline = np.polyval(coeffs, independent_var)
                        # Label by ascending power: c0 = constant term, c1 = x^1,
                        # ..., c{degree} = x^{degree}. np.polyfit returns coeffs
                        # highest-power first, so c{p} = coeffs[degree - p].
                        ordered = [float(coeffs[degree - p]) for p in range(degree + 1)]
                    else:
                        t = normalized_axis(independent_var)
                        ordered = fit_polynomial(t, spectrum, degree, basis)
                        baseline = eval_polynomial(ordered, t, basis)
                        ordered = [float(v) for v in ordered]
                    fit_params_list.append({
                        'spectrum_index': i,
                        'fit_type': fit_type,
                        **dict(zip(coefficient_names(degree, basis), ordered))
                    })
                elif fit_type == 'linear':
                    coeffs = np.polyfit(independent_var, spectrum, 1)
                    baseline = np.polyval(coeffs, independent_var)
                    fit_params_list.append({
                        'spectrum_index': i,
                        'fit_type': fit_type,
                        'slope': coeffs[0],
                        'intercept': coeffs[1]
                    })
                elif fit_type == 'exponential':
                    try:
                        def exp_func(x, a, b, c):
                            return a * np.exp(b * x) + c

                        popt, _ = optimize.curve_fit(exp_func, independent_var, spectrum,
                                                    p0=[1, 0.1, np.mean(spectrum)],
                                                    maxfev=5000)
                        baseline = exp_func(independent_var, *popt)
                        fit_params_list.append({
                            'spectrum_index': i,
                            'fit_type': fit_type,
                            'a': popt[0],
                            'b': popt[1],
                            'c': popt[2]
                        })
                    except:
                        coeffs = np.polyfit(independent_var, spectrum, 1)
                        baseline = np.polyval(coeffs, independent_var)
                        fit_params_list.append({
                            'spectrum_index': i,
                            'fit_type': 'linear_fallback',
                            'slope': coeffs[0],
                            'intercept': coeffs[1]
                        })
                elif fit_type == 'als':
                    # Asymmetric Least Squares - preserves peaks
                    baseline = als_baseline(spectrum, lam=als_lambda, p=als_p)
                    fit_params_list.append({
                        'spectrum_index': i,
                        'fit_type': fit_type,
                        'lambda': als_lambda,
                        'p': als_p
                    })
                elif fit_type == 'rubberband':
                    # Convex hull rubber band
                    baseline = rubberband_baseline(independent_var, spectrum)
                    fit_params_list.append({
                        'spectrum_index': i,
                        'fit_type': fit_type
                    })
                elif fit_type == 'endpoints':
                    # Fit only to endpoints - good for STS
                    baseline = endpoint_baseline(independent_var, spectrum,
                                                 n_points=max(5, len(spectrum)//20),
                                                 degree=degree, basis=basis)
                    fit_params_list.append({
                        'spectrum_index': i,
                        'fit_type': fit_type,
                        'degree': degree,
                        'basis': basis
                    })
                else:
                    raise ValueError(f"Unknown fit type: {fit_type}")

                # Track baseline statistics for diagnostics
                baseline_values.append({
                    'spectrum_index': i,
                    'baseline_mean': np.mean(baseline),
                    'baseline_std': np.std(baseline),
                    'baseline_min': np.min(baseline),
                    'baseline_max': np.max(baseline)
                })

                # Subtract baseline
                corrected = spectrum - baseline
                corrected_spectra.append(corrected)

            # Log baseline variance across spectra to diagnose "all same amount" issue
            baseline_means = [b['baseline_mean'] for b in baseline_values]
            baseline_variance = np.var(baseline_means)
            logger.info(f"BaselineCorrection: Baseline mean variance across {len(baseline_means)} spectra: {baseline_variance:.6e}")
            logger.info(f"BaselineCorrection: Baseline means range: {np.min(baseline_means):.6e} to {np.max(baseline_means):.6e}")

            # Debug logging for output
            corrected_array = np.array(corrected_spectra).T
            logger.info(f"BaselineCorrection: Output data range: min={np.nanmin(corrected_array):.6e}, max={np.nanmax(corrected_array):.6e}")

            # Create user-friendly names using naming convention
            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(dataset_name, operation="Baseline_Corrected")
            file_safe_name = self._sanitize_filename(base_name)

            # Save fit parameters (auxiliary files use base_name, not convention)
            params_df = pd.DataFrame(fit_params_list)
            params_path = self._ensure_output_dir('fitted') / f"{file_safe_name}_FitParams_{fit_type}.csv"
            params_df.to_csv(params_path, index=False)

            # Coefficients dataset: one row per spectrum, one column per fitted
            # coefficient (plus a Spectrum_Index column). Lets the user analyse
            # how the polynomial coefficients vary across spectra — e.g. to
            # infer metallicity — and export/map them. Built as FLAT data
            # (data_type='flat', 'Spectrum_Index' index, the source's spatial
            # dimensions) so it drops straight into the Map Generator: each
            # coefficient column becomes a spatial map. No 'original' key so it
            # is not overlaid on the source's graph window.
            coeff_dataset = None
            coeff_dataset_name = ""
            numeric_params = params_df.drop(columns=['fit_type'], errors='ignore')
            numeric_params = numeric_params.apply(pd.to_numeric, errors='coerce')
            if ('spectrum_index' in numeric_params.columns
                    and numeric_params.shape[1] >= 2):
                coeff_cols = [c for c in numeric_params.columns if c != 'spectrum_index']
                coeff_df = numeric_params[['spectrum_index'] + coeff_cols].copy()
                coeff_df = coeff_df.rename(columns={'spectrum_index': 'Spectrum_Index'})
                try:
                    coeff_meta = SpectralMetadata(
                        source_type='fit_coefficients',
                        dimensions=spectral_data.metadata.dimensions,
                        scan_mode=spectral_data.metadata.scan_mode,
                        units={'independent': 'Index', 'dependent': 'Coefficient'},
                        additional_info={
                            'created_from': 'curve_fitting',
                            'source_dataset': dataset_name,
                            'fit_type': fit_type,
                            'degree': degree,
                            'basis': basis,
                            'coefficient_columns': coeff_cols,
                        },
                        data_type='flat',
                    )
                    coeff_dataset = SpectralData(
                        coeff_df, coeff_meta,
                        topography=getattr(spectral_data, 'topography', None))
                    coeff_dataset_name = f"{base_name} - Fit Coefficients"
                    self._datasets[coeff_dataset_name] = coeff_dataset
                    if not self._workflow_mode:
                        self.dataLoaded.emit(coeff_dataset_name)
                    logger.info("Fit coefficients flat dataset '%s' created (%d spectra x %d coeffs)",
                                coeff_dataset_name, len(coeff_df), len(coeff_cols))
                except (ValueError, TypeError) as e:
                    logger.warning("Fit coefficients could not be promoted to a dataset: %s", e)
                    coeff_dataset, coeff_dataset_name = None, ""

            # Save baseline diagnostics for debugging
            baseline_df = pd.DataFrame(baseline_values)
            baseline_diag_path = self._ensure_output_dir('fitted') / f"{file_safe_name}_BaselineDiagnostics_{fit_type}.csv"
            baseline_df.to_csv(baseline_diag_path, index=False)
            logger.info(f"Baseline diagnostics saved to: {baseline_diag_path}")

            # Save corrected spectra
            corrected_df = pd.DataFrame(corrected_array, columns=spectral_data.spectra.columns)
            corrected_df.insert(0, spectral_data.independent_var_name, independent_var)

            corrected_path = self._ensure_output_dir('fitted') / f"{convention_name}.csv"
            corrected_df.to_csv(corrected_path, index=False)

            # Create new dataset with clean base name (convention only for file path)
            friendly_name = f"{base_name} - Baseline Corrected"
            metadata = SpectralMetadata(
                source_type=spectral_data.metadata.source_type,
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units=spectral_data.metadata.units.copy(),
                additional_info={
                    **self._carry_spatial_info(spectral_data.metadata),
                    'baseline_correction': fit_type,
                    'original': dataset_name
                }
            )
            corrected_spectral_data = SpectralData(corrected_df, metadata)
            # Store only with friendly name (no duplicates)
            self._datasets[friendly_name] = corrected_spectral_data
            # Only emit to browser when not in workflow mode (intermediate results shouldn't appear)
            if not self._workflow_mode:
                self.dataLoaded.emit(friendly_name)

            logger.info(f"Fit results saved to {params_path} and {corrected_path}")

            return str(corrected_path)

        except Exception as e:
            logger.error(f"Curve fitting error: {e}", exc_info=True)
            self.errorOccurred.emit("Fitting Error", str(e))
            return ""

    def estimate_dataset_baseline(self, task, dataset_name: str,
                                  params: Optional[dict] = None) -> dict:
        """Fit a background to every spectrum and subtract it.

        Runs the whole :func:`src.processing.peak_detection.estimate_baseline`
        family -- the same engine Confinement Analysis and the Map Generator
        use, so a background estimated here is the one they would have
        subtracted. Curve Fitting predates that engine and carries its own
        polynomial/ALS/rubberband implementation, which cannot do arPLS or
        SNIP at all.

        ``method='none'`` returns a background of zeros, so the corrected
        spectra are the raw ones. That is deliberate: a chain can keep the
        node wired in and turn the correction off without being rewired, and
        downstream nodes still see the axis and the column names they expect.

        Parameters
        ----------
        params : dict
            ``method`` plus the knobs :func:`estimate_baseline` takes. QML and
            the workflow engine send every number as a float, so the integer
            ones are cast back.

        Returns
        -------
        dict with the created SpectralData objects (for workflow capture),
        their names and the CSV paths.
        """
        empty = {'corrected': None, 'baseline': None, 'coefficients': None,
                 'dataset_names': {}, 'corrected_path': '', 'baseline_path': ''}
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return empty

            spectral_data = self._datasets[dataset_name]
            independent_var = np.asarray(spectral_data.independent_var, dtype=np.float64)
            spectra = np.asarray(spectral_data.spectra.values, dtype=np.float64)
            n_samples, n_spectra = spectra.shape

            params = params or {}
            method = str(params.get('method', CONFINEMENT_DEFAULTS['baseline']))
            if method not in BASELINE_KINDS:
                raise ValueError(f"Unknown background method {method!r}; "
                                 f"expected one of {BASELINE_KINDS}")
            degree = int(params.get('degree', 3))
            iterations = int(params.get('iterations', 25))
            direction = str(params.get('direction', 'positive'))
            als_lambda = float(params.get('als_lambda', 1e5))
            als_p = float(params.get('als_p', 0.01))
            endpoint_points = int(params.get('endpoint_points', 10))
            basis = str(params.get('basis', 'power'))

            logger.info(
                "BaselineEstimate: %s — %d spectra x %d points, background=%s"
                "(deg %d, %s, %d iterations, %s)",
                dataset_name, n_spectra, n_samples, method, degree, basis,
                iterations, direction)

            # Only the polynomial families have coefficients to report; for
            # arPLS, SNIP and rubberband the background is not a polynomial
            # and refitting one to it would describe the fit, not the data.
            coefficient_columns = (coefficient_names(degree, basis)
                                   if method in ('poly', 'poly-iter', 'endpoints')
                                   else [])

            baselines = np.full((n_samples, n_spectra), np.nan)
            coeff_rows = []
            for i in range(n_spectra):
                if getattr(task, 'cancelled', False):
                    logger.info("BaselineEstimate cancelled after %d/%d spectra",
                                i, n_spectra)
                    return empty

                # Fit on the finite samples only and scatter the result back:
                # a single NaN would otherwise poison a least-squares fit, and
                # a gap in the sweep must stay a gap in the background rather
                # than becoming a zero that the subtraction then keeps.
                y = spectra[:, i]
                idx = np.flatnonzero(np.isfinite(y) & np.isfinite(independent_var))
                fitted = np.zeros(0)
                if idx.size:
                    fitted = np.asarray(
                        estimate_baseline(independent_var[idx], y[idx], kind=method,
                                          degree=degree, iterations=iterations,
                                          direction=direction, als_lambda=als_lambda,
                                          als_p=als_p, endpoint_points=endpoint_points,
                                          basis=basis),
                        dtype=np.float64)
                    baselines[:, i] = _expand(fitted, idx, n_samples)

                if coefficient_columns:
                    coeffs = _baseline_coefficients(independent_var[idx], fitted,
                                                    degree, basis)
                    coeff_rows.append({'Spectrum_Index': i,
                                       **{name: coeffs[p]
                                          for p, name in enumerate(coefficient_columns)}})

                task.progress = int(100 * (i + 1) / max(1, n_spectra))

            corrected = spectra - baselines

            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(
                dataset_name, operation="Baseline_Estimate")
            fitted_dir = self._ensure_output_dir('fitted')
            columns = list(spectral_data.spectra.columns)
            created: dict = {}
            settings = {'baseline_method': method, 'degree': degree,
                        'basis': basis, 'direction': direction}

            def _register(suffix: str, frame: pd.DataFrame, metadata: SpectralMetadata):
                name = f"{base_name} - {suffix}"
                try:
                    dataset = SpectralData(frame, metadata)
                except (ValueError, TypeError) as exc:
                    logger.warning("BaselineEstimate: '%s' could not be built: %s", name, exc)
                    return
                self._datasets[name] = dataset
                if not self._workflow_mode:
                    self.dataLoaded.emit(name)
                created[suffix] = name

            def _meta(source_type, extra=None, *, overlay=False, flat=False):
                info = {'created_from': 'baseline_estimate',
                        'source_dataset': dataset_name, **settings, **(extra or {})}
                if not flat:
                    # Per-spectrum outputs keep the source's positions, so a
                    # corrected line scan can still be mapped onto the sample.
                    info = {**self._carry_spatial_info(spectral_data.metadata), **info}
                if overlay:
                    # Routes the result onto the source's graph window.
                    info['original'] = dataset_name
                return SpectralMetadata(
                    source_type=source_type,
                    dimensions=spectral_data.metadata.dimensions,
                    scan_mode=spectral_data.metadata.scan_mode,
                    units=dict(spectral_data.metadata.units or {}),
                    additional_info=info,
                    data_type='flat' if flat else spectral_data.metadata.data_type,
                )

            def _frame(values: np.ndarray) -> pd.DataFrame:
                frame = pd.DataFrame(values, columns=columns)
                frame.insert(0, spectral_data.independent_var_name, independent_var)
                return frame

            corrected_df = _frame(corrected)
            corrected_path = fitted_dir / f"{convention_name}.csv"
            corrected_df.to_csv(corrected_path, index=False)
            _register('Baseline Corrected', corrected_df,
                      _meta(spectral_data.metadata.source_type, overlay=True))

            background_df = _frame(baselines)
            baseline_path = fitted_dir / f"{convention_name}_Background.csv"
            background_df.to_csv(baseline_path, index=False)
            _register('Baseline', background_df,
                      _meta(spectral_data.metadata.source_type, overlay=True))

            if coeff_rows:
                _register('Baseline Coefficients', pd.DataFrame(coeff_rows),
                          _meta('fit_coefficients',
                                {'coefficient_columns': coefficient_columns},
                                flat=True))

            logger.info("BaselineEstimate: %s over %d spectra; created %s",
                        method, n_spectra, ", ".join(created.values()) or "nothing")

            return {
                'corrected': self._datasets.get(created.get('Baseline Corrected', '')),
                'baseline': self._datasets.get(created.get('Baseline', '')),
                'coefficients': self._datasets.get(created.get('Baseline Coefficients', '')),
                'dataset_names': created,
                'corrected_path': str(corrected_path),
                'baseline_path': str(baseline_path),
            }

        except Exception as e:
            logger.error(f"Baseline estimate error: {e}", exc_info=True)
            self.errorOccurred.emit("Baseline Estimate Error", str(e))
            return empty

    # ========================================================================
    # Map Generator
    # ========================================================================

    #: Scan paths the map builder understands. "auto" reads the dataset's
    #: own scan_mode, which is what every pre-existing caller relied on.
    SCAN_TYPES = ('auto', 'map_meander', 'map_raster', 'line')

    def _resolve_scan_type(self, scan_type: str, metadata) -> str:
        """Turn 'auto' into the concrete path this dataset was acquired on.

        A line scan has no second spatial axis, so folding it into rows would
        silently produce nonsense; it is recognised here and mapped to a
        single-row strip instead.
        """
        scan_type = (scan_type or 'auto').strip().lower()
        if scan_type in self.SCAN_TYPES and scan_type != 'auto':
            return scan_type

        info = getattr(metadata, 'additional_info', None) or {}
        dims = tuple(getattr(metadata, 'dimensions', ()) or ())
        layout = str(info.get('spatial_layout', '')).lower()
        mode = str(getattr(metadata, 'scan_mode', '') or '').lower()

        if layout == 'line' or mode == 'line' or (len(dims) == 2 and 1 in dims):
            return 'line'
        if mode == 'meander' and not info.get('meander_corrected', False):
            return 'map_meander'
        return 'map_raster'

    @staticmethod
    def _reshape_map_values(values: np.ndarray, dims, scan_type: str) -> np.ndarray:
        """Lay a per-spectrum value array out as a 2-D field.

        ``dims`` is (width, height) as carried on the metadata. Rows are
        flipped so the first acquired row ends up at the bottom, matching the
        orientation the maps have always been exported in.

        - ``map_meander``: odd rows were acquired right-to-left, so they are
          reversed — without this every other row is mirrored.
        - ``map_raster``: straight row-major fill.
        - ``line``: a single row, whatever ``dims`` claims.
        """
        values = np.asarray(values, dtype=np.float64).ravel()

        if scan_type == 'line':
            return values.reshape(1, values.size)

        dim_h, dim_v = int(dims[0]), int(dims[1])
        expected = dim_h * dim_v
        if values.size != expected:
            if expected and values.size % expected == 0:
                # Multi-channel payload (e.g. SNOM amplitude+phase): map the
                # first channel rather than refusing outright.
                n_channels = values.size // expected
                logger.warning("Map values are %dx the %dx%d grid; using the "
                               "first channel", n_channels, dim_h, dim_v)
                values = values[:expected]
            else:
                raise ValueError(
                    f"Data length {values.size} doesn't match dimensions "
                    f"{dim_h}x{dim_v}={expected} and is not a clean multiple")

        map_data = np.zeros((dim_v, dim_h), dtype=np.float64)
        for row in range(dim_v):
            chunk = values[row * dim_h:(row + 1) * dim_h]
            if scan_type == 'map_meander' and row % 2 == 1:
                chunk = chunk[::-1]
            map_data[dim_v - row - 1, :] = chunk
        return map_data

    def generate_map(self, task, flat_dataset_name: str, value_index: int = 0,
                     scan_type: str = 'auto') -> str:
        """
        Generate spatial map from flat data for a single value column.

        Flat data is any dataset with one value per spatial point (e.g., integrated
        spectral data, peak heights, fitted parameters, etc.).

        Parameters:
        -----------
        flat_dataset_name : str
            Name of flat dataset (e.g., integrated data, peak heights)
        value_index : int
            Index of value column to map (0 for first value column)

        Returns:
        --------
        output_path : str
            Path to generated map base (without extension)
        """
        try:
            # Convert to int in case QML passes as float
            value_index = int(value_index)

            if flat_dataset_name not in self._datasets:
                raise ValueError("Dataset not found")

            spectral_data = self._datasets[flat_dataset_name]
            logger.info(f"Generating map from {flat_dataset_name}, value index {value_index}")

            # Get dimensions (width, height)
            dim_h, dim_v = spectral_data.metadata.dimensions

            # Get flat values from the data
            # Flat data has "Spectrum_Index" (or similar x-column) + value columns
            data_df = spectral_data.data

            # Get value columns (skip index/x column which is typically first)
            value_columns = [col for col in data_df.columns if col != 'Spectrum_Index']

            if value_index >= len(value_columns):
                raise ValueError(f"Value index {value_index} out of range (max {len(value_columns)-1})")

            value_col = value_columns[value_index]
            flat_values = data_df[value_col].values

            logger.info(f"Got {len(flat_values)} flat values for value index {value_index}")

            path = self._resolve_scan_type(scan_type, spectral_data.metadata)
            map_data = self._reshape_map_values(flat_values, (dim_h, dim_v), path)
            logger.info("Map laid out as %s -> shape %s", path, map_data.shape)

            # Create output path base with clean name
            base_name = self._extract_clean_base_name(flat_dataset_name)
            file_safe_name = self._sanitize_filename(base_name)

            # Try to get interval info if available (for integrated data),
            # otherwise name the map by its value column (e.g. a coefficient
            # 'c0'/'c1'), falling back to a generic index.
            intervals = spectral_data.metadata.additional_info.get('intervals', [])
            if intervals and value_index < len(intervals):
                interval_info = intervals[value_index]
                value_str = f"{interval_info[0]:.3f}_{interval_info[1]:.3f}"
            elif value_col:
                value_str = self._sanitize_filename(str(value_col))
            else:
                value_str = f"val{value_index}"
            map_basename = f"{file_safe_name}_Map_{value_str}"
            output_base = self._ensure_output_dir('maps') / map_basename

            # Writes the calibrated TIFF/GSF and the CSV. (This used to be
            # followed by a second, pandas CSV write to the same path, which
            # overwrote the first with a header row; both map paths now leave
            # the same headerless grid.)
            self._save_map_images(map_data, output_base,
                                  source_metadata=spectral_data.metadata)

            logger.info(f"Map saved with base name: {output_base}")
            return str(output_base)

        except Exception as e:
            logger.error(f"Map generation error: {e}", exc_info=True)
            raise

    # -- intervals -----------------------------------------------------------

    #: Metadata keys under which a dataset may carry integration intervals.
    #: ``integration_intervals`` is what Confinement Analysis writes;
    #: ``intervals`` is what the Integration tool has always written.
    INTERVAL_KEYS = ('integration_intervals', 'intervals')

    def dataset_intervals(self, dataset_name: str) -> list:
        """Integration intervals carried by a dataset, as ``[[lo, hi], …]``.

        This is how the Map Generator picks up the intervals a Confinement
        Analysis run already found, instead of the user exporting a JSON file
        and loading it back.
        """
        dataset = self._datasets.get(dataset_name)
        if dataset is None:
            return []
        info = getattr(dataset.metadata, 'additional_info', None) or {}
        for key in self.INTERVAL_KEYS:
            raw = info.get(key)
            if not raw:
                continue
            out = []
            for item in raw:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    try:
                        out.append([float(item[0]), float(item[1])])
                    except (TypeError, ValueError):
                        continue
                elif isinstance(item, str) and '_' in item:
                    # Legacy "0.100_0.200" strings from older projects.
                    lo, _, hi = item.partition('_')
                    try:
                        out.append([float(lo), float(hi)])
                    except ValueError:
                        continue
            if out:
                return out
        return []

    @staticmethod
    def _grid_width(width: float, step: float,
                    source: str = "k_B*T/2") -> Tuple[float, str]:
        """``(width, why)`` for an energy grid, never finer than the sweep.

        The bin is the coarser of the two resolutions in play: k_B*T/2 (what
        the temperature justifies) and the sweep's own step (what the
        measurement actually resolves). Going finer than the step produces
        neighbouring bins that integrate the same two samples — duplicate
        maps that only look like extra information.

        Shared with :meth:`bin_peak_energies` so a chain built out of nodes
        and the Map Generator cannot drift onto different grids. A width of
        0.0 back means there is nothing to bin on at all: no temperature and
        no sweep to take a step from.
        """
        if width <= 0:
            return step, "no temperature set — using the sweep's own step"
        if step > 0 and width < step:
            return step, f"{source} is finer than the sweep step"
        return width, source

    def detect_map_intervals(self, task, dataset_name: str,
                             params: Optional[dict] = None) -> list:
        """Find the integration intervals for a dataset by peak detection.

        Runs exactly the Confinement Analysis pass — same background
        correction, same peak search — and then, with a temperature set,
        **takes the occupied k_B*T/2 bins as the intervals**, which is the
        grid Confinement Analysis reports its occupancy table on. The two
        tools therefore agree on where the confined states are, and each map
        covers one state at the resolution the temperature justifies.

        Without a temperature there are no bins, so it falls back to merging
        the peaks' FWHM bands. That fallback is lossy — overlapping bands fuse
        into a few wide ones (on 4.5 K line-scan data: 206 occupied bins
        against 3 merged bands, one of them a quarter of the sweep) — which is
        why binning is preferred.

        Returns ``[[lo, hi], …]``.
        """
        if dataset_name not in self._datasets:
            self.errorOccurred.emit("Error", "Dataset not found")
            return []

        spectral_data = self._datasets[dataset_name]
        independent_var = np.asarray(spectral_data.independent_var, dtype=np.float64)
        spectra = np.asarray(spectral_data.spectra.values, dtype=np.float64)

        params = {**MAP_DEFAULTS, **(params or {})}
        detect_params = params_from_dict({**CONFINEMENT_DEFAULTS, **params})
        detect_params.validate()
        if detect_params.thermal_width > 0 and not detect_params.min_distance:
            detect_params.min_distance = detect_params.thermal_width

        results = analyze_many(
            independent_var, spectra, detect_params,
            should_cancel=lambda: bool(getattr(task, 'cancelled', False)),
        )
        if len(results) < spectra.shape[1]:
            logger.info("Map interval detection cancelled after %d/%d spectra",
                        len(results), spectra.shape[1])
            return []

        # -- one interval per occupied bin ---------------------------------
        step = float(np.median(np.abs(np.diff(independent_var)))) if independent_var.size > 1 else 0.0
        width, why = self._grid_width(detect_params.bin_width, step)

        if width <= 0:
            logger.warning("Map Generator: cannot bin %s — no usable bias axis",
                           dataset_name)
            return []

        edges, _centers = energy_bins(independent_var, width)
        # How many spectra have a peak in each bin, so thinly-populated bins
        # can be dropped without touching the energy grid.
        spectra_per_bin: Dict[int, int] = {}
        for result in results:
            for bin_index, _peak, _merged in group_peaks_by_bin(result.peaks, edges):
                spectra_per_bin[int(bin_index)] = spectra_per_bin.get(int(bin_index), 0) + 1

        min_spectra = max(1, int(float((params or {}).get('min_spectra_per_bin', 1) or 1)))
        occupied = sorted(b for b, n in spectra_per_bin.items() if n >= min_spectra)
        intervals = [[float(edges[b]), float(edges[b + 1])] for b in occupied]
        logger.info("Map Generator: %d peak(s) over %d spectra -> %d occupied bin(s) "
                    "of %.4g (%s), %d kept at >=%d spectra",
                    sum(len(r.peaks) for r in results), spectra.shape[1],
                    len(spectra_per_bin), width, why, len(intervals), min_spectra)
        return intervals

    def bin_peak_energies(self, task, peaks_dataset_name: str,
                          params: Optional[dict] = None,
                          source_dataset_name: Optional[str] = None) -> dict:
        """Bin peaks that have already been found onto the k_B*T/2 grid.

        This is the second half of :meth:`detect_map_intervals` — the half
        that turns peaks into intervals — with the search taken off the
        front, so a chain that has already found its peaks (Peak Finder,
        Confinement Analysis) does not pay for a second pass over the
        spectra. Both share :meth:`_grid_width`, so the intervals a workflow
        builds this way are the ones the Map Generator would have used.

        Deliberately not Peak Finder's ``intervals`` port: those are FWHM
        bands merged wherever they overlap, which fuses everything into a
        handful of wide ones (on 4.5 K line-scan data, 206 occupied bins
        against 3 merged bands, one of them a quarter of the sweep). Occupied
        bins are also the axis Confinement Analysis reports its binned
        occupancy table on, so the two tools describe the same states.

        Parameters
        ----------
        source_dataset_name : str, optional
            The spectra the peaks came from. It supplies the sweep step,
            which floors the bin width, and the span the grid covers. Without
            it the grid is anchored on the peaks themselves: it reaches no
            further than the outermost state, and nothing catches a width
            finer than the measurement can resolve.

        Returns
        -------
        dict with the occupied bins, the whole grid, and the bin table.
        """
        empty = {'intervals': [], 'all_bins': [], 'bins': None, 'bins_name': '',
                 'bin_width': 0.0, 'bin_width_reason': '', 'edges': []}
        try:
            if peaks_dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Peak table not found")
                return empty

            source_data = None
            if source_dataset_name:
                source_data = self._datasets.get(source_dataset_name)
                if source_data is None:
                    self.errorOccurred.emit("Error", "Dataset not found")
                    return empty

            # Peak Finder and Confinement Analysis both write snake_case, but
            # a table that has been through a flat-data tool comes back with
            # Spectrum_Index, so the names are matched case-insensitively.
            frame = self._datasets[peaks_dataset_name].data
            by_name = {str(column).lower(): column for column in frame.columns}
            missing = [name for name in ('spectrum_index', 'position_value')
                       if name not in by_name]
            if missing:
                self.errorOccurred.emit(
                    "Energy Binning Error",
                    f"The peak table has no {' and no '.join(missing)} column")
                return empty

            spectrum_index = pd.to_numeric(frame[by_name['spectrum_index']],
                                           errors='coerce').to_numpy()
            position = pd.to_numeric(frame[by_name['position_value']],
                                     errors='coerce').to_numpy()
            usable = np.isfinite(spectrum_index) & np.isfinite(position)
            spectrum_index = spectrum_index[usable].astype(np.int64)
            position = position[usable].astype(np.float64)
            if position.size == 0:
                # A run that found nothing is an answer, not a fault — the
                # chain downstream gets no intervals and says so.
                logger.warning("EnergyBinning: %s holds no usable peaks",
                               peaks_dataset_name)
                return empty

            params = params or {}
            # Validated through Params so the unit and the temperature are
            # rejected here on exactly the terms the engine rejects them on.
            grid_params = params_from_dict({
                'temperature_k': params.get('temperature_k', 0.0),
                'x_energy_unit': params.get('x_energy_unit', 'eV')})
            grid_params.validate()

            if source_data is not None:
                x_span = np.asarray(source_data.independent_var, dtype=np.float64)
                step = (float(np.median(np.abs(np.diff(x_span))))
                        if x_span.size > 1 else 0.0)
            else:
                logger.info("EnergyBinning: no source spectra for %s — the grid "
                            "is anchored on the peak positions, not the sweep",
                            peaks_dataset_name)
                x_span, step = position, 0.0

            requested = float(params.get('bin_width', 0.0) or 0.0)
            width, why = self._grid_width(
                requested if requested > 0 else grid_params.bin_width, step,
                "the requested bin width" if requested > 0 else "k_B*T/2")
            if width <= 0:
                logger.warning("EnergyBinning: cannot bin %s — no temperature, "
                               "no bin width, and no sweep to take a step from",
                               peaks_dataset_name)
                return empty

            edges, centers = energy_bins(x_span, width)

            # Several peaks of one spectrum in one bin are one occupancy, the
            # collapse group_peaks_by_bin performs: peaks closer together than
            # the bin are not distinguishable, so counting them separately
            # would let one spectrum outvote its neighbours in the
            # min_spectra_per_bin filter.
            occupancy = pd.DataFrame({'spectrum': spectrum_index,
                                      'bin': assign_bins(position, edges)})
            peaks_per_bin = occupancy.groupby('bin').size()
            spectra_per_bin = occupancy.drop_duplicates().groupby('bin').size()

            min_spectra = max(1, int(float(params.get('min_spectra_per_bin', 1) or 1)))
            populated = [int(b) for b in spectra_per_bin.index]
            intervals, rows = [], []
            for done, bin_index in enumerate(populated):
                if getattr(task, 'cancelled', False):
                    logger.info("EnergyBinning cancelled after %d/%d bins",
                                done, len(populated))
                    return empty
                n_spectra = int(spectra_per_bin.loc[bin_index])
                occupied = n_spectra >= min_spectra
                if occupied:
                    intervals.append([float(edges[bin_index]),
                                      float(edges[bin_index + 1])])
                rows.append({'bin_center': float(centers[bin_index]),
                             'bin_index': bin_index,
                             'bin_low': float(edges[bin_index]),
                             'bin_high': float(edges[bin_index + 1]),
                             'n_spectra': n_spectra,
                             'n_peaks': int(peaks_per_bin.loc[bin_index]),
                             'occupied': int(occupied)})
                task.progress = int(100 * (done + 1) / max(1, len(populated)))

            all_bins = [[float(edges[b]), float(edges[b + 1])]
                        for b in range(len(edges) - 1)]

            base_name = self._extract_clean_base_name(
                source_dataset_name or peaks_dataset_name)
            bins_name = f"{base_name} - Energy Bins"
            info = {
                'created_from': 'energy_binning',
                'source_dataset': source_dataset_name or peaks_dataset_name,
                'peaks_dataset': peaks_dataset_name,
                'bin_width': float(width),
                'bin_width_reason': why,
                'temperature_k': float(grid_params.temperature_k),
                'x_energy_unit': grid_params.x_energy_unit,
                'min_spectra_per_bin': min_spectra,
                # Published under integration_intervals so dataset_intervals()
                # finds them. Never under 'intervals': that key marks a
                # dataset as integrated VALUES, which the Hyperspectral tab
                # skips, and this one is a table of bins.
                'integration_intervals': [list(iv) for iv in intervals],
                'bin_edges': [float(edge) for edge in edges],
            }
            metadata = SpectralMetadata(
                source_type='energy_bins',
                dimensions=(len(rows), 1),
                scan_mode='bins',
                units=(dict(source_data.metadata.units or {})
                       if source_data is not None
                       else {'x': grid_params.x_energy_unit,
                             'independent': grid_params.x_energy_unit}),
                # No 'original' key on purpose: a table of bins is not a
                # spectrum and must not be overlaid on the source's graph.
                additional_info=info,
            )

            bins_dataset = None
            if rows:
                try:
                    bins_dataset = SpectralData(
                        pd.DataFrame(rows, columns=['bin_center', 'bin_index',
                                                    'bin_low', 'bin_high',
                                                    'n_spectra', 'n_peaks',
                                                    'occupied']),
                        metadata)
                except (ValueError, TypeError) as exc:
                    logger.warning("EnergyBinning: '%s' could not be built: %s",
                                   bins_name, exc)
            if bins_dataset is not None:
                self._datasets[bins_name] = bins_dataset
                if not self._workflow_mode:
                    self.dataLoaded.emit(bins_name)
            else:
                bins_name = ''

            logger.info("EnergyBinning: %d peak(s) over %d spectra -> %d occupied "
                        "bin(s) of %.4g (%s), %d kept at >=%d spectra",
                        int(position.size), int(occupancy['spectrum'].nunique()),
                        len(populated), width, why, len(intervals), min_spectra)

            return {
                'intervals': intervals,
                'all_bins': all_bins,
                'bins': bins_dataset,
                'bins_name': bins_name,
                'bin_width': float(width),
                'bin_width_reason': why,
                'edges': [float(edge) for edge in edges],
            }

        except Exception as e:
            logger.error(f"Energy binning error: {e}", exc_info=True)
            self.errorOccurred.emit("Energy Binning Error", str(e))
            return empty

    def _resolve_map_intervals(self, task, dataset_name: str,
                               params: dict) -> list:
        """Intervals for a map run, from whichever source the user picked."""
        source = str(params.get('interval_source', 'detect')).lower()

        if source in ('manual', 'given', 'list'):
            return self._clean_intervals(params.get('intervals'))

        if source in ('dataset', 'analysis', 'confinement'):
            name = params.get('intervals_from') or dataset_name
            found = self.dataset_intervals(name)
            if not found:
                # Fall back to whatever the caller passed, so a stale pick
                # doesn't silently produce zero maps.
                found = self._clean_intervals(params.get('intervals'))
            return found

        return self.detect_map_intervals(task, dataset_name, params)

    @staticmethod
    def _interval_grid(bounds: list, tol: float = 0.02):
        """``(bin_width, on_a_grid)`` for a sorted list of ``[lo, hi]``.

        True when every interval has the same width and every start sits a
        whole number of widths from the first — i.e. they are bins of one
        grid, which is what the detected intervals always are. Hand-entered
        intervals usually are not, and must not be forced onto one.
        """
        if len(bounds) < 2:
            return (float(bounds[0][1] - bounds[0][0]) if bounds else 0.0, False)
        widths = np.array([hi - lo for lo, hi in bounds], dtype=np.float64)
        width = float(np.median(widths))
        if width <= 0:
            return 0.0, False
        if np.any(np.abs(widths - width) > tol * width):
            return width, False
        starts = np.array([lo for lo, _hi in bounds], dtype=np.float64)
        steps = (starts - starts[0]) / width
        if np.any(np.abs(steps - np.round(steps)) > tol):
            return width, False
        return width, True

    @staticmethod
    def _clean_intervals(raw) -> list:
        out = []
        for item in raw or []:
            if isinstance(item, dict):
                lo, hi = item.get('lower', item.get('start')), item.get('upper', item.get('end'))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                lo, hi = item[0], item[1]
            else:
                continue
            try:
                lo, hi = float(lo), float(hi)
            except (TypeError, ValueError):
                continue
            if hi < lo:
                lo, hi = hi, lo
            if hi > lo:
                out.append([lo, hi])
        return out

    def _assemble_value_maps(self, task, *, base_name: str, file_safe_name: str,
                             value_columns: dict, intervals: Optional[list],
                             source_data, source_dataset_name: str,
                             scan_type: str, dims, columns: list,
                             folders: dict, created_from: str,
                             extra_info: Optional[dict] = None) -> dict:
        """Lay one value per spectrum out on the sample, once per column.

        Everything downstream of "one number per spectrum" lives here: the
        layout, the physical scale, the per-column files and the joined
        interval map. The Map Generator and the Map Assembly node both go
        through it, so a chain rebuilt out of nodes cannot drift onto a
        different orientation, a different file name or a different scale
        from the composite it replaces.

        ``intervals`` runs parallel to ``value_columns`` and is what makes the
        joined map possible: without it the columns share no axis to be
        stacked on, and only the per-column maps are written.

        ``source_data`` is whatever knows where the spectra were taken, which
        need not be the dataset holding the values — a flat table of integrals
        usually records only its source's name. May be None, in which case
        nothing claims a position and the maps go out in point indices.
        """
        # Real positions along the line, so a map's x axis is distance
        # rather than a column index. Left unset for area scans, whose
        # geometry the metadata already describes.
        positions = (self._line_positions_m(source_data)
                     if scan_type == 'line' else None)
        position_step = (self._line_step_m(source_data)
                         if scan_type == 'line' else None)
        units = dict(getattr(getattr(source_data, 'metadata', None),
                             'units', None) or {})
        value_unit = units.get('dependent')

        map_scale = None
        if position_step:
            map_scale = {'dx': position_step, 'dy': position_step,
                         'unit': 'm', 'value_unit': value_unit,
                         'x_offset': float(positions[0]) if positions is not None else 0.0,
                         'axis_note': 'x=position (m)'}
        elif scan_type == 'line':
            # The loader did not record positions (a dataset re-imported
            # from CSV, say). The column INDEX is still a real axis, so it
            # is written as one rather than leaving the file dimensionless
            # — what must never happen is claiming metres we do not have.
            map_scale = {'dx': 1.0, 'dy': 1.0, 'unit': None,
                         'value_unit': value_unit, 'mixed_axes': True,
                         'axis_note': 'x=position (point index)'}

        cancelled = {'map_paths': [], 'interval_map': '', 'interval_map_path': '',
                     'interval_map_dataset': None, 'empty_bins': 0,
                     'on_a_grid': False, 'cancelled': True}

        map_paths = []
        labels = list(value_columns)
        for i, label in enumerate(labels):
            if getattr(task, 'cancelled', False):
                return cancelled
            task.progress = i / len(labels)

            map_data = self._reshape_map_values(value_columns[label], dims, scan_type)
            output_base = (folders['root']
                           / f"{file_safe_name}_Map_{self._sanitize_filename(str(label))}")
            self._save_map_images(map_data, output_base,
                                  source_metadata=getattr(source_data, 'metadata', None),
                                  folders=folders, scale=map_scale)
            map_paths.append(str(folders['tiff'] / f"{output_base.name}.tiff"))

        # One map joining every interval: x is the position along the
        # line, y is the interval, indexed by its midpoint. Reading a
        # column gives that position's spectrum over the states found —
        # what the per-interval maps cannot show side by side. (A 2-D
        # grid would need a third axis; not built here.)
        interval_map_name = ""
        interval_map_path = ""
        interval_map_dataset = None
        empty_rows = 0
        on_a_grid = False
        if intervals and len(value_columns) > 1:
            ordered = sorted(zip(intervals, value_columns.values()),
                             key=lambda pair: (pair[0][0] + pair[0][1]) / 2.0)
            n_spectra = int(np.asarray(ordered[0][1]).size)

            # Detected intervals are bins on one uniform grid, and the
            # occupied ones need not be adjacent. A file's energy axis is
            # linear, so those rows are laid out on the FULL grid with
            # ZERO rows where no spectrum had a peak — packing only the
            # occupied rows together would put every state at the wrong
            # bias. Hand-entered intervals are usually neither uniform nor
            # aligned, and then one row per interval is all that can
            # honestly be claimed.
            #
            # Empty bins are written as 0, not NaN: no peak means no
            # spectral weight at that bias, which is a value. NaN means
            # "not measured", and viewers render it as a masked or
            # interpolated region — reading as though something were
            # there.
            bounds = [iv for iv, _ in ordered]
            bin_width, on_a_grid = self._interval_grid(bounds)
            first_low = float(bounds[0][0])

            if on_a_grid:
                def _row_of(interval):
                    return int(round((interval[0] - first_low) / bin_width))

                n_rows = _row_of(bounds[-1]) + 1
                stack = np.zeros((n_rows, n_spectra), dtype=np.float64)
                filled = np.zeros(n_rows, dtype=bool)
                for interval, values_for_bin in ordered:
                    row = _row_of(interval)
                    stack[row, :] = np.asarray(values_for_bin, dtype=np.float64)
                    filled[row] = True
                empty_rows = int((~filled).sum())
                midpoints = first_low + (np.arange(n_rows) + 0.5) * bin_width
            else:
                stack = np.vstack([np.asarray(v, dtype=np.float64)
                                   for _, v in ordered])
                midpoints = np.array([(lo + hi) / 2.0 for lo, hi in bounds])
                n_rows = stack.shape[0]
                empty_rows = 0

            if empty_rows:
                logger.info("Interval map: %d of %d rows are empty bins, "
                            "written as zero (kept so the energy axis "
                            "stays linear)", empty_rows, n_rows)

            joined_base = folders['root'] / f"{file_safe_name}_IntervalMap"
            # x is distance along the line, y is the interval's energy —
            # two different quantities, so the export records both rather
            # than labelling them with one unit (see export_field's
            # ``mixed_axes``).
            # The energy axis spans the intervals themselves — from the
            # bottom of the lowest to the top of the highest — so a
            # reader lands on real bias values, not row numbers. dy is
            # that span divided by the rows, and the offset is where it
            # starts; ``np.median`` of the midpoint spacing would be
            # wrong the moment the occupied bins are not contiguous.
            energy_low = float(min(lo for lo, _hi in bounds))
            energy_high = (energy_low + n_rows * bin_width if on_a_grid
                           else float(max(hi for _lo, hi in bounds)))
            energy_span = energy_high - energy_low
            x_unit = units.get('independent', 'V')

            joined_scale = {
                'dx': position_step if position_step else 1.0,
                'dy': (energy_span / stack.shape[0]) if energy_span > 0 else 1.0,
                'unit': None,          # the two axes do not share one
                'value_unit': value_unit,
                'mixed_axes': True,
                'x_offset': float(positions[0]) if positions is not None else 0.0,
                'y_offset': energy_low,
                'axis_note': (
                    f"x=position ({'m' if position_step else 'point index'}) "
                    f"{'%.4g..%.4g' % (positions[0], positions[-1]) if positions is not None else '0..%d' % (stack.shape[1] - 1)}, "
                    f"y=energy ({x_unit}) {energy_low:.4g}..{energy_high:.4g}"),
            }
            # Low bias at the bottom, matching the per-interval maps.
            self._save_map_images(np.flipud(stack), joined_base,
                                  source_metadata=None, folders=folders,
                                  scale=joined_scale)
            interval_map_path = str(folders['tiff'] / f"{joined_base.name}.tiff")

            # Registered as a spectral dataset — bias on the independent
            # axis, one column per position — so it opens in the
            # Hyperspectral tab as a kymograph like any line scan.
            joined = pd.DataFrame(stack, columns=columns)
            # The row axis is energy. Naming it after the source works while
            # the source is the spectra; a flat table's first column is the
            # spectrum number, which would label the energy axis with the
            # wrong quantity, so that case falls back to the recorded unit.
            axis_name = getattr(source_data, 'independent_var_name', None)
            if getattr(getattr(source_data, 'metadata', None),
                       'data_type', 'flat') == 'flat':
                axis_name = units.get('independent') or 'Energy'
            joined.insert(0, axis_name, midpoints)
            interval_map_name = f"{base_name} - Interval Map"
            interval_map_dataset = SpectralData(
                joined,
                SpectralMetadata(
                    source_type=getattr(getattr(source_data, 'metadata', None),
                                        'source_type', 'map_values'),
                    # (positions, 1): the Hyperspectral tab reads that as
                    # a line scan and draws the kymograph.
                    dimensions=(len(columns), 1),
                    scan_mode='line',
                    units=dict(units),
                    additional_info={
                        'created_from': created_from,
                        'source_dataset': source_dataset_name,
                        # NOT 'intervals': that key marks a dataset as
                        # integrated values, which the Hyperspectral tab
                        # skips. These bounds are documentation only.
                        'interval_bounds': [list(iv) for iv, _ in ordered],
                        'interval_midpoints': midpoints.tolist(),
                        'bin_width': bin_width,
                        'empty_bins': empty_rows,
                        # Column positions in metres, so the kymograph's
                        # x axis is distance and not a column number.
                        'position_m': (self._line_positions_m(source_data).tolist()
                                       if self._line_positions_m(source_data) is not None
                                       else None),
                        'position_step_m': position_step,
                        'scan_type': scan_type,
                        'spatial_layout': 'line',
                        **(extra_info or {}),
                    },
                ))
            self._datasets[interval_map_name] = interval_map_dataset
            if not self._workflow_mode:
                self.dataLoaded.emit(interval_map_name)
            logger.info("Interval map: %d intervals x %d positions -> %s",
                        stack.shape[0], stack.shape[1], interval_map_name)

        return {'map_paths': map_paths,
                'interval_map': interval_map_name,
                'interval_map_path': interval_map_path,
                'interval_map_dataset': interval_map_dataset,
                'empty_bins': empty_rows,
                'on_a_grid': on_a_grid,
                'cancelled': False}

    def generate_maps_from_spectra(self, task, dataset_name: str,
                                   params: Optional[dict] = None) -> dict:
        """Background-correct, integrate over V intervals, and map the result.

        One pass over the spectra replaces the old three-step detour (export
        peak intervals to JSON → background-correct by hand → integrate →
        map): the background comes off with the same polynomial/ALS machinery
        Confinement Analysis uses, the intervals come from that same peak
        search (or from a previous run's results), and each interval's
        integral becomes one map.

        Outputs are unchanged: one calibrated ``.tiff`` (+ ``.gsf``/``.csv``)
        per interval, via the usual export path.
        """
        params = {**MAP_DEFAULTS, **(params or {})}
        empty = {'map_paths': [], 'intervals': [], 'values_dataset': '',
                 'interval_map': '', 'interval_map_path': '', 'output_folder': '',
                 'scan_type': '', 'n_maps': 0}
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return empty

            # Claim the output folder FIRST. It is the one step that can fail
            # for a reason having nothing to do with the data -- no project is
            # open, so there is nowhere to write -- and it used to be the last
            # step before the files were written, roughly two minutes in: peak
            # detection over every spectrum, then a full background correction
            # over every spectrum, and only then "No project set". Multiply by
            # a batch of three datasets and the run looks like it worked and
            # quietly produced nothing.
            #
            # mkdir is idempotent, so doing it here costs nothing but an empty
            # directory in the case where a later stage has no intervals.
            folders = self._map_output_folders(dataset_name)

            spectral_data = self._datasets[dataset_name]
            independent_var = np.asarray(spectral_data.independent_var, dtype=np.float64)
            spectra = np.asarray(spectral_data.spectra.values, dtype=np.float64)
            n_samples, n_spectra = spectra.shape

            scan_type = self._resolve_scan_type(params.get('scan_type', 'auto'),
                                                spectral_data.metadata)
            dims = params.get('dimensions') or spectral_data.metadata.dimensions
            dims = (int(dims[0]), int(dims[1])) if len(dims) >= 2 else (n_spectra, 1)

            intervals = self._resolve_map_intervals(task, dataset_name, params)
            if task.cancelled:
                return empty
            if not intervals:
                self.errorOccurred.emit(
                    "Map Generator",
                    "No integration intervals — detect peaks, pick an analysis "
                    "result, or enter intervals by hand.")
                return empty

            logger.info("Map Generator: %s — %d spectra, %s layout %s, %d interval(s)",
                        dataset_name, n_spectra, scan_type, dims, len(intervals))

            # Background correction: the integral must measure the state, not
            # the band edge under it, so the same correction the peak search
            # ran on is what gets integrated.
            detect_params = params_from_dict({**CONFINEMENT_DEFAULTS, **params})
            detect_params.validate()
            corrected = spectra
            spectrum_sigma = np.zeros(n_spectra)
            if detect_params.baseline != 'none':
                results = analyze_many(
                    independent_var, spectra, detect_params,
                    should_cancel=lambda: bool(getattr(task, 'cancelled', False)),
                )
                if len(results) < n_spectra:
                    logger.info("Map Generator cancelled during background correction")
                    return empty
                corrected = np.array([
                    _expand(r.y_raw - r.baseline, r.idx, n_samples)
                    if r.baseline.size == r.y_raw.size
                    else _expand(r.y_raw, r.idx, n_samples)
                    for r in results]).T
                spectrum_sigma = np.array([
                    noise_sigma(r.y_raw - r.baseline)
                    if r.baseline.size == r.y_raw.size else noise_sigma(r.y_raw)
                    for r in results])
            else:
                spectrum_sigma = np.array([noise_sigma(spectra[:, i])
                                           for i in range(n_spectra)])

            base_name = self._extract_clean_base_name(dataset_name)
            file_safe_name = self._sanitize_filename(base_name)
            columns = list(spectral_data.spectra.columns)

            # An interval narrower than the sweep's own step holds one sample
            # or none, and integrating that returns exactly zero — every map
            # came out blank. Thermal bins are routinely finer than the bias
            # resolution (0.19 mV bins on a 4.7 mV grid at 4.5 K), so the
            # window is widened to the measurement's resolution while the
            # interval keeps naming the state it belongs to.
            steps = np.abs(np.diff(independent_var))
            steps = steps[steps > 0]
            dx = float(np.median(steps)) if steps.size else 0.0
            min_width = 2.0 * dx
            widened = 0

            # Noise floor, in multiples of each spectrum's own sigma. Only
            # what stands above it is integrated.
            #
            # Without one, a bin holding no state integrates pure noise, which
            # is negative half the time — on real dI/dV line scans 41% of the
            # map's cells came out negative, carrying |weight| comparable to
            # the real states. That is not a background that can be fitted
            # better: the row medians sit 6x below the within-row scatter, so
            # there is no systematic overshoot to remove. At 1 sigma the
            # negatives vanish, the states keep their weight, and the empty
            # bins collapse to ~0 — the map shows spectral weight instead of
            # the noise floor. 0 removes the floor but NOT the positivity
            # rule: the integral is always over the positive part, because a
            # density of states cannot be negative. This tool is dI/dV-only
            # (it runs the confinement engine), so there is nothing signed
            # for it to be wrong about.
            noise_floor = max(0.0, float(params.get('noise_floor', 1.0) or 0.0))

            value_columns = {}
            for i, (lo, hi) in enumerate(intervals):
                if task.cancelled:
                    return empty
                task.progress = i / len(intervals)

                lo_w, hi_w = lo, hi
                if dx > 0 and (hi_w - lo_w) < min_width:
                    centre = (lo + hi) / 2.0
                    lo_w, hi_w = centre - dx, centre + dx
                    widened += 1

                mask = (independent_var >= lo_w) & (independent_var <= hi_w)
                if np.count_nonzero(mask) < 2:
                    # Still too narrow to integrate (an edge bin, or a single
                    # sample): take the nearest two samples so the map carries
                    # the same quantity as every other map in the run.
                    nearest = int(np.argmin(np.abs(independent_var - (lo + hi) / 2.0)))
                    lo_idx = max(0, min(nearest, independent_var.size - 2))
                    mask = np.zeros(independent_var.size, dtype=bool)
                    mask[lo_idx:lo_idx + 2] = True
                if not np.any(mask):
                    logger.warning("Map Generator: no samples in interval [%g, %g]", lo, hi)
                    continue

                # NaN-tolerant: a railed sample must not wipe out the integral
                # of the whole spectrum.
                block = np.nan_to_num(corrected[mask, :], nan=0.0)
                if noise_floor > 0:
                    # Only the part standing above each spectrum's own noise
                    # counts as spectral weight; the rest is not measurement.
                    block = block - noise_floor * spectrum_sigma[None, :]
                # Negative LDOS is not a measurement: only the positive part
                # is integrated, so a two-sided noise excursion cannot cancel
                # real spectral weight elsewhere in the same interval. With
                # noise_floor at 0 this is the only thing keeping the map off
                # the fit residual.
                values = positive_integral(block, independent_var[mask], axis=0)

                label = f"{lo:.3f}_{hi:.3f}"
                value_columns[label] = values

            assembled = self._assemble_value_maps(
                task, base_name=base_name, file_safe_name=file_safe_name,
                value_columns=value_columns, intervals=intervals,
                source_data=spectral_data, source_dataset_name=dataset_name,
                scan_type=scan_type, dims=dims, columns=columns,
                folders=folders, created_from='map_generator')
            if assembled['cancelled']:
                return empty
            map_paths = assembled['map_paths']
            interval_map_name = assembled['interval_map']
            interval_map_path = assembled['interval_map_path']

            # The per-interval integrals as a flat dataset, so the numbers
            # behind the maps stay inspectable (and re-mappable) instead of
            # living only inside the image files.
            values_name = ""
            if value_columns:
                frame = pd.DataFrame({'Spectrum_Index': np.arange(n_spectra),
                                      **value_columns})
                metadata = SpectralMetadata(
                    source_type='map_values',
                    dimensions=spectral_data.metadata.dimensions,
                    scan_mode=spectral_data.metadata.scan_mode,
                    units=dict(spectral_data.metadata.units or {}),
                    additional_info={
                        'created_from': 'map_generator',
                        'source_dataset': dataset_name,
                        'intervals': [list(iv) for iv in intervals],
                        'integration_intervals': [list(iv) for iv in intervals],
                        'scan_type': scan_type,
                        'background': detect_params.baseline,
                        'bias_step': dx,
                        'noise_floor': noise_floor,
                        'noise_sigma_median': float(np.median(spectrum_sigma))
                        if spectrum_sigma.size else 0.0,
                        'integration_window': max(min_width, 0.0),
                        'windows_widened': widened,
                        'spectrum_columns': columns,
                    },
                    data_type='flat',
                )
                values_name = f"{base_name} - Map Values"
                self._datasets[values_name] = SpectralData(frame, metadata)
                if not self._workflow_mode:
                    self.dataLoaded.emit(values_name)

            if noise_floor > 0:
                logger.info("Map Generator: integrating above a %.1f-sigma noise "
                            "floor (median sigma %.3g)", noise_floor,
                            float(np.median(spectrum_sigma)) if spectrum_sigma.size else 0.0)
            if widened:
                logger.info("Map Generator: %d of %d interval(s) were narrower than "
                            "the %.4g V bias step and were integrated over %.4g V "
                            "instead — the sweep cannot resolve finer than that",
                            widened, len(intervals), dx, min_width)

            task.progress = 1.0
            return {'map_paths': map_paths,
                    'intervals': [list(iv) for iv in intervals],
                    'values_dataset': values_name,
                    'interval_map': interval_map_name,
                    'interval_map_path': interval_map_path,
                    'output_folder': str(folders['root']),
                    'scan_type': scan_type,
                    'n_maps': len(map_paths)}

        except Exception as e:
            logger.error(f"Map generation error: {e}", exc_info=True)
            self.errorOccurred.emit("Map Generator Error", str(e))
            return empty

    @staticmethod
    def _intervals_from_columns(names) -> Optional[list]:
        """``[[lo, hi], …]`` read back out of value-column names, or None.

        Integration writes ``Interval_0.150_0.250`` and the Map Generator
        ``0.150_0.250``; both name the interval the column was integrated
        over, so a table that has lost its metadata — round-tripped through
        CSV, say — can still be stacked into a joined map. All or nothing: a
        partial parse would pair the wrong energies with the wrong columns,
        which is worse than having no energy axis at all.
        """
        import re

        bounds = []
        for name in names:
            text = str(name)
            if text.lower().startswith('interval_'):
                text = text[len('interval_'):]
            match = re.fullmatch(r'(-?\d+(?:\.\d+)?)_(-?\d+(?:\.\d+)?)', text)
            if not match:
                return None
            lo, hi = float(match.group(1)), float(match.group(2))
            bounds.append([min(lo, hi), max(lo, hi)])
        return bounds or None

    def assemble_maps(self, task, flat_dataset_name: str,
                      params: Optional[dict] = None,
                      source_dataset_name: Optional[str] = None,
                      intervals: Optional[list] = None) -> dict:
        """Lay one value per spectrum out on the sample, with its real scale.

        The generic half of the Map Generator: numbers that already exist —
        integrals, peak counts, background coefficients, confinement sizes —
        turned into "show me where". Nothing here searches, corrects or
        integrates; whatever produced the column decides what the map means.

        The scale is the reason this exists next to ``generate_all_maps``,
        which lays the same values out but writes a line scan with no
        physical axis at all, so the file opens in Gwyddion as bare pixels.
        Here the positions come from the spectra the values were measured on
        and every field goes out in metres — the project's export rule, not a
        nicety.

        Parameters
        ----------
        source_dataset_name : str, optional
            The spectra the values came from. A flat table rarely carries its
            own positions, and this is where they come from when it does not;
            failing both, the table's recorded origin is followed.
        intervals : list, optional
            The energy interval each value column covers, in the order the
            columns appear. They are what the joined map's energy axis is
            built on; without them each column is only a name, and the joined
            map is not written.
        """
        params = params or {}
        empty = {'map_paths': [], 'n_maps': 0, 'interval_map': '',
                 'interval_map_path': '', 'interval_map_dataset': None,
                 'scan_type': '', 'columns': []}
        try:
            if flat_dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return empty

            flat_data = self._datasets[flat_dataset_name]
            frame = flat_data.data
            all_columns = [c for c in frame.columns if str(c) != 'Spectrum_Index']
            if not all_columns:
                self.errorOccurred.emit(
                    "Map Assembly",
                    "That dataset has no value columns — it holds only the "
                    "spectrum index.")
                return empty

            # Where the positions come from. The values may live in a table
            # that knows nothing about the sample, so the spectra are the
            # better authority whenever the caller can name them.
            source_data = flat_data
            spatial_name = flat_dataset_name
            if source_dataset_name:
                if source_dataset_name not in self._datasets:
                    self.errorOccurred.emit("Error", "Source dataset not found")
                    return empty
                source_data = self._datasets[source_dataset_name]
                spatial_name = source_dataset_name

            # Intervals pair with the columns by position, so a count that
            # does not match cannot be trusted: the names are tried instead,
            # and failing those the run simply has no energy axis.
            #
            # Cleaned rather than taken as they come: a wire carries whatever
            # the node upstream had, and Integration passes hand-typed
            # intervals through as ``{'lower': …, 'upper': …}`` dicts.
            resolved = (self._clean_intervals(intervals) if intervals
                        else self.dataset_intervals(flat_dataset_name))
            if resolved and len(resolved) != len(all_columns):
                logger.info("Map Assembly: %d interval(s) against %d value "
                            "column(s) — reading the intervals off the column "
                            "names instead", len(resolved), len(all_columns))
                resolved = None
            if not resolved:
                resolved = self._intervals_from_columns(all_columns)

            requested = [name.strip() for name
                         in str(params.get('columns', '') or '').split(',')
                         if name.strip()]
            if requested:
                wanted = {name.lower() for name in requested}
                keep = [i for i, column in enumerate(all_columns)
                        if str(column).lower() in wanted]
                if not keep:
                    self.errorOccurred.emit(
                        "Map Assembly",
                        f"None of {', '.join(requested)} is a value column of "
                        f"{flat_dataset_name}")
                    return empty
            else:
                keep = list(range(len(all_columns)))

            # An interval names the state a map belongs to, which is what the
            # Map Generator's file names say; a column with no interval can
            # only be named after itself.
            value_columns = {}
            for i in keep:
                column = all_columns[i]
                label = (f"{resolved[i][0]:.3f}_{resolved[i][1]:.3f}"
                         if resolved else str(column))
                value_columns[label] = pd.to_numeric(
                    frame[column], errors='coerce').to_numpy(dtype=np.float64)
            paired = [resolved[i] for i in keep] if resolved else None
            if not bool(params.get('joined_map', True)):
                # The per-column maps still carry their interval names; only
                # the stack across them is dropped.
                paired = None

            n_values = int(len(frame))
            metadata = source_data.metadata
            scan_type = self._resolve_scan_type(params.get('scan_type', 'auto'),
                                                metadata)
            dims = getattr(metadata, 'dimensions', None) or ()
            dims = (int(dims[0]), int(dims[1])) if len(dims) >= 2 else (n_values, 1)

            # One column name per spectrum, for the joined map's positions.
            # The spectra name them when they are to hand; a flat table that
            # came from the Map Generator recorded them; otherwise there is
            # nothing to call them but their number.
            columns = None
            if getattr(metadata, 'data_type', '') != 'flat':
                columns = list(source_data.spectra.columns)
            if columns is None or len(columns) != n_values:
                recorded = (getattr(flat_data.metadata, 'additional_info', None)
                            or {}).get('spectrum_columns')
                columns = (list(recorded) if recorded and len(recorded) == n_values
                           else [f"col{i}" for i in range(n_values)])

            logger.info("Map Assembly: %s — %d value(s) over %d spectra, %s "
                        "layout %s, %s", flat_dataset_name, len(value_columns),
                        n_values, scan_type, dims,
                        f"{len(paired)} interval(s)" if paired else "no intervals")

            assembled = self._assemble_value_maps(
                task, base_name=self._extract_clean_base_name(flat_dataset_name),
                file_safe_name=self._sanitize_filename(
                    self._extract_clean_base_name(flat_dataset_name)),
                value_columns=value_columns, intervals=paired,
                source_data=source_data, source_dataset_name=spatial_name,
                scan_type=scan_type, dims=dims, columns=columns,
                folders=self._map_output_folders(flat_dataset_name),
                created_from='map_assembly',
                extra_info={'flat_dataset': flat_dataset_name})
            if assembled['cancelled']:
                return empty

            task.progress = 1.0
            return {'map_paths': assembled['map_paths'],
                    'n_maps': len(assembled['map_paths']),
                    'interval_map': assembled['interval_map'],
                    'interval_map_path': assembled['interval_map_path'],
                    'interval_map_dataset': assembled['interval_map_dataset'],
                    'scan_type': scan_type,
                    'columns': list(value_columns)}

        except Exception as e:
            logger.error(f"Map assembly error: {e}", exc_info=True)
            self.errorOccurred.emit("Map Assembly Error", str(e))
            return empty

    #: Metadata that describes WHERE each spectrum was taken. A tool that
    #: returns one output column per input spectrum must carry these across,
    #: or the result can no longer be mapped onto the sample — a derivative of
    #: a line scan is still that line scan's spectra.
    SPATIAL_KEYS = ('spectrum_meta', 'position_m', 'position_step_m',
                    'spatial_layout')

    @classmethod
    def _carry_spatial_info(cls, metadata, columns=None) -> dict:
        """The spatial keys of ``metadata``, for a derived dataset.

        ``columns`` names the subset of spectra the derived dataset keeps; the
        per-spectrum entries are filtered to match so position i still refers
        to column i.
        """
        info = getattr(metadata, 'additional_info', None) or {}
        carried = {key: info[key] for key in cls.SPATIAL_KEYS if info.get(key) is not None}

        if columns is not None and carried.get('spectrum_meta'):
            wanted = list(columns)
            by_column = {entry.get('column'): entry
                         for entry in carried['spectrum_meta']
                         if isinstance(entry, dict)}
            if all(name in by_column for name in wanted):
                carried['spectrum_meta'] = [by_column[name] for name in wanted]
                # A subset invalidates a whole-line position list.
                carried.pop('position_m', None)
            else:
                carried.pop('spectrum_meta', None)
                carried.pop('position_m', None)
        return carried

    def _line_positions_m(self, spectral_data, _depth: int = 0) -> Optional[np.ndarray]:
        """Distance along a line scan, in metres, one entry per spectrum.

        Read from the per-spectrum locations a loader recorded
        (``spectrum_meta[i]['location_m']``), or a ``position_m`` list. When
        the dataset carries neither — a result whose tool predates the
        metadata being carried across — the search follows its recorded
        source dataset, so a derivative of a line scan still maps onto the
        sample. Returns None when nothing upstream knows either.
        """
        info = getattr(getattr(spectral_data, 'metadata', None),
                       'additional_info', None) or {}

        stored = info.get('position_m')
        if stored and len(stored) > 1:
            try:
                return np.asarray(stored, dtype=np.float64)
            except (TypeError, ValueError):
                pass
        meta = info.get('spectrum_meta') or []
        points = []
        for entry in meta:
            loc = (entry or {}).get('location_m')
            if not loc or len(loc) < 2:
                return self._positions_from_source(spectral_data, _depth)
            try:
                points.append((float(loc[0]), float(loc[1])))
            except (TypeError, ValueError):
                return None
        if len(points) < 2:
            return self._positions_from_source(spectral_data, _depth)

        arr = np.asarray(points, dtype=np.float64)
        steps = np.hypot(np.diff(arr[:, 0]), np.diff(arr[:, 1]))
        return np.concatenate([[0.0], np.cumsum(steps)])

    @staticmethod
    def _spectrum_count(spectral_data) -> Optional[int]:
        """How many spectra a dataset describes, spectral or flat.

        A flat table has one ROW per spectrum and one column per value, so
        reading ``num_spectra`` off it counts the values instead: an
        integration of eight positions over two intervals looks like two
        spectra, and the guard below then refuses the very positions it came
        from.
        """
        if getattr(getattr(spectral_data, 'metadata', None),
                   'data_type', '') == 'flat':
            return getattr(spectral_data, 'num_points', None)
        return getattr(spectral_data, 'num_spectra', None)

    def _positions_from_source(self, spectral_data, depth: int = 0):
        """Follow a derived dataset back to whatever recorded the positions.

        Three keys are tried because three generations of tools recorded the
        provenance under three names: ``original`` (the overlay key), the
        newer ``source_dataset``, and ``original_dataset``, which is what the
        Integration tool writes. Missing the last one is not cosmetic — an
        Integration -> Map Assembly chain then maps a line scan in point
        indices instead of metres, and the export rule says a file must carry
        the real dimensions whenever they are available.

        Bounded so a metadata loop cannot hang the run.
        """
        if depth > 4:
            return None
        info = getattr(getattr(spectral_data, 'metadata', None),
                       'additional_info', None) or {}
        for key in ('original', 'source_dataset', 'original_dataset'):
            parent_name = info.get(key)
            parent = self._datasets.get(parent_name) if parent_name else None
            if parent is None or parent is spectral_data:
                continue
            if self._spectrum_count(parent) != self._spectrum_count(spectral_data):
                continue     # a different set of spectra: its positions are not ours
            found = self._line_positions_m(parent, depth + 1)
            if found is not None:
                logger.info("Positions for the map taken from the source dataset %r",
                            parent_name)
                return found
        return None

    def _line_step_m(self, spectral_data) -> Optional[float]:
        """Mean spacing between line-scan positions, in metres."""
        positions = self._line_positions_m(spectral_data)
        if positions is None or positions[-1] <= 0:
            return None
        return float(positions[-1] / max(1, len(positions) - 1))

    def _map_output_folders(self, dataset_name: str) -> dict:
        """``maps/<dataset>/<format>/`` — one folder per dataset, one per format.

        A run over many intervals writes three files each; dropping 200 maps
        x 3 formats into one flat folder made the results unusable. Grouping
        by dataset keeps one experiment's output together, and by format keeps
        the Gwyddion files apart from the rasters and the raw numbers.
        """
        safe = self._sanitize_filename(self._extract_clean_base_name(dataset_name))
        root = self._ensure_output_dir('maps') / safe
        folders = {'root': root}
        for kind in ('gsf', 'tiff', 'csv'):
            folder = root / kind
            folder.mkdir(parents=True, exist_ok=True)
            folders[kind] = folder
        return folders

    def _save_map_images(self, map_data: np.ndarray, output_base: Path,
                         source_metadata=None, folders: Optional[dict] = None,
                         scale: Optional[dict] = None):
        """Save map data as TIFF and CSV only (no PNG outputs).

        The TIFF keeps the **real float32 values** and carries the physical
        pixel scale when the source dataset recorded its scan geometry, so the
        file opens in Gwyddion with true dimensions and true Z values. It used
        to be normalised to 0–65535 uint16, which threw the physical quantity
        away and made the export unusable for quantitative work.
        """
        from src.utils.field_export import export_field_from_metadata

        info = getattr(source_metadata, 'additional_info', None) or {}
        # Units live on the metadata object, not inside additional_info.
        if getattr(source_metadata, 'units', None) and 'units' not in info:
            info = {**info, 'units': source_metadata.units}

        name = output_base.name
        written = {}

        if scale:
            # An explicit scale (a line scan's real positions, or a
            # bias-versus-position field) beats anything derivable from the
            # source's scan geometry, which describes the spectra rather than
            # the map being written.
            from src.utils.field_export import export_field

            targets = ([(kind, folders[kind] / name) for kind in ('gsf', 'tiff')]
                       if folders else [(None, output_base)])
            for kind, base in targets:
                written.update(export_field(
                    base, np.asarray(map_data),
                    dx=scale.get('dx'), dy=scale.get('dy'),
                    unit=scale.get('unit'), value_unit=scale.get('value_unit'),
                    title=name, axis_note=scale.get('axis_note'),
                    mixed_axes=bool(scale.get('mixed_axes')),
                    x_offset=float(scale.get('x_offset') or 0.0),
                    y_offset=float(scale.get('y_offset') or 0.0),
                    formats=(kind,) if kind else ('gsf', 'tiff'),
                    context=f"generated map {name}"))
        elif folders:
            # One call per format so each lands in its own folder.
            for kind in ('gsf', 'tiff'):
                written.update(export_field_from_metadata(
                    folders[kind] / name, np.asarray(map_data), info=info,
                    formats=(kind,), title=name,
                    context=f"generated map {name}"))
        else:
            written = export_field_from_metadata(
                output_base, np.asarray(map_data), info=info,
                title=name, context=f"generated map {name}")
        logger.info("Map exported: %s", ", ".join(sorted(written.values())))

        # Save as CSV for raw data
        csv_base = (folders['csv'] / name) if folders else output_base
        csv_path = Path(str(csv_base) + '.csv')
        np.savetxt(str(csv_path), map_data, delimiter=',', fmt='%.6e')
        logger.info(f"CSV saved to: {csv_path}")

        # Verify files were created
        for kind, produced in written.items():
            if not Path(produced).exists():
                logger.error("%s file was not created at: %s", kind, produced)
        if not csv_path.exists():
            logger.error(f"CSV file was not created at: {csv_path}")

    def generate_all_maps(self, task, flat_dataset_name: str,
                          scan_type: str = 'auto') -> list:
        """
        Generate spatial maps for ALL value columns in a flat dataset.
        Returns a list of paths to generated maps.

        Parameters:
        -----------
        task : Task
            Task object for cancellation checking
        flat_dataset_name : str
            Name of flat dataset (e.g., integrated data)

        Returns:
        --------
        list of str : Paths to generated map files (TIFF)
        """
        try:
            if flat_dataset_name not in self._datasets:
                raise ValueError("Dataset not found")

            spectral_data = self._datasets[flat_dataset_name]
            data_df = spectral_data.data

            # Get value columns (skip index/x column which is typically first)
            value_columns = [col for col in data_df.columns if col != 'Spectrum_Index']

            if not value_columns:
                raise ValueError("No value columns found in flat dataset")

            generated_maps = []

            for idx, col in enumerate(value_columns):
                if task.cancelled:
                    break

                task.progress = idx / len(value_columns)
                logger.info(f"Generating map {idx+1}/{len(value_columns)} for column: {col}")

                # Generate map for this value index
                map_path = self.generate_map(task, flat_dataset_name, value_index=idx,
                                             scan_type=scan_type)
                if map_path:
                    # The path is a base without extension - TIFF is what we want
                    tiff_path = f"{map_path}.tiff"
                    # Verify the file was actually created
                    from pathlib import Path
                    if Path(tiff_path).exists():
                        generated_maps.append(tiff_path)
                        logger.info(f"Map verified at: {tiff_path}")
                    else:
                        logger.error(f"Map file not found after generation: {tiff_path}")

            logger.info(f"Generated {len(generated_maps)} verified maps from {flat_dataset_name}")
            return generated_maps

        except Exception as e:
            logger.error(f"Error generating all maps: {e}", exc_info=True)
            return []

    # ========================================================================
    # Peak Indexing
    # ========================================================================

    def find_peaks(self, task, dataset_name: str, prominence: float = 0.0,
                  min_distance: int = 5, fwhm_multiplier: float = 1.5) -> dict:
        """
        Find and index peaks in spectral data, returning FWHM-based integration intervals.

        Parameters:
        -----------
        dataset_name : str
            Dataset to analyze
        prominence : float
            Minimum peak prominence. Pass ``0`` (or any non-positive value)
            to use a noise-aware adaptive threshold computed per spectrum;
            this is the recommended default so the same call works across
            measurements with very different signal levels.
        min_distance : int
            Minimum distance between peaks (in indices)
        fwhm_multiplier : float
            Multiplier for FWHM to create integration interval (default 1.5x FWHM)

        Returns:
        --------
        dict with:
            - 'peaks_path': str - Path to peak information CSV
            - 'intervals': list - Non-overlapping intervals [[start, end], ...]
        """
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return {'peaks_path': '', 'intervals': []}

            spectral_data = self._datasets[dataset_name]
            logger.info(f"Finding peaks in {dataset_name}")

            independent_var = spectral_data.independent_var
            spectra = spectral_data.spectra.values
            x_step = np.mean(np.diff(independent_var))

            adaptive = prominence is None or prominence <= 0

            # Debug logging
            logger.info(f"PeakFinder: Dataset has {spectra.shape[1]} spectra, {spectra.shape[0]} points each")
            logger.info(f"PeakFinder: Data range: min={np.nanmin(spectra):.6f}, max={np.nanmax(spectra):.6f}")
            logger.info(f"PeakFinder: X range: {independent_var[0]:.4f} to {independent_var[-1]:.4f}")
            logger.info(
                f"PeakFinder: Prominence mode={'adaptive' if adaptive else 'fixed'} "
                f"(value={prominence}), min_distance={min_distance}"
            )

            # Storage for peak data
            all_peaks = []
            raw_intervals = []  # Store all intervals before merging
            adaptive_values: list = []  # for diagnostic logging

            # Find peaks in each spectrum
            from src.backend.peak_fitting import adaptive_prominence as _adaptive_prominence
            for i, spectrum in enumerate(spectra.T):
                if task.cancelled:
                    return {'peaks_path': '', 'intervals': []}

                if adaptive:
                    spectrum_prominence = _adaptive_prominence(spectrum)
                    adaptive_values.append(spectrum_prominence)
                else:
                    spectrum_prominence = prominence

                peaks, properties = signal.find_peaks(
                    spectrum,
                    prominence=spectrum_prominence,
                    distance=min_distance
                )

                if len(peaks) == 0:
                    continue

                # Calculate FWHM for each peak
                try:
                    widths, width_heights, left_ips, right_ips = signal.peak_widths(
                        spectrum, peaks, rel_height=0.5
                    )
                except Exception as e:
                    logger.warning(f"Could not calculate FWHM for spectrum {i}: {e}")
                    continue

                for j, peak_idx in enumerate(peaks):
                    fwhm_indices = widths[j]
                    fwhm_value = fwhm_indices * x_step
                    peak_position = independent_var[peak_idx]

                    # Calculate interval based on FWHM
                    half_interval = (fwhm_value * fwhm_multiplier) / 2
                    interval_start = peak_position - half_interval
                    interval_end = peak_position + half_interval

                    peak_info = {
                        'spectrum_index': i,
                        'peak_number': j,
                        'position_index': peak_idx,
                        'position_value': peak_position,
                        'height': spectrum[peak_idx],
                        'prominence': properties['prominences'][j],
                        'fwhm_indices': fwhm_indices,
                        'fwhm_value': fwhm_value,
                        'interval_start': interval_start,
                        'interval_end': interval_end
                    }
                    all_peaks.append(peak_info)
                    raw_intervals.append([interval_start, interval_end, peak_position, properties['prominences'][j]])

            if adaptive and adaptive_values:
                vals = np.asarray(adaptive_values, dtype=np.float64)
                logger.info(
                    f"PeakFinder: adaptive prominence per spectrum — "
                    f"median={float(np.median(vals)):.4g}, "
                    f"min={float(vals.min()):.4g}, max={float(vals.max()):.4g}"
                )

            # Merge overlapping intervals and remove duplicates
            merged_intervals = self._merge_peak_intervals(raw_intervals, independent_var)

            # Create user-friendly names using naming convention
            convention_name = self._apply_naming_convention(dataset_name, operation="Peaks")

            # Save peak data with convention-based filename
            peaks_df = pd.DataFrame(all_peaks)
            output_path = self._ensure_output_dir('peaks') / f"{convention_name}.csv"
            peaks_df.to_csv(output_path, index=False)

            # Save intervals as JSON for easy loading
            intervals_path = self._ensure_output_dir('peaks') / f"{convention_name}_intervals.json"
            import json
            with open(intervals_path, 'w') as f:
                json.dump({
                    'intervals': merged_intervals,
                    'source_dataset': dataset_name,
                    'num_peaks_found': len(all_peaks),
                    'num_intervals': len(merged_intervals)
                }, f, indent=2)

            logger.info(f"Peak data saved to {output_path}: {len(all_peaks)} peaks found, {len(merged_intervals)} non-overlapping intervals")

            # Promote the peak table to a real dataset so it shows in the
            # browser and can be captured by workflow dataset-output nodes.
            # (Previously the tool only returned a dict, which also blanked the
            # browser: it was stored as an output-file 'path' and getOutputList
            # then called Path(dict).) position_value is the natural X axis; the
            # remaining numeric metrics become the "spectra" columns.
            peak_dataset = None
            peak_dataset_name = ""
            if not peaks_df.empty:
                ordered = (['position_value']
                           + [c for c in peaks_df.columns if c != 'position_value'])
                ds_df = peaks_df[ordered].apply(pd.to_numeric, errors='coerce')
                try:
                    peak_meta = SpectralMetadata(
                        source_type='peak_table',
                        dimensions=(len(ds_df.columns) - 1, 1),
                        scan_mode='peaks',
                        units={'x': 'position', 'independent': 'position'},
                        # No 'original' key on purpose: this table is not a
                        # spectrum, so it must not be overlaid on the source's
                        # graph window by the derived-dataset router.
                        additional_info={
                            'created_from': 'peak_finder',
                            'source_dataset': dataset_name,
                            'num_peaks': len(peaks_df),
                            'num_intervals': len(merged_intervals),
                            'peaks_path': str(output_path),
                        },
                    )
                    peak_dataset = SpectralData(ds_df, peak_meta)
                    base_name = self._extract_clean_base_name(dataset_name)
                    peak_dataset_name = f"{base_name} - Peaks"
                    self._datasets[peak_dataset_name] = peak_dataset
                    if not self._workflow_mode:
                        self.dataLoaded.emit(peak_dataset_name)
                except (ValueError, TypeError) as e:
                    logger.warning("Peak table could not be promoted to a dataset: %s", e)
                    peak_dataset, peak_dataset_name = None, ""

            return {
                'peaks_path': str(output_path),
                'intervals': merged_intervals,
                'dataset': peak_dataset,          # SpectralData (or None) for workflow capture
                'dataset_name': peak_dataset_name,
            }

        except Exception as e:
            logger.error(f"Peak finding error: {e}", exc_info=True)
            self.errorOccurred.emit("Peak Finding Error", str(e))
            return {'peaks_path': '', 'intervals': []}

    # ========================================================================
    # Confinement Analysis
    # ========================================================================

    def analyze_confinement(self, task, dataset_name: str,
                            params: Optional[dict] = None,
                            fwhm_multiplier: float = 1.5,
                            emit_matrix: bool = True,
                            matrix_column_limit: int = 4096) -> dict:
        """
        Background subtraction and peak detection in a single pass.

        Supersedes Peak Indexing (which had no background handling, search
        window or derivative smoothing) and the baseline half of Curve
        Fitting. Running both together is not a convenience: the height
        threshold is a percentage of the CORRECTED curve's span inside the
        search window, so subtracting the background first is what lets small
        in-gap features clear a threshold the band edges would otherwise
        dominate.

        Parameters:
        -----------
        dataset_name : str
            Dataset to analyse.
        params : dict
            Any field of :class:`src.processing.peak_detection.Params`.
            Unknown keys are ignored so QML and the workflow engine can pass
            their whole parameter map.
        fwhm_multiplier : float
            Integration interval width as a multiple of each peak's FWHM,
            matching the Peak Indexing behaviour that feeds the Integration
            tool.
        emit_matrix : bool
            Build the peak-occupancy dataset. One column per spectrum, so it
            is skipped above ``matrix_column_limit`` spectra unless forced.
        matrix_column_limit : int
            Spectrum count above which the occupancy table is suppressed.

        Returns:
        --------
        dict with the created SpectralData objects (for workflow capture),
        their names, the merged intervals and the CSV paths.
        """
        empty = {'peaks': None, 'peak_matrix': None, 'peak_matrix_binned': None,
                 'peak_matrix_offset': None, 'peak_matrix_binned_offset': None,
                 'corrected': None, 'baseline': None, 'coefficients': None,
                 'peak_count': None, 'intervals': [], 'peaks_path': '',
                 'matrix_path': '', 'binned_matrix_path': '',
                 'offset_matrix_path': '', 'binned_offset_matrix_path': '',
                 'dataset_names': {}}
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return empty

            spectral_data = self._datasets[dataset_name]
            independent_var = np.asarray(spectral_data.independent_var, dtype=np.float64)
            spectra = np.asarray(spectral_data.spectra.values, dtype=np.float64)
            n_samples, n_spectra = spectra.shape

            detect_params = params_from_dict({**CONFINEMENT_DEFAULTS, **(params or {})})
            detect_params.validate()

            # A temperature sets the resolution limit two ways, and both are
            # needed. Binning alone would leave a pair 3 meV apart reported
            # separately whenever they straddle a bin edge, so k_B*T also
            # becomes the minimum separation: peaks closer than that are one
            # feature and only the most prominent survives. This one is the
            # FULL k_B*T — it is the physical resolution limit, unlike the
            # reporting bins, which are half that wide.
            if detect_params.thermal_width > 0 and not detect_params.min_distance:
                detect_params.min_distance = detect_params.thermal_width

            logger.info(
                "ConfinementAnalysis: %s — %d spectra x %d points, background=%s(deg %d), "
                "height=%.3g%% (%s), window=%s..%s",
                dataset_name, n_spectra, n_samples, detect_params.baseline,
                detect_params.baseline_degree, detect_params.height,
                detect_params.height_mode, detect_params.xmin, detect_params.xmax,
            )

            results = analyze_many(
                independent_var, spectra, detect_params,
                should_cancel=lambda: bool(getattr(task, 'cancelled', False)),
            )
            if len(results) < n_spectra:
                logger.info("ConfinementAnalysis cancelled after %d/%d spectra",
                            len(results), n_spectra)
                return empty

            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(dataset_name, operation="Confinement")
            file_safe_name = self._sanitize_filename(base_name)
            peaks_dir = self._ensure_output_dir('peaks')
            columns = list(spectral_data.spectra.columns)
            created: dict = {}

            def _register(suffix: str, frame: pd.DataFrame, metadata: SpectralMetadata):
                name = f"{base_name} - {suffix}"
                try:
                    dataset = SpectralData(frame, metadata)
                except (ValueError, TypeError) as exc:
                    logger.warning("ConfinementAnalysis: '%s' could not be built: %s", name, exc)
                    return None, ""
                self._datasets[name] = dataset
                if not self._workflow_mode:
                    self.dataLoaded.emit(name)
                created[suffix] = name
                return dataset, name

            def _meta(source_type, extra, *, overlay=False, flat=False):
                info = {'created_from': 'confinement_analysis',
                        'source_dataset': dataset_name, **extra}
                if not flat:
                    # Per-spectrum outputs keep the source's positions, so a
                    # corrected line scan can still be mapped onto the sample.
                    info = {**self._carry_spatial_info(spectral_data.metadata), **info}
                if overlay:
                    # Routes the result onto the source's graph window.
                    info['original'] = dataset_name
                return SpectralMetadata(
                    source_type=source_type,
                    dimensions=spectral_data.metadata.dimensions,
                    scan_mode=spectral_data.metadata.scan_mode,
                    units=dict(spectral_data.metadata.units or {}),
                    additional_info=info,
                    data_type='flat' if flat else spectral_data.metadata.data_type,
                )

            # Thermal grouping: k_B*T is the position error bar and the
            # minimum separation, so peaks the experiment cannot tell apart
            # are not reported apart. The reporting bins are half that wide,
            # so peaks that *are* resolvable keep their own bin.
            thermal_width = detect_params.thermal_width
            bin_width = detect_params.bin_width
            edges, bin_centers = (energy_bins(independent_var, bin_width)
                                  if bin_width > 0 else (None, None))
            if bin_width > 0:
                logger.info("ConfinementAnalysis: grouping at T=%.6g K -> kBT=%.6g %s, "
                            "bin width=%.6g %s, %d bins",
                            detect_params.temperature_k, thermal_width,
                            detect_params.x_energy_unit, bin_width,
                            detect_params.x_energy_unit, len(bin_centers))

            settings = {'background': detect_params.baseline,
                        'degree': detect_params.baseline_degree,
                        'basis': detect_params.baseline_basis,
                        'height_percent': detect_params.height,
                        'height_mode': detect_params.height_mode,
                        'direction': detect_params.direction,
                        'temperature_k': detect_params.temperature_k,
                        'kbt': thermal_width,
                        'bin_width': bin_width,
                        'x_energy_unit': detect_params.x_energy_unit}

            # -- 1. peak list -------------------------------------------------
            x_step = float(np.mean(np.diff(independent_var))) if n_samples > 1 else 1.0
            rows, raw_intervals = [], []
            for i, result in enumerate(results):
                if not result.peaks:
                    continue

                if edges is not None:
                    kept = [(pk, int(b)) for b, pk, _ in group_peaks_by_bin(result.peaks, edges)]
                else:
                    kept = [(pk, -1) for pk in result.peaks]

                widths = _peak_fwhm(result, [pk.index for pk, _ in kept])
                for j, ((pk, bin_index), fwhm_idx) in enumerate(zip(kept, widths)):
                    fwhm_value = float(fwhm_idx) * abs(x_step)
                    half = (fwhm_value * float(fwhm_multiplier)) / 2.0
                    row = {
                        'spectrum_index': i,
                        'spectrum_name': columns[i] if i < len(columns) else f"col{i}",
                        'peak_number': j,
                        'position_index': pk.index,
                        'position_value': pk.x,
                        'height': pk.y,
                        'height_corrected': pk.y_corrected,
                        'prominence': pk.prominence,
                        'fwhm_indices': float(fwhm_idx),
                        'fwhm_value': fwhm_value,
                        'interval_start': pk.x - half,
                        'interval_end': pk.x + half,
                    }
                    if edges is not None:
                        row['bin_index'] = bin_index
                        row['bin_center'] = float(bin_centers[bin_index])
                    rows.append(row)
                    raw_intervals.append([pk.x - half, pk.x + half, pk.x, pk.prominence])

            peaks_df = pd.DataFrame(rows)
            peaks_path = peaks_dir / f"{convention_name}.csv"
            peaks_df.to_csv(peaks_path, index=False)

            # Merged now (not at the end) so every dataset this run registers
            # carries them: that is how the Map Generator reads the intervals
            # of a previous analysis straight out of the project.
            merged_intervals = self._merge_peak_intervals(raw_intervals, independent_var)
            settings['integration_intervals'] = [list(iv) for iv in merged_intervals]

            if not peaks_df.empty:
                ordered = ['position_value'] + [c for c in peaks_df.columns
                                                if c not in ('position_value', 'spectrum_name')]
                _register('Peaks', peaks_df[ordered].apply(pd.to_numeric, errors='coerce'),
                          _meta('peak_table', {'num_peaks': len(peaks_df), **settings}))

            # -- 2. occupancy matrices ----------------------------------------
            # Two tables, because they answer different questions. The
            # full-resolution one keeps every peak on the measured energy
            # axis; the binned one is the confinement table, coarse enough
            # that regions can be compared column by column. Emitting only
            # the binned version would throw away positions that the raw
            # axis still resolves, so both are written when a temperature is
            # set, each to its own CSV.
            matrix_path = ''
            binned_matrix_path = ''
            offset_matrix_path = ''
            binned_offset_matrix_path = ''

            def _emit_matrix(suffix: str, matrix: np.ndarray, axis_values, filename: str,
                             extra: dict):
                frame = pd.DataFrame(matrix, columns=columns)
                frame.insert(0, spectral_data.independent_var_name, axis_values)
                path = peaks_dir / filename
                _write_occupancy_csv(frame, columns, path)
                marked = int(np.isfinite(matrix).sum())
                _register(suffix, frame,
                          _meta('peak_matrix',
                                {'total_peaks': marked,
                                 'n_rows': int(len(axis_values)),
                                 **extra, **settings}))
                return str(path)

            if emit_matrix and n_spectra > int(matrix_column_limit):
                logger.warning(
                    "ConfinementAnalysis: %d spectra exceeds the %d-column limit; "
                    "skipping the occupancy tables (peak counts are still emitted)",
                    n_spectra, int(matrix_column_limit))
            elif emit_matrix:
                matrix_path = _emit_matrix(
                    'Peak Matrix', peak_matrix(n_samples, results), independent_var,
                    f"{file_safe_name}_PeakMatrix.csv", {'binned': False})

                # Same marks, but each column carries its own 1-based number
                # instead of a flat 1. Plotting the 1/blank table stacks every
                # spectrum on one line; numbering offsets them onto separate
                # rows so the columns can be told apart.
                offset_matrix_path = _emit_matrix(
                    'Peak Matrix (offset)',
                    peak_matrix(n_samples, results, mark_by_column=True),
                    independent_var, f"{file_safe_name}_PeakMatrix_offset.csv",
                    {'binned': False, 'offset': True})

                if edges is not None:
                    binned_matrix_path = _emit_matrix(
                        'Peak Matrix (binned)', binned_peak_matrix(results, edges),
                        bin_centers, f"{file_safe_name}_PeakMatrix_binned.csv",
                        {'binned': True, 'n_bins': int(len(bin_centers))})

                    binned_offset_matrix_path = _emit_matrix(
                        'Peak Matrix (binned, offset)',
                        binned_peak_matrix(results, edges, mark_by_column=True),
                        bin_centers, f"{file_safe_name}_PeakMatrix_binned_offset.csv",
                        {'binned': True, 'offset': True, 'n_bins': int(len(bin_centers))})

            # -- 3. corrected + background ------------------------------------
            # raw minus background, NOT the smoothed curve the search ran on.
            # Smoothing is a detection aid and is on by default, so folding it
            # into an exported dataset would quietly alter the user's data;
            # this also matches what Curve Fitting's 'corrected' output means.
            corrected = np.array([_expand(r.y_raw - r.baseline, r.idx, n_samples)
                                  if r.baseline.size == r.y_raw.size
                                  else _expand(r.y_raw, r.idx, n_samples)
                                  for r in results]).T
            corrected_df = pd.DataFrame(corrected, columns=columns)
            corrected_df.insert(0, spectral_data.independent_var_name, independent_var)
            _register('Background Corrected', corrected_df,
                      _meta(spectral_data.metadata.source_type, settings, overlay=True))

            if detect_params.baseline != 'none':
                background = np.array([_expand(r.baseline, r.idx, n_samples) for r in results]).T
                background_df = pd.DataFrame(background, columns=columns)
                background_df.insert(0, spectral_data.independent_var_name, independent_var)
                _register('Background', background_df,
                          _meta(spectral_data.metadata.source_type, settings, overlay=True))

            # -- 4. flat outputs for the Map Generator -------------------------
            if detect_params.baseline in ('poly', 'poly-iter'):
                degree = int(detect_params.baseline_degree)
                basis = detect_params.baseline_basis
                names = coefficient_names(degree, basis)
                coeff_rows = []
                for i, result in enumerate(results):
                    coeffs = _fit_coefficients(result, degree, basis)
                    coeff_rows.append({'Spectrum_Index': i,
                                       **{name: coeffs[p] for p, name in enumerate(names)}})
                _register('Fit Coefficients', pd.DataFrame(coeff_rows),
                          _meta('fit_coefficients',
                                {'coefficient_columns': names, 'basis': basis, **settings},
                                flat=True))

            counts_df = pd.DataFrame({
                'Spectrum_Index': np.arange(len(results)),
                'Peak_Count': [len(r.peaks) for r in results],
            })
            _register('Peak Count', counts_df,
                      _meta('peak_count', settings, flat=True))

            logger.info("ConfinementAnalysis: %d peaks over %d spectra, %d intervals; created %s",
                        len(peaks_df), n_spectra, len(merged_intervals),
                        ", ".join(created.values()) or "nothing")

            return {
                'peaks': self._datasets.get(created.get('Peaks', '')),
                'peak_matrix': self._datasets.get(created.get('Peak Matrix', '')),
                'peak_matrix_binned': self._datasets.get(created.get('Peak Matrix (binned)', '')),
                'peak_matrix_offset': self._datasets.get(created.get('Peak Matrix (offset)', '')),
                'peak_matrix_binned_offset': self._datasets.get(
                    created.get('Peak Matrix (binned, offset)', '')),
                'corrected': self._datasets.get(created.get('Background Corrected', '')),
                'baseline': self._datasets.get(created.get('Background', '')),
                'coefficients': self._datasets.get(created.get('Fit Coefficients', '')),
                'peak_count': self._datasets.get(created.get('Peak Count', '')),
                'intervals': merged_intervals,
                'peaks_path': str(peaks_path),
                'matrix_path': matrix_path,
                'binned_matrix_path': binned_matrix_path,
                'offset_matrix_path': offset_matrix_path,
                'binned_offset_matrix_path': binned_offset_matrix_path,
                'dataset_names': created,
            }

        except Exception as e:
            logger.error(f"Confinement analysis error: {e}", exc_info=True)
            self.errorOccurred.emit("Confinement Analysis Error", str(e))
            return empty

    # ========================================================================
    # Confinement Designer
    # ========================================================================

    #: Defaults for one designer run, applied under the caller's own values.
    #: The search range and tolerance are the Tk app's; the detection knobs
    #: come from CONFINEMENT_DEFAULTS, so the designer and Confinement
    #: Analysis see the same peaks.
    DESIGNER_DEFAULTS = {
        'spectrum_index': 0,
        'carrier': 'electrons',
        'meff_e': '0.067',
        'meff_h': '0.45',
        'ndim': '1D',
        'coords': 'cartesian',
        'sym': 'orthorhombic',
        'Lmin': 1.0,
        'Lmax': 20.0,
        'tol': 5.0,
        'maxsol': 6,
        'match': 'delta_e',
        'priority': 'uniform',
        'split_e': 0.0,
        'split_h': 0.0,
        'min_abs_V': 0.0,
        'pair_tol_nm': 1.0,
        'sort': 'rrmse',
    }

    @staticmethod
    def _designer_carriers(params: dict, peaks) -> list:
        """The searches to run, one per carrier asked for.

        Each carries its own targets and its own list of effective masses:
        the same energy with a heavier carrier asks for a different well, so
        electron and hole are separate searches that only the geometry ties
        back together.
        """
        from src.physics.designer import (CARRIER_BOTH, CARRIER_ELECTRON,
                                          CARRIER_HOLE, parse_masses)

        mode = str(params.get('carrier', CARRIER_ELECTRON))
        carriers = []
        if mode in (CARRIER_ELECTRON, CARRIER_BOTH):
            carriers.append({'carrier': 'e', 'label': 'electron',
                             'Et': np.asarray(peaks.electron_eV, dtype=float),
                             'meffs': parse_masses(params.get('meff_e', '0.067'),
                                                   'm*_e')})
        if mode in (CARRIER_HOLE, CARRIER_BOTH):
            carriers.append({'carrier': 'h', 'label': 'hole',
                             'Et': np.asarray(peaks.hole_eV, dtype=float),
                             'meffs': parse_masses(params.get('meff_h', '0.45'),
                                                   'm*_h')})
        return carriers

    @staticmethod
    def _designer_candidate(sol: dict, index: int) -> dict:
        """One candidate as plain numbers, for QML and for the plot.

        Everything the panel and the figure need travels in this map, so
        neither has to reach back into a Python-side cache that a second run
        would have replaced underneath them.
        """
        from src.physics.pairing import confinement_size_nm

        matches = sol.get('matches') or []
        targets = [float(m['target_E']) for m in matches]
        computed = [float(m['computed_E']) for m in matches]
        errors = [((c - t) / t * 100.0) if t else 0.0
                  for t, c in zip(targets, computed)]
        hole = sol.get('pair_hole')

        out = {
            'index': int(index),
            'dims_nm': [float(d) for d in sol.get('dims', ())],
            'size_nm': float(confinement_size_nm(sol, sol.get('meff'))),
            'rrmse': float(sol.get('RRMSE', float('nan'))),
            'rrmse_de': float(sol.get('RRMSE_dE', sol.get('RRMSE', float('nan')))),
            'meff': float(sol.get('meff', 0.0)),
            'carrier': str(sol.get('carrier', 'e')),
            'offset_eV': float(sol.get('offset', 0.0) or 0.0),
            'ndim': str(sol.get('ndim', '')),
            'coords': str(sol.get('coords', '')),
            'sym': str(sol.get('sym', '')),
            'targets': targets,
            'computed': computed,
            'errors_pct': errors,
            'qn': [[int(q) for q in (m.get('qn') or ())] for m in matches],
        }
        if hole:
            out['hole'] = ToolImplementations._designer_candidate(hole, index)
            out['pair_score'] = float(sol.get('pair_score', float('nan')))
            out['pair_mismatch_nm'] = float(sol.get('pair_mismatch_nm', 0.0))
        return out

    def design_confinement(self, task, dataset_name: str,
                           params: Optional[dict] = None) -> dict:
        """Which well produces this spectrum's ladder of levels?

        One spectrum in, candidate geometries out. The peaks come from the
        same engine Confinement Analysis uses, are split into the electron
        and hole branches by the sign of the bias, and each branch is
        searched separately; with both carriers asked for, the two are paired
        by geometry, because it is one well that confines them both.

        Slow enough to belong on the worker — a search is ~0.25 s per
        candidate — and cancellable between carriers and masses.
        """
        empty = {'ok': False, 'candidates': [], 'pairs': 0, 'edges': None,
                 'peaks': {}, 'error': '', 'dataset': dataset_name,
                 'spectrum_index': 0}
        try:
            from src.physics.branches import DidvCurve, analyze_curve
            from src.physics.designer import CARRIER_BOTH, Designer
            from src.physics.pairing import edges_from_solutions, pair_candidates

            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return {**empty, 'error': "Dataset not found"}

            params = {**self.DESIGNER_DEFAULTS, **(params or {})}
            spectral_data = self._datasets[dataset_name]
            spectra = spectral_data.spectra
            n_spectra = int(spectra.shape[1])
            index = max(0, min(int(params.get('spectrum_index', 0)), n_spectra - 1))

            x = np.asarray(spectral_data.independent_var, dtype=np.float64)
            y = np.asarray(spectra.values[:, index], dtype=np.float64)
            column = str(spectra.columns[index])

            peaks = analyze_curve(
                DidvCurve(x=x, y=y, name=column), params,
                min_abs_V=float(params.get('min_abs_V', 0.0)),
                split_e=float(params.get('split_e', 0.0)),
                split_h=float(params.get('split_h', 0.0)))

            carriers = self._designer_carriers(params, peaks)
            # Two targets are the minimum that means anything: one level is
            # explained by any size at all, so the fit would be a tautology.
            for carrier in carriers:
                if carrier['Et'].size < 2:
                    return {**empty,
                            'error': (f"Only {carrier['Et'].size} peak(s) on the "
                                      f"{carrier['label']} branch — a single level "
                                      f"is explained by any size."),
                            'peaks': self._designer_peak_summary(peaks, column),
                            'spectrum_index': index}

            search = {'ndim': str(params['ndim']), 'coords': str(params['coords']),
                      'sym': str(params['sym']),
                      'fixed': dict(params.get('fixed')
                                    or {'d1': None, 'd2': None, 'd3': None}),
                      'Lmin': float(params['Lmin']), 'Lmax': float(params['Lmax']),
                      'tol': float(params['tol']), 'maxsol': int(params['maxsol']),
                      'priority': str(params['priority']),
                      'match': str(params['match'])}

            designer = Designer(seed=params.get('seed'))
            by_carrier = {}
            for carrier in carriers:
                if getattr(task, 'cancelled', False):
                    logger.info("Confinement Designer cancelled")
                    return empty
                task.progress = 0.1
                found = designer.search_carrier(search, carrier)
                # Aliases before anything else: a well k times larger matches
                # the same targets with the quantum numbers multiplied by k,
                # and which one the optimiser lands on is the random seed.
                #
                # Deduplicated AFTER the reduction, not before: the search
                # dedupes the geometries it found, and two of those collapse
                # onto one well the moment the aliases are folded in. Without
                # this the list showed the same candidate several times.
                reduced = []
                for sol in found:
                    primary = designer.primary_alias(
                        sol, {**search, 'Et': carrier['Et'],
                              'meff': sol.get('meff')})
                    if not any(abs(primary['meff'] - kept['meff']) < 1e-9
                               and designer.is_duplicate(primary, [kept])
                               for kept in reduced):
                        reduced.append(primary)
                by_carrier[carrier['carrier']] = reduced

            paired = str(params.get('carrier')) == CARRIER_BOTH
            pairs = []
            if paired:
                pairs = pair_candidates(by_carrier.get('e', []),
                                        by_carrier.get('h', []),
                                        tol_nm=float(params['pair_tol_nm']))
                # The pair's own error rides on the electron candidate, which
                # is what the list shows and sorts by.
                for pair in pairs:
                    pair['electron']['pair_hole'] = pair['hole']
                    pair['electron']['pair_score'] = pair['score']
                    pair['electron']['pair_mismatch_nm'] = pair['mismatch_nm']
                solutions = [pair['electron'] for pair in pairs]
            else:
                solutions = [sol for sols in by_carrier.values() for sol in sols]

            solutions = designer.sort_solutions(
                solutions, str(params.get('sort', 'rrmse')), paired=bool(pairs))

            edges = edges_from_solutions(by_carrier, pairs,
                                         float(params.get('split_e', 0.0)),
                                         float(params.get('split_h', 0.0)))

            task.progress = 1.0
            logger.info("Confinement Designer: %s[%d] — %d candidate(s)%s",
                        dataset_name, index, len(solutions),
                        f", {len(pairs)} pair(s)" if paired else "")
            return {
                'ok': bool(solutions),
                'candidates': [self._designer_candidate(sol, i)
                               for i, sol in enumerate(solutions)],
                'pairs': len(pairs),
                'edges': edges,
                'peaks': self._designer_peak_summary(peaks, column),
                'error': "" if solutions else "No candidate fits within the tolerance.",
                'dataset': dataset_name,
                'spectrum_index': index,
            }

        except ValueError as exc:
            # A bad mass list or an empty target field: the user's to fix, and
            # naming it is the whole point of the message.
            logger.info("Confinement Designer: %s", exc)
            return {**empty, 'error': str(exc)}
        except Exception as e:
            logger.error(f"Confinement designer error: {e}", exc_info=True)
            self.errorOccurred.emit("Confinement Designer Error", str(e))
            return {**empty, 'error': str(e)}

    @staticmethod
    def _designer_peak_summary(peaks, column: str) -> dict:
        """What the search was given, for the panel to show alongside it."""
        return {
            'column': column,
            'electron_eV': [float(v) for v in peaks.electron_eV],
            'hole_eV': [float(v) for v in peaks.hole_eV],
            'peaks_V': [float(v) for v in peaks.peaks_V],
            'in_gap_V': [float(v) for v in peaks.in_gap_V],
            'total': int(peaks.total),
        }

    # ========================================================================
    # Line Scan Designer
    # ========================================================================

    #: On top of DESIGNER_DEFAULTS, for a whole line rather than one
    #: spectrum. ``max_rrmse`` doubles as the search tolerance, so a position
    #: whose best candidate is worse than this is reported as having no
    #: confinement rather than being given a number anyway.
    LINE_DESIGNER_DEFAULTS = {
        'maxsol': 1,
        'group_tol_nm': 1.0,
        'max_rrmse': 5.0,
    }

    #: Columns the table always has, in this order. Everything numeric is
    #: NaN where a position has no confinement — never 0, which would map as
    #: a very small well and read as a real measurement.
    LINE_DESIGNER_COLUMNS = ('point_index', 'position_m', 'size_nm',
                             'rrmse_pct', 'group', 'meff', 'n_peaks')

    def _line_scan_from_dataset(self, spectral_data, dataset_name: str):
        """A :class:`~src.physics.line_scan.LineScan` over a dataset's spectra.

        The step comes from the loader's own positions, so the map's axis is
        distance rather than a column number; without one the axis falls back
        to the point index, which is honest rather than invented.
        """
        from src.physics.line_scan import LineScan

        step_m = self._line_step_m(spectral_data)
        return LineScan(
            x=np.asarray(spectral_data.independent_var, dtype=np.float64),
            ys=np.asarray(spectral_data.spectra.values, dtype=np.float64),
            names=[str(c) for c in spectral_data.spectra.columns],
            path=dataset_name,
            step_nm=(float(step_m) * 1e9) if step_m else None)

    def design_line_scan(self, task, dataset_name: str,
                         params: Optional[dict] = None) -> dict:
        """One confinement search per position along a line.

        The single-spectrum question repeated point by point — and **not
        converging is an answer**. On an arbitrary scan most positions fall
        outside the confining structure, and a map where every point has a
        size is a map that lies; those come back as NaN with the reason
        recorded beside them.

        The output is a flat table, one row per position, because that is
        what the rest of the project can already use: Map Assembly lays any
        of its columns out on the sample, and the Hyperspectral tab opens it.
        """
        empty = {'ok': False, 'dataset': '', 'map_paths': [], 'groups': [],
                 'summary': {}, 'error': '', 'points': []}
        try:
            from src.physics.branches import analyze_curve
            from src.physics.designer import (CARRIER_BOTH, CARRIER_HOLE,
                                              MATCH_ABSOLUTE, Designer)
            from src.physics.line_scan import (NO_PAIR, analyze_line_scan,
                                               group_by_size,
                                               segments_along_line, summarize)
            from src.physics.pairing import confinement_size_nm, pair_candidates

            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return {**empty, 'error': "Dataset not found"}

            params = {**self.DESIGNER_DEFAULTS, **self.LINE_DESIGNER_DEFAULTS,
                      **(params or {})}
            spectral_data = self._datasets[dataset_name]
            scan = self._line_scan_from_dataset(spectral_data, dataset_name)

            # A dummy peak table decides nothing here; the carriers do, and
            # they are rebuilt per position because each spectrum has its own
            # peaks. This only reads the mass lists and the mode.
            from src.physics.branches import DidvPeaks
            carriers = self._designer_carriers(
                params, DidvPeaks(electron_eV=[], hole_eV=[], peaks_V=[]))
            if not carriers:
                return {**empty, 'error': "No carrier selected"}
            paired = str(params.get('carrier')) == CARRIER_BOTH
            hole_first = str(params.get('carrier')) == CARRIER_HOLE
            primary = carriers[0]

            search = {'ndim': str(params['ndim']), 'coords': str(params['coords']),
                      'sym': str(params['sym']),
                      'fixed': dict(params.get('fixed')
                                    or {'d1': None, 'd2': None, 'd3': None}),
                      'Lmin': float(params['Lmin']), 'Lmax': float(params['Lmax']),
                      'tol': float(params['max_rrmse']),
                      'maxsol': int(params['maxsol']),
                      'priority': str(params['priority']),
                      'match': str(params['match'])}
            designer = Designer(seed=params.get('seed'))

            split_e = float(params.get('split_e', 0.0) or 0.0)
            split_h = float(params.get('split_h', 0.0) or 0.0)
            # In delta-E only the differences count, so a lone peak defines no
            # ladder; in absolute energies one level is already a constraint.
            min_peaks = 1 if search['match'] == MATCH_ABSOLUTE else 2

            def targets_fn(curve):
                peaks = analyze_curve(curve, params, split_e=split_e,
                                      split_h=split_h,
                                      min_abs_V=float(params.get('min_abs_V', 0.0)))
                branch = peaks.hole_eV if hole_first else peaks.electron_eV
                return {'targets': branch, 'peaks': peaks,
                        'n_peaks': len(peaks.peaks_V)}

            def _candidates(targets, carrier):
                found = []
                for meff in carrier['meffs']:
                    p = {**search, 'Et': np.asarray(targets, dtype=float),
                         'meff': meff, 'carrier': carrier['carrier']}
                    found.extend(designer.primary_alias(sol, p)
                                 for sol in designer.find_solutions(p))
                return found

            def search_fn(found):
                solutions = _candidates(found['targets'], primary)
                if not paired:
                    return solutions

                # Both carriers: the position only counts when the two close
                # on the same well — the pair's requirement, point by point.
                hole_targets = found['peaks'].hole_eV
                if len(hole_targets) < 2:
                    found['reason'] = NO_PAIR
                    return []
                holes = _candidates(hole_targets, carriers[-1])
                pairs = pair_candidates(solutions, holes,
                                        tol_nm=float(params['pair_tol_nm']),
                                        max_pairs=int(params['maxsol']))
                if not pairs:
                    found['reason'] = NO_PAIR
                    return []
                found['hole_size_nm'] = confinement_size_nm(
                    pairs[0]['hole'], pairs[0]['hole'].get('meff'))
                found['mismatch_nm'] = pairs[0]['mismatch_nm']
                return [pair['electron'] for pair in pairs]

            def progress(index, total):
                task.progress = index / max(1, total)
                return not bool(getattr(task, 'cancelled', False))

            logger.info("Line Scan Designer: %s — %d position(s), %s/%s, "
                        "match %s, carrier %s", dataset_name, scan.n_points,
                        search['ndim'], search['coords'], search['match'],
                        params.get('carrier'))

            results = analyze_line_scan(
                scan, targets_fn, search_fn,
                size_fn=lambda sol: confinement_size_nm(sol, sol.get('meff')),
                min_peaks=min_peaks, max_rrmse=float(params['max_rrmse']),
                progress=progress)

            groups = group_by_size(results, float(params['group_tol_nm']))
            table_name = self._register_line_scan_table(
                results, dataset_name, spectral_data, params)

            # The size map, laid out by the same node any other per-spectrum
            # column goes through — no second export path to keep in step.
            assembled = self.assemble_maps(
                task, table_name, params={'scan_type': 'line',
                                          'columns': 'size_nm',
                                          'joined_map': False},
                source_dataset_name=dataset_name)

            task.progress = 1.0
            return {
                'ok': True,
                'dataset': table_name,
                'map_paths': assembled.get('map_paths', []),
                'groups': [{k: v for k, v in group.items()} for group in groups],
                'summary': summarize(results),
                'points': [self._line_point_row(r) for r in results],
                # The spatial reading: where each domain starts and ends,
                # with the empty stretches between them, which are part of
                # the answer rather than gaps in it.
                'segments': [{'group': (-1 if seg['group'] is None
                                        else int(seg['group'])),
                              'start': float(seg['start']),
                              'end': float(seg['end']),
                              'count': int(seg['count'])}
                             for seg in segments_along_line(results)],
                'error': '',
            }

        except ValueError as exc:
            logger.info("Line Scan Designer: %s", exc)
            return {**empty, 'error': str(exc)}
        except Exception as e:
            logger.error(f"Line scan designer error: {e}", exc_info=True)
            self.errorOccurred.emit("Line Scan Designer Error", str(e))
            return {**empty, 'error': str(e)}

    @staticmethod
    def _line_point_row(point) -> dict:
        """One position as plain numbers, for QML and for the strip plot."""
        def _number(value):
            return float(value) if value is not None else float('nan')

        return {
            'point_index': int(point.index),
            'position_nm': float(point.position),
            'size_nm': _number(point.size_nm),
            'rrmse_pct': _number(point.rrmse),
            'group': (int(point.group) if point.group is not None else -1),
            'n_peaks': int(point.n_peaks),
            'reason': str(point.reason or ''),
            'converged': bool(point.converged),
        }

    def _register_line_scan_table(self, results, dataset_name: str,
                                  spectral_data, params: dict) -> str:
        """The run as a flat table, one row per position.

        Flat because the rest of the project consumes flat data: every column
        is immediately a map, and ``group`` is an integer for the same reason
        — a categorical string cannot be plotted or mapped, an integer can.

        Nothing that failed to converge is written as 0. NaN is an empty cell
        in CSV, is skipped by plots and masked by the colour strip; 0 would
        map as a very small well and read as a real measurement.
        """
        positions_m = self._line_positions_m(spectral_data)
        n_dims = max((len(r.dims_nm) for r in results), default=0)
        nan = float('nan')

        frame = pd.DataFrame({
            'point_index': [r.index for r in results],
            'position_m': [float(positions_m[r.index])
                           if positions_m is not None and r.index < len(positions_m)
                           else nan for r in results],
            'size_nm': [r.size_nm if r.size_nm is not None else nan for r in results],
            'rrmse_pct': [r.rrmse if r.rrmse is not None else nan for r in results],
            'group': [float(r.group) if r.group is not None else nan for r in results],
            'meff': [r.meff if r.meff is not None else nan for r in results],
            'n_peaks': [r.n_peaks for r in results],
        })
        for d in range(n_dims):
            frame[f'dim_{d + 1}_nm'] = [
                float(r.dims_nm[d]) if len(r.dims_nm) > d else nan for r in results]
        if any(r.hole_size_nm is not None for r in results):
            frame['hole_size_nm'] = [r.hole_size_nm if r.hole_size_nm is not None
                                     else nan for r in results]
            frame['mismatch_nm'] = [r.mismatch_nm if r.mismatch_nm is not None
                                    else nan for r in results]
        # The only string column, and the only place a reason appears.
        frame['reason'] = [r.reason or '' for r in results]

        base_name = self._extract_clean_base_name(dataset_name)
        table_name = f"{base_name} - Confinement"
        metadata = SpectralMetadata(
            source_type='confinement_line',
            dimensions=spectral_data.metadata.dimensions,
            scan_mode=spectral_data.metadata.scan_mode,
            units={'independent': 'Index', 'dependent': 'Confinement size (nm)'},
            additional_info={
                'created_from': 'line_scan_designer',
                'source_dataset': dataset_name,
                'original_dataset': dataset_name,
                'ndim': params.get('ndim'),
                'coords': params.get('coords'),
                'match': params.get('match'),
                'carrier': params.get('carrier'),
                'group_tol_nm': float(params.get('group_tol_nm', 1.0)),
                'max_rrmse': float(params.get('max_rrmse', 0.0)),
                **self._carry_spatial_info(spectral_data.metadata),
            },
            data_type='flat',
        )
        self._datasets[table_name] = SpectralData(frame, metadata)

        path = self._ensure_output_dir('confinement') / (
            self._sanitize_filename(table_name) + '.csv')
        frame.to_csv(path, index=False)
        logger.info("Line Scan Designer: %d position(s) -> %s", len(frame), path)

        if not self._workflow_mode:
            self.dataLoaded.emit(table_name)
        return table_name

    # ========================================================================
    # Direct solvers
    # ========================================================================

    #: A quantum well solved numerically, rather than searched for.
    WELL_SOLVER_DEFAULTS = {
        'L_nm': 10.0,
        'N': 800,
        'n_states': 8,
        'meff': 0.067,
        'V0_eV': 0.0,          # 0 = infinite barrier: the box walls confine
        'bc': 'dirichlet',
    }

    #: A quantum dot solved numerically. ``channels`` is l for the sphere and
    #: |m| for the disc — how many angular-momentum ladders to open.
    DOT_SOLVER_DEFAULTS = {
        'model': 'spherical',
        'R_nm': 5.0,
        'Lz_nm': 3.0,
        'hw_xy_meV': 30.0,
        'hw_z_meV': 100.0,
        'meff': 0.067,
        'V0_eV': 0.0,
        'channels': 3,
        'n_per_channel': 4,
        'N': 800,
        'state_index': 0,
        'broadening_eV': 0.005,
        'charging_eV': 0.0,
    }

    @staticmethod
    def _solver_spec(candidate: Optional[dict]):
        """A :class:`SolutionSpec` from a designer candidate map, or None.

        The bridge between the two halves of the tool: the designer produces
        candidates as plain maps for QML, and the solvers want a spec.
        """
        from src.physics.solution_spec import spec_from_designer

        candidate = dict(candidate or {})
        if not candidate.get('dims_nm'):
            return None
        solution = {
            'ndim': candidate.get('ndim', '1D'),
            'coords': candidate.get('coords', 'cartesian'),
            'dims': list(candidate['dims_nm']),
            'offset': candidate.get('offset_eV', 0.0),
            'RRMSE': candidate.get('rrmse'),
            'sym': candidate.get('sym', ''),
            'match': candidate.get('match', ''),
            'matches': [{'computed_E': value, 'qn': qn}
                        for value, qn in zip(candidate.get('computed') or [],
                                             candidate.get('qn') or [])],
        }
        return spec_from_designer(solution, float(candidate.get('meff', 0.067)),
                                  candidate.get('targets') or [],
                                  V0_eV=candidate.get('V0_eV'))

    def describe_candidate(self, candidate: Optional[dict]) -> dict:
        """What a candidate is, and which solver could simulate it.

        ``solver`` is ``"well"``, ``"dot"`` or ``""`` — and the empty answer
        is a real one: a 2D or 3D candidate is a geometry neither solver
        builds, and offering to simulate it would mean simulating something
        else.
        """
        from src.physics.solvers import (can_simulate, dot_from_spec,
                                         states_needed, well_from_spec)

        blank = {'ok': False, 'solver': '', 'model': '', 'label': '',
                 'params': {}, 'error': ''}
        try:
            spec = self._solver_spec(candidate)
            if spec is None:
                return {**blank, 'error': "That candidate has no geometry."}

            solver = can_simulate(spec)
            if not solver:
                return {**blank, 'model': spec.model, 'label': spec.label(),
                        'error': (f"{spec.label()} is a {spec.ndim}D geometry — "
                                  f"no solver here builds one.")}

            if solver == "well":
                args = well_from_spec(spec)
                params = {'L_nm': args['L_nm'], 'meff': args['meff'],
                          'n_states': args['n_states'],
                          'V0_eV': 0.0 if spec.infinite_barrier
                                   else abs(spec.V0_eV),
                          'bc': args['bc']}
            else:
                args = dot_from_spec(spec)
                dims = list(args['dims_nm']) + [0.0, 0.0]
                params = {'model': spec.model.replace('dot_', ''),
                          'meff': args['meff'],
                          'channels': args['channels'],
                          'V0_eV': abs(spec.V0_eV or 0.0),
                          'R_nm': dims[0], 'Lz_nm': dims[1],
                          'hw_xy_meV': dims[0], 'hw_z_meV': dims[1],
                          'n_states': states_needed(spec)}

            return {'ok': True, 'solver': solver, 'model': spec.model,
                    'label': spec.label(), 'params': params,
                    'targets': [float(t) for t in spec.targets_eV],
                    'error': ''}
        except Exception as exc:
            logger.error("describe_candidate failed: %s", exc, exc_info=True)
            return {**blank, 'error': str(exc)}

    def solve_quantum_well(self, params: Optional[dict] = None) -> dict:
        """Solve one 1-D well on a grid and report its levels.

        Numerical where the designer is analytical: this is how an alias of
        the arithmetic is told from a well that really produces those levels.
        Milliseconds at any sensible grid size, so it runs where it is called
        from rather than going to the worker.
        """
        from src.physics.features import SegmentFeature1D
        from src.physics.solvers import compare_with_targets, solve_well_1d

        blank = {'ok': False, 'E_eV': [], 'x_nm': [], 'V_eV': [], 'psi': [],
                 'comparison': {}, 'error': ''}
        try:
            params = {**self.WELL_SOLVER_DEFAULTS, **(params or {})}
            L_well = float(params['L_nm'])
            V0 = abs(float(params.get('V0_eV', 0.0) or 0.0))

            # A finite barrier needs room for the evanescent tail: putting
            # the box wall against the well returns the box's levels.
            if V0 > 0:
                L_box = max(3.0 * L_well, L_well + 10.0)
                x0 = (L_box - L_well) / 2.0
                features = [SegmentFeature1D(x0, L_well, -V0,
                                             float(params['meff']))]
            else:
                L_box = L_well
                features = [SegmentFeature1D(0.0, L_well, 0.0,
                                             float(params['meff']))]

            result = solve_well_1d(
                L_nm=L_box, N=int(params['N']),
                n_states=int(params['n_states']), meff=float(params['meff']),
                features=features, V_background_eV=0.0,
                bc=str(params.get('bc', 'dirichlet')))

            # Only bound states are levels: above the barrier the "state" is
            # the box's, and reporting it as the well's is a lie the grid
            # makes easy.
            energies = [float(E) for E in result['E_eV']]
            bound = [E for E in energies if V0 <= 0 or E < 0.0]
            targets = [float(t) for t in (params.get('targets') or [])]

            psi = result['psi']
            density = [(psi[:, i] ** 2).tolist() for i in range(psi.shape[1])]
            return {
                'ok': True,
                'E_eV': energies,
                'bound': bound if V0 > 0 else energies,
                'x_nm': result['x_nm'].tolist(),
                'V_eV': result['V_eV'].tolist(),
                'psi': density,
                'L_box_nm': L_box,
                'comparison': (compare_with_targets(
                    energies, self._target_spec(targets)) if targets else {}),
                'error': '',
            }
        except Exception as exc:
            logger.error("Quantum well solver failed: %s", exc, exc_info=True)
            return {**blank, 'error': str(exc)}

    @staticmethod
    def _target_spec(targets):
        """A throwaway spec carrying only targets, for the comparison."""
        from src.physics.solution_spec import SolutionSpec

        return SolutionSpec(model='1d', dims_nm=(1.0,),
                            targets_eV=tuple(targets))

    def solve_quantum_dot(self, params: Optional[dict] = None) -> dict:
        """Solve one quantum dot and report its shells.

        A dot confines in every direction, so the spectrum is discrete and
        reads like an atom's: levels group into shells, and the addition
        energies peak where a shell closes — the signature a Coulomb-blockade
        measurement shows.
        """
        from src.physics.quantum_dot import (addition_energies, level_spectrum,
                                             shell_table)
        from src.physics.solvers import compare_with_targets, solve_dot

        blank = {'ok': False, 'levels': [], 'shells': [], 'addition_eV': [],
                 'dos': {}, 'radial': {}, 'comparison': {}, 'error': ''}
        try:
            params = {**self.DOT_SOLVER_DEFAULTS, **(params or {})}
            model = str(params['model'])
            if model == 'parabolic':
                dims = [float(params['hw_xy_meV']), float(params['hw_z_meV'])]
            elif model == 'disc':
                dims = [float(params['R_nm']), float(params['Lz_nm'])]
            else:
                dims = [float(params['R_nm'])]

            levels = solve_dot(model, dims, meff=float(params['meff']),
                               V0_eV=abs(float(params.get('V0_eV', 0.0) or 0.0)) or None,
                               channels=int(params['channels']),
                               n_per_channel=int(params['n_per_channel']),
                               N=int(params['N']))
            if not levels:
                return {**blank,
                        'error': ("No state fits in this dot — widen it or "
                                  "deepen the barrier.")}

            index = max(0, min(int(params.get('state_index', 0)), len(levels) - 1))
            chosen = levels[index]
            grid, dos = level_spectrum(
                levels, broadening_eV=float(params['broadening_eV']))

            targets = [float(t) for t in (params.get('targets') or [])]
            return {
                'ok': True,
                'levels': [{'index': i, 'E_eV': float(lv.E_eV),
                            'label': lv.label,
                            'degeneracy': int(lv.degeneracy),
                            'occupancy': int(lv.occupancy),
                            'channel': int(lv.channel),
                            'qn': [int(q) for q in lv.quantum_numbers]}
                           for i, lv in enumerate(levels)],
                'shells': [{'E_eV': float(E), 'labels': list(labels),
                            'degeneracy': int(degeneracy), 'filled': int(filled)}
                           for E, labels, degeneracy, filled
                           in shell_table(levels)],
                'addition_eV': [float(v) for v in addition_energies(
                    levels, charging_eV=float(params['charging_eV']))],
                'dos': {'x': grid.tolist(), 'y': dos.tolist()},
                'radial': ({'r_nm': chosen.r_nm.tolist(),
                            'psi': (chosen.radial ** 2).tolist(),
                            'label': chosen.label, 'index': index}
                           if chosen.radial is not None
                           and chosen.r_nm is not None else {}),
                'comparison': (compare_with_targets(
                    [lv.E_eV for lv in levels], self._target_spec(targets))
                    if targets else {}),
                'error': '',
            }
        except Exception as exc:
            logger.error("Quantum dot solver failed: %s", exc, exc_info=True)
            return {**blank, 'error': str(exc)}

    # ========================================================================
    # Occupancy Matrix
    # ========================================================================

    def build_occupancy_matrix(self, task, peaks_dataset_name: str,
                               params: Optional[dict] = None,
                               source_dataset_name: Optional[str] = None,
                               intervals=None) -> dict:
        """Build the occupancy table from a peak list and an axis.

        The engine already assembles these tables, but through
        :func:`peak_matrix` / :func:`binned_peak_matrix`, which take
        :class:`Analysis` objects -- the search's own output, which only the
        tool that ran the search holds. A workflow carries a peak *table*
        instead, because that is what travels down a wire. This builds the
        same tables from that table plus an axis, reusing
        :func:`occupancy_matrix` itself so a hand-wired chain lands on
        Confinement Analysis's matrix rather than on something that resembles
        it.

        Marks are 1 and blanks are NaN, never 0: zero is a measured value, and
        a table full of them cannot say whether a spectrum was searched and
        found nothing or was never searched at all.

        Parameters
        ----------
        source_dataset_name : str, optional
            The spectra the peaks came from. It supplies the measured energy
            axis and, more importantly, the full column list -- a spectrum
            with no peak has no row in the peak table, so without the source
            it would vanish from the table instead of standing there as a
            blank column, which is the difference between "no state" and "not
            measured".
        intervals : list, optional
            ``[[lo, hi], …]`` to put the rows on instead of the measured
            samples. Feed Energy Binning's ``all_bins``: the occupied bins
            alone would drop the empty rows and with them the regular energy
            spacing that makes the table readable as a map.

        Returns
        -------
        dict with the created SpectralData objects (for workflow capture),
        their names and the CSV paths.
        """
        empty = {'matrix': None, 'matrix_offset': None, 'peak_count': None,
                 'matrix_path': '', 'offset_matrix_path': '', 'dataset_names': {}}
        try:
            if peaks_dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Peak table not found")
                return empty

            source_data = None
            if source_dataset_name:
                source_data = self._datasets.get(source_dataset_name)
                if source_data is None:
                    self.errorOccurred.emit("Error", "Dataset not found")
                    return empty

            bins = sorted(self._clean_intervals(intervals), key=lambda iv: iv[0])
            if not bins and source_data is None:
                self.errorOccurred.emit(
                    "Occupancy Matrix Error",
                    "Building the table needs either the source spectra or a "
                    "set of bins, to know what the rows are")
                return empty

            # Peak Finder and Confinement Analysis both write snake_case, but
            # a table that has been through a flat-data tool comes back with
            # Spectrum_Index, so the names are matched case-insensitively.
            frame = self._datasets[peaks_dataset_name].data
            by_name = {str(column).lower(): column for column in frame.columns}
            missing = [name for name in ('spectrum_index', 'position_value')
                       if name not in by_name]
            if missing:
                self.errorOccurred.emit(
                    "Occupancy Matrix Error",
                    f"The peak table has no {' and no '.join(missing)} column")
                return empty

            def _column(key):
                return pd.to_numeric(frame[by_name[key]], errors='coerce').to_numpy()

            spectrum_index = _column('spectrum_index')
            position = _column('position_value')
            usable = np.isfinite(spectrum_index) & np.isfinite(position)
            spectrum_index = spectrum_index[usable].astype(np.int64)
            position = position[usable].astype(np.float64)

            if source_data is not None:
                columns = [str(name) for name in source_data.spectra.columns]
            else:
                # Without the source the table is only as wide as the peaks
                # reach, so the highest index that carries a peak is the last
                # column there can be.
                highest = int(spectrum_index.max()) if spectrum_index.size else -1
                columns = [f"col{i}" for i in range(highest + 1)]
            if not columns:
                logger.warning("OccupancyMatrix: %s holds no usable peaks and no "
                               "source spectra name the columns",
                               peaks_dataset_name)
                return empty

            if bins:
                lows = np.asarray([iv[0] for iv in bins], dtype=np.float64)
                highs = np.asarray([iv[1] for iv in bins], dtype=np.float64)
                axis_values = (lows + highs) / 2.0
                # searchsorted picks the last bin that starts at or below the
                # peak, so the containment test is the only thing left to do —
                # and it has to be a real test, because a set of bins may have
                # gaps in it (occupied bins, hand-typed intervals) and a peak
                # in a gap belongs to no row at all.
                slot = np.searchsorted(lows, position, side='right') - 1
                placed = slot >= 0
                rows = np.where(placed, slot, 0)
                upper = highs[rows]
                # The top edge belongs to the last row rather than to nothing:
                # a state sitting exactly at the end of the sweep is where a
                # band edge usually is, and dropping it would be a silent loss.
                on_a_row = placed & np.where(rows == len(bins) - 1,
                                             position <= upper, position < upper)
            else:
                axis_values = np.asarray(source_data.independent_var, dtype=np.float64)
                if 'position_index' in by_name:
                    sample = _column('position_index')[usable]
                    on_a_row = np.isfinite(sample)
                    rows = np.where(on_a_row, sample, 0).astype(np.int64)
                else:
                    # A table that lost its sample index — hand-edited, or from
                    # a tool that kept only the physical columns — is still
                    # placeable: the peak was found on the sweep, so the nearest
                    # sample is its row to within half a step.
                    rows = self._nearest_sample(axis_values, position)
                    on_a_row = np.ones(position.size, dtype=bool)
                    logger.info("OccupancyMatrix: %s carries no position_index; "
                                "rows come from the nearest sample of %s",
                                peaks_dataset_name, source_dataset_name)

            n_columns = len(columns)
            n_rows = int(len(axis_values))
            in_range = (spectrum_index >= 0) & (spectrum_index < n_columns)
            # Counted before the row test on purpose: a peak that falls outside
            # the bins is still a peak that spectrum has, and a peak count that
            # disagreed with the peak table would look like a bug in the search.
            counts = np.bincount(spectrum_index[in_range], minlength=n_columns)

            marked = in_range & on_a_row
            by_column = {int(column): group.to_numpy() for column, group
                         in pd.DataFrame({'column': spectrum_index[marked],
                                          'row': rows[marked]}
                                         ).groupby('column')['row']}
            per_spectrum_rows = []
            for done in range(n_columns):
                if getattr(task, 'cancelled', False):
                    logger.info("OccupancyMatrix cancelled after %d/%d spectra",
                                done, n_columns)
                    return empty
                per_spectrum_rows.append(by_column.get(done, ()))
                task.progress = int(100 * (done + 1) / max(1, n_columns))

            base_name = self._extract_clean_base_name(
                source_dataset_name or peaks_dataset_name)
            file_safe_name = self._sanitize_filename(base_name)
            peaks_dir = self._ensure_output_dir('peaks')
            # The source's own label when there is a source; otherwise the peak
            # table's name for the quantity, rather than inventing a unit that
            # nothing in the chain actually told us.
            axis_name = (source_data.independent_var_name if source_data is not None
                         else str(by_name['position_value']))
            settings = {'created_from': 'occupancy_matrix',
                        'source_dataset': source_dataset_name or peaks_dataset_name,
                        'peaks_dataset': peaks_dataset_name,
                        'binned': bool(bins),
                        'n_rows': n_rows}
            created: dict = {}

            def _register(suffix: str, frame_out: pd.DataFrame,
                          source_type: str, extra: dict, *, flat=False):
                info = {**settings, **extra}
                if not flat and source_data is not None:
                    # One column per spectrum, so this is a per-spectrum output:
                    # it keeps the source's positions and a line scan's table
                    # can still be mapped onto the sample.
                    info = {**self._carry_spatial_info(source_data.metadata), **info}
                metadata = SpectralMetadata(
                    source_type=source_type,
                    dimensions=(tuple(source_data.metadata.dimensions)
                                if source_data is not None else (n_columns, 1)),
                    scan_mode=(source_data.metadata.scan_mode
                               if source_data is not None else 'peaks'),
                    units=(dict(source_data.metadata.units or {})
                           if source_data is not None else {}),
                    # No 'original' key on purpose: a table of marks is not a
                    # spectrum and must not be overlaid on the source's graph.
                    additional_info=info,
                    data_type='flat' if flat else (
                        source_data.metadata.data_type
                        if source_data is not None else 'spectral'),
                )
                name = f"{base_name} - {suffix}"
                try:
                    dataset = SpectralData(frame_out, metadata)
                except (ValueError, TypeError) as exc:
                    logger.warning("OccupancyMatrix: '%s' could not be built: %s",
                                   name, exc)
                    return
                self._datasets[name] = dataset
                if not self._workflow_mode:
                    self.dataLoaded.emit(name)
                created[suffix] = name

            def _emit(suffix: str, matrix: np.ndarray, filename: str, extra: dict):
                frame_out = pd.DataFrame(matrix, columns=columns)
                frame_out.insert(0, axis_name, axis_values)
                path = peaks_dir / filename
                _write_occupancy_csv(frame_out, columns, path)
                _register(suffix, frame_out, 'peak_matrix',
                          {'total_peaks': int(np.isfinite(matrix).sum()), **extra})
                return str(path)

            matrix_path = _emit('Occupancy Matrix',
                                occupancy_matrix(n_rows, per_spectrum_rows),
                                f"{file_safe_name}_OccupancyMatrix.csv", {})

            # Same marks, but each column carries its own 1-based number
            # instead of a flat 1. Plotting the 1/blank table stacks every
            # spectrum on one line; numbering offsets them onto separate rows
            # so the columns can be told apart.
            offset_matrix_path = _emit(
                'Occupancy Matrix (offset)',
                occupancy_matrix(n_rows, per_spectrum_rows, mark_by_column=True),
                f"{file_safe_name}_OccupancyMatrix_offset.csv", {'offset': True})

            _register('Peak Count',
                      pd.DataFrame({'Spectrum_Index': np.arange(n_columns),
                                    'Peak_Count': counts.astype(np.int64)}),
                      'peak_count', {}, flat=True)

            logger.info("OccupancyMatrix: %d peak(s) over %d spectra -> %d rows "
                        "(%s), %d marked; created %s",
                        int(position.size), n_columns, n_rows,
                        "bins" if bins else "measured axis",
                        int(marked.sum()), ", ".join(created.values()) or "nothing")

            return {
                'matrix': self._datasets.get(created.get('Occupancy Matrix', '')),
                'matrix_offset': self._datasets.get(
                    created.get('Occupancy Matrix (offset)', '')),
                'peak_count': self._datasets.get(created.get('Peak Count', '')),
                'matrix_path': matrix_path,
                'offset_matrix_path': offset_matrix_path,
                'dataset_names': created,
            }

        except Exception as e:
            logger.error(f"Occupancy matrix error: {e}", exc_info=True)
            self.errorOccurred.emit("Occupancy Matrix Error", str(e))
            return empty

    @staticmethod
    def _nearest_sample(axis: np.ndarray, values: np.ndarray) -> np.ndarray:
        """Index of the axis sample closest to each value.

        The axis is not assumed to ascend: a retrace sweep runs the other way,
        and searchsorted on it would return nonsense.
        """
        axis = np.asarray(axis, dtype=np.float64)
        values = np.asarray(values, dtype=np.float64)
        if axis.size < 2 or values.size == 0:
            return np.zeros(values.size, dtype=np.int64)
        order = np.argsort(axis)
        ascending = axis[order]
        slot = np.clip(np.searchsorted(ascending, values), 1, ascending.size - 1)
        below, above = ascending[slot - 1], ascending[slot]
        pick = np.where(values - below <= above - values, slot - 1, slot)
        return order[pick].astype(np.int64)

    # ========================================================================
    # Spectral Features
    # ========================================================================

    def extract_spectral_features(self, task, dataset_name: str,
                                  params: Optional[dict] = None) -> dict:
        """Reduce every spectrum to a row of physical features.

        Emits one flat dataset -- ``<base> - Features`` -- with a column per
        quantity (gap width, doping offset, band-edge coefficients, confined
        state count, ...). Being flat data, every column is immediately a
        spatial map via the Map Generator, and the table is the input to
        PCA / clustering.

        Parameters
        ----------
        params : dict
            Any field of :class:`src.processing.spectral_features.FeatureConfig`.
            Unknown keys are ignored, so QML and the workflow engine can pass
            their whole parameter map.
        """
        empty = {'features': None, 'dataset_name': '', 'features_path': '',
                 'n_valid': 0, 'n_total': 0}
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return empty

            spectral_data = self._datasets[dataset_name]
            independent_var = np.asarray(spectral_data.independent_var, dtype=np.float64)
            spectra = np.asarray(spectral_data.spectra.values, dtype=np.float64)

            # Same reason as the Map Generator: nowhere to write is not a
            # property of the data, so it must not be found out after every
            # spectrum has been reduced.
            out_dir = self._ensure_output_dir('peaks')

            config = _feature_config(params)
            config.validate()

            logger.info(
                "SpectralFeatures: %s — %d spectra, normalize=%s, gap delta=%.3g, "
                "%s degree %d",
                dataset_name, spectra.shape[1], config.normalize, config.gap_delta,
                config.poly_basis, config.poly_degree)

            rows = feature_table(
                independent_var, spectra, config,
                should_cancel=lambda: bool(getattr(task, 'cancelled', False)),
            )
            if len(rows) < spectra.shape[1]:
                logger.info("SpectralFeatures cancelled after %d/%d spectra",
                            len(rows), spectra.shape[1])
                return empty

            # Fixed column order, and numeric only: 'doping_type' is a label
            # and 'invalid_reason' is free text, so neither belongs in a table
            # destined for PCA. Both are kept in the CSV for inspection.
            columns = [c for c in feature_columns(config) if c in (rows[0] if rows else {})]
            frame = pd.DataFrame(rows)
            csv_path = out_dir / \
                f"{self._apply_naming_convention(dataset_name, operation='Features')}.csv"
            frame.to_csv(csv_path, index=False)

            numeric = frame[columns].apply(pd.to_numeric, errors='coerce')
            n_valid = int(numeric['valid'].sum()) if 'valid' in numeric else 0

            base_name = self._extract_clean_base_name(dataset_name)
            name = f"{base_name} - Features"
            metadata = SpectralMetadata(
                source_type='spectral_features',
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units={'independent': 'Index', 'dependent': 'Feature'},
                # No 'original' key: a feature table is not a spectrum and
                # must not be overlaid on the source's graph window.
                additional_info={
                    'created_from': 'spectral_features',
                    'source_dataset': dataset_name,
                    'feature_columns': [c for c in columns if c != 'Spectrum_Index'],
                    'normalize': config.normalize,
                    'basis': config.poly_basis,
                    'poly_degree': config.poly_degree,
                    'gap_delta': config.gap_delta,
                    'n_valid': n_valid,
                    'n_total': int(len(rows)),
                    'features_path': str(csv_path),
                },
                data_type='flat',
            )
            try:
                dataset = SpectralData(numeric, metadata,
                                       topography=getattr(spectral_data, 'topography', None))
            except (ValueError, TypeError) as exc:
                logger.warning("Feature table could not be promoted to a dataset: %s", exc)
                return empty

            self._datasets[name] = dataset
            if not self._workflow_mode:
                self.dataLoaded.emit(name)

            logger.info("SpectralFeatures: '%s' created (%d spectra, %d valid, %d features)",
                        name, len(rows), n_valid, len(columns) - 1)
            return {'features': dataset, 'dataset_name': name,
                    'features_path': str(csv_path),
                    'n_valid': n_valid, 'n_total': int(len(rows))}

        except Exception as e:
            logger.error(f"Spectral feature extraction error: {e}", exc_info=True)
            self.errorOccurred.emit("Spectral Features Error", str(e))
            return empty

    # ------------------------------------------------------------------
    # Confinement dimensionality
    # ------------------------------------------------------------------

    #: Verdict as a number, so the column is a map rather than a label. The
    #: order is "how much the fit committed to", which is what a colour scale
    #: should read as: nothing said, said no, said maybe, said yes.
    DIMENSIONALITY_VERDICT_CODES = {
        UNDERDETERMINED: 0.0,
        REJECTED: 1.0,
        AMBIGUOUS: 2.0,
        CONCLUSIVE: 3.0,
    }

    def analyze_confinement_dimensionality(self, task, dataset_name: str,
                                           params: Optional[dict] = None) -> dict:
        """Per-spectrum band-edge fit and confinement-geometry ranking.

        Two questions per spectrum, both answered against the temperature:

        * **Where is the band edge, and how disordered is it?**
          :func:`~src.processing.edge_analysis.fit_two_regime` locates the
          edge as the breakpoint between the steep in-gap tail and the
          shallower regime outside it, and reports the tail decay energy
          ``E0``. A single exponential branch cannot give an edge position --
          ``ln g = c - |V - V0|/E0`` is degenerate in ``(c, V0)`` -- so the
          breakpoint is the only estimator offered, and it is withheld
          entirely when the two regimes are not distinguishable.
        * **Which confinement geometry do the states fit?**
          :func:`~src.physics.level_ratio_fit.rank_patterns` compares the
          detected level positions against the dimensionless ladders of a 1D
          well, a square 2D box, a 2D disc, a cubic 3D box and a sphere. The
          ratios are size- and mass-independent and survive broadening,
          because a symmetric kernel preserves feature positions even where
          it destroys onset shapes.

        The per-level uncertainty is the resolution and the disorder added in
        quadrature: a level cannot be located better than the thermal and
        modulation width, and the local potential moves it again by about
        ``E0``. Both are measured from the same spectrum rather than assumed.

        Emits ``<base> - Dimensionality``, one row per spectrum, so every
        column is a spatial map. ``confined_dims`` is the dimensionality map
        itself; ``verdict_code`` says how much each pixel's answer is worth
        and should be read alongside it, since a confident-looking dimension
        on an ``underdetermined`` pixel means nothing.

        Whole-dataset statistics -- whether ``E0`` is the same everywhere, and
        the correlation length of the band-edge landscape -- are computed by
        :mod:`src.processing.spatial_coherence` and stored in the metadata,
        because they are properties of the set and not of any one spectrum.

        Parameters
        ----------
        params : dict
            ``temperature_k`` (required for any thermal statement),
            ``v_mod`` and ``mod_convention`` (lock-in amplitude),
            ``n_kt`` (how far from zero the fit window starts),
            ``max_skips`` (unresolved levels the ladder fit may invent),
            ``use_edge_as_offset`` (fix the ratio fit's offset to the measured
            band edge, which buys back a degree of freedom), plus any
            :data:`CONFINEMENT_DEFAULTS` peak-search knob.
        """
        empty = {'dimensionality': None, 'dataset_name': '',
                 'table_path': '', 'n_valid': 0, 'n_total': 0, 'coherence': {}}
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return empty

            raw = dict(params or {})
            temperature_k = float(raw.get('temperature_k') or 0.0)
            v_mod = float(raw.get('v_mod') or 0.0)
            convention = str(raw.get('mod_convention') or 'zero_to_peak')
            n_kt = float(raw.get('n_kt') or 3.0)
            # dI/dV taken WITHOUT a lock-in is not thermally limited: the
            # window used to differentiate I(V) is an instrument function too,
            # and at 94 K a 50 mV window is wider than the 28.6 mV thermal
            # kernel. Recording zero modulation and stopping there would hide
            # the dominant term.
            deriv_window_v = float(raw.get('deriv_window_v') or 0.0)
            deriv_polyorder = int(float(raw.get('deriv_polyorder') or 2))
            deriv_kind = str(raw.get('deriv_kind') or 'savgol_deriv')
            max_skips = int(float(raw.get('max_skips') or 2))
            use_edge_offset = bool(raw.get('use_edge_as_offset', False))
            if temperature_k <= 0:
                logger.warning(
                    "Dimensionality: no temperature given for '%s'. The tail "
                    "energies are still measured, but nothing can be called "
                    "resolution-limited and the level errors fall back to the "
                    "modulation width alone.", dataset_name)

            # Claim the output directory before fitting anything: with no
            # project open there is nowhere to write, and discovering that
            # after a per-spectrum fit over the whole dataset wastes the run.
            out_dir = self._ensure_output_dir('peaks')

            spectral_data = self._datasets[dataset_name]
            x = np.asarray(spectral_data.independent_var, dtype=np.float64)
            spectra = np.asarray(spectral_data.spectra.values, dtype=np.float64)
            n_spectra = int(spectra.shape[1])

            # Fall back to whatever the loader recorded. The MATRIX loader
            # reads the lock-in amplitude out of the parameter tree, so a
            # user who leaves the field alone gets the real number rather than
            # zero -- and is told when the convention behind it was assumed
            # rather than stated by the instrument.
            info = getattr(spectral_data.metadata, 'additional_info', None) or {}
            # Same for the differentiation window. When TRANS took the
            # derivative itself it recorded the window it used, so a curve
            # that came through the Derivative tool carries its own
            # instrument function and nobody has to remember it.
            if deriv_window_v <= 0 and info.get('deriv_window_v'):
                deriv_window_v = float(info['deriv_window_v'])
                deriv_polyorder = int(info.get('deriv_polyorder') or deriv_polyorder)
                deriv_kind = str(info.get('deriv_kind') or deriv_kind)
                logger.info(
                    "Dimensionality: using the recorded differentiation "
                    "window = %.4g V (%s, order %d)",
                    deriv_window_v, deriv_kind, deriv_polyorder)

            if v_mod <= 0 and info.get('v_mod'):
                v_mod = float(info['v_mod'])
                convention = str(info.get('v_mod_convention') or convention)
                logger.info(
                    "Dimensionality: using the loader's V_mod = %.4g V (%s%s)",
                    v_mod, convention,
                    ", convention ASSUMED, not stated by the instrument"
                    if info.get('v_mod_convention_assumed') else "")

            search = params_from_dict({**CONFINEMENT_DEFAULTS, **raw})
            search.validate()
            patterns = tuple(all_patterns())
            fwhm = resolution_fwhm(temperature_k, v_mod, convention,
                                   deriv_window_v, deriv_polyorder, deriv_kind)
            # FWHM -> Gaussian sigma. A level is not locatable to better than
            # the width of the kernel that smeared it.
            resolution_sigma = (fwhm / 2.3548 if math.isfinite(fwhm) and fwhm > 0
                                else 0.0)

            logger.info(
                "Dimensionality: %s — %d spectra at %.4g K, V_mod = %.4g V "
                "(%s), derivative window %.4g V (order %d), resolution %.4g eV",
                dataset_name, n_spectra, temperature_k, v_mod, convention,
                deriv_window_v, deriv_polyorder, fwhm)

            rows = []
            for i in range(n_spectra):
                if getattr(task, 'cancelled', False):
                    logger.info("Dimensionality cancelled after %d/%d spectra",
                                i, n_spectra)
                    return empty
                y = spectra[:, i]
                row = {'Spectrum_Index': float(i)}
                row.update(edge_summary(x, y, temperature_k, v_mod=v_mod,
                                        convention=convention, n_kt=n_kt,
                                        deriv_window_v=deriv_window_v,
                                        deriv_polyorder=deriv_polyorder,
                                        deriv_kind=deriv_kind))
                row.update(self._rank_one_spectrum(
                    x, y, row, search, patterns, resolution_sigma,
                    max_skips, use_edge_offset))
                rows.append(row)

            if not rows:
                return empty

            frame = pd.DataFrame(rows)
            csv_path = out_dir / \
                f"{self._apply_naming_convention(dataset_name, operation='Dimensionality')}.csv"
            frame.to_csv(csv_path, index=False)

            coherence = self._dimensionality_coherence(spectral_data, frame)

            # Text columns stay in the CSV: 'best_pattern' and 'verdict' are
            # labels, and a map wants 'confined_dims' and 'verdict_code'.
            columns = [c for c in self._dimensionality_columns() if c in frame]
            numeric = frame[columns].apply(pd.to_numeric, errors='coerce')
            n_valid = int(numeric['valid'].sum()) if 'valid' in numeric else 0

            base_name = self._extract_clean_base_name(dataset_name)
            name = f"{base_name} - Dimensionality"
            metadata = SpectralMetadata(
                source_type='confinement_dimensionality',
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units={'independent': 'Index', 'dependent': 'Feature'},
                additional_info={
                    'created_from': 'confinement_dimensionality',
                    'source_dataset': dataset_name,
                    'feature_columns': [c for c in columns if c != 'Spectrum_Index'],
                    'temperature_k': temperature_k,
                    'v_mod': v_mod,
                    'mod_convention': convention,
                    'deriv_window_v': deriv_window_v,
                    'deriv_polyorder': deriv_polyorder,
                    'deriv_kind': deriv_kind,
                    'resolution_fwhm': fwhm,
                    'n_valid': n_valid,
                    'n_total': n_spectra,
                    'table_path': str(csv_path),
                    'spatial_coherence': coherence,
                    # A feature table is not a spectrum, so no 'original' key:
                    # it must not be overlaid on the source's graph window.
                    **self._carry_spatial_info(spectral_data.metadata),
                },
                data_type='flat',
            )
            try:
                dataset = SpectralData(numeric, metadata,
                                       topography=getattr(spectral_data, 'topography', None))
            except (ValueError, TypeError) as exc:
                logger.warning("Dimensionality table could not be promoted: %s", exc)
                return empty

            self._datasets[name] = dataset
            if not self._workflow_mode:
                self.dataLoaded.emit(name)

            logger.info("Dimensionality: '%s' created (%d spectra, %d valid). "
                        "E0 %s; band edge %s",
                        name, n_spectra, n_valid,
                        coherence.get('e0_verdict', '?'),
                        coherence.get('v0_verdict', '?'))
            return {'dimensionality': dataset, 'dataset_name': name,
                    'table_path': str(csv_path), 'n_valid': n_valid,
                    'n_total': n_spectra, 'coherence': coherence}

        except Exception as e:
            logger.error(f"Confinement dimensionality error: {e}", exc_info=True)
            self.errorOccurred.emit("Dimensionality Error", str(e))
            return empty

    @staticmethod
    def _dimensionality_columns() -> list:
        """Numeric column order of the emitted table. Stable, so a map built
        on one run lines up with the next."""
        return (['Spectrum_Index'] + list(edge_columns())
                + ['n_levels', 'confined_dims', 'ratio_21',
                   'ratio_21_corrected', 'ratio_21_corrected_err',
                   'delta_aic', 'pattern_p_value', 'scale_ev', 'offset_ev',
                   'verdict_code'])

    def _rank_one_spectrum(self, x, y, edge_row, search, patterns,
                           resolution_sigma, max_skips, use_edge_offset) -> dict:
        """Detect the states in one spectrum and rank the geometries.

        Kept separate so the level uncertainty is stated in one place: it is
        the resolution and the disorder in quadrature, both measured from this
        spectrum rather than assumed.
        """
        blank = {'n_levels': 0.0, 'confined_dims': float('nan'),
                 'ratio_21': float('nan'), 'ratio_21_corrected': float('nan'),
                 'ratio_21_corrected_err': float('nan'),
                 'delta_aic': float('nan'), 'pattern_p_value': float('nan'),
                 'scale_ev': float('nan'), 'offset_ev': float('nan'),
                 'best_pattern': '', 'verdict': UNDERDETERMINED,
                 'verdict_code': self.DIMENSIONALITY_VERDICT_CODES[UNDERDETERMINED]}
        try:
            result = analyze(x, y, search)
        except Exception:
            logger.debug("Dimensionality: peak search failed", exc_info=True)
            return blank

        levels = np.array(sorted(float(pk.x) for pk in result.peaks),
                          dtype=np.float64)
        if levels.size < 2:
            return blank

        # A level is uncertain by the width of the kernel that smeared it and
        # again by how far the local potential moved it. E0 is this
        # spectrum's own measure of the second; fall back to the resolution
        # alone where no tail energy could be fitted.
        e0s = [edge_row.get('e0_neg'), edge_row.get('e0_pos')]
        e0s = [v for v in e0s if isinstance(v, float) and math.isfinite(v) and v > 0]
        disorder = float(np.mean(e0s)) if e0s else 0.0
        sigma = math.hypot(resolution_sigma, disorder)
        if sigma <= 0:
            sigma = max(float(np.median(np.abs(np.diff(x)))), 1e-6)

        offset_fixed = None
        if use_edge_offset:
            edges = [edge_row.get('v_edge_neg'), edge_row.get('v_edge_pos')]
            edges = [v for v in edges if isinstance(v, float) and math.isfinite(v)]
            if edges:
                offset_fixed = float(np.mean(edges))

        verdict = rank_patterns(levels, sigma, patterns=patterns,
                                offset_fixed=offset_fixed, max_skips=max_skips)
        best = verdict.best
        return {
            'n_levels': float(verdict.n_levels),
            'confined_dims': float(best.confined_dims) if best else float('nan'),
            'ratio_21': verdict.ratio_21,
            'ratio_21_corrected': verdict.ratio_21_corrected,
            'ratio_21_corrected_err': verdict.ratio_21_corrected_err,
            'delta_aic': verdict.delta_aic,
            'pattern_p_value': verdict.p_value,
            'scale_ev': float(best.scale_ev) if best else float('nan'),
            'offset_ev': float(best.offset_ev) if best else float('nan'),
            'best_pattern': best.pattern if best else '',
            'verdict': verdict.verdict,
            'verdict_code': self.DIMENSIONALITY_VERDICT_CODES.get(
                verdict.verdict, float('nan')),
        }

    def _dimensionality_coherence(self, spectral_data, frame) -> dict:
        """Whether E0 is uniform, and how far the band edge stays correlated.

        Properties of the SET of spectra, not of any one, so they live in the
        metadata rather than in a column. Positions come from whatever the
        loader recorded; without them only the uniformity half can be
        answered, which is still the half that separates compositional
        disorder from a uniform zero-point term.
        """
        try:
            e0 = pd.to_numeric(frame.get('e0_neg'), errors='coerce')
            e0_pos = pd.to_numeric(frame.get('e0_pos'), errors='coerce')
            # One tail energy per spectrum: the mean of the two branches where
            # both were fitted, otherwise whichever one was.
            e0 = pd.concat([e0, e0_pos], axis=1).mean(axis=1, skipna=True)
            v0 = pd.to_numeric(frame.get('v_edge_neg'), errors='coerce')

            # No per-point error bar is available from a single spectrum, so
            # the resolution stands in for it: two points differing by less
            # than that are not distinguishable anyway.
            info = getattr(spectral_data.metadata, 'additional_info', None) or {}
            err = info.get('resolution_fwhm')
            positions = self._line_positions_m(spectral_data)
            return coherence_summary(
                e0.to_numpy(dtype=np.float64),
                float(err) / 2.3548 if err else None,
                positions if positions is not None else None,
                v0.to_numpy(dtype=np.float64) if positions is not None else None,
            )
        except Exception:
            logger.debug("Spatial coherence summary failed", exc_info=True)
            return {}

    def _merge_peak_intervals(self, raw_intervals: list, independent_var: np.ndarray) -> list:
        """
        Merge overlapping intervals and remove duplicates, keeping the most prominent peaks.

        Parameters:
        -----------
        raw_intervals : list
            List of [start, end, peak_position, prominence]
        independent_var : np.ndarray
            Independent variable array for bounds checking

        Returns:
        --------
        list of [start, end] intervals, non-overlapping
        """
        if not raw_intervals:
            return []

        # Sort by peak position
        raw_intervals.sort(key=lambda x: x[2])

        # Group nearby intervals (within tolerance)
        x_range = independent_var[-1] - independent_var[0]
        tolerance = x_range * 0.02  # 2% of range

        # First pass: group intervals with similar peak positions
        grouped = []
        current_group = [raw_intervals[0]]

        for interval in raw_intervals[1:]:
            if abs(interval[2] - current_group[-1][2]) < tolerance:
                # Same peak region - add to group
                current_group.append(interval)
            else:
                # New peak region - process current group and start new
                grouped.append(current_group)
                current_group = [interval]

        grouped.append(current_group)

        # Second pass: for each group, take the interval with highest prominence
        representative_intervals = []
        for group in grouped:
            # Find the interval with highest prominence
            best = max(group, key=lambda x: x[3])
            representative_intervals.append([best[0], best[1]])

        # Third pass: merge any remaining overlaps
        representative_intervals.sort(key=lambda x: x[0])
        merged = []

        for interval in representative_intervals:
            if not merged:
                merged.append(interval)
            else:
                last = merged[-1]
                if interval[0] <= last[1]:
                    # Overlapping - merge
                    last[1] = max(last[1], interval[1])
                else:
                    # Not overlapping - add new
                    merged.append(interval)

        # Clip to data bounds
        x_min, x_max = independent_var[0], independent_var[-1]
        clipped = []
        for start, end in merged:
            clipped_start = max(start, x_min)
            clipped_end = min(end, x_max)
            if clipped_start < clipped_end:
                clipped.append([clipped_start, clipped_end])

        return clipped

    # ========================================================================
    # Map Discretization
    # ========================================================================

    def discretize_map(self, task, image_path: str, target_x: int, target_y: int) -> str:
        """
        Reduce spatial resolution of map images by averaging pixel blocks.

        Parameters:
        -----------
        image_path : str
            Path to image file
        target_x : int
            Target width in pixels
        target_y : int
            Target height in pixels

        Returns:
        --------
        output_path : str
            Path to discretized image
        """
        try:
            from PIL import Image
            import numpy as np

            logger.info(f"Discretizing map: {image_path} to {target_x}x{target_y}")

            # Load image
            img = Image.open(image_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            img_array = np.array(img)
            original_height, original_width = img_array.shape[:2]

            logger.info(f"Original size: {original_width}x{original_height}")

            # Calculate block sizes
            block_width = original_width // target_x
            block_height = original_height // target_y

            if block_width < 1 or block_height < 1:
                self.errorOccurred.emit("Error",
                    f"Target size ({target_x}x{target_y}) is larger than original ({original_width}x{original_height})")
                return ""

            # Create output array
            discretized = np.zeros((target_y, target_x, 3), dtype=np.uint8)

            # Average blocks
            for i in range(target_y):
                for j in range(target_x):
                    y_start = i * block_height
                    y_end = min((i + 1) * block_height, original_height)
                    x_start = j * block_width
                    x_end = min((j + 1) * block_width, original_width)

                    block = img_array[y_start:y_end, x_start:x_end]
                    discretized[i, j] = block.mean(axis=(0, 1)).astype(np.uint8)

            # Save discretized image as TIFF with readable filename
            filename = Path(image_path).stem
            # Clean up the filename using helper
            base_name = self._extract_clean_base_name(filename)
            file_safe_name = self._sanitize_filename(base_name)
            base = (self._ensure_output_dir('discretized')
                    / f"{file_safe_name}_discretized_{target_x}x{target_y}")
            # Discretising preserves the scanned AREA while reducing the pixel
            # count, so the per-pixel size scales up by the block factor.
            from src.utils.field_export import export_field
            from src.utils.tiff_io import read_tiff_calibration
            cal = read_tiff_calibration(image_path) or {}
            dx = dy = None
            if cal.get('dx') and cal.get('dy'):
                dx = cal['dx'] * (original_width / max(target_x, 1))
                dy = cal['dy'] * (original_height / max(target_y, 1))
            written = export_field(
                base, np.asarray(discretized, dtype=np.float32),
                dx=dx, dy=dy, unit=cal.get('unit'),
                title=base.name, context="map discretisation")
            output_path = written.get('tiff', str(base) + '.tiff')

            # Status update will be handled by callback in main thread
            logger.info(f"Map discretized from {original_width}x{original_height} to {target_x}x{target_y}, saved to {output_path}")

            return str(output_path)

        except Exception as e:
            logger.error(f"Map discretization error: {e}", exc_info=True)
            self.errorOccurred.emit("Discretization Error", str(e))
            return ""

    # ========================================================================
    # Data Manipulation - Equation-based operations
    # ========================================================================

    def evaluate_data_equation(self, equation: str, dataset_a=None, dataset_b=None,
                               flat_a=None, flat_b=None, output_name: str = "Manipulated"):
        """
        Evaluate an equation on datasets or flat data.

        Supports:
        - Arithmetic: +, -, *, /, ^ (power)
        - Functions: sqrt, log, log10, exp, abs, sin, cos, tan
        - References: A (or A[col]), B (or B[col])
        - Constants: pi, e

        Parameters:
        -----------
        equation : str
            Equation to evaluate (e.g., "A + B", "sqrt(A)", "A * 2 - B / 3")
        dataset_a : SpectralData, optional
            First dataset (referenced as 'A')
        dataset_b : SpectralData, optional
            Second dataset (referenced as 'B')
        flat_a : SpectralData, optional
            First flat data (referenced as 'A')
        flat_b : SpectralData, optional
            Second flat data (referenced as 'B')
        output_name : str
            Label for the output

        Returns:
        --------
        dict with 'result_dataset', 'result_flat', 'error'
        """
        result = {'result_dataset': None, 'result_flat': None, 'error': None}

        try:
            # Determine what data we're working with
            working_on_datasets = dataset_a is not None or dataset_b is not None
            working_on_flat = flat_a is not None or flat_b is not None

            if not working_on_datasets and not working_on_flat:
                result['error'] = "No input data provided"
                return result

            # Get data arrays
            A = None
            B = None
            reference_data = None  # For creating output with same structure

            if working_on_datasets:
                if dataset_a is not None:
                    A = dataset_a.spectra.values.copy()
                    reference_data = dataset_a
                if dataset_b is not None:
                    B = dataset_b.spectra.values.copy()
                    if reference_data is None:
                        reference_data = dataset_b
            else:
                if flat_a is not None:
                    # For flat data, get the numeric columns only
                    if hasattr(flat_a, 'spectra'):
                        A = flat_a.spectra.values.copy()
                    elif hasattr(flat_a, 'data'):
                        A = flat_a.data.iloc[:, 1:].values.copy()  # Skip first column (usually x)
                    reference_data = flat_a
                if flat_b is not None:
                    if hasattr(flat_b, 'spectra'):
                        B = flat_b.spectra.values.copy()
                    elif hasattr(flat_b, 'data'):
                        B = flat_b.data.iloc[:, 1:].values.copy()
                    if reference_data is None:
                        reference_data = flat_b

            # Validate dimensions if both A and B are provided
            if A is not None and B is not None:
                if A.shape != B.shape:
                    result['error'] = f"Dimension mismatch: A has shape {A.shape}, B has shape {B.shape}"
                    return result

            # Parse and evaluate the equation safely
            evaluated = self._safe_eval_equation(equation, A, B)

            if evaluated is None:
                result['error'] = "Failed to evaluate equation"
                return result

            # Create output dataset/flat data with same structure as reference
            if working_on_datasets:
                result['result_dataset'] = self._create_result_dataset(
                    evaluated, reference_data, output_name
                )
            else:
                result['result_flat'] = self._create_result_flat(
                    evaluated, reference_data, output_name
                )

            logger.info(f"Data manipulation complete: {equation} -> {output_name}")

        except Exception as e:
            logger.error(f"Data manipulation error: {e}", exc_info=True)
            result['error'] = str(e)

        return result

    def _safe_eval_equation(self, equation: str, A, B):
        """
        Safely evaluate a mathematical equation on arrays A and B.

        Only allows safe mathematical operations, no exec/eval of arbitrary code.
        """
        import re

        # Replace ^ with ** for power
        equation = equation.replace('^', '**')

        # Define allowed functions
        safe_funcs = {
            'sqrt': np.sqrt,
            'log': np.log,
            'log10': np.log10,
            'exp': np.exp,
            'abs': np.abs,
            'sin': np.sin,
            'cos': np.cos,
            'tan': np.tan,
            'arcsin': np.arcsin,
            'arccos': np.arccos,
            'arctan': np.arctan,
            'sinh': np.sinh,
            'cosh': np.cosh,
            'tanh': np.tanh,
            'floor': np.floor,
            'ceil': np.ceil,
            'round': np.round,
            'mean': np.mean,
            'sum': np.sum,
            'min': np.min,
            'max': np.max,
        }

        # Constants
        safe_vars = {
            'A': A if A is not None else np.array([0]),
            'B': B if B is not None else np.array([0]),
            'pi': np.pi,
            'e': np.e,
        }

        # Validate equation - only allow safe characters
        allowed_pattern = r'^[A-Za-z0-9\s\+\-\*\/\(\)\.\,\[\]\_\^]+$'
        if not re.match(allowed_pattern, equation):
            logger.warning(f"Equation contains disallowed characters: {equation}")
            return None

        # Check for dangerous patterns
        dangerous = ['import', 'exec', 'eval', 'open', 'file', '__', 'os.', 'sys.']
        for d in dangerous:
            if d in equation.lower():
                logger.warning(f"Equation contains dangerous pattern: {d}")
                return None

        try:
            # Use numpy's safe evaluation
            result = eval(equation, {"__builtins__": {}}, {**safe_funcs, **safe_vars})
            return result
        except Exception as e:
            logger.error(f"Equation evaluation failed: {e}")
            return None

    def _create_result_dataset(self, data_array, reference_data, output_name: str):
        """Create a new SpectralData object from result array."""
        import pandas as pd

        # Create DataFrame with same structure as reference
        columns = reference_data.spectra.columns
        result_df = pd.DataFrame(data_array, columns=columns)
        result_df.insert(0, reference_data.independent_var_name, reference_data.independent_var)

        # Create new SpectralData
        metadata = SpectralMetadata(
            source_file=f"Calculated: {output_name}",
            source_type='calculated',
            num_spectra=data_array.shape[1] if len(data_array.shape) > 1 else 1,
            num_points=data_array.shape[0]
        )

        result = SpectralData(
            data=result_df,
            independent_var_name=reference_data.independent_var_name,
            metadata=metadata
        )

        return result

    def _create_result_flat(self, data_array, reference_data, output_name: str):
        """Create a new flat data object from result array."""
        import pandas as pd

        # Get reference structure
        if hasattr(reference_data, 'spectra'):
            columns = reference_data.spectra.columns
            independent_var = reference_data.independent_var
            independent_var_name = reference_data.independent_var_name
        elif hasattr(reference_data, 'data'):
            columns = reference_data.data.columns[1:]  # Skip first column
            independent_var = reference_data.data.iloc[:, 0].values
            independent_var_name = reference_data.data.columns[0]
        else:
            columns = [f'col_{i}' for i in range(data_array.shape[1] if len(data_array.shape) > 1 else 1)]
            independent_var = np.arange(data_array.shape[0])
            independent_var_name = 'x'

        result_df = pd.DataFrame(data_array, columns=columns[:data_array.shape[1]] if len(data_array.shape) > 1 else columns[:1])
        result_df.insert(0, independent_var_name, independent_var[:len(result_df)])

        # Create new SpectralData
        metadata = SpectralMetadata(
            source_file=f"Calculated: {output_name}",
            source_type='calculated',
            num_spectra=data_array.shape[1] if len(data_array.shape) > 1 else 1,
            num_points=data_array.shape[0]
        )

        result = SpectralData(
            data=result_df,
            independent_var_name=independent_var_name,
            metadata=metadata
        )

        return result

    # ========================================================================
    # Filter Bad Data
    # Algorithms adapted from ststools by Rafael Reis
    # (https://github.com/rafinhareis/ststools)
    # ========================================================================

    def filter_bad_data(self, task, dataset_name: str,
                        weight_saturation: float = 1.0,
                        weight_noise: float = 1.0,
                        weight_linear: float = 1.0,
                        weight_periodic: float = 1.0,
                        weight_partial_noise: float = 1.0,
                        weight_featureless: float = 1.0,
                        threshold: float = 0.5,
                        correct_periodic: bool = False,
                        min_structure_ratio: float = 3.0,
                        min_coherence: float = 0.12,
                        min_finite_fraction: float = 0.5,
                        filter_offset_outliers: bool = False,
                        filter_bandgap_outliers: bool = False,
                        filter_saturation_outliers: bool = False,
                        max_offset_outliers: int = 5,
                        max_bandgap_outliers: int = 5,
                        max_saturation_outliers: int = 5,
                        outlier_group_by: str = 'point',
                        outlier_intervals: int = 8,
                        outlier_z: float = 3.5) -> str:
        """
        Filter bad spectra on saturation, noise, linear artifact, periodic
        noise, partial noise and featurelessness.

        A spectrum with too few finite samples is bad unconditionally, whatever
        the weights say: every detector returns 0 for a curve it cannot
        measure, so an all-NaN column used to score 0 across the board and land
        in *Good Data*. Measured on real STS data, 103 of 167 "good" spectra
        were entirely empty.

        **Outliers** are judged separately, and only if asked for. Every
        detector above looks at one curve on its own; an outlier is a curve
        that may be perfectly sound and still wrong to average in, which is a
        question about the *population* it sits in. See
        :mod:`src.processing.curve_outliers`: the comparison runs within each
        point's repetitions by default, because averaging across points is
        averaging across different places on the sample.

        Creates three new datasets — '{base} - Good Data', '{base} - Bad
        Data' and '{base} - FFT Spectra' — and exports every output of the run
        into one folder, ``curves/{base}_Filtered/``: the three datasets as
        CSV plus the text report.

        Returns the path to the text report.
        """
        from src.backend.sts_algorithms import (
            detect_saturation, detect_noise, detect_linear_artifact,
            detect_periodic_noise, correct_periodic_noise,
            detect_partial_noise, detect_featureless, structure_metrics
        )
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            independent_var = spectral_data.independent_var
            spectra = spectral_data.spectra
            num_spectra = spectra.shape[1]

            logger.info(f"Filtering bad data for {dataset_name}: {num_spectra} spectra, "
                        f"weights=({weight_saturation}, {weight_noise}, {weight_linear}, "
                        f"{weight_periodic}, {weight_partial_noise}, {weight_featureless}), "
                        f"threshold={threshold}, correct_periodic={correct_periodic}, "
                        f"min_structure_ratio={min_structure_ratio}, min_coherence={min_coherence}")

            # A curve with too little of itself left is not judged, it is
            # rejected: every detector scores 0 on data it cannot measure.
            min_finite = max(8, int(math.ceil(min_finite_fraction * len(independent_var))))
            empty_indices = []

            good_indices = []
            bad_indices = []
            fft_magnitudes = {}
            fft_frequencies = None
            corrected_spectra = {}

            correction_note = " (periodic correction enabled)" if correct_periodic else ""
            report_lines = [
                f"Filter Bad Data Report",
                f"Dataset: {dataset_name}",
                f"Total spectra: {num_spectra}",
                f"Combination: max(weighted scores) — each detector independently triggers",
                f"Weights: saturation={weight_saturation}, noise={weight_noise}, "
                f"linear={weight_linear}, periodic={weight_periodic}, "
                f"partial_noise={weight_partial_noise}, featureless={weight_featureless}",
                f"Threshold: {threshold}{correction_note}",
                f"Featureless: structure ratio < {min_structure_ratio} or coherence < {min_coherence}",
                f"Rejected outright: fewer than {min_finite} finite samples of {len(independent_var)}",
                "",
                f"{'Index':>6} {'Sat':>8} {'Noise':>8} {'Linear':>8} {'Periodic':>10} {'Partial':>10} "
                f"{'Featless':>10} {'Combined':>10} {'Trigger':>12} {'Status':>8} "
                f"{'Ratio':>10} {'Cohere':>8} {'Sigma':>11}",
                "-" * 130,
            ]

            for i in range(num_spectra):
                if task.cancelled:
                    return ""
                task.progress = i / num_spectra

                spectrum = spectra.iloc[:, i].values
                col_name = spectra.columns[i]

                # Reject before scoring: a mostly-empty column has nothing for
                # a detector to measure, and every one of them would return 0.
                n_finite = int(np.count_nonzero(np.isfinite(spectrum)))
                if n_finite < min_finite:
                    empty_indices.append(i)
                    bad_indices.append(i)
                    report_lines.append(
                        f"{i:>6} {'—':>8} {'—':>8} {'—':>8} {'—':>10} {'—':>10} "
                        f"{'—':>10} {1.0:>10.3f} {'empty':>12} {'BAD':>8} "
                        f"{'—':>10} {'—':>8} {'—':>11}"
                        f"   ({n_finite} finite samples)"
                    )
                    continue

                sat_score = detect_saturation(spectrum)
                noise_score = detect_noise(spectrum)
                lin_score = detect_linear_artifact(independent_var, spectrum)
                periodic_score, fft_mag, _bg, peak_mask = detect_periodic_noise(spectrum)
                partial_score = detect_partial_noise(independent_var, spectrum)
                featureless_score = detect_featureless(
                    independent_var, spectrum,
                    min_ratio=min_structure_ratio, min_coherence=min_coherence)
                metrics = structure_metrics(spectrum)

                # Store FFT magnitude for output dataset
                fft_magnitudes[col_name] = fft_mag
                if fft_frequencies is None:
                    # Compute frequency axis once using full spectrum length
                    # (detect_periodic_noise strips NaN internally, so use the same length)
                    dx = np.abs(np.mean(np.diff(independent_var))) if len(independent_var) > 1 else 1.0
                    n_clean = len(spectrum[~np.isnan(spectrum)])
                    fft_frequencies = np.fft.rfftfreq(n_clean, d=dx)
                    fft_expected_len = n_clean // 2 + 1

                # Periodic noise correction
                if correct_periodic and np.any(peak_mask):
                    corrected_spectra[i] = correct_periodic_noise(spectrum, peak_mask)

                # Max-based combination: each detector can independently trigger
                weighted_scores = []
                score_labels = []
                if weight_saturation > 0:
                    weighted_scores.append(weight_saturation * sat_score)
                    score_labels.append("saturation")
                if weight_noise > 0:
                    weighted_scores.append(weight_noise * noise_score)
                    score_labels.append("noise")
                if weight_linear > 0:
                    weighted_scores.append(weight_linear * lin_score)
                    score_labels.append("linear")
                if weight_periodic > 0:
                    weighted_scores.append(weight_periodic * periodic_score)
                    score_labels.append("periodic")
                if weight_partial_noise > 0:
                    weighted_scores.append(weight_partial_noise * partial_score)
                    score_labels.append("partial_noise")
                if weight_featureless > 0:
                    weighted_scores.append(weight_featureless * featureless_score)
                    score_labels.append("featureless")

                if weighted_scores:
                    max_idx = int(np.argmax(weighted_scores))
                    combined = weighted_scores[max_idx]
                    trigger = score_labels[max_idx]
                else:
                    combined = 0.0
                    trigger = "-"

                status = "BAD" if combined >= threshold else "GOOD"
                if combined >= threshold:
                    bad_indices.append(i)
                else:
                    good_indices.append(i)

                ratio = metrics['ratio']
                report_lines.append(
                    f"{i:>6} {sat_score:>8.3f} {noise_score:>8.3f} {lin_score:>8.3f} "
                    f"{periodic_score:>10.3f} {partial_score:>10.3f} "
                    f"{featureless_score:>10.3f} {combined:>10.3f} {trigger:>12} {status:>8} "
                    f"{ratio:>10.1f} {metrics['coherence']:>8.3f} {metrics['sigma']:>11.3e}"
                )

            # ---------------------------------------------------------------
            # Outliers: a population question, asked only of the survivors.
            #
            # It runs after the per-spectrum pass so the population is not
            # defined by curves already known to be junk — an all-NaN column
            # or a railed one would drag the median around and hide the very
            # curve being looked for.
            # ---------------------------------------------------------------
            outlier_enabled = {
                'offset': bool(filter_offset_outliers),
                'bandgap': bool(filter_bandgap_outliers),
                'saturation': bool(filter_saturation_outliers),
            }
            outlier_messages: List[str] = []
            outlier_kind_of: Dict[str, str] = {}
            # Which columns belong to which point, kept past the outlier block
            # so the per-point averages below can be built from it.
            group_columns: Dict[str, List[str]] = {}
            if any(outlier_enabled.values()) and len(good_indices) >= 3:
                from src.processing import curve_outliers as _outliers

                surviving = [spectra.columns[i] for i in good_indices]
                groups = _outliers.build_groups(
                    surviving,
                    spectral_data.metadata.additional_info.get('spectrum_meta'),
                    mode=str(outlier_group_by or 'point'),
                )
                group_columns = {label: [surviving[i] for i in indices]
                                 for label, indices in groups.items()}
                analyses = _outliers.analyze_grouped(
                    independent_var, spectra[surviving].values, surviving, groups,
                    n_intervals=int(outlier_intervals),
                    z_threshold=float(outlier_z),
                )
                to_remove, outlier_messages = _outliers.select_grouped(
                    analyses, outlier_enabled,
                    {'offset': int(max_offset_outliers),
                     'bandgap': int(max_bandgap_outliers),
                     'saturation': int(max_saturation_outliers)},
                )
                for analysis in analyses.values():
                    outlier_kind_of.update(analysis.kind_of)

                if to_remove:
                    removed = set(to_remove)
                    by_name = {spectra.columns[i]: i for i in good_indices}
                    moved = [by_name[name] for name in to_remove if name in by_name]
                    good_indices = [i for i in good_indices
                                    if spectra.columns[i] not in removed]
                    bad_indices.extend(moved)
                    bad_indices.sort()

                report_lines.append("")
                report_lines.append(
                    f"Outliers (compared within {'each point' if groups and 'all curves' not in groups else 'the whole dataset'}, "
                    f"{len(groups)} group(s), {outlier_intervals} intervals, z>{outlier_z})")
                for message in outlier_messages or ["Nothing flagged."]:
                    report_lines.append(f"  {message}")
                if to_remove:
                    report_lines.append(
                        "  These pass every per-spectrum test and are marked GOOD in the "
                        "table above; they are moved to Bad Data as a decision about the "
                        "population, not about the curve.")
                if 'all curves' in groups:
                    report_lines.append(
                        "  NOTE: this dataset records no per-spectrum point index, so every "
                        "curve was compared against every other. That is only meaningful if "
                        "they really are repetitions of one measurement.")

            report_lines.append("")
            report_lines.append(f"Good spectra: {len(good_indices)}")
            report_lines.append(f"Bad spectra: {len(bad_indices)}")
            if empty_indices:
                report_lines.append(
                    f"  of which rejected as empty (too few finite samples): {len(empty_indices)}")
            if outlier_kind_of:
                listed = ', '.join(f"{col} ({kind})"
                                   for col, kind in sorted(outlier_kind_of.items()))
                report_lines.append(f"  outliers identified: {listed}")
            if correct_periodic:
                report_lines.append(f"Spectra with periodic correction applied: {len(corrected_spectra)}")

            base_name = self._extract_clean_base_name(dataset_name)
            file_safe_name = self._sanitize_filename(base_name)

            # Every output of one run lands in its own folder, so a filtered
            # dataset's good/bad/FFT curves and its report stay together:
            #   curves/<dataset>_Filtered/{Good_Data,Bad_Data,FFT_Spectra}.csv
            #                             + <dataset>_filter_report.txt
            output_dir = self._ensure_output_dir('curves') / f"{file_safe_name}_Filtered"
            output_dir.mkdir(parents=True, exist_ok=True)
            written_files = []

            def _write_dataset(dataset, suffix):
                """Write one result dataset into the run folder as CSV.

                A failed export must not lose the filtering result, so it is
                logged and the tool carries on.
                """
                path = output_dir / f"{file_safe_name}_{suffix}.csv"
                try:
                    dataset.save(str(path))
                except Exception as exc:
                    logger.warning("Filter Bad Data: could not write %s: %s", path, exc)
                    return
                written_files.append(path)

            # Build good dataset (with optional periodic correction).
            # Carry the original spectrum captions across so downstream
            # processing can still identify each column by name.
            good_name = f"{base_name} - Good Data"
            if good_indices:
                good_cols = [spectra.columns[i] for i in good_indices]
                if correct_periodic and corrected_spectra:
                    # Use corrected spectra where available
                    good_data = []
                    for idx in good_indices:
                        if idx in corrected_spectra:
                            good_data.append(corrected_spectra[idx])
                        else:
                            good_data.append(spectra.iloc[:, idx].values)
                    good_df = pd.DataFrame(
                        np.column_stack(good_data),
                        columns=good_cols,
                    )
                else:
                    good_df = pd.DataFrame(
                        spectra[good_cols].values,
                        columns=good_cols,
                    )
                good_df.insert(0, spectral_data.independent_var_name, independent_var)

                good_metadata = SpectralMetadata(
                    source_type=spectral_data.metadata.source_type,
                    dimensions=spectral_data.metadata.dimensions,
                    scan_mode=spectral_data.metadata.scan_mode,
                    units=spectral_data.metadata.units.copy(),
                    additional_info={
                        **self._carry_spatial_info(spectral_data.metadata, good_cols),
                        'original': dataset_name,
                        'filter': 'good',
                        'count': len(good_indices),
                        'periodic_corrected': correct_periodic
                    }
                )
                good_dataset = SpectralData(good_df, good_metadata)
                self._datasets[good_name] = good_dataset
                _write_dataset(good_dataset, 'Good_Data')
                if not self._workflow_mode:
                    self.dataLoaded.emit(good_name)
            else:
                report_lines.append("No good spectra found — 'Good Data' dataset not created.")

            # Per-point averages, with the outliers left out.
            #
            # This is the dataset the outlier pass exists to produce. An
            # overview holds every repetition at every point; what the
            # analysis actually wants is one curve per point, and an average
            # is only worth taking once the curves that would drag it are
            # gone. One column per point, each the NaN-aware mean of the
            # repetitions that survived both the per-spectrum tests and the
            # outlier pass.
            averaged_name = f"{base_name} - Outliers Removed"
            if group_columns and good_indices:
                surviving_cols = {spectra.columns[i] for i in good_indices}
                source_meta = {
                    entry.get('column'): entry
                    for entry in (spectral_data.metadata.additional_info.get(
                        'spectrum_meta') or []) if isinstance(entry, dict)
                }

                def _point_of(label: str, members: List[str]):
                    """Point index for a group, for naming and ordering."""
                    for member in members:
                        entry = source_meta.get(member) or {}
                        for key in ('point_index', 'line_pos'):
                            if entry.get(key) is not None:
                                return int(entry[key])
                    return None

                kept: List[tuple] = []
                for label, members in group_columns.items():
                    alive = [c for c in members if c in surviving_cols]
                    if not alive:
                        continue          # every repetition here was rejected
                    kept.append((_point_of(label, alive), label, alive))

                # Acquisition order, with any unidentified group last.
                kept.sort(key=lambda item: (item[0] is None, item[0], item[1]))
                max_point = max((p for p, _, _ in kept if p is not None),
                                default=len(kept))

                avg_cols: Dict[str, np.ndarray] = {}
                avg_meta: List[dict] = []
                for point, label, alive in kept:
                    name = f"P{_pad(point, max_point)}" if point is not None else label
                    with warnings.catch_warnings():
                        # An all-NaN bias step is a real reading of "nothing
                        # survived here", not something to warn about.
                        warnings.simplefilter('ignore', category=RuntimeWarning)
                        avg_cols[name] = np.nanmean(spectra[alive].values, axis=1)
                    template = source_meta.get(alive[0]) or {}
                    # Three numbers, because "13 averaged" on its own is
                    # ambiguous: how many the input held at this point, how
                    # many the per-spectrum tests had already taken out, and
                    # how many the outlier pass took.
                    n_input = sum(
                        1 for entry_ in source_meta.values()
                        if entry_.get('point_index') is not None
                        and entry_.get('point_index') == template.get('point_index')
                    ) or len(group_columns[label])
                    entry = {
                        'column': name,
                        'group': label,
                        'n_averaged': len(alive),
                        'n_input': n_input,
                        'n_outliers_removed': len(group_columns[label]) - len(alive),
                        'n_rejected_by_tests': max(
                            0, n_input - len(group_columns[label])),
                        'source_columns': alive,
                    }
                    for key in ('point_index', 'line_pos', 'location_px',
                                'location_m', 'parent_image'):
                        if template.get(key) is not None:
                            entry[key] = template[key]
                    avg_meta.append(entry)

                if avg_cols:
                    avg_df = pd.DataFrame(avg_cols)
                    avg_df.insert(0, spectral_data.independent_var_name,
                                  independent_var)
                    src_info = spectral_data.metadata.additional_info
                    avg_metadata = SpectralMetadata(
                        source_type=spectral_data.metadata.source_type,
                        # One column per point now, not per repetition.
                        dimensions=(len(avg_cols), 1),
                        scan_mode=spectral_data.metadata.scan_mode,
                        units=spectral_data.metadata.units.copy(),
                        additional_info={
                            'original': dataset_name,
                            'filter': 'outliers_removed',
                            'averaged_over_reps': True,
                            'count': len(avg_cols),
                            'spectrum_meta': avg_meta,
                            'spatial_layout': src_info.get('spatial_layout')
                                              or ('line' if len(avg_cols) > 1 else 'point'),
                            'instrument': src_info.get('instrument'),
                            'session_label': src_info.get('session_label'),
                        },
                    )
                    averaged_dataset = SpectralData(avg_df, avg_metadata)
                    self._datasets[averaged_name] = averaged_dataset
                    _write_dataset(averaged_dataset, 'Outliers_Removed')
                    if not self._workflow_mode:
                        self.dataLoaded.emit(averaged_name)
                    report_lines.append(
                        f"Per-point averages ('{averaged_name}'): {len(avg_cols)} point(s), "
                        f"{sum(e['n_averaged'] for e in avg_meta)} curve(s) averaged, "
                        f"{sum(e['n_outliers_removed'] for e in avg_meta)} dropped as "
                        f"outliers, {sum(e['n_rejected_by_tests'] for e in avg_meta)} "
                        f"already rejected by the per-spectrum tests.")

            # Build bad dataset (always original, uncorrected spectra)
            bad_name = f"{base_name} - Bad Data"
            if bad_indices:
                bad_cols = [spectra.columns[i] for i in bad_indices]
                bad_df = pd.DataFrame(
                    spectra[bad_cols].values,
                    columns=bad_cols,
                )
                bad_df.insert(0, spectral_data.independent_var_name, independent_var)

                bad_metadata = SpectralMetadata(
                    source_type=spectral_data.metadata.source_type,
                    dimensions=spectral_data.metadata.dimensions,
                    scan_mode=spectral_data.metadata.scan_mode,
                    units=spectral_data.metadata.units.copy(),
                    additional_info={
                        **self._carry_spatial_info(spectral_data.metadata, bad_cols),
                        'original': dataset_name,
                        'filter': 'bad',
                        'count': len(bad_indices)
                    }
                )
                bad_dataset = SpectralData(bad_df, bad_metadata)
                self._datasets[bad_name] = bad_dataset
                _write_dataset(bad_dataset, 'Bad_Data')
                if not self._workflow_mode:
                    self.dataLoaded.emit(bad_name)
            else:
                report_lines.append("No bad spectra found — 'Bad Data' dataset not created.")

            # Build FFT Spectra output dataset
            if fft_frequencies is not None and fft_magnitudes:
                fft_data = {'Frequency': fft_frequencies}
                n_freq = len(fft_frequencies)
                skipped = 0
                for col_name, mag in fft_magnitudes.items():
                    if len(mag) == n_freq:
                        fft_data[col_name] = mag
                    elif len(mag) > n_freq:
                        # Truncate to match (different NaN count in this spectrum)
                        fft_data[col_name] = mag[:n_freq]
                    else:
                        # Too short (e.g. edge case with <8 clean points) — skip
                        skipped += 1

                if skipped > 0:
                    logger.warning(f"FFT: skipped {skipped} spectra with mismatched lengths")

                if len(fft_data) > 1:  # At least Frequency + one spectrum
                    fft_df = pd.DataFrame(fft_data)

                    orig_units = spectral_data.metadata.units
                    indep_unit = orig_units.get('independent', 'V')
                    fft_metadata = SpectralMetadata(
                        source_type='computed',
                        dimensions='1D',
                        scan_mode='FFT',
                        units={'independent': f'1/{indep_unit}', 'dependent': 'a.u.'},
                        additional_info={
                            'original': dataset_name,
                            'type': 'fft_spectra'
                        }
                    )
                    fft_name = f"{base_name} - FFT Spectra"
                    fft_dataset = SpectralData(fft_df, fft_metadata)
                    self._datasets[fft_name] = fft_dataset
                    _write_dataset(fft_dataset, 'FFT_Spectra')
                    if not self._workflow_mode:
                        self.dataLoaded.emit(fft_name)

            # Save report alongside the exported curves
            report_lines.append("")
            report_lines.append(f"Output folder: {output_dir}")
            for path in written_files:
                report_lines.append(f"  {path.name}")

            report_text = "\n".join(report_lines)
            output_path = output_dir / f"{file_safe_name}_filter_report.txt"
            output_path.write_text(report_text)

            logger.info(f"Filter complete: {len(good_indices)} good, {len(bad_indices)} bad")
            return str(output_path)

        except Exception as e:
            logger.error(f"Filter Bad Data error: {e}", exc_info=True)
            self.errorOccurred.emit("Filter Bad Data Error", str(e))
            return ""

    # ========================================================================
    # Detect Bandgap & Doping
    # Algorithms adapted from ststools by Rafael Reis
    # (https://github.com/rafinhareis/ststools)
    # ========================================================================

    def detect_bandgap_doping(self, task, dataset_name: str,
                              smoothing: float = 1.0,
                              delta: float = 5.0,
                              resolution: float = 0.01,
                              smoothing_method: str = 'Savgol') -> str:
        """
        Detect bandgap and doping type per spectrum.

        Pipeline: validate -> smooth -> derivative -> normalize -> bandgap -> doping.
        Produces TWO output datasets:
        - '{base_name} - Bandgap': Spectrum Index, Bandgap (eV), Gap Left Edge (V), Gap Right Edge (V), Valid
        - '{base_name} - Doping': Spectrum Index, Doping Type, Doping Offset (V), Valid
        """
        from src.backend.sts_algorithms import (
            numerical_derivative, normalize_ldos, detect_bandgap,
            classify_doping, validate_ldos
        )
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            independent_var = spectral_data.independent_var
            spectra = spectral_data.spectra
            num_spectra = spectra.shape[1]

            logger.info(f"Detecting bandgap/doping for {dataset_name}: {num_spectra} spectra")

            # Result arrays
            bandgaps = np.full(num_spectra, np.nan)
            doping_offsets = np.full(num_spectra, np.nan)
            doping_numeric = np.full(num_spectra, np.nan)
            xmins = np.full(num_spectra, np.nan)
            xmaxs = np.full(num_spectra, np.nan)
            valid_flags = np.zeros(num_spectra, dtype=int)

            delta_frac = delta / 100.0  # Convert from % to fraction

            for i in range(num_spectra):
                if task.cancelled:
                    return ""
                task.progress = i / num_spectra

                y = spectra.iloc[:, i].values.copy()
                x = independent_var.copy()

                # 1. Validate
                is_valid, reason = validate_ldos(x, y)
                if not is_valid:
                    continue
                valid_flags[i] = 1

                # 2. Smooth if requested
                if smoothing > 0 and smoothing_method != 'None':
                    # Convert smoothing % to window size
                    window = max(3, int(len(x) * smoothing / 100.0))
                    if window % 2 == 0:
                        window += 1
                    window = min(window, len(x) - 1)
                    if window >= 3:
                        if smoothing_method == 'Savgol':
                            poly_order = min(3, window - 1)
                            y = signal.savgol_filter(y, window, poly_order)
                        elif smoothing_method == 'Moving Avg':
                            y = np.convolve(y, np.ones(window) / window, mode='same')

                # 3. Numerical derivative -> dI/dV
                dx, dy = numerical_derivative(x, y)

                if len(dx) < 3:
                    continue

                # 4. Normalize LDOS
                dx_norm, dy_norm = normalize_ldos(dx, dy)

                # 5. Detect bandgap
                gap, typ, xmin, xmax = detect_bandgap(dx_norm, dy_norm, delta_frac)

                # 6. Classify doping
                doping_str = classify_doping(typ, resolution)

                bandgaps[i] = gap
                doping_offsets[i] = typ
                xmins[i] = xmin
                xmaxs[i] = xmax

                doping_map = {'N': -1, 'Neutral': 0, 'P': 1}
                doping_numeric[i] = doping_map.get(doping_str, 0)

            # --- Bandgap dataset ---
            bandgap_base = self._extract_clean_base_name(dataset_name)
            bandgap_convention = self._apply_naming_convention(dataset_name, operation="Bandgap")
            bandgap_df = pd.DataFrame({
                'Spectrum Index': range(num_spectra),
                'Bandgap (eV)': bandgaps,
                'Gap Left Edge (V)': xmins,
                'Gap Right Edge (V)': xmaxs,
                'Valid': valid_flags
            })

            bandgap_csv = self._ensure_output_dir('curves') / f"{bandgap_convention}.csv"
            bandgap_df.to_csv(bandgap_csv, index=False)

            bandgap_name = f"{bandgap_base} - Bandgap"
            bandgap_metadata = SpectralMetadata(
                source_type="bandgap",
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units={'independent': 'Index', 'dependent': 'eV'},
                additional_info={
                    'original': dataset_name,
                    'original_source_type': spectral_data.metadata.source_type,
                    'smoothing': smoothing,
                    'delta': delta,
                    'valid_count': int(np.sum(valid_flags)),
                    'total_count': num_spectra
                },
                data_type='flat'
            )
            self._datasets[bandgap_name] = SpectralData(bandgap_df, bandgap_metadata)
            if not self._workflow_mode:
                self.dataLoaded.emit(bandgap_name)

            # --- Doping dataset ---
            doping_base = self._extract_clean_base_name(dataset_name)
            doping_convention = self._apply_naming_convention(dataset_name, operation="Doping")
            doping_df = pd.DataFrame({
                'Spectrum Index': range(num_spectra),
                'Doping Type': doping_numeric,
                'Doping Offset (V)': doping_offsets,
                'Valid': valid_flags
            })

            doping_csv = self._ensure_output_dir('curves') / f"{doping_convention}.csv"
            doping_df.to_csv(doping_csv, index=False)

            doping_name = f"{doping_base} - Doping"
            doping_metadata = SpectralMetadata(
                source_type="doping",
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units={'independent': 'Index', 'dependent': 'V'},
                additional_info={
                    'original': dataset_name,
                    'original_source_type': spectral_data.metadata.source_type,
                    'resolution': resolution,
                    'valid_count': int(np.sum(valid_flags)),
                    'total_count': num_spectra
                },
                data_type='flat'
            )
            self._datasets[doping_name] = SpectralData(doping_df, doping_metadata)
            if not self._workflow_mode:
                self.dataLoaded.emit(doping_name)

            logger.info(f"Bandgap/Doping complete: {int(np.sum(valid_flags))}/{num_spectra} valid spectra")
            return str(bandgap_csv)

        except Exception as e:
            logger.error(f"Bandgap/Doping error: {e}", exc_info=True)
            self.errorOccurred.emit("Bandgap/Doping Error", str(e))
            return ""

    # ========================================================================
    # Dirac Point Estimator
    # Algorithms adapted from ststools by Rafael Reis
    # (https://github.com/rafinhareis/ststools)
    # ========================================================================

    def estimate_dirac_point(self, task, dataset_name: str,
                             left_min: float = -1.0,
                             left_max: float = -0.2,
                             right_min: float = 0.2,
                             right_max: float = 1.0,
                             smoothing: float = 1.0,
                             smoothing_method: str = 'Savgol',
                             auto_detect: bool = False) -> str:
        """
        Estimate Dirac point per spectrum via linear slope intersection.

        Pipeline: validate -> smooth -> derivative -> normalize -> fit two lines -> intersection.
        Output is flat_data with columns: Spectrum Index, Dirac Voltage (V), Dirac LDOS,
        Left Slope, Left Intercept, Right Slope, Right Intercept, Left Fit R\u00b2, Right Fit R\u00b2,
        Left Range Min (V), Left Range Max (V), Right Range Min (V), Right Range Max (V).

        If auto_detect=True, fit ranges are determined per-spectrum using bandgap edge detection
        instead of using the fixed global left/right ranges.
        """
        from src.backend.sts_algorithms import (
            numerical_derivative, normalize_ldos, validate_ldos,
            fit_dirac_point, auto_detect_dirac_ranges
        )
        try:
            if dataset_name not in self._datasets:
                self.errorOccurred.emit("Error", "Dataset not found")
                return ""

            spectral_data = self._datasets[dataset_name]
            independent_var = spectral_data.independent_var
            spectra = spectral_data.spectra
            num_spectra = spectra.shape[1]

            logger.info(f"Estimating Dirac point for {dataset_name}: {num_spectra} spectra "
                        f"(auto_detect={auto_detect})")

            # Result arrays
            dirac_xs = np.full(num_spectra, np.nan)
            dirac_ys = np.full(num_spectra, np.nan)
            left_slopes = np.full(num_spectra, np.nan)
            right_slopes = np.full(num_spectra, np.nan)
            left_r2s = np.full(num_spectra, np.nan)
            right_r2s = np.full(num_spectra, np.nan)
            left_intercepts = np.full(num_spectra, np.nan)
            right_intercepts = np.full(num_spectra, np.nan)
            fit_left_mins = np.full(num_spectra, np.nan)
            fit_left_maxs = np.full(num_spectra, np.nan)
            fit_right_mins = np.full(num_spectra, np.nan)
            fit_right_maxs = np.full(num_spectra, np.nan)

            for i in range(num_spectra):
                if task.cancelled:
                    return ""
                task.progress = i / num_spectra

                y = spectra.iloc[:, i].values.copy()
                x = independent_var.copy()

                # 1. Validate
                is_valid, reason = validate_ldos(x, y)
                if not is_valid:
                    continue

                # 2. Smooth if requested
                if smoothing > 0 and smoothing_method != 'None':
                    window = max(3, int(len(x) * smoothing / 100.0))
                    if window % 2 == 0:
                        window += 1
                    window = min(window, len(x) - 1)
                    if window >= 3:
                        if smoothing_method == 'Savgol':
                            poly_order = min(3, window - 1)
                            y = signal.savgol_filter(y, window, poly_order)
                        elif smoothing_method == 'Moving Avg':
                            y = np.convolve(y, np.ones(window) / window, mode='same')

                # 3. Numerical derivative -> dI/dV
                dx, dy = numerical_derivative(x, y)
                if len(dx) < 3:
                    continue

                # 4. Normalize LDOS
                dx_norm, dy_norm = normalize_ldos(dx, dy)

                # 5. Determine fit ranges
                if auto_detect:
                    try:
                        lmin, lmax, rmin, rmax = auto_detect_dirac_ranges(dx_norm, dy_norm)
                        # Fallback if auto-detect returns degenerate intervals
                        if lmin >= lmax or rmin >= rmax:
                            lmin, lmax, rmin, rmax = left_min, left_max, right_min, right_max
                    except Exception:
                        lmin, lmax, rmin, rmax = left_min, left_max, right_min, right_max
                else:
                    lmin, lmax, rmin, rmax = left_min, left_max, right_min, right_max

                # 6. Fit Dirac point
                result = fit_dirac_point(
                    dx_norm, dy_norm,
                    left_range=(lmin, lmax),
                    right_range=(rmin, rmax)
                )
                dirac_xs[i] = result[0]
                dirac_ys[i] = result[1]
                left_slopes[i] = result[2]
                right_slopes[i] = result[3]
                left_r2s[i] = result[4]
                right_r2s[i] = result[5]
                left_intercepts[i] = result[6]
                right_intercepts[i] = result[7]
                fit_left_mins[i] = lmin
                fit_left_maxs[i] = lmax
                fit_right_mins[i] = rmin
                fit_right_maxs[i] = rmax

            # Build output DataFrame with user-friendly column names
            output_df = pd.DataFrame({
                'Spectrum Index': range(num_spectra),
                'Dirac Voltage (V)': dirac_xs,
                'Dirac LDOS': dirac_ys,
                'Left Slope': left_slopes,
                'Left Intercept': left_intercepts,
                'Right Slope': right_slopes,
                'Right Intercept': right_intercepts,
                'Left Fit R\u00b2': left_r2s,
                'Right Fit R\u00b2': right_r2s,
                'Left Range Min (V)': fit_left_mins,
                'Left Range Max (V)': fit_left_maxs,
                'Right Range Min (V)': fit_right_mins,
                'Right Range Max (V)': fit_right_maxs
            })

            base_name = self._extract_clean_base_name(dataset_name)
            convention_name = self._apply_naming_convention(dataset_name, operation="Dirac_Point")

            # Save CSV
            output_path = self._ensure_output_dir('curves') / f"{convention_name}.csv"
            output_df.to_csv(output_path, index=False)

            # Create SpectralData (flat_data compatible)
            friendly_name = f"{base_name} - Dirac Point"
            metadata = SpectralMetadata(
                source_type="diracpoint_flat",
                dimensions=spectral_data.metadata.dimensions,
                scan_mode=spectral_data.metadata.scan_mode,
                units={'independent': 'Index', 'dependent': 'V'},
                additional_info={
                    'original': dataset_name,
                    'original_source_type': spectral_data.metadata.source_type,
                    'left_range': (left_min, left_max),
                    'right_range': (right_min, right_max),
                    'smoothing': smoothing,
                    'auto_detect': auto_detect
                },
                data_type='flat'
            )
            result_data = SpectralData(output_df, metadata)
            self._datasets[friendly_name] = result_data
            if not self._workflow_mode:
                self.dataLoaded.emit(friendly_name)

            logger.info(f"Dirac Point estimation complete for {num_spectra} spectra")
            return str(output_path)

        except Exception as e:
            logger.error(f"Dirac Point error: {e}", exc_info=True)
            self.errorOccurred.emit("Dirac Point Error", str(e))
            return ""
