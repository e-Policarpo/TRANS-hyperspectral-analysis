/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * NoteWindowContent — embedded read-only viewer for text annotations
 * (WITec TDText entries, user notes, etc.). Mirrors the structure of
 * GraphWindowContent / ImageWindowContent.
 *
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: May 2026
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    // No local ``backend`` property — relies on the global QML context
    // property (see ImageWindowContent for the rationale).

    property string entityId: ""
    property string noteTitle: ""
    property string noteText: ""
    property string noteSource: ""

    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgDarker: (mainWin && mainWin.bgDarker !== undefined) ? mainWin.bgDarker : Theme.bgDarker
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

    implicitWidth: 520
    implicitHeight: 320

    ColumnLayout {
        anchors.fill: parent
        spacing: 6
        anchors.margins: 8

        Label {
            Layout.fillWidth: true
            text: noteTitle
            font.pixelSize: 13
            font.bold: true
            color: textLight
            elide: Label.ElideRight
        }

        Label {
            Layout.fillWidth: true
            text: noteSource ? "Source: " + noteSource : ""
            font.pixelSize: 10
            color: textMuted
            visible: !!noteSource
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDarker
            border.color: borderColor
            border.width: 1
            radius: 4

            ScrollView {
                anchors.fill: parent
                anchors.margins: 4
                clip: true

                TextArea {
                    text: noteText
                    readOnly: true
                    color: textLight
                    background: Rectangle { color: "transparent" }
                    font.family: "Menlo, Consolas, monospace"
                    font.pixelSize: 12
                    wrapMode: TextArea.Wrap
                    selectByMouse: true
                }
            }
        }
    }
}
