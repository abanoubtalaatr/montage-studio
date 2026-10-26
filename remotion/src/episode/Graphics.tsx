// Motion graphics in the theme's "terminal builder" language: keywords type onto a
// prompt, chapters are commits, the prompt is a window, the sting is a build.
import React from 'react';
import {AbsoluteFill, Img, interpolate, spring, useCurrentFrame} from 'remotion';
import {ENTER, EXIT, FPS, LAYOUT, SPRING} from './tokens';
import {Gfx, Word} from './timeline';
import {alpha, font, useAsset, useTheme} from './theme';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

const enterExit = (f: number, len: number) => {
  const inn = spring({frame: f, fps: FPS, config: SPRING, durationInFrames: ENTER});
  const out = interpolate(f, [len - EXIT, len], [1, 0], clamp);
  return {inn, out, alive: f >= 0 && f < len};
};

/** Latin text typed character by character. */
const typed = (s: string, f: number, cps = 28) => s.slice(0, Math.max(0, Math.floor((f / FPS) * cps)));

/** Arabic can't be typed letter by letter (the letters join), so it is wiped in from the right. */
const Wipe: React.FC<{p: number; children: React.ReactNode}> = ({p, children}) => (
  <span style={{display: 'inline-block', clipPath: `inset(-20% 0 -20% ${(1 - p) * 100}%)`}}>{children}</span>
);

const Caret: React.FC<{h: number; on?: boolean}> = ({h, on = true}) => {
  const t = useTheme();
  const f = useCurrentFrame();
  const blink = Math.floor(f / 15) % 2 === 0;
  return <span style={{display: 'inline-block', width: h * 0.45, height: h, background: t.colors.accent, opacity: on && blink ? 1 : 0, verticalAlign: 'middle'}} />;
};

/** A spoken key phrase lands on screen: big prompt line in "talk", a command chip over the screen. */
export const Keyword: React.FC<{g: Gfx; from: number; len: number; layout: 'talk' | 'screen'}> = ({g, from, len, layout}) => {
  const t = useTheme();
  const c = t.colors;
  const f = useCurrentFrame() - from;
  const {inn, out, alive} = enterExit(f, len);
  if (!alive) return null;
  const wipe = interpolate(f, [3, 16], [0, 1], {...clamp, easing: (x) => 1 - Math.pow(1 - x, 3)});
  const line = interpolate(f, [8, 22], [0, 1], clamp);
  const icon = t.keywords.icons && g.icon;
  if (layout === 'screen') {
    const lens = LAYOUT.screen.screen;
    return (
      <div style={{position: 'absolute', top: lens.y + 70, left: lens.x, width: lens.w, display: 'flex', justifyContent: 'center', opacity: inn * out, transform: `translateY(${(1 - inn) * -24}px)`}}>
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 18, direction: 'rtl', background: alpha(c.bg, 0.92),
            border: `1.5px solid ${alpha(c.primary, 0.8)}`, borderRadius: 14, padding: '14px 30px', boxShadow: '0 20px 60px #0009',
          }}
        >
          <span style={{fontFamily: font(t, 'mono'), fontWeight: 700, fontSize: 40, color: c.accent}}>$</span>
          {icon && <span style={{fontSize: 46}}>{g.icon}</span>}
          <Wipe p={wipe}>
            <span style={{fontFamily: font(t, 'ar'), fontWeight: 700, fontSize: 56, color: c.text}}>{g.text}</span>
          </Wipe>
          {g.sub && <span style={{fontFamily: font(t, 'ar'), fontWeight: 500, fontSize: 34, color: c.muted}}>// {g.sub}</span>}
        </div>
      </div>
    );
  }
  const size = t.keywords.size;
  return (
    <div
      style={{
        position: 'absolute', left: 60, width: LAYOUT.talk.cam.x - 120, top: 0, height: 1080,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        opacity: inn * out, transform: `translateY(${(1 - inn) * 40 - (1 - out) * 16}px)`, paddingBottom: 80,
      }}
    >
      {icon && <div style={{fontSize: size * 1.05, marginBottom: 10}}>{g.icon}</div>}
      <div style={{display: 'flex', alignItems: 'center', gap: 26, direction: 'rtl'}}>
        <span style={{fontFamily: font(t, 'mono'), fontWeight: 800, fontSize: size * 0.62, color: c.accent}}>{'>_'}</span>
        <Wipe p={wipe}>
          <span style={{fontFamily: font(t, 'ar'), fontWeight: 700, fontSize: size, color: c.text, lineHeight: 1.2, whiteSpace: 'nowrap'}}>{g.text}</span>
        </Wipe>
        <Caret h={size * 0.8} on={wipe > 0.98} />
      </div>
      <div style={{height: 6, width: 560, marginTop: 22, background: `linear-gradient(270deg, ${c.primary}, ${alpha(c.primary, 0)})`, transform: `scaleX(${line})`, transformOrigin: 'right'}} />
      {g.sub && (
        <div style={{fontFamily: font(t, 'mono'), fontSize: 30, color: c.muted, marginTop: 22, direction: 'rtl', opacity: line}}>
          <span style={{color: alpha(c.accent, 0.8)}}>// </span>
          <span style={{fontFamily: font(t, 'ar')}}>{g.sub}</span>
        </div>
      )}
    </div>
  );
};

/** Items join one by one as they are said — like lines of program output. */
export const ListCard: React.FC<{g: Gfx; from: number; len: number; itemFrames: number[]}> = ({g, from, len, itemFrames}) => {
  const t = useTheme();
  const c = t.colors;
  const now = useCurrentFrame();
  const {inn, out, alive} = enterExit(now - from, len);
  if (!alive) return null;
  return (
    <div
      style={{
        position: 'absolute', left: 60, width: LAYOUT.talk.cam.x - 120, top: 0, height: 1080,
        display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: inn * out, paddingBottom: 80,
      }}
    >
      <div style={{direction: 'rtl', minWidth: 620}}>
        <div style={{display: 'flex', gap: 18, alignItems: 'center', marginBottom: 26}}>
          <span style={{fontFamily: font(t, 'mono'), fontWeight: 800, fontSize: 44, color: c.accent}}>{'>'}</span>
          <span style={{fontFamily: font(t, 'ar'), fontWeight: 700, fontSize: 56, color: c.muted}}>{g.title}</span>
        </div>
        {g.items.map((it: {text: string; icon?: string}, i: number) => {
          if (now < itemFrames[i]) return null;
          const p = spring({frame: now - itemFrames[i], fps: FPS, config: SPRING, durationInFrames: ENTER});
          return (
            <div key={i} style={{display: 'flex', alignItems: 'center', gap: 24, margin: '14px 0', opacity: p, transform: `translateX(${(1 - p) * -30}px)`}}>
              <span style={{width: 18, height: 18, background: c.primary, borderRadius: 4, flex: 'none'}} />
              {t.keywords.icons && it.icon && <span style={{fontSize: 64}}>{it.icon}</span>}
              <span style={{fontFamily: font(t, 'ar'), fontWeight: 700, fontSize: 84, color: c.text}}>{it.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** A chapter is a commit: big for 1.2 s, then it settles into the tag at the top-left. */
export const Chapter: React.FC<{g: Gfx; from: number; until: number}> = ({g, from, until}) => {
  const t = useTheme();
  const c = t.colors;
  const f = useCurrentFrame() - from;
  if (f < 0 || f >= until - from) return null;
  const big = spring({frame: f, fps: FPS, config: SPRING, durationInFrames: ENTER});
  const settle = spring({frame: f - 38, fps: FPS, config: SPRING, durationInFrames: 18});
  const dim = interpolate(f, [0, 8, 36, 50], [0, 0.72, 0.72, 0], clamp);
  const cmd = typed('git commit -m', f, 40);
  const wipe = interpolate(f, [8, 20], [0, 1], clamp);
  if (settle > 0.98) {
    return (
      <div
        style={{
          position: 'absolute', left: 60, top: 34, display: 'flex', alignItems: 'center', gap: 14, direction: 'ltr',
          fontFamily: font(t, 'mono'), fontSize: 22, color: c.muted, background: alpha(c.bg, 0.8),
          border: `1px solid ${c.line}`, borderRadius: 10, padding: '7px 16px',
        }}
      >
        <span style={{width: 10, height: 10, borderRadius: 5, background: c.accent}} />
        <span>{t.identity.path}/{t.identity.series}</span>
        <span style={{color: c.accent, fontWeight: 700}}>{g.num}</span>
        <span style={{fontFamily: font(t, 'ar'), fontWeight: 700, color: c.text, fontSize: 24}}>{g.title}</span>
      </div>
    );
  }
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{background: c.bg, opacity: dim}} />
      <AbsoluteFill
        style={{
          alignItems: 'center', justifyContent: 'center', opacity: big * (1 - settle),
          transform: `scale(${(0.94 + 0.06 * big) * (1 - 0.6 * settle)}) translate(${-settle * 900}px, ${-settle * 520}px)`,
        }}
      >
        <div style={{fontFamily: font(t, 'mono'), fontSize: 38, color: c.muted, direction: 'ltr', marginBottom: 18}}>
          <span style={{color: c.accent}}>$ </span>
          {cmd}
        </div>
        <div style={{display: 'flex', alignItems: 'center', gap: 36, direction: 'ltr'}}>
          <span style={{fontFamily: font(t, 'mono'), fontWeight: 800, fontSize: 150, color: c.accent, lineHeight: 1}}>{g.num}</span>
          <Wipe p={wipe}>
            <span style={{fontFamily: font(t, 'ar'), fontWeight: 700, fontSize: 124, color: c.text, lineHeight: 1.15}}>"{g.title}"</span>
          </Wipe>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** whoami — name card that types itself next to the camera window. */
export const LowerThird: React.FC<{g: Gfx; from: number}> = ({g, from}) => {
  const t = useTheme();
  const c = t.colors;
  const f = useCurrentFrame() - from;
  const len = Math.round((g.dur ?? 4) * FPS);
  const {inn, out, alive} = enterExit(f, len);
  if (!alive) return null;
  const cam = LAYOUT.talk.cam;
  const name = g.title || t.identity.name;
  const role = g.sub || t.identity.role;
  return (
    <div
      style={{
        position: 'absolute', left: cam.x - 120, top: cam.y + cam.h - 190, opacity: out, direction: 'ltr',
        transform: `translateY(${(1 - inn) * 30}px)`, background: alpha(c.bg, 0.94), border: `1.5px solid ${alpha(c.primary, 0.8)}`,
        borderRadius: 14, padding: '16px 26px', boxShadow: '0 24px 60px #000a', minWidth: 420,
      }}
    >
      <div style={{fontFamily: font(t, 'mono'), fontSize: 22, color: c.muted}}>
        <span style={{color: c.accent}}>{t.identity.handle}</span>:~$ {typed('whoami', f - 2, 18)}
      </div>
      <div style={{fontFamily: font(t, 'mono'), fontWeight: 800, fontSize: 44, color: c.text, marginTop: 6, opacity: interpolate(f, [12, 18], [0, 1], clamp)}}>
        {name}
      </div>
      <div style={{fontFamily: font(t, 'mono'), fontSize: 21, color: c.primary, marginTop: 2, opacity: interpolate(f, [16, 24], [0, 1], clamp)}}>{role}</div>
    </div>
  );
};

/** The prompt being written: each word appears the moment it is said. */
export const PromptCard: React.FC<{g: Gfx; from: number; to: number; words: {w: Word; frame: number}[]}> = ({g, from, to, words}) => {
  const t = useTheme();
  const c = t.colors;
  const now = useCurrentFrame();
  const {inn, out, alive} = enterExit(now - from, to - from);
  if (!alive) return null;
  const shown = words.filter((x) => x.frame <= now);
  const lens = LAYOUT.screen.screen;
  return (
    <div
      style={{
        position: 'absolute', left: lens.x + 80, width: lens.w - 160, top: lens.y + lens.h - 350, height: 310,
        opacity: inn * out, transform: `translateY(${(1 - inn) * 40}px)`, background: alpha(c.bg, 0.96), borderRadius: 16,
        boxShadow: '0 30px 80px #000b', border: `1.5px solid ${alpha(c.primary, 0.8)}`, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}
    >
      <div style={{height: 40, display: 'flex', alignItems: 'center', gap: 9, padding: '0 16px', borderBottom: `1px solid ${c.line}`, direction: 'ltr'}}>
        {['#FF5F57', '#FEBC2E', '#28C840'].map((d) => (
          <span key={d} style={{width: 11, height: 11, borderRadius: 6, background: d}} />
        ))}
        <span style={{marginLeft: 12, fontFamily: font(t, 'mono'), fontSize: 18, color: c.muted}}>{g.label || 'prompt.txt'}</span>
      </div>
      <div
        style={{
          flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', padding: '14px 34px 22px', direction: 'rtl',
          // Older lines scroll up and fade instead of being sliced by the edge.
          maskImage: 'linear-gradient(to bottom, transparent 0, black 34%)',
        }}
      >
        <div style={{fontFamily: font(t, 'ar'), fontWeight: 500, fontSize: 48, lineHeight: 1.5, color: c.text}}>
          {shown.map((x, i) => (
            <span key={i} style={{opacity: interpolate(now - x.frame, [0, 5], [0, 1], clamp), color: i === shown.length - 1 ? c.accent : c.text}}>
              {x.w.w}{' '}
            </span>
          ))}
          <Caret h={44} />
        </div>
      </div>
    </div>
  );
};

/** The opening sting is a build: a command types, a bar fills, the logo lands. */
export const Sting: React.FC<{from: number; frames: number}> = ({from, frames}) => {
  const t = useTheme();
  const c = t.colors;
  const asset = useAsset();
  const f = useCurrentFrame() - from;
  if (f < 0 || f >= frames) return null;
  const inn = interpolate(f, [0, 5], [0, 1], clamp);
  const out = interpolate(f, [frames - 8, frames], [1, 0], clamp);
  const bar = interpolate(f, [16, 38], [0, 1], {...clamp, easing: (x) => 1 - Math.pow(1 - x, 2)});
  const logo = spring({frame: f - 36, fps: FPS, config: SPRING, durationInFrames: 16});
  return (
    <AbsoluteFill style={{opacity: inn * out, background: c.bg, alignItems: 'center', justifyContent: 'center'}}>
      <AbsoluteFill style={{background: `radial-gradient(700px 480px at 50% 50%, ${alpha(c.glow, 0.3)}, transparent 70%)`}} />
      <div style={{width: 760, direction: 'ltr', fontFamily: font(t, 'mono'), color: c.muted, fontSize: 30, opacity: 1 - logo}}>
        <div>
          <span style={{color: c.accent}}>$ </span>
          {typed(`./build --series ${t.identity.series}`, f, 60)}
        </div>
        <div style={{marginTop: 22, height: 14, borderRadius: 7, background: c.line, overflow: 'hidden'}}>
          <div style={{width: `${bar * 100}%`, height: '100%', background: c.accent}} />
        </div>
      </div>
      <div style={{position: 'absolute', display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: logo, transform: `scale(${0.9 + 0.1 * logo})`}}>
        <div style={{fontFamily: font(t, 'mono'), fontWeight: 800, fontSize: 96, color: c.text, direction: 'ltr'}}>
          <span style={{color: c.accent}}>{'<'}</span>
          {t.identity.name.split(' ')[0].toLowerCase()}
          <span style={{color: c.accent}}>{' />'}</span>
        </div>
        {t.identity.logo && <Img src={asset(t.identity.logo)} style={{height: 64, marginTop: 18, opacity: 0.9}} />}
      </div>
    </AbsoluteFill>
  );
};

export const Outro: React.FC<{g: Gfx; from: number; frames: number}> = ({g, from}) => {
  const t = useTheme();
  const c = t.colors;
  const asset = useAsset();
  const f = useCurrentFrame() - from;
  if (f < 0) return null;
  const inn = interpolate(f, [0, 10], [0, 1], clamp);
  const a = spring({frame: f - 26, fps: FPS, config: SPRING, durationInFrames: ENTER});
  const b = spring({frame: f - 36, fps: FPS, config: SPRING, durationInFrames: ENTER});
  return (
    <AbsoluteFill style={{opacity: inn, background: c.bg, alignItems: 'center', justifyContent: 'center'}}>
      <AbsoluteFill style={{background: `radial-gradient(800px 500px at 50% 40%, ${alpha(c.glow, 0.28)}, transparent 70%)`}} />
      <div style={{fontFamily: font(t, 'mono'), fontSize: 34, color: c.muted, direction: 'ltr', marginBottom: 46}}>
        <span style={{color: c.accent}}>$ </span>
        {typed('git push origin next-episode', f, 50)}
      </div>
      <div style={{fontFamily: font(t, 'ar'), fontWeight: 700, fontSize: 104, color: c.accent, opacity: a, transform: `translateY(${(1 - a) * 30}px)`}}>{g.title}</div>
      <div style={{fontFamily: font(t, 'ar'), fontWeight: 500, fontSize: 56, color: c.text, marginTop: 14, opacity: b, transform: `translateY(${(1 - b) * 30}px)`, direction: 'rtl'}}>
        {g.sub}
      </div>
      <div style={{display: 'flex', alignItems: 'center', gap: 22, marginTop: 64, opacity: b, direction: 'ltr'}}>
        <span style={{fontFamily: font(t, 'mono'), fontSize: 30, color: c.muted}}>{t.identity.handle}</span>
        {t.identity.logo && <Img src={asset(t.identity.logo)} style={{height: 44}} />}
      </div>
    </AbsoluteFill>
  );
};

/** Session log: what was said so far in this chapter stays as quiet terminal history. */
export const SessionLog: React.FC<{lines: {text: string; at: number}[]}> = ({lines}) => {
  const t = useTheme();
  const c = t.colors;
  const now = useCurrentFrame();
  const shown = lines.filter((l) => l.at <= now).slice(-5);
  if (!shown.length) return null;
  return (
    <div style={{position: 'absolute', left: 60, top: 96, direction: 'rtl', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6}}>
      {shown.map((l, i) => {
        const a = interpolate(now - l.at, [0, 10], [0, 1], clamp) * (0.35 + 0.65 * ((i + 1) / shown.length));
        return (
          <div key={l.at + l.text} style={{opacity: a, fontSize: 26, color: c.muted, display: 'flex', gap: 10, alignItems: 'center'}}>
            <span style={{fontFamily: font(t, 'ar'), fontWeight: 500}}>{l.text}</span>
            <span style={{fontFamily: font(t, 'mono'), color: alpha(c.accent, 0.7)}}>✓</span>
          </div>
        );
      })}
    </div>
  );
};
