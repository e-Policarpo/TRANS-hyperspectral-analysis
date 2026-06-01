"""
``LinearRegionItem`` — vertical-band overlay with draggable handles.

Ported from ``pyqtgraph/graphicsItems/LinearRegionItem.py``
(commit ``d588dd3ec30915e61c8496a0fe1db21fc25e4da5``, MIT). The original
relies on the ``QGraphicsScene`` event pipeline and two internal
``InfiniteLine`` instances; this port reduces both to a single pure-
state object:

- Two ``x`` values + a swap-mode policy (``sort`` / ``block`` / ``push``
  / ``None``) — identical semantics to upstream.
- ``hit_test`` consumes a pixel ``x`` plus a ``data_to_pixel_x``
  callback, returning which sub-region of the item was hit (handle-lo,
  handle-hi, body, or nothing). Handle slop defaults to 6 px on each
  side, matching upstream's default hover slop.
- ``begin_drag`` / ``update_drag`` / ``end_drag`` consume data-space
  ``x`` values from the host canvas, which translates pixel deltas
  through its viewbox transform before calling.
- ``render`` paints the band + the two handles on a host-supplied
  ``QPainter``, clipped to the host's axes rect.
- ``get_state`` / ``apply_state`` round-trip the JSON-serialisable
  payload for project save/load.

Horizontal orientation is deliberately omitted from this first cut —
every TRANS use site (peak-fit region picker, cosmic-ray window,
baseline anchor) wants a vertical band. The constructor still accepts
``orientation="vertical"`` for forward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen


HIT_NONE = "none"
HIT_HANDLE_LO = "handle_lo"
HIT_HANDLE_HI = "handle_hi"
HIT_BODY = "body"

_VALID_SWAP_MODES = ("sort", "block", "push", None)
_HIT_TYPES = (HIT_NONE, HIT_HANDLE_LO, HIT_HANDLE_HI, HIT_BODY)


@dataclass
class LinearRegionState:
    """JSON-serialisable state for a ``LinearRegionItem``."""

    region_id: Any = 0
    values: Tuple[float, float] = (0.0, 1.0)
    bounds: Optional[Tuple[Optional[float], Optional[float]]] = None
    movable: bool = True
    swap_mode: Optional[str] = "sort"
    pen_color: str = "#5BCEFA"
    pen_width: float = 1.0
    brush_color: str = "#5BCEFA"
    brush_alpha: int = 50
    hover_brush_alpha: int = 100
    handle_grab_px: float = 6.0
    label: str = ""


class LinearRegionItem:
    """Vertical-band overlay with two draggable handles."""

    def __init__(
        self,
        region_id: Any = 0,
        *,
        values: Tuple[float, float] = (0.0, 1.0),
        bounds: Optional[Tuple[Optional[float], Optional[float]]] = None,
        movable: bool = True,
        swap_mode: Optional[str] = "sort",
        pen_color: str = "#5BCEFA",
        pen_width: float = 1.0,
        brush_color: str = "#5BCEFA",
        brush_alpha: int = 50,
        hover_brush_alpha: int = 100,
        handle_grab_px: float = 6.0,
        label: str = "",
        orientation: str = "vertical",
    ) -> None:
        if orientation != "vertical":
            raise NotImplementedError(
                "Only vertical orientation is implemented in this port.",
            )
        if swap_mode not in _VALID_SWAP_MODES:
            raise ValueError(
                f"swap_mode must be one of {_VALID_SWAP_MODES}, got {swap_mode!r}",
            )
        v0 = float(values[0]); v1 = float(values[1])
        self._state = LinearRegionState(
            region_id=region_id,
            values=(v0, v1),
            bounds=_normalize_bounds(bounds),
            movable=bool(movable),
            swap_mode=swap_mode,
            pen_color=str(pen_color),
            pen_width=float(pen_width),
            brush_color=str(brush_color),
            brush_alpha=int(brush_alpha),
            hover_brush_alpha=int(hover_brush_alpha),
            handle_grab_px=float(handle_grab_px),
            label=str(label),
        )

    # --- accessors --------------------------------------------------

    @property
    def region_id(self) -> Any:
        return self._state.region_id

    @property
    def movable(self) -> bool:
        return self._state.movable

    @property
    def label(self) -> str:
        return self._state.label

    def region(self) -> Tuple[float, float]:
        """Return ``(lo, hi)``. With ``swap_mode='sort'`` the output is
        always ascending; otherwise the raw stored order is returned."""
        v0, v1 = self._state.values
        if self._state.swap_mode == "sort":
            return (min(v0, v1), max(v0, v1))
        return (v0, v1)

    def raw_values(self) -> Tuple[float, float]:
        """The two ``x`` values in storage order — useful for tests."""
        return self._state.values

    def bounds(self) -> Optional[Tuple[Optional[float], Optional[float]]]:
        return self._state.bounds

    # --- mutators ---------------------------------------------------

    def set_region(self, lo: float, hi: float) -> bool:
        """Programmatic setter. Applies bounds + swap policy and
        returns ``True`` if the stored values changed."""
        return self._apply_with_hit(float(lo), float(hi), hit=None)

    def set_bounds(
        self,
        bounds: Optional[Tuple[Optional[float], Optional[float]]],
    ) -> bool:
        """Set clamp range. ``(None, None)`` disables. Returns ``True``
        if the current region was pulled by the new bounds."""
        self._state.bounds = _normalize_bounds(bounds)
        v0, v1 = self._state.values
        return self._apply_with_hit(v0, v1, hit=None)

    def set_movable(self, movable: bool) -> None:
        self._state.movable = bool(movable)

    def set_label(self, label: str) -> None:
        self._state.label = str(label)

    # --- hit testing + drag ----------------------------------------

    def hit_test(
        self,
        x_pixel: float,
        *,
        data_to_pixel_x: Callable[[float], float],
        ax_rect: Optional[QRectF] = None,
    ) -> str:
        """Classify a press at pixel ``x_pixel``.

        - ``HIT_HANDLE_LO`` / ``HIT_HANDLE_HI`` if within ``handle_grab_px``
          of either handle.
        - ``HIT_BODY`` if between the two handles (band fill).
        - ``HIT_NONE`` otherwise.

        ``ax_rect`` is used only to short-circuit when the press is
        clearly outside the plot area; supply it whenever you have it.
        """
        if not self._state.movable:
            return HIT_NONE
        if ax_rect is not None and not (
            ax_rect.left() - 1.0 <= x_pixel <= ax_rect.right() + 1.0
        ):
            return HIT_NONE
        lo, hi = self.region()
        try:
            px_lo = float(data_to_pixel_x(lo))
            px_hi = float(data_to_pixel_x(hi))
        except Exception:
            return HIT_NONE
        slop = self._state.handle_grab_px
        if abs(x_pixel - px_lo) <= slop:
            # Handle-lo wins ties with body.
            return HIT_HANDLE_LO
        if abs(x_pixel - px_hi) <= slop:
            return HIT_HANDLE_HI
        # Body extends between the (possibly swapped) handles. Slop
        # was already consumed by the handle checks above, so a body
        # hit only needs the point to be inside the band — overlap with
        # the handle-slop zones is fine because handles take priority.
        body_lo = min(px_lo, px_hi)
        body_hi = max(px_lo, px_hi)
        if body_lo <= x_pixel <= body_hi:
            return HIT_BODY
        return HIT_NONE

    def begin_drag(self, x_data: float, hit: str) -> Dict[str, Any]:
        """Snapshot the press state. Returns an opaque dict the host
        passes back to ``update_drag`` / ``end_drag``."""
        if hit not in _HIT_TYPES or hit == HIT_NONE:
            raise ValueError(f"Cannot begin drag with hit={hit!r}")
        return {
            "hit": hit,
            "press_x": float(x_data),
            "start_values": self._state.values,
        }

    def update_drag(
        self,
        x_data: float,
        press_state: Dict[str, Any],
    ) -> bool:
        """Translate the press into a new region. Returns ``True`` if
        the region changed."""
        hit = press_state["hit"]
        v0, v1 = press_state["start_values"]
        if hit == HIT_BODY:
            dx = float(x_data) - press_state["press_x"]
            v0 += dx
            v1 += dx
        elif hit == HIT_HANDLE_LO:
            v0 = float(x_data)
        elif hit == HIT_HANDLE_HI:
            v1 = float(x_data)
        else:
            return False
        return self._apply_with_hit(v0, v1, hit=hit)

    def end_drag(
        self,
        press_state: Dict[str, Any],
    ) -> Tuple[float, float]:
        """Return the final ``region()`` after a drag. The press state
        is discarded by the caller; this is just a convenience handle
        to let the host emit ``Finished`` signals with the same shape
        as the in-flight ``Changed`` signal."""
        del press_state
        return self.region()

    # --- rendering --------------------------------------------------

    def render(
        self,
        painter: QPainter,
        ax_rect: QRectF,
        data_to_pixel_x: Callable[[float], float],
        *,
        hover: bool = False,
    ) -> None:
        """Paint the band and the two handles, clipped to ``ax_rect``.

        ``hover`` flips the brush alpha to the configured hover value
        — the host canvas decides whether to set it (during drag, or
        when the cursor is over the item).
        """
        lo, hi = self.region()
        try:
            px_lo = float(data_to_pixel_x(lo))
            px_hi = float(data_to_pixel_x(hi))
        except Exception:
            return
        if px_lo > px_hi:
            px_lo, px_hi = px_hi, px_lo

        # Clip the band to the axes rect — handles still draw at their
        # raw positions below so a half-off-screen item shows a real
        # edge instead of vanishing entirely.
        body_lo = max(px_lo, ax_rect.left())
        body_hi = min(px_hi, ax_rect.right())
        if body_hi > body_lo:
            alpha = (
                self._state.hover_brush_alpha if hover
                else self._state.brush_alpha
            )
            brush_color = QColor(self._state.brush_color)
            brush_color.setAlpha(int(alpha))
            painter.save()
            painter.setBrush(QBrush(brush_color))
            painter.setPen(Qt.NoPen)
            painter.drawRect(
                QRectF(
                    body_lo, ax_rect.top(),
                    body_hi - body_lo, ax_rect.height(),
                ),
            )
            painter.restore()

        # Handle lines — draw both at their raw positions, in storage
        # order, so the pen colour reads consistently across swap-mode
        # changes.
        pen = QPen(QColor(self._state.pen_color))
        pen.setWidthF(max(self._state.pen_width, 1.0))
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for v in self._state.values:
            try:
                px = float(data_to_pixel_x(v))
            except Exception:
                continue
            if ax_rect.left() <= px <= ax_rect.right():
                painter.drawLine(
                    QPointF(px, ax_rect.top()),
                    QPointF(px, ax_rect.bottom()),
                )
        painter.restore()

        # Optional label — small text just inside the band's top-left
        # corner. Skipped when the band is off-screen or too narrow.
        if self._state.label and body_hi - body_lo > 16.0:
            painter.save()
            painter.setPen(QColor(self._state.pen_color))
            painter.drawText(
                QRectF(body_lo + 4, ax_rect.top() + 2, body_hi - body_lo - 8, 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                self._state.label,
            )
            painter.restore()

    # --- persistence -----------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "region_id": self._state.region_id,
            "values": [float(v) for v in self._state.values],
            "bounds": (
                list(self._state.bounds) if self._state.bounds is not None
                else None
            ),
            "movable": self._state.movable,
            "swap_mode": self._state.swap_mode,
            "pen_color": self._state.pen_color,
            "pen_width": self._state.pen_width,
            "brush_color": self._state.brush_color,
            "brush_alpha": self._state.brush_alpha,
            "hover_brush_alpha": self._state.hover_brush_alpha,
            "handle_grab_px": self._state.handle_grab_px,
            "label": self._state.label,
        }

    def apply_state(self, state: Dict[str, Any]) -> None:
        """Merge a payload back in. Unknown / bogus fields are ignored
        so older project files load cleanly (and so a partial update
        from QML — just the values — works too)."""
        if not isinstance(state, dict):
            return
        if "region_id" in state:
            self._state.region_id = state["region_id"]
        vs = state.get("values")
        if (
            isinstance(vs, (list, tuple))
            and len(vs) == 2
            and all(isinstance(v, (int, float)) for v in vs)
        ):
            self._state.values = (float(vs[0]), float(vs[1]))
        if "bounds" in state:
            self._state.bounds = _normalize_bounds(state["bounds"])
        if isinstance(state.get("movable"), bool):
            self._state.movable = state["movable"]
        sm = state.get("swap_mode")
        if sm in _VALID_SWAP_MODES:
            self._state.swap_mode = sm
        if isinstance(state.get("pen_color"), str):
            self._state.pen_color = state["pen_color"]
        if isinstance(state.get("pen_width"), (int, float)):
            self._state.pen_width = float(state["pen_width"])
        if isinstance(state.get("brush_color"), str):
            self._state.brush_color = state["brush_color"]
        if isinstance(state.get("brush_alpha"), int):
            self._state.brush_alpha = state["brush_alpha"]
        if isinstance(state.get("hover_brush_alpha"), int):
            self._state.hover_brush_alpha = state["hover_brush_alpha"]
        if isinstance(state.get("handle_grab_px"), (int, float)):
            self._state.handle_grab_px = float(state["handle_grab_px"])
        if isinstance(state.get("label"), str):
            self._state.label = state["label"]
        # Re-apply clamps under whatever bounds + swap policy is now
        # in effect.
        v0, v1 = self._state.values
        self._apply_with_hit(v0, v1, hit=None)

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

    def _apply_with_hit(
        self,
        v0: float,
        v1: float,
        *,
        hit: Optional[str],
    ) -> bool:
        v0 = self._clamp(v0)
        v1 = self._clamp(v1)
        swap = self._state.swap_mode
        if v0 > v1 and swap == "block":
            # Block: the dragged handle is held at the fixed handle.
            if hit == HIT_HANDLE_LO:
                v0 = v1
            elif hit == HIT_HANDLE_HI:
                v1 = v0
            else:
                # Programmatic (no hit) or body drag — sort silently;
                # falling through to `sort` would do the same.
                v0, v1 = v1, v0
        elif v0 > v1 and swap == "push":
            # Push: the fixed handle is shoved to follow the dragged.
            if hit == HIT_HANDLE_LO:
                v1 = v0
            elif hit == HIT_HANDLE_HI:
                v0 = v1
            else:
                v0, v1 = v1, v0
        # ``sort`` and ``None`` leave the raw values alone; ``region()``
        # sorts on read for ``sort``.
        changed = (v0, v1) != self._state.values
        self._state.values = (v0, v1)
        return changed


def _normalize_bounds(
    bounds: Optional[Tuple[Optional[float], Optional[float]]],
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """Accept ``(None, None)`` as disabled (returns ``None``); coerce
    numbers to ``float``; pass other tuples through after validation."""
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
