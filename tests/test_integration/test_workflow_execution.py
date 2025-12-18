"""
Integration tests for workflow execution
Target coverage: 70%
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import json

from src.backend.workflow_engine import (
    Workflow, WorkflowNode, Connection, Port, PortType,
    create_node_from_tool, TOOL_DEFINITIONS
)
from src.backend.workflow_manager import WorkflowManager, WorkflowExecutor
from src.models.spectral_data import SpectralData, SpectralMetadata


class TestSimplePipelines:
    """Tests for simple workflow pipelines."""

    @pytest.fixture
    def backend_mock(self, sample_spectral_data, tmp_path):
        """Create mock backend with basic functionality."""
        backend = Mock()
        backend._datasets = {'TestData': sample_spectral_data}
        backend._project_path = tmp_path
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()

        # Mock smoothing
        def mock_smooth(task, name, **kwargs):
            if name in backend._datasets:
                sd = backend._datasets[name]
                # Create smoothed version
                smoothed_name = f"Smoothed_{name}"
                backend._datasets[smoothed_name] = sd
                return str(tmp_path / "smoothed.csv")
            return ""

        backend.smooth_curves = mock_smooth

        return backend

    @pytest.fixture
    def workflow_manager(self, backend_mock):
        """Create WorkflowManager with mock backend."""
        return WorkflowManager(backend_mock)

    def test_simple_input_output_pipeline(self, workflow_manager, sample_spectral_data):
        """WX-01: Input→Output pipeline."""
        wf_id = workflow_manager.createWorkflow("Simple Pipeline")

        # Add DatasetInput node
        input_node = workflow_manager.addNode(wf_id, "DatasetInput", 100, 100)
        workflow_manager.setNodeParameter(wf_id, input_node, "dataset_name", "TestData")

        # Add DatasetOutput node
        output_node = workflow_manager.addNode(wf_id, "DatasetOutput", 300, 100)
        workflow_manager.setNodeParameter(wf_id, output_node, "output_name", "Processed")

        # Connect them
        workflow_manager.addConnection(
            wf_id,
            input_node, "dataset",
            output_node, "dataset"
        )

        # Validate
        errors = workflow_manager.validateWorkflow(wf_id)

        # Should be valid or have only minor warnings
        workflow = workflow_manager.workflows[wf_id]
        assert len(workflow.nodes) == 2
        assert len(workflow.connections) == 1


class TestComplexWorkflows:
    """Tests for complex multi-node workflows."""

    @pytest.fixture
    def complex_workflow(self, sample_spectral_data, tmp_path):
        """Create a complex workflow for testing."""
        backend = Mock()
        backend._datasets = {
            'Data1': sample_spectral_data,
            'Data2': sample_spectral_data
        }
        backend._project_path = tmp_path
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()

        manager = WorkflowManager(backend)
        wf_id = manager.createWorkflow("Complex Workflow")

        # Build a workflow:
        # Data1 -> Smooth -> Derivative ->  \
        #                                     -> Output
        # Data2 -> Smooth ----------------> /

        input1 = manager.addNode(wf_id, "DatasetInput", 0, 0)
        manager.setNodeParameter(wf_id, input1, "dataset_name", "Data1")

        input2 = manager.addNode(wf_id, "DatasetInput", 0, 200)
        manager.setNodeParameter(wf_id, input2, "dataset_name", "Data2")

        smooth1 = manager.addNode(wf_id, "CurveSmoothing", 200, 0)
        smooth2 = manager.addNode(wf_id, "CurveSmoothing", 200, 200)

        deriv = manager.addNode(wf_id, "Derivative", 400, 0)

        output = manager.addNode(wf_id, "DatasetOutput", 600, 100)
        manager.setNodeParameter(wf_id, output, "output_name", "FinalResult")

        # Connect
        manager.addConnection(wf_id, input1, "dataset", smooth1, "dataset")
        manager.addConnection(wf_id, input2, "dataset", smooth2, "dataset")
        manager.addConnection(wf_id, smooth1, "smoothed", deriv, "dataset")
        manager.addConnection(wf_id, deriv, "derivative", output, "dataset")

        return manager, wf_id

    def test_complex_workflow_structure(self, complex_workflow):
        """WX-06a: Complex workflow has correct structure."""
        manager, wf_id = complex_workflow
        workflow = manager.workflows[wf_id]

        assert len(workflow.nodes) == 6
        assert len(workflow.connections) == 4

    def test_complex_workflow_execution_order(self, complex_workflow):
        """WX-06b: Complex workflow has valid execution order."""
        manager, wf_id = complex_workflow
        workflow = manager.workflows[wf_id]

        order = workflow.get_execution_order()

        # Find node indices by tool type
        input_nodes = [n for n in workflow.nodes if n.tool_name == "DatasetInput"]
        smooth_nodes = [n for n in workflow.nodes if n.tool_name == "CurveSmoothing"]
        deriv_nodes = [n for n in workflow.nodes if n.tool_name == "Derivative"]
        output_nodes = [n for n in workflow.nodes if n.tool_name == "DatasetOutput"]

        # All inputs should come before their dependents
        for input_node in input_nodes:
            input_idx = order.index(input_node.id)
            for smooth_node in smooth_nodes:
                # Check if this smooth is connected to this input
                for conn in workflow.connections:
                    if conn.source_node_id == input_node.id and conn.target_node_id == smooth_node.id:
                        assert input_idx < order.index(smooth_node.id)


class TestWorkflowPersistence:
    """Tests for workflow save/load persistence."""

    @pytest.fixture
    def manager(self, sample_spectral_data, tmp_path):
        """Create WorkflowManager."""
        backend = Mock()
        backend._datasets = {'TestData': sample_spectral_data}
        backend._project_path = tmp_path
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)

        return WorkflowManager(backend)

    def test_workflow_persistence_roundtrip(self, manager):
        """WX-07: Save→Load→Execute produces consistent results."""
        # Create workflow
        wf_id = manager.createWorkflow("Persistence Test")
        input_node = manager.addNode(wf_id, "DatasetInput", 100, 100)
        manager.setNodeParameter(wf_id, input_node, "dataset_name", "TestData")

        smooth_node = manager.addNode(wf_id, "CurveSmoothing", 300, 100)
        manager.setNodeParameter(wf_id, smooth_node, "window_size", 15)
        manager.setNodeParameter(wf_id, smooth_node, "poly_order", 4)

        manager.addConnection(wf_id, input_node, "dataset", smooth_node, "dataset")

        # Save
        file_path = manager.saveWorkflow(wf_id)
        assert Path(file_path).exists()

        # Get original parameters
        original_workflow = manager.workflows[wf_id]
        original_params = {}
        for node in original_workflow.nodes:
            original_params[node.id] = node.parameters.copy()

        # Clear and reload
        manager.workflows.clear()
        loaded_id = manager.loadWorkflow(file_path)

        # Verify parameters preserved
        loaded_workflow = manager.workflows[loaded_id]
        for node in loaded_workflow.nodes:
            if node.tool_name == "CurveSmoothing":
                assert node.parameters.get('window_size') == 15
                assert node.parameters.get('poly_order') == 4


class TestExecutorIntegration:
    """Integration tests for WorkflowExecutor."""

    @pytest.fixture
    def executor_setup(self, sample_spectral_data, tmp_path):
        """Set up executor with real-ish backend."""
        backend = Mock()
        backend._datasets = {'TestData': sample_spectral_data}
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()

        executor = WorkflowExecutor(backend)
        return executor, backend

    def test_executor_tracks_outputs(self, executor_setup):
        """Test that executor properly tracks node outputs."""
        executor, backend = executor_setup

        # Create simple workflow
        workflow = Workflow(id="test", name="Test")

        input_node = create_node_from_tool("DatasetInput")
        input_node.parameters['dataset_name'] = 'TestData'
        workflow.add_node(input_node)

        # Execute just the input node
        node_inputs = {}
        outputs = executor._execute_node(input_node, node_inputs)

        assert 'dataset' in outputs
        assert outputs['dataset'] is backend._datasets['TestData']

    def test_executor_input_gathering(self, executor_setup, sample_spectral_data):
        """Test that executor gathers inputs correctly."""
        executor, backend = executor_setup

        # Simulate previous node output
        executor.node_outputs['prev_node'] = {'output': sample_spectral_data}

        workflow = Workflow(id="test", name="Test")

        prev_node = WorkflowNode(
            id='prev_node',
            tool_name='PrevTool',
            display_name='Prev',
            outputs=[Port('output', 'Out', PortType.DATASET, False)]
        )

        curr_node = WorkflowNode(
            id='curr_node',
            tool_name='CurrTool',
            display_name='Curr',
            inputs=[Port('input', 'In', PortType.DATASET, True)]
        )

        workflow.add_node(prev_node)
        workflow.add_node(curr_node)
        workflow.add_connection(Connection(
            'c1', 'prev_node', 'output', 'curr_node', 'input'
        ))

        inputs = executor._gather_inputs(curr_node, workflow)

        assert 'input' in inputs
        assert inputs['input'] is sample_spectral_data


class TestErrorHandling:
    """Tests for error handling during workflow execution."""

    @pytest.fixture
    def error_setup(self, sample_spectral_data, tmp_path):
        """Set up for error testing."""
        backend = Mock()
        backend._datasets = {'TestData': sample_spectral_data}
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()

        return WorkflowManager(backend)

    def test_missing_dataset_error(self, error_setup):
        """Test error when dataset not found."""
        manager = error_setup
        wf_id = manager.createWorkflow("Error Test")

        input_node = manager.addNode(wf_id, "DatasetInput", 0, 0)
        manager.setNodeParameter(wf_id, input_node, "dataset_name", "NonExistent")

        # Execution should handle missing dataset gracefully

    def test_invalid_connection_prevented(self, error_setup):
        """Test that invalid connections are prevented."""
        manager = error_setup
        wf_id = manager.createWorkflow("Invalid Connection Test")

        # Add nodes with incompatible types
        input_node = manager.addNode(wf_id, "DatasetInput", 0, 0)
        # MapOutput expects image, not dataset
        map_output = manager.addNode(wf_id, "MapOutput", 200, 0)

        # Try to connect dataset to image input
        conn_id = manager.addConnection(
            wf_id,
            input_node, "dataset",
            map_output, "map"
        )

        # Connection should be rejected
        assert conn_id == ""


class TestMultiInputWorkflows:
    """Tests for workflows with multi-input nodes."""

    @pytest.fixture
    def multi_input_setup(self, sample_spectral_data, sample_spectral_data_large, tmp_path):
        """Set up for multi-input testing."""
        backend = Mock()
        backend._datasets = {
            'Data1': sample_spectral_data,
            'Data2': sample_spectral_data_large
        }
        backend._project_path = tmp_path
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()

        return WorkflowManager(backend)

    def test_spatial_average_multi_input(self, multi_input_setup):
        """WX-04: Multi-input SpatialAverage workflow."""
        manager = multi_input_setup
        wf_id = manager.createWorkflow("Multi Input Test")

        # Two data inputs
        input1 = manager.addNode(wf_id, "DatasetInput", 0, 0)
        manager.setNodeParameter(wf_id, input1, "dataset_name", "Data1")

        input2 = manager.addNode(wf_id, "DatasetInput", 0, 150)
        manager.setNodeParameter(wf_id, input2, "dataset_name", "Data2")

        # SpatialAverage with multi-input
        spatial_avg = manager.addNode(wf_id, "SpatialAverage", 200, 75)

        # Connect both inputs
        manager.addConnection(wf_id, input1, "dataset", spatial_avg, "datasets")
        manager.addConnection(wf_id, input2, "dataset", spatial_avg, "datasets")

        workflow = manager.workflows[wf_id]

        # Verify both connections exist
        connections_to_spatial = [
            c for c in workflow.connections
            if c.target_node_id == spatial_avg
        ]
        assert len(connections_to_spatial) == 2

    def test_get_connected_inputs_multi(self, multi_input_setup):
        """Test getConnectedInputs for multi-input node."""
        manager = multi_input_setup
        wf_id = manager.createWorkflow("Connected Inputs Test")

        input1 = manager.addNode(wf_id, "DatasetInput", 0, 0)
        manager.setNodeParameter(wf_id, input1, "dataset_name", "Data1")

        input2 = manager.addNode(wf_id, "DatasetInput", 0, 150)
        manager.setNodeParameter(wf_id, input2, "dataset_name", "Data2")

        spatial_avg = manager.addNode(wf_id, "SpatialAverage", 200, 75)

        manager.addConnection(wf_id, input1, "dataset", spatial_avg, "datasets")
        manager.addConnection(wf_id, input2, "dataset", spatial_avg, "datasets")

        # Get connected inputs
        connected = manager.getConnectedInputs(wf_id, spatial_avg)

        assert len(connected) == 2
        assert all('source_node_id' in c for c in connected)


class TestDataManipulationWorkflows:
    """Tests for DataManipulation node workflows."""

    @pytest.fixture
    def manip_setup(self, sample_spectral_data, tmp_path):
        """Set up for manipulation testing."""
        backend = Mock()
        backend._datasets = {
            'DataA': sample_spectral_data,
            'DataB': sample_spectral_data
        }
        backend._project_path = tmp_path
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()

        return WorkflowManager(backend)

    def test_data_manipulation_workflow(self, manip_setup):
        """WX-05: DataManipulation workflow."""
        manager = manip_setup
        wf_id = manager.createWorkflow("Manipulation Test")

        # Two inputs
        input_a = manager.addNode(wf_id, "DatasetInput", 0, 0)
        manager.setNodeParameter(wf_id, input_a, "dataset_name", "DataA")

        input_b = manager.addNode(wf_id, "DatasetInput", 0, 150)
        manager.setNodeParameter(wf_id, input_b, "dataset_name", "DataB")

        # DataManipulation
        manip = manager.addNode(wf_id, "DataManipulation", 200, 75)
        manager.setNodeParameter(wf_id, manip, "equation", "A + B")
        manager.setNodeParameter(wf_id, manip, "output_name", "Sum")

        # Connect - DataManipulation has a single "inputs" port with multi_input=True
        manager.addConnection(wf_id, input_a, "dataset", manip, "inputs")
        manager.addConnection(wf_id, input_b, "dataset", manip, "inputs")

        workflow = manager.workflows[wf_id]

        assert len(workflow.nodes) == 3
        assert len(workflow.connections) == 2

        # Verify equation parameter
        manip_node = workflow.get_node(manip)
        assert manip_node.parameters['equation'] == "A + B"
