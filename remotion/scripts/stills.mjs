// Render a contact sheet of stills for an episode in one bundle.
// node scripts/stills.mjs <episode> <outDir> <frame> [frame...]
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import path from 'node:path';

const [episode, outDir, ...frames] = process.argv.slice(2);
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
const inputProps = {episode};
const composition = await selectComposition({serveUrl, id: 'EpisodeYouTube', inputProps});
for (const f of frames) {
  await renderStill({serveUrl, composition, inputProps, frame: Number(f), output: path.join(outDir, `f${f}.jpg`), imageFormat: 'jpeg'});
  process.stdout.write(`${f} `);
}
console.log(`\ntotal ${composition.durationInFrames} frames`);
