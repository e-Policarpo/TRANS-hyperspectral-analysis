/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Preferences Dialog - Color scheme and font customization
 * Made by Eduarda Policarpo, with love
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Dialog {
    id: preferencesDialog
    title: "Preferences"
    modal: true
    width: 800
    height: 600

    // Theme colors (use passed-in or default)
    property color bgDark: "#1a1a2e"
    property color bgMedium: "#2a2a3e"
    property color bgLight: "#3a3a4e"
    property color textLight: "#ffffff"
    property color textMuted: "#cccccc"
    property color borderColor: "#9B4F96"
    property color accentPink: "#F5A9B8"
    property color accentBlue: "#5BCEFA"

    // Current scheme being edited
    property var currentScheme: ({})
    property string currentSchemeName: ""

    // Reference to preferences manager
    property var preferencesManager: null

    background: Rectangle {
        color: bgDark
        border.color: borderColor
        border.width: 1
        radius: 8
    }

    header: Rectangle {
        color: bgMedium
        height: 50
        radius: 8

        Rectangle {
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            height: parent.radius
            color: parent.color
        }

        Text {
            anchors.centerIn: parent
            text: "Preferences"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: borderColor
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 15
        spacing: 15

        // Left sidebar - Scheme selection
        Rectangle {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            color: bgMedium
            border.color: borderColor
            radius: 6

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 10

                Text {
                    text: "Color Schemes"
                    font.pixelSize: 14
                    font.bold: true
                    color: textLight
                }

                // Presets section
                Text {
                    text: "Presets"
                    font.pixelSize: 12
                    font.italic: true
                    color: textMuted
                }

                ListView {
                    id: presetsList
                    Layout.fillWidth: true
                    Layout.preferredHeight: 280
                    clip: true
                    spacing: 2

                    model: ListModel {
                        id: presetsModel
                    }

                    delegate: Rectangle {
                        width: presetsList.width
                        height: 36
                        color: currentSchemeName === model.schemeId ? accentBlue : (mouseArea.containsMouse ? bgLight : "transparent")
                        opacity: currentSchemeName === model.schemeId ? 0.3 : 1
                        radius: 4

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            spacing: 0

                            Text {
                                text: model.name
                                font.pixelSize: 11
                                font.bold: true
                                color: textLight
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: model.description
                                font.pixelSize: 9
                                color: textMuted
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }

                        MouseArea {
                            id: mouseArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                loadScheme(model.schemeId, true)
                            }
                        }
                    }

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }
                }

                // Custom schemes section
                Text {
                    text: "Custom Schemes"
                    font.pixelSize: 12
                    font.italic: true
                    color: textMuted
                    Layout.topMargin: 10
                }

                ListView {
                    id: customList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 2

                    model: ListModel {
                        id: customModel
                    }

                    delegate: Rectangle {
                        width: customList.width
                        height: 36
                        color: currentSchemeName === model.schemeId ? accentPink : (customMouseArea.containsMouse ? bgLight : "transparent")
                        opacity: currentSchemeName === model.schemeId ? 0.3 : 1
                        radius: 4

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0

                                Text {
                                    text: model.name
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: textLight
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: model.description || "Custom scheme"
                                    font.pixelSize: 9
                                    color: textMuted
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }

                            Button {
                                Layout.preferredWidth: 20
                                Layout.preferredHeight: 20
                                text: "X"
                                font.pixelSize: 10
                                visible: customMouseArea.containsMouse

                                background: Rectangle {
                                    color: parent.hovered ? "#ff6666" : "transparent"
                                    radius: 3
                                }

                                contentItem: Text {
                                    text: parent.text
                                    color: textLight
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }

                                onClicked: {
                                    if (preferencesManager) {
                                        preferencesManager.deleteCustomScheme(model.schemeId)
                                        loadCustomSchemes()
                                    }
                                }
                            }
                        }

                        MouseArea {
                            id: customMouseArea
                            anchors.fill: parent
                            hoverEnabled: true
                            propagateComposedEvents: true
                            onClicked: {
                                loadScheme(model.schemeId, false)
                            }
                        }
                    }

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }
                }

                // Save custom button
                Button {
                    Layout.fillWidth: true
                    text: "Save as Custom..."

                    background: Rectangle {
                        color: parent.hovered ? accentPink : bgLight
                        border.color: borderColor
                        radius: 4
                    }

                    contentItem: Text {
                        text: parent.text
                        color: textLight
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                    }

                    onClicked: saveCustomDialog.open()
                }
            }
        }

        // Right panel - Color/Font editing
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgMedium
            border.color: borderColor
            radius: 6

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 15
                spacing: 15

                // Current scheme name
                Text {
                    text: currentScheme.name || "Select a scheme"
                    font.pixelSize: 16
                    font.bold: true
                    color: accentPink
                }

                Text {
                    text: currentScheme.description || ""
                    font.pixelSize: 12
                    color: textMuted
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                // Tab bar for Colors / Fonts
                TabBar {
                    id: editTabBar
                    Layout.fillWidth: true

                    background: Rectangle {
                        color: bgDark
                        radius: 4
                    }

                    TabButton {
                        text: "Colors"
                        contentItem: Text {
                            text: parent.text
                            color: parent.checked ? accentBlue : textMuted
                            font.pixelSize: 12
                            horizontalAlignment: Text.AlignHCenter
                        }
                        background: Rectangle {
                            color: parent.checked ? bgLight : "transparent"
                            radius: 4
                        }
                    }

                    TabButton {
                        text: "Fonts"
                        contentItem: Text {
                            text: parent.text
                            color: parent.checked ? accentBlue : textMuted
                            font.pixelSize: 12
                            horizontalAlignment: Text.AlignHCenter
                        }
                        background: Rectangle {
                            color: parent.checked ? bgLight : "transparent"
                            radius: 4
                        }
                    }
                }

                // Content stack
                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: editTabBar.currentIndex

                    // Colors tab
                    ScrollView {
                        clip: true

                        GridLayout {
                            width: parent.width - 20
                            columns: 2
                            rowSpacing: 8
                            columnSpacing: 15

                            // Background colors
                            Text { text: "Background Colors"; font.bold: true; color: accentPink; Layout.columnSpan: 2 }

                            ColorEditor { colorKey: "bgDark"; colorLabel: "Dark Background"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "bgDarker"; colorLabel: "Darker Background"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "bgMedium"; colorLabel: "Medium Background"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "bgLight"; colorLabel: "Light Background"; currentScheme: preferencesDialog.currentScheme }

                            // Accent colors
                            Text { text: "Accent Colors"; font.bold: true; color: accentPink; Layout.columnSpan: 2; Layout.topMargin: 10 }

                            ColorEditor { colorKey: "accentPrimary"; colorLabel: "Primary Accent"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "accentSecondary"; colorLabel: "Secondary Accent"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "accentTertiary"; colorLabel: "Tertiary Accent"; currentScheme: preferencesDialog.currentScheme }

                            // Text colors
                            Text { text: "Text Colors"; font.bold: true; color: accentPink; Layout.columnSpan: 2; Layout.topMargin: 10 }

                            ColorEditor { colorKey: "textPrimary"; colorLabel: "Primary Text"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "textSecondary"; colorLabel: "Secondary Text"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "textMuted"; colorLabel: "Muted Text"; currentScheme: preferencesDialog.currentScheme }

                            // Status colors
                            Text { text: "Status Colors"; font.bold: true; color: accentPink; Layout.columnSpan: 2; Layout.topMargin: 10 }

                            ColorEditor { colorKey: "borderColor"; colorLabel: "Border Color"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "success"; colorLabel: "Success"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "warning"; colorLabel: "Warning"; currentScheme: preferencesDialog.currentScheme }
                            ColorEditor { colorKey: "error"; colorLabel: "Error"; currentScheme: preferencesDialog.currentScheme }
                        }
                    }

                    // Fonts tab
                    ColumnLayout {
                        spacing: 15

                        Text { text: "Font Settings"; font.bold: true; color: accentPink }

                        GridLayout {
                            columns: 2
                            rowSpacing: 10
                            columnSpacing: 15

                            Text { text: "Font Family:"; color: textLight }
                            ComboBox {
                                id: fontFamilyCombo
                                Layout.preferredWidth: 200
                                model: ["system-ui", "Arial", "Helvetica", "Roboto", "Source Sans Pro", "Open Sans", "Lato", "SF Pro"]

                                background: Rectangle {
                                    color: bgLight
                                    border.color: borderColor
                                    radius: 4
                                }

                                contentItem: Text {
                                    text: fontFamilyCombo.displayText
                                    color: textLight
                                    font.pixelSize: 12
                                    verticalAlignment: Text.AlignVCenter
                                    leftPadding: 8
                                }

                                onCurrentTextChanged: {
                                    if (currentScheme.font) {
                                        currentScheme.font.family = currentText
                                    }
                                }
                            }

                            Text { text: "Small Size:"; color: textLight }
                            SpinBox {
                                id: smallSizeSpinner
                                from: 8
                                to: 24
                                value: currentScheme.font ? currentScheme.font.sizeSmall || 10 : 10

                                background: Rectangle {
                                    color: bgLight
                                    border.color: borderColor
                                    radius: 4
                                }

                                contentItem: Text {
                                    text: smallSizeSpinner.value
                                    color: textLight
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }

                                onValueChanged: {
                                    if (currentScheme.font) {
                                        currentScheme.font.sizeSmall = value
                                    }
                                }
                            }

                            Text { text: "Medium Size:"; color: textLight }
                            SpinBox {
                                id: mediumSizeSpinner
                                from: 10
                                to: 28
                                value: currentScheme.font ? currentScheme.font.sizeMedium || 12 : 12

                                background: Rectangle {
                                    color: bgLight
                                    border.color: borderColor
                                    radius: 4
                                }

                                contentItem: Text {
                                    text: mediumSizeSpinner.value
                                    color: textLight
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }

                                onValueChanged: {
                                    if (currentScheme.font) {
                                        currentScheme.font.sizeMedium = value
                                    }
                                }
                            }

                            Text { text: "Large Size:"; color: textLight }
                            SpinBox {
                                id: largeSizeSpinner
                                from: 12
                                to: 32
                                value: currentScheme.font ? currentScheme.font.sizeLarge || 14 : 14

                                background: Rectangle {
                                    color: bgLight
                                    border.color: borderColor
                                    radius: 4
                                }

                                contentItem: Text {
                                    text: largeSizeSpinner.value
                                    color: textLight
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }

                                onValueChanged: {
                                    if (currentScheme.font) {
                                        currentScheme.font.sizeLarge = value
                                    }
                                }
                            }

                            Text { text: "Header Size:"; color: textLight }
                            SpinBox {
                                id: headerSizeSpinner
                                from: 14
                                to: 48
                                value: currentScheme.font ? currentScheme.font.sizeHeader || 16 : 16

                                background: Rectangle {
                                    color: bgLight
                                    border.color: borderColor
                                    radius: 4
                                }

                                contentItem: Text {
                                    text: headerSizeSpinner.value
                                    color: textLight
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }

                                onValueChanged: {
                                    if (currentScheme.font) {
                                        currentScheme.font.sizeHeader = value
                                    }
                                }
                            }
                        }

                        // Preview
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 100
                            color: currentScheme.colors ? currentScheme.colors.bgDark || bgDark : bgDark
                            border.color: borderColor
                            radius: 6

                            ColumnLayout {
                                anchors.centerIn: parent
                                spacing: 5

                                Text {
                                    text: "Preview Text"
                                    font.pixelSize: headerSizeSpinner.value
                                    font.bold: true
                                    font.family: fontFamilyCombo.currentText
                                    color: currentScheme.colors ? currentScheme.colors.textPrimary || textLight : textLight
                                }
                                Text {
                                    text: "This is sample text in the selected font"
                                    font.pixelSize: mediumSizeSpinner.value
                                    font.family: fontFamilyCombo.currentText
                                    color: currentScheme.colors ? currentScheme.colors.textSecondary || textMuted : textMuted
                                }
                            }
                        }

                        Item { Layout.fillHeight: true }
                    }
                }
            }
        }
    }

    footer: Rectangle {
        color: bgMedium
        height: 60
        radius: 8

        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: parent.radius
            color: parent.color
        }

        Rectangle {
            anchors.top: parent.top
            width: parent.width
            height: 1
            color: borderColor
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 10

            Item { Layout.fillWidth: true }

            Button {
                text: "Cancel"
                Layout.preferredWidth: 100

                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    border.color: borderColor
                    radius: 4
                }

                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: preferencesDialog.reject()
            }

            Button {
                text: "Apply"
                Layout.preferredWidth: 100

                background: Rectangle {
                    color: parent.hovered ? accentBlue : bgLight
                    border.color: accentBlue
                    radius: 4
                }

                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: {
                    applyCurrentScheme()
                }
            }

            Button {
                text: "OK"
                Layout.preferredWidth: 100

                background: Rectangle {
                    color: parent.hovered ? accentPink : accentBlue
                    radius: 4
                }

                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 12
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: {
                    applyCurrentScheme()
                    preferencesDialog.accept()
                }
            }
        }
    }

    // Save custom scheme dialog
    Dialog {
        id: saveCustomDialog
        title: "Save Custom Scheme"
        modal: true
        width: 400
        height: 200

        background: Rectangle {
            color: bgMedium
            border.color: borderColor
            radius: 6
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 10

            Text {
                text: "Name:"
                color: textLight
            }

            TextField {
                id: customNameField
                Layout.fillWidth: true
                placeholderText: "My Custom Theme"
                color: textLight
                placeholderTextColor: textMuted

                background: Rectangle {
                    color: bgLight
                    border.color: borderColor
                    radius: 4
                }
            }

            Text {
                text: "Description:"
                color: textLight
            }

            TextField {
                id: customDescField
                Layout.fillWidth: true
                placeholderText: "Optional description"
                color: textLight
                placeholderTextColor: textMuted

                background: Rectangle {
                    color: bgLight
                    border.color: borderColor
                    radius: 4
                }
            }
        }

        footer: RowLayout {
            spacing: 10

            Item { Layout.fillWidth: true }

            Button {
                text: "Cancel"
                onClicked: saveCustomDialog.reject()

                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    border.color: borderColor
                    radius: 4
                }

                contentItem: Text {
                    text: parent.text
                    color: textLight
                }
            }

            Button {
                text: "Save"
                onClicked: {
                    if (customNameField.text.trim() !== "") {
                        var schemeId = customNameField.text.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '')
                        if (preferencesManager) {
                            preferencesManager.saveCurrentAsCustom(
                                customNameField.text,
                                customDescField.text,
                                schemeId
                            )
                            loadCustomSchemes()
                        }
                        saveCustomDialog.accept()
                    }
                }

                background: Rectangle {
                    color: parent.hovered ? accentPink : accentBlue
                    radius: 4
                }

                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.bold: true
                }
            }
        }
    }

    // Color editor component
    component ColorEditor: RowLayout {
        property string colorKey: ""
        property string colorLabel: ""
        property var currentScheme: ({})

        spacing: 10

        Text {
            text: colorLabel + ":"
            color: textLight
            font.pixelSize: 11
            Layout.preferredWidth: 120
        }

        Rectangle {
            Layout.preferredWidth: 30
            Layout.preferredHeight: 20
            color: currentScheme.colors ? (currentScheme.colors[colorKey] || "#888888") : "#888888"
            border.color: textMuted
            border.width: 1
            radius: 3

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    colorPickerDialog.colorKey = colorKey
                    colorPickerDialog.currentColor = parent.color
                    colorPickerDialog.open()
                }
            }
        }

        TextField {
            Layout.preferredWidth: 80
            text: currentScheme.colors ? (currentScheme.colors[colorKey] || "#888888") : "#888888"
            font.pixelSize: 10
            color: textLight

            background: Rectangle {
                color: bgLight
                border.color: borderColor
                radius: 3
            }

            onTextEdited: {
                if (currentScheme.colors && text.match(/^#[0-9A-Fa-f]{6}$/)) {
                    currentScheme.colors[colorKey] = text
                }
            }
        }
    }

    // Simple color picker dialog
    Dialog {
        id: colorPickerDialog
        title: "Pick Color"
        modal: true
        width: 300
        height: 350

        property string colorKey: ""
        property color currentColor: "#ffffff"

        background: Rectangle {
            color: bgMedium
            border.color: borderColor
            radius: 6
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 10

            // Hex input
            RowLayout {
                Text { text: "Hex:"; color: textLight }
                TextField {
                    id: hexInput
                    Layout.fillWidth: true
                    text: colorPickerDialog.currentColor.toString()
                    color: textLight

                    background: Rectangle {
                        color: bgLight
                        border.color: borderColor
                        radius: 3
                    }

                    onTextEdited: {
                        if (text.match(/^#[0-9A-Fa-f]{6}$/)) {
                            colorPickerDialog.currentColor = text
                        }
                    }
                }
            }

            // Preview
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 50
                color: colorPickerDialog.currentColor
                border.color: textMuted
                radius: 4
            }

            // Quick color palette
            GridLayout {
                columns: 8
                rowSpacing: 4
                columnSpacing: 4

                Repeater {
                    model: [
                        "#F5A9B8", "#5BCEFA", "#FFFFFF", "#D60270", "#9B4F96", "#0038A8",
                        "#FCF434", "#9C59D1", "#FF0018", "#FFA52C", "#FFFF41", "#008018",
                        "#0000F9", "#86007D", "#000000", "#333333", "#666666", "#999999",
                        "#CCCCCC", "#FFFFFF", "#FF6B6B", "#66FF99", "#66B3FF", "#FFB366"
                    ]

                    Rectangle {
                        width: 25
                        height: 25
                        color: modelData
                        border.color: textMuted
                        border.width: 1
                        radius: 3

                        MouseArea {
                            anchors.fill: parent
                            onClicked: {
                                colorPickerDialog.currentColor = modelData
                                hexInput.text = modelData
                            }
                        }
                    }
                }
            }
        }

        footer: RowLayout {
            spacing: 10

            Item { Layout.fillWidth: true }

            Button {
                text: "Cancel"
                onClicked: colorPickerDialog.reject()

                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    border.color: borderColor
                    radius: 4
                }

                contentItem: Text {
                    text: parent.text
                    color: textLight
                }
            }

            Button {
                text: "Apply"
                onClicked: {
                    if (currentScheme.colors) {
                        currentScheme.colors[colorPickerDialog.colorKey] = colorPickerDialog.currentColor.toString()
                        // Force UI update
                        var temp = currentScheme
                        currentScheme = {}
                        currentScheme = temp
                    }
                    colorPickerDialog.accept()
                }

                background: Rectangle {
                    color: parent.hovered ? accentPink : accentBlue
                    radius: 4
                }

                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.bold: true
                }
            }
        }
    }

    // Functions
    function loadPresets() {
        presetsModel.clear()

        if (preferencesManager) {
            var presets = preferencesManager.getAllPresets()
            for (var i = 0; i < presets.length; i++) {
                presetsModel.append({
                    schemeId: presets[i].id,
                    name: presets[i].name,
                    description: presets[i].description
                })
            }
        }
    }

    function loadCustomSchemes() {
        customModel.clear()

        if (preferencesManager) {
            var customs = preferencesManager.getAllCustomSchemes()
            for (var i = 0; i < customs.length; i++) {
                customModel.append({
                    schemeId: customs[i].id,
                    name: customs[i].name,
                    description: customs[i].description
                })
            }
        }
    }

    function loadScheme(schemeId, isPreset) {
        if (preferencesManager) {
            var schemeInfo = preferencesManager.getSchemeInfo(schemeId)
            if (schemeInfo) {
                currentScheme = JSON.parse(JSON.stringify(schemeInfo)) // Deep copy
                currentSchemeName = schemeId

                // Update font controls
                if (currentScheme.font) {
                    fontFamilyCombo.currentIndex = fontFamilyCombo.model.indexOf(currentScheme.font.family) || 0
                    smallSizeSpinner.value = currentScheme.font.sizeSmall || 10
                    mediumSizeSpinner.value = currentScheme.font.sizeMedium || 12
                    largeSizeSpinner.value = currentScheme.font.sizeLarge || 14
                    headerSizeSpinner.value = currentScheme.font.sizeHeader || 16
                }
            }
        }
    }

    function applyCurrentScheme() {
        if (preferencesManager && currentSchemeName) {
            preferencesManager.setScheme(currentSchemeName)
        }
    }

    onOpened: {
        loadPresets()
        loadCustomSchemes()

        // Load current scheme
        if (preferencesManager) {
            var currentName = preferencesManager.getCurrentSchemeName()
            var schemeInfo = preferencesManager.getSchemeInfo(currentName)
            if (schemeInfo) {
                currentScheme = JSON.parse(JSON.stringify(schemeInfo))
                currentSchemeName = currentName
            }
        }
    }
}
