---
name: montage
description: Edit a screencast/podcast episode end-to-end — phone video + PodMic/Scarlett audio from Audacity → synced, cleaned, loudness-normalised YouTube (16:9) + Reel (9:16) with Arabic subtitles and thumbnails, via montage/montage.py. Use whenever the user sends/mentions a new recording or wants editing — triggers include "منتاج", "مونتاج", "عدّل الفيديو", "الحلقة الجديدة", "بعتلك الفيديو", "سجلت حلقة", "اعمل ريل", "podcast edit", "montage", "edit the video" — even if they just say "الفيديو وصل".
---

# Montage Studio — منتاج الحلقات

The user films on their phone and records the voice with a Rode PodMic →
Focusrite Scarlett Solo 4th Gen → Audacity on this Mac. You turn the two
files into a finished episode. The heavy lifting is `montage/montage.py`
(ffmpeg + numpy); your job is finding the inputs, running it, **checking
the result like an editor would**, and reporting back in Arabic.

## 1. Find the inputs

- **Video**: the user AirDrops it from the phone → newest `.mov`/`.mp4` in
  `~/Downloads`, or anything they drop in `montage/inbox/`.
- **Audio**: exported from Audacity (File → Export Audio → WAV) → newest
  `.wav`/`.m4a` in `montage/inbox/` or `~/Downloads`.
- **Screen** (optional): OBS screen recording → newest `.mp4` in `~/Movies`.
  If the user recorded the screen, it MUST go in via `--screen` — an edit
  that drops it is not the episode they filmed. Ask if unsure whether one exists.
- **WhatsApp-forwarded video** (`WhatsApp Video …`, ~480 px wide) is
  recompressed and soft — ask for the AirDrop original before rendering.
- If either is missing or ambiguous (several candidates from today), list
  them with size + time and ask which. Never guess between two takes.
- Sanity: the audio and the video should be roughly the same length
  (within a few minutes). Wildly different → probably the wrong pair; ask.
- Disk is tight on this Mac (~25 GB free). Need ≈ 2× the video size free;
  check `df -h ~` before rendering a long episode.

## 2. Run

```bash
python3 montage/montage.py --video <video> --audio <wav> --name "<short-name>" [--jumpcut]
```

- `--jumpcut` removes silences > 0.8 s (`--min-silence` to tune). Default
  ON for monologue/tips episodes; OFF for interviews/conversations, where
  pauses carry meaning — ask if unclear.
- `--offset <s>` only if auto-sync failed (see checks).
- `--k4` keeps 4K for YouTube — only when the user asks; files are big.
- `--screen <obs.mp4>` merges the screen recording: YouTube = screen
  full-frame + camera picture-in-picture bottom-right; Reel = screen on top,
  camera below. It syncs off OBS's own copy of the Scarlett mic
  (`report.json` → `screen.offset_s` / `sync_peak_ratio`, same ≥ 1.15 rule);
  `--screen-offset <s>` forces it. Check the opening seconds: OBS often
  starts on the Claude/setup window before the user switches apps. Find the
  switch (`select='gt(scene,0.15)',showinfo` on the first ~15 s of
  `youtube.mp4`) and re-render with `--camera-first <s>` (final-video
  seconds): the camera fills the frame until then, so no speech is cut.
- A quiet mic is pre-gained so speech peaks near -20 dBFS before the voice
  chain; without that, the denoiser/gate treated -45 dB speech as noise and
  the voice came out thin ("sounds like the phone").
- Run long renders in the background (≈ 0.3–0.5× real-time on this M1).

Output: `montage/episodes/<date>-<name>/` → `youtube.mp4`, `reel.mp4`,
`subtitles.srt` (when a Whisper model is in `montage/models/`),
`thumbnails/thumb-1..4.jpg`, `report.json`.

### Full edit pipeline (montage/DESIGN.md — pilot, stages 1–3 built)

`montage.py` alone only syncs + cleans; a real edit goes through
`montage/pipeline/` on one master timeline (`edit/` inside the episode):

```bash
python3 montage/pipeline/ingest.py --episode <folder> --video … --audio … --screen …
python3 montage/pipeline/transcribe.py --episode <folder>   # words.json (chunked + DTW)
# proofread → edit/fixes.json (time-keyed), re-run transcribe
# write editorial decisions → edit/edl.json (hook / cuts / speed, reasons in ARABIC)
python3 montage/pipeline/roughcut.py --episode <folder>     # adds pause cuts, segments, cut.html
python3 montage/pipeline/serve.py   # http://127.0.0.1:8765/<folder>/edit/cut.html
```

- Whole-file whisper drifted and duplicated a sentence; transcribe splits at
  pauses (≤ 25 s chunks) and drops known hallucinations («ترجمة نانسي قنقر»).
- cut.html needs an HTTP server with Range (serve.py) — `http.server` can't seek video.
- The user reviews cut.html and pastes back `cut review {...}` (ids off + notes):
  apply it to edl.json, re-run roughcut.py.
- **Cut conservatively.** The user wants every meaningful sentence kept — cut only
  slate/claps, setup talk («نوقف التسجيل»), true stutters, «آآ», and pauses.
  Restating, «وهكذا», «يعني» stay. A slow dictation stays at 1× (pauses tightened);
  speeding up speech was rejected.
- Motion graphics are mandatory, not optional: write `shots[]` (talk / screen +
  zoom/focus) and `gfx[]` into edl.json — `keyword` whenever a key phrase is SAID
  (e.g. «موبايل أبليكيشن» → it appears on screen), `list`, `chapter`,
  `lower_third`, `prompt` (typed text appears word by word), `sting`, `outro`.
  Times are master seconds. Check with stills before the full render:
  `npx remotion still src/index.ts EpisodeYouTube out.jpg --frame=N` in remotion/.
- Stage 7: `python3 montage/pipeline/render.py --episode <folder>` → voice.py (de-breath,
  edl.json "audio") → Remotion `EpisodeYouTube` → `youtube.mp4` at -14 LUFS.
- **Identity**: theme `abanoub-terminal`
  (remotion/public/themes/, "Terminal Builder": #0B0D12 / indigo #5B57FF / lime
  #C6FF3D, IBM Plex Sans Arabic + JetBrains Mono, keywords as `>_` prompts, chapters as
  git commits). Set `"theme"` in edl.json.
- **Breathing was audible** after the -14 master: always ship voice_final.wav (voice.py).
- **Dashboard** (the user wants full control without prompting):
  `npm --prefix remotion run studio` → http://127.0.0.1:5190 (launch.json
  "montage-studio"). Live Player preview, cuts/graphics/shots/identity/audio editors,
  Save (edl.json + backup), Render with progress. Point the user there for small tweaks.

## 3. Check before saying it's done (read `report.json`)

| Field | Good | If not |
|---|---|---|
| `channel_levels_db` max | > -40 dB | Mic barely recorded → Scarlett gain low or Audacity on Mono (mic is on **channel 2**; Audacity must record **2 (Stereo)**). Tell the user; don't "fix" with gain — it amplifies noise. |
| `sync_peak_ratio` | ≥ 1.15 | Weak match → look at the offset; ask the user to clap at the start next time. Re-run with `--offset` if they know it. |
| `offset_s` | plausible (usually 0–30 s) | A huge value = wrong file pair. |
| output loudness | ≈ -16 LUFS, peak ≤ -1.5 | Measure: `ffmpeg -i youtube.mp4 -af ebur128=peak=true -f null - 2>&1 \| tail -12` |
| `jumpcut.cut_s` | a modest share of the length | Cutting > 40 % usually means the mic was too quiet and speech got treated as silence. |

Then **proofread `subtitles.srt`** (Whisper large-v3-turbo, Arabic): fix
mis-heard product terms by hand — brand names, «الـ AI», English tech words —
and obvious split words («هنا تكلم» → «هنتكلم»). Keep the timings; edit
text only. Don't pass `--prompt` to whisper-cli: it made the turbo model
return an empty transcript.

Then **look**: Read 2–3 thumbnails, and grab a frame from `reel.mp4` to
make sure the 9:16 crop keeps the speaker's face (it is a centre crop — if
the speaker sat off-centre, say so).

## 4. Report (Arabic, short)

Length before/after, what was cut, sync offset, loudness, the paths of
the two videos + subtitles, and the best thumbnail. Open the folder with
`open montage/episodes/<folder>`.

Publishing anywhere is a separate, outward-facing step: only on the user's
explicit go-ahead for that file.

## 5. Tidy up (ask first)

Raw phone videos are large. After the user confirms the edit is good,
offer to delete the source files in `montage/inbox/` / `~/Downloads`.

## Known limits / gotchas

- **Burned-in subtitles**: this ffmpeg has no libass/drawtext, so subtitles
  ship as `.srt` (YouTube upload / CapCut import). Burning Arabic captions
  into the Reel is a future step via `remotion/`.
- **iPhone HDR** (HLG/Dolby Vision) is converted to normal colours through
  VideoToolbox (`scale_vt`); that path skips ffmpeg autorotate, so the
  script rotates by hand — keep both if you touch it.
- Whisper model goes in `montage/models/ggml-*.bin` (not committed). The
  biggest one present is used, language forced to Arabic.
