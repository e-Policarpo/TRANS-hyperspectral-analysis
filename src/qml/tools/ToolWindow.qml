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
import "../components"

DraggableWindow {
    id: toolWindow

    property string toolName: "Generic Tool"
    property var toolConfig: ({})

    windowTitle: toolName

    // Tool-specific content loader
    Loader {
        id: toolContentLoader
        anchors.fill: parent

        Component.onCompleted: {
            // Load appropriate tool UI based on toolName
            var toolPath = getToolPath(toolName)
            if (toolPath) {
                source = toolPath
            } else {
                source = "GenericToolUI.qml"
            }
        }
    }

    // Map tool names to QML files
    function getToolPath(name) {
        var toolMap = {
            "1D FFT": "FFT1DTool.qml",
            "2D FFT": "FFT2DTool.qml",
            "Curve Smoothing": "CurveSmoothingTool.qml",
            "Image Smoothing": "ImageSmoothingTool.qml",
            "Derivative Calculator": "DerivativeTool.qml",
            "Gradient Filter": "GradientTool.qml",
            "Curve Fitting": "CurveFittingTool.qml",
            "Integration Utility": "IntegrationTool.qml",
            "Map Generator": "MapGeneratorTool.qml",
            "Spatial Average": "SpatialAverageTool.qml",
            "Map Discretizer": "MapDiscretizerTool.qml",
            "Map Processing": "MapProcessingTool.qml",
            "Curve Analysis": "CurveAnalysisTool.qml",
            "Truncate Data": "TruncateTool.qml"
        }

        return toolMap[name] || null
    }
}
