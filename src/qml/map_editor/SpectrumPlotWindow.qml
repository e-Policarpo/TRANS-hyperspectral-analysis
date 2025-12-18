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
import Qt.labs.platform 1.1 as Platform
import TransQML 1.0

// Spectrum Plot Window - Displays spectra from map pixel selection
// Supports multiple curves and can be opened multiple times

Window {
    id: plotWindow

    property string datasetName: ""
    property var spectra: []  // Array of spectrum objects {x, y, x_name, y_name, title, row, col}

    title: datasetName ? "Spectrum: " + datasetName : "Spectrum Plot"
    width: 700
    height: 500
    minimumWidth: 400
    minimumHeight: 300

    color: bgDark

    // Theme colors - find main window for reactive bindings
    property var mainWin: null

    function findMainWindow() {
        for (var i = 0; i < Qt.application.allWindows.length; i++) {
            var win = Qt.application.allWindows[i]
            if (win.objectName === "mainWindow" || (win !== plotWindow && win.bgDark !== undefined)) {
                mainWin = win
                break
            }
        }
    }

    Component.onCompleted: {
        findMainWindow()
    }

    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 0
        spacing: 0

        // Toolbar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            color: bgMedium

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                Label {
                    text: datasetName
                    font.pixelSize: 12
                    font.bold: true
                    color: accentPink
                }

                Label {
                    text: "(" + spectra.length + " curve" + (spectra.length !== 1 ? "s" : "") + ")"
                    font.pixelSize: 11
                    color: textMuted
                }

                Item { Layout.fillWidth: true }

                // Show Average toggle
                CheckBox {
                    id: showAverageCheck
                    text: "Show Average"
                    font.pixelSize: 10
                    checked: false

                    indicator: Rectangle {
                        implicitWidth: 14
                        implicitHeight: 14
                        x: showAverageCheck.leftPadding
                        y: parent.height / 2 - height / 2
                        radius: 2
                        border.color: "#5BCEFA"
                        color: showAverageCheck.checked ? "#5BCEFA" : bgDark

                        Text {
                            anchors.centerIn: parent
                            text: "\u2713"
                            color: bgDark
                            font.pixelSize: 10
                            visible: showAverageCheck.checked
                        }
                    }

                    contentItem: Text {
                        text: showAverageCheck.text
                        font: showAverageCheck.font
                        color: textLight
                        leftPadding: showAverageCheck.indicator.width + 4
                        verticalAlignment: Text.AlignVCenter
                    }

                    onCheckedChanged: plotSpectra()
                }

                // Separator
                Rectangle {
                    width: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 8
                    Layout.bottomMargin: 8
                    color: borderColor
                }

                // Export button
                Button {
                    text: "Export CSV"
                    font.pixelSize: 10
                    Layout.preferredHeight: 26

                    background: Rectangle {
                        color: parent.hovered ? bgLight : bgDark
                        border.color: borderColor
                        radius: 3
                    }

                    contentItem: Text {
                        text: parent.text
                        font: parent.font
                        color: textLight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: exportDialog.open()
                }

                // Clear button
                Button {
                    text: "Clear"
                    font.pixelSize: 10
                    Layout.preferredHeight: 26

                    background: Rectangle {
                        color: parent.hovered ? bgLight : bgDark
                        border.color: borderColor
                        radius: 3
                    }

                    contentItem: Text {
                        text: parent.text
                        font: parent.font
                        color: textLight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: {
                        spectra = []
                        showAverageCheck.checked = false
                        profileCanvas.clearProfile()
                    }
                }
            }
        }

        // Plot canvas
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark

            ProfileCanvas {
                id: profileCanvas
                anchors.fill: parent
                anchors.margins: 4

                Component.onCompleted: {
                    if (spectra.length > 0) {
                        plotSpectra()
                    }
                }
            }

            // Empty state
            Rectangle {
                anchors.fill: parent
                color: bgDark
                visible: spectra.length === 0

                Label {
                    anchors.centerIn: parent
                    text: "No spectra to display"
                    font.pixelSize: 14
                    color: textMuted
                }
            }
        }

        // Legend / curve list
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: spectra.length > 0 ? (showAverageCheck.checked ? 48 : Math.min(100, 28 + spectra.length * 20)) : 0
            visible: spectra.length > 0
            color: bgMedium

            ScrollView {
                anchors.fill: parent
                anchors.margins: 4
                clip: true

                ColumnLayout {
                    width: parent.width
                    spacing: 2

                    Label {
                        text: showAverageCheck.checked ? "Average of " + spectra.length + " curves:" : "Curves:"
                        font.pixelSize: 10
                        font.bold: true
                        color: textMuted
                    }

                    // Show average indicator when in average mode
                    RowLayout {
                        visible: showAverageCheck.checked
                        Layout.fillWidth: true
                        spacing: 8

                        Rectangle {
                            width: 12
                            height: 3
                            color: "#5BCEFA"
                            radius: 1
                        }

                        Label {
                            text: "Average (" + spectra.length + " spectra)"
                            font.pixelSize: 10
                            font.bold: true
                            color: "#5BCEFA"
                            Layout.fillWidth: true
                        }
                    }

                    // Show individual curves when not in average mode
                    Repeater {
                        model: showAverageCheck.checked ? [] : spectra

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Rectangle {
                                width: 12
                                height: 3
                                color: getColorForIndex(index)
                                radius: 1
                            }

                            Label {
                                text: modelData.title || ("(" + modelData.row + ", " + modelData.col + ")")
                                font.pixelSize: 10
                                color: textLight
                                Layout.fillWidth: true
                                elide: Text.ElideMiddle
                            }
                        }
                    }
                }
            }
        }

        // Status bar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            color: "#0d0d1a"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 16

                Label {
                    id: cursorLabel
                    text: "X: -, Y: -"
                    font.pixelSize: 10
                    font.family: "monospace"
                    color: textMuted
                }

                Item { Layout.fillWidth: true }

                Label {
                    text: spectra.length > 0 && spectra[0].x ?
                          spectra[0].x.length + " points" : ""
                    font.pixelSize: 10
                    color: textMuted
                }
            }
        }
    }

    // Export dialog
    Loader {
        id: exportDialog
        active: false
        sourceComponent: Component {
            Platform.FileDialog {
                title: "Export Spectra as CSV"
                nameFilters: ["CSV Files (*.csv)"]
                fileMode: Platform.FileDialog.SaveFile
                onAccepted: {
                    var path = file.toString()
                    if (path.startsWith("file://")) path = path.substring(7)
                    exportToCsv(path)
                    exportDialog.active = false
                }
                onRejected: exportDialog.active = false
                Component.onCompleted: open()
            }
        }
        function open() { active = true }
    }

    // Color palette for multiple curves
    function getColorForIndex(index) {
        var colors = [
            "#F5A9B8",  // pink
            "#5BCEFA",  // blue
            "#66ff99",  // green
            "#FFB7C5",  // orange
            "#cc66ff",  // purple
            "#D60270",  // red
            "#66ffff",  // cyan
            "#ffff66"   // yellow
        ]
        return colors[index % colors.length]
    }

    // Plot all spectra
    function plotSpectra() {
        if (spectra.length === 0) return

        // Clear previous plots
        profileCanvas.clearProfile()

        // Use first spectrum for axis labels
        var first = spectra[0]
        profileCanvas.setAxisLabels(first.x_name || "X", first.y_name || "Intensity")

        // If showing average only
        if (showAverageCheck.checked && spectra.length > 1) {
            // Calculate average
            var avgY = calculateAverageY()
            if (avgY) {
                profileCanvas.setProfileData(first.x, avgY)
                // Set the line color to gold/yellow for average
                profileCanvas.lineColor = "#5BCEFA"
            }
        } else {
            // Plot first curve
            if (first.x && first.y) {
                profileCanvas.setProfileData(first.x, first.y)
            }

            // Add additional curves
            for (var i = 1; i < spectra.length; i++) {
                var s = spectra[i]
                if (s.x && s.y) {
                    profileCanvas.addCurveSimple(s.x, s.y, getColorForIndex(i))
                }
            }

            // If show average is checked, also add average as an additional curve
            if (showAverageCheck.checked && spectra.length === 1) {
                // Only one spectrum, nothing to average
            }
        }
    }

    // Calculate average Y values across all spectra
    function calculateAverageY() {
        if (spectra.length === 0) return null
        if (spectra.length === 1) return spectra[0].y

        var numPoints = spectra[0].y.length
        var avgY = []

        for (var i = 0; i < numPoints; i++) {
            var sum = 0
            var count = 0
            for (var j = 0; j < spectra.length; j++) {
                if (spectra[j].y && i < spectra[j].y.length) {
                    sum += spectra[j].y[i]
                    count++
                }
            }
            avgY.push(count > 0 ? sum / count : 0)
        }

        return avgY
    }

    // Add a spectrum to the plot
    function addSpectrum(spectrum) {
        spectra.push(spectrum)
        spectra = spectra  // Trigger update
        plotSpectra()
    }

    // Set spectra data
    function setSpectra(newSpectra) {
        spectra = newSpectra
        if (spectra.length > 0) {
            plotSpectra()
        }
    }

    // Export to CSV
    function exportToCsv(path) {
        if (spectra.length === 0) return

        // Build CSV content
        var csv = ""

        // Header
        var headers = [spectra[0].x_name || "X"]
        for (var i = 0; i < spectra.length; i++) {
            headers.push(spectra[i].title || "Y" + (i + 1))
        }
        csv += headers.join(",") + "\n"

        // Data rows
        var numPoints = spectra[0].x.length
        for (var row = 0; row < numPoints; row++) {
            var rowData = [spectra[0].x[row]]
            for (var col = 0; col < spectra.length; col++) {
                rowData.push(spectra[col].y[row])
            }
            csv += rowData.join(",") + "\n"
        }

        // Write to file (would need backend support)
        console.log("Export CSV to:", path, "- Content length:", csv.length)
        // TODO: Call backend to write file
    }

    // Update on spectra change
    onSpectraChanged: {
        if (visible && spectra.length > 0) {
            plotSpectra()
        }
    }

    Component.onCompleted: {
        if (spectra.length > 0) {
            plotSpectra()
        }
    }
}
