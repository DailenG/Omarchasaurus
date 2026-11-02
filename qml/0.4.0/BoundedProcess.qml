import QtQuick
import Quickshell.Io

// Only raw chunks cross into JS. Bound each stream for the entire invocation,
// before concatenation; three bytes per UTF-16 code unit is a conservative
// UTF-8 ceiling (including surrogate pairs and replacement characters).
Item {
    id: root
    property alias command: child.command
    property alias running: child.running
    property int timeoutMs: 12000
    property int killGraceMs: 5000
    property int stdoutLimit: 16384
    property int stderrLimit: 8192
    property string stdoutText: ""
    property string stderrText: ""
    property string failureReason: ""
    property int stdoutBytes: 0
    property int stderrBytes: 0
    signal output(string text)
    signal exited(int code)

    function diagnostic(text) {
        return String(text).slice(-2048)
            .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
            .replace(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/g, "").trim()
    }
    function stop() {
        if (!child.running || killTimer.running) return
        deadline.stop()
        child.signal(15)
        killTimer.start()
    }
    function fail(message) {
        if (!failureReason) failureReason = message
        output(failureReason)
        stop()
    }
    function consume(chunk, errorStream) {
        if (failureReason) return
        var text = String(chunk)
        var used = errorStream ? stderrBytes : stdoutBytes
        var limit = errorStream ? stderrLimit : stdoutLimit
        if (text.length > Math.floor((limit - used) / 3)) {
            fail(qsTr("Helper output exceeded its safety limit."))
            return
        }
        if (errorStream) {
            stderrBytes += text.length * 3
            stderrText += text
        } else {
            stdoutBytes += text.length * 3
            stdoutText += text
        }
        output(diagnostic(stderrText || stdoutText))
    }
    Process {
        id: child
        stdout: SplitParser { splitMarker: ""; onRead: function(chunk) { root.consume(chunk, false) } }
        stderr: SplitParser { splitMarker: ""; onRead: function(chunk) { root.consume(chunk, true) } }
        onRunningChanged: {
            if (running) {
                root.stdoutText = ""
                root.stderrText = ""
                root.failureReason = ""
                root.stdoutBytes = 0
                root.stderrBytes = 0
                killTimer.stop()
                if (root.timeoutMs > 0) deadline.restart()
            }
        }
        onExited: function(code) {
            deadline.stop()
            killTimer.stop()
            root.exited(root.failureReason ? -1 : code)
        }
    }
    Timer {
        id: deadline
        interval: Math.max(1, root.timeoutMs)
        onTriggered: root.fail(qsTr("Helper timed out."))
    }
    Timer {
        id: killTimer
        interval: root.killGraceMs
        onTriggered: if (child.running) child.signal(9)
    }
    Component.onDestruction: {
        // Session guardians forward TERM and protect coordinator cleanup from
        // Process's immediate destructor KILL. Normal Quit waits for onExited.
        if (child.running) child.signal(15)
    }
}
