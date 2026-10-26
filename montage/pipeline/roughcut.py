#!/usr/bin/env python3
"""Stage 3 — rough cut: compile edl.json and build the cut.html review page.

edl.json holds the editorial decisions (see montage/DESIGN.md §4):
  hook[]   ranges played first as the cold open
  cuts[]   ranges removed; kind = slate | false_start | repeat | filler | setup | pause
  speed[]  ranges sped up (rate, voice "mute"|"keep")
Each has "on" so the review page can switch it off. Claude writes the editorial
ones by reading words.json; this script adds the mechanical "pause" cuts (silence
longer than MAX_PAUSE_S inside kept speech, leaving BREATH_S of air either side),
snaps every editorial cut edge to the quietest 10 ms within SNAP_S so no cut lands
inside a syllable, and compiles "segments" — the ordered playlist that Remotion renders.

Usage:  python3 montage/pipeline/roughcut.py --episode 2026-10-25-episode1
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

import transcribe  # noqa: E402  (montage helpers)

m = transcribe.m
MAX_PAUSE_S = 0.4
BREATH_S = 0.1
# Silence = more than PAUSE_DB under loud speech. transcribe's 30 dB "voiced" mask is
# too lenient here: keyboard clicks under a dictation kept every pause alive.
PAUSE_DB = 22
SNAP_S = 0.12
TEMPLATE = Path(__file__).resolve().parent / "cut_template.html"


def subtract(spans, holes):
    """spans minus holes; both lists of (a, b)."""
    out = []
    for a, b in spans:
        cur = a
        for h0, h1 in sorted(holes):
            if h1 <= cur or h0 >= b:
                continue
            if h0 > cur:
                out.append((cur, h0))
            cur = max(cur, h1)
        if cur < b:
            out.append((cur, b))
    return [(a, b) for a, b in out if b - a > 0.04]


def energy_db(voice):
    x = transcribe.m.decode_mono(voice, 16000)
    hop = int(16000 * transcribe.HOP)
    f = x[: len(x) // hop * hop].reshape(-1, hop).astype(np.float64)
    db = 20 * np.log10(np.sqrt((f ** 2).mean(axis=1)) + 1e-12)
    return np.convolve(db, np.ones(3) / 3, mode="same")


def snap(t, db):
    hop = transcribe.HOP
    a, b = max(int((t - SNAP_S) / hop), 0), min(int((t + SNAP_S) / hop) + 1, len(db))
    return round((a + int(np.argmin(db[a:b]))) * hop, 2) if b > a else t


def pause_cuts(voiced, spans, previous):
    was = {(c["start"], c["end"]): c["on"] for c in previous if c["kind"] == "pause"}
    hop, cuts = transcribe.HOP, []
    for a, b in spans:
        k0, k1, run = int(a / hop), int(b / hop), None
        for k in range(k0, k1 + 1):
            silent = k < k1 and not voiced[k]
            if silent and run is None:
                run = k
            elif not silent and run is not None:
                s, e = run * hop, k * hop
                if e - s > MAX_PAUSE_S and s > a and e < b:     # never at a span edge
                    c0, c1 = round(s + BREATH_S, 2), round(e - BREATH_S, 2)
                    cuts.append({"start": c0, "end": c1, "kind": "pause", "by": "auto",
                                 "on": was.get((c0, c1), True),
                                 "reason": f"{e - s:.2f} s silence → {2 * BREATH_S:.2f} s"})
                run = None
    for i, c in enumerate(cuts, 1):
        c["id"] = f"p{i}"
    return cuts


def compile_segments(edl, duration):
    on = lambda xs: [x for x in xs if x.get("on", True)]   # noqa: E731
    holes = [(c["start"], c["end"]) for c in on(edl["cuts"])]
    segs = [{"start": h["start"], "end": h["end"], "rate": 1, "mute": False, "role": "hook"}
            for h in on(edl["hook"])]
    speeds = on(edl["speed"])
    for a, b in subtract([(0.0, duration)], holes):
        # Split each kept span at speed-range edges.
        edges = sorted({a, b} | {x for s in speeds for x in (s["start"], s["end"]) if a < x < b})
        for s0, s1 in zip(edges, edges[1:]):
            sp = next((s for s in speeds if s["start"] <= s0 and s1 <= s["end"]), None)
            segs.append({"start": round(s0, 3), "end": round(s1, 3),
                         "rate": sp["rate"] if sp else 1,
                         "mute": bool(sp and sp.get("voice") == "mute"),
                         "role": "speed" if sp else "body"})
    return segs


def main():
    p = argparse.ArgumentParser(description="Montage Studio — stage 3 rough cut")
    p.add_argument("--episode", required=True)
    args = p.parse_args()
    edit = m.EPISODES / args.episode / "edit"
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    words = json.loads((edit / "words.json").read_text(encoding="utf-8"))
    duration = words["duration_s"]

    editorial = [c for c in edl["cuts"] if c["kind"] != "pause"]
    db = energy_db(edit / "voice.wav")
    voiced = db > np.percentile(db, 95) - PAUSE_DB
    for c in editorial + edl["hook"]:
        if c.get("by") != "auto" and not c.get("snapped"):
            # Edges at 0 or at the end of the recording stay put.
            if c["start"] > 0:
                c["start"] = snap(c["start"], db)
            if c["end"] < duration - 0.05:
                c["end"] = snap(c["end"], db)
            c["snapped"] = True
    taken = [(c["start"], c["end"]) for c in editorial if c.get("on", True)]
    taken += [(s["start"], s["end"]) for s in edl["speed"] if s.get("on", True)]
    spans = subtract([(0.0, duration)], taken)
    edl["cuts"] = sorted(editorial + pause_cuts(voiced, spans, edl["cuts"]), key=lambda c: c["start"])
    edl["segments"] = compile_segments(edl, duration)
    edl["duration_s"] = duration
    final = sum((s["end"] - s["start"]) / s["rate"] for s in edl["segments"])
    edl["edited_s"] = round(final, 2)
    (edit / "edl.json").write_text(json.dumps(edl, ensure_ascii=False, indent=1))

    data = {"episode": args.episode, "edl": edl, "words": words["words"]}
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (edit / "cut.html").write_text(html, encoding="utf-8")
    kinds = {}
    for c in edl["cuts"]:
        if c.get("on", True):
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print(f"{duration:.1f}s → {final:.1f}s | cuts {kinds} | {len(edl['segments'])} segments")
    print(f"review -> {edit / 'cut.html'}")


if __name__ == "__main__":
    main()
