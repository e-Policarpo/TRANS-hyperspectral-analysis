/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * DatasetComboBox - Dynamic sizing ComboBox with rolling text on hover
 * Made by Eduarda Policarpo, with love
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ComboBox {
    id: root

    // Configuration
    property int minimumWidth: 180
    property int maximumWidth: 400
    property int hoverDelay: 400  // ms before rolling starts
    property int rollSpeed: 50    // pixels per second
    property string placeholderText: "Select dataset..."

    // Theme colors
    property color bgColor: "#3a3a4e"
    property color borderColorNormal: "#9B4F96"
    property color borderColorFocus: "#F5A9B8"
    property color textColor: "#ffffff"
    property color textMutedColor: "#cccccc"

    // Calculate optimal width based on model content.
    // Measured via FontMetrics.advanceWidth(text) — a plain function call.
    // (Writing TextMetrics.text inside this binding and reading its
    // advanceWidth back created a binding loop that re-walked the whole
    // model over and over — very costly with many datasets loaded.)
    property int calculatedWidth: {
        var maxWidth = minimumWidth
        if (model) {
            for (var i = 0; i < model.length; i++) {
                var textWidth = fontMetrics.advanceWidth(model[i]) + 50  // padding + arrow
                if (textWidth > maxWidth) {
                    maxWidth = textWidth
                }
            }
        }
        return Math.min(maxWidth, maximumWidth)
    }

    // Font metrics for measuring
    FontMetrics {
        id: fontMetrics
        font: root.font
    }

    implicitWidth: calculatedWidth
    Layout.minimumWidth: minimumWidth
    Layout.preferredWidth: calculatedWidth

    displayText: currentIndex >= 0 ? currentText : placeholderText

    background: Rectangle {
        color: bgColor
        border.color: root.activeFocus ? borderColorFocus : borderColorNormal
        border.width: 1
        radius: 4
    }

    contentItem: Item {
        implicitHeight: 30

        // Clipping container for rolling text
        Item {
            id: textContainer
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 30  // Space for dropdown arrow
            clip: true

            Text {
                id: displayTextItem
                text: root.displayText
                font: root.font
                color: root.currentIndex >= 0 ? textColor : textMutedColor
                verticalAlignment: Text.AlignVCenter
                height: parent.height

                // Animation for rolling text
                property bool shouldRoll: displayTextItem.implicitWidth > textContainer.width
                property bool isHovered: hoverArea.containsMouse
                property bool isRolling: false

                x: 0

                Behavior on x {
                    enabled: displayTextItem.isRolling
                    NumberAnimation {
                        duration: Math.abs(displayTextItem.x) / rollSpeed * 1000
                        easing.type: Easing.Linear
                    }
                }

                // Timer for hover delay before rolling
                Timer {
                    id: rollDelayTimer
                    interval: hoverDelay
                    repeat: false
                    onTriggered: {
                        if (displayTextItem.shouldRoll && displayTextItem.isHovered) {
                            displayTextItem.isRolling = true
                            displayTextItem.x = -(displayTextItem.implicitWidth - textContainer.width + 20)
                        }
                    }
                }

                // Timer for resetting after roll completes
                Timer {
                    id: resetTimer
                    interval: 1500  // Pause at end before reset
                    repeat: false
                    onTriggered: {
                        displayTextItem.isRolling = false
                        displayTextItem.x = 0
                        // Restart rolling if still hovered
                        if (displayTextItem.isHovered && displayTextItem.shouldRoll) {
                            rollDelayTimer.restart()
                        }
                    }
                }

                onXChanged: {
                    // When roll animation completes, start reset timer
                    if (isRolling && x <= -(implicitWidth - textContainer.width + 20)) {
                        resetTimer.start()
                    }
                }

                onIsHoveredChanged: {
                    if (isHovered && shouldRoll) {
                        rollDelayTimer.start()
                    } else {
                        rollDelayTimer.stop()
                        resetTimer.stop()
                        isRolling = false
                        x = 0
                    }
                }
            }
        }

        // Mouse area for hover detection
        MouseArea {
            id: hoverArea
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.NoButton  // Pass clicks to ComboBox
            propagateComposedEvents: true
        }
    }

    // Dropdown indicator
    indicator: Canvas {
        id: canvas
        x: root.width - width - 8
        y: (root.height - height) / 2
        width: 12
        height: 8
        contextType: "2d"

        Connections {
            target: root
            function onPressedChanged() { canvas.requestPaint() }
        }

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.moveTo(0, 0)
            ctx.lineTo(width, 0)
            ctx.lineTo(width / 2, height)
            ctx.closePath()
            ctx.fillStyle = root.pressed ? borderColorFocus : textMutedColor
            ctx.fill()
        }
    }

    // Popup styling with dynamic width
    popup: Popup {
        y: root.height
        width: Math.max(root.width, popupContentWidth)
        implicitHeight: contentItem.implicitHeight + 2
        padding: 1

        property int popupContentWidth: {
            var maxW = root.width
            if (root.model) {
                for (var i = 0; i < root.model.length; i++) {
                    var itemW = fontMetrics.advanceWidth(root.model[i]) + 30
                    if (itemW > maxW) maxW = itemW
                }
            }
            return Math.min(maxW, maximumWidth + 50)
        }

        background: Rectangle {
            color: bgColor
            border.color: borderColorNormal
            border.width: 1
            radius: 4
        }

        contentItem: ListView {
            id: listView
            clip: true
            implicitHeight: Math.min(contentHeight, 300)
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            ScrollBar.vertical: ScrollBar { }
        }
    }

    // Delegate for dropdown items with rolling text
    delegate: ItemDelegate {
        id: delegateItem
        width: root.popup.width - 2
        height: 32

        required property int index
        required property var modelData

        contentItem: Item {
            anchors.fill: parent

            // Clipping container for delegate rolling text
            Item {
                id: delegateTextContainer
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                clip: true

                Text {
                    id: delegateText
                    text: delegateItem.modelData
                    font: root.font
                    color: delegateItem.highlighted ? textColor : textMutedColor
                    verticalAlignment: Text.AlignVCenter
                    height: parent.height

                    property bool shouldRoll: delegateText.implicitWidth > delegateTextContainer.width
                    property bool isHovered: delegateHoverArea.containsMouse
                    property bool isRolling: false

                    x: 0

                    Behavior on x {
                        enabled: delegateText.isRolling
                        NumberAnimation {
                            duration: Math.abs(delegateText.x) / rollSpeed * 1000
                            easing.type: Easing.Linear
                        }
                    }

                    Timer {
                        id: delegateRollTimer
                        interval: hoverDelay
                        repeat: false
                        onTriggered: {
                            if (delegateText.shouldRoll && delegateText.isHovered) {
                                delegateText.isRolling = true
                                delegateText.x = -(delegateText.implicitWidth - delegateTextContainer.width + 10)
                            }
                        }
                    }

                    Timer {
                        id: delegateResetTimer
                        interval: 1500
                        repeat: false
                        onTriggered: {
                            delegateText.isRolling = false
                            delegateText.x = 0
                            if (delegateText.isHovered && delegateText.shouldRoll) {
                                delegateRollTimer.restart()
                            }
                        }
                    }

                    onXChanged: {
                        if (isRolling && x <= -(implicitWidth - delegateTextContainer.width + 10)) {
                            delegateResetTimer.start()
                        }
                    }

                    onIsHoveredChanged: {
                        if (isHovered && shouldRoll) {
                            delegateRollTimer.start()
                        } else {
                            delegateRollTimer.stop()
                            delegateResetTimer.stop()
                            isRolling = false
                            x = 0
                        }
                    }
                }
            }

            MouseArea {
                id: delegateHoverArea
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.NoButton
                propagateComposedEvents: true
            }
        }

        background: Rectangle {
            color: delegateItem.highlighted ? Qt.rgba(0.96, 0.66, 0.72, 0.3) : "transparent"
            radius: 2
        }

        highlighted: root.highlightedIndex === index
    }
}
