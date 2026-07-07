# dotnet-coverage-kit

A toolkit that helps .NET teams add unit tests to old code, write good tests for
new code, and measure test coverage in a way everyone can trust. The coverage numbers
come from real tools (not guesses), and a simple text file in each repo explains why
every file is tested or skipped.

```text
   ┌────────────────────┐   plan the repo. A parallel sweep classifies every file;
   │   coverage-init    │   mixed files carve out their testable methods, so a
   └─────────┬──────────┘   god-class is never skipped whole.
             │   draft, self-critique, refine  (loops until the plan is clean;
             ▼                                   only unclear cases go to you)
   ┌────────────────────┐   write the tests  (optional parallel backfill).
   │   generate-tests   │   GOAL: Adjusted (testable) coverage reaches the
   └─────────┬──────────┘   target, default C0 95% / C1 85%.
             │   suite self-critique, then fix  (before the baseline locks in)
             ▼
   ┌────────────────────┐   measure vs target + baseline
   │  coverage-report   │   (one command, action-first report)
   └─────────┬──────────┘
             ▼
   ┌────────────────────┐   set the baseline. The floor is recorded a few points
   │   merge to master  │   below the target (headroom); it only moves up.
   └─────────┬──────────┘
             ▼
   ┌────────────────────┐   keep it green: diff coverage at target + ratchet +
   │  check each change │   scope guard  (dev locally + CI gate on every PR to master)
   └────────────────────┘

   Already onboarded on an older kit version? Run coverage-redo instead of
   coverage-init: it re-audits, corrects and migrates the manifest, and fills
   only the newly-found gaps.
```

> 🔎 **Full visual overview:** open [`docs/overview.html`](docs/overview.html) in a browser for the
> complete pipeline — the parallel agents, the critique passes, the report anatomy, and the gate.

**Step 1 · `coverage-init`** — set up the repo (do this once)
- **How:** run the `coverage-init` skill inside the repo.
- **What:** it reads through your code to sort every file — what to test, what to skip and
  why — and drafts the plan (`coverage-manifest.yml`) plus the config it needs. Then a
  **self-critique loop** kicks in: a separate reviewer checks the draft against the same rules,
  feeds its corrections back in, and keeps refining until the only thing left is the genuinely
  unclear calls — which it brings to you. It also catches the *same* mistake repeated across
  projects.
- **Why:** every repo is a little different. Writing the plan down once, in a file, means
  the results are repeatable and clear to everyone — not a one-time AI guess. The
  double-check matters because no one can carefully review a long skip-list by hand every
  time.
- **Big repo?** Sorting every file can be a lot of reading. The skill can fan that step out
  across several agents in parallel — it asks you first how many to run (more agents finish
  sooner but cost more). The final double-check stays a single reviewer on purpose, so it can
  catch mistakes that repeat across the whole codebase.

**Step 2 · `generate-tests`** — write the tests
- **How:** run the `generate-tests` skill and point it at the code you want to cover.
- **What:** for old code, it writes tests that lock in how the code behaves today. For
  new code, it writes tests that check the code does what it *should*. Code that can't be
  tested safely is listed in the manifest with a reason — the source code is never changed.
- **Why:** you get a safety net so future changes can't break things by accident, without
  touching the code you are protecting.
- **Goal:** the aim is for the *testable* part of the code (the "Adjusted" coverage, after
  skips) to reach the repo's target, by default 95% of lines and 85% of branches. That target
  lives in the manifest: the backfill drives toward it, the PR gate holds new code to it, and
  the baseline floor is recorded just under it so normal churn does not trip the check.
- **Self-check before the baseline:** once the suite is written, a **critique loop** reviews it —
  is anything marked "can't test" actually testable? are any tests shallow? — and fixes what it
  can before the baseline locks in. (It never second-guesses the coverage numbers; those are the
  tool's.)
- **Big backlog?** On a large legacy service this can be a lot of tests. The skill can fan the
  work out across several agents in parallel — it asks you first how fast you want it (e.g. 1
  agent ≈ a day, 3 ≈ a few hours, 10 ≈ ~an hour), since more agents finish sooner but cost more.

**Step 3 · `coverage-report`** — measure and explain
- **How:** one command, any time, no arguments — `./.claude/coverage/tools/report.sh` (or run the
  `coverage-report` skill). It writes a saved `coverage/REPORT.md` and prints it.
- **What:** it runs the real coverage tools, then produces a short, scannable report built to
  act on: a one-line verdict (pass/fail + the numbers), a **Do next** list of the highest-impact
  files to test (and how many points they'd add), quick insights, and the by-bucket breakdown.
  The full per-file drill-down stays in the HTML report, so the summary isn't a wall of text.
- **Why:** the numbers always come from the tools, never from guessing; nothing is hidden — and
  the same report runs locally and in CI, so what you see is what the PR sees.

**Check coverage** — keep coverage from slipping
- **How:** while a developer writes or edits code, they run `coverage-report` on their own
  machine to make sure the new tests pass and coverage is high enough. Later, the CI server
  runs the same check automatically when they open a pull request (PR).
- **What:** it checks three things — the new or changed lines are tested, overall coverage
  hasn't dropped below the agreed level, and all tests pass. If any check fails on CI, the
  PR is blocked until it's fixed.
- **Where the "agreed level" comes from:** when you first merge, `coverage-report` writes
  the overall coverage number into the manifest file (saved in git). Each later run measures
  the current coverage and compares it to that saved number. If the new number is lower, the
  check fails — that's how a drop is caught.
- **Why:** you catch problems early on your own machine, and CI makes sure nothing slips
  through — so coverage only goes up, never down.

## A few terms

- **Target (goal):** the coverage level you want the testable code to reach and hold, by
  default 95% of lines (C0) and 85% of branches (C1) on the Adjusted slice. The backfill aims
  for it, the PR gate holds new code to it, and the baseline floor sits just under it.
- **Coverage** — how much of your code the tests actually run. We track lines run and
  decision branches taken.
- **Baseline** — the coverage level on the day you first merge. It becomes the minimum to
  protect from then on.
- **Manifest** — the plain-text plan file in each repo that says what is tested, what is
  skipped, and why.

## What is shared vs. what lives in each repo

Shared (part of this toolkit, the same for every repo):
- `rules/unit-testing.base.md`, `rules/coverage-report.base.md`
- `skills/coverage-init`, `skills/generate-tests`, `skills/coverage-report`, `skills/coverage-redo`
- `templates/coverage.runsettings`, `templates/coverage-manifest.yml`
- `scripts/run-coverage.sh`

Per repo (created by `coverage-init`, owned by your team):
- `.claude/coverage/refs/coverage-manifest.yml` — the plan (what to test, what to skip and why,
  the baseline). This is the one file that changes from repo to repo.
- `.claude/coverage/refs/unit-testing.md` — extra notes for this repo: short for clean codebases,
  longer for older, messier ones.
- `.claude/coverage/refs/coverage.runsettings` — the coverage config.

## How to adopt it (same steps in every repo)

1. Install the toolkit, then run **`coverage-init`**. It reads your projects and drafts the
   plan; you review and fix it.
2. Run **`generate-tests`**. It writes tests for old code and new code. Code that can't be
   tested goes on the skip list (with a reason) — no source changes.
3. Run **`coverage-report`** to get the first real coverage numbers and make all tests pass.
4. Merge to your main branch. That point is your **baseline**. From now on, developers run
   the check locally as they work, and CI runs it on every PR — both keep coverage at or
   above the baseline.

**Already set up on an older kit version?** Run **`coverage-redo`** instead of re-running
`coverage-init`. It re-checks the repo against the current rules, corrects and migrates your
existing manifest (it does not overwrite it), generates tests only for the newly-found gaps
while keeping your existing tests intact, and writes a fresh report.

## Seeing the report on GitHub

The `coverage/` folder is generated and git-ignored, so it only exists on the machine that
ran it. To see results in a pull request, let CI publish them. The run script already writes
a GitHub-flavored Markdown summary (`coverage/html/SummaryGithub.md`); pipe it into the
Actions **job summary** and it shows up on the PR's checks tab — no extra tools, nothing
committed:

`coverage-init` sets this up for you. It copies the run script into your repo at
`.claude/coverage/tools/run-coverage.sh` (committed), so CI runs the exact same script you run
locally, and it scaffolds a workflow at `.github/workflows/coverage.yml`:

```yaml
# .github/workflows/coverage.yml
on:
  pull_request:
    branches: [master]   # only PRs whose target (base) branch is master

jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.0.x'

      - name: Coverage
        run: ./.claude/coverage/tools/run-coverage.sh <solution.sln> ./coverage

      - name: Publish coverage summary
        if: always()
        run: cat coverage/html/SummaryGithub.md >> "$GITHUB_STEP_SUMMARY"
```

The `branches: [master]` filter is on the PR's **base** branch, so this runs only when a PR
targets `master` — not for PRs into `develop`, release branches, etc.

**If your repo already has CI**, `coverage-init` will not clobber it: if a coverage workflow
already exists it leaves it alone, and if a workflow already runs your tests on PRs into
`master` it proposes adding the two coverage steps to that one instead of creating a second
job — so you never pay for duplicate test runs.

### Enforcing it on every change

The CI job runs the **full gate** on each PR to `master`:
- **Diff coverage** — the lines you added or changed must be tested (threshold in the manifest).
  This is what actually forces new code to have tests; the ratchet alone is too weak for small
  PRs.
- **Ratchet** — overall in-scope coverage can't drop below the baseline.
- **Scope-change guard** — you can't quietly dodge the gate by growing the skip-list or dropping
  new code into an excluded folder; that fails the check until a maintainer adds the
  `coverage-scope-change` label to approve it.

Two setup steps make this binding, not advisory:
1. **Make the coverage check required.** In *Settings → Branches → branch protection for
   `master`*, require the Coverage status check to pass before merging. Without this, a red gate
   doesn't actually block the merge.
2. **Protect the floor.** The baseline number lives in the committed manifest; only let it move
   up. Lowering it should be a reviewed manifest change, never a silent one.

Developers get the same gate locally before pushing: `BASE=origin/master ./.claude/coverage/tools/report.sh`.

Want the full browsable HTML report too? Upload `coverage/html` as a build artifact
(`actions/upload-artifact`). Want per-line annotations on changed code and history over
time? Send `coverage/merged.cobertura.xml` to a hosted service like Codecov or Coveralls.

## Rolling out to many services

Start with one repo, end to end. Try your cleanest codebase first to prove the happy path,
then your messiest one to see where the extra notes are really needed. Doing both tells you
whether your repos differ only in structure (small plan changes) or in how they like to test
(bigger notes changes).

## Requirements

Works only with modern, SDK-style `.csproj` projects (a limit of the coverage tool). Older,
non-SDK projects need a different tool (coverlet) and are not covered here.
