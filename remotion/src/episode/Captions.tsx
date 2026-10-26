// Kinetic captions: 2–3 words at a time, the word being said lights up in the accent.
import React from 'react';
import {useCurrentFrame} from 'remotion';
import {FPS} from './tokens';
import {Timeline, Word} from './timeline';
import {alpha, font, useTheme} from './theme';

type Tok = {w: string; from: number; to: number};
export type Chunk = {toks: Tok[]; from: number; to: number};

const MAX_CHARS = 22;
const GAP = Math.round(0.35 * FPS);

export function buildCaptions(words: Word[], tl: Timeline, hidden: [number, number][], maxWords: number): Chunk[] {
  const toks: Tok[] = [];
  for (const w of words) {
    if (hidden.some(([a, b]) => w.start >= a && w.start < b)) continue;
    for (const s of tl.spans(w.start, Math.max(w.end, w.start + 0.12))) toks.push({w: w.w, from: s.from, to: s.to});
  }
  toks.sort((a, b) => a.from - b.from);
  const chunks: Chunk[] = [];
  for (const t of toks) {
    const c = chunks[chunks.length - 1];
    const text = c ? c.toks.map((x) => x.w).join(' ') + ' ' + t.w : '';
    if (!c || c.toks.length >= maxWords || text.length > MAX_CHARS || t.from - c.to > GAP) {
      chunks.push({toks: [t], from: t.from, to: t.to});
    } else {
      c.toks.push(t);
      c.to = t.to;
    }
  }
  // Hold each chunk until the next one (or 0.4 s), so captions don't flicker off between words.
  chunks.forEach((c, i) => {
    const next = chunks[i + 1];
    c.to = next ? Math.min(next.from, c.to + Math.round(0.4 * FPS)) : c.to + Math.round(0.4 * FPS);
  });
  return chunks;
}

export const Captions: React.FC<{chunks: Chunk[]; blocked: (f: number) => boolean}> = ({chunks, blocked}) => {
  const t = useTheme();
  const c = t.colors;
  const f = useCurrentFrame();
  if (!t.captions.show || blocked(f)) return null;
  const ch = chunks.find((x) => x.from <= f && f < x.to);
  if (!ch) return null;
  const pop = Math.min(1, (f - ch.from + 1) / 4);
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom: 50, display: 'flex', justifyContent: 'center'}}>
      <div
        style={{
          direction: 'rtl', fontFamily: font(t, 'ar'), fontWeight: 700, fontSize: t.captions.size, lineHeight: 1.35,
          background: alpha(c.bg, 0.86), border: `1.5px solid ${alpha(c.primary, 0.6)}`, borderRadius: 14, padding: '4px 28px',
          transform: `translateY(${(1 - pop) * 10}px)`, opacity: pop,
        }}
      >
        {ch.toks.map((tk, i) => (
          <span key={i} style={{color: f >= tk.from && f < tk.to ? c.accent : c.text}}>
            {tk.w}
            {i < ch.toks.length - 1 ? ' ' : ''}
          </span>
        ))}
      </div>
    </div>
  );
};
