const puppeteer = require('D:/nghich/git-to-gif/node_modules/puppeteer');
const path = require('path');
const fs = require('fs');

const HTML = path.resolve(__dirname, 'index.html');
const OUT = path.resolve(__dirname, 'frames');
const MANIFEST = path.resolve(__dirname, 'frames.txt');
const WIDTH = 1200;
const HEIGHT = 675;
const DURATION_MS = 20000;

(async () => {
  if (fs.existsSync(OUT)) fs.rmSync(OUT, { recursive: true });
  fs.mkdirSync(OUT);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--hide-scrollbars']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });

  await page.goto('file:///' + HTML.replace(/\\/g, '/'), { waitUntil: 'networkidle0' });
  await page.evaluateHandle('document.fonts.ready');
  await new Promise(r => setTimeout(r, 400));

  const client = await page.target().createCDPSession();

  const frames = [];
  let frameIdx = 0;
  let startTs = null;
  let stopped = false;

  client.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
    try { await client.send('Page.screencastFrameAck', { sessionId }); } catch {}
    if (stopped) return;
    const ts = metadata.timestamp;
    if (startTs === null) startTs = ts;
    const elapsedMs = (ts - startTs) * 1000;
    if (elapsedMs > DURATION_MS + 200) { stopped = true; return; }
    const name = `frame_${String(frameIdx).padStart(5, '0')}.png`;
    fs.writeFileSync(path.join(OUT, name), Buffer.from(data, 'base64'));
    frames.push({ name, elapsedMs });
    frameIdx++;
  });

  await page.evaluate(() => window.runLoop && window.runLoop());

  await client.send('Page.startScreencast', { format: 'png', everyNthFrame: 1 });
  await new Promise(r => setTimeout(r, DURATION_MS + 200));
  stopped = true;
  try { await client.send('Page.stopScreencast'); } catch {}
  await browser.close();

  const lines = [];
  const outPosix = OUT.replace(/\\/g, '/');
  for (let i = 0; i < frames.length; i++) {
    const cur = frames[i];
    const nextMs = i + 1 < frames.length ? frames[i + 1].elapsedMs : DURATION_MS;
    const dur = Math.max(0.001, (nextMs - cur.elapsedMs) / 1000);
    lines.push(`file '${outPosix}/${cur.name}'`);
    lines.push(`duration ${dur.toFixed(4)}`);
  }
  if (frames.length) lines.push(`file '${outPosix}/${frames[frames.length - 1].name}'`);
  fs.writeFileSync(MANIFEST, lines.join('\n'));
  console.log(`Captured ${frames.length} frames over ${DURATION_MS}ms`);
})();
