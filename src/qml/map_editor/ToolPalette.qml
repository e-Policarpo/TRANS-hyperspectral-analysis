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

// Tool Palette for Map Editor
// Provides tool selection buttons for map interaction modes

Rectangle {
    id: toolPalette

    property string currentTool: "pointer"

    // Signals
    signal toolSelected(string toolName)
    signal selectAllRequested()
    signal clearSelectionRequested()
    signal filterRequested(string filterType, var params)

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentPurple: mainWin ? mainWin.accentPurple : "#9B4F96"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"
    property string monoFont: mainWin ? mainWin.fontFamilyMono : (Qt.platform.os === "osx" ? "Menlo" : "Consolas")

    color: bgMedium
    width: 52
    radius: 6

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 4
        spacing: 2

        // Section: Interaction Tools
        Label {
            text: "Tools"
            font.pixelSize: 9
            font.bold: true
            color: textMuted
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            Layout.topMargin: 4
        }

        // Pointer Tool
        ToolPaletteButton {
            id: pointerTool
            toolName: "pointer"
            iconText: "P"
            tooltipText: "Pointer - Click to view spectrum"
            isActive: currentTool === "pointer"
            onClicked: selectTool("pointer")
        }

        // Block Select Tool (TRANS_v3 style)
        ToolPaletteButton {
            id: blockSelectTool
            toolName: "block_select"
            iconText: "B"
            tooltipText: "Block Select - Toggle block selection"
            isActive: currentTool === "block_select"
            onClicked: selectTool("block_select")
        }

        // Line Profile Tool
        ToolPaletteButton {
            id: profileTool
            toolName: "line_profile"
            iconText: "L"
            tooltipText: "Line Profile - Drag to draw profile"
            isActive: currentTool === "line_profile"
            onClicked: selectTool("line_profile")
        }

        // Crosshair Tool
        ToolPaletteButton {
            id: crosshairTool
            toolName: "crosshair"
            iconText: "+"
            tooltipText: "Crosshair - Interactive position cursor"
            isActive: currentTool === "crosshair"
            onClicked: selectTool("crosshair")
        }

        // Point Inspector
        ToolPaletteButton {
            id: inspectorTool
            toolName: "point_inspector"
            iconText: "i"
            tooltipText: "Point Inspector - Click for point info"
            isActive: currentTool === "point_inspector"
            onClicked: selectTool("point_inspector")
        }

        // Zoom Rectangle
        ToolPaletteButton {
            id: zoomTool
            toolName: "zoom_rect"
            iconText: "Z"
            tooltipText: "Zoom Rectangle - Draw to zoom"
            isActive: currentTool === "zoom_rect"
            onClicked: selectTool("zoom_rect")
        }

        // Rectangle Select
        ToolPaletteButton {
            id: rectSelectTool
            toolName: "rect_select"
            iconText: "R"
            tooltipText: "Rectangle Select - Select region"
            isActive: currentTool === "rect_select"
            onClicked: selectTool("rect_select")
        }

        // Measure Tool
        ToolPaletteButton {
            id: measureTool
            toolName: "measure"
            iconText: "M"
            tooltipText: "Measure - Distance measurement"
            isActive: currentTool === "measure"
            onClicked: selectTool("measure")
        }

        // Smooth/Filter Tool
        ToolPaletteButton {
            id: filterTool
            toolName: "filter"
            iconText: "S"
            tooltipText: "Smooth - Gaussian/Median filter"
            isActive: false
            onClicked: filterDialog.open()
        }

        // Level/Flatten Tool
        ToolPaletteButton {
            id: levelTool
            toolName: "level"
            iconText: "F"
            tooltipText: "Flatten - Plane / Polynomial / Facet leveling, Row align"
            isActive: false
            onClicked: levelDialog.open()
        }

        Item { Layout.fillHeight: true }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: borderColor
            Layout.topMargin: 4
            Layout.bottomMargin: 4
        }

        // Section: Selection Actions
        Label {
            text: "Select"
            font.pixelSize: 9
            font.bold: true
            color: textMuted
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
        }

        // Select All Button
        Button {
            id: selectAllBtn
            text: "All"
            Layout.preferredWidth: 44
            Layout.preferredHeight: 28
            Layout.alignment: Qt.AlignHCenter

            ToolTip.text: "Select All Blocks"
            ToolTip.visible: hovered
            ToolTip.delay: 500

            onClicked: selectAllRequested()

            background: Rectangle {
                color: parent.pressed ? accentBlue : (parent.hovered ? bgLight : bgDark)
                radius: 4
                border.color: borderColor
                border.width: 1
                opacity: parent.pressed ? 0.7 : 1
            }

            contentItem: Text {
                text: parent.text
                font.pixelSize: 11
                color: textLight
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

        // Clear Selection Button
        Button {
            id: clearBtn
            text: "Clear"
            Layout.preferredWidth: 44
            Layout.preferredHeight: 28
            Layout.alignment: Qt.AlignHCenter

            ToolTip.text: "Clear Selection"
            ToolTip.visible: hovered
            ToolTip.delay: 500

            onClicked: clearSelectionRequested()

            background: Rectangle {
                color: parent.pressed ? accentPink : (parent.hovered ? bgLight : bgDark)
                radius: 4
                border.color: borderColor
                border.width: 1
                opacity: parent.pressed ? 0.7 : 1
            }

            contentItem: Text {
                text: parent.text
                font.pixelSize: 11
                color: textLight
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

    }

    // Filter Dialog
    Dialog {
        id: filterDialog
        title: "Image Smoothing"
        modal: true
        width: 280
        x: (parent.width - width) / 2 + 100
        y: (parent.height - height) / 2

        background: Rectangle {
            color: bgMedium
            border.color: accentBlue
            border.width: 1
            radius: 6
        }

        header: Rectangle {
            height: 36
            color: bgDark
            radius: 6

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: parent.radius
                color: parent.color
            }

            Label {
                anchors.centerIn: parent
                text: "Image Smoothing"
                font.pixelSize: 13
                font.bold: true
                color: textLight
            }
        }

        contentItem: ColumnLayout {
            spacing: 12

            // Filter type selector
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Label {
                    text: "Filter Type"
                    font.pixelSize: 11
                    color: textMuted
                }

                ComboBox {
                    id: filterTypeCombo
                    Layout.fillWidth: true
                    model: ["Gaussian", "Median"]
                    currentIndex: 0

                    background: Rectangle {
                        color: bgDark
                        border.color: borderColor
                        radius: 4
                    }

                    contentItem: Text {
                        text: filterTypeCombo.displayText
                        color: textLight
                        font.pixelSize: 11
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 8
                    }
                }
            }

            // Size/Sigma control
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Label {
                    text: filterTypeCombo.currentIndex === 0 ? "Sigma (pixels)" : "Window Size"
                    font.pixelSize: 11
                    color: textMuted
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Slider {
                        id: filterSizeSlider
                        Layout.fillWidth: true
                        from: filterTypeCombo.currentIndex === 0 ? 0.5 : 3
                        to: filterTypeCombo.currentIndex === 0 ? 10 : 15
                        value: filterTypeCombo.currentIndex === 0 ? 1.0 : 3
                        stepSize: filterTypeCombo.currentIndex === 0 ? 0.5 : 2

                        background: Rectangle {
                            x: filterSizeSlider.leftPadding
                            y: filterSizeSlider.topPadding + filterSizeSlider.availableHeight / 2 - height / 2
                            width: filterSizeSlider.availableWidth
                            height: 4
                            radius: 2
                            color: bgDark

                            Rectangle {
                                width: filterSizeSlider.visualPosition * parent.width
                                height: parent.height
                                color: accentBlue
                                radius: 2
                            }
                        }

                        handle: Rectangle {
                            x: filterSizeSlider.leftPadding + filterSizeSlider.visualPosition * (filterSizeSlider.availableWidth - width)
                            y: filterSizeSlider.topPadding + filterSizeSlider.availableHeight / 2 - height / 2
                            width: 16
                            height: 16
                            radius: 8
                            color: filterSizeSlider.pressed ? accentBlue : textLight
                            border.color: accentBlue
                        }
                    }

                    Label {
                        text: filterTypeCombo.currentIndex === 0 ?
                              filterSizeSlider.value.toFixed(1) :
                              filterSizeSlider.value.toFixed(0)
                        font.pixelSize: 11
                        font.family: monoFont
                        color: accentBlue
                        Layout.preferredWidth: 30
                    }
                }
            }

            // Info text
            Label {
                text: filterTypeCombo.currentIndex === 0 ?
                      "Gaussian: Smooth with bell curve weighting" :
                      "Median: Remove noise while preserving edges"
                font.pixelSize: 10
                color: Qt.darker(textMuted, 1.2)
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
        }

        footer: DialogButtonBox {
            background: Rectangle { color: "transparent" }

            Button {
                text: "Apply"
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole

                background: Rectangle {
                    color: parent.pressed ? Qt.darker(accentBlue, 1.2) : (parent.hovered ? accentBlue : bgLight)
                    radius: 4
                }

                contentItem: Text {
                    text: parent.text
                    font.pixelSize: 11
                    color: textLight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Button {
                text: "Cancel"
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole

                background: Rectangle {
                    color: parent.hovered ? bgLight : bgDark
                    radius: 4
                    border.color: borderColor
                }

                contentItem: Text {
                    text: parent.text
                    font.pixelSize: 11
                    color: textLight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        onAccepted: {
            var filterType = filterTypeCombo.currentIndex === 0 ? "gaussian_filter" : "median_filter"
            var params = {}

            if (filterTypeCombo.currentIndex === 0) {
                params.sigma = filterSizeSlider.value
            } else {
                params.size = Math.round(filterSizeSlider.value)
            }

            filterRequested(filterType, params)
        }
    }

    // Level / Flatten Dialog
    Dialog {
        id: levelDialog
        title: "Flatten / Level"
        modal: true
        width: 300
        x: (parent.width - width) / 2 + 100
        y: (parent.height - height) / 2
        standardButtons: Dialog.Apply | Dialog.Close

        background: Rectangle {
            color: bgMedium
            border.color: accentBlue
            border.width: 1
            radius: 6
        }

        // Combo index → backend operation name.
        readonly property var levelOps: [
            "plane_level", "poly_level", "facet_level", "row_align"
        ]

        contentItem: ColumnLayout {
            spacing: 10

            Label {
                text: "Background subtraction / surface leveling for the active channel."
                color: textMuted
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                Layout.preferredWidth: 260
                font.pixelSize: 11
            }

            Label { text: "Method"; color: textLight; font.bold: true }

            ComboBox {
                id: levelMethodCombo
                Layout.fillWidth: true
                model: [
                    "Plane Level (least-squares plane)",
                    "Polynomial Plane Correction",
                    "Facet Reorientation (dominant facet)",
                    "Row Align (median line correction)"
                ]
            }

            // Polynomial order — only for the polynomial method.
            RowLayout {
                Layout.fillWidth: true
                visible: levelMethodCombo.currentIndex === 1
                Label { text: "Polynomial order:"; color: textLight }
                SpinBox {
                    id: polyOrderSpin
                    from: 1; to: 6; value: 2
                }
                Item { Layout.fillWidth: true }
            }

            Label {
                Layout.fillWidth: true
                Layout.preferredWidth: 260
                wrapMode: Text.Wrap
                color: accentPurple
                font.pixelSize: 10
                text: {
                    switch (levelMethodCombo.currentIndex) {
                    case 0: return "Fits and subtracts a single tilted plane."
                    case 1: return "Subtracts a fitted polynomial surface — removes gentle bowing / scanner creep. Higher order = more flexible."
                    case 2: return "Levels so the most common surface facet is horizontal; robust to steps and spikes that pull a plane fit off true."
                    case 3: return "Subtracts the median of each row — removes line-to-line drift streaks."
                    default: return ""
                    }
                }
            }
        }

        onApplied: {
            var op = levelDialog.levelOps[levelMethodCombo.currentIndex]
            var params = {}
            if (op === "poly_level") params.order = polyOrderSpin.value
            filterRequested(op, params)
        }
    }

    // Internal function to handle tool selection
    function selectTool(toolName) {
        currentTool = toolName
        toolSelected(toolName)
    }

    // Tool Button Component
    component ToolPaletteButton: Button {
        id: toolBtn

        property string toolName: ""
        property string iconText: ""
        property string tooltipText: ""
        property bool isActive: false

        Layout.preferredWidth: 44
        Layout.preferredHeight: 40
        Layout.alignment: Qt.AlignHCenter

        checkable: true
        checked: isActive

        ToolTip.text: tooltipText
        ToolTip.visible: hovered && tooltipText !== ""
        ToolTip.delay: 500

        background: Rectangle {
            color: {
                if (toolBtn.isActive) return accentBlue
                if (toolBtn.pressed) return bgLight
                if (toolBtn.hovered) return bgLight
                return bgDark
            }
            radius: 4
            border.color: toolBtn.isActive ? accentBlue : borderColor
            border.width: toolBtn.isActive ? 2 : 1
            opacity: toolBtn.isActive ? 0.8 : 1

            Behavior on color { ColorAnimation { duration: 100 } }
        }

        contentItem: Text {
            text: toolBtn.iconText
            font.pixelSize: 16
            font.bold: toolBtn.isActive
            color: toolBtn.isActive ? textLight : textMuted
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }
}
