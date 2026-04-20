---
name: repo-visuals
description: Create animated hero GIFs (and later: static hero images, social cards) for GitHub repositories. Runs a structured discovery conversation (scan repo → propose creative scenarios → agree on a brief), then designs a bespoke HTML animation, previews it in the browser, and exports it as an optimized GIF. v1 ships hero GIF only.
---

# repo-visuals

Turn a repo (GitHub URL, local folder, or free-text brief) into a hero GIF that a viewer sees at the top of the README and instantly understands *what this project does and why it's interesting*.

The skill's quality comes from the **discovery dialog**, not from templates. Every hero is bespoke.

## Phases

1. **Discovery** — scan the repo, summarize findings, ask the user about vibe/audience/hero moment, propose 2–3 scenarios, converge on a brief.
2. **Build** — write HTML/CSS/JS for the chosen scenario. No storyboard step.
3. **Preview & iterate** — open the HTML in the user's default browser, iterate in text until the user says ship.
4. **Export** — convert HTML to optimized GIF via Puppeteer screencast + ffmpeg palette pipeline.
5. **Output** — place the GIF in the target repo; optionally open a PR that embeds it in the README.

---

## Phase 1 — Discovery

Discovery runs **before any HTML is written**. Its job: go from a vague ask ("make a hero GIF for my repo") to a specific, committed creative brief.

### 1.1 Activation

Enter discovery mode whenever the user invokes the skill, **unless** they explicitly say "skip discovery, I have the brief ready."

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

Summarize findings back to the user in ~6–10 bullets so they can correct misreadings early.

### 1.4 Direction questions (after the scan summary)

Ask these as a structured batch, with suggested defaults based on what the scan found so the user can just accept or redirect:

1. **Where will this hero live?** — README top / project website / social posts (Twitter, LinkedIn) / conference slide / internal demo / elsewhere. *This drives dimensions and loop length.*
2. **Do you want a GIF output?** — yes / no. If **no**, the skill still produces the HTML animation and the user takes it from there (e.g. screenshots, drops into a site). Default: yes. *(MP4/WebM, static PNG, and square social cards are planned for v2+ — see appendix.)*
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
- [ ] GIF wanted? (yes/no)
- [ ] Placement agreed (README / website / social / slide / other)
- [ ] Duration chosen (typical: 15–25s loop; default 20s)
- [ ] Dimensions chosen (see §1.7 — NOT a fixed default; pick per repo and placement)

Write the brief back to the user in a compact block. Wait for **"go"** before writing any HTML.

### 1.7 Dimension selection

Dimensions are **not fixed**. Choose per repo based on what the hero needs to show:

| Aspect | Typical use | When to choose |
|---|---|---|
| 1200×675 (16:9) | Rich product demo, multi-scene storytelling, terminal + UI + graph | CLI tools with visual output, apps, dashboards, complex projects |
| 1200×450 (~8:3) | Compact demo with a primary focus area | Most libraries with one standout feature |
| 1200×400 (3:1) | Banner-style, tagline + single animated flourish | Simple libraries, frameworks, minimalist vibe |
| 1200×300 (4:1) | Slim marquee, logo + one beat | Tiny utilities, one-liners, brand-first projects |
| 1200×200 (6:1) | Ultra-slim status-line feel | CLI themes, shell utilities, prompts |
| 800×800 (1:1) | Social-card crossover | When the hero will also post to Twitter / LinkedIn |

Recommend one based on the scan (forcefully, per the recommendation style), then let the user override.

---

## Phase 2 — Build

Once the brief is locked and the user says "go", write the HTML in **one file** (`index.html` in a working directory for this repo's hero).

### 2.1 Working directory

Default layout:

```
<current-dir>/repo-visuals-work/
  index.html        # the hero animation source
  assets/           # any images/SVGs the scenario needs
```

Use `repo-visuals-work/` so the scratch files stay obviously separate from the target repo.

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

- **Windows**: `start repo-visuals-work/index.html`
- **macOS**: `open repo-visuals-work/index.html`
- **Linux**: `xdg-open repo-visuals-work/index.html`

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

### 4.3 GIF pipeline (the proven recipe)

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

### 4.4 Output file name

`repo-visuals-work/hero.gif` — keep in the scratch dir until Phase 5 (Output) moves it.

---

### Appendix — planned v2 formats (not in v1)

When multi-format support is added, these become Phase 4.5+:

- **MP4 / WebM loop** — `libx264 -crf 18` or `libvpx-vp9 -crf 32`. Higher fidelity, smaller files. Note: GitHub renders `.mp4` uploaded via issue/PR drag-and-drop but not `.mp4` checked into the repo and linked in markdown.
- **Static PNG** — single-frame Puppeteer screenshot at the chosen "hero moment". Offer a 9-frame contact sheet so the user picks the moment.
- **Square social card (800×800 or 1200×1200)** — variant of static PNG, often reframed rather than cropped.

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

If the user doesn't want a PR, leave `hero.gif` at `repo-visuals-work/hero.gif` and print the path. Don't modify the target repo.

---

## Phase 6 — Evaluate

Score the **final artifact**, not the process. Always runs at the end of every work.

### 6.1 Criteria (5 dimensions)

| # | Criterion | Who rates | Signal for low score |
|---|---|---|---|
| 1 | **Hero moment delivery** | User | Viewer wouldn't "get it" in 10 seconds |
| 2 | **Repo fidelity** | Claude | On-screen text, terminology, vibe don't feel like the repo's own voice |
| 3 | **Technical polish** | Claude | Blurry text, palette banding, loop seam jank, over-budget file |
| 4 | **Visual impact** | User | Doesn't make a viewer want to try the repo |
| 5 | **Ship-worthiness** | User | Gut-check: would you put this on the repo today? |

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

Display as a markdown table at the end of the work. Claude fills its own criteria first with one-sentence justifications, then asks the user for their three:

```
| Criterion            | Score       | Note                                                    |
|----------------------|-------------|---------------------------------------------------------|
| Hero moment delivery | (ask user)  | (ask user)                                              |
| Repo fidelity        | 4 / Strong  | Mirrors README phrasing; tagline could be tighter.      |
| Technical polish     | 4 / Strong  | Sharp text, clean loop, 8.2 MB (under 10 MB cap).       |
| Visual impact        | (ask user)  | (ask user)                                              |
| Ship-worthiness      | (ask user)  | (ask user)                                              |
```

After the user fills in their three, show the completed table and compute an overall average. Also ask for **one line of free-text feedback** — the single most useful input for future improvement.

### 6.4 Evaluation log (two-tier)

**Tier 1 — curated aggregate (committed):** `<skill-dir>/evaluations/index.md`
- Rolling stats per criterion across runs
- Notable lessons learned
- Recurring failure modes
- Edited by the meta-skill (Phase 6.5) during retros

**Tier 2 — raw per-run files (gitignored by default):** `<skill-dir>/evaluations/runs/<YYYY-MM-DD>-<slug>.md`
- The brief
- The scorecard
- User's free-text feedback
- Path to the archived `hero.gif` / HTML if user opts to keep them

User can opt in to commit specific runs (typically OSS repos they're happy to publicize).

### 6.5 Meta-skill: `repo-visuals-retro`

A separate skill (not part of `repo-visuals`'s runtime) for improving the skill itself. See `../repo-visuals-retro/SKILL.md` for its own design. Invoked on-demand when you have enough samples to spot patterns — not automatically per run.
