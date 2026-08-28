/*
 * T.R.A.N.S. — continuous slider for tool panels, styled for the dark
 * palette.
 *
 * An unstyled Slider follows the OS rather than this theme: on a light
 * system it paints a pale groove and a pale handle onto a near-black panel,
 * and on a dark one it borrows an accent that is not ours. Both the groove
 * and the handle are therefore drawn here.
 */
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Slider {
    id: sliderRoot

    property ToolTheme theme: ToolTheme { win: sliderRoot.Window.window }

    implicitHeight: 24
    padding: 0
    leftPadding: 7
    rightPadding: 7

    background: Rectangle {
        x: sliderRoot.leftPadding
        y: sliderRoot.topPadding + sliderRoot.availableHeight / 2 - height / 2
        implicitWidth: 120
        implicitHeight: 4
        width: sliderRoot.availableWidth
        height: 4
        radius: 2
        color: sliderRoot.theme.bgDark
        border.color: sliderRoot.theme.bgLight
        border.width: 1

        // The travelled part, so the handle's position is readable at a
        // glance without reading the number beside it.
        Rectangle {
            width: sliderRoot.position * parent.width
            height: parent.height
            radius: 2
            color: sliderRoot.enabled ? sliderRoot.theme.accentBlue
                                      : sliderRoot.theme.bgLight
        }
    }

    handle: Rectangle {
        x: sliderRoot.leftPadding
           + sliderRoot.visualPosition * (sliderRoot.availableWidth - width)
        y: sliderRoot.topPadding + sliderRoot.availableHeight / 2 - height / 2
        implicitWidth: 14
        implicitHeight: 14
        radius: width / 2
        color: !sliderRoot.enabled ? sliderRoot.theme.bgMedium
               : (sliderRoot.pressed ? Qt.lighter(sliderRoot.theme.accentBlue, 1.2)
                                     : sliderRoot.theme.textLight)
        border.color: sliderRoot.enabled ? sliderRoot.theme.accentBlue
                                         : sliderRoot.theme.bgLight
        border.width: 2
    }
}
