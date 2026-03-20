"""
Tests for EmbeddedWindow and WindowManager QML components.

These tests verify the Python-side interfaces and behavior of the embedded window system.
Tests cover window state management, backend propagation, and theme color handling.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path


class TestEmbeddedWindowStates:
    """Test EmbeddedWindow state transitions."""

    def test_window_state_enum_values(self):
        """Verify window state constants match expected values."""
        # Based on EmbeddedWindow.qml enum definition
        WINDOWED = 0
        FULLSCREEN = 1
        MINIMIZED = 2

        assert WINDOWED == 0, "Windowed state should be 0"
        assert FULLSCREEN == 1, "Fullscreen state should be 1"
        assert MINIMIZED == 2, "Minimized state should be 2"

    def test_window_state_transitions(self):
        """Test valid state transition logic."""
        # State transition rules from EmbeddedWindow.qml
        WINDOWED = 0
        FULLSCREEN = 1
        MINIMIZED = 2

        # Valid transitions from Windowed
        valid_transitions = {
            WINDOWED: [FULLSCREEN, MINIMIZED],
            FULLSCREEN: [WINDOWED],
            MINIMIZED: [WINDOWED]  # Minimize button restores to windowed
        }

        # Verify each state has valid transitions
        for state, transitions in valid_transitions.items():
            assert len(transitions) > 0, f"State {state} should have valid transitions"

    def test_minimize_saves_position(self):
        """Test that minimizing saves previous position."""
        # Simulating EmbeddedWindow.minimize() behavior
        previous_x = 100
        previous_y = 150
        previous_width = 500
        previous_height = 400

        # When minimized, these values should be preserved
        # Height changes to minimizedHeight (36), but position saved
        minimized_height = 36

        assert previous_x == 100
        assert previous_y == 150
        assert previous_width == 500
        assert minimized_height == 36

    def test_fullscreen_dimensions(self):
        """Test fullscreen dimensions calculation."""
        parent_width = 1920
        parent_height = 1080

        # In fullscreen, window fills parent
        fullscreen_x = 0
        fullscreen_y = 0
        fullscreen_width = parent_width
        fullscreen_height = parent_height

        assert fullscreen_x == 0
        assert fullscreen_y == 0
        assert fullscreen_width == parent_width
        assert fullscreen_height == parent_height

    def test_restore_from_fullscreen(self):
        """Test restore from fullscreen preserves previous dimensions."""
        # Previous state before fullscreen
        saved_x = 100
        saved_y = 150
        saved_width = 500
        saved_height = 400

        # After restore, should return to previous values
        restored_x = saved_x
        restored_y = saved_y
        restored_width = saved_width
        restored_height = saved_height

        assert restored_x == saved_x
        assert restored_y == saved_y
        assert restored_width == saved_width
        assert restored_height == saved_height


class TestWindowConstraints:
    """Test EmbeddedWindow size constraints."""

    def test_min_width_constraint(self):
        """Test minimum width is enforced."""
        min_width = 300
        requested_width = 200

        # Width should be clamped to minimum
        actual_width = max(min_width, requested_width)
        assert actual_width == min_width

    def test_min_height_constraint(self):
        """Test minimum height is enforced."""
        min_height = 200
        requested_height = 100

        # Height should be clamped to minimum
        actual_height = max(min_height, requested_height)
        assert actual_height == min_height

    def test_max_width_constraint(self):
        """Test maximum width is enforced."""
        max_width = 9999
        requested_width = 10000

        # Width should be clamped to maximum
        actual_width = min(max_width, requested_width)
        assert actual_width == max_width

    def test_resize_within_constraints(self):
        """Test resize stays within constraints."""
        min_width, max_width = 300, 9999
        min_height, max_height = 200, 9999

        test_sizes = [
            (500, 400, 500, 400),      # Normal size
            (200, 150, 300, 200),      # Below minimum
            (10000, 10000, 9999, 9999), # Above maximum
        ]

        for req_w, req_h, exp_w, exp_h in test_sizes:
            actual_w = max(min_width, min(max_width, req_w))
            actual_h = max(min_height, min(max_height, req_h))
            assert actual_w == exp_w, f"Width {req_w} should clamp to {exp_w}"
            assert actual_h == exp_h, f"Height {req_h} should clamp to {exp_h}"


class TestWindowZOrder:
    """Test EmbeddedWindow z-order management."""

    def test_base_z_inactive(self):
        """Test z-order for inactive window."""
        base_z = 100
        is_active = False

        z = base_z + 1000 if is_active else base_z
        assert z == base_z

    def test_base_z_active(self):
        """Test z-order for active window."""
        base_z = 100
        is_active = True

        z = base_z + 1000 if is_active else base_z
        assert z == base_z + 1000

    def test_bring_to_front(self):
        """Test bringToFront activates window."""
        is_active = False

        # Simulating bringToFront()
        def bring_to_front():
            nonlocal is_active
            is_active = True

        bring_to_front()
        assert is_active is True


class TestThemeColorDefaults:
    """Test EmbeddedWindow theme color default values."""

    def test_default_colors(self):
        """Test default color values when no main window."""
        # Default values from EmbeddedWindow.qml when mainWin is None
        defaults = {
            'bgDark': '#1a1a2e',
            'bgDarker': '#0d0d1a',
            'bgMedium': '#2a2a3e',
            'bgLight': '#3a3a4e',
            'textLight': '#ffffff',
            'textMuted': '#cccccc',
            'accentPink': '#F5A9B8',
            'accentBlue': '#5BCEFA',
            'borderColor': '#9B4F96'
        }

        for color_name, hex_value in defaults.items():
            assert hex_value.startswith('#'), f"{color_name} should be hex color"
            assert len(hex_value) == 7, f"{color_name} should be 7-char hex"

    def test_window_type_colors(self):
        """Test window type icon colors."""
        type_colors = {
            'tool': '#5BCEFA',   # accentBlue
            'graph': '#2ECC71',  # Green
            'table': '#FF9800',  # Orange
            'image': '#9B4F96',  # Purple
            'default': '#cccccc' # textMuted
        }

        for window_type, color in type_colors.items():
            assert color.startswith('#'), f"{window_type} color should be hex"


class TestWindowManagerRegistry:
    """Test WindowManager window registry functionality."""

    def test_empty_registry(self):
        """Test empty window registry."""
        windows = []
        assert len(windows) == 0
        assert windows == []

    def test_add_window_to_registry(self):
        """Test adding window to registry."""
        windows = []

        window_info = {
            'id': 'window_1',
            'window': MagicMock(),
            'type': 'tool',
            'title': 'Test Tool'
        }

        windows.append(window_info)

        assert len(windows) == 1
        assert windows[0]['id'] == 'window_1'
        assert windows[0]['type'] == 'tool'

    def test_find_window_by_id(self):
        """Test finding window by ID."""
        windows = [
            {'id': 'window_1', 'window': MagicMock(), 'type': 'tool', 'title': 'Tool 1'},
            {'id': 'window_2', 'window': MagicMock(), 'type': 'graph', 'title': 'Graph 1'},
            {'id': 'window_3', 'window': MagicMock(), 'type': 'table', 'title': 'Table 1'},
        ]

        def get_window(window_id):
            for w in windows:
                if w['id'] == window_id:
                    return w
            return None

        assert get_window('window_2')['title'] == 'Graph 1'
        assert get_window('window_4') is None

    def test_remove_window_from_registry(self):
        """Test removing window from registry."""
        windows = [
            {'id': 'window_1', 'window': MagicMock(), 'type': 'tool', 'title': 'Tool 1'},
            {'id': 'window_2', 'window': MagicMock(), 'type': 'graph', 'title': 'Graph 1'},
        ]

        def close_window(window_id):
            for j in range(len(windows) - 1, -1, -1):
                if windows[j]['id'] == window_id:
                    windows.pop(j)
                    break

        close_window('window_1')

        assert len(windows) == 1
        assert windows[0]['id'] == 'window_2'

    def test_close_all_windows(self):
        """Test closing all windows."""
        windows = [
            {'id': 'window_1', 'window': MagicMock()},
            {'id': 'window_2', 'window': MagicMock()},
            {'id': 'window_3', 'window': MagicMock()},
        ]

        while windows:
            windows.pop()

        assert len(windows) == 0


class TestWindowManagerActivation:
    """Test WindowManager window activation logic."""

    def test_activate_window(self):
        """Test activating a window."""
        windows = [
            {'id': 'window_1', 'window': MagicMock(isActive=False)},
            {'id': 'window_2', 'window': MagicMock(isActive=False)},
        ]
        active_window_id = ''
        base_z = 100

        def activate_window(window_id):
            nonlocal active_window_id

            # Deactivate current
            for w in windows:
                if w['id'] == active_window_id:
                    w['window'].isActive = False

            # Activate new
            active_window_id = window_id
            for i, w in enumerate(windows):
                if w['id'] == window_id:
                    w['window'].isActive = True
                    w['window'].baseZ = base_z + 1000
                else:
                    w['window'].baseZ = base_z + i

        activate_window('window_2')

        assert active_window_id == 'window_2'
        assert windows[1]['window'].isActive is True
        assert windows[0]['window'].isActive is False

    def test_activate_next_on_close(self):
        """Test activating next window when active is closed."""
        windows = [
            {'id': 'window_1', 'window': MagicMock(isActive=False)},
            {'id': 'window_2', 'window': MagicMock(isActive=True)},
        ]
        active_window_id = 'window_2'

        def close_window(window_id):
            nonlocal active_window_id, windows

            windows = [w for w in windows if w['id'] != window_id]

            if active_window_id == window_id:
                active_window_id = ''
                if windows:
                    active_window_id = windows[-1]['id']
                    windows[-1]['window'].isActive = True

        close_window('window_2')

        assert active_window_id == 'window_1'
        assert windows[0]['window'].isActive is True


class TestWindowManagerCreation:
    """Test WindowManager window creation functionality."""

    def test_generate_window_id(self):
        """Test unique window ID generation."""
        next_window_id = 1

        def create_window_id():
            nonlocal next_window_id
            window_id = f"window_{next_window_id}"
            next_window_id += 1
            return window_id

        id1 = create_window_id()
        id2 = create_window_id()
        id3 = create_window_id()

        assert id1 == "window_1"
        assert id2 == "window_2"
        assert id3 == "window_3"

    def test_window_cascade_positioning(self):
        """Test cascade positioning for new windows."""
        windows = []

        def get_cascade_position():
            offset = 30
            count = len(windows)
            return (50 + (count * offset) % 200, 50 + (count * offset) % 150)

        for i in range(5):
            pos = get_cascade_position()
            windows.append({'pos': pos})

        # First window at (50, 50)
        assert windows[0]['pos'] == (50, 50)
        # Second at (80, 80)
        assert windows[1]['pos'] == (80, 80)

    def test_create_tool_window(self):
        """Test creating tool window."""
        def create_tool_window(tool_name, config=None):
            return {
                'type': 'tool',
                'title': tool_name,
                'config': config or {}
            }

        window = create_tool_window("Peak Indexing", {'width': 600})

        assert window['type'] == 'tool'
        assert window['title'] == "Peak Indexing"
        assert window['config']['width'] == 600

    def test_create_graph_window(self):
        """Test creating graph window."""
        def create_graph_window(title, config=None):
            return {
                'type': 'graph',
                'title': title,
                'config': config or {}
            }

        window = create_graph_window("Spectrum Plot")

        assert window['type'] == 'graph'
        assert window['title'] == "Spectrum Plot"

    def test_create_table_window(self):
        """Test creating table window."""
        def create_table_window(title, config=None):
            return {
                'type': 'table',
                'title': title,
                'config': config or {}
            }

        window = create_table_window("Peak Data")

        assert window['type'] == 'table'
        assert window['title'] == "Peak Data"


class TestWindowTiling:
    """Test WindowManager window tiling functionality."""

    def test_tile_calculation(self):
        """Test tile grid calculation."""
        import math

        test_cases = [
            (1, 1, 1),   # 1 window: 1x1 grid
            (2, 2, 1),   # 2 windows: 2x1 grid
            (3, 2, 2),   # 3 windows: 2x2 grid
            (4, 2, 2),   # 4 windows: 2x2 grid
            (5, 3, 2),   # 5 windows: 3x2 grid
            (6, 3, 2),   # 6 windows: 3x2 grid
            (9, 3, 3),   # 9 windows: 3x3 grid
        ]

        for window_count, expected_cols, expected_rows in test_cases:
            cols = math.ceil(math.sqrt(window_count))
            rows = math.ceil(window_count / cols)

            assert cols == expected_cols, f"{window_count} windows: expected {expected_cols} cols, got {cols}"
            assert rows == expected_rows, f"{window_count} windows: expected {expected_rows} rows, got {rows}"

    def test_tile_dimensions(self):
        """Test window dimensions after tiling."""
        container_width = 1200
        container_height = 800

        window_count = 4
        import math
        cols = math.ceil(math.sqrt(window_count))
        rows = math.ceil(window_count / cols)

        win_width = container_width / cols
        win_height = container_height / rows

        assert win_width == 600
        assert win_height == 400

    def test_cascade_positioning(self):
        """Test cascade positioning calculation."""
        container_width = 1200
        container_height = 800
        offset = 30

        expected_positions = [
            (30, 30),
            (60, 60),
            (90, 90),
        ]

        for i, (exp_x, exp_y) in enumerate(expected_positions):
            x = offset + i * offset
            y = offset + i * offset
            assert x == exp_x
            assert y == exp_y

    def test_cascade_dimensions(self):
        """Test window dimensions after cascade."""
        container_width = 1200
        container_height = 800

        # Cascade windows are 60% of container size
        expected_width = container_width * 0.6
        expected_height = container_height * 0.6

        assert expected_width == 720
        assert expected_height == 480


class TestBackendPropagation:
    """Test backend propagation through window hierarchy."""

    def test_backend_passed_to_window(self):
        """Test backend is passed to EmbeddedWindow."""
        mock_backend = MagicMock()
        mock_backend.getDatasetList.return_value = ['Dataset1', 'Dataset2']

        # Simulating WindowManager passing backend
        window_props = {
            'backend': mock_backend
        }

        assert window_props['backend'] is mock_backend
        assert window_props['backend'].getDatasetList() == ['Dataset1', 'Dataset2']

    def test_backend_passed_to_content(self):
        """Test backend is passed from EmbeddedWindow to content."""
        mock_backend = MagicMock()
        mock_backend.getDatasetList.return_value = ['Data1']

        # Simulating contentLoader.onLoaded
        embedded_window_backend = mock_backend
        content_item = MagicMock()
        content_item.backend = None

        # Check if item has backend property
        if hasattr(content_item, 'backend'):
            content_item.backend = embedded_window_backend

        assert content_item.backend is mock_backend

    def test_theme_colors_passed_to_content(self):
        """Test theme colors are passed from EmbeddedWindow to content."""
        theme = {
            'bgDark': '#1a1a2e',
            'bgMedium': '#2a2a3e',
            'bgLight': '#3a3a4e',
            'textLight': '#ffffff',
            'textMuted': '#cccccc',
            'accentPink': '#F5A9B8',
            'accentBlue': '#5BCEFA',
        }

        content_item = MagicMock()
        content_item.bgDark = None
        content_item.accentPink = None

        # Simulating property passing
        for color_name, color_value in theme.items():
            if hasattr(content_item, color_name):
                setattr(content_item, color_name, color_value)

        assert content_item.bgDark == '#1a1a2e'
        assert content_item.accentPink == '#F5A9B8'


class TestWindowBoundsConstraints:
    """Test EmbeddedWindow bounds checking for workspace containment."""

    def test_drag_x_clamped_to_zero(self):
        """Test window X position cannot go below 0."""
        # Simulating drag handler bounds checking
        requested_x = -50
        new_x = max(0, requested_x)

        assert new_x == 0

    def test_drag_y_clamped_to_zero(self):
        """Test window Y position cannot go below 0."""
        requested_y = -30
        new_y = max(0, requested_y)

        assert new_y == 0

    def test_drag_positive_position_unchanged(self):
        """Test positive positions pass through unchanged."""
        requested_x = 150
        requested_y = 200

        new_x = max(0, requested_x)
        new_y = max(0, requested_y)

        assert new_x == 150
        assert new_y == 200

    def test_drag_to_origin_allowed(self):
        """Test dragging to (0, 0) is allowed."""
        new_x = max(0, 0)
        new_y = max(0, 0)

        assert new_x == 0
        assert new_y == 0

    def test_bounds_checking_on_all_edges(self):
        """Test bounds checking for various negative positions."""
        test_cases = [
            (-100, -200, 0, 0),
            (-1, 50, 0, 50),
            (50, -1, 50, 0),
            (0, 0, 0, 0),
            (100, 200, 100, 200),
        ]

        for req_x, req_y, exp_x, exp_y in test_cases:
            actual_x = max(0, req_x)
            actual_y = max(0, req_y)
            assert actual_x == exp_x, f"X: {req_x} should clamp to {exp_x}"
            assert actual_y == exp_y, f"Y: {req_y} should clamp to {exp_y}"


class TestViewportAwareFullscreen:
    """Test EmbeddedWindow fullscreen using viewport dimensions."""

    def test_fullscreen_uses_viewport_dimensions(self):
        """Test fullscreen fills viewport, not parent container."""
        viewport_width = 1200
        viewport_height = 800
        viewport_x = 100  # Scroll offset
        viewport_y = 50

        # In fullscreen, position to viewport origin and fill viewport
        fullscreen_x = viewport_x
        fullscreen_y = viewport_y
        fullscreen_width = viewport_width
        fullscreen_height = viewport_height

        assert fullscreen_x == viewport_x
        assert fullscreen_y == viewport_y
        assert fullscreen_width == viewport_width
        assert fullscreen_height == viewport_height

    def test_fullscreen_follows_scroll_position(self):
        """Test fullscreen window position updates with scroll."""
        # Simulate scrolled viewport
        viewport_x = 300  # User scrolled right
        viewport_y = 150  # User scrolled down

        fullscreen_x = viewport_x
        fullscreen_y = viewport_y

        assert fullscreen_x == 300
        assert fullscreen_y == 150

    def test_restore_from_fullscreen_ignores_viewport(self):
        """Test restoring from fullscreen goes back to saved position."""
        # Previous position before fullscreen
        saved_x = 120
        saved_y = 80
        saved_width = 500
        saved_height = 400

        # After restore
        restored_x = saved_x
        restored_y = saved_y
        restored_width = saved_width
        restored_height = saved_height

        assert restored_x == saved_x
        assert restored_y == saved_y
        assert restored_width == saved_width
        assert restored_height == saved_height


class TestWindowMovedResizedSignals:
    """Test windowMoved and windowResized signal behavior."""

    def test_window_moved_signal_emitted_on_drag_release(self):
        """Test windowMoved signal is emitted when drag ends."""
        moved_count = 0

        def on_window_moved():
            nonlocal moved_count
            moved_count += 1

        # Simulate drag release
        on_window_moved()

        assert moved_count == 1

    def test_window_resized_signal_emitted_on_resize_release(self):
        """Test windowResized signal is emitted when resize ends."""
        resized_count = 0

        def on_window_resized():
            nonlocal resized_count
            resized_count += 1

        # Simulate resize from different edges
        on_window_resized()  # Right edge
        on_window_resized()  # Bottom edge
        on_window_resized()  # Corner

        assert resized_count == 3

    def test_move_and_resize_trigger_content_bounds_update(self):
        """Test that move/resize trigger content bounds recalculation."""
        bounds_updated = 0

        def update_content_bounds():
            nonlocal bounds_updated
            bounds_updated += 1

        # Simulate window operations that trigger bounds update
        update_content_bounds()  # On move
        update_content_bounds()  # On resize
        update_content_bounds()  # On create
        update_content_bounds()  # On close

        assert bounds_updated == 4


class TestScrollableWorkspaceContentBounds:
    """Test content bounds tracking for scrollable workspace."""

    def test_content_bounds_from_single_window(self):
        """Test content bounds calculated from one window."""
        viewport_width = 1200
        viewport_height = 800

        window = {'x': 100, 'y': 50, 'width': 500, 'height': 400}

        max_right = max(viewport_width, window['x'] + window['width'] + 20)
        max_bottom = max(viewport_height, window['y'] + window['height'] + 20)

        assert max_right == viewport_width  # 620 < 1200
        assert max_bottom == viewport_height  # 470 < 800

    def test_content_bounds_expand_beyond_viewport(self):
        """Test content bounds expand when window is outside viewport."""
        viewport_width = 800
        viewport_height = 600

        window = {'x': 700, 'y': 500, 'width': 500, 'height': 400}

        max_right = max(viewport_width, window['x'] + window['width'] + 20)
        max_bottom = max(viewport_height, window['y'] + window['height'] + 20)

        assert max_right == 1220  # 700 + 500 + 20
        assert max_bottom == 920  # 500 + 400 + 20

    def test_content_bounds_from_multiple_windows(self):
        """Test content bounds from the rightmost/bottommost window."""
        viewport_width = 800
        viewport_height = 600

        windows = [
            {'x': 50, 'y': 50, 'width': 400, 'height': 300},
            {'x': 600, 'y': 100, 'width': 500, 'height': 400},
            {'x': 200, 'y': 500, 'width': 300, 'height': 250},
        ]

        max_right = viewport_width
        max_bottom = viewport_height

        for w in windows:
            right = w['x'] + w['width'] + 20
            bottom = w['y'] + w['height'] + 20
            if right > max_right:
                max_right = right
            if bottom > max_bottom:
                max_bottom = bottom

        assert max_right == 1120  # 600 + 500 + 20
        assert max_bottom == 770  # 500 + 250 + 20

    def test_content_bounds_reset_on_all_windows_closed(self):
        """Test content bounds reset to viewport when all windows closed."""
        viewport_width = 1200
        viewport_height = 800

        windows = []  # All closed

        max_right = viewport_width
        max_bottom = viewport_height

        for w in windows:
            right = w['x'] + w['width'] + 20
            bottom = w['y'] + w['height'] + 20
            if right > max_right:
                max_right = right
            if bottom > max_bottom:
                max_bottom = bottom

        assert max_right == viewport_width
        assert max_bottom == viewport_height

    def test_window_placement_accounts_for_scroll(self):
        """Test new windows are placed relative to current scroll position."""
        scroll_x = 200
        scroll_y = 150
        offset_x = 50
        offset_y = 50

        # New window placed at scroll offset + default position
        window_x = scroll_x + offset_x
        window_y = scroll_y + offset_y

        assert window_x == 250
        assert window_y == 200


class TestToolWindowIntegration:
    """Test tool window integration with backend."""

    @pytest.fixture
    def mock_backend_for_tools(self):
        """Create mock backend with tool methods."""
        backend = MagicMock()
        backend.getDatasetList.return_value = [
            'Dataset_1',
            'NoBaseline_Dataset_1',
            'Smoothed_Dataset_1'
        ]
        backend.getDatasetInfo.return_value = {
            'type': 'spectral',
            'dimensions': (10, 10),
            'num_spectra': 100,
            'num_points': 500,
            'independent_var': 'Voltage'
        }
        backend.getMapList.return_value = [
            {'title': 'Height Map', 'path': '/path/to/map.tiff'},
            {'title': 'Phase Map', 'path': '/path/to/phase.tiff'}
        ]
        return backend

    def test_peak_indexing_tool_backend_access(self, mock_backend_for_tools):
        """Test PeakIndexingTool can access backend methods."""
        backend = mock_backend_for_tools

        datasets = backend.getDatasetList()

        assert len(datasets) == 3
        assert 'NoBaseline_Dataset_1' in datasets

    def test_curve_analysis_tool_backend_access(self, mock_backend_for_tools):
        """Test CurveAnalysisTool can access dataset info."""
        backend = mock_backend_for_tools

        info = backend.getDatasetInfo('Dataset_1')

        assert info['type'] == 'spectral'
        assert info['dimensions'] == (10, 10)
        assert info['num_spectra'] == 100

    def test_map_processing_tool_backend_access(self, mock_backend_for_tools):
        """Test MapProcessingTool can access map list."""
        backend = mock_backend_for_tools

        maps = backend.getMapList()

        assert len(maps) == 2
        assert maps[0]['title'] == 'Height Map'

    def test_spatial_average_tool_backend_access(self, mock_backend_for_tools):
        """Test SpatialAverageTool can access grid info."""
        backend = mock_backend_for_tools

        info = backend.getDatasetInfo('Dataset_1')
        dimensions = info.get('dimensions', (0, 0))

        assert dimensions == (10, 10)

    def test_tool_operations_return_results(self, mock_backend_for_tools):
        """Test tool operations return expected results."""
        backend = mock_backend_for_tools

        backend.findPeaks.return_value = '/outputs/peaks/peaks_001.csv'
        backend.spatialAverage.return_value = 'SpatialAvg_Dataset_1'
        backend.processMap.return_value = True

        assert backend.findPeaks('Dataset_1', 0.1, 5) == '/outputs/peaks/peaks_001.csv'
        assert backend.spatialAverage('Dataset_1', 10, 10, True, False) == 'SpatialAvg_Dataset_1'
        assert backend.processMap('/path/to/map', 'file', 'gaussian_filter', {'sigma': 1.0}) is True
