---
name: repo-visuals
description: Create hero visuals — animated GIF or static PNG — for GitHub repositories. Runs a structured discovery conversation (scan repo → recommend format → propose creative scenarios → agree on a brief), then designs bespoke HTML, previews it in the browser, and exports.
---

# repo-visuals

Turn a repo (GitHub URL, local folder, or free-text brief) into a hero visual that a viewer sees at the top of the README and instantly understands *what this project does and why it's interesting*. The hero may be an **animated GIF** or a **static PNG** — the skill recommends one based on the repo's identity, the user picks.

The skill's quality comes from the **discovery dialog**, not from templates. Every hero is bespoke.

## Phases

1. **Discovery** — pick operating mode (Auto / Semi-auto / Manual, §1.1a), scan the repo, summarize findings, recommend a format (animated vs static), ask about vibe/audience/hero moment, propose 2–3 scenarios, converge on a brief. The mode controls *how many* of these the user answers vs. Claude decides silently — it does not skip any of the craft checks.
2. **Build** — write HTML/CSS/JS for the chosen scenario. For static, design one decisive frame; for animated, a loop. No storyboard step.
3. **Preview & iterate** — open the HTML in the user's default browser, iterate in text until the user says ship.
4. **Export** — animated → Puppeteer screencast + ffmpeg palette pipeline to GIF. Static → Puppeteer `page.screenshot` to PNG (with `deviceScaleFactor: 2` for retina crispness).
5. **Output** — place the hero in the target repo; optionally open a PR that embeds it in the README.

**Dev mode (author-only):** Phase 6 — Evaluate exists but **only runs in dev mode**. Dev mode is for the skill's author iterating on the skill itself; it collects scorecard data and writes run logs under `./evaluations/` in the user's current working directory. Enable it only when the user explicitly says "dev mode" (or sets `REPO_VISUALS_DEV=1`). In every normal run — including Manual, Semi-auto, and Auto — the skill ends after Phase 5. Do not mention Phase 6 to end users.

---

## Phase 1 — Discovery

Discovery runs **before any HTML is written**. Its job: go from a vague ask ("make a hero GIF for my repo") to a specific, committed creative brief.

### 1.1 Activation

Enter discovery mode whenever the user invokes the skill, **unless** they explicitly say "skip discovery, I have the brief ready."

### 1.1a Operating mode (ask first, once per run)

Before anything else — before the scan summary, before any direction questions — ask the user which operating mode they want for this run. Use the `AskUserQuestion` tool so the choice is structured and visible, not buried in free text. Offer three modes; describe each in concrete terms (what gets asked, what gets decided silently) and include pros/cons so the user can pick with open eyes. Default recommendation: **Semi-auto**.

> Note: this "operating mode" is a skill-level concept about how many questions the skill asks. It is distinct from the Claude Code harness's own auto-mode; the two do not replace each other.

Question shape:

```
AskUserQuestion({
  questions: [{
    header: "Run mode",
    question: "How involved do you want to be in this run? This affects how many decisions I ask you to make before we ship an artifact.",
    multiSelect: false,
    options: [
      {
        label: "Semi-auto (Recommended)",
        description: "I decide vibe, audience, scenario, dimensions, copy. You decide: output format (GIF/PNG/HTML) and one preview-and-iterate review before export. ~2 decisions. Pros: fast, keeps production-grade gate, keeps your taste in the loop on the things that matter most. Cons: you miss input on smaller creative calls."
      },
      {
        label: "Manual",
        description: "I ask you at every decision point — scenario pick, vibe confirmation, brief approval, preview iteration rounds, export ship-intent. I still make suggestions and recommendations at each step. Pros: max control, highest ceiling on quality. Cons: slow — 8–12 back-and-forths before an artifact."
      },
      {
        label: "Auto",
        description: "I make every decision and go straight to the exported artifact (GIF or PNG, my call). Pros: hands-off, 0 decisions, fastest path to a shippable draft. Cons: lower quality ceiling, more risk of missing your taste or the repo's real scope; expect to redirect after seeing the result."
      }
    ]
  }]
})
```

Rules that apply to **every** mode regardless of choice (craft non-negotiables):

- **§1.3 inventory count is always collected.** Auto/semi don't skip it.
- **§4.0 scope-match rule is always enforced.** If the hero says "all" or shows a grid, on-screen reality must match the real inventory — regardless of mode.
- **Any mode can be upgraded mid-run.** If Auto drifts, user can say "stop, switch to semi" and we resume from the nearest decision point. Do not silently re-ask everything; pick up at the next unanswered question.

After the user picks a mode, commit it to memory for the run (e.g. "Mode: Semi-auto") and reference it when deciding whether to ask or decide silently at each subsequent step. In Auto and Semi-auto, make decisions with a brief one-line note ("going with the Product-UI marketing archetype per §1.4c — amplication-shape repo") so the user can redirect if they disagree.

### 1.2 Input triage

User may provide:

- **GitHub URL** → clone shallow, plus use `gh repo view` for stars/topics/languages/releases.
- **Local path** → scan the tree directly.
- **Free-text brief only** → proceed to direction questions immediately.
- **Nothing** → ask first for one of the above.

### 1.3 Scan checklist (collect a lot)

Gather as much as possible before asking the user anything. Goal: Claude should already have an opinion about what this repo is before the vibe conversation starts.

- README (full text) — extract tagline from first paragraph.
- Manifest(s): `package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, `*.csproj`, etc. — description, keywords, dependencies, entry points.
- File tree (depth 3) + top 10 files by size.
- Language breakdown (LOC per language).
- Existing visuals in repo: `assets/`, `docs/`, `.github/`, any `*.png` / `*.gif` / `*.svg` near the root.
- `LICENSE`, `CHANGELOG.md` — maturity signal.
- Recent git log (last 10 commits) — what's active.
- If GitHub: stars, topics, releases, open issues count.
- If `ast-graph` is available locally and the repo has supported languages: run `scan` + `hotspots` + `symbol` on top-level exports for structural inventory.
- **Count the real inventory** — if the repo exposes a collection (tools, commands, pages, themes, plugins, routes), count them from source (route files, `src/tools/*`, CLI command registrations, etc.). Do not estimate from the README. This number is used later: any hero that says "all", "every", "the whole", or shows a grid meant to represent scope must match this count — or explicitly frame itself as a sample ("10 of 30 shown", scroll affordance, "30+"). An undercount reads as a broken promise.

Summarize findings back to the user in ~6–10 bullets so they can correct misreadings early. Include the inventory count when one exists.

### 1.4 Direction questions (after the scan summary)

Ask these as a structured batch, with suggested defaults based on what the scan found so the user can just accept or redirect:

1. **Where will this hero live?** — README top / project website / social posts (Twitter, LinkedIn) / conference slide / internal demo / elsewhere. *This drives dimensions and loop length.*
2. **Output format?** — **animated GIF** / **static image (PNG)** / **HTML only (no export)**. Not every repo wants motion; some strong identities read better as one sharp frame. Scan the repo first and offer a recommendation (see §1.4c), then let the user override. Default: whichever §1.4c recommends. *(MP4/WebM and square social cards are listed in the future-formats appendix.)*
3. **Audience** — working devs / eng leaders / newcomers / prospective contributors / all
4. **Vibe** — minimal, playful, technical, cinematic, retro-terminal, brutalist, polished-SaaS
5. **Energy** — calm & meditative / steady / frenetic & showy
6. **Hero moment** — the single thing a viewer should take away
7. **Hard constraints** — brand colors, existing fonts, imagery to include/avoid, duration cap

### 1.4a Probing when the user doesn't know

Many users will answer "I don't know" to vibe / hero moment / audience. That's normal. Don't force them to guess — extract intent sideways:

- **"Show me a repo whose hero you liked"** — reverse-engineer what they respond to.
- **"What do you wish someone understood about this project in 10 seconds?"** — surfaces the hero moment without asking for it directly.
- **"Who's the person whose opinion about this repo matters most to you?"** — surfaces the audience.
- **"Is this repo a calm/serious tool or a fun/exciting one?"** — a binary that usually works for vibe.

If they still can't articulate, offer Claude's best guess based on the scan and ask them to confirm or push back. Be willing to **commit first, confirm second** — a concrete wrong guess triggers better reactions than another open-ended question.

### 1.4c Format recommendation (animated vs static)

Before asking Q2, form an opinion from the scan. **First consult `craft/reference-gallery.md`** — try to place the target repo in one of the catalogued archetypes (Terminal-demo GIF / Product-UI marketing / Brand-first logo / Banner/promo graphic / Diagram-as-hero) and cite the match by name when recommending. If no clean match, fall back to the heuristics below.

The repo's identity tells you which format fits:

**Lean static (PNG) when:**
- The repo's pitch is a **surface**, not a process — a landing page, a typography choice, an API shape, a single striking screenshot.
- Existing visuals in `assets/` / `docs/` are already static and strong.
- The vibe is brutalist, editorial, documentation-first, or "the screenshot is the product" (design systems, component libs shown in a grid, CLI themes whose appeal is one frame).
- Audience skews toward skim-then-click (social posts shared as preview cards, directory listings).
- README opens with one crisp hero sentence and a screenshot — mirror that, don't animate it.

**Lean animated (GIF) when:**
- There's a **before→after transformation**, a step sequence, or a multi-stage pipeline — the motion *is* the pitch.
- The repo is a tool with visible runtime behavior (CLI output, live reload, computation unfolding).
- The hero moment is "watch this happen," not "see this exists."
- The scan surfaces multiple distinct capabilities worth walking through (then: animated; or: static grid).

**Lean HTML-only when:**
- The user will embed on a site they control and wants the live animation.
- The user explicitly wants to iterate further with their own tools.

Present the recommendation forcefully: *"Based on the scan, I'd go **static** — this repo's identity is [X], and motion would add noise not signal. Want me to proceed with static, or would you rather animated?"* Then honor whatever they pick.

### 1.5 Scenario proposal

Offer **2–3 concrete scenarios** (two if the viable directions are closely related, three if they diverge meaningfully), each with:

- **Concept** — one line
- **Scene beats** — 3–5 bullets describing what happens second-by-second
- **Vibe anchor** — a visual reference ("think Linear changelog", "think `htop`")
- **Why it suits this repo** — one paragraph grounding it in the scan findings
- **Risk** — one line on what could make this one weaker

Then **Claude's recommendation**: pick one and argue for it forcefully in 1–2 sentences. Frame it as something the user can still redirect.

### 1.6 Convergence signal — "enough info"

Move to the build phase when all six are settled:

- [ ] Chosen scenario (one of the 2–3 proposed, possibly with edits)
- [ ] Vibe locked
- [ ] Hero moment named in one sentence
- [ ] Audience named
- [ ] Hard constraints captured (or confirmed "none")
- [ ] Output format chosen (animated GIF / static PNG / HTML only)
- [ ] Placement agreed (README / website / social / slide / other)
- [ ] Duration chosen — animated only (typical: 15–25s loop; default 20s); skip for static
- [ ] Dimensions confirmed (see §1.7 — locked to 1200×675; do not vary)
- [ ] Real inventory count captured from §1.3 scan (if the repo has a countable collection)
- [ ] Operating mode recorded from §1.1a (Auto / Semi-auto / Manual)

Write the brief back to the user in a compact block. Wait for **"go"** before writing any HTML — *unless* the mode is **Auto**, in which case proceed directly to Phase 2 with a brief summary line and no wait. In **Semi-auto**, show the brief but proceed after a brief pause unless the user interjects. In **Manual**, wait explicitly for "go".

### 1.7 Dimensions — locked

**Always 1200×675 (16:9).** Do not try to match the target repo's existing image dimensions; do not pick a slim banner because the current logo is slim; do not offer the user a choice. This is a hard default.

Why locked:
- Predictable craft bar. A 16:9 canvas gives enough room for real content (terminal + editor, multi-scene narrative, brand + demo split) without the skill producing cramped marquees.
- Consistent export pipeline. Capture, screenshot, and evaluation scripts assume 1200×675; varying dimensions multiplied incidental bugs in past runs.
- README rendering. At GitHub's ~1000px content width, a 1200-wide hero scales to ~560h — taller than the target repo's current logo, but the visual upgrade is worth the added vertical space. The user can object if they truly want a slimmer hero; default hard, override rare.

Other aspect ratios (8:3, 6:1, 1:1, etc.) are not supported defaults. If a user explicitly asks for a slim banner or social-card crossover, build it at 1200×675 and communicate that the export will be cropped for those contexts downstream — don't change the source dimensions.

---

## Phase 2 — Build

Once the brief is locked and the user says "go", write the HTML in **one file** (`index.html` in a working directory for this repo's hero).

### 2.1 Working directory

Default layout — always nest per-repo under a subdirectory named after the target repo (e.g. `last30days-skill`, `my-cli`):

```
<current-dir>/repo-visuals-work/<repo-name>/
  index.html        # the hero animation source
  assets/           # any images/SVGs the scenario needs
```

Use `repo-visuals-work/<repo-name>/` so the scratch files stay obviously separate from the target repo **and** runs for different repos don't clobber each other. Never write directly into `repo-visuals-work/` — always into the repo-named subfolder. If no obvious repo name, use a short slug derived from the brief.

### 2.2 Re-read the README before writing

Open the target repo's README once more right before writing HTML. Mirror its actual phrasing, headings, and technical terms in the animation's on-screen text. The hero should feel like it was written *by* the repo author, not *for* them.

### 2.2a Consult the craft library

Before writing any scene copy or layout, read:

- `craft/headlines.md` — headline patterns (imperative-plus-invariant, narrative arc), voice rules, anti-patterns.
- `craft/templates/*.html` — full working heroes from past runs. Read end-to-end to see how a complete scene system is composed (stage + browser chrome + tool-body + rotating hero text + progress indicator + timeline scheduler). Don't copy verbatim — steal patterns.

Every scene needs a headline. A demo without copy delivers no meaning.

### 2.3 Structure of `index.html`

Single self-contained file. No build step. Sections:

1. **Stage** — a fixed container sized to the chosen dimensions (§1.7). Everything absolutely positioned inside. Outside the stage: a subtle page background so the capture crop is unambiguous.
2. **Fonts & tokens** — import fonts at the top (Google Fonts `@import`), define CSS custom properties for the palette (`--bg`, `--accent`, `--text`, `--muted`, etc.) derived from the vibe/constraints.
3. **Scene DOM** — the HTML elements that each scene uses. Build all of them upfront; scenes show/hide via classes.
4. **Timeline object** — a JS `TIMELINE` with named keys (e.g. `scene2Start: 3500`) so pacing is tweakable in one spot. Include `loopPauseAt` so the animation has a clean loop boundary.
5. **Timer helpers** — `schedule(t, fn)` wrapping `setTimeout` into an `animTimers` array, plus a `runLoop()` that clears and restarts. This is what the export pipeline calls to reset to t=0 deterministically.
6. **Scenes** — each scene is a plain function that flips classes / starts tweens. Keep CSS transitions for simple motion; use small rAF-driven tweens for counters or typing effects.

### 2.4 Rules of thumb

- **Durations**: match the chosen loop length (default 20s). Each scene ~3–6s, never so fast the viewer can't read it. Shorter dimensions (banner / slim) naturally want shorter loops — 10–15s.
- **Motion**: use `transform` and `opacity` only — never `top/left/width/height` (janky, expensive).
- **Type**: scale the minimum body size to stage height — ~2.5% of stage height, bumped up for GIF legibility. At 675h that's ~17px; at 300h that's ~14px minimum. Never below 13px.
- **Palette**: pick 4–6 colors. More kills GIF compression *and* looks busy.
- **Loop seam**: the last frame should visually match the first (or transition back smoothly). `runLoop()` is the hard reset if needed.
- **Determinism**: no `Math.random()` without a seed, no `Date.now()`-based logic. Everything must replay identically each capture.
- **Avoid the NY Times / editorial-newspaper theme**: no serif-headline + rule-lines + dateline + column-grid pastiche. It's become a default AI-design shortcut and reads as generic. Pick a visual language that actually suits the repo's domain (terminal, data-viz, spatial, playful, brutalist, neon, etc.) — not a broadsheet aesthetic unless the repo is explicitly about journalism or publishing.
- **No drift-prone claims in on-screen copy.** Never hardcode anything that becomes stale the moment upstream ships or the clock ticks forward. The hero outlives any single release — a visible `v1.9.2` turns obsolete the next Tuesday, a visible `6.4k stars` turns obsolete the next weekend.
  - **Banned as exact values:** version numbers (`v1.9.2`, `2.0.0-rc3`), language/runtime floors (`Node 20+`, `Python 3.10+` — these bump every ~2yrs), star counts (`6.4k stars`), download counts (`12M weekly`), contributor counts (`52 contributors`), "last updated" / release dates, benchmark figures pulled from a specific build.
  - **Allowed timeless claims:** package name, license, architecture primitives (e.g. "MCP", "CLI + API"), domain nouns ("semantic search", "static analysis"), scope words ("multi-platform", "zero-config").
  - **Soft-cap rule for drift-prone stats:** if a number genuinely helps the pitch, phrase it as **`<next lower round number>+`** so upstream movement doesn't falsify it. Examples: `44 rules → "40+ rules"`, `6,421 stars → "6k+ stars"`, `127 contributors → "100+ contributors"`, `12.3M weekly downloads → "10M+ weekly downloads"`. Round **down** to the nearest meaningful milestone — never round up, and never pick a cap the number is about to cross (a `9k+ stars` claim on a 9.1k repo is a landmine; use `9k+` only when the repo is comfortably past that for months, otherwise drop to `5k+`).
  - **Precise counts acceptable only when frozen:** finished tutorial series, explicitly versioned snapshots, historical data — contexts where the count is *designed* not to move.
- **Left-column layout — don't pin content to edges.** In split-stage heroes with a brand/tagline column on the left, avoid `grid-template-rows: auto 1fr auto` or any pattern that parks the bottom row flush against the stage edge — it reads as cramped / "glued-in" at export. Either (a) center the column content vertically (`align-content: center` on the grid) with explicit gaps, or (b) use `grid-template-rows: auto auto 1fr` with meaningful breathing room (≥32px equivalent) below the last content row. Default to option (a) unless the column genuinely has more content than vertical space.
- **Preview-vs-export parity — the HTML the user sees is the PNG/GIF they get.** A recurring failure mode: `index.html` looks perfect in the browser, but the exported PNG/GIF is cropped or shifted because the browser's natural centering (`body { display: grid; place-items: center }`) + the stage's `box-shadow` + any body padding collectively move the stage away from the `(0, 0)` origin the capture pipeline samples from. Rules to prevent this:
  - **Body must pin the stage at (0, 0) for export.** Either drop the centering entirely (`body { margin: 0; padding: 0 }` with the stage at flow position) or wrap centering in `@media (min-height: 800px)` so headless Chrome at the capture viewport lands at origin. Never rely on `place-items: center` alone if the capture viewport equals the stage size exactly.
  - **`box-shadow` on the stage is for the HTML preview only.** Shadows extend outside the 1200×675 box and get guillotined by the capture crop — fine, expected. But don't rely on the shadow as a visual boundary; the content inside the stage must read as complete without the shadow.
  - **Never let content exceed the stage.** Any absolute-positioned element with `top: -N` or `right: -N` to create an "overlap" effect will be clipped in export. If you want a visual that bleeds past the stage edge, reposition it inside or fake the bleed with a gradient — do not let real content live outside.
  - **Puppeteer screenshot must use explicit `clip`.** Always pass `clip: { x: 0, y: 0, width: 1200, height: 675 }` to `page.screenshot()` rather than relying on viewport-equals-capture. This guarantees the crop, regardless of scroll offset or body margin that slipped in.
  - **Validate parity before declaring done.** After export, open the exported PNG/GIF side-by-side with `index.html` in the browser. If they don't match visually, the HTML is wrong (not the pipeline) — fix the layout, don't fix the pipeline.

### 2.5 When to stop writing and preview

First preview as soon as:

- All scenes are implemented (even if polish is rough)
- Timing hits the full duration target
- No console errors

Don't polish before first preview. User's reaction on overall shape is more valuable than Claude's local polish loop.

---

## Phase 3 — Preview & iterate

Keep this phase conversational. The goal is to converge on a version the user loves before spending time on export.

### 3.1 Open in browser

After writing `index.html`, **give the user the command** to open it themselves (their browser, their timing):

- **Windows**: `start repo-visuals-work/<repo-name>/index.html`
- **macOS**: `open repo-visuals-work/<repo-name>/index.html`
- **Linux**: `xdg-open repo-visuals-work/<repo-name>/index.html`

Tell them to watch **one full loop** (the animation restarts automatically via `runLoop()`).

### 3.2 What to ask after first preview

Keep first-preview questions focused on **shape**, not polish:

- Does the *hero moment* land?
- Does the overall pace feel right (too fast? too slow?)
- Does any scene feel confusing or unnecessary?
- Does the loop seam look clean?

Don't ask about colors/fonts/spacing on the first round. Polish comes after shape is right.

### 3.3 Iteration rhythm

- Each round: Claude edits, user refreshes, one sentence of reaction.
- After shape converges, switch to polish rounds: type hierarchy, color calibration, micro-timing, loop seam.
- If user gives vague feedback ("feels off"), ask **one pointed question** to narrow it — don't guess.
- **Style stuck? Invoke `frontend-design`.** If the user has gone back-and-forth on *style* (palette, type, overall aesthetic, visual language) for **3+ rounds** without converging — or says something like "still not it" / "try a totally different direction" — stop tweaking in place. Invoke the `frontend-design` skill via the `Skill` tool to get a fresh, high-quality design pass. Pass it the brief, the repo scan summary, the current `index.html`, and a plain-language description of what's not working. Use its output as the new starting point, then return to this iteration loop. Don't invoke it for pacing, timing, or animation-logic feedback — only when the blocker is *visual design quality*.

### 3.4 Mid-build GIF sanity check *(only if GIF is a target output)*

GIF quantization causes specific failures that HTML preview hides: small text blurs, near-identical hues posterize, fine gradients band. If GIF was selected in §1.4, run the export pipeline **once** at ~70% polish so these surface before the final polish rounds. Check:

- Is small text still legible?
- Do any colors posterize badly?
- Does the animation feel the same speed as the HTML?

If problems appear, tune the HTML (bigger type, fewer palette neighbors, simpler gradients) and keep iterating on the preview.

**Skip this section entirely if the output is not a GIF** (MP4/WebM preserve HTML fidelity; static outputs are sampled directly).

### 3.5 Stop signal

Stop iterating when the user says "ship it" (or equivalent). Don't invite more rounds — excess polish is real cost. If Claude thinks there's still a clear improvement available, mention it *once* and let the user decide.

### 3.6 Deliver all the intent, even unstated

The user may not fully know what they want. Keep watching for mismatches between the scan/brief and the HTML behavior:

- Did the README say "fast"? The hero should feel quick, not luxurious.
- Is the audience newcomers? Don't assume they know jargon — the hero's text should echo README phrasing.
- Did the brief say "calm"? Check for accidental frenetic motion (fast cuts, snappy eases).

When you spot a mismatch, flag it proactively ("the README leans 'fast' but the current pacing is slower — intentional, or should we tighten?"). Deliver intent, not just instructions.

---

## Phase 4 — Export

### 4.0 Entry gate — do not skip

Before you export anything, confirm — the exact gate depends on operating mode (§1.1a):

| Gate item | Manual | Semi-auto | Auto |
|---|---|---|---|
| User has **seen the artifact running** (open in browser or rendered screenshot) | required | required | skipped |
| At least **one iteration round** after first look | required | required | skipped |
| **Scope match** — hero claims (*"all"*, *"every"*, grid/list representing the repo) match real inventory from §1.3, or explicitly framed as sample ("10 of 30", "30+", scroll affordance) | **required** | **required** | **required** |
| User has explicitly said ship / go / export | required | required (after 1 preview) | not required |

The scope-match rule is **non-negotiable in every mode** — it's a craft check, not a human-involvement question. The human-in-the-loop items are what modes toggle.

Export is the **last** step, not a midpoint. A capture→encode→evaluate cycle feels productive but burns the user's patience on a draft that wasn't ready. When in doubt between "export this pass" and "one more iteration", prefer the iteration — except in Auto mode, where the point is to deliver a first draft fast and let the user redirect.

### 4.1 Prerequisites (ask before installing)

Check presence, list missing, ask the user before installing:

- **Node.js + `puppeteer`** — via `node --version` and looking for `node_modules/puppeteer`. If missing: `npm install puppeteer` (~170MB Chromium download).
- **`ffmpeg`** — via `ffmpeg -version`. If missing:
  1. Prefer system package manager (`choco install ffmpeg`, `brew install ffmpeg`, `apt install ffmpeg`) — needs admin.
  2. On Windows without admin, download **portable** ffmpeg from `https://github.com/GyanD/codexffmpeg/releases/latest` and extract `ffmpeg.exe` into the skill's `bin/` dir. Do NOT add to PATH; call by absolute path.

Never install silently. Show the plan, ask, then act.

### 4.2 Capture script (reused across repos)

Ship at `<skill-dir>/scripts/capture.js`. Accepts CLI args:

```
node capture.js --html <path-to-index.html> --out <frames-dir> --duration 20700 --width 1200 --height 675
```

### 4.3 Branch on chosen format

Based on the format decided in Phase 1.4c:

- **Animated GIF** → continue with §4.3 (GIF pipeline).
- **Static PNG** → skip to §4.3s (static pipeline).
- **HTML only** → skip Phase 4 entirely; the hand-off is `repo-visuals-work/<repo-name>/index.html`.

### 4.3g GIF pipeline (the proven recipe)

Use as-is unless there's a specific reason to deviate.

**Capture:**

- Launch Puppeteer (`headless: 'new'`).
- `setViewport({ width, height, deviceScaleFactor: 1 })`.
- `page.goto(file://...)` with `waitUntil: 'networkidle0'`.
- `await page.evaluateHandle('document.fonts.ready')`.
- Small real-time settle (300ms).
- `await page.evaluate(() => window.runLoop())` to reset the animation to t=0.
- Create a CDP session: `page.target().createCDPSession()`.
- Subscribe to `Page.screencastFrame` — save each frame as PNG, record `metadata.timestamp` (seconds).
- `client.send('Page.startScreencast', { format: 'png', everyNthFrame: 1 })`.
- Wait `duration + 200ms`, then `Page.stopScreencast` and close browser.
- Write an ffmpeg **concat manifest** with per-frame durations from timestamp deltas — preserves the real paint cadence.

**Why screencast, not screenshot-loop or virtual-time:** real screencast records exactly what the compositor paints, including CSS transitions. Screenshot loops drift under load; virtual-time (`Emulation.setVirtualTimePolicy`) freezes the compositor and captures stale frames.

**Encode (two-pass palette):**

```bash
# Pass 1: palette tuned for motion
ffmpeg -y -f concat -safe 0 -i frames.txt \
  -vf "fps=30,palettegen=stats_mode=diff:max_colors=256" \
  palette.png

# Pass 2: apply palette with sharp-text dither
ffmpeg -y -f concat -safe 0 -i frames.txt -i palette.png \
  -lavfi "fps=30 [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  -loop 0 hero.gif
```

- `stats_mode=diff` — palette focuses on moving regions; static UI chrome doesn't dominate.
- `bayer:bayer_scale=5` — sharper than `sierra2_4a` for UI text. Try `dither=none` if text is still blurry and gradients are minimal.
- Do **not** re-scale in the filter graph if frames are already the target size.

**Size budget:**

- **Target: ≤ 10 MB** — default cap. Renders cleanly on GitHub, mobile / slow connections don't suffer.
- **Hard max: 15 MB** — only if the content genuinely requires it *and* the user has confirmed they accept the bigger file. Never exceed silently.
- Reduction ladder when over 10 MB: drop to `fps=20` → drop to `fps=15` → `max_colors=192` → `max_colors=128` → shorten loop. Apply in order; stop as soon as under budget.

### 4.3s Static PNG pipeline

For the static format, skip ffmpeg entirely — a single crisp screenshot is enough.

**Capture via Puppeteer:**

- Launch Puppeteer (`headless: 'new'`).
- `setViewport({ width, height, deviceScaleFactor: 2 })` — retina-crisp for README rendering at native size.
- `page.goto(file://...)` with `waitUntil: 'networkidle0'`.
- `await page.evaluateHandle('document.fonts.ready')`.
- Settle 500ms so any entrance transition finishes.
- `await page.screenshot({ path: 'hero.png', type: 'png', omitBackground: false })`.

If the HTML has an animation that evolves over time, either:
- Design the static HTML to render its final/decisive frame at t=0 (preferred), or
- Before the screenshot: `await page.evaluate(() => window.seekTo(<seconds>))` if the source HTML exposes such a hook.

**Optional compression:** run `pngquant --quality=80-95 hero.png --output hero.png --force` if the PNG is over ~500 KB. Static heroes rarely need it.

**Size budget:**

- Target: ≤ 500 KB for a 1200-wide retina PNG. If over 1 MB, compress.

**Ship script:** `node scripts/screenshot.js --html <path> --out hero.png --width 1200 --height 675` (thin wrapper around the steps above — see `scripts/screenshot.js`).

### 4.4 Output file name

- Animated → `repo-visuals-work/<repo-name>/hero.gif`
- Static   → `repo-visuals-work/<repo-name>/hero.png`

Keep in the scratch dir until Phase 5 (Output) moves it.

---

### Appendix — future formats

Future formats Claude may extend this skill with — not part of the current export pipeline:

- **MP4 / WebM loop** — `libx264 -crf 18` or `libvpx-vp9 -crf 32`. Higher fidelity, smaller files. Note: GitHub renders `.mp4` uploaded via issue/PR drag-and-drop but not `.mp4` checked into the repo and linked in markdown.
- **Square social card (800×800 or 1200×1200)** — variant of static PNG, often reframed rather than cropped, with headline overlay tuned for LinkedIn / Twitter preview rendering.
- **9-frame contact sheet** — helper for picking the decisive moment of a long animation before static export.

---

## Phase 5 — Output

Move `hero.gif` from the scratch dir into the target repo, update the README, and optionally open a PR.

### 5.1 Placement in the target repo

Read the target repo to infer convention, then ask. Priority order when inferring:

1. Existing `assets/` or `images/` → follow it.
2. Existing `docs/` with images → place at `docs/hero.gif` (or `docs/<repo-name>-hero.gif` if multiple visuals).
3. Existing `.github/` with images → `.github/hero.gif`.
4. No visible convention → default to `assets/hero.gif` and create the dir.

File name: default `hero.gif`. If the repo already has a `hero.gif` or keeps multiple visuals, prefer `<repo-name>-hero.gif` or `<repo-name>-demo.gif`.

### 5.2 README embed

Read the README first. Ask:

- **Top of README** (most common) → insert `![alt](path)` right after the H1 title and tagline.
- **Replace an existing image** → identify it, confirm with user.
- **Specific section** → user names where.

Alt text default: `<repo-name> demo` (user can override).

**Always use a relative path** — `![alt](assets/hero.gif)` or `<img src="assets/hero.gif">`, never `https://raw.githubusercontent.com/<owner>/<repo>/main/assets/hero.gif`. Even if the existing README uses absolute `raw.githubusercontent.com` URLs for its current images, do not mirror that style for your new hero. Reasons:

- Absolute URLs pinned to `main` don't render in forks or in the PR preview — the image stays broken until the PR merges, which hurts review quality and often triggers reviewer objections (has happened: `htmlhint/HTMLHint#1861`).
- Relative paths resolve correctly on GitHub web, npm package pages, and most README-rendering tools.
- If the existing logo uses an absolute URL, that's legacy debt — it was shipped before the author realized the tradeoff. Don't propagate it.

If the user explicitly asks for an absolute URL (e.g. embedding the hero on an external site that loads the README), use one — but the default for in-repo embeds is always relative.

### 5.3 Commit

Branch name default: `docs/add-hero-gif`. Override if the repo has a branch-name convention (check recent PRs or `CONTRIBUTING.md`).

Commit message default: `docs: add animated hero gif to README`. Follow existing commit style (conventional commits, imperative, etc.).

**Co-author footer: default OFF.** Only add a `Co-Authored-By: Claude …` footer if the user explicitly opts in for this repo.

### 5.4 Push & PR

Detect auth and repo ownership:

- **User owns the repo** → push branch to `origin`, open PR via `gh pr create` against the default branch.
- **User does NOT own the repo** → `gh repo fork --clone=false`, add the fork as a remote, push the branch there, then `gh pr create --repo <upstream> --head <user>:<branch>`.
- **Not authed as the account the user wants to use** → stop and ask them to `gh auth login` as the right account. Never guess.

Commit identity: if the user specifies a different git account for this repo, set `user.name` / `user.email` on the local repo config only, not globally. Use `<login>@users.noreply.github.com` if email is unknown.

### 5.5 Hand-off

After the PR opens, report:

- PR URL
- Final GIF size
- Placement path in the repo
- What was added/changed in the README (one-line diff summary)

Stop there.

### 5.6 Opt-out: local-only

If the user doesn't want a PR, leave `hero.gif` at `repo-visuals-work/<repo-name>/hero.gif` and print the path. Don't modify the target repo.

---

## Phase 6 — Evaluate *(dev mode only — skip in normal runs)*

**Gate:** run this phase only when dev mode is active (user said "dev mode" this run, or `REPO_VISUALS_DEV=1`). In every other run — Manual, Semi-auto, Auto — stop after Phase 5. Do not ask user-rating questions, do not write run logs, do not mention this phase.

Score the **final artifact**, not the process. In dev mode, always runs at the end.

### 6.1 Criteria (four rater types)

Each criterion is rated by exactly one of: **User**, **Claude** (subjective, chat-blind), **Code** (deterministic script), or **AI** (Claude re-reads the final GIF/HTML with vision, blind to prior chat).

**User-rated (3) — viewer-side truth.**

| Criterion | What it measures | Signal for low score |
|---|---|---|
| **Hero moment delivery** | Does a cold viewer "get it" in ~10 seconds — both *what the repo is* and *why they'd reach for it*? | After one loop, viewer still can't state the repo's purpose or motivation |
| **Visual impact** | Does the artifact make the viewer *want* to try the repo? | Looks fine but feels generic; no pull |
| **Ship-worthiness** | Gut check: would the user paste this into the repo's README today, as-is? | User hesitates, wants "one more pass" |

**Claude-rated (1) — repo-fit judgment.**

| Criterion | What it measures | Signal for low score |
|---|---|---|
| **Repo fidelity** | Do on-screen text, terminology, and vibe feel like this specific repo's own voice? | Headlines read like generic marketing; terminology drifts from README |

**Code-evaluated — `scripts/evaluate.js` runs automatically after export. Rows depend on format.**

| Criterion | Applies to | Pass rule | Fail signal |
|---|---|---|---|
| **File size** | GIF + PNG | GIF: ≤ 10 MB target / ≤ 15 MB cap. PNG: ≤ 500 KB target / ≤ 1 MB cap. | Over target → 3; over cap → 1 |
| **Dimensions** | GIF + PNG | Matches spec (e.g. 1200×675). PNG at 2× device pixel scale is also acceptable. | Wrong size → 1 |
| **Loop duration** | GIF only | 15–25 s (hero default) | Outside band → 2 |
| **Loop seam** | GIF only | First-frame vs last-frame pixel diff under ~2% | Visible jump on loop → 2 |
| **Palette size** | GIF only | Palette ≤ 256, no visible banding on solid regions | Banding detected → 2 |

**AI-evaluated (4) — Claude re-opens the exported artifact with vision, blind to prior chat. Prompt in §6.3.**

| Criterion | What it measures | Signal for low score |
|---|---|---|
| **Legibility** | Every headline readable at native render size, no sub-pixel smear | Any headline unreadable → 2 |
| **Scene clarity** | Each scene conveys one idea in its airtime | Two scenes blur together or one feels like filler → 3 |
| **Voice match** | Headlines match tone and terminology of the repo's README | Drift from repo's own language → 2 |
| **Intent delivery** | After one loop, can a cold viewer state *why* to reach for this repo? | Demos *what* without delivering *why* → 3 |

### 6.2 Scale (1–5, labeled)

| Score | Label | Meaning |
|---|---|---|
| 1 | Poor | Falls apart on the criterion |
| 2 | Weak | Noticeably misses |
| 3 | OK | Gets there, nothing more |
| 4 | Strong | Clearly delivers |
| 5 | Excellent | Best-in-class for this repo |

Use the labels, not bare numbers. A "3" alone is noise; "3 / OK" is meaningful.

### 6.3 Hand-off scorecard

Assemble in four steps:

1. **Run code eval** — `node scripts/evaluate.js <path-to-hero.gif-or-png>` → emits a JSON scorecard.
2. **Run AI eval** — extract 4–6 keyframes from the GIF first (`ffmpeg -ss <t> -i hero.gif -update 1 -frames:v 1 frame.png` at evenly spaced times), then re-read each frame with vision, blind to prior chat. Use this fixed prompt — **anchored, evidence-required, and fed the repo's real inventory** so factual drift is catchable:

   > You are evaluating a hero GIF for the repo `<owner/repo>`.
   >
   > **Repo ground truth (from §1.3 scan):**
   > - README excerpt (first 40 lines): `<excerpt>`
   > - Real inventory count: `<N>` (e.g. "30 tools", "12 commands", "N/A"). Specific names: `<list if applicable>`.
   > - Stated hero moment (from §1.6 brief): `<one sentence>`
   >
   > **Rating protocol — read carefully:**
   > - **Default every score to 3 / OK.** A 3 means "gets there, nothing more." Only move up with specific visual evidence from the frames; only move down with specific visual evidence of a problem.
   > - **4 / Strong requires one concrete observation** from the frames that the criterion is clearly delivered (cite it in the note).
   > - **5 / Excellent requires two concrete observations AND that you cannot name a realistic improvement.** If you can name one, cap at 4.
   > - Do not grade on effort, intent, or potential. Grade only what is visible in the frames.
   > - Compare on-screen claims against the repo ground truth. If the hero says *"all"* / *"every"* / shows a grid of N items but the repo has more, **cap Intent delivery at 2 / Weak** and note the undercount. An unverified claim is weaker than a verified one.
   >
   > **Rate each of Legibility, Scene clarity, Voice match, Intent delivery (1–5 Poor/Weak/OK/Strong/Excellent)** with a one-sentence justification citing specific frame evidence. Do not reference any prior conversation — judge only what you see in the frames and read in the ground truth above.
   >
   > **At the end, for any score ≥ 4, answer: "what specific change would push this to 5?" If you have an answer, lower the score by one.**

3. **Fill Claude's repo-fidelity row** with a one-sentence justification.
4. **Ask the user** for the 3 User rows via the `AskUserQuestion` tool — **in Manual and Semi-auto only**. In **Auto** mode, skip the User rows entirely; compute the overall average from Code + AI + Claude rows alone and flag in the run file that User ratings were not collected (so the evaluations index can weight it correctly).

   Use four questions in one call: Hero moment delivery, Visual impact, Ship-worthiness, and a fourth free-text-via-Other for the one-line feedback. Structure each rating question with four labeled options matching the scale (omit 5 to fit the 4-option max; users can pick "Other" to enter 5/Excellent or a custom score). Example shape:

   ```
   AskUserQuestion({
     questions: [
       {
         header: "Hero moment",
         question: "Hero moment delivery — after one loop, would a cold viewer get *what* this repo is *and why* they'd reach for it?",
         options: [
           { label: "2 / Weak", description: "Noticeably misses" },
           { label: "3 / OK", description: "Gets there, nothing more" },
           { label: "4 / Strong", description: "Clearly delivers" },
           { label: "1 / Poor", description: "Falls apart" }
         ],
         multiSelect: false
       },
       { header: "Visual impact", question: "Visual impact — does it make you want to try the repo?", options: [/* same 4 */], multiSelect: false },
       { header: "Ship-worthiness", question: "Ship-worthiness — would you paste this into the README today, as-is?", options: [/* same 4 */], multiSelect: false },
       {
         header: "Feedback",
         question: "One line of free-text feedback — the single most useful signal for next time.",
         options: [
           { label: "Nothing to add", description: "Skip this round" },
           { label: "Add a comment", description: "Pick 'Other' to type your line" }
         ],
         multiSelect: false
       }
     ]
   })
   ```

   The "Other" escape hatch covers 5 / Excellent and any other custom response. Capture the returned labels + any `annotations.notes` or "Other" text into the scorecard.

Display the completed table, grouped by rater, then compute an overall simple average. Keep the full table in the run file.

```
| Criterion            | Rater  | Score        | Note                                                   |
|----------------------|--------|--------------|--------------------------------------------------------|
| Hero moment delivery | User   | (ask user)   | (ask user)                                             |
| Visual impact        | User   | (ask user)   | (ask user)                                             |
| Ship-worthiness      | User   | (ask user)   | (ask user)                                             |
| Repo fidelity        | Claude | 4 / Strong   | Mirrors README phrasing; tagline could be tighter.     |
| File size            | Code   | 5 / Excellent| 2.4 MB (10 MB target).                                 |
| Dimensions           | Code   | 5 / Excellent| 1200×675 matches spec.                                 |
| Loop duration        | Code   | 5 / Excellent| 20.1 s inside 15–25 s band.                            |
| Loop seam            | Code   | 4 / Strong   | 1.3% first/last-frame diff (threshold 2%).             |
| Palette size         | Code   | 5 / Excellent| 212 colors, no banding flagged.                        |
| Legibility           | AI     | 4 / Strong   | All 7 headlines readable at native size.               |
| Scene clarity        | AI     | 3 / OK       | Cron and JWT scenes blur into each other.              |
| Voice match          | AI     | 4 / Strong   | Matches README's "one-off utility" framing.            |
| Intent delivery      | AI     | 3 / OK       | Shows *what* each tool does, not *why* a user needs it.|
```

### 6.4 Evaluation log (two-tier)

Write all evaluation files under `./evaluations/` in the **user's current working directory** — NOT the plugin cache, which is wiped on `/plugin update`. Create the directory if it doesn't exist on first dev-mode run.

**Tier 1 — curated aggregate (committed):** `./evaluations/index.md`
- Rolling stats per criterion across runs
- Notable lessons learned
- Recurring failure modes
- Edited by the meta-skill (Phase 6.5) during retros

**Tier 2 — raw per-run files (gitignored by default):** `./evaluations/runs/<YYYY-MM-DD>-<slug>.md`
- The brief
- The scorecard
- User's free-text feedback
- Path to the archived `hero.gif` / HTML if user opts to keep them

User can opt in to commit specific runs (typically OSS repos they're happy to publicize).

### 6.5 Meta-skill: `repo-visuals-retro`

A separate skill (not part of `repo-visuals`'s runtime) for improving the skill itself. See `../repo-visuals-retro/SKILL.md` for its own design. Invoked on-demand when you have enough samples to spot patterns — not automatically per run.
