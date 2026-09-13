"""
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy

Sequential multi-dataset execution for tools.

A tool that processes one dataset at a time can be handed several datasets
at once. They are processed **one after another, in the order the user
picked them** — never merged — so every result traces back to exactly one
input and the per-input output names stay unambiguous.

Adding another tool to the feature is one entry in ``BATCH_TOOLS`` plus
swapping that tool's dataset combo for a ``DatasetMultiSelect`` in QML; no
new backend slot is needed, because ``AppBackend.runToolOnDatasets`` drives
every registered tool through this module.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _as_bool(value: Any) -> bool:
    """QML hands booleans over faithfully, but a saved workflow or a REST-ish
    caller may pass the strings 'true'/'false'."""
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def _as_int(value: Any) -> int:
    """QML numbers arrive as floats; SciPy/NumPy arguments need real ints."""
    return int(float(value))


@dataclass(frozen=True)
class BatchToolSpec:
    """How to run one registered tool over a single dataset."""

    label: str                       # shown in status text and output registration
    method: str                      # ToolImplementations method to call
    takes_task: bool = False         # method's first argument is the worker task
    params: Dict[str, Callable[[Any], Any]] = field(default_factory=dict)
    defaults: Dict[str, Any] = field(default_factory=dict)
    # Tools whose knobs are a map rather than keyword arguments take the whole
    # dict through untouched and coerce it themselves.
    params_as_dict: bool = False
    # Backend method that handles one dataset's result. Tools returning a
    # dict of datasets and paths need their own registration (maps to open,
    # datasets to publish); without one, a plain path string is registered.
    completion: Optional[str] = None

    def coerce(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert the QML parameter map into keyword arguments.

        Unknown keys are dropped rather than forwarded: the QML side may
        carry UI-only state, and an unexpected keyword would be a TypeError
        at call time.
        """
        supplied = dict(params or {})
        out = dict(self.defaults)
        for name, cast in self.params.items():
            if name in supplied and supplied[name] is not None:
                try:
                    out[name] = cast(supplied[name])
                except (TypeError, ValueError):
                    logger.warning("Batch %s: bad value for %r (%r), using default",
                                   self.label, name, supplied[name])
        return out


BATCH_TOOLS: Dict[str, BatchToolSpec] = {
    'map_generator': BatchToolSpec(
        label="Map Generator",
        method="generate_maps_from_spectra",
        takes_task=True,
        params_as_dict=True,
        completion="_on_map_generation_completed",
    ),
    'line_scan_designer': BatchToolSpec(
        label="Line Scan Designer",
        method="design_line_scan",
        takes_task=True,
        params_as_dict=True,
        completion="_on_line_scan_design_completed",
    ),
    'confinement_dimensionality': BatchToolSpec(
        label="Confinement Dimensionality",
        method="analyze_confinement_dimensionality",
        takes_task=True,
        # The knobs are a map -- temperature, modulation, and every peak-search
        # default -- rather than a fixed keyword list, and the tool coerces
        # them itself against CONFINEMENT_DEFAULTS.
        params_as_dict=True,
        # Returns a dict (dataset, table path, and the whole-set coherence
        # statistics), not a path, so it needs its own registration.
        completion="_on_dimensionality_completed",
    ),
    'filter_bad_data': BatchToolSpec(
        label="Filter Bad Data",
        method="filter_bad_data",
        takes_task=True,
        params={'weight_saturation': float, 'weight_noise': float,
                'weight_linear': float, 'weight_periodic': float,
                'weight_partial_noise': float, 'weight_featureless': float,
                'threshold': float, 'correct_periodic': _as_bool,
                'min_structure_ratio': float, 'min_coherence': float,
                'filter_offset_outliers': _as_bool,
                'filter_bandgap_outliers': _as_bool,
                'filter_saturation_outliers': _as_bool,
                'max_offset_outliers': _as_int,
                'max_bandgap_outliers': _as_int,
                'max_saturation_outliers': _as_int,
                'outlier_group_by': str,
                'outlier_intervals': _as_int, 'outlier_z': float},
        defaults={'weight_saturation': 1.0, 'weight_noise': 1.0,
                  'weight_linear': 1.0, 'weight_periodic': 1.0,
                  'weight_partial_noise': 1.0, 'weight_featureless': 1.0,
                  'threshold': 0.5, 'correct_periodic': False,
                  'min_structure_ratio': 3.0, 'min_coherence': 0.12,
                  # Outlier removal is opt-in: it deletes curves that are
                  # individually sound, which is only right for a set of
                  # repetitions the user means to average.
                  'filter_offset_outliers': False,
                  'filter_bandgap_outliers': False,
                  'filter_saturation_outliers': False,
                  'max_offset_outliers': 5, 'max_bandgap_outliers': 5,
                  'max_saturation_outliers': 5,
                  'outlier_group_by': 'point',
                  'outlier_intervals': 8, 'outlier_z': 3.5},
    ),
    'average_curves': BatchToolSpec(
        label="Average Curves",
        method="average_curves",
        takes_task=True,
    ),
    'smooth_curves': BatchToolSpec(
        label="Curve Smoothing",
        method="smooth_curves",
        takes_task=True,
        params={'window_size': _as_int, 'poly_order': _as_int,
                'smoothing_type': str},
        defaults={'window_size': 11, 'poly_order': 3,
                  'smoothing_type': 'savgol'},
    ),
    'fft_1d': BatchToolSpec(
        label="1D FFT",
        method="_do_fft1D",
        takes_task=True,
        params={'window': str, 'detrend': _as_bool, 'one_sided': _as_bool,
                'power_spectrum': _as_bool},
        defaults={'window': 'none', 'detrend': True, 'one_sided': True,
                  'power_spectrum': False},
    ),
    'truncate': BatchToolSpec(
        label="Truncate Data",
        method="_do_truncate_data",
        takes_task=True,
        params={'min_val': float, 'max_val': float},
    ),
    'curve_background_flattening': BatchToolSpec(
        # Was "Curve Fitting": the tool fits a baseline and subtracts it, so
        # the name now says what comes out rather than how it is done.
        label="Curve Background Flattening",
        method="fit_curves",
        takes_task=True,
        params={'fit_type': str, 'degree': _as_int, 'basis': str},
        defaults={'fit_type': 'polynomial', 'degree': 2, 'basis': 'power'},
    ),
    'gradient_filter': BatchToolSpec(
        # The "dataset" here is a browser ref — ``map:<id>``, ``image:<id>``
        # or a bare file path — resolved by the tool itself.
        label="Gradient Filter",
        method="apply_gradient_filter",
        takes_task=True,
        params={'method': str},
        defaults={'method': 'sobel'},
        completion="_on_gradient_completed",
    ),
    'multi_peak_fit': BatchToolSpec(
        label="Multi-Peak Fitting",
        method="fit_multipeak_dataset",
        takes_task=True,
        params={'peak_shape': str, 'n_peaks_auto': _as_int,
                'baseline_degree': _as_int, 'positive_only': _as_bool},
        defaults={'peak_shape': 'gaussian', 'n_peaks_auto': 0,
                  'baseline_degree': 1, 'positive_only': True},
    ),
    'axis_convert': BatchToolSpec(
        label="Unit Converter",
        method="convert_axis_dataset",
        takes_task=True,
        params={'target_unit': str, 'excitation_nm': float},
        defaults={'target_unit': 'eV', 'excitation_nm': 0.0},
        completion="_on_unit_converter_completed",
    ),
    'unit_formula': BatchToolSpec(
        label="Unit Converter",
        method="apply_formula_dataset",
        takes_task=True,
        params={'x_formula': str, 'y_formula': str, 'x_unit': str, 'y_unit': str,
                'x_name': str, 'y_name': str, 'replace': _as_bool},
        defaults={'x_formula': '', 'y_formula': '', 'x_unit': '', 'y_unit': '',
                  'x_name': '', 'y_name': '', 'replace': False},
        completion="_on_unit_converter_completed",
    ),
    'confinement_designer': BatchToolSpec(
        label="Confinement Designer",
        method="design_confinement",
        takes_task=True,
        # The designer's knobs are a map — geometry, symmetry, masses, edges,
        # matching — coerced against DESIGNER_DEFAULTS by the tool itself.
        params_as_dict=True,
        # Returns the candidates (for the panel's list), not a path.
        completion="_on_designer_completed",
    ),
    'derivative': BatchToolSpec(
        label="Derivative Calculator",
        method="calculate_derivative",
        takes_task=False,
        params={'order': _as_int,
                'smooth_before': _as_bool,
                'smooth_after': _as_bool},
        defaults={'order': 1, 'smooth_before': True, 'smooth_after': True},
    ),
}


def get_spec(tool_key: str) -> Optional[BatchToolSpec]:
    return BATCH_TOOLS.get(tool_key)


def run_dataset_batch(backend, task, tool_key: str, dataset_names: List[str],
                      params: Optional[Dict[str, Any]] = None,
                      on_result: Optional[Callable[[Dict[str, Any]], None]] = None
                      ) -> List[Dict[str, Any]]:
    """Run one registered tool over each dataset in turn.

    Parameters
    ----------
    backend : object
        The AppBackend (anything exposing the spec's method and ``_datasets``).
    task : object
        Worker task; ``task.cancelled`` stops the run between datasets and
        ``task.progress`` tracks datasets completed.
    dataset_names : list of str
        Processed in this exact order.

    Returns a list of ``{'dataset', 'output', 'error'}`` — one per dataset
    actually attempted. A dataset that raises does not abort the rest of the
    batch: its failure is recorded and the run continues, so one bad dataset
    can't cost the user the other twenty.
    """
    spec = get_spec(tool_key)
    if spec is None:
        raise ValueError(f"Unknown batch tool: {tool_key!r}")

    names = [n for n in (dataset_names or []) if n]
    if not names:
        return []

    kwargs = spec.coerce(params)
    method = getattr(backend, spec.method)
    results: List[Dict[str, Any]] = []

    logger.info("Batch %s over %d dataset(s): %s", spec.label, len(names), names)

    for i, name in enumerate(names):
        if getattr(task, 'cancelled', False):
            logger.info("Batch %s cancelled after %d/%d datasets",
                        spec.label, i, len(names))
            break

        task.progress = i / len(names)
        # Where this dataset sits in the batch, for a tool that reports its
        # own progress and wants its estimate to cover the whole batch.
        task.batch = (i, len(names), name)
        entry: Dict[str, Any] = {'dataset': name, 'output': '', 'error': ''}
        try:
            if spec.params_as_dict:
                entry['output'] = (method(task, name, dict(params or {}))
                                   if spec.takes_task
                                   else method(name, dict(params or {}))) or ''
            elif spec.takes_task:
                entry['output'] = method(task, name, **kwargs) or ''
            else:
                entry['output'] = method(name, **kwargs) or ''
        except Exception as exc:                      # noqa: BLE001 - reported per dataset
            entry['error'] = str(exc)
            logger.error("Batch %s failed on %r: %s", spec.label, name, exc,
                         exc_info=True)

        results.append(entry)
        if on_result:
            try:
                on_result(entry)
            except Exception:                          # noqa: BLE001
                logger.debug("Batch %s: on_result callback failed", spec.label,
                             exc_info=True)

    task.progress = 1.0
    return results
