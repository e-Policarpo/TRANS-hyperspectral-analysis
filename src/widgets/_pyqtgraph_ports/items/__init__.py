"""
Interactive in-plot overlay items ported from pyqtgraph.

Each item is a pure-state object: it owns its data-space configuration
(values, bounds, swap-mode) and knows how to render itself, hit-test a
pixel-space point, and update under drag. The host canvas owns the
data <-> pixel transform and dispatches mouse events into the active
item.

Upstream sources live under ``pyqtgraph/graphicsItems/`` at commit
``d588dd3ec30915e61c8496a0fe1db21fc25e4da5`` (MIT). See the package
``LICENSE`` at ``src/widgets/_pyqtgraph_ports/LICENSE``.
"""

from .linear_region import (  # noqa: F401
    HIT_BODY,
    HIT_HANDLE_HI,
    HIT_HANDLE_LO,
    HIT_NONE,
    LinearRegionItem,
    LinearRegionState,
)

__all__ = [
    "HIT_BODY",
    "HIT_HANDLE_HI",
    "HIT_HANDLE_LO",
    "HIT_NONE",
    "LinearRegionItem",
    "LinearRegionState",
]
