/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * ImageWindowContent — embedded image viewer.
 *
 * Uses Qt Quick's native ``Image`` element backed by the
 * ``image://trans/<id>`` provider registered in ``main.py``. Qt handles
 * scaling, mipmapping, and antialiasing — no QPainter, no LUT, no moiré.
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

    // The image entity to display. Looked up via ``image://trans/<imageId>``.
    property string imageId: ""

    // Persistence id (used by WindowManager for state save/restore).
    property string entityId: ""

    // Backwards-compat shim — the old code had ``content.appBackend = …``
    // assignments in WindowManager. Keep the property so those continue
    // to work even though we no longer need the backend reference here.
    property var appBackend: null

    // Theme colors (best-effort; resolve to safe defaults if no main window).
    property var mainWin: ApplicationWindow.window
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    implicitWidth: 640
    implicitHeight: 460

    Rectangle {
        anchors.fill: parent
        color: bgDarker
        border.color: borderColor
        border.width: 1

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 1
            spacing: 0

            // ----- viewport: native Image element ---------------------------
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#000000"
                clip: true

                Image {
                    id: img
                    anchors.fill: parent
                    anchors.margins: 4
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                    asynchronous: true
                    cache: true
                    source: imageId ? "image://trans/" + imageId : ""
                    sourceSize: Qt.size(0, 0)  // load at native resolution
                }

                Label {
                    anchors.centerIn: parent
                    visible: img.status !== Image.Ready
                    text: img.status === Image.Loading ? "Loading…"
                          : img.status === Image.Error ? "Image failed to load"
                          : "No image"
                    color: textMuted
                    font.pixelSize: 12
                }
            }

            // ----- thin info bar --------------------------------------------
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 24
                color: bgDark

                Label {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    color: textMuted
                    font.pixelSize: 11
                    text: img.sourceSize.width > 0
                          ? img.sourceSize.width + " × " + img.sourceSize.height + " px"
                          : ""
                }

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right
                    anchors.rightMargin: 6
                    spacing: 4

                    Button {
                        text: "Fit"
                        flat: true
                        font.pixelSize: 10
                        onClicked: img.fillMode = Image.PreserveAspectFit
                    }
                    Button {
                        text: "1:1"
                        flat: true
                        font.pixelSize: 10
                        onClicked: img.fillMode = Image.Pad
                    }
                    Button {
                        text: "Stretch"
                        flat: true
                        font.pixelSize: 10
                        onClicked: img.fillMode = Image.Stretch
                    }
                }
            }
        }
    }
}
