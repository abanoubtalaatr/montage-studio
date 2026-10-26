#!/usr/bin/env python3
"""Voice finishing: duck breaths and air noise between words → edit/voice_final.wav.

The PodMic sits close, so between phrases it hears exhales and air rumble ~20 dB
under the speech. The compressor and the -14 LUFS master lift that right back up
("I can hear myself breathing"). A broadband gate would also chop quiet word
endings, so speech is detected on the 180–4000 Hz band only — where breath rumble
has little energy — and everything else is turned DOWN (not muted, so the room
tone stays and cuts don't sound gated).

Parameters come from edl.json → "audio" (the dashboard edits them):
  highpass_hz      80–140  second high-pass against air rumble (default 110)
  breath_duck_db   0…-30   how far non-speech is turned down (default -18)
  speech_db        12–30   speech = band energy within this many dB of loud speech (default 20)
  hold_ms                  keep open after speech (default 160)

Usage:  python3 montage/pipeline/voice.py --episode 2026-10-25-episode1
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage as m  # noqa: E402

SR = 48000
DEFAULTS = {"highpass_hz": 110, "breath_duck_db": -18, "speech_db": 20, "hold_ms": 160}
PRE_MS = 40           # open slightly before speech so onsets keep their attack
ATTACK_MS, RELEASE_MS = 8, 70


def speech_mask(x, p):
    hop, win = SR // 100, SR // 50
    n = len(x) // hop - 2
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop][:n] * np.hanning(win)
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    fr = np.fft.rfftfreq(win, 1 / SR)
    band = 10 * np.log10(spec[:, (fr > 180) & (fr < 4000)].sum(axis=1) + 1e-12)
    on = band > np.percentile(band, 95) - p["speech_db"]
    # Drop clicks shorter than 40 ms, then hold open after speech and pre-open before it.
    k = 0
    while k < n:
        if on[k]:
            j = k
            while j < n and on[j]:
                j += 1
            if j - k < 4:
                on[k:j] = False
            k = j
        else:
            k += 1
    hold, pre = p["hold_ms"] // 10, PRE_MS // 10
    out = on.copy()
    idx = np.nonzero(on)[0]
    for i in idx:
        out[max(i - pre, 0): i + hold + 1] = True
    return out, hop


def gain_curve(mask, hop, n_samples, duck_db):
    floor = 10 ** (duck_db / 20)
    target = np.where(mask, 1.0, floor)
    a = np.exp(-1 / (ATTACK_MS / 10))
    r = np.exp(-1 / (RELEASE_MS / 10))
    g, cur = np.empty_like(target), floor
    for k, t in enumerate(target):
        c = a if t > cur else r
        cur = c * cur + (1 - c) * t
        g[k] = cur
    t_frames = (np.arange(len(g)) + 0.5) * hop
    return np.interp(np.arange(n_samples), t_frames, g)


def main():
    p = argparse.ArgumentParser(description="Montage Studio — voice finishing (de-breath)")
    p.add_argument("--episode", required=True)
    args = p.parse_args()
    edit = m.EPISODES / args.episode / "edit"
    edl_path = edit / "edl.json"
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    prm = {**DEFAULTS, **edl.get("audio", {})}

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", edit / "voice.wav", "-af",
                          f"highpass=f={prm['highpass_hz']},highpass=f={prm['highpass_hz']}",
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    mask, hop = speech_mask(x, prm)
    y = (x * gain_curve(mask, hop, len(x), prm["breath_duck_db"])).astype(np.float32)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                    "-c:a", "pcm_s16le", edit / "voice_final.wav"], input=y.tobytes(), check=True)
    ducked = 1 - mask.mean()
    print(f"voice_final.wav: {ducked * 100:.0f}% of the time ducked by {prm['breath_duck_db']} dB "
          f"(highpass {prm['highpass_hz']} Hz)")


if __name__ == "__main__":
    main()
