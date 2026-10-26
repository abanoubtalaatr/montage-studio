// Montage Studio — full control over an episode: cuts, graphics, shots, identity, audio, render.
// Everything edits edl.json / the theme in memory; the Player re-renders live; Save writes to disk.
import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Player, PlayerRef} from '@remotion/player';
import {Episode} from '../src/episode/Episode';
import {Edl, Word, buildTimeline} from '../src/episode/timeline';
import {Theme} from '../src/episode/theme';
import {Timeline} from './Timeline';
import {AudioPanel, BrandPanel, CutsPanel, GfxPanel, ShotsPanel} from './panels';

export type Job = {id: string; kind: string; status: 'running' | 'done' | 'error'; log: string[]; progress: number};

const api = async <T,>(url: string, init?: RequestInit): Promise<T> => {
  const r = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...init});
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
};

const TABS = [
  ['cuts', 'القص'],
  ['gfx', 'الجرافيك'],
  ['shots', 'اللقطات'],
  ['brand', 'الهوية'],
  ['audio', 'الصوت'],
] as const;
type Tab = (typeof TABS)[number][0];

export type Ctx = {
  edl: Edl;
  words: Word[];
  theme: Theme;
  setEdl: (fn: (e: Edl) => Edl) => void;
  setTheme: (fn: (t: Theme) => Theme) => void;
  now: number; // source seconds at the playhead
  seekSource: (t: number) => void;
  runJob: (kind: 'voice' | 'roughcut') => Promise<void>;
  busy: string | null;
};

export const App: React.FC = () => {
  const [episodes, setEpisodes] = useState<string[]>([]);
  const [episode, setEpisode] = useState<string>('');
  const [edl, setEdlRaw] = useState<Edl | null>(null);
  const [words, setWords] = useState<Word[]>([]);
  const [theme, setThemeRaw] = useState<Theme | null>(null);
  const [past, setPast] = useState<Edl[]>([]);
  const [future, setFuture] = useState<Edl[]>([]);
  const [dirty, setDirty] = useState({edl: false, theme: false});
  const [tab, setTab] = useState<Tab>('cuts');
  const [frame, setFrame] = useState(0);
  const [voiceVer, setVoiceVer] = useState(Date.now());
  const [job, setJob] = useState<Job | null>(null);
  const [toast, setToast] = useState('');
  const [outputs, setOutputs] = useState<string[]>([]);
  const player = useRef<PlayerRef>(null);

  const say = (s: string) => {
    setToast(s);
    setTimeout(() => setToast(''), 2600);
  };

  useEffect(() => {
    api<string[]>('/api/episodes').then((l) => {
      setEpisodes(l);
      setEpisode(new URLSearchParams(location.search).get('ep') || l[0] || '');
    });
  }, []);

  const load = useCallback(async (ep: string) => {
    const d = await api<{edl: Edl; words: Word[]; outputs: string[]}>(`/api/episode/${ep}`);
    const th = await api<Theme>(`/api/theme/${d.edl.theme || 'abanoub-terminal'}`);
    setEdlRaw(d.edl);
    setWords(d.words);
    setOutputs(d.outputs);
    setThemeRaw(th);
    setPast([]);
    setFuture([]);
    setDirty({edl: false, theme: false});
  }, []);
  useEffect(() => {
    if (episode) load(episode);
  }, [episode, load]);

  const setEdl = useCallback(
    (fn: (e: Edl) => Edl) =>
      setEdlRaw((e) => {
        if (!e) return e;
        setPast((p) => [...p.slice(-80), e]);
        setFuture([]);
        setDirty((d) => ({...d, edl: true}));
        return fn(structuredClone(e));
      }),
    [],
  );
  const setTheme = useCallback(
    (fn: (t: Theme) => Theme) =>
      setThemeRaw((t) => {
        if (!t) return t;
        setDirty((d) => ({...d, theme: true}));
        return fn(structuredClone(t));
      }),
    [],
  );
  const undo = () => {
    if (!past.length || !edl) return;
    setFuture((f) => [edl, ...f]);
    setEdlRaw(past[past.length - 1]);
    setPast((p) => p.slice(0, -1));
    setDirty((d) => ({...d, edl: true}));
  };
  const redo = () => {
    if (!future.length || !edl) return;
    setPast((p) => [...p, edl]);
    setEdlRaw(future[0]);
    setFuture((f) => f.slice(1));
  };

  const save = useCallback(async () => {
    if (!edl || !theme) return;
    if (dirty.edl) await api(`/api/episode/${episode}/edl`, {method: 'PUT', body: JSON.stringify(edl)});
    if (dirty.theme) await api(`/api/theme/${theme.name}`, {method: 'PUT', body: JSON.stringify(theme)});
    setDirty({edl: false, theme: false});
    say('اتحفظ ✓');
  }, [edl, theme, dirty, episode]);

  const tl = useMemo(() => (edl ? buildTimeline(edl) : null), [edl]);
  const now = (tl && tl.sourceAt(frame)) ?? 0;

  useEffect(() => {
    const p = player.current;
    if (!p) return;
    const on = (e: {detail: {frame: number}}) => setFrame(e.detail.frame);
    p.addEventListener('frameupdate', on);
    p.addEventListener('seeked', on);
    return () => {
      p.removeEventListener('frameupdate', on);
      p.removeEventListener('seeked', on);
    };
  }, [tl !== null]);

  const seekSource = useCallback(
    (t: number) => {
      if (!tl) return;
      const f = tl.bodyFrame(t);
      player.current?.seekTo(f);
      setFrame(f);
    },
    [tl],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = /INPUT|TEXTAREA|SELECT/.test((e.target as HTMLElement).tagName);
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        save();
      } else if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !typing) {
        e.preventDefault();
        e.shiftKey ? redo() : undo();
      } else if (e.key === ' ' && !typing) {
        e.preventDefault();
        player.current?.toggle();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const poll = async (j: Job) => {
    setJob(j);
    let cur = j;
    while (cur.status === 'running') {
      await new Promise((r) => setTimeout(r, 1000));
      cur = await api<Job>(`/api/job/${cur.id}`);
      setJob(cur);
    }
    return cur;
  };
  const runJob = async (kind: 'voice' | 'roughcut') => {
    await save();
    const done = await poll(await api<Job>(`/api/episode/${episode}/${kind}`, {method: 'POST'}));
    if (done.status !== 'done') return say('حصل خطأ — شوف السجل');
    if (kind === 'voice') setVoiceVer(Date.now());
    if (kind === 'roughcut') await load(episode);
    say('تمام ✓');
  };
  const render = async () => {
    await save();
    const done = await poll(await api<Job>(`/api/episode/${episode}/render`, {method: 'POST'}));
    if (done.status === 'done') {
      setOutputs((o) => [...new Set([...o, 'youtube.mp4'])]);
      say('الفيديو جاهز ✓');
    } else say('الرندر فشل — شوف السجل');
  };

  const asset = useCallback((p: string) => (p.endsWith('voice_final.wav') ? `/${p}?v=${voiceVer}` : `/${p}`), [voiceVer]);
  const inputProps = useMemo(() => ({episode, edl: edl!, words, theme: theme!, asset}), [episode, edl, words, theme, asset]);

  if (!edl || !theme || !tl) return <div className="loading">بيحمّل…</div>;
  const ctx: Ctx = {edl, words, theme, setEdl, setTheme, now, seekSource, runJob, busy: job?.status === 'running' ? job.kind : null};
  const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`;
  const isDirty = dirty.edl || dirty.theme;

  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="dot" /> Montage Studio
        </div>
        <select value={episode} onChange={(e) => setEpisode(e.target.value)}>
          {episodes.map((e) => (
            <option key={e}>{e}</option>
          ))}
        </select>
        <span className="chip num">
          {fmt(frame / 30)} / {fmt(tl.total / 30)}
        </span>
        <div className="grow" />
        <button onClick={undo} disabled={!past.length} title="Cmd+Z">↶ رجوع</button>
        <button onClick={redo} disabled={!future.length} title="Cmd+Shift+Z">↷ تقدّم</button>
        <button className={isDirty ? 'primary' : ''} onClick={save} title="Cmd+S">
          {isDirty ? '● احفظ' : 'محفوظ'}
        </button>
        <button className="accent" onClick={render} disabled={job?.status === 'running'}>
          ▶ رندر الفيديو
        </button>
        {outputs.includes('youtube.mp4') && (
          <>
            <a className="btn" href={`/api/episode/${episode}/output/youtube.mp4?t=${job?.id ?? ''}`} target="_blank" rel="noreferrer">
              افتح النسخة النهائية
            </a>
            <button onClick={() => api(`/api/episode/${episode}/reveal/youtube.mp4`, {method: 'POST'})}>Finder</button>
          </>
        )}
      </header>
      {job && (
        <div className={`job ${job.status}`}>
          <b>{{render: 'رندر', voice: 'معالجة الصوت', roughcut: 'حساب السكتات'}[job.kind] ?? job.kind}</b>
          <div className="bar">
            <i style={{width: `${Math.round(job.progress * 100)}%`}} />
          </div>
          <span className="num">{job.status === 'running' ? `${Math.round(job.progress * 100)}%` : job.status === 'done' ? 'خلص ✓' : 'فشل ✗'}</span>
          <code dir="ltr">{job.log[job.log.length - 1]}</code>
          {job.status !== 'running' && <button onClick={() => setJob(null)}>×</button>}
        </div>
      )}
      <main>
        <section className="stage">
          <div className="player" dir="ltr">
            <Player
              ref={player}
              component={Episode}
              inputProps={inputProps}
              durationInFrames={tl.total}
              fps={30}
              compositionWidth={1920}
              compositionHeight={1080}
              controls
              // Voice segments + SFX overlap; 0 = no shared-tag pool (the play click unlocks audio).
              numberOfSharedAudioTags={0}
              style={{width: '100%', aspectRatio: '16 / 9'}}
            />
          </div>
          <Timeline edl={edl} tl={tl} frame={frame} now={now} onSeek={seekSource} />
        </section>
        <aside>
          <nav>
            {TABS.map(([id, label]) => (
              <button key={id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>
                {label}
              </button>
            ))}
          </nav>
          <div className="panel">
            {tab === 'cuts' && <CutsPanel ctx={ctx} />}
            {tab === 'gfx' && <GfxPanel ctx={ctx} />}
            {tab === 'shots' && <ShotsPanel ctx={ctx} />}
            {tab === 'brand' && <BrandPanel ctx={ctx} />}
            {tab === 'audio' && <AudioPanel ctx={ctx} />}
          </div>
        </aside>
      </main>
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
};
