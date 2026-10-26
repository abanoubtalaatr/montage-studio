#!/usr/bin/env python3
"""Stage 7 — render: HyperFrames draws the film from hf/index.html, ffmpeg masters the sound.

  1. voice.py      edl.json "audio" → voice_final.wav (hard-linked into hf/assets, so the
                   project picks the new take up without re-composing)
  2. compose.py    only when hf/ does not exist yet — never over Studio edits
  3. hyperframes render   hf/ → .youtube.mp4 (pinned CLI version, delivery quality)
  4. master        -14 LUFS, true peak -1 dB (DESIGN.md §3) → youtube.mp4

Usage:  python3 montage/pipeline/render.py --episode 2026-10-25-episode1
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage as m  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose import HF_VERSION  # noqa: E402

LUFS, TP = -14, -1.0


def master(src, out):
    stats = m.run(["ffmpeg", "-hide_banner", "-i", src, "-af",
                   f"loudnorm=I={LUFS}:TP={TP}:LRA=9:print_format=json", "-f", "null", "-"], capture=True)
    s = json.loads(stats[stats.rindex("{"): stats.rindex("}") + 1])
    m.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-c:v", "copy", "-af",
           f"loudnorm=I={LUFS}:TP={TP}:LRA=9:measured_I={s['input_i']}:measured_TP={s['input_tp']}:"
           f"measured_LRA={s['input_lra']}:measured_thresh={s['input_thresh']}:"
           f"offset={s['target_offset']}:linear=true",
           "-ar", "48000", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", out])


def main():
    p = argparse.ArgumentParser(description="Montage Studio — stage 7 render (HyperFrames)")
    p.add_argument("--episode", required=True)
    p.add_argument("--out", default="youtube.mp4")
    p.add_argument("--quality", default="delivery", choices=["draft", "looks", "delivery"])
    args = p.parse_args()
    ep = m.EPISODES / args.episode
    here = Path(__file__).parent

    print("1/4 voice (de-breath)", flush=True)
    m.run([sys.executable, here / "voice.py", "--episode", args.episode])
    if not (ep / "hf" / "index.html").exists():
        print("2/4 compose (first time)", flush=True)
        m.run([sys.executable, here / "compose.py", "--episode", args.episode])
    else:
        print("2/4 compose — skipped, rendering the Studio version of hf/index.html", flush=True)

    print("3/4 hyperframes render", flush=True)
    raw = ep / f".{args.out}"
    # Not captured: the CLI's own progress output is useful in a terminal.
    proc = subprocess.run(["npx", "--yes", f"hyperframes@{HF_VERSION}", "render", "--quality", args.quality,
                           "--output", str(raw.resolve())], cwd=ep / "hf")
    if proc.returncode != 0:
        raise SystemExit("hyperframes render failed")
    print("4/4 master -14 LUFS", flush=True)
    master(raw, ep / args.out)
    raw.unlink()
    print(f"done -> {ep / args.out}")


if __name__ == "__main__":
    main()
