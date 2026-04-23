# Lessons

Durable lessons surfaced from past `repo-visuals` runs. Each one came from a concrete user correction and is worth re-checking against `SKILL.md` on every retro — if a lesson isn't reflected in the skill, it will regress.

Format: rule → **Why** (the incident) → **How to apply**.

---

## 1. Production-grade over speed-to-result

For creative/design iteration, prefer slow, iterated passes over fast script→export→done runs. Export is the **last** step, not the midpoint.

**Why:** In the `2026-04-21 · emtyty/devtool v2` run, the flow went from "got the idea" → write HTML → capture → encode → eval scorecard in minutes. User called it out: *"the flow was like to make the result as fast as possible, not focus on delivery production-grade."* The run scored 2/3/2 on the three User criteria even though Claude/AI/Code raters all rated 4–5 — a gap that says the skill optimized for the measurable axes while skipping the judgment beats.

**How to apply:**
- After writing the HTML, do a real preview-and-iterate beat with the user before moving to export. Don't skip or compress §3 of `SKILL.md`.
- When in doubt between "ship this pass" and "one more pass," prefer the extra pass.
- Don't treat a first-working artifact as a finished artifact.
- Auto mode is not a license to rush. "Execute autonomously" means "don't ask for trivial confirmations," not "skip iteration beats."

---

## 2. Hero claims must match the repo's real scope

If a hero says "all", "every", or "the whole" — or shows a grid meant to represent the repo's scope — the count/content on screen must match reality, or the hero must explicitly frame itself as a sample.

**Why:** In the `2026-04-21 · emtyty/devtool v2` run, the thesis was "One tab. All the small tools." with a finale grid of **8 tool cards** — but the repo has **20–30 tools**. User feedback: *"the GIF just shows 8 tools, not exposing all the greatness of it."* A good layout thesis became a factual undercount that undermined the pitch.

**How to apply:**
- During Phase 1 scan, pull the target repo's actual inventory from source (route files, README sections, `src/tools/*`, CLI registrations). Don't rely on memory or a partial README.
- If the real count is too large for a grid, frame it: scroll rail that clearly extends beyond the viewport, a "30+ tools" caption, or categorized groupings. Don't silently sample.
- The AI-eval "Voice match" criterion can miss this; feed the real inventory count into the AI eval prompt so it can flag factual drift.
- Words to double-check before shipping: *all, every, each, the whole, complete, full*. If on-screen reality doesn't back up the word, change the word or the reality.

---

## 3. README heroes must blend with GitHub's surface

For heroes destined for a GitHub README top slot: stage bg should match GitHub's own canvas (`#0D1117` dark / `#FFFFFF`/`#F6F8FA` light), and the display type should be sans (IBM Plex Sans, Geist, Manrope) rather than editorial serif. Italics within the sans can still carry the "accent voice" work.

**Why:** On `livlign/repo-visuals` in April 2026, a Fraunces + midnight-indigo (`#141C35`) hero was rejected mid-run with two specific notes: the serif "doesn't match well with GitHub font" and the surface should "blend with background of github." The hero read as a floating colored block with foreign typography on a GitHub README page — broke immersion. IBM Plex Sans on `#0D1117` sat flush and felt native. Editorial serifs still work for PDF / slide / social contexts; the constraint is specifically README-top.

**How to apply:**
- When placement in §1.1 is "README top" (not social, not slide), bias the format recommendation away from cream-editorial palettes and serif displays.
- In the §1.4 vibe question, flag "editorial / NYT" and "literary serif" options as carrying a GitHub-mismatch risk.
- When proposing the palette in Phase 2, anchor stage bg to the GitHub surface the repo's readers are likely to view (dark-mode default for the dev audience). Treat deviations as a deliberate choice worth calling out to the user.

---

## 4. Dimensions tailored to repo spirit, not fixed at 1200×675

1200×675 is the **default** when the repo gives no strong signal — not a lock. Deviate when the target repo's spirit argues for another shape: slim banner for wordmark brands, wider for dashboards/timelines, taller for stacked-panel tools, square for mobile/social-first.

**Why:** The user has raised this more than once. A fixed 16:9 crop misrepresents repos whose identity is a different shape — a slim terminal-banner repo looks wrong as a chunky 560px-tall hero, and a data-viz timeline wants more lateral room than 16:9 gives. The hero should feel like it belongs to *that* repo, not like a template applied over it. Original SKILL.md wording was "Dimensions — locked," which encoded the wrong default posture.

**How to apply:**
- During the scan, note the existing hero image's shape and the format archetype from `craft/reference-gallery.md`.
- If they argue for a non-16:9 dimension, surface the tailored option alongside the default in the direction-questions batch and let the user pick.
- If the repo gives no strong signal, just use 1200×675 without making it a question.
- Never frame the default as "locked" in user-facing text.
- Capture pipeline (`scripts/screenshot.js`, `capture.js`) already accepts `--width`/`--height` — pass the brief's chosen size through; don't hardcode.
- Craft rules (font-size floors, clearance minimums) are written around 1200×675 but expressed as ratios; recompute when deviating.

---

## 5. Break from ast-graph template DNA — pitch a distinct concept first

When starting a new hero, propose a *visually distinct* concept before writing any HTML. Don't default to the ast-graph template pattern (top brand chip + STEP 01/04 indicator + rotating headline slot above a card stage). Every repo deserves its own structural idea; inheriting chrome from a strong template leads to sameness across projects.

**Why:** On `livlign/claude-skills` in April 2026, the v1/v2 drafts both used the ast-graph scaffolding — header bar with brand chip, ACT 01/03 step indicator, big rotating hero headline above a card-within-card stage. User called it out directly: *"this got a lot of similar wit ast-graph template. Let's redesign a whole new with more creativity."* The v3 redesign used a "wall of heroes + bloom-and-reveal" concept (18-cell grid of visually diverse mini-heroes, one blooms into a centered spotlight) and was accepted on the first look. User followed up with explicit praise: *"I like your creativity in v3, let's keep in mind for next projects."*

**How to apply:**
- After the scan, **before writing HTML**, pitch 2–3 scenarios as usual (§1.5) — but explicitly call out how each one diverges structurally from the ast-graph reference, not just which feature it foregrounds. If all three proposals share the ast-graph chrome pattern, the proposal phase hasn't done its job.
- If the first draft falls into the ast-graph chrome by default (brand chip top-left + step indicator top-right + hero headline slot + card stage), proactively offer a clean-slate redesign rather than tweaking inside that scaffold.
- Creative-direction options worth having in the bank (not exhaustive): wall/gallery/catalog of variations, Russian-doll meta-reveal, kinetic-type declaration, loom/weaving of ribbons, dev-console conversation playback, camera pull-back parallax, polaroid stack, film-strip contact sheet, single-glyph transformation.
- The ast-graph templates remain valuable as structural references (timeline scheduler, rotating slot mechanics, scene-class pattern) — borrow the *engineering*, not the *composition*.

---

## 6. Retina capture (deviceScaleFactor: 2) is the default, not an opt-in

Puppeteer screencast at `deviceScaleFactor: 1` produces noticeably softer GIFs than the HTML preview, especially on small type and fine UI details in embedded assets. Capturing at `deviceScaleFactor: 2` (rendering the page at doubled internal resolution) and then lanczos-downscaling to the final size in ffmpeg gives dramatically sharper output.

**Why:** On `gui-cs/Terminal.Gui` in April 2026, the user explicitly flagged this: *"the gif we export before is much blurrier than the html. Can we not make that mistake this time?"* Switching from 1× to 2× capture with `scale=W:H:flags=lanczos+accurate_rnd+full_chroma_int` during the two-pass palette encode produced a materially sharper hero in one pass — a bigger win than any amount of dither/palette tuning.

**How to apply:**
- `scripts/capture.js` currently hardcodes `deviceScaleFactor: 1`. Treat this as a structural bug: at minimum accept a `--scale` CLI flag; better, default to `2` with an opt-out for size-sensitive runs.
- In the ffmpeg two-pass encode, add `scale=W:H:flags=lanczos+accurate_rnd+full_chroma_int` to *both* `palettegen` and `paletteuse` passes. The extra scaling flags are effectively free but noticeably cleaner.
- Fiddling with `bayer_scale`, `dither=none`, and `stats_mode=full` vs `diff` matters far less than capturing at 2× to begin with. Only reach for those after retina is on.
- Expect the frame PNGs to be ~4× larger on disk (2× width × 2× height). This is fine — they are temporary artifacts, deleted after encode.

---

## 7. Embedding a user-provided asset inside the hero has its own rulebook

When a reviewer, user, or upstream repo provides a GIF/MOV/screenshot that must appear *inside* the outer hero (as a demo frame, screenshot card, etc.), the composition has constraints that chrome-only heroes don't.

**Why:** On `gui-cs/Terminal.Gui` in April 2026, a PR reviewer asked for a specific animated demo to be embedded in the hero. Several things went wrong before getting right: the inner GIF was 37.7s (out-of-range for a 15–25s outer loop), the inner was pre-downscaled to 860w which compounded blur after the outer's own downscale, and the outer's colorful chrome fought the inner's vivid ANSI palette for the 256-color budget.

**How to apply:**
- **Loop alignment:** the inner asset's loop length should be equal to, or a clean divisor of, the outer loop. For a mismatched source, use `ffmpeg -filter_complex "setpts=<ratio>*PTS"` to speed-trim (e.g., 37.7 s → 20 s at `setpts=0.5305*PTS`) and regenerate the palette. A seamless inner-loop = seamless outer-loop.
- **Resolution:** keep the inner at **native source resolution** (not pre-downscaled). The browser has more pixels to sample from during the outer capture, which compounds positively with retina capture.
- **Palette budget:** a colorful inner + colorful outer chrome will blow the 256-color GIF palette. The fix is to keep the outer chrome monochrome or low-chroma so the inner's colors "pop" and the palette stays honest. We confirmed this on Terminal.Gui: switching the outer from cyan/purple/yellow accents to black/white/gray let the AttributePicker's ANSI red/blue/yellow render cleanly.
- **Reviewer assets are sacred.** If a reviewer supplied the asset, do not silently replace it with a self-generated recording — that re-opens their review. If a replacement is a better match, flag the scope change explicitly and ask.

---

## 8. Symmetry is load-bearing — check paddings, margins, and anchors deliberately

Before shipping, verify that top-padding equals bottom-padding and left-margin equals right-margin. When shrinking a right-anchored element (e.g., `shot-wrap` with `right: 24px`), preserve its **left-edge position**, not its right margin — otherwise the left whitespace gap grows as the element narrows, creating an orphaned composition.

**Why:** On `gui-cs/Terminal.Gui` in April 2026, the initial layout had `top: 56px` on the title block and `bottom: 26px` on the footer — asymmetric. User called it out: *"reduce the height so the padding Cross-platform to top equal MIT to bottom."* Later, when the demo was shrunk from 788×528 to 686×460 while `right: 24` stayed fixed, the demo's left edge receded from 388 to 490, leaving ~146px of dead whitespace on its left. User: *"the gif now is farther to the left than before."* Final resolution combined: (a) equalize top/bottom padding (both 40px), (b) equalize left/right margins by trimming the stage width, (c) preserve the demo's left-edge position. Other related symptoms observed: stat labels like `'17 / Since` that read cryptic cold — if a label isn't obvious to a first-time viewer, rewrite (`Since 2017`).

**How to apply:**
- Add a §1.6 convergence-checklist item: **paddings are symmetric (top = bottom, left = right) unless a deliberate asymmetry is called out in the brief.**
- When resizing a right-anchored element, decide upfront whether you're preserving the left edge (anchor there with `left: <x>px`) or the right margin (keep `right: <x>px`). The wrong choice creates orphan whitespace.
- Cold-read every on-screen label before ship. If a cold reader can't explain what `'17 / Since` means in 2 seconds, it's failed the legibility bar — rewrite as `Since 2017` or remove.

---

## 9. "Reduce" means reduce

When the user says *reduce the size*, they mean make it smaller. If I'm rebalancing, equalizing, or symmetrizing in a way that happens to *grow* a dimension — that's a misread. Restate and re-confirm rather than execute.

**Why:** On `gui-cs/Terminal.Gui` in April 2026, user asked *"reduce the height so the padding Cross-platform to top equal MIT to bottom"* — intent was reduce. I interpreted as equalize-padding-while-preserving-content, which bumped the demo from 749×502 to 788×528 (bigger). User corrected: *"no i mean reduce the size of the hero, not increase it to bigger."* The literal word was clear; the misread cost a capture-and-encode round trip.

**How to apply:**
- Any time a directional verb ("reduce", "smaller", "tighten", "cut") combines with a relational clause ("so that …"), treat the directional verb as load-bearing. If the easy execution of the relational clause would violate the direction, stop and restate.
- In terms of CSS: `width: 788px → 686px` is a reduction; `width: 749px → 788px` is not, regardless of what padding or symmetry argument motivates it. Visibly-bigger is visibly-bigger.
- This is a specific instance of the broader "deliver intent, not just instructions" principle in `SKILL.md §3.6`.

---

## How this file is used

The `repo-visuals-retro` skill should read this file at the start of every retro, alongside the run evaluations. Each lesson is a claim about what `SKILL.md` *should* encode. For each lesson, verify the corresponding guidance is still present in the current `SKILL.md` — if it's been weakened or lost, propose re-adding it. New lessons discovered during a retro should be appended here in the same format.
