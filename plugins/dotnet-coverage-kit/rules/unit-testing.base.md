# Unit Testing — Base Rules (architecture-independent)

These rules are universal and identical across every repo. Repo-specific decisions
(which projects are domain/application, what counts as a unit, mocking strategy for
this stack) live in the per-repo overlay `.claude/coverage/refs/unit-testing.md` and in
`.claude/coverage/refs/coverage-manifest.yml`. This file never names a specific project,
namespace, or layer — it refers to roles defined in the manifest.

## "Untestable" is a proven last resort, never an assumption or a shortcut

Marking code untestable (any `exclusions` bucket, or a `cannot_test` entry) removes it from
the coverage obligation — so it is the path of least resistance to a green gate, and the
default bias must run the other way. Three rules make this concrete:

1. **The unit of the untestable claim is the METHOD, never the file or folder.** A file, and
   especially a whole folder (`Controllers/`, `**/Api/**`, an "Infrastructure" project), is
   almost never uniformly untestable — a controller action validates and branches before it
   delegates; an IO orchestrator has pure mapping/decision methods between its calls. Classify
   the file by its dominant signal for reporting, but every deterministic branching method it
   contains is a **carve-out** that stays in scope. A file-level or folder-level exclusion may
   never silently swallow a testable method.

2. **A signal is a reason to look, not a verdict.** "Uses `HttpClient`", "reads `DateTime.Now`",
   "is a controller" are triggers to inspect, not conclusions. Confirm the untestable condition
   actually holds — the dependency has no injected seam (not merely that infra is *mentioned*),
   the nondeterministic value actually flows into the output you would assert (not just that the
   type appears in the file). When the honest answer to "could a competent engineer test this
   without changing source?" is yes or maybe, it is testable — classify it as target and let the
   run-capture-fill loop prove it, rather than pre-declaring it untestable to save a cycle.

3. **Every untestable claim carries its evidence and its exit.** An exclusion/`cannot_test`
   entry states the objective signal that justifies it (cited at `file:line`) and — for
   `cannot_test` — a **mitigation**: the specific source change that would make it testable
   (extract `IClock`, inject the repository interface, move the pure slice out), or an explicit
   "none — genuinely nondeterministic external boundary" when nothing would. `cannot_test` is
   tracked debt with a way out, not a permanent exemption.

## Two modes

Every test is written in exactly one of two modes. The mode is decided by what is
being tested, not by preference.

**Characterization** — for code that existed at the baseline (untested legacy).
The goal is to freeze current observable behavior as the baseline, including any
latent bugs. The "expected" value is whatever the code actually produces now, never
what it "should" produce.

**Spec** — for new code and for any line changed after the baseline. The goal is to
assert intended behavior against acceptance criteria. The "expected" value comes from
the requirement, not from running the code.

A file may contain both: baseline methods characterized, newly added methods spec'd.

## Run-capture-fill is mandatory for characterization

A characterization test's expected value MUST be obtained by running the code and
reading the actual output. Never compute or predict an expected value by reading the
source.

The required loop for each characterization test:

1. Write the test with explicit, pinned inputs and a placeholder expected value.
2. Run the single test.
3. Read the actual value from the failure (or passing) output.
4. Write that actual value into the assertion.
5. Re-run until green.

If the test genuinely cannot be executed (requires real infrastructure with no seam,
depends on non-deterministic runtime state that flows into the asserted output), it does
NOT get a predicted assertion. It goes to the cannot-test log in the manifest with a reason
**and a mitigation** (see the untestable-is-a-last-resort rule above). A predicted value that
happens to pass is worse than a logged exclusion: it freezes a number that was never the real
output, silently.

**A test that does not compile is not evidence of untestable code.** A compile failure is
almost always a test-authoring problem — a wrong mock setup, a missing reference the test
project legitimately should carry, a constructor argument not yet stubbed. Fix the authoring
problem and run the test. Only route to `cannot_test` when the unit genuinely cannot be
constructed or exercised through any interface *after* the authoring causes are ruled out —
never on the first red build.

Spec tests do not use this loop — their expected values come from the spec.

## No source changes during characterization backfill

The characterization backfill adds tests only. It does not refactor source to make
code testable. If a unit cannot be tested without changing source (no seam for a
clock / id / random generator, hard-wired infrastructure), log it as `nondeterministic`
or the appropriate category in the manifest and move on. Introducing seams is a
separate, deliberate change made under spec rules, not part of the backfill.

This is the opposite of the spec-mode rule below, and that is intentional — the rules
differ by mode.

## Spec mode: untestable code is a dependency problem

For new or changed code, if a unit cannot be tested through its interfaces, that is a
design problem to fix in the same change — extract an interface, move a service, inject
a seam. Do not skip the test and do not widen the test project's references to reach
into infrastructure.

## Assertion style: state and output, not interaction

Default to asserting observable results: return values, resulting state, thrown
exceptions, persisted output. Do NOT assert internal call sequences or mock invocation
order as the primary check.

Interaction verification (`mock.Verify(...)`) is allowed ONLY where the side effect is
itself the observable behavior — publishing a message, sending an email, writing to an
external sink that has no return value to assert. Everywhere else, freezing call order
freezes internal mechanics and breaks on behavior-preserving refactors, which defeats
the safety net.

Use plain xUnit + FluentAssertions assertions throughout, in both modes. Snapshot
assertion libraries are out of scope by default; if a characterization target returns
an object too large to assert field-by-field, log it for review rather than reaching
for a second assertion style.

## Pinned inputs

Characterization tests use explicit, literal inputs for the value under
characterization. AutoFixture may construct surrounding objects that do not affect the
output, but never the inputs that determine the frozen result — random inputs make a
frozen snapshot meaningless.

## Determinism seams

Code reading wall-clock time, generated ids, or randomness directly cannot produce a
stable C0/C1 result. In characterization mode these are logged as `nondeterministic`
and excluded (no source change). In spec mode, new code must take an injected seam for
these so it is testable.

## Structure and naming

- Test files mirror source structure under the test project.
- Substitute dependencies rather than wiring up real ones: mock interfaces/abstracts, and back a
  constructor-injected `DbContext` with the EF in-memory or SQLite-in-memory provider. An
  in-memory-backed context is a test substitute, not a live collaborator, so the test stays at
  unit level (a sibling service already unit-tested this way is the proof it belongs in scope).
  Never reach a live database, network, filesystem, or a statically-constructed / inline-`new`ed
  context. The in-memory provider does not translate raw SQL or enforce relational constraints;
  use SQLite-in-memory when query fidelity matters, and leave raw-SQL methods in integration scope.
- Name tests `MethodName_Scenario_ExpectedResult`.
- A test must not depend on the order it runs in or on another test having run.

## Tests are part of the change

When a signature changes, the tests that exercise it are part of that change — update
them in the same edit. A stale assertion on a removed parameter is relaxed or deleted,
not left asserting dead behavior. A change that leaves the test project red is
incomplete.
