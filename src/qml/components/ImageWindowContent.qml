/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * ImageWindowContent — embedded image viewer with editing tools.
 *
 * Uses Qt Quick's native ``Image`` element backed by the
 * ``image://trans/<id>?cmap=…&min=…&max=…`` provider; pan/zoom/crop
 * happen via QML mouse + transform machinery, no custom QPainter.
 *
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: May 2026
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    // The image entity to display (looked up via the image://trans/ provider).
    property string imageId: ""
    // Persistence id (used by WindowManager for state save/restore).
    property string entityId: ""
    // Backwards-compat — WindowManager.openImageWindow may still set this.
    property var appBackend: null

    // ----- Edit-state ---------------------------------------------------
    property string colormap: "original"
    property real displayMin: 0
    property real displayMax: 255
    property bool isRgb: false
    property bool isSingleChannel: false
    property real imageNativeWidth: 0
    property real imageNativeHeight: 0
    // Crop selection rectangle in *image-pixel* coordinates (independent
    // of the viewport's current zoom/pan).
    property bool cropActive: false
    property var cropRect: null   // {x, y, w, h} or null

    // Theme colors
    property var mainWin: ApplicationWindow.window
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    implicitWidth: 820
    implicitHeight: 520

    Component.onCompleted: refreshInfo()
    onImageIdChanged: refreshInfo()

    function refreshInfo() {
        if (!backend || !imageId) return
        var info = backend.getImageInfo(imageId)
        if (!info || !info.width) return
        imageNativeWidth = info.width
        imageNativeHeight = info.height
        isRgb = info.is_rgb === true
        isSingleChannel = info.is_single_channel === true
        if (isSingleChannel) {
            displayMin = info.auto_min
            displayMax = info.auto_max
            minField.text = displayMin.toFixed(displayMin > 50 ? 1 : 4)
            maxField.text = displayMax.toFixed(displayMax > 50 ? 1 : 4)
        }
        refreshHistogram()
        // Force the Image element to reload so the new info applies.
        img.source = buildSourceUrl()
    }

    function buildSourceUrl() {
        if (!imageId) return ""
        var url = "image://trans/" + imageId
        // Only single-channel images respect the query params.
        if (isSingleChannel) {
            url += "?cmap=" + encodeURIComponent(colormap)
                 + "&min=" + displayMin
                 + "&max=" + displayMax
                 + "&t=" + Date.now()   // cache-bust on every reload
        }
        return url
    }

    function refreshHistogram() {
        if (!backend || !imageId) {
            histogramView.counts = []
            return
        }
        histogramView.counts = backend.getImageHistogram(imageId, 64)
    }

    function applyEdits() { img.source = buildSourceUrl() }

    function applyCrop() {
        if (!cropRect || cropRect.w <= 0 || cropRect.h <= 0) return
        var newId = backend.cropImage(
            imageId,
            Math.round(cropRect.x),
            Math.round(cropRect.y),
            Math.round(cropRect.x + cropRect.w),
            Math.round(cropRect.y + cropRect.h),
        )
        cropRect = null
        cropActive = false
        if (newId) {
            // Switch this window to the new cropped image.
            imageId = newId
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ===================================================== viewport
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDarker
            border.color: borderColor
            border.width: 1
            clip: true

            // Holds the image and its scale/translate transforms. Sized to
            // the natural image pixels; the parent clips and we move /
            // scale inside.
            Item {
                id: viewport
                anchors.fill: parent

                // Pan + zoom transform: scale the image around the cursor,
                // translate it so the pointer stays on the same pixel.
                property real zoom: 1.0
                property real panX: 0
                property real panY: 0
                property real fitScale: {
                    if (!imageNativeWidth || !imageNativeHeight) return 1
                    return Math.min(
                        viewport.width / imageNativeWidth,
                        viewport.height / imageNativeHeight,
                    )
                }
                property real effectiveScale: zoom * fitScale
                property real renderWidth: imageNativeWidth * effectiveScale
                property real renderHeight: imageNativeHeight * effectiveScale
                property real renderX: (viewport.width - renderWidth) / 2 + panX
                property real renderY: (viewport.height - renderHeight) / 2 + panY

                Image {
                    id: img
                    smooth: true
                    mipmap: true
                    asynchronous: true
                    cache: false  // we manage via query-string cache-bust
                    fillMode: Image.Stretch
                    width: viewport.renderWidth
                    height: viewport.renderHeight
                    x: viewport.renderX
                    y: viewport.renderY
                    source: buildSourceUrl()
                    sourceSize: Qt.size(0, 0)  // load at native resolution
                }

                Label {
                    anchors.centerIn: parent
                    visible: img.status !== Image.Ready
                    text: img.status === Image.Loading ? "Loading…"
                          : img.status === Image.Error ? "Image failed to load"
                          : "No image"
                    color: textMuted
                    font.pixelSize: 12
                }

                // Crop overlay rectangle in image-pixel coordinates → drawn
                // in viewport coordinates after applying the same scale.
                Rectangle {
                    id: cropBox
                    visible: cropRect !== null
                    color: "transparent"
                    border.color: accentPink
                    border.width: 2
                    x: viewport.renderX + (cropRect ? cropRect.x * viewport.effectiveScale : 0)
                    y: viewport.renderY + (cropRect ? cropRect.y * viewport.effectiveScale : 0)
                    width: cropRect ? cropRect.w * viewport.effectiveScale : 0
                    height: cropRect ? cropRect.h * viewport.effectiveScale : 0
                }

                MouseArea {
                    id: viewMouse
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                    hoverEnabled: false
                    cursorShape: cropActive ? Qt.CrossCursor : Qt.OpenHandCursor

                    property point pressPos
                    property real pressPanX
                    property real pressPanY
                    property point pressImagePoint

                    function viewToImage(px, py) {
                        if (viewport.effectiveScale <= 0) return Qt.point(0, 0)
                        return Qt.point(
                            (px - viewport.renderX) / viewport.effectiveScale,
                            (py - viewport.renderY) / viewport.effectiveScale,
                        )
                    }

                    onPressed: function(mouse) {
                        pressPos = Qt.point(mouse.x, mouse.y)
                        if (cropActive && mouse.button === Qt.LeftButton) {
                            var p = viewToImage(mouse.x, mouse.y)
                            cropRect = { x: p.x, y: p.y, w: 0, h: 0 }
                        } else {
                            pressPanX = viewport.panX
                            pressPanY = viewport.panY
                        }
                    }

                    onPositionChanged: function(mouse) {
                        if (!pressed) return
                        if (cropActive && cropRect) {
                            var p = viewToImage(mouse.x, mouse.y)
                            var start = viewToImage(pressPos.x, pressPos.y)
                            var x0 = Math.max(0, Math.min(start.x, p.x))
                            var y0 = Math.max(0, Math.min(start.y, p.y))
                            var x1 = Math.min(imageNativeWidth, Math.max(start.x, p.x))
                            var y1 = Math.min(imageNativeHeight, Math.max(start.y, p.y))
                            cropRect = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
                        } else {
                            viewport.panX = pressPanX + (mouse.x - pressPos.x)
                            viewport.panY = pressPanY + (mouse.y - pressPos.y)
                        }
                    }

                    onWheel: function(wheel) {
                        // Zoom about cursor: keep the image-point under the
                        // pointer stable across the scale change.
                        var step = wheel.angleDelta.y > 0 ? 1.15 : 1 / 1.15
                        var newZoom = Math.max(0.05, Math.min(40.0, viewport.zoom * step))
                        if (newZoom === viewport.zoom) return
                        var imgPt = viewToImage(wheel.x, wheel.y)
                        viewport.zoom = newZoom
                        // Re-compute renderX/Y after zoom and adjust pan so
                        // the point under the cursor still maps to the same
                        // pixel.
                        var newImgPt = viewToImage(wheel.x, wheel.y)
                        viewport.panX += (newImgPt.x - imgPt.x) * viewport.effectiveScale
                        viewport.panY += (newImgPt.y - imgPt.y) * viewport.effectiveScale
                    }
                }
            }
        }

        // =================================================== side panel
        Rectangle {
            Layout.preferredWidth: 240
            Layout.fillHeight: true
            color: bgDark
            border.color: borderColor
            border.width: 1

            ScrollView {
                anchors.fill: parent
                anchors.margins: 6
                clip: true
                contentWidth: availableWidth

                ColumnLayout {
                    width: parent.width
                    spacing: 10

                    Label {
                        Layout.fillWidth: true
                        color: textMuted
                        font.pixelSize: 11
                        text: imageNativeWidth > 0
                              ? imageNativeWidth + " × " + imageNativeHeight + " px"
                              : "No image loaded"
                        wrapMode: Text.WordWrap
                    }

                    // -------- View tools (Fit / 1:1 / reset) --------------
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Button {
                            Layout.fillWidth: true
                            text: "Fit"
                            onClicked: { viewport.zoom = 1.0; viewport.panX = 0; viewport.panY = 0 }
                        }
                        Button {
                            Layout.fillWidth: true
                            text: "1:1"
                            onClicked: {
                                viewport.zoom = 1 / viewport.fitScale
                                viewport.panX = 0; viewport.panY = 0
                            }
                        }
                    }

                    // -------- Histogram --------------------------------------
                    Label {
                        text: "Histogram"
                        color: textLight
                        font.pixelSize: 11
                        font.bold: true
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 64
                        color: bgDarker
                        border.color: borderColor
                        border.width: 1
                        Item {
                            id: histogramView
                            anchors.fill: parent
                            anchors.margins: 2
                            property var counts: []
                            property real maxCount: {
                                var m = 1
                                for (var i = 0; i < counts.length; i++)
                                    if (counts[i] > m) m = counts[i]
                                return m
                            }
                            Repeater {
                                model: histogramView.counts.length
                                Rectangle {
                                    width: histogramView.width / Math.max(histogramView.counts.length, 1)
                                    x: index * width
                                    color: accentBlue
                                    opacity: 0.7
                                    height: histogramView.height *
                                            (histogramView.counts[index] / histogramView.maxCount)
                                    anchors.bottom: parent.bottom
                                }
                            }
                        }
                    }

                    // -------- Display range (single-channel only) -----------
                    Label {
                        text: "Display range"
                        color: textLight
                        font.pixelSize: 11
                        font.bold: true
                        visible: isSingleChannel
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: isSingleChannel
                        Label { text: "min"; color: textMuted; font.pixelSize: 10; Layout.preferredWidth: 26 }
                        TextField {
                            id: minField
                            Layout.fillWidth: true
                            font.pixelSize: 11
                            validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                            onEditingFinished: {
                                var v = parseFloat(text)
                                if (!isNaN(v)) { displayMin = v; applyEdits() }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: isSingleChannel
                        Label { text: "max"; color: textMuted; font.pixelSize: 10; Layout.preferredWidth: 26 }
                        TextField {
                            id: maxField
                            Layout.fillWidth: true
                            font.pixelSize: 11
                            validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                            onEditingFinished: {
                                var v = parseFloat(text)
                                if (!isNaN(v)) { displayMax = v; applyEdits() }
                            }
                        }
                    }
                    Button {
                        Layout.fillWidth: true
                        visible: isSingleChannel
                        text: "Auto-range"
                        onClicked: {
                            var info = backend.getImageInfo(imageId)
                            if (info && info.auto_min !== undefined) {
                                displayMin = info.auto_min
                                displayMax = info.auto_max
                                minField.text = displayMin.toFixed(displayMin > 50 ? 1 : 4)
                                maxField.text = displayMax.toFixed(displayMax > 50 ? 1 : 4)
                                applyEdits()
                            }
                        }
                    }

                    // -------- Colormap --------------------------------------
                    Label {
                        text: "Colormap"
                        color: textLight
                        font.pixelSize: 11
                        font.bold: true
                    }
                    ComboBox {
                        id: cmapCombo
                        Layout.fillWidth: true
                        enabled: isSingleChannel
                        model: enabled
                            ? ["Original (gray)", "viridis", "magma", "inferno",
                               "plasma", "cividis", "hot"]
                            : ["Original RGB"]
                        onActivated: {
                            if (!enabled) return
                            var pick = currentText.indexOf("Original") === 0
                                       ? "original" : currentText
                            if (pick !== colormap) {
                                colormap = pick
                                applyEdits()
                            }
                        }
                    }

                    // -------- Crop ------------------------------------------
                    Label {
                        text: "Crop"
                        color: textLight
                        font.pixelSize: 11
                        font.bold: true
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Button {
                            Layout.fillWidth: true
                            text: cropActive ? "Cancel" : "Start"
                            onClicked: {
                                cropActive = !cropActive
                                if (!cropActive) cropRect = null
                            }
                        }
                        Button {
                            Layout.fillWidth: true
                            text: "Apply"
                            enabled: cropActive && cropRect && cropRect.w > 1 && cropRect.h > 1
                            onClicked: applyCrop()
                        }
                        Button {
                            Layout.fillWidth: true
                            text: "Reset"
                            onClicked: { cropRect = null; cropActive = false }
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: cropActive
                        color: textMuted
                        font.pixelSize: 10
                        text: cropRect
                              ? "Selection: " + Math.round(cropRect.w) +
                                "×" + Math.round(cropRect.h) + " px"
                              : "Drag on the image to define a rectangle."
                        wrapMode: Text.WordWrap
                    }

                    Item { Layout.fillHeight: true }  // spacer
                }
            }
        }
    }
}
