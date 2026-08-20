/*
 * T.R.A.N.S. — shared tool palette.
 *
 * Tools live in embedded windows, so `Window.window` is the application
 * window: reading a colour it does not carry yields `undefined`, which lands
 * as an invalid QColor and paints text black-on-black. Every colour is
 * resolved through pick() with an explicit fallback instead.
 */
import QtQuick 2.15

QtObject {
    id: theme

    // The window whose palette to follow — pass `Window.window`.
    property var win: null

    function pick(name, fallback) {
        return (win && win[name] !== undefined && win[name] !== null)
                ? win[name] : fallback
    }

    readonly property color bgDark: pick("bgDark", "#1a1a2e")
    readonly property color bgMedium: pick("bgMedium", "#2a2a3e")
    readonly property color bgLight: pick("bgLight", "#3a3a4e")
    readonly property color accentPink: pick("accentPink", "#F5A9B8")
    readonly property color accentBlue: pick("accentBlue", "#5BCEFA")
    readonly property color accentPurple: pick("accentPurple", "#9B4F96")
    readonly property color textLight: pick("textLight", "#ffffff")
    readonly property color textMuted: pick("textMuted", "#cccccc")
    readonly property color borderColor: pick("borderColor", "#9B4F96")
}
