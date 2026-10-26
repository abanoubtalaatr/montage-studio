#!/usr/bin/env python3
"""Stage 2 — transcribe: word-level Arabic transcript on the master timeline.

whisper-cli with DTW token alignment (needs flash attention OFF: -nfa) gives each
token an onset; tokens that start with a space open a new word. One pass over the
whole file drifted on episode 1 — it stretched a slow dictation across 30 s and
transcribed one sentence twice — so the voice is split at pauses into chunks of
at most CHUNK_S and each chunk is transcribed on its own. Word ends come from
the voice energy: a word ends at its last voiced 10 ms frame before the next word.

Proofreading lives in edit/fixes.json, keyed by TIME so a re-run keeps it:
  [{"start": 35.0, "end": 35.8, "text": "الـ AI"}]  # words starting in [start, end) → one
  [{"start": 15.4, "end": 15.5, "text": ""}]        # empty text deletes them

Writes edit/words.json: {"words": [{"i", "w", "start", "end", "p", "raw"?}]}.

Usage:  python3 montage/pipeline/transcribe.py --episode 2026-10-25-episode1 [--fresh]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage as m  # noqa: E402

DTW_PRESET = {"turbo": "large.v3.turbo", "large-v3": "large.v3", "medium": "medium"}
HOP = 0.01          # energy frame, seconds
CHUNK_S = 25        # longest chunk handed to whisper
MIN_PAUSE_S = 0.3   # a pause this long is a safe place to split
# Subtitle credits whisper learned from YouTube and "hears" in silence or claps.
HALLUCINATIONS = ["ترجمة نانسي قنقر", "اشتركوا في القناة", "شكرا للمشاهدة"]


def voiced_frames(voice):
    x = m.decode_mono(voice, 16000)
    hop = int(16000 * HOP)
    f = x[: len(x) // hop * hop].reshape(-1, hop).astype(np.float64)
    db = 20 * np.log10(np.sqrt((f ** 2).mean(axis=1)) + 1e-12)
    return db > np.percentile(db, 95) - 30          # within 30 dB of loud speech


def chunk_bounds(voiced):
    """Split points in the middle of pauses, each chunk <= CHUNK_S."""
    n, need = len(voiced), int(MIN_PAUSE_S / HOP)
    pauses, run = [], 0
    for k, v in enumerate(voiced):
        run = 0 if v else run + 1
        if run == need:
            pauses.append(k - need // 2)
    bounds, start = [0], 0
    while n - start > CHUNK_S / HOP:
        inside = [q for q in pauses if start + 5 / HOP < q <= start + CHUNK_S / HOP]
        start = inside[-1] if inside else start + int(CHUNK_S / HOP)
        bounds.append(start)
    return [b * HOP for b in bounds] + [n * HOP]


def transcribe_chunks(voice, voiced, edit):
    model = sorted(m.MODELS.glob("ggml-*.bin"), key=lambda p: p.stat().st_size, reverse=True)[0]
    preset = next((v for k, v in DTW_PRESET.items() if k in model.name), None)
    edges, chunks = chunk_bounds(voiced), []
    for a, b in zip(edges, edges[1:]):
        wav = edit / ".chunk.wav"
        m.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.2f}", "-t", f"{b - a:.2f}",
               "-i", voice, "-ac", "1", "-ar", "16000", wav])
        cmd = ["whisper-cli", "-m", model, "-l", "ar", "-f", wav, "-ojf", "-of", edit / ".chunk"]
        if preset:
            cmd += ["-dtw", preset, "-nfa"]
        m.run(cmd)
        data = json.loads((edit / ".chunk.json").read_text(encoding="utf-8"))
        chunks.append({"start": a, "end": b, "transcription": data["transcription"]})
    for f in (".chunk.wav", ".chunk.json"):
        (edit / f).unlink(missing_ok=True)
    return {"model": model.name, "chunks": chunks}


def group_words(raw):
    words = []
    for ch in raw["chunks"]:
        first = len(words)
        for seg in ch["transcription"]:
            for tok in seg["tokens"]:
                text = tok["text"]
                if text.startswith("[_") or not text.strip():
                    continue
                t = (tok["t_dtw"] / 100 if tok.get("t_dtw", -1) >= 0
                     else tok["offsets"]["from"] / 1000) + ch["start"]
                t = min(max(t, ch["start"]), ch["end"])
                if text.startswith(" ") or len(words) == first:
                    words.append({"w": text.strip(), "start": t, "p": [tok["p"]]})
                else:
                    words[-1]["w"] += text
                    words[-1]["p"].append(tok["p"])
    return words


def drop_hallucinations(words):
    text = [w["w"] for w in words]
    for phrase in HALLUCINATIONS:
        n = len(phrase.split())
        for k in range(len(words) - n, -1, -1):
            if " ".join(text[k: k + n]) == phrase:
                del words[k: k + n], text[k: k + n]
    return words


def snap_ends(words, voiced, total):
    n = len(voiced)
    for k, w in enumerate(words):
        nxt = words[k + 1]["start"] if k + 1 < len(words) else total
        a, b = int(w["start"] / HOP), min(int(nxt / HOP), n)
        frames = np.nonzero(voiced[a:b])[0]
        # Last voiced frame before the next word; a word is at least 80 ms long.
        end = (a + frames[-1] + 1) * HOP if len(frames) else nxt
        w["end"] = round(min(max(w["start"] + 0.08, end), max(nxt, w["start"] + 0.08)), 3)
        w["start"] = round(w["start"], 3)
        w["p"] = round(float(np.mean(w["p"])), 3)
        w["raw"] = w["w"]


def apply_fixes(words, fixes):
    for f in sorted(fixes, key=lambda f: f["start"], reverse=True):
        idx = [k for k, w in enumerate(words) if f["start"] <= w["start"] < f["end"]]
        if not idx:
            print(f"  ! fix {f} matches no word")
            continue
        span = words[idx[0]: idx[-1] + 1]
        new = ([{"w": f["text"], "start": span[0]["start"], "end": span[-1]["end"], "p": 1.0,
                 "raw": " ".join(w["raw"] for w in span)}] if f["text"] else [])
        words[idx[0]: idx[-1] + 1] = new
    for i, w in enumerate(words):
        w["i"] = i


def main():
    p = argparse.ArgumentParser(description="Montage Studio — stage 2 transcribe")
    p.add_argument("--episode", required=True)
    p.add_argument("--fresh", action="store_true", help="ignore the cached whisper.json")
    args = p.parse_args()
    edit = m.EPISODES / args.episode / "edit"
    voice = edit / "voice.wav"
    cache = edit / "whisper.json"
    voiced = voiced_frames(voice)

    if args.fresh or not cache.exists() or "chunks" not in json.loads(cache.read_text()):
        raw = transcribe_chunks(voice, voiced, edit)
        cache.write_text(json.dumps(raw, ensure_ascii=False))
    else:
        raw = json.loads(cache.read_text(encoding="utf-8"))

    words = drop_hallucinations(group_words(raw))
    total = float(m.probe(voice)["format"]["duration"])
    snap_ends(words, voiced, total)
    fixes_path = edit / "fixes.json"
    fixes = json.loads(fixes_path.read_text(encoding="utf-8")) if fixes_path.exists() else []
    apply_fixes(words, fixes)

    out = {"model": raw["model"], "duration_s": total, "fixes": len(fixes),
           "words": [{k: w[k] for k in ("i", "w", "start", "end", "p")}
                     | ({"raw": w["raw"]} if w["raw"] != w["w"] else {}) for w in words]}
    (edit / "words.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(words)} words in {len(raw['chunks'])} chunks ({len(fixes)} fixes) -> {edit / 'words.json'}")


if __name__ == "__main__":
    main()
