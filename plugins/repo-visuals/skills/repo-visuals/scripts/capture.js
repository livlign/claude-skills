// Animated capture via Puppeteer Page.startScreencast.
// Usage: node scripts/capture.js --html <path> --out <frames-dir> --manifest <frames.txt> --duration <ms> --width 1200 --height 675 [--scale 2]
// Writes numbered PNGs to <frames-dir> and an ffmpeg concat manifest to <frames.txt>.
//
// --scale defaults to 2 (retina). Current Chromium honors deviceScaleFactor during
// screencast, so frames emit at (width*scale × height*scale). The ffmpeg encode
// should lanczos-downscale to the target (width × height). See SKILL.md §4.3g for
// the zoom:2 viewport-doubling fallback if a future Chromium regresses dSF support.

const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const args = process.argv.slice(2);
function flag(name, def) {
  const i = args.indexOf(`--${name}`);
  if (i < 0) return def;
  const v = args[i + 1];
  return v === undefined ? def : v;
}

const HTML = path.resolve(flag('html', path.resolve(__dirname, 'gif-v1.html')));
const OUT = path.resolve(flag('out', path.resolve(__dirname, 'frames')));
const MANIFEST = path.resolve(flag('manifest', path.resolve(__dirname, 'frames.txt')));
const DURATION_MS = Number(flag('duration', 20700));
const WIDTH = Number(flag('width', 1200));
const HEIGHT = Number(flag('height', 675));
const SCALE = Number(flag('scale', 2));

(async () => {
  if (fs.existsSync(OUT)) fs.rmSync(OUT, { recursive: true });
  fs.mkdirSync(OUT);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--hide-scrollbars']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: SCALE });

  await page.goto('file:///' + HTML.replace(/\\/g, '/'), { waitUntil: 'networkidle0' });
  await page.evaluateHandle('document.fonts.ready');
  await new Promise(r => setTimeout(r, 300));

  const client = await page.target().createCDPSession();

  const frames = []; // { idx, ts } — timestamps are seconds since epoch (monotonic)
  let frameIdx = 0;
  let startTs = null;
  let stopped = false;

  client.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
    try { await client.send('Page.screencastFrameAck', { sessionId }); } catch {}
    if (stopped) return;
    const ts = metadata.timestamp; // seconds
    if (startTs === null) startTs = ts;
    const elapsedMs = (ts - startTs) * 1000;
    if (elapsedMs > DURATION_MS + 200) { stopped = true; return; }
    const name = `frame_${String(frameIdx).padStart(5, '0')}.png`;
    fs.writeFileSync(path.join(OUT, name), Buffer.from(data, 'base64'));
    frames.push({ name, elapsedMs });
    frameIdx++;
  });

  // Restart animation timeline right before starting the screencast.
  await page.evaluate(() => window.runLoop && window.runLoop());

  await client.send('Page.startScreencast', {
    format: 'png',
    everyNthFrame: 1
  });

  // Let it run for the full duration plus a tiny safety margin.
  await new Promise(r => setTimeout(r, DURATION_MS + 200));
  stopped = true;
  try { await client.send('Page.stopScreencast'); } catch {}
  await browser.close();

  // Write an ffmpeg concat manifest with per-frame durations from real timestamps.
  // Each line: file 'frame_00000.png' / duration <secs>. Last frame repeated.
  const lines = [];
  for (let i = 0; i < frames.length; i++) {
    const cur = frames[i];
    const nextMs = i + 1 < frames.length ? frames[i + 1].elapsedMs : DURATION_MS;
    const dur = Math.max(0.001, (nextMs - cur.elapsedMs) / 1000);
    lines.push(`file '${OUT.replace(/\\/g, '/')}/${cur.name}'`);
    lines.push(`duration ${dur.toFixed(4)}`);
  }
  // concat demuxer quirk: repeat last file with no duration
  if (frames.length) lines.push(`file '${OUT.replace(/\\/g, '/')}/${frames[frames.length - 1].name}'`);
  fs.writeFileSync(MANIFEST, lines.join('\n'));
  console.log(`Captured ${frames.length} frames across ${DURATION_MS}ms at ${SCALE}x (${WIDTH * SCALE}×${HEIGHT * SCALE}).`);
})();
