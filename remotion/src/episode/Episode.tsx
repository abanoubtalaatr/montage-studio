// Episode renderer — draws montage/episodes/<id>/edit/{edl,words}.json with a theme
// from public/themes (montage/DESIGN.md). The dashboard renders the same component live.
import React, {useMemo} from 'react';
import {AbsoluteFill, CalculateMetadataFunction, staticFile, useCurrentFrame} from 'remotion';
import {Background, CameraLayer, ScreenLayer, ShotAt, Sfx, Sound} from './Layers';
import {Captions, buildCaptions} from './Captions';
import {Chapter, Keyword, ListCard, LowerThird, Outro, PromptCard, SessionLog, Sting} from './Graphics';
import {Edl, Word, buildTimeline} from './timeline';
import {AssetCtx, AssetResolver, Theme, ThemeCtx} from './theme';
import {FPS} from './tokens';

export const DEFAULT_THEME = 'abanoub-terminal';

export type EpisodeProps = {
  episode: string;
  edl?: Edl;
  words?: Word[];
  theme?: Theme;
  /** Media URL resolver for the dashboard Player; undefined = staticFile() in Remotion. */
  asset?: AssetResolver;
};

export const calculateEpisodeMetadata: CalculateMetadataFunction<EpisodeProps> = async ({props}) => {
  const base = `episodes/${props.episode}`;
  const edl: Edl = props.edl ?? (await fetch(staticFile(`${base}/edl.json`)).then((r) => r.json()));
  const words: Word[] = props.words ?? (await fetch(staticFile(`${base}/words.json`)).then((r) => r.json())).words;
  const theme: Theme = props.theme ?? (await fetch(staticFile(`themes/${edl.theme ?? DEFAULT_THEME}.json`)).then((r) => r.json()));
  return {durationInFrames: buildTimeline(edl).total, props: {...props, edl, words, theme}};
};

/** Everything the episode derives from edl + words; shared with the dashboard. */
export function useEpisodeModel(edl: Edl, words: Word[], theme: Theme) {
  return useMemo(() => {
    const tl = buildTimeline(edl);
    const shots: ShotAt[] = (edl.shots.length ? edl.shots : [{at: 0, layout: 'talk' as const}]).map((s) => ({
      ...s,
      frame: s.at <= 0 ? 0 : tl.bodyFrame(s.at),
    }));
    const g = edl.gfx.filter((x) => x.on !== false);
    const prompts = g.filter((x) => x.type === 'prompt');
    const chapters = g.filter((x) => x.type === 'chapter').map((c) => ({c, from: tl.bodyFrame(c.at!)}));
    const promptSpans = prompts.map((p) => ({p, from: tl.bodyFrame(p.at!), to: tl.bodyFrame(p.end!)}));
    const chunks = buildCaptions(words, tl, prompts.map((p) => [p.at!, p.end!] as [number, number]), theme.captions.maxWords);
    const sfx: Sfx[] = [];
    shots.slice(1).forEach((s) => sfx.push({frame: s.frame - 4, file: 'whoosh', volume: 0.8}));
    chapters.forEach(({from}) => sfx.push({frame: from, file: 'blip', volume: 0.6}));
    g.filter((x) => x.type === 'keyword').forEach((x) =>
      tl.frames(x.at!).forEach((f) => [3, 7, 11].forEach((d) => sfx.push({frame: f + d, file: 'key', volume: 0.5}))),
    );
    promptSpans.forEach(({p}) =>
      words.filter((w) => w.start >= p.at! && w.start < p.end!).forEach((w) => sfx.push({frame: tl.bodyFrame(w.start), file: 'key', volume: 0.35})),
    );
    if (tl.sting) {
      for (let d = 2; d < 22; d += 3) sfx.push({frame: tl.sting.from + d, file: 'key', volume: 0.4});
      sfx.push({frame: tl.sting.from + 32, file: 'whoosh'});
    }
    if (tl.outro) sfx.push({frame: tl.outro.from, file: 'whoosh'});

    // Keywords and lists share the stage: one ends when the next one starts.
    const stage = g
      .filter((x) => x.type === 'keyword' || x.type === 'list')
      .flatMap((x) => (x.type === 'keyword' ? tl.frames(x.at!) : [tl.bodyFrame(x.at!)]).map((from) => ({g: x, from})))
      .sort((a, b) => a.from - b.from)
      .map((s, i, all) => {
        const own = Math.round((s.g.dur ?? (s.g.type === 'list' ? 4 : 2)) * FPS);
        const next = all[i + 1]?.from;
        return {...s, len: next !== undefined ? Math.min(own, Math.max(next - s.from, 6)) : own};
      });
    // Session log: each keyword joins the log when it leaves the stage; a chapter clears it.
    const log = stage
      .filter((s) => s.g.type === 'keyword' && tl.placed.some((p) => p.seg.role !== 'hook' && p.from <= s.from && s.from < p.from + p.frames))
      .map((s) => ({text: s.g.text as string, at: s.from + s.len, chapter: [...chapters].reverse().find((c) => c.from <= s.from)?.from ?? 0}));
    return {tl, shots, g, chapters, promptSpans, chunks, sfx, stage, log};
  }, [edl, words, theme]);
}

const Body: React.FC<{episode: string; edl: Edl; words: Word[]; theme: Theme}> = ({episode, edl, words, theme}) => {
  const base = `episodes/${episode}`;
  const {tl, shots, g, chapters, promptSpans, chunks, sfx, stage, log} = useEpisodeModel(edl, words, theme);
  const frame = useCurrentFrame();
  const chapterNow = [...chapters].reverse().find((c) => c.from <= frame)?.from ?? 0;
  const layoutAt = (f: number) => [...shots].reverse().find((s) => s.frame <= f)?.layout ?? 'talk';
  const blocked = (f: number) =>
    !!(tl.sting && f >= tl.sting.from && f < tl.sting.from + tl.sting.frames) ||
    !!(tl.outro && f >= tl.outro.from) ||
    chapters.some((c) => f >= c.from && f < c.from + 46) ||
    promptSpans.some((p) => f >= p.from && f < p.to);
  const screenTitle = (shots.find((s) => s.layout === 'screen') as any)?.title ?? 'screen.rec';

  return (
    <AbsoluteFill style={{background: theme.colors.bg}}>
      <Background />
      <ScreenLayer tl={tl} base={base} shots={shots} title={screenTitle} />
      <CameraLayer tl={tl} base={base} shots={shots} />
      {layoutAt(frame) === 'talk' && <SessionLog lines={log.filter((l) => l.chapter === chapterNow)} />}
      {stage.map((s, i) =>
        s.g.type === 'keyword' ? (
          <Keyword key={s.g.id + i} g={s.g} from={s.from} len={s.len} layout={layoutAt(s.from)} />
        ) : (
          <ListCard key={s.g.id} g={s.g} from={s.from} len={s.len} itemFrames={s.g.items.map((it: {at: number}) => tl.bodyFrame(it.at))} />
        ),
      )}
      {g.filter((x) => x.type === 'lower_third').map((x) => <LowerThird key={x.id} g={x} from={tl.bodyFrame(x.at!) + 48} />)}
      {promptSpans.map(({p, from, to}) => (
        <PromptCard
          key={p.id}
          g={p}
          from={from}
          to={to}
          words={words.filter((w) => w.start >= p.at! && w.start < p.end!).map((w) => ({w, frame: tl.bodyFrame(w.start)}))}
        />
      ))}
      <Captions chunks={chunks} blocked={blocked} />
      {chapters.map(({c, from}, i) => (
        <Chapter key={c.id} g={c} from={from} until={chapters[i + 1]?.from ?? tl.outro?.from ?? tl.total} />
      ))}
      {tl.sting && <Sting from={tl.sting.from} frames={tl.sting.frames} />}
      {tl.outro && <Outro g={g.find((x) => x.type === 'outro')!} from={tl.outro.from} frames={tl.outro.frames} />}
      <Sound tl={tl} base={base} sfx={sfx} />
    </AbsoluteFill>
  );
};

export const Episode: React.FC<EpisodeProps> = ({episode, edl, words, theme, asset}) => {
  if (!edl || !words || !theme) return null;
  return (
    <ThemeCtx.Provider value={theme}>
      <AssetCtx.Provider value={asset ?? null}>
        <Body episode={episode} edl={edl} words={words} theme={theme} />
      </AssetCtx.Provider>
    </ThemeCtx.Provider>
  );
};

export const EPISODE_FPS = FPS;
