# repo-visuals

A Claude Code skill for producing hero visuals — **animated GIF** or **static PNG** — for GitHub repositories. Later: social cards, MP4 demos.

The skill scans the repo, recommends a format (animated vs static) based on the repo's identity, and lets the user pick. It then generates bespoke HTML per repo via a structured discovery dialog, previews it in the browser, and exports to an optimized GIF or retina PNG.

## Operating modes

At the start of every run the skill asks (via `AskUserQuestion`) which mode to run in. The mode controls **how many decisions the skill asks the user to make** before shipping an artifact — it does **not** relax any craft rules (real-inventory count, scope match, Code + AI eval always run).

| Mode | What **you** decide | What **Claude** decides silently | Phase 6 scorecard | Typical back-and-forths |
|---|---|---|---|---|
| **Auto** | nothing | everything (format, scenario, vibe, audience, dimensions, copy, ship) | Code + AI + Claude rows only (no User ratings) | 0 |
| **Semi-auto** _(default)_ | output format (GIF/PNG/HTML), one preview-and-iterate review, User scorecard | scenario, vibe, audience, dimensions, copy | full 4-rater scorecard | ~3 |
| **Manual** | every decision point — scenario pick, vibe, brief approval, preview iteration rounds, ship intent, full scorecard | nothing (Claude still suggests and recommends at each step) | full 4-rater scorecard | 8–12 |

### Which to pick

- **Auto** — hands-off draft. Pros: fastest path to a shippable artifact; zero decisions. Cons: lower ceiling on quality; higher risk of missing your taste or the repo's real scope. Best when you want a starting point to react against, not a finished product.
- **Semi-auto** — the recommended default. Pros: fast, keeps the production-grade preview gate, keeps your taste in the loop on the decisions that matter most (format, final review, scorecard). Cons: you don't get input on the smaller creative calls.
- **Manual** — full control. Pros: highest ceiling on quality; your voice present at every beat. Cons: slow — expect 8–12 back-and-forths before an artifact lands.

Any mode can be upgraded mid-run — say *"stop, switch to semi"* and the skill resumes from the nearest unanswered decision point without re-asking what you've already settled.

## Layout

- [`SKILL.md`](./SKILL.md) — the main skill definition (discovery → build → preview → export → output → evaluate).
- [`craft/`](./craft/) — craft library referenced by the skill during builds.
  - [`craft/headlines.md`](./craft/headlines.md) — headline patterns (imperative-plus-invariant, narrative arc), voice rules, anti-patterns.
  - [`craft/reference-gallery.md`](./craft/reference-gallery.md) — catalogued archetypes from real-world repo heroes (freeCodeCamp, shallow-backup, amplication, etc.); consulted during Phase 1.4c format recommendation.
  - [`craft/templates/`](./craft/templates/) — full working heroes from past runs; reference them to see how scene systems compose.
- [`scripts/`](./scripts/) — export pipeline + evaluator. `capture.js` (animated: Puppeteer `Page.startScreencast` + ffmpeg palette recipe); `screenshot.js` (static: Puppeteer `page.screenshot` @2x); `evaluate.js` (Phase 6 code-evaluated scorecard rows, format-aware).
- [`repo-visuals-retro/`](./repo-visuals-retro/) — the retrospective meta-skill that reads evaluation logs and proposes edits to `SKILL.md`.
- [`work/`](./work/) — scratch working dirs per repo (git-ignored noise removed, HTML/GIF kept).
- `evaluations/runs/` — gitignored per-run raw scorecards.
- `evaluations/index.md` — curated aggregate (committed, public).

## Dependencies

- Node.js
- `puppeteer` (auto-installs ~170 MB Chromium on first run)
- `ffmpeg` + `ffprobe` (system or portable download — see `SKILL.md` §4.1)
- `gifsicle` (optional — enables palette-size check in `scripts/evaluate.js`)

## Status

Early. Dogfood-in-progress. First real run: `work/emtyty-devtool/` — see its `hero.gif` for what this skill currently produces.
