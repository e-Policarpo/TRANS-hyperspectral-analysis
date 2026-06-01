"""
Shared colormap LUT cache.

Consolidates the previously-duplicated ``_get_lut`` /
``_lut`` implementations from ``qml_image_canvas`` and
``image_provider`` so there's a single cache of 256×3 ``uint8`` LUTs
used by every image-rendering site.

Also fixes a cache-poisoning bug both originals shared: when
matplotlib's ``get_cmap`` raised — say because matplotlib wasn't
installed in a slim deployment, or because the user passed a typo —
each module cached the gray-ramp fallback **under the requested
colormap name**. Once poisoned, every subsequent request for that
name returned gray for the rest of the process, even after fixing
matplotlib. We now:

1. Cache only successful builds keyed by colormap name.
2. On failure, log once at WARN level and return the gray ramp
   *without caching it under the failed name*.
3. Catch only ``ImportError`` (matplotlib missing) and
   ``ValueError`` / ``KeyError`` / ``AttributeError`` (unknown
   colormap on either matplotlib API). Everything else propagates
   so the caller sees the real bug.

The gray ramp is itself cached under the canonical name ``"gray"``
(also reachable via the aliases ``"grey"`` and ``"original"``) so a
fallback request after one failure still hits the cache for the gray
ramp request.
"""

from __future__ import annotations

import logging
from typing import Dict

import numpy as np


logger = logging.getLogger(__name__)


_LUT_CACHE: Dict[str, np.ndarray] = {}
_GRAY_ALIASES = ("gray", "grey", "original")
_WARNED_FAILURES: set[str] = set()


def get_lut(name: str) -> np.ndarray:
    """Return a cached ``(256, 3)`` ``uint8`` LUT for ``name``.

    ``"gray"`` / ``"grey"`` / ``"original"`` return a plain grayscale
    ramp. Any other name is resolved through matplotlib; on failure
    the gray ramp is returned without poisoning the cache for the
    requested name.
    """
    key = _normalize_name(name)
    if key in _LUT_CACHE:
        return _LUT_CACHE[key]
    if key in _GRAY_ALIASES:
        return _store(key, _gray_ramp())

    try:
        lut = _build_matplotlib_lut(key)
    except (ImportError, ValueError, KeyError, AttributeError) as exc:
        # Log once per offending name so a missing matplotlib doesn't
        # spam the log; subsequent calls return gray silently.
        if key not in _WARNED_FAILURES:
            _WARNED_FAILURES.add(key)
            logger.warning(
                "Colormap %r unavailable (%s); falling back to gray. "
                "Subsequent failures for the same name will be silent.",
                key, exc,
            )
        # Re-route to the gray ramp without caching under ``key`` —
        # otherwise a later fix (matplotlib installed, colormap
        # registered) would still produce gray.
        return _store("gray", _gray_ramp())
    return _store(key, lut)


def clear_cache() -> None:
    """Drop every cached LUT. Useful in tests."""
    _LUT_CACHE.clear()
    _WARNED_FAILURES.clear()


def cached_names() -> tuple[str, ...]:
    """Names currently in the cache. Exposed for diagnostics + tests."""
    return tuple(sorted(_LUT_CACHE))


def _normalize_name(name: str) -> str:
    if not name:
        return "original"
    return str(name).strip().lower()


def _gray_ramp() -> np.ndarray:
    return np.tile(np.arange(256, dtype=np.uint8)[:, None], (1, 3))


def _store(key: str, lut: np.ndarray) -> np.ndarray:
    _LUT_CACHE[key] = lut
    return lut


def _build_matplotlib_lut(name: str) -> np.ndarray:
    """Build a 256×3 LUT from a matplotlib colormap. Raises if the
    colormap isn't available — the caller turns that into the gray
    fallback."""
    import matplotlib

    try:
        cmap = matplotlib.colormaps.get_cmap(name)
    except (AttributeError, ValueError, KeyError):
        # matplotlib < 3.7 — fall back to the legacy ``cm.get_cmap``.
        from matplotlib import cm
        cmap = cm.get_cmap(name)
    samples = cmap(np.linspace(0, 1, 256))[:, :3]  # drop alpha
    return (samples * 255).astype(np.uint8)
