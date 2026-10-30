"use strict";

// Everything essential remains available without JavaScript.
const paletteControls = document.getElementById("palette-controls");
const valleyImage = document.getElementById("valley-image");
const paletteCaption = document.getElementById("palette-caption");
const palettes = {
  morning: {
    name: "Morning",
    source: "./assets/valley-morning.webp",
    alt: "Morning palette production capture of the ASCII dinosaur valley, with character-drawn dinosaurs, mountains, trees, clouds and a lake."
  },
  dusk: {
    name: "Dusk",
    source: "./assets/valley-dusk.webp",
    alt: "Dusk palette production capture of the ASCII dinosaur valley, with character-drawn dinosaurs, mountains, trees, clouds and a lake."
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
      paletteCaption.textContent = `${palette.name} palette / static artwork`;
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
      paletteCaption.textContent = `${palette.name} palette / static artwork`;
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
