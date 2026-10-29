import QtQuick
import Qt.labs.platform 1.1 as Platform
import Quickshell
import Quickshell.Io

Item {
    id: root
    property var shell: null
    property var manifest: null
    property string statusLine: qsTr("Manual terminal sessions · idle OFF")
    property bool standalone: false
    property bool shuttingDown: false
    readonly property bool busy: coordinator.running || preview.running || stopper.running
    signal quitRequested()
    readonly property string pluginId: "dailen.omarchasaurus"
    readonly property string pluginDir: decodeURIComponent(String(Qt.resolvedUrl(".")).replace(/^file:\/\//, "").replace(/\/$/, ""))
    readonly property string launcher: pluginDir + "/scripts/launch-dinosaurs"

    function configure() {
        if (shuttingDown) return
        if (shell && typeof shell.summon === "function") shell.summon(pluginId, "{}")
        else Quickshell.execDetached(["omarchy-shell", "shell", "summon", pluginId, "{}"])
    }
    function hideControlRoom() {
        if (shell && typeof shell.hide === "function") shell.hide(pluginId)
        else Quickshell.execDetached(["omarchy-shell", "shell", "hide", pluginId])
    }
    function startSession() {
        if (shuttingDown || stopper.running) return
        if (coordinator.running) { hideControlRoom(); return }
        statusLine = qsTr("Opening one truecolor terminal per output…")
        coordinator.running = true
        hideControlRoom()
    }
    function stopSession() {
        if (stopper.running) return
        statusLine = qsTr("Stopping owned terminals…")
        stopper.running = true
    }
    function enterImmersion() {
        if (shuttingDown) return
        if (shell && typeof shell.enterImmersion === "function") shell.enterImmersion()
        else previewScene()
    }
    function previewScene() {
        if (shuttingDown || stopper.running) return
        if (preview.running) { hideControlRoom(); return }
        statusLine = qsTr("Opening terminal preview…")
        preview.running = true
        hideControlRoom()
    }
    function shutdown() {
        shuttingDown = true
        coordinator.stop()
        preview.stop()
    }

    BoundedProcess {
        id: coordinator
        command: ["python3", root.launcher, "start"]
        timeoutMs: 0
        killGraceMs: 30000
        onOutput: function(text) { root.statusLine = text }
        onExited: function(code) {
            if (code === 0) root.statusLine = qsTr("Session ended · idle remains OFF")
            else {
                root.statusLine = qsTr("Terminal session failed (exit %1): ").arg(code) + (failureReason || diagnostic(stderrText || stdoutText))
                if (!root.shuttingDown) root.configure()
            }
        }
    }
    BoundedProcess {
        id: preview
        command: ["python3", root.launcher, "preview", "--fullscreen"]
        timeoutMs: 0
        killGraceMs: 30000
        onOutput: function(text) { root.statusLine = text }
        onExited: function(code) {
            if (code === 0) root.statusLine = qsTr("Terminal preview closed")
            else {
                root.statusLine = qsTr("Terminal immersion failed (exit %1): ").arg(code) + (failureReason || diagnostic(stderrText || stdoutText))
                if (!root.shuttingDown) root.configure()
            }
        }
    }
    BoundedProcess {
        id: stopper
        command: ["python3", root.launcher, "stop"]
        // Two session modes can each wait for readiness and cleanup replies.
        timeoutMs: 90000
        onOutput: function(text) { root.statusLine = text }
        onExited: function(code) {
            if (code !== 0) root.statusLine = qsTr("Stop failed (exit %1): ").arg(code) + (failureReason || diagnostic(stderrText || stdoutText))
        }
    }

    Platform.SystemTrayIcon {
        visible: true
        icon.source: Qt.resolvedUrl("assets/tray.svg")
        // Static tooltip avoids treating process output as tray-host markup.
        tooltip: qsTr("Omarchasaurus · click for settings · middle-click to enter immersion")
        menu: Platform.Menu {
            Platform.MenuItem { text: qsTr("Control Room"); onTriggered: root.configure() }
            Platform.MenuItem { text: qsTr("Start on All Outputs"); enabled: !coordinator.running && !stopper.running; onTriggered: root.startSession() }
            Platform.MenuItem { text: qsTr("Stop Owned Sessions"); enabled: !stopper.running; onTriggered: root.stopSession() }
            Platform.MenuItem { text: qsTr("Enter Immersion"); enabled: !stopper.running && !root.shuttingDown; onTriggered: root.enterImmersion() }
            Platform.MenuSeparator { visible: root.standalone }
            Platform.MenuItem { text: qsTr("Quit Omarchasaurus"); visible: root.standalone; onTriggered: root.quitRequested() }
        }
        onActivated: function(reason) {
            if (reason === Platform.SystemTrayIcon.MiddleClick) root.enterImmersion()
            else if (reason === Platform.SystemTrayIcon.Trigger || reason === Platform.SystemTrayIcon.DoubleClick) root.configure()
        }
    }
    IpcHandler {
        target: "omarchasaurus"
        function start(): string { root.startSession(); return root.statusLine }
        function stop(): string { root.stopSession(); return root.statusLine }
        function preview(): string { root.previewScene(); return root.statusLine }
        function configure(): void { root.configure() }
        function status(): string { return root.statusLine }
        function pluginDirectory(): string { return root.pluginDir }
    }
    Component.onDestruction: root.shutdown()
}
