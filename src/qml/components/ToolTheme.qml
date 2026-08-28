/*
 * T.R.A.N.S. — shared tool palette.
 *
 * A thin adapter, kept for the tools that already use it. The colours now come
 * from the Theme singleton, which no window has to be located for; `win` stays
 * as an override for a host that publishes a colour of its own (the Workflow
 * editor does), and as the reason this file still exists at all.
 *
 * Every colour is still resolved through pick() with a fallback rather than
 * read straight off `win`: a name the host does not carry yields `undefined`,
 * which lands as an invalid QColor and paints text black-on-black. Note the
 * fallback argument is what ties each binding to the singleton — pick() reads
 * win[name] by string, and a dynamic lookup is not something the binding can
 * depend on, so naming Theme.<colour> in the call is what makes a live scheme
 * change reach these properties.
 */
import QtQuick 2.15

QtObject {
    id: theme

    // Optional host override — pass `Window.window`. Left null, everything
    // comes from the singleton. (A QtObject cannot read the Window attached
    // property itself, which is why this is handed in from outside.)
    property var win: null

    function pick(name, fallback) {
        return (win && win[name] !== undefined && win[name] !== null)
                ? win[name] : fallback
    }

    readonly property color bgDark: pick("bgDark", Theme.bgDark)
    readonly property color bgDarker: pick("bgDarker", Theme.bgDarker)
    readonly property color bgMedium: pick("bgMedium", Theme.bgMedium)
    readonly property color bgLight: pick("bgLight", Theme.bgLight)
    readonly property color accentPink: pick("accentPink", Theme.accentPink)
    readonly property color accentBlue: pick("accentBlue", Theme.accentBlue)
    readonly property color accentMagenta: pick("accentMagenta", Theme.accentMagenta)
    readonly property color accentPurple: pick("accentPurple", Theme.accentPurple)
    readonly property color accentOrange: pick("accentOrange", Theme.accentOrange)
    readonly property color textLight: pick("textLight", Theme.textLight)
    readonly property color textMuted: pick("textMuted", Theme.textMuted)
    readonly property color borderColor: pick("borderColor", Theme.borderColor)
    readonly property color successColor: pick("successColor", Theme.successColor)
}
