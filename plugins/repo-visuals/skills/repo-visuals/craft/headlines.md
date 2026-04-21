# Headline craft guide

Reference for writing punchy per-scene headlines in `repo-visuals` heroes.

Good dev-tool copy is **terse, rhythmic, and contrarian**. Viewers give you two seconds per scene. Use them.

## Core pattern: imperative + invariant

Template: `<action>. <invariant>.`

The action is an imperative verb phrase (2–4 words). The invariant is what's true regardless — usually a contrarian claim about the space the repo positions against. The second clause is highlighted in brand color so it lands hardest.

Examples from `emtyty/devtool` (local-first dev toolkit, positioned against SaaS tools that upload your data):

| Scene | Headline |
|---|---|
| SQL Formatter | *Format SQL. **Don't ship it.*** |
| JSON Tools | *Repair JSON. **Don't send it.*** |
| Diagram Generator | *Mermaid. **Minus the cloud.*** |
| Cron Builder | *Cron, **finally decoded.*** |
| Color Converter | *HEX → OKLCH. **One click.*** |
| JWT Decode | *Decode tokens. **Leak nothing.*** |
| Grid finale | ***26 tools.** **0 uploads.*** |

## Rules

1. **One headline, one claim.** Don't list features. Pick the one thing that matters.
2. **Under 5 words per clause.** Seriously. "Every color space. One picker." is 5 words total and already feels long next to "HEX → OKLCH. One click."
3. **Imperative voice beats descriptive.** "Format SQL" not "SQL formatting." "Decode tokens" not "Token inspection."
4. **Put the contrarian punch last.** The second clause (after the period) is where the emotional payoff lives. Highlight it in brand color.
5. **Rhythm matters.** Read aloud. If it doesn't trip off the tongue in one breath, rewrite.
6. **Specific > abstract.** Numbers, named formats, named tools. "HEX → OKLCH" is sharper than "all color formats." "26 tools" is sharper than "many tools."
7. **Unify voice across scenes.** Every scene in one hero should sound like the same person wrote it. Pick a voice (contrarian / confident / playful / technical) and hold it for all 5–7 scenes.

## Anti-patterns

- **Hedging:** "Powerful JSON utilities." Who is this for? What does "powerful" mean?
- **Feature lists:** "Format, minify, repair, diff, tree view, TS generation." Save it for the docs.
- **Marketing adjectives:** "Beautifully crafted." "Lightning fast." "Delightful." These are noise.
- **Passive voice:** "JSON is repaired automatically." → "Repairs broken JSON."
- **Vague benefit:** "Developer productivity." Cut until something concrete remains.

## Voice tags

Pick one and hold it across the whole hero:

- **Contrarian** — positions against a common pain (what `emtyty/devtool` uses: "Don't ship it" assumes you know SaaS tools want your data).
- **Confident-technical** — names the exact thing. "Lex. Parse. Emit." / "TypeScript. Built-in."
- **Playful** — wordplay, rhythm, a wink. Use sparingly; it ages fast.
- **Minimal-descriptive** — what it does, no embellishment. Suits brutalist / Apple-ish vibes. "Invoke a skill. Watch it run."

## Workflow

1. Before writing headlines, name the **contrarian claim**: "This repo exists because [status quo] is wrong." If there's no such claim, the hero is probably just a feature list — reconsider the scenario.
2. Draft three candidates per scene. Pick the one that sounds best read aloud.
3. Ensure every scene's headline echoes the same voice.
4. Strip every word that isn't doing work. The final copy should feel almost too short.

## Alternate pattern: narrative arc (for longer-form heroes)

When the hero has 4+ scenes and the repo's value isn't single-punch but cumulative, write headlines as a **mini-story across scenes** instead of independent punches. Each line sets up the next. The cumulative effect is stronger than any single line.

Template:
1. **The pain** — name the frustration the user currently lives with.
2. **The capability** — how this repo works mechanically.
3. **The result** — what the user gets.
4. **The payoff** — the emotional win (time saved, stress avoided, scale unlocked).

Example from `ast-graph` (see `craft/templates/ast-graph-v1.html`):

1. *Made for codebases that **outgrew you**.* — pain (burnout, feeling lost)
2. *Every file. Every call. **In seconds.*** — capability (mechanics, speed)
3. *A **map** your team **and AI** can navigate.* — result (shared artifact)
4. *Answer questions that used to take **hours**.* — payoff (time reclaimed)

Note the emotional specificity: "outgrew you" (not "complex"), "hours" (not "long time"), "team and AI" (not "collaborators"). Narrative copy trades terseness for resonance — 5–8 words per line is fine when each word is doing emotional work.

### Picking between patterns

- **Imperative + invariant** (dev-tool / CLI / library) — when each scene is a *different feature* and the benefit is contrarian/technical.
- **Narrative arc** (dev-insight / platform / paradigm shift) — when the repo represents a new *way of working* and the cumulative journey is the sell.

## Structural references

Read these end-to-end before designing a new hero. They demonstrate full scene systems, progress indicators, hero-text rotation, and timeline scheduling:

- `craft/templates/ast-graph-v1.html` — narrative-arc pattern, 4 scenes, rotating hero slot, step progress indicator.
- `craft/templates/ast-graph-v2.html` — same copy + scene system, visual refinements.
- `<skill-dir>/../repo-visuals-work/<slug>/index.html` — most recent run's source, available after any dogfood.

## See also

- Production-tested examples accumulate in `evaluations/runs/` (where user scorecards let us see which headlines landed).
