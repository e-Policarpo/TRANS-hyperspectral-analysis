"""
Additional Tool Implementations
Extension of AppBackend with remaining analysis tools
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from scipy import signal, interpolate, optimize
from PIL import Image
import logging

from src.models.spectral_data import SpectralData, SpectralMetadata

logger = logging.getLogger(__name__)


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
                    'derivative_order': order,
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

    def _als_baseline(self, y, lam=1e5, p=0.01, niter=10):
        """
        Asymmetric Least Squares baseline correction.

        This method iteratively fits a smooth baseline that stays below the peaks,
        making it ideal for spectroscopy data where you want to preserve peak features.

        Parameters:
        -----------
        y : array
            Input spectrum
        lam : float
            Smoothness parameter (larger = smoother baseline). Default 1e5.
        p : float
            Asymmetry parameter (smaller = baseline pushed below peaks). Default 0.01.
        niter : int
            Number of iterations. Default 10.

        Returns:
        --------
        baseline : array
            Estimated baseline
        """
        from scipy import sparse
        from scipy.sparse.linalg import spsolve

        L = len(y)
        D = sparse.diags([1, -2, 1], [0, -1, -2], shape=(L, L - 2))
        D = lam * D.dot(D.T)
        w = np.ones(L)

        for _ in range(niter):
            W = sparse.spdiags(w, 0, L, L)
            Z = W + D
            z = spsolve(Z, w * y)
            w = p * (y > z) + (1 - p) * (y < z)

        return z

    def _rubberband_baseline(self, x, y):
        """
        Rubber band baseline correction using convex hull.

        Creates a baseline by stretching a "rubber band" under the spectrum,
        touching only the lowest points. Good for spectra with broad features.

        Parameters:
        -----------
        x : array
            Independent variable (e.g., voltage)
        y : array
            Spectrum values

        Returns:
        --------
        baseline : array
            Estimated baseline
        """
        from scipy.spatial import ConvexHull

        # Create points for convex hull (flip y to get lower envelope)
        points = np.column_stack([x, -y])

        try:
            hull = ConvexHull(points)
            # Get vertices on the lower envelope (which is upper envelope of -y)
            hull_points = points[hull.vertices]
            # Sort by x
            hull_points = hull_points[np.argsort(hull_points[:, 0])]
            # Interpolate to get baseline at all x points
            baseline = -np.interp(x, hull_points[:, 0], hull_points[:, 1])
        except Exception:
            # Fallback to linear if convex hull fails
            baseline = np.linspace(y[0], y[-1], len(y))

        return baseline

    def _endpoint_baseline(self, x, y, n_points=10, degree=1):
        """
        Endpoint-based baseline correction.

        Fits a polynomial only to the endpoints of the spectrum, preserving
        features in the middle. Ideal for STS data where you want to remove
        a linear/polynomial trend but keep the peaks.

        Parameters:
        -----------
        x : array
            Independent variable
        y : array
            Spectrum values
        n_points : int
            Number of points to use from each end. Default 10.
        degree : int
            Polynomial degree for the fit. Default 1 (linear).

        Returns:
        --------
        baseline : array
            Estimated baseline
        """
        # Use points from both ends
        n = min(n_points, len(y) // 4)  # Don't use more than 25% from each end

        x_ends = np.concatenate([x[:n], x[-n:]])
        y_ends = np.concatenate([y[:n], y[-n:]])

        coeffs = np.polyfit(x_ends, y_ends, degree)
        baseline = np.polyval(coeffs, x)

        return baseline

    def fit_curves(self, task, dataset_name: str, fit_type: str, degree: int = 2,
                   als_lambda: float = 1e5, als_p: float = 0.01) -> str:
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
                    coeffs = np.polyfit(independent_var, spectrum, degree)
                    baseline = np.polyval(coeffs, independent_var)
                    fit_params_list.append({
                        'spectrum_index': i,
                        'fit_type': fit_type,
                        **{f'coeff_{j}': c for j, c in enumerate(coeffs)}
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
                    baseline = self._als_baseline(spectrum, lam=als_lambda, p=als_p)
                    fit_params_list.append({
                        'spectrum_index': i,
                        'fit_type': fit_type,
                        'lambda': als_lambda,
                        'p': als_p
                    })
                elif fit_type == 'rubberband':
                    # Convex hull rubber band
                    baseline = self._rubberband_baseline(independent_var, spectrum)
                    fit_params_list.append({
                        'spectrum_index': i,
                        'fit_type': fit_type
                    })
                elif fit_type == 'endpoints':
                    # Fit only to endpoints - good for STS
                    baseline = self._endpoint_baseline(independent_var, spectrum,
                                                       n_points=max(5, len(spectrum)//20),
                                                       degree=degree)
                    fit_params_list.append({
                        'spectrum_index': i,
                        'fit_type': fit_type,
                        'degree': degree
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

    # ========================================================================
    # Map Generator
    # ========================================================================

    def generate_map(self, task, flat_dataset_name: str, value_index: int = 0) -> str:
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

            # Verify data length matches dimensions
            expected_len = dim_h * dim_v
            actual_len = len(flat_values)

            # Handle multi-channel SNOM data: if data length is a multiple of expected,
            # it might contain multiple channels concatenated
            if actual_len != expected_len:
                # Check if it's a clean multiple (e.g., 2x for amplitude+phase)
                if actual_len % expected_len == 0:
                    n_channels = actual_len // expected_len
                    logger.warning(f"Data length {actual_len} is {n_channels}x expected {expected_len}. "
                                 f"Using first channel only (may indicate multi-channel data)")
                    # Take only first channel's worth of data
                    flat_values = flat_values[:expected_len]
                else:
                    raise ValueError(f"Data length {actual_len} doesn't match "
                                   f"dimensions {dim_h}x{dim_v}={expected_len} and is not a clean multiple")

            # Reconstruct map with proper meander correction (matching old TRANS_v3 behavior)
            # The old code manually reversed odd rows during map creation
            map_data = np.zeros((dim_v, dim_h))
            index = 0

            for row in range(dim_v):
                # Flip vertically: bottom row becomes top row
                real_row = dim_v - row - 1

                # Check if original data had meander pattern
                # If data was already meander-corrected, use straight indexing
                # If not, reverse odd rows
                scan_mode = spectral_data.metadata.scan_mode
                was_corrected = spectral_data.metadata.additional_info.get('meander_corrected', False)

                if scan_mode == 'meander' and not was_corrected:
                    # Reverse odd rows for uncorrected meander data
                    if row % 2 == 1:
                        map_data[real_row, :] = flat_values[index:index + dim_h][::-1]
                    else:
                        map_data[real_row, :] = flat_values[index:index + dim_h]
                else:
                    # Data already corrected or not meander - use straight indexing
                    map_data[real_row, :] = flat_values[index:index + dim_h]

                index += dim_h

            # Create output path base with clean name
            base_name = self._extract_clean_base_name(flat_dataset_name)
            file_safe_name = self._sanitize_filename(base_name)

            # Try to get interval info if available (for integrated data), otherwise use value column name
            intervals = spectral_data.metadata.additional_info.get('intervals', [])
            if intervals and value_index < len(intervals):
                interval_info = intervals[value_index]
                value_str = f"{interval_info[0]:.3f}_{interval_info[1]:.3f}"
            else:
                value_str = f"val{value_index}"
            map_basename = f"{file_safe_name}_Map_{value_str}"
            output_base = self._ensure_output_dir('maps') / map_basename

            # Save as images
            self._save_map_images(map_data, output_base)

            # Save numerical data as CSV
            csv_path = output_base.with_suffix('.csv')
            pd.DataFrame(map_data).to_csv(csv_path, index=False)

            logger.info(f"Map saved with base name: {output_base}")
            return str(output_base)

        except Exception as e:
            logger.error(f"Map generation error: {e}", exc_info=True)
            raise

    def _save_map_images(self, map_data: np.ndarray, output_base: Path):
        """Save map data as TIFF and CSV only (no PNG outputs)."""
        import tifffile

        # Save as 16-bit TIFF (preserving more precision than 8-bit)
        # Use string concatenation instead of with_suffix() to avoid issues
        # when basename contains dots (e.g., "Map_-0.500_-0.300" would have .300 treated as suffix)
        tiff_path = Path(str(output_base) + '.tiff')
        # Normalize to 16-bit range for TIFF
        if np.ptp(map_data) > 0:
            normalized_map = 65535 * (map_data - np.min(map_data)) / np.ptp(map_data)
        else:
            normalized_map = np.zeros_like(map_data)
        image_data = normalized_map.astype(np.uint16)
        tifffile.imwrite(str(tiff_path), image_data)
        logger.info(f"TIFF saved to: {tiff_path}")

        # Save as CSV for raw data
        csv_path = Path(str(output_base) + '.csv')
        np.savetxt(str(csv_path), map_data, delimiter=',', fmt='%.6e')
        logger.info(f"CSV saved to: {csv_path}")

        # Verify files were created
        if not tiff_path.exists():
            logger.error(f"TIFF file was not created at: {tiff_path}")
        if not csv_path.exists():
            logger.error(f"CSV file was not created at: {csv_path}")

    def generate_all_maps(self, task, flat_dataset_name: str) -> list:
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
                map_path = self.generate_map(task, flat_dataset_name, value_index=idx)
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

    def find_peaks(self, task, dataset_name: str, prominence: float = 0.1,
                  min_distance: int = 5, fwhm_multiplier: float = 1.5) -> dict:
        """
        Find and index peaks in spectral data, returning FWHM-based integration intervals.

        Parameters:
        -----------
        dataset_name : str
            Dataset to analyze
        prominence : float
            Minimum peak prominence
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

            # Debug logging
            logger.info(f"PeakFinder: Dataset has {spectra.shape[1]} spectra, {spectra.shape[0]} points each")
            logger.info(f"PeakFinder: Data range: min={np.nanmin(spectra):.6f}, max={np.nanmax(spectra):.6f}")
            logger.info(f"PeakFinder: X range: {independent_var[0]:.4f} to {independent_var[-1]:.4f}")
            logger.info(f"PeakFinder: Using prominence={prominence}, min_distance={min_distance}")

            # Storage for peak data
            all_peaks = []
            raw_intervals = []  # Store all intervals before merging

            # Find peaks in each spectrum
            for i, spectrum in enumerate(spectra.T):
                if task.cancelled:
                    return {'peaks_path': '', 'intervals': []}

                peaks, properties = signal.find_peaks(
                    spectrum,
                    prominence=prominence,
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

            return {
                'peaks_path': str(output_path),
                'intervals': merged_intervals
            }

        except Exception as e:
            logger.error(f"Peak finding error: {e}", exc_info=True)
            self.errorOccurred.emit("Peak Finding Error", str(e))
            return {'peaks_path': '', 'intervals': []}

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
            import tifffile
            filename = Path(image_path).stem
            # Clean up the filename using helper
            base_name = self._extract_clean_base_name(filename)
            file_safe_name = self._sanitize_filename(base_name)
            output_path = self._ensure_output_dir('discretized') / f"{file_safe_name}_discretized_{target_x}x{target_y}.tiff"
            tifffile.imwrite(str(output_path), discretized)

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
                        threshold: float = 0.5,
                        correct_periodic: bool = False) -> str:
        """
        Filter bad spectra based on saturation, noise, linear artifact, and periodic noise heuristics.

        Returns path to the text report. Creates three new datasets:
        '{base} - Good Data', '{base} - Bad Data', and '{base} - FFT Spectra'.
        """
        from src.backend.sts_algorithms import (
            detect_saturation, detect_noise, detect_linear_artifact,
            detect_periodic_noise, correct_periodic_noise,
            detect_partial_noise
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
                        f"weights=({weight_saturation}, {weight_noise}, {weight_linear}, {weight_periodic}, {weight_partial_noise}), "
                        f"threshold={threshold}, correct_periodic={correct_periodic}")

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
                f"linear={weight_linear}, periodic={weight_periodic}, partial_noise={weight_partial_noise}",
                f"Threshold: {threshold}{correction_note}",
                "",
                f"{'Index':>6} {'Sat':>8} {'Noise':>8} {'Linear':>8} {'Periodic':>10} {'Partial':>10} {'Combined':>10} {'Trigger':>12} {'Status':>8}",
                "-" * 90,
            ]

            for i in range(num_spectra):
                if task.cancelled:
                    return ""
                task.progress = i / num_spectra

                spectrum = spectra.iloc[:, i].values
                col_name = spectra.columns[i]

                sat_score = detect_saturation(spectrum)
                noise_score = detect_noise(spectrum)
                lin_score = detect_linear_artifact(independent_var, spectrum)
                periodic_score, fft_mag, _bg, peak_mask = detect_periodic_noise(spectrum)
                partial_score = detect_partial_noise(independent_var, spectrum)

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

                report_lines.append(
                    f"{i:>6} {sat_score:>8.3f} {noise_score:>8.3f} {lin_score:>8.3f} "
                    f"{periodic_score:>10.3f} {partial_score:>10.3f} {combined:>10.3f} {trigger:>12} {status:>8}"
                )

            report_lines.append("")
            report_lines.append(f"Good spectra: {len(good_indices)}")
            report_lines.append(f"Bad spectra: {len(bad_indices)}")
            if correct_periodic:
                report_lines.append(f"Spectra with periodic correction applied: {len(corrected_spectra)}")

            base_name = self._extract_clean_base_name(dataset_name)
            file_safe_name = self._sanitize_filename(base_name)

            # Build good dataset (with optional periodic correction)
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
                        columns=[f"Spectrum_{i}" for i in range(len(good_indices))]
                    )
                else:
                    good_df = pd.DataFrame(
                        spectra[good_cols].values,
                        columns=[f"Spectrum_{i}" for i in range(len(good_indices))]
                    )
                good_df.insert(0, spectral_data.independent_var_name, independent_var)

                good_metadata = SpectralMetadata(
                    source_type=spectral_data.metadata.source_type,
                    dimensions=spectral_data.metadata.dimensions,
                    scan_mode=spectral_data.metadata.scan_mode,
                    units=spectral_data.metadata.units.copy(),
                    additional_info={
                        'original': dataset_name,
                        'filter': 'good',
                        'count': len(good_indices),
                        'periodic_corrected': correct_periodic
                    }
                )
                self._datasets[good_name] = SpectralData(good_df, good_metadata)
                if not self._workflow_mode:
                    self.dataLoaded.emit(good_name)
            else:
                report_lines.append("No good spectra found — 'Good Data' dataset not created.")

            # Build bad dataset (always original, uncorrected spectra)
            bad_name = f"{base_name} - Bad Data"
            if bad_indices:
                bad_cols = [spectra.columns[i] for i in bad_indices]
                bad_df = pd.DataFrame(
                    spectra[bad_cols].values,
                    columns=[f"Spectrum_{i}" for i in range(len(bad_indices))]
                )
                bad_df.insert(0, spectral_data.independent_var_name, independent_var)

                bad_metadata = SpectralMetadata(
                    source_type=spectral_data.metadata.source_type,
                    dimensions=spectral_data.metadata.dimensions,
                    scan_mode=spectral_data.metadata.scan_mode,
                    units=spectral_data.metadata.units.copy(),
                    additional_info={
                        'original': dataset_name,
                        'filter': 'bad',
                        'count': len(bad_indices)
                    }
                )
                self._datasets[bad_name] = SpectralData(bad_df, bad_metadata)
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
                    self._datasets[fft_name] = SpectralData(fft_df, fft_metadata)
                    if not self._workflow_mode:
                        self.dataLoaded.emit(fft_name)

            # Save report
            report_text = "\n".join(report_lines)
            output_path = self._ensure_output_dir('curves') / f"{file_safe_name}_filter_report.txt"
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
                source_type="bandgap_flat",
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
                source_type="doping_flat",
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
