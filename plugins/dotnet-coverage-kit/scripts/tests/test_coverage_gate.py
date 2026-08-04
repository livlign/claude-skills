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
  - kit-sync: leaves a locally MODIFIED tool copy alone (regression: it once silently
    overwrote a documented repo-local change and only CI noticed)
  - kit-sync: refreshes stale tool copies + `auto` manifest migrations, preserves the
    manifest's comments, is idempotent, and never rewrites a workflow
  - scope-change guard: added TEST files are ignored (a PR that only adds tests must stay green),
    while added product code under an excluded path still fails. Runs the gate over a throwaway
    git repo, since the guard only engages with --base.

Run:  python3 scripts/tests/test_coverage_gate.py
Exit: 0 = pass (or SKIP if PyYAML unavailable and can't be installed), 1 = a failure.
PyYAML is a documented kit dependency; CI installs it, so the test runs there.
"""
import io, os, subprocess, sys, tempfile, textwrap

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


# --- scope-change guard fixture (needs a real git repo, so it gets its own tempdir) -------------
SCOPE_MANIFEST = MANIFEST + """  - pattern: "**/Tests/**"
    category: non-product
    reason: "Test code"
"""


def _git(d, *a):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git"] + list(a), cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def _write(d, rel, body):
    p = os.path.join(d, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(body)


def scope_guard_checks():
    """Adding a test file must not trip the scope-change guard.

    The guard exists to catch PRODUCT code landing under an excluded path. Every repo excludes its
    own test sources, so before this was fixed a PR that merely ADDED an xUnit file failed CI and
    demanded the `coverage-scope-change` label, which trains reviewers to rubber-stamp the one check
    that stops real logic being reclassified as untestable.
    """
    fails = 0
    with tempfile.TemporaryDirectory() as d:
        if _git(d, "init", "-q", "-b", "master").returncode != 0:
            print("  SKIP  scope guard: git unavailable")
            return 0
        os.makedirs(os.path.join(d, "trx"))
        _write(d, "trx/r.trx", TRX)
        _write(d, "cobertura.xml", COBERTURA)
        _write(d, "manifest.yml", SCOPE_MANIFEST)
        _write(d, "src/App/Application/OrderService.cs", "// base\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "base")
        _git(d, "checkout", "-q", "-b", "pr")

        def run():
            # The gate verdict lines go to stderr (stdout is the Markdown report), so read both.
            p = subprocess.run(
                [sys.executable, os.path.abspath(GATE),
                 "--cobertura", "cobertura.xml", "--manifest", "manifest.yml",
                 "--test-results-dir", "trx", "--repo-name", "fixture", "--base", "master"],
                cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace")
            return p.stdout + p.stderr

        # 1. Test files only: the guard must pass and say what it ignored.
        _write(d, "src/Tests/ServiceTests/UserServiceTests/VpiSettingChangeLogTests.cs", "// test\n")
        _write(d, "src/App.UnitTests/OrderServiceTests.cs", "// test\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "add tests")
        out = run()
        blob = "\n".join(l for l in out.splitlines() if "Scope change" in l) or out
        fails += check("scope guard: added tests do not trip it",
                       "Scope change" in blob and "none" in blob, blob)
        fails += check("scope guard: ignored count reported", "2 added test files ignored" in blob, blob)
        fails += check("scope guard: gate not failed by added tests", "[coverage-gate] PASS" in out, out)

        # 2. Product code under an excluded path still trips it, test files notwithstanding.
        _write(d, "src/App/Infrastructure/NewRepoService.cs", "// product\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "add excluded product file")
        out2 = run()
        fails += check("scope guard: excluded product file still flagged",
                       "new file under excluded path" in out2 and "NewRepoService.cs" in out2, out2)
        fails += check("scope guard: test file not reported as new excluded source",
                       "VpiSettingChangeLogTests.cs" not in out2, out2)
    return fails


def enforcement_checks():
    """Default is report-only: a real breach is reported, named ADVISORY, and still exits 0.

    The fixture's floor (C0 10 / C1 0) is deliberately raised above the measured 20%/0% so the
    ratchet genuinely breaches; the only difference between the two runs is `--enforce`.
    """
    fails = 0
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "trx"))
        _write(d, "trx/r.trx", TRX)
        _write(d, "cobertura.xml", COBERTURA)
        # Floor above what the fixture achieves => ratchet breach.
        _write(d, "manifest.yml", MANIFEST.replace("c0: 10.0", "c0: 99.0").replace("c1: 0.0", "c1: 99.0"))

        def run(*extra):
            p = subprocess.run(
                [sys.executable, os.path.abspath(GATE), "--cobertura", "cobertura.xml",
                 "--manifest", "manifest.yml", "--test-results-dir", "trx",
                 "--repo-name", "fixture"] + list(extra),
                cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace")
            return p.returncode, p.stdout + p.stderr

        rc, out = run()
        fails += check("enforce: breach does not fail by default", rc == 0, out)
        fails += check("enforce: breach still reported", "Ratchet" in out and "FAIL" in out, out)
        fails += check("enforce: advisory line names the check",
                       "ADVISORY: ratchet breached but NOT enforced" in out, out)
        fails += check("enforce: report header states report-only",
                       "**Enforced checks:** none (report only" in out, out)

        rc_on, out_on = run("--enforce", "ratchet")
        fails += check("enforce: --enforce ratchet fails the run", rc_on == 1, out_on)
        fails += check("enforce: verdict names the enforced check",
                       "FAIL (enforced: ratchet)" in out_on, out_on)
        fails += check("enforce: header lists armed checks", "**Enforced checks:** ratchet" in out_on, out_on)

        rc_other, out_other = run("--enforce", "diff")
        fails += check("enforce: arming a different check leaves this breach advisory",
                       rc_other == 0 and "ADVISORY: ratchet" in out_other, out_other)

        rc_man, out_man = run()
        _write(d, "manifest.yml", MANIFEST.replace("c0: 10.0", "c0: 99.0")
               .replace("c1: 0.0", "c1: 99.0").replace("ratchet: true", "ratchet: true\n  enforce: true"))
        rc_man2, out_man2 = run()
        fails += check("enforce: manifest gate.enforce: true fails the run",
                       rc_man == 0 and rc_man2 == 1, out_man2)

        rc_bad, out_bad = run("--enforce", "nonsense")
        fails += check("enforce: unknown value is rejected, not silently ignored",
                       rc_bad == 2 and "unknown gate.enforce value" in out_bad, out_bad)
    return fails


SYNC = os.path.join(os.path.dirname(__file__), "..", "kit-sync.py")

STALE_MANIFEST = """schema_version: 1

# COMMENT SENTINEL: a manifest is mostly comments and they must survive a migration.
target:
  c0: 95
gate:
  # comment inside gate
  diff_coverage_min_c0: 95
  ratchet: true
exclusions:
  - pattern: "**/Migrations/**"
    category: generated
    reason: "generated"
"""

BAD_WORKFLOW = """name: Coverage
on:
  push:
    branches: [dev]
  pull_request:
    types: [opened]
jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - run: ./.claude/coverage/tools/run-coverage.sh
"""


GOOD_WORKFLOW = """name: Coverage
on:
  pull_request:
    branches: [master]
    types: [opened]
jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - run: ./.claude/coverage/tools/run-coverage.sh
"""


def sync_checks():
    """kit-sync must update a stale repo, keep manifest comments, and be idempotent.

    It must also refuse to do the dangerous half: no sign-off migration, no workflow rewrite. A sync
    that silently reclassified code or edited CI would be worse than no sync at all.
    """
    import yaml
    fails = 0
    kit = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    with tempfile.TemporaryDirectory() as d:
        _write(d, ".claude/coverage/refs/coverage-manifest.yml", STALE_MANIFEST)
        _write(d, ".claude/coverage/tools/coverage-gate.py", "# stale copy")
        _write(d, ".github/workflows/coverage.yml", BAD_WORKFLOW)
        wf_before = open(os.path.join(d, ".github", "workflows", "coverage.yml")).read()

        def run(*extra):
            p = subprocess.run([sys.executable, os.path.abspath(SYNC), "--repo", d,
                                "--kit", kit] + list(extra),
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            return p.returncode, p.stdout + p.stderr

        rc, out = run("--check")
        man_after_check = open(os.path.join(d, ".claude/coverage/refs/coverage-manifest.yml".replace("/", os.sep))).read()
        fails += check("sync: --check writes nothing", man_after_check == STALE_MANIFEST, out)
        fails += check("sync: --check still reports the work", "update .claude/coverage/tools/coverage-gate.py" in out, out)

        rc, out = run()
        gate_dst = os.path.join(d, ".claude/coverage/tools/coverage-gate.py".replace("/", os.sep))
        man = open(os.path.join(d, ".claude/coverage/refs/coverage-manifest.yml".replace("/", os.sep)), encoding="utf-8").read()
        fails += check("sync: report.sh install signals re-exec (exit 10)", rc == 10, out)
        fails += check("sync: stale tool copy replaced", "is_test_source" in open(gate_dst, encoding="utf-8").read(), out)
        fails += check("sync: kit-sync installs itself", os.path.isfile(os.path.join(d, ".claude/coverage/tools/kit-sync.py".replace("/", os.sep))), out)
        fails += check("sync: manifest comments preserved", "COMMENT SENTINEL" in man and "# comment inside gate" in man, man)
        fails += check("sync: gate.enforce added", "enforce: false" in man, man)
        fails += check("sync: kit_version stamped", 'kit_version: "' in man, man)
        fails += check("sync: migrated manifest is valid YAML", yaml.safe_load(man) is not None, man)
        fails += check("sync: enforcement stays off after migration",
                       (yaml.safe_load(man)["gate"]["enforce"]) is False, man)
        fails += check("sync: exclusions untouched",
                       len(yaml.safe_load(man)["exclusions"]) == 1, man)
        fails += check("sync: reminds the user to commit", "COMMIT these files" in out, out)

        # Workflow: reported, never rewritten.
        fails += check("sync: flags non-PR trigger", "triggers besides pull_request (push)" in out, out)
        fails += check("sync: flags missing base-branch filter",
                       "pull_request has no `branches:` filter" in out, out)
        fails += check("sync: does NOT rewrite the workflow",
                       open(os.path.join(d, ".github", "workflows", "coverage.yml")).read() == wf_before, out)

        # A second run copies nothing and migrates nothing. The workflow notes DO repeat, because the
        # fixture workflow is still wrong: a real problem must not go quiet just because it was
        # mentioned once.
        rc2, out2 = run()
        did_write = [l for l in out2.splitlines() if " update " in l or " install " in l or "manifest" in l]
        fails += check("sync: second run copies and migrates nothing", rc2 == 0 and not did_write, out2)
        fails += check("sync: an unfixed workflow is reported every run",
                       "triggers besides pull_request" in out2, out2)

        # With the workflow corrected there is nothing left to say, and --quiet says nothing.
        _write(d, ".github/workflows/coverage.yml", GOOD_WORKFLOW)
        rc3, out3 = run("--quiet")
        fails += check("sync: --quiet prints nothing when current and clean",
                       rc3 == 0 and out3.strip() == "", repr(out3))

        rc4 = subprocess.run([sys.executable, os.path.abspath(SYNC), "--repo", d, "--kit",
                              os.path.join(d, "nope")], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").returncode
        fails += check("sync: bogus --kit falls back to this kit, no crash", rc4 in (0, 10), str(rc4))

    # The pointer file is what lets a bare `report.sh` in any repo find the kit with no environment
    # set up, which is the whole premise of the auto-update. Exercised against a throwaway HOME so the
    # test never writes to the real one.
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as d2:
        _write(d2, ".claude/coverage/refs/coverage-manifest.yml", STALE_MANIFEST)
        env = dict(os.environ, HOME=home, USERPROFILE=home)
        env.pop("KIT_ROOT", None)
        env.pop("CLAUDE_PLUGIN_ROOT", None)

        def run_env(*extra):
            p = subprocess.run([sys.executable, os.path.abspath(SYNC), "--repo", d2] + list(extra),
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env=env)
            return p.returncode, p.stdout + p.stderr

        run_env("--kit", kit)
        pointer = os.path.join(home, ".claude", "dotnet-coverage-kit-root")
        fails += check("sync: resolved kit path is remembered", os.path.isfile(pointer), pointer)
        if os.path.isfile(pointer):
            fails += check("sync: pointer holds the kit root",
                           open(pointer, encoding="utf-8").read().strip() == os.path.abspath(kit),
                           open(pointer, encoding="utf-8").read())
        rc5, out5 = run_env()   # no --kit, no env: must resolve via the pointer
        fails += check("sync: later run resolves with no hints",
                       "no kit checkout found" not in out5, out5)
        fails += check("sync: --check does not write the pointer",
                       run_env("--check")[0] == 0, "check mode")
    return fails


def local_edit_checks():
    """A repo-local edit to a tool script must survive a sync.

    This is a regression test for a real incident: a repo carried a documented TEST_PROJECT_EXCLUDE
    change in run-coverage.sh, the auto-sync overwrote it, and the only signal was CI hard-failing on
    the solution-membership guard. The sync now records what it writes, so a copy differing from BOTH
    the kit and that record is a deliberate edit and is left alone.
    """
    fails = 0
    kit = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    with tempfile.TemporaryDirectory() as d:
        _write(d, ".claude/coverage/refs/coverage-manifest.yml", STALE_MANIFEST)

        def run(*extra):
            p = subprocess.run([sys.executable, os.path.abspath(SYNC), "--repo", d, "--kit", kit]
                               + list(extra), capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
            return p.returncode, p.stdout + p.stderr

        run()                                     # baseline install, writes the record
        rc_path = os.path.join(d, ".claude", "coverage", "tools", ".kit-installed.json")
        fails += check("local-edit: install record written", os.path.isfile(rc_path), rc_path)

        tool = os.path.join(d, ".claude", "coverage", "tools", "run-coverage.sh")
        with io.open(tool, "a", encoding="utf-8") as fh:
            fh.write("# REPO-LOCAL TWEAK" + chr(10))
        rc, out = run()
        body = io.open(tool, encoding="utf-8").read()
        fails += check("local-edit: modified tool is NOT overwritten", "REPO-LOCAL TWEAK" in body, out)
        fails += check("local-edit: it is reported, not silent", "locally MODIFIED" in out, out)
        fails += check("local-edit: names the way through", "--force" in out, out)

        rc, out = run("--force")
        body = io.open(tool, encoding="utf-8").read()
        fails += check("local-edit: --force discards it", "REPO-LOCAL TWEAK" not in body, out)

    # No record yet (first sync after adopting this version): the old copy is kept, not assumed junk.
    with tempfile.TemporaryDirectory() as d2:
        _write(d2, ".claude/coverage/refs/coverage-manifest.yml", STALE_MANIFEST)
        _write(d2, ".claude/coverage/tools/run-coverage.sh", "# ancient copy")
        p = subprocess.run([sys.executable, os.path.abspath(SYNC), "--repo", d2, "--kit", kit],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        bak = os.path.join(d2, ".claude", "coverage", "tools", "run-coverage.sh.pre-sync")
        fails += check("local-edit: unrecorded copy is backed up", os.path.isfile(bak),
                       p.stdout + p.stderr)
        if os.path.isfile(bak):
            fails += check("local-edit: backup holds the old content",
                           io.open(bak, encoding="utf-8").read() == "# ancient copy", "")
    return fails


def unit_checks():
    """is_test_source: directory-segment detection, and the words it must NOT mistake for tests."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(GATE)))
    import importlib.util
    spec = importlib.util.spec_from_file_location("cg", os.path.abspath(GATE))
    cg = importlib.util.module_from_spec(spec); spec.loader.exec_module(cg)
    fails = 0
    for p in ("src/Tests/Foo/BarTests.cs", "tests/App.Tests/BarTests.cs",
              "src/App.UnitTests/BarTests.cs", "src/unit-tests/Bar.cs", "src/Test/Bar.cs"):
        fails += check("is_test_source: %s" % p, cg.is_test_source(p), p)
    for p in ("src/App/Latest/Bar.cs", "src/App/Manifest/Bar.cs", "src/App/Service/TestData.cs",
              "src/App/Infrastructure/RepoService.cs"):
        fails += check("is_test_source: NOT %s" % p, not cg.is_test_source(p), p)
    fails += check("is_test_source: manifest glob override",
                   cg.is_test_source("src/App/Spec/BarSpec.cs", ["**/Spec/**"]), "override")
    return fails


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
            cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace")
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

        # Kit-drift note. The fixture manifest carries no `kit_version:`, so an unstamped repo must
        # say so by itself: the whole point is that nobody has to think of asking.
        fails += check("drift: unstamped note present", "Kit updates may be pending" in out, out)

        def rerun_with(extra_manifest_lines):
            man2 = os.path.join(d, "m2.yml")
            open(man2, "w").write(MANIFEST + extra_manifest_lines)
            return subprocess.run(
                [sys.executable, os.path.abspath(GATE),
                 "--cobertura", cob, "--manifest", man2, "--test-results-dir", "trx",
                 "--repo-name", "fixture"],
                cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

        def drift_state(extra_manifest_lines):
            man2 = os.path.join(d, "m3.yml")
            open(man2, "w").write(MANIFEST + extra_manifest_lines)
            return subprocess.run(
                [sys.executable, os.path.abspath(GATE), "--manifest", man2, "--print-kit-drift"],
                cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.split()

        cur = drift_state("")
        behind_out = rerun_with('\nkit_version: "0.4.0"\n')
        fails += check("drift: behind names coverage-redo",
                       "Kit updates pending" in behind_out and "coverage-redo" in behind_out, behind_out)
        current_out = rerun_with('\nkit_version: "%s"\n' % cur[2])
        fails += check("drift: current emits no note",
                       "Kit updates" not in current_out and "Stale tool copies" not in current_out,
                       current_out)
        fails += check("drift: query mode states",
                       drift_state("")[0] == "unstamped"
                       and drift_state('\nkit_version: "0.4.0"\n')[0] == "behind"
                       and drift_state('\nkit_version: "%s"\n' % cur[2])[0] == "current"
                       and drift_state('\nkit_version: "99.0.0"\n')[0] == "ahead",
                       " ".join(drift_state("")))

        fails += unit_checks()
        fails += enforcement_checks()
        fails += scope_guard_checks()
        fails += sync_checks()
        fails += local_edit_checks()

        if fails:
            print("\n%d check(s) FAILED (gate exit %d)" % (fails, r.returncode))
            if r.stderr:
                print("stderr:\n" + r.stderr[:2000])
            return 1
        print("\nAll gate render checks passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
