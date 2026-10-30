import QtQuick
import Quickshell
import Quickshell.Io

// The service owns staged choices and helpers, independently of overlay lifetime.
Item {
    id: root
    property var controller: null
    readonly property var shell: controller ? controller.shell : null
    property bool opened: false
    property string pendingSession: ""
    property bool shuttingDown: false
    readonly property bool localEventBusy: command.running || stopRequest.running
    readonly property bool finiteHelperBusy: settingsReader.running || resolver.running || sessionProbe.running || randomizer.running
    readonly property bool randomizing: randomizer.running
    readonly property bool canRandomize: settingsValid && documentReadable && !externalChange && !saving && !localEventBusy && !finiteHelperBusy && !readPending && !shuttingDown
    property int stagingGeneration: 0
    property bool readPending: false
    property string commandStatus: ""
    property string probeStatus: qsTr("Manual start only · idle OFF")
    property var overrides: ({})
    property var effective: ({})
    property bool documentValid: false
    property bool documentReadable: false
    readonly property bool saving: save.running
    readonly property bool editable: documentValid && !saving && !localEventBusy && !randomizing && !externalChange && !shuttingDown
    property string validationError: ""
    property string loadedSnapshot: "{}"
    property bool settingsValid: false
    property bool dirty: false
    property bool externalChange: false
    readonly property string sessionStatus: commandStatus || (controller ? controller.statusLine : probeStatus)
    property string actionStatus: ""
    readonly property string pluginId: "dailen.omarchasaurus"
    readonly property string pluginDir: decodeURIComponent(String(Qt.resolvedUrl("../../")).replace(/^file:\/\//, "").replace(/\/$/, ""))
    readonly property string launcher: pluginDir + "/scripts/launch-dinosaurs"
    readonly property string configDir: (Quickshell.env("XDG_CONFIG_HOME") || (Quickshell.env("HOME") + "/.config")) + "/omarchasaurus"
    readonly property string configPath: configDir + "/settings.json"

    function open(payloadJson) {
        if (opened || shuttingDown) return
        opened = true
        if (!dirty && !saving && !randomizing) {
            externalChange = false
            documentReadable = false
            documentValid = false
            settingsValid = false
            actionStatus = ""
            readSettings()
        }
        refreshSession()
    }
    function close() {
        opened = false
        // Closing during Apply must not start a session after the UI disappears.
        pendingSession = ""
    }
    function dismiss() {
        close()
        if (shell && typeof shell.hide === "function") shell.hide(pluginId)
    }
    function readSettings() {
        if (shuttingDown) return
        readPending = true
        readTimer.restart()
    }
    function readFailed(message) {
        if (dirty) {
            markExternalChange()
            return
        }
        stagingGeneration++
        documentReadable = false
        documentValid = false
        settingsValid = false
        effective = ({})
        validationError = qsTr("Cannot read sparse settings: ") + message
    }
    function shutdown() {
        shuttingDown = true
        stagingGeneration++
        pendingSession = ""
        readTimer.stop()
        validationTimer.stop()
        command.stop()
        settingsReader.stop()
        resolver.stop()
        sessionProbe.stop()
        randomizer.stop()
    }
    function loadSettings(text) {
        var value
        try {
            value = text.trim() ? JSON.parse(text) : ({})
            if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("expected object")
        } catch (error) {
            readFailed(qsTr("Invalid helper response."))
            return
        }
        var snapshot = JSON.stringify(value)
        if (!dirty && documentReadable && documentValid && settingsValid && snapshot === loadedSnapshot) return
        if (dirty) {
            // File watchers also report our atomic save and unchanged reloads.
            // Attribute those to the known baseline/pending write, not an editor.
            if (snapshot === loadedSnapshot || (save.inputSnapshot && snapshot === save.inputSnapshot)) return
            markExternalChange()
            return
        }
        documentReadable = true
        documentValid = false
        settingsValid = false
        effective = ({})
        overrides = value
        stagingGeneration++
        loadedSnapshot = snapshot
        externalChange = false
        validationError = ""
        queueValidation()
    }
    function markExternalChange() {
        externalChange = true
        stagingGeneration++
        actionStatus = qsTr("An external settings change was observed. Reload before applying; staged choices were not saved.")
    }
    function stage(next) {
        overrides = next
        stagingGeneration++
        dirty = true
        queueValidation()
    }
    function hasOverride(section, key) {
        return !!overrides[section] && Object.prototype.hasOwnProperty.call(overrides[section], key)
    }
    function fieldValue(section, key) {
        return hasOverride(section, key) ? overrides[section][key] : effective[section][key]
    }
    function selectPalette(name) {
        if (!editable) return
        var next = JSON.parse(JSON.stringify(overrides))
        next.preset = name
        stage(next)
    }
    function resetPalette() {
        if (!editable) return
        var next = JSON.parse(JSON.stringify(overrides))
        delete next.preset
        stage(next)
    }
    function toggleMotion() {
        if (!editable) return
        var next = JSON.parse(JSON.stringify(overrides))
        next.motion = next.motion || ({})
        next.motion.reducedMotion = !fieldValue("motion", "reducedMotion")
        stage(next)
    }
    function setScenery(key, value) {
        if (!editable) return
        var next = JSON.parse(JSON.stringify(overrides))
        next.scenery = next.scenery || ({})
        next.scenery[key] = Math.round(value * 10) / 10
        stage(next)
    }
    function toggleNest() {
        if (!editable || !effective.scenery) return
        var next = JSON.parse(JSON.stringify(overrides))
        next.scenery = next.scenery || ({})
        next.scenery.nestEnabled = !fieldValue("scenery", "nestEnabled")
        stage(next)
    }
    function toggleAnimal(key) {
        if (!editable || !effective.animals) return
        var next = JSON.parse(JSON.stringify(overrides))
        next.animals = next.animals || ({})
        next.animals[key] = !fieldValue("animals", key)
        stage(next)
    }
    function setPopulation(key, value) {
        if (!editable) return
        var next = JSON.parse(JSON.stringify(overrides))
        next.population = next.population || ({})
        next.population[key] = Math.round(value)
        stage(next)
    }
    function toggleRandomVisitors() {
        if (!editable || !effective.population) return
        var next = JSON.parse(JSON.stringify(overrides))
        next.population = next.population || ({})
        next.population.randomVisitors = !fieldValue("population", "randomVisitors")
        stage(next)
    }
    function resetField(section, key) {
        if (!editable || !hasOverride(section, key)) return
        var next = JSON.parse(JSON.stringify(overrides))
        delete next[section][key]
        if (!Object.keys(next[section]).length) delete next[section]
        stage(next)
    }
    function randomizeValley() {
        if (!canRandomize) return
        randomizer.inputSnapshot = JSON.stringify(overrides)
        randomizer.inputGeneration = stagingGeneration
        randomizer.command = ["python3", launcher, "randomize-settings", randomizer.inputSnapshot]
        actionStatus = qsTr("Randomizing a staged valley…")
        randomizer.running = true
    }
    function queueValidation() {
        settingsValid = false
        validationTimer.restart()
    }
    function resolveSettings() {
        if (resolver.running || !documentReadable) return
        var snapshot = JSON.stringify(overrides)
        if (snapshot.length > 64000) {
            documentValid = false
            validationError = qsTr("Settings payload is too large.")
            return
        }
        resolver.inputSnapshot = snapshot
        resolver.command = ["python3", launcher, "resolve-settings", snapshot]
        resolver.running = true
    }
    function beginSession(method) {
        if (shuttingDown || !settingsValid || externalChange || saving || localEventBusy || randomizing) return
        if (dirty) {
            pendingSession = method
            applySettings()
        } else request(method)
    }
    function applySettings() {
        if (shuttingDown || !settingsValid || externalChange || saving || localEventBusy || randomizing) return
        save.inputSnapshot = JSON.stringify(overrides)
        save.command = ["python3", launcher, "save-settings", save.inputSnapshot, "--expected", loadedSnapshot]
        actionStatus = qsTr("Validating and atomically saving sparse choices…")
        save.running = true
    }
    function testEvent(event) {
        if (shuttingDown || !settingsValid || dirty || externalChange || saving || localEventBusy || randomizing) return
        actionStatus = qsTr("Opening a temporary event test using saved settings…")
        command.eventTest = true
        command.command = ["python3", root.launcher, "preview", "--fullscreen", "--supervised", "--test-event", event]
        command.running = true
        dismiss()
    }
    function request(method) {
        // Local tests retain their coordinator in command until the preview ends.
        // Surface must still be able to ask it (and other owned sessions) to stop.
        if (method === "stop" && command.running) {
            command.stop()
            if (controller) controller.stopSession()
            else if (!stopRequest.running) stopRequest.running = true
            return
        }
        if (shuttingDown || command.running) return
        if (controller) {
            if (method === "preview") controller.previewScene()
            else if (method === "start") controller.startSession()
            else if (method === "stop") controller.stopSession()
            return
        }
        command.command = ["omarchy-shell", "omarchasaurus", method]
        command.running = true
    }
    function refreshSession() { if (!shuttingDown && !controller && !sessionProbe.running) sessionProbe.running = true }
    Component.onCompleted: readSettings()

    // Watch metadata only. Contents enter QML exclusively through the bounded,
    // descriptor-validated read-settings helper, never through FileView.
    FileView {
        id: settingsFile
        path: root.configPath
        watchChanges: true
        preload: false
        blockAllReads: true
        printErrors: false
        onFileChanged: root.readSettings()
    }
    FileView {
        id: settingsDirectoryWatcher
        path: root.configDir
        watchChanges: true
        preload: false
        blockAllReads: true
        printErrors: false
        onFileChanged: root.readSettings()
    }
    Timer {
        id: readTimer
        interval: 80
        onTriggered: {
            if (!root.readPending || root.shuttingDown || settingsReader.running || save.running) return
            root.readPending = false
            settingsReader.running = true
        }
    }
    BoundedProcess {
        id: settingsReader
        command: ["python3", root.launcher, "read-settings"]
        stdoutLimit: 262144
        onExited: function(code) {
            if (root.shuttingDown) return
            if (root.readPending) { readTimer.restart(); return }
            if (code === 0) root.loadSettings(stdoutText)
            else root.readFailed(failureReason || diagnostic(stderrText) || qsTr("Settings reader failed."))
        }
    }
    Timer { id: validationTimer; interval: 80; onTriggered: root.resolveSettings() }
    BoundedProcess {
        id: resolver
        property string inputSnapshot: ""
        stdoutLimit: 65536
        onExited: function(code) {
            if (root.shuttingDown || !root.documentReadable) return
            if (inputSnapshot !== JSON.stringify(root.overrides)) {
                validationTimer.restart()
                return
            }
            try {
                if (code !== 0) throw new Error(failureReason || diagnostic(stderrText) || qsTr("Settings validation failed."))
                var value = JSON.parse(stdoutText)
                root.effective = value
                root.documentValid = true
                root.settingsValid = true
                root.validationError = ""
            } catch (error) {
                root.documentValid = false
                root.settingsValid = false
                root.validationError = diagnostic(String(error))
            }
        }
    }
    BoundedProcess {
        id: randomizer
        property string inputSnapshot: ""
        property int inputGeneration: -1
        stdoutLimit: 65536
        onExited: function(code) {
            if (root.shuttingDown || root.externalChange) return
            if (inputGeneration !== root.stagingGeneration || inputSnapshot !== JSON.stringify(root.overrides)) {
                root.actionStatus = qsTr("Settings changed while randomizing; no randomized choices were staged.")
                return
            }
            try {
                if (code !== 0) throw new Error(failureReason || diagnostic(stderrText) || qsTr("Randomization failed."))
                var value = JSON.parse(stdoutText)
                if (!value || typeof value !== "object" || Array.isArray(value))
                    throw new Error(qsTr("Invalid randomization response."))
                root.stage(value)
                root.actionStatus = qsTr("Randomized scenery and animals are staged with rotating visitors. Review the choices, then Apply Settings. Nothing has been saved or rerolled live.")
            } catch (error) {
                root.actionStatus = qsTr("Valley was not randomized: ") + diagnostic(String(error))
            }
        }
    }
    BoundedProcess {
        id: save
        property string inputSnapshot: ""
        onOutput: function(text) { root.actionStatus = text }
        onExited: function(code) {
            var nextSession = root.pendingSession
            root.pendingSession = ""
            if (code === 0) {
                root.loadedSnapshot = inputSnapshot
                root.dirty = false
                root.externalChange = false
            } else root.actionStatus = qsTr("Settings were not applied (exit %1): ").arg(code) + (failureReason || diagnostic(stderrText || stdoutText))
            inputSnapshot = ""
            root.readSettings()
            if (code === 0 && nextSession && !root.shuttingDown) root.request(nextSession)
        }
    }
    BoundedProcess {
        id: command
        property bool eventTest: false
        timeoutMs: eventTest ? 0 : 12000
        killGraceMs: eventTest ? 30000 : 5000
        onOutput: function(text) { root.commandStatus = text }
        onExited: function(code) {
            var wasEventTest = eventTest
            eventTest = false
            var detail = failureReason || diagnostic(stderrText || stdoutText)
            root.commandStatus = ""
            if (code !== 0) {
                if (wasEventTest && !root.shuttingDown) {
                    root.opened = true
                    if (root.shell && typeof root.shell.summon === "function")
                        root.shell.summon(root.pluginId, "{}")
                }
                root.actionStatus = qsTr("Session request failed (exit %1): ").arg(code) + detail
            } else if (wasEventTest) {
                root.actionStatus = qsTr("Event test ended; saved settings are unchanged.")
            }
        }
    }
    BoundedProcess {
        id: stopRequest
        command: ["python3", root.launcher, "stop"]
        // Two session modes can each wait for readiness and cleanup replies.
        timeoutMs: 90000
        onOutput: function(text) { root.commandStatus = text }
        onExited: function(code) {
            root.commandStatus = ""
            if (code !== 0) root.actionStatus = qsTr("Stop failed (exit %1): ").arg(code) + (failureReason || diagnostic(stderrText || stdoutText))
        }
    }
    BoundedProcess {
        id: sessionProbe
        command: ["python3", root.launcher, "status"]
        onOutput: function(text) { root.probeStatus = text }
        onExited: function(code) {
            if (code !== 0) root.probeStatus = failureReason || diagnostic(stderrText) || qsTr("Session status unavailable.")
        }
    }
    Timer { interval: 2000; running: root.opened && !root.controller; repeat: true; onTriggered: root.refreshSession() }
    Component.onDestruction: root.shutdown()
}
