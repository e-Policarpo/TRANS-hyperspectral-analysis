/*
 * Exercise 01_01: Basic QML Application
 * Solution: Main window with title 'Hello TRANS'
 */

import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    id: mainWindow

    // Window properties
    visible: true
    width: 800
    height: 600
    title: "Hello TRANS"

    // Background color
    color: "#1a1a2e"

    // Center content
    Item {
        anchors.centerIn: parent

        Text {
            anchors.centerIn: parent
            text: "Welcome to TRANS-QML!"
            font.pixelSize: 32
            font.bold: true
            color: "#5BCEFA"
        }
    }
}
