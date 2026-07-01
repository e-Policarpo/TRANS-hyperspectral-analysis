"""
Workflow Engine for TRANS-QML
Visual pipeline system for connecting analysis tools

A workflow is a directed acyclic graph (DAG) of tool nodes connected by data flows.
Each node represents a tool with typed inputs and outputs.
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, Set
from pathlib import Path
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class PortType(Enum):
    """Data types for workflow ports"""
    DATASET = "dataset"          # SpectralData object (full spectral data)
    FLAT_DATA = "flat_data"      # Flattened dataset - DataFrame with x values in first column, single values per curve
    IMAGE = "image"              # Image/map file path
    MAP = "map"                  # Map data (2D array or TIFF file)
    TABLE = "table"              # DataFrame/table data
    NUMBER = "number"            # Single numeric value
    STRING = "string"            # Text value
    INTERVAL_LIST = "intervals"  # List of [start, end] intervals
    ANY = "any"                  # Any type (flexible)


@dataclass
class Port:
    """Input or output port on a workflow node"""
    id: str
    name: str
    port_type: PortType
    is_input: bool
    required: bool = True
    default_value: Any = None
    description: str = ""
    multi_input: bool = False  # If True, allows multiple connections to this port

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'port_type': self.port_type.value,
            'is_input': self.is_input,
            'required': self.required,
            'default_value': self.default_value,
            'description': self.description,
            'multi_input': self.multi_input
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Port':
        return cls(
            id=data['id'],
            name=data['name'],
            port_type=PortType(data['port_type']),
            is_input=data['is_input'],
            required=data.get('required', True),
            default_value=data.get('default_value'),
            description=data.get('description', ''),
            multi_input=data.get('multi_input', False)
        )


@dataclass
class WorkflowNode:
    """A node in the workflow representing a tool"""
    id: str
    tool_name: str
    display_name: str
    x: float = 100
    y: float = 100
    inputs: List[Port] = field(default_factory=list)
    outputs: List[Port] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'tool_name': self.tool_name,
            'display_name': self.display_name,
            'x': self.x,
            'y': self.y,
            'inputs': [p.to_dict() for p in self.inputs],
            'outputs': [p.to_dict() for p in self.outputs],
            'parameters': self.parameters
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkflowNode':
        # Merge saved parameters with defaults from tool definition
        tool_name = data['tool_name']
        saved_params = data.get('parameters', {})

        # Get default parameters from TOOL_DEFINITIONS
        default_params = {}
        if tool_name in TOOL_DEFINITIONS:
            tool_def = TOOL_DEFINITIONS[tool_name]
            for param_name, param_def in tool_def.get('parameters', {}).items():
                if 'default' in param_def:
                    default_params[param_name] = param_def['default']

        # Merge: defaults first, then override with saved values
        merged_params = {**default_params, **saved_params}

        return cls(
            id=data['id'],
            tool_name=tool_name,
            display_name=data['display_name'],
            x=data.get('x', 100),
            y=data.get('y', 100),
            inputs=[Port.from_dict(p) for p in data.get('inputs', [])],
            outputs=[Port.from_dict(p) for p in data.get('outputs', [])],
            parameters=merged_params
        )

    def get_input_port(self, port_id: str) -> Optional[Port]:
        for port in self.inputs:
            if port.id == port_id:
                return port
        return None

    def get_output_port(self, port_id: str) -> Optional[Port]:
        for port in self.outputs:
            if port.id == port_id:
                return port
        return None


@dataclass
class Connection:
    """Connection between two ports"""
    id: str
    source_node_id: str
    source_port_id: str
    target_node_id: str
    target_port_id: str

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Connection':
        return cls(**data)


@dataclass
class Workflow:
    """Complete workflow definition"""
    id: str
    name: str
    description: str = ""
    nodes: List[WorkflowNode] = field(default_factory=list)
    connections: List[Connection] = field(default_factory=list)
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    modified: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'nodes': [n.to_dict() for n in self.nodes],
            'connections': [c.to_dict() for c in self.connections],
            'created': self.created,
            'modified': self.modified
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        return cls(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            nodes=[WorkflowNode.from_dict(n) for n in data.get('nodes', [])],
            connections=[Connection.from_dict(c) for c in data.get('connections', [])],
            created=data.get('created', datetime.now().isoformat()),
            modified=data.get('modified', datetime.now().isoformat())
        )

    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def add_node(self, node: WorkflowNode):
        self.nodes.append(node)
        self.modified = datetime.now().isoformat()

    def remove_node(self, node_id: str):
        self.nodes = [n for n in self.nodes if n.id != node_id]
        # Remove connections to/from this node
        self.connections = [
            c for c in self.connections
            if c.source_node_id != node_id and c.target_node_id != node_id
        ]
        self.modified = datetime.now().isoformat()

    def add_connection(self, connection: Connection) -> bool:
        """Add connection if valid. Returns True if added."""
        if self.validate_connection(connection):
            self.connections.append(connection)
            self.modified = datetime.now().isoformat()
            return True
        return False

    def remove_connection(self, connection_id: str):
        self.connections = [c for c in self.connections if c.id != connection_id]
        self.modified = datetime.now().isoformat()

    def validate_connection(self, connection: Connection) -> bool:
        """Check if a connection is valid (types match, no cycles)"""
        source_node = self.get_node(connection.source_node_id)
        target_node = self.get_node(connection.target_node_id)

        if not source_node or not target_node:
            return False

        source_port = source_node.get_output_port(connection.source_port_id)
        target_port = target_node.get_input_port(connection.target_port_id)

        if not source_port or not target_port:
            return False

        # Check type compatibility
        if not self._types_compatible(source_port.port_type, target_port.port_type):
            return False

        # Check for cycles (would create with this connection)
        if self._would_create_cycle(connection):
            return False

        # Check if target port already has a connection (unless it's a multi_input port)
        if not target_port.multi_input:
            for c in self.connections:
                if c.target_node_id == connection.target_node_id and \
                   c.target_port_id == connection.target_port_id:
                    return False  # Input port already connected

        return True

    def _types_compatible(self, source_type: PortType, target_type: PortType) -> bool:
        """Check if source type can connect to target type"""
        if target_type == PortType.ANY or source_type == PortType.ANY:
            return True
        return source_type == target_type

    def _would_create_cycle(self, new_connection: Connection) -> bool:
        """Check if adding this connection would create a cycle"""
        # Build adjacency list including the new connection
        adj: Dict[str, Set[str]] = {n.id: set() for n in self.nodes}
        for c in self.connections:
            adj[c.source_node_id].add(c.target_node_id)
        adj[new_connection.source_node_id].add(new_connection.target_node_id)

        # DFS to detect cycle
        visited = set()
        rec_stack = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for neighbor in adj.get(node_id, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node_id)
            return False

        for node in self.nodes:
            if node.id not in visited:
                if dfs(node.id):
                    return True
        return False

    def _has_cycle(self) -> bool:
        """Check if the current workflow graph has a cycle"""
        if not self.nodes:
            return False

        # Build adjacency list from existing connections
        adj: Dict[str, Set[str]] = {n.id: set() for n in self.nodes}
        for c in self.connections:
            adj[c.source_node_id].add(c.target_node_id)

        # DFS to detect cycle
        visited = set()
        rec_stack = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for neighbor in adj.get(node_id, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node_id)
            return False

        for node in self.nodes:
            if node.id not in visited:
                if dfs(node.id):
                    return True
        return False

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate the entire workflow.
        Returns (is_valid, list_of_errors)
        """
        errors = []

        # Check for empty workflow
        if not self.nodes:
            errors.append("Workflow has no nodes")
            return False, errors

        # Check all required inputs are connected
        for node in self.nodes:
            # Skip comment nodes - they don't have inputs
            if node.tool_name == "CommentNode":
                continue

            for input_port in node.inputs:
                if input_port.required:
                    connected = any(
                        c.target_node_id == node.id and c.target_port_id == input_port.id
                        for c in self.connections
                    )
                    if not connected and input_port.default_value is None:
                        errors.append(
                            f"Required input '{input_port.name}' on node '{node.display_name}' is not connected"
                        )

        # Check for missing required parameters
        for node in self.nodes:
            # Skip comment nodes
            if node.tool_name == "CommentNode":
                continue

            tool_def = TOOL_DEFINITIONS.get(node.tool_name)
            if tool_def:
                for param_name, param_def in tool_def.get('parameters', {}).items():
                    if param_def.get('required', False):
                        param_value = node.parameters.get(param_name)
                        # Check if parameter is missing or empty
                        if param_value is None or (isinstance(param_value, str) and not param_value.strip()):
                            # Check if there's a default value
                            if 'default' not in param_def:
                                errors.append(
                                    f"Node '{node.display_name}': Missing required parameter '{param_def.get('label', param_name)}'"
                                )

        # Check for disconnected nodes (warning, not error) - skip comment nodes
        connected_nodes = set()
        for c in self.connections:
            connected_nodes.add(c.source_node_id)
            connected_nodes.add(c.target_node_id)

        for node in self.nodes:
            # Comment nodes can be standalone
            if node.tool_name == "CommentNode":
                continue
            if node.id not in connected_nodes and len(self.nodes) > 1:
                # Only warn if there are other non-comment nodes
                non_comment_nodes = [n for n in self.nodes if n.tool_name != "CommentNode"]
                if len(non_comment_nodes) > 1:
                    errors.append(f"Node '{node.display_name}' is not connected to any other node")

        # Check for cycles
        if self._has_cycle():
            errors.append("Workflow contains a cycle - this would cause infinite execution")

        return len(errors) == 0, errors

    def get_execution_order(self) -> List[str]:
        """
        Get nodes in topological order for execution.
        Uses Kahn's algorithm.
        """
        # Build in-degree map
        in_degree = {n.id: 0 for n in self.nodes}
        adj: Dict[str, List[str]] = {n.id: [] for n in self.nodes}

        for c in self.connections:
            adj[c.source_node_id].append(c.target_node_id)
            in_degree[c.target_node_id] += 1

        # Start with nodes that have no incoming edges
        queue = [n_id for n_id, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            node_id = queue.pop(0)
            result.append(node_id)

            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result


# =============================================================================
# Tool Definitions - Define available tools and their ports
# =============================================================================

TOOL_DEFINITIONS = {
    # ===========================================================================
    # INPUT NODES
    # ===========================================================================
    "DatasetInput": {
        "display_name": "Dataset",
        "category": "Input",
        "description": "Load a dataset into the workflow",
        "inputs": [],
        "outputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "description": "Selected dataset"}
        ],
        "parameters": {
            "dataset_name": {"type": "dataset_select", "label": "Dataset", "required": True}
        }
    },

    "MapInput": {
        "display_name": "Map",
        "category": "Input",
        "description": "Load a map (TIFF) into the workflow",
        "inputs": [],
        "outputs": [
            {"id": "map", "name": "Map", "port_type": "map", "description": "Loaded map data"}
        ],
        "parameters": {
            "file_path": {"type": "file_select", "label": "Map File", "required": True, "filter": "TIFF files (*.tif *.tiff)", "description": "Select a TIFF map file"}
        }
    },

    "ImageInput": {
        "display_name": "Image",
        "category": "Input",
        "description": "Load an image into the workflow",
        "inputs": [],
        "outputs": [
            {"id": "image", "name": "Image", "port_type": "image", "description": "Loaded image data"}
        ],
        "parameters": {
            "file_path": {"type": "file_select", "label": "Image File", "required": True, "filter": "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)", "description": "Select an image file"}
        }
    },

    "FlatDataInput": {
        "display_name": "Flat Data",
        "category": "Input",
        "description": "Load flat data into the workflow",
        "inputs": [],
        "outputs": [
            {"id": "flat_data", "name": "Flat Data", "port_type": "flat_data", "description": "Selected flat data"}
        ],
        "parameters": {
            "dataset_name": {"type": "flat_data_select", "label": "Flat Dataset", "required": True}
        }
    },

    # ===========================================================================
    # OUTPUT NODES
    # ===========================================================================
    "DatasetOutput": {
        "display_name": "Dataset",
        "category": "Output",
        "description": "Save dataset to project",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [],
        "parameters": {
            "output_name": {"type": "string", "label": "Output Name", "required": True, "default": "Processed"}
        }
    },

    "MapOutput": {
        "display_name": "Map",
        "category": "Output",
        "description": "Display and save map as TIFF",
        "inputs": [
            {"id": "map", "name": "Map", "port_type": "map", "required": True, "description": "Map data to save (TIFF format)"}
        ],
        "outputs": [],
        "parameters": {
            "output_name": {"type": "string", "label": "Output Name", "required": True, "default": "Map"},
            "display": {"type": "bool", "label": "Display Window", "default": True}
        }
    },

    "ImageOutput": {
        "display_name": "Image",
        "category": "Output",
        "description": "Display and save image file",
        "inputs": [
            {"id": "image", "name": "Image", "port_type": "image", "required": True, "description": "Image to save and display"}
        ],
        "outputs": [],
        "parameters": {
            "output_name": {"type": "string", "label": "Output Name", "required": True, "default": "Image"},
            "format": {"type": "combo", "label": "Format", "default": "png", "options": ["png", "tiff", "jpg"], "description": "Output image format"},
            "display": {"type": "bool", "label": "Display Window", "default": True}
        }
    },

    "FlatDataOutput": {
        "display_name": "Flat Data",
        "category": "Output",
        "description": "Save flat data (one value per spectrum)",
        "inputs": [
            {"id": "flat_data", "name": "Flat Data", "port_type": "flat_data", "required": True}
        ],
        "outputs": [],
        "parameters": {
            "output_name": {"type": "string", "label": "Output Name", "required": True, "default": "FlatData"},
            "save_csv": {"type": "bool", "label": "Save as CSV", "default": True}
        }
    },

    # ===========================================================================
    # PROCESSING NODES
    # ===========================================================================
    "ColumnSelector": {
        "display_name": "Column Selector",
        "category": "Processing",
        "description": "Filter dataset columns - keeps X values and selected data columns",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "filtered", "name": "Filtered", "port_type": "dataset", "description": "Dataset with selected columns only"}
        ],
        "parameters": {
            "selected_columns": {"type": "column_select", "label": "Select Columns", "default": [], "description": "Select which data columns to keep (X column is always preserved)"}
        }
    },

    "TruncateData": {
        "display_name": "Truncate",
        "category": "Processing",
        "description": "Limit data to X range",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "truncated", "name": "Truncated", "port_type": "dataset", "description": "Truncated data"}
        ],
        "parameters": {
            "x_min": {"type": "float", "label": "X Min", "required": True, "default": -1.0},
            "x_max": {"type": "float", "label": "X Max", "required": True, "default": 1.0}
        }
    },

    "Derivative": {
        "display_name": "Derivative",
        "category": "Processing",
        "description": "Calculate derivative (dI/dV)",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "derivative", "name": "Derivative", "port_type": "dataset", "description": "Derivative data"}
        ],
        "parameters": {
            "order": {"type": "int", "label": "Order", "default": 1, "min": 1, "max": 2},
            "smooth_before": {"type": "bool", "label": "Smooth Before", "default": True},
            "smooth_after": {"type": "bool", "label": "Smooth After", "default": True}
        }
    },

    "CurveSmoothing": {
        "display_name": "Smoothing",
        "category": "Processing",
        "description": "Smooth spectral curves",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "smoothed", "name": "Smoothed", "port_type": "dataset", "description": "Smoothed data"}
        ],
        "parameters": {
            "window_size": {"type": "int", "label": "Window Size", "default": 11, "min": 3, "max": 101},
            "poly_order": {"type": "int", "label": "Polynomial Order", "default": 3, "min": 1, "max": 5},
            "smoothing_type": {"type": "select", "label": "Type", "options": ["savgol", "moving_average", "gaussian"], "default": "savgol"}
        }
    },

    "CosmicRayFilter": {
        "display_name": "Cosmic Ray Filter",
        "category": "Processing",
        "description": "Remove narrow CCD spikes (cosmic rays / hot pixels) from spectra",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "cleaned", "name": "Cleaned", "port_type": "dataset", "description": "Spectra with spikes replaced by the local median"}
        ],
        "parameters": {
            "threshold_sigmas": {"type": "float", "label": "Threshold (σ)", "default": 5.0, "min": 2.0, "max": 20.0, "description": "Sample is flagged when local residual exceeds this × MAD-σ."},
            "window": {"type": "int", "label": "Median Window", "default": 5, "min": 3, "max": 21, "description": "Sliding-median window length; forced odd."},
            "max_width": {"type": "int", "label": "Max Spike Width", "default": 2, "min": 1, "max": 5, "description": "Flagged runs wider than this are kept (likely real peaks)."}
        }
    },

    "BackgroundSubtraction": {
        "display_name": "Background Subtraction",
        "category": "Processing",
        "description": "Subtract a reference background dataset from a signal; truncates to axis overlap if needed",
        "inputs": [
            {"id": "signal", "name": "Signal", "port_type": "dataset", "required": True},
            {"id": "background", "name": "Background", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "corrected", "name": "Corrected", "port_type": "dataset", "description": "Signal minus mean background, optionally truncated to overlap"}
        ],
        "parameters": {}
    },

    "CurveFitting": {
        "display_name": "Baseline",
        "category": "Processing",
        "description": "Subtract baseline from curves",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "corrected", "name": "Corrected", "port_type": "dataset", "description": "Baseline-corrected data"}
        ],
        "parameters": {
            "fit_type": {"type": "select", "label": "Method",
                        "options": ["endpoints", "als", "rubberband", "polynomial", "linear", "exponential"],
                        "default": "endpoints"},
            "degree": {"type": "int", "label": "Degree (poly/endpoints)", "default": 1, "min": 1, "max": 10},
            "als_lambda": {"type": "float", "label": "ALS Smoothness", "default": 100000.0, "min": 100, "max": 10000000},
            "als_p": {"type": "float", "label": "ALS Asymmetry", "default": 0.01, "min": 0.001, "max": 0.5}
        }
    },

    "Integration": {
        "display_name": "Integration",
        "category": "Processing",
        "description": "Integrate over intervals",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True},
            {"id": "intervals", "name": "Intervals", "port_type": "intervals", "required": False, "description": "Optional intervals from Peak Finder"}
        ],
        "outputs": [
            {"id": "flat_data", "name": "Flat Data", "port_type": "flat_data", "description": "Flattened data (one value per curve)"},
            {"id": "intervals_out", "name": "Intervals", "port_type": "intervals", "description": "Pass-through intervals"}
        ],
        "parameters": {
            "intervals": {"type": "interval_list", "label": "Integration Intervals (manual)", "required": False}
        }
    },

    "SpatialAverage": {
        "display_name": "Spatial Average",
        "category": "Processing",
        "description": "Average over spatial blocks",
        "inputs": [
            {"id": "datasets", "name": "Datasets", "port_type": "dataset", "required": False, "multi_input": True, "description": "One or more datasets to process"},
            {"id": "flat_data_inputs", "name": "Flat Data", "port_type": "flat_data", "required": False, "multi_input": True, "description": "One or more flat data inputs to process"}
        ],
        "outputs": [
            {"id": "averaged_datasets", "name": "Averaged Datasets", "port_type": "dataset", "description": "Spatially averaged datasets (list)"},
            {"id": "averaged_flat_data", "name": "Averaged Flat Data", "port_type": "flat_data", "description": "Spatially averaged flat data (list)"}
        ],
        "parameters": {
            "block_x": {"type": "int", "label": "Block X", "default": 2, "min": 1, "description": "Averaging block width"},
            "block_y": {"type": "int", "label": "Block Y", "default": 2, "min": 1, "description": "Averaging block height"},
            "input_queue": {"type": "multi_input_queue", "label": "Processing Queue", "default": [], "description": "Select and order inputs for processing"}
        }
    },

    "DataManipulation": {
        "display_name": "Math Operation",
        "category": "Processing",
        "description": "Apply equations with multiple inputs (A+B+C, sqrt, etc.)",
        "inputs": [
            {"id": "inputs", "name": "Inputs", "port_type": "any", "required": True, "multi_input": True, "description": "Connect multiple datasets or flat data (referenced as A, B, C, ... in equation)"}
        ],
        "outputs": [
            {"id": "result_dataset", "name": "Result Dataset", "port_type": "dataset", "description": "Result as full dataset (if input was dataset)"},
            {"id": "result_flat", "name": "Result Flat", "port_type": "flat_data", "description": "Result as flat data (if input was flat data)"}
        ],
        "parameters": {
            "equation": {"type": "equation", "label": "Equation", "required": True, "description": "Equation to apply (e.g., 'A + B', 'sqrt(A)', 'A * 2 - B / 3')"},
            "output_name": {"type": "string", "label": "Output Label", "default": "Manipulated"},
            "input_mapping": {"type": "input_mapping", "label": "Input Mapping", "description": "Map connected inputs to variables (A, B, C, ...)"}
        }
    },

    "FFT1D": {
        "display_name": "FFT",
        "category": "Processing",
        "description": "1D Fourier transform",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "fft_result", "name": "FFT Result", "port_type": "dataset", "description": "FFT transformed data"}
        ],
        "parameters": {
            "output_type": {"type": "select", "label": "Output", "options": ["magnitude", "phase", "complex"], "default": "magnitude"}
        }
    },

    # ===========================================================================
    # ANALYSIS NODES
    # ===========================================================================
    "PeakFinder": {
        "display_name": "Peak Finder",
        "category": "Analysis",
        "description": "Detect peaks and intervals",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "peaks", "name": "Peaks", "port_type": "dataset", "description": "Peak table as a dataset (connect to a Dataset output node to capture)"},
            {"id": "intervals", "name": "Peak Intervals", "port_type": "intervals", "description": "Non-overlapping intervals around peaks for integration"}
        ],
        "parameters": {
            "prominence": {"type": "float", "label": "Min Prominence", "default": 0.0, "min": 0, "description": "Minimum peak prominence to detect. Leave at 0 for adaptive (noise-aware) per-spectrum threshold."},
            "min_distance": {"type": "int", "label": "Min Distance", "default": 5, "min": 1, "description": "Minimum distance between peaks (indices)"},
            "fwhm_multiplier": {"type": "float", "label": "FWHM Multiplier", "default": 1.5, "min": 0.5, "max": 5.0, "description": "Interval width as multiplier of FWHM"}
        }
    },

    # ===========================================================================
    # VISUALIZATION NODES
    # ===========================================================================
    "MapGenerator": {
        "display_name": "Map Generator",
        "category": "Visualization",
        "description": "Create spatial maps from flat data",
        "inputs": [
            {"id": "flat_data", "name": "Flat Dataset", "port_type": "flat_data", "required": True}
        ],
        "outputs": [
            {"id": "maps", "name": "Maps", "port_type": "map", "description": "List of generated TIFF map paths"}
        ],
        "parameters": {
            "intervals": {"type": "interval_checklist", "label": "Intervals to Generate", "description": "Select which intervals to generate maps for (auto-populated from input)"},
            "generate_all": {"type": "bool", "label": "Generate All", "default": True, "description": "Generate maps for all available intervals"}
        }
    },

    # ===========================================================================
    # IMAGE PROCESSING NODES
    # ===========================================================================
    "ImageSmoothing": {
        "display_name": "Image Smoothing",
        "category": "Image Processing",
        "description": "Smooth image/map",
        "inputs": [
            {"id": "image", "name": "Image", "port_type": "image", "required": True}
        ],
        "outputs": [
            {"id": "smoothed", "name": "Smoothed", "port_type": "image", "description": "Smoothed image"}
        ],
        "parameters": {
            "filter_type": {"type": "select", "label": "Filter", "options": ["gaussian", "median", "bilateral"], "default": "gaussian"},
            "kernel_size": {"type": "int", "label": "Kernel Size", "default": 5, "min": 3, "max": 21}
        }
    },

    "GradientFilter": {
        "display_name": "Gradient",
        "category": "Image Processing",
        "description": "Edge detection filter",
        "inputs": [
            {"id": "image", "name": "Image", "port_type": "image", "required": True}
        ],
        "outputs": [
            {"id": "gradient", "name": "Gradient", "port_type": "image", "description": "Gradient image"}
        ],
        "parameters": {
            "method": {"type": "select", "label": "Method", "options": ["sobel", "prewitt", "scharr"], "default": "sobel"}
        }
    },

    "ImageDiscretizer": {
        "display_name": "Image Discretizer",
        "category": "Image Processing",
        "description": "Discretize image values into bins for visualization or analysis",
        "inputs": [
            {"id": "image", "name": "Image", "port_type": "image", "required": True, "description": "Input image to discretize"}
        ],
        "outputs": [
            {"id": "discretized", "name": "Discretized", "port_type": "image", "description": "Discretized image"},
            {"id": "labels", "name": "Labels", "port_type": "table", "description": "Bin labels and value ranges"}
        ],
        "parameters": {
            "method": {"type": "select", "label": "Method", "options": ["uniform", "quantile", "kmeans"], "default": "uniform", "description": "Binning method: uniform (equal width), quantile (equal count), kmeans (clustering)"},
            "n_bins": {"type": "int", "label": "Number of Bins", "default": 5, "min": 2, "max": 256, "description": "Number of discrete levels"},
            "output_type": {"type": "select", "label": "Output Type", "options": ["labels", "centroids"], "default": "centroids", "description": "Output as bin labels (0,1,2,...) or bin centroid values"}
        }
    },

    # ===========================================================================
    # ANNOTATION NODES
    # ===========================================================================
    "CommentNode": {
        "display_name": "Comment",
        "category": "Annotations",
        "description": "Add notes to workflow",
        "inputs": [],
        "outputs": [],
        "parameters": {
            "text": {"type": "string", "label": "Comment", "default": "Enter note here...", "multiline": True},
            "bg_color": {"type": "color", "label": "Background Color", "default": "#F5A9B8", "description": "Background color with RGB sliders"},
            "text_color": {"type": "color", "label": "Text Color", "default": "#333333", "description": "Text color with RGB sliders"},
            "opacity": {"type": "float", "label": "Opacity", "default": 0.9, "min": 0.1, "max": 1.0, "description": "Background transparency (0.1-1.0)"},
            "font_size": {"type": "int", "label": "Font Size", "default": 12, "min": 8, "max": 32, "description": "Font size in pixels"},
            "node_width": {"type": "int", "label": "Width", "default": 180, "min": 100, "max": 600, "description": "Node width in pixels"},
            "node_height": {"type": "int", "label": "Height", "default": 100, "min": 60, "max": 400, "description": "Node height in pixels"}
        }
    },

    # ==========================================================================
    # Map Processing Nodes
    # ==========================================================================

    "MapGaussianFilter": {
        "display_name": "Map Gaussian Filter",
        "category": "Image Processing",
        "description": "Apply Gaussian smoothing filter to a map image",
        "inputs": [
            {"id": "map", "name": "Map", "port_type": "map", "required": True, "description": "Input map image"}
        ],
        "outputs": [
            {"id": "filtered_map", "name": "Filtered Map", "port_type": "map", "description": "Gaussian filtered map"}
        ],
        "parameters": {
            "sigma": {"type": "float", "label": "Sigma", "default": 1.0, "min": 0.1, "max": 10.0, "description": "Gaussian sigma (higher = more smoothing)"}
        }
    },

    "MapMedianFilter": {
        "display_name": "Map Median Filter",
        "category": "Image Processing",
        "description": "Apply median filter to a map image (removes salt-and-pepper noise)",
        "inputs": [
            {"id": "map", "name": "Map", "port_type": "map", "required": True, "description": "Input map image"}
        ],
        "outputs": [
            {"id": "filtered_map", "name": "Filtered Map", "port_type": "map", "description": "Median filtered map"}
        ],
        "parameters": {
            "size": {"type": "int", "label": "Kernel Size", "default": 3, "min": 3, "max": 21, "description": "Filter kernel size (odd numbers)"}
        }
    },

    "MapPlaneLevel": {
        "display_name": "Map Plane Level",
        "category": "Image Processing",
        "description": "Subtract a fitted plane from the map to remove tilt",
        "inputs": [
            {"id": "map", "name": "Map", "port_type": "map", "required": True, "description": "Input map image"}
        ],
        "outputs": [
            {"id": "leveled_map", "name": "Leveled Map", "port_type": "map", "description": "Plane-leveled map"}
        ],
        "parameters": {}
    },

    "MapRowAlign": {
        "display_name": "Map Row Align",
        "category": "Image Processing",
        "description": "Align rows by subtracting the median of each row",
        "inputs": [
            {"id": "map", "name": "Map", "port_type": "map", "required": True, "description": "Input map image"}
        ],
        "outputs": [
            {"id": "aligned_map", "name": "Aligned Map", "port_type": "map", "description": "Row-aligned map"}
        ],
        "parameters": {}
    },

    "MapNormalize": {
        "display_name": "Map Normalize",
        "category": "Image Processing",
        "description": "Normalize map values to [0, 1] range",
        "inputs": [
            {"id": "map", "name": "Map", "port_type": "map", "required": True, "description": "Input map image"}
        ],
        "outputs": [
            {"id": "normalized_map", "name": "Normalized Map", "port_type": "map", "description": "Normalized map"}
        ],
        "parameters": {}
    },

    "MapPolynomialBGRemoval": {
        "display_name": "Map Polynomial BG Removal",
        "category": "Image Processing",
        "description": "Remove polynomial background from map",
        "inputs": [
            {"id": "map", "name": "Map", "port_type": "map", "required": True, "description": "Input map image"}
        ],
        "outputs": [
            {"id": "corrected_map", "name": "Corrected Map", "port_type": "map", "description": "Background-corrected map"}
        ],
        "parameters": {
            "order": {"type": "int", "label": "Polynomial Order", "default": 2, "min": 1, "max": 6, "description": "Order of polynomial to fit (higher = more flexible)"}
        }
    },

    # ==========================================================================
    # STS Analysis Nodes
    # Algorithms adapted from ststools by Rafael Reis
    # (https://github.com/rafinhareis/ststools)
    # ==========================================================================

    "FilterBadData": {
        "display_name": "Filter Bad Data",
        "category": "Processing",
        "description": "Classify and separate bad spectra (saturation, noise, linear artifacts, periodic noise)",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "good_data", "name": "Good Data", "port_type": "dataset"},
            {"id": "bad_data", "name": "Bad Data", "port_type": "dataset"},
            {"id": "fft_spectra", "name": "FFT Spectra", "port_type": "dataset"},
            {"id": "report", "name": "Report", "port_type": "string"}
        ],
        "parameters": {
            "weight_saturation": {"type": "float", "default": 1.0, "min": 0.0, "max": 1.0, "label": "Saturation Weight"},
            "weight_noise": {"type": "float", "default": 1.0, "min": 0.0, "max": 1.0, "label": "Noise Weight"},
            "weight_linear": {"type": "float", "default": 1.0, "min": 0.0, "max": 1.0, "label": "Linear Artifact Weight"},
            "weight_periodic": {"type": "float", "default": 1.0, "min": 0.0, "max": 1.0, "label": "Periodic Noise Weight"},
            "weight_partial_noise": {"type": "float", "default": 1.0, "min": 0.0, "max": 1.0, "label": "Partial Noise Weight"},
            "threshold": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "label": "Quality Threshold"},
            "correct_periodic": {"type": "bool", "default": False, "label": "Correct Periodic Noise"}
        }
    },

    "DetectBandgapDoping": {
        "display_name": "Detect Bandgap & Doping",
        "category": "Analysis",
        "description": "Bandgap size and doping type (N/P/Neutral) per spectrum",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "bandgap_data", "name": "Bandgap Data", "port_type": "flat_data"},
            {"id": "doping_data", "name": "Doping Data", "port_type": "flat_data"}
        ],
        "parameters": {
            "smoothing": {"type": "float", "default": 1.0, "min": 0, "max": 50, "label": "Smoothing (%)"},
            "delta": {"type": "float", "default": 5.0, "min": 0.1, "max": 100, "label": "Delta Threshold (%)"},
            "resolution": {"type": "float", "default": 0.01, "min": 0.001, "max": 1.0, "label": "Doping Offset Tolerance (V)"},
            "smoothing_method": {"type": "select", "default": "Savgol", "options": ["Savgol", "Moving Avg", "None"], "label": "Smoothing Method"}
        }
    },

    "DiracPointEstimator": {
        "display_name": "Dirac Point Estimator",
        "category": "Analysis",
        "description": "Estimate Dirac point from linear slope intersections",
        "inputs": [
            {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
        ],
        "outputs": [
            {"id": "flat_data", "name": "Dirac Point Data", "port_type": "flat_data"}
        ],
        "parameters": {
            "auto_detect": {"type": "bool", "default": True, "label": "Auto-detect Fit Ranges"},
            "left_min": {"type": "float", "default": -1.0, "label": "Left Fit Min (V)"},
            "left_max": {"type": "float", "default": -0.2, "label": "Left Fit Max (V)"},
            "right_min": {"type": "float", "default": 0.2, "label": "Right Fit Min (V)"},
            "right_max": {"type": "float", "default": 1.0, "label": "Right Fit Max (V)"},
            "smoothing": {"type": "float", "default": 1.0, "min": 0, "max": 50, "label": "Smoothing (%)"},
            "smoothing_method": {"type": "select", "default": "Savgol", "options": ["Savgol", "Moving Avg", "None"], "label": "Smoothing Method"}
        }
    },

    # ===========================================================================
    # TEXT OUTPUT NODE
    # ===========================================================================
    "TextOutput": {
        "display_name": "Text Report",
        "category": "Output",
        "description": "Save text report to project outputs",
        "inputs": [
            {"id": "text", "name": "Text", "port_type": "string", "required": True}
        ],
        "outputs": [],
        "parameters": {
            "output_name": {"type": "string", "label": "Report Name", "required": True, "default": "Report"}
        }
    }
}


def create_node_from_tool(tool_name: str, x: float = 100, y: float = 100) -> Optional[WorkflowNode]:
    """Create a WorkflowNode from a tool definition"""
    if tool_name not in TOOL_DEFINITIONS:
        logger.error(f"Unknown tool: {tool_name}")
        return None

    tool_def = TOOL_DEFINITIONS[tool_name]
    node_id = str(uuid.uuid4())[:8]

    # Create input ports
    inputs = []
    for port_def in tool_def.get('inputs', []):
        inputs.append(Port(
            id=port_def['id'],
            name=port_def['name'],
            port_type=PortType(port_def['port_type']),
            is_input=True,
            required=port_def.get('required', True),
            description=port_def.get('description', ''),
            multi_input=port_def.get('multi_input', False)
        ))

    # Create output ports
    outputs = []
    for port_def in tool_def.get('outputs', []):
        outputs.append(Port(
            id=port_def['id'],
            name=port_def['name'],
            port_type=PortType(port_def['port_type']),
            is_input=False,
            required=False,
            description=port_def.get('description', ''),
            multi_input=port_def.get('multi_input', False)
        ))

    # Create default parameters
    parameters = {}
    for param_name, param_def in tool_def.get('parameters', {}).items():
        if 'default' in param_def:
            parameters[param_name] = param_def['default']

    return WorkflowNode(
        id=node_id,
        tool_name=tool_name,
        display_name=tool_def['display_name'],
        x=x,
        y=y,
        inputs=inputs,
        outputs=outputs,
        parameters=parameters
    )


def get_tool_categories() -> List[Dict]:
    """Get tools organized by category with optimal ordering.

    Returns a list of {"category": str, "tools": List[str]} dicts to preserve
    category order (PySide6 QVariantMap sorts keys alphabetically).

    Category order: Input -> Output -> Annotations -> Processing -> Analysis -> Visualization -> Image Processing
    Within each category, tools are sorted for optimal UX flow.
    """
    # Define category order for optimal UX - Image Processing last
    category_order = ["Input", "Output", "Annotations", "Processing", "Analysis", "Visualization", "Image Processing"]

    categories: Dict[str, List[str]] = {}
    for tool_name, tool_def in TOOL_DEFINITIONS.items():
        category = tool_def.get('category', 'Other')
        if category not in categories:
            categories[category] = []
        categories[category].append(tool_name)

    # Sort tools within each category for logical flow
    tool_order = {
        # Input tools
        "DatasetInput": 0,
        "MapInput": 1,
        "ImageInput": 2,
        "FlatDataInput": 3,
        "IntervalInput": 4,
        # Output tools
        "DatasetOutput": 0,
        "MapOutput": 1,
        "ImageOutput": 2,
        "FlatDataOutput": 3,
        "TextOutput": 4,
        # Annotations
        "CommentNode": 0,
        # Processing tools - ordered by typical workflow
        "ColumnSelector": 0,
        "TruncateData": 1,
        "Derivative": 2,
        "CurveSmoothing": 2,
        "CurveFitting": 3,
        "Integration": 4,
        "SpatialAverage": 5,
        "DataManipulation": 6,
        "FFT1D": 7,
        "FilterBadData": 8,
        "CosmicRayFilter": 9,
        "BackgroundSubtraction": 10,
        # Analysis tools
        "PeakFinder": 0,
        "DetectBandgapDoping": 1,
        "DiracPointEstimator": 2,
        # Visualization
        "MapGenerator": 0,
        # Image Processing - image tools first, then map processing
        "ImageSmoothing": 0,
        "GradientFilter": 1,
        "ImageDiscretizer": 2,
        "MapGaussianFilter": 3,
        "MapMedianFilter": 4,
        "MapPlaneLevel": 5,
        "MapRowAlign": 6,
        "MapNormalize": 7,
        "MapPolynomialBGRemoval": 8,
    }

    for category in categories:
        categories[category].sort(key=lambda x: tool_order.get(x, 999))

    # Build ordered list to preserve category order (QVariantList, not QVariantMap)
    result = []
    for cat in category_order:
        if cat in categories:
            result.append({"category": cat, "tools": categories[cat]})

    # Add any remaining categories not in the order list
    seen = {r["category"] for r in result}
    for cat in categories:
        if cat not in seen:
            result.append({"category": cat, "tools": categories[cat]})

    return result


def get_tool_info(tool_name: str) -> Optional[Dict]:
    """Get information about a tool including port types for UI display"""
    tool_def = TOOL_DEFINITIONS.get(tool_name)
    if not tool_def:
        return None

    # Collect unique port types from inputs and outputs
    port_types = []
    seen_types = set()

    # Add input port types first
    for port in tool_def.get('inputs', []):
        pt = port.get('port_type', 'any')
        if pt not in seen_types:
            port_types.append(pt)
            seen_types.add(pt)

    # Add output port types
    for port in tool_def.get('outputs', []):
        pt = port.get('port_type', 'any')
        if pt not in seen_types:
            port_types.append(pt)
            seen_types.add(pt)

    # Return tool definition with port_types added
    return {
        **tool_def,
        'port_types': port_types
    }
