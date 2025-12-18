/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

Dialog {
    id: dialog

    title: "Save Layout"
    modal: true
    standardButtons: Dialog.Save | Dialog.Cancel

    width: 400
    height: 200

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#2d2d3e"
    property color textLight: mainWin ? mainWin.textLight : "#e0e0e0"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"

    background: Rectangle {
        color: bgLight
        border.color: borderColor
        border.width: 1
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 15

        Label {
            text: "Enter a name for this layout:"
            font.pixelSize: 13
            color: textLight
        }

        TextField {
            id: layoutNameField
            Layout.fillWidth: true
            placeholderText: "e.g., My Workspace, Analysis Setup, etc."
            color: textLight
            placeholderTextColor: textMuted
            selectByMouse: true

            background: Rectangle {
                color: bgDark
                border.color: layoutNameField.activeFocus ? accentPink : borderColor
                border.width: 1
                radius: 3
            }
        }

        Label {
            text: "This will save the current window positions and dock layout."
            font.pixelSize: 11
            color: textMuted
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Item { Layout.fillHeight: true }

        Label {
            id: statusLabel
            text: ""
            font.pixelSize: 12
            color: accentPink
            visible: text !== ""
            Layout.fillWidth: true
        }
    }

    onAccepted: {
        var layoutName = layoutNameField.text.trim()
        if (layoutName === "") {
            statusLabel.text = "Please enter a layout name"
            return
        }

        if (backend && backend.dockManager) {
            var result = backend.dockManager.saveLayout(layoutName)
            if (result.success) {
                console.log("Layout saved:", result.message)
                layoutNameField.text = ""
                statusLabel.text = ""
            } else {
                statusLabel.text = "Error: " + result.message
            }
        }
    }

    onOpened: {
        layoutNameField.text = ""
        statusLabel.text = ""
        layoutNameField.forceActiveFocus()
    }
}
