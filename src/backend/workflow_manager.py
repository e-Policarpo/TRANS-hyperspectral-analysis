"""
Workflow Manager for TRANS-QML
Handles workflow execution, saving, and loading
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot

from src.utils.naming import pad as _pad

from src.backend.workflow_engine import (
    Workflow, WorkflowNode, Connection, Port, PortType,
    TOOL_DEFINITIONS, create_node_from_tool, get_tool_categories, get_tool_info
)

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Executes a workflow by running nodes in topological order"""

    def __init__(self, app_backend):
        self.app_backend = app_backend
        self.node_outputs: Dict[str, Dict[str, Any]] = {}  # node_id -> {port_id: value}
        self.cancelled = False
        self.workflow_name = ""
        self.original_dataset_name = ""  # Track source dataset for naming outputs
        # Names actually handed out to output nodes this run. Collected as
        # they are produced rather than recomputed at cleanup time, because
        # a naming convention carrying [index] yields a different name on a
        # second call — which used to delete the very datasets it named.
        self.produced_output_names: set = set()
        # One pass per selected dataset when a DatasetInput holds several:
        # {node_id: dataset_name} for the pass being executed.
        self.dataset_overrides: Dict[str, str] = {}
        self._pass_count = 1
        self._pass_index = 0

    def _dataset_batches(self, workflow: Workflow) -> List[Dict[str, str]]:
        """Plan the passes to run, one per selected dataset.

        A ``DatasetInput`` node may hold several datasets (``dataset_names``).
        The whole workflow is then executed once per dataset **in sequence**,
        so each run has exactly one source and its outputs can be named after
        that source — no ambiguity about which input produced which output.

        Returns a list of ``{node_id: dataset_name}`` assignments, one per
        pass. A single-dataset workflow yields one pass, i.e. the behaviour
        the executor has always had.
        """
        per_node: Dict[str, List[str]] = {}
        for node in workflow.nodes:
            if node.tool_name != "DatasetInput":
                continue
            raw = node.parameters.get('dataset_names') or []
            if hasattr(raw, 'toVariant'):      # QJSValue array from QML
                raw = raw.toVariant() or []
            names = [str(n) for n in raw if n]
            if not names:
                single = node.parameters.get('dataset_name')
                names = [single] if single else []
            if names:
                per_node[node.id] = names

        if not per_node:
            return [{}]

        passes = max(len(v) for v in per_node.values())
        if passes == 1:
            return [{nid: v[0] for nid, v in per_node.items()}]

        multi = {nid: v for nid, v in per_node.items() if len(v) > 1}
        if len({len(v) for v in multi.values()}) > 1:
            # Nothing sensible to pair up — say so instead of silently
            # inventing combinations the user never asked for.
            logger.warning(
                "Workflow has dataset inputs with different selection counts "
                "(%s); the shorter ones repeat their last dataset.",
                {nid: len(v) for nid, v in multi.items()})

        plan = []
        for k in range(passes):
            assignment = {}
            for nid, v in per_node.items():
                # A single-dataset input feeds every pass unchanged; a shorter
                # multi-selection holds its last entry.
                assignment[nid] = v[k] if k < len(v) else v[-1]
            plan.append(assignment)
        return plan

    def execute(self, workflow: Workflow, progress_callback: Callable = None) -> Dict[str, Any]:
        """
        Execute a workflow and return results.

        Returns:
        --------
        Dict with 'success', 'results', 'errors' keys
        """
        self.node_outputs.clear()
        self.cancelled = False
        self.workflow_name = workflow.name.replace(" ", "_")
        self.original_dataset_name = ""
        self.produced_output_names = set()
        self.dataset_overrides = {}
        errors = []
        results = {}

        # Validate first
        is_valid, validation_errors = workflow.validate()
        if not is_valid:
            return {
                'success': False,
                'results': {},
                'errors': validation_errors
            }

        # Get execution order
        execution_order = workflow.get_execution_order()
        total_nodes = len(execution_order)

        # One pass per selected dataset — run in sequence, never interleaved.
        batches = self._dataset_batches(workflow)
        self._pass_count = len(batches)
        total_steps = total_nodes * self._pass_count

        logger.info(f"Executing workflow '{workflow.name}' with {total_nodes} nodes"
                    + (f" over {self._pass_count} datasets" if self._pass_count > 1 else ""))

        # Enable workflow mode to suppress intermediate dataset additions to project browser
        self.app_backend._workflow_mode = True

        # A run over several datasets produces a full set of outputs per pass;
        # opening every one of them would bury the workspace, so output nodes
        # register their results without displaying them.
        multi_dataset = len(batches) > 1
        if multi_dataset:
            self.app_backend._suppress_auto_open = True

        # Snapshot datasets before execution for cleanup
        datasets_before = set(self.app_backend._datasets.keys())

        try:
            for pass_index, assignment in enumerate(batches):
                if self.cancelled:
                    # Cancelled between passes: the remaining datasets never
                    # ran, so this is not a successful execution.
                    errors.append("Workflow execution cancelled")
                    break

                # Fresh state per pass: node outputs from the previous dataset
                # must never leak into this one.
                self._pass_index = pass_index
                self.dataset_overrides = assignment
                self.node_outputs.clear()
                self.original_dataset_name = ""

                pass_label = ""
                if self._pass_count > 1:
                    pass_dataset = next(iter(assignment.values()), "")
                    pass_label = f" [{pass_index + 1}/{self._pass_count}: {pass_dataset}]"
                    logger.info(f"Workflow pass {pass_index + 1}/{self._pass_count} "
                                f"over datasets: {list(assignment.values())}")

                for i, node_id in enumerate(execution_order):
                    if self.cancelled:
                        errors.append("Workflow execution cancelled")
                        break

                    node = workflow.get_node(node_id)
                    if not node:
                        continue

                    # Skip comment nodes - they are just for annotations
                    if node.tool_name == "CommentNode":
                        logger.debug(f"Skipping comment node: {node.display_name}")
                        continue

                    if progress_callback:
                        progress_callback(pass_index * total_nodes + i + 1, total_steps,
                                          f"Executing: {node.display_name}{pass_label}")

                    try:
                        # Gather inputs for this node
                        node_inputs = self._gather_inputs(node, workflow)

                        # Execute the node
                        node_result = self._execute_node(node, node_inputs)

                        # Store outputs
                        self.node_outputs[node_id] = node_result

                        # If this is an output node, add to results. With
                        # several datasets the key carries the source, so one
                        # pass can't overwrite another's result.
                        if node.tool_name in ['DatasetOutput', 'MapOutput', 'ImageOutput', 'TableOutput', 'FlatDataOutput', 'TextOutput', 'IntervalOutput']:
                            output_name = node.parameters.get('output_name', f'output_{node_id}')
                            if self._pass_count > 1:
                                output_name = f"{output_name} [{self.original_dataset_name}]"
                            results[output_name] = node_result

                        logger.info(f"Node '{node.display_name}' executed successfully")

                    except Exception as e:
                        error_msg = f"Error executing '{node.display_name}'{pass_label}: {str(e)}"
                        logger.error(error_msg, exc_info=True)
                        errors.append(error_msg)
        finally:
            # Always disable workflow mode when done
            self.app_backend._workflow_mode = False
            if multi_dataset:
                self.app_backend._suppress_auto_open = False

            # Clean up intermediate datasets added during workflow
            datasets_after = set(self.app_backend._datasets.keys())
            intermediate_datasets = datasets_after - datasets_before

            # Names the output nodes actually stored under, across every
            # pass — recomputing them here would drift from what was stored.
            output_names = set(self.produced_output_names)

            # Remove intermediate datasets that aren't final outputs
            for name in intermediate_datasets:
                if name not in output_names:
                    del self.app_backend._datasets[name]
                    logger.debug(f"Cleaned up intermediate dataset: {name}")

            # Emit dataLoaded for each preserved output AFTER cleanup
            # This ensures the Project Browser only sees final outputs, not intermediates
            for name in output_names:
                if name in self.app_backend._datasets:
                    self.app_backend.dataLoaded.emit(name)
                    logger.debug(f"Emitted dataLoaded for output: {name}")

        success = len(errors) == 0
        return {
            'success': success,
            'results': results,
            'errors': errors
        }

    def _gather_inputs(self, node: WorkflowNode, workflow: Workflow) -> Dict[str, Any]:
        """Gather input values for a node from connected outputs"""
        inputs = {}

        # Get input_queue for ordering multi-inputs (if available)
        input_queue = node.parameters.get('input_queue', [])

        for input_port in node.inputs:
            # Find all connections to this input
            connections = []
            for c in workflow.connections:
                if c.target_node_id == node.id and c.target_port_id == input_port.id:
                    connections.append(c)

            if connections:
                if input_port.multi_input:
                    # Gather all connected values as a list with source info
                    values = []
                    for conn in connections:
                        source_outputs = self.node_outputs.get(conn.source_node_id, {})
                        value = source_outputs.get(conn.source_port_id)
                        if value is not None:
                            # Include source info for queue ordering
                            source_node = workflow.get_node(conn.source_node_id)
                            source_name = source_node.display_name if source_node else conn.source_node_id
                            values.append({
                                'value': value,
                                'source_node_id': conn.source_node_id,
                                'source_node_name': source_name,
                                'source_port_id': conn.source_port_id
                            })

                    # Sort values according to input_queue order if available
                    if input_queue:
                        # Create order map from queue (source_node_id -> index)
                        order_map = {q.get('source_node_id'): i for i, q in enumerate(input_queue)}
                        # Sort values: queued items first (by queue order), then unqueued items
                        values.sort(key=lambda v: order_map.get(v['source_node_id'], len(order_map)))
                        logger.debug(f"Multi-input values sorted according to input_queue: {[v['source_node_name'] for v in values]}")

                    inputs[input_port.id] = values
                else:
                    # Single connection - just get the value
                    source_outputs = self.node_outputs.get(connections[0].source_node_id, {})
                    inputs[input_port.id] = source_outputs.get(connections[0].source_port_id)
            elif input_port.default_value is not None:
                inputs[input_port.id] = input_port.default_value

        return inputs

    def _execute_node(self, node: WorkflowNode, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single node and return its outputs"""
        tool_name = node.tool_name
        params = node.parameters
        outputs = {}

        # Route to appropriate tool implementation
        if tool_name == "DatasetInput":
            # This pass's dataset when several were selected, otherwise the
            # node's single dataset.
            dataset_name = self.dataset_overrides.get(node.id) or params.get('dataset_name')
            if dataset_name and dataset_name in self.app_backend._datasets:
                outputs['dataset'] = self.app_backend._datasets[dataset_name]
                # Track original dataset name for output naming
                if not self.original_dataset_name:
                    self.original_dataset_name = dataset_name

        elif tool_name == "FlatDataInput":
            dataset_name = params.get('dataset_name')
            if dataset_name and dataset_name in self.app_backend._datasets:
                outputs['flat_data'] = self.app_backend._datasets[dataset_name]

        elif tool_name == "IntervalInput":
            intervals_param = params.get('intervals', []) or []
            intervals = []
            for interval in intervals_param:
                if isinstance(interval, dict):
                    intervals.append(interval)
                elif isinstance(interval, (list, tuple)) and len(interval) >= 2:
                    intervals.append([interval[0], interval[1]])
            outputs['intervals'] = intervals
            logger.info(f"IntervalInput provided {len(intervals)} intervals")

        elif tool_name == "MapInput":
            file_path = params.get('file_path')
            if file_path:
                if Path(file_path).exists():
                    outputs['map'] = file_path
                else:
                    logger.error(f"Map file not found: {file_path}")

        elif tool_name == "ImageInput":
            file_path = params.get('file_path')
            if file_path:
                if Path(file_path).exists():
                    outputs['image'] = file_path
                else:
                    logger.error(f"Image file not found: {file_path}")

        elif tool_name == "Integration":
            dataset = inputs.get('dataset')
            intervals_param = params.get('intervals', [])
            # Also check for intervals from input port (e.g., from PeakFinder)
            intervals_input = inputs.get('intervals', [])

            # Use intervals from input port if available, otherwise from parameter
            intervals_raw = intervals_input if intervals_input else intervals_param

            if dataset and intervals_raw:
                # Validate input is a proper dataset object, not a string
                if isinstance(dataset, str):
                    logger.error(f"Integration received string instead of dataset: {dataset}")
                    return outputs

                # Store dataset temporarily
                dataset_name = self._get_temp_dataset_name(dataset, "integrate")
                self.app_backend._datasets[dataset_name] = dataset

                # Convert intervals to format expected by _do_integrate
                # _do_integrate expects list of dicts with 'lower' and 'upper' keys
                intervals = []
                for interval in intervals_raw:
                    if isinstance(interval, dict):
                        intervals.append(interval)
                    elif isinstance(interval, (list, tuple)) and len(interval) >= 2:
                        intervals.append({'lower': interval[0], 'upper': interval[1]})

                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend._do_integrate(MockTask(), dataset_name, intervals)

                # Get the integrated dataset using friendly name pattern
                base_name = self.app_backend._extract_clean_base_name(dataset_name)
                result_name = f"{base_name} - Integrated"
                if result_name in self.app_backend._datasets:
                    outputs['flat_data'] = self.app_backend._datasets[result_name]
                    outputs['intervals_out'] = intervals_raw  # Pass through intervals

        elif tool_name == "Derivative":
            dataset = inputs.get('dataset')
            if dataset:
                # Validate input is a proper dataset object, not a string
                if isinstance(dataset, str):
                    logger.error(f"Derivative received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset, "derivative")
                self.app_backend._datasets[dataset_name] = dataset

                # calculate_derivative doesn't take a task parameter
                result_path = self.app_backend.calculate_derivative(
                    dataset_name,
                    order=params.get('order', 1),
                    smooth_before=params.get('smooth_before', True),
                    smooth_after=params.get('smooth_after', True)
                )
                # Get the result dataset using friendly name pattern
                base_name = self.app_backend._extract_clean_base_name(dataset_name)
                order_label = "1st Derivative" if params.get('order', 1) == 1 else "2nd Derivative"
                result_name = f"{base_name} - {order_label}"
                if result_name in self.app_backend._datasets:
                    outputs['derivative'] = self.app_backend._datasets[result_name]

        elif tool_name == "CurveSmoothing":
            dataset = inputs.get('dataset')
            if dataset:
                # Validate input is a proper dataset object, not a string
                if isinstance(dataset, str):
                    logger.error(f"CurveSmoothing received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset)
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                self.app_backend.smooth_curves(
                    MockTask(), dataset_name,
                    window_size=params.get('window_size', 11),
                    poly_order=params.get('poly_order', 3),
                    smoothing_type=params.get('smoothing_type', 'savgol')
                )
                # Get the result dataset using friendly name pattern
                base_name = self.app_backend._extract_clean_base_name(dataset_name)
                result_name = f"{base_name} - Smoothed"
                if result_name in self.app_backend._datasets:
                    outputs['smoothed'] = self.app_backend._datasets[result_name]

        elif tool_name == "CosmicRayFilter":
            dataset = inputs.get('dataset')
            if dataset:
                if isinstance(dataset, str):
                    logger.error(f"CosmicRayFilter received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset)
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                self.app_backend.remove_cosmic_rays(
                    MockTask(), dataset_name,
                    threshold_sigmas=params.get('threshold_sigmas', 5.0),
                    window=params.get('window', 5),
                    max_width=params.get('max_width', 2),
                )
                base_name = self.app_backend._extract_clean_base_name(dataset_name)
                result_name = f"{base_name} - CR Cleaned"
                if result_name in self.app_backend._datasets:
                    outputs['cleaned'] = self.app_backend._datasets[result_name]

        elif tool_name == "BackgroundSubtraction":
            signal = inputs.get('signal')
            background = inputs.get('background')
            if signal is not None and background is not None:
                if isinstance(signal, str) or isinstance(background, str):
                    logger.error(
                        "BackgroundSubtraction received string instead of dataset"
                    )
                    return outputs

                signal_name = self._get_temp_dataset_name(signal)
                bg_name = self._get_temp_dataset_name(background)
                self.app_backend._datasets[signal_name] = signal
                self.app_backend._datasets[bg_name] = background

                class MockTask:
                    cancelled = False
                    progress = 0

                self.app_backend.subtract_background_datasets(
                    MockTask(), [signal_name], bg_name,
                )
                base_name = self.app_backend._extract_clean_base_name(signal_name)
                result_name = f"{base_name} - BgSub"
                if result_name in self.app_backend._datasets:
                    outputs['corrected'] = self.app_backend._datasets[result_name]

        elif tool_name == "BaselineEstimate":
            dataset = inputs.get('dataset')
            if dataset:
                if isinstance(dataset, str):
                    logger.error(f"BaselineEstimate received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset, "baseline")
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                result = self.app_backend.estimate_dataset_baseline(
                    MockTask(), dataset_name, params=dict(params))
                for port in ('corrected', 'baseline', 'coefficients'):
                    outputs[port] = result.get(port)

        elif tool_name == "CurveFitting":
            dataset = inputs.get('dataset')
            if dataset:
                # Validate input is a proper dataset object, not a string
                if isinstance(dataset, str):
                    logger.error(f"CurveFitting received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset)
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                self.app_backend.fit_curves(
                    MockTask(), dataset_name,
                    fit_type=params.get('fit_type', 'endpoints'),
                    degree=params.get('degree', 1),
                    als_lambda=params.get('als_lambda', 1e5),
                    als_p=params.get('als_p', 0.01),
                    basis=params.get('basis', 'power')
                )
                # Get the result datasets using friendly name pattern
                base_name = self.app_backend._extract_clean_base_name(dataset_name)
                result_name = f"{base_name} - Baseline Corrected"
                if result_name in self.app_backend._datasets:
                    outputs['corrected'] = self.app_backend._datasets[result_name]
                coeff_name = f"{base_name} - Fit Coefficients"
                if coeff_name in self.app_backend._datasets:
                    coeff_ds = self.app_backend._datasets[coeff_name]
                    outputs['coefficients'] = coeff_ds          # -> DatasetOutput
                    outputs['coefficients_flat'] = coeff_ds      # -> MapGenerator (flat_data)

        elif tool_name == "MapGenerator":
            # MapGenerator generates TIFF maps for all value columns in flat data
            flat_data = inputs.get('flat_data')
            if flat_data:
                # Store flat data temporarily
                dataset_name = self._get_temp_dataset_name(flat_data)
                self.app_backend._datasets[dataset_name] = flat_data

                class MockTask:
                    cancelled = False
                    progress = 0

                # Generate all maps (one per value column/interval)
                map_paths = self.app_backend.generate_all_maps(
                    MockTask(), dataset_name,
                    scan_type=params.get('scan_type', 'auto'))
                outputs['maps'] = map_paths
                logger.info(f"MapGenerator created {len(map_paths)} TIFF maps")

        elif tool_name == "MapAssembly":
            flat_data = inputs.get('flat_data')
            if flat_data is not None:
                if isinstance(flat_data, str):
                    logger.error(f"MapAssembly received string instead of dataset: {flat_data}")
                    return outputs

                flat_name = self._get_temp_dataset_name(flat_data)
                self.app_backend._datasets[flat_name] = flat_data

                # Both extras are optional and answer different questions: the
                # spectra say where the values were measured, the intervals say
                # what energy each column covers.
                source = inputs.get('source')
                source_name = None
                if source is not None and not isinstance(source, str):
                    source_name = self._get_temp_dataset_name(source)
                    self.app_backend._datasets[source_name] = source

                class MockTask:
                    cancelled = False
                    progress = 0

                result = self.app_backend.assemble_maps(
                    MockTask(), flat_name, params=dict(params),
                    source_dataset_name=source_name,
                    intervals=inputs.get('intervals') or [])
                outputs['maps'] = result.get('map_paths', [])
                outputs['interval_map'] = result.get('interval_map_dataset')
                outputs['interval_map_path'] = result.get('interval_map_path', '')
                logger.info("MapAssembly wrote %d map(s)%s", result.get('n_maps', 0),
                            " and the joined interval map"
                            if result.get('interval_map_path') else "")

        elif tool_name == "FFT1D":
            dataset = inputs.get('dataset')
            if dataset:
                dataset_name = self._get_temp_dataset_name(dataset)
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                # _do_fft1D only takes task and dataset_name
                result = self.app_backend._do_fft1D(MockTask(), dataset_name)
                outputs['fft_result'] = result

        elif tool_name == "SpatialAverage":
            # Support multiple dataset and flat_data inputs
            # Note: inputs are already sorted by _gather_inputs according to input_queue order
            datasets_input = inputs.get('datasets', [])  # List of {value, source_node_id, ...}
            flat_data_inputs = inputs.get('flat_data_inputs', [])  # List of {value, source_node_id, ...}

            class MockTask:
                cancelled = False
                progress = 0

            block_x = params.get('block_x', 2)
            block_y = params.get('block_y', 2)

            # Get input queue for enabled/disabled filtering
            input_queue = params.get('input_queue', [])
            # Create quick lookup for enabled status
            enabled_map = {q.get('source_node_id'): q.get('enabled', True) for q in input_queue}

            # Process datasets (already in queue order from _gather_inputs)
            averaged_datasets = []
            processing_order = []
            for input_info in datasets_input:
                source_node_id = input_info.get('source_node_id')
                source_name = input_info.get('source_node_name', 'Unknown')

                # Check if this input is disabled in the queue
                if input_queue and source_node_id in enabled_map and not enabled_map[source_node_id]:
                    logger.debug(f"SpatialAverage: Skipping disabled input from {source_name}")
                    continue  # Skip disabled inputs

                processing_order.append(source_name)
                dataset = input_info.get('value') if isinstance(input_info, dict) else input_info
                if dataset:
                    dataset_name = self._get_temp_dataset_name(dataset)
                    self.app_backend._datasets[dataset_name] = dataset

                    result = self.app_backend._do_spatial_average(
                        MockTask(), dataset_name,
                        discrete_x=block_x,
                        discrete_y=block_y,
                        ignore_empty=params.get('ignore_empty', True),
                        save_intermediate=params.get('save_intermediate', False)
                    )
                    if result:
                        averaged_datasets.append({
                            'value': result,
                            'source_name': source_name
                        })

            # Process flat data (already in queue order from _gather_inputs)
            averaged_flat_data = []
            for input_info in flat_data_inputs:
                source_node_id = input_info.get('source_node_id')
                source_name = input_info.get('source_node_name', 'Unknown')

                # Check if this input is disabled in the queue
                if input_queue and source_node_id in enabled_map and not enabled_map[source_node_id]:
                    logger.debug(f"SpatialAverage: Skipping disabled flat_data input from {source_name}")
                    continue  # Skip disabled inputs

                processing_order.append(source_name)
                flat_data = input_info.get('value') if isinstance(input_info, dict) else input_info
                if flat_data:
                    flat_name = self._get_temp_dataset_name(flat_data)
                    self.app_backend._datasets[flat_name] = flat_data

                    result_flat = self.app_backend._do_spatial_average(
                        MockTask(), flat_name,
                        discrete_x=block_x,
                        discrete_y=block_y,
                        ignore_empty=params.get('ignore_empty', True),
                        save_intermediate=params.get('save_intermediate', False)
                    )
                    if result_flat:
                        averaged_flat_data.append({
                            'value': result_flat,
                            'source_name': source_name
                        })

            outputs['averaged_datasets'] = averaged_datasets
            outputs['averaged_flat_data'] = averaged_flat_data
            logger.info(f"SpatialAverage processed {len(averaged_datasets)} datasets and {len(averaged_flat_data)} flat data inputs")
            if processing_order:
                logger.info(f"SpatialAverage processing order: {' -> '.join(processing_order)}")

        elif tool_name == "TruncateData":
            dataset = inputs.get('dataset')
            if dataset:
                # Validate input is a proper dataset object, not a string
                if isinstance(dataset, str):
                    logger.error(f"TruncateData received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset)
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                # _do_truncate_data uses min_val/max_val not x_min/x_max
                # Use defaults matching workflow_engine.py TOOL_DEFINITIONS
                x_min = params.get('x_min', -1.0)
                x_max = params.get('x_max', 1.0)

                # Skip if invalid range (e.g., both 0.0 or min >= max)
                if x_min >= x_max:
                    logger.warning(f"TruncateData: Invalid range ({x_min}, {x_max}), skipping. Configure valid min/max values.")
                    outputs['truncated'] = dataset  # Pass through unchanged
                    return outputs

                result_path = self.app_backend._do_truncate_data(
                    MockTask(), dataset_name,
                    min_val=x_min,
                    max_val=x_max
                )
                # Get the actual dataset object using friendly name pattern
                base_name = self.app_backend._extract_clean_base_name(dataset_name)
                result_name = f"{base_name} - Truncated ({x_min:.1f} to {x_max:.1f})"
                if result_name in self.app_backend._datasets:
                    outputs['truncated'] = self.app_backend._datasets[result_name]

        elif tool_name == "ColumnSelector":
            dataset = inputs.get('dataset')
            if dataset:
                selected_columns = params.get('selected_columns', [])

                # If no columns selected, pass through unchanged
                if not selected_columns:
                    logger.info("ColumnSelector: No columns selected, passing through unchanged")
                    outputs['filtered'] = dataset
                else:
                    # Filter the dataset to keep only selected columns
                    try:
                        if hasattr(dataset, 'data') and hasattr(dataset.data, 'columns'):
                            df = dataset.data
                            # Always keep the first column (X values) plus selected columns
                            x_col = df.columns[0]
                            cols_to_keep = [x_col] + [c for c in selected_columns if c in df.columns and c != x_col]
                            filtered_df = df[cols_to_keep].copy()

                            # Create new dataset with filtered data
                            from copy import deepcopy
                            filtered_dataset = deepcopy(dataset)
                            filtered_dataset.data = filtered_df
                            outputs['filtered'] = filtered_dataset
                            logger.info(f"ColumnSelector: Kept {len(cols_to_keep)} columns from {len(df.columns)}")
                        else:
                            # Pass through if not a proper dataset
                            outputs['filtered'] = dataset
                            logger.warning("ColumnSelector: Input doesn't have expected structure, passing through")
                    except Exception as e:
                        logger.error(f"ColumnSelector error: {e}")
                        outputs['filtered'] = dataset

        elif tool_name == "PeakFinder":
            dataset = inputs.get('dataset')
            if dataset:
                # Validate input is a proper dataset object, not a string
                if isinstance(dataset, str):
                    logger.error(f"PeakFinder received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset)
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                # find_peaks now returns a dict with 'peaks_path' and 'intervals'.
                # Default prominence=0 → adaptive per-spectrum threshold.
                result = self.app_backend.find_peaks(
                    MockTask(), dataset_name,
                    prominence=params.get('prominence', 0.0),
                    min_distance=params.get('min_distance', 5),
                    fwhm_multiplier=params.get('fwhm_multiplier', 1.5)
                )

                # 'peaks' now carries the peak-table dataset object so it can
                # connect to a DatasetOutput node (the old "table" path was a
                # dead-end — no node could capture it).
                outputs['peaks'] = result.get('dataset')
                outputs['intervals'] = result.get('intervals', [])

        elif tool_name == "ConfinementAnalysis":
            dataset = inputs.get('dataset')
            if dataset:
                if isinstance(dataset, str):
                    logger.error(f"ConfinementAnalysis received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset)
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                # fwhm_multiplier is a tool argument rather than a detection
                # parameter, so it travels separately from the params map.
                detection_params = {k: v for k, v in params.items() if k != 'fwhm_multiplier'}
                result = self.app_backend.analyze_confinement(
                    MockTask(), dataset_name,
                    params=detection_params,
                    fwhm_multiplier=params.get('fwhm_multiplier', 1.5),
                )

                for port, key in (('peak_matrix', 'peak_matrix'),
                                  ('peak_matrix_binned', 'peak_matrix_binned'),
                                  ('peak_matrix_offset', 'peak_matrix_offset'),
                                  ('peak_matrix_binned_offset', 'peak_matrix_binned_offset'),
                                  ('peaks', 'peaks'),
                                  ('corrected', 'corrected'), ('baseline', 'baseline'),
                                  ('coefficients', 'coefficients'), ('peak_count', 'peak_count')):
                    outputs[port] = result.get(key)
                outputs['intervals'] = result.get('intervals', [])

        elif tool_name == "ConfinementDesign":
            dataset = inputs.get('dataset')
            if dataset is not None:
                if isinstance(dataset, str):
                    logger.error(f"ConfinementDesign received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset)
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                result = self.app_backend.design_line_scan(
                    MockTask(), dataset_name, params=dict(params))
                # The table is registered under its own name inside the tool;
                # the port carries the dataset object so a downstream node
                # (Map Assembly, an output) gets it without a lookup.
                table = result.get('dataset')
                outputs['table'] = self.app_backend._datasets.get(table)
                outputs['maps'] = result.get('map_paths', [])
                logger.info("ConfinementDesign: %s",
                            result.get('summary') or result.get('error'))

        elif tool_name == "EnergyBinning":
            peaks = inputs.get('peaks')
            if peaks is not None:
                if isinstance(peaks, str):
                    logger.error(f"EnergyBinning received string instead of dataset: {peaks}")
                    return outputs

                peaks_name = self._get_temp_dataset_name(peaks)
                self.app_backend._datasets[peaks_name] = peaks

                # The source spectra are optional: without them the grid is
                # anchored on the peaks and has no sweep step to be floored at.
                source = inputs.get('dataset')
                source_name = None
                if source is not None and not isinstance(source, str):
                    source_name = self._get_temp_dataset_name(source)
                    self.app_backend._datasets[source_name] = source

                class MockTask:
                    cancelled = False
                    progress = 0

                result = self.app_backend.bin_peak_energies(
                    MockTask(), peaks_name, params=dict(params),
                    source_dataset_name=source_name)
                outputs['intervals'] = result.get('intervals', [])
                outputs['all_bins'] = result.get('all_bins', [])
                outputs['bins'] = result.get('bins')

        elif tool_name == "OccupancyMatrix":
            peaks = inputs.get('peaks')
            if peaks is not None:
                if isinstance(peaks, str):
                    logger.error(f"OccupancyMatrix received string instead of dataset: {peaks}")
                    return outputs

                peaks_name = self._get_temp_dataset_name(peaks)
                self.app_backend._datasets[peaks_name] = peaks

                # Both extras are optional and answer different questions: the
                # spectra give the axis and the columns, the bins replace the
                # axis with a coarser one.
                source = inputs.get('dataset')
                source_name = None
                if source is not None and not isinstance(source, str):
                    source_name = self._get_temp_dataset_name(source)
                    self.app_backend._datasets[source_name] = source

                class MockTask:
                    cancelled = False
                    progress = 0

                result = self.app_backend.build_occupancy_matrix(
                    MockTask(), peaks_name, params=dict(params),
                    source_dataset_name=source_name,
                    intervals=inputs.get('intervals') or [])
                for port in ('matrix', 'matrix_offset', 'peak_count'):
                    outputs[port] = result.get(port)

        elif tool_name == "SpectralFeatures":
            dataset = inputs.get('dataset')
            if dataset:
                if isinstance(dataset, str):
                    logger.error(f"SpectralFeatures received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset)
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                result = self.app_backend.extract_spectral_features(
                    MockTask(), dataset_name, params=dict(params))
                outputs['features'] = result.get('features')

        elif tool_name == "ImageSmoothing":
            image_path = inputs.get('image')
            if image_path:
                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend.smooth_image(
                    MockTask(), image_path,
                    filter_type=params.get('filter_type', 'gaussian'),
                    kernel_size=params.get('kernel_size', 5)
                )
                outputs['smoothed'] = result_path

        elif tool_name == "GradientFilter":
            image_path = inputs.get('image')
            if image_path:
                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend.apply_gradient_filter(
                    MockTask(), image_path,
                    method=params.get('method', 'sobel')
                )
                outputs['gradient'] = result_path

        elif tool_name == "ImageDiscretizer":
            image_path = inputs.get('image')
            if image_path:
                class MockTask:
                    cancelled = False
                    progress = 0

                result = self.app_backend.discretize_image(
                    MockTask(), image_path,
                    method=params.get('method', 'uniform'),
                    n_bins=params.get('n_bins', 5),
                    output_type=params.get('output_type', 'centroids')
                )
                if result:
                    outputs['discretized'] = result.get('image_path')
                    outputs['labels'] = result.get('labels')

        elif tool_name == "DataManipulation":
            # Get inputs
            dataset_a = inputs.get('dataset_a')
            dataset_b = inputs.get('dataset_b')
            flat_a = inputs.get('flat_a')
            flat_b = inputs.get('flat_b')

            # Validate inputs are not strings
            for name, val in [('dataset_a', dataset_a), ('dataset_b', dataset_b),
                              ('flat_a', flat_a), ('flat_b', flat_b)]:
                if val is not None and isinstance(val, str):
                    logger.error(f"DataManipulation received string for {name}: {val}")
                    return outputs

            equation = params.get('equation', '')
            output_name = params.get('output_name', 'Manipulated')

            if not equation:
                logger.error("DataManipulation: No equation provided")
                return outputs

            # Call the equation evaluator
            result = self.app_backend.evaluate_data_equation(
                equation=equation,
                dataset_a=dataset_a,
                dataset_b=dataset_b,
                flat_a=flat_a,
                flat_b=flat_b,
                output_name=output_name
            )

            if result.get('error'):
                logger.error(f"DataManipulation error: {result['error']}")
            else:
                if result.get('result_dataset'):
                    outputs['result_dataset'] = result['result_dataset']
                if result.get('result_flat'):
                    outputs['result_flat'] = result['result_flat']
                logger.info(f"DataManipulation executed: {equation}")

        elif tool_name == "DatasetOutput":
            dataset = inputs.get('dataset')
            if dataset:
                # Validate input is a proper dataset object, not a string
                if isinstance(dataset, str):
                    logger.error(f"DatasetOutput received string instead of dataset: {dataset}")
                    return outputs

                # Create human-readable output name
                # Format: "SourceDataset - OutputLabel (WorkflowName)"
                user_output_name = params.get('output_name', 'Processed')
                output_name = self._format_output_name(user_output_name)

                self.app_backend._datasets[output_name] = dataset
                # NOTE: dataLoaded emission deferred to after cleanup in execute()
                outputs['result'] = dataset
                logger.info(f"Dataset saved as: {output_name}")

        elif tool_name == "MapOutput":
            map_path = inputs.get('map')
            if map_path:
                outputs['result'] = map_path
                if params.get('display', True):
                    # Create human-readable output name
                    user_output_name = params.get('output_name', 'Map')
                    output_name = self._format_output_name(user_output_name)

                    # Handle both single paths and lists of paths
                    if isinstance(map_path, list):
                        # Open each map in the list, checking existence first
                        from pathlib import Path
                        for i, path in enumerate(map_path):
                            if not Path(path).exists():
                                logger.error(f"Map file not found: {path}")
                                continue
                            map_name = (f"{output_name}_{_pad(i + 1, len(map_path))}"
                                        if len(map_path) > 1 else output_name)
                            self.app_backend._open_map_window(str(path), f"wf_map_{node.id}_{i}", map_name)
                            # Register map in project browser
                            self.app_backend._map_id_counter += 1
                            map_id = f"map_{self.app_backend._map_id_counter}"
                            self.app_backend.maps.append({
                                'id': map_id, 'title': map_name, 'path': str(path),
                                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            self.app_backend.mapCreated.emit(map_id, map_name)
                            logger.info(f"Map displayed as: {map_name}")
                    else:
                        from pathlib import Path
                        if Path(map_path).exists():
                            self.app_backend._open_map_window(str(map_path), f"wf_map_{node.id}", output_name)
                            # Register map in project browser
                            self.app_backend._map_id_counter += 1
                            map_id = f"map_{self.app_backend._map_id_counter}"
                            self.app_backend.maps.append({
                                'id': map_id, 'title': output_name, 'path': str(map_path),
                                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            self.app_backend.mapCreated.emit(map_id, output_name)
                            logger.info(f"Map displayed as: {output_name}")
                        else:
                            logger.error(f"Map file not found: {map_path}")

        elif tool_name == "ImageOutput":
            image_path = inputs.get('image')
            if image_path:
                outputs['result'] = image_path
                user_output_name = params.get('output_name', 'Image')
                output_name = self._format_output_name(user_output_name)
                output_format = params.get('format', 'png')

                # Handle both single paths and lists of paths
                if isinstance(image_path, list):
                    for i, path in enumerate(image_path):
                        image_name = (f"{output_name}_{_pad(i + 1, len(image_path))}"
                                      if len(image_path) > 1 else output_name)
                        # Copy/convert to output directory if needed
                        if params.get('display', True):
                            self.app_backend._open_map_window(str(path), f"wf_image_{node.id}_{i}", image_name)
                        logger.info(f"Image output: {image_name}")
                else:
                    if params.get('display', True):
                        self.app_backend._open_map_window(str(image_path), f"wf_image_{node.id}", output_name)
                    logger.info(f"Image output: {output_name}")

        elif tool_name == "FlatDataOutput":
            flat_data = inputs.get('flat_data')
            if flat_data:
                # Create human-readable output name
                user_output_name = params.get('output_name', 'Integrated')
                output_name = self._format_output_name(user_output_name)

                # Store as dataset
                self.app_backend._datasets[output_name] = flat_data
                # NOTE: dataLoaded emission deferred to after cleanup in execute()

                # Optionally save as CSV
                if params.get('save_csv', True):
                    try:
                        # Use safe filename (no special chars)
                        safe_filename = output_name.replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
                        output_path = self.app_backend._ensure_output_dir('integrated') / f"{safe_filename}.csv"
                        if hasattr(flat_data, 'data'):
                            flat_data.data.to_csv(output_path, index=False)
                        elif hasattr(flat_data, 'to_csv'):
                            flat_data.to_csv(output_path, index=False)
                        logger.info(f"Flat data saved to {output_path}")
                    except Exception as e:
                        logger.warning(f"Could not save flat data to CSV: {e}")

                outputs['result'] = flat_data
                logger.info(f"Flat data saved as: {output_name}")

        elif tool_name == "IntervalOutput":
            intervals_raw = inputs.get('intervals') or []
            # Normalize to [start, end] pairs (accepts dicts with lower/upper too)
            interval_pairs = []
            for interval in intervals_raw:
                if isinstance(interval, dict):
                    start = interval.get('lower', interval.get('start'))
                    end = interval.get('upper', interval.get('end'))
                    if start is not None and end is not None:
                        interval_pairs.append([start, end])
                elif isinstance(interval, (list, tuple)) and len(interval) >= 2:
                    interval_pairs.append([interval[0], interval[1]])

            if interval_pairs:
                user_output_name = params.get('output_name', 'Intervals')
                output_name = self._format_output_name(user_output_name)
                outputs['result'] = interval_pairs

                if params.get('save_csv', True):
                    try:
                        import pandas as pd
                        safe_filename = output_name.replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
                        output_path = self.app_backend._ensure_output_dir('curves') / f"{safe_filename}.csv"
                        df = pd.DataFrame(interval_pairs, columns=['Start', 'End'])
                        df.to_csv(output_path, index=False)

                        # Register so it shows in ProjectBrowser
                        self.app_backend._output_id_counter += 1
                        output_id = f"output_{self.app_backend._output_id_counter}"
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.app_backend.output_files.append({
                            'id': output_id,
                            'type': 'Intervals',
                            'path': str(output_path),
                            'timestamp': timestamp,
                            'name': output_name
                        })
                        self.app_backend.outputCreated.emit(output_id, "Intervals", str(output_path))
                        logger.info(f"Intervals saved as: {output_name} -> {output_path}")
                    except Exception as e:
                        logger.warning(f"Could not save intervals to CSV: {e}")
            else:
                logger.warning("IntervalOutput received no intervals")

        # Map Processing Nodes
        elif tool_name == "MapGaussianFilter":
            map_path = inputs.get('map')
            if map_path:
                sigma = params.get('sigma', 1.0)

                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend._do_process_map(
                    MockTask(), str(map_path), 'file', 'gaussian_filter',
                    {'sigma': sigma, 'save_tiff': True, 'save_png': False}
                )
                if result_path:
                    outputs['filtered_map'] = result_path
                    logger.info(f"MapGaussianFilter: sigma={sigma}, output={result_path}")

        elif tool_name == "MapMedianFilter":
            map_path = inputs.get('map')
            if map_path:
                size = params.get('size', 3)

                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend._do_process_map(
                    MockTask(), str(map_path), 'file', 'median_filter',
                    {'size': size, 'save_tiff': True, 'save_png': False}
                )
                if result_path:
                    outputs['filtered_map'] = result_path
                    logger.info(f"MapMedianFilter: size={size}, output={result_path}")

        elif tool_name == "MapPlaneLevel":
            map_path = inputs.get('map')
            if map_path:
                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend._do_process_map(
                    MockTask(), str(map_path), 'file', 'plane_level',
                    {'save_tiff': True, 'save_png': False}
                )
                if result_path:
                    outputs['leveled_map'] = result_path
                    logger.info(f"MapPlaneLevel: output={result_path}")

        elif tool_name == "MapRowAlign":
            map_path = inputs.get('map')
            if map_path:
                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend._do_process_map(
                    MockTask(), str(map_path), 'file', 'row_align',
                    {'save_tiff': True, 'save_png': False}
                )
                if result_path:
                    outputs['aligned_map'] = result_path
                    logger.info(f"MapRowAlign: output={result_path}")

        elif tool_name == "MapNormalize":
            map_path = inputs.get('map')
            if map_path:
                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend._do_process_map(
                    MockTask(), str(map_path), 'file', 'normalize',
                    {'save_tiff': True, 'save_png': False}
                )
                if result_path:
                    outputs['normalized_map'] = result_path
                    logger.info(f"MapNormalize: output={result_path}")

        elif tool_name == "MapPolynomialBGRemoval":
            map_path = inputs.get('map')
            if map_path:
                order = params.get('order', 2)

                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend._do_process_map(
                    MockTask(), str(map_path), 'file', 'polynomial_bg_removal',
                    {'order': order, 'save_tiff': True, 'save_png': False}
                )
                if result_path:
                    outputs['corrected_map'] = result_path
                    logger.info(f"MapPolynomialBGRemoval: order={order}, output={result_path}")

        # STS Analysis Nodes
        elif tool_name == "FilterBadData":
            dataset = inputs.get('dataset')
            if dataset:
                if isinstance(dataset, str):
                    logger.error(f"FilterBadData received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset, "filter")
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                result_path = self.app_backend.filter_bad_data(
                    MockTask(), dataset_name,
                    weight_saturation=params.get('weight_saturation', 1.0),
                    weight_noise=params.get('weight_noise', 1.0),
                    weight_linear=params.get('weight_linear', 1.0),
                    weight_periodic=params.get('weight_periodic', 1.0),
                    weight_partial_noise=params.get('weight_partial_noise', 1.0),
                    threshold=params.get('threshold', 0.5),
                    correct_periodic=params.get('correct_periodic', False)
                )

                # Get output datasets by their actual names
                base_name = self.app_backend._extract_clean_base_name(dataset_name)

                good_name = f"{base_name} - Good Data"
                if good_name in self.app_backend._datasets:
                    outputs['good_data'] = self.app_backend._datasets[good_name]

                bad_name = f"{base_name} - Bad Data"
                if bad_name in self.app_backend._datasets:
                    outputs['bad_data'] = self.app_backend._datasets[bad_name]

                fft_name = f"{base_name} - FFT Spectra"
                if fft_name in self.app_backend._datasets:
                    outputs['fft_spectra'] = self.app_backend._datasets[fft_name]

                # Capture report text for TextOutput connection
                if result_path:
                    try:
                        report_text = Path(result_path).read_text()
                        outputs['report'] = report_text
                    except Exception as e:
                        logger.warning(f"Could not read filter report: {e}")

        elif tool_name == "DetectBandgapDoping":
            dataset = inputs.get('dataset')
            if dataset:
                if isinstance(dataset, str):
                    logger.error(f"DetectBandgapDoping received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset, "bandgap")
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                self.app_backend.detect_bandgap_doping(
                    MockTask(), dataset_name,
                    smoothing=params.get('smoothing', 1.0),
                    delta=params.get('delta', 5.0),
                    resolution=params.get('resolution', 0.01),
                    smoothing_method=params.get('smoothing_method', 'Savgol')
                )

                # Retrieve both output datasets
                base_name = self.app_backend._extract_clean_base_name(dataset_name)
                bandgap_name = f"{base_name} - Bandgap"
                doping_name = f"{base_name} - Doping"
                if bandgap_name in self.app_backend._datasets:
                    outputs['bandgap_data'] = self.app_backend._datasets[bandgap_name]
                if doping_name in self.app_backend._datasets:
                    outputs['doping_data'] = self.app_backend._datasets[doping_name]

        elif tool_name == "DiracPointEstimator":
            dataset = inputs.get('dataset')
            if dataset:
                if isinstance(dataset, str):
                    logger.error(f"DiracPointEstimator received string instead of dataset: {dataset}")
                    return outputs

                dataset_name = self._get_temp_dataset_name(dataset, "dirac")
                self.app_backend._datasets[dataset_name] = dataset

                class MockTask:
                    cancelled = False
                    progress = 0

                self.app_backend.estimate_dirac_point(
                    MockTask(), dataset_name,
                    left_min=params.get('left_min', -1.0),
                    left_max=params.get('left_max', -0.1),
                    right_min=params.get('right_min', 0.1),
                    right_max=params.get('right_max', 1.0),
                    smoothing=params.get('smoothing', 1.0),
                    smoothing_method=params.get('smoothing_method', 'Savgol'),
                    auto_detect=params.get('auto_detect', True)
                )

                # Get the result dataset
                base_name = self.app_backend._extract_clean_base_name(dataset_name)
                result_name = f"{base_name} - Dirac Point"
                if result_name in self.app_backend._datasets:
                    outputs['flat_data'] = self.app_backend._datasets[result_name]

        elif tool_name == "TextOutput":
            text = inputs.get('text')
            if text and isinstance(text, str):
                user_output_name = params.get('output_name', 'Report')
                output_name = self._format_output_name(user_output_name)
                safe_filename = output_name.replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
                output_path = self.app_backend._ensure_output_dir('curves') / f"{safe_filename}.txt"
                output_path.write_text(text)

                # Register so it shows in ProjectBrowser
                self.app_backend._output_id_counter += 1
                output_id = f"output_{self.app_backend._output_id_counter}"
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.app_backend.output_files.append({
                    'id': output_id,
                    'type': 'Text Report',
                    'path': str(output_path),
                    'timestamp': timestamp,
                    'name': output_name
                })
                self.app_backend.outputCreated.emit(output_id, "Text Report", str(output_path))
                outputs['result'] = str(output_path)
                logger.info(f"Text report saved as: {output_name} -> {output_path}")

        return outputs

    def _format_output_name(self, output_label: str) -> str:
        """
        Create a human-readable output name using the project's naming convention.

        Uses the naming convention set in the project browser if available,
        otherwise falls back to the default format.

        Parameters:
        -----------
        output_label : str
            The operation/output type label (e.g., "Smoothed", "Integrated", "Map")

        Returns:
        --------
        str : Formatted output name
        """
        source = self.original_dataset_name if self.original_dataset_name else "Data"

        name = ""
        # Try to use the naming convention from the backend
        if hasattr(self.app_backend, '_apply_naming_convention'):
            try:
                name = self.app_backend._apply_naming_convention(source, operation=output_label)
            except Exception as e:
                logger.warning(f"Could not apply naming convention: {e}")

        if not name:
            # Fallback to simple format
            workflow = self.workflow_name.replace("_", " ") if self.workflow_name else "Workflow"
            name = f"{source} - {output_label} ({workflow})"

        name = self._unique_output_name(name, source)
        self.produced_output_names.add(name)
        return name

    def _unique_output_name(self, name: str, source: str) -> str:
        """Keep one pass's outputs from overwriting another's.

        With a naming convention that doesn't include [dataset_name] every
        pass would otherwise land on the same name and only the last dataset
        would survive. Only batched runs are touched, so single-dataset
        naming is exactly as before.
        """
        if self._pass_count <= 1 or name not in self.produced_output_names:
            return name

        try:
            suffix = self.app_backend._extract_clean_base_name(source)
        except Exception:
            suffix = source
        candidate = f"{name}_{suffix}" if suffix else name
        if candidate in self.produced_output_names:
            candidate = f"{candidate}_{self._pass_index + 1}"
        return candidate

    def _get_temp_dataset_name(self, dataset, operation: str = "") -> str:
        """Generate a temporary dataset name for internal workflow processing.

        These names start with '_wf_' to mark them as internal/temporary.
        The operation parameter helps identify what processing step created this dataset.
        """
        # Use original dataset name if available for better traceability
        source = self.original_dataset_name if self.original_dataset_name else "temp"
        # Include operation type if provided
        op_suffix = f"_{operation}" if operation else ""
        # Short unique suffix
        unique_id = uuid.uuid4().hex[:6]
        return f"_wf_{source}{op_suffix}_{unique_id}"

    def cancel(self):
        """Cancel workflow execution"""
        self.cancelled = True


class WorkflowManager(QObject):
    """Manages workflows - creation, saving, loading, execution"""

    # Signals
    workflowCreated = Signal(str, str)  # id, name
    workflowSaved = Signal(str)  # path
    workflowLoaded = Signal(str)  # name
    workflowExecutionStarted = Signal(str)  # workflow name
    workflowExecutionCompleted = Signal(str, bool, list)  # name, success, errors
    workflowExecutionProgress = Signal(int, int, str)  # current, total, message

    def __init__(self, app_backend, parent=None):
        super().__init__(parent)
        self.app_backend = app_backend
        self.workflows: Dict[str, Workflow] = {}
        self.current_workflow: Optional[Workflow] = None
        self.executor: Optional[WorkflowExecutor] = None
        # workflow_id -> last saved file path; lets a rename replace the old
        # .flow file instead of leaving a stale duplicate behind
        self._workflow_paths: Dict[str, str] = {}

    def _get_workflows_dir(self) -> Path:
        """Get the workflows directory for the current project, creating it if needed."""
        if self.app_backend._project_path:
            workflows_dir = self.app_backend._project_path / "workflows"
            workflows_dir.mkdir(parents=True, exist_ok=True)
            return workflows_dir
        else:
            # Fallback to app directory if no project is open
            fallback_dir = Path("workflows")
            fallback_dir.mkdir(exist_ok=True)
            return fallback_dir

    @Slot(str, result=str)
    def createWorkflow(self, name: str) -> str:
        """Create a new empty workflow"""
        workflow_id = str(uuid.uuid4())[:8]
        workflow = Workflow(
            id=workflow_id,
            name=name,
            description=""
        )
        self.workflows[workflow_id] = workflow
        self.current_workflow = workflow
        self.workflowCreated.emit(workflow_id, name)
        logger.info(f"Created workflow: {name} (ID: {workflow_id})")
        return workflow_id

    @Slot(str, str, float, float, result=str)
    def addNode(self, workflow_id: str, tool_name: str, x: float, y: float) -> str:
        """Add a node to a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return ""

        node = create_node_from_tool(tool_name, x, y)
        if node:
            workflow.add_node(node)
            logger.info(f"Added node {node.display_name} to workflow {workflow.name}")
            return node.id
        return ""

    @Slot(str, str)
    def removeNode(self, workflow_id: str, node_id: str):
        """Remove a node from a workflow"""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            workflow.remove_node(node_id)
            logger.info(f"Removed node {node_id} from workflow {workflow.name}")

    @Slot(str, str, str, str, str, result=str)
    def addConnection(self, workflow_id: str, source_node: str, source_port: str,
                     target_node: str, target_port: str) -> str:
        """Add a connection between nodes"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return ""

        connection = Connection(
            id=str(uuid.uuid4())[:8],
            source_node_id=source_node,
            source_port_id=source_port,
            target_node_id=target_node,
            target_port_id=target_port
        )

        if workflow.add_connection(connection):
            logger.info(f"Added connection in workflow {workflow.name}")
            return connection.id
        return ""

    @Slot(str, str)
    def removeConnection(self, workflow_id: str, connection_id: str):
        """Remove a connection"""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            workflow.remove_connection(connection_id)

    @Slot(str, str, float, float)
    def updateNodePosition(self, workflow_id: str, node_id: str, x: float, y: float):
        """Update node position"""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            node = workflow.get_node(node_id)
            if node:
                node.x = x
                node.y = y

    @Slot(str, str, str, 'QVariant')
    def setNodeParameter(self, workflow_id: str, node_id: str, param_name: str, value):
        """Set a node parameter"""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            node = workflow.get_node(node_id)
            if node:
                node.parameters[param_name] = value

    @Slot(str, result='QVariantList')
    def validateWorkflow(self, workflow_id: str) -> List[str]:
        """Validate a workflow and return errors"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return ["Workflow not found"]

        is_valid, errors = workflow.validate()
        return errors

    @Slot(str, str)
    def setWorkflowName(self, workflow_id: str, name: str):
        """Update workflow name."""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            workflow.name = name
            workflow.modified = datetime.now().isoformat()
            logger.info(f"Updated workflow name to: {name}")

    def _sanitize_for_json(self, data: Any) -> Any:
        """
        Recursively sanitize data to ensure it's JSON-serializable.
        Handles QML/Qt types that might not serialize properly.
        """
        if data is None:
            return None
        if isinstance(data, (bool, int, float, str)):
            return data
        if isinstance(data, dict):
            return {str(k): self._sanitize_for_json(v) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return [self._sanitize_for_json(item) for item in data]
        # Handle Qt/QML types by converting to Python types
        try:
            # Try to convert to list (for QJSValue arrays)
            if hasattr(data, 'toVariant'):
                return self._sanitize_for_json(data.toVariant())
            if hasattr(data, '__iter__'):
                return [self._sanitize_for_json(item) for item in data]
            # Try string conversion as last resort
            return str(data)
        except Exception:
            logger.warning(f"Could not serialize value of type {type(data)}, using None")
            return None

    @Slot(str, result=str)
    def saveWorkflow(self, workflow_id: str) -> str:
        """Save workflow to file in the current project's workflows directory."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return ""

        # Update modified timestamp
        workflow.modified = datetime.now().isoformat()

        # Create safe filename
        safe_name = "".join(c for c in workflow.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        workflows_dir = self._get_workflows_dir()
        file_path = workflows_dir / f"{safe_name}.flow"

        try:
            # Sanitize workflow data to ensure JSON serializability
            workflow_data = self._sanitize_for_json(workflow.to_dict())

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(workflow_data, f, indent=2)

            # If the workflow was renamed, remove the file saved under the
            # old name so the saved list stays stable (no stale duplicates)
            old_path = self._workflow_paths.get(workflow_id)
            if old_path and Path(old_path) != file_path:
                try:
                    if Path(old_path).exists():
                        Path(old_path).unlink()
                        logger.info(f"Removed stale workflow file after rename: {old_path}")
                except Exception as e:
                    logger.warning(f"Could not remove old workflow file {old_path}: {e}")
            self._workflow_paths[workflow_id] = str(file_path)

            self.workflowSaved.emit(str(file_path))
            logger.info(f"Saved workflow to {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Error saving workflow: {e}")
            return ""

    def clear_workflows(self):
        """Forget all in-memory workflows.

        Called when a project is opened or closed so workflows from the
        previous project are not written into the new project's workflows
        directory (and rename cleanup cannot touch the old project's files).
        """
        self.workflows.clear()
        self._workflow_paths.clear()
        self.current_workflow = None
        logger.info("Cleared in-memory workflows")

    def save_all_workflows(self) -> int:
        """Persist every in-memory workflow that has content.

        Called when the project is saved so open workflow editors survive a
        save/reopen cycle even if the user never pressed Save in the editor.
        """
        count = 0
        for workflow_id, workflow in list(self.workflows.items()):
            if not workflow.nodes:
                continue  # skip empty "New Workflow" placeholders
            if self.saveWorkflow(workflow_id):
                count += 1
        if count:
            logger.info(f"Saved {count} workflow(s) with the project")
        return count

    @Slot(str, result=str)
    def loadWorkflow(self, file_path: str) -> str:
        """Load workflow from file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            workflow = Workflow.from_dict(data)
            self.workflows[workflow.id] = workflow
            self.current_workflow = workflow
            self._workflow_paths[workflow.id] = str(Path(file_path))
            self.workflowLoaded.emit(workflow.name)
            logger.info(f"Loaded workflow: {workflow.name}")
            return workflow.id

        except Exception as e:
            logger.error(f"Error loading workflow: {e}")
            return ""

    @Slot(result='QVariantList')
    def getSavedWorkflows(self) -> List[Dict]:
        """Get list of saved workflows from the current project's workflows directory."""
        workflows = []
        workflows_dir = self._get_workflows_dir()

        # Search for .flow files
        for file_path in workflows_dir.glob("*.flow"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                workflows.append({
                    'path': str(file_path),
                    'name': data.get('name', file_path.stem),
                    'description': data.get('description', ''),
                    'modified': data.get('modified', '')
                })
            except Exception as e:
                logger.warning(f"Error reading workflow file {file_path}: {e}")

        return workflows

    @Slot(str, result=bool)
    def deleteWorkflow(self, file_path: str) -> bool:
        """Delete a workflow file."""
        try:
            path = Path(file_path)
            if path.exists() and path.suffix == '.flow':
                path.unlink()
                logger.info(f"Deleted workflow file: {file_path}")
                return True
            else:
                logger.warning(f"Workflow file not found or invalid: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting workflow: {e}")
            return False

    @Slot(str)
    def executeWorkflow(self, workflow_id: str):
        """Execute a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            self.workflowExecutionCompleted.emit("Unknown", False, ["Workflow not found"])
            return

        self.workflowExecutionStarted.emit(workflow.name)

        # Create executor and run
        self.executor = WorkflowExecutor(self.app_backend)

        def progress_callback(current, total, message):
            self.workflowExecutionProgress.emit(current, total, message)

        result = self.executor.execute(workflow, progress_callback)

        self.workflowExecutionCompleted.emit(
            workflow.name,
            result['success'],
            result['errors']
        )

    @Slot()
    def cancelExecution(self):
        """Cancel current workflow execution"""
        if self.executor:
            self.executor.cancel()

    @Slot(result='QVariantList')
    def getToolCategories(self) -> list:
        """Get available tools organized by category (ordered list)"""
        return get_tool_categories()

    @Slot(str, result='QVariantMap')
    def getToolInfo(self, tool_name: str) -> Dict:
        """Get information about a specific tool"""
        info = get_tool_info(tool_name)
        return info if info else {}

    @Slot(str, result='QVariantMap')
    def getWorkflowData(self, workflow_id: str) -> Dict:
        """Get workflow data for QML"""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            return workflow.to_dict()
        return {}

    @Slot(result='QVariantList')
    def getAvailableDatasets(self) -> List[str]:
        """Get list of available datasets for DatasetInput node"""
        return list(self.app_backend._datasets.keys())

    @Slot(result='QVariantList')
    def getAvailableFlatDatasets(self) -> List[str]:
        """Get list of flat data datasets for FlatDataInput node."""
        return [
            name for name, ds in self.app_backend._datasets.items()
            if hasattr(ds, 'metadata') and getattr(ds.metadata, 'data_type', 'spectral') == 'flat'
        ]

    @Slot(str, str, result='QVariantList')
    def getConnectedInputs(self, workflow_id: str, node_id: str) -> List[Dict]:
        """
        Get list of connected inputs for a node.
        Returns list of {source_node_id, source_node_name, source_port_id, target_port_id}
        for use in multi-input queue UI.
        """
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return []

        node = workflow.get_node(node_id)
        if not node:
            return []

        connected_inputs = []
        for c in workflow.connections:
            if c.target_node_id == node_id:
                source_node = workflow.get_node(c.source_node_id)
                source_name = source_node.display_name if source_node else c.source_node_id

                # Get dataset name if it's a DatasetInput node
                display_name = source_name
                if source_node and source_node.tool_name == "DatasetInput":
                    dataset_name = source_node.parameters.get('dataset_name', '')
                    if dataset_name:
                        display_name = dataset_name

                connected_inputs.append({
                    'source_node_id': c.source_node_id,
                    'source_node_name': display_name,
                    'source_port_id': c.source_port_id,
                    'target_port_id': c.target_port_id,
                    'enabled': True  # Default to enabled
                })

        return connected_inputs
