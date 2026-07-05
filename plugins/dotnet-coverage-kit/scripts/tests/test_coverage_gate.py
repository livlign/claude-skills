#!/usr/bin/env python3
"""End-to-end render test for coverage-gate.py.

Builds a fixture Cobertura report + coverage-manifest.yml + a red .trx, runs the gate as a
subprocess, and asserts on the emitted Markdown. Covers the report-hardening behaviors that have
no live-repo coverage otherwise:

  - red-suite banner when tests fail
  - Risk Hotspots omit methods already in cannot_test (no "unit-test it" for dead code)
  - section 6 split into 6a (design debt) / 6b (structural)
  - category-alias normalization (framework_mismatch -> framework-mismatch, requires-seam -> requires-source-change)
  - systematic-seam cluster callout (>=3 entries sharing Guid.NewGuid)

Run:  python3 scripts/tests/test_coverage_gate.py
Exit: 0 = pass (or SKIP if PyYAML unavailable and can't be installed), 1 = a failure.
PyYAML is a documented kit dependency; CI installs it, so the test runs there.
"""
import os, subprocess, sys, tempfile, textwrap

GATE = os.path.join(os.path.dirname(__file__), "..", "coverage-gate.py")


def ensure_pyyaml():
    try:
        import yaml  # noqa: F401
        return True
    except ImportError:
        pass
    # Best-effort install so the test is self-sufficient; skip cleanly if the env forbids it.
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "pyyaml"],
                       check=True)
        import yaml  # noqa: F401
        return True
    except Exception:
        return False


COBERTURA = """<?xml version="1.0"?>
<coverage line-rate="0.1" branch-rate="0.1" version="1.9">
  <packages><package name="App"><classes>
    <class name="App.Application.OrderService" filename="src/App/Application/OrderService.cs">
      <lines>
        <line number="10" hits="1"/>
        <line number="11" hits="0"/>
        <line number="12" hits="0"/>
      </lines>
      <methods>
        <method name="Process" signature="(int)" complexity="8">
          <lines>
            <line number="11" hits="0" branch="true" condition-coverage="0% (0/8)"/>
            <line number="12" hits="0"/>
          </lines>
        </method>
      </methods>
    </class>
    <class name="App.Application.DeadHelper" filename="src/App/Application/DeadHelper.cs">
      <lines>
        <line number="20" hits="0"/>
        <line number="21" hits="0"/>
      </lines>
      <methods>
        <method name="OrphanCalc" signature="()" complexity="10">
          <lines>
            <line number="20" hits="0" branch="true" condition-coverage="0% (0/10)"/>
            <line number="21" hits="0"/>
          </lines>
        </method>
      </methods>
    </class>
    <class name="App.Infrastructure.RepoService" filename="src/App/Infrastructure/RepoService.cs">
      <lines>
        <line number="30" hits="0"/>
        <line number="31" hits="0"/>
      </lines>
      <methods>
        <method name="BigQuery" signature="()" complexity="120">
          <lines>
            <line number="30" hits="0" branch="true" condition-coverage="0% (0/120)"/>
            <line number="31" hits="0"/>
          </lines>
        </method>
      </methods>
    </class>
  </classes></package></packages>
</coverage>
"""

MANIFEST = """schema_version: 1
baseline:
  ref: "test"
  recorded_overall:
    c0: 10.0
    c1: 0.0
gate:
  ratchet: true
category_map:
  application:
    - "**/Application/**"
exclusions:
  - pattern: "**/Infrastructure/**"
    category: integration-scope
    reason: "IO orchestration; covered by integration tests"
cannot_test:
  - target: "OrderHandlerA.Handle"
    category: nondeterministic
    reason: "OrderHandlerA.cs:42 Guid.NewGuid() with no seam"
    mitigation: "Inject IGuidProvider"
  - target: "OrderHandlerB.Handle"
    category: nondeterministic
    reason: "OrderHandlerB.cs:42 Guid.NewGuid() with no seam"
    mitigation: "Inject IGuidProvider"
  - target: "OrderHandlerC.Handle"
    category: nondeterministic
    reason: "OrderHandlerC.cs:42 Guid.NewGuid() with no seam"
    mitigation: "Inject IGuidProvider"
  - target: "Legacy.Foo"
    category: requires-seam
    reason: "internal type; needs InternalsVisibleTo"
    mitigation: "Add InternalsVisibleTo to the test project"
  - target: "Weird.Branch"
    category: unreachable-branch
    reason: "compiler-lowered ?. short-circuit, provably non-null"
    mitigation: "none - compiler artifact"
  - target: "Old.Thing"
    category: framework_mismatch
    reason: "owning project targets netcoreapp3.1"
    mitigation: "none - retarget the project"
  - target: "DeadHelper.OrphanCalc"
    category: dead-code
    reason: "no caller anywhere in the codebase"
    mitigation: "remove the dead method"
"""

TRX = """<?xml version="1.0" encoding="UTF-8"?>
<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
  <Times start="2026-01-01T00:00:00.0000000+00:00" finish="2026-01-01T00:00:10.0000000+00:00"/>
  <ResultSummary><Counters total="10" passed="8" failed="2" error="0" timeout="0" aborted="0"
    notExecuted="0" inconclusive="0" disconnected="0"/></ResultSummary>
</TestRun>
"""


def check(name, cond, out):
    if cond:
        print("  PASS  " + name)
        return 0
    print("  FAIL  " + name)
    print(textwrap.indent(out, "        | ")[:4000])
    return 1


def main():
    if not ensure_pyyaml():
        print("SKIP: PyYAML not available and could not be installed; skipping gate render test.")
        return 0

    with tempfile.TemporaryDirectory() as d:
        cob = os.path.join(d, "cobertura.xml")
        man = os.path.join(d, "coverage-manifest.yml")
        trxdir = os.path.join(d, "trx")
        os.makedirs(trxdir)
        open(cob, "w").write(COBERTURA)
        open(man, "w").write(MANIFEST)
        open(os.path.join(trxdir, "r.trx"), "w").write(TRX)

        # cwd = tempdir so parse_trx's containment check accepts the relative results dir.
        r = subprocess.run(
            [sys.executable, os.path.abspath(GATE),
             "--cobertura", cob, "--manifest", man, "--test-results-dir", "trx",
             "--repo-name", "fixture"],
            cwd=d, capture_output=True, text=True)
        out = r.stdout

        # Baseline floor (C0 10 / C1 0) sits at or below the fixture's Adjusted, so the ratchet
        # passes (exit 0). We assert on the report body regardless of exit code.
        fails = 0
        fails += check("red-suite banner present", "test(s) FAILING" in out, out)
        fails += check("section 6a present", "6a. Design debt" in out, out)
        fails += check("section 6b present", "6b. Structurally uncoverable" in out, out)
        fails += check("systematic-seam cluster callout", "Systematic seam opportunity" in out and "Guid.NewGuid" in out, out)
        fails += check("alias normalized: framework-mismatch", "framework-mismatch" in out and "framework_mismatch" not in out.split("6b")[-1], out)
        fails += check("alias normalized: requires-source-change", "requires-source-change" in out, out)

        # Risk Hotspots: the target-bucket gap (Process) shows; the dead-code target (OrphanCalc)
        # is suppressed to §6 and noted, so it must NOT be a hotspot row.
        hot = out.split("## 4. Risk Hotspots")[-1].split("## 5.")[0]
        fails += check("hotspot: real gap (Process) shown", "Process" in hot, hot)
        fails += check("hotspot: dead-code (OrphanCalc) suppressed", "OrphanCalc" not in hot, hot)
        fails += check("hotspot: suppression noted", "already logged in section 6" in hot, hot)
        fails += check("hotspot: exactly 1 in-scope gap", "1 of these sit in a target bucket" in hot, hot)

        if fails:
            print("\n%d check(s) FAILED (gate exit %d)" % (fails, r.returncode))
            if r.stderr:
                print("stderr:\n" + r.stderr[:2000])
            return 1
        print("\nAll gate render checks passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
