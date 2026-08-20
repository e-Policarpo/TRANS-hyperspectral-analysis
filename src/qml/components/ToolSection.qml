/*
 * T.R.A.N.S. — titled parameter block, styled for the dark tool palette.
 * The native style paints GroupBox light, which is unreadable here.
 */
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

GroupBox {
    id: sectionRoot

    // Resolved from the control itself: Window.window is an Item
    // attached property, so it cannot be read inside a QtObject.
    property ToolTheme theme: ToolTheme { win: sectionRoot.Window.window }

    Layout.fillWidth: true
    topPadding: 28

    background: Rectangle {
        y: sectionRoot.topPadding - 24
        width: parent.width
        height: parent.height - sectionRoot.topPadding + 24
        color: sectionRoot.theme.bgMedium
        border.color: sectionRoot.theme.bgLight
        border.width: 1
        radius: 4
    }

    label: Text {
        text: sectionRoot.title
        color: sectionRoot.theme.accentPink
        font.bold: true
        font.pixelSize: 12
        padding: 4
    }
}
