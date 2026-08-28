/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * GraphContent - Standalone graph content component (no window frame)
 * For use inside EmbeddedWindow or as content for FloatingEntity
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import TransQML 1.0

Item {
    id: graphContent

    // Entity identification (set by parent window)
    property string entityId: ""
    property string entityTitle: "Graph"

    // Graph data
    property var curves: []  // Array of {x: [], y: [], label: "", color: ""}
    property string xLabel: "X"
    property string yLabel: "Y"
    property string graphTitle: ""

    // Link to table for bidirectional communication
    property string linkedTableId: ""

    // Access to GraphCanvas
    property var graphCanvas: canvas

    // Display options
    property bool showGrid: true
    property bool showLegend: true
    property real lineWidth: 2

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgDarker: (mainWin && mainWin.bgDarker !== undefined) ? mainWin.bgDarker : Theme.bgDarker
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color accentBlue: (mainWin && mainWin.accentBlue !== undefined) ? mainWin.accentBlue : Theme.accentBlue
    property color accentPurple: (mainWin && mainWin.accentPurple !== undefined) ? mainWin.accentPurple : Theme.accentPurple
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

    // Color palette for curves
    readonly property var colorPalette: [
        "#F5A9B8", "#5BCEFA", "#66ff66", "#FFD700", "#FF6B6B",
        "#9B4F96", "#00BCD4", "#FF9800", "#E91E63", "#2ECC71"
    ]

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Toolbar
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            Layout.margins: 4
            spacing: 4

            Button {
                text: "Reset"
                onClicked: if (canvas) canvas.resetView()
                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }
                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 10
                }
            }

            Button {
                text: "+"
                onClicked: if (canvas) canvas.zoomIn(1.2)
                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }
                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 12
                    font.bold: true
                }
            }

            Button {
                text: "-"
                onClicked: if (canvas) canvas.zoomOut(1.2)
                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }
                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 12
                    font.bold: true
                }
            }

            Rectangle { width: 1; height: 20; color: borderColor }

            CheckBox {
                id: gridCheck
                text: "Grid"
                checked: graphContent.showGrid
                onCheckedChanged: if (canvas) canvas.showGrid = checked
                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 10
                    leftPadding: parent.indicator.width + 4
                }
                indicator: Rectangle {
                    implicitWidth: 14
                    implicitHeight: 14
                    radius: 3
                    color: bgLight
                    border.color: parent.checked ? accentBlue : borderColor
                    Rectangle {
                        width: 8; height: 8; x: 3; y: 3
                        radius: 2
                        color: accentBlue
                        visible: parent.parent.checked
                    }
                }
            }

            CheckBox {
                id: legendCheck
                text: "Legend"
                checked: graphContent.showLegend
                onCheckedChanged: if (canvas) canvas.showLegend = checked
                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 10
                    leftPadding: parent.indicator.width + 4
                }
                indicator: Rectangle {
                    implicitWidth: 14
                    implicitHeight: 14
                    radius: 3
                    color: bgLight
                    border.color: parent.checked ? accentBlue : borderColor
                    Rectangle {
                        width: 8; height: 8; x: 3; y: 3
                        radius: 2
                        color: accentBlue
                        visible: parent.parent.checked
                    }
                }
            }

            Item { Layout.fillWidth: true }

            Text {
                id: cursorDisplay
                text: ""
                color: textMuted
                font.pixelSize: 10
            }
        }

        // Graph canvas with matplotlib rendering
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark

            GraphCanvas {
                id: canvas
                anchors.fill: parent
                anchors.margins: 2

                showGrid: graphContent.showGrid
                showLegend: graphContent.showLegend

                // The plot's chrome follows the scheme.
                backgroundColor: graphContent.bgDark
                foregroundColor: graphContent.textMuted
                // borderColor, not bgLight: this draws the axes frame and the
                // gridlines, and bgLight-on-bgDark measures 1.12:1 to 1.54:1 on
                // all 22 schemes — the frame came out fainter than either
                // candidate and the painted gridline at 1.02–1.08:1, i.e. no
                // visible box on any scheme. borderColor wins on 21 of the 22.
                gridColor: graphContent.borderColor

                onCursorMoved: function(x, y) {
                    cursorDisplay.text = "X: " + x.toFixed(4) + ", Y: " + y.toExponential(3)
                }

                onCurveSelected: function(curveId) {
                    console.log("Curve selected:", curveId)
                }

                Component.onCompleted: {
                    // Add initial curves if any
                    if (graphContent.curves && graphContent.curves.length > 0) {
                        for (var i = 0; i < graphContent.curves.length; i++) {
                            var curve = graphContent.curves[i]
                            canvas.addCurve(
                                curve.label || ("Curve " + (i + 1)),
                                curve.x || [],
                                curve.y || [],
                                curve.color || graphContent.colorPalette[i % graphContent.colorPalette.length],
                                2.0
                            )
                        }
                    }
                    // Set labels
                    canvas.xLabel = graphContent.xLabel
                    canvas.yLabel = graphContent.yLabel
                }
            }
        }

        // Math operations bar
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            Layout.margins: 4
            spacing: 4

            Text {
                text: "Operations:"
                color: textMuted
                font.pixelSize: 10
            }

            Repeater {
                model: ["Derivative", "Smooth", "Integrate", "FFT", "Normalize"]

                Button {
                    text: modelData
                    enabled: canvas && canvas.selectedCurveId >= 0
                    onClicked: {
                        if (canvas && canvas.selectedCurveId >= 0) {
                            var op = modelData.toLowerCase()
                            var params = {}
                            if (op === "derivative") params = {order: 1}
                            else if (op === "smooth") params = {method: "savgol", window: 11}
                            canvas.applyCurveOperation(canvas.selectedCurveId, op, params)
                        }
                    }
                    background: Rectangle {
                        color: parent.enabled ? (parent.hovered ? accentBlue : bgLight) : bgDark
                        radius: 3
                        border.color: parent.enabled ? accentBlue : borderColor
                    }
                    contentItem: Text {
                        text: parent.text
                        color: parent.enabled ? textLight : textMuted
                        font.pixelSize: 9
                    }
                }
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Clear"
                onClicked: if (canvas) canvas.clearCurves()
                background: Rectangle {
                    color: parent.hovered ? Qt.darker(accentPink, 1.3) : bgLight
                    radius: 3
                }
                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 9
                }
            }
        }
    }

    // Public API - delegates to GraphCanvas
    function addCurve(x, y, label, color) {
        if (canvas) {
            canvas.addCurve(
                label || ("Curve " + (curves.length + 1)),
                x, y,
                color || colorPalette[curves.length % colorPalette.length],
                lineWidth
            )
        } else {
            // Store for later if content not loaded yet
            var newCurve = {
                x: x,
                y: y,
                label: label || ("Curve " + (curves.length + 1)),
                color: color || colorPalette[curves.length % colorPalette.length]
            }
            curves = curves.concat([newCurve])
        }
    }

    function clearCurves() {
        curves = []
        if (canvas) {
            canvas.clearCurves()
        }
    }

    function updateCurve(index, x, y) {
        if (canvas) {
            canvas.updateCurve(index, x, y)
        }
    }

    function refresh() {
        if (canvas) {
            canvas.update()
        }
    }

    // Apply math operation to a curve
    function applyCurveOperation(curveId, operation, params) {
        if (canvas) {
            return canvas.applyCurveOperation(curveId, operation, params)
        }
        return -1
    }

    Component.onDestruction: {
        if (canvas) canvas.cleanup()
    }

    Component.onCompleted: {
        console.log("GraphContent created:", entityId)
    }
}
