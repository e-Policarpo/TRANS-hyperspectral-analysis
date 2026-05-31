"""
Tick-value and tick-string computation.

Pure-function refactor of three methods from pyqtgraph's
``AxisItem`` (`graphicsItems/AxisItem.py`):

- ``AxisItem.tickValues``  → :func:`tick_values`
- ``AxisItem.tickSpacing`` → :func:`tick_spacing`
- ``AxisItem.tickStrings`` → :func:`tick_strings`
- ``AxisItem.logTickValues``  → :func:`log_tick_values` (called from
  :func:`tick_values` when ``log=True``)
- ``AxisItem.logTickStrings`` → :func:`log_tick_strings` (called from
  :func:`tick_strings` when ``log=True``)

The refactor removes the ``self`` baggage (``self.scale``,
``self.logMode``, ``self.style['maxTickLevel']``, ``self._tickSpacing``,
``self._tickDensity``) and exposes the same knobs as keyword arguments
with the upstream defaults (``scale=1.0``, ``log=False``,
``max_tick_level=2``, ``tick_density=1.0``, ``explicit_spacing=None``).
No Qt imports — call sites build their own tick lines / labels from the
returned values.

Upstream: https://github.com/pyqtgraph/pyqtgraph @ d588dd3
Originally: pyqtgraph, MIT-licensed (see ``LICENSE`` in this package).
"""

from __future__ import annotations

from math import ceil, floor, frexp, log10, sqrt
from typing import List, Optional, Tuple

import numpy as np


TickLevel = Tuple[float, List[float]]
SpacingLevel = Tuple[float, float]

# Upstream uses 300 px as the "comfortable" axis size in
# ``tickSpacing`` to grow tick count sub-linearly with axis length.
_REF_SIZE_PX = 300.0
# Below ``2.25`` the algorithm can't guarantee two visible labels.
_MIN_TICK_INTERVALS = 2.25
# 1 / log2(10) — used in the IEEE-754 mantissa/exponent shortcut.
_INV_LOG2_OF_10 = 1.0 / 3.32192809488736


def tick_spacing(
    min_val: float,
    max_val: float,
    size: float,
    *,
    tick_density: float = 1.0,
    max_tick_level: int = 2,
    explicit_spacing: Optional[List[SpacingLevel]] = None,
) -> List[SpacingLevel]:
    """Return ``[(major_spacing, offset), (minor_spacing, offset), ...]``.

    Mirrors pyqtgraph ``AxisItem.tickSpacing``. ``size`` is the axis
    length in pixels; longer axes grow more tick levels.

    ``explicit_spacing`` short-circuits the algorithm if the caller has
    its own preferred levels (pyqtgraph exposes this as
    ``setTickSpacing``); pass ``None`` for the default behaviour.
    """
    if explicit_spacing is not None:
        return list(explicit_spacing)

    dif = abs(max_val - min_val)
    if dif == 0:
        return []

    # Sub-linear growth of tick count with axis length.
    min_number_of_intervals = max(
        _MIN_TICK_INTERVALS,
        _MIN_TICK_INTERVALS * tick_density * sqrt(size / _REF_SIZE_PX),
    )
    major_max_spacing = dif / min_number_of_intervals

    # Pull the IEEE-754 binary exponent out of major_max_spacing to
    # cheaply estimate the largest power of ten below it. Subtract 1
    # because the IEEE exponent is the ceiling of the true exponent,
    # then subtract another so we work with integer scale factors >= 5.
    _mantissa, exp2 = frexp(major_max_spacing)
    p10unit = 10.0 ** (floor((exp2 - 1) * _INV_LOG2_OF_10) - 1)

    # The mantissa shortcut can underestimate by one power of ten when
    # major_max_spacing is just above a threshold.
    if 100.0 * p10unit <= major_max_spacing:
        major_scale_factor = 10
        p10unit *= 10.0
    else:
        for major_scale_factor in (50, 20, 10):
            if major_scale_factor * p10unit <= major_max_spacing:
                break

    major_interval = major_scale_factor * p10unit
    levels: List[SpacingLevel] = [(major_interval, 0.0)]

    if max_tick_level >= 1:
        # No more than one minor tick per two pixels.
        minor_min_spacing = 2.0 * dif / size if size > 0 else dif
        trials = (5, 10) if major_scale_factor == 10 else (10, 20, 50)
        for minor_scale_factor in trials:
            minor_interval = minor_scale_factor * p10unit
            if minor_interval >= minor_min_spacing:
                break
        levels.append((minor_interval, 0.0))

    if max_tick_level >= 2:
        if major_scale_factor == 10:
            trials = (1, 2, 5, 10)
        elif major_scale_factor == 20:
            trials = (2, 5, 10, 20)
        elif major_scale_factor == 50:
            trials = (5, 10, 50)
        else:
            trials = ()
            extra_interval = minor_interval

        for extra_scale_factor in trials:
            extra_interval = extra_scale_factor * p10unit
            if extra_interval >= minor_min_spacing or extra_interval == minor_interval:
                break

        if extra_interval < minor_interval:
            levels.append((extra_interval, 0.0))

    return levels


def tick_values(
    min_val: float,
    max_val: float,
    size: float,
    *,
    scale: float = 1.0,
    log: bool = False,
    tick_density: float = 1.0,
    max_tick_level: int = 2,
    explicit_spacing: Optional[List[SpacingLevel]] = None,
) -> List[TickLevel]:
    """Return ``[(spacing, [values...]), ...]`` per tick level.

    Mirrors pyqtgraph ``AxisItem.tickValues``. When ``log=True`` the
    upstream ``logTickValues`` post-process runs (decade ticks at
    integer log values, plus the 2,3,...,9 minor marks per decade when
    the linear algorithm doesn't produce enough levels).
    """
    if min_val > max_val:
        min_val, max_val = max_val, min_val

    min_val *= scale
    max_val *= scale

    ticks: List[TickLevel] = []
    levels = tick_spacing(
        min_val, max_val, size,
        tick_density=tick_density,
        max_tick_level=max_tick_level,
        explicit_spacing=explicit_spacing,
    )
    all_values = np.array([], dtype=np.float64)

    for spacing, offset in levels:
        start = (ceil((min_val - offset) / spacing) * spacing) + offset
        num = int((max_val - start) / spacing) + 1
        values = (np.arange(num) * spacing + start) / scale

        # Drop any tick that's within spacing/100 of one we've already
        # emitted at a coarser level — those are the major ticks
        # "re-found" by the minor-spacing algorithm.
        if all_values.size:
            close = np.any(
                np.isclose(
                    all_values,
                    values[:, np.newaxis],
                    rtol=0,
                    atol=spacing / scale * 0.01,
                ),
                axis=-1,
            )
            values = values[~close]
        all_values = np.concatenate([all_values, values])
        ticks.append((spacing / scale, values.tolist()))

    if log:
        return log_tick_values(min_val, max_val, size, ticks)
    return ticks


def log_tick_values(
    min_val: float,
    max_val: float,
    size: float,
    std_ticks: List[TickLevel],
) -> List[TickLevel]:
    """Log-mode post-processing of :func:`tick_values`.

    Keeps the linear levels whose spacing is >= 1 (those are decades),
    then synthesises a single minor level at the 2,3,...,9 marks per
    decade when fewer than three levels survived.
    """
    ticks: List[TickLevel] = [
        (spacing, t) for spacing, t in std_ticks if spacing >= 1.0
    ]
    if len(ticks) < 3:
        v1 = int(floor(min_val))
        v2 = int(ceil(max_val))
        minor: List[float] = []
        for v in range(v1, v2):
            minor.extend((v + np.log10(np.arange(1, 10))).tolist())
        minor = [x for x in minor if min_val < x < max_val]
        ticks.append((float("nan"), minor))  # sentinel: undefined spacing
    return ticks


def tick_strings(
    values: List[float],
    scale: float,
    spacing: float,
    *,
    log: bool = False,
) -> List[str]:
    """Return the label string for each tick value.

    Mirrors pyqtgraph ``AxisItem.tickStrings``.

    In linear mode the formatter picks decimal places from ``spacing``,
    falling back to ``%g`` for very small / very large values. In log
    mode the upstream ``logTickStrings`` runs (renders ``10ⁿ`` with
    superscript exponents).
    """
    if log:
        return log_tick_strings(values, scale, spacing)

    places = max(0, ceil(-log10(spacing * scale)))
    out: List[str] = []
    for v in values:
        vs = v * scale
        if abs(vs) < 0.001 or abs(vs) >= 10000:
            out.append("%g" % vs)
        else:
            out.append(("%%0.%df" % places) % vs)
    return out


# Superscript map for log-mode exponents (upstream uses these
# Unicode codepoints directly).
_SUPERSCRIPT = str.maketrans({
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
})


def log_tick_strings(
    values: List[float],
    scale: float,
    spacing: float,
) -> List[str]:
    """Format log-mode tick values as ``10ⁿ`` strings.

    Verbatim from pyqtgraph ``AxisItem.logTickStrings`` — the values
    are interpreted as ``log10(x * scale)`` and rendered with Unicode
    superscripts.
    """
    _ = spacing  # unused upstream but kept in the signature
    e_strings = [
        "%0.1g" % x
        for x in 10 ** np.asarray(values, dtype=np.float64) * scale
    ]
    out: List[str] = []
    for e in e_strings:
        if "e" not in e:
            out.append(e)
            continue
        v, p = e.split("e")
        sign = "⁻" if p[0] == "-" else ""
        pot = p[1:].lstrip("0").translate(_SUPERSCRIPT)
        head = "" if v == "1" else f"{v}·"
        out.append(f"{head}10{sign}{pot}")
    return out
