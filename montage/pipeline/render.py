#!/usr/bin/env python3
"""Stage 7 — render: Remotion draws the edit from edl.json, ffmpeg masters the sound.

Runs voice.py first (edl.json "audio" → voice_final.wav). Remotion reads
montage/episodes/<ep>/edit through the symlink
remotion/public/episodes/<ep> (created here if missing). The voice was
normalised for podcasts (-16 LUFS); the finished video is mastered to the
YouTube/Reels standard: -14 LUFS, true peak -1 dB (montage/DESIGN.md §3).

Usage:  python3 montage/pipeline/render.py --episode 2026-10-25-episode1
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage as m  # noqa: E402

REMOTION = m.ROOT.parent / "remotion"
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
    p = argparse.ArgumentParser(description="Montage Studio — stage 7 render")
    p.add_argument("--episode", required=True)
    p.add_argument("--composition", default="EpisodeYouTube")
    p.add_argument("--out", default="youtube.mp4")
    args = p.parse_args()
    ep = m.EPISODES / args.episode
    link = REMOTION / "public" / "episodes" / args.episode
    if not link.exists():
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(Path("../../../montage/episodes") / args.episode / "edit")
    raw = ep / f".{args.out}"
    props = json.dumps({"episode": args.episode})
    print("1/3 voice (de-breath)", flush=True)
    m.run([sys.executable, Path(__file__).parent / "voice.py", "--episode", args.episode])
    print("2/3 remotion render", flush=True)
    # Streamed, not captured: the dashboard reads "Rendered N/M" lines for its progress bar.
    proc = subprocess.Popen(["npx", "remotion", "render", "src/index.ts", args.composition, str(raw.resolve()),
                             "--codec=h264", "--crf=18", f"--props={props}"], cwd=REMOTION,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        print(line.rstrip(), flush=True)
    if proc.wait() != 0:
        raise SystemExit("remotion render failed")
    print("3/3 master -14 LUFS", flush=True)
    master(raw, ep / args.out)
    raw.unlink()
    print(f"done -> {ep / args.out}")


if __name__ == "__main__":
    main()
