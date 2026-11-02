import QtQuick
import Quickshell.Wayland

Item {
    id: root
    property string helper: ""
    property bool desiredEnabled: false
    property bool panelOpened: false
    property bool shuttingDown: false
    property bool leaseOwned: false
    property bool statusOwned: false
    property bool statusEligible: false
    property int screensaverTimeout: 150
    property bool keepAwake: false
    property bool sessionLocked: true
    property bool statusFresh: false
    property string statusReason: qsTr("Checking Omarchy idle integration…")
    property string leaseError: ""
    property int statusGeneration: 0
    property bool statusReprobePending: false
    property bool pendingRestart: false
    property int consecutiveFailures: 0

    readonly property bool leaseRunning: leaseProcess.running
    readonly property bool armed: !shuttingDown && desiredEnabled && leaseProcess.running
        && leaseOwned && statusFresh && statusOwned && statusEligible && screensaverTimeout >= 1
    readonly property bool canRetry: !shuttingDown && !!helper
        && (!statusProbe.running) && (!desiredEnabled || !armed || !!leaseError)
    readonly property bool busy: leaseProcess.running || statusProbe.running
    readonly property string summary: armed
        ? qsTr("Automatic idle activation ready · %1s Omarchy timeout · lock timing preserved").arg(screensaverTimeout)
        : (desiredEnabled && leaseError ? qsTr("Automatic idle blocked: ") + leaseError : statusReason)

    signal activate()

    function startLease() {
        if (shuttingDown || !desiredEnabled || !helper) return
        if (leaseProcess.running) {
            pendingRestart = true
            return
        }
        pendingRestart = false
        leaseOwned = false
        leaseError = ""
        leaseProcess.command = ["python3", helper, "lease"]
        leaseProcess.running = true
    }

    function stopLease() {
        pendingRestart = false
        leaseOwned = false
        if (leaseProcess.running) leaseProcess.stop()
    }

    function syncLease() {
        consecutiveFailures = 0
        if (shuttingDown || !desiredEnabled) {
            leaseError = ""
            stopLease()
            if (!shuttingDown) refreshStatus()
        } else if (!leaseProcess.running) {
            startLease()
        } else {
            refreshStatus()
        }
    }

    function retry() {
        if (shuttingDown || !helper) return
        consecutiveFailures = 0
        leaseError = ""
        if (desiredEnabled) {
            if (leaseProcess.running) {
                pendingRestart = true
                leaseProcess.stop()
            } else {
                startLease()
            }
        } else {
            refreshStatus()
        }
    }

    function refreshStatus() {
        if (shuttingDown || !helper) return
        statusGeneration += 1
        if (statusProbe.running) {
            statusReprobePending = true
            return
        }
        statusProbe.requestGeneration = statusGeneration
        statusProbe.command = ["python3", helper, "status"]
        statusProbe.running = true
    }

    function shutdown() {
        shuttingDown = true
        statusReprobePending = false
        pendingRestart = false
        leaseOwned = false
        statusFresh = false
        pollTimer.stop()
        freshnessTimer.stop()
        stopLease()
        statusProbe.stop()
    }

    onDesiredEnabledChanged: syncLease()
    onHelperChanged: if (helper && !shuttingDown) syncLease()
    onPanelOpenedChanged: if (panelOpened && !shuttingDown) refreshStatus()
    Component.onCompleted: if (helper && !shuttingDown) refreshStatus()
    Component.onDestruction: shutdown()

    IdleMonitor {
        id: idleMonitor
        enabled: root.armed
        timeout: Math.max(1, root.screensaverTimeout)
        respectInhibitors: true
        onIsIdleChanged: {
            if (isIdle && root.armed) root.activate()
        }
    }

    Timer {
        id: pollTimer
        interval: root.panelOpened ? 2000 : 5000
        repeat: true
        running: !root.shuttingDown && !!root.helper
            && (root.panelOpened || (root.desiredEnabled && leaseProcess.running
                && root.leaseOwned && root.consecutiveFailures < 3))
        onTriggered: root.refreshStatus()
    }

    Timer {
        id: freshnessTimer
        interval: 15000
        onTriggered: root.statusFresh = false
    }

    BoundedProcess {
        id: leaseProcess
        timeoutMs: 0
        killGraceMs: 30000
        stdoutLimit: 4096
        stderrLimit: 4096
        onOutput: function() {
            var firstLine = String(stdoutText).split("\n")[0].trim()
            if (!failureReason && firstLine === "owned" && !root.leaseOwned) {
                root.leaseOwned = true
                root.leaseError = ""
                root.refreshStatus()
            }
        }
        onExited: function(code) {
            var restart = root.pendingRestart && root.desiredEnabled && !root.shuttingDown
            var unexpected = !restart && root.desiredEnabled && !root.shuttingDown
            root.pendingRestart = false
            root.leaseOwned = false
            if (unexpected) {
                root.leaseError = failureReason || diagnostic(stderrText)
                    || qsTr("Idle lease exited (code %1).").arg(code)
            }
            root.refreshStatus()
            if (restart) root.startLease()
        }
    }

    BoundedProcess {
        id: statusProbe
        property int requestGeneration: 0
        timeoutMs: 4000
        stdoutLimit: 8192
        stderrLimit: 4096
        onExited: function(code) {
            if (root.shuttingDown) return
            var latest = requestGeneration === root.statusGeneration
            try {
                if (code !== 0 || failureReason)
                    throw new Error(failureReason || diagnostic(stderrText || stdoutText) || qsTr("Idle status check failed."))
                var parsed = JSON.parse(stdoutText)
                if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)
                        || parsed.version !== 1
                        || typeof parsed.owned !== "boolean"
                        || typeof parsed.eligible !== "boolean"
                        || typeof parsed.timeout !== "number" || !isFinite(parsed.timeout)
                        || parsed.timeout < 0 || Math.floor(parsed.timeout) !== parsed.timeout
                        || typeof parsed.keepAwake !== "boolean"
                        || typeof parsed.locked !== "boolean"
                        || typeof parsed.reason !== "string") {
                    throw new Error(qsTr("Invalid idle status response."))
                }
                if (latest) {
                    root.consecutiveFailures = 0
                    root.statusOwned = parsed.owned
                    root.statusEligible = parsed.eligible
                    if (parsed.timeout >= 1) root.screensaverTimeout = parsed.timeout
                    root.keepAwake = parsed.keepAwake
                    root.sessionLocked = parsed.locked
                    root.statusReason = diagnostic(parsed.reason).slice(0, 240)
                    root.statusFresh = true
                    freshnessTimer.restart()
                }
            } catch (error) {
                if (latest) {
                    root.consecutiveFailures += 1
                    root.statusOwned = false
                    root.statusEligible = false
                    root.statusFresh = false
                    freshnessTimer.stop()
                    root.statusReason = diagnostic(String(error)).slice(0, 240)
                }
            }
            if (root.statusReprobePending && !root.shuttingDown) {
                root.statusReprobePending = false
                root.refreshStatus()
            }
        }
    }
}
