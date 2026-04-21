#!/usr/bin/env node
// Static hero PNG export. Retina-crisp via deviceScaleFactor: 2.
// Usage: node scripts/screenshot.js --html <path> --out hero.png --width 1200 --height 675 [--seek 0]

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
const HTML = flag('html');
const OUT = flag('out', 'hero.png');
const WIDTH = Number(flag('width', 1200));
const HEIGHT = Number(flag('height', 675));
const SEEK = flag('seek', null);

if (!HTML || !fs.existsSync(HTML)) {
  console.error('Usage: node scripts/screenshot.js --html <path> --out hero.png --width 1200 --height 675 [--seek <seconds>]');
  process.exit(1);
}

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--hide-scrollbars'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 2 });

  const htmlPath = path.resolve(HTML).replace(/\\/g, '/');
  await page.goto('file:///' + htmlPath, { waitUntil: 'networkidle0' });
  await page.evaluateHandle('document.fonts.ready');
  await new Promise(r => setTimeout(r, 500));

  if (SEEK !== null) {
    await page.evaluate((s) => window.seekTo && window.seekTo(Number(s)), SEEK);
    await new Promise(r => setTimeout(r, 200));
  }

  await page.screenshot({
    path: path.resolve(OUT),
    type: 'png',
    omitBackground: false,
    // Explicit clip so the captured region is always (0,0,W,H) regardless of
    // body centering, scroll offset, or stray margin. Prevents preview-vs-export drift.
    clip: { x: 0, y: 0, width: WIDTH, height: HEIGHT },
  });
  await browser.close();

  const bytes = fs.statSync(OUT).size;
  console.log(`Wrote ${OUT} (${(bytes / 1024).toFixed(1)} KB, ${WIDTH}×${HEIGHT} @2x).`);
})();
