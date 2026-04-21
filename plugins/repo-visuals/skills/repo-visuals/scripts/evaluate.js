#!/usr/bin/env node
// Code-evaluated scorecard rows for Phase 6. Emits JSON to stdout.
// Usage: node scripts/evaluate.js <path-to-hero.gif-or-png> [--width 1200] [--height 675] [--min-duration 15] [--max-duration 25]
// Format detected by file extension. PNG skips duration/seam/palette rows.
// Requires: ffmpeg + ffprobe (on PATH or in <repo>/bin/) for GIF eval. Optional: gifsicle for palette count.

const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const args = process.argv.slice(2);
const file = args[0];
if (!file || !fs.existsSync(file)) {
  console.error('Usage: node scripts/evaluate.js <path-to-hero.gif-or-png> [--width N] [--height N] [--min-duration S] [--max-duration S]');
  process.exit(1);
}
const ext = path.extname(file).toLowerCase();
const isGif = ext === '.gif';
const isPng = ext === '.png';
if (!isGif && !isPng) {
  console.error(`Unsupported format: ${ext}. Expected .gif or .png.`);
  process.exit(1);
}

function flag(name, def) {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? Number(args[i + 1]) : def;
}
const targetW = flag('width', 1200);
const targetH = flag('height', 675);
const minDur = flag('min-duration', 15);
const maxDur = flag('max-duration', 25);

const SIZE_TARGET = isGif ? 10 * 1024 * 1024 : 500 * 1024;
const SIZE_CAP = isGif ? 15 * 1024 * 1024 : 1024 * 1024;
const SEAM_WARN = 0.02;

const LOCAL_BIN = path.resolve(__dirname, '..', 'bin');
function resolveBin(name) {
  for (const ext of ['', '.exe']) {
    const p = path.join(LOCAL_BIN, name + ext);
    if (fs.existsSync(p)) return p;
  }
  return name;
}
const FFMPEG = resolveBin('ffmpeg');
const FFPROBE = resolveBin('ffprobe');
const GIFSICLE = resolveBin('gifsicle');

function run(cmd, cmdArgs) {
  const res = spawnSync(cmd, cmdArgs, { encoding: 'utf8' });
  return { code: res.status, stdout: res.stdout || '', stderr: res.stderr || '', err: res.error };
}
function label(s) { return ['', 'Poor', 'Weak', 'OK', 'Strong', 'Excellent'][s] || String(s); }
function row(score, note) { return { score, label: label(score), note }; }

// --- file size
const bytes = fs.statSync(file).size;
const human = isGif ? `${(bytes / 1024 / 1024).toFixed(2)} MB` : `${(bytes / 1024).toFixed(1)} KB`;
const targetHuman = isGif ? `${SIZE_TARGET / 1024 / 1024} MB` : `${SIZE_TARGET / 1024} KB`;
const capHuman = isGif ? `${SIZE_CAP / 1024 / 1024} MB` : `${SIZE_CAP / 1024} KB`;
const sizeRow = bytes <= SIZE_TARGET
  ? row(5, `${human} (under ${targetHuman} target).`)
  : bytes <= SIZE_CAP
  ? row(3, `${human} (over target, under ${capHuman} cap).`)
  : row(1, `${human} (over hard cap).`);

// --- dimensions + (gif only) duration
let dimsRow, durRow = null, width = null, height = null, duration = null;
const probe = run(FFPROBE, [
  '-v', 'error',
  '-select_streams', 'v:0',
  '-show_entries', 'stream=width,height:format=duration',
  '-of', 'json',
  file,
]);
if (probe.err || probe.code !== 0) {
  dimsRow = row(3, `ffprobe unavailable (${probe.err ? probe.err.code : 'exit ' + probe.code}); manual check advised.`);
  if (isGif) durRow = row(3, 'ffprobe unavailable; manual check advised.');
} else {
  const j = JSON.parse(probe.stdout);
  width = j.streams[0].width;
  height = j.streams[0].height;
  duration = Number(j.format.duration);
  // PNG at @2x is acceptable: accept either exact match or 2× match.
  const exact = width === targetW && height === targetH;
  const retina = isPng && width === targetW * 2 && height === targetH * 2;
  dimsRow = (exact || retina)
    ? row(5, `${width}×${height}${retina ? ' (@2x retina)' : ''} matches spec.`)
    : row(1, `${width}×${height} does not match spec ${targetW}×${targetH}${isPng ? ` (or ${targetW * 2}×${targetH * 2} @2x)` : ''}.`);
  if (isGif) {
    durRow = (duration >= minDur && duration <= maxDur)
      ? row(5, `${duration.toFixed(1)} s inside ${minDur}–${maxDur} s band.`)
      : row(2, `${duration.toFixed(1)} s outside ${minDur}–${maxDur} s band.`);
  }
}

// --- loop seam (gif only)
let seamRow = null;
if (isGif) {
if (probe.err || probe.code !== 0 || duration == null) {
  seamRow = row(3, 'ffmpeg unavailable; manual seam check advised.');
} else {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'repo-visuals-eval-'));
  const first = path.join(tmp, 'first.png');
  const last = path.join(tmp, 'last.png');
  const r1 = run(FFMPEG, ['-y', '-loglevel', 'error', '-i', file, '-vf', 'select=eq(n\\,0)', '-update', '1', '-frames:v', '1', first]);
  const r2 = run(FFMPEG, ['-y', '-loglevel', 'error', '-sseof', '-0.1', '-i', file, '-update', '1', '-frames:v', '1', last]);
  if (r1.code !== 0 || r2.code !== 0 || !fs.existsSync(first) || !fs.existsSync(last)) {
    seamRow = row(3, 'Could not extract first/last frame; manual seam check advised.');
  } else {
    const diff = run(FFMPEG, [
      '-i', first, '-i', last,
      '-lavfi', 'blend=all_mode=difference,signalstats,metadata=mode=print:file=-',
      '-f', 'null', '-',
    ]);
    const haystack = (diff.stdout || '') + '\n' + (diff.stderr || '');
    const m = haystack.match(/lavfi\.signalstats\.YAVG=([\d.]+)/) || haystack.match(/YAVG[:= ]([\d.]+)/);
    if (!m) {
      seamRow = row(3, 'Seam diff unreadable from ffmpeg; manual check advised.');
    } else {
      const frac = Number(m[1]) / 255;
      seamRow = frac <= SEAM_WARN
        ? row(5, `${(frac * 100).toFixed(2)}% first/last-frame diff (threshold ${(SEAM_WARN * 100).toFixed(1)}%).`)
        : frac <= SEAM_WARN * 2
        ? row(3, `${(frac * 100).toFixed(2)}% first/last-frame diff (above ${(SEAM_WARN * 100).toFixed(1)}% threshold).`)
        : row(2, `${(frac * 100).toFixed(2)}% first/last-frame diff (visible seam likely).`);
    }
  }
  try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {}
}
}

// --- palette (gif only, gifsicle optional)
let paletteRow = null;
if (isGif) {
  const gs = run(GIFSICLE, ['--info', file]);
  if (gs.err || gs.code !== 0) {
    paletteRow = row(3, 'gifsicle not installed; palette check skipped.');
  } else {
    const m = gs.stdout.match(/global color table \[(\d+)\]/i) || gs.stdout.match(/(\d+)\s+colors?/i);
    const colors = m ? Number(m[1]) : null;
    paletteRow = colors != null
      ? (colors <= 256 ? row(5, `${colors} colors in palette.`) : row(2, `${colors} colors — unusual for GIF.`))
      : row(3, 'gifsicle output parsed but color count not found.');
  }
}

const rows = { 'File size': sizeRow, 'Dimensions': dimsRow };
if (isGif) {
  rows['Loop duration'] = durRow;
  rows['Loop seam'] = seamRow;
  rows['Palette size'] = paletteRow;
}

const scorecard = {
  path: path.resolve(file),
  format: isGif ? 'gif' : 'png',
  bytes,
  width,
  height,
  duration_s: duration,
  rows,
};
const vals = Object.values(rows).filter(Boolean);
scorecard.average = vals.reduce((a, r) => a + r.score, 0) / vals.length;

console.log(JSON.stringify(scorecard, null, 2));
