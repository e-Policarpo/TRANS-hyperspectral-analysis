"""
ViewBox state machine — view range, limits, aspect, mouse modes,
zoom history.

Pure-Python refactor of the parts of pyqtgraph's
``graphicsItems/ViewBox/ViewBox.py`` that don't depend on
``QGraphicsScene`` — the upstream class is a ``GraphicsWidget`` that
participates in pyqtgraph's scene-graph, while TRANS's canvases are
``QQuickPaintedItem``s that own their own paint cycle. This port keeps
the algorithms (range / target-range bookkeeping, aspect lock, range
limits, mouse-mode interaction handlers, zoom history) and drops the
scene plumbing.

The class is **transform-agnostic**: the canvas registers two
callables, ``pixel_to_data`` and ``data_to_pixel``, plus the axes
pixel rect (``set_axes_pixel_rect``). In Phase 2 the canvas backs
those with matplotlib's ``transData``; in Phase 3 it swaps them for a
``QTransform``. The view-state contract doesn't change either way.

Upstream: https://github.com/pyqtgraph/pyqtgraph @ d588dd3
Originally: pyqtgraph, MIT-licensed (see ``LICENSE`` in this package).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


PixelToData = Callable[[float, float], Tuple[float, float]]
DataToPixel = Callable[[float, float], Tuple[float, float]]
DirtyCallback = Callable[[], None]


@dataclass
class ViewRect:
    """Inclusive view range in data units (``x_min`` to ``x_max``,
    ``y_min`` to ``y_max``)."""
    x_min: float = 0.0
    x_max: float = 1.0
    y_min: float = 0.0
    y_max: float = 1.0

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    def as_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x_min, self.x_max, self.y_min, self.y_max)


# Axes pixel rect (where the plot area lives inside the widget),
# expressed as (left, top, right, bottom) in widget pixel coords.
AxesPixelRect = Tuple[float, float, float, float]


@dataclass
class ViewLimits:
    """Optional outer bounds the view can never escape.

    ``None`` means "no limit on that side". Used by ``apply_limits``
    before any view-range mutation lands, so user interaction can't push
    the view past where the data lives.
    """
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None


# Mouse interaction modes.
MOUSE_MODE_PAN = "pan"          # left-drag pans, drag selects
MOUSE_MODE_RECT = "rect"        # left-drag rubber-band-zooms


class ViewBoxState:
    """View-state + mouse handlers for a single 2-D plot area.

    The canvas owns the rendering substrate and the QQuickPaintedItem
    chrome; this class owns the view rect, limits, aspect, axis
    inversion, mouse-mode, zoom history, and the interaction state for
    pan / rubber-band-zoom.

    ``x_mode_only=True`` collapses the y-axis interactions (the profile
    canvas selects an x-range with no y component).
    """

    def __init__(self, *, x_mode_only: bool = False) -> None:
        # Core state.
        self._view = ViewRect()
        self._target = ViewRect()
        self._limits = ViewLimits()
        self._inverted_x = False
        self._inverted_y = False

        # Aspect lock — when set, every x-range mutation forces the
        # y-range to ``height = width / ratio``.
        self._aspect_locked = False
        self._aspect_ratio = 1.0

        # Auto-range with margin (5 % matches the upstream default).
        self._auto_range_enabled = True
        self._auto_range_margin = 0.05
        self._auto_range_data: Optional[ViewRect] = None

        # Mouse mode + interaction state.
        self._mouse_mode = MOUSE_MODE_PAN
        self._x_mode_only = bool(x_mode_only)
        self._is_panning = False
        self._is_selecting = False
        self._pan_last_px: Optional[Tuple[float, float]] = None
        self._selection_start_data: Optional[Tuple[float, float]] = None
        self._selection_end_data: Optional[Tuple[float, float]] = None

        # Zoom history (stack of prior ranges for "undo zoom").
        self._scale_history: List[ViewRect] = []
        self._scale_history_limit = 50

        # Transform adapters — pluggable so Phase 3 can swap the
        # matplotlib transData backing for a native QTransform.
        self._pixel_to_data: PixelToData = lambda px, py: (px, py)
        self._data_to_pixel: DataToPixel = lambda x, y: (x, y)
        self._axes_pixel_rect: Optional[AxesPixelRect] = None

        # Notify the canvas when state mutates so it knows to repaint.
        self._dirty: Optional[DirtyCallback] = None

    # =====================================================================
    # Transform / axes-rect plumbing (called by the canvas after each render)
    # =====================================================================

    def set_transforms(
        self, pixel_to_data: PixelToData, data_to_pixel: DataToPixel,
    ) -> None:
        self._pixel_to_data = pixel_to_data
        self._data_to_pixel = data_to_pixel

    def set_axes_pixel_rect(self, rect: AxesPixelRect) -> None:
        self._axes_pixel_rect = rect

    def set_dirty_callback(self, cb: DirtyCallback) -> None:
        self._dirty = cb

    def _mark_dirty(self) -> None:
        if self._dirty is not None:
            self._dirty()

    # =====================================================================
    # View range / target range
    # =====================================================================

    def view_range(self) -> ViewRect:
        return ViewRect(*self._view.as_tuple())

    def set_view_range(
        self,
        x_min: float, x_max: float,
        y_min: float, y_max: float,
        *,
        push_history: bool = True,
        disable_auto: bool = True,
    ) -> None:
        """Set the visible range. Push the previous range onto the zoom
        history unless the caller is already restoring from it.

        ``disable_auto`` is the upstream default: any manual range
        change turns off auto-range so the user's choice sticks until
        they hit ``reset_view``."""
        new_x_min, new_x_max = sorted((float(x_min), float(x_max)))
        new_y_min, new_y_max = sorted((float(y_min), float(y_max)))
        new = ViewRect(new_x_min, new_x_max, new_y_min, new_y_max)
        self._apply_limits(new)
        self._apply_aspect(new)
        if push_history:
            self._push_history(self._view)
        self._view = new
        self._target = ViewRect(*new.as_tuple())
        if disable_auto:
            self._auto_range_enabled = False
        self._mark_dirty()

    def view_x_range(self) -> Tuple[float, float]:
        return (self._view.x_min, self._view.x_max)

    def view_y_range(self) -> Tuple[float, float]:
        return (self._view.y_min, self._view.y_max)

    # =====================================================================
    # Auto-range
    # =====================================================================

    def set_auto_range_data(self, data: ViewRect) -> None:
        """Tell the viewbox the current data extent (used by
        :meth:`trigger_auto_range`)."""
        self._auto_range_data = ViewRect(*data.as_tuple())

    def auto_range_enabled(self) -> bool:
        return self._auto_range_enabled

    def set_auto_range_enabled(self, enabled: bool) -> None:
        self._auto_range_enabled = bool(enabled)

    def auto_range_margin(self) -> float:
        return self._auto_range_margin

    def set_auto_range_margin(self, margin: float) -> None:
        self._auto_range_margin = max(0.0, float(margin))

    def trigger_auto_range(self) -> None:
        """Snap the view to the data extent + margin. No-op when no
        data extent has been registered yet."""
        if self._auto_range_data is None:
            return
        margin = self._auto_range_margin
        d = self._auto_range_data
        dx = (d.x_max - d.x_min) * margin or 0.5
        dy = (d.y_max - d.y_min) * margin or 0.5
        self.set_view_range(
            d.x_min - dx, d.x_max + dx,
            d.y_min - dy, d.y_max + dy,
            push_history=True,
            disable_auto=False,  # auto-range stays on
        )
        self._auto_range_enabled = True

    # =====================================================================
    # Limits
    # =====================================================================

    def set_limits(
        self, *,
        x_min: Optional[float] = None, x_max: Optional[float] = None,
        y_min: Optional[float] = None, y_max: Optional[float] = None,
    ) -> None:
        if x_min is not None:
            self._limits.x_min = float(x_min)
        if x_max is not None:
            self._limits.x_max = float(x_max)
        if y_min is not None:
            self._limits.y_min = float(y_min)
        if y_max is not None:
            self._limits.y_max = float(y_max)
        # Re-clamp the current view in case it now violates limits.
        clamped = ViewRect(*self._view.as_tuple())
        self._apply_limits(clamped)
        if clamped.as_tuple() != self._view.as_tuple():
            self._view = clamped
            self._target = ViewRect(*clamped.as_tuple())
            self._mark_dirty()

    def _apply_limits(self, rect: ViewRect) -> None:
        """Clamp ``rect`` in-place to the configured outer bounds."""
        L = self._limits
        if L.x_min is not None and rect.x_min < L.x_min:
            rect.x_min = L.x_min
        if L.x_max is not None and rect.x_max > L.x_max:
            rect.x_max = L.x_max
        if L.y_min is not None and rect.y_min < L.y_min:
            rect.y_min = L.y_min
        if L.y_max is not None and rect.y_max > L.y_max:
            rect.y_max = L.y_max

    # =====================================================================
    # Aspect lock
    # =====================================================================

    def set_aspect_locked(
        self, locked: bool, *, ratio: float = 1.0,
    ) -> None:
        """Force y-range height = width / ratio. ``ratio=1.0`` is
        equal-units-per-pixel — useful for image overlays.
        """
        self._aspect_locked = bool(locked)
        if ratio > 0:
            self._aspect_ratio = float(ratio)
        if self._aspect_locked:
            adjusted = ViewRect(*self._view.as_tuple())
            self._apply_aspect(adjusted)
            self._view = adjusted
            self._target = ViewRect(*adjusted.as_tuple())
            self._mark_dirty()

    def _apply_aspect(self, rect: ViewRect) -> None:
        if not self._aspect_locked:
            return
        target_h = rect.width / self._aspect_ratio
        cy = (rect.y_min + rect.y_max) / 2
        rect.y_min = cy - target_h / 2
        rect.y_max = cy + target_h / 2

    # =====================================================================
    # Axis inversion
    # =====================================================================

    def set_inverted(
        self, *, x: Optional[bool] = None, y: Optional[bool] = None,
    ) -> None:
        if x is not None:
            self._inverted_x = bool(x)
        if y is not None:
            self._inverted_y = bool(y)
        self._mark_dirty()

    def inverted_x(self) -> bool:
        return self._inverted_x

    def inverted_y(self) -> bool:
        return self._inverted_y

    # =====================================================================
    # Zoom history
    # =====================================================================

    def _push_history(self, rect: ViewRect) -> None:
        self._scale_history.append(ViewRect(*rect.as_tuple()))
        if len(self._scale_history) > self._scale_history_limit:
            self._scale_history.pop(0)

    def undo_view(self) -> bool:
        """Pop the most recent prior view off the history. Returns
        ``True`` if anything was restored.
        """
        if not self._scale_history:
            return False
        prev = self._scale_history.pop()
        # Don't re-push onto history during the undo itself.
        self._view = prev
        self._target = ViewRect(*prev.as_tuple())
        self._mark_dirty()
        return True

    # =====================================================================
    # Mouse mode
    # =====================================================================

    def mouse_mode(self) -> str:
        return self._mouse_mode

    def set_mouse_mode(self, mode: str) -> None:
        if mode not in (MOUSE_MODE_PAN, MOUSE_MODE_RECT):
            raise ValueError(
                f"unknown mouse mode {mode!r}; expected 'pan' or 'rect'"
            )
        self._mouse_mode = mode
        # Cancel any in-flight interaction when the mode changes.
        self._is_panning = False
        self._is_selecting = False
        self._pan_last_px = None
        self._selection_start_data = None
        self._selection_end_data = None
        self._mark_dirty()

    # =====================================================================
    # Interaction handlers — called from the canvas's mouse events.
    # Return ``True`` when the viewbox consumed the event so the canvas
    # knows whether to invoke its own follow-up logic (e.g. emitting
    # ``rangeSelected`` after a successful rubber-band zoom).
    # =====================================================================

    def is_panning(self) -> bool:
        return self._is_panning

    def is_selecting(self) -> bool:
        return self._is_selecting

    def selection_box_data(
        self,
    ) -> Optional[Tuple[float, float, float, float]]:
        """``(x_min, y_min, x_max, y_max)`` of the current rubber-band
        rectangle in data units, or ``None`` when nothing is being
        selected.
        """
        s = self._selection_start_data
        e = self._selection_end_data
        if s is None or e is None:
            return None
        x_min, x_max = sorted((s[0], e[0]))
        y_min, y_max = sorted((s[1], e[1]))
        return (x_min, y_min, x_max, y_max)

    def handle_press_left(
        self, pos_px: Tuple[float, float],
    ) -> bool:
        """Left-button press. The interaction it starts depends on the
        active mouse mode (driven by the graph toolbar's pan/zoom
        toggle):

        * ``MOUSE_MODE_RECT`` → begin a rubber-band zoom rectangle.
        * ``MOUSE_MODE_PAN``  → begin a left-drag pan.

        Previously the left button always started a zoom-rect
        regardless of mode, so the toolbar toggle had no effect — the
        pan/zoom switch is what this respects now.
        """
        if self._mouse_mode == MOUSE_MODE_RECT:
            x, y = self._pixel_to_data(*pos_px)
            self._is_selecting = True
            self._selection_start_data = (x, y)
            self._selection_end_data = (x, y)
            return True
        # Pan mode: left-drag pans, tracked in pixel space (same path
        # as a right-button pan) so log-scale axes behave correctly.
        self._is_panning = True
        self._pan_last_px = pos_px
        return True

    def handle_press_right(
        self, pos_px: Tuple[float, float],
    ) -> bool:
        """Right-button press starts a pan. Pan tracks in pixel space
        so log-scale axes behave correctly."""
        self._is_panning = True
        self._pan_last_px = pos_px
        return True

    def handle_move(
        self, pos_px: Tuple[float, float],
    ) -> bool:
        """Update the active interaction. Returns ``True`` when the
        view range changed (so the canvas knows to repaint).
        """
        if self._is_selecting:
            x, y = self._pixel_to_data(*pos_px)
            self._selection_end_data = (x, y)
            self._mark_dirty()
            return False  # range hasn't changed; selection overlay needs repaint
        if self._is_panning and self._pan_last_px is not None:
            dx_px = pos_px[0] - self._pan_last_px[0]
            dy_px = pos_px[1] - self._pan_last_px[1]
            rect = self._axes_pixel_rect
            if rect is None:
                return False
            left, top, right, bottom = rect
            ax_w = right - left
            ax_h = bottom - top
            if ax_w <= 0 or ax_h <= 0:
                return False
            # Convert the shifted axes corners back through the
            # pixel→data adapter — works for both linear and log scale.
            new_xmin, _ = self._pixel_to_data(left - dx_px, top)
            new_xmax, _ = self._pixel_to_data(right - dx_px, top)
            _, new_ymax = self._pixel_to_data(left, top - dy_px)
            _, new_ymin = self._pixel_to_data(left, bottom - dy_px)
            self._pan_last_px = pos_px
            if self._x_mode_only:
                # Keep the existing y-range; pan only in x.
                self.set_view_range(
                    new_xmin, new_xmax,
                    self._view.y_min, self._view.y_max,
                    push_history=False,
                )
            else:
                self.set_view_range(
                    new_xmin, new_xmax, new_ymin, new_ymax,
                    push_history=False,
                )
            return True
        return False

    def handle_release_left(
        self, pos_px: Tuple[float, float], *, drag_threshold_px: float = 5.0,
    ) -> Optional[Tuple[float, float, float, float]]:
        """Finish a left-drag. Returns ``(x_min, y_min, x_max, y_max)``
        when the drag was long enough to count as a zoom-rect; returns
        ``None`` otherwise (so the canvas can fall through to its
        single-click behaviour)."""
        # In pan mode the left button drives a pan, not a selection —
        # end it here (mirrors ``handle_release_right``).
        if self._is_panning:
            self._is_panning = False
            self._pan_last_px = None
            self._mark_dirty()
            return None
        result: Optional[Tuple[float, float, float, float]] = None
        if self._is_selecting and self._selection_start_data is not None:
            x, y = self._pixel_to_data(*pos_px)
            self._selection_end_data = (x, y)
            sx, sy = self._selection_start_data
            ex, ey = self._selection_end_data
            spx, spy = self._data_to_pixel(sx, sy)
            epx, epy = self._data_to_pixel(ex, ey)
            if (
                abs(epx - spx) > drag_threshold_px
                and abs(epy - spy) > drag_threshold_px
            ):
                xlo, xhi = sorted((sx, ex))
                ylo, yhi = sorted((sy, ey))
                if self._x_mode_only:
                    ylo, yhi = self._view.y_min, self._view.y_max
                self.set_view_range(xlo, xhi, ylo, yhi)
                result = (xlo, ylo, xhi, yhi)
        # Always clear interaction state regardless.
        self._is_selecting = False
        self._selection_start_data = None
        self._selection_end_data = None
        self._mark_dirty()
        return result

    def handle_release_right(self) -> None:
        self._is_panning = False
        self._pan_last_px = None
        self._mark_dirty()

    def handle_wheel(
        self,
        pos_px: Tuple[float, float],
        delta_y: float,
        *,
        zoom_step: float = 0.85,
    ) -> bool:
        """Zoom centred on the cursor. ``delta_y > 0`` zooms in.
        Returns ``True`` when the view changed."""
        rect = self._axes_pixel_rect
        if rect is None:
            return False
        left, top, right, bottom = rect
        ax_w = right - left
        ax_h = bottom - top
        if ax_w <= 0 or ax_h <= 0:
            return False
        shrink = zoom_step if delta_y > 0 else (1.0 / zoom_step)
        fx = (pos_px[0] - left) / ax_w
        fy = (pos_px[1] - top) / ax_h
        fx = max(0.0, min(1.0, fx))
        fy = max(0.0, min(1.0, fy))
        # New pixel bounds shrunk/expanded around the cursor pixel.
        new_left = pos_px[0] - fx * ax_w * shrink
        new_right = pos_px[0] + (1 - fx) * ax_w * shrink
        new_top = pos_px[1] - fy * ax_h * shrink
        new_bottom = pos_px[1] + (1 - fy) * ax_h * shrink
        xmin, ymax = self._pixel_to_data(new_left, new_top)
        xmax, ymin = self._pixel_to_data(new_right, new_bottom)
        if self._x_mode_only:
            self.set_view_range(
                xmin, xmax,
                self._view.y_min, self._view.y_max,
            )
        else:
            self.set_view_range(xmin, xmax, ymin, ymax)
        return True

    def handle_double_click(self) -> None:
        """Double-click resets the view (auto-range)."""
        self._auto_range_enabled = True
        self.trigger_auto_range()
