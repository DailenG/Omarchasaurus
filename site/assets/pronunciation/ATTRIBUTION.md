# Name-pronunciation audio

These nine MP3s are synthetic English name readings created for Omarchasaurus with **ElevenLabs on 2026-11-01**. They are not recordings of museum narrators, performances recorded specifically for this project by the voice contributor, or prehistoric animal calls. The website hosts the finished files itself: listeners need no ElevenLabs account, API key, speech engine or voice-model download. The terminal plugin remains silent.

## Rights and sources

The project's copyright interest in these finished assets, insofar as copyright applies, is offered under the project's [MIT license](../../../LICENSE). Copyright (c) 2026 Dailen Gunter. These credits do not imply endorsement by ElevenLabs, the voice contributor, the museums or the dictionary.

- **Generation entitlement:** created while using a paid ElevenLabs account; the project owner confirmed paid-plan publishing eligibility before synthesis. ElevenLabs' [publishing guidance](https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform) states that paid-plan, non-Beta outputs have commercial-use rights that continue after the subscription. Free-plan output is not an interchangeable licensing substitute.
- **Output rights:** section 4(c) of the [ElevenLabs Terms of Service](https://elevenlabs.io/terms-of-use) distinguishes generated output from the provider's models and states that the user retains rights to their output as between the user and ElevenLabs. The provider's terms and policies govern its service and generated output; this repository does not license or distribute its voice models, service, trademarks or a real speaker's identity.
- **Voice:** ElevenLabs' premade **Bella — Professional, Bright, Warm**, voice ID `hpp4J3VqNfWAUOO0d1Us`. The account's voice catalog identified Standard American English, educational use, crisp diction and Flash v2 support, with no custom voice rate. No personal voice clone or voice-library addition was used.
- **Model:** `eleven_flash_v2`, the English model supporting individual-word [CMU Arpabet phoneme tags](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices#phoneme-tags-for-v2-models). Neither the model nor a provider SDK is included in this repository.
- **Local preparation:** FFmpeg `n9.0.2` with `libmp3lame`. No encoder executable or library is distributed here.

Provider licensing/ownership guidance was checked on 2026-11-01. The generation key remained outside the repository and browser. Only the finished audio is served by GitHub Pages; playing a name does not contact ElevenLabs.

## Pronunciation references

These are one set of clear English readings, not the only correct pronunciations. Accent, vowel quality and scientific-name stress can vary. The written guides are spelling aids, not formal IPA. Capitals mark stronger beats; the first capitalized syllable in `STEG-oh-SORE-us` and `DIP-low-DOCK-us` has secondary stress. `REKS` is a separately stressed word. Parasaurolophus **ROL** uses the short vowel in *doll*, not *roll*.

Seven guides retain the Natural History Museum, London, Dino Directory references consulted on 2026-10-31:

- [Brachiosaurus](https://www.nhm.ac.uk/discover/dino-directory/brachiosaurus.html): `BRAK-ee-oh-sore-us`.
- [Tyrannosaurus](https://www.nhm.ac.uk/discover/dino-directory/tyrannosaurus.html): `tie-RAN-oh-sore-us`, followed by `REKS` for *rex*.
- [Triceratops](https://www.nhm.ac.uk/discover/dino-directory/triceratops.html): museum `tri-SERRA-tops`, rendered as `try-SERR-uh-tops`.
- [Stegosaurus](https://www.nhm.ac.uk/discover/dino-directory/stegosaurus.html): `STEG-oh-SORE-us`.
- [Ankylosaurus](https://www.nhm.ac.uk/discover/dino-directory/ankylosaurus.html): `an-KYE-low-sore-us`.
- [Parasaurolophus](https://www.nhm.ac.uk/discover/dino-directory/parasaurolophus.html): `pa-ra-saw-ROL-off-us`.
- [Diplodocus](https://www.nhm.ac.uk/discover/dino-directory/diplodocus.html): `DIP-low-DOCK-us`.

[Plesiosaurus](https://www.merriam-webster.com/dictionary/plesiosaurus) follows Merriam-Webster's `ˌplēsēəˈsȯrəs`, rendered as `PLEE-see-uh-SORE-us`.

For [Pteranodon](https://www.merriam-webster.com/dictionary/pteranodon), the selected American variant is Merriam-Webster's `tə-ˈra-nə-ˌdän`, rendered as **tuh-RAN-uh-DON**: RAN has primary stress and DON secondary stress. This was cross-checked on 2026-11-01 against the [American Museum of Natural History OLogy guide](https://www.amnh.org/explore/ology/ology-cards/358-pteranodon-longiceps), which writes `ter-AN-o-don`. The silent initial P is not spoken. Pteranodon is a pterosaur and Plesiosaurus a marine reptile, not dinosaurs.

These references informed pronunciation; none of their audio was copied.

## Actual generation and preparation

API endpoint: `POST /v1/text-to-speech/hpp4J3VqNfWAUOO0d1Us?output_format=mp3_44100_128`.

```json
{
  "model_id": "eleven_flash_v2",
  "language_code": "en",
  "voice_settings": {
    "stability": 0.8,
    "similarity_boost": 0.75,
    "style": 0,
    "use_speaker_boost": true,
    "speed": 0.85
  },
  "seed": 42
}
```

The selected Pteranodon retake used seed 43; the other files used seed 42. Tyrannosaurus and rex have separate tags because the model's phoneme controls apply to individual words. The following are the complete selected text inputs, including final punctuation:

Filename labels below are for reference only; only each following phoneme-tag line was submitted as API text.

```xml
brachiosaurus
<phoneme alphabet="cmu-arpabet" ph="B R AE1 K IY0 OW0 S AO2 R AH0 S">Brachiosaurus</phoneme>.

tyrannosaurus-rex
<phoneme alphabet="cmu-arpabet" ph="T AY2 R AE1 N OW0 S AO2 R AH0 S">Tyrannosaurus</phoneme> <phoneme alphabet="cmu-arpabet" ph="R EH1 K S">rex</phoneme>.

triceratops
<phoneme alphabet="cmu-arpabet" ph="T R AY0 S EH1 R AH0 T AA0 P S">Triceratops</phoneme>.

stegosaurus
<phoneme alphabet="cmu-arpabet" ph="S T EH2 G OW0 S AO1 R AH0 S">Stegosaurus</phoneme>.

ankylosaurus
<phoneme alphabet="cmu-arpabet" ph="AE0 NG K AY1 L OW0 S AO2 R AH0 S">Ankylosaurus</phoneme>.

parasaurolophus
<phoneme alphabet="cmu-arpabet" ph="P AE2 R AH0 S AO0 R AA1 L AA0 F AH0 S">Parasaurolophus</phoneme>.

diplodocus
<phoneme alphabet="cmu-arpabet" ph="D IH2 P L OW0 D AA1 K AH0 S">Diplodocus</phoneme>.

plesiosaurus
<phoneme alphabet="cmu-arpabet" ph="P L IY2 S IY0 AH0 S AO1 R AH0 S">Plesiosaurus</phoneme>.

pteranodon
<phoneme alphabet="cmu-arpabet" ph="T AH0 R AE1 N AH0 D AA2 N">Pteranodon</phoneme>.
```

The generation batch used 10 requests, including one Pteranodon retake, and 963 submitted text characters including phoneme markup. It stayed within the approved 12-request/2,000-character limit. Seeds are best-effort controls, not a promise of byte-identical neural regeneration; published files are identified by their hashes below.

Each decoded provider MP3 received a constant gain chosen as `min(-20 - RMS_dBFS, -2 - peak_dBFS)` before padding, then 80 ms leading and 150 ms trailing silence. No syllables were trimmed, and no pitch shift or additional time stretching was applied. The final conversion was:

```sh
ffmpeg -i INPUT.mp3 \
  -af "volume=GAINdB,adelay=80:all=1,apad=pad_dur=0.15" \
  -ac 1 -ar 44100 -c:a libmp3lame -b:a 128k OUTPUT.mp3
```

All finished files are mono MP3 at 44,100 Hz / 128 kbit/s, totaling **241,545 bytes**. Durations, sizes and gain values below were measured or recorded from the actual files, not estimated from text.

| File | Spoken guide | Bytes | Duration (s) | Gain (dB) |
| --- | --- | ---: | ---: | ---: |
| `brachiosaurus.mp3` | BRAK-ee-oh-sore-us | 27,210 | 1.623197 | +9.684141 |
| `tyrannosaurus-rex.mp3` | tie-RAN-oh-sore-us REKS | 32,225 | 1.948277 | -1.276306 |
| `triceratops.mp3` | try-SERR-uh-tops | 26,374 | 1.576757 | +2.191605 |
| `stegosaurus.mp3` | STEG-oh-SORE-us | 26,374 | 1.576757 | +5.262850 |
| `ankylosaurus.mp3` | an-KYE-low-sore-us | 27,628 | 1.669637 | -0.504690 |
| `parasaurolophus.mp3` | pa-ra-saw-ROL-off-us | 27,210 | 1.623197 | +3.044655 |
| `diplodocus.mp3` | DIP-low-DOCK-us | 25,538 | 1.530317 | -1.838112 |
| `plesiosaurus.mp3` | PLEE-see-uh-SORE-us | 27,210 | 1.623197 | +1.824812 |
| `pteranodon.mp3` | tuh-RAN-uh-DON | 21,776 | 1.298118 | +2.041358 |

SHA-256 of the finished files:

```text
aa8fd2c114b58ecef6d4b1becb85ea2b4ec6ed41cdc423aaedafa7b79a6547be  brachiosaurus.mp3
1347f870fba1e75430e8c2931770b4fd0521da6efc104fb6e0062f31888d0346  tyrannosaurus-rex.mp3
8de7ed1228da4b891c1aab40d84d96b681bc652371bdfc84023f3d96e22881fd  triceratops.mp3
6cf57e8b349e6621f9ae12688d6fb745eb2c0fe9bf78471be16df9515131c76c  stegosaurus.mp3
14ccc2495f483ae2a32bcd69541f7c4f48b8fede52541e21b17fa6869811280e  ankylosaurus.mp3
4f535368e1ce0b36d3c7115656f080f1b0327ff06a2276c0ba3b3eeea8ed1867  parasaurolophus.mp3
d14aa8875b405928952d0781274937e2c5fb56db2a1b672049de554e0baac6bc  diplodocus.mp3
1b3336689d7b2166660c1fca51ab9f2feaff0226270e0c05c449c3e79c298e4f  plesiosaurus.mp3
094abb061f9d573c638785b612f85cc0cb7800dd59bd1a51934a425cb40a8922  pteranodon.mp3
```

## Quality evidence and limits

All nine finished files decoded successfully to 32-bit float PCM. No decoded samples reached full scale. Final peaks ranged from −7.34 to −2.54 dBFS; RMS levels, including padding, ranged from −21.30 to −20.99 dBFS.

An independent offline check used faster-whisper 1.2.1, Whisper `small.en`, CPU/int8, English, beam size 5, temperature 0, no preceding-text conditioning and **no name list or text prompt**. It recovered all nine selected names, ignoring capitalization and punctuation. The first Pteranodon attempt was recognized as an approximate phonetic phrase; the final dictionary-supported retake was recognized as Pteranodon.

Speech recognition is an intelligibility aid, **not a human listening review or proof of every vowel and stress**. No host-speaker playback was performed. Browser decoding/playback is checked muted separately. Generation scripts, credentials, intermediate audio, recognizer packages and model weights are not bundled with the site.
