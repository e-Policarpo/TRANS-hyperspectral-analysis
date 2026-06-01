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

from .infinite_line import (  # noqa: F401
    HIT_LINE,
    HIT_NONE as INFLINE_HIT_NONE,
    InfiniteLine,
    InfiniteLineState,
    ORIENT_HORIZONTAL,
    ORIENT_VERTICAL,
)
from .linear_region import (  # noqa: F401
    HIT_BODY,
    HIT_HANDLE_HI,
    HIT_HANDLE_LO,
    HIT_NONE,
    LinearRegionItem,
    LinearRegionState,
)
from .target_item import (  # noqa: F401
    HIT_TARGET,
    HIT_NONE as TARGET_HIT_NONE,
    SYMBOL_CIRCLE,
    SYMBOL_CROSSHAIR,
    TargetItem,
    TargetItemState,
)

__all__ = [
    "HIT_BODY",
    "HIT_HANDLE_HI",
    "HIT_HANDLE_LO",
    "HIT_LINE",
    "HIT_NONE",
    "HIT_TARGET",
    "INFLINE_HIT_NONE",
    "InfiniteLine",
    "InfiniteLineState",
    "LinearRegionItem",
    "LinearRegionState",
    "ORIENT_HORIZONTAL",
    "ORIENT_VERTICAL",
    "SYMBOL_CIRCLE",
    "SYMBOL_CROSSHAIR",
    "TARGET_HIT_NONE",
    "TargetItem",
    "TargetItemState",
]
