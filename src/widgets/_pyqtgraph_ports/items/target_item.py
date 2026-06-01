"""
``TargetItem`` — draggable point marker with an optional label.

Ported from ``pyqtgraph/graphicsItems/TargetItem.py`` (commit
``d588dd3ec30915e61c8496a0fe1db21fc25e4da5``, MIT). Trimmed down to the
two symbols TRANS needs:

- ``"crosshair"`` — a circle with a ``+`` inscribed (the upstream
  default).
- ``"circle"`` — just the circle, no crosshair.

The richer symbol library (squares, triangles, custom
``QPainterPath``s) and the ``ScatterPlotItem`` symbol-import path are
deliberately omitted; we add more shapes only when a use site needs
one. The size in pixels is constant on screen — zoom does not scale
the marker, matching upstream's ``UIGraphicsItem`` semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen


SYMBOL_CROSSHAIR = "crosshair"
SYMBOL_CIRCLE = "circle"
_VALID_SYMBOLS = (SYMBOL_CROSSHAIR, SYMBOL_CIRCLE)

HIT_NONE = "none"
HIT_TARGET = "target"


@dataclass
class TargetItemState:
    target_id: Any = 0
    position: Tuple[float, float] = (0.0, 0.0)
    bounds_x: Optional[Tuple[Optional[float], Optional[float]]] = None
    bounds_y: Optional[Tuple[Optional[float], Optional[float]]] = None
    movable: bool = True
    symbol: str = SYMBOL_CROSSHAIR
    symbol_size: float = 12.0
    pen_color: str = "#FFD700"
    pen_width: float = 1.5
    hover_pen_color: str = "#FF00FF"
    brush_color: str = "#5BCEFA"
    brush_alpha: int = 60
    hover_brush_alpha: int = 120
    label: str = ""


class TargetItem:
    """Single draggable point marker with a screen-space constant size."""

    def __init__(
        self,
        target_id: Any = 0,
        *,
        position: Tuple[float, float] = (0.0, 0.0),
        bounds_x: Optional[Tuple[Optional[float], Optional[float]]] = None,
        bounds_y: Optional[Tuple[Optional[float], Optional[float]]] = None,
        movable: bool = True,
        symbol: str = SYMBOL_CROSSHAIR,
        symbol_size: float = 12.0,
        pen_color: str = "#FFD700",
        pen_width: float = 1.5,
        hover_pen_color: str = "#FF00FF",
        brush_color: str = "#5BCEFA",
        brush_alpha: int = 60,
        hover_brush_alpha: int = 120,
        label: str = "",
    ) -> None:
        if symbol not in _VALID_SYMBOLS:
            raise ValueError(
                f"symbol must be one of {_VALID_SYMBOLS}, got {symbol!r}",
            )
        self._state = TargetItemState(
            target_id=target_id,
            position=(float(position[0]), float(position[1])),
            bounds_x=_normalize_bounds(bounds_x),
            bounds_y=_normalize_bounds(bounds_y),
            movable=bool(movable),
            symbol=symbol,
            symbol_size=float(symbol_size),
            pen_color=str(pen_color),
            pen_width=float(pen_width),
            hover_pen_color=str(hover_pen_color),
            brush_color=str(brush_color),
            brush_alpha=int(brush_alpha),
            hover_brush_alpha=int(hover_brush_alpha),
            label=str(label),
        )
        # Clamp the initial position under any bounds.
        self._state.position = self._clamp(*self._state.position)

    # --- accessors --------------------------------------------------

    @property
    def target_id(self) -> Any:
        return self._state.target_id

    @property
    def movable(self) -> bool:
        return self._state.movable

    @property
    def label(self) -> str:
        return self._state.label

    @property
    def symbol(self) -> str:
        return self._state.symbol

    def position(self) -> Tuple[float, float]:
        return self._state.position

    def bounds(self) -> Tuple[
        Optional[Tuple[Optional[float], Optional[float]]],
        Optional[Tuple[Optional[float], Optional[float]]],
    ]:
        return self._state.bounds_x, self._state.bounds_y

    # --- mutators ---------------------------------------------------

    def set_position(self, x: float, y: float) -> bool:
        clamped = self._clamp(float(x), float(y))
        if clamped == self._state.position:
            return False
        self._state.position = clamped
        return True

    def set_bounds(
        self,
        bounds_x: Optional[Tuple[Optional[float], Optional[float]]] = None,
        bounds_y: Optional[Tuple[Optional[float], Optional[float]]] = None,
    ) -> bool:
        self._state.bounds_x = _normalize_bounds(bounds_x)
        self._state.bounds_y = _normalize_bounds(bounds_y)
        new_pos = self._clamp(*self._state.position)
        if new_pos == self._state.position:
            return False
        self._state.position = new_pos
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
        """Hit if the press is within ``symbol_size / 2 + 2`` px of
        the marker centre. The extra 2 px gives a generous slop on
        small symbols without making large symbols feel imprecise."""
        if not self._state.movable:
            return HIT_NONE
        if ax_rect is not None and not _point_in_rect(
            x_pixel, y_pixel, ax_rect, slop=self._state.symbol_size,
        ):
            return HIT_NONE
        try:
            px, py = data_to_pixel(*self._state.position)
        except Exception:
            return HIT_NONE
        radius = self._state.symbol_size / 2.0 + 2.0
        if (x_pixel - px) ** 2 + (y_pixel - py) ** 2 <= radius ** 2:
            return HIT_TARGET
        return HIT_NONE

    def begin_drag(self, x_data: float, y_data: float) -> Dict[str, Any]:
        """Capture the offset from the press point to the marker
        centre. Preserved across the drag so the marker stays anchored
        to the press point's relative position to it."""
        dx = self._state.position[0] - float(x_data)
        dy = self._state.position[1] - float(y_data)
        return {"offset": (dx, dy), "start": self._state.position}

    def update_drag(
        self,
        x_data: float,
        y_data: float,
        press_state: Dict[str, Any],
    ) -> bool:
        ox, oy = press_state["offset"]
        return self.set_position(float(x_data) + ox, float(y_data) + oy)

    def end_drag(self, press_state: Dict[str, Any]) -> Tuple[float, float]:
        del press_state
        return self._state.position

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
            px, py = data_to_pixel(*self._state.position)
        except Exception:
            return
        # Clip-cull: skip rendering when the marker is wholly off-screen.
        margin = self._state.symbol_size
        if not (
            ax_rect.left() - margin <= px <= ax_rect.right() + margin
            and ax_rect.top() - margin <= py <= ax_rect.bottom() + margin
        ):
            return

        size = self._state.symbol_size
        half = size / 2.0

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
        painter.drawEllipse(QPointF(px, py), half, half)
        if self._state.symbol == SYMBOL_CROSSHAIR:
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(
                QPointF(px - half, py), QPointF(px + half, py),
            )
            painter.drawLine(
                QPointF(px, py - half), QPointF(px, py + half),
            )

        if self._state.label:
            painter.setPen(pen_color)
            label_rect = QRectF(px + half + 4, py - 8, 200, 16)
            painter.drawText(
                label_rect, Qt.AlignLeft | Qt.AlignVCenter,
                self._state.label,
            )
        painter.restore()

    # --- persistence -----------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "target_id": self._state.target_id,
            "position": [float(self._state.position[0]),
                         float(self._state.position[1])],
            "bounds_x": (
                list(self._state.bounds_x) if self._state.bounds_x else None
            ),
            "bounds_y": (
                list(self._state.bounds_y) if self._state.bounds_y else None
            ),
            "movable": self._state.movable,
            "symbol": self._state.symbol,
            "symbol_size": self._state.symbol_size,
            "pen_color": self._state.pen_color,
            "pen_width": self._state.pen_width,
            "hover_pen_color": self._state.hover_pen_color,
            "brush_color": self._state.brush_color,
            "brush_alpha": self._state.brush_alpha,
            "hover_brush_alpha": self._state.hover_brush_alpha,
            "label": self._state.label,
        }

    def apply_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        if "target_id" in state:
            self._state.target_id = state["target_id"]
        pos = state.get("position")
        if (
            isinstance(pos, (list, tuple))
            and len(pos) == 2
            and all(isinstance(v, (int, float)) for v in pos)
        ):
            self._state.position = (float(pos[0]), float(pos[1]))
        if "bounds_x" in state:
            self._state.bounds_x = _normalize_bounds(state["bounds_x"])
        if "bounds_y" in state:
            self._state.bounds_y = _normalize_bounds(state["bounds_y"])
        if isinstance(state.get("movable"), bool):
            self._state.movable = state["movable"]
        sym = state.get("symbol")
        if sym in _VALID_SYMBOLS:
            self._state.symbol = sym
        if isinstance(state.get("symbol_size"), (int, float)):
            self._state.symbol_size = float(state["symbol_size"])
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
        if isinstance(state.get("label"), str):
            self._state.label = state["label"]
        self._state.position = self._clamp(*self._state.position)

    # --- internals --------------------------------------------------

    def _clamp(self, x: float, y: float) -> Tuple[float, float]:
        return self._clamp_axis(x, self._state.bounds_x), \
               self._clamp_axis(y, self._state.bounds_y)

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
