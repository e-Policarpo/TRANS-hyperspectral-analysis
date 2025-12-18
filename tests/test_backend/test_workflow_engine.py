"""
Tests for Workflow Engine classes
Target coverage: 90%
"""

import pytest
import json
from datetime import datetime

from src.backend.workflow_engine import (
    Port, PortType, WorkflowNode, Connection, Workflow,
    TOOL_DEFINITIONS, create_node_from_tool, get_tool_categories, get_tool_info
)


class TestPortType:
    """Tests for PortType enum."""

    def test_port_type_values(self):
        """Test all PortType enum values exist."""
        assert PortType.DATASET.value == "dataset"
        assert PortType.FLAT_DATA.value == "flat_data"
        assert PortType.IMAGE.value == "image"
        assert PortType.MAP.value == "map"  # New MAP type for map processing
        assert PortType.TABLE.value == "table"
        assert PortType.NUMBER.value == "number"
        assert PortType.STRING.value == "string"
        assert PortType.INTERVAL_LIST.value == "intervals"
        assert PortType.ANY.value == "any"

    def test_map_port_type_creation(self):
        """Test MAP port type can be used in ports."""
        port = Port(
            id="map_port",
            name="Map",
            port_type=PortType.MAP,
            is_input=True
        )
        assert port.port_type == PortType.MAP
        assert port.port_type.value == "map"


class TestPort:
    """Tests for Port dataclass."""

    def test_port_creation(self):
        """WE-01: Create Port object."""
        port = Port(
            id="test_port",
            name="Test Port",
            port_type=PortType.DATASET,
            is_input=True
        )
        assert port.id == "test_port"
        assert port.name == "Test Port"
        assert port.port_type == PortType.DATASET
        assert port.is_input is True
        assert port.required is True  # default
        assert port.multi_input is False  # default

    def test_port_creation_with_defaults(self):
        """Test Port with non-default values."""
        port = Port(
            id="optional_port",
            name="Optional Port",
            port_type=PortType.NUMBER,
            is_input=True,
            required=False,
            default_value=10,
            description="An optional numeric port",
            multi_input=False
        )
        assert port.required is False
        assert port.default_value == 10
        assert port.description == "An optional numeric port"

    def test_port_multi_input(self):
        """Test multi_input port flag."""
        port = Port(
            id="multi_port",
            name="Multi Port",
            port_type=PortType.ANY,
            is_input=True,
            multi_input=True
        )
        assert port.multi_input is True

    def test_port_serialization(self):
        """WE-02: Port to_dict/from_dict round-trip."""
        original = Port(
            id="test_port",
            name="Test Port",
            port_type=PortType.DATASET,
            is_input=True,
            required=False,
            default_value="default",
            description="Test description",
            multi_input=True
        )

        # Serialize
        port_dict = original.to_dict()
        assert port_dict['id'] == "test_port"
        assert port_dict['port_type'] == "dataset"
        assert port_dict['multi_input'] is True

        # Deserialize
        restored = Port.from_dict(port_dict)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.port_type == original.port_type
        assert restored.is_input == original.is_input
        assert restored.required == original.required
        assert restored.multi_input == original.multi_input


class TestWorkflowNode:
    """Tests for WorkflowNode dataclass."""

    def test_node_creation(self):
        """WE-03: Create WorkflowNode."""
        input_port = Port("in", "Input", PortType.DATASET, True)
        output_port = Port("out", "Output", PortType.DATASET, False)

        node = WorkflowNode(
            id="node_001",
            tool_name="TestTool",
            display_name="Test Tool",
            x=100.0,
            y=200.0,
            inputs=[input_port],
            outputs=[output_port],
            parameters={'param1': 10}
        )

        assert node.id == "node_001"
        assert node.tool_name == "TestTool"
        assert len(node.inputs) == 1
        assert len(node.outputs) == 1
        assert node.parameters['param1'] == 10

    def test_node_serialization(self):
        """WE-04: Node to_dict/from_dict round-trip."""
        original = WorkflowNode(
            id="node_001",
            tool_name="CurveSmoothing",
            display_name="Curve Smoothing",
            x=150.0,
            y=250.0,
            inputs=[Port("dataset", "Dataset", PortType.DATASET, True)],
            outputs=[Port("smoothed", "Smoothed", PortType.DATASET, False)],
            parameters={'window_size': 11, 'poly_order': 3}
        )

        # Serialize
        node_dict = original.to_dict()
        assert node_dict['id'] == "node_001"
        assert node_dict['x'] == 150.0
        assert len(node_dict['inputs']) == 1
        assert node_dict['parameters']['window_size'] == 11

        # Deserialize
        restored = WorkflowNode.from_dict(node_dict)
        assert restored.id == original.id
        assert restored.tool_name == original.tool_name
        assert restored.x == original.x
        assert len(restored.inputs) == len(original.inputs)
        # Check that all saved parameters are preserved (defaults may be added)
        for key, value in original.parameters.items():
            assert restored.parameters[key] == value

    def test_node_get_input_port(self):
        """Test getting input port by ID."""
        node = WorkflowNode(
            id="n1",
            tool_name="Test",
            display_name="Test",
            inputs=[
                Port("in1", "Input 1", PortType.DATASET, True),
                Port("in2", "Input 2", PortType.NUMBER, True)
            ],
            outputs=[]
        )

        port = node.get_input_port("in1")
        assert port is not None
        assert port.name == "Input 1"

        port2 = node.get_input_port("nonexistent")
        assert port2 is None

    def test_node_get_output_port(self):
        """Test getting output port by ID."""
        node = WorkflowNode(
            id="n1",
            tool_name="Test",
            display_name="Test",
            inputs=[],
            outputs=[
                Port("out1", "Output 1", PortType.DATASET, False),
                Port("out2", "Output 2", PortType.IMAGE, False)
            ]
        )

        port = node.get_output_port("out1")
        assert port is not None
        assert port.name == "Output 1"

        port2 = node.get_output_port("nonexistent")
        assert port2 is None


class TestConnection:
    """Tests for Connection dataclass."""

    def test_connection_creation(self):
        """WE-05: Create Connection."""
        conn = Connection(
            id="conn_001",
            source_node_id="node_1",
            source_port_id="output",
            target_node_id="node_2",
            target_port_id="input"
        )

        assert conn.id == "conn_001"
        assert conn.source_node_id == "node_1"
        assert conn.source_port_id == "output"
        assert conn.target_node_id == "node_2"
        assert conn.target_port_id == "input"

    def test_connection_serialization(self):
        """Test Connection to_dict/from_dict."""
        original = Connection(
            id="conn_001",
            source_node_id="node_1",
            source_port_id="out",
            target_node_id="node_2",
            target_port_id="in"
        )

        conn_dict = original.to_dict()
        restored = Connection.from_dict(conn_dict)

        assert restored.id == original.id
        assert restored.source_node_id == original.source_node_id
        assert restored.target_port_id == original.target_port_id


class TestWorkflow:
    """Tests for Workflow class."""

    @pytest.fixture
    def simple_workflow(self):
        """Create a simple workflow for testing."""
        workflow = Workflow(id="wf_001", name="Test Workflow")

        # Add nodes
        node1 = WorkflowNode(
            id="n1",
            tool_name="DatasetInput",
            display_name="Dataset Input",
            outputs=[Port("dataset", "Dataset", PortType.DATASET, False)]
        )
        node2 = WorkflowNode(
            id="n2",
            tool_name="CurveSmoothing",
            display_name="Smoothing",
            inputs=[Port("dataset", "Dataset", PortType.DATASET, True)],
            outputs=[Port("smoothed", "Smoothed", PortType.DATASET, False)]
        )

        workflow.add_node(node1)
        workflow.add_node(node2)

        return workflow

    def test_workflow_add_node(self, simple_workflow):
        """WE-06: Add node to workflow."""
        assert len(simple_workflow.nodes) == 2

        new_node = WorkflowNode(
            id="n3",
            tool_name="Derivative",
            display_name="Derivative"
        )
        simple_workflow.add_node(new_node)

        assert len(simple_workflow.nodes) == 3
        assert simple_workflow.get_node("n3") is not None

    def test_workflow_remove_node(self, simple_workflow):
        """WE-07: Remove node removes connections too."""
        # Add connection
        conn = Connection(
            id="c1",
            source_node_id="n1",
            source_port_id="dataset",
            target_node_id="n2",
            target_port_id="dataset"
        )
        simple_workflow.add_connection(conn)

        assert len(simple_workflow.connections) == 1

        # Remove source node
        simple_workflow.remove_node("n1")

        assert len(simple_workflow.nodes) == 1
        assert len(simple_workflow.connections) == 0  # Connection should be removed

    def test_workflow_add_connection(self, simple_workflow):
        """WE-08: Add valid connection."""
        conn = Connection(
            id="c1",
            source_node_id="n1",
            source_port_id="dataset",
            target_node_id="n2",
            target_port_id="dataset"
        )
        result = simple_workflow.add_connection(conn)

        assert result is True
        assert len(simple_workflow.connections) == 1

    def test_workflow_add_invalid_connection_nonexistent_node(self, simple_workflow):
        """WE-09: Add connection to non-existent node fails."""
        conn = Connection(
            id="c1",
            source_node_id="nonexistent",
            source_port_id="out",
            target_node_id="n2",
            target_port_id="dataset"
        )
        result = simple_workflow.add_connection(conn)

        assert result is False
        assert len(simple_workflow.connections) == 0


class TestWorkflowValidation:
    """Tests for workflow validation."""

    @pytest.fixture
    def workflow_with_types(self):
        """Create workflow with typed ports."""
        workflow = Workflow(id="wf_typed", name="Typed Workflow")

        node1 = WorkflowNode(
            id="n1",
            tool_name="Source",
            display_name="Source",
            outputs=[Port("dataset_out", "Dataset", PortType.DATASET, False)]
        )
        node2 = WorkflowNode(
            id="n2",
            tool_name="ProcessDataset",
            display_name="Process",
            inputs=[Port("dataset_in", "Dataset", PortType.DATASET, True)],
            outputs=[Port("result", "Result", PortType.DATASET, False)]
        )
        node3 = WorkflowNode(
            id="n3",
            tool_name="ProcessImage",
            display_name="Image Process",
            inputs=[Port("image_in", "Image", PortType.IMAGE, True)]
        )
        node4 = WorkflowNode(
            id="n4",
            tool_name="AnyInput",
            display_name="Any Input",
            inputs=[Port("any_in", "Any", PortType.ANY, True)]
        )

        workflow.add_node(node1)
        workflow.add_node(node2)
        workflow.add_node(node3)
        workflow.add_node(node4)

        return workflow

    def test_validate_connection_type_match(self, workflow_with_types):
        """WE-10: Same port types are valid."""
        conn = Connection(
            id="c1",
            source_node_id="n1",
            source_port_id="dataset_out",
            target_node_id="n2",
            target_port_id="dataset_in"
        )
        result = workflow_with_types.validate_connection(conn)
        assert result is True

    def test_validate_connection_type_mismatch(self, workflow_with_types):
        """WE-11: Different types are invalid."""
        conn = Connection(
            id="c1",
            source_node_id="n1",
            source_port_id="dataset_out",
            target_node_id="n3",
            target_port_id="image_in"
        )
        result = workflow_with_types.validate_connection(conn)
        assert result is False

    def test_validate_connection_any_type(self, workflow_with_types):
        """WE-12: ANY port type accepts anything."""
        conn = Connection(
            id="c1",
            source_node_id="n1",
            source_port_id="dataset_out",
            target_node_id="n4",
            target_port_id="any_in"
        )
        result = workflow_with_types.validate_connection(conn)
        assert result is True

    def test_validate_connection_duplicate(self):
        """WE-13: Duplicate connection to same input is invalid."""
        workflow = Workflow(id="wf", name="Test")

        node1 = WorkflowNode(
            id="n1", tool_name="A", display_name="A",
            outputs=[Port("out", "Out", PortType.DATASET, False)]
        )
        node2 = WorkflowNode(
            id="n2", tool_name="B", display_name="B",
            outputs=[Port("out", "Out", PortType.DATASET, False)]
        )
        node3 = WorkflowNode(
            id="n3", tool_name="C", display_name="C",
            inputs=[Port("in", "In", PortType.DATASET, True, multi_input=False)]
        )

        workflow.add_node(node1)
        workflow.add_node(node2)
        workflow.add_node(node3)

        # First connection
        conn1 = Connection("c1", "n1", "out", "n3", "in")
        workflow.add_connection(conn1)

        # Second connection to same input
        conn2 = Connection("c2", "n2", "out", "n3", "in")
        result = workflow.validate_connection(conn2)

        assert result is False

    def test_validate_multi_input_port(self):
        """WE-14: Multiple connections to multi_input port are valid."""
        workflow = Workflow(id="wf", name="Test")

        node1 = WorkflowNode(
            id="n1", tool_name="A", display_name="A",
            outputs=[Port("out", "Out", PortType.DATASET, False)]
        )
        node2 = WorkflowNode(
            id="n2", tool_name="B", display_name="B",
            outputs=[Port("out", "Out", PortType.DATASET, False)]
        )
        node3 = WorkflowNode(
            id="n3", tool_name="C", display_name="C",
            inputs=[Port("in", "In", PortType.ANY, True, multi_input=True)]
        )

        workflow.add_node(node1)
        workflow.add_node(node2)
        workflow.add_node(node3)

        conn1 = Connection("c1", "n1", "out", "n3", "in")
        workflow.add_connection(conn1)

        conn2 = Connection("c2", "n2", "out", "n3", "in")
        result = workflow.validate_connection(conn2)

        assert result is True


class TestCycleDetection:
    """Tests for cycle detection in workflow graphs."""

    def test_cycle_detection_simple(self):
        """WE-15: Simple A→B→A cycle detected."""
        workflow = Workflow(id="wf", name="Test")

        nodeA = WorkflowNode(
            id="A", tool_name="A", display_name="A",
            inputs=[Port("in", "In", PortType.ANY, True)],
            outputs=[Port("out", "Out", PortType.ANY, False)]
        )
        nodeB = WorkflowNode(
            id="B", tool_name="B", display_name="B",
            inputs=[Port("in", "In", PortType.ANY, True)],
            outputs=[Port("out", "Out", PortType.ANY, False)]
        )

        workflow.add_node(nodeA)
        workflow.add_node(nodeB)

        # A → B
        workflow.add_connection(Connection("c1", "A", "out", "B", "in"))

        # B → A (would create cycle)
        conn_cycle = Connection("c2", "B", "out", "A", "in")
        result = workflow.validate_connection(conn_cycle)

        assert result is False

    def test_cycle_detection_complex(self):
        """WE-16: Complex A→B→C→A cycle detected."""
        workflow = Workflow(id="wf", name="Test")

        for name in ["A", "B", "C"]:
            node = WorkflowNode(
                id=name, tool_name=name, display_name=name,
                inputs=[Port("in", "In", PortType.ANY, True)],
                outputs=[Port("out", "Out", PortType.ANY, False)]
            )
            workflow.add_node(node)

        workflow.add_connection(Connection("c1", "A", "out", "B", "in"))
        workflow.add_connection(Connection("c2", "B", "out", "C", "in"))

        # C → A (would create cycle)
        conn_cycle = Connection("c3", "C", "out", "A", "in")
        result = workflow.validate_connection(conn_cycle)

        assert result is False

    def test_no_cycle_linear(self):
        """WE-17: Linear graph has no cycle."""
        workflow = Workflow(id="wf", name="Test")

        for name in ["A", "B", "C", "D"]:
            node = WorkflowNode(
                id=name, tool_name=name, display_name=name,
                inputs=[Port("in", "In", PortType.ANY, True, required=False)],
                outputs=[Port("out", "Out", PortType.ANY, False)]
            )
            workflow.add_node(node)

        workflow.add_connection(Connection("c1", "A", "out", "B", "in"))
        workflow.add_connection(Connection("c2", "B", "out", "C", "in"))

        # C → D (no cycle)
        conn = Connection("c3", "C", "out", "D", "in")
        result = workflow.validate_connection(conn)

        assert result is True


class TestWorkflowValidationComplete:
    """Tests for complete workflow validation."""

    def test_workflow_validation_empty(self):
        """WE-18a: Empty workflow is invalid."""
        workflow = Workflow(id="wf", name="Empty")
        is_valid, errors = workflow.validate()

        assert is_valid is False
        assert len(errors) > 0

    def test_workflow_validation_required_inputs(self):
        """WE-19: Unconnected required inputs are errors."""
        workflow = Workflow(id="wf", name="Test")

        node = WorkflowNode(
            id="n1", tool_name="Test", display_name="Test",
            inputs=[Port("required_in", "Required", PortType.DATASET, True, required=True)]
        )
        workflow.add_node(node)

        is_valid, errors = workflow.validate()
        assert is_valid is False
        assert any("required" in e.lower() or "Required" in e for e in errors)


class TestExecutionOrder:
    """Tests for topological sort."""

    def test_execution_order_simple(self):
        """WE-20: Simple DAG has correct topological order."""
        workflow = Workflow(id="wf", name="Test")

        # A → B → C
        for name in ["A", "B", "C"]:
            node = WorkflowNode(
                id=name, tool_name=name, display_name=name,
                inputs=[Port("in", "In", PortType.ANY, True, required=False)],
                outputs=[Port("out", "Out", PortType.ANY, False)]
            )
            workflow.add_node(node)

        workflow.add_connection(Connection("c1", "A", "out", "B", "in"))
        workflow.add_connection(Connection("c2", "B", "out", "C", "in"))

        order = workflow.get_execution_order()

        # A should come before B, B before C
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_execution_order_complex(self):
        """WE-21: Complex DAG with multiple paths."""
        workflow = Workflow(id="wf", name="Test")

        # A → B → D
        # A → C → D
        for name in ["A", "B", "C", "D"]:
            node = WorkflowNode(
                id=name, tool_name=name, display_name=name,
                inputs=[Port("in", "In", PortType.ANY, True, required=False, multi_input=True)],
                outputs=[Port("out", "Out", PortType.ANY, False)]
            )
            workflow.add_node(node)

        workflow.add_connection(Connection("c1", "A", "out", "B", "in"))
        workflow.add_connection(Connection("c2", "A", "out", "C", "in"))
        workflow.add_connection(Connection("c3", "B", "out", "D", "in"))
        workflow.add_connection(Connection("c4", "C", "out", "D", "in"))

        order = workflow.get_execution_order()

        # A should come first
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        # D should come last
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")


class TestToolDefinitions:
    """Tests for TOOL_DEFINITIONS and related functions."""

    def test_create_node_from_tool(self):
        """WE-22: Create node from TOOL_DEFINITIONS."""
        node = create_node_from_tool("DatasetInput", x=100, y=200)

        assert node is not None
        assert node.tool_name == "DatasetInput"
        assert node.display_name == "Dataset"  # Updated display name
        assert node.x == 100
        assert node.y == 200
        assert len(node.outputs) >= 1

    def test_create_node_from_tool_with_parameters(self):
        """Test node creation includes default parameters."""
        node = create_node_from_tool("CurveSmoothing")

        assert node is not None
        assert 'window_size' in node.parameters
        assert node.parameters['window_size'] == 11  # default value

    def test_create_node_from_unknown_tool(self):
        """Test creating node from unknown tool returns None."""
        node = create_node_from_tool("NonExistentTool")
        assert node is None

    def test_get_tool_categories(self):
        """WE-23: Get tools organized by category."""
        categories = get_tool_categories()

        assert isinstance(categories, dict)
        assert "Input" in categories
        assert "Processing" in categories
        assert "Output" in categories

        assert "DatasetInput" in categories["Input"]
        assert "CurveSmoothing" in categories["Processing"]

    def test_get_tool_info(self):
        """Test getting tool info."""
        info = get_tool_info("CurveSmoothing")

        assert info is not None
        assert info['display_name'] == "Smoothing"  # Updated display name
        assert 'inputs' in info
        assert 'outputs' in info
        assert 'parameters' in info

    def test_get_tool_info_unknown(self):
        """Test getting info for unknown tool."""
        info = get_tool_info("NonExistentTool")
        assert info is None

    def test_get_tool_info_includes_port_types(self):
        """Test that get_tool_info returns port_types list."""
        info = get_tool_info("Integration")

        assert info is not None
        assert 'port_types' in info
        assert isinstance(info['port_types'], list)
        # Integration has dataset input, intervals input, flat_data output, intervals output
        assert 'dataset' in info['port_types']
        assert 'flat_data' in info['port_types']
        assert 'intervals' in info['port_types']

    def test_get_tool_categories_ordering(self):
        """Test that categories are returned in correct order.

        Expected order: Input -> Output -> Annotations -> Processing -> Analysis -> Visualization -> Image Processing
        Image Processing should be LAST.
        """
        categories = get_tool_categories()

        # Convert dict keys to list to check order
        category_list = list(categories.keys())

        # Input should come before Output
        if "Input" in category_list and "Output" in category_list:
            assert category_list.index("Input") < category_list.index("Output")

        # Output should come before Annotations
        if "Output" in category_list and "Annotations" in category_list:
            assert category_list.index("Output") < category_list.index("Annotations")

        # Annotations should come before Processing
        if "Annotations" in category_list and "Processing" in category_list:
            assert category_list.index("Annotations") < category_list.index("Processing")

        # Processing should come before Analysis
        if "Processing" in category_list and "Analysis" in category_list:
            assert category_list.index("Processing") < category_list.index("Analysis")

        # Analysis should come before Visualization
        if "Analysis" in category_list and "Visualization" in category_list:
            assert category_list.index("Analysis") < category_list.index("Visualization")

        # Visualization should come before Image Processing
        if "Visualization" in category_list and "Image Processing" in category_list:
            assert category_list.index("Visualization") < category_list.index("Image Processing")

        # Image Processing should be LAST
        if "Image Processing" in category_list:
            assert category_list.index("Image Processing") == len(category_list) - 1, \
                f"Image Processing should be last but is at index {category_list.index('Image Processing')} of {len(category_list)}"

    def test_tools_within_category_ordering(self):
        """Test that tools within Processing category are in workflow order."""
        categories = get_tool_categories()

        if "Processing" in categories:
            processing_tools = categories["Processing"]
            # TruncateData should come before Derivative
            if "TruncateData" in processing_tools and "Derivative" in processing_tools:
                assert processing_tools.index("TruncateData") < processing_tools.index("Derivative")
            # Derivative should come before Integration
            if "Derivative" in processing_tools and "Integration" in processing_tools:
                assert processing_tools.index("Derivative") < processing_tools.index("Integration")

    def test_display_names_homogenized(self):
        """Test that display names are simplified/homogenized."""
        # Check the simplified display names
        assert get_tool_info("DatasetInput")['display_name'] == "Dataset"
        assert get_tool_info("DatasetOutput")['display_name'] == "Dataset"
        assert get_tool_info("TruncateData")['display_name'] == "Truncate"
        assert get_tool_info("CurveSmoothing")['display_name'] == "Smoothing"
        assert get_tool_info("CurveFitting")['display_name'] == "Baseline"
        assert get_tool_info("DataManipulation")['display_name'] == "Math Operation"
        assert get_tool_info("FFT1D")['display_name'] == "FFT"


class TestWorkflowSerialization:
    """Tests for workflow serialization."""

    def test_workflow_serialization(self, sample_workflow_dict):
        """WE-24: Workflow to_dict/from_dict round-trip."""
        workflow = Workflow.from_dict(sample_workflow_dict)

        assert workflow.id == sample_workflow_dict['id']
        assert workflow.name == sample_workflow_dict['name']
        assert len(workflow.nodes) == 2
        assert len(workflow.connections) == 1

        # Serialize back
        serialized = workflow.to_dict()
        assert serialized['id'] == sample_workflow_dict['id']
        assert len(serialized['nodes']) == 2

    def test_workflow_json_compatible(self, sample_workflow_dict):
        """Test workflow can be serialized to JSON."""
        workflow = Workflow.from_dict(sample_workflow_dict)
        serialized = workflow.to_dict()

        # Should not raise
        json_str = json.dumps(serialized)
        assert len(json_str) > 0

        # Should be able to parse back
        parsed = json.loads(json_str)
        assert parsed['name'] == workflow.name


class TestNewTools:
    """Tests for new tools added to the workflow system."""

    def test_image_discretizer_exists(self):
        """Test ImageDiscretizer tool is defined."""
        assert "ImageDiscretizer" in TOOL_DEFINITIONS
        tool_def = TOOL_DEFINITIONS["ImageDiscretizer"]
        assert tool_def["category"] == "Image Processing"
        assert tool_def["display_name"] == "Image Discretizer"

    def test_image_discretizer_parameters(self):
        """Test ImageDiscretizer has correct parameters."""
        tool_def = TOOL_DEFINITIONS["ImageDiscretizer"]
        params = tool_def["parameters"]

        assert "method" in params
        assert params["method"]["default"] == "uniform"
        assert "n_bins" in params
        assert params["n_bins"]["default"] == 5
        assert "output_type" in params
        assert params["output_type"]["default"] == "centroids"

    def test_image_discretizer_node_creation(self):
        """Test creating ImageDiscretizer node."""
        node = create_node_from_tool("ImageDiscretizer")
        assert node is not None
        assert node.tool_name == "ImageDiscretizer"
        assert len(node.inputs) == 1
        assert len(node.outputs) == 2
        assert node.parameters.get("method") == "uniform"
        assert node.parameters.get("n_bins") == 5

    def test_map_processing_tools_exist(self):
        """Test all map processing tools are defined."""
        map_tools = [
            "MapGaussianFilter",
            "MapMedianFilter",
            "MapPlaneLevel",
            "MapRowAlign",
            "MapNormalize",
            "MapPolynomialBGRemoval"
        ]
        for tool_name in map_tools:
            assert tool_name in TOOL_DEFINITIONS, f"{tool_name} not found"
            assert TOOL_DEFINITIONS[tool_name]["category"] == "Image Processing"

    def test_map_processing_tools_use_map_port_type(self):
        """Test map processing tools use MAP port type."""
        map_tools = [
            "MapGaussianFilter",
            "MapMedianFilter",
            "MapPlaneLevel",
            "MapRowAlign",
            "MapNormalize",
            "MapPolynomialBGRemoval"
        ]
        for tool_name in map_tools:
            node = create_node_from_tool(tool_name)
            assert node is not None, f"Failed to create {tool_name}"
            # Check input port uses MAP type
            assert len(node.inputs) >= 1
            assert node.inputs[0].port_type == PortType.MAP
            # Check output port uses MAP type
            assert len(node.outputs) >= 1
            assert node.outputs[0].port_type == PortType.MAP

    def test_comment_node_parameters(self):
        """Test CommentNode has updated parameters."""
        assert "CommentNode" in TOOL_DEFINITIONS
        tool_def = TOOL_DEFINITIONS["CommentNode"]
        params = tool_def["parameters"]

        # Check new parameters
        assert "bg_color" in params
        assert params["bg_color"]["default"] == "#F5A9B8"  # Trans pink
        assert "text_color" in params
        assert "opacity" in params
        assert params["opacity"]["default"] == 0.9
        assert "font_size" in params
        assert params["font_size"]["type"] == "int"  # Changed from select
        assert "node_width" in params
        assert "node_height" in params

    def test_comment_node_creation(self):
        """Test creating CommentNode with new parameters."""
        node = create_node_from_tool("CommentNode")
        assert node is not None
        assert node.parameters.get("bg_color") == "#F5A9B8"
        assert node.parameters.get("opacity") == 0.9
        assert node.parameters.get("node_width") == 180
        assert node.parameters.get("node_height") == 100

    def test_image_processing_category_exists(self):
        """Test Image Processing category contains merged tools."""
        categories = get_tool_categories()
        assert "Image Processing" in categories

        image_tools = categories["Image Processing"]
        # Should contain both image tools and map processing tools
        assert "ImageSmoothing" in image_tools
        assert "GradientFilter" in image_tools
        assert "ImageDiscretizer" in image_tools
        assert "MapGaussianFilter" in image_tools
        assert "MapPlaneLevel" in image_tools

    def test_spatial_average_input_queue_default(self):
        """Test SpatialAverage has input_queue default value."""
        assert "SpatialAverage" in TOOL_DEFINITIONS
        params = TOOL_DEFINITIONS["SpatialAverage"]["parameters"]
        assert "input_queue" in params
        assert params["input_queue"]["default"] == []
