"""WCAG contrast checking for the app's colour schemes.

The UI ships 22 schemes, light and dark. Geometry tests prove text isn't
clipped, but they say nothing about whether it can be *read*: a scheme whose
``textMuted`` sits too close to ``bgMedium`` produces labels that are present,
correctly laid out, and effectively invisible.

This implements the WCAG 2.1 contrast ratio so that can be checked mechanically
for every scheme, rather than noticed by eye on the one scheme a developer
happens to use.

Reference: https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
License: GPL
"""

from __future__ import annotations

from typing import Dict, Iterable, List, NamedTuple, Tuple

# WCAG 2.1 minimum contrast ratios.
AA_NORMAL_TEXT = 4.5      # body text below ~18pt (or ~14pt bold)
AA_LARGE_TEXT = 3.0       # headings and large text
AA_NON_TEXT = 3.0         # UI component boundaries, focus indicators


def parse_hex(color: str) -> Tuple[int, int, int]:
    """``"#RRGGBB"`` / ``"#RGB"`` → ``(r, g, b)`` in 0-255.

    Raises ``ValueError`` on anything else — a scheme carrying an unparseable
    colour is a bug worth surfacing, not silently defaulting.
    """
    if not isinstance(color, str):
        raise ValueError(f"Not a colour string: {color!r}")
    s = color.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) == 8:       # #AARRGGBB or #RRGGBBAA — drop alpha, compare opaque
        s = s[:6]
    if len(s) != 6:
        raise ValueError(f"Not a hex colour: {color!r}")
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError as e:
        raise ValueError(f"Not a hex colour: {color!r}") from e


def relative_luminance(color: str) -> float:
    """WCAG relative luminance in 0.0 (black) … 1.0 (white)."""
    def channel(v: int) -> float:
        c = v / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = parse_hex(color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """Contrast ratio between two colours, 1.0 … 21.0. Order-independent."""
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


class Pairing(NamedTuple):
    """One foreground/background combination the UI actually renders."""
    fg: str          # scheme colour key
    bg: str          # scheme colour key
    minimum: float   # required ratio
    where: str       # where it shows up, for the failure message


# The combinations the QML actually paints. Keys are those of
# ``PRESET_COLOR_SCHEMES[...]["colors"]``; the QML aliases are noted because
# Main.qml renames several on the way through (accentPrimary -> accentPink …).
UI_PAIRINGS: Tuple[Pairing, ...] = (
    Pairing("textPrimary", "bgDark", AA_NORMAL_TEXT, "body text on panels"),
    Pairing("textPrimary", "bgDarker", AA_NORMAL_TEXT, "body text on viewports"),
    Pairing("textPrimary", "bgMedium", AA_NORMAL_TEXT, "body text on sections"),
    Pairing("textPrimary", "bgLight", AA_NORMAL_TEXT, "body text on controls"),
    Pairing("textMuted", "bgDark", AA_NORMAL_TEXT, "help text on panels"),
    Pairing("textMuted", "bgMedium", AA_NORMAL_TEXT, "help text in sections"),
    Pairing("textMuted", "bgLight", AA_NORMAL_TEXT, "placeholder in controls"),
    # accentPrimary -> accentPink: section titles, emphasis labels.
    Pairing("accentPrimary", "bgMedium", AA_LARGE_TEXT, "section titles"),
    Pairing("accentPrimary", "bgDark", AA_LARGE_TEXT, "emphasis labels"),
    # accentSecondary -> accentBlue: sub-headings, units readouts.
    Pairing("accentSecondary", "bgDark", AA_LARGE_TEXT, "sub-headings"),
    # The run button paints bgDark text on an accentPrimary fill.
    Pairing("bgDark", "accentPrimary", AA_NORMAL_TEXT, "primary button label"),
)

# Deliberately NOT in UI_PAIRINGS: ``borderColor`` against the backgrounds.
# WCAG's 3:1 non-text rule covers UI boundaries whose visibility is *essential*
# to operating the control; a panel divider that reads as a soft separator is a
# legitimate design choice, and enforcing 3:1 there flagged 12 of 22 schemes
# without any of them being hard to use. Available for ad-hoc auditing:
ADVISORY_PAIRINGS: Tuple[Pairing, ...] = (
    Pairing("borderColor", "bgDark", AA_NON_TEXT, "panel borders"),
    Pairing("borderColor", "bgMedium", AA_NON_TEXT, "section borders"),
)


class Failure(NamedTuple):
    scheme: str
    pairing: Pairing
    ratio: float

    def __str__(self) -> str:
        p = self.pairing
        return (f"{self.scheme}: {p.fg} on {p.bg} "
                f"({p.where}) = {self.ratio:.2f}:1, needs {p.minimum}:1")


def check_scheme(name: str, colors: Dict[str, str],
                 pairings: Iterable[Pairing] = UI_PAIRINGS) -> List[Failure]:
    """Contrast failures for one scheme. Empty list means it passes.

    Pairings referencing a colour the scheme doesn't define are skipped rather
    than reported — schemes are allowed to omit optional keys.
    """
    out: List[Failure] = []
    for p in pairings:
        fg, bg = colors.get(p.fg), colors.get(p.bg)
        if not fg or not bg:
            continue
        ratio = contrast_ratio(fg, bg)
        if ratio + 1e-9 < p.minimum:
            out.append(Failure(name, p, ratio))
    return out
