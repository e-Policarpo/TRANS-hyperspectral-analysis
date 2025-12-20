/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * StatisticsPanelEntity - Floating entity wrapper for Map Editor StatisticsPanel
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
    id: statisticsPanelEntity

    entityType: "statistics"
    entityTitle: "Statistics"
    minWidth: 220
    minHeight: 180

    // Statistics data
    property var stats: ({})
    property string channelName: ""
    property bool isSelection: false
    property int selectionCount: 0

    // Method to update statistics
    function updateStats(newStats, channel, selection, count) {
        stats = newStats
        channelName = channel
        isSelection = selection
        selectionCount = count
        if (contentItem) {
            contentItem.updateStats(newStats, channel, selection, count)
        }
    }

    // Content component - embedded StatisticsPanel
    contentComponent: Component {
        MapEditor.StatisticsPanel {
            id: embeddedStats
        }
    }

    // Initialize from entityData when loaded
    onEntityDataChanged: {
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.stats) {
                updateStats(entityData.stats, entityData.channelName || "", entityData.isSelection || false, entityData.selectionCount || 0)
            }
        }
    }

    Component.onCompleted: {
        console.log("StatisticsPanelEntity created:", entityId)
    }
}
