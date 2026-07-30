# Migration ledger

What to apply to a repo that was already onboarded on an OLDER kit version. `coverage-redo` reads
this file, works out the delta from the repo's recorded `kit_version:` forward, and applies every
entry below it. Do not read this as release notes: each entry exists so an upgrade is a **bounded,
detectable delta** rather than a full re-audit.

**How an entry is written.** Every entry carries:

- **Detect** an on-disk check that says whether this repo still needs it. Detection is authoritative,
  the version number is only an ordering hint: a repo may have picked a change up early by hand, and
  a repo with no `kit_version:` must be walked from the top of this file.
- **Apply** the concrete change.
- **Gate** how it reaches the user:
  - `auto` mechanical, no effect on what is measured or on any number. Apply it silently and list it
    in the closing report.
  - `sign-off` it can move the Adjusted denominator, the floor, or the exclusion set. Fold it into
    the ONE manifest confirmation (`coverage-redo` step 6). Never apply it silently, never split it
    into its own separate question.

**One gate, then autonomous.** Every `sign-off` item in the delta goes into that single confirmation
together. After it, run to completion without re-asking per item.

---

## Preflight: detect drift on EVERY kit run

A repo left behind on an old kit must say so by itself. Waiting for someone to ask "are there kit
updates?" is how a repo sits for months on rules that have since been corrected, and the person
running a report is exactly the person who does not know to ask. So **every** entry point checks,
whether or not the user mentioned an upgrade:

```
python .claude/coverage/tools/coverage-gate.py --manifest <manifest> --print-kit-drift
# -> "<current|behind|unstamped|ahead> <manifest stamp> <kit semver>"
```

Manifest-only, so it costs nothing and needs no coverage run. `report.sh` prints it as `KIT_DRIFT=`
before collecting, and the report itself carries a note when the state is not `current`, so the
signal reaches the artifact people already read.

**What each entry point does with a non-`current` state** (the split matters: detection is always
automatic, application is not always safe):

| Entry point | On drift |
|---|---|
| `coverage-report` | Report it. Apply NOTHING to the manifest. A report that quietly changed scope would make its own numbers unreproducible, and the drift note plus one sentence naming `coverage-redo` is the whole job. Refreshing stale `.claude/coverage/tools/` copies is the one thing it offers to fix, as it already does. |
| `generate-tests` | Apply the `auto` entries that govern how THIS pass runs (tool refresh, fan-out contract, frozen-bug recording), because running a backfill on superseded mechanics wastes the whole pass. Surface `sign-off` entries and do NOT apply them: a scope change mid-backfill moves the worklist under your own feet. Say plainly that `coverage-redo` is what applies them. |
| `coverage-redo` | The full path. Walk this ledger from the stamp forward, apply `auto`, fold `sign-off` into the one manifest confirmation, re-stamp when they land. |
| `coverage-init` | Not applicable (greenfield). It stamps the current version, which is what makes the first later upgrade a delta. |

State the finding in one line, not a lecture: "This repo is on kit 0.9.0, current is 0.13.0; N
entries apply, run `coverage-redo`". If the state is `current`, say nothing at all.

---

## v0.13.0 Drift detects itself, and frozen bugs survive the parallel backfill

**Detect:** the manifest has no `kit_version:` key (`--print-kit-drift` reports `unstamped`), OR the
repo's `.claude/coverage/tools/` copies predate this version, OR the manifest has no `latent_bugs:`
key while the suite contains tests whose names or assertions state a defect (see the tells in
`generate-tests`, suite critique item 6).

**Apply:** add the `kit_version:` stamp so future upgrades are a delta rather than a full walk, and
refresh the installed tool copies so `report.sh` prints `KIT_DRIFT=` and the report carries the
pending-updates note (that is what makes every later kit change announce itself without being asked
about). Then run critique item 6 over the existing suite as a
one-off audit and propose a `latent_bugs:` entry for every frozen defect that is not recorded. A
finding a chunk agent returned before this version was never persisted, so on any repo backfilled
with the fan-out, assume the recorded list is incomplete and re-derive it from the assertions.

**Gate:** `auto` for the tool refresh. `sign-off` for the proposed `latent_bugs:` entries, because
each names a live product defect and the report will escalate the A/B/C ones by name.

## v0.12.0 Vendored reference projects leave BOTH measurement and test scope

**Detect:** a directory under the repo root that is a copy of another repo (its own `.sln`/README/CI,
assembly names following another repo's convention, relative `ProjectReference` paths that climb out
and land back inside, a bulk-import commit) and is NOT listed in `scope.vendored_paths`. Also: any
`target`, `carve_outs`, or `cannot_test` entry whose path is inside such a directory.

**Apply:** list each such directory in `scope.vendored_paths` (bare library name is fine, the gate
resolves it). `coverage-gate.py` then derives both the filefilter exclusion and a `non-product`
`exclusions` entry from that one declaration, so measurement scope and test scope cannot disagree.
DELETE every manifest entry pointing into a vendored path, and the tests generated from those
entries: this is the one case in a redo where removing an existing test is correct, so name each
deletion explicitly in the closing report.

**Gate:** `sign-off`. It shrinks the denominator, changes exclusions, and deletes tests.

## v0.11.0 `latent_bugs:` renders as report section 7

**Detect:** the manifest has no `latent_bugs:` key, or an old report/`CANNOT-TEST.md` carries
suspected defects as prose.

**Apply:** add the key and migrate every prose finding into a structured entry
`{ severity A-E, target, file?, summary, pinned_by }`. Prose in a report body or appended to
`CANNOT-TEST.md` is lost on the next `report.sh` run, so treat any you find as unrecorded. Sweep the
existing suite for tests that assert a bug on purpose and give each an entry with its `pinned_by`.

**Gate:** `sign-off` (each entry names a live defect).

## v0.10.0 Scope-change sign-off actually triggers a run

**Detect:** `.github/workflows/*coverage*.yml` PR triggers lack `labeled` or `unlabeled`.

**Apply:** add both. Without `labeled`, adding the sign-off label starts no run; without
`unlabeled`, revoking it leaves a stale green check. Note in the report that "Re-run jobs" replays
the original label-less payload and so cannot approve a just-added label.

**Gate:** `auto` (CI plumbing, no manifest effect).

## v0.9.0 A scoping mistake cannot masquerade as a regression

**Detect:** `baseline.scope_lines` is null or absent while `baseline.recorded_overall` is set.

**Apply:** stamp `scope_lines` from the "Total lines (Adjusted)" denominator of the report produced
during this redo, even when preserving the existing floor. A floor without the scope size it was
measured against is why an inflated denominator reads as lost coverage.

**Gate:** `auto` (records what is already true, moves no threshold).

## v0.9.0 The `scope` block is the single definition of what is measured

**Detect:** the manifest has no `scope` block, or `scope.file_filter` is empty while the CI workflow
passes a filter expression to `run-coverage.sh`.

**Apply:** copy the expression CI currently passes, VERBATIM, including its exclusions, into
`scope.file_filter`. For older repos the exclusions live only in CI, so local runs have been
measuring a different file set than CI all along, and copying it in is what ends that split.

**Gate:** `sign-off` if it changes the measured set locally (it usually does).

## v0.8.0 Dated reports, and `CANNOT-TEST.md` is generated

**Detect:** reports are written flat rather than under `reports/<YYYY-MM-DD>/`, or `CANNOT-TEST.md`
contains hand-written content below the generated body.

**Apply:** regenerate through `report.sh` so the dated layout applies. Move any hand-written
cannot-test content into manifest `cannot_test` entries first: the file is regenerated from the
manifest on every run despite its MANUAL-APPEND marker, so an append is silently lost.

**Gate:** `auto`.

## v0.7.0 Fan-out worklists travel by disk manifest

**Detect:** nothing on disk. This governs how THIS run invokes the backfill.

**Apply:** follow the `generate-tests` fan-out contract exactly: write
`coverage/backfill/worklist.json` first and confirm it is non-empty, pass `args` as a real JSON
object with `worklistManifest`, never an inline `worklist` and never a stringified payload, and
invoke via `scriptPath`. Each of those is a real field failure where zero agents ran and the launch
still looked like success.

**Gate:** `auto`.

## v0.6.0 Explicit Adjusted coverage target

**Detect:** the manifest has no `target` block.

**Apply:** add the default (C0 95 / C1 85 on the Adjusted slice) so the report reads against the
goal. Preserve the existing `gate` and `baseline` as they are: raising the diff gate to the target is
a reviewed change, not part of the migration.

**Gate:** `auto` for adding the target block (it is an aim, not a gate). `sign-off` for any change to
`gate.*` thresholds.

## v0.5.0 Carve-out slices count toward Adjusted

**Detect:** carve-out methods exist but the last report's Adjusted denominator excluded them (an
Adjusted slice smaller than target + carve-outs).

**Apply:** regenerate the report with the current `coverage-gate.py`. The counting is the script's,
not the manifest's, so the tool refresh is the whole fix. Expect the percentage to move.

**Gate:** `sign-off` when the number moves enough to touch the floor decision.

## v0.4.0 Structured carve-outs and the false-exclusion rules

**Detect:** prose `CARVE-OUT:` text anywhere in the manifest; an exclusion that is a folder glob or
multi-file pattern carrying carve-outs (the gate warns on these); a `cannot_test` entry with a
non-canonical category or no `mitigation`; a service excluded as `integration-scope` whose only
infra dependency is a constructor-injected `DbContext`.

**Apply:** convert prose to a structured `carve_outs:` list; split every carve-out-bearing pattern
into one per-file entry with its own `carve_outs` and `excluded_rest`; move each stale `cannot_test`
entry to the canonical nature and give it a `mitigation`; promote wrongly-frozen testable code
(an injected `DbContext` is a seam, not an exclusion) to `target` or a carve-out.

**Gate:** `sign-off`. This grows the testable set and can lower recorded coverage.
