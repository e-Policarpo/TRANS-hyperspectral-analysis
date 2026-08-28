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
    property color bgDarker: (mainWin && mainWin.bgDarker !== undefined) ? mainWin.bgDarker : Theme.bgDarker
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor
    property string monoFont: mainWin ? mainWin.fontFamilyMono : (Qt.platform.os === "osx" ? "Menlo" : "Consolas")
    // Log severity. The hues are semantic and stay — green is "it worked",
    // red is "it did not" — but they come from the scheme rather than
    // being three pastels mixed for one dark console: every scheme carries
    // a `success` and an `error` key, published here as successColor and
    // accentMagenta, and on a light scheme those are readable where
    // #b3ffb3 and #ffb3b3 are not. Amber has no home on Theme yet, so the
    // warning colour is still spelled out; it wants a `warningColor` on
    // the singleton in the pass that adds one.
    property color accentGreen: (mainWin && mainWin.successColor !== undefined) ? mainWin.successColor : Theme.successColor
    property color accentRed: (mainWin && mainWin.accentMagenta !== undefined) ? mainWin.accentMagenta : Theme.accentMagenta
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
