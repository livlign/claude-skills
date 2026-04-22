# repo-visuals

![repo-visuals demo](./assets/hero.gif)

A Claude Code plugin for producing hero visuals — **animated GIF** or **static PNG** — for GitHub repositories.

The plugin scans the target repo, recommends a format based on the repo's identity, generates bespoke HTML via a structured discovery dialog, previews it in the browser, and exports to an optimized GIF or retina PNG.

See [`SHOWCASE.md`](./SHOWCASE.md) for heroes that landed in their target repo.

## Install

```
/plugin marketplace add livlign/claude-skills
/plugin install repo-visuals@livlign
```

After install, restart Claude Code (or start a new session) so the plugin's skills are discovered.

## Dependencies (install these yourself)

The plugin install does **not** install these — you need them on your system before running:

- **Node.js 18+**
- **puppeteer** — run `npm install` once inside the plugin directory. This downloads ~170 MB of Chromium the first time.
- **ffmpeg** + **ffprobe** (for GIF export and code-evaluated scorecard rows) — `brew install ffmpeg` / `apt install ffmpeg` / `choco install ffmpeg`.
- **gifsicle** *(optional)* — enables palette-size checks in `scripts/evaluate.js`.

`npm install` runs from the plugin's cache directory after install. If you can't find it, use `/plugin` to locate the install path, then `cd` into it and run `npm install`.

## How to run

### Standard run (no scorecard)

> Generate a hero GIF for this repo: https://github.com/owner/name

Claude asks which operating mode to use (see below), runs discovery → build → preview → export → output, and stops. No evaluation is collected.

### Dev run (with scorecard)

> Generate a hero GIF for this repo in dev mode: https://github.com/owner/name

Dev mode enables Phase 6 — a 4-rater scorecard (User / Claude / Code / AI-vision-blind). The scorecard is written to `./evaluations/runs/<YYYY-MM-DD>-<slug>.md` in your **current working directory** (not the plugin cache, which is wiped on `/plugin update`).

Enable dev mode either by saying *"dev mode"* in the prompt, or by setting `REPO_VISUALS_DEV=1` in the environment.

### Retro — improve the skill from logs

After you have a handful of dev-mode runs logged:

> Run retro on my repo-visuals evaluations

The `repo-visuals-retro` skill reads `./evaluations/runs/*.md`, spots patterns, and proposes diffs against the main skill. It proposes — it does not auto-apply.

## Operating modes

Every run, the skill asks which mode to use. This is about **how many decisions Claude asks you to make** — it does not relax craft rules.

| Mode | What **you** decide | What **Claude** decides silently | Phase 6 scorecard | Typical back-and-forths |
|---|---|---|---|---|
| **Auto** | nothing | everything (format, scenario, vibe, audience, dimensions, copy, ship) | Code + AI + Claude rows only (no User ratings) | 0 |
| **Semi-auto** _(default)_ | output format (GIF/PNG/HTML), one preview-and-iterate review | scenario, vibe, audience, dimensions, copy | full 4-rater scorecard | ~3 |
| **Manual** | every decision point | nothing (Claude still suggests and recommends) | full 4-rater scorecard | 8–12 |

Any mode can be upgraded mid-run — say *"stop, switch to semi"* and Claude resumes from the nearest unanswered decision point.

**Note:** operating mode (Auto/Semi/Manual) and dev mode are independent. Dev mode is about whether Phase 6 runs; operating mode is about conversation density.

## Layout

- [`skills/repo-visuals/SKILL.md`](./skills/repo-visuals/SKILL.md) — main skill (discovery → build → preview → export → output → evaluate).
- [`skills/repo-visuals/craft/`](./skills/repo-visuals/craft/) — headline patterns, reference gallery, template HTML.
- [`skills/repo-visuals/scripts/`](./skills/repo-visuals/scripts/) — `capture.js` (GIF), `screenshot.js` (PNG), `evaluate.js` (code-evaluated scorecard).
- [`skills/repo-visuals-retro/SKILL.md`](./skills/repo-visuals-retro/SKILL.md) — retrospective meta-skill, on-demand.
- [`SHOWCASE.md`](./SHOWCASE.md) — merged hero visuals produced with this skill; open a PR to add yours.
