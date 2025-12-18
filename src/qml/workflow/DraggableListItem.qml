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

Rectangle {
    id: dragItem

    property int itemIndex: 0
    property string itemText: ""
    property bool itemEnabled: true
    property bool isDragging: false
    property var listView: null

    // Theme colors - find parent window
    property var parentWindow: Window.window
    property color bgDark: parentWindow && parentWindow.bgDark ? parentWindow.bgDark : "#1a1a2e"
    property color bgMedium: parentWindow && parentWindow.bgMedium ? parentWindow.bgMedium : "#2a2a3e"
    property color bgLight: parentWindow && parentWindow.bgLight ? parentWindow.bgLight : "#3a3a4e"
    property color accentPink: parentWindow && parentWindow.accentPink ? parentWindow.accentPink : "#F5A9B8"
    property color accentBlue: parentWindow && parentWindow.accentBlue ? parentWindow.accentBlue : "#5BCEFA"
    property color accentGreen: "#66ff99"  // Keep status color
    property color textLight: parentWindow && parentWindow.textLight ? parentWindow.textLight : "#ffffff"
    property color textMuted: parentWindow && parentWindow.textMuted ? parentWindow.textMuted : "#cccccc"
    property color borderColor: parentWindow && parentWindow.borderColor ? parentWindow.borderColor : "#9B4F96"

    signal itemMoved(int fromIndex, int toIndex)
    signal itemEnabledToggled(int index, bool enabled)

    width: listView ? listView.width : 200
    height: 36
    color: isDragging ? bgLight : (dragArea.containsMouse ? Qt.darker(bgMedium, 1.1) : bgMedium)
    border.color: isDragging ? accentPink : borderColor
    border.width: isDragging ? 2 : 1
    radius: 4

    // Drag state
    Drag.active: dragArea.held
    Drag.source: dragItem
    Drag.hotSpot.x: width / 2
    Drag.hotSpot.y: height / 2

    RowLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 8

        // Drag handle
        Rectangle {
            Layout.preferredWidth: 20
            Layout.preferredHeight: 20
            color: "transparent"

            Column {
                anchors.centerIn: parent
                spacing: 3

                Repeater {
                    model: 3
                    Rectangle {
                        width: 12
                        height: 2
                        radius: 1
                        color: dragArea.containsMouse ? textLight : textMuted
                    }
                }
            }

            MouseArea {
                id: dragArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.SizeAllCursor

                property bool held: false
                property int startY: 0

                onPressed: function(mouse) {
                    held = true
                    startY = mouse.y
                    dragItem.isDragging = true
                    dragItem.z = 100
                }

                onReleased: {
                    held = false
                    dragItem.isDragging = false
                    dragItem.z = 0
                }

                onPositionChanged: function(mouse) {
                    if (held && listView) {
                        // Calculate new position
                        var pos = dragItem.mapToItem(listView, mouse.x, mouse.y)
                        var newIndex = Math.floor(pos.y / dragItem.height)
                        newIndex = Math.max(0, Math.min(newIndex, listView.count - 1))

                        if (newIndex !== itemIndex) {
                            itemMoved(itemIndex, newIndex)
                        }
                    }
                }
            }
        }

        // Enable checkbox
        CheckBox {
            id: enableCheck
            checked: itemEnabled

            indicator: Rectangle {
                implicitWidth: 18
                implicitHeight: 18
                radius: 3
                color: bgDark
                border.color: enableCheck.checked ? accentGreen : borderColor
                border.width: 1

                Rectangle {
                    width: 10
                    height: 10
                    anchors.centerIn: parent
                    radius: 2
                    color: accentGreen
                    visible: enableCheck.checked
                }
            }

            onCheckedChanged: {
                itemEnabledToggled(itemIndex, checked)
            }
        }

        // Item text with rolling animation
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Text {
                id: itemTextLabel
                anchors.verticalCenter: parent.verticalCenter
                text: itemText
                color: itemEnabled ? textLight : textMuted
                font.pixelSize: 11
                font.strikeout: !itemEnabled

                // Rolling animation for long text
                property bool needsRolling: implicitWidth > parent.width
                property bool isHovered: textHoverArea.containsMouse

                x: 0

                SequentialAnimation on x {
                    id: rollAnimation
                    running: itemTextLabel.needsRolling && itemTextLabel.isHovered
                    loops: Animation.Infinite

                    // Pause at start
                    PauseAnimation { duration: 1000 }

                    // Roll left
                    NumberAnimation {
                        to: -(itemTextLabel.implicitWidth - itemTextLabel.parent.width + 10)
                        duration: Math.max(2000, (itemTextLabel.implicitWidth - itemTextLabel.parent.width) * 30)
                        easing.type: Easing.Linear
                    }

                    // Pause at end
                    PauseAnimation { duration: 1000 }

                    // Roll back
                    NumberAnimation {
                        to: 0
                        duration: Math.max(1000, (itemTextLabel.implicitWidth - itemTextLabel.parent.width) * 15)
                        easing.type: Easing.Linear
                    }
                }

                // Reset position when not hovering
                onIsHoveredChanged: {
                    if (!isHovered) {
                        rollAnimation.stop()
                        x = 0
                    }
                }

                MouseArea {
                    id: textHoverArea
                    anchors.fill: parent
                    hoverEnabled: true
                    propagateComposedEvents: true
                    acceptedButtons: Qt.NoButton
                }
            }

            // Fade effect for long text
            Rectangle {
                visible: itemTextLabel.needsRolling && !itemTextLabel.isHovered
                anchors.right: parent.right
                width: 20
                height: parent.height
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 1.0; color: dragItem.color }
                }
            }
        }

        // Order indicator
        Rectangle {
            Layout.preferredWidth: 24
            Layout.preferredHeight: 20
            radius: 3
            color: bgDark

            Text {
                anchors.centerIn: parent
                text: (itemIndex + 1).toString()
                color: accentBlue
                font.pixelSize: 10
                font.bold: true
            }
        }
    }

    // Drop area for reordering
    DropArea {
        anchors.fill: parent

        onEntered: function(drag) {
            var fromItem = drag.source
            if (fromItem && fromItem !== dragItem && fromItem.itemIndex !== undefined) {
                itemMoved(fromItem.itemIndex, itemIndex)
            }
        }
    }
}
