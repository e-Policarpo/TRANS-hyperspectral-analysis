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
            property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
            property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
            property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
            property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
            property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
            property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
            property color accentBlue: (mainWin && mainWin.accentBlue !== undefined) ? mainWin.accentBlue : Theme.accentBlue
            property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

            // Use the actual ProjectBrowser component
            ProjectBrowser {
                id: embeddedBrowser
                anchors.fill: parent
                // Note: ProjectBrowser gets backend from global context, not property
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
