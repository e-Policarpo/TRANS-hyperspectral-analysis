/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Spectral Axis Converter — switch a dataset's x-axis between
 * nm / eV / cm⁻¹ / Raman shift cm⁻¹ (relative to a laser excitation
 * wavelength). Backed by AppBackend.convertDatasetAxis(...).
 *
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: May 2026
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../components"

Item {
    id: root
    property var closeWindow: null

    // Theme colors mirror the other tool QML files.
    property var parentWindow: Window.window
    property color bgDark: parentWindow ? parentWindow.bgDark : "#1a1a2e"
    property color bgMedium: parentWindow ? parentWindow.bgMedium : "#2a2a3e"
    property color bgLight: parentWindow ? parentWindow.bgLight : "#3a3a4e"
    property color accentPink: parentWindow ? parentWindow.accentPink : "#F5A9B8"
    property color accentBlue: parentWindow ? parentWindow.accentBlue : "#5BCEFA"
    property color accentPurple: parentWindow ? parentWindow.accentPurple : "#9B4F96"
    property color textLight: parentWindow ? parentWindow.textLight : "#ffffff"
    property color textMuted: parentWindow ? parentWindow.textMuted : "#cccccc"

    // Mapping from ComboBox display label to the unit string the backend
    // expects. The Raman-shift label is enabled only when the user supplies
    // a positive excitation wavelength.
    readonly property var unitOptions: [
        { label: "Wavelength (nm)",        unit: "nm",          needsExcitation: false },
        { label: "Energy (eV)",            unit: "eV",          needsExcitation: false },
        { label: "Wavenumber (cm⁻¹)",       unit: "cm-1",        needsExcitation: false },
        { label: "Raman shift (cm⁻¹)",      unit: "raman_cm-1",  needsExcitation: true  }
    ]

    function selectedUnit() { return unitOptions[unitCombo.currentIndex] }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        Label {
            text: "Spectral Axis Converter"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Convert a dataset's spectral axis between equivalent units.\n" +
                  "Raman-shift conversion needs the laser excitation wavelength."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Source dataset"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                DatasetComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: backend.getDatasetList()
                }
            }
        }

        GroupBox {
            title: "Target unit"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 6

                ComboBox {
                    id: unitCombo
                    Layout.fillWidth: true
                    model: unitOptions.map(function(o) { return o.label })
                    currentIndex: 0
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Label {
                        text: "Excitation λ (nm):"
                        color: selectedUnit().needsExcitation ? textLight : textMuted
                        Layout.preferredWidth: 130
                    }
                    TextField {
                        id: excitationField
                        Layout.fillWidth: true
                        text: "532"
                        enabled: selectedUnit().needsExcitation
                        validator: DoubleValidator {
                            bottom: 0.0
                            decimals: 4
                            notation: DoubleValidator.StandardNotation
                        }
                        placeholderText: "e.g. 532, 633, 785"
                    }
                }

                Label {
                    visible: selectedUnit().needsExcitation
                    text: "Common Raman lasers: 532 nm, 633 nm, 785 nm, 1064 nm."
                    font.pixelSize: 10
                    color: textMuted
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        GroupBox {
            title: "Output dataset name (optional)"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                TextField {
                    id: outputNameField
                    Layout.fillWidth: true
                    placeholderText: "Leave blank to auto-name <source> (<unit>)"
                }
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Convert"
                enabled: datasetCombo.currentIndex >= 0 &&
                         (!selectedUnit().needsExcitation ||
                          parseFloat(excitationField.text) > 0)
                highlighted: true
                onClicked: doConvert()
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Close"
                onClicked: {
                    if (root.closeWindow) { root.closeWindow() }
                    else { var win = Window.window; if (win) win.close() }
                }
            }
        }
    }

    function doConvert() {
        var sel = selectedUnit()
        var lambda_ex = sel.needsExcitation ? parseFloat(excitationField.text) : 0.0
        var newName = backend.convertDatasetAxis(
            datasetCombo.currentText,
            sel.unit,
            isNaN(lambda_ex) ? 0.0 : lambda_ex,
            outputNameField.text
        )
        if (newName) {
            console.log("Created converted dataset:", newName)
            if (root.closeWindow) { root.closeWindow() }
        }
    }
}
