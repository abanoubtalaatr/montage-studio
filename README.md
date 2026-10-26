# Montage Studio

An editing pipeline for screencast-style episodes. A phone camera, a podcast mic and an OBS
screen recording go in, and a finished YouTube edit comes out. It handles sync, voice
cleanup, de-breathing and a rough cut from a word-level transcript. Then it composes a
[HyperFrames](https://github.com/heygen-com/hyperframes) project with motion graphics in
your identity, so you can edit the film in **HyperFrames Studio** before rendering it with
a -14 LUFS master.

> استديو مونتاج: بيزامن الكاميرا والمايك وتسجيل الشاشة، وينضّف الصوت ويشيل صوت النفس، وبيقص من التفريغ كلمة بكلمة. بعدها بيبني مشروع HyperFrames فيه الموشن جرافيك بهويتك. تعدّل الفيلم في HyperFrames Studio، وترندره.

## Pipeline

```
inbox/ phone.mov + mic.wav + obs.mp4
  1 ingest.py      sync everything onto one master timeline, clean the voice
  2 transcribe.py  whisper (chunked + DTW) → words.json, proofreading in fixes.json
  3 roughcut.py    conservative cuts snapped to silence → edl.json + cut.html review
  4 voice.py       de-breath: duck non-speech found on the 180–4000 Hz band
  5 compose.py     edl.json + theme → HyperFrames project (episodes/<ep>/hf/index.html)
  6 Studio         npx hyperframes preview — move, trim and split clips, edit text, undo
  7 render.py      voice → hyperframes render → -14 LUFS master → youtube.mp4
```

Every kept segment becomes three clips: camera, screen and voice. Each one sits at its edit
time, with `data-media-start` pointing back into the source, so trimming a clip in Studio is
a real edit. The graphics are plain HTML + GSAP clips:

- keywords as `>_` prompts
- chapters as `git commit`
- `whoami` lower third
- a live `prompt.txt`
- kinetic captions
- a build sting and an outro

The design rules (style, identity, cutting rules, QC) are in [montage/DESIGN.md](montage/DESIGN.md).

## Setup

```bash
./setup.sh
```

The script installs:

- `ffmpeg` and `whisper-cpp` (Homebrew)
- `numpy`
- the pinned HyperFrames CLI
- the Whisper model **large-v3-turbo q5_0** (574 MB), downloaded from the official whisper.cpp
  repo on Hugging Face and verified by SHA-1. It isn't in git because GitHub refuses files over 100 MB.

Requirements: macOS with Homebrew, `python3` and **Node 22+**.

## Quick start

```bash
E=ep1
python3 montage/pipeline/ingest.py     --episode $E --video phone.mov --audio mic.wav --screen obs.mp4
python3 montage/pipeline/transcribe.py --episode $E
python3 montage/pipeline/roughcut.py   --episode $E      # review edit/cut.html (serve.py)
python3 montage/pipeline/compose.py    --episode $E      # writes episodes/$E/hf/
cd montage/episodes/$E/hf && npx hyperframes@0.8.199 preview   # edit in Studio
python3 montage/pipeline/render.py     --episode $E      # → episodes/$E/youtube.mp4
```

Once you have edited `hf/index.html` in Studio, `compose.py` refuses to overwrite it.
`--force` regenerates it from `edl.json` and keeps the old file as a backup.

## Identity

Themes are JSON files in `montage/themes/`, and the episode picks one with `edl.json → "theme"`.
The default, `abanoub-terminal`, is called **Terminal Builder**: near-black with indigo
#5B57FF and lime #C6FF3D.

Fonts are configurable per theme:

- Fonts HyperFrames bundles (Inter, JetBrains Mono…) need no file.
- Any other font needs `montage/assets/fonts/<Name>-{Medium,Bold}.ttf`. Tajawal and IBM Plex Sans Arabic are included (OFL).

Music is off by default. Put a track at `montage/assets/music/music.mp3` and set `music.on` in the theme.
