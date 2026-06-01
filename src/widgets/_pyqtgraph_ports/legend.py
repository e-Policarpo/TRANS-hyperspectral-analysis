"""
Self-laid-out legend for the native graph renderer.

Refactor of ``pyqtgraph/graphicsItems/LegendItem.py`` — drops the
``QGraphicsScene`` plumbing (parent-item anchors, scene events,
``GraphicsWidget`` mixins) and keeps the layout algorithm: rows of
``[pen sample | label]``, anchored relative to the plot's axes rect
with a pixel offset, with a frame.

The renderer drives this class via three methods:

- :meth:`compute_geometry` — given the axes rect and current font
  metrics, lay out the rows and return the legend's pixel rect.
- :meth:`render` — paint the frame, pen samples, eye toggles, and
  labels.
- :meth:`hit_test` — classify a pixel under the cursor as either
  the body (drag-to-move), an eye toggle (click to hide/show that
  curve), or outside the legend.

State (anchor, offset, hidden curve IDs) is plain attributes so it
serialises trivially through ``get_state`` / ``apply_state``.

Upstream: https://github.com/pyqtgraph/pyqtgraph @ d588dd3
Originally: pyqtgraph, MIT-licensed (see ``LICENSE`` in this package).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen,
)


# Anchor names map to ``(parent corner, item corner)`` pairs — the
# legend's anchored corner gets aligned to the parent's matching
# corner, then offset by ``offset_px``. Matches pyqtgraph's anchor
# convention.
ANCHOR_TOP_LEFT = "top-left"
ANCHOR_TOP_RIGHT = "top-right"
ANCHOR_BOTTOM_LEFT = "bottom-left"
ANCHOR_BOTTOM_RIGHT = "bottom-right"
VALID_ANCHORS = (
    ANCHOR_TOP_LEFT, ANCHOR_TOP_RIGHT,
    ANCHOR_BOTTOM_LEFT, ANCHOR_BOTTOM_RIGHT,
)


@dataclass(frozen=True)
class LegendEntry:
    """One row in the legend. Built fresh per render from the canvas's
    curve state — the legend doesn't keep references to ``CurveData``.
    """
    curve_id: int
    label: str
    color: str          # CSS-style colour string
    linewidth: float
    linestyle: str      # "-", "--", ":", "-." (matplotlib-style)


# Geometry constants — keep small enough that the legend doesn't
# crowd typical 800×600 plots but big enough to be readable.
_PAD_X = 8.0
_PAD_Y = 6.0
_SAMPLE_W = 24.0
_SAMPLE_GAP = 6.0
_EYE_GAP = 6.0
_EYE_SIZE = 10.0
_ROW_GAP = 2.0


@dataclass
class LegendGeometry:
    """Cached pixel-space layout produced by :meth:`LegendBox.compute_geometry`.

    Row rects are in *widget* coords (i.e. already accounting for
    anchor + offset) and ordered to match :attr:`entries`. The
    ``eye_rects`` list parallel-indexes to ``entries`` and gives the
    click region for the per-curve visibility toggle.
    """
    bounding_rect: QRectF
    row_rects: List[QRectF]
    eye_rects: List[QRectF]
    sample_rects: List[QRectF]
    label_rects: List[QRectF]
    entries: List[LegendEntry]


# Result tags from :meth:`hit_test`.
HIT_NONE = "none"
HIT_BODY = "body"      # drag-to-move region
HIT_EYE = "eye"        # per-curve visibility toggle


class LegendBox:
    """Drag-anchored legend with per-row eye toggles.

    The legend doesn't own curve data — the canvas builds a fresh list
    of :class:`LegendEntry` instances each render. The legend's own
    state is just position (anchor + offset) and the set of hidden
    curve IDs, which is small enough to round-trip through the
    project file.
    """

    def __init__(
        self,
        *,
        anchor: str = ANCHOR_TOP_RIGHT,
        offset_px: Tuple[float, float] = (10.0, 10.0),
        hidden_curves: Optional[Iterable[int]] = None,
        font_size: int = 9,
    ) -> None:
        self._anchor: str = ANCHOR_TOP_RIGHT
        self._offset_px: Tuple[float, float] = (10.0, 10.0)
        self._hidden_curves: Set[int] = set()
        self._font_size: int = int(font_size)
        # Cached geometry — None until first render or compute call.
        self._geometry: Optional[LegendGeometry] = None
        self.set_anchor(anchor)
        self.set_offset(*offset_px)
        if hidden_curves is not None:
            self._hidden_curves = {int(c) for c in hidden_curves}

    # --- public state accessors -----------------------------------

    def anchor(self) -> str:
        return self._anchor

    def set_anchor(self, anchor: str) -> None:
        if anchor not in VALID_ANCHORS:
            raise ValueError(
                f"unknown legend anchor {anchor!r}; "
                f"expected one of {VALID_ANCHORS}"
            )
        self._anchor = anchor

    def offset(self) -> Tuple[float, float]:
        return self._offset_px

    def set_offset(self, dx: float, dy: float) -> None:
        self._offset_px = (float(dx), float(dy))

    def is_curve_hidden(self, curve_id: int) -> bool:
        return int(curve_id) in self._hidden_curves

    def set_curve_hidden(self, curve_id: int, hidden: bool) -> None:
        cid = int(curve_id)
        if hidden:
            self._hidden_curves.add(cid)
        else:
            self._hidden_curves.discard(cid)

    def hidden_curves(self) -> List[int]:
        return sorted(self._hidden_curves)

    def set_hidden_curves(self, curve_ids: Iterable[int]) -> None:
        self._hidden_curves = {int(c) for c in curve_ids}

    def get_state(self) -> dict:
        """Serialisable snapshot for the project file."""
        return {
            "anchor": self._anchor,
            "offset_px": list(self._offset_px),
            "hidden_curves": self.hidden_curves(),
        }

    def apply_state(self, state: dict) -> None:
        """Reload from a :meth:`get_state` snapshot. Unknown fields
        and missing keys fall back to the constructor defaults so
        older project files load without complaint."""
        if not isinstance(state, dict):
            return
        anchor = state.get("anchor")
        if isinstance(anchor, str) and anchor in VALID_ANCHORS:
            self._anchor = anchor
        offset = state.get("offset_px")
        if (
            isinstance(offset, (list, tuple))
            and len(offset) == 2
        ):
            try:
                self._offset_px = (float(offset[0]), float(offset[1]))
            except (TypeError, ValueError):
                pass
        hidden = state.get("hidden_curves")
        if isinstance(hidden, (list, tuple)):
            try:
                self._hidden_curves = {int(c) for c in hidden}
            except (TypeError, ValueError):
                pass

    # --- geometry --------------------------------------------------

    def compute_geometry(
        self,
        font: QFont,
        ax_rect: QRectF,
        entries: List[LegendEntry],
    ) -> Optional[LegendGeometry]:
        """Lay out the legend inside (or near) ``ax_rect`` and cache
        the result on ``self``. Returns the geometry (or ``None`` if
        ``entries`` is empty)."""
        if not entries:
            self._geometry = None
            return None

        fm = QFontMetricsF(font)
        row_h = max(fm.height(), _EYE_SIZE + 2.0)
        max_label_w = max(fm.horizontalAdvance(e.label) for e in entries)
        body_w = (
            _PAD_X * 2 + _SAMPLE_W + _SAMPLE_GAP
            + max_label_w + _EYE_GAP + _EYE_SIZE
        )
        body_h = _PAD_Y * 2 + row_h * len(entries) + _ROW_GAP * (
            max(0, len(entries) - 1)
        )

        top_left = self._anchor_top_left(ax_rect, body_w, body_h)
        bounding = QRectF(top_left, top_left + QPointF(body_w, body_h))

        sample_rects: List[QRectF] = []
        label_rects: List[QRectF] = []
        eye_rects: List[QRectF] = []
        row_rects: List[QRectF] = []
        cursor_y = bounding.top() + _PAD_Y
        for entry in entries:
            row = QRectF(
                bounding.left(), cursor_y, body_w, row_h,
            )
            row_rects.append(row)

            sample_x = bounding.left() + _PAD_X
            sample_rect = QRectF(
                sample_x, cursor_y + row_h / 2 - 1.0,
                _SAMPLE_W, 2.0,
            )
            sample_rects.append(sample_rect)

            label_x = sample_x + _SAMPLE_W + _SAMPLE_GAP
            label_rect = QRectF(
                label_x, cursor_y,
                max_label_w, row_h,
            )
            label_rects.append(label_rect)

            eye_x = label_x + max_label_w + _EYE_GAP
            eye_rect = QRectF(
                eye_x, cursor_y + row_h / 2 - _EYE_SIZE / 2,
                _EYE_SIZE, _EYE_SIZE,
            )
            eye_rects.append(eye_rect)

            cursor_y += row_h + _ROW_GAP

        geom = LegendGeometry(
            bounding_rect=bounding,
            row_rects=row_rects,
            eye_rects=eye_rects,
            sample_rects=sample_rects,
            label_rects=label_rects,
            entries=list(entries),
        )
        self._geometry = geom
        return geom

    def _anchor_top_left(
        self,
        ax_rect: QRectF,
        body_w: float,
        body_h: float,
    ) -> QPointF:
        """Position the legend's top-left so its anchored corner is
        at the matching corner of ``ax_rect`` shifted by ``offset_px``.
        """
        dx, dy = self._offset_px
        if self._anchor == ANCHOR_TOP_LEFT:
            return QPointF(ax_rect.left() + dx, ax_rect.top() + dy)
        if self._anchor == ANCHOR_TOP_RIGHT:
            return QPointF(
                ax_rect.right() - body_w - dx,
                ax_rect.top() + dy,
            )
        if self._anchor == ANCHOR_BOTTOM_LEFT:
            return QPointF(
                ax_rect.left() + dx,
                ax_rect.bottom() - body_h - dy,
            )
        # ANCHOR_BOTTOM_RIGHT
        return QPointF(
            ax_rect.right() - body_w - dx,
            ax_rect.bottom() - body_h - dy,
        )

    def geometry(self) -> Optional[LegendGeometry]:
        """Last result of :meth:`compute_geometry`. ``None`` before
        first render."""
        return self._geometry

    # --- drag handling -------------------------------------------

    def shift_offset(
        self,
        dx_px: float, dy_px: float,
        ax_rect: QRectF,
    ) -> None:
        """Move the legend by ``(dx, dy)`` pixels.

        The shift direction is anchor-dependent: dragging right
        increases ``offset_px[0]`` for a right-anchored legend but
        decreases it for a left-anchored one (closer to its anchor =
        smaller offset). ``ax_rect`` is the current axes rect so we
        can keep the legend at least partly inside.
        """
        sign_x = 1.0 if self._anchor in (
            ANCHOR_TOP_LEFT, ANCHOR_BOTTOM_LEFT,
        ) else -1.0
        sign_y = 1.0 if self._anchor in (
            ANCHOR_TOP_LEFT, ANCHOR_TOP_RIGHT,
        ) else -1.0
        new_dx = self._offset_px[0] + sign_x * dx_px
        new_dy = self._offset_px[1] + sign_y * dy_px
        # Soft clamp: don't let the user drag the legend so far that
        # it disappears off the plot.
        max_dx = max(0.0, ax_rect.width() - _PAD_X * 2)
        max_dy = max(0.0, ax_rect.height() - _PAD_Y * 2)
        new_dx = min(max(-_PAD_X, new_dx), max_dx)
        new_dy = min(max(-_PAD_Y, new_dy), max_dy)
        self._offset_px = (float(new_dx), float(new_dy))

    # --- hit testing ---------------------------------------------

    def hit_test(self, point: QPointF) -> Tuple[str, Optional[int]]:
        """Classify ``point`` under the cursor.

        Returns ``("none", None)`` when the click is outside the
        legend body, ``("eye", curve_id)`` when on a per-row visibility
        toggle, or ``("body", None)`` when on the drag region.
        """
        geom = self._geometry
        if geom is None or not geom.bounding_rect.contains(point):
            return HIT_NONE, None
        # Eye toggles take priority over the drag body.
        for entry, eye in zip(geom.entries, geom.eye_rects):
            if eye.contains(point):
                return HIT_EYE, int(entry.curve_id)
        return HIT_BODY, None

    # --- rendering ------------------------------------------------

    # Dark-theme defaults; the canvas overrides via :meth:`render`'s
    # optional colour kwargs to match its own palette.
    DEFAULT_BG = QColor(42, 42, 42, 230)
    DEFAULT_BORDER = QColor(68, 68, 68)
    DEFAULT_TEXT = QColor(204, 204, 204)
    EYE_OPEN = QColor(155, 79, 150)        # accent — "shown"
    EYE_CLOSED = QColor(102, 102, 102)     # muted — "hidden"

    def render(
        self,
        painter: QPainter,
        font: QFont,
        ax_rect: QRectF,
        entries: List[LegendEntry],
        *,
        bg_color: QColor = DEFAULT_BG,
        border_color: QColor = DEFAULT_BORDER,
        text_color: QColor = DEFAULT_TEXT,
    ) -> Optional[LegendGeometry]:
        """Lay out + paint in one call. Returns the cached geometry
        (or ``None`` when there's nothing to draw)."""
        geom = self.compute_geometry(font, ax_rect, entries)
        if geom is None:
            return None

        painter.save()
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setFont(font)

            # Frame.
            painter.setPen(QPen(border_color))
            painter.setBrush(QBrush(bg_color))
            painter.drawRoundedRect(geom.bounding_rect, 3.0, 3.0)

            fm = QFontMetricsF(font)
            ascent = fm.ascent()
            for entry, sample, label, eye in zip(
                geom.entries, geom.sample_rects,
                geom.label_rects, geom.eye_rects,
            ):
                hidden = entry.curve_id in self._hidden_curves

                # Pen sample line. Lighter when the curve is hidden.
                pen = QPen(QColor(entry.color))
                pen.setWidthF(float(entry.linewidth))
                pen.setStyle(self._pen_style(entry.linestyle))
                if hidden:
                    c = QColor(entry.color)
                    c.setAlpha(80)
                    pen.setColor(c)
                painter.setPen(pen)
                y_centre = sample.center().y()
                painter.drawLine(
                    QPointF(sample.left(), y_centre),
                    QPointF(sample.right(), y_centre),
                )

                # Label.
                lbl_color = QColor(text_color)
                if hidden:
                    lbl_color.setAlpha(110)
                painter.setPen(lbl_color)
                painter.drawText(
                    QPointF(label.left(), label.top() + ascent),
                    entry.label,
                )

                # Eye toggle — filled dot when shown, hollow when
                # hidden. Cheap, reads well at 10 px.
                eye_color = self.EYE_CLOSED if hidden else self.EYE_OPEN
                eye_pen = QPen(eye_color)
                eye_pen.setWidthF(1.4)
                painter.setPen(eye_pen)
                if hidden:
                    painter.setBrush(QBrush(Qt.transparent))
                else:
                    painter.setBrush(QBrush(eye_color))
                painter.drawEllipse(eye)
        finally:
            painter.restore()

        return geom

    @staticmethod
    def _pen_style(linestyle: str) -> Qt.PenStyle:
        ls = (linestyle or "-").strip().lower()
        if ls in ("--", "dashed"):
            return Qt.DashLine
        if ls in (":", "dotted"):
            return Qt.DotLine
        if ls in ("-.", "dashdot"):
            return Qt.DashDotLine
        return Qt.SolidLine
