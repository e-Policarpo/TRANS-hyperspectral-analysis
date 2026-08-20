/*
 * T.R.A.N.S. — checkbox whose label follows the tool palette.
 */
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

CheckBox {
    id: checkRoot

    property ToolTheme theme: ToolTheme { win: checkRoot.Window.window }

    contentItem: Text {
        text: checkRoot.text
        color: checkRoot.enabled ? checkRoot.theme.textLight : checkRoot.theme.textMuted
        leftPadding: checkRoot.indicator.width + 6
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
}
