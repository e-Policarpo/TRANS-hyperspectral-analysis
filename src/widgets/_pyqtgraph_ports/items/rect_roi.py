"""
``RectROI`` — draggable axis-aligned rectangle with corner-handle resize
and an optional snap-to-grid extension.

Distilled from ``pyqtgraph/graphicsItems/ROI.py`` (commit
``d588dd3ec30915e61c8496a0fe1db21fc25e4da5``, MIT). Upstream's ``ROI``
is a polymorphic family (``RectROI`` / ``EllipseROI`` / ``LineROI`` /
…) with arbitrary rotation, free-form handle placement, and a full
QGraphicsScene event pipeline. This port keeps only what TRANS needs
for the map canvas:

- Axis-aligned rectangle in data coordinates (no rotation).
- Four corner handles for resize, plus the body for translate.
- Optional per-axis bounds.
- ``snap_step`` + ``snap_origin`` extension: when the ROI is told to
  snap, every corner is quantised to a grid step on each axis. The
  map canvas wires this to the block grid so an ROI dropped on a
  discretised map locks to the same cells the existing
  ``BLOCK_SELECT`` tool would have toggled. Pass ``None`` (or both
  axes ``None``) to disable.

Edge handles, rotation, custom handle widgets, and the
``snapInToGrid``/``parentBounds`` glue all live in upstream's full
``ROI`` and aren't reproduced here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen


HIT_NONE = "none"
HIT_BODY = "body"
HIT_NW = "nw"
HIT_NE = "ne"
HIT_SW = "sw"
HIT_SE = "se"

_CORNERS = (HIT_NW, HIT_NE, HIT_SW, HIT_SE)


@dataclass
class RectROIState:
    """JSON-serialisable state for a ``RectROI``."""

    roi_id: Any = 0
    # Always stored normalised: x0 <= x1, y0 <= y1.
    rect: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    bounds_x: Optional[Tuple[Optional[float], Optional[float]]] = None
    bounds_y: Optional[Tuple[Optional[float], Optional[float]]] = None
    movable: bool = True
    snap_step: Optional[Tuple[Optional[float], Optional[float]]] = None
    snap_origin: Tuple[float, float] = (0.0, 0.0)
    pen_color: str = "#5BCEFA"
    pen_width: float = 1.5
    hover_pen_color: str = "#FFD700"
    brush_color: str = "#5BCEFA"
    brush_alpha: int = 40
    hover_brush_alpha: int = 80
    handle_size_px: float = 8.0
    handle_grab_px: float = 8.0
    label: str = ""


class RectROI:
    """Axis-aligned rectangular ROI with corner-handle resize."""

    def __init__(
        self,
        roi_id: Any = 0,
        *,
        rect: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
        bounds_x: Optional[Tuple[Optional[float], Optional[float]]] = None,
        bounds_y: Optional[Tuple[Optional[float], Optional[float]]] = None,
        movable: bool = True,
        snap_step: Optional[Tuple[Optional[float], Optional[float]]] = None,
        snap_origin: Tuple[float, float] = (0.0, 0.0),
        pen_color: str = "#5BCEFA",
        pen_width: float = 1.5,
        hover_pen_color: str = "#FFD700",
        brush_color: str = "#5BCEFA",
        brush_alpha: int = 40,
        hover_brush_alpha: int = 80,
        handle_size_px: float = 8.0,
        handle_grab_px: float = 8.0,
        label: str = "",
    ) -> None:
        self._state = RectROIState(
            roi_id=roi_id,
            rect=_normalize_rect(rect),
            bounds_x=_normalize_bounds(bounds_x),
            bounds_y=_normalize_bounds(bounds_y),
            movable=bool(movable),
            snap_step=_normalize_snap_step(snap_step),
            snap_origin=(
                float(snap_origin[0]), float(snap_origin[1]),
            ),
            pen_color=str(pen_color),
            pen_width=float(pen_width),
            hover_pen_color=str(hover_pen_color),
            brush_color=str(brush_color),
            brush_alpha=int(brush_alpha),
            hover_brush_alpha=int(hover_brush_alpha),
            handle_size_px=float(handle_size_px),
            handle_grab_px=float(handle_grab_px),
            label=str(label),
        )
        self._state.rect = self._clamp_rect(self._state.rect)

    # --- accessors --------------------------------------------------

    @property
    def roi_id(self) -> Any:
        return self._state.roi_id

    @property
    def movable(self) -> bool:
        return self._state.movable

    @property
    def label(self) -> str:
        return self._state.label

    def rect(self) -> Tuple[float, float, float, float]:
        return self._state.rect

    def snap_step(self) -> Optional[Tuple[Optional[float], Optional[float]]]:
        return self._state.snap_step

    def bounds(self) -> Tuple[
        Optional[Tuple[Optional[float], Optional[float]]],
        Optional[Tuple[Optional[float], Optional[float]]],
    ]:
        return self._state.bounds_x, self._state.bounds_y

    # --- mutators ---------------------------------------------------

    def set_rect(
        self,
        x0: float, y0: float, x1: float, y1: float,
    ) -> bool:
        new_rect = self._clamp_rect((float(x0), float(y0), float(x1), float(y1)))
        if new_rect == self._state.rect:
            return False
        self._state.rect = new_rect
        return True

    def set_snap_step(
        self,
        snap_step: Optional[Tuple[Optional[float], Optional[float]]],
    ) -> bool:
        self._state.snap_step = _normalize_snap_step(snap_step)
        new_rect = self._clamp_rect(self._state.rect)
        if new_rect == self._state.rect:
            return False
        self._state.rect = new_rect
        return True

    def set_snap_origin(self, x: float, y: float) -> None:
        self._state.snap_origin = (float(x), float(y))

    def set_bounds(
        self,
        bounds_x: Optional[Tuple[Optional[float], Optional[float]]] = None,
        bounds_y: Optional[Tuple[Optional[float], Optional[float]]] = None,
    ) -> bool:
        self._state.bounds_x = _normalize_bounds(bounds_x)
        self._state.bounds_y = _normalize_bounds(bounds_y)
        new_rect = self._clamp_rect(self._state.rect)
        if new_rect == self._state.rect:
            return False
        self._state.rect = new_rect
        return True

    def set_movable(self, movable: bool) -> None:
        self._state.movable = bool(movable)

    # --- hit testing + drag ----------------------------------------

    def hit_test(
        self,
        x_pixel: float,
        y_pixel: float,
        *,
        data_to_pixel: Callable[[float, float], Tuple[float, float]],
        ax_rect: Optional[QRectF] = None,
    ) -> str:
        """Classify a press. Corners win over body within their slop
        window; presses outside the rectangle and outside any corner
        slop return ``HIT_NONE``."""
        if not self._state.movable:
            return HIT_NONE
        if ax_rect is not None and not _point_in_rect(
            x_pixel, y_pixel, ax_rect, slop=self._state.handle_grab_px,
        ):
            return HIT_NONE
        try:
            corners_px = self._corner_pixels(data_to_pixel)
        except Exception:
            return HIT_NONE
        slop = self._state.handle_grab_px
        for name, (cx, cy) in corners_px.items():
            if abs(x_pixel - cx) <= slop and abs(y_pixel - cy) <= slop:
                return name
        # Body hit: between the two corner pairs (in pixel space).
        xs = sorted(c[0] for c in corners_px.values())
        ys = sorted(c[1] for c in corners_px.values())
        if xs[0] <= x_pixel <= xs[-1] and ys[0] <= y_pixel <= ys[-1]:
            return HIT_BODY
        return HIT_NONE

    def begin_drag(
        self,
        x_data: float, y_data: float, hit: str,
    ) -> Dict[str, Any]:
        if hit == HIT_BODY:
            return {
                "hit": hit,
                "press_x": float(x_data),
                "press_y": float(y_data),
                "start_rect": self._state.rect,
            }
        if hit in _CORNERS:
            return {
                "hit": hit,
                "start_rect": self._state.rect,
            }
        raise ValueError(f"Cannot begin drag with hit={hit!r}")

    def update_drag(
        self,
        x_data: float, y_data: float,
        press_state: Dict[str, Any],
    ) -> bool:
        hit = press_state["hit"]
        x0, y0, x1, y1 = press_state["start_rect"]
        if hit == HIT_BODY:
            dx = float(x_data) - press_state["press_x"]
            dy = float(y_data) - press_state["press_y"]
            new = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
        else:
            # Corner drag — move just the relevant corner.
            xd = float(x_data); yd = float(y_data)
            if hit == HIT_NW:
                new = (xd, yd, x1, y1)
            elif hit == HIT_NE:
                new = (x0, yd, xd, y1)
            elif hit == HIT_SW:
                new = (xd, y0, x1, yd)
            else:  # HIT_SE
                new = (x0, y0, xd, yd)
        clamped = self._clamp_rect(new)
        if clamped == self._state.rect:
            return False
        self._state.rect = clamped
        return True

    def end_drag(
        self,
        press_state: Dict[str, Any],
    ) -> Tuple[float, float, float, float]:
        del press_state
        return self._state.rect

    # --- rendering --------------------------------------------------

    def render(
        self,
        painter: QPainter,
        ax_rect: QRectF,
        data_to_pixel: Callable[[float, float], Tuple[float, float]],
        *,
        hover: bool = False,
    ) -> None:
        try:
            corners = self._corner_pixels(data_to_pixel)
        except Exception:
            return
        xs = [c[0] for c in corners.values()]
        ys = [c[1] for c in corners.values()]
        px_l, px_r = min(xs), max(xs)
        px_t, px_b = min(ys), max(ys)
        # Cull when wholly off-screen (plus a corner-handle margin).
        margin = self._state.handle_size_px
        if (
            px_r < ax_rect.left() - margin
            or px_l > ax_rect.right() + margin
            or px_b < ax_rect.top() - margin
            or px_t > ax_rect.bottom() + margin
        ):
            return

        pen_color = QColor(
            self._state.hover_pen_color if hover else self._state.pen_color,
        )
        pen = QPen(pen_color)
        pen.setWidthF(max(self._state.pen_width, 1.0))

        brush_color = QColor(self._state.brush_color)
        brush_color.setAlpha(
            self._state.hover_brush_alpha if hover
            else self._state.brush_alpha,
        )

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(QBrush(brush_color))
        painter.drawRect(
            QRectF(px_l, px_t, px_r - px_l, px_b - px_t),
        )
        # Handles — filled squares centred on each corner.
        handle = self._state.handle_size_px
        painter.setBrush(QBrush(pen_color))
        for cx, cy in corners.values():
            painter.drawRect(
                QRectF(
                    cx - handle / 2.0, cy - handle / 2.0,
                    handle, handle,
                ),
            )
        if self._state.label:
            painter.setPen(pen_color)
            painter.drawText(
                QRectF(px_l + 4, px_t + 2, max(0.0, px_r - px_l - 8), 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                self._state.label,
            )
        painter.restore()

    # --- persistence -----------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "roi_id": self._state.roi_id,
            "rect": list(self._state.rect),
            "bounds_x": (
                list(self._state.bounds_x) if self._state.bounds_x else None
            ),
            "bounds_y": (
                list(self._state.bounds_y) if self._state.bounds_y else None
            ),
            "movable": self._state.movable,
            "snap_step": (
                list(self._state.snap_step)
                if self._state.snap_step is not None else None
            ),
            "snap_origin": list(self._state.snap_origin),
            "pen_color": self._state.pen_color,
            "pen_width": self._state.pen_width,
            "hover_pen_color": self._state.hover_pen_color,
            "brush_color": self._state.brush_color,
            "brush_alpha": self._state.brush_alpha,
            "hover_brush_alpha": self._state.hover_brush_alpha,
            "handle_size_px": self._state.handle_size_px,
            "handle_grab_px": self._state.handle_grab_px,
            "label": self._state.label,
        }

    def apply_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        if "roi_id" in state:
            self._state.roi_id = state["roi_id"]
        r = state.get("rect")
        if (
            isinstance(r, (list, tuple)) and len(r) == 4
            and all(isinstance(v, (int, float)) for v in r)
        ):
            self._state.rect = _normalize_rect(tuple(float(v) for v in r))
        if "bounds_x" in state:
            self._state.bounds_x = _normalize_bounds(state["bounds_x"])
        if "bounds_y" in state:
            self._state.bounds_y = _normalize_bounds(state["bounds_y"])
        if isinstance(state.get("movable"), bool):
            self._state.movable = state["movable"]
        if "snap_step" in state:
            self._state.snap_step = _normalize_snap_step(state["snap_step"])
        so = state.get("snap_origin")
        if (
            isinstance(so, (list, tuple)) and len(so) == 2
            and all(isinstance(v, (int, float)) for v in so)
        ):
            self._state.snap_origin = (float(so[0]), float(so[1]))
        if isinstance(state.get("pen_color"), str):
            self._state.pen_color = state["pen_color"]
        if isinstance(state.get("pen_width"), (int, float)):
            self._state.pen_width = float(state["pen_width"])
        if isinstance(state.get("hover_pen_color"), str):
            self._state.hover_pen_color = state["hover_pen_color"]
        if isinstance(state.get("brush_color"), str):
            self._state.brush_color = state["brush_color"]
        if isinstance(state.get("brush_alpha"), int):
            self._state.brush_alpha = state["brush_alpha"]
        if isinstance(state.get("hover_brush_alpha"), int):
            self._state.hover_brush_alpha = state["hover_brush_alpha"]
        if isinstance(state.get("handle_size_px"), (int, float)):
            self._state.handle_size_px = float(state["handle_size_px"])
        if isinstance(state.get("handle_grab_px"), (int, float)):
            self._state.handle_grab_px = float(state["handle_grab_px"])
        if isinstance(state.get("label"), str):
            self._state.label = state["label"]
        self._state.rect = self._clamp_rect(self._state.rect)

    # --- internals --------------------------------------------------

    def _corner_pixels(
        self,
        data_to_pixel: Callable[[float, float], Tuple[float, float]],
    ) -> Dict[str, Tuple[float, float]]:
        x0, y0, x1, y1 = self._state.rect
        return {
            HIT_NW: data_to_pixel(x0, y0),
            HIT_NE: data_to_pixel(x1, y0),
            HIT_SW: data_to_pixel(x0, y1),
            HIT_SE: data_to_pixel(x1, y1),
        }

    def _clamp_rect(
        self,
        rect: Tuple[float, float, float, float],
    ) -> Tuple[float, float, float, float]:
        x0, y0, x1, y1 = rect
        # Normalise so x0 < x1 and y0 < y1.
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        x0 = self._clamp_axis(x0, self._state.bounds_x)
        x1 = self._clamp_axis(x1, self._state.bounds_x)
        y0 = self._clamp_axis(y0, self._state.bounds_y)
        y1 = self._clamp_axis(y1, self._state.bounds_y)
        # Snap each corner independently to ``snap_step``.
        snap = self._state.snap_step
        if snap is not None:
            ox, oy = self._state.snap_origin
            sx, sy = snap
            if sx is not None and sx > 0.0:
                x0 = _snap_to(x0, ox, sx)
                x1 = _snap_to(x1, ox, sx)
            if sy is not None and sy > 0.0:
                y0 = _snap_to(y0, oy, sy)
                y1 = _snap_to(y1, oy, sy)
            # After snapping, re-normalise in case rounding crossed.
            if x0 > x1:
                x0, x1 = x1, x0
            if y0 > y1:
                y0, y1 = y1, y0
        return (x0, y0, x1, y1)

    @staticmethod
    def _clamp_axis(
        value: float,
        bounds: Optional[Tuple[Optional[float], Optional[float]]],
    ) -> float:
        if bounds is None:
            return value
        lo, hi = bounds
        if lo is not None and value < lo:
            value = lo
        if hi is not None and value > hi:
            value = hi
        return value


# ---------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------

def _normalize_rect(
    rect: Tuple[float, float, float, float],
) -> Tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in rect)
    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0
    return (x0, y0, x1, y1)


def _normalize_bounds(
    bounds: Optional[Tuple[Optional[float], Optional[float]]],
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    if bounds is None:
        return None
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        return None
    lo, hi = bounds
    lo_f = float(lo) if isinstance(lo, (int, float)) else None
    hi_f = float(hi) if isinstance(hi, (int, float)) else None
    if lo_f is None and hi_f is None:
        return None
    return (lo_f, hi_f)


def _normalize_snap_step(
    snap_step: Optional[Tuple[Optional[float], Optional[float]]],
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    if snap_step is None:
        return None
    if not isinstance(snap_step, (list, tuple)) or len(snap_step) != 2:
        return None
    sx, sy = snap_step
    sx_f = float(sx) if isinstance(sx, (int, float)) and sx else None
    sy_f = float(sy) if isinstance(sy, (int, float)) and sy else None
    if sx_f is None and sy_f is None:
        return None
    return (sx_f, sy_f)


def _snap_to(value: float, origin: float, step: float) -> float:
    """Round ``value`` to the nearest multiple of ``step`` measured
    from ``origin``."""
    n = round((value - origin) / step)
    return origin + n * step


def _point_in_rect(
    x: float, y: float, rect: QRectF, *, slop: float,
) -> bool:
    return (
        rect.left() - slop <= x <= rect.right() + slop
        and rect.top() - slop <= y <= rect.bottom() + slop
    )
