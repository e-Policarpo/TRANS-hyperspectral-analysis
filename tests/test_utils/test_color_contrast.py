"""WCAG contrast across every shipped colour scheme.

The geometry tests prove text isn't clipped; these prove it can be *read*. A
scheme whose ``textMuted`` sits close to ``bgMedium`` produces labels that are
present, correctly laid out and effectively invisible — and nobody notices,
because a developer only ever looks at the one scheme they use.

The app ships 22 schemes and several are pride-flag palettes whose colours are
deliberate, so this is a **regression guard, not a redesign**: where a shortfall
is the flag colour itself, it is recorded rather than muted. Existing ones live in
KNOWN_SHORTFALLS with their measured ratio, and the tests assert that

* every scheme/pairing not listed meets WCAG AA, so a NEW scheme cannot ship
  unreadable, and
* listed ones never get *worse*, and the list has no stale entries — fixing a
  palette makes the test tell you to delete its line.
"""

import pytest

from src.backend.preferences_manager import PRESET_COLOR_SCHEMES
from src.utils.color_contrast import (AA_LARGE_TEXT, AA_NORMAL_TEXT,
                                      UI_PAIRINGS, check_scheme,
                                      contrast_ratio, parse_hex,
                                      relative_luminance)

# (scheme, foreground key, background key) -> ratio measured 2026-08-16.
#
# Every remaining entry is an ACCENT against a background — the flag colours
# themselves, which are deliberate and not ours to mute. All *text* shortfalls
# have been fixed by adjusting each palette in place; text meets AA in all 22
# schemes, enforced separately and without an allowlist.
#
# None of these is asserted to be acceptable, only to be no worse than it was.
KNOWN_SHORTFALLS = {
    ("blahaj_light", "bgDark", "accentPrimary"): 3.64,
    ("fruity_rainbow", "bgDark", "accentPrimary"): 3.93,
    ("kitchen_table", "bgDark", "accentPrimary"): 3.45,
    ("sitting_weird", "bgDark", "accentPrimary"): 3.67,
    ("straight_dark", "accentSecondary", "bgDark"): 2.98,
    ("straight_dark", "bgDark", "accentPrimary"): 3.78,
    ("straight_light", "bgDark", "accentPrimary"): 4.35,
    ("sunshine_valid", "accentPrimary", "bgDark"): 2.5,
    ("sunshine_valid", "accentPrimary", "bgMedium"): 2.38,
    ("sunshine_valid", "bgDark", "accentPrimary"): 2.5,
    ("tropical_panch", "accentSecondary", "bgDark"): 2.42,
    ("uhaul_ready", "bgDark", "accentPrimary"): 3.77,
}

# Anything at or below this reads as genuinely hard to use rather than merely
# short of AA. Kept separate so the worst cases stay visible.
SEVERE = 2.5


class TestContrastMath:
    """The ratio implementation itself, against published WCAG values."""

    def test_black_on_white_is_maximal(self):
        assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)

    def test_identical_colours_have_no_contrast(self):
        assert contrast_ratio("#4a4a4a", "#4a4a4a") == pytest.approx(1.0, abs=0.01)

    def test_wcag_boundary_grey(self):
        """#767676 on white is the canonical 4.5:1 boundary."""
        assert contrast_ratio("#767676", "#ffffff") == pytest.approx(4.54, abs=0.02)

    def test_ratio_is_order_independent(self):
        assert contrast_ratio("#123456", "#abcdef") == pytest.approx(
            contrast_ratio("#abcdef", "#123456"))

    def test_luminance_endpoints(self):
        assert relative_luminance("#000000") == pytest.approx(0.0)
        assert relative_luminance("#ffffff") == pytest.approx(1.0)

    @pytest.mark.parametrize("value,expected", [
        ("#ffffff", (255, 255, 255)),
        ("#000", (0, 0, 0)),
        ("#F5A9B8", (245, 169, 184)),
        ("  #5BCEFA  ", (91, 206, 250)),
        ("#FF5BCEFA", (255, 91, 206)),   # 8-digit: alpha dropped
    ])
    def test_parse_hex(self, value, expected):
        assert parse_hex(value) == expected

    @pytest.mark.parametrize("bad", ["", "red", "#12", "#12345", None, 42])
    def test_parse_hex_rejects_junk(self, bad):
        with pytest.raises(ValueError):
            parse_hex(bad)


def _failures():
    out = {}
    for name, scheme in PRESET_COLOR_SCHEMES.items():
        for f in check_scheme(name, scheme["colors"]):
            out[(name, f.pairing.fg, f.pairing.bg)] = f.ratio
    return out


class TestShippedSchemes:
    def test_every_scheme_defines_the_colours_the_ui_paints(self):
        needed = {p.fg for p in UI_PAIRINGS} | {p.bg for p in UI_PAIRINGS}
        for name, scheme in PRESET_COLOR_SCHEMES.items():
            missing = needed - set(scheme["colors"])
            assert not missing, f"{name} is missing {sorted(missing)}"

    def test_no_new_contrast_failures(self):
        """A new or edited scheme must meet AA on every UI pairing."""
        new = {k: v for k, v in _failures().items() if k not in KNOWN_SHORTFALLS}
        assert not new, (
            "New contrast failures — these would ship unreadable text:\n"
            + "\n".join(f"  {s}: {fg} on {bg} = {r:.2f}:1"
                         for (s, fg, bg), r in sorted(new.items())))

    def test_known_shortfalls_do_not_regress(self):
        current = _failures()
        worse = {k: (KNOWN_SHORTFALLS[k], current[k])
                 for k in KNOWN_SHORTFALLS
                 if k in current and current[k] < KNOWN_SHORTFALLS[k] - 0.01}
        assert not worse, (
            "Known shortfalls got worse:\n"
            + "\n".join(f"  {s}: {fg} on {bg} {was:.2f} -> {now:.2f}"
                         for (s, fg, bg), (was, now) in sorted(worse.items())))

    def test_no_stale_entries_in_the_allowlist(self):
        """Fixing a palette should delete its line, so the list stays honest."""
        current = _failures()
        fixed = sorted(k for k in KNOWN_SHORTFALLS if k not in current)
        assert not fixed, (
            "These now pass — remove them from KNOWN_SHORTFALLS:\n"
            + "\n".join(f"  {s}: {fg} on {bg}" for s, fg, bg in fixed))

    def test_severe_cases_are_tracked(self):
        """The worst offenders must at least be known about."""
        severe = {k: v for k, v in _failures().items() if v <= SEVERE}
        untracked = set(severe) - set(KNOWN_SHORTFALLS)
        assert not untracked, f"Untracked severe contrast failures: {untracked}"

    @pytest.mark.parametrize("scheme", sorted(PRESET_COLOR_SCHEMES))
    def test_text_meets_aa_in_every_scheme(self, scheme):
        """Text is held to AA unconditionally, with no allowlist.

        The accent colours are pride-flag palettes and deliberately not ours to
        mute, but *readability of text* is not a design preference — every
        ``textPrimary``/``textMuted`` pairing must pass in every scheme. This
        deliberately does not consult KNOWN_SHORTFALLS: a text failure is a bug
        to fix in the palette, not to record.
        """
        colors = PRESET_COLOR_SCHEMES[scheme]["colors"]
        text_pairings = [p for p in UI_PAIRINGS
                         if p.fg in ("textPrimary", "textMuted")]
        failures = check_scheme(scheme, colors, text_pairings)
        assert not failures, "\n".join(str(f) for f in failures)

    @pytest.mark.parametrize("scheme", sorted(PRESET_COLOR_SCHEMES))
    @pytest.mark.parametrize("accent", ["accentPrimary", "accentSecondary"])
    def test_accents_are_distinguishable_from_text(self, scheme, accent):
        """An accent must not be the same colour as the text.

        Three schemes shipped ``accentSecondary`` as ``#FFFFFF`` — identical to
        ``textPrimary`` — so a selected/highlighted control and the label on it
        were the same colour and the label vanished. This only forbids the
        degenerate case; how *close* an accent sits to the text is a design
        choice, but being indistinguishable from it is not.
        """
        colors = PRESET_COLOR_SCHEMES[scheme]["colors"]
        ratio = contrast_ratio(colors[accent], colors["textPrimary"])
        assert ratio > 1.05, (
            f"{scheme}: {accent} {colors[accent]} is indistinguishable from "
            f"textPrimary {colors['textPrimary']} ({ratio:.2f}:1)")

    def test_default_scheme_is_fully_accessible(self):
        """Whatever ships as the default must pass outright."""
        assert not check_scheme("blahaj_aesthetic",
                                PRESET_COLOR_SCHEMES["blahaj_aesthetic"]["colors"])
