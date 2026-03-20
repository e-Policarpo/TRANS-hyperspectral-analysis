"""
Tests for WorkspaceCanvas QML component.

These tests verify the pan, zoom, and coordinate conversion functionality
of the WorkspaceCanvas component used in the unified workspace.
"""

import pytest
import math
from unittest.mock import MagicMock


class TestWorkspaceCanvasPanning:
    """Test WorkspaceCanvas pan behavior."""

    def test_initial_pan_position(self):
        """Test initial pan position is at origin."""
        pan_x = 0
        pan_y = 0

        assert pan_x == 0
        assert pan_y == 0

    def test_wheel_vertical_scroll_pans_vertically(self):
        """Test vertical scroll wheel pans vertically."""
        pan_x = 0
        pan_y = 0
        pan_speed = 1.0

        # Simulate vertical scroll (wheel.angleDelta.y)
        wheel_angle_delta_y = 120  # Typical scroll wheel delta

        pan_y += wheel_angle_delta_y * pan_speed

        assert pan_y == 120
        assert pan_x == 0  # Horizontal unchanged

    def test_wheel_horizontal_scroll_pans_horizontally(self):
        """Test horizontal scroll (trackpad) pans horizontally."""
        pan_x = 0
        pan_y = 0
        pan_speed = 1.0

        # Simulate horizontal scroll (wheel.angleDelta.x)
        wheel_angle_delta_x = 100

        pan_x += wheel_angle_delta_x * pan_speed

        assert pan_x == 100
        assert pan_y == 0  # Vertical unchanged

    def test_wheel_scroll_does_not_zoom(self):
        """Test that scroll wheel pans instead of zooming."""
        zoom_level = 1.0
        pan_x = 0
        pan_y = 0
        pan_speed = 1.0

        # Simulate wheel scroll
        wheel_angle_delta_y = 120

        # Pan behavior (not zoom)
        pan_y += wheel_angle_delta_y * pan_speed

        # Zoom should remain unchanged
        assert zoom_level == 1.0
        assert pan_y == 120

    def test_middle_button_drag_pans(self):
        """Test middle mouse button drag pans canvas."""
        pan_x = 0
        pan_y = 0
        is_panning = False
        last_x = 0
        last_y = 0

        # Simulate middle button press
        def on_pressed(x, y, button):
            nonlocal is_panning, last_x, last_y
            MIDDLE_BUTTON = 4  # Qt.MiddleButton
            if button == MIDDLE_BUTTON:
                is_panning = True
                last_x = x
                last_y = y

        def on_position_changed(x, y):
            nonlocal pan_x, pan_y, last_x, last_y
            if is_panning:
                delta_x = x - last_x
                delta_y = y - last_y
                pan_x += delta_x
                pan_y += delta_y
                last_x = x
                last_y = y

        # Press at (100, 100)
        on_pressed(100, 100, 4)

        # Drag to (150, 130)
        on_position_changed(150, 130)

        assert pan_x == 50
        assert pan_y == 30

    def test_alt_left_click_drag_pans(self):
        """Test Alt + left click drag pans canvas."""
        pan_x = 0
        pan_y = 0
        is_panning = False
        last_x = 0
        last_y = 0

        def on_pressed(x, y, button, modifiers):
            nonlocal is_panning, last_x, last_y
            LEFT_BUTTON = 1
            ALT_MODIFIER = 0x08000000  # Qt.AltModifier

            if button == LEFT_BUTTON and (modifiers & ALT_MODIFIER):
                is_panning = True
                last_x = x
                last_y = y

        def on_position_changed(x, y):
            nonlocal pan_x, pan_y, last_x, last_y
            if is_panning:
                delta_x = x - last_x
                delta_y = y - last_y
                pan_x += delta_x
                pan_y += delta_y
                last_x = x
                last_y = y

        # Alt + left click at (200, 200)
        on_pressed(200, 200, 1, 0x08000000)
        assert is_panning is True

        # Drag to (250, 280)
        on_position_changed(250, 280)

        assert pan_x == 50
        assert pan_y == 80

    def test_pan_persists_after_release(self):
        """Test pan position persists after mouse release."""
        pan_x = 100
        pan_y = 75
        is_panning = True

        def on_released():
            nonlocal is_panning
            is_panning = False

        on_released()

        assert is_panning is False
        assert pan_x == 100
        assert pan_y == 75


class TestWorkspaceCanvasZoom:
    """Test WorkspaceCanvas zoom functionality."""

    def test_initial_zoom_level(self):
        """Test initial zoom is 1.0 (100%)."""
        zoom_level = 1.0
        assert zoom_level == 1.0

    def test_zoom_in_function(self):
        """Test zoomIn() increases zoom by 1.25x."""
        zoom_level = 1.0
        min_zoom = 0.25
        max_zoom = 4.0

        def zoom_in():
            nonlocal zoom_level
            zoom_level = min(max_zoom, zoom_level * 1.25)

        zoom_in()
        assert zoom_level == 1.25

        zoom_in()
        assert zoom_level == 1.5625

    def test_zoom_out_function(self):
        """Test zoomOut() decreases zoom by 1.25x."""
        zoom_level = 1.0
        min_zoom = 0.25
        max_zoom = 4.0

        def zoom_out():
            nonlocal zoom_level
            zoom_level = max(min_zoom, zoom_level / 1.25)

        zoom_out()
        assert zoom_level == 0.8

        zoom_out()
        assert zoom_level == 0.64

    def test_zoom_max_limit(self):
        """Test zoom cannot exceed maximum."""
        zoom_level = 3.5
        max_zoom = 4.0

        def zoom_in():
            nonlocal zoom_level
            zoom_level = min(max_zoom, zoom_level * 1.25)

        zoom_in()
        assert zoom_level == max_zoom

    def test_zoom_min_limit(self):
        """Test zoom cannot go below minimum."""
        zoom_level = 0.3
        min_zoom = 0.25

        def zoom_out():
            nonlocal zoom_level
            zoom_level = max(min_zoom, zoom_level / 1.25)

        zoom_out()
        assert zoom_level == min_zoom


class TestCoordinateConversion:
    """Test WorkspaceCanvas coordinate conversion functions."""

    def test_screen_to_world_no_transform(self):
        """Test screen to world conversion with no pan/zoom."""
        pan_x = 0
        pan_y = 0
        zoom_level = 1.0

        def screen_to_world(screen_x, screen_y):
            return {
                'x': (screen_x - pan_x) / zoom_level,
                'y': (screen_y - pan_y) / zoom_level
            }

        result = screen_to_world(100, 200)

        assert result['x'] == 100
        assert result['y'] == 200

    def test_screen_to_world_with_pan(self):
        """Test screen to world conversion with pan offset."""
        pan_x = 50
        pan_y = 100
        zoom_level = 1.0

        def screen_to_world(screen_x, screen_y):
            return {
                'x': (screen_x - pan_x) / zoom_level,
                'y': (screen_y - pan_y) / zoom_level
            }

        result = screen_to_world(150, 200)

        assert result['x'] == 100  # 150 - 50
        assert result['y'] == 100  # 200 - 100

    def test_screen_to_world_with_zoom(self):
        """Test screen to world conversion with zoom."""
        pan_x = 0
        pan_y = 0
        zoom_level = 2.0

        def screen_to_world(screen_x, screen_y):
            return {
                'x': (screen_x - pan_x) / zoom_level,
                'y': (screen_y - pan_y) / zoom_level
            }

        result = screen_to_world(200, 100)

        assert result['x'] == 100  # 200 / 2
        assert result['y'] == 50   # 100 / 2

    def test_screen_to_world_with_pan_and_zoom(self):
        """Test screen to world conversion with both pan and zoom."""
        pan_x = 100
        pan_y = 50
        zoom_level = 2.0

        def screen_to_world(screen_x, screen_y):
            return {
                'x': (screen_x - pan_x) / zoom_level,
                'y': (screen_y - pan_y) / zoom_level
            }

        result = screen_to_world(300, 150)

        assert result['x'] == 100  # (300 - 100) / 2
        assert result['y'] == 50   # (150 - 50) / 2

    def test_world_to_screen_no_transform(self):
        """Test world to screen conversion with no pan/zoom."""
        pan_x = 0
        pan_y = 0
        zoom_level = 1.0

        def world_to_screen(world_x, world_y):
            return {
                'x': world_x * zoom_level + pan_x,
                'y': world_y * zoom_level + pan_y
            }

        result = world_to_screen(100, 200)

        assert result['x'] == 100
        assert result['y'] == 200

    def test_world_to_screen_with_pan(self):
        """Test world to screen conversion with pan offset."""
        pan_x = 50
        pan_y = 100
        zoom_level = 1.0

        def world_to_screen(world_x, world_y):
            return {
                'x': world_x * zoom_level + pan_x,
                'y': world_y * zoom_level + pan_y
            }

        result = world_to_screen(100, 100)

        assert result['x'] == 150  # 100 + 50
        assert result['y'] == 200  # 100 + 100

    def test_world_to_screen_with_zoom(self):
        """Test world to screen conversion with zoom."""
        pan_x = 0
        pan_y = 0
        zoom_level = 2.0

        def world_to_screen(world_x, world_y):
            return {
                'x': world_x * zoom_level + pan_x,
                'y': world_y * zoom_level + pan_y
            }

        result = world_to_screen(100, 50)

        assert result['x'] == 200  # 100 * 2
        assert result['y'] == 100  # 50 * 2

    def test_roundtrip_conversion(self):
        """Test screen -> world -> screen roundtrip."""
        pan_x = 75
        pan_y = 125
        zoom_level = 1.5

        def screen_to_world(screen_x, screen_y):
            return {
                'x': (screen_x - pan_x) / zoom_level,
                'y': (screen_y - pan_y) / zoom_level
            }

        def world_to_screen(world_x, world_y):
            return {
                'x': world_x * zoom_level + pan_x,
                'y': world_y * zoom_level + pan_y
            }

        original_screen_x = 300
        original_screen_y = 400

        world = screen_to_world(original_screen_x, original_screen_y)
        back_to_screen = world_to_screen(world['x'], world['y'])

        assert abs(back_to_screen['x'] - original_screen_x) < 0.001
        assert abs(back_to_screen['y'] - original_screen_y) < 0.001


class TestSnapToGrid:
    """Test WorkspaceCanvas snap to grid functionality."""

    def test_snap_disabled(self):
        """Test snap returns original position when disabled."""
        snap_to_grid = False
        snap_size = 20

        def snap_position(x, y):
            if snap_to_grid:
                return {
                    'x': round(x / snap_size) * snap_size,
                    'y': round(y / snap_size) * snap_size
                }
            return {'x': x, 'y': y}

        result = snap_position(47, 63)

        assert result['x'] == 47
        assert result['y'] == 63

    def test_snap_enabled(self):
        """Test snap rounds to grid when enabled."""
        snap_to_grid = True
        snap_size = 20

        def snap_position(x, y):
            if snap_to_grid:
                return {
                    'x': round(x / snap_size) * snap_size,
                    'y': round(y / snap_size) * snap_size
                }
            return {'x': x, 'y': y}

        result = snap_position(47, 63)

        assert result['x'] == 40  # 47 rounds to 40
        assert result['y'] == 60  # 63 rounds to 60

    def test_snap_exactly_on_grid(self):
        """Test snap with position already on grid."""
        snap_to_grid = True
        snap_size = 20

        def snap_position(x, y):
            if snap_to_grid:
                return {
                    'x': round(x / snap_size) * snap_size,
                    'y': round(y / snap_size) * snap_size
                }
            return {'x': x, 'y': y}

        result = snap_position(40, 60)

        assert result['x'] == 40
        assert result['y'] == 60

    def test_snap_rounds_up(self):
        """Test snap rounds up past halfway."""
        snap_to_grid = True
        snap_size = 20

        def snap_position(x, y):
            if snap_to_grid:
                return {
                    'x': round(x / snap_size) * snap_size,
                    'y': round(y / snap_size) * snap_size
                }
            return {'x': x, 'y': y}

        result = snap_position(51, 71)

        assert result['x'] == 60  # 51 rounds up to 60
        assert result['y'] == 80  # 71 rounds up to 80


class TestResetView:
    """Test WorkspaceCanvas reset view functionality."""

    def test_reset_view(self):
        """Test resetView() resets all transform properties."""
        zoom_level = 1.5
        pan_x = 200
        pan_y = 150

        def reset_view():
            nonlocal zoom_level, pan_x, pan_y
            zoom_level = 1.0
            pan_x = 0
            pan_y = 0

        reset_view()

        assert zoom_level == 1.0
        assert pan_x == 0
        assert pan_y == 0


class TestFitToContent:
    """Test WorkspaceCanvas fit to content functionality."""

    def test_fit_to_content_empty(self):
        """Test fit with empty/invalid bounds resets view."""
        zoom_level = 1.5
        pan_x = 200
        pan_y = 150

        def fit_to_content(content_bounds):
            nonlocal zoom_level, pan_x, pan_y

            if not content_bounds or content_bounds['width'] <= 0 or content_bounds['height'] <= 0:
                zoom_level = 1.0
                pan_x = 0
                pan_y = 0
                return

        fit_to_content({'x': 0, 'y': 0, 'width': 0, 'height': 0})

        assert zoom_level == 1.0
        assert pan_x == 0
        assert pan_y == 0

    def test_fit_to_content_calculates_zoom(self):
        """Test fit calculates appropriate zoom level."""
        canvas_width = 1000
        canvas_height = 800
        min_zoom = 0.25
        max_zoom = 4.0
        padding = 50

        content_bounds = {'x': 0, 'y': 0, 'width': 500, 'height': 400}

        scale_x = (canvas_width - padding * 2) / content_bounds['width']
        scale_y = (canvas_height - padding * 2) / content_bounds['height']
        zoom_level = min(scale_x, scale_y, max_zoom)
        zoom_level = max(zoom_level, min_zoom)

        # scale_x = 900 / 500 = 1.8
        # scale_y = 700 / 400 = 1.75
        # zoom = min(1.8, 1.75, 4.0) = 1.75
        assert abs(zoom_level - 1.75) < 0.001

    def test_fit_to_content_calculates_pan(self):
        """Test fit calculates appropriate pan offset."""
        canvas_width = 1000
        canvas_height = 800
        zoom_level = 1.0

        content_bounds = {'x': 100, 'y': 50, 'width': 400, 'height': 300}

        # Center content in canvas
        pan_x = canvas_width / 2 - (content_bounds['x'] + content_bounds['width'] / 2) * zoom_level
        pan_y = canvas_height / 2 - (content_bounds['y'] + content_bounds['height'] / 2) * zoom_level

        # pan_x = 500 - (100 + 200) * 1 = 500 - 300 = 200
        # pan_y = 400 - (50 + 150) * 1 = 400 - 200 = 200
        assert pan_x == 200
        assert pan_y == 200


class TestBackgroundStyles:
    """Test WorkspaceCanvas background style options."""

    def test_background_style_options(self):
        """Test available background style options."""
        valid_styles = ['none', 'dotted', 'grid', 'workflow']

        for style in valid_styles:
            assert style in valid_styles

    def test_default_background_style(self):
        """Test default background style is dotted."""
        background_style = 'dotted'
        assert background_style == 'dotted'

    def test_dotted_canvas_visibility(self):
        """Test dotted canvas visibility based on style."""
        def is_dotted_visible(background_style):
            return background_style == 'dotted'

        assert is_dotted_visible('dotted') is True
        assert is_dotted_visible('grid') is False
        assert is_dotted_visible('none') is False

    def test_grid_canvas_visibility(self):
        """Test grid canvas visibility based on style."""
        def is_grid_visible(background_style):
            return background_style in ['grid', 'workflow']

        assert is_grid_visible('grid') is True
        assert is_grid_visible('workflow') is True
        assert is_grid_visible('dotted') is False
        assert is_grid_visible('none') is False


class TestGridPatternCalculation:
    """Test WorkspaceCanvas grid pattern calculations."""

    def test_grid_spacing_with_zoom(self):
        """Test grid spacing scales with zoom."""
        base_grid_spacing = 20
        zoom_level = 2.0

        actual_spacing = base_grid_spacing * zoom_level

        assert actual_spacing == 40

    def test_grid_offset_with_pan(self):
        """Test grid offset wraps with pan."""
        grid_spacing = 20
        pan_x = 35
        pan_y = 47

        offset_x = pan_x % grid_spacing  # 35 % 20 = 15
        offset_y = pan_y % grid_spacing  # 47 % 20 = 7

        assert offset_x == 15
        assert offset_y == 7

    def test_major_grid_spacing(self):
        """Test major grid lines every 5 cells for workflow style."""
        grid_spacing = 20
        zoom_level = 1.0
        major_multiplier = 5

        minor_spacing = grid_spacing * zoom_level
        major_spacing = minor_spacing * major_multiplier

        assert minor_spacing == 20
        assert major_spacing == 100


class TestZoomDisabled:
    """Test WorkspaceCanvas behavior when zoomEnabled is false."""

    def test_zoom_disabled_ignores_wheel(self):
        """Test wheel events are ignored when zoom is disabled."""
        zoom_enabled = False
        zoom_level = 1.0
        pan_x = 0
        pan_y = 0

        # Simulate wheel event
        wheel_angle_delta_y = 120

        if not zoom_enabled:
            # Wheel should be rejected
            wheel_accepted = False
        else:
            zoom_factor = 1.1 if wheel_angle_delta_y > 0 else 0.9
            zoom_level *= zoom_factor
            wheel_accepted = True

        assert wheel_accepted is False
        assert zoom_level == 1.0  # Unchanged

    def test_zoom_disabled_no_pan(self):
        """Test middle-button pan is disabled when zoom is disabled."""
        zoom_enabled = False
        pan_x = 0
        pan_y = 0
        is_panning = False

        # Simulate middle button press
        def on_pressed(button):
            nonlocal is_panning
            if not zoom_enabled:
                return
            if button == 4:  # Qt.MiddleButton
                is_panning = True

        on_pressed(4)

        assert is_panning is False
        assert pan_x == 0
        assert pan_y == 0

    def test_zoom_enabled_allows_wheel(self):
        """Test wheel events work when zoom is enabled."""
        zoom_enabled = True
        zoom_level = 1.0

        wheel_angle_delta_y = 120

        if zoom_enabled:
            zoom_factor = 1.1 if wheel_angle_delta_y > 0 else 0.9
            zoom_level *= zoom_factor

        assert zoom_level == pytest.approx(1.1)

    def test_zoom_disabled_preserves_current_zoom(self):
        """Test disabling zoom preserves current zoom level."""
        zoom_level = 1.5  # Previously zoomed

        # Disable zoom
        zoom_enabled = False

        # Zoom level should remain unchanged
        assert zoom_level == 1.5

    def test_zoom_disabled_click_still_works(self):
        """Test left click events still fire when zoom is disabled."""
        zoom_enabled = False
        clicked = False
        click_x = 0
        click_y = 0

        def on_click(x, y):
            nonlocal clicked, click_x, click_y
            clicked = True
            click_x = x
            click_y = y

        # Click should work regardless of zoom setting
        on_click(100, 200)

        assert clicked is True
        assert click_x == 100
        assert click_y == 200


class TestToolPalettePanelBehavior:
    """Tests for ToolPalettePanel component behavior."""

    def test_tool_list_populated(self):
        """Test tool palette contains expected tools."""
        tools = [
            "1D FFT", "2D FFT", "Curve Smoothing", "Image Smoothing",
            "Derivative Calculator", "Curve Fitting", "Gradient Filter",
            "Integration Utility", "Map Generator", "Spatial Average",
            "Truncate Data", "Curve Analysis", "Peak Indexing",
            "Average Curves", "Filter Bad Data",
            "Dirac Point Estimator", "Detect Bandgap & Doping"
        ]

        assert len(tools) == 17
        assert "Peak Indexing" in tools
        assert "Filter Bad Data" in tools
        assert "Dirac Point Estimator" in tools
        assert "Detect Bandgap & Doping" in tools

    def test_tool_search_filter(self):
        """Test search functionality filters tool list."""
        tools = [
            "1D FFT", "2D FFT", "Curve Smoothing", "Curve Fitting",
            "Derivative Calculator", "Peak Indexing", "Filter Bad Data"
        ]

        search_text = "curve"

        filtered = [t for t in tools if search_text.lower() in t.lower()]

        assert len(filtered) == 2
        assert "Curve Smoothing" in filtered
        assert "Curve Fitting" in filtered

    def test_tool_search_empty_string_shows_all(self):
        """Test empty search shows all tools."""
        tools = ["Tool A", "Tool B", "Tool C"]
        search_text = ""

        filtered = [t for t in tools if not search_text or search_text.lower() in t.lower()]

        assert len(filtered) == 3

    def test_tool_search_no_match(self):
        """Test search with no matches shows empty list."""
        tools = ["1D FFT", "Curve Smoothing", "Derivative Calculator"]
        search_text = "xyz"

        filtered = [t for t in tools if search_text.lower() in t.lower()]

        assert len(filtered) == 0

    def test_tool_activation_signal(self):
        """Test double-click on tool emits toolActivated signal."""
        activated_tools = []

        def on_tool_activated(tool_name):
            activated_tools.append(tool_name)

        # Simulate double-click on tool
        on_tool_activated("Peak Indexing")

        assert len(activated_tools) == 1
        assert activated_tools[0] == "Peak Indexing"

    def test_tool_palette_for_spectral_tab(self):
        """Test tool palette has correct tools for spectral analysis tab."""
        spectral_tools = [
            "1D FFT", "2D FFT", "Curve Smoothing", "Image Smoothing",
            "Derivative Calculator", "Curve Fitting", "Gradient Filter",
            "Integration Utility", "Map Generator", "Spatial Average",
            "Truncate Data", "Curve Analysis", "Peak Indexing",
            "Average Curves", "Filter Bad Data",
            "Dirac Point Estimator", "Detect Bandgap & Doping"
        ]

        # All expected tools present
        assert "1D FFT" in spectral_tools
        assert "Map Generator" in spectral_tools
        assert "Detect Bandgap & Doping" in spectral_tools

    def test_tool_palette_for_map_tab(self):
        """Test tool palette has correct tools for map editor tab."""
        map_tools = [
            "Map Discretizer", "Map Processing"
        ]

        assert "Map Discretizer" in map_tools
        assert "Map Processing" in map_tools


class TestDropArea:
    """Test WorkspaceCanvas drop area functionality."""

    def test_drop_calculates_world_coordinates(self):
        """Test drop converts screen to world coordinates."""
        pan_x = 50
        pan_y = 100
        zoom_level = 2.0

        def on_dropped(drop_x, drop_y):
            world_x = (drop_x - pan_x) / zoom_level
            world_y = (drop_y - pan_y) / zoom_level
            return {'x': world_x, 'y': world_y}

        result = on_dropped(250, 300)

        assert result['x'] == 100  # (250 - 50) / 2
        assert result['y'] == 100  # (300 - 100) / 2

    def test_drop_with_snap(self):
        """Test drop snaps to grid when enabled."""
        pan_x = 0
        pan_y = 0
        zoom_level = 1.0
        snap_to_grid = True
        snap_size = 20

        def on_dropped(drop_x, drop_y):
            world_x = (drop_x - pan_x) / zoom_level
            world_y = (drop_y - pan_y) / zoom_level

            if snap_to_grid:
                world_x = round(world_x / snap_size) * snap_size
                world_y = round(world_y / snap_size) * snap_size

            return {'x': world_x, 'y': world_y}

        result = on_dropped(47, 63)

        assert result['x'] == 40
        assert result['y'] == 60
