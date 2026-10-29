import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    id: root
    property bool quitting: false

    function summon(pluginId, payload) {
        if (!quitting) room.open(payload)
    }
    function hide(pluginId) { room.close() }
    function enterImmersion() {
        if (!room.settingsValid || room.externalChange || room.saving || room.randomizing) {
            summon("", "{}")
            return
        }
        room.beginSession("preview")
    }
    function requestQuit() {
        quitting = true
        room.pendingSession = ""
        room.shutdown()
        room.close()
        sessions.shutdown()
        finishQuit()
    }
    function finishQuit() {
        // Keep the controller alive until saves finish and all helpers reap.
        if (quitting && !room.saving && !room.localEventBusy && !room.finiteHelperBusy && !sessions.busy) Qt.quit()
    }

    Service {
        id: sessions
        shell: root
        standalone: true
        onBusyChanged: root.finishQuit()
        onQuitRequested: root.requestQuit()
    }
    Config {
        id: room
        shell: root
        controller: sessions
        onSavingChanged: root.finishQuit()
        onLocalEventBusyChanged: root.finishQuit()
        onFiniteHelperBusyChanged: root.finishQuit()
    }
    IpcHandler {
        target: "omarchasaurus-control"
        function open(): void { root.summon("", "{}") }
        function quit(): void { root.requestQuit() }
    }
    Component.onCompleted: {
        // Give this resident app its own tray pin/hide identity, not "quickshell".
        Qt.application.name = "Omarchasaurus"
        room.open("{}")
    }
}
