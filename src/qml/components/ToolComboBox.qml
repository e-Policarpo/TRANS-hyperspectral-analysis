/*
 * T.R.A.N.S. — dropdown for tool panels, styled for the dark palette.
 */
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

ComboBox {
    id: comboRoot

    property ToolTheme theme: ToolTheme { win: comboRoot.Window.window }

    contentItem: Text {
        leftPadding: 8
        rightPadding: 26
        text: comboRoot.displayText
        font: comboRoot.font
        color: comboRoot.enabled ? comboRoot.theme.textLight : comboRoot.theme.textMuted
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        implicitHeight: 30
        color: comboRoot.theme.bgDark
        border.color: comboRoot.activeFocus ? comboRoot.theme.accentBlue : comboRoot.theme.bgLight
        border.width: 1
        radius: 4
    }

    delegate: ItemDelegate {
        width: comboRoot.width
        contentItem: Text {
            text: modelData
            color: comboRoot.theme.textLight
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        highlighted: comboRoot.highlightedIndex === index
        background: Rectangle {
            color: highlighted ? comboRoot.theme.bgLight : comboRoot.theme.bgMedium
        }
    }

    popup: Popup {
        y: comboRoot.height
        width: comboRoot.width
        implicitHeight: Math.min(contentItem.implicitHeight, 260)
        padding: 1
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: comboRoot.popup.visible ? comboRoot.delegateModel : null
            ScrollIndicator.vertical: ScrollIndicator { }
        }
        background: Rectangle {
            color: comboRoot.theme.bgMedium
            border.color: comboRoot.theme.accentPurple
            border.width: 1
            radius: 4
        }
    }
}
