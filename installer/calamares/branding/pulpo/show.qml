// Pulpo Preview — Calamares slideshow (slideshowAPI 1).
//
// A single static slide: the UEFI boot splash with the tagline.
// No animation, no version string, no network copy. If this QML
// fails to load, Calamares logs a warning and installs without a
// slideshow — it never fails the install.
import QtQuick 2.0

Rectangle {
    id: root
    width: 800
    height: 600
    color: "#1E1A26"

    Image {
        anchors.fill: parent
        source: "welcome.png"
        fillMode: Image.PreserveAspectCrop
    }
}
