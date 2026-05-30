"""
Background subtraction for luminescence / Raman spectra.

A background dataset (typically acquired with the laser shutter closed, or
on a region with no sample) is subtracted from each spectral dataset to
remove CCD dark current, scattered-light contributions, and other
instrument-only signals.

X-axis handling
---------------
The signal and background axes don't always exactly match — the user may
have acquired the background on a slightly different range, or with a
different number of bins. The helper handles three cases:

1. **Identical axes** — straight subtraction column by column.
2. **Background covers signal range** — interpolate the background's mean
   spectrum onto the signal axis, then subtract.
3. **Partial overlap** — truncate both to the overlap interval (with the
   signal's sample spacing preserved by interpolation of the background)
   and emit a warning.

The background is reduced to a single 1-D spectrum (the mean across all
its columns) before subtraction. This matches the standard practice of
treating "background" as a single reference acquisition.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd

from ..models.spectral_data import SpectralData, SpectralMetadata

logger = logging.getLogger(__name__)


@dataclass
class BackgroundSubtractionResult:
    """Outcome of a single dataset−background subtraction.

    ``truncated`` is True when the signal axis was clipped to the overlap
    interval with the background axis; ``overlap_range`` is the
    ``(x_min, x_max)`` of the interval that survived.
    """
    corrected: SpectralData
    truncated: bool
    overlap_range: Tuple[float, float]
    samples_kept: int


def subtract_background(
    signal: SpectralData,
    background: SpectralData,
) -> BackgroundSubtractionResult:
    """Subtract the mean ``background`` spectrum from each spectrum in ``signal``.

    Parameters
    ----------
    signal
        Dataset to correct (one or more columns of spectra).
    background
        Reference background dataset; its mean spectrum across columns is
        used as the per-bin background. Axis is auto-aligned to ``signal``.

    Returns
    -------
    BackgroundSubtractionResult
        Holds the corrected dataset, a flag indicating whether truncation
        was needed, and the surviving overlap range.
    """
    sig_x = np.asarray(signal.independent_var, dtype=np.float64)
    bg_x = np.asarray(background.independent_var, dtype=np.float64)
    if sig_x.size == 0:
        raise ValueError("Signal dataset has an empty axis")
    if bg_x.size == 0:
        raise ValueError("Background dataset has an empty axis")

    bg_mean = np.asarray(background.spectra.values, dtype=np.float64).mean(axis=1)

    # Overlap interval. We treat the axes as possibly-increasing or
    # decreasing — sort both for the overlap math and project back at the end.
    sig_min, sig_max = float(sig_x.min()), float(sig_x.max())
    bg_min, bg_max = float(bg_x.min()), float(bg_x.max())
    x_lo = max(sig_min, bg_min)
    x_hi = min(sig_max, bg_max)
    if x_hi <= x_lo:
        raise ValueError(
            f"Signal and background axes do not overlap "
            f"(signal {sig_min}..{sig_max}, background {bg_min}..{bg_max})."
        )

    # Mask signal samples that lie within the overlap.
    overlap_mask = (sig_x >= x_lo) & (sig_x <= x_hi)
    truncated = not overlap_mask.all()
    sig_x_kept = sig_x[overlap_mask]
    if sig_x_kept.size < 2:
        raise ValueError("Overlap interval contains fewer than 2 samples")

    # Interpolate the background to the (kept) signal samples. Use ascending
    # axes for np.interp; recover original order via indices.
    bg_sort = np.argsort(bg_x)
    bg_resampled = np.interp(sig_x_kept, bg_x[bg_sort], bg_mean[bg_sort])

    sig_values = np.asarray(signal.spectra.values, dtype=np.float64)
    sig_values_kept = sig_values[overlap_mask, :]
    corrected_values = sig_values_kept - bg_resampled[:, None]

    new_df = pd.DataFrame(corrected_values, columns=signal.spectra.columns)
    new_df.insert(0, signal.independent_var_name, sig_x_kept)

    extra = dict(signal.metadata.additional_info or {})
    extra['background_subtraction'] = {
        'truncated': bool(truncated),
        'overlap_range': (float(x_lo), float(x_hi)),
        'samples_kept': int(sig_x_kept.size),
        'background_source': str(extra.get('source_file', '')) or 'in-memory',
    }
    new_metadata = SpectralMetadata(
        source_type=signal.metadata.source_type,
        dimensions=signal.metadata.dimensions,
        scan_mode=signal.metadata.scan_mode,
        units=dict(signal.metadata.units or {}),
        acquisition_date=signal.metadata.acquisition_date,
        additional_info=extra,
        data_type=signal.metadata.data_type,
    )

    if truncated:
        logger.info(
            "Background subtraction truncated to overlap %.4f..%.4f "
            "(%d/%d samples kept)",
            x_lo, x_hi, sig_x_kept.size, sig_x.size,
        )

    return BackgroundSubtractionResult(
        corrected=SpectralData(new_df, new_metadata),
        truncated=truncated,
        overlap_range=(float(x_lo), float(x_hi)),
        samples_kept=int(sig_x_kept.size),
    )
