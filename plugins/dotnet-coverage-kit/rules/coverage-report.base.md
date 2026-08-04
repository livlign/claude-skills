# Coverage Measurement & Gate — Base Rules (architecture-independent)

How coverage is measured, reported, and gated. Universal across repos. The per-repo
category map, exclusion patterns, baseline number, and ratchet floor live in
`.claude/coverage/refs/coverage-manifest.yml`.

## C0 and C1 definitions

- **C0** = line coverage (statements executed).
- **C1** = branch coverage (decision branches taken).

Both come from the coverage tool. Neither is ever estimated, inferred, or produced by
a language model. The numbers in every report are tool output.

## Tooling

- Collector: dotnet-coverage (Microsoft.CodeCoverage), already transitively present via
  `Microsoft.NET.Test.Sdk`. Invoked with `--collect "Code Coverage;Format=cobertura"`.
- Merge / convert: `dotnet-coverage merge -f cobertura`.
- Report: ReportGenerator (HTML for humans; Cobertura + JsonSummary as machine-readable
  inputs to the report join).

The collector is replaceable: every downstream step consumes Cobertura XML, so swapping
collectors does not change the report logic.

## What the tool produces vs what the manifest explains

The tool produces numbers and the per-file covered/uncovered list. It cannot say *why*
a file is included, excluded, or untestable — that is editorial and lives in the
manifest. The report joins the two:

- File covered or partially covered → reported with its C0/C1.
- File uncovered AND matched by a manifest exclusion pattern → reported as excluded,
  with the manifest's category and reason.
- File uncovered AND in the manifest's cannot-test list → reported as cannot-test, with
  reason.
- File uncovered AND matched by nothing → reported as **uncovered, needs attention**.
  This bucket is the actionable output; it must not be silently absorbed.

## Output artifacts (per run)

`report.sh` writes a dated per-run folder `.claude/coverage/reports/<YYYY-MM-DD>/` holding
`REPORT.md`, `REPORT.html`, and `CANNOT-TEST.md`. A new run creates a new dated folder rather
than overwriting, so prior dates stay for comparison (override with `REPORT_DATE=YYYY-MM-DD`).
`CANNOT-TEST.md` is generated from the manifest `cannot_test` entries, grouped by blocking
construct, each row citing target, reason, and unlock; it is not hand-written and invents no
line numbers the manifest does not supply.

## Report hierarchy

Overall → category → project → file. Categories come from the manifest's `category_map`.
Repos without clean layering collapse to overall → project → file (single `uncategorized`
category). Every report shows C0 and C1 at each level, plus the three lists above
(included, excluded-with-reason, cannot-test-with-reason) and the needs-attention bucket.

## Two-pass reporting: Raw + Adjusted

The collector instruments every loaded production assembly. Reporting target coverage
against that whole total is misleading: it is dominated by code the manifest declared
out of target (e2e, integration, dto-no-logic, generated, non-product) and barely moves
as real tests are added. So every report shows **two passes**, for both C0 and C1:

- **Raw** — covered/total over all instrumented code. The honest unfiltered number.
- **Adjusted** — covered/total over the **target** set only (the `category_map` categories
  plus `uncategorized`); files matched by an `exclusions` pattern are removed from the
  Adjusted denominator. This is the headline and the ratchet floor basis.

Everything excluded from Adjusted is **informational, not hidden**: each `exclusions`
bucket is still measured and shown in the report as its own line (e.g. "integration 7.0% —
not counted"), so reviewers see it without it dragging the target number. Nothing is
dropped from the report; the only thing exclusions change is what counts toward Adjusted.

A file moving from target into an `exclusions` pattern shrinks the Adjusted denominator —
allowed only with a manifest reason, never silently, so exclusions cannot inflate Adjusted.

## The merge checklist (run locally by the developer, then re-run on CI per PR)

The developer runs these same checks locally while writing or editing code, so coverage
problems are caught before the PR is opened. CI then runs the identical checks on the PR
and reports them on the PR — local is the fast feedback loop, CI is the backstop. Whether a
failing check also BLOCKS the merge is set per check by the manifest's `gate.enforce`, which is
empty by default: measure and report always, fail the build only where the repo asked for it.

1. Pull the production branch into the feature branch and resolve conflicts there first.
2. Full suite green on the merged result.
3. **Diff coverage**: lines added or changed in this PR meet the diff-coverage threshold
   in the manifest. This is what enforces "new code has tests" — a green suite (and the
   ratchet) alone do not, because adding a little untested code barely moves the overall %.
   Changed lines in an in-scope file are all checked; changed lines in an **excluded file are
   checked only when they fall inside a documented carve-out method** (the `CARVE-OUT:` names in
   that file's exclusion `reason`, minus anything in `cannot_test`). This closes the hole where
   editing a god-class's pure carve-out slice would otherwise escape diff coverage; code outside
   any carve-out in an excluded file stays genuinely out of scope.
4. **Ratchet**: in-scope C0/C1 must not fall below the manifest's recorded floor. The floor
   is updated upward (never downward) when a backfill raises it.
5. **Scope-change guard**: a PR cannot silently dodge the gate by growing `exclusions` /
   `cannot_test`, by landing new source under an excluded path, **or by lowering the recorded
   floor** (`baseline.recorded_overall`). Removing or reducing the floor counts as a scope
   reduction. Any such change is flagged, and fails the run when `scope` is enforced, unless a
   maintainer signs off (the
   `coverage-scope-change` PR label / the gate's `--allow-scope-change`). Reducing scope is
   allowed only with a documented, reviewed reason. **Added test files do not count**: every repo
   excludes its own test sources, so counting them would demand sign-off for the ordinary act of
   adding a test and teach reviewers to apply the label without reading it. The gate detects test
   paths by directory segment (`test`/`tests`, `Foo.Tests`, `UserServiceTests`); an unusual layout
   is declared in `gate.test_path_patterns`.

All of these are measured mechanically by `scripts/coverage-gate.py` (installed at
`.claude/coverage/tools/coverage-gate.py`), which CI runs after `run-coverage.sh`. Given `--base
<target>` it diffs the changed lines and intersects them with the Cobertura per-line hits (checks 3
and 5); the ratchet (check 4) is computed whenever a floor is recorded. Without `--base` (a plain
local report) only the ratchet applies.

**What turns a measurement into a gate** is `gate.enforce` in the manifest (or `--enforce` on the
CLI): the named checks (`ratchet`, `diff`, `scope`) exit 1 on breach, and everything else is printed
as `ADVISORY` with exit 0. The key ships empty, so by default only a failing build or a failing test
makes CI red. Two consequences to be honest about:

- While `diff` is unenforced, nothing mechanical requires a test for new code. A green suite does not
  mean the change was tested: it stays green precisely BECAUSE untested code keeps it green. The
  threshold is then a review obligation, not a rule, and this section is the checklist a reviewer
  runs by hand.
- An enforced check still only blocks a merge if it is a **required status check** on the protected
  branch. Enforcement plus branch protection is what makes it binding; either alone is advisory.

Pre-existing failures unrelated to the change: confirm they already fail on a clean
production branch, state that explicitly, do not let them block, and never introduce a
new failure.

## Baseline semantics

The production branch after the backfill merges is the baseline. Characterization tests
are green by construction at that point. **The baseline is recorded only off a fully green
suite** — coverage measured while any test fails is unreliable (a failing test may not have
executed the lines it was meant to), so the report prints a ⚠️ red-suite banner and the
baseline step is blocked until every failure is fixed. A run that ends with failing tests is
unfinished, not a baseline. The recorded **in-scope** overall (see "In-scope
denominator") becomes the initial ratchet floor; the raw overall is recorded alongside it
for reference only. Suspected latent bugs found during backfill are frozen (the test asserts
current behavior) and listed in the report's observations — frozen, not endorsed. When
someone later fixes such a bug, the characterization test failing is correct: update the
test, document the behavior delta in the PR, get review.

## Maintaining the manifest as code changes (the ongoing contract)

The manifest is a hand-maintained source of truth; it does NOT auto-update. The gate enforces
*part* of keeping it honest, but not all — so a per-PR contract is needed (put a repo-specific
copy in the overlay so it loads into context):

- **New target-layer code** → diff-coverage requires tests (mechanical). New business-logic
  files must land under a `category_map` target path (extend it for a new project/folder).
- **New non-target file** (infra/controller/DTO/generated) → if no existing `exclusions` pattern
  matches, add one with a reason; the scope-change guard flags it for reviewer sign-off. Never add
  an exclusion to dodge testing real logic.
- **New pure logic inside an already-excluded file** (a fresh validator/mapper in an
  `integration-scope` god-class) → the gate only diff-checks carve-out methods already listed, so
  the author MUST add the new method to that file's `CARVE-OUT:` list and unit-test it. **This is
  the one drift the gate cannot detect** — it has no way to know a new testable method appeared in
  an excluded file. Keeping `CARVE-OUT:` lists current is a developer + reviewer duty, not a
  mechanical guarantee; a periodic `coverage-init` re-classification is the catch-up sweep that
  surfaces such drift.
- **Seam added to a `cannot_test` target** → remove the entry and test it.
- **File moved/renamed** → re-run the report and confirm it lands in its intended layer (a rename
  can silently break an exclusion pattern — see the path-verification rule in coverage-init).
- **Floor / gate config** → move-up-only; lowering or weakening fails the scope-change guard.
