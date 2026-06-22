# Unit Testing — Base Rules (architecture-independent)

These rules are universal and identical across every repo. Repo-specific decisions
(which projects are domain/application, what counts as a unit, mocking strategy for
this stack) live in the per-repo overlay `.claude/coverage/refs/unit-testing.md` and in
`.claude/coverage/refs/coverage-manifest.yml`. This file never names a specific project,
namespace, or layer — it refers to roles defined in the manifest.

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

If the test cannot be executed (does not compile in isolation, requires real
infrastructure, depends on non-deterministic runtime state), it does NOT get a
predicted assertion. It goes to the cannot-test log in the manifest with a reason.
A predicted value that happens to pass is worse than a logged exclusion: it freezes a
number that was never the real output, silently.

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
- Mock dependencies through their interfaces; do not construct real collaborators in a
  unit test (this is what makes it a unit test).
- Name tests `MethodName_Scenario_ExpectedResult`.
- A test must not depend on the order it runs in or on another test having run.

## Tests are part of the change

When a signature changes, the tests that exercise it are part of that change — update
them in the same edit. A stale assertion on a removed parameter is relaxed or deleted,
not left asserting dead behavior. A change that leaves the test project red is
incomplete.
