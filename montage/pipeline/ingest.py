#!/usr/bin/env python3
"""Stage 1 — ingest: put every source on ONE master timeline (see montage/DESIGN.md §4).

Master time 0 = the first instant the mic, the phone and (optionally) the screen
all have content. Every later stage (transcript, edl.json, HyperFrames) speaks in
master seconds, so nothing downstream has to know about sync offsets again.

Writes to montage/episodes/<episode>/edit/:
  voice.wav     cleaned mic, master timeline, -16 LUFS (re-mastered at the mix stage)
  cam.mp4       phone video trimmed to the master timeline, 30 fps CFR
  screen.mp4    OBS recording trimmed to the master timeline, 30 fps CFR
  proxy.mp4     960x540 screen + camera bubble + voice, for review pages
  sources.json  offsets, durations, resolutions

Usage:
  python3 montage/pipeline/ingest.py --episode 2026-10-25-episode1 \
      --video phone.mov --audio mic.wav [--screen obs.mp4]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage as m  # noqa: E402  (reuse probe / sync / voice chain)

FPS = 30


def trim(src, start, duration, out, vf):
    m.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
           "-i", src, "-an", "-vf", f"{vf},fps={FPS}", "-c:v", "h264_videotoolbox",
           "-b:v", "12M", "-movflags", "+faststart", out])


def main():
    p = argparse.ArgumentParser(description="Montage Studio — stage 1 ingest")
    p.add_argument("--episode", required=True, help="folder name under montage/episodes/")
    p.add_argument("--video", required=True)
    p.add_argument("--audio", required=True)
    p.add_argument("--screen")
    p.add_argument("--offset", type=float)
    p.add_argument("--screen-offset", type=float)
    args = p.parse_args()

    edit = m.EPISODES / args.episode / "edit"
    edit.mkdir(parents=True, exist_ok=True)
    src = {"fps": FPS}

    vinfo = m.inspect_video(args.video)
    adur = float(m.probe(args.audio)["format"]["duration"])
    ch, levels = m.pick_mic_channel(args.audio)
    offset, ratio = ((args.offset, None) if args.offset is not None
                     else m.find_offset(args.video, args.audio, ch))
    print(f"  mic ch{ch + 1} {max(levels):.1f} dB | camera offset {offset:+.3f}s (peak {ratio})")
    m0, m1 = max(0.0, -offset), min(adur, vinfo["duration"] - offset)
    src["camera"] = {"path": args.video, "offset_s": offset, "sync_peak_ratio": ratio,
                     "width": vinfo["width"], "height": vinfo["height"]}

    if args.screen:
        soff, sratio = ((args.screen_offset, None) if args.screen_offset is not None
                        else m.find_offset(args.screen, args.audio, ch))
        sv = m.inspect_video(args.screen)
        print(f"  screen offset {soff:+.3f}s (peak {sratio}) {sv['width']}x{sv['height']}")
        m0, m1 = max(m0, -soff), min(m1, sv["duration"] - soff)
        src["screen"] = {"path": args.screen, "offset_s": soff, "sync_peak_ratio": sratio,
                         "width": sv["width"], "height": sv["height"]}
    duration = m1 - m0
    src["audio"] = {"path": args.audio, "channel": ch, "level_db": round(max(levels), 1),
                    "master_start_s": round(m0, 3)}
    src["duration_s"] = round(duration, 3)

    print(f"  master timeline {duration:.2f}s (mic {m0:.2f} → {m1:.2f})")
    src["input_lufs"] = m.clean_audio(args.audio, ch, m0, duration, edit / "voice.wav", edit)
    # The phone path skips HDR handling on purpose: VT tone-mapping lives in montage.py's
    # render, and a pilot on SDR WhatsApp video does not need it. Revisit for iPhone HDR.
    trim(args.video, m0 + offset, duration, edit / "cam.mp4", "setsar=1")
    if args.screen:
        trim(args.screen, m0 + src["screen"]["offset_s"], duration, edit / "screen.mp4", "setsar=1")
        main_in, graph = edit / "screen.mp4", (
            "[0:v]scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:-1:-1[s];"
            "[1:v]crop='min(iw,ih)':'min(iw,ih)':0:'(ih-oh)*0.3',scale=180:180[c];"
            "[s][c]overlay=W-w-16:H-h-16[v]")
    else:
        main_in, graph = edit / "cam.mp4", "[0:v]scale=-2:540[v];[1:v]nullsink"
    m.run(["ffmpeg", "-y", "-v", "error", "-i", main_in, "-i", edit / "cam.mp4",
           "-i", edit / "voice.wav", "-filter_complex", graph, "-map", "[v]", "-map", "2:a",
           "-c:v", "h264_videotoolbox", "-b:v", "2M", "-g", "15", "-c:a", "aac", "-b:a", "128k",
           "-shortest", "-movflags", "+faststart", edit / "proxy.mp4"])

    (edit / "sources.json").write_text(json.dumps(src, indent=2, ensure_ascii=False))
    print(f"done -> {edit}")


if __name__ == "__main__":
    main()
