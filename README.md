# repo-visuals

A Claude Code skill for producing animated hero GIFs (and, later, static hero images, social cards, demo videos) for GitHub repositories.

v1 ships hero GIF only. Generates bespoke HTML per repo via a structured discovery dialog, previews it in the browser, then exports to an optimized GIF.

## Layout

- [`SKILL.md`](./SKILL.md) — the main skill definition (discovery → build → preview → export → output → evaluate).
- [`craft/`](./craft/) — craft library referenced by the skill during builds.
  - [`craft/headlines.md`](./craft/headlines.md) — headline patterns (imperative-plus-invariant, narrative arc), voice rules, anti-patterns.
  - [`craft/templates/`](./craft/templates/) — full working heroes from past runs; reference them to see how scene systems compose.
- [`scripts/`](./scripts/) — proven export pipeline helpers (Puppeteer `Page.startScreencast` + ffmpeg palette recipe).
- [`repo-visuals-retro/`](./repo-visuals-retro/) — the retrospective meta-skill that reads evaluation logs and proposes edits to `SKILL.md`.
- [`work/`](./work/) — scratch working dirs per repo (git-ignored noise removed, HTML/GIF kept).
- `evaluations/runs/` — gitignored per-run raw scorecards.
- `evaluations/index.md` — curated aggregate (committed, public).

## Dependencies

- Node.js
- `puppeteer` (auto-installs ~170 MB Chromium on first run)
- `ffmpeg` (system or portable download — see `SKILL.md` §4.1)

## Status

Early. Dogfood-in-progress. First real run: `work/emtyty-devtool/` — see its `hero.gif` for what this skill currently produces.
