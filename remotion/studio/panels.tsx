// Editor panels. Each one edits edl.json (or the theme) through ctx.setEdl / ctx.setTheme.
import React, {useState} from 'react';
import type {Ctx} from './App';
import {Gfx, Range} from '../src/episode/timeline';
import {FONTS} from '../src/episode/theme';
import {KIND_COLOR} from './Timeline';

const KIND: Record<string, string> = {
  slate: 'كواليس', false_start: 'بداية غلط', repeat: 'تكرار', filler: 'حشو', setup: 'كلام كواليس', pause: 'سكتة', manual: 'قص يدوي',
};
const uid = (p: string) => `${p}${Date.now().toString(36)}`;
const r2 = (x: number) => Math.round(x * 100) / 100;
const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(2).padStart(5, '0')}`;

const Num: React.FC<{value: number; step?: number; min?: number; max?: number; onChange: (v: number) => void; w?: number}> = ({value, step = 0.05, min, max, onChange, w = 84}) => (
  <input type="number" className="num" style={{width: w}} value={value} step={step} min={min} max={max} onChange={(e) => onChange(Number(e.target.value))} />
);
const Toggle: React.FC<{on: boolean; onChange: (v: boolean) => void}> = ({on, onChange}) => (
  <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />
);

/* ------------------------------------------------------------------ cuts */

export const CutsPanel: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {edl, words, setEdl, seekSource, now} = ctx;
  const [sel, setSel] = useState<[number, number] | null>(null);
  const [showPauses, setShowPauses] = useState(false);
  // A word counts as cut when a cut covers most of it (pauses inside long words don't).
  const cutOf = (a: number, b: number) =>
    edl.cuts.find((c) => c.on !== false && Math.min(b, c.end) - Math.max(a, c.start) > 0.6 * (b - a));
  const span = sel ? [Math.min(...sel), Math.max(...sel)] : null;
  const selText = span ? words.slice(span[0], span[1] + 1).map((w) => w.w).join(' ') : '';
  const selRange = span ? {start: r2(words[span[0]].start - 0.03), end: r2(words[span[1]].end + 0.03)} : null;

  const clickWord = (i: number, e: React.MouseEvent) => {
    if (e.shiftKey && sel) setSel([sel[0], i]);
    else setSel([i, i]);
    seekSource(words[i].start - 0.2);
  };
  const update = (id: string, patch: Partial<Range>) =>
    setEdl((e) => ({...e, cuts: e.cuts.map((c) => (c.id === id ? {...c, ...patch} : c))}));

  const editorial = edl.cuts.filter((c) => c.kind !== 'pause');
  const pauses = edl.cuts.filter((c) => c.kind === 'pause');
  const pausesOn = pauses.filter((p) => p.on !== false).length;

  return (
    <div>
      <p className="hint">دوس على كلمة علشان تروح لها، و Shift + كلمة تانية علشان تختار جملة. بعدها اختار تعمل إيه بيها.</p>
      <div className="words">
        {words.map((w, i) => {
          const c = cutOf(w.start, w.end);
          const selected = span && i >= span[0] && i <= span[1];
          const current = now >= w.start && now < w.end;
          return (
            <span
              key={i}
              className={`w ${c ? 'cut' : ''} ${selected ? 'sel' : ''} ${current ? 'now' : ''}`}
              style={c ? {textDecorationColor: KIND_COLOR[c.kind ?? 'manual']} : undefined}
              title={`${fmt(w.start)}${c ? ' · ' + (KIND[c.kind ?? 'manual'] ?? c.kind) : ''}`}
              onClick={(e) => clickWord(i, e)}
            >
              {w.w}{' '}
            </span>
          );
        })}
      </div>
      {span && selRange && (
        <div className="selbar">
          <div className="seltext">«{selText}»</div>
          <div className="row-actions">
            <button
              className="danger"
              onClick={() => {
                setEdl((e) => ({...e, cuts: [...e.cuts, {id: uid('u'), ...selRange, kind: 'manual', by: 'user', on: true, reason: `«${selText}»`}].sort((a, b) => a.start - b.start)}));
                setSel(null);
              }}
            >
              ✂ اقطع ده
            </button>
            <button
              onClick={() => {
                // Restore: switch off every cut that overlaps the selection.
                setEdl((e) => ({...e, cuts: e.cuts.map((c) => (c.start < selRange.end && selRange.start < c.end ? {...c, on: false} : c))}));
                setSel(null);
              }}
            >
              ↺ رجّعه
            </button>
            <button
              onClick={() => {
                setEdl((e) => ({
                  ...e,
                  gfx: [...e.gfx, {id: uid('k'), type: 'keyword', at: words[span[0]].start, dur: Math.max(1.8, selRange.end - selRange.start + 1), text: selText}],
                }));
                setSel(null);
              }}
            >
              ✦ اعمله Keyword
            </button>
            <button
              onClick={() => {
                setEdl((e) => ({...e, hook: [{id: uid('h'), ...selRange, on: true, by: 'user', reason: `«${selText}»`}]}));
                setSel(null);
              }}
            >
              ★ خليه الـ Hook
            </button>
            <button onClick={() => setSel(null)}>إلغاء</button>
          </div>
        </div>
      )}

      <h3>البداية (Hook)</h3>
      {edl.hook.map((h) => (
        <div key={h.id} className="item" style={{borderInlineStartColor: '#FFC857'}}>
          <Toggle on={h.on !== false} onChange={(v) => setEdl((e) => ({...e, hook: e.hook.map((x) => (x.id === h.id ? {...x, on: v} : x))}))} />
          <div className="grow">
            <div className="row-fields">
              من <Num value={h.start} onChange={(v) => setEdl((e) => ({...e, hook: e.hook.map((x) => (x.id === h.id ? {...x, start: v} : x))}))} />
              لـ <Num value={h.end} onChange={(v) => setEdl((e) => ({...e, hook: e.hook.map((x) => (x.id === h.id ? {...x, end: v} : x))}))} />
            </div>
            <div className="reason">{h.reason}</div>
          </div>
          <button onClick={() => seekSource(h.start)}>▶</button>
        </div>
      ))}

      <h3>القطعات ({editorial.filter((c) => c.on !== false).length})</h3>
      {editorial.map((c) => (
        <div key={c.id} className={`item ${c.on === false ? 'off' : ''}`} style={{borderInlineStartColor: KIND_COLOR[c.kind ?? 'manual']}}>
          <Toggle on={c.on !== false} onChange={(v) => update(c.id, {on: v})} />
          <div className="grow">
            <div className="row-fields">
              <b>{KIND[c.kind ?? 'manual'] ?? c.kind}</b>
              من <Num value={c.start} step={0.02} onChange={(v) => update(c.id, {start: v})} />
              لـ <Num value={c.end} step={0.02} onChange={(v) => update(c.id, {end: v})} />
              <span className="muted num">{(c.end - c.start).toFixed(2)}s</span>
            </div>
            <div className="reason">{c.reason}</div>
          </div>
          <button onClick={() => seekSource(c.start - 2)} title="شغّل من قبلها بثانيتين">▶</button>
          <button className="ghost" onClick={() => setEdl((e) => ({...e, cuts: e.cuts.filter((x) => x.id !== c.id)}))}>🗑</button>
        </div>
      ))}

      <h3>
        السكتات ({pausesOn}/{pauses.length})
        <button onClick={() => setEdl((e) => ({...e, cuts: e.cuts.map((c) => (c.kind === 'pause' ? {...c, on: pausesOn === 0} : c))}))}>
          {pausesOn ? 'سيبهم كلهم' : 'قصّرهم كلهم'}
        </button>
        <button onClick={() => setShowPauses(!showPauses)}>{showPauses ? 'اخفي' : 'اعرض'}</button>
        <button onClick={() => ctx.runJob('roughcut')} disabled={!!ctx.busy}>احسبهم من جديد</button>
      </h3>
      {showPauses &&
        pauses.map((c) => (
          <div key={c.id} className={`item small ${c.on === false ? 'off' : ''}`}>
            <Toggle on={c.on !== false} onChange={(v) => update(c.id, {on: v})} />
            <span className="num grow">
              {fmt(c.start)} → {fmt(c.end)}
            </span>
            <button onClick={() => seekSource(c.start - 1.5)}>▶</button>
          </div>
        ))}
    </div>
  );
};

/* ------------------------------------------------------------------ graphics */

const FIELDS: Record<string, [string, string, 'text' | 'num'][]> = {
  keyword: [['text', 'النص', 'text'], ['sub', 'سطر صغير', 'text'], ['icon', 'أيقونة', 'text'], ['at', 'يبدأ', 'num'], ['dur', 'المدة', 'num']],
  chapter: [['num', 'الرقم', 'text'], ['title', 'العنوان', 'text'], ['at', 'يبدأ', 'num']],
  list: [['title', 'العنوان', 'text'], ['at', 'يبدأ', 'num'], ['dur', 'المدة', 'num']],
  lower_third: [['title', 'الاسم', 'text'], ['sub', 'الوصف', 'text'], ['at', 'يبدأ', 'num'], ['dur', 'المدة', 'num']],
  prompt: [['label', 'العنوان', 'text'], ['at', 'يبدأ', 'num'], ['end', 'ينتهي', 'num']],
  sting: [['dur', 'المدة', 'num']],
  outro: [['title', 'العنوان', 'text'], ['sub', 'الجملة', 'text'], ['dur', 'المدة', 'num']],
};
const TYPE_LABEL: Record<string, string> = {
  keyword: 'كلمة على الشاشة', chapter: 'فصل', list: 'قايمة', lower_third: 'الاسم', prompt: 'كارت البرومبت', sting: 'الشعار', outro: 'النهاية',
};

export const GfxPanel: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {edl, setEdl, seekSource, now} = ctx;
  const [open, setOpen] = useState<string | null>(null);
  const set = (id: string, patch: Partial<Gfx>) => setEdl((e) => ({...e, gfx: e.gfx.map((g) => (g.id === id ? {...g, ...patch} : g))}));
  const add = (g: Gfx) => {
    setEdl((e) => ({...e, gfx: [...e.gfx, g]}));
    setOpen(g.id);
  };
  const sorted = [...edl.gfx].sort((a, b) => (a.at ?? (a.type === 'sting' ? -1 : 1e9)) - (b.at ?? (b.type === 'sting' ? -1 : 1e9)));
  return (
    <div>
      <div className="row-actions">
        <button onClick={() => add({id: uid('k'), type: 'keyword', at: r2(now), dur: 2, text: 'كلمة جديدة'})}>+ كلمة هنا</button>
        <button onClick={() => add({id: uid('c'), type: 'chapter', at: r2(now), num: '0' + (edl.gfx.filter((g) => g.type === 'chapter').length + 1), title: 'فصل جديد'})}>+ فصل هنا</button>
        <button onClick={() => add({id: uid('l'), type: 'list', at: r2(now), dur: 4, title: 'قايمة', items: [{at: r2(now + 0.5), text: 'أول حاجة'}]})}>+ قايمة هنا</button>
      </div>
      <p className="hint">«هنا» يعني مكان المؤشر في الفيديو دلوقتي. التوقيتات بالثواني على التسجيل الأصلي.</p>
      {sorted.map((g) => (
        <div key={g.id} className={`item col ${g.on === false ? 'off' : ''}`}>
          <div className="item-head" onClick={() => setOpen(open === g.id ? null : g.id)}>
            <Toggle on={g.on !== false} onChange={(v) => set(g.id, {on: v})} />
            <span className="tag">{TYPE_LABEL[g.type] ?? g.type}</span>
            <span className="grow ellipsis">{g.text ?? g.title ?? g.label ?? ''}</span>
            {g.at !== undefined && <span className="muted num">{fmt(g.at)}</span>}
            {g.at !== undefined && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  seekSource(g.at!);
                }}
              >
                ▶
              </button>
            )}
          </div>
          {open === g.id && (
            <div className="fields">
              {(FIELDS[g.type] ?? []).map(([k, label, kind]) => (
                <label key={k}>
                  <span>{label}</span>
                  {kind === 'num' ? (
                    <span className="row-fields">
                      <Num value={g[k] ?? 0} onChange={(v) => set(g.id, {[k]: v})} />
                      {(k === 'at' || k === 'end') && <button onClick={() => set(g.id, {[k]: r2(now)})}>= هنا</button>}
                    </span>
                  ) : (
                    <input value={g[k] ?? ''} onChange={(e) => set(g.id, {[k]: e.target.value})} />
                  )}
                </label>
              ))}
              {g.type === 'list' && (
                <div className="subitems">
                  {(g.items as {at: number; text: string}[]).map((it, i) => (
                    <div key={i} className="row-fields">
                      <input value={it.text} onChange={(e) => set(g.id, {items: g.items.map((x: any, j: number) => (j === i ? {...x, text: e.target.value} : x))})} />
                      <Num value={it.at} onChange={(v) => set(g.id, {items: g.items.map((x: any, j: number) => (j === i ? {...x, at: v} : x))})} />
                      <button onClick={() => set(g.id, {items: g.items.map((x: any, j: number) => (j === i ? {...x, at: r2(now)} : x))})}>= هنا</button>
                      <button className="ghost" onClick={() => set(g.id, {items: g.items.filter((_: any, j: number) => j !== i)})}>🗑</button>
                    </div>
                  ))}
                  <button onClick={() => set(g.id, {items: [...g.items, {at: r2(now), text: 'عنصر'}]})}>+ عنصر هنا</button>
                </div>
              )}
              <button className="danger" onClick={() => setEdl((e) => ({...e, gfx: e.gfx.filter((x) => x.id !== g.id)}))}>
                امسح ده
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

/* ------------------------------------------------------------------ shots */

export const ShotsPanel: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {edl, setEdl, seekSource, now} = ctx;
  const shots = edl.shots.map((s, i) => ({s, i})).sort((a, b) => a.s.at - b.s.at);
  const set = (i: number, patch: any) => setEdl((e) => ({...e, shots: e.shots.map((s, j) => (j === i ? {...s, ...patch} : s))}));
  return (
    <div>
      <div className="row-actions">
        <button onClick={() => setEdl((e) => ({...e, shots: [...e.shots, {at: r2(now), layout: 'screen', zoom: 1.6, focus: [0.5, 0.5]}]}))}>+ شاشة من هنا</button>
        <button onClick={() => setEdl((e) => ({...e, shots: [...e.shots, {at: r2(now), layout: 'talk'}]}))}>+ كاميرا من هنا</button>
      </div>
      <p className="hint">كل لقطة بتفضل لحد اللقطة اللي بعدها. الـ Zoom ومركزه بيتحكموا في الجزء اللي بيكبر من الشاشة.</p>
      {shots.map(({s, i}) => (
        <div key={i} className="item col">
          <div className="item-head">
            <select value={s.layout} onChange={(e) => set(i, {layout: e.target.value})}>
              <option value="talk">كاميرا</option>
              <option value="screen">شاشة + كاميرا صغيرة</option>
            </select>
            من <Num value={s.at} onChange={(v) => set(i, {at: v})} />
            <button onClick={() => set(i, {at: r2(now)})}>= هنا</button>
            <div className="grow" />
            <button onClick={() => seekSource(s.at)}>▶</button>
            <button className="ghost" onClick={() => setEdl((e) => ({...e, shots: e.shots.filter((_, j) => j !== i)}))}>🗑</button>
          </div>
          {s.layout === 'screen' && (
            <div className="fields">
              <label>
                <span>Zoom {(s.zoom ?? 1).toFixed(2)}×</span>
                <input type="range" min={1} max={3} step={0.05} value={s.zoom ?? 1} onChange={(e) => set(i, {zoom: Number(e.target.value)})} />
              </label>
              <label>
                <span>المركز أفقي</span>
                <input type="range" min={0} max={1} step={0.01} value={s.focus?.[0] ?? 0.5} onChange={(e) => set(i, {focus: [Number(e.target.value), s.focus?.[1] ?? 0.5]})} />
              </label>
              <label>
                <span>المركز رأسي</span>
                <input type="range" min={0} max={1} step={0.01} value={s.focus?.[1] ?? 0.5} onChange={(e) => set(i, {focus: [s.focus?.[0] ?? 0.5, Number(e.target.value)]})} />
              </label>
              <label>
                <span>عنوان الشباك</span>
                <input value={(s as any).title ?? ''} onChange={(e) => set(i, {title: e.target.value})} />
              </label>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

/* ------------------------------------------------------------------ brand */

const GROUP: Record<string, string> = {
  colors: 'الألوان', fonts: 'الخطوط', identity: 'الهوية', captions: 'الترجمة', keywords: 'الكلمات', music: 'المزيكا', sfx: 'المؤثرات',
};
const COLOR_LABEL: Record<string, string> = {
  bg: 'الخلفية', glow: 'التوهّج', primary: 'الأساسي', accent: 'المميّز', text: 'النص', muted: 'نص هادي', card: 'الكروت', line: 'الخطوط', paper: 'ورق', ink: 'حبر',
};

export const BrandPanel: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {theme, setTheme} = ctx;
  const setPath = (path: string[], v: unknown) =>
    setTheme((t) => {
      const copy: any = t;
      let o = copy;
      path.slice(0, -1).forEach((k) => (o = o[k]));
      o[path[path.length - 1]] = v;
      return copy;
    });
  const field = (path: string[], v: any) => {
    const key = path[path.length - 1];
    if (path[0] === 'fonts')
      return (
        <select value={v} onChange={(e) => setPath(path, e.target.value)}>
          {Object.keys(FONTS).map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
      );
    if (typeof v === 'boolean') return <Toggle on={v} onChange={(x) => setPath(path, x)} />;
    if (typeof v === 'number')
      return key === 'volume' ? (
        <span className="row-fields">
          <input type="range" min={0} max={1} step={0.01} value={v} onChange={(e) => setPath(path, Number(e.target.value))} />
          <span className="num muted">{v.toFixed(2)}</span>
        </span>
      ) : (
        <Num value={v} step={1} onChange={(x) => setPath(path, x)} />
      );
    if (typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v))
      return (
        <span className="row-fields">
          <input type="color" value={v} onChange={(e) => setPath(path, e.target.value)} />
          <code>{v}</code>
        </span>
      );
    return <input value={v} onChange={(e) => setPath(path, e.target.value)} />;
  };
  return (
    <div>
      <p className="hint">
        الهوية دي (<code>{theme.name}</code>) بتتحفظ في <code>public/themes/{theme.name}.json</code> وبتتطبّق على كل الحلقات اللي بتستخدمها.
      </p>
      {Object.entries(theme).map(([k, v]) =>
        typeof v === 'object' && v !== null ? (
          <fieldset key={k}>
            <legend>{GROUP[k] ?? k}</legend>
            {Object.entries(v).map(([k2, v2]) => (
              <label key={k2}>
                <span>{k === 'colors' ? COLOR_LABEL[k2] ?? k2 : k2}</span>
                {field([k, k2], v2)}
              </label>
            ))}
          </fieldset>
        ) : k === 'name' || k === 'label' ? null : (
          <label key={k}>
            <span>{k}</span>
            {field([k], v)}
          </label>
        ),
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ audio */

const AUDIO: [string, string, number, number, number, number, string][] = [
  ['breath_duck_db', 'خفض صوت النَفَس والهوا بين الكلام', -40, 0, 1, -18, 'dB — كل ما يقل، النفس يختفي أكتر'],
  ['speech_db', 'حساسية كشف الكلام', 10, 32, 1, 20, 'dB تحت أعلى صوت — لو آخر الكلمات بيتاكل، زوّده'],
  ['hold_ms', 'يفضل مفتوح بعد الكلام', 40, 400, 10, 160, 'ms'],
  ['highpass_hz', 'شيل الهمهمة الواطية', 60, 160, 5, 110, 'Hz'],
];

export const AudioPanel: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {edl, setEdl, runJob, busy} = ctx;
  const a: any = edl.audio ?? {};
  return (
    <div>
      <p className="hint">التعديلات دي بتتطبّق على ملف الصوت نفسه. حرّك، وبعدها دوس «طبّق على الصوت»، والمعاينة هتتحدّث.</p>
      {AUDIO.map(([k, label, min, max, step, def, unit]) => (
        <label key={k} className="slider">
          <span>{label}</span>
          <span className="row-fields">
            <input type="range" min={min} max={max} step={step} value={a[k] ?? def} onChange={(e) => setEdl((x) => ({...x, audio: {...(x.audio ?? {}), [k]: Number(e.target.value)}}))} />
            <b className="num">{a[k] ?? def}</b>
          </span>
          <small>{unit}</small>
        </label>
      ))}
      <button className="primary" onClick={() => runJob('voice')} disabled={!!busy}>
        {busy === 'voice' ? 'بيعالج…' : 'طبّق على الصوت'}
      </button>
      <p className="hint">المزيكا والمؤثرات بتتظبط من تبويب «الهوية».</p>
    </div>
  );
};
