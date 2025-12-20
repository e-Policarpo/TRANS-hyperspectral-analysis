/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * ProjectBrowserEntity - Floating entity wrapper for ProjectBrowser
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

FloatingEntity {
    id: projectBrowserEntity

    entityType: "browser"
    entityTitle: "Project Browser"
    minWidth: 250
    minHeight: 300

    // Backend reference (passed from parent)
    property var backend: null

    // Forward signals from embedded ProjectBrowser
    signal datasetDoubleClicked(string datasetName)
    signal datasetActivated(string datasetName)
    signal spectrumRequestedFromBrowser(string datasetName, int spectrumIndex)

    // Content component - embedded ProjectBrowser
    contentComponent: Component {
        Item {
            id: browserWrapper

            // Theme colors
            property var mainWin: ApplicationWindow.window
            property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
            property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
            property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
            property color textLight: mainWin ? mainWin.textLight : "#ffffff"
            property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
            property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
            property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
            property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

            // Use the actual ProjectBrowser component
            ProjectBrowser {
                id: embeddedBrowser
                anchors.fill: parent
                backend: projectBrowserEntity.backend

                // Forward signals
                onDatasetDoubleClicked: function(name) {
                    projectBrowserEntity.datasetDoubleClicked(name)
                }

                onDatasetActivated: function(name) {
                    projectBrowserEntity.datasetActivated(name)
                }

                onSpectrumRequestedFromBrowser: function(name, index) {
                    projectBrowserEntity.spectrumRequestedFromBrowser(name, index)
                }
            }
        }
    }

    // Initialize from entityData when loaded
    onEntityDataChanged: {
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.backend) backend = entityData.backend
        }
    }

    Component.onCompleted: {
        console.log("ProjectBrowserEntity created:", entityId)
    }
}
