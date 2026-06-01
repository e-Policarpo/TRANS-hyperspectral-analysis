"""
``InfiniteLine`` — a single draggable vertical or horizontal cursor.

Ported from ``pyqtgraph/graphicsItems/InfiniteLine.py`` (commit
``d588dd3ec30915e61c8496a0fe1db21fc25e4da5``, MIT). Mirrors the same
pure-state shape as ``LinearRegionItem`` — the host canvas owns the
data <-> pixel transform and dispatches mouse events into
``hit_test`` / ``begin_drag`` / ``update_drag`` / ``end_drag``.

Constraints relative to upstream:

- Only the two orthogonal angles (``90`` = vertical, ``0`` = horizontal)
  are supported. Upstream also accepts arbitrary angles but
  pyqtgraph's bounds semantics only work on the orthogonal cases
  anyway; the diagonal case is unused in TRANS.
- The optional ``InfLineLabel`` and the ``addMarker`` API are
  deliberately omitted. A flat in-line ``label`` string is supported
  and rendered as small text at the top (vertical) or right
  (horizontal) end of the line, matching what TRANS's spectral
  cursors and data-reader use today.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen


ORIENT_VERTICAL = "vertical"
ORIENT_HORIZONTAL = "horizontal"

HIT_NONE = "none"
HIT_LINE = "line"


@dataclass
class InfiniteLineState:
    """JSON-serialisable state."""

    line_id: Any = 0
    orientation: str = ORIENT_VERTICAL
    value: float = 0.0
    bounds: Optional[Tuple[Optional[float], Optional[float]]] = None
    movable: bool = True
    pen_color: str = "#FFD700"
    pen_width: float = 1.0
    hover_pen_color: str = "#FF6B6B"
    handle_grab_px: float = 6.0
    label: str = ""


class InfiniteLine:
    """A single draggable vertical or horizontal line at a fixed
    data-coordinate value."""

    def __init__(
        self,
        line_id: Any = 0,
        *,
        orientation: str = ORIENT_VERTICAL,
        value: float = 0.0,
        bounds: Optional[Tuple[Optional[float], Optional[float]]] = None,
        movable: bool = True,
        pen_color: str = "#FFD700",
        pen_width: float = 1.0,
        hover_pen_color: str = "#FF6B6B",
        handle_grab_px: float = 6.0,
        label: str = "",
    ) -> None:
        if orientation not in (ORIENT_VERTICAL, ORIENT_HORIZONTAL):
            raise ValueError(
                f"orientation must be {ORIENT_VERTICAL!r} or "
                f"{ORIENT_HORIZONTAL!r}, got {orientation!r}",
            )
        self._state = InfiniteLineState(
            line_id=line_id,
            orientation=orientation,
            value=float(value),
            bounds=_normalize_bounds(bounds),
            movable=bool(movable),
            pen_color=str(pen_color),
            pen_width=float(pen_width),
            hover_pen_color=str(hover_pen_color),
            handle_grab_px=float(handle_grab_px),
            label=str(label),
        )
        # Re-clamp the initial value under bounds.
        self._state.value = self._clamp(self._state.value)

    # --- accessors --------------------------------------------------

    @property
    def line_id(self) -> Any:
        return self._state.line_id

    @property
    def orientation(self) -> str:
        return self._state.orientation

    @property
    def movable(self) -> bool:
        return self._state.movable

    @property
    def label(self) -> str:
        return self._state.label

    def value(self) -> float:
        return self._state.value

    def bounds(self) -> Optional[Tuple[Optional[float], Optional[float]]]:
        return self._state.bounds

    # --- mutators ---------------------------------------------------

    def set_value(self, v: float) -> bool:
        """Programmatic setter. Returns ``True`` if the value changed."""
        clamped = self._clamp(float(v))
        if clamped == self._state.value:
            return False
        self._state.value = clamped
        return True

    def set_bounds(
        self,
        bounds: Optional[Tuple[Optional[float], Optional[float]]],
    ) -> bool:
        self._state.bounds = _normalize_bounds(bounds)
        new_val = self._clamp(self._state.value)
        if new_val == self._state.value:
            return False
        self._state.value = new_val
        return True

    def set_movable(self, movable: bool) -> None:
        self._state.movable = bool(movable)

    def set_label(self, label: str) -> None:
        self._state.label = str(label)

    # --- hit testing + drag ----------------------------------------

    def hit_test(
        self,
        x_pixel: float,
        y_pixel: float,
        *,
        data_to_pixel: Callable[[float, float], Tuple[float, float]],
        ax_rect: Optional[QRectF] = None,
    ) -> str:
        """Classify a press at the given pixel position.

        Returns ``HIT_LINE`` if the press is within ``handle_grab_px``
        of the line, ``HIT_NONE`` otherwise.
        """
        if not self._state.movable:
            return HIT_NONE
        if ax_rect is not None and not _point_in_rect(
            x_pixel, y_pixel, ax_rect, slop=self._state.handle_grab_px,
        ):
            return HIT_NONE
        try:
            # The y-anchor for vertical lines (and x-anchor for
            # horizontal lines) doesn't matter — the transform is
            # affine, so we feed a dummy.
            px, py = data_to_pixel(
                self._state.value if self._state.orientation == ORIENT_VERTICAL else 0.0,
                self._state.value if self._state.orientation == ORIENT_HORIZONTAL else 0.0,
            )
        except Exception:
            return HIT_NONE
        slop = self._state.handle_grab_px
        if self._state.orientation == ORIENT_VERTICAL:
            if abs(x_pixel - px) <= slop:
                return HIT_LINE
        else:
            if abs(y_pixel - py) <= slop:
                return HIT_LINE
        return HIT_NONE

    def begin_drag(self, x_data: float, y_data: float) -> Dict[str, Any]:
        """Snapshot the press state.

        The data-coordinate the user pressed at is captured so a body
        drag preserves the cursor offset from the line (matches
        pyqtgraph's ``cursorOffset`` semantics)."""
        if self._state.orientation == ORIENT_VERTICAL:
            offset = self._state.value - float(x_data)
        else:
            offset = self._state.value - float(y_data)
        return {
            "offset": offset,
            "start_value": self._state.value,
        }

    def update_drag(
        self,
        x_data: float,
        y_data: float,
        press_state: Dict[str, Any],
    ) -> bool:
        """Compute the new line value from the current cursor position
        and the press offset. Returns ``True`` if the value changed."""
        if self._state.orientation == ORIENT_VERTICAL:
            new_value = float(x_data) + press_state["offset"]
        else:
            new_value = float(y_data) + press_state["offset"]
        return self.set_value(new_value)

    def end_drag(self, press_state: Dict[str, Any]) -> float:
        """Return the final value after a drag."""
        del press_state
        return self._state.value

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
            if self._state.orientation == ORIENT_VERTICAL:
                px, _ = data_to_pixel(self._state.value, 0.0)
                if not (ax_rect.left() <= px <= ax_rect.right()):
                    return
                p0 = QPointF(px, ax_rect.top())
                p1 = QPointF(px, ax_rect.bottom())
            else:
                _, py = data_to_pixel(0.0, self._state.value)
                if not (ax_rect.top() <= py <= ax_rect.bottom()):
                    return
                p0 = QPointF(ax_rect.left(), py)
                p1 = QPointF(ax_rect.right(), py)
        except Exception:
            return

        color = QColor(
            self._state.hover_pen_color if hover else self._state.pen_color,
        )
        pen = QPen(color)
        pen.setWidthF(max(self._state.pen_width, 1.0))
        painter.save()
        painter.setPen(pen)
        painter.drawLine(p0, p1)

        if self._state.label:
            painter.setPen(color)
            if self._state.orientation == ORIENT_VERTICAL:
                painter.drawText(
                    QRectF(p0.x() + 4, ax_rect.top() + 2, 80, 14),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    self._state.label,
                )
            else:
                painter.drawText(
                    QRectF(ax_rect.right() - 84, p0.y() - 14, 80, 14),
                    Qt.AlignRight | Qt.AlignVCenter,
                    self._state.label,
                )
        painter.restore()

    # --- persistence -----------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "line_id": self._state.line_id,
            "orientation": self._state.orientation,
            "value": float(self._state.value),
            "bounds": (
                list(self._state.bounds) if self._state.bounds is not None
                else None
            ),
            "movable": self._state.movable,
            "pen_color": self._state.pen_color,
            "pen_width": self._state.pen_width,
            "hover_pen_color": self._state.hover_pen_color,
            "handle_grab_px": self._state.handle_grab_px,
            "label": self._state.label,
        }

    def apply_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        if "line_id" in state:
            self._state.line_id = state["line_id"]
        ori = state.get("orientation")
        if ori in (ORIENT_VERTICAL, ORIENT_HORIZONTAL):
            self._state.orientation = ori
        if isinstance(state.get("value"), (int, float)):
            self._state.value = float(state["value"])
        if "bounds" in state:
            self._state.bounds = _normalize_bounds(state["bounds"])
        if isinstance(state.get("movable"), bool):
            self._state.movable = state["movable"]
        if isinstance(state.get("pen_color"), str):
            self._state.pen_color = state["pen_color"]
        if isinstance(state.get("pen_width"), (int, float)):
            self._state.pen_width = float(state["pen_width"])
        if isinstance(state.get("hover_pen_color"), str):
            self._state.hover_pen_color = state["hover_pen_color"]
        if isinstance(state.get("handle_grab_px"), (int, float)):
            self._state.handle_grab_px = float(state["handle_grab_px"])
        if isinstance(state.get("label"), str):
            self._state.label = state["label"]
        self._state.value = self._clamp(self._state.value)

    # --- internals --------------------------------------------------

    def _clamp(self, value: float) -> float:
        if self._state.bounds is None:
            return value
        lo, hi = self._state.bounds
        if lo is not None and value < lo:
            value = lo
        if hi is not None and value > hi:
            value = hi
        return value


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


def _point_in_rect(
    x: float, y: float, rect: QRectF, *, slop: float,
) -> bool:
    return (
        rect.left() - slop <= x <= rect.right() + slop
        and rect.top() - slop <= y <= rect.bottom() + slop
    )
