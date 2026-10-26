# Montage Studio

An editing pipeline and dashboard for screencast-style episodes: a phone camera, a
podcast mic and an OBS screen recording go in, and a finished YouTube edit comes out.
It handles sync, voice cleanup, de-breathing, a rough cut from a word-level
transcript, motion graphics in Remotion and a -14 LUFS master. Every decision lives
in one `edl.json`, and you edit it live in a local dashboard.

> استديو مونتاج: بيزامن الكاميرا والمايك وتسجيل الشاشة، وينضّف الصوت ويشيل صوت النفس. بعدها بيقص من التفريغ كلمة بكلمة، ويضيف موشن جرافيك بـ Remotion. وتقدر تتحكم في كل حاجة من داشبورد.

## Pipeline

```
inbox/ phone.mov + mic.wav + obs.mp4
  1 ingest.py      sync everything onto one master timeline, clean the voice
  2 transcribe.py  whisper (chunked + DTW) → words.json, proofreading in fixes.json
  3 roughcut.py    conservative cuts snapped to silence → edl.json + cut.html review
  4 voice.py       de-breath: duck non-speech found on the 180–4000 Hz band
  5 render.py      voice → Remotion (EpisodeYouTube) → -14 LUFS master → youtube.mp4
```

The design rules (style, identity, cutting rules, QC) are in [montage/DESIGN.md](montage/DESIGN.md).

## Dashboard

```bash
cd remotion && npm install
npm run studio            # → http://127.0.0.1:5190
```

- **Live preview** (Remotion Player) of the exact component that renders.
- **Cuts:** click a word to seek, shift-click to select. Then cut it, restore it, turn it into an on-screen keyword, or make it the hook.
- **Graphics, shots** (talk/screen, zoom and focus), **identity** (theme colours, fonts, name, captions, music, SFX) and **audio** (de-breath settings).
- **Save** (Cmd+S, with `edl.backup.json`), **undo** (Cmd+Z), and **render** with a progress bar.

## Identity

Themes are JSON files in `remotion/public/themes/`. The default, `abanoub-terminal`,
is called **Terminal Builder**:

- Colours: near-black, indigo #5B57FF and lime #C6FF3D.
- Fonts: IBM Plex Sans Arabic and JetBrains Mono.
- Graphics: keywords appear as `>_` prompts, chapters as `git commit` and the name as `whoami`.

## Requirements

- macOS
- `ffmpeg`
- `python3` with `numpy`
- `whisper-cli` (whisper.cpp), with a model in `montage/models/ggml-*.bin`
- Node 18+

Music is off by default. Put a track at `remotion/public/music.mp3` and switch it on in the dashboard.

## Quick start

```bash
python3 montage/pipeline/ingest.py --episode ep1 --video phone.mov --audio mic.wav --screen obs.mp4
python3 montage/pipeline/transcribe.py --episode ep1
python3 montage/pipeline/roughcut.py --episode ep1
cd remotion && npm run studio        # add graphics/shots, then Render
```
