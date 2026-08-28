/*
 * T.R.A.N.S. — push button for tool panels, styled for the dark palette.
 *
 * The Basic style's Button carries an implicit width of 100 px whatever its
 * label says — "Clear" is 31 px of text in a 100 px button. Three of them in
 * a row therefore need 310 px, and a row is never given less than the sum of
 * its non-filling children, so in a 291 px parameter column the third one is
 * simply clipped away. This one is as wide as its own text plus its padding,
 * and a caller that sets Layout.fillWidth can shrink it further — the label
 * elides rather than the button overflowing its panel.
 */
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Button {
    id: buttonRoot

    // Resolved from the control itself: Window.window is an Item attached
    // property, so it cannot be read inside the QtObject.
    property ToolTheme theme: ToolTheme { win: buttonRoot.Window.window }

    // The one action the panel exists for — Solve, Run. Filled rather than
    // outlined so it reads as the thing to press. `highlighted` paints the
    // native accent, which is not this palette's.
    property bool primary: false

    padding: 10
    implicitHeight: 30
    font.pixelSize: 12

    contentItem: Text {
        text: buttonRoot.text
        font: buttonRoot.font
        color: !buttonRoot.enabled
               ? buttonRoot.theme.textMuted
               : (buttonRoot.primary ? buttonRoot.theme.bgDark : buttonRoot.theme.textLight)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 4
        color: {
            if (!buttonRoot.enabled)
                return buttonRoot.theme.bgMedium
            if (buttonRoot.primary)
                return buttonRoot.down ? Qt.darker(buttonRoot.theme.accentBlue, 1.25)
                     : buttonRoot.hovered ? Qt.lighter(buttonRoot.theme.accentBlue, 1.1)
                     : buttonRoot.theme.accentBlue
            return buttonRoot.down ? buttonRoot.theme.bgLight
                 : buttonRoot.hovered ? Qt.lighter(buttonRoot.theme.bgMedium, 1.4)
                 : buttonRoot.theme.bgMedium
        }
        border.color: buttonRoot.primary && buttonRoot.enabled
                      ? buttonRoot.theme.accentBlue : buttonRoot.theme.bgLight
        border.width: 1
    }
}
