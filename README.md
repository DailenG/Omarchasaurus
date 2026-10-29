# Omarchasaurus

An interactive truecolor ASCII dinosaur valley for **Omarchy Quattro**, inspired by Omarcharium's terminal style. Dinosaurs, mountains, tall trees, a lake, clouds and flying Pteranodon are drawn with ordinary characters inside a real terminal—no image protocol or separate GPU scene.

![Omarchasaurus character-grid snapshot](preview.png)

**Development preview:** manual immersion and screensaver-style Start are available. Automatic idle activation and sound are **off and not implemented**. Marketplace submission/approval is separate from this repository; no marketplace verification is claimed.

## Requirements

- Omarchy Quattro with its Quickshell-based shell and Hyprland.
- Python 3.11 or newer; runtime Python uses only the standard library.
- Ghostty or Kitty. The launcher prefers Ghostty and opens separately owned terminal instances.
- A UTF-8, truecolor terminal and a monospace font. SGR mouse reporting enables interaction.

There is no runtime package installer, source download, build step, account, API key or elevated helper. No sudo or pkexec is required. Dependencies must already be present; the plugin does not install or update them.

## Install

```sh
omarchy plugin add https://github.com/DailenG/Omarchasaurus --enable
```

The plugin ID is **`dailen.omarchasaurus`**. Open its tray menu or run:

```sh
omarchy-shell omarchasaurus configure
```

Choose **Enter Immersion** for an interactive preview on the focused output. **Start All Outputs** opens one owned screensaver-style terminal per active output. **Surface** stops owned sessions only; it does not kill unrelated terminals or other screensavers.

## Updating — 0.2.0

Apply or discard staged choices and Surface owned previews before updating. Quit any separately launched standalone control room, then use the normal updater:

```sh
omarchy plugin update dailen.omarchasaurus
```

From 0.2.0 onward, updates replace the tray service and settings components without restarting the whole desktop shell. Each QML release uses distinct paths for its complete UI payload, avoiding Quickshell's compiled-component cache. The plugin does not fetch updates itself.

**One-time migration from 0.1.0:** that version retained its service across rescans. After updating, disable only Omarchasaurus, wait for its tray icon to disappear, then enable it again:

```sh
omarchy plugin disable dailen.omarchasaurus
omarchy plugin enable dailen.omarchasaurus
omarchy-shell omarchasaurus runtimeVersion
```

The final command reports `0.2.0`. This does not require restarting unrelated plugins or the desktop shell. An already-up-to-date checkout does not trigger an updater rescan, so it still needs that one-time migration.

Closing/reopening the control room preserves staged choices and in-flight Apply/Randomize work while its service stays loaded. A release reload discards unsaved staged choices and may atomically cancel finite helpers. Standalone instances keep their loaded release until quit.

### 0.2.0 scenery changes

The complete Brachiosaurus/tree group moves eight world units right; its anatomy, browsing relationship and hatchling destination move together. Nearby plants leave the nest's eggs and rim clear, and the nest sits slightly higher to avoid bottom-row clipping. Narrow framing fits the stationary nest and browsing group together without relocating them as the terminal changes size. Passing animals can still temporarily cross in front of the nest.

## Settings

Choices remain staged until **Apply Settings**, or until **Enter Immersion / Start All Outputs** saves pending valid choices before launching. **Reload / Discard** drops staged changes. Each **Reset** removes only that field's explicit choice and restores its default; other choices remain intact.

- **Morning / Dusk:** colour palette only. Changing colours does not change speed, parallax, scenery, species, residency or event schedules.
- **Reduced motion:** an independent accessibility choice. Animation profiles are quieter; an active event keeps its birth profile rather than snapping when this changes.
- **Animals:** Tyrannosaurus rex, Triceratops, Stegosaurus, Ankylosaurus, Parasaurolophus families, Plesiosaurus, Diplodocus and Pteranodon can be selected. The focal Brachiosaurus always stays. Plesiosaurus is a marine reptile; Pteranodon is a pterosaur.
- **Diplodocus stays by the lake:** independent of its species switch and the palette. On makes it resident; Off gives scheduled visits every 10–20 active minutes.
- **Animal ceiling:** an upper bound, not a cloning target. Every family member, calf, young Brachiosaurus, flyer and active lake jumper counts. Full budgets skip arrivals rather than evict visible animals. A ceiling of one leaves the adult Brachiosaurus.
- **Scenery:** seven density controls, from 0% to 200%, plus the Brachiosaurus nest. The focal tree and major terrain remain. Ambient-cloud density is separate from the passing weather cloud.

### Randomize Valley

**Randomize Valley** stages varied scenery, optional animals and lake residency, and enables rotating visitors. It preserves the colour palette, motion/accessibility preferences, scene seed, animal ceiling and family ceiling. Review the generated choices, then Apply.

It never saves automatically or silently rerolls an existing scene. Rotating visitors leave fully before a replacement enters; recurring events provide additional activity without periodically relocating the scenery or visible animals. At tight ceilings, the preserved budget still takes priority.

### Interaction and events

In immersion, click a dinosaur for an articulated head/jaw/tail reaction, open sky for a meteor, or lake water for a small animal leap and splash. One meteor and one lake leap can coexist; the leap needs a free animal slot. Additional clicks do not queue.

Rare events use **unpaused session time**, not wall-clock time between sessions:

- Soft volcano puffs: 3–7 minutes.
- Pteranodon flocks: 4–9 minutes, subject to free seats.
- Brachiosaurus hatching: 8–15 minutes, with a nest and one free seat.
- Gentle shower followed by a rainbow: 10–15 minutes; no animal seat required.

The terminal canvas scales dinosaur silhouettes with available space and is bounded to 500×200 cells. Default animation is 15 FPS. Occupied seats and viewport-safe entry/exit guards prevent ordinary arrivals from replacing dinosaurs in the middle of the scene.

## Try an event without waiting

In the control room, choose **Test unique event**, then **Test Event**. Apply or discard staged changes first, and Surface any existing preview.

From a checkout:

```sh
python3 scripts/launch-dinosaurs preview --test-event rainbow
```

Other event keys: `shower`, `hatching`, `flock`, `diplodocus`, `volcano`. Add `--fullscreen` for immersion.

Tests temporarily select the necessary animals, nest and seats without changing saved preferences. They preserve palette and motion; the Diplodocus test temporarily selects visitor behavior. Rainbow starts visibly; animals still enter naturally at the configured speed and may take longer with slow/reduced motion. Quit and relaunch to replay a test.

For an animation in the current terminal rather than a new window:

```sh
python3 scripts/dinosaurs.py --preview --test-event hatching
```

**Q / Esc:** quit. **Space:** pause. **P:** switch palette. **N:** choose another seeded layout. **R:** clear temporary P/N choices and reload saved settings. These keys do not save preferences; N resets seeded schedules rather than replaying a selected test. In screensaver-style Start, ordinary input dismisses owned outputs instead of interacting.

## Files, privacy and security boundaries

Runtime makes **no HTTP/TCP requests** and sends no data to remote services. Installation/update through Omarchy contacts GitHub to obtain the repository; that is separate from plugin runtime. Local integrations are Hyprland, Omarchy/Quickshell IPC and same-user Unix-domain control sockets.

Files used by the plugin:

- `$XDG_CONFIG_HOME/omarchasaurus/settings.json` (normally `~/.config/omarchasaurus/settings.json`): sparse user choices, written by Apply, pending-choice saves before a session launch, or the explicit save helper.
- The sibling `settings.lock`: cooperative writer lock, retained between runs.
- `$XDG_RUNTIME_DIR/omarchasaurus-terminal/`: owner-only coordinator locks, mode-0600 control sockets and private per-session directories. Session files include `authority.json` and, on dismissal, `dismissed.json`; their random nonce never travels in process arguments. Active session data and sockets are cleaned up after owned terminals stop. Empty runtime directories/lock files can remain until logout.
- Python may generate ignored `__pycache__` files in its checkout. Quickshell may retain its normal controller logs under its runtime directory; the plugin does not remove host logs.

Settings reads are byte-bounded, schema-validated and use no-follow/nonblocking descriptors. Unsafe file types, links, ownership/permissions and symlinked directory chains are rejected, not repaired. Official saves are exclusive mode-0600 temporaries followed by atomic replacement and file/directory synchronization. Directory and file operations retain validated directory descriptors.

Short discovery commands have raw stdout/stderr budgets, absolute deadlines and owned-group TERM/KILL/reap cleanup. Local control checks peer UID and bounds clients, request size and processing work. Native text diagnostics are bounded and rendered as plain text. There are no plugin-managed credentials, privileged rules, systemd units, autostart hooks, global keybindings, clipboard reads or input-device capture.

External-edit conflict detection is **best-effort**: supported saves serialize with the cooperative lock and reject a changed baseline. An unrelated editor that ignores the lock can still race final atomic replacement. Avoid externally editing the file during Apply. Invalid live settings retain the last valid scene; they are not replaced with a new saved file.

Community plugins run as unsandboxed user code. Advisor review, tests and the marketplace's narrow static baseline are **not a security audit, certification, warranty or endorsement**.

## Removing

Surface owned sessions first. If you launched directly from a terminal, stop them before removing the source:

```sh
python3 ~/.config/omarchy/plugins/dailen.omarchasaurus/scripts/launch-dinosaurs stop
omarchy plugin remove dailen.omarchasaurus
```

Shell unload signals supervised session coordinators; they stop and reap owned terminals even when Quickshell immediately kills its direct helper process. Standalone Quit waits for local event tests, saves and helper processes before exiting.

Removal intentionally **keeps** `settings.json` and `settings.lock` under the configuration directory so reinstalling preserves choices. Stopped runtime lock files can remain until logout, and normal Quickshell logs follow the host's retention. No account credentials, keyring entries, installed packages, units, hooks, firewall rules or shared Hyprland configuration need removal because this plugin creates none. Omarchy manages the plugin registration itself. Remove retained settings manually only if you want to discard them; do not delete a shared configuration directory.

## Development checks

```sh
python3 -m unittest discover -s tests -q
```

The suite covers animation/admission transitions, palette independence, bounded randomization, adversarial file/process/socket boundaries and private terminal cleanup. Ruff, mypy-checked scene/security boundaries and `omarchy-plugin-validate` are additional development checks. Private desktop transports and unmapped native rendering do not establish physical multi-output/hot-plug, fullscreen aesthetic or long-running resource/soak acceptance.

Every QML code release must increment `manifest.version`, move the **entire** QML payload to `qml/<version>/`, update its entrypoints and `Service.runtimeVersion`, and remove the previous payload. Do not reuse unchanged QML URLs or retain old root wrappers: the host disables Quickshell's own reload and may retain compiled transitive components. Standalone configure resolves and validates the release through the manifest.

The public repository excludes historical desktop captures, development-agent instruction trees and private review corpora. The preview above is an actual production character-grid snapshot rendered to PNG without a desktop capture; no font files are bundled.

## License

[MIT](LICENSE). Scene strokes and the tray artwork are project assets. Omarcharium inspired the execution style; no Omarcharium artwork is bundled.
