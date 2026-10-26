// Picture layers: background, screen window, camera window/bubble, voice + music + SFX.
import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, Sequence, interpolate, spring, useCurrentFrame} from 'remotion';
import {CHROME, FPS, LAYOUT, LAYOUT_MOVE, Rect, SPRING, ZOOM_MOVE} from './tokens';
import {Shot, Timeline} from './timeline';
import {alpha, font, useAsset, useTheme} from './theme';

export const Background: React.FC = () => {
  const t = useTheme();
  const f = useCurrentFrame();
  const c = t.colors;
  return (
    <AbsoluteFill style={{background: c.bg}}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(900px 620px at 10% 0%, ${alpha(c.glow, 0.28)}, transparent 70%),
            radial-gradient(700px 500px at 100% 100%, ${alpha(c.accent, 0.06)}, transparent 70%)`,
        }}
      />
      {t.grid && (
        <AbsoluteFill
          style={{
            backgroundImage: `radial-gradient(${alpha(c.muted, 0.28)} 1.4px, transparent 1.6px)`,
            backgroundSize: '44px 44px',
            backgroundPosition: `${(f * 0.25) % 44}px ${(f * 0.12) % 44}px`,
            maskImage: 'radial-gradient(ellipse 80% 70% at 50% 45%, black, transparent)',
          }}
        />
      )}
    </AbsoluteFill>
  );
};

const mix = (a: Rect, b: Rect, k: number): Rect => ({
  x: a.x + (b.x - a.x) * k,
  y: a.y + (b.y - a.y) * k,
  w: a.w + (b.w - a.w) * k,
  h: a.h + (b.h - a.h) * k,
  r: a.r + (b.r - a.r) * k,
});

export type ShotAt = Shot & {frame: number};

/** Where every layer sits at this frame, easing between shots. */
export function useLayout(shots: ShotAt[]) {
  const f = useCurrentFrame();
  let k = 0;
  shots.forEach((s, i) => {
    if (s.frame <= f) k = i;
  });
  const cur = shots[k];
  const prev = shots[Math.max(k - 1, 0)];
  const t = k === 0 ? 1 : spring({frame: f - cur.frame, fps: FPS, config: SPRING, durationInFrames: LAYOUT_MOVE});
  const a = LAYOUT[prev.layout];
  const b = LAYOUT[cur.layout];
  const zoomTarget = cur.layout === 'screen' ? cur.zoom ?? 1 : 1;
  const zoomFrom = prev.layout === 'screen' && k > 0 ? prev.zoom ?? 1 : 1;
  const z = interpolate(f - cur.frame - LAYOUT_MOVE / 2, [0, ZOOM_MOVE], [zoomFrom, zoomTarget], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  });
  return {
    layout: t > 0.5 ? cur.layout : prev.layout,
    cam: mix(a.cam, b.cam, t),
    screen: mix(a.screen, b.screen, t),
    screenOpacity: a.screenOpacity + (b.screenOpacity - a.screenOpacity) * t,
    zoom: z,
    focus: cur.focus ?? prev.focus ?? [0.5, 0.5],
  };
}

/** A terminal-style window: title bar with three dots + mono title, content below. */
const Window: React.FC<{r: Rect; title: string; chrome: number; style?: React.CSSProperties; children: React.ReactNode}> = ({
  r,
  title,
  chrome,
  style,
  children,
}) => {
  const t = useTheme();
  const c = t.colors;
  const bar = CHROME * chrome;
  return (
    <div
      style={{
        position: 'absolute', left: r.x, top: r.y, width: r.w, height: r.h, borderRadius: r.r, overflow: 'hidden',
        background: c.card, boxShadow: `0 30px 90px ${alpha('#000000', 0.55)}, 0 0 0 1.5px ${alpha(c.primary, 0.55)}`,
        ...style,
      }}
    >
      {bar > 1 && (
        <div
          style={{
            height: bar, display: 'flex', alignItems: 'center', gap: 10, padding: '0 18px', opacity: chrome,
            background: c.card, borderBottom: `1px solid ${c.line}`, direction: 'ltr',
          }}
        >
          {['#FF5F57', '#FEBC2E', '#28C840'].map((d) => (
            <span key={d} style={{width: 13, height: 13, borderRadius: 7, background: d}} />
          ))}
          <span style={{marginLeft: 14, fontFamily: font(t, 'mono'), fontSize: 19, color: c.muted}}>{title}</span>
        </div>
      )}
      <div style={{position: 'relative', width: '100%', height: r.h - bar, overflow: 'hidden'}}>{children}</div>
    </div>
  );
};

const Clips: React.FC<{tl: Timeline; src: string; fit: React.CSSProperties}> = ({tl, src, fit}) => (
  <>
    {tl.placed.map((p, i) => (
      <Sequence key={i} from={p.from} durationInFrames={p.frames} layout="none">
        <OffthreadVideo
          src={src}
          startFrom={Math.round(p.seg.start * FPS)}
          playbackRate={p.seg.rate}
          muted
          style={{width: '100%', height: '100%', ...fit}}
        />
      </Sequence>
    ))}
  </>
);

export const ScreenLayer: React.FC<{tl: Timeline; base: string; shots: ShotAt[]; title: string}> = ({tl, base, shots, title}) => {
  const L = useLayout(shots);
  const asset = useAsset();
  if (L.screenOpacity < 0.01) return null;
  return (
    <Window r={L.screen} title={title} chrome={1} style={{opacity: L.screenOpacity, background: '#fff'}}>
      <div style={{width: '100%', height: '100%', transform: `scale(${L.zoom})`, transformOrigin: `${L.focus[0] * 100}% ${L.focus[1] * 100}%`}}>
        <Clips tl={tl} src={asset(`${base}/screen.mp4`)} fit={{objectFit: 'cover'}} />
      </div>
    </Window>
  );
};

export const CameraLayer: React.FC<{tl: Timeline; base: string; shots: ShotAt[]}> = ({tl, base, shots}) => {
  const L = useLayout(shots);
  const t = useTheme();
  const asset = useAsset();
  // The bubble is a circle: the title bar fades as the corner radius grows.
  const chrome = interpolate(L.cam.r, [18, 80], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <Window
      r={L.cam}
      title="live.cam"
      chrome={chrome}
      style={chrome < 0.5 ? {boxShadow: `0 24px 70px #0008, 0 0 0 5px ${t.colors.accent}`} : undefined}
    >
      <Clips tl={tl} src={asset(`${base}/cam.mp4`)} fit={{objectFit: 'cover', objectPosition: '50% 30%'}} />
    </Window>
  );
};

export type Sfx = {frame: number; file: 'whoosh' | 'key' | 'blip'; volume?: number};

export const Sound: React.FC<{tl: Timeline; base: string; sfx: Sfx[]}> = ({tl, base, sfx}) => {
  const t = useTheme();
  const asset = useAsset();
  const music = (f: number) => {
    const inSting = tl.sting && f >= tl.sting.from - 6 && f < tl.sting.from + tl.sting.frames;
    const inOutro = tl.outro && f >= tl.outro.from - 10;
    const level = t.music.volume * (inSting ? 5 : inOutro ? 4 : 1);
    const fadeIn = interpolate(f, [0, 20], [0, 1], {extrapolateRight: 'clamp'});
    const fadeOut = interpolate(f, [tl.total - 45, tl.total], [1, 0], {extrapolateLeft: 'clamp'});
    return Math.min(level, 0.4) * fadeIn * fadeOut;
  };
  return (
    <>
      {tl.placed.map((p, i) => (
        <Sequence key={i} from={p.from} durationInFrames={p.frames} layout="none">
          <Audio
            src={asset(`${base}/voice_final.wav`)}
            startFrom={Math.round(p.seg.start * FPS)}
            playbackRate={p.seg.rate}
            // 2-frame ramps at every cut so no edge clicks.
            volume={(f) => (p.seg.mute ? 0 : Math.min(1, (f + 1) / 2, (p.frames - f) / 2))}
          />
        </Sequence>
      ))}
      {t.music.on && <Audio src={asset(t.music.file)} loop volume={music} />}
      {t.sfx.on &&
        sfx.map((s, i) => (
          <Sequence key={'sfx' + i} from={Math.max(0, s.frame)} durationInFrames={30} layout="none">
            <Audio src={asset(`sfx/${s.file}.wav`)} volume={t.sfx.volume * (s.volume ?? 1)} />
          </Sequence>
        ))}
    </>
  );
};
