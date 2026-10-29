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
        if (!sessions.control.settingsValid || sessions.control.externalChange || sessions.control.saving || sessions.control.randomizing) {
            summon("", "{}")
            return
        }
        sessions.control.beginSession("preview")
    }
    function requestQuit() {
        quitting = true
        room.close()
        sessions.shutdown()
        finishQuit()
    }
    function finishQuit() {
        // Keep the controller alive until saves finish and all helpers reap.
        if (quitting && !sessions.busy) Qt.quit()
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
        service: sessions
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
