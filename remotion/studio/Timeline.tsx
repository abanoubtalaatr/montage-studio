// Source timeline: what is cut, what plays as the hook, which layout is on, where graphics land.
import React, {useRef} from 'react';
import {Edl, Timeline as TL} from '../src/episode/timeline';

export const KIND_COLOR: Record<string, string> = {
  slate: '#8A6FD1', false_start: '#E0607E', repeat: '#E58A3C', filler: '#D9A400',
  setup: '#6C7A89', pause: '#4A5068', manual: '#FF5D73', speed: '#5B57FF',
};

export const Timeline: React.FC<{edl: Edl; tl: TL; frame: number; now: number; onSeek: (t: number) => void}> = ({edl, now, onSeek}) => {
  const ref = useRef<HTMLDivElement>(null);
  const dur = edl.duration_s;
  const pct = (t: number) => `${(t / dur) * 100}%`;
  const click = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    onSeek(((e.clientX - r.left) / r.width) * dur);
  };
  const shots = [...edl.shots].sort((a, b) => a.at - b.at);
  const ticks = Array.from({length: Math.floor(dur / 10) + 1}, (_, i) => i * 10);
  return (
    <div className="timeline" dir="ltr">
      <div className="rows" ref={ref} onClick={click}>
        <div className="row label-row">
          {ticks.map((t) => (
            <span key={t} className="tick" style={{left: pct(t)}}>
              {Math.floor(t / 60)}:{String(t % 60).padStart(2, '0')}
            </span>
          ))}
        </div>
        <div className="row" title="اللقطات">
          {shots.map((s, i) => (
            <div
              key={i}
              className={`shot ${s.layout}`}
              style={{left: pct(s.at), width: pct((shots[i + 1]?.at ?? dur) - s.at)}}
            >
              {s.layout === 'talk' ? 'كاميرا' : `شاشة ${s.zoom ?? 1}×`}
            </div>
          ))}
        </div>
        <div className="row" title="القص">
          {edl.cuts.map((c) => (
            <div
              key={c.id}
              className={`blk ${c.on === false ? 'off' : ''}`}
              title={`${c.kind}: ${c.reason ?? ''}`}
              style={{left: pct(c.start), width: pct(c.end - c.start), background: KIND_COLOR[c.kind ?? 'manual'] ?? '#FF5D73'}}
            />
          ))}
          {edl.hook.map((h) => (
            <div key={h.id} className={`blk hook ${h.on === false ? 'off' : ''}`} style={{left: pct(h.start), width: pct(h.end - h.start)}} />
          ))}
        </div>
        <div className="row" title="الجرافيك">
          {edl.gfx
            .filter((g) => g.at !== undefined)
            .map((g) => (
              <div
                key={g.id}
                className={`gfx ${g.type} ${g.on === false ? 'off' : ''}`}
                style={{left: pct(g.at!), width: g.end ? pct(g.end - g.at!) : g.dur ? pct(g.dur) : undefined}}
                title={`${g.type}: ${g.text ?? g.title ?? ''}`}
              />
            ))}
        </div>
        <div className="head" style={{left: pct(now)}} />
      </div>
    </div>
  );
};
