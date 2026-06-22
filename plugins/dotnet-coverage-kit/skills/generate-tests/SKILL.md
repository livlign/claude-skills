---
name: generate-tests
description: "Generate unit tests for a .NET service following the coverage-kit conventions. Use when the user asks to 'generate tests', 'backfill tests', 'characterize this service', or 'add tests for' a target after coverage-init has run. Operates in characterization mode (freeze current behavior for existing code) or spec mode (assert intended behavior for new/changed code), enforces the run-capture-fill loop, routes untestable units to the manifest cannot-test log, can fan the backfill out across a user-chosen number of parallel agents for large worklists (asking first, since more agents cost more tokens), and runs a single read-only suite critique before the baseline locks in (auditing cannot-test legitimacy, assertion/C1 depth, and systematic gaps — never the C0/C1 numbers themselves)."
---

# generate-tests

Generates tests under the base rules and this repo's overlay + manifest. Read all three
before generating:
- `${CLAUDE_PLUGIN_ROOT}/rules/unit-testing.base.md`
- `.claude/coverage/refs/unit-testing.md` (repo overlay)
- `.claude/coverage/refs/coverage-manifest.yml` (categories, exclusions, gate)

## Build the full worklist first — then cover ALL of it (do not stop early)

The scope of a backfill pass is **the entire testable set the manifest defines**, not a
handful of "priority" files. Before writing any test, enumerate that set explicitly from the
manifest and write it down as a checklist. The testable set is:

1. Every file matched by a `category_map` target category and **not** matched by an
   `exclusions` pattern (the genuine unit-scope files), AND
2. Every **CARVE-OUT method** documented in an `integration-scope` exclusion's `reason`
   (the thin pure slices of god-classes — the UserService pattern). These are testable units
   even though their file is integration-scope; init recorded them precisely so this step
   covers them.

Items already covered by existing tests are checked off, not re-done. Items in `cannot_test`
are out. Everything else in the set MUST be either tested in this backfill or appended to
`cannot_test` with a reason — there is no third option of silently leaving it untouched.

**Hard rule: a coverage percentage is never a stopping condition.** Do not stop because the
number "looks low" or "looks done." The pass ends only when every worklist item has a test or
a `cannot_test` entry. Stopping at an arbitrary % and jumping to commit is the failure this
rule exists to prevent.

## Phasing — when the worklist is large, plan it and report progress

If the worklist is large enough that one pass is impractical (rule of thumb: more than
~15 target files or ~40 carve-out methods, or it spans multiple test projects), **do not
silently do a slice and stop.** Instead:

1. Split the worklist into phases (group by file/service/test-project so each phase is a
   coherent, runnable chunk).
2. **Tell the user the phase plan up front** — the full count of testable units, how many
   phases, and what each phase covers — before generating. This is the "let me know if it
   needs phases" contract.
3. Execute phases in order. After each phase, report progress as **N of M worklist items
   done** and what remains. Keep going through all phases unless the user says otherwise.
4. The working tree stays dirty across phases; do NOT commit between phases.

## Scaling the backfill — efficiency, then optional parallel fan-out

A legacy worklist can be enormous. Two levers: make each unit cheaper, and (optionally) do many
at once. The efficiency rules apply **whichever way you run** — sequential or parallel:

1. **Batch run-capture-fill per class, not per method.** The dominant cost is build + test
   execution. Write the whole test class for a file, build once, run the class once, capture
   *all* actual values from that single run, then fill. Never pay a build/run cycle per method.
2. **Pre-triage before the loop, using the init signals.** Before the write-build-run loop, scan
   each unit for an untestable signal (direct `DateTime.Now`/`UtcNow`, `Guid.NewGuid`, `Random`
   with no seam; works only against real infra/IO). Route those straight to `cannot_test` — do
   not spend a full cycle discovering it.
3. **Pattern-replicate across siblings.** Legacy services are full of structurally identical
   units (handlers, validators, mappers). Solve the seam/mock setup once on a representative,
   then replicate the shape across the lookalikes. A "phase 0" that builds the shared
   fixtures/builders once feeds this.
4. **Risk-order the worklist** by complexity × churn × fan-in so the most valuable coverage lands
   first and the hardest seam problems surface early (while there is budget to fix them). This
   does not reduce total work — the worklist is still covered in full — it just sequences it well.

### Optional parallel fan-out (ask the user first)

The worklist is independent per file, so it parallelizes cleanly. For a large worklist, **offer**
to run the backfill as a fan-out workflow — but **never auto-spawn agents**. Parallel agents burn
tokens fast, and the right count depends on how quickly the user wants it done and their budget,
so present the trade-off and let them choose:

1. Build and risk-order the full worklist (above). State the total count of testable units.
2. Ask the user how many agents to run, mapping count to a *rough* wall-clock for **this**
   worklist (scale the examples to the real size; caveat that they are estimates and that more
   agents = proportionally more token burn):
   - **1 agent** — sequential, lowest token burn, ~a day for a big service.
   - **3 agents** (default) — balanced, ~6 hours.
   - **10 agents** — fastest, highest burn, ~1 hour.
3. On their choice, invoke the workflow:
   `Workflow({ scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/coverage-backfill.workflow.js",
   args: { concurrency: <chosen>, solution: "<sln>", worklist: [...] } })`.
   If the user just says "go", default `concurrency: 3`.

The workflow partitions the worklist into `concurrency` chunks (one agent each, in its own git
worktree so parallel writes don't collide), generates + adversarially verifies each chunk, then a
single assemble step applies every chunk's patch to the main tree, merges `cannot_test` discoveries
once (no manifest write races), and confirms the full suite is green. It leaves the tree dirty:
the promotion gate below still governs when the baseline report and commit happen.

## Promotion gate — report and commit only when the worklist is exhausted

`coverage-report` (to set/raise the baseline) and any commit are **promotion steps**. They
run ONLY after the entire worklist is exhausted (every item tested or in `cannot_test`) **and
the suite critique below has run**. Per the action ladder, generation itself is edit-only:
leave the tree dirty and stop. Do not run the baseline report mid-backfill, and do not propose
committing a partial backfill — a partial baseline locks in a misleadingly low floor.

**Measure via the wrapper, not by hand.** When you do measure, run the one-command wrapper
`./.claude/coverage/tools/report.sh` (it collects with the repo filefilter, joins the manifest, and
**persists `coverage/REPORT.md`**). Do NOT hand-run `run-coverage.sh` + `coverage-gate.py` and
read the numbers off stdout — that leaves no saved report and skips the repo scoping, so the
report effectively goes missing. If `report.sh` isn't installed yet (repo pre-dates it), copy
it from `${CLAUDE_PLUGIN_ROOT}/scripts/report.sh` first, then run it. Only after `REPORT.md`
exists do you write the measured Adjusted into `baseline.recorded_overall`.

## Suite critique — once, before the baseline locks in

When the worklist is exhausted and the suite is green, run a single critique over the *finished*
suite **before** `coverage-report` sets the baseline. This is the natural moment: fixing is
cheapest now, and a dodged `cannot_test` or shallow tests would otherwise freeze a misleading
floor. Run `report.sh` first so the critique can use the report's analytics (e.g. low-C1
buckets) as leads.

Spawn **one read-only subagent** over the whole suite + the manifest + the report. **Single and
read-only on purpose** (same reasoning as the init critique): systematic problems — a bucket
dodged wholesale, the same smell everywhere — are only visible to one reviewer seeing all of it,
applying one standard; it produces findings, it does not silently rewrite tests. Its mandate:

1. **`cannot_test` legitimacy.** Re-check **every** `cannot_test` entry against the rubric
   signal: is it genuinely untestable (no seam, real infra, nondeterministic), or did generation
   take the easy out? Flag any entry where a seam exists or a deterministic test is feasible.
   This is the escape hatch — audit it hardest.
2. **Assertion quality / C1 depth.** Find files where C0 is high but C1 is low (lines run but
   branches never asserted → shallow tests) and any vacuous/tautological assertions the
   per-chunk verify missed (asserting a mock returns what it was set to). Whole-suite view —
   do not re-do the per-test check the backfill workflow already did.
3. **Systematic patterns.** Clusters of `cannot_test` that share one fixable seam (one
   extract-interface unlocks many), a category dodged wholesale, repeated smells.
4. **Highest-ROI next moves** — concrete, not vibes.
5. **In-scope coverage gaps — TARGET layer only (the lens that is easiest to miss).** From the
   report's **Risk Hotspots** and per-file table, list every **target-layer** method/file whose
   testable branches fall below the diff-coverage branch threshold — uncovered branches in code we
   OWN. These are NOT `cannot_test` and NOT shallow-assertion cases (item 2 only catches
   covered-but-unasserted lines); they are **unfinished characterization** — a complex method got a
   happy-path test and its other branches (filters, switch arms, error paths) were never executed.
   A **target**-bucket row in Risk Hotspots is the signal. An `excl:*` hotspot is fine to leave (it
   is integration/E2E-covered, not unit) — only target-layer gaps count here. Close them before the
   baseline locks (see Output).

**Trust the C0/C1 numbers; do not second-guess them** — they are tool output; if a number looks
wrong that is a pipeline check (file-filter, merge, instrumentation), never an LLM opinion. But
trusting the numbers is NOT ignoring them: item 5 exists precisely to ACT on the in-scope gaps they
reveal. (A target method at 70% slipping into the baseline because the critique was "number-blind"
is the exact failure this item closes.)

Output: split findings into (a) **clear-cut fixes to apply now**, before baseline — a
`cannot_test` entry that is actually testable → write the test and remove the entry; **a
target-layer coverage gap (item 5) → write the missing branch tests (run-capture-fill) until the
method clears the threshold and drops off Risk Hotspots**; and (b) **judgment calls / larger
refactors** escalated to the human. Apply the clear-cut fixes, then re-check them (loop until none
remain) — a fix can surface another, e.g. writing the test that retires one `cannot_test` reveals a
shared seam that retires more. **The baseline does not lock while any target-layer in-scope gap
remains.** Append the findings to the report under `## Suite review`. Only after this loop settles
does the baseline report run.

## Pick the mode

- Target existed at the baseline → **characterization**.
- Target is new, or a line changed after the baseline → **spec**.
- Mixed file → characterize baseline methods, spec the new/changed ones.

Skip anything matched by a manifest `exclusions` pattern — that uncovered state is
intentional and explained by the manifest.

## Characterization mode — run-capture-fill (hard precondition)

For each target method:

1. Write the test: explicit pinned inputs, dependencies mocked through interfaces,
   a placeholder expected value. Assert observable output/state/exceptions — not mock
   call order (interaction verification only where the side effect IS the behavior:
   message publish, email send, external sink with no return value).
2. **Run the single test.** This is required. Do not write an expected value from
   reading the source.
3. Read the actual value from the run. Write it into the assertion.
4. Re-run until green.

If step 2 is impossible — does not compile in isolation, needs real infrastructure,
depends on wall-clock/id/random with no seam — DO NOT write a predicted assertion.
Add the target to the manifest `cannot_test` list with a category and reason
(`nondeterministic`, or `integration-scope` if it needs real IO). Make no source change
to fix it; the backfill freezes source.

**Cover the BRANCHES, not just one happy path** — a target method is "done" only when its
branches are exercised, not when it merely has *a* green test. For a method with branching
(filters, a `switch`, error paths, asc/desc, null guards), one input lands ~one path and leaves
the rest uncovered — that is the partial-coverage gap that otherwise slips to the report's Risk
Hotspots (e.g. a `GetAll` with keyword + type + unit filters and a 3-way order switch needs a
test per filter and per switch arm). Enumerate the method's branches and pin an input for each;
a branch that genuinely cannot be reached without real infra goes to `cannot_test`, not ignored.
This is cheapest here, at write time — the suite critique's item 5 is the backstop, not the plan.

## Spec mode

Expected values come from the requirement/acceptance criteria, not from running the code.
The run-capture-fill loop does not apply. If a new unit is not testable through its
interfaces, that is a dependency problem to fix in this change (extract interface, inject
seam) — do not skip and do not widen the test project's references.

## First-run triage (characterization backfill)

A characterization test is green by construction once run-capture-fill completes, because
the assertion holds the actual output. The only judgment calls are the units where the
captured output looks like a latent bug. Freeze them anyway (assert the actual value) and
record them as observations for the report — frozen, not endorsed. Do not change behavior.

## Output of a generation pass

- New/updated test files mirroring source structure, named `Method_Scenario_Expected`.
- Any newly discovered untestable targets appended to the manifest `cannot_test` list.
- A short list of suspected-latent-bug observations (target + what looked wrong), for the
  report's observations section. Do not fix them.
- The updated worklist checklist: N of M items done, what remains (and which phase, if phased).

Only once the worklist is fully exhausted **and the suite critique has run** (see the promotion
gate and "Suite critique"), run `coverage-report` to measure and set the baseline. Do not assert
coverage numbers yourself — they come from the tool. Until then, leave the tree dirty and stop
without committing.
