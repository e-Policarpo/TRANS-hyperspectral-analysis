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

// Debug console for showing log messages and feedback
Rectangle {
    id: debugConsoleRoot

    color: bgDarker
    border.color: borderColor
    border.width: 1
    radius: 6

    property int maxLines: 1000
    property alias text: consoleText.text

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgLight: mainWin ? mainWin.bgLight : "#2d2d3e"
    property color textLight: mainWin ? mainWin.textLight : "#e0e0e0"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"
    property string monoFont: mainWin ? mainWin.fontFamilyMono : (Qt.platform.os === "osx" ? "Menlo" : "Consolas")
    property color accentGreen: "#b3ffb3"   // Keep log-specific colors
    property color accentRed: "#ffb3b3"
    property color accentYellow: "#ffffb3"

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: bgDark

            RowLayout {
                anchors.fill: parent
                anchors.margins: 5
                spacing: 10

                Text {
                    text: "Debug Console"
                    font.pixelSize: 12
                    font.bold: true
                    color: textLight
                    Layout.fillWidth: true
                }

                Button {
                    text: "Clear"
                    Layout.preferredHeight: 24
                    font.pixelSize: 11

                    onClicked: debugConsoleRoot.clear()

                    background: Rectangle {
                        color: parent.pressed ? accentPink : (parent.hovered ? bgLight : "transparent")
                        border.color: borderColor
                        border.width: 1
                        radius: 3
                    }

                    contentItem: Text {
                        text: parent.text
                        font: parent.font
                        color: textLight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Button {
                    text: "Copy"
                    Layout.preferredHeight: 24
                    font.pixelSize: 11

                    onClicked: {
                        consoleText.selectAll()
                        consoleText.copy()
                        consoleText.deselect()
                        logMessage("Copied to clipboard", "info")
                    }

                    background: Rectangle {
                        color: parent.pressed ? accentPink : (parent.hovered ? bgLight : "transparent")
                        border.color: borderColor
                        border.width: 1
                        radius: 3
                    }

                    contentItem: Text {
                        text: parent.text
                        font: parent.font
                        color: textLight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        // Console output area
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            TextArea {
                id: consoleText
                readOnly: true
                wrapMode: TextArea.Wrap
                selectByMouse: true
                font.family: monoFont
                font.pixelSize: 11
                color: textLight

                background: Rectangle {
                    color: bgDark
                }
            }
        }
    }

    function log(message, level) {
        logMessage(message, level)
    }

    function logMessage(message, level) {
        var timestamp = Qt.formatDateTime(new Date(), "HH:mm:ss")
        var prefix = ""
        var colorCode = ""

        switch(level) {
            case "info":
                prefix = "[INFO]"
                colorCode = "#5BCEFA"  // Blue
                break
            case "success":
                prefix = "[SUCCESS]"
                colorCode = "#b3ffb3"  // Green
                break
            case "warning":
                prefix = "[WARNING]"
                colorCode = "#ffffb3"  // Yellow
                break
            case "error":
                prefix = "[ERROR]"
                colorCode = "#ffb3b3"  // Red
                break
            default:
                prefix = "[LOG]"
                colorCode = "#e0e0e0"  // Light gray
        }

        var logLine = timestamp + " " + prefix + " " + message + "\n"
        consoleText.append(logLine)

        // Auto-scroll to bottom
        consoleText.cursorPosition = consoleText.length

        // Limit number of lines
        trimLines()
    }

    function clear() {
        consoleText.text = ""
        logMessage("Console cleared", "info")
    }

    function trimLines() {
        var lines = consoleText.text.split("\n")
        if (lines.length > maxLines) {
            var linesToRemove = lines.length - maxLines
            lines.splice(0, linesToRemove)
            consoleText.text = lines.join("\n")
        }
    }

    // Connect to backend signals
    Connections {
        target: backend

        function onStatusChanged(status) {
            debugConsoleRoot.logMessage(status, "info")
        }

        function onDataLoaded(datasetName) {
            debugConsoleRoot.logMessage("Data loaded: " + datasetName, "success")
        }

        function onErrorOccurred(title, message) {
            debugConsoleRoot.logMessage(title + ": " + message, "error")
        }

        function onToolOpened(toolName) {
            debugConsoleRoot.logMessage("Opened tool: " + toolName, "info")
        }

        function onToolCompleted(toolName, outputPath) {
            debugConsoleRoot.logMessage("Tool completed: " + toolName + " -> " + outputPath, "success")
        }

        function onProjectLoaded(projectPath) {
            debugConsoleRoot.logMessage("Project loaded: " + projectPath, "success")
        }

        function onProjectSaved(projectPath) {
            debugConsoleRoot.logMessage("Project saved: " + projectPath, "success")
        }


        function onWindowClosed(windowType, windowId) {
            debugConsoleRoot.logMessage("Closed " + windowType + ": " + windowId, "info")
        }
    }

    Component.onCompleted: {
        logMessage("Debug console initialized", "info")
        logMessage("Application: TRANS-QML", "info")
    }
}
