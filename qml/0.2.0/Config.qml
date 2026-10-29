pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls as Controls
import Quickshell
import Quickshell.Wayland

Loader {
    id: overlay
    property var shell: null
    property var manifest: null
    // Injected by Omarchy after load; standalone Settings supplies its Service.
    property var service: null
    active: service !== null
    function open(payloadJson) {
        if (!service || service.control.opened || service.control.shuttingDown) return
        if (item) item.resetScroll()
        service.control.open(payloadJson)
    }
    function close() { if (service) service.control.close() }
    sourceComponent: Item {
    id: view
    readonly property var control: overlay.service.control
    function resetScroll() { settingsScroll.contentY = 0 }
    readonly property bool moreBelow: settingsScroll.contentY + settingsScroll.height < settingsScroll.contentHeight - 1
    readonly property bool moreAbove: settingsScroll.contentY > 1

    function revealItem(item) {
        // Fixed footer actions are not part of the scrollable settings body.
        var ancestor = item
        while (ancestor && ancestor !== content) ancestor = ancestor.parent
        if (!ancestor) return
        var y = item.mapToItem(content, 0, 0).y
        var maximum = Math.max(0, settingsScroll.contentHeight - settingsScroll.height)
        if (y < settingsScroll.contentY)
            settingsScroll.contentY = Math.max(0, y)
        else if (y + item.height > settingsScroll.contentY + settingsScroll.height)
            settingsScroll.contentY = Math.min(maximum, y + item.height - settingsScroll.height)
    }
    function scrollBy(amount) {
        settingsScroll.contentY = Math.max(0, Math.min(
            Math.max(0, settingsScroll.contentHeight - settingsScroll.height),
            settingsScroll.contentY + amount))
    }

    component Label: Text { textFormat: Text.PlainText; color: "#c7d6c6"; font.pixelSize: 14 }
    component Action: Controls.Button {
        id: actionButton
        required property string label
        property bool selected: false
        text: label
        width: 170
        height: 42
        focusPolicy: Qt.StrongFocus
        hoverEnabled: true
        Accessible.name: label
        onActiveFocusChanged: if (activeFocus) view.revealItem(actionButton)
        background: Rectangle {
            color: !actionButton.enabled ? "#26352f" : actionButton.selected ? "#a8d78b" : actionButton.hovered ? "#41694d" : "#2e513b"
            border.color: actionButton.activeFocus ? "#f1d69a" : actionButton.selected ? "#d7edbb" : "#6c9270"
            opacity: actionButton.enabled ? 1 : 0.5
        }
        contentItem: Label {
            text: actionButton.label
            color: actionButton.selected ? "#142918" : "#eff5df"
            font.pixelSize: 13
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            opacity: actionButton.enabled ? 1 : 0.5
        }
    }
    component DensityRow: Column {
        id: densityRow
        required property string settingKey
        required property string label
        required property string description
        width: parent.width
        spacing: 4
        readonly property bool ready: !!control.effective.scenery
        readonly property real currentValue: ready ? control.fieldValue("scenery", settingKey) : 0
        Row {
            width: parent.width
            Label { width: parent.width - 160; text: densityRow.label; color: "#eff5df" }
            Label {
                width: 160
                horizontalAlignment: Text.AlignRight
                text: control.validationError ? qsTr("Unavailable") : !control.settingsValid ? qsTr("Checking…") :
                      (densityRow.currentValue === 0 ? qsTr("Off") : Math.round(densityRow.currentValue * 100) + "%")
            }
        }
        Row {
            width: parent.width
            spacing: 10
            Controls.Slider {
                id: densitySlider
                objectName: "density-" + densityRow.settingKey
                width: Math.max(40, parent.width - 104)
                height: 34
                palette.highlight: "#a8d78b"
                from: 0
                to: 2
                stepSize: 0.1
                value: densityRow.currentValue
                enabled: control.editable && densityRow.ready
                Accessible.name: densityRow.label + qsTr(" density")
                Accessible.description: densityRow.description
                onValueChanged: if (enabled && densityRow.ready && Math.abs(value - densityRow.currentValue) > 0.000001) control.setScenery(densityRow.settingKey, value)
                onActiveFocusChanged: if (activeFocus) view.revealItem(densityRow)
            }
            Action {
                label: qsTr("Reset")
                objectName: "reset-" + densityRow.settingKey
                Accessible.name: densityRow.label + qsTr(" reset to default")
                width: 94
                height: 34
                enabled: control.editable && control.hasOverride("scenery", densityRow.settingKey)
                onClicked: control.resetField("scenery", densityRow.settingKey)
            }
        }
        Label { width: parent.width; wrapMode: Text.WordWrap; text: densityRow.description; font.pixelSize: 12; color: "#9cb39e" }
    }
    component SpeciesRow: Column {
        id: speciesRow
        required property string settingKey
        required property string label
        required property string description
        width: parent.width
        spacing: 4
        Row {
            width: parent.width
            spacing: 10
            Controls.CheckBox {
                id: speciesToggle
                objectName: "animal-" + speciesRow.settingKey
                width: parent.width - 104
                text: speciesRow.label
                palette.windowText: "#eff5df"
                palette.highlight: "#a8d78b"
                checked: !!control.effective.animals && control.fieldValue("animals", speciesRow.settingKey)
                enabled: control.editable && !!control.effective.animals
                Accessible.name: speciesRow.label
                Accessible.description: speciesRow.description
                onToggled: control.toggleAnimal(speciesRow.settingKey)
                onActiveFocusChanged: if (activeFocus) view.revealItem(speciesRow)
            }
            Action {
                label: qsTr("Reset")
                objectName: "reset-" + speciesRow.settingKey
                Accessible.name: speciesRow.label + qsTr(" reset to default")
                width: 94
                height: 34
                enabled: control.editable && control.hasOverride("animals", speciesRow.settingKey)
                onClicked: control.resetField("animals", speciesRow.settingKey)
            }
        }
        Label {
            width: parent.width
            wrapMode: Text.WordWrap
            text: speciesRow.description
            font.pixelSize: 12
            color: "#9cb39e"
        }
    }

    PanelWindow {
        visible: control.opened
        anchors { top: true; bottom: true; left: true; right: true }
        color: "#a6102018"
        WlrLayershell.namespace: "omarchasaurus-control-room"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
        exclusionMode: ExclusionMode.Ignore

        Rectangle {
            objectName: "control-room-panel"
            Accessible.role: Accessible.Pane
            Accessible.name: qsTr("Omarchasaurus Control Room")
            anchors.centerIn: parent
            width: Math.min(720, parent.width - 32)
            height: Math.min(980, parent.height - 32)
            color: "#14291f"
            border.color: "#87ac77"
            focus: true
            Keys.onEscapePressed: control.dismiss()
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_PageDown) view.scrollBy(settingsScroll.height * 0.82)
                else if (event.key === Qt.Key_PageUp) view.scrollBy(-settingsScroll.height * 0.82)
                else if (event.key === Qt.Key_Down) view.scrollBy(64)
                else if (event.key === Qt.Key_Up) view.scrollBy(-64)
                else if (event.key === Qt.Key_Home) settingsScroll.contentY = 0
                else if (event.key === Qt.Key_End) view.scrollBy(settingsScroll.contentHeight)
                else return
                event.accepted = true
            }
            Column {
                id: header
                anchors { top: parent.top; left: parent.left; right: parent.right; margins: 24 }
                spacing: 8
                Label { text: "OMARCHASAURUS"; font.pixelSize: 28; font.bold: true; color: "#d7edbb" }
                Label { width: parent.width; wrapMode: Text.WordWrap; text: qsTr("A living dinosaur valley, drawn with truecolor ASCII inside a real terminal. No native renderer or build step.") }
                Label { width: parent.width; wrapMode: Text.WordWrap; text: control.sessionStatus; color: "#d7edbb"; font.pixelSize: 13 }
                Rectangle { width: parent.width; height: 1; color: "#41694d" }
            }
            Column {
                id: footer
                anchors { bottom: parent.bottom; left: parent.left; right: parent.right; margins: 24 }
                spacing: 10
                Label {
                    width: parent.width
                    text: view.moreBelow ? qsTr("↓ More settings below · scroll or Page Down") :
                          view.moreAbove ? qsTr("↑ More settings above · scroll or Page Up") : qsTr("All settings visible")
                    color: view.moreBelow || view.moreAbove ? "#edd39c" : "#9cb39e"
                    Accessible.role: Accessible.StaticText
                    Accessible.name: text
                }
                Label { width: parent.width; wrapMode: Text.WrapAnywhere; visible: !!text; text: control.actionStatus; color: "#edd39c"; font.pixelSize: 13 }
                Flow {
                    width: parent.width
                    spacing: 10
                    Action { label: control.saving ? qsTr("Saving…") : qsTr("Apply Settings"); objectName: "apply-settings"; enabled: control.editable && control.settingsValid && control.dirty; onClicked: control.applySettings() }
                    Action { label: qsTr("Enter Immersion"); width: 200; selected: true; enabled: control.editable && control.settingsValid; onClicked: control.beginSession("preview") }
                    Action { label: qsTr("Surface"); width: 100; onClicked: { control.pendingSession = ""; control.request("stop") } }
                    Action { label: qsTr("Close · Esc"); width: 120; onClicked: control.dismiss() }
                }
            }
            Flickable {
                id: settingsScroll
                anchors { top: header.bottom; bottom: footer.top; left: parent.left; right: parent.right; leftMargin: 24; rightMargin: 24; topMargin: 12; bottomMargin: 12 }
                contentWidth: width - 24
                contentHeight: content.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                Controls.ScrollBar.vertical: Controls.ScrollBar {
                    policy: Controls.ScrollBar.AlwaysOn
                    visible: settingsScroll.contentHeight > settingsScroll.height
                    minimumSize: 0.12
                    width: 14
                    contentItem: Rectangle { implicitWidth: 10; color: "#b1d68e"; radius: 5 }
                    background: Rectangle { color: "#365343"; radius: 5 }
                }
                Column {
                    id: content
                    width: settingsScroll.contentWidth
                    spacing: 16
                    Action {
                        label: control.randomizing ? qsTr("Randomizing…") : qsTr("Randomize Valley")
                        objectName: "randomize-valley"
                        width: 210
                        enabled: control.canRandomize
                        Accessible.description: qsTr("Stage randomized scenery and optional animals with rotating visitors. Preserve the colour palette, reduced motion and population limits. Review the choices and Apply Settings; no automatic save or live reroll.")
                        onClicked: control.randomizeValley()
                    }
                    Label {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("Try a different valley in one click: randomize scenery and optional animals, and turn on rotating visitors. Your colour palette, reduced motion and population limits stay unchanged. Review the staged choices, then Apply Settings. Running scenes never reroll silently.")
                        color: "#9cb39e"
                        font.pixelSize: 12
                    }
                    Rectangle { width: parent.width; height: 1; color: "#41694d" }
                    Label { text: qsTr("Test unique event"); font.pixelSize: 18; color: "#eff5df" }
                    Label {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("Temporary tests isolate the target event, enable its prerequisites and reserve animal seats in a fresh preview. Saved palette and motion choices remain. The Diplodocus test temporarily uses visiting behaviour in either palette. Tests never save staged changes. Apply / Discard staged changes first. Surface an existing preview before testing another event.")
                        color: "#9cb39e"
                        font.pixelSize: 12
                    }
                    Controls.ComboBox {
                        id: eventSelector
                        objectName: "test-event-selector"
                        width: parent.width
                        textRole: "label"
                        valueRole: "key"
                        model: [
                            { key: "shower", label: qsTr("Gentle shower") },
                            { key: "rainbow", label: qsTr("Seven-colour rainbow") },
                            { key: "hatching", label: qsTr("Brachiosaurus hatching") },
                            { key: "flock", label: qsTr("Pteranodon flock") },
                            { key: "diplodocus", label: qsTr("Diplodocus visit") },
                            { key: "volcano", label: qsTr("Soft volcano puff") }
                        ]
                        palette.button: "#2e513b"
                        palette.buttonText: "#eff5df"
                        palette.base: "#14291f"
                        palette.text: "#eff5df"
                        palette.highlight: "#a8d78b"
                        palette.highlightedText: "#14291f"
                        enabled: control.editable && control.settingsValid && !control.dirty
                        focusPolicy: Qt.StrongFocus
                        Accessible.name: qsTr("Unique event to test")
                        Accessible.description: qsTr("Choose one temporary event preview. Apply or discard staged settings before testing.")
                        onActiveFocusChanged: if (activeFocus) view.revealItem(eventSelector)
                    }
                    Action {
                        label: qsTr("Test Event")
                        objectName: "test-event-button"
                        enabled: control.editable && control.settingsValid && !control.dirty
                        Accessible.description: qsTr("Open the selected event in a fresh fullscreen preview using saved settings, without saving staged changes.")
                        onClicked: control.testEvent(eventSelector.currentValue)
                    }
                    Rectangle { width: parent.width; height: 1; color: "#41694d" }
                    Label { text: qsTr("Colour palette only"); font.pixelSize: 18; color: "#eff5df" }
                    Flow {
                        width: parent.width
                        spacing: 10
                        Action { label: qsTr("Morning"); objectName: "palette-morning"; selected: control.effective.preset === "morning"; enabled: control.editable; onClicked: control.selectPalette("morning") }
                        Action { label: qsTr("Dusk"); objectName: "palette-dusk"; selected: control.effective.preset === "dusk"; enabled: control.editable; onClicked: control.selectPalette("dusk") }
                        Action { label: qsTr("Reset"); objectName: "reset-palette"; Accessible.name: qsTr("Colour palette reset to default"); enabled: control.editable && Object.prototype.hasOwnProperty.call(control.overrides, "preset"); onClicked: control.resetPalette() }
                    }
                    Label { width: parent.width; wrapMode: Text.WordWrap; text: qsTr("Morning and Dusk change colours only, not motion, scenery, animals or visitor schedules. Reset restores the default palette. Each Reset below restores only that setting's default."); color: "#9cb39e"; font.pixelSize: 12 }
                    Label { text: qsTr("Motion"); font.pixelSize: 18; color: "#eff5df" }
                    Row {
                        width: parent.width
                        spacing: 10
                        Controls.CheckBox {
                            id: reducedMotionToggle
                            objectName: "motion-reducedMotion"
                            width: parent.width - 104
                            text: qsTr("Reduced motion")
                            palette.windowText: "#eff5df"
                            palette.highlight: "#a8d78b"
                            checked: !!control.effective.motion && control.fieldValue("motion", "reducedMotion")
                            enabled: control.editable && !!control.effective.motion
                            Accessible.name: qsTr("Reduced motion")
                            Accessible.description: qsTr("Calmer motion in either colour palette. This choice is independent of Morning and Dusk.")
                            onToggled: control.toggleMotion()
                            onActiveFocusChanged: if (activeFocus) view.revealItem(reducedMotionToggle)
                        }
                        Action { label: qsTr("Reset"); objectName: "reset-reducedMotion"; Accessible.name: qsTr("Reduced motion reset to default"); width: 94; height: 34; enabled: control.editable && control.hasOverride("motion", "reducedMotion"); onClicked: control.resetField("motion", "reducedMotion") }
                    }
                    Label { text: qsTr("Animals and crowding"); font.pixelSize: 18; color: "#eff5df" }
                    Label { width: parent.width; wrapMode: Text.WordWrap; text: qsTr("Brachiosaurus always stays. The animal limit is a ceiling, not a target. Visible animals keep their places; new arrivals never remove them mid-scene. At a full limit, a pass or surfacing can be skipped until another natural entry. Lowering the limit or switching an animal Off applies immediately.") }
                    Row {
                        width: parent.width
                        spacing: 10
                        Controls.CheckBox {
                            id: randomVisitorsToggle
                            objectName: "population-randomVisitors"
                            width: parent.width - 104
                            text: qsTr("Random visitors")
                            palette.windowText: "#eff5df"
                            palette.highlight: "#a8d78b"
                            checked: !!control.effective.population && control.fieldValue("population", "randomVisitors")
                            enabled: control.editable && !!control.effective.population
                            Accessible.name: qsTr("Random visitors")
                            Accessible.description: qsTr("Choose one enabled ground dinosaur or one family encounter at a time; flyers remain separate.")
                            onToggled: control.toggleRandomVisitors()
                            onActiveFocusChanged: if (activeFocus) view.revealItem(randomVisitorsToggle)
                        }
                        Action { label: qsTr("Reset"); objectName: "reset-randomVisitors"; Accessible.name: qsTr("Random visitors reset to default"); width: 94; height: 34; enabled: control.editable && control.hasOverride("population", "randomVisitors"); onClicked: control.resetField("population", "randomVisitors") }
                    }
                    Label {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("One random enabled ground encounter starts in view when space permits. Once the whole encounter leaves, the next enters from the left; with several choices, the next species differs. New sessions shuffle independently. Triceratops can bring one counted calf. A Parasaurolophus family needs families enabled, a nonzero family cap and at least two free animal slots; random mode admits one family encounter, even with a family cap of 2. Occupied seats are never taken from visible animals. Brachiosaurus stays; Plesiosaurus, Diplodocus and flyers remain separate. Off keeps enabled roamers and families on repeating, viewport-safe routes.")
                        color: "#9cb39e"
                        font.pixelSize: 12
                    }
                    SpeciesRow { settingKey: "trexEnabled"; label: qsTr("Tyrannosaurus rex"); description: qsTr("Walks and stops to look around, make a silent playful roar or sit with bent knees. Body and skull keep their shape. Reduced motion substitutes a calm head tilt for the automatic roar; clicking still moves its head, jaw and tail.") }
                    SpeciesRow { settingKey: "triceratopsEnabled"; label: qsTr("Triceratops"); description: qsTr("One three-horned grazer and, when the animal ceiling permits, one smaller calf with stubby horns. The calf follows and gently nuzzles its parent's flank during shared stops. Each uses one slot; a low ceiling keeps the adult alone.") }
                    SpeciesRow { settingKey: "stegosaurusEnabled"; label: qsTr("Stegosaurus"); description: qsTr("One plated grazer with a small head, feeding pauses and a swishing tail.") }
                    SpeciesRow { settingKey: "ankylosaurusEnabled"; label: qsTr("Ankylosaurus"); description: qsTr("One low armored animal on the front bank: waddles, naps, and wakes when clicked.") }
                    SpeciesRow { settingKey: "parasaurolophusEnabled"; label: qsTr("Parasaurolophus families"); description: qsTr("Families of 2–4 members: juveniles follow a leader and stop to drink at the lake shoreline. Each member counts individually toward the visible-animal ceiling.") }
                    SpeciesRow { settingKey: "plesiosaurusEnabled"; label: qsTr("Plesiosaurus · marine reptile"); description: qsTr("One marine reptile surfaces, looks around and dives in the lake; underwater phases are normal. Separate from Random visitors. While surfaced, it uses one animal slot.") }
                    SpeciesRow { settingKey: "diplodocusEnabled"; label: qsTr("Diplodocus · shoreline sauropod"); description: qsTr("One long, low sauropod drinks at the far bank. Its separate lake-residency choice controls whether it stays or visits, in either palette. Separate from Random visitors; each visible individual uses one slot.") }
                    SpeciesRow { settingKey: "diplodocusResident"; label: qsTr("Diplodocus stays by the lake"); description: qsTr("On keeps an enabled Diplodocus by the lake. Off (the default) makes it a scheduled visitor in either palette: it arrives every 10–20 active minutes, drinks and leaves to the right. Slow or busy visits never queue. This does not enable the species; its switch and Reset are separate.") }
                    SpeciesRow { settingKey: "pteranodonEnabled"; label: qsTr("Pteranodon · pterosaur"); description: qsTr("Three regular pterosaurs glide, flap and bank. Occasional flocks add up to five more on a 4–9 active-minute schedule, only when at least two slots are free; busy arrivals never queue. Each individual counts toward the limit. Reduced motion keeps banking quiet.") }
                    Row {
                        width: parent.width
                        spacing: 10
                        Label { text: qsTr("Maximum families"); width: Math.max(100, parent.width - 224); anchors.verticalCenter: parent.verticalCenter }
                        Controls.SpinBox {
                            id: familyLimit
                            objectName: "population-maxFamilies"
                            width: 110
                            from: 0
                            to: 2
                            editable: true
                            palette.text: "#eff5df"
                            palette.base: "#26352f"
                            palette.buttonText: "#eff5df"
                            value: control.effective.population ? control.fieldValue("population", "maxFamilies") : 1
                            enabled: control.editable && !!control.effective.population
                            Accessible.name: qsTr("Maximum Parasaurolophus families")
                            Accessible.description: qsTr("Range 0–2; 0 disables families. Each family needs at least two individual slots, so the visible-animal ceiling must be at least 3 including Brachiosaurus. Random mode allows one family encounter even when this cap is 2.")
                            onValueChanged: if (enabled && value !== control.fieldValue("population", "maxFamilies")) control.setPopulation("maxFamilies", value)
                            onActiveFocusChanged: if (activeFocus) view.revealItem(familyLimit)
                        }
                        Action { label: qsTr("Reset"); objectName: "reset-maxFamilies"; Accessible.name: qsTr("Maximum Parasaurolophus families reset to default"); width: 94; height: 34; enabled: control.editable && control.hasOverride("population", "maxFamilies"); onClicked: control.resetField("population", "maxFamilies") }
                    }
                    Label {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("Range 0–2; default 1; 0 disables families. A family needs at least two available individual slots for its leader and one juvenile, so the visible-animal ceiling must be at least 3 including Brachiosaurus. More juveniles fit only when slots remain. Random mode allows one family encounter even with a cap of 2.")
                        color: "#9cb39e"
                        font.pixelSize: 12
                    }
                    Row {
                        width: parent.width
                        spacing: 10
                        Label { text: qsTr("Maximum visible animals"); width: Math.max(100, parent.width - 224); anchors.verticalCenter: parent.verticalCenter }
                        Controls.SpinBox {
                            id: populationLimit
                            objectName: "population-maxVisible"
                            width: 110
                            from: 1
                            to: 128
                            editable: true
                            palette.text: "#eff5df"
                            palette.base: "#26352f"
                            palette.buttonText: "#eff5df"
                            value: control.effective.population ? control.fieldValue("population", "maxVisible") : 1
                            enabled: control.editable && !!control.effective.population
                            Accessible.name: qsTr("Maximum visible animals")
                            onValueChanged: if (enabled && value !== control.fieldValue("population", "maxVisible")) control.setPopulation("maxVisible", value)
                            onActiveFocusChanged: if (activeFocus) view.revealItem(populationLimit)
                        }
                        Action { label: qsTr("Reset"); objectName: "reset-maxVisible"; Accessible.name: qsTr("Maximum visible animals reset to default"); width: 94; height: 34; enabled: control.editable && control.hasOverride("population", "maxVisible"); onClicked: control.resetField("population", "maxVisible") }
                    }
                    Label {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("Range 1–128; at most 25 authored individuals plus one transient lake jumper, not a population target. Family members, the Triceratops calf, each flock member and the young Brachiosaurus use a slot. Existing occupants keep their seats until a natural exit or dive; new animals enter only when space is available. Lake clicks and hatching need a free slot and never make another dinosaur disappear. At 1 only the adult Brachiosaurus remains. Extra space does not spawn copies.")
                        color: "#9cb39e"
                        font.pixelSize: 12
                    }
                    Rectangle { width: parent.width; height: 1; color: "#41694d" }
                    Label { text: qsTr("Scenery density"); font.pixelSize: 18; color: "#eff5df" }
                    Label { width: parent.width; wrapMode: Text.WordWrap; text: qsTr("0% removes an optional category; 100% is normal; 200% is the bounded maximum. Reset restores that setting's default. The focal Brachiosaurus and tall tree remain.") }
                    DensityRow { settingKey: "treeDensity"; label: qsTr("Background trees"); description: qsTr("Trees behind the dinosaurs; does not change the tall browsing tree.") }
                    DensityRow { settingKey: "cycadDensity"; label: qsTr("Cycads"); description: qsTr("Short, broad-crowned foreground plants.") }
                    DensityRow { settingKey: "fernDensity"; label: qsTr("Ferns"); description: qsTr("Low foreground plants, kept away from the focal body and head.") }
                    DensityRow { settingKey: "rockDensity"; label: qsTr("Rocks"); description: qsTr("Foreground boulders and pebbles within fixed safe placement zones.") }
                    DensityRow { settingKey: "flowerDensity"; label: qsTr("Flowers"); description: qsTr("Small foreground blooms, kept below the focal dinosaurs.") }
                    DensityRow { settingKey: "lilyPadDensity"; label: qsTr("Lily pads"); description: qsTr("Floating leaves and occasional blooms within the lake.") }
                    DensityRow { settingKey: "cloudDensity"; label: qsTr("Ambient clouds"); description: qsTr("Slow background clouds only. A passing gentle shower and seven-colour rainbow are scheduled every 10–15 active minutes, even at zero ambient clouds. Does not change mountains, smoke or flying Pteranodon.") }
                    Flow {
                        width: parent.width
                        spacing: 10
                        Action { objectName: "nest-presence"; label: qsTr("Brachiosaurus nest"); selected: !!control.effective.scenery && control.fieldValue("scenery", "nestEnabled"); enabled: control.editable && !!control.effective.scenery; onClicked: control.toggleNest() }
                        Action { objectName: "reset-nest"; label: qsTr("Reset"); Accessible.name: qsTr("Brachiosaurus nest reset to default"); enabled: control.editable && control.hasOverride("scenery", "nestEnabled"); onClicked: control.resetField("scenery", "nestEnabled") }
                    }
                    Label { objectName: "nest-hatching-description"; width: parent.width; wrapMode: Text.WordWrap; text: qsTr("Brachiosaurus eggs wobble, crack and hatch on an 8–15 active-minute schedule when one animal slot is free. The young Brachiosaurus toddles to its parent; occupied seats are never taken. Nest Off disables hatching and cancels the current event. Turning it back on waits for a future scheduled hatch; busy attempts never queue."); color: "#9cb39e"; font.pixelSize: 12 }
                    Label { width: parent.width; wrapMode: Text.WrapAnywhere; visible: !!control.validationError; text: control.validationError; color: "#f0bf9c"; font.pixelSize: 13 }
                    Action { label: qsTr("Reload / Discard"); objectName: "reload-settings"; enabled: !control.saving && !control.localEventBusy && !control.randomizing && !control.shuttingDown; onClicked: { control.stagingGeneration++; control.dirty = false; control.externalChange = false; control.actionStatus = ""; control.readSettings() } }
                    Action { label: qsTr("Start All Outputs"); enabled: control.editable && control.settingsValid; onClicked: control.beginSession("start") }
                    Label { width: parent.width; wrapMode: Text.WrapAnywhere; text: qsTr("Sparse choices: ") + control.configPath + "\n" + qsTr("Changes are staged until Apply. Only explicit choices are saved; running scenes reload valid changes. Saves check observed changes and serialize cooperating writers. External editors do not share that lock: conflict detection is best effort, not a guarantee against concurrent overwrites."); color: "#9cb39e"; font.pixelSize: 12 }
                    Label { width: parent.width; wrapMode: Text.WordWrap; text: qsTr("Immersion: click a dinosaur for a head and tail reaction; open sky for a meteor; lake water for a small animal leap and splash. One meteor and one water jump can run together within the animal ceiling; extra clicks do not queue. Pteranodon are pterosaurs, not dinosaurs. Sound and idle remain OFF; Surface stops only owned sessions."); color: "#a8d78b"; font.pixelSize: 13 }
                }
            }
        }
    }
    Component.onDestruction: if (control) control.close()
    }
}
