/*
 * T.R.A.N.S. — dropdown for tool panels, styled for the dark palette.
 */
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

ComboBox {
    id: comboRoot

    property ToolTheme theme: ToolTheme { win: comboRoot.Window.window }

    // How wide the list may grow past the box itself. A dataset name is
    // longer than any dropdown that fits a tool panel, and a column of
    // "2026Jul21-143815 · line3 (64pts 64rep…" tells you nothing about which
    // one you are picking.
    property int popupMaxWidth: 560

    FontMetrics { id: comboMetrics; font: comboRoot.font }

    readonly property int widestEntryWidth: {
        var widest = comboRoot.width
        var entries = comboRoot.model
        if (entries && entries.length !== undefined) {
            for (var i = 0; i < entries.length; i++) {
                var entry = entries[i]
                if (entry && typeof entry === "object" && comboRoot.textRole)
                    entry = entry[comboRoot.textRole]
                if (entry === undefined || entry === null)
                    continue
                var entryWidth = comboMetrics.advanceWidth(String(entry)) + 30
                if (entryWidth > widest)
                    widest = entryWidth
            }
        }
        return Math.min(widest, comboRoot.popupMaxWidth)
    }

    // The closed box has to elide, so hovering it says the whole thing.
    // hoverEnabled is explicit: without it `hovered` never turns true under
    // some styles and the tooltip simply never shows.
    hoverEnabled: true
    ToolTip.text: comboRoot.displayText
    ToolTip.delay: 400
    ToolTip.visible: comboRoot.hovered && comboText.truncated && !comboRoot.popup.visible

    contentItem: Text {
        id: comboText
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
        width: ListView.view ? ListView.view.width : comboRoot.width
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
        width: comboRoot.widestEntryWidth
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
