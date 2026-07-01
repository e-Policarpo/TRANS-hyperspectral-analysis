/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * CollapsibleSection - a right-panel section with a header that collapses
 * (chevron button) and a bottom handle that drag-resizes the body height.
 * Used to build the single scrolling right panel of the map editor (item 4).
 * Made by Eduarda Policarpo, with love
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: section

    // Public API
    property string title: ""
    property bool collapsed: false
    property int bodyHeight: 200          // resizable body height when expanded
    property int minBodyHeight: 48
    property int maxBodyHeight: 1200
    property alias headerColor: header.color

    // A single child panel is reparented into the body and filled.
    default property alias content: body.data

    // Theme
    property var mainWin: ApplicationWindow.window
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"

    readonly property int headerHeight: 26
    readonly property int handleHeight: 6

    Layout.fillWidth: true
    Layout.preferredHeight: headerHeight + (collapsed ? 0 : bodyHeight + handleHeight)

    Behavior on Layout.preferredHeight {
        NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
    }

    Column {
        anchors.fill: parent
        spacing: 0

        // --- Header (doubles as the section separator) -------------------
        Rectangle {
            id: header
            width: parent.width
            height: headerHeight
            color: bgMedium
            border.color: borderColor
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                spacing: 6

                // Collapse / expand chevron
                Label {
                    text: collapsed ? "▶" : "▼"
                    font.pixelSize: 10
                    color: accentPink
                }

                Label {
                    text: section.title
                    font.pixelSize: 11
                    font.bold: true
                    color: textLight
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: section.collapsed = !section.collapsed
            }
        }

        // --- Body (holds the one child panel) ----------------------------
        Item {
            id: body
            width: parent.width
            height: collapsed ? 0 : bodyHeight
            visible: !collapsed
            clip: true
        }

        // --- Resize handle (drag to change bodyHeight) -------------------
        Rectangle {
            id: handle
            width: parent.width
            height: handleHeight
            visible: !collapsed
            color: dragArea.containsMouse || dragArea.pressed ? accentPink : borderColor

            // Grip dots
            Row {
                anchors.centerIn: parent
                spacing: 3
                Repeater {
                    model: 3
                    Rectangle {
                        width: 2; height: 2; radius: 1
                        color: dragArea.containsMouse || dragArea.pressed
                               ? section.bgMedium : section.bgLight
                    }
                }
            }

            MouseArea {
                id: dragArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.SizeVerCursor
                property real _startY: 0
                property int _startH: 0
                onPressed: function(mouse) {
                    _startY = mouse.y
                    _startH = section.bodyHeight
                }
                onPositionChanged: function(mouse) {
                    if (!pressed) return
                    var h = _startH + (mouse.y - _startY)
                    section.bodyHeight = Math.max(section.minBodyHeight,
                                                  Math.min(section.maxBodyHeight, h))
                }
            }
        }
    }
}
