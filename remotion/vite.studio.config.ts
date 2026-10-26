// Montage dashboard: `npm run studio` → http://127.0.0.1:5190
// The API below is the only thing that touches disk: edl.json / themes / the pipeline scripts.
import {defineConfig, Plugin} from 'vite';
import react from '@vitejs/plugin-react';
import {spawn, execFile} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import type {IncomingMessage, ServerResponse} from 'node:http';

const HERE = __dirname;
const ROOT = path.resolve(HERE, '..'); // marketing workspace
const EPISODES = path.join(ROOT, 'montage', 'episodes');
const THEMES = path.join(HERE, 'public', 'themes');
const PIPELINE = path.join(ROOT, 'montage', 'pipeline');
const SAFE = /^[\w.-]+$/;

type Job = {id: string; kind: string; episode: string; status: 'running' | 'done' | 'error'; log: string[]; progress: number; started: number};
const jobs = new Map<string, Job>();

const send = (res: ServerResponse, code: number, body: unknown) => {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(body));
};
const readBody = (req: IncomingMessage) =>
  new Promise<any>((ok, bad) => {
    let s = '';
    req.on('data', (c) => (s += c));
    req.on('end', () => {
      try {
        ok(s ? JSON.parse(s) : {});
      } catch (e) {
        bad(e);
      }
    });
  });
const editDir = (ep: string) => path.join(EPISODES, ep, 'edit');

function runJob(kind: string, episode: string, script: string): Job {
  const job: Job = {id: `${kind}-${Date.now()}`, kind, episode, status: 'running', log: [], progress: 0, started: Date.now()};
  jobs.set(job.id, job);
  const p = spawn('python3', [path.join(PIPELINE, script), '--episode', episode], {cwd: ROOT});
  const onData = (b: Buffer) => {
    for (const line of b.toString().split(/\r?\n/)) {
      if (!line.trim()) continue;
      job.log.push(line);
      if (job.log.length > 400) job.log.shift();
      const m = line.match(/Rendered (\d+)\/(\d+)/);
      if (m) job.progress = Number(m[1]) / Number(m[2]);
    }
  };
  p.stdout.on('data', onData);
  p.stderr.on('data', onData);
  p.on('close', (code) => {
    job.status = code === 0 ? 'done' : 'error';
    if (code === 0) job.progress = 1;
  });
  return job;
}

function serveFile(req: IncomingMessage, res: ServerResponse, file: string) {
  if (!fs.existsSync(file)) return send(res, 404, {error: 'not found'});
  const size = fs.statSync(file).size;
  const m = (req.headers.range || '').match(/bytes=(\d*)-(\d*)/);
  res.setHeader('Content-Type', 'video/mp4');
  res.setHeader('Accept-Ranges', 'bytes');
  if (m) {
    const start = m[1] ? Number(m[1]) : 0;
    const end = m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
    res.statusCode = 206;
    res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`);
    res.setHeader('Content-Length', end - start + 1);
    fs.createReadStream(file, {start, end}).pipe(res);
  } else {
    res.setHeader('Content-Length', size);
    fs.createReadStream(file).pipe(res);
  }
}

function api(): Plugin {
  return {
    name: 'montage-api',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url || '/', 'http://x');
        if (!url.pathname.startsWith('/api/')) return next();
        const parts = url.pathname.split('/').filter(Boolean).slice(1).map(decodeURIComponent);
        if (parts.some((p) => !SAFE.test(p))) return send(res, 400, {error: 'bad path'});
        try {
          const [what, name, action, extra] = parts;
          if (what === 'episodes') {
            const list = fs.readdirSync(EPISODES).filter((d) => fs.existsSync(path.join(editDir(d), 'edl.json'))).sort().reverse();
            return send(res, 200, list);
          }
          if (what === 'episode' && name) {
            const dir = editDir(name);
            if (!action && req.method === 'GET') {
              const read = (f: string) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
              return send(res, 200, {edl: read('edl.json'), words: read('words.json').words, outputs: ['youtube.mp4', 'reel.mp4'].filter((f) => fs.existsSync(path.join(EPISODES, name, f)))});
            }
            if (action === 'edl' && req.method === 'PUT') {
              const edl = await readBody(req);
              fs.copyFileSync(path.join(dir, 'edl.json'), path.join(dir, 'edl.backup.json'));
              fs.writeFileSync(path.join(dir, 'edl.json'), JSON.stringify(edl, null, 1));
              return send(res, 200, {ok: true});
            }
            if (action === 'voice' && req.method === 'POST') return send(res, 200, runJob('voice', name, 'voice.py'));
            if (action === 'roughcut' && req.method === 'POST') return send(res, 200, runJob('roughcut', name, 'roughcut.py'));
            if (action === 'render' && req.method === 'POST') {
              const busy = [...jobs.values()].find((j) => j.kind === 'render' && j.status === 'running');
              if (busy) return send(res, 409, busy);
              return send(res, 200, runJob('render', name, 'render.py'));
            }
            if (action === 'output' && extra) return serveFile(req, res, path.join(EPISODES, name, extra));
            if (action === 'reveal' && req.method === 'POST') {
              execFile('open', ['-R', path.join(EPISODES, name, extra || 'youtube.mp4')]);
              return send(res, 200, {ok: true});
            }
          }
          if (what === 'job' && name) {
            const j = jobs.get(name);
            return j ? send(res, 200, {...j, log: j.log.slice(-40)}) : send(res, 404, {error: 'no job'});
          }
          if (what === 'themes') {
            return send(res, 200, fs.readdirSync(THEMES).filter((f) => f.endsWith('.json')).map((f) => f.slice(0, -5)));
          }
          if (what === 'theme' && name) {
            const file = path.join(THEMES, `${name}.json`);
            if (req.method === 'PUT') {
              fs.writeFileSync(file, JSON.stringify(await readBody(req), null, 2) + '\n');
              return send(res, 200, {ok: true});
            }
            return send(res, 200, JSON.parse(fs.readFileSync(file, 'utf8')));
          }
          return send(res, 404, {error: 'unknown endpoint'});
        } catch (e) {
          return send(res, 500, {error: String(e)});
        }
      });
    },
  };
}

export default defineConfig({
  root: path.join(HERE, 'studio'),
  publicDir: path.join(HERE, 'public'),
  plugins: [react(), api()],
  server: {host: '127.0.0.1', port: Number(process.env.PORT) || 5190, fs: {allow: [HERE, ROOT]}},
});
