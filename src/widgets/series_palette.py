"""Keeping a data series visible on whatever ground the scheme provides.

A curve's colour is its identity: curve 3 is the gold one in the legend, in
the plot, and in the export, and it must not change when the user picks a
different colour scheme. That rule held trivially while every plot in the app
was painted on a hardcoded ``#1a1a1a`` — the ten series hues were chosen
against exactly that ground and were legible on it.

The theming sweep made the figure ground follow the scheme's ``bgDark``, and
eight of the twenty-two schemes are light: ``just_light`` is ``#F5F5F5``,
``sunshine_valid`` ``#FFFEF0``. Measured there, nine of the ten hues fall
below the 3:1 WCAG threshold for a meaningful graphical mark — chartreuse
``#7FFF00`` lands at 1.19:1, gold ``#FFD700`` at 1.23:1. A user on a light
scheme with four curves on screen cannot see two of them.

The answer is not a second palette. A second palette breaks identity twice
over: the legend swatch and the curve would have to agree about which of the
two is in force, and the "green one" would be a different green depending on
a setting nobody associates with the plot. Instead each colour is walked
along its own lightness axis — hue and saturation untouched — only as far as
it takes to clear the threshold against the ground it is actually drawn on.
Chartreuse stays chartreuse; on white it becomes a darker chartreuse.

Colours that already pass are returned byte-identical, so every dark scheme
paints exactly what it painted before this module existed.
"""

from __future__ import annotations

import colorsys
from typing import Optional

from src.utils.color_contrast import contrast_ratio

#: The threshold a mark that carries meaning has to clear. WCAG 2.1 §1.4.11
#: sets 3:1 for a graphical object; a curve is the most load-bearing
#: graphical object this app draws.
MIN_SERIES_RATIO = 3.0

#: How finely the lightness axis is walked. 64 steps over the 0..1 range is
#: finer than the 8-bit channel it ends up quantised to, so the result is the
#: least adjustment that clears the threshold rather than an approximation.
_STEPS = 64


def _to_rgb(colour: str) -> Optional[tuple]:
    """``#rrggbb`` (or ``#rgb``) to a 0..1 triple, or None if unparseable."""
    if not isinstance(colour, str):
        return None
    text = colour.strip().lstrip('#')
    if len(text) == 3:
        text = ''.join(ch * 2 for ch in text)
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None


def _to_hex(rgb) -> str:
    return '#%02x%02x%02x' % tuple(
        max(0, min(255, int(round(channel * 255.0)))) for channel in rgb)


def _luminance(rgb) -> float:
    """Relative luminance, the same definition ``color_contrast`` uses."""
    channels = [(c / 12.92) if c <= 0.03928 else (((c + 0.055) / 1.055) ** 2.4)
                for c in rgb]
    return (0.2126 * channels[0] + 0.7152 * channels[1]
            + 0.0722 * channels[2])


def readable_on(colour: str, ground: str,
                min_ratio: float = MIN_SERIES_RATIO) -> str:
    """``colour``, darkened or lightened just enough to read on ``ground``.

    Returns ``colour`` unchanged whenever it already clears ``min_ratio``,
    when either argument cannot be parsed (a caller's fallback is not this
    module's to second-guess), or when no lightness on the colour's own hue
    clears the threshold — a mid-grey series on a mid-grey ground has no
    answer along this axis, and returning the caller's colour is a more
    honest failure than returning black.
    """
    rgb = _to_rgb(colour)
    bg = _to_rgb(ground)
    if rgb is None or bg is None:
        return colour
    if contrast_ratio(_to_hex(rgb), _to_hex(bg)) >= min_ratio:
        return colour

    # Which way to walk. On a light ground the only room is downward, and the
    # test is luminance rather than a channel mean because a saturated yellow
    # is a *light* colour however little red it carries.
    darken = _luminance(bg) > 0.5
    hue, lightness, saturation = colorsys.rgb_to_hls(*rgb)

    best = None
    for step in range(1, _STEPS + 1):
        fraction = step / _STEPS
        moved = (lightness * (1.0 - fraction)) if darken else (
            lightness + (1.0 - lightness) * fraction)
        candidate = _to_hex(colorsys.hls_to_rgb(hue, moved, saturation))
        if contrast_ratio(candidate, _to_hex(bg)) >= min_ratio:
            best = candidate
            break
    return best if best is not None else colour
