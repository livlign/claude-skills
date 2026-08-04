#!/usr/bin/env python3
"""kit-sync: bring a repo's installed coverage kit up to the kit you have checked out.

Why this exists: the kit's scripts and rules live in a plugin, but every repo carries its OWN copies
under `.claude/coverage/tools/` (CI runs the committed copies, not the plugin). Pulling a new kit
therefore changed nothing in any repo until somebody remembered to copy files by hand, which is how a
repo sits for months on a gate whose bug was fixed upstream. This script closes that gap: it is
invoked automatically at the top of `report.sh`, so simply RUNNING the report in a repo installs the
new tool copies and applies the mechanical (`auto`) manifest migrations.

What it will and will not do, by design:

  * COPIES the tool scripts, because they are ours and a repo has no business editing them.
  * SEEDS `refs/coverage.runsettings` only when absent. It is repo-tunable, so an existing one is
    reported as differing and never overwritten.
  * APPLIES only migrations classified `auto` in MIGRATIONS.md, as TEXT edits that preserve the
    manifest's comments (a yaml round-trip would delete every comment in a heavily documented file).
  * NEVER applies a `sign-off` migration, never edits classifications, exclusions, the floor, or any
    number. Those change what is measured and stay a reviewed decision; they are printed as pending.
  * NEVER rewrites a workflow file. It CHECKS the coverage workflow's triggers and reports drift,
    because silently editing someone's CI is a worse failure than telling them about it.

Exit codes: 0 = nothing to do or done; 10 = `report.sh` itself was replaced, so the caller must
re-exec it to pick up the new version; 2 = error.
"""
import argparse
import io
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Kit file -> path inside the repo. Overwritten whenever the content differs.
TOOLS = {
    "scripts/coverage-gate.py": ".claude/coverage/tools/coverage-gate.py",
    "scripts/run-coverage.sh": ".claude/coverage/tools/run-coverage.sh",
    "scripts/report.sh": ".claude/coverage/tools/report.sh",
    "scripts/kit-sync.py": ".claude/coverage/tools/kit-sync.py",
}

# Seeded when missing, never overwritten: the repo is expected to tune these.
SEED = {
    "templates/coverage.runsettings": ".claude/coverage/refs/coverage.runsettings",
}

MANIFEST_REL = ".claude/coverage/refs/coverage-manifest.yml"

# report.sh is the one file whose replacement the caller must react to: bash reads a running script
# incrementally, so overwriting it mid-run can corrupt execution.
REEXEC_SENTINEL = "scripts/report.sh"
EXIT_REEXEC = 10


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    # newline="" keeps whatever line endings the content carries, so a checkout on Windows does not
    # rewrite every line and produce a diff that looks like a change nobody made.
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def kit_semver(kit_root):
    try:
        meta = json.loads(read(os.path.join(kit_root, ".claude-plugin", "plugin.json")))
        return str(meta.get("version") or "").strip()
    except Exception:
        return ""


# Where a resolved kit path is remembered, so the NEXT run finds it with no environment set up. It is
# a per-machine absolute path, so it lives in the user's home and never in the repo: committing it
# would hand every other developer (and CI) a path that does not exist on their machine.
POINTER = os.path.join(os.path.expanduser("~"), ".claude", "dotnet-coverage-kit-root")

PLUGIN_NAME = "dotnet-coverage-kit"


def is_kit(path):
    return bool(path) and os.path.isfile(os.path.join(path, ".claude-plugin", "plugin.json"))


def _search_plugin_roots():
    """Plausible install locations, so a plain `report.sh` in a repo finds the kit unaided."""
    import glob
    home = os.path.expanduser("~")
    pats = [
        os.path.join(home, ".claude", "plugins", "*", "plugins", PLUGIN_NAME),
        os.path.join(home, ".claude", "plugins", PLUGIN_NAME),
        os.path.join(home, ".claude", "marketplaces", "*", "plugins", PLUGIN_NAME),
        os.path.join(home, ".claude", "*", "plugins", PLUGIN_NAME),
    ]
    found = []
    for pat in pats:
        for hit in glob.glob(pat):
            if is_kit(hit):
                found.append(os.path.abspath(hit))
    return found


def locate_kit(explicit):
    """Kit root, searched in order of how explicit the signal is.

    The pointer file is what makes this work from a bare repo: the first run that DOES know where the
    kit is (a skill run with CLAUDE_PLUGIN_ROOT set, an explicit --kit, or a run from inside the kit)
    records it, and every later `report.sh` in any repo resolves instantly.
    """
    cands = [explicit, os.environ.get("KIT_ROOT"), os.environ.get("CLAUDE_PLUGIN_ROOT")]
    if os.path.isfile(POINTER):
        try:
            cands.append(read(POINTER).strip())
        except Exception:
            pass
    cands.append(os.path.dirname(HERE))          # running straight from the kit checkout
    cands.extend(_search_plugin_roots())
    for cand in cands:
        if not cand:
            continue
        cand = os.path.abspath(os.path.expanduser(cand))
        if is_kit(cand):
            return cand
    return None


def remember_kit(path):
    """Record the resolved kit path for later runs. Best effort: never fail a sync over it."""
    try:
        if os.path.isfile(POINTER) and read(POINTER).strip() == path:
            return
        write(POINTER, path + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------------------------
# AUTO manifest migrations. Each takes the manifest TEXT and returns (new_text, note) with note
# None when the manifest already satisfies it. Text edits, never a yaml round-trip: the manifest is
# mostly comments and they are the reason anyone can review it.
# ---------------------------------------------------------------------------------------------

def mig_gate_enforce(text):
    """v0.15.0: make the enforcement choice explicit.

    Writes `enforce: false`, which is exactly what an absent key already means, so behavior is
    unchanged and only the manifest becomes self-describing. ARMING a check is the opposite
    direction and stays a human decision.
    """
    if re.search(r"^gate:\s*$", text, re.M) is None:
        return text, None
    gate_block = re.search(r"^gate:\s*$(?:\n(?:[ \t].*|\s*)$)*", text, re.M)
    if gate_block and re.search(r"^\s+enforce\s*:", gate_block.group(0), re.M):
        return text, None
    add = (
        "  # Which checks may FAIL the run: any of ratchet, diff, scope (or true / false).\n"
        "  # false (the default) reports every breach and keeps the run green; only a failing build\n"
        "  # or test run is red. Arm per check when ready, e.g. `enforce: [diff]`.\n"
        "  enforce: false\n"
    )
    return re.sub(r"^gate:\s*$\n", "gate:\n" + add, text, count=1, flags=re.M), \
        "added `gate.enforce: false` (explicit form of the existing default)"


def mig_kit_version_key(text):
    """v0.13.0: the manifest must carry a `kit_version:` stamp so later upgrades are a delta."""
    if re.search(r"^kit_version\s*:", text, re.M):
        return text, None
    anchor = re.search(r"^schema_version\s*:.*$", text, re.M)
    stamp = 'kit_version: ""\n'
    if anchor:
        i = anchor.end()
        return text[:i] + "\n\n" + stamp.rstrip("\n") + text[i:], "added the `kit_version:` stamp"
    return stamp + text, "added the `kit_version:` stamp"


# Ordered oldest-first. Every entry must be idempotent: a second run is a no-op.
AUTO_MIGRATIONS = [
    ("0.13.0", mig_kit_version_key),
    ("0.15.0", mig_gate_enforce),
]

# Migrations that change what is measured. Never applied here; named so the user learns they are due.
SIGNOFF_HINTS = [
    ("0.12.0", "`scope.vendored_paths` for any first-party library COPIED INTO this repo"),
    ("0.11.0", "`latent_bugs:` entries for defects frozen by characterization tests"),
]


def stamp_kit_version(text, semver):
    if not semver:
        return text, None
    m = re.search(r'^kit_version\s*:\s*"?([^"\n]*)"?\s*$', text, re.M)
    if not m:
        return text, None
    if m.group(1).strip() == semver:
        return text, None
    old = m.group(1).strip() or "unstamped"
    return text[:m.start()] + 'kit_version: "%s"' % semver + text[m.end():], \
        "stamped kit_version %s -> %s" % (old, semver)


# ---------------------------------------------------------------------------------------------
# Workflow trigger check (reported, never rewritten)
# ---------------------------------------------------------------------------------------------

def check_workflow(repo, production_branch):
    """Confirm the coverage workflow runs ONLY for pull requests into the production branch."""
    wf_dir = os.path.join(repo, ".github", "workflows")
    if not os.path.isdir(wf_dir):
        return []
    findings = []
    for name in sorted(os.listdir(wf_dir)):
        if not name.endswith((".yml", ".yaml")):
            continue
        path = os.path.join(wf_dir, name)
        try:
            body = read(path)
        except Exception:
            continue
        if "run-coverage.sh" not in body and "coverage-gate.py" not in body:
            continue
        rel = os.path.join(".github/workflows", name).replace("\\", "/")
        on_block = re.search(r"^on:\s*$((?:\n(?:[ \t].*)?$)*)", body, re.M)
        if not on_block:
            findings.append("%s: could not read its `on:` block; check it runs on PRs only" % rel)
            continue
        block = on_block.group(1)
        # Top-level trigger keys inside `on:` are the two-space-indented mapping keys.
        triggers = re.findall(r"^  ([a-z_]+):", block, re.M)
        extra = [t for t in triggers if t != "pull_request"]
        if extra:
            findings.append("%s: triggers besides pull_request (%s). This job is meant to run ONLY "
                            "on PRs into %s." % (rel, ", ".join(sorted(set(extra))), production_branch))
        if "pull_request" not in triggers:
            findings.append("%s: no pull_request trigger." % rel)
        # Read the branch filter from the pull_request sub-block ONLY. Scanning the whole `on:` block
        # would happily report another trigger's filter (a `push: branches: [dev]`) as the PR filter,
        # which sends the reader looking at the wrong four lines.
        pr_block = re.search(r"^  pull_request:\s*$((?:\n(?:    .*|\s*)$)*)", block, re.M)
        pr_body = pr_block.group(1) if pr_block else ""
        branches = re.search(r"^\s+branches:\s*\[([^\]]*)\]", pr_body, re.M)
        if branches:
            names = [b.strip().strip("'\"") for b in branches.group(1).split(",") if b.strip()]
            if names != [production_branch]:
                findings.append("%s: pull_request base-branch filter is %s, expected [%s]."
                                % (rel, names, production_branch))
        elif re.search(r"^\s+branches:", pr_body, re.M):
            findings.append("%s: pull_request `branches:` is not a simple list; confirm it only "
                            "matches %s." % (rel, production_branch))
        elif "pull_request" in triggers:
            findings.append("%s: pull_request has no `branches:` filter, so it runs for PRs into ANY "
                            "branch. Add `branches: [%s]`." % (rel, production_branch))
    return findings


def main():
    ap = argparse.ArgumentParser(description="Sync a repo's installed coverage kit to this kit.")
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--kit", help="kit root; defaults to $KIT_ROOT, $CLAUDE_PLUGIN_ROOT, or this script's kit")
    ap.add_argument("--production-branch", default="master")
    ap.add_argument("--check", action="store_true", help="report what WOULD change; write nothing")
    ap.add_argument("--quiet", action="store_true", help="print nothing when already up to date")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    kit = locate_kit(args.kit)
    if not kit:
        # Not an error: CI runs from the committed copies with no kit checkout in sight, and that is
        # the normal case. Staying silent keeps it out of the CI log.
        if not args.quiet:
            print("[kit-sync] no kit checkout found; skipped. Point at it once with "
                  "`--kit <path>` or KIT_ROOT=<path> and it is remembered in %s." % POINTER)
        return 0
    if os.path.normcase(kit) == os.path.normcase(os.path.join(repo, ".claude", "coverage")):
        return 0
    if not args.check:
        remember_kit(kit)

    semver = kit_semver(kit)
    actions, notes, reexec = [], [], False

    for src_rel, dst_rel in TOOLS.items():
        src, dst = os.path.join(kit, src_rel), os.path.join(repo, dst_rel)
        if not os.path.isfile(src):
            continue
        new = read(src)
        if os.path.isfile(dst) and read(dst) == new:
            continue
        actions.append("%s %s" % ("update" if os.path.isfile(dst) else "install", dst_rel))
        if not args.check:
            write(dst, new)
            shutil.copymode(src, dst)
            if src_rel == REEXEC_SENTINEL:
                reexec = True

    for src_rel, dst_rel in SEED.items():
        src, dst = os.path.join(kit, src_rel), os.path.join(repo, dst_rel)
        if not os.path.isfile(src):
            continue
        if not os.path.exists(dst):
            actions.append("install %s" % dst_rel)
            if not args.check:
                write(dst, read(src))
        elif read(dst) != read(src):
            notes.append("%s differs from the kit template; left as-is (repo-tunable)." % dst_rel)

    man_path = os.path.join(repo, MANIFEST_REL)
    if os.path.isfile(man_path):
        text = original = read(man_path)
        for ver, fn in AUTO_MIGRATIONS:
            text, note = fn(text)
            if note:
                actions.append("manifest (v%s): %s" % (ver, note))
        text, note = stamp_kit_version(text, semver)
        if note:
            actions.append("manifest: %s" % note)
        if text != original and not args.check:
            try:
                import yaml
                yaml.safe_load(text)
            except Exception as e:
                print("[kit-sync] ERROR: the migrated manifest does not parse (%s); left untouched."
                      % e, file=sys.stderr)
                return 2
            write(man_path, text)
        stamped = re.search(r'^kit_version\s*:\s*"?([^"\n]*)"?\s*$', text, re.M)
        cur = (stamped.group(1).strip() if stamped else "")
        for ver, what in SIGNOFF_HINTS:
            if cur and semver and _older(cur, ver):
                notes.append("pending review (v%s, NOT auto-applied): %s. Run `coverage-redo`."
                             % (ver, what))
    else:
        notes.append("no %s here; run `coverage-init` first." % MANIFEST_REL)

    notes.extend(check_workflow(repo, args.production_branch))

    if actions or notes:
        head = "[kit-sync] kit %s%s" % (semver or "?", " (check only, nothing written)" if args.check else "")
        print(head)
        for a in actions:
            print("[kit-sync]   %s" % a)
        for n in notes:
            print("[kit-sync]   note: %s" % n)
        if actions and not args.check:
            print("[kit-sync] COMMIT these files: they are what CI runs.")
    elif not args.quiet:
        print("[kit-sync] kit %s: already up to date." % (semver or "?"))

    return EXIT_REEXEC if reexec else 0


def _older(a, b):
    def parts(v):
        out = []
        for x in str(v).split("."):
            m = re.match(r"\d+", x)
            out.append(int(m.group(0)) if m else 0)
        return out + [0] * (3 - len(out))
    return parts(a) < parts(b)


if __name__ == "__main__":
    sys.exit(main())
