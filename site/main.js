"use strict";

// Everything essential remains available without JavaScript.
const paletteControls = document.getElementById("palette-controls");
const valleyImage = document.getElementById("valley-image");
const paletteCaption = document.getElementById("palette-caption");
const palettes = {
  morning: {
    name: "Morning",
    source: "./assets/valley-morning.webp?v=native-terminal-10pt",
    alt: "Morning native terminal screenshot of the ASCII valley, with Brachiosaurus, Tyrannosaurus rex, Stegosaurus and a Parasaurolophus family among mountains, trees and a lake."
  },
  dusk: {
    name: "Dusk",
    source: "./assets/valley-dusk.webp?v=native-terminal-10pt",
    alt: "Dusk native terminal screenshot of the ASCII valley, with Brachiosaurus, Tyrannosaurus rex, Stegosaurus and a Parasaurolophus family among mountains, trees and a lake."
  }
};

if (paletteControls && valleyImage && paletteCaption) {
  let activePalette = "morning";
  let request = 0;
  paletteControls.hidden = false;

  paletteControls.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-palette]");
    if (!button || !paletteControls.contains(button)) return;
    const key = button.dataset.palette;
    const palette = palettes[key];
    if (!palette) return;
    const currentRequest = ++request;

    if (key === activePalette) {
      valleyImage.parentElement.removeAttribute("aria-busy");
      paletteCaption.textContent = `${palette.name} palette / paused default scene`;
      return;
    }

    paletteCaption.textContent = `Loading ${palette.name} palette…`;
    valleyImage.parentElement.setAttribute("aria-busy", "true");
    const nextImage = new Image();
    nextImage.onload = () => {
      if (currentRequest !== request) return;
      valleyImage.src = palette.source;
      valleyImage.alt = palette.alt;
      activePalette = key;
      for (const control of paletteControls.querySelectorAll("button[data-palette]")) {
        control.setAttribute("aria-pressed", String(control.dataset.palette === key));
      }
      valleyImage.parentElement.removeAttribute("aria-busy");
      paletteCaption.textContent = `${palette.name} palette / paused default scene`;
    };
    nextImage.onerror = () => {
      if (currentRequest !== request) return;
      valleyImage.parentElement.removeAttribute("aria-busy");
      paletteCaption.textContent = `Could not load ${palette.name}. ${palettes[activePalette].name} is still shown; try again.`;
    };
    nextImage.src = palette.source;
  });
}

const copyButton = document.getElementById("copy-install");
const installCommand = document.getElementById("install-command");
const copyStatus = document.getElementById("copy-status");

if (copyButton && installCommand && copyStatus) {
  copyButton.hidden = false;
  copyStatus.textContent = "Copy the command, then run it in your terminal.";

  copyButton.addEventListener("click", async () => {
    copyButton.disabled = true;
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) {
        throw new Error("Clipboard is unavailable");
      }
      await navigator.clipboard.writeText(installCommand.textContent.trim());
      copyStatus.textContent = "Command copied. Paste it into your terminal to install.";
    } catch {
      const selection = window.getSelection();
      if (selection) {
        const range = document.createRange();
        range.selectNodeContents(installCommand);
        selection.removeAllRanges();
        selection.addRange(range);
      }
      copyStatus.textContent = "Clipboard unavailable. Select and copy the command manually.";
    } finally {
      copyButton.disabled = false;
    }
  });
}

const pronunciationControls = [];
let activePronunciation = null;

function labelPronunciation(control, playing) {
  const action = playing ? "Pause" : "Play";
  control.button.textContent = action;
  control.button.setAttribute("aria-label", `${action} ${control.player.getAttribute("aria-label")}`);
}

function pausePronunciation(control) {
  control.request += 1;
  control.player.pause();
  if (activePronunciation === control) activePronunciation = null;
  labelPronunciation(control, false);
}

function pronunciationError(control) {
  pausePronunciation(control);
  control.status.textContent = "Audio unavailable. Press Play to try again.";
}

for (const player of document.querySelectorAll("audio.pronunciation-player")) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "pronunciation-button";
  button.setAttribute("aria-describedby", "pronunciation-help");
  const status = document.createElement("p");
  status.className = "pronunciation-status";
  status.setAttribute("role", "status");
  const control = { player, button, status, request: 0 };
  pronunciationControls.push(control);
  labelPronunciation(control, false);

  button.addEventListener("click", async () => {
    status.textContent = "";
    if (activePronunciation === control) {
      pausePronunciation(control);
      return;
    }
    for (const other of pronunciationControls) pausePronunciation(other);
    if (player.error) player.load();
    activePronunciation = control;
    const request = ++control.request;
    labelPronunciation(control, true);
    try {
      await player.play();
    } catch {
      // Switching, pausing or leaving the page invalidates the pending play.
      if (request !== control.request || activePronunciation !== control) return;
      pronunciationError(control);
    }
  });
  player.addEventListener("play", () => {
    if (activePronunciation !== control) player.pause();
  });
  player.addEventListener("pause", () => {
    if (player.paused && activePronunciation === control) pausePronunciation(control);
  });
  player.addEventListener("ended", () => {
    if (player.ended) pausePronunciation(control);
  });
  player.addEventListener("error", () => {
    if (player.error && activePronunciation === control) pronunciationError(control);
  });

  player.before(button, status);
  player.controls = false;
  player.hidden = true;
}

window.addEventListener("pagehide", () => {
  for (const control of pronunciationControls) pausePronunciation(control);
});
