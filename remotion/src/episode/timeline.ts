// Maps the master timeline (edl.json, source seconds) onto the edit timeline (frames).
// Order of the edit: hook → sting → body → outro. Segments are compiled HERE from
// hook/cuts/speed (same rules as montage/pipeline/roughcut.py), so the dashboard
// preview and the render can never disagree.
import {FPS} from './tokens';

export type Segment = {start: number; end: number; rate: number; mute: boolean; role: 'hook' | 'body' | 'speed'};
export type Word = {i: number; w: string; start: number; end: number};
export type Range = {id: string; start: number; end: number; on?: boolean; kind?: string; reason?: string; by?: string};
export type Speed = Range & {rate: number; voice?: 'mute' | 'keep'};
export type Gfx = {id: string; type: string; at?: number; dur?: number; end?: number; [k: string]: any};
export type Shot = {at: number; layout: 'talk' | 'screen'; zoom?: number; focus?: [number, number]};
export type AudioParams = {highpass_hz?: number; breath_duck_db?: number; speech_db?: number; hold_ms?: number};
export type Edl = {
  theme?: string;
  duration_s: number;
  hook: Range[];
  cuts: Range[];
  speed: Speed[];
  gfx: Gfx[];
  shots: Shot[];
  audio?: AudioParams;
};

const isOn = (x: {on?: boolean}) => x.on !== false;

export function compileSegments(edl: Edl): Segment[] {
  const holes = edl.cuts.filter(isOn).map((c) => [c.start, c.end]).sort((a, b) => a[0] - b[0]);
  const speeds = edl.speed.filter(isOn);
  const segs: Segment[] = edl.hook.filter(isOn).map((h) => ({start: h.start, end: h.end, rate: 1, mute: false, role: 'hook'}));
  const spans: [number, number][] = [];
  let cur = 0;
  for (const [a, b] of holes) {
    if (b <= cur) continue;
    if (a > cur) spans.push([cur, a]);
    cur = Math.max(cur, b);
  }
  if (cur < edl.duration_s) spans.push([cur, edl.duration_s]);
  for (const [a, b] of spans.filter(([a, b]) => b - a > 0.04)) {
    const edges = [...new Set([a, b, ...speeds.flatMap((s) => [s.start, s.end]).filter((x) => x > a && x < b)])].sort((p, q) => p - q);
    for (let i = 0; i < edges.length - 1; i++) {
      const sp = speeds.find((s) => s.start <= edges[i] && edges[i + 1] <= s.end);
      segs.push({start: edges[i], end: edges[i + 1], rate: sp ? sp.rate : 1, mute: !!(sp && sp.voice === 'mute'), role: sp ? 'speed' : 'body'});
    }
  }
  return segs;
}

export type Placed = {seg: Segment; from: number; frames: number};

export type Timeline = {
  placed: Placed[];
  sting: {from: number; frames: number} | null;
  outro: {from: number; frames: number} | null;
  total: number;
  /** First edit frame showing source time t in the BODY (cut time → next kept frame). */
  bodyFrame: (t: number) => number;
  /** Every edit frame where source time t is visible (hook and body). */
  frames: (t: number) => number[];
  /** Edit-frame spans [from, to) where the source span [a, b) is visible. */
  spans: (a: number, b: number) => {from: number; to: number; role: Segment['role']}[];
  /** Source time shown at edit frame f (null in sting/outro). */
  sourceAt: (f: number) => number | null;
};

export function buildTimeline(edl: Edl): Timeline {
  const sec = (s: number) => Math.round(s * FPS);
  const segments = compileSegments(edl);
  const stingG = edl.gfx.find((g) => g.type === 'sting' && g.on !== false);
  const outroG = edl.gfx.find((g) => g.type === 'outro' && g.on !== false);
  const placed: Placed[] = [];
  let cursor = 0; // edit seconds
  let sting: Timeline['sting'] = null;
  const hooks = segments.filter((s) => s.role === 'hook');
  const body = segments.filter((s) => s.role !== 'hook');
  const put = (seg: Segment) => {
    const from = sec(cursor);
    cursor += (seg.end - seg.start) / seg.rate;
    placed.push({seg, from, frames: sec(cursor) - from});
  };
  hooks.forEach(put);
  if (stingG && hooks.length) {
    sting = {from: sec(cursor), frames: sec(stingG.dur ?? 2)};
    cursor += stingG.dur ?? 2;
  }
  body.forEach(put);
  const outro = outroG ? {from: sec(cursor), frames: sec(outroG.dur ?? 4)} : null;
  if (outroG) cursor += outroG.dur ?? 4;

  const at = (p: Placed, t: number) => p.from + Math.round(((t - p.seg.start) / p.seg.rate) * FPS);
  const bodyPlaced = placed.filter((p) => p.seg.role !== 'hook');
  return {
    placed,
    sting,
    outro,
    total: Math.max(sec(cursor), 1),
    bodyFrame: (t) => {
      const p = bodyPlaced.find((q) => t < q.seg.end);
      if (!p) return outro ? outro.from : sec(cursor);
      return t <= p.seg.start ? p.from : at(p, t);
    },
    frames: (t) => placed.filter((p) => p.seg.start <= t && t < p.seg.end).map((p) => at(p, t)),
    spans: (a, b) =>
      placed
        .filter((p) => p.seg.start < b && a < p.seg.end)
        .map((p) => ({
          from: at(p, Math.max(a, p.seg.start)),
          to: Math.min(at(p, Math.min(b, p.seg.end)), p.from + p.frames),
          role: p.seg.role,
        }))
        .filter((s) => s.to > s.from),
    sourceAt: (f) => {
      const p = placed.find((q) => f >= q.from && f < q.from + q.frames);
      return p ? p.seg.start + ((f - p.from) / FPS) * p.seg.rate : null;
    },
  };
}
