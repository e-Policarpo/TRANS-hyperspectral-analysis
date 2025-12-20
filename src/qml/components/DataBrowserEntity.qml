/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * DataBrowserEntity - Floating entity wrapper for Map Editor DataBrowser
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
    id: dataBrowserEntity

    entityType: "browser"
    entityTitle: "Data Browser"
    minWidth: 220
    minHeight: 250

    // Data properties
    property var channelNames: []
    property string activeChannel: ""
    property var maskNames: []
    property bool hasSpectralData: false
    property int spectralPoints: 0
    property int mapRows: 0
    property int mapCols: 0

    // Forward signals from embedded DataBrowser
    signal channelSelected(string channelName)
    signal maskSelected(string maskName)
    signal channelDeleteRequested(string channelName)
    signal maskDeleteRequested(string maskName)
    signal statisticsRequested(string channelName)

    // Content component - embedded DataBrowser
    contentComponent: Component {
        MapEditor.DataBrowser {
            id: embeddedBrowser

            channelNames: dataBrowserEntity.channelNames
            activeChannel: dataBrowserEntity.activeChannel
            maskNames: dataBrowserEntity.maskNames
            hasSpectralData: dataBrowserEntity.hasSpectralData
            spectralPoints: dataBrowserEntity.spectralPoints
            mapRows: dataBrowserEntity.mapRows
            mapCols: dataBrowserEntity.mapCols

            // Forward signals
            onChannelSelected: function(name) { dataBrowserEntity.channelSelected(name) }
            onMaskSelected: function(name) { dataBrowserEntity.maskSelected(name) }
            onChannelDeleteRequested: function(name) { dataBrowserEntity.channelDeleteRequested(name) }
            onMaskDeleteRequested: function(name) { dataBrowserEntity.maskDeleteRequested(name) }
            onStatisticsRequested: function(name) { dataBrowserEntity.statisticsRequested(name) }
        }
    }

    // Initialize from entityData when loaded
    onEntityDataChanged: {
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.channelNames) channelNames = entityData.channelNames
            if (entityData.activeChannel) activeChannel = entityData.activeChannel
        }
    }

    Component.onCompleted: {
        console.log("DataBrowserEntity created:", entityId)
    }
}
