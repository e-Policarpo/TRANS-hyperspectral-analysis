/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * PointInspectorEntity - Floating entity wrapper for Map Editor PointInspector
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../map_editor" as MapEditor

FloatingEntity {
    id: pointInspectorEntity

    entityType: "inspector"
    entityTitle: "Point Inspector"
    minWidth: 200
    minHeight: 150

    // Point data
    property int currentRow: -1
    property int currentCol: -1
    property real currentValue: 0
    property string channelName: ""
    property bool hasSpectrum: false

    // Forward signals
    signal plotSpectrumRequested(int row, int col)
    signal addToComparisonRequested(int row, int col)

    // Methods to update point
    function setPoint(row, col, value, channel) {
        currentRow = row
        currentCol = col
        currentValue = value
        channelName = channel
        if (contentItem) {
            contentItem.setPoint(row, col, value, channel)
        }
    }

    function setSpectrumAvailable(available) {
        hasSpectrum = available
        if (contentItem) {
            contentItem.hasSpectrum = available
        }
    }

    // Content component - embedded PointInspector
    contentComponent: Component {
        MapEditor.PointInspector {
            id: embeddedInspector

            hasSpectrum: pointInspectorEntity.hasSpectrum

            onPlotSpectrumRequested: function(row, col) {
                pointInspectorEntity.plotSpectrumRequested(row, col)
            }

            onAddToComparisonRequested: function(row, col) {
                pointInspectorEntity.addToComparisonRequested(row, col)
            }
        }
    }

    // Initialize from entityData when loaded
    onEntityDataChanged: {
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.hasSpectrum !== undefined) hasSpectrum = entityData.hasSpectrum
        }
    }

    Component.onCompleted: {
        console.log("PointInspectorEntity created:", entityId)
    }
}
