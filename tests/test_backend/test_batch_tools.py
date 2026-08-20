"""
Tests for running a tool over several datasets in sequence
(src/backend/batch_tools.py).
"""

import pytest

from src.backend import batch_tools
from src.backend.batch_tools import BatchToolSpec, run_dataset_batch


class Task:
    cancelled = False
    progress = 0.0


class FakeBackend:
    """Minimal stand-in exposing the methods the specs name."""

    def __init__(self):
        self.calls = []
        self.fail_on = set()

    def calculate_derivative(self, dataset_name, order=1,
                             smooth_before=True, smooth_after=True):
        self.calls.append((dataset_name, order, smooth_before, smooth_after))
        if dataset_name in self.fail_on:
            raise ValueError(f"boom on {dataset_name}")
        return f"/out/{dataset_name}_deriv.csv"

    def needs_task(self, task, dataset_name, gain=1):
        self.calls.append((task, dataset_name, gain))
        return f"/out/{dataset_name}_task.csv"


class TestRegistry:
    def test_derivative_is_registered(self):
        spec = batch_tools.get_spec('derivative')
        assert spec is not None
        assert spec.method == 'calculate_derivative'

    def test_unknown_tool_raises(self):
        with pytest.raises(ValueError):
            run_dataset_batch(FakeBackend(), Task(), 'nope', ['A'], {})

    def test_qml_floats_are_cast_for_scipy(self):
        """QML numbers arrive as floats; order must reach the tool as an int."""
        spec = batch_tools.get_spec('derivative')
        kwargs = spec.coerce({'order': 2.0, 'smooth_before': False})
        assert kwargs['order'] == 2 and isinstance(kwargs['order'], int)
        assert kwargs['smooth_before'] is False
        # Untouched parameters keep their defaults
        assert kwargs['smooth_after'] is True

    def test_unknown_params_are_dropped(self):
        """UI-only state must not reach the tool as an unexpected keyword."""
        spec = batch_tools.get_spec('derivative')
        assert 'colour' not in spec.coerce({'colour': 'pink', 'order': 1})


class TestSequentialRun:
    def test_runs_every_dataset_in_selection_order(self):
        backend = FakeBackend()
        results = run_dataset_batch(backend, Task(), 'derivative',
                                    ['Third', 'First', 'Second'],
                                    {'order': 1})

        assert [c[0] for c in backend.calls] == ['Third', 'First', 'Second']
        assert [r['dataset'] for r in results] == ['Third', 'First', 'Second']
        assert all(r['output'] for r in results)
        assert all(not r['error'] for r in results)

    def test_outputs_are_one_per_input(self):
        backend = FakeBackend()
        results = run_dataset_batch(backend, Task(), 'derivative', ['A', 'B'], {})
        assert [r['output'] for r in results] == ['/out/A_deriv.csv', '/out/B_deriv.csv']

    def test_one_failing_dataset_does_not_abort_the_batch(self):
        backend = FakeBackend()
        backend.fail_on = {'B'}

        results = run_dataset_batch(backend, Task(), 'derivative', ['A', 'B', 'C'], {})

        assert [r['dataset'] for r in results] == ['A', 'B', 'C']
        assert results[1]['error'] and not results[1]['output']
        assert results[0]['output'] and results[2]['output']

    def test_cancellation_stops_between_datasets(self):
        backend = FakeBackend()
        task = Task()

        def cancel_after_first(entry):
            task.cancelled = True

        results = run_dataset_batch(backend, task, 'derivative',
                                    ['A', 'B', 'C'], {},
                                    on_result=cancel_after_first)

        assert len(results) == 1
        assert [c[0] for c in backend.calls] == ['A']

    def test_empty_selection_is_a_no_op(self):
        backend = FakeBackend()
        assert run_dataset_batch(backend, Task(), 'derivative', [], {}) == []
        assert backend.calls == []

    def test_progress_advances(self):
        task = Task()
        run_dataset_batch(FakeBackend(), task, 'derivative', ['A', 'B'], {})
        assert task.progress == 1.0

    def test_task_is_forwarded_when_the_spec_asks_for_it(self, monkeypatch):
        spec = BatchToolSpec(label="Needs Task", method="needs_task",
                             takes_task=True, params={'gain': int},
                             defaults={'gain': 1})
        monkeypatch.setitem(batch_tools.BATCH_TOOLS, 'needs_task', spec)

        backend = FakeBackend()
        task = Task()
        run_dataset_batch(backend, task, 'needs_task', ['A'], {'gain': 3.0})

        assert backend.calls == [(task, 'A', 3)]


class TestBackendSlot:
    """The QML-facing slot: one worker task, per-dataset output registration."""

    @pytest.fixture
    def backend(self):
        """A stand-in carrying only what the slot touches, so the test needs
        no Qt application."""
        from unittest.mock import Mock

        class Stub:
            pass

        stub = Stub()
        stub.status = ""
        stub.worker_manager = Mock()
        stub.errorOccurred = Mock()
        stub._on_tool_completed = Mock()
        stub._do_run_tool_on_datasets = Mock()
        stub._on_batch_completed = Mock()
        return stub

    def _run(self, backend, tool, names, params=None):
        from src.backend.app_backend import AppBackend
        AppBackend.runToolOnDatasets(backend, tool, names, params or {})

    def test_submits_one_task_with_the_datasets_in_order(self, backend):
        self._run(backend, 'derivative', ['B', 'A'], {'order': 2})

        assert backend.worker_manager.submit.call_count == 1
        kwargs = backend.worker_manager.submit.call_args.kwargs
        assert kwargs['dataset_names'] == ['B', 'A']
        assert kwargs['tool_key'] == 'derivative'
        assert kwargs['params']['order'] == 2

    def test_empty_selection_is_reported_not_submitted(self, backend):
        self._run(backend, 'derivative', [])
        backend.worker_manager.submit.assert_not_called()
        backend.errorOccurred.emit.assert_called_once()

    def test_unknown_tool_is_reported_not_submitted(self, backend):
        self._run(backend, 'not_a_tool', ['A'])
        backend.worker_manager.submit.assert_not_called()
        backend.errorOccurred.emit.assert_called_once()

    def test_every_output_is_registered_when_the_batch_finishes(self, backend):
        from src.backend.app_backend import AppBackend

        AppBackend._on_batch_completed(backend, 'derivative', "Derivative Calculator", [
            {'dataset': 'A', 'output': '/out/a.csv', 'error': ''},
            {'dataset': 'B', 'output': '/out/b.csv', 'error': ''},
        ])

        registered = [c.args for c in backend._on_tool_completed.call_args_list]
        assert registered == [("Derivative Calculator", "/out/a.csv"),
                              ("Derivative Calculator", "/out/b.csv")]
        backend.errorOccurred.emit.assert_not_called()

    def test_failures_are_reported_without_losing_the_successes(self, backend):
        from src.backend.app_backend import AppBackend

        AppBackend._on_batch_completed(backend, 'derivative', "Derivative Calculator", [
            {'dataset': 'A', 'output': '/out/a.csv', 'error': ''},
            {'dataset': 'B', 'output': '', 'error': 'no such column'},
        ])

        assert backend._on_tool_completed.call_count == 1
        backend.errorOccurred.emit.assert_called_once()
        message = backend.errorOccurred.emit.call_args.args[1]
        assert 'B' in message and 'no such column' in message


class TestNoAutoOpenForMultipleInputs:
    """Several inputs means several results — they go to the project browser,
    not onto the screen as a graph or map window per input."""

    @staticmethod
    def _stub():
        from unittest.mock import Mock

        class Stub:
            pass

        stub = Stub()
        stub.status = ""
        stub.errorOccurred = Mock()
        stub._suppress_auto_open = False
        stub.seen = []
        stub._on_tool_completed = Mock(
            side_effect=lambda *_: stub.seen.append(stub._suppress_auto_open))
        return stub

    def _complete(self, stub, n):
        from src.backend.app_backend import AppBackend
        AppBackend._on_batch_completed(stub, 'derivative', "Derivative Calculator", [
            {'dataset': f"D{i}", 'output': f"/out/{i}.csv", 'error': ''}
            for i in range(n)])

    def test_results_are_not_opened_when_several_datasets_ran(self):
        stub = self._stub()
        self._complete(stub, 3)
        assert stub.seen == [True, True, True]

    def test_a_single_dataset_still_opens_its_result(self):
        stub = self._stub()
        self._complete(stub, 1)
        assert stub.seen == [False]

    def test_the_flag_is_cleared_afterwards(self):
        stub = self._stub()
        self._complete(stub, 3)
        assert stub._suppress_auto_open is False

    def test_the_flag_is_cleared_even_if_registering_fails(self):
        stub = self._stub()
        stub._on_tool_completed.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            self._complete(stub, 2)
        assert stub._suppress_auto_open is False

    def test_derived_results_are_not_overlaid_on_a_graph(self):
        from unittest.mock import Mock
        from src.backend.app_backend import AppBackend

        class Stub:
            pass

        stub = Stub()
        stub._workflow_mode = False
        stub._suppress_auto_open = True
        stub._datasets = {'Result': object()}
        stub._seen_dataset_keys = set()
        stub._display_derived_dataset = Mock()

        AppBackend._route_derived_datasets(stub)

        stub._display_derived_dataset.assert_not_called()
        # Still marked as seen, so they don't pop up on the NEXT single run.
        assert stub._seen_dataset_keys == {'Result'}

    def test_map_windows_are_not_opened(self):
        from src.backend.app_backend import AppBackend

        class Stub:
            pass

        stub = Stub()
        stub._suppress_auto_open = True
        stub.open_windows = []
        stub.open_map_windows = []

        # Returns before touching MapVisualizationWindow at all.
        AppBackend._open_map_window(stub, "/out/map.tiff", "map_1", "Map 1")
        assert stub.open_map_windows == []


class TestOnlyTheSummaryMapOpens:
    """A run over many intervals writes dozens of maps. They all reach the
    project browser, but only the joined interval map gets a window — opening
    one per interval locked the workspace up."""

    @staticmethod
    def _stub():
        from unittest.mock import Mock

        class Stub:
            pass

        stub = Stub()
        stub.status = ""
        stub.maps = []
        stub._map_id_counter = 0
        stub._suppress_auto_open = False
        stub.mapCreated = Mock()
        stub.toolCompleted = Mock()
        stub.browserTreeChanged = Mock()
        stub.intervalMapReady = Mock()
        stub.mapIntervalsReady = Mock()
        stub._auto_file = Mock(return_value=False)
        stub.opened = []
        stub._open_map_window = Mock(
            side_effect=lambda path, map_id, title: stub.opened.append(path))
        # The real registration path, so this exercises what actually runs.
        from src.backend.app_backend import AppBackend
        stub._on_maps_completed = (
            lambda paths, open_paths=None:
            AppBackend._on_maps_completed(stub, paths, open_paths=open_paths))
        return stub

    def _complete(self, stub, result):
        from src.backend.app_backend import AppBackend
        AppBackend._on_map_generation_completed(stub, result)

    def test_only_the_joined_map_is_opened(self):
        stub = self._stub()
        self._complete(stub, {
            'map_paths': [f"/out/m{i}.tiff" for i in range(30)],
            'interval_map_path': "/out/joined.tiff",
            'interval_map': "line3 - Interval Map",
            'output_folder': "/out/line3",
        })

        assert stub.opened == ["/out/joined.tiff"]

    def test_every_map_still_reaches_the_browser(self):
        stub = self._stub()
        self._complete(stub, {
            'map_paths': [f"/out/m{i}.tiff" for i in range(30)],
            'interval_map_path': "/out/joined.tiff",
            'interval_map': "line3 - Interval Map",
        })

        assert stub.mapCreated.emit.call_count == 31    # 30 + the joined one
        assert len(stub.maps) == 31

    def test_a_single_map_still_opens(self):
        stub = self._stub()
        self._complete(stub, {'map_paths': ["/out/only.tiff"]})
        assert stub.opened == ["/out/only.tiff"]

    def test_many_maps_without_a_summary_open_nothing(self):
        stub = self._stub()
        self._complete(stub, {'map_paths': ["/out/a.tiff", "/out/b.tiff"]})
        assert stub.opened == []

    def test_the_tool_is_told_which_dataset_to_offer(self):
        stub = self._stub()
        self._complete(stub, {
            'map_paths': ["/out/m0.tiff"],
            'interval_map': "line3 - Interval Map",
            'interval_map_path': "/out/joined.tiff",
        })
        stub.intervalMapReady.emit.assert_called_once_with("line3 - Interval Map")


class TestMapGeneratorBatch:
    """The Map Generator runs over several datasets like any batch tool."""

    def test_it_is_registered(self):
        spec = batch_tools.get_spec('map_generator')
        assert spec is not None
        assert spec.method == 'generate_maps_from_spectra'
        assert spec.takes_task and spec.params_as_dict

    def test_the_whole_parameter_map_is_passed_through(self):
        """Its knobs are a map it coerces itself, not keyword arguments."""
        seen = []

        class Backend:
            def generate_maps_from_spectra(self, task, name, params):
                seen.append((name, params))
                return {'map_paths': [f"/out/{name}.tiff"], 'n_maps': 1}

        params = {'baseline': 'poly-iter', 'temperature_k': 4.5,
                  'intervals': [[0.1, 0.2]], 'scan_type': 'line'}
        results = run_dataset_batch(Backend(), Task(), 'map_generator',
                                    ['A', 'B'], params)

        assert [name for name, _ in seen] == ['A', 'B']
        assert seen[0][1] == params        # untouched, including the lists
        assert results[0]['output']['n_maps'] == 1

    def test_each_dataset_result_goes_to_the_map_completion(self):
        from unittest.mock import Mock
        from src.backend.app_backend import AppBackend

        class Stub:
            pass

        stub = Stub()
        stub.status = ""
        stub.errorOccurred = Mock()
        stub._suppress_auto_open = False
        stub._on_tool_completed = Mock()
        stub._on_map_generation_completed = Mock()

        AppBackend._on_batch_completed(stub, 'map_generator', "Map Generator", [
            {'dataset': 'A', 'output': {'map_paths': ['/out/a.tiff']}, 'error': ''},
            {'dataset': 'B', 'output': {'map_paths': ['/out/b.tiff']}, 'error': ''},
        ])

        assert stub._on_map_generation_completed.call_count == 2
        # The generic path would have handed a dict to a Signal(str).
        stub._on_tool_completed.assert_not_called()

    def test_a_failing_dataset_does_not_stop_the_others(self):
        class Backend:
            def generate_maps_from_spectra(self, task, name, params):
                if name == 'B':
                    raise ValueError("no intervals")
                return {'map_paths': [f"/out/{name}.tiff"]}

        results = run_dataset_batch(Backend(), Task(), 'map_generator',
                                    ['A', 'B', 'C'], {})
        assert [bool(r['error']) for r in results] == [False, True, False]
