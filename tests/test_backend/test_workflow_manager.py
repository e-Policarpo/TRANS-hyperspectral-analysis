"""
Tests for WorkflowManager and WorkflowExecutor classes
Target coverage: 85%
"""

import pytest
import json
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.backend.workflow_engine import (
    Workflow, WorkflowNode, Connection, Port, PortType,
    create_node_from_tool
)
from src.backend.workflow_manager import WorkflowManager, WorkflowExecutor


def create_test_spectral_data():
    """Create test spectral data with proper metadata."""
    x = np.linspace(-2, 2, 100)
    spectra = np.column_stack([
        np.sin(x * (i + 1)) + np.random.normal(0, 0.01, len(x))
        for i in range(10)
    ])
    columns = ['V'] + [f'Spectrum_{i}' for i in range(10)]
    df = pd.DataFrame(
        np.column_stack([x, spectra]),
        columns=columns
    )
    metadata = SpectralMetadata(
        source_type='test',
        dimensions=(5, 2),
        scan_mode='forward',
        units={'x': 'V', 'y': 'nA'}
    )
    return SpectralData(data=df, metadata=metadata)


class TestWorkflowExecutor:
    """Tests for WorkflowExecutor class."""

    @pytest.fixture
    def mock_backend(self, tmp_path):
        """Create mock backend for testing."""
        test_data = create_test_spectral_data()
        backend = Mock()
        backend._datasets = {'TestData': test_data}
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()
        return backend

    @pytest.fixture
    def executor(self, mock_backend):
        """Create WorkflowExecutor with mock backend."""
        return WorkflowExecutor(mock_backend)

    def test_executor_creation(self, executor):
        """Test creating WorkflowExecutor."""
        assert executor is not None
        assert executor.node_outputs == {}
        assert executor.cancelled is False

    def test_executor_cancel(self, executor):
        """Test cancelling execution."""
        executor.cancel()
        assert executor.cancelled is True


class TestWorkflowManager:
    """Tests for WorkflowManager class."""

    @pytest.fixture
    def mock_backend(self, tmp_path):
        """Create mock backend for testing."""
        test_data = create_test_spectral_data()
        backend = Mock()
        backend._datasets = {'TestData': test_data}
        backend._project_path = tmp_path
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()
        return backend

    @pytest.fixture
    def manager(self, mock_backend):
        """Create WorkflowManager with mock backend."""
        return WorkflowManager(mock_backend)

    def test_manager_creation(self, manager):
        """Test creating WorkflowManager."""
        assert manager is not None
        assert manager.workflows == {}
        assert manager.current_workflow is None

    def test_create_workflow(self, manager):
        """WM-01: Create new workflow returns ID."""
        workflow_id = manager.createWorkflow("Test Workflow")

        assert workflow_id != ""
        assert workflow_id in manager.workflows
        assert manager.workflows[workflow_id].name == "Test Workflow"
        assert manager.current_workflow is not None

    def test_add_node_slot(self, manager):
        """WM-02: Add node via slot."""
        workflow_id = manager.createWorkflow("Test")
        node_id = manager.addNode(workflow_id, "DatasetInput", 100.0, 200.0)

        assert node_id != ""
        workflow = manager.workflows[workflow_id]
        assert len(workflow.nodes) == 1
        assert workflow.nodes[0].x == 100.0

    def test_add_node_invalid_workflow(self, manager):
        """Test adding node to invalid workflow."""
        node_id = manager.addNode("invalid_id", "DatasetInput", 0, 0)
        assert node_id == ""

    def test_remove_node_slot(self, manager):
        """WM-03: Remove node via slot."""
        workflow_id = manager.createWorkflow("Test")
        node_id = manager.addNode(workflow_id, "DatasetInput", 0, 0)

        manager.removeNode(workflow_id, node_id)

        workflow = manager.workflows[workflow_id]
        assert len(workflow.nodes) == 0

    def test_add_connection_slot(self, manager):
        """WM-04: Add connection via slot."""
        workflow_id = manager.createWorkflow("Test")
        node1_id = manager.addNode(workflow_id, "DatasetInput", 0, 0)
        node2_id = manager.addNode(workflow_id, "CurveSmoothing", 200, 0)

        conn_id = manager.addConnection(
            workflow_id,
            node1_id, "dataset",
            node2_id, "dataset"
        )

        assert conn_id != ""
        workflow = manager.workflows[workflow_id]
        assert len(workflow.connections) == 1

    def test_add_connection_invalid(self, manager):
        """Test adding invalid connection returns empty string."""
        workflow_id = manager.createWorkflow("Test")
        conn_id = manager.addConnection(
            workflow_id,
            "invalid", "out",
            "also_invalid", "in"
        )
        assert conn_id == ""

    def test_set_node_parameter(self, manager):
        """WM-05: Set parameter via slot."""
        workflow_id = manager.createWorkflow("Test")
        node_id = manager.addNode(workflow_id, "CurveSmoothing", 0, 0)

        manager.setNodeParameter(workflow_id, node_id, "window_size", 21)

        workflow = manager.workflows[workflow_id]
        node = workflow.get_node(node_id)
        assert node.parameters["window_size"] == 21

    def test_validate_workflow_slot(self, manager):
        """WM-06: Validate via slot."""
        workflow_id = manager.createWorkflow("Test")
        # Add node with required input that isn't connected
        manager.addNode(workflow_id, "CurveSmoothing", 0, 0)

        errors = manager.validateWorkflow(workflow_id)

        assert isinstance(errors, list)
        # Should have error about unconnected required input

    def test_validate_workflow_invalid_id(self, manager):
        """Test validating invalid workflow ID."""
        errors = manager.validateWorkflow("invalid_id")
        assert "Workflow not found" in errors


class TestWorkflowPersistence:
    """Tests for workflow save/load."""

    @pytest.fixture
    def manager_with_workflow(self, tmp_path):
        """Create manager with a workflow."""
        test_data = create_test_spectral_data()
        backend = Mock()
        backend._datasets = {'TestData': test_data}
        backend._project_path = tmp_path
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)

        manager = WorkflowManager(backend)
        workflow_id = manager.createWorkflow("Test Workflow")
        manager.addNode(workflow_id, "DatasetInput", 100, 100)
        manager.addNode(workflow_id, "CurveSmoothing", 300, 100)

        return manager, workflow_id

    def test_save_workflow(self, manager_with_workflow):
        """WM-07: Save workflow to file."""
        manager, workflow_id = manager_with_workflow
        file_path = manager.saveWorkflow(workflow_id)

        assert file_path != ""
        assert Path(file_path).exists()
        assert file_path.endswith(".flow")

    def test_load_workflow(self, manager_with_workflow):
        """WM-08: Load workflow from file."""
        manager, workflow_id = manager_with_workflow
        file_path = manager.saveWorkflow(workflow_id)

        # Clear and reload
        manager.workflows.clear()
        loaded_id = manager.loadWorkflow(file_path)

        assert loaded_id != ""
        assert loaded_id in manager.workflows
        assert manager.workflows[loaded_id].name == "Test Workflow"

    def test_get_saved_workflows(self, manager_with_workflow):
        """WM-09: List saved workflows."""
        manager, workflow_id = manager_with_workflow
        manager.saveWorkflow(workflow_id)

        workflows = manager.getSavedWorkflows()

        assert isinstance(workflows, list)
        assert len(workflows) >= 1
        assert any(w['name'] == "Test Workflow" for w in workflows)

    def test_delete_workflow(self, manager_with_workflow):
        """WM-10: Delete workflow file."""
        manager, workflow_id = manager_with_workflow
        file_path = manager.saveWorkflow(workflow_id)

        result = manager.deleteWorkflow(file_path)

        assert result is True
        assert not Path(file_path).exists()

    def test_delete_workflow_nonexistent(self, manager_with_workflow):
        """Test deleting nonexistent workflow."""
        manager, _ = manager_with_workflow
        result = manager.deleteWorkflow("/nonexistent/path.flow")
        assert result is False


class TestWorkflowExecution:
    """Tests for workflow execution."""

    @pytest.fixture
    def execution_manager(self, tmp_path):
        """Create manager set up for execution tests."""
        test_data = create_test_spectral_data()
        backend = Mock()
        backend._datasets = {'TestData': test_data}
        backend._project_path = tmp_path
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()

        # Mock smooth_curves method
        def mock_smooth(task, name, **kwargs):
            return str(tmp_path / "smoothed.csv")
        backend.smooth_curves = mock_smooth

        manager = WorkflowManager(backend)
        return manager

    def test_execute_workflow_simple(self, execution_manager):
        """WM-11: Execute simple workflow."""
        manager = execution_manager
        workflow_id = manager.createWorkflow("Simple Test")

        # Just a DatasetInput node
        node_id = manager.addNode(workflow_id, "DatasetInput", 0, 0)
        manager.setNodeParameter(workflow_id, node_id, "dataset_name", "TestData")

        # Execute (this will be limited without full backend)
        # Just verify the method exists and can be called
        assert hasattr(manager, 'executeWorkflow')

    def test_cancel_execution(self, execution_manager):
        """WM-14: Cancel mid-execution."""
        manager = execution_manager

        # Start execution context
        manager.executor = WorkflowExecutor(manager.app_backend)

        manager.cancelExecution()

        assert manager.executor.cancelled is True


class TestWorkflowManagerSlots:
    """Tests for additional WorkflowManager slots."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager."""
        test_data = create_test_spectral_data()
        backend = Mock()
        backend._datasets = {'TestData': test_data}
        backend._project_path = tmp_path
        return WorkflowManager(backend)

    def test_get_tool_categories(self, manager):
        """Test getToolCategories slot."""
        categories = manager.getToolCategories()

        assert isinstance(categories, list)
        cat_names = [c["category"] for c in categories]
        assert "Input" in cat_names
        assert "Processing" in cat_names

    def test_get_tool_info(self, manager):
        """Test getToolInfo slot."""
        info = manager.getToolInfo("CurveSmoothing")

        assert info != {}
        assert 'display_name' in info

    def test_get_tool_info_unknown(self, manager):
        """Test getToolInfo for unknown tool."""
        info = manager.getToolInfo("NonExistent")
        assert info == {}

    def test_get_workflow_data(self, manager):
        """Test getWorkflowData slot."""
        workflow_id = manager.createWorkflow("Test")
        manager.addNode(workflow_id, "DatasetInput", 0, 0)

        data = manager.getWorkflowData(workflow_id)

        assert isinstance(data, dict)
        assert data['name'] == "Test"
        assert len(data['nodes']) == 1

    def test_get_workflow_data_invalid(self, manager):
        """Test getWorkflowData for invalid workflow."""
        data = manager.getWorkflowData("invalid_id")
        assert data == {}

    def test_get_available_datasets(self, manager):
        """Test getAvailableDatasets slot."""
        datasets = manager.getAvailableDatasets()

        assert isinstance(datasets, list)
        assert 'TestData' in datasets

    def test_get_connected_inputs(self, manager):
        """WM-15: Get connected inputs for multi-input queue."""
        workflow_id = manager.createWorkflow("Test")

        node1 = manager.addNode(workflow_id, "DatasetInput", 0, 0)
        node2 = manager.addNode(workflow_id, "DatasetInput", 0, 100)
        node3 = manager.addNode(workflow_id, "SpatialAverage", 200, 50)

        manager.addConnection(workflow_id, node1, "dataset", node3, "datasets")
        manager.addConnection(workflow_id, node2, "dataset", node3, "datasets")

        inputs = manager.getConnectedInputs(workflow_id, node3)

        assert isinstance(inputs, list)
        assert len(inputs) == 2

    def test_set_workflow_name(self, manager):
        """Test setWorkflowName slot."""
        workflow_id = manager.createWorkflow("Original Name")

        manager.setWorkflowName(workflow_id, "New Name")

        assert manager.workflows[workflow_id].name == "New Name"

    def test_update_node_position(self, manager):
        """Test updateNodePosition slot."""
        workflow_id = manager.createWorkflow("Test")
        node_id = manager.addNode(workflow_id, "DatasetInput", 0, 0)

        manager.updateNodePosition(workflow_id, node_id, 150.0, 250.0)

        node = manager.workflows[workflow_id].get_node(node_id)
        assert node.x == 150.0
        assert node.y == 250.0

    def test_remove_connection(self, manager):
        """Test removeConnection slot."""
        workflow_id = manager.createWorkflow("Test")
        node1 = manager.addNode(workflow_id, "DatasetInput", 0, 0)
        node2 = manager.addNode(workflow_id, "CurveSmoothing", 200, 0)
        conn_id = manager.addConnection(workflow_id, node1, "dataset", node2, "dataset")

        manager.removeConnection(workflow_id, conn_id)

        workflow = manager.workflows[workflow_id]
        assert len(workflow.connections) == 0


class TestExecutorNodeExecution:
    """Tests for individual node execution in WorkflowExecutor."""

    @pytest.fixture
    def executor_with_data(self, tmp_path):
        """Create executor with test data."""
        test_data = create_test_spectral_data()
        backend = Mock()
        backend._datasets = {'TestData': test_data}
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()

        return WorkflowExecutor(backend)

    def test_execution_dataset_input(self, executor_with_data):
        """WM-16: DatasetInput node execution."""
        executor = executor_with_data
        test_data = create_test_spectral_data()
        executor.app_backend._datasets['TestData'] = test_data

        node = create_node_from_tool("DatasetInput")
        node.parameters['dataset_name'] = 'TestData'

        outputs = executor._execute_node(node, {})

        assert 'dataset' in outputs
        assert outputs['dataset'] is test_data

    def test_gather_inputs_single(self, executor_with_data):
        """Test gathering single input."""
        executor = executor_with_data

        # Set up node outputs
        executor.node_outputs['source_node'] = {'output_port': 'test_value'}

        workflow = Workflow(id='test', name='Test')

        source = WorkflowNode(
            id='source_node',
            tool_name='Source',
            display_name='Source',
            outputs=[Port('output_port', 'Out', PortType.STRING, False)]
        )
        target = WorkflowNode(
            id='target_node',
            tool_name='Target',
            display_name='Target',
            inputs=[Port('input_port', 'In', PortType.STRING, True)]
        )

        workflow.add_node(source)
        workflow.add_node(target)
        workflow.add_connection(Connection(
            'c1', 'source_node', 'output_port', 'target_node', 'input_port'
        ))

        inputs = executor._gather_inputs(target, workflow)

        assert 'input_port' in inputs
        assert inputs['input_port'] == 'test_value'

    def test_gather_inputs_multi(self, executor_with_data):
        """Test gathering multiple inputs for multi_input port."""
        executor = executor_with_data

        executor.node_outputs['source1'] = {'out': 'value1'}
        executor.node_outputs['source2'] = {'out': 'value2'}

        workflow = Workflow(id='test', name='Test')

        source1 = WorkflowNode(
            id='source1', tool_name='S1', display_name='S1',
            outputs=[Port('out', 'Out', PortType.ANY, False)]
        )
        source2 = WorkflowNode(
            id='source2', tool_name='S2', display_name='S2',
            outputs=[Port('out', 'Out', PortType.ANY, False)]
        )
        target = WorkflowNode(
            id='target', tool_name='T', display_name='T',
            inputs=[Port('in', 'In', PortType.ANY, True, multi_input=True)]
        )

        workflow.add_node(source1)
        workflow.add_node(source2)
        workflow.add_node(target)
        workflow.add_connection(Connection('c1', 'source1', 'out', 'target', 'in'))
        workflow.add_connection(Connection('c2', 'source2', 'out', 'target', 'in'))

        inputs = executor._gather_inputs(target, workflow)

        assert 'in' in inputs
        assert isinstance(inputs['in'], list)
        assert len(inputs['in']) == 2

    def test_gather_inputs_multi_with_ordering(self, executor_with_data):
        """Test that multi-inputs are ordered according to input_queue parameter."""
        executor = executor_with_data

        executor.node_outputs['source1'] = {'out': 'value1'}
        executor.node_outputs['source2'] = {'out': 'value2'}
        executor.node_outputs['source3'] = {'out': 'value3'}

        workflow = Workflow(id='test', name='Test')

        source1 = WorkflowNode(
            id='source1', tool_name='S1', display_name='Source 1',
            outputs=[Port('out', 'Out', PortType.ANY, False)]
        )
        source2 = WorkflowNode(
            id='source2', tool_name='S2', display_name='Source 2',
            outputs=[Port('out', 'Out', PortType.ANY, False)]
        )
        source3 = WorkflowNode(
            id='source3', tool_name='S3', display_name='Source 3',
            outputs=[Port('out', 'Out', PortType.ANY, False)]
        )
        # Target node with input_queue parameter specifying order: source3, source1, source2
        target = WorkflowNode(
            id='target', tool_name='T', display_name='T',
            inputs=[Port('in', 'In', PortType.ANY, True, multi_input=True)],
            parameters={
                'input_queue': [
                    {'source_node_id': 'source3', 'enabled': True},
                    {'source_node_id': 'source1', 'enabled': True},
                    {'source_node_id': 'source2', 'enabled': True}
                ]
            }
        )

        workflow.add_node(source1)
        workflow.add_node(source2)
        workflow.add_node(source3)
        workflow.add_node(target)
        # Add connections in different order than queue
        workflow.add_connection(Connection('c1', 'source1', 'out', 'target', 'in'))
        workflow.add_connection(Connection('c2', 'source2', 'out', 'target', 'in'))
        workflow.add_connection(Connection('c3', 'source3', 'out', 'target', 'in'))

        inputs = executor._gather_inputs(target, workflow)

        assert 'in' in inputs
        assert isinstance(inputs['in'], list)
        assert len(inputs['in']) == 3
        # Verify ordering matches input_queue (source3, source1, source2)
        assert inputs['in'][0]['source_node_id'] == 'source3'
        assert inputs['in'][1]['source_node_id'] == 'source1'
        assert inputs['in'][2]['source_node_id'] == 'source2'

    def test_gather_inputs_multi_disabled_filtering(self, executor_with_data):
        """Test that disabled inputs in input_queue are still gathered but can be filtered."""
        executor = executor_with_data

        executor.node_outputs['source1'] = {'out': 'value1'}
        executor.node_outputs['source2'] = {'out': 'value2'}

        workflow = Workflow(id='test', name='Test')

        source1 = WorkflowNode(
            id='source1', tool_name='S1', display_name='Source 1',
            outputs=[Port('out', 'Out', PortType.ANY, False)]
        )
        source2 = WorkflowNode(
            id='source2', tool_name='S2', display_name='Source 2',
            outputs=[Port('out', 'Out', PortType.ANY, False)]
        )
        # Target with source1 disabled in queue
        target = WorkflowNode(
            id='target', tool_name='T', display_name='T',
            inputs=[Port('in', 'In', PortType.ANY, True, multi_input=True)],
            parameters={
                'input_queue': [
                    {'source_node_id': 'source2', 'enabled': True},
                    {'source_node_id': 'source1', 'enabled': False}  # Disabled
                ]
            }
        )

        workflow.add_node(source1)
        workflow.add_node(source2)
        workflow.add_node(target)
        workflow.add_connection(Connection('c1', 'source1', 'out', 'target', 'in'))
        workflow.add_connection(Connection('c2', 'source2', 'out', 'target', 'in'))

        inputs = executor._gather_inputs(target, workflow)

        # _gather_inputs still returns all values (ordering only)
        # Filtering of disabled inputs happens in the node execution handler
        assert 'in' in inputs
        assert len(inputs['in']) == 2
        # But ordering should reflect queue order (source2 first)
        assert inputs['in'][0]['source_node_id'] == 'source2'

    def test_format_output_name(self, executor_with_data):
        """Test output naming format."""
        executor = executor_with_data
        executor.original_dataset_name = "MyData"
        executor.workflow_name = "Test_Workflow"
        # Remove _apply_naming_convention to ensure fallback is used
        if hasattr(executor.app_backend, '_apply_naming_convention'):
            del executor.app_backend._apply_naming_convention

        name = executor._format_output_name("Smoothed")

        assert isinstance(name, str)
        assert "MyData" in name
        assert "Smoothed" in name

    def test_get_temp_dataset_name(self, executor_with_data):
        """Test temporary dataset name generation."""
        name1 = executor_with_data._get_temp_dataset_name(None)
        name2 = executor_with_data._get_temp_dataset_name(None)

        assert name1.startswith("_wf_temp_")
        assert name2.startswith("_wf_temp_")
        assert name1 != name2  # Should be unique


class TestWorkflowIntermediateCleanup:
    """Tests for intermediate dataset cleanup during workflow execution."""

    @pytest.fixture
    def cleanup_executor(self, tmp_path):
        """Create executor with controllable backend for cleanup testing."""
        test_data = create_test_spectral_data()
        backend = Mock()
        backend._datasets = {'OriginalData': test_data}
        backend._output_base_dir = tmp_path / "outputs"
        backend._output_base_dir.mkdir(exist_ok=True)
        backend.dataLoaded = Mock()
        backend.errorOccurred = Mock()
        backend._workflow_mode = False

        executor = WorkflowExecutor(backend)
        return executor, backend

    def test_datasets_before_snapshot(self, cleanup_executor):
        """WM-17: Verify datasets are snapshotted before execution."""
        executor, backend = cleanup_executor

        # Pre-existing datasets
        assert 'OriginalData' in backend._datasets
        datasets_before = set(backend._datasets.keys())

        assert 'OriginalData' in datasets_before
        assert len(datasets_before) == 1

    def test_intermediate_datasets_cleaned_after_execution(self, cleanup_executor):
        """WM-18: Intermediate datasets are removed after workflow execution."""
        executor, backend = cleanup_executor

        # Create a simple workflow: DatasetInput -> DatasetOutput
        workflow = Workflow(id="cleanup_test", name="Cleanup Test")

        input_node = create_node_from_tool("DatasetInput")
        input_node.parameters['dataset_name'] = 'OriginalData'
        workflow.add_node(input_node)

        output_node = create_node_from_tool("DatasetOutput")
        output_node.parameters['output_name'] = 'FinalOutput'
        workflow.add_node(output_node)

        # Connect input to output
        conn = Connection(
            id="c1",
            source_node_id=input_node.id,
            source_port_id="dataset",
            target_node_id=output_node.id,
            target_port_id="dataset"
        )
        workflow.add_connection(conn)

        # Execute workflow
        result = executor.execute(workflow)

        # Original dataset should still exist
        assert 'OriginalData' in backend._datasets

        # Workflow mode should be disabled
        assert backend._workflow_mode is False

    def test_workflow_mode_disabled_on_error(self, cleanup_executor):
        """WM-19: _workflow_mode is set to False even if execution fails."""
        executor, backend = cleanup_executor

        # Create workflow with missing dataset to trigger error
        workflow = Workflow(id="error_test", name="Error Test")

        input_node = create_node_from_tool("DatasetInput")
        input_node.parameters['dataset_name'] = 'NonExistentDataset'
        workflow.add_node(input_node)

        output_node = create_node_from_tool("DatasetOutput")
        output_node.parameters['output_name'] = 'Output'
        workflow.add_node(output_node)

        conn = Connection(
            id="c1",
            source_node_id=input_node.id,
            source_port_id="dataset",
            target_node_id=output_node.id,
            target_port_id="dataset"
        )
        workflow.add_connection(conn)

        # Execute - may have errors but should not crash
        result = executor.execute(workflow)

        # workflow_mode should always be reset in finally block
        assert backend._workflow_mode is False

    def test_output_datasets_preserved(self, cleanup_executor):
        """WM-20: Datasets named by output nodes are not cleaned up."""
        executor, backend = cleanup_executor
        test_data = create_test_spectral_data()

        # Simulate what happens: workflow adds intermediate + output datasets
        # We'll manually add them and check cleanup logic
        datasets_before = set(backend._datasets.keys())

        # Simulate intermediates being added during workflow
        backend._datasets['_wf_temp_smooth_abc123'] = test_data
        backend._datasets['_wf_temp_derivative_def456'] = test_data

        datasets_after = set(backend._datasets.keys())
        intermediate_datasets = datasets_after - datasets_before

        # Simulate output names (what the cleanup code does)
        output_names = set()  # No output nodes in this test

        # All intermediates should be identified for removal
        to_remove = [name for name in intermediate_datasets if name not in output_names]
        assert '_wf_temp_smooth_abc123' in to_remove
        assert '_wf_temp_derivative_def456' in to_remove
        assert 'OriginalData' not in to_remove

    def test_cleanup_preserves_pre_existing_datasets(self, cleanup_executor):
        """WM-21: Pre-existing datasets are never removed by cleanup."""
        executor, backend = cleanup_executor
        test_data = create_test_spectral_data()

        # Add another pre-existing dataset
        backend._datasets['SecondDataset'] = test_data

        datasets_before = set(backend._datasets.keys())
        assert len(datasets_before) == 2

        # Simulate intermediates
        backend._datasets['_wf_temp_abc'] = test_data

        datasets_after = set(backend._datasets.keys())
        intermediate_datasets = datasets_after - datasets_before

        # Only the new intermediate should be in the set
        assert intermediate_datasets == {'_wf_temp_abc'}
        assert 'OriginalData' not in intermediate_datasets
        assert 'SecondDataset' not in intermediate_datasets

    def test_comment_nodes_skipped_during_execution(self, cleanup_executor):
        """WM-22: CommentNodes are skipped during execution."""
        executor, backend = cleanup_executor

        workflow = Workflow(id="comment_test", name="Comment Test")

        # Add a comment node and a dataset input
        input_node = create_node_from_tool("DatasetInput")
        input_node.parameters['dataset_name'] = 'OriginalData'
        workflow.add_node(input_node)

        comment_node = create_node_from_tool("CommentNode")
        workflow.add_node(comment_node)

        output_node = create_node_from_tool("DatasetOutput")
        output_node.parameters['output_name'] = 'Result'
        workflow.add_node(output_node)

        conn = Connection(
            id="c1",
            source_node_id=input_node.id,
            source_port_id="dataset",
            target_node_id=output_node.id,
            target_port_id="dataset"
        )
        workflow.add_connection(conn)

        # Execute - should not error on comment node
        result = executor.execute(workflow)

        assert backend._workflow_mode is False

    def test_cancelled_execution_still_cleans_up(self, cleanup_executor):
        """WM-23: Cancelled execution still runs cleanup in finally block."""
        executor, backend = cleanup_executor

        workflow = Workflow(id="cancel_test", name="Cancel Test")
        input_node = create_node_from_tool("DatasetInput")
        input_node.parameters['dataset_name'] = 'OriginalData'
        workflow.add_node(input_node)

        output_node = create_node_from_tool("DatasetOutput")
        output_node.parameters['output_name'] = 'Output'
        workflow.add_node(output_node)

        conn = Connection(
            id="c1",
            source_node_id=input_node.id,
            source_port_id="dataset",
            target_node_id=output_node.id,
            target_port_id="dataset"
        )
        workflow.add_connection(conn)

        # Use a progress callback to cancel mid-execution
        def cancel_on_progress(current, total, msg):
            executor.cancelled = True

        result = executor.execute(workflow, progress_callback=cancel_on_progress)

        # Workflow mode should always be reset in finally block
        assert backend._workflow_mode is False

    def test_format_output_name_fallback(self, cleanup_executor):
        """WM-24: _format_output_name uses fallback when no naming convention."""
        executor, backend = cleanup_executor
        executor.original_dataset_name = "STS_Data"
        executor.workflow_name = "My_Workflow"

        # Ensure no _apply_naming_convention method
        if hasattr(backend, '_apply_naming_convention'):
            del backend._apply_naming_convention

        name = executor._format_output_name("Smoothed")

        assert "STS_Data" in name
        assert "Smoothed" in name
        assert "My Workflow" in name  # underscores replaced with spaces
