---
name: coverage-init
description: "Initialize the coverage backfill in a .NET repo. Use when setting up dotnet-coverage-kit in a new service for the first time, or when the user says 'init coverage', 'set up coverage backfill', or 'scaffold the coverage manifest'. Detects the repo's architecture and projects, sweeps every source file against an objective per-category signal rubric in parallel (user-chosen agent count) to classify them, synthesizes a coverage-manifest.yml and a per-repo unit-testing overlay at the main agent, runs a single cross-project self-critique to catch wrongly-excluded testable code and wrongly-included untestable code (including the same mistake repeated across projects) before human review, installs the runsettings + run script, and scaffolds a PR coverage workflow without clobbering existing CI."
---

# coverage-init

Run once per repo. Discovers the repo's shape and drafts the per-repo config. It DRAFTS;
a human reviews and corrects before any test generation. Never proceed to generation in
the same turn.

## Precondition — run on the latest production branch (master)

The manifest, the detected structure, and the baseline number must reflect the code that
ships, not an in-flight feature branch. Before doing anything else:

1. Confirm the repo is on the production branch (master). If checked out on a feature/topic
   branch, **stop** and ask the user to switch — do not init against feature work.
2. Pull it up to date with the remote (`git fetch` + fast-forward) so the baseline matches
   the current tip of master.
3. Confirm a clean working tree. Uncommitted local changes skew detection and the baseline;
   if the tree is dirty, stop and report rather than measuring against unknown edits.

State the branch and commit you initialized against in the step 11 report, so the eventual
`baseline.ref` is traceable to a real production commit.

## Steps

1. **Detect SDK-style.** Confirm projects are SDK-style `.csproj` (dotnet-coverage only
   supports these). If any target project is a legacy non-SDK `.csproj`, stop and report
   it — that project needs coverlet instead and is out of scope for this kit.

2. **Inventory projects.** List `.csproj` files and their references. Identify the test
   project(s) and what they reference. Identify likely roles (domain, application,
   infrastructure, presentation, workers) from project names, references, and folder
   layout. Detect whether MediatR is present (handlers vs pipeline behaviors).

3. **Derive the TARGET-set hypothesis from the repo's architecture — do NOT apply a fixed
   template.** The target is the code whose coverage is counted toward the headline
   ("Adjusted") number. This step only forms the *hypothesis* of where target code lives; the
   sweep (step 4) classifies the actual files. Based on step 2:
   - **Clean / layered** (distinct `*.Domain`, `*.Application` assemblies): candidate target is
     those layer assemblies; Infrastructure/Api/Web are informational.
   - **Service-oriented / flat** (no layer assemblies; logic in service projects or sub-folders
     of an API project): candidate target is the business-logic projects/sub-folders
     (e.g. `Account.API/Service/**`), by name + content — do not promote a whole API project if
     its logic is confined to a sub-folder.
   - **No discernible structure**: `uncategorized`; do not invent layering.

   Everything outside the target is **informational**: still collected and shown, but not
   counted toward Adjusted. The report is two-pass — *Raw* (all instrumented code) and
   *Adjusted* (target only); the ratchet gates Adjusted. Nothing is hidden.

4. **Sweep — classify EVERY source file against the rubric, in parallel (ask first).**
   Enumerate all source files: the candidate-target globs from step 3 **and** the rest of the
   instrumented production code (so exclusions are evidence-based, not assumed). **Read every
   file.** Do not classify by name/folder alone, do not skip small files, do not sample —
   small files get misclassified too, and fanning the sweep out removes the cost reason that
   ever justified skipping.

   Every file is classified by an **objective signal in the source**, cited at `file:line`
   (each rule is a concrete condition — the spec a future static-analysis helper would
   automate):

   | Classification | Objective signal that justifies it |
   |---|---|
   | `dto-no-logic` | only auto-properties / fields; no method body branches (`if`/`switch`/`?:`/loop); cyclomatic complexity ≈ 1. **Not** an AutoMapper `Profile`/mapping-config class (those are `mapper-config`, below) |
   | `mapper-config` | an AutoMapper `Profile` or mapping/DI-config class: declarative `CreateMap`/registration only, no branches today. Labeled distinctly from `dto-no-logic` so a future conditional `MapFrom`/`ConvertUsing` is not silently hidden under a "data carrier" label |
   | `integration-scope` | depends on infrastructure: `DbContext`/repository impl, `HttpClient`, file/network IO, or an external SDK client — used directly, no seam |
   | `e2e-scope` | `ControllerBase`/`[ApiController]`, a hosted/background worker, or a `Program`/startup composition root |
   | `generated` | `[GeneratedCode]` attribute, a `*.g.cs`/`*.Designer.cs` file, or a `Migrations/` path |
   | `cannot_test: nondeterministic` | a `DateTime.Now`/`UtcNow`, `Guid.NewGuid`, `Random`, `Stopwatch`, `Environment` call with no injected seam **whose value flows into observable output** — a return value, an emitted command/document, or persisted state. **Dataflow-blind matching is the classic false positive:** if the only consumer of the value is a logging/telemetry call (`Serilog.Log.*`, `LogContext.PushProperty`, `ILogger`, a `Stopwatch` timing an `elapsed-ms` log line), it is NOT nondeterministic — classify by the method's real behavior instead (usually the mapping → target/carve-out, or `integration-scope` if the body is `DbContext`-bound). A correlation-id/elapsed-ms logged on every handler is a house style, not an untestable seam |
   | target (unit-scope) | ≥1 method whose body branches **and** every dependency is mockable (interface/abstract) — no direct infra/IO/clock/random use |

   **The file's classification is a REPORTING label; testability is decided per method.** A
   non-trivial file is rarely uniformly testable or untestable — the classification is its
   dominant signal, but the sweep must also record, for each non-trivial file, a **per-method
   breakdown**: `{ method, lines, testable, reason }` (e.g. `MapResult` lines 40–58 testable;
   `FetchRaw` lines 60–95 not testable — direct `HttpClient`, no seam). This is what turns
   "this file is untestable" into "lines 40–58 testable, lines 60–95 not testable because …".
   Every method marked `testable: true` in a file that carries a non-target classification is a
   **carve-out** and MUST be listed in `carveOutMethods` so the backfill covers it.

   **This applies to whole folders that "look" untestable, not just god-classes.**
   `Controllers/`, `**/Api/**`, and `*.Infrastructure` projects are the classic trap: they get a
   blanket `e2e-scope`/`integration-scope` label, yet controller actions validate and branch
   before delegating, and IO orchestrators have pure mapping/decision methods between their
   calls. Read them for their carve-outs — do not let a folder-level verdict swallow the testable
   slice. A `god-class` (large or dependency-heavy, >~300 lines or many injected collaborators) is
   just the extreme case of this same rule: classify by dominant signal, carve out the pure logic
   (the UserService pattern). A file gets `trivial`/no-carve-out treatment only when it genuinely
   has zero deterministic branching methods.

   **Hard rule — a bare (no-carve-out) exclusion on a LARGE file is not allowed without a
   method-level re-scan.** A big multi-method service is the likeliest place to under-carve: the
   file gets judged whole, one `integration-scope` label, and its pure validator/mapper cluster is
   lost. So for any file above a size/method-count threshold (rule of thumb: >~400 lines OR >~10
   methods) that you are about to label `integration-scope`/`e2e-scope` with an EMPTY
   `carveOutMethods`, you MUST first walk its methods and prove each is genuinely IO-bound. A large
   bare exclusion is a red flag, not a default — the real case (e.g. a 2,400-line preset service
   hiding `ValidateFileFormat`, `ValidateWidthHeight`, `IsInvalidAssignment`) is that several pure
   validators were missed. The critique (step 6) treats every large bare exclusion as a lead to
   re-open.

   **Trivial files are marked, not surfaced.** A tiny file (~15 lines or fewer) that is
   high-confidence excluded — a DTO/record of auto-properties only, an interface, an enum with
   no behavior — is flagged `trivial`. These get **collapsed into glob patterns** at synthesis
   (step 5), not carried as per-file rows. On a large repo they are often ~40% of the files and
   the lowest-signal rows; collapsing them keeps the manifest and the critique focused.

   Run the sweep the **same way as the backfill** — fan it out at a user-chosen parallelism:
   1. Count the files to classify and **ask the user how many agents to run**, suggesting
      counts scaled to that size and the context (rough: small repo → 1; medium → 3;
      large / many-project → 6–10; more agents finish sooner but cost proportionally more
      tokens).
   2. **Clear `coverage/sweep/` first** (`rm -rf coverage/sweep`) so a prior or crashed run
      cannot leave stale `chunk-N.json` files behind — a different chunk count would otherwise
      mix old and new evidence. Then **write the enumerated paths to disk** as a JSON array at
      `coverage/sweep/files.json` (e.g. pipe your file enumeration through `jq -R . | jq -s .`,
      or write the array directly). **Pass the manifest path, never the list itself** — a large
      inline `files` array mis-parses in the tool call, and inlining it into the workflow script
      trips the approval-dialog control-char guard (CRLF from a Windows heredoc). Then invoke
      `Workflow({ scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/coverage-sweep.workflow.js",
      args: { concurrency: <chosen>, filesManifest: "coverage/sweep/files.json",
      rubric: "<the table above>", evidenceDir: "coverage/sweep" } })`. If the user just says
      "go", default `concurrency: 3`.

   **Evidence goes to disk, not into context.** Each chunk agent writes ALL its per-file rows
   `{ path, classification, signal, confidence, trivial, carveOutMethods, methodBreakdown, notes }`
   to `coverage/sweep/chunk-N.json`, and returns only a compact summary: counts per classification,
   the trivial count, and the rows that need a look (low-confidence, god-classes, surprising).
   `coverage/` is git-ignored (step 8), so this evidence is transient. The sweep is read-only on
   production source and never writes the manifest.

5. **Synthesize the draft at main (single — NOT parallel).** **Read the on-disk evidence**
   (`coverage/sweep/chunk-*.json`) — do not rely on rows being in the conversation; on a large
   repo the full set is thousands of rows and lives in those files. Merge it into one coherent
   draft: `category_map` (the target globs), `exclusions` (each non-target classification,
   grouped into patterns with the rubric signal as the reason), and `cannot_test` (the
   nondeterministic-no-seam methods only — each with a `mitigation`). **Carve-outs are NOT
   `cannot_test` — they are testable methods that stay IN scope.** For every non-target file whose
   `methodBreakdown` has ≥1 `testable: true` method, append those method names to that pattern's
   exclusion `reason` in the exact parseable form `CARVE-OUT: MethodA, MethodB` (the gate reads
   carve-outs from the reason and keeps their lines in scope). Putting a carve-out into
   `cannot_test` would exclude the very method the backfill must cover — the opposite of the
   granularity goal. **Collapse `trivial` files into
   glob exclusion patterns by directory** (e.g. `**/Dtos/**` → `dto-no-logic`) instead of one
   row each; emit per-file detail only for non-trivial files. **Normalize across chunks** —
   parallel agents drift in vocabulary (one says `integration-scope`, another `infra`);
   reconcile to one category set and resolve cross-project boundaries. This must be one head:
   the whole-repo view is what makes the manifest coherent and consistent.

   **Verify every pattern actually matches the paths it intends — a written pattern is a
   hypothesis until joined against real paths.** A glob that silently matches nothing leaks
   those files into `application`/`uncategorized`, inflating the Adjusted denominator with
   uncovered code (and a glob that matches too much wrongly shrinks it). After collapsing to
   globs, **re-apply the globs to the swept file list and assert each file lands in the bucket
   its sweep row assigned**; any divergence is a pattern bug to fix now, not at measure time.
   Watch the failure modes that caused real leaks in the field:
   - **Path/segment typos.** A file under `Integration/Looker/Implemetations/LookerService.cs`
     is NOT matched by `**/Integration/LookerService.cs`. Pattern the real path, and don't trust
     folder names from memory (note the misspelled `Implemetations`).
   - **Dot-segment vs plain-segment.** `**/*.Model/**` matches a project folder named
     `Foo.Model` but NOT a plain `Model/` folder; `**/DataAccess/**` matches `DataAccess/` but
     NOT `Foo.DataAccess/`. Add both forms (`**/Model/**` / `**/*.DataAccess/**`) when the repo
     uses both. DTOs/host files also leak when they live outside the expected folder
     (`Program.cs`, `Startup.cs`, `**/Filters/**`, `**/*Assembly.cs`, DI `ServiceExtensions.cs`).
   - **Filename collisions across projects.** The same class name in N projects (e.g.
     `SendEmailService.cs`, `RedisHelper.cs`, `AccountService.cs`, `UserInfoService.cs`) often
     has DIFFERENT classifications per project. A bare `**/Name.cs` applies one verdict to all;
     when they differ, emit a **path-qualified entry per project** and confirm each resolves to
     its own bucket. Also exclude test code itself (`**/Tests/**` → non-product) so test
     fixtures never count toward Adjusted.

   This pattern-vs-path verification is cheap (it runs against the swept file list already on
   disk — no coverage run needed) and catches the class of bug that otherwise only surfaces as a
   mysteriously-low Adjusted number after the whole backfill is done.

6. **Critique the synthesized draft (a single agent, deliberately NOT parallel).** A wrong
   manifest is the most damaging error here — excluding testable code hides real gaps,
   including untestable code produces churn and false "needs attention" noise. One reviewer
   reads the draft and the on-disk evidence (`coverage/sweep/chunk-*.json`) — load it in slices
   / group by signal, do not pull all rows into context at once. **Kept single on purpose:** a
   *systematic* mistake — the same misclassification repeated across projects (e.g.
   mappers-with-branches labelled `dto-no-logic` everywhere) — is only visible to a reviewer
   who sees all of it at once, and one reviewer applies one consistent standard; parallel
   critics would each rationalize the repeated error locally. Group by signal → label to
   surface repeated mismatches cheaply, prioritize the sweep's `attention` rows, and
   spot-read — you do not re-read every file. Using the step 4 rubric, a classification is a
   **mismatch** when the label is not supported by its signal; check both directions:

   - **False exclusions (testable code wrongly skipped):** a file labelled `dto-no-logic` that
     actually branches, or `integration-scope` with no infra dependency, has the **target**
     signal and belongs in scope.
   - **False inclusions (untestable code wrongly kept):** a target file that is really IO
     orchestration → `integration-scope` with a carve-out; nondeterministic-no-seam →
     `cannot_test`.
   - **Classic traps (signal hiding under a misleading name):** DTOs with validation/computed
     members; "infrastructure"-named pure logic; mappers with conditional logic; enums with
     behavior.
   - **Verify NEGATIVE citations against source — the sweep's `attention` list cannot catch
     these.** A confidently-wrong exclusion rests on a negative claim ("auto-properties only",
     "no seam", "no branches") that is high-confidence, so it never appears in `attention`, and
     reading only the evidence rows cannot reveal that the claim itself is false. Sample the
     high-confidence exclusions per bucket and per project and open the actual file to confirm
     the negative claim holds (no `if`/`switch`/`?:`/loop; the collaborator really is not an
     injected interface). One wrong negative claim, repeated across a project by pattern, is the
     largest silent false-exclusion — spend the reads here, not on the already-flagged rows.
   - **Missing carve-outs are false exclusions.** For every `integration-scope`/`e2e-scope`
     file, check its per-method breakdown: any deterministic branching method not listed in
     `carveOutMethods` is testable code silently dropped. Add it as a carve-out.
   - **Dataflow-blind `nondeterministic` is THE recurring false positive — audit it as a
     population, not row-by-row.** Pull every `nondeterministic` entry at once and check where the
     flagged `Guid.NewGuid`/`Stopwatch`/`DateTime.Now` value actually goes. If its only consumer
     is a logging/telemetry call (`Serilog.Log.*`, `LogContext.PushProperty`, `ILogger`, a
     `Stopwatch` for an elapsed-ms log), the entry is wrong: reclassify to the method's real
     behavior — `target`/carve-out if the body is a pure mapping, or `integration-scope` if the
     body is `DbContext`-bound (correctly frozen, but for the wrong reason). This is a house-style
     pattern (correlation-id + elapsed-ms on every handler), so it clusters — a batch of
     near-identical handler entries frozen for a logged Guid is the signature. Expect to reclassify
     most of them.
   - **Large bare exclusions.** Any `integration-scope`/`e2e-scope` file above ~400 lines / ~10
     methods with an EMPTY `carveOutMethods` is a lead to re-open — a whole-file judgment likely
     missed a pure validator/mapper cluster. Re-scan its methods before accepting the bare label.

   Reconcile as a loop: apply the clear-cut corrections (signal unambiguously contradicts the
   label) to the draft, then re-check the corrected entries; repeat until no clear-cut mismatch
   remains. Only then carry the genuine gray-zone disagreements into the step 11 report as
   explicit questions — do not silently resolve them. The human adjudicates only the few
   ambiguous cases.

7. **Write files into the repo** (do not overwrite without confirmation). Lay `.claude/coverage/`
   out in subfolders by role — `tools/` (executable scripts), `refs/` (config + the testing-rules
   overlay), `reports/` (the committed report snapshot), `history/` (gitignored local trend):
   - `.claude/coverage/refs/coverage-manifest.yml` — from the template, filled with the
     critique-corrected draft. Unresolved open questions are written with their current
     (pre-critique) classification and noted as pending in the step 11 report.
   - `.claude/coverage/refs/coverage.runsettings` — copied from the kit template.
   - `.claude/coverage/tools/run-coverage.sh` — copied from the kit's `scripts/`. Committed so CI
     (which does not run Claude Code) can invoke it at a stable path, identical to local runs.
   - `.claude/coverage/tools/coverage-gate.py` — copied from the kit's `scripts/`. The in-scope
     join + gate + Unit Test Report CI runs after `run-coverage.sh` (needs Python + PyYAML).
   - `.claude/coverage/tools/report.sh` — copied from the kit's `scripts/`. One-command wrapper
     (collect + gate + write `reports/REPORT.{md,html}`). It resolves `../refs` and `../reports`
     relative to itself, so the tools/refs/reports split is a hard contract — keep the scripts in
     `tools/` and config in `refs/`.
   - `.claude/coverage/refs/unit-testing.md` — the per-repo overlay. Starts as a pointer to the
     base rules plus this repo's specifics: which projects the test project may reference, the
     mocking strategy for this stack, repo-specific exclusions, the **Enforcement** section, and
     the **Maintaining the manifest** contract (from the base rule). For a flat/legacy repo this
     carries more; for clean-arch it is thin.
   - `.claude/coverage/reports/` — created empty; the first `report.sh` run fills it. Committed.

8. **Set `.gitignore` correctly — committed config vs throwaway output vs local trend:**
   - Ignore the regenerated output dir `coverage/` at the repo root (HTML drill-down, cobertura,
     results) — never commit it.
   - Ignore `.claude/coverage/history/` — ReportGenerator drops one trend snapshot per run there;
     committing a per-run XML is churn and CI can't accumulate it anyway. Local-only.
   - Do **NOT** ignore the rest of `.claude/coverage/` — `tools/`, `refs/`, and `reports/` are
     committed config + the report snapshot.

9. **Scaffold the PR coverage workflow — without clobbering or duplicating existing CI.**
   First inspect `.github/workflows/` for existing workflow files. Decide, in this order:

   - **A coverage workflow already exists** (a `coverage.yml`, or any workflow that already
     runs `run-coverage.sh`) → do **not** overwrite or add a second one. Report it; at most
     offer a diff for the user to apply by hand.
   - **A workflow already runs the test suite on PRs into the production branch** (look for
     `dotnet test` under a `pull_request` trigger targeting master) → do **not** add a second
     workflow that rebuilds and retests — that doubles CI minutes and creates two competing
     gates. Instead, *propose* adding the two coverage steps (run `run-coverage.sh`, then
     publish `SummaryGithub.md` to `$GITHUB_STEP_SUMMARY`) into that existing workflow, and
     present it as a suggested diff. Do not edit their workflow automatically.
   - **No existing PR-test or coverage workflow** → write `.github/workflows/coverage.yml`
     from `${CLAUDE_PLUGIN_ROOT}/templates/coverage-workflow.yml`, filled with the detected
     solution path, SDK version, and production branch name. Confirm the gate step keeps
     `--base origin/${{ github.base_ref }}` — without it only the ratchet runs and **new untested
     code is not caught** (the ratchet barely moves on a large repo). If step 2's inventory found
     **relative ProjectReferences into sibling repos** (e.g. `..\..\..\<sibling>\...`), fill the
     sibling-checkout block: check this repo out under `path:` and each sibling out beside it,
     or CI cannot build and the gate never runs. State the sibling repos + assumed org/ref in the
     step 11 report for the human to confirm.

   Never modify or delete any other workflow file. Record which path you took (created /
   skipped-because-exists / proposed-merge) in the step 11 report.

   **Tell the user the gate is only advisory until they make it binding** (you cannot do this
   for them — it is a GitHub setting): in branch protection for the production branch, require
   the Coverage status check to pass before merging, and treat the baseline floor in the
   manifest as move-up-only (lowering it is a reviewed change). Surface this as an explicit
   action item in the step 11 report.

10. **Wire context loading.** A plugin's rules do not auto-load into a repo's context.
   Tell the user to add an import of `.claude/coverage/refs/unit-testing.md` to the repo's
   `CLAUDE.md` so the convention is in context while writing tests.

11. **Comprehensiveness gate — do not report or stop until the scan is provably complete.**
   The point of stopping is to hand a human a *trustworthy, complete* draft; a report over a
   partial or unreconciled scan is worse than no report. Before writing the step-11 report,
   assert ALL of the following, and if any fails, fix it and re-check — do not proceed:
   - **Every enumerated file is accounted for.** `filesClassified == filesPlanned` from the
     sweep result (0 unaccounted). If a chunk failed and files are missing, re-sweep the gap —
     do not report over a hole. The workflow returns this; act on it, never just note it.
   - **The enumeration itself was complete.** The swept set covers all instrumented production
     source — no source directory silently omitted from `files.json`. Cross-check the enumerated
     paths against the project/folder inventory from step 2; a whole folder missing from the
     sweep is the same failure as a folder blanket-excluded.
   - **No testable method was swallowed.** Every `integration-scope`/`e2e-scope` file with a
     deterministic branching method has that method recorded as a carve-out (the step-6 check
     passed for all such files, not a sample).
   - **The critique loop has settled.** No clear-cut mismatch remains; only genuine gray-zone
     questions are left, and those are carried into the report as explicit questions.

   State in the report that this gate passed, with the file counts. Only genuine ambiguity is
   deferred to the human — incompleteness is not.

   **Report the draft and stop.** Show the proposed category_map and exclusions with a
   one-line rationale each, the detected test-project reference boundary, and the
   critique findings — split into corrections already applied and open questions the
   human must decide. Ask the user to confirm or correct the category_map and exclusions
   before running `generate-tests`. Flag anything ambiguous as a question rather than
   guessing.

## Base references
- `${CLAUDE_PLUGIN_ROOT}/rules/unit-testing.base.md`
- `${CLAUDE_PLUGIN_ROOT}/rules/coverage-report.base.md`
- `${CLAUDE_PLUGIN_ROOT}/templates/coverage-manifest.yml`
- `${CLAUDE_PLUGIN_ROOT}/templates/coverage.runsettings`
- `${CLAUDE_PLUGIN_ROOT}/templates/coverage-workflow.yml`
- `${CLAUDE_PLUGIN_ROOT}/scripts/run-coverage.sh`
- `${CLAUDE_PLUGIN_ROOT}/scripts/coverage-gate.py`
- `${CLAUDE_PLUGIN_ROOT}/scripts/report.sh`
- `${CLAUDE_PLUGIN_ROOT}/workflows/coverage-sweep.workflow.js`
