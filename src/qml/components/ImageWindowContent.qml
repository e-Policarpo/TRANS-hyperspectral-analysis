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
import QtQuick.Dialogs

Item {
    id: root

    // Inline marquee label: shows ``text`` truncated to fit the parent
    // width by default; on mouse hover, the text scrolls horizontally so
    // the user can read overflow without resizing the panel. Static
    // (no animation) when the text already fits.
    component MarqueeLabel: Item {
        id: ml
        property string text: ""
        property color textColor: "white"
        property int pixelSize: 10
        property bool bold: false

        clip: true
        implicitHeight: scrollText.implicitHeight
        property bool overflow: scrollText.implicitWidth > width
        property real travel: Math.max(0, scrollText.implicitWidth - width + 4)

        Label {
            id: scrollText
            text: ml.text
            color: ml.textColor
            font.pixelSize: ml.pixelSize
            font.bold: ml.bold
            // No elide here — we manually clip to ``ml.width`` so the
            // overflow part is reachable by the marquee animation.
            x: 0
            anchors.verticalCenter: parent.verticalCenter
        }

        // Static fade hint at the right edge when the text overflows
        // and the user isn't hovering — same visual affordance Apple
        // uses to suggest "there's more, hover me".
        Rectangle {
            visible: ml.overflow && !mouseArea.containsMouse
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: 14; height: parent.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#00000000" }
                GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.45) }
            }
        }

        MouseArea {
            id: mouseArea
            anchors.fill: parent
            hoverEnabled: true
            // Reset when the cursor leaves so the next hover restarts
            // the scroll from the beginning.
            onContainsMouseChanged: { if (!containsMouse) scrollText.x = 0 }
        }

        SequentialAnimation {
            running: mouseArea.containsMouse && ml.overflow
            loops: Animation.Infinite
            PauseAnimation { duration: 500 }
            NumberAnimation {
                target: scrollText; property: "x"
                from: 0; to: -ml.travel
                duration: Math.max(1500, ml.travel * 25)
            }
            PauseAnimation { duration: 800 }
            NumberAnimation {
                target: scrollText; property: "x"
                from: -ml.travel; to: 0
                duration: Math.max(1500, ml.travel * 25)
            }
        }
    }

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
    // Spatial cursors saved by the acquisition software (e.g. WITec
    // ``TDSpaceCursor``). Each entry: ``{x_pixel, y_pixel, label, ...}``.
    property var spatialCursors: []
    property bool showCrosshair: false

    // ----- Per-spectrum overlays (Feature B) ---------------------------
    // Every spectrum (across loaded datasets) whose acquisition coord
    // falls inside this image's bounds. Populated by
    // ``backend.getDatasetOverlaysForImage(imageId)``. Each spectrum is
    // toggleable independently, with its own colour from the palette.
    // The dataset_name is used purely as a grouping header in the side
    // panel.
    // When ``showLaserFocus`` is on, every visible spectrum gets a
    // second marker drawn at the *wip-stored video-centre* pixel (the
    // raw position WITec wrote into the file, before adding the probe
    // offset). The primary "+" crosshair is the offset-corrected
    // laser hit point; the secondary square is the video-centre. The
    // line between them is exactly the configured (ΔX, ΔY) offset.
    property bool showLaserFocus: false
    property var overlayPool: []
    // Ordered list of unique dataset names found in ``overlayPool``
    // (used only as side-panel section headers).
    property var overlayDatasetNames: []
    // dataset_name → [overlay entries in pool order], for the grouped
    // side-panel rendering.
    property var overlayDatasetGroups: ({})
    // spectrum_key → colour. Key is ``dataset_name + '/' + spectrum_index``.
    property var overlaySpectrumColors: ({})
    // spectrum_key → bool. Default true so each new image starts with
    // every compatible spectrum visible.
    property var overlaySelected: ({})

    // ----- Sibling zoom-region overlays (Feature C) --------------------
    // Other images in the same .wip whose extent overlaps this one;
    // rendered as a rectangle on the parent. From
    // ``backend.getZoomRegionsForImage(imageId)``.
    property var zoomRegionPool: []
    property var zoomRegionNames: []
    property var zoomRegionColors: ({})
    property var zoomRegionSelected: ({})

    // High-contrast palette, cycled per dataset / per sibling.
    readonly property var overlayPalette: [
        "#F5A9B8", "#5BCEFA", "#A6E3A1", "#F9E2AF", "#CBA6F7", "#FAB387",
        "#94E2D5", "#F38BA8", "#74C7EC", "#FAB0B0",
    ]

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
        spatialCursors = info.spatial_cursors || []
        refreshDatasetOverlays()
        refreshZoomRegions()
        refreshHistogram()
        // Force the Image element to reload so the new info applies.
        img.source = buildSourceUrl()
    }

    // Spectrum-key helper: stable across refreshes (dataset name +
    // index uniquely identifies one acquisition position in the project).
    function overlayKeyOf(entry) {
        return entry.dataset_name + "/" + entry.spectrum_index
    }

    // Pull per-spectrum overlay candidates from the backend and rebuild
    // grouping headers. Selection state *and* per-spectrum colour are
    // carried forward across refreshes — even for keys that aren't in
    // the current pool (a probe-offset edit can push a spectrum out of
    // bounds and a later edit can bring it back). The previous code
    // only preserved entries in the current pool, so an unchecked
    // spectrum that left and re-entered the pool would silently revert
    // to ``true`` with a possibly-different palette colour. Persisting
    // the full map fixes both regressions.
    function refreshDatasetOverlays() {
        if (!backend || !imageId) {
            overlayPool = []; overlayDatasetNames = []
            overlayDatasetGroups = ({})
            overlaySpectrumColors = ({}); overlaySelected = ({})
            return
        }
        var pool = backend.getDatasetOverlaysForImage(imageId) || []
        overlayPool = pool

        // Start from every previously-known key/value — out-of-pool
        // entries are kept intact so they survive offset round-trips.
        var sel = ({})
        var prevSel = overlaySelected
        for (var k in prevSel) sel[k] = prevSel[k]

        var colors = ({})
        var prevColors = overlaySpectrumColors
        for (var c in prevColors) colors[c] = prevColors[c]

        // Track how many distinct keys we've already coloured so new
        // entries get the next free palette slot deterministically.
        var nextColorIdx = 0
        for (var ck in colors) nextColorIdx++

        var names = []
        var groups = ({})
        for (var i = 0; i < pool.length; i++) {
            var entry = pool[i]
            var d = entry.dataset_name
            if (names.indexOf(d) < 0) {
                names.push(d); groups[d] = []
            }
            groups[d].push(entry)
            var key = overlayKeyOf(entry)
            if (!(key in sel)) sel[key] = true       // new spectrum: visible by default
            if (!(key in colors)) {
                colors[key] = overlayPalette[nextColorIdx % overlayPalette.length]
                nextColorIdx++
            }
        }
        overlayDatasetNames = names
        overlayDatasetGroups = groups
        overlaySpectrumColors = colors
        overlaySelected = sel
    }

    // Filtered overlay list (only spectra whose checkbox is on).
    function selectedOverlays() {
        var out = []
        for (var i = 0; i < overlayPool.length; i++) {
            var ov = overlayPool[i]
            if (overlaySelected[overlayKeyOf(ov)]) out.push(ov)
        }
        return out
    }

    // Toggle one spectrum's visibility.
    function toggleOverlaySpectrum(key) {
        var sel = ({})
        for (var k in overlaySelected) sel[k] = overlaySelected[k]
        sel[key] = !sel[key]
        overlaySelected = sel
    }

    // Bulk-set every spectrum in ``dsName`` to ``value`` (small "All"
    // / "None" convenience controls in each side-panel group).
    function setOverlayDatasetAll(dsName, value) {
        var sel = ({})
        for (var k in overlaySelected) sel[k] = overlaySelected[k]
        for (var i = 0; i < overlayPool.length; i++) {
            var entry = overlayPool[i]
            if (entry.dataset_name === dsName) sel[overlayKeyOf(entry)] = value
        }
        overlaySelected = sel
    }

    // Populate the zoom-region pool (sibling-image rectangles). Colours
    // start halfway through the palette so they don't visually collide
    // with spectrum-overlay crosshairs on the same image. Like
    // refreshDatasetOverlays, this preserves the user's per-rectangle
    // visibility toggles *and* colours across refreshes — even for
    // rectangles that temporarily leave the pool.
    function refreshZoomRegions() {
        if (!backend || !imageId) {
            zoomRegionPool = []; zoomRegionNames = []
            zoomRegionColors = ({}); zoomRegionSelected = ({})
            return
        }
        var pool = backend.getZoomRegionsForImage(imageId) || []
        zoomRegionPool = pool

        var sel = ({})
        var prevSel = zoomRegionSelected
        for (var k in prevSel) sel[k] = prevSel[k]

        var colors = ({})
        var prevColors = zoomRegionColors
        for (var c in prevColors) colors[c] = prevColors[c]

        var nextColorIdx = 0
        for (var ck in colors) nextColorIdx++
        var offset = Math.floor(overlayPalette.length / 2)

        var names = []
        for (var i = 0; i < pool.length; i++) {
            var d = pool[i].label
            if (names.indexOf(d) < 0) {
                names.push(d)
                if (!(d in colors)) {
                    colors[d] = overlayPalette[(nextColorIdx + offset) % overlayPalette.length]
                    nextColorIdx++
                }
                if (!(d in sel)) sel[d] = false       // new rectangle: off by default
            }
        }
        zoomRegionNames = names
        zoomRegionColors = colors
        zoomRegionSelected = sel
    }

    function selectedZoomRegions() {
        var out = []
        for (var i = 0; i < zoomRegionPool.length; i++) {
            var r = zoomRegionPool[i]
            if (zoomRegionSelected[r.label]) out.push(r)
        }
        return out
    }

    function toggleZoomRegion(name) {
        var sel = ({})
        for (var k in zoomRegionSelected) sel[k] = zoomRegionSelected[k]
        sel[name] = !sel[name]
        zoomRegionSelected = sel
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
            histogramView.dataMin = 0
            histogramView.dataMax = 1
            return
        }
        // Phase 7.4b — switched to the richer slot so the level
        // handles know where they sit on the histogram x-axis.
        var payload = backend.getImageHistogramFull(imageId, 64)
        if (payload && payload.counts) {
            histogramView.counts = payload.counts
            histogramView.dataMin = payload.dataMin
            histogramView.dataMax = payload.dataMax
        } else {
            histogramView.counts = []
        }
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

                // Per-spectrum crosshair overlays (Feature B). One per
                // single-point spectrum whose acquisition coord, resolved
                // through the image's affine, lands inside this image.
                // Each spectrum carries its own colour from the palette.
                Repeater {
                    model: selectedOverlays()
                    delegate: Item {
                        x: viewport.renderX + modelData.x_pixel * viewport.effectiveScale
                        y: viewport.renderY + modelData.y_pixel * viewport.effectiveScale
                        z: 6
                        property color tint: overlaySpectrumColors[overlayKeyOf(modelData)] || accentBlue
                        Rectangle { x: -20; y: -1; width: 40; height: 2; color: tint; opacity: 0.95 }
                        Rectangle { x: -1; y: -20; width: 2; height: 40; color: tint; opacity: 0.95 }
                        Rectangle {
                            x: -3; y: -3; width: 6; height: 6; radius: 3
                            color: "transparent"; border.color: tint; border.width: 2
                        }
                    }
                }

                // Wip-stored video-centre diagnostic marker (Feature B
                // debug). When ``showLaserFocus`` is on, each visible
                // spectrum gets a SECOND, smaller marker at the raw
                // pixel the wip file recorded (= image centre at the
                // moment the spectrum was acquired). The primary "+"
                // is the offset-corrected laser hit point; the
                // displacement between the two is the probe offset.
                Repeater {
                    model: showLaserFocus ? selectedOverlays() : []
                    delegate: Item {
                        x: viewport.renderX + modelData.x_pixel_laser * viewport.effectiveScale
                        y: viewport.renderY + modelData.y_pixel_laser * viewport.effectiveScale
                        z: 7
                        property color tint: overlaySpectrumColors[overlayKeyOf(modelData)] || accentBlue
                        // Hollow outline square at the laser pixel.
                        Rectangle {
                            x: -7; y: -7; width: 14; height: 14
                            color: "transparent"
                            border.color: tint
                            border.width: 1
                            opacity: 0.95
                        }
                        // Small "X" inside so it's identifiable as
                        // "laser focus" vs. the primary "+" crosshair.
                        Rectangle {
                            x: -5; y: -0.5; width: 10; height: 1
                            color: tint; opacity: 0.95
                            rotation: 45
                        }
                        Rectangle {
                            x: -5; y: -0.5; width: 10; height: 1
                            color: tint; opacity: 0.95
                            rotation: -45
                        }
                    }
                }


                // Sibling zoom-region rectangles (Feature C). One per
                // other image in the .wip whose extent overlaps this
                // image, drawn as a coloured outline with small corner
                // markers (so the bounds stay visible even when the
                // sibling covers almost the whole parent) plus a label
                // with the precise µm dimensions.
                Repeater {
                    model: selectedZoomRegions()
                    delegate: Item {
                        x: viewport.renderX + modelData.x_min_pixel * viewport.effectiveScale
                        y: viewport.renderY + modelData.y_min_pixel * viewport.effectiveScale
                        width: (modelData.x_max_pixel - modelData.x_min_pixel) * viewport.effectiveScale
                        height: (modelData.y_max_pixel - modelData.y_min_pixel) * viewport.effectiveScale
                        z: 5
                        property color tint: zoomRegionColors[modelData.label] || accentPink
                        Rectangle {
                            anchors.fill: parent
                            color: "transparent"
                            border.color: parent.tint
                            border.width: 2
                        }
                        // Corner markers — small filled squares at each
                        // of the four corners so the bounds are
                        // unmistakable when the rectangle clips out of
                        // view or visually matches the parent's edges.
                        Repeater {
                            model: [
                                {ax: 0, ay: 0},
                                {ax: 1, ay: 0},
                                {ax: 0, ay: 1},
                                {ax: 1, ay: 1},
                            ]
                            delegate: Rectangle {
                                width: 6; height: 6
                                color: parent.parent.tint
                                x: modelData.ax === 0 ? -3 : parent.parent.width - 3
                                y: modelData.ay === 0 ? -3 : parent.parent.height - 3
                            }
                        }
                        Label {
                            x: 4; y: 4
                            text: modelData.label
                            color: parent.tint
                            font.pixelSize: 10
                            font.bold: true
                            background: Rectangle {
                                color: bgDarker; opacity: 0.7; radius: 2
                            }
                            leftPadding: 4; rightPadding: 4
                        }
                    }
                }

                // Legend in the top-left of the viewport. One entry per
                // spectrum (Feature B) and one entry per sibling-image
                // rectangle (Feature C). Unselected entries are dimmed.
                Column {
                    x: 8; y: 8; z: 10
                    spacing: 2
                    visible: overlayPool.length > 0 || zoomRegionNames.length > 0
                    Repeater {
                        // Only selected spectra appear in the legend.
                        // Previously this iterated the full ``overlayPool``
                        // and merely dimmed deselected entries, so
                        // unchecking a spectrum left a "ghost" legend row
                        // behind. Driving off ``selectedOverlays()`` removes
                        // the row in lock-step with the on-image crosshair
                        // (which already uses the same model).
                        model: selectedOverlays()
                        delegate: Row {
                            spacing: 6
                            Rectangle {
                                width: 10; height: 10
                                color: overlaySpectrumColors[overlayKeyOf(modelData)] || accentBlue
                                anchors.verticalCenter: parent.verticalCenter
                                border.color: bgDarker; border.width: 1
                            }
                            Label {
                                text: modelData.label
                                color: textLight
                                font.pixelSize: 10
                                font.bold: true
                                background: Rectangle {
                                    color: bgDarker; opacity: 0.7; radius: 2
                                }
                                leftPadding: 4; rightPadding: 4
                            }
                        }
                    }
                    Repeater {
                        model: zoomRegionNames
                        delegate: Row {
                            spacing: 6
                            opacity: zoomRegionSelected[modelData] ? 1.0 : 0.35
                            Rectangle {
                                width: 10; height: 10
                                color: zoomRegionColors[modelData] || accentPink
                                anchors.verticalCenter: parent.verticalCenter
                                border.color: bgDarker; border.width: 1
                            }
                            Label {
                                text: "⬛ " + modelData
                                color: textLight
                                font.pixelSize: 10
                                font.bold: true
                                background: Rectangle {
                                    color: bgDarker; opacity: 0.7; radius: 2
                                }
                                leftPadding: 4; rightPadding: 4
                            }
                        }
                    }
                }

                // Crosshair overlays — one per spatial cursor that the
                // loader resolved to fall inside this image's bounds.
                // Pixel coords come from TDSpaceTransformation.pixel_xy()
                // (world µm → image pixels).
                Repeater {
                    model: showCrosshair ? spatialCursors : []
                    delegate: Item {
                        visible: modelData.x_pixel >= 0 && modelData.y_pixel >= 0
                        x: viewport.renderX + modelData.x_pixel * viewport.effectiveScale
                        y: viewport.renderY + modelData.y_pixel * viewport.effectiveScale
                        z: 5
                        Rectangle {  // horizontal arm
                            x: -20; y: -1
                            width: 40; height: 2
                            color: accentBlue
                            opacity: 0.9
                        }
                        Rectangle {  // vertical arm
                            x: -1; y: -20
                            width: 2; height: 40
                            color: accentBlue
                            opacity: 0.9
                        }
                        Rectangle {  // small center marker
                            x: -3; y: -3
                            width: 6; height: 6
                            radius: 3
                            color: "transparent"
                            border.color: accentBlue
                            border.width: 2
                        }
                        Label {
                            x: 8; y: -22
                            text: modelData.label || "Cursor"
                            color: accentBlue
                            font.pixelSize: 10
                            font.bold: true
                            // subtle background for legibility
                            background: Rectangle {
                                color: bgDarker
                                opacity: 0.75
                                radius: 2
                            }
                            leftPadding: 4; rightPadding: 4
                        }
                    }
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
            Layout.preferredWidth: 280
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

                    // -------- View tools (Reset zoom / 1:1) ---------------
                    // "Reset zoom" zeroes both wheel-zoom and any
                    // accumulated pan so the image is fully fit to the
                    // viewport again — the recovery button when the
                    // user has zoomed/panned far enough to lose it.
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Button {
                            Layout.fillWidth: true
                            text: "Reset zoom"
                            onClicked: {
                                viewport.zoom = 1.0
                                viewport.panX = 0
                                viewport.panY = 0
                            }
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

                    // -------- Crosshair (spatial cursors from WITec, etc.) -----
                    Button {
                        Layout.fillWidth: true
                        enabled: spatialCursors.length > 0
                        text: spatialCursors.length === 0
                              ? "No crosshair in file"
                              : (showCrosshair ? "Hide crosshair (" + spatialCursors.length + ")"
                                               : "Show crosshair (" + spatialCursors.length + ")")
                        onClicked: showCrosshair = !showCrosshair
                    }

                    // -------- WITec probe offset (calibration) ------------
                    // Constant µm offset between the recorded laser focus
                    // and the video crosshair the user actually aimed
                    // with. The overlay backend subtracts it so crosshairs
                    // land at the user-targeted pixel. Only affects WITec
                    // overlays — other instruments are untouched.
                    Label {
                        text: "WITec probe offset"
                        color: textLight
                        font.pixelSize: 11
                        font.bold: true
                    }
                    Label {
                        Layout.fillWidth: true
                        color: textMuted
                        font.pixelSize: 9
                        wrapMode: Text.WordWrap
                        text: "Laser − video centre (µm). The wip stores "
                            + "the video-centre coord; this delta is added "
                            + "to it so the crosshair lands at the actual "
                            + "laser hit point. WITec spectra only."
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label {
                            text: "ΔX"
                            color: textMuted
                            font.pixelSize: 10
                            Layout.preferredWidth: 18
                        }
                        TextField {
                            id: probeOffsetXField
                            Layout.fillWidth: true
                            font.pixelSize: 10
                            selectByMouse: true
                            // Pin to C locale so the validator treats '.'
                            // as the decimal separator everywhere, even
                            // on a pt-BR / es / de system where the
                            // default validator would interpret '.' as
                            // a thousands separator and eat the dot.
                            validator: DoubleValidator {
                                notation: DoubleValidator.StandardNotation
                                locale: "C"
                            }
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            text: backend && backend.preferencesManager
                                ? backend.preferencesManager.getProbeOffsetX().toFixed(2)
                                : "0.00"
                            onEditingFinished: {
                                if (!backend || !backend.preferencesManager) return
                                // Accept comma as decimal too (user
                                // habit) before handing off to parseFloat.
                                var v = parseFloat(text.replace(",", "."))
                                if (isNaN(v)) return
                                var dy = parseFloat(probeOffsetYField.text.replace(",", "."))
                                if (isNaN(dy)) dy = backend.preferencesManager.getProbeOffsetY()
                                backend.preferencesManager.setProbeOffset(v, dy)
                                refreshDatasetOverlays()
                            }
                        }
                        Label {
                            text: "ΔY"
                            color: textMuted
                            font.pixelSize: 10
                            Layout.preferredWidth: 18
                            Layout.leftMargin: 4
                        }
                        TextField {
                            id: probeOffsetYField
                            Layout.fillWidth: true
                            font.pixelSize: 10
                            selectByMouse: true
                            validator: DoubleValidator {
                                notation: DoubleValidator.StandardNotation
                                locale: "C"
                            }
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            text: backend && backend.preferencesManager
                                ? backend.preferencesManager.getProbeOffsetY().toFixed(2)
                                : "0.00"
                            onEditingFinished: {
                                if (!backend || !backend.preferencesManager) return
                                var v = parseFloat(text.replace(",", "."))
                                if (isNaN(v)) return
                                var dx = parseFloat(probeOffsetXField.text.replace(",", "."))
                                if (isNaN(dx)) dx = backend.preferencesManager.getProbeOffsetX()
                                backend.preferencesManager.setProbeOffset(dx, v)
                                refreshDatasetOverlays()
                            }
                        }
                    }
                    Button {
                        Layout.fillWidth: true
                        text: "Reset to default"
                        font.pixelSize: 9
                        padding: 2
                        Layout.preferredHeight: 18
                        onClicked: {
                            if (!backend || !backend.preferencesManager) return
                            backend.preferencesManager.resetProbeOffsetToDefault()
                            probeOffsetXField.text = backend.preferencesManager.getProbeOffsetX().toFixed(2)
                            probeOffsetYField.text = backend.preferencesManager.getProbeOffsetY().toFixed(2)
                            refreshDatasetOverlays()
                        }
                    }

                    // Diagnostic toggle: show the wip-stored video
                    // centre (hollow square + X) alongside the primary
                    // "+" crosshair (= video centre + offset = laser
                    // hit). The displacement between the two markers
                    // visualises exactly what the offset is doing.
                    CheckBox {
                        Layout.fillWidth: true
                        text: "Show video centre (debug)"
                        font.pixelSize: 10
                        checked: showLaserFocus
                        onClicked: showLaserFocus = checked
                    }

                    // Keep the side-panel fields in sync if the offset
                    // changes elsewhere (e.g. project import).
                    Connections {
                        target: backend && backend.preferencesManager
                            ? backend.preferencesManager : null
                        function onProbeOffsetChanged(dx, dy) {
                            probeOffsetXField.text = dx.toFixed(2)
                            probeOffsetYField.text = dy.toFixed(2)
                            refreshDatasetOverlays()
                        }
                    }

                    // -------- Per-spectrum overlays (Feature B) -------------
                    Label {
                        text: "Spectrum overlays"
                        color: textLight
                        font.pixelSize: 11
                        font.bold: true
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: overlayDatasetNames.length === 0
                        color: textMuted
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                        text: "No compatible spectra in the project."
                    }
                    // For each dataset: a full-width header (marquee
                    // on hover when the dataset name is long), a thin
                    // controls row with the spectrum count and
                    // All / None bulk toggles, then one row per
                    // spectrum with its own checkbox + colour swatch +
                    // marquee-on-hover label.
                    Repeater {
                        model: overlayDatasetNames
                        delegate: ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            property string dsName: modelData
                            property int dsCount: overlayDatasetGroups[dsName]
                                ? overlayDatasetGroups[dsName].length : 0
                            MarqueeLabel {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 14
                                text: dsName
                                textColor: textMuted
                                pixelSize: 10
                                bold: true
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 4
                                Label {
                                    text: dsCount + " spec" + (dsCount === 1 ? "" : "tra")
                                    color: textMuted
                                    font.pixelSize: 9
                                    Layout.fillWidth: true
                                }
                                Button {
                                    text: "All"
                                    font.pixelSize: 9
                                    padding: 2
                                    Layout.preferredHeight: 18
                                    onClicked: setOverlayDatasetAll(dsName, true)
                                }
                                Button {
                                    text: "None"
                                    font.pixelSize: 9
                                    padding: 2
                                    Layout.preferredHeight: 18
                                    onClicked: setOverlayDatasetAll(dsName, false)
                                }
                            }
                            Repeater {
                                model: overlayDatasetGroups[dsName] || []
                                delegate: RowLayout {
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 8
                                    spacing: 6
                                    property string skey: overlayKeyOf(modelData)
                                    CheckBox {
                                        checked: overlaySelected[skey] === true
                                        onClicked: toggleOverlaySpectrum(skey)
                                        Layout.preferredWidth: 18
                                    }
                                    Rectangle {
                                        Layout.preferredWidth: 10
                                        Layout.preferredHeight: 10
                                        radius: 2
                                        color: overlaySpectrumColors[skey] || accentBlue
                                        Layout.alignment: Qt.AlignVCenter
                                    }
                                    MarqueeLabel {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 14
                                        text: modelData.label
                                        textColor: textLight
                                        pixelSize: 10
                                    }
                                }
                            }
                        }
                    }
                    // -------- Zoom-region overlays (Feature C) --------------
                    Label {
                        text: "Zoom regions"
                        color: textLight
                        font.pixelSize: 11
                        font.bold: true
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: zoomRegionNames.length === 0
                        color: textMuted
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                        text: "No overlapping images in the project."
                    }
                    Repeater {
                        model: zoomRegionNames
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            CheckBox {
                                checked: zoomRegionSelected[modelData] === true
                                onClicked: toggleZoomRegion(modelData)
                                Layout.preferredWidth: 18
                            }
                            Rectangle {
                                Layout.preferredWidth: 10
                                Layout.preferredHeight: 10
                                radius: 2
                                color: zoomRegionColors[modelData] || accentPink
                                Layout.alignment: Qt.AlignVCenter
                            }
                            MarqueeLabel {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 14
                                text: modelData
                                textColor: textLight
                                pixelSize: 10
                            }
                        }
                    }

                    Button {
                        Layout.fillWidth: true
                        enabled: overlayDatasetNames.length > 0 || zoomRegionNames.length > 0
                        text: "Export with overlays…"
                        onClicked: overlayExportDialog.open()
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
                        Layout.preferredHeight: 72
                        color: bgDarker
                        border.color: borderColor
                        border.width: 1
                        Item {
                            id: histogramView
                            anchors.fill: parent
                            anchors.margins: 2

                            // Phase 7.4b — interactive histogram.
                            // ``counts`` + ``dataMin`` / ``dataMax``
                            // arrive from ``backend.getImageHistogramFull``.
                            // The two vertical handles drive the
                            // ``displayMin`` / ``displayMax`` properties
                            // on the parent window (which in turn
                            // rebuild the ``image://trans/<id>`` URL
                            // through ``applyEdits``).
                            property var counts: []
                            property real dataMin: 0
                            property real dataMax: 1
                            property real maxCount: {
                                var m = 1
                                for (var i = 0; i < counts.length; i++)
                                    if (counts[i] > m) m = counts[i]
                                return m
                            }
                            // Only show handles on single-channel
                            // images; RGB ignores ``displayMin/Max``.
                            property bool handlesVisible: isSingleChannel

                            function valueToPixel(v) {
                                var span = dataMax - dataMin
                                if (span <= 0) return 0
                                var px = (v - dataMin) / span * width
                                if (px < 0) px = 0
                                if (px > width) px = width
                                return px
                            }
                            function pixelToValue(p) {
                                var span = dataMax - dataMin
                                var clamped = Math.max(0, Math.min(p, width))
                                return dataMin + (clamped / Math.max(width, 1)) * span
                            }

                            Repeater {
                                model: histogramView.counts.length
                                Rectangle {
                                    width: histogramView.width / Math.max(histogramView.counts.length, 1)
                                    x: index * width
                                    color: accentBlue
                                    opacity: 0.55
                                    height: histogramView.height *
                                            (histogramView.counts[index] / histogramView.maxCount)
                                    anchors.bottom: parent.bottom
                                }
                            }

                            // In-window shaded overlay between the
                            // two handles. Helps the eye read which
                            // bars actually map to the visible LUT
                            // range.
                            Rectangle {
                                id: inRangeBand
                                visible: histogramView.handlesVisible
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                x: histogramView.valueToPixel(displayMin)
                                width: Math.max(
                                    0,
                                    histogramView.valueToPixel(displayMax) - x,
                                )
                                color: accentBlue
                                opacity: 0.18
                            }

                            // Min handle.
                            Rectangle {
                                id: minHandle
                                visible: histogramView.handlesVisible
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                x: histogramView.valueToPixel(displayMin) - 1
                                width: 2
                                color: "#5BCEFA"
                            }
                            MouseArea {
                                id: minHandleArea
                                visible: histogramView.handlesVisible
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                x: minHandle.x - 5
                                width: 12
                                cursorShape: Qt.SizeHorCursor
                                acceptedButtons: Qt.LeftButton
                                property bool dragging: false
                                onPressed: dragging = true
                                onReleased: {
                                    dragging = false
                                    applyEdits()
                                    refreshHistogram()
                                }
                                onPositionChanged: {
                                    if (!dragging) return
                                    var hostX = mapToItem(
                                        histogramView, mouse.x, 0,
                                    ).x
                                    var v = histogramView.pixelToValue(hostX)
                                    // Don't cross max.
                                    if (v < displayMax) {
                                        displayMin = v
                                    }
                                }
                            }

                            // Max handle.
                            Rectangle {
                                id: maxHandle
                                visible: histogramView.handlesVisible
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                x: histogramView.valueToPixel(displayMax) - 1
                                width: 2
                                color: "#F5A9B8"
                            }
                            MouseArea {
                                id: maxHandleArea
                                visible: histogramView.handlesVisible
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                x: maxHandle.x - 5
                                width: 12
                                cursorShape: Qt.SizeHorCursor
                                acceptedButtons: Qt.LeftButton
                                property bool dragging: false
                                onPressed: dragging = true
                                onReleased: {
                                    dragging = false
                                    applyEdits()
                                    refreshHistogram()
                                }
                                onPositionChanged: {
                                    if (!dragging) return
                                    var hostX = mapToItem(
                                        histogramView, mouse.x, 0,
                                    ).x
                                    var v = histogramView.pixelToValue(hostX)
                                    if (v > displayMin) {
                                        displayMax = v
                                    }
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

    // Save-as dialog for the annotated image. Extension drives format
    // routing in the backend (tiff carries pixel-scale metadata; png is
    // a plain raster).
    FileDialog {
        id: overlayExportDialog
        title: "Export image with overlays"
        fileMode: FileDialog.SaveFile
        nameFilters: ["TIFF (*.tiff *.tif)", "PNG (*.png)"]
        onAccepted: {
            var path = selectedFile.toString()
            if (path.startsWith("file:///")) path = path.substring(7)
            else if (path.startsWith("file://")) path = path.substring(7)
            // Build per-overlay payload with the user-visible colour
            // baked in (backend doesn't know the QML palette). Mix
            // crosshair and rect entries — the backend's draw loop
            // routes by ``type``.
            var payload = []
            var sel = selectedOverlays()
            for (var i = 0; i < sel.length; i++) {
                var ov = sel[i]
                payload.push({
                    "type": "crosshair",
                    "x_pixel": ov.x_pixel, "y_pixel": ov.y_pixel,
                    "label": ov.label,
                    "color": overlaySpectrumColors[overlayKeyOf(ov)] || "#5BCEFA",
                })
            }
            var rects = selectedZoomRegions()
            for (var j = 0; j < rects.length; j++) {
                var r = rects[j]
                payload.push({
                    "type": "rect",
                    "x_min_pixel": r.x_min_pixel, "y_min_pixel": r.y_min_pixel,
                    "x_max_pixel": r.x_max_pixel, "y_max_pixel": r.y_max_pixel,
                    "label": r.label,
                    "color": zoomRegionColors[r.label] || "#F5A9B8",
                })
            }
            var fmt = path.toLowerCase().endsWith(".png") ? "png" : "tiff"
            var saved = backend.exportImageWithOverlays(imageId, payload, path, fmt)
            if (saved) console.log("Saved annotated image: " + saved)
        }
    }
}
