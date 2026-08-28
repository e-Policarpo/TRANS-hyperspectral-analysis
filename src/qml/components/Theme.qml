/*
 * T.R.A.N.S. — the colour scheme, as one object the whole tree can bind to.
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * License: GPL
 *
 * Until now the scheme lived on Main.qml, and everything downstream reached it
 * by locating that window at runtime — `Window.window`, `ApplicationWindow.window`,
 * or a scan of Qt.application.allWindows for objectName "mainWindow". Each of
 * those can come back null (a plain Window is not an ApplicationWindow; the
 * scan runs once and never retries), and a null host silently drops every
 * colour onto a hardcoded fallback from a scheme that no longer exists. This
 * singleton is the target that cannot be missing: it has no parent to find.
 *
 * Main.qml still publishes the same twelve names — nine tool files and every
 * Tool* component read them off the window — but now as bindings to this
 * object rather than as the source of truth.
 */
pragma Singleton
import QtQuick 2.15

QtObject {
    id: theme

    // ─────────────────────────────────────────────────────────────────────
    // Where the colours come from.
    //
    // The PreferencesManager owns the scheme; this object mirrors it. It is
    // handed in rather than looked up because a QML singleton is built the
    // first time anything reads it, which may be before the engine has a
    // `backend` context property at all — a singleton that resolved its
    // source once, at construction, would sit on the defaults for the rest of
    // the session and paint an entire app in the wrong palette. Assigning
    // `preferences` at any later moment re-runs the sync, so wiring order
    // stops mattering. _autoAttach() tries the context property anyway, so a
    // QML-only harness (a test loading one tool) still gets the real scheme.
    // ─────────────────────────────────────────────────────────────────────
    property QtObject preferences: null

    // Bumped every time the scheme is re-read. Anything that must recompute a
    // derived value (a JS object of colours, say — QML does not track changes
    // *inside* an object) can bind to this instead of to each colour in turn.
    property int revision: 0

    // ── The palette ──────────────────────────────────────────────────────
    // These names are the ones the rest of the tree already uses, and three of
    // them are aliases whose name does not match what they hold:
    //
    //     accentPink    holds the scheme's accentPrimary
    //     accentBlue    holds the scheme's accentSecondary
    //     accentOrange  holds the scheme's accentTertiary
    //     accentMagenta holds the scheme's error
    //     accentPurple  holds the scheme's borderColor  (a duplicate of borderColor)
    //
    // They are wrong-headed — under "Just Dark Mode" accentPink is blue and
    // accentBlue is pink — but they are load-bearing: nine tool files and every
    // Tool* component read them by these names, so renaming them here would
    // invert the palette everywhere at once. Renaming is a separate pass.
    property color bgDark: "#1a1a2e"
    property color bgDarker: "#0d0d1a"
    property color bgMedium: "#2a2a3e"
    property color bgLight: "#3a3a4e"
    property color accentPink: "#F5A9B8"       // scheme accentPrimary
    property color accentBlue: "#5BCEFA"       // scheme accentSecondary
    property color accentMagenta: "#D60270"    // scheme error
    property color accentPurple: "#9B4F96"     // scheme borderColor
    property color accentOrange: "#FF9B55"     // scheme accentTertiary
    property color textLight: "#ffffff"        // scheme textPrimary
    property color textMuted: "#cccccc"
    property color borderColor: "#9B4F96"
    // The three semantic colours. Every one of the 22 schemes carries all
    // three keys and until now the tree read only `error`, and read it under
    // the misleading name accentMagenta. They are published here under their
    // own names because the canvases need them by meaning, not by hue: an
    // error bar's green/amber/red IS the good/marginal/bad scale, so a canvas
    // asking for "the warning colour" must not have to know that the scheme
    // calls it accentTertiary or that accentMagenta happens to hold `error`.
    //
    // accentMagenta stays as it is and keeps holding `error` — nine tool
    // files read it by that name — so errorColor is deliberately a second
    // name for the same value rather than a replacement.
    property color successColor: "#2ECC71"     // scheme success
    property color warningColor: "#FF9800"     // scheme warning
    property color errorColor: "#D60270"       // scheme error (== accentMagenta)

    // ── Fonts ────────────────────────────────────────────────────────────
    // Same source, same signal, so they live here too rather than leaving
    // half of applyColorScheme() behind on the window.
    property int fontSizeSmall: 10
    property int fontSizeMedium: 12
    property int fontSizeLarge: 14
    property int fontSizeHeader: 16
    property int fontSizeTitle: 18
    property string fontFamily: Qt.platform.os === "osx" ? ".AppleSystemUIFont" : "Segoe UI"
    property string fontFamilyMono: Qt.platform.os === "osx" ? "Menlo" : "Consolas"

    readonly property int fontSizeXSmall: Math.max(8, fontSizeSmall - 2)
    readonly property int fontSizeXLarge: fontSizeHeader + 2

    // ── Following the scheme ─────────────────────────────────────────────

    // ── Readability ──────────────────────────────────────────────────────
    //
    // WCAG relative luminance, so the guard below measures the same thing
    // src/utils/color_contrast.py does rather than eyeballing brightness.
    function _luminance(colour) {
        function channel(v) {
            return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(colour.r) + 0.7152 * channel(colour.g)
             + 0.0722 * channel(colour.b)
    }

    function _contrast(fg, bg) {
        var a = _luminance(fg), b = _luminance(bg)
        return a < b ? (b + 0.05) / (a + 0.05) : (a + 0.05) / (b + 0.05)
    }

    // `colour`, moved along its own lightness until it can be read as text on
    // `ground`. Hue and saturation are untouched, so it is still the scheme's
    // green — only far enough from the ground to be legible.
    //
    // This exists because `success` is used as status TEXT ("Workflow is
    // valid", "Connection added", the node-parameter validity dot) and 10 of
    // the 22 schemes put their own success below the 4.5:1 body-text minimum
    // on bgDark: Fruity Rainbow and Intersectional ship #008018 at 3.40:1,
    // Just Light 2.72:1, Straight Dark 3.46:1. The tree used to paint that
    // text a fixed #66ff99 — 13.53:1 on a dark scheme — so routing it to the
    // scheme was a 4x contrast regression on schemes where nothing had been
    // wrong. Adjusting rather than substituting keeps the scheme's own colour
    // and satisfies the guard.
    // Whichever of the two text colours can actually be read on `fill`.
    //
    // A chip painted in an accent has no fixed right ink: measured over the
    // 22 schemes, bgDark on accentSecondary runs from 2.42:1 (Tropical
    // Panchito) to 12.06:1 (Attracted to Pans), and textLight is the better
    // choice on exactly the schemes where bgDark is the worse one. Picking
    // per scheme is the only answer that holds on all of them; nailing either
    // one down makes some scheme's selected chip unreadable.
    function ink(fill) {
        return _contrast(textLight, fill) >= _contrast(bgDark, fill)
             ? textLight : bgDark
    }

    // How far apart two colours are, on the 0..441 RGB scale
    // qml_figure_canvas.py's scale_or_default uses. RGB and not contrast,
    // because contrast is luminance alone and green-against-red is a
    // difference no luminance measure can see.
    function _distance(a, b) {
        return Math.abs(a.r - b.r) * 255 + Math.abs(a.g - b.g) * 255
             + Math.abs(a.b - b.b) * 255
    }

    //: Below this the two colours read as the same colour. The same number
    //: the Python canvases use, so both halves of the app agree.
    readonly property real scaleMinDistance: 60

    function readable(colour, ground, minimum) {
        var c = Qt.colorEqual(colour, colour) ? colour : colour   // force a color
        if (_contrast(c, ground) >= minimum)
            return c
        // Move away from the ground: lighten over a dark one, darken over a
        // light one. Bounded — a hue that cannot reach the target (a mid
        // grey on a mid grey) stops at its best rather than looping.
        var towardsWhite = _luminance(ground) < 0.5
        var best = c
        for (var i = 0; i < 24; i++) {
            c = towardsWhite ? Qt.lighter(c, 1.12) : Qt.darker(c, 1.12)
            if (_contrast(c, ground) > _contrast(best, ground))
                best = c
            if (_contrast(c, ground) >= minimum)
                return c
        }
        return best
    }

    // Re-read everything from the PreferencesManager. Safe to call at any
    // time and with no preferences attached: with nothing to read from it
    // leaves the defaults in place rather than blanking the palette, because
    // an unset QML color is an invalid QColor and paints black on black.
    function refresh() {
        if (!preferences)
            return

        var scheme = preferences.getCurrentScheme()
        if (!scheme || !scheme.colors)
            return
        var c = scheme.colors

        bgDark = c.bgDark || "#1a1a2e"
        bgDarker = c.bgDarker || "#0d0d1a"
        bgMedium = c.bgMedium || "#2a2a3e"
        bgLight = c.bgLight || "#3a3a4e"

        accentPink = c.accentPrimary || "#F5A9B8"
        accentBlue = c.accentSecondary || "#5BCEFA"
        accentOrange = c.accentTertiary || "#FF9B55"
        accentMagenta = c.error || "#D60270"
        accentPurple = c.borderColor || "#9B4F96"

        textLight = c.textPrimary || "#ffffff"
        textMuted = c.textMuted || "#cccccc"
        borderColor = c.borderColor || "#9B4F96"
        // The semantic three are the only colours here that get read as body
        // text against bgDark rather than being chosen for it, so they are the
        // only ones passed through readable(). See the note on that function.
        // The semantic three carry a *meaning*, and a meaning that is only in
        // the colour dies the moment two of the three are the same colour.
        // Two schemes ship exactly that: Straight Light's success #6a6a6a and
        // error #706a6a are 6 apart out of 441, Straight Dark's are 33 — so
        // "it worked" and "it failed" painted the identical grey in the
        // workflow result dialog, the node-parameter validity dot and the
        // debug console. Where the scheme's own scale has collapsed, the
        // fixed triple stands in; this is the same fallback, and the same
        // threshold, that qml_figure_canvas.scale_or_default applies to the
        // canvases, so the two halves of the app never disagree.
        var su = Qt.color(c.success || "#2ECC71")
        var wa = Qt.color(c.warning || "#FF9800")
        var er = Qt.color(c.error || "#D60270")
        if (_distance(su, er) < scaleMinDistance
                || _distance(su, wa) < scaleMinDistance
                || _distance(wa, er) < scaleMinDistance) {
            su = Qt.color("#2ECC71"); wa = Qt.color("#FF9800"); er = Qt.color("#FF6B6B")
        }
        successColor = readable(su, bgDark, 4.5)
        warningColor = readable(wa, bgDark, 4.5)
        errorColor = readable(er, bgDark, 4.5)

        if (scheme.font) {
            fontSizeSmall = scheme.font.sizeSmall || 10
            fontSizeMedium = scheme.font.sizeMedium || 12
            fontSizeLarge = scheme.font.sizeLarge || 14
            fontSizeHeader = scheme.font.sizeHeader || 16
            fontSizeTitle = scheme.font.sizeTitle || 18
            var ff = scheme.font.family || ""
            if (!ff || ff === "system-ui")
                ff = Qt.platform.os === "osx" ? ".AppleSystemUIFont" : "Segoe UI"
            fontFamily = ff
        }

        revision = revision + 1
    }

    // Point the singleton at a PreferencesManager. Idempotent, so both
    // Main.qml and _autoAttach() may call it.
    function attach(prefs) {
        if (!prefs || preferences === prefs) {
            refresh()
            return
        }
        preferences = prefs   // onPreferencesChanged refreshes
    }

    // Last-resort wiring for contexts that never run Main.qml — a test that
    // loads a single tool, say. `typeof` on an unbound name is the one JS
    // form that does not throw, so this is safe when there is no backend.
    function _autoAttach() {
        if (preferences)
            return
        try {
            if (typeof backend !== "undefined" && backend && backend.preferencesManager)
                attach(backend.preferencesManager)
        } catch (e) {
            // No backend in this context: the defaults stand.
        }
    }

    onPreferencesChanged: refresh()

    // A live scheme change (the Preferences dialog) and the initial load both
    // arrive as signals from the manager. Keeping the listener here — rather
    // than one per window — is what lets a window opened *after* a scheme
    // change start correct instead of stale.
    property Connections _schemeLink: Connections {
        target: theme.preferences
        enabled: theme.preferences !== null
        function onColorSchemeChanged(schemeName) { theme.refresh() }
        function onPreferencesLoaded() { theme.refresh() }
        function onFontChanged() { theme.refresh() }
    }

    Component.onCompleted: _autoAttach()
}
