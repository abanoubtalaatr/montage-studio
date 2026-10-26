#!/usr/bin/env python3
"""Stage 5 — compose: turn edl.json into a HyperFrames project you edit in Studio.

    montage/episodes/<ep>/hf/
      index.html      the whole film: every kept segment is a camera clip, a screen
                      clip and a voice clip at its edit time (data-media-start = where it
                      sits in the source), plus graphics, captions and SFX as timed clips
      assets/         hard links to the media (no extra disk), fonts, SFX, logo
      hyperframes.json, meta.json, package.json

After this, the HTML is what you edit (HyperFrames Studio: `npx hyperframes preview`
inside hf/). Re-composing would throw those edits away, so it refuses when index.html
changed since it was generated — pass --force to regenerate (the old file is kept as
index.<time>.html).

Look and identity come from montage/themes/<edl.theme>.json (DESIGN.md §2).

Usage:  python3 montage/pipeline/compose.py --episode 2026-10-25-episode1 [--force]
"""

import argparse
import hashlib
import html
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import roughcut  # noqa: E402  (compile_segments)

m = roughcut.m
ROOT = m.ROOT                       # montage/
THEMES = ROOT / "themes"
ASSETS = ROOT / "assets"
FPS = 30
HF_VERSION = "0.8.199"              # pinned: a release some days old, not the newest
W, H = 1920, 1080

# Geometry (DESIGN.md §2). The camera window is one fixed box; the screen layout
# turns it into a circle with transform + clip-path (HyperFrames forbids tweening
# left/top/width/height).
CAM = dict(x=1310, y=110, w=500, h=830)
CIRCLE = dict(x=1570, y=640, d=290)
LENS = dict(x=60, y=110, w=1480, h=832)
CHROME = 44
MOVE = 0.66                         # layout change, seconds
FACE_Y = 0.46                       # where the face sits in the camera window


def esc(s):
    return html.escape(str(s), quote=True)


def t3(f):
    """Frames → seconds string, frame-exact."""
    return f"{f / FPS:.3f}"


# ------------------------------------------------------------------ timeline

class Timeline:
    """Hook → sting → body → outro, in frames."""

    def __init__(self, edl):
        segs = roughcut.compile_segments(edl, edl["duration_s"])
        gfx = [g for g in edl["gfx"] if g.get("on", True)]
        sting = next((g for g in gfx if g["type"] == "sting"), None)
        outro = next((g for g in gfx if g["type"] == "outro"), None)
        self.placed, cursor = [], 0.0

        def put(s):
            nonlocal cursor
            f0 = round(cursor * FPS)
            cursor += (s["end"] - s["start"]) / s["rate"]
            self.placed.append({"seg": s, "from": f0, "frames": round(cursor * FPS) - f0})

        hooks = [s for s in segs if s["role"] == "hook"]
        for s in hooks:
            put(s)
        self.sting = None
        if sting and hooks:
            self.sting = (round(cursor * FPS), round(sting.get("dur", 2) * FPS))
            cursor += sting.get("dur", 2)
        for s in segs:
            if s["role"] != "hook":
                put(s)
        self.outro = None
        if outro:
            self.outro = (round(cursor * FPS), round(outro.get("dur", 4) * FPS))
            cursor += outro.get("dur", 4)
        self.total = round(cursor * FPS)
        self.body = [p for p in self.placed if p["seg"]["role"] != "hook"]

    def _at(self, p, t):
        return p["from"] + round((t - p["seg"]["start"]) / p["seg"]["rate"] * FPS)

    def body_frame(self, t):
        for p in self.body:
            if t < p["seg"]["end"]:
                return p["from"] if t <= p["seg"]["start"] else self._at(p, t)
        return self.outro[0] if self.outro else self.total

    def frames(self, t):
        return [self._at(p, t) for p in self.placed if p["seg"]["start"] <= t < p["seg"]["end"]]

    def spans(self, a, b):
        out = []
        for p in self.placed:
            s = p["seg"]
            if s["start"] < b and a < s["end"]:
                f0 = self._at(p, max(a, s["start"]))
                f1 = min(self._at(p, min(b, s["end"])), p["from"] + p["frames"])
                if f1 > f0:
                    out.append((f0, f1))
        return out


# ------------------------------------------------------------------ builders

class Film:
    def __init__(self, edl, words, theme, tl):
        self.edl, self.words, self.th, self.tl = edl, words, theme, tl
        self.html, self.js, self.audio = [], [], []
        self.n = 0

    def uid(self, p):
        self.n += 1
        return f"{p}{self.n}"

    def clip(self, cls, f0, f1, inner, track, style="", extra=""):
        i = self.uid(cls.split()[0][:3])
        self.html.append(
            f'<div id="{i}" class="clip {cls}" data-start="{t3(f0)}" data-duration="{t3(f1 - f0)}" '
            f'data-track-index="{track}"{extra} style="{style}">{inner}</div>')
        return i

    def sfx(self, f, name, vol=1.0):
        if not self.th["sfx"]["on"] or f < 0:
            return
        i = self.uid("sfx")
        self.audio.append(f'<audio id="{i}" src="assets/sfx/{name}.wav" data-start="{t3(f)}" '
                          f'data-duration="0.5" data-track-index="9" '
                          f'data-volume="{self.th["sfx"]["volume"] * vol:.2f}"></audio>')

    # --- media: one camera / screen / voice clip per kept segment
    def media(self):
        cam, scr = [], []
        for k, p in enumerate(self.tl.placed):
            s, f0, n = p["seg"], p["from"], p["frames"]
            common = (f'data-start="{t3(f0)}" data-duration="{t3(n)}" '
                      f'data-media-start="{s["start"]:.3f}"')
            cam.append(f'<video id="cam{k}" class="clip" src="assets/cam.mp4" {common} '
                       f'data-track-index="1" muted playsinline></video>')
            scr.append(f'<video id="scr{k}" class="clip" src="assets/screen.mp4" {common} '
                       f'data-track-index="2" muted playsinline></video>')
            vol = 0 if s.get("mute") else 1
            self.audio.append(f'<audio id="voice{k}" src="assets/voice_final.wav" {common} '
                              f'data-track-index="8" data-volume="{vol}" '
                              f'data-fade-in="0.03" data-fade-out="0.03"></audio>')
        return cam, scr

    # --- layout changes between "talk" and "screen"
    def layout(self):
        shots = sorted(self.edl["shots"] or [{"at": 0, "layout": "talk"}], key=lambda s: s["at"])
        frames = [0 if s["at"] <= 0 else self.tl.body_frame(s["at"]) for s in shots]
        first = shots[0]
        js = self.js
        side = CIRCLE["d"] / CAM["w"]
        # The square kept for the bubble is centred on the face (FACE_Y of the window height).
        top = min(max(round(CAM["h"] * FACE_Y - CAM["w"] / 2), 0), CAM["h"] - CAM["w"])
        circle = {"x": CIRCLE["x"] - CAM["x"], "y": round(CIRCLE["y"] - CAM["y"] - top * side), "scale": side,
                  "clipPath": f"inset({top}px 0px {CAM['h'] - CAM['w'] - top}px 0px round {CAM['w'] / 2}px)"}
        card = {"x": 0, "y": 0, "scale": 1, "clipPath": f"inset(0px 0px 0px 0px round {self.th['radius']}px)"}
        # clip-path tweens need the same shape on both ends: the card is an inset with a radius too.
        js.append(f'gsap.set("#camwin", {{transformOrigin: "0 0"}});')
        js.append(f'tl.set("#camwin", {json.dumps(circle if first["layout"] == "screen" else card)}, 0);')
        js.append(f'tl.set("#screenwin", {{opacity: {1 if first["layout"] == "screen" else 0}, scale: 1}}, 0);')
        js.append(f'tl.set(["#camchrome"], {{opacity: {0 if first["layout"] == "screen" else 1}}}, 0);')
        js.append(f'tl.set("#camring", {{opacity: {1 if first["layout"] == "screen" else 0}}}, 0);')
        prev = first
        for s, f in zip(shots, frames):
            t = f / FPS
            if s is first:
                self.zoom(s, t, instant=True)
                continue
            if s["layout"] != prev["layout"]:
                to_screen = s["layout"] == "screen"
                ease = '"power3.inOut"'
                js.append(f'tl.to("#camwin", {{...{json.dumps(circle if to_screen else card)}, duration: {MOVE}, ease: {ease}}}, {t:.3f});')
                js.append(f'tl.to("#camchrome", {{opacity: {0 if to_screen else 1}, duration: {MOVE / 2}}}, {t + (0 if to_screen else MOVE / 2):.3f});')
                js.append(f'tl.to("#camring", {{opacity: {1 if to_screen else 0}, duration: {MOVE / 2}}}, {t + (MOVE / 2 if to_screen else 0):.3f});')
                js.append(f'tl.fromTo("#screenwin", {{opacity: {0 if to_screen else 1}, scale: {0.94 if to_screen else 1}}}, '
                          f'{{opacity: {1 if to_screen else 0}, scale: {1 if to_screen else 0.94}, duration: {MOVE}, ease: {ease}}}, {t:.3f});')
                self.sfx(f - 4, "whoosh", 0.8)
            self.zoom(s, t + MOVE / 2, instant=False)
            prev = s

    def zoom(self, s, t, instant):
        z = s.get("zoom", 1) if s["layout"] == "screen" else 1
        fx, fy = s.get("focus", [0.5, 0.5])
        origin = f"{fx * 100:.1f}% {fy * 100:.1f}%"
        if instant:
            self.js.append(f'tl.set("#screenzoom", {{scale: {z}, transformOrigin: "{origin}"}}, 0);')
        else:
            self.js.append(f'tl.set("#screenzoom", {{transformOrigin: "{origin}"}}, {t:.3f});')
            self.js.append(f'tl.to("#screenzoom", {{scale: {z}, duration: 0.8, ease: "power2.inOut"}}, {t:.3f});')

    def layout_at(self, f):
        shots = sorted(self.edl["shots"] or [{"at": 0, "layout": "talk"}], key=lambda s: s["at"])
        cur = shots[0]["layout"]
        for s in shots:
            if (0 if s["at"] <= 0 else self.tl.body_frame(s["at"])) <= f:
                cur = s["layout"]
        return cur

    # --- small helpers for motion
    def enter(self, sel, t, y=36):
        self.js.append(f'tl.fromTo("{sel}", {{opacity: 0, y: {y}}}, {{opacity: 1, y: 0, duration: 0.4, ease: "power3.out"}}, {t:.3f});')

    def leave(self, sel, t):
        self.js.append(f'tl.to("{sel}", {{opacity: 0, duration: 0.25, ease: "power2.in"}}, {t - 0.25:.3f});')

    def wipe(self, sel, t, dur=0.45):
        # Arabic letters join, so they are wiped in from the right, not typed.
        self.js.append(f'tl.fromTo("{sel}", {{clipPath: "inset(-20% 0% -20% 100%)"}}, '
                       f'{{clipPath: "inset(-20% 0% -20% 0%)", duration: {dur}, ease: "power2.out"}}, {t:.3f});')

    def typed(self, text, sel_id, t, cps=34):
        """Latin text typed char by char: spans flipped visible on time."""
        spans = "".join(f'<span class="ch">{esc(c)}</span>' for c in text)
        for k in range(len(text)):
            self.js.append(f'tl.set("#{sel_id} .ch:nth-child({k + 1})", {{opacity: 1}}, {t + k / cps:.3f});')
        return spans

    def caret(self, sel, t0, t1):
        n = max(1, int((t1 - t0) / 0.5))
        self.js.append(f'tl.fromTo("{sel}", {{opacity: 1}}, {{opacity: 0, duration: 0.25, ease: "steps(1)", '
                       f'repeat: {n}, yoyo: true}}, {t0:.3f});')

    # --- graphics
    def stage(self):
        """Keywords and lists share the stage: one ends when the next one starts."""
        items = []
        for g in self.edl["gfx"]:
            if not g.get("on", True) or g["type"] not in ("keyword", "list"):
                continue
            starts = self.tl.frames(g["at"]) if g["type"] == "keyword" else [self.tl.body_frame(g["at"])]
            for f in starts:
                items.append((f, g))
        items.sort(key=lambda x: x[0])
        log = {}
        for k, (f0, g) in enumerate(items):
            own = round(g.get("dur", 4 if g["type"] == "list" else 2) * FPS)
            nxt = items[k + 1][0] if k + 1 < len(items) else None
            f1 = f0 + (own if nxt is None else min(own, max(nxt - f0, 6)))
            if g["type"] == "keyword":
                self.keyword(g, f0, f1)
                ch = self.chapter_of(f0)
                if any(p["from"] <= f0 < p["from"] + p["frames"] and p["seg"]["role"] != "hook" for p in self.tl.placed):
                    log.setdefault(ch, []).append((f1, g["text"]))
            else:
                self.listcard(g, f0, f1)
        self.session_log(log)

    def keyword(self, g, f0, f1):
        t0, t1 = f0 / FPS, f1 / FPS
        layout = self.layout_at(f0)
        sub = f'<div class="kw-sub"><span class="slash">//</span> {esc(g["sub"])}</div>' if g.get("sub") else ""
        icon = f'<div class="kw-icon">{esc(g["icon"])}</div>' if g.get("icon") and self.th["keywords"]["icons"] else ""
        if layout == "screen":
            inner = (f'<div class="chip"><span class="dollar">$</span>{icon}<span class="wipe">{esc(g["text"])}</span>'
                     f'{f"<span class=kw-chipsub>// {esc(g["sub"])}</span>" if g.get("sub") else ""}</div>')
            i = self.clip("kw-screen", f0, f1, inner, 4)
        else:
            inner = (f'{icon}<div class="kw-row"><span class="pfx">&gt;_</span><span class="wipe">{esc(g["text"])}</span>'
                     f'<span class="caret"></span></div><div class="kw-line"></div>{sub}')
            i = self.clip("kw-talk", f0, f1, inner, 4)
            self.js.append(f'tl.fromTo("#{i} .kw-line", {{scaleX: 0}}, {{scaleX: 1, duration: 0.5, ease: "power2.out"}}, {t0 + 0.25:.3f});')
            self.caret(f"#{i} .caret", t0 + 0.5, t1)
        self.enter(f"#{i} > *", t0)
        self.wipe(f"#{i} .wipe", t0 + 0.08)
        self.leave(f"#{i} > *", t1)
        for d in (3, 7, 11):
            self.sfx(f0 + d, "key", 0.5)

    def listcard(self, g, f0, f1):
        rows = []
        for k, it in enumerate(g["items"]):
            rows.append(f'<div class="li" id="{{id}}-{k}"><span class="sq"></span><span>{esc(it["text"])}</span></div>')
        inner = (f'<div class="list"><div class="list-title"><span class="pfx">&gt;</span> {esc(g["title"])}</div>'
                 + "".join(rows) + "</div>")
        i = self.uid("lst")
        inner = inner.replace("{id}", i)
        self.html.append(f'<div id="{i}" class="clip kw-talk" data-start="{t3(f0)}" data-duration="{t3(f1 - f0)}" '
                         f'data-track-index="4">{inner}</div>')
        self.enter(f"#{i} .list-title", f0 / FPS)
        for k, it in enumerate(g["items"]):
            ft = max(self.tl.body_frame(it["at"]), f0)
            self.js.append(f'tl.fromTo("#{i}-{k}", {{opacity: 0, x: -30}}, {{opacity: 1, x: 0, duration: 0.35, ease: "power3.out"}}, {ft / FPS:.3f});')
            self.sfx(ft, "key", 0.4)
        self.leave(f"#{i} .list", f1 / FPS)

    def chapters(self):
        cs = sorted([g for g in self.edl["gfx"] if g["type"] == "chapter" and g.get("on", True)], key=lambda g: g["at"])
        self.chapter_frames = [(self.tl.body_frame(c["at"]), c) for c in cs]
        end = self.tl.outro[0] if self.tl.outro else self.tl.total
        th = self.th
        for k, (f0, c) in enumerate(self.chapter_frames):
            t0 = f0 / FPS
            big_end = f0 + round(1.5 * FPS)
            nid = self.uid("cmd")
            cmd = self.typed("git commit -m", nid, t0 + 0.05)
            inner = (f'<div class="dim"></div><div class="ch-big"><div class="ch-cmd" id="{nid}">'
                     f'<span class="dollar">$ </span>{cmd}</div><div class="ch-title"><span class="ch-num">{esc(c["num"])}</span>'
                     f'<span class="wipe">"{esc(c["title"])}"</span></div></div>')
            i = self.clip("chapter", f0, big_end, inner, 5)
            self.js.append(f'tl.fromTo("#{i} .dim", {{opacity: 0}}, {{opacity: 0.72, duration: 0.25}}, {t0:.3f});')
            self.js.append(f'tl.fromTo("#{i} .ch-big", {{opacity: 0, scale: 0.94}}, {{opacity: 1, scale: 1, duration: 0.4, ease: "power3.out"}}, {t0:.3f});')
            self.wipe(f"#{i} .wipe", t0 + 0.3)
            self.js.append(f'tl.to("#{i} > *", {{opacity: 0, duration: 0.3, ease: "power2.in"}}, {big_end / FPS - 0.3:.3f});')
            self.sfx(f0, "blip", 0.6)
            nxt = self.chapter_frames[k + 1][0] if k + 1 < len(self.chapter_frames) else end
            tag = (f'<span class="dot"></span><span>{esc(th["identity"]["path"])}/{esc(th["identity"]["series"])}</span>'
                   f'<span class="tag-num">{esc(c["num"])}</span><span class="tag-title">{esc(c["title"])}</span>')
            j = self.clip("ch-tag", big_end - 8, nxt, tag, 5)
            self.js.append(f'tl.fromTo("#{j}", {{opacity: 0, x: -20}}, {{opacity: 1, x: 0, duration: 0.35, ease: "power3.out"}}, {(big_end - 8) / FPS:.3f});')

    def chapter_of(self, f):
        cur = 0
        for cf, _ in getattr(self, "chapter_frames", []):
            if cf <= f:
                cur = cf
        return cur

    def session_log(self, log):
        """What was said in this chapter stays as quiet terminal history (talk layout only)."""
        ends = sorted([cf for cf, _ in self.chapter_frames] + [self.tl.outro[0] if self.tl.outro else self.tl.total])
        for ch, lines in log.items():
            stop = next((e for e in ends if e > ch), self.tl.total)
            for k, (f, text) in enumerate(lines[:6]):
                # Hide during screen shots: end the line at the next screen layout.
                f_end = stop
                for g in range(f, stop):
                    if self.layout_at(g) == "screen":
                        f_end = g
                        break
                if f_end - f < 10:
                    continue
                i = self.clip("log", f, f_end, f'<span>{esc(text)}</span><span class="tick">✓</span>', 6,
                              style=f"top:{100 + k * 38}px")
                self.js.append(f'tl.fromTo("#{i}", {{opacity: 0}}, {{opacity: 0.75, duration: 0.3}}, {f / FPS:.3f});')

    def lower_third(self):
        th = self.th["identity"]
        for g in self.edl["gfx"]:
            if g["type"] != "lower_third" or not g.get("on", True):
                continue
            f0 = self.tl.body_frame(g["at"]) + 48
            f1 = f0 + round(g.get("dur", 4) * FPS)
            nid = self.uid("who")
            inner = (f'<div class="lt-cmd" id="{nid}"><span class="accent">{esc(th["handle"])}</span>:~$ '
                     f'{self.typed("whoami", nid, f0 / FPS + 0.15, 16)}</div>'
                     f'<div class="lt-name">{esc(g.get("title") or th["name"])}</div>'
                     f'<div class="lt-role">{esc(g.get("sub") or th["role"])}</div>')
            i = self.clip("lower-third", f0, f1, inner, 6)
            self.js.append(f'tl.fromTo("#{i}", {{opacity: 0, y: 30}}, {{opacity: 1, y: 0, duration: 0.4, ease: "power3.out"}}, {f0 / FPS:.3f});')
            self.js.append(f'tl.fromTo("#{i} .lt-name, #{i} .lt-role", {{opacity: 0}}, {{opacity: 1, duration: 0.3, stagger: 0.15}}, {f0 / FPS + 0.45:.3f});')
            self.leave(f"#{i}", f1 / FPS)

    def prompt(self):
        for g in self.edl["gfx"]:
            if g["type"] != "prompt" or not g.get("on", True):
                continue
            f0, f1 = self.tl.body_frame(g["at"]), self.tl.body_frame(g["end"])
            ws = [w for w in self.words if g["at"] <= w["start"] < g["end"]]
            i = self.uid("prm")
            spans = "".join(f'<span class="pw" id="{i}w{k}">{esc(w["w"])} </span>' for k, w in enumerate(ws))
            inner = (f'<div class="win-bar"><i></i><i></i><i></i><span>{esc(g.get("label") or "prompt.txt")}</span></div>'
                     f'<div class="pr-body"><div class="pr-text">{spans}<span class="caret"></span></div></div>')
            self.html.append(f'<div id="{i}" class="clip promptcard" data-start="{t3(f0)}" data-duration="{t3(f1 - f0)}" '
                             f'data-track-index="4">{inner}</div>')
            self.enter(f"#{i}", f0 / FPS, 40)
            for k, w in enumerate(ws):
                ft = self.tl.body_frame(w["start"]) / FPS
                self.js.append(f'tl.set("#{i}w{k}", {{display: "inline", color: "var(--accent)"}}, {ft:.3f});')
                if k:
                    self.js.append(f'tl.set("#{i}w{k - 1}", {{color: "var(--text)"}}, {ft:.3f});')
                self.sfx(round(ft * FPS), "key", 0.35)
            self.caret(f"#{i} .caret", f0 / FPS, f1 / FPS)
            self.leave(f"#{i}", f1 / FPS)

    def captions(self):
        if not self.th["captions"]["show"]:
            return
        hidden = [(g["at"], g["end"]) for g in self.edl["gfx"] if g["type"] == "prompt" and g.get("on", True)]
        toks = []
        for w in self.words:
            if any(a <= w["start"] < b for a, b in hidden):
                continue
            for f0, f1 in self.tl.spans(w["start"], max(w["end"], w["start"] + 0.12)):
                toks.append((f0, f1, w["w"]))
        toks.sort()
        groups, gap, mx = [], round(0.35 * FPS), self.th["captions"]["maxWords"]
        for t in toks:
            g = groups[-1] if groups else None
            text = (" ".join(x[2] for x in g) + " " + t[2]) if g else ""
            if not g or len(g) >= mx or len(text) > 22 or t[0] - g[-1][1] > gap:
                groups.append([t])
            else:
                g.append(t)
        blocked = []
        if self.tl.sting:
            blocked.append((self.tl.sting[0], sum(self.tl.sting)))
        if self.tl.outro:
            blocked.append((self.tl.outro[0], self.tl.total))
        blocked += [(cf, cf + 46) for cf, _ in self.chapter_frames]
        for k, g in enumerate(groups):
            f0 = g[0][0]
            f1 = min(groups[k + 1][0][0], g[-1][1] + 12) if k + 1 < len(groups) else g[-1][1] + 12
            if any(a <= f0 < b for a, b in blocked):
                continue
            i = self.uid("cap")
            words = "".join(f'<span class="cw" id="{i}-{n}">{esc(x[2])}</span>{" " if n < len(g) - 1 else ""}'
                            for n, x in enumerate(g))
            self.html.append(f'<div id="{i}" class="clip cap" data-start="{t3(f0)}" data-duration="{t3(f1 - f0)}" '
                             f'data-track-index="7"><div class="cap-box">{words}</div></div>')
            self.js.append(f'tl.fromTo("#{i} .cap-box", {{opacity: 0, y: 10}}, {{opacity: 1, y: 0, duration: 0.12}}, {f0 / FPS:.3f});')
            for n, x in enumerate(g):
                self.js.append(f'tl.set("#{i}-{n}", {{color: "var(--accent)"}}, {x[0] / FPS:.3f});')
                self.js.append(f'tl.set("#{i}-{n}", {{color: "var(--text)"}}, {x[1] / FPS:.3f});')

    def sting(self):
        if not self.tl.sting:
            return
        f0, n = self.tl.sting
        t0, th = f0 / FPS, self.th
        cid = self.uid("bld")
        cmd = self.typed(f"./build --series {th['identity']['series']}", cid, t0 + 0.05, 60)
        name = th["identity"]["name"].split()[0].lower()
        logo = f'<img class="st-logo" src="assets/logo.png" alt="">' if th["identity"].get("logo") else ""
        inner = (f'<div class="glow"></div><div class="st-term"><div id="{cid}"><span class="dollar">$ </span>{cmd}</div>'
                 f'<div class="bar"><i></i></div></div><div class="st-mark"><div class="st-name">'
                 f'<span class="accent">&lt;</span>{esc(name)}<span class="accent"> /&gt;</span></div>{logo}</div>')
        i = self.clip("sting", f0, f0 + n, inner, 5)
        self.js.append(f'tl.fromTo("#{i} .bar i", {{scaleX: 0}}, {{scaleX: 1, duration: 0.75, ease: "power2.out"}}, {t0 + 0.5:.3f});')
        self.js.append(f'tl.to("#{i} .st-term", {{opacity: 0, duration: 0.25}}, {t0 + 1.2:.3f});')
        self.js.append(f'tl.fromTo("#{i} .st-mark", {{opacity: 0, scale: 0.9}}, {{opacity: 1, scale: 1, duration: 0.5, ease: "power3.out"}}, {t0 + 1.25:.3f});')
        self.js.append(f'tl.to("#{i} > *", {{opacity: 0, duration: 0.25}}, {(f0 + n) / FPS - 0.25:.3f});')
        for d in range(2, 22, 3):
            self.sfx(f0 + d, "key", 0.4)
        self.sfx(f0 + 36, "whoosh")

    def outro(self):
        if not self.tl.outro:
            return
        g = next(x for x in self.edl["gfx"] if x["type"] == "outro")
        f0, n = self.tl.outro
        t0, th = f0 / FPS, self.th
        cid = self.uid("psh")
        cmd = self.typed("git push origin next-episode", cid, t0 + 0.1, 50)
        logo = f'<img class="out-logo" src="assets/logo.png" alt="">' if th["identity"].get("logo") else ""
        inner = (f'<div class="glow"></div><div class="out-cmd" id="{cid}"><span class="dollar">$ </span>{cmd}</div>'
                 f'<div class="out-title">{esc(g.get("title", ""))}</div><div class="out-sub">{esc(g.get("sub", ""))}</div>'
                 f'<div class="out-handle"><span>{esc(th["identity"]["handle"])}</span>{logo}</div>')
        i = self.clip("outro", f0, f0 + n, inner, 5)
        self.js.append(f'tl.fromTo("#{i}", {{opacity: 0}}, {{opacity: 1, duration: 0.35}}, {t0:.3f});')
        self.js.append(f'tl.fromTo("#{i} .out-title, #{i} .out-sub, #{i} .out-handle", {{opacity: 0, y: 30}}, '
                       f'{{opacity: 1, y: 0, duration: 0.45, stagger: 0.25, ease: "power3.out"}}, {t0 + 0.9:.3f});')
        self.sfx(f0, "whoosh")

    def background(self):
        js = self.js
        js.append(f'tl.fromTo("#grid", {{backgroundPosition: "0px 0px"}}, {{backgroundPosition: "{self.tl.total / FPS * 7.5:.0f}px '
                  f'{self.tl.total / FPS * 3.6:.0f}px", duration: {self.tl.total / FPS:.3f}, ease: "none"}}, 0);')


# HyperFrames resolves these by name; any other family needs @font-face to a file.
BUNDLED = {"Inter", "Montserrat", "Outfit", "Nunito", "Oswald", "League Gothic", "Archivo Black", "Space Mono",
           "IBM Plex Mono", "JetBrains Mono", "EB Garamond", "Playfair Display", "Source Code Pro", "Noto Sans JP",
           "Roboto", "Open Sans", "Lato", "Poppins"}
WEIGHTS = {"Medium": 500, "Bold": 700, "ExtraBold": 800}


def font_faces(th):
    """@font-face for every non-bundled theme font, from montage/assets/fonts/<Name>-<Weight>.ttf."""
    out = []
    for family in dict.fromkeys(th["fonts"].values()):
        if family in BUNDLED:
            continue
        stem = family.replace(" ", "")
        files = [(w, ASSETS / "fonts" / f"{stem}-{w}.ttf") for w in WEIGHTS]
        files = [(w, f) for w, f in files if f.exists()]
        if not files:
            raise SystemExit(f"theme font '{family}' is not bundled with HyperFrames and has no file in "
                             f"montage/assets/fonts/{stem}-Medium.ttf / -Bold.ttf — add it or pick another font")
        out += [f'@font-face {{ font-family: "{family}"; src: url("assets/fonts/{f.name}"); font-weight: {WEIGHTS[w]}; }}'
                for w, f in files]
    return "\n".join(out)


def css(th):
    c, f = th["colors"], th["fonts"]
    ar = f["ar"]
    return font_faces(th) + f"""
:root {{
  --bg: {c['bg']}; --glow: {c['glow']}; --primary: {c['primary']}; --accent: {c['accent']};
  --text: {c['text']}; --muted: {c['muted']}; --card: {c['card']}; --line: {c['line']};
  --ar: "{ar}"; --mono: "{f['mono']}"; --radius: {th['radius']}px;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: var(--bg); }}
#root {{ position: relative; width: 100%; height: 100%; font-family: var(--ar); color: var(--text); }}
.clip {{ position: absolute; inset: 0; }}
.accent {{ color: var(--accent); }}
.dollar, .pfx, .slash {{ color: var(--accent); font-family: var(--mono); font-weight: 800; }}
.ch {{ opacity: 0; }}
#bg {{ background: radial-gradient(900px 620px at 10% 0%, color-mix(in srgb, var(--glow) 28%, transparent), transparent 70%),
       radial-gradient(700px 500px at 100% 100%, color-mix(in srgb, var(--accent) 6%, transparent), transparent 70%), var(--bg); }}
#grid {{ background-image: radial-gradient(color-mix(in srgb, var(--muted) 28%, transparent) 1.4px, transparent 1.6px);
         background-size: 44px 44px; mask-image: radial-gradient(ellipse 80% 70% at 50% 45%, black, transparent); }}
/* windows */
.win {{ position: absolute; overflow: hidden; border-radius: var(--radius); background: var(--card);
        box-shadow: 0 30px 90px #000a, 0 0 0 1.5px color-mix(in srgb, var(--primary) 55%, transparent); }}
.win-bar {{ position: absolute; top: 0; left: 0; right: 0; height: {CHROME}px; display: flex; align-items: center; gap: 10px;
            padding: 0 18px; background: var(--card); border-bottom: 1px solid var(--line); z-index: 2; direction: ltr; }}
.win-bar i {{ width: 13px; height: 13px; border-radius: 7px; background: #FF5F57; }}
.win-bar i:nth-child(2) {{ background: #FEBC2E; }} .win-bar i:nth-child(3) {{ background: #28C840; }}
.win-bar span {{ margin-left: 14px; font: 19px var(--mono); color: var(--muted); }}
#screenwin {{ left: {LENS['x']}px; top: {LENS['y']}px; width: {LENS['w']}px; height: {LENS['h']}px; background: #fff; }}
#screenview {{ position: absolute; top: {CHROME}px; left: 0; right: 0; bottom: 0; overflow: hidden; }}
#screenzoom {{ position: absolute; inset: 0; }}
#screenzoom video, #camwin video {{ width: 100%; height: 100%; object-fit: cover; }}
#camwin {{ left: {CAM['x']}px; top: {CAM['y']}px; width: {CAM['w']}px; height: {CAM['h']}px; }}
#camwin video {{ object-position: 50% 30%; }}
#camring {{ position: absolute; left: {CIRCLE['x'] - 5}px; top: {CIRCLE['y'] - 5}px; width: {CIRCLE['d'] + 10}px; height: {CIRCLE['d'] + 10}px;
            border-radius: 50%; border: 5px solid var(--accent); box-shadow: 0 24px 70px #0008; }}
/* keyword on the talk layout */
.kw-talk {{ display: flex; flex-direction: column; align-items: center; justify-content: center; right: auto;
            width: {CAM['x'] - 60}px; padding-bottom: 80px; }}
.kw-row {{ display: flex; align-items: center; gap: 26px; direction: rtl; }}
.kw-row .pfx {{ font-size: {th['keywords']['size'] * 0.62:.0f}px; }}
.kw-row .wipe {{ font-size: {th['keywords']['size']}px; font-weight: 700; white-space: nowrap; line-height: 1.2; }}
.caret {{ display: inline-block; width: 0.42em; height: 0.8em; background: var(--accent); vertical-align: middle; }}
.kw-row .caret {{ font-size: {th['keywords']['size']}px; }}
.kw-line {{ width: 560px; height: 6px; margin-top: 22px; background: linear-gradient(270deg, var(--primary), transparent); transform-origin: right; }}
.kw-sub {{ margin-top: 22px; font-size: 32px; color: var(--muted); direction: rtl; }}
.kw-icon {{ font-size: 110px; margin-bottom: 10px; }}
/* keyword over the screen */
.kw-screen {{ display: flex; justify-content: center; align-items: flex-start; padding-top: {LENS['y'] + 70}px; right: {W - LENS['x'] - LENS['w']}px; left: {LENS['x']}px; }}
.chip {{ display: flex; align-items: center; gap: 18px; direction: rtl; background: color-mix(in srgb, var(--bg) 92%, transparent);
         border: 1.5px solid color-mix(in srgb, var(--primary) 80%, transparent); border-radius: 14px; padding: 14px 30px; box-shadow: 0 20px 60px #0009; }}
.chip .dollar {{ font-size: 40px; }} .chip .wipe {{ font-size: 56px; font-weight: 700; }}
.kw-chipsub {{ font-size: 32px; color: var(--muted); }}
/* list */
.list {{ direction: rtl; min-width: 620px; }}
.list-title {{ font-size: 56px; font-weight: 700; color: var(--muted); margin-bottom: 26px; }}
.li {{ display: flex; align-items: center; gap: 24px; margin: 14px 0; font-size: 84px; font-weight: 700; opacity: 0; }}
.sq {{ width: 18px; height: 18px; border-radius: 4px; background: var(--primary); flex: none; }}
/* chapter */
.chapter .dim {{ position: absolute; inset: 0; background: var(--bg); }}
.ch-big {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.ch-cmd {{ font: 38px var(--mono); color: var(--muted); margin-bottom: 18px; direction: ltr; }}
.ch-title {{ display: flex; align-items: center; gap: 36px; direction: ltr; }}
.ch-num {{ font: 800 150px var(--mono); color: var(--accent); line-height: 1; }}
.ch-title .wipe {{ font-size: 124px; font-weight: 700; line-height: 1.15; }}
.ch-tag {{ inset: auto; left: 60px; top: 36px; height: 46px; display: flex; align-items: center; gap: 14px; direction: ltr;
           font: 22px var(--mono); color: var(--muted); background: color-mix(in srgb, var(--bg) 80%, transparent);
           border: 1px solid var(--line); border-radius: 10px; padding: 0 16px; }}
.ch-tag .dot {{ width: 10px; height: 10px; border-radius: 5px; background: var(--accent); }}
.tag-num {{ color: var(--accent); font-weight: 700; }} .tag-title {{ font: 700 24px var(--ar); color: var(--text); }}
.log {{ inset: auto; left: 60px; height: 34px; display: flex; gap: 10px; align-items: center; direction: rtl;
        font-size: 26px; color: var(--muted); }}
.log .tick {{ font-family: var(--mono); color: var(--accent); }}
/* lower third */
.lower-third {{ inset: auto; left: {CAM['x'] - 120}px; top: {CAM['y'] + CAM['h'] - 190}px; min-width: 440px; direction: ltr;
                background: color-mix(in srgb, var(--bg) 94%, transparent); border: 1.5px solid color-mix(in srgb, var(--primary) 80%, transparent);
                border-radius: 14px; padding: 16px 26px; box-shadow: 0 24px 60px #000a; font-family: var(--mono); }}
.lt-cmd {{ font-size: 22px; color: var(--muted); }} .lt-name {{ font-size: 44px; font-weight: 800; margin-top: 6px; }}
.lt-role {{ font-size: 21px; color: var(--primary); margin-top: 2px; }}
/* prompt card */
.promptcard {{ inset: auto; left: {LENS['x'] + 80}px; width: {LENS['w'] - 160}px; top: {LENS['y'] + LENS['h'] - 350}px; height: 310px;
           background: color-mix(in srgb, var(--bg) 96%, transparent); border: 1.5px solid color-mix(in srgb, var(--primary) 80%, transparent);
           border-radius: 16px; box-shadow: 0 30px 80px #000b; overflow: hidden; }}
.promptcard .win-bar {{ height: 40px; }}
.pr-body {{ position: absolute; top: 40px; left: 0; right: 0; bottom: 0; padding: 14px 34px 22px; display: flex; flex-direction: column;
            justify-content: flex-end; overflow: hidden; direction: rtl; mask-image: linear-gradient(to bottom, transparent 0, black 34%); }}
.pr-text {{ font-size: 48px; font-weight: 500; line-height: 1.5; }}
.pw {{ display: none; }}
/* captions */
.cap {{ top: auto; bottom: 50px; height: 100px; display: flex; justify-content: center; align-items: center; }}
.cap-box {{ direction: rtl; font-size: {th['captions']['size']}px; font-weight: 700; line-height: 1.35; padding: 4px 28px; border-radius: 14px;
            background: color-mix(in srgb, var(--bg) 86%, transparent); border: 1.5px solid color-mix(in srgb, var(--primary) 60%, transparent); }}
/* sting + outro */
.sting, .outro {{ background: var(--bg); display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.glow {{ position: absolute; inset: 0; background: radial-gradient(760px 500px at 50% 48%, color-mix(in srgb, var(--glow) 30%, transparent), transparent 70%); }}
.st-term {{ position: relative; width: 760px; font: 30px var(--mono); color: var(--muted); direction: ltr; }}
.bar {{ margin-top: 22px; height: 14px; border-radius: 7px; background: var(--line); overflow: hidden; }}
.bar i {{ display: block; height: 100%; background: var(--accent); transform-origin: left; }}
.st-mark {{ position: absolute; display: flex; flex-direction: column; align-items: center; opacity: 0; }}
.st-name {{ font: 800 96px var(--mono); direction: ltr; }}
.st-logo {{ height: 64px; margin-top: 18px; }}
.out-cmd {{ position: relative; font: 34px var(--mono); color: var(--muted); direction: ltr; margin-bottom: 46px; }}
.out-title {{ position: relative; font-size: 104px; font-weight: 700; color: var(--accent); }}
.out-sub {{ position: relative; font-size: 56px; font-weight: 500; margin-top: 14px; direction: rtl; }}
.out-handle {{ position: relative; display: flex; gap: 22px; align-items: center; margin-top: 64px; font: 30px var(--mono); color: var(--muted); }}
.out-logo {{ height: 44px; }}
"""


def link(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main():
    p = argparse.ArgumentParser(description="Montage Studio — stage 5 compose (edl.json → HyperFrames)")
    p.add_argument("--episode", required=True)
    p.add_argument("--force", action="store_true", help="regenerate even if index.html was edited in Studio")
    args = p.parse_args()
    ep = m.EPISODES / args.episode
    edit, hf = ep / "edit", ep / "hf"
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    words = json.loads((edit / "words.json").read_text(encoding="utf-8"))["words"]
    theme = json.loads((THEMES / f"{edl.get('theme', 'abanoub-terminal')}.json").read_text(encoding="utf-8"))
    index, stamp = hf / "index.html", hf / ".generated.json"

    if index.exists():
        made = json.loads(stamp.read_text()).get("sha1") if stamp.exists() else None
        now = hashlib.sha1(index.read_bytes()).hexdigest()
        if now != made and not args.force:
            raise SystemExit("hf/index.html was edited in Studio since it was generated — "
                             "re-run with --force to regenerate (it will be backed up)")
        if now != made:
            shutil.copy2(index, hf / f"index.{time.strftime('%Y%m%d-%H%M%S')}.html")

    if not (edit / "voice_final.wav").exists():
        m.run([sys.executable, Path(__file__).parent / "voice.py", "--episode", args.episode])
    for name in ("cam.mp4", "screen.mp4", "voice_final.wav"):
        link(edit / name, hf / "assets" / name)
    for f in (ASSETS / "fonts").glob("*.ttf"):
        link(f, hf / "assets" / "fonts" / f.name)
    for f in (ASSETS / "sfx").glob("*.wav"):
        link(f, hf / "assets" / "sfx" / f.name)
    logo = theme["identity"].get("logo")
    if logo:
        link(ASSETS / "logos" / logo, hf / "assets" / "logo.png")

    tl = Timeline(edl)
    film = Film(edl, words, theme, tl)
    cam, scr = film.media()
    film.chapters()
    film.layout()
    film.background()
    film.stage()
    film.lower_third()
    film.prompt()
    film.captions()
    film.sting()
    film.outro()
    mus = theme.get("music", {})
    if mus.get("on") and (ASSETS / "music" / mus["file"]).exists():
        link(ASSETS / "music" / mus["file"], hf / "assets" / "music" / mus["file"])
        film.audio.append(f'<audio id="music" src="assets/music/{esc(mus["file"])}" data-start="0" '
                          f'data-duration="{t3(tl.total)}" data-track-index="10" data-volume="{mus["volume"]:.2f}" '
                          f'data-fade-in="1" data-fade-out="2"></audio>')
    shot_title = next((s.get("title") for s in edl["shots"] if s["layout"] == "screen" and s.get("title")), "screen.rec")
    total = tl.total / FPS

    page = f"""<!doctype html>
<html lang="ar">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<!-- Generated by montage/pipeline/compose.py from edit/edl.json. Edit freely in Studio;
     re-composing needs --force and backs this file up first. -->
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css(theme)}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total:.3f}" data-width="{W}" data-height="{H}">
<div id="bg" class="clip" data-start="0" data-duration="{total:.3f}" data-track-index="0"></div>
<div id="grid" class="clip" data-start="0" data-duration="{total:.3f}" data-track-index="0"></div>
<div id="screenwin" class="win">
  <div class="win-bar"><i></i><i></i><i></i><span>{esc(shot_title)}</span></div>
  <div id="screenview"><div id="screenzoom">
{chr(10).join(scr)}
  </div></div>
</div>
<div id="camring"></div>
<div id="camwin" class="win">
  <div id="camchrome" class="win-bar"><i></i><i></i><i></i><span>live.cam</span></div>
{chr(10).join(cam)}
</div>
{chr(10).join(film.html)}
{chr(10).join(film.audio)}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(film.js)}
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
tl.seek(0);
</script>
</body>
</html>
"""
    hf.mkdir(parents=True, exist_ok=True)
    index.write_text(page, encoding="utf-8")
    stamp.write_text(json.dumps({"sha1": hashlib.sha1(page.encode()).hexdigest(), "episode": args.episode}))
    (hf / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": True}}, indent=2) + "\n")
    meta = hf / "meta.json"
    if not meta.exists():
        meta.write_text(json.dumps({"id": args.episode, "name": args.episode}, indent=2) + "\n")
    (hf / "package.json").write_text(json.dumps({
        "name": args.episode.lower(), "private": True, "type": "module",
        "scripts": {k: f"npx --yes hyperframes@{HF_VERSION} {v}" for k, v in
                    {"dev": "preview", "check": "check", "render": "render"}.items()}}, indent=2) + "\n")
    print(f"{len(tl.placed)} segments, {len(film.html)} graphic clips, {len(film.audio)} audio clips, "
          f"{total:.1f}s -> {index}")


if __name__ == "__main__":
    main()
