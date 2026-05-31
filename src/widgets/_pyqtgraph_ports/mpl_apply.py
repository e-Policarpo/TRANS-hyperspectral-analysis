"""
Bridge from :mod:`ticks` (pure functions) to a matplotlib ``Axes``.

Phase 1 keeps the matplotlib rendering substrate; the only change is
*what* ticks matplotlib draws. This helper computes major-tick values
for the current axis limits using the ported pyqtgraph algorithm and
applies them via ``Axes.set_xticks`` / ``set_yticks`` plus a
``FuncFormatter`` that runs the pyqtgraph string formatter.

Call from inside ``_renderMatplotlib`` right before ``tight_layout`` /
``canvas.draw``. When Phase 3 retires matplotlib from the interactive
render path, this module stays in service for the export-only render.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from matplotlib.ticker import FuncFormatter, FixedLocator

from .ticks import tick_strings, tick_values

if TYPE_CHECKING:
    from matplotlib.axes import Axes


def apply_pyqtgraph_ticks(
    axes: "Axes",
    *,
    x_size_px: float,
    y_size_px: float,
    log_x: bool = False,
    log_y: bool = False,
) -> None:
    """Replace ``axes``' major ticks with the pyqtgraph-ported layout.

    ``x_size_px`` / ``y_size_px`` are the axis lengths in pixels; the
    tick algorithm uses them to grow tick count sub-linearly with axis
    length. They're usually the widget's width / height.

    ``log_x`` / ``log_y`` tell the tick algorithm to switch into log
    mode (decade ticks + ``10ⁿ`` formatting). The caller is responsible
    for setting ``axes.set_xscale('log')`` separately if it wants
    matplotlib to actually plot on a log axis.
    """
    _apply_axis(axes, axis="x", size_px=x_size_px, log=log_x)
    _apply_axis(axes, axis="y", size_px=y_size_px, log=log_y)


def _apply_axis(
    axes: "Axes", *, axis: str, size_px: float, log: bool,
) -> None:
    if axis == "x":
        lo, hi = axes.get_xlim()
        mpl_axis = axes.xaxis
        setter = axes.set_xticks
    else:
        lo, hi = axes.get_ylim()
        mpl_axis = axes.yaxis
        setter = axes.set_yticks

    levels = tick_values(lo, hi, size_px, log=log)
    if not levels:
        return

    # Only the first level (major) goes through ``set_xticks`` /
    # ``set_yticks``; minor ticks are deferred to Phase 4. Empty major
    # lists are skipped so matplotlib's auto-locator stays in charge of
    # truly degenerate axes.
    major_spacing, major_values = levels[0]
    if not major_values:
        return

    setter(major_values)

    labels = tick_strings(
        major_values, scale=1.0, spacing=major_spacing, log=log,
    )

    # ``FixedLocator`` ensures matplotlib doesn't re-compute ticks
    # behind our back during ``tight_layout``.
    mpl_axis.set_major_locator(FixedLocator(major_values))

    label_lookup = dict(zip(major_values, labels))
    mpl_axis.set_major_formatter(
        FuncFormatter(lambda v, _pos: label_lookup.get(v, ""))
    )
