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
import QtQuick.Window 2.15

// Generic tool UI template
Item {
    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // Tool description
        GroupBox {
            title: "Tool Information"
            Layout.fillWidth: true

            Label {
                text: "This tool has not been implemented yet.\n\nPlease check back later or contact the development team."
                wrapMode: Text.Wrap
            }
        }

        // Spacer
        Item {
            Layout.fillHeight: true
        }

        // Action buttons
        RowLayout {
            Layout.fillWidth: true

            Item { Layout.fillWidth: true }

            Button {
                text: "Close"
                onClicked: {
                    var win = Window.window
                    if (win) win.close()
                }
            }
        }
    }
}
