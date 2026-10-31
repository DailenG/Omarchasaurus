# Name-pronunciation audio

These nine files are **newly generated English speech**, made locally for Omarchasaurus. They are not recordings of a museum narrator, the original voice contributor, or prehistoric animals. No animal calls, video extracts, browser speech services, or remote synthesis APIs were used. The website serves the finished MP3s itself; listeners do not need a speech engine, model download, or third-party request.

## Rights and sources

The generated assets are supplied under the project's [MIT license](../../../LICENSE), insofar as copyright applies. Copyright (c) 2026 Dailen Gunter. The upstream sources below impose no additional restriction on these generated speech files. Credits do not imply endorsement by the museums, dictionary, tool authors, or voice contributor.

- **Voice:** `en_US-ljspeech-high`, a single-speaker US-English Piper neural voice by **Bryce Beattie**. His [voice publication page](https://brycebeattie.com/files/tts/) explicitly labels the LJSpeech high model **public domain** and permits redistribution of his models. The voice was downloaded from the [rhasspy/piper-voices mirror](https://huggingface.co/rhasspy/piper-voices/tree/b4e358ffcb232591bf73a540e70f7de528e4174a/en/en_US/ljspeech/high), pinned to revision `b4e358ffcb232591bf73a540e70f7de528e4174a`. Its [model card](https://huggingface.co/rhasspy/piper-voices/blob/b4e358ffcb232591bf73a540e70f7de528e4174a/en/en_US/ljspeech/high/MODEL_CARD) identifies the public-domain training dataset. The mirror's repository metadata is MIT; the publisher's more specific public-domain declaration applies to this voice.
- **Dataset:** [The LJ Speech Dataset 1.1](https://keithito.com/LJ-Speech-Dataset/), credited to **Keith Ito and Linda Johnson**. Its source page states that the text, audio, and annotations are public domain in the United States, with no restrictions on use. Linda Johnson's original readings were recorded for LibriVox in 2016–2017. These assets are synthetic outputs of the trained model, not excerpts from those recordings.
- **Synthesis tool:** [Piper `piper-tts` 1.8.0](https://pypi.org/project/piper-tts/1.8.0/), [source release](https://github.com/OHF-Voice/piper1-gpl/tree/v1.8.0), commit `639388b6317fc4731e91d53da42aea68fd4166ff`, **GPL-3.0-or-later**. Piper and its dependencies were run in a private ephemeral environment, not bundled into the website. These MP3s contain speech, not Piper program code; the tool's license is separate from the generated assets. Its [GPL license](https://github.com/OHF-Voice/piper1-gpl/blob/v1.8.0/COPYING), section 2, describes how the license applies to program output.
- **Encoding tool:** FFmpeg `n9.0.2`, using `libmp3lame`. No encoder executable or library is distributed here.

Downloaded model SHA-256:

```text
en_US-ljspeech-high.onnx
5d4f08ba6a2a48c44592eed3ce56bf85e9de3dd4e20df90541ae68a8310c029a

en_US-ljspeech-high.onnx.json
7e1f4634af596d83cca997fb7a931ba80b70f8a316a2655ee69c55365e0ace14
```

The model, Python environment, recognizer models, intermediate WAVs, and generation scripts are deliberately not included in the repository.

## Pronunciation references

These are one set of clear English readings, not the only correct pronunciations. Accent, vowel quality, and scientific-name stress can vary. The short guides below are spelling aids, not formal IPA transcriptions. Capitals show emphasized syllables. In `STEG-oh-SORE-us` and `DIP-low-DOCK-us`, the earlier capitalized syllable has secondary stress; `REKS` is a separate stressed word. In Parasaurolophus, **ROL** uses the short vowel in *doll*, not the vowel in *roll*.

Seven readings follow the Natural History Museum, London, Dino Directory:

- [Brachiosaurus](https://www.nhm.ac.uk/discover/dino-directory/brachiosaurus.html): `BRAK-ee-oh-sore-us`.
- [Tyrannosaurus](https://www.nhm.ac.uk/discover/dino-directory/tyrannosaurus.html): `tie-RAN-oh-sore-us`, followed by `REKS` for *rex*.
- [Triceratops](https://www.nhm.ac.uk/discover/dino-directory/triceratops.html): museum `tri-SERRA-tops`, rendered here as `try-SERR-uh-tops`.
- [Stegosaurus](https://www.nhm.ac.uk/discover/dino-directory/stegosaurus.html): `STEG-oh-SORE-us`.
- [Ankylosaurus](https://www.nhm.ac.uk/discover/dino-directory/ankylosaurus.html): `an-KYE-low-sore-us`.
- [Parasaurolophus](https://www.nhm.ac.uk/discover/dino-directory/parasaurolophus.html): `pa-ra-saw-ROL-off-us`.
- [Diplodocus](https://www.nhm.ac.uk/discover/dino-directory/diplodocus.html): `DIP-low-DOCK-us`.

[Pteranodon](https://www.amnh.org/explore/ology/ology-cards/358-pteranodon-longiceps) follows the American Museum of Natural History OLogy guide `ter-AN-o-don`, rendered as `ter-AN-oh-don`. [Plesiosaurus](https://www.merriam-webster.com/dictionary/plesiosaurus) follows Merriam-Webster's `ˌplēsēəˈsȯrəs`, rendered as `PLEE-see-uh-SORE-us`. Pteranodon is a pterosaur and Plesiosaurus a marine reptile, not dinosaurs.

These sources were consulted for pronunciation, not copied for audio. Links and licensing statements were checked on 2026-10-31.

## Exact synthesis inputs and file measurements

The complete `[[...]]` inputs below use Piper's [documented raw-phoneme block implementation](https://github.com/OHF-Voice/piper1-gpl/blob/v1.8.0/src/piper/voice.py). They bypass automatic word lookup so unusual names keep the selected vowels and stress. The stream uses the model's eSpeak `en` phoneme inventory and its IPA-like symbols, not a promise of universal IPA or a different voice's accent. In particular, its training inventory uses `a` for the TRAP vowel, `ɒ` for the LOT vowel, and `əʊ` for GOAT. All supplied symbols were confirmed present in the model's phoneme map; the raw input was confirmed to reach synthesis unchanged.

| File | Spoken guide | Complete Piper input | Bytes | Duration (s) |
| --- | --- | --- | ---: | ---: |
| `brachiosaurus.mp3` | BRAK-ee-oh-sore-us | `[[bɹˈakiːəʊsɔːɹəs.]]` | 12,758 | 1.507075 |
| `tyrannosaurus-rex.mp3` | tie-RAN-oh-sore-us REKS | `[[taɪɹˈanəʊsɔːɹəs ɹˈɛks.]]` | 15,279 | 1.878594 |
| `triceratops.mp3` | try-SERR-uh-tops | `[[tɹaɪsˈɛɹətɒps.]]` | 11,213 | 1.530295 |
| `stegosaurus.mp3` | STEG-oh-SORE-us | `[[stˌɛɡəʊsˈɔːɹəs.]]` | 12,912 | 1.530295 |
| `ankylosaurus.mp3` | an-KYE-low-sore-us | `[[aŋkˈaɪləʊsɔːɹəs.]]` | 12,781 | 1.588345 |
| `parasaurolophus.mp3` | pa-ra-saw-ROL-off-us | `[[paɹəsɔːɹˈɒlɒfəs.]]` | 12,803 | 1.623175 |
| `diplodocus.mp3` | DIP-low-DOCK-us | `[[dˌɪpləʊdˈɒkəs.]]` | 11,113 | 1.379365 |
| `plesiosaurus.mp3` | PLEE-see-uh-SORE-us | `[[plˌiːsiəsˈɔːɹəs.]]` | 10,931 | 1.414195 |
| `pteranodon.mp3` | ter-AN-oh-don | `[[tɛɹˈanəʊdɒn.]]` | 8,269 | 1.216825 |

All files are mono MP3, 22,050 Hz, variable bitrate (`libmp3lame -q:a 4`). Total audio size: **108,059 bytes**. Durations and stream properties were measured from the encoded files with `ffprobe`, rather than estimated from the text.

Synthesis settings: `length_scale=1.12`, `noise_scale=0.5`, `noise_w_scale=0.333`, `normalize_audio=True`, `volume=0.8`, CPU inference. Each intermediate 16-bit mono WAV had 0.08 seconds of leading silence and 0.15 seconds of trailing silence added. The final FFmpeg conversion was:

```sh
ffmpeg -hide_banner -loglevel error -y -i INPUT.wav \
  -map_metadata -1 -ac 1 -ar 22050 -codec:a libmp3lame -q:a 4 OUTPUT.mp3
```

Neural synthesis includes randomness; these inputs and settings describe the actual production method but do not promise byte-identical regeneration. The published files are identified by these SHA-256 hashes:

```text
375949a98408ac75f3344678f232f0dd73d0b69a6efa9cff0e4bb1a2eccd9caf  brachiosaurus.mp3
acd3071e760664af6111d1ec16e7d423db16088ea9c709b6b87c8c2d15525625  tyrannosaurus-rex.mp3
e138248bc528ab14f5aa051d85bdd433b5fad69943ef1263747ebdd9935438c8  triceratops.mp3
02ac643667b3496b8965dfe1eee3dda4fb15449fd651634f5c9a14a8d4eca7fc  stegosaurus.mp3
fcf84abfb60d5c353c3f97eb4dd57aafd88e14c962d825fe4446b576baf701fd  ankylosaurus.mp3
4d9c77166fe8318356c2a3107824165a233dbdb137d5198338f59d09f7709699  parasaurolophus.mp3
4c7f6b7fd070da7e43ffa5676b7c88495fc0b0f610f3fa2ae645c9d4b28838f2  diplodocus.mp3
528516ba98d6bd086f7fdcfdf87c8d72e4000536806cb02d6a4571188d48fde2  plesiosaurus.mp3
438944cd990a823b2581c899d50893843bd68063e79a34af3eef3f9fb71846ae  pteranodon.mp3
```

## Quality evidence and limits

All nine encoded files were decoded successfully back to PCM with FFmpeg, contained non-silent signals, and had zero clipped 16-bit samples. Their decoded peak levels ranged from -1.96 to -1.51 dBFS and RMS levels from -21.00 to -16.61 dBFS. No host-speaker playback was performed.

An offline Whisper recognition spot-check recovered several names exactly, including Brachiosaurus, Tyrannosaurus rex, Triceratops, Diplodocus, Parasaurolophus, and Plesiosaurus. Recognition of some short isolated names was approximate. That is an intelligibility aid, **not a human listening review or proof of phonetic accuracy**. Vowels and stress were selected from the references and supplied explicitly; subjective naturalness and every audible syllable were not independently confirmed by a human listener during asset generation. Browser playback/decoding is checked separately by the site integration owner.
