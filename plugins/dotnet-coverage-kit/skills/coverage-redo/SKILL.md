---
name: coverage-redo
description: "Re-audit and reconcile a repo that was already onboarded with an OLDER version of this kit. Use when a repo already has a coverage-manifest.yml, generated tests, and a report, and you want to redo/re-run/recheck/reconcile/upgrade/migrate it against the current classification rules: re-sweep to spot misclassifications (false exclusions such as DbContext-injected services wrongly frozen, mixed folders collapsed to one glob), correct the manifest in place, migrate it to the current schema, generate tests only for the newly-found gaps while keeping existing tests intact, and write a fresh report. Triggers: 'redo coverage', 're-run coverage-init', 'recheck the manifest', 'reconcile coverage', 'upgrade the manifest', 'fix an old manifest', 'the manifest is from v1'."
---

# coverage-redo

Reconcile a repo that an EARLIER kit version already onboarded. It re-runs the classification
against today's rules, corrects the existing manifest rather than replacing it, migrates it to
the current schema, fills only the gaps in test coverage, and regenerates the report. It is the
idempotent successor to `coverage-init` for repos that already have a manifest, tests, and a
report.

Use `coverage-init` instead when there is NO manifest yet (greenfield). Use this skill when a
manifest exists and may be stale, because the classification rules have improved since it was
written (for example: a constructor-injected `DbContext` is now a testable seam, not an
`integration-scope` exclusion; mixed files must be per-file structured carve-outs, not one
folder glob).

## Non-negotiables

These are what make a redo safe to run on a live repo:

1. **Existing tests are kept intact and reused.** Never delete, rewrite, or "regenerate" a test
   that already exists and passes. The backfill only ADDS tests for spots that are newly in
   scope and not already covered. A reclassification that would orphan an existing test is
   reported for a human to resolve, never actioned by deleting the test.
2. **Correct the manifest, do not rewrite it.** Preserve the human-curated content: the
   `baseline`, the `gate` thresholds, intentional gray-zone exclusions, and every carve-out that
   is still valid. Produce a reviewable DIFF of changes with a reason each, not a fresh file.
3. **Migrate the schema.** Convert legacy `CARVE-OUT:` prose to structured `carve_outs:`, split
   any carve-out-bearing folder glob or multi-file pattern into per-file entries (the gate warns
   on these), and recategorize stale `cannot_test` entries to the canonical natures, adding the
   now-required `mitigation`.
4. **Never silently move the ratchet.** Bringing newly-found testable code into scope grows the
   Adjusted denominator and can lower the recorded coverage. The re-baseline decision is explicit
   and human-gated (step 8). Lowering the floor is a reviewed change, never automatic.
5. **Stop for human confirmation of the corrected manifest BEFORE generating any test** (step 6).
   Generating tests off an unreviewed reclassification is exactly the mistake this skill exists
   to fix.

## Preconditions

Same as `coverage-init`: run on the production branch (master), fast-forwarded to the remote,
with a clean working tree. Additionally:

- **A manifest must already exist** at `.claude/coverage/refs/coverage-manifest.yml`. If not,
  stop and tell the user to run `coverage-init` instead.
- **The existing suite must be green.** Run it first. A reconciliation built on a red suite is
  untrustworthy, and you cannot tell a real gap from a pre-existing failure. If red, stop and
  report the failures.
- **Refresh the installed kit files.** Copy the current `scripts/` (`coverage-gate.py`,
  `run-coverage.sh`, `report.sh`) and `templates/coverage.runsettings` into
  `.claude/coverage/tools/` and `refs/` if they differ from the kit, so the gate and report use
  the corrected logic. Do not touch the repo-owned `coverage-manifest.yml` or `unit-testing.md`
  here; those are reconciled in step 5.

## Steps

1. **Detect the prior state.** Record what exists: the manifest (and any `schema_version`), the
   test projects and roughly how many tests, the last report, and, if discoverable, which kit
   version produced them. Note whether the manifest uses legacy prose `CARVE-OUT:` (a v1 signal)
   and whether any exclusion is a folder glob carrying carve-outs (an ambiguity the current gate
   flags).

2. **Re-sweep the whole repo.** Run the classification sweep EXACTLY as `coverage-init` step 4:
   enumerate every source file, clear `coverage/sweep/`, write `files.json`, and run the
   `coverage-sweep` workflow at a user-chosen parallelism with the CURRENT rubric (the table in
   `coverage-init`, including the exclusion-signal principle and the DbContext-seam note). This
   is what surfaces the misclassifications the old manifest baked in. The sweep is read-only on
   source.

3. **Diff the sweep against the existing manifest (single, at main).** Read the on-disk evidence
   (`coverage/sweep/chunk-*.json`) and the current manifest. Produce a reconciliation, not a
   rewrite. Classify every delta into:
   - **False exclusion to fix:** the sweep found a testable method inside a file the manifest
     excludes (the DbContext-injected-service case, a mixed folder collapsed to one glob, a
     branching validator under a `**/Model/**` glob). Add the carve-out, or promote the file to
     `target`, per the current rubric.
   - **Schema migration:** legacy prose `CARVE-OUT:` becomes a structured `carve_outs:` list;
     a carve-out-bearing folder/multi-file pattern is split into one per-file entry each with its
     own `carve_outs` and `excluded_rest`; a `cannot_test` entry with a non-canonical category is
     moved to the canonical nature and given a `mitigation`. A manifest with no `target` block is
     given the default (C0 95% / C1 85% on the Adjusted slice) so the report reads against the goal;
     the existing `gate` and `baseline` are preserved (raising the diff gate to the target is a
     reviewed change, not automatic).
   - **Preserve:** an exclusion the sweep still agrees with, a still-valid carve-out, the
     `baseline`, and the `gate` block are carried over unchanged.
   - **Gray zone:** a genuine disagreement (vendored-vs-product, a host blanket that may hide a
     slice) is carried into the step-9 report as an explicit question, not resolved silently.
   Apply `coverage-init` step 5's pattern-vs-path verification to every new or split pattern.

4. **Guard the existing tests.** For every reclassification, check the existing test files: a
   method moving INTO scope that already has a carve-out test means that test now counts toward
   Adjusted (reuse it, intact). A method moving OUT of scope that has a test is a potential
   orphan: flag it in the report, do not delete it. Assert that no existing, passing test is
   invalidated by a manifest change; if one is, that delta is a question for the human.

5. **Critique the reconciled draft (single, not parallel).** Run `coverage-init` step 6's
   cross-project self-critique on the corrected manifest and the sweep evidence, with two added
   checks specific to redo: (a) no existing test was orphaned by a reclassification, and (b) the
   migration is complete (no prose `CARVE-OUT:` and no carve-out-bearing multi-file pattern
   remain). Reconcile clear-cut corrections in a loop; leave only genuine gray zones.

6. **Write the corrected manifest and STOP for confirmation.** Write the reconciled, migrated
   manifest (do not clobber without showing the diff). Present the diff grouped as: false
   exclusions fixed, schema migrations, entries preserved, and open questions. Ask the user to
   confirm or correct before any test is generated. This is the hard gate: do not proceed to
   step 7 in the same turn without confirmation.

7. **Generate tests for the NEW gaps only.** Run `generate-tests` in characterization mode
   (this is existing code: freeze current behavior) with the reconciled manifest. Its worklist is
   the newly-in-scope carve-outs and targets; items already covered by existing tests are checked
   off and left untouched, per that skill's rules. For a large newly-found backlog, fan it out
   with the same parallel backfill option, asking first. Untestable-as-is units are routed to
   `cannot_test` with a `mitigation`, exactly as in a normal backfill.

8. **Re-baseline decision (explicit, human-gated).** Re-measure with `coverage-report`. Because
   newly-in-scope code entered the Adjusted denominator, the recorded coverage may have moved.
   Present the old floor and the new measured Adjusted, and ask the user which to record. Never
   lower `baseline.recorded_overall` automatically; raising it (once the new gaps are covered) is
   the normal outcome.

9. **New report and comprehensiveness gate.** Regenerate `reports/REPORT.{md,html}` via
   `report.sh`. Assert `coverage-init` step 11's comprehensiveness gate PLUS the redo-specific
   ones: every enumerated file accounted for, no orphaned test, migration complete (the gate's
   ambiguous-carve-out warning is empty). Report the before/after: files reclassified, carve-outs
   added, tests generated, tests reused unchanged, and the coverage delta. Stop and hand the
   human the summary and any open questions.

## What this skill reuses (do not re-specify)

- Sweep enumeration, parallelism prompt, and evidence-to-disk contract: `coverage-init` step 4 +
  the `coverage-sweep` workflow.
- Synthesis, pattern-vs-path verification, and the cross-project critique: `coverage-init`
  steps 5 and 6.
- The backfill loop, characterization vs spec mode, and the parallel backfill: `generate-tests`.
- Measurement, the report, and the baseline contract: `coverage-report` and `coverage-gate.py`.

## Base references
- `${CLAUDE_PLUGIN_ROOT}/skills/coverage-init/SKILL.md`
- `${CLAUDE_PLUGIN_ROOT}/skills/generate-tests/SKILL.md`
- `${CLAUDE_PLUGIN_ROOT}/skills/coverage-report/SKILL.md`
- `${CLAUDE_PLUGIN_ROOT}/rules/unit-testing.base.md`
- `${CLAUDE_PLUGIN_ROOT}/templates/coverage-manifest.yml`
- `${CLAUDE_PLUGIN_ROOT}/workflows/coverage-sweep.workflow.js`
