#!/usr/bin/env python3
"""Montage Studio pipeline — phone video + PodMic audio -> finished podcast edit.

Steps:
  1. probe     read both inputs (resolution, fps, HDR, duration)
  2. mic       pick the live channel of the Scarlett recording (mic sits on ch 2)
  3. sync      find the offset between the phone's own audio and the mic audio
  4. clean     voice chain: highpass -> denoise -> compressor -> de-esser -> -16 LUFS
  5. jumpcut   (optional) remove long silences
  6. render    one pass, two outputs: 16:9 YouTube + 9:16 Reel
  7. extras    Arabic subtitles (.srt, needs a Whisper model) + thumbnail candidates

Usage:
  python3 montage/montage.py --video phone.mov --audio mic.wav --name "episode-1"
  python3 montage/montage.py --video phone.mov --audio mic.wav --name ep1 --jumpcut
  python3 montage/montage.py --video phone.mov --audio mic.wav --screen obs.mp4 --name ep1
Only needs ffmpeg + numpy. Everything lands in montage/episodes/<date>-<name>/.
"""

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
EPISODES = ROOT / "episodes"
MODELS = ROOT / "models"

SYNC_SR = 8000          # sample rate used for the cross-correlation
SYNC_WINDOW_S = 180     # how much of each file to compare
TARGET_LUFS = -16       # podcast / YouTube loudness standard
TARGET_TP = -1.5


# ---------------------------------------------------------------- helpers

def run(cmd, capture=False, cwd=None):
    print("  $", " ".join(str(c) for c in cmd[:6]), "..." if len(cmd) > 6 else "")
    res = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)
    if res.returncode != 0:
        sys.stderr.write(res.stderr[-3000:])
        raise SystemExit(f"command failed: {cmd[0]}")
    return res.stderr if capture else res.stdout


def probe(path):
    out = run(["ffprobe", "-v", "error", "-print_format", "json",
               "-show_streams", "-show_format", path])
    return json.loads(out)


def decode_mono(path, sr, seconds=None, channel=None, start=0.0):
    """Decode audio to a float32 numpy array (mono, given sample rate)."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", path]
    if seconds:
        cmd += ["-t", str(seconds)]
    if channel is not None:
        cmd += ["-af", f"pan=mono|c0=c{channel}"]
    cmd += ["-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12)


# ---------------------------------------------------------------- steps

def inspect_video(path):
    info = probe(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = v.get("avg_frame_rate", "30/1").split("/")
    rotation = 0
    for sd in v.get("side_data_list", []):
        rotation = int(sd.get("rotation", rotation) or 0)
    w, h = int(v["width"]), int(v["height"])
    coded = (w, h)
    if abs(rotation) in (90, 270):
        w, h = h, w
    return {
        "width": w, "height": h, "coded": coded, "rotation": rotation,
        "fps": float(num) / float(den or 1),
        "duration": float(info["format"]["duration"]),
        "hdr": v.get("color_transfer") in ("arib-std-b67", "smpte2084"),
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
    }


def pick_mic_channel(path):
    """Scarlett Solo records 2 channels; the PodMic is on whichever one is alive."""
    info = probe(path)
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    n = int(a.get("channels", 1))
    if n == 1:
        return 0, [rms_db(decode_mono(path, SYNC_SR, 60))]
    levels = [rms_db(decode_mono(path, SYNC_SR, 60, channel=c)) for c in range(n)]
    return int(np.argmax(levels)), levels


def find_offset(video, audio, mic_channel):
    """Seconds the video is AHEAD of the mic: t_video = t_mic + offset."""
    v = decode_mono(video, SYNC_SR, SYNC_WINDOW_S)
    a = decode_mono(audio, SYNC_SR, SYNC_WINDOW_S, channel=mic_channel)
    if len(v) == 0 or len(a) == 0:
        raise SystemExit("could not decode audio for sync")
    # Compare loudness envelopes, not raw waves: the phone mic and the PodMic
    # colour the voice very differently, but the rhythm of speech is identical.
    def envelope(x):
        hop = SYNC_SR // 200                        # 5 ms resolution
        x = np.abs(x[: len(x) // hop * hop]).reshape(-1, hop).mean(axis=1)
        x = np.log1p(x * 1000)
        return (x - x.mean()) / (x.std() + 1e-9)
    ev, ea = envelope(v), envelope(a)
    n = 1 << int(np.ceil(np.log2(len(ev) + len(ea))))
    corr = np.fft.irfft(np.fft.rfft(ev, n) * np.conj(np.fft.rfft(ea, n)), n)
    k = int(np.argmax(corr))
    lag = k if k < n // 2 else k - n
    # Confidence: best peak vs the best peak more than 0.5 s away from it.
    others = corr.copy()
    idx = (np.arange(n) - k) % n
    others[(idx < 100) | (idx > n - 100)] = -np.inf
    peak_ratio = float(corr[k] / (others.max() + 1e-9))
    return lag / 200.0, peak_ratio


def speech_level_db(audio, channel):
    """Loud-speech level of the mic: 95th percentile of 100 ms RMS frames."""
    x = decode_mono(audio, SYNC_SR, channel=channel)
    hop = SYNC_SR // 10
    frames = x[: len(x) // hop * hop].reshape(-1, hop).astype(np.float64)
    return float(np.percentile(20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-12), 95))


def clean_audio(audio, channel, start, duration, out_wav, work):
    """Voice chain + two-pass EBU R128 loudness normalisation."""
    # The gate/denoise thresholds below assume speech peaking near -20 dBFS. A quiet
    # Scarlett gain (speech at -45) put the voice under them and the chain ate it.
    pregain = min(max(-20 - speech_level_db(audio, channel), 0.0), 30.0)
    chain = ",".join([
        f"pan=mono|c0=c{channel}",
        f"volume={pregain:.1f}dB",
        "highpass=f=80",                              # rumble, desk knocks
        "afftdn=nr=12:nf=-40:tn=1",                   # steady room noise (AC, fans)
        "agate=threshold=0.008:ratio=2:attack=10:release=250",
        "acompressor=threshold=-21dB:ratio=3:attack=8:release=120:makeup=3",
        "deesser=i=0.4",
        "equalizer=f=3500:t=q:w=1.2:g=2",             # presence
    ])
    tmp = work / "voice_pre.wav"
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
         "-i", audio, "-af", chain, "-ar", "48000", tmp])
    stats = run(["ffmpeg", "-hide_banner", "-i", tmp, "-af",
                 f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=7:print_format=json",
                 "-f", "null", "-"], capture=True)
    m = json.loads(stats[stats.rindex("{"): stats.rindex("}") + 1])
    run(["ffmpeg", "-y", "-v", "error", "-i", tmp, "-af",
         f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=7:"
         f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
         f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
         f"offset={m['target_offset']}:linear=true",
         "-ar", "48000", out_wav])
    tmp.unlink()
    return float(m["input_i"])


def speech_segments(wav, min_silence, pad):
    """Keep-list of (start, end) after removing silences longer than min_silence."""
    log = run(["ffmpeg", "-hide_banner", "-i", wav, "-af",
               f"silencedetect=noise=-38dB:d={min_silence}", "-f", "null", "-"], capture=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    total = float(probe(wav)["format"]["duration"])
    keep, cur = [], 0.0
    for s, e in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if s + pad > cur:
            keep.append((cur, min(s + pad, total)))
        cur = max(cur, e - pad)
    if cur < total:
        keep.append((cur, total))
    return [(a, b) for a, b in keep if b - a > 0.25]


def build_filters(vinfo, keep, args):
    look = "eq=contrast=1.05:saturation=1.10:gamma=0.98,unsharp=5:5:0.35:5:5:0"
    pre = []
    if vinfo["hdr"]:
        # iPhone HDR (HLG/Dolby Vision) -> SDR via VideoToolbox; avoids the washed-out look.
        # scale_vt needs explicit (coded) dimensions and hands back 10-bit p010le frames.
        cw, ch = vinfo["coded"]
        pre.append(f"scale_vt=w={cw}:h={ch}:color_matrix=bt709:color_primaries=bt709:"
                   "color_transfer=bt709,hwdownload,format=p010le,format=yuv420p")
        # Hardware frames skip ffmpeg's autorotate, so apply the phone's rotation by hand
        # (same mapping fftools uses: display rotation r -> turn the picture by -r).
        turn = {90: "transpose=clock", 270: "transpose=cclock", 180: "hflip,vflip"}
        rot = (-vinfo["rotation"]) % 360
        if rot in turn:
            pre.append(turn[rot])
    if keep:
        expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keep)
        vsel = f"select='{expr}',setpts=N/FRAME_RATE/TB"
        asel = f"aselect='{expr}',asetpts=N/SR/TB"
    else:
        vsel, asel = "null", "anull"
    height = 2160 if args.k4 and vinfo["height"] >= 2160 else 1080
    landscape = vinfo["width"] >= vinfo["height"]
    if landscape:
        wide = f"scale=-2:{height}:flags=lanczos"
        tall = "crop=ih*9/16:ih,scale=1080:1920:flags=lanczos"
    else:  # filmed vertically: reel is native, YouTube gets a blurred-fill 16:9
        tall = "scale=1080:1920:flags=lanczos"
        wide = ("split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,"
                "crop=1920:1080,boxblur=30:3[bg];[b]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0")
    fps = "fps=%g" % round(vinfo["fps"], 3)
    if args.screen:
        # Screen + camera. YouTube: the screen full-frame with the camera as a
        # picture-in-picture bottom-right. Reel: screen on top, camera filling the
        # rest. Faces sit in the upper part of a frame, so crops lean up (y * 0.35).
        cam = ",".join(pre + [fps, "setpts=PTS-STARTPTS", look])
        pip = ("crop=w='min(iw,ih*3/4)':h='min(ih,iw*4/3)':x='(iw-ow)/2':y='(ih-oh)*0.35',"
               "scale=-2:480:flags=lanczos,pad=iw+8:ih+8:4:4:color=white")
        below = ("crop=w='min(iw,ih*1080/1312)':h='min(ih,iw*1312/1080)':x='(iw-ow)/2':"
                 "y='(ih-oh)*0.35',scale=1080:1312:flags=lanczos")
        # --camera-first S: the camera alone fills both frames for the first S seconds
        # (e.g. while OBS still shows the setup window), then the screen layout takes over.
        # S is in final-video time; the overlay runs before the jumpcut, so map it back.
        first = args.camera_first or 0
        if first and keep:
            left = first
            for a, b in keep:
                if left <= b - a:
                    first = a + left
                    break
                left -= b - a
        solo_wide = ("scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
                     if landscape else wide)
        graph = (
            f"[0:v]{cam},split={4 if first else 2}[c1][c2]{'[c3][c4]' if first else ''};"
            f"[2:v]{fps},setpts=PTS-STARTPTS,split=2[s1][s2];"
            "[s1]scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x111111[sw];"
            f"[c1]{pip}[pip];[sw][pip]overlay=W-w-40:H-h-40:shortest=1[w0];"
            "[s2]scale=1080:608:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=1080:608:(ow-iw)/2:(oh-ih)/2:color=0x111111[st];"
            f"[c2]{below}[cb];[st][cb]vstack=shortest=1[t0];")
        if first:
            graph += (f"[c3]{solo_wide}[wc];[w0][wc]overlay=0:0:enable='lt(t,{first})'[w1];"
                      f"[c4]{tall}[tc];[t0][tc]overlay=0:0:enable='lt(t,{first})'[t1];")
            w, t = "[w1]", "[t1]"
        else:
            w, t = "[w0]", "[t0]"
        graph += (f"{w}{vsel},format=yuv420p[wide];{t}{vsel},format=yuv420p[tall];"
                  f"[1:a]{asel},asplit=2[a1][a2]")
        return graph, 1080
    v = ",".join(pre + [vsel, look, fps, "split=2[v1][v2]"])
    graph = (f"[0:v]{v};[v1]{wide},format=yuv420p[wide];[v2]{tall},format=yuv420p[tall];"
             f"[1:a]{asel},asplit=2[a1][a2]")
    return graph, height


def render(video, clean_wav, start, duration, vinfo, keep, out_dir, args, screen_start=None):
    graph, height = build_filters(vinfo, keep, args)
    bitrate = "40M" if height == 2160 else "14M"
    hw = (["-noautorotate", "-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
          if vinfo["hdr"] else [])
    enc = ["-c:v", "h264_videotoolbox", "-profile:v", "high", "-allow_sw", "1"]
    aenc = ["-c:a", "aac", "-b:a", "256k", "-ar", "48000"]
    screen = (["-ss", f"{screen_start:.3f}", "-t", f"{duration:.3f}", "-i", args.screen]
              if args.screen else [])
    run(["ffmpeg", "-y", "-v", "error", "-stats", *hw,
         "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", video, "-i", clean_wav, *screen,
         "-filter_complex", graph,
         "-map", "[wide]", "-map", "[a1]", *enc, "-b:v", bitrate, "-maxrate", bitrate,
         *aenc, "-movflags", "+faststart", out_dir / "youtube.mp4",
         "-map", "[tall]", "-map", "[a2]", *enc, "-b:v", "16M", *aenc,
         "-movflags", "+faststart", out_dir / "reel.mp4"])


def subtitles(out_dir):
    models = sorted(MODELS.glob("ggml-*.bin"), key=lambda p: p.stat().st_size, reverse=True)
    if not models or not shutil.which("whisper-cli"):
        print("  ! no Whisper model in montage/models/ — skipping subtitles")
        return None
    wav16 = out_dir / ".speech16k.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", out_dir / "youtube.mp4", "-vn",
         "-ac", "1", "-ar", "16000", wav16])
    # No --max-len: whisper's own sentence segments read far better in Arabic than a
    # character cut (which strands single words on their own line). A --prompt with
    # product vocabulary was tried and made the turbo model return nothing — don't add one.
    run(["whisper-cli", "-m", models[0], "-l", "ar", "-f", wav16,
         "-osrt", "-of", out_dir / "subtitles"])
    wav16.unlink()
    srt = out_dir / "subtitles.srt"
    srt.write_text(tidy_srt(srt.read_text(encoding="utf-8")), encoding="utf-8")
    return srt


def tidy_srt(text, max_chars=55):
    """Trim whitespace and split over-long lines at word boundaries, timing by length."""
    def ts(s):
        h, m, rest = s.split(":")
        sec, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000

    def fmt(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        a, b = (ts(x.strip()) for x in lines[1].split("-->"))
        words = " ".join(lines[2:]).split()
        if not words:
            continue
        chunks, cur = [], []
        for w in words:
            if cur and len(" ".join(cur + [w])) > max_chars:
                chunks.append(cur)
                cur = []
            cur.append(w)
        chunks.append(cur)
        if len(chunks) > 1 and len(chunks[-1]) == 1:     # never leave one word alone
            chunks[-2].append(chunks.pop()[0])
        total = sum(len(" ".join(c)) for c in chunks)
        t = a
        for c in chunks:
            end = t + (b - a) * len(" ".join(c)) / total
            cues.append((t, end, " ".join(c)))
            t = end
    return "\n".join(f"{i}\n{fmt(a)} --> {fmt(b)}\n{s}\n" for i, (a, b, s) in enumerate(cues, 1))


def thumbnails(out_dir, duration):
    thumbs = out_dir / "thumbnails"
    thumbs.mkdir(exist_ok=True)
    for i, frac in enumerate((0.15, 0.35, 0.55, 0.75), 1):
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{duration * frac:.2f}",
             "-i", out_dir / "youtube.mp4", "-vf", "thumbnail=60", "-frames:v", "1",
             "-q:v", "2", thumbs / f"thumb-{i}.jpg"])


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="Montage Studio — sync, clean, quick edit")
    p.add_argument("--video", required=True, help="video from the phone")
    p.add_argument("--audio", required=True, help="PodMic recording exported from Audacity (wav/m4a)")
    p.add_argument("--name", required=True, help="episode name, used for the folder")
    p.add_argument("--jumpcut", action="store_true", help="remove silences longer than --min-silence")
    p.add_argument("--min-silence", type=float, default=0.8)
    p.add_argument("--offset", type=float, help="force sync offset in seconds (skip auto-sync)")
    p.add_argument("--k4", action="store_true", help="keep 4K for YouTube (bigger files)")
    p.add_argument("--screen", help="OBS screen recording to merge with the camera")
    p.add_argument("--screen-offset", type=float, help="force screen sync offset in seconds")
    p.add_argument("--camera-first", type=float,
                   help="with --screen: show only the camera for the first N seconds")
    p.add_argument("--no-subs", action="store_true")
    args = p.parse_args()

    slug = re.sub(r"[^\w\-]+", "-", args.name, flags=re.UNICODE).strip("-")
    out_dir = EPISODES / f"{dt.date.today():%Y-%m-%d}-{slug}"
    work = out_dir / ".work"
    work.mkdir(parents=True, exist_ok=True)
    report = {"video": args.video, "audio": args.audio}

    print("1/7 probe")
    vinfo = inspect_video(args.video)
    adur = float(probe(args.audio)["format"]["duration"])
    report["video_info"] = vinfo
    print(f"    video {vinfo['width']}x{vinfo['height']} @ {vinfo['fps']:.2f}fps, "
          f"{vinfo['duration']:.1f}s, HDR={vinfo['hdr']} | audio {adur:.1f}s")

    print("2/7 mic channel")
    ch, levels = pick_mic_channel(args.audio)
    report["mic_channel"], report["channel_levels_db"] = ch, [round(x, 1) for x in levels]
    print(f"    using channel {ch + 1}  (levels dB: {', '.join(f'{x:.1f}' for x in levels)})")
    if max(levels) < -50:
        print("    ! mic is nearly silent — check the Scarlett gain / Audacity channels")

    print("3/7 sync")
    if args.offset is not None:
        offset, ratio = args.offset, None
    elif not vinfo["has_audio"]:
        raise SystemExit("phone video has no audio track — pass --offset manually")
    else:
        offset, ratio = find_offset(args.video, args.audio, ch)
    report["offset_s"], report["sync_peak_ratio"] = offset, ratio
    print(f"    offset {offset:+.3f}s" + (f"  (peak ratio {ratio:.2f})" if ratio else ""))
    if ratio is not None and ratio < 1.15:
        print("    ! weak sync match — clap once at the start of the next recording")
    # Work in mic time: every source is cut to the span they all cover.
    m0, m1 = max(0.0, -offset), min(adur, vinfo["duration"] - offset)
    screen_offset = None
    if args.screen:
        # OBS records the same Scarlett mic, so the screen syncs like the phone does.
        if args.screen_offset is not None:
            screen_offset, sratio = args.screen_offset, None
        else:
            screen_offset, sratio = find_offset(args.screen, args.audio, ch)
        sdur = float(probe(args.screen)["format"]["duration"])
        report["screen"] = {"path": args.screen, "offset_s": screen_offset, "sync_peak_ratio": sratio}
        print(f"    screen offset {screen_offset:+.3f}s" + (f"  (peak ratio {sratio:.2f})" if sratio else ""))
        if sratio is not None and sratio < 1.15:
            print("    ! weak screen sync match — check it, or pass --screen-offset")
        m0, m1 = max(m0, -screen_offset), min(m1, sdur - screen_offset)
    start = m0 + offset                            # video time where everything has content
    duration = m1 - m0
    if duration < 1:
        raise SystemExit("video and audio do not overlap — wrong files or wrong offset")
    report["overlap"] = [round(start, 3), round(start + duration, 3)]

    print("4/7 clean voice")
    clean_wav = work / "voice.wav"
    report["input_lufs"] = clean_audio(args.audio, ch, m0, duration, clean_wav, work)

    keep = None
    if args.jumpcut:
        print("5/7 jumpcut")
        keep = speech_segments(clean_wav, args.min_silence, pad=0.18)
        kept = sum(b - a for a, b in keep)
        report["jumpcut"] = {"segments": len(keep), "kept_s": round(kept, 1), "cut_s": round(duration - kept, 1)}
        print(f"    {len(keep)} segments, removed {duration - kept:.1f}s of silence")
    else:
        print("5/7 jumpcut (off)")

    print("6/7 render youtube.mp4 + reel.mp4")
    render(args.video, clean_wav, start, duration, vinfo, keep, out_dir, args,
           screen_start=None if screen_offset is None else m0 + screen_offset)

    print("7/7 subtitles + thumbnails")
    final_dur = float(probe(out_dir / "youtube.mp4")["format"]["duration"])
    if not args.no_subs:
        srt = subtitles(out_dir)
        report["subtitles"] = str(srt) if srt else None
    thumbnails(out_dir, final_dur)

    shutil.rmtree(work, ignore_errors=True)
    report["final_duration_s"] = round(final_dur, 2)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\ndone -> {out_dir}")


if __name__ == "__main__":
    main()
