#!/usr/bin/env python3
"""
coverage-gate: join a ReportGenerator Cobertura report against the repo's
coverage-manifest.yml, compute IN-SCOPE (Adjusted) coverage, emit the Unit Test Report
(Markdown), and report the gate checks.

In-scope = every source file NOT matched by a manifest `exclusions` pattern. Exclusions
are checked first; remaining files are bucketed by `category_map` (unmatched -> uncategorized).
The excluded buckets are removed from the denominator, per rules/coverage-report.base.md.

Checks (always MEASURED; whether a breach FAILS the run is set by `gate.enforce` / --enforce,
which defaults to NONE, so by default only a failing build or test run is red):
- Ratchet: Adjusted (in-scope) C0/C1 must not drop below baseline.recorded_overall.
- Diff coverage (PR mode, --base given): changed in-scope lines must meet the manifest minimums.
- Scope-change guard (PR mode): growth of `exclusions`/`cannot_test`, or new product source under
  an excluded path, is flagged unless --allow-scope-change is passed.

Exit codes: 0 = pass, 1 = gate fail, 2 = usage/parse error.

The report has the fixed Unit Test Report shape (see rules/coverage-report.base.md):
  1 Test Results · 2 Coverage Summary · 3 Coverage by Layer · 4 Risk Hotspots
  5 Excluded Code · 6 Not Testable.
Numbers are tool output only (Cobertura + the join here); the model never edits them.
"""
import argparse, fnmatch, sys, re, subprocess, glob, os, datetime
import xml.etree.ElementTree as ET

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252; report has ✅/❌
except Exception:
    pass

try:
    import yaml
except ImportError:
    print("coverage-gate: PyYAML is required (pip install pyyaml).", file=sys.stderr)
    sys.exit(2)


# Bumped whenever the installed tools/ scripts change in a way a repo should pick
# up. report.sh prints it, so a stale copy in a repo is visible without diffing.
KIT_VERSION = "2.4.0"

# The PLUGIN version these scripts ship with (KIT_VERSION above tracks the script contract; this
# tracks the kit release, and is bumped alongside .claude-plugin/plugin.json). It exists so that any
# run can compare itself against the manifest's `kit_version:` stamp and say "this repo has not been
# brought up to the current kit yet" without anyone having to remember to ask. See MIGRATIONS.md.
KIT_SEMVER = "0.17.0"

# Section 7's heading text, used both to emit the heading and to build the banner's jump anchor via
# _slug(). One constant so the link and the target cannot drift apart.
LATENT_HEADING = "7. Latent bugs frozen by characterization (ACTION REQUIRED)"

# Severity scale for manifest `latent_bugs:`. A/B/C are the "needs resolving" band counted in the
# banner; D/E are recorded but not escalated.
SEV_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
SEV_LABEL = {
    "A": "A / Security / cross-tenant",
    "B": "B / Data loss or corruption",
    "C": "C / Unhandled exception surfacing as a 500",
    "D": "D / Correctness / observability",
    "E": "E / Dead code or note, not a defect",
}


def _semver(v):
    """('0','9','0') -> (0, 9, 0). Unparseable or empty -> None, treated as "older than anything"."""
    parts = re.findall(r"\d+", str(v or ""))
    if not parts:
        return None
    return tuple(int(p) for p in (parts + ["0", "0", "0"])[:3])


def kit_drift(manifest):
    """Compare the manifest's `kit_version:` stamp against the kit these scripts ship with.

    Returns (stamped, state) where state is one of "current", "behind", "unstamped", "ahead".
    Deterministic and manifest-only, so every entry point (report, backfill, redo) can ask the same
    question cheaply and reach the same answer instead of each eyeballing it.
    """
    stamped = (manifest.get("kit_version") or "").strip()
    if not stamped:
        return stamped, "unstamped"
    a, b = _semver(stamped), _semver(KIT_SEMVER)
    if a == b:
        return stamped, "current"
    return stamped, "behind" if (a is None or a < b) else "ahead"


def drift_note(manifest):
    """One Markdown line for the report when a repo is not on the current kit, else None.

    Deliberately a NOTE, not a red banner: pending updates are normal maintenance, not a defect, and
    a false alarm on every run is how real banners get ignored. The point is that nobody has to know
    to ask, so the prompt reaches the artifact people already read.
    """
    stamped, state = kit_drift(manifest)
    if state == "current":
        return None
    if state == "unstamped":
        return ("> ℹ️ **Kit updates may be pending.** This manifest carries no `kit_version:` stamp, "
                "so it predates the stamp and has not been reconciled against kit %s. Run "
                "`coverage-redo` to apply the migrations that still apply to it (it detects them; "
                "nothing is applied silently that could move the numbers)." % KIT_SEMVER)
    if state == "ahead":
        return ("> ℹ️ **Stale tool copies.** The manifest is stamped kit %s but these scripts ship "
                "with %s, so `.claude/coverage/tools/` is older than the manifest it reads. Refresh "
                "the copies from the plugin before trusting a gate result." % (stamped, KIT_SEMVER))
    return ("> ℹ️ **Kit updates pending.** This repo is reconciled to kit %s; the current kit is %s. "
            "Run `coverage-redo` to review and apply what changed since (it walks MIGRATIONS.md and "
            "detects which entries this repo still needs). The numbers below are unaffected: this "
            "report applies nothing." % (stamped, KIT_SEMVER))


# Directories never worth walking when locating a vendored project.
_SKIP_DIRS = {".git", ".vs", ".idea", "node_modules", "bin", "obj", "packages", "coverage",
              "TestResults", ".claude"}


def locate_vendored_dir(repo_root, declared, max_depth=4):
    """Repo-relative path of a declared vendored directory, or None.

    Accepts the bare library name ("sharedlib") as well as a full relative path
    ("src/sharedlib"), because the bare name is what people naturally write while the directory
    usually sits a level or two down. Returns the path as found, with forward slashes, so callers
    build filter terms that match the real paths rather than the declaration.
    """
    declared = declared.replace("\\", "/").strip("/")
    if not declared:
        return None
    direct = os.path.join(repo_root, declared)
    if os.path.isdir(direct):
        return declared

    # Shallow breadth-first walk: a vendored library is a top-level-ish directory, never buried deep.
    for root, dirs, _files in os.walk(repo_root):
        rel = os.path.relpath(root, repo_root).replace("\\", "/")
        depth = 0 if rel == "." else rel.count("/") + 1
        if depth >= max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for d in dirs:
            cand = ("%s/%s" % ("" if rel == "." else rel, d)).lstrip("/")
            if cand == declared or cand.endswith("/" + declared) or d == declared:
                return cand
    return None


def resolve_file_filter(m, repo_filter=None, repo_root="."):
    """The ReportGenerator -filefilters expression for this repo.

    Single source of truth, read from the manifest, so a local run and CI cannot
    drift apart. Resolution order:

      1. manifest scope.file_filter, when set
      2. otherwise derive "+*<repo_filter>*" from the bare substring

    Then every declared scope.vendored_paths entry that actually exists as a
    directory in the repo gets a "-*<path>*" exclusion appended if missing.

    That last step is the load-bearing one. A first-party shared library copied
    INTO the repo sits under the repo root, so its paths contain the repo's own
    name and are swallowed by the "+*<repo>*" include. Left unexcluded it lands
    in the denominator: one real case pulled in 2447 foreign files and moved the
    reported figure from 83.9% to 33.3% with no code change behind it.
    """
    scope = m.get("scope") or {}
    base = (scope.get("file_filter") or "").strip()
    if not base and repo_filter:
        base = "+*%s*" % repo_filter

    terms = [t.strip() for t in base.split(";") if t.strip()]
    have = {t.lower() for t in terms}
    absent = []
    for path in scope.get("vendored_paths") or []:
        path = str(path).strip().strip("/\\")
        if not path:
            continue
        # Only exclude what is actually present: a declared-but-absent path means
        # the vendoring has not reached this repo yet, and a standing exclusion
        # for it would be dead weight that hides the day it arrives.
        found = locate_vendored_dir(repo_root, path)
        if not found:
            # Pre-declaring a library before it is vendored here is RECOMMENDED (it closes the hole
            # automatically on the day the migration lands), so an absent entry is the normal case,
            # not a problem. Collect them and say it once, quietly, rather than warning per path on
            # every run.
            absent.append(path)
            continue
        # Use the path as FOUND, not as declared. Declaring the bare library name is the natural
        # thing to write, but the directory usually sits a level or two down (src/<name>), and a
        # `-*<name>*` term built from the bare name would not match the real paths.
        path = found
        # A multi-segment path needs BOTH separator spellings. ReportGenerator matches these globs
        # against the raw paths in the coverage data, which are backslashed on Windows and
        # forward-slashed on Linux, and a glob cannot express "either separator". Emitting one
        # spelling silently no-ops on the other platform: the filter looks correct, and the foreign
        # files land in the denominator anyway. Single-segment paths have no separator to disagree
        # about, so they stay one term.
        spellings = [path]
        if "/" in path or "\\" in path:
            spellings = [path.replace("\\", "/"), path.replace("/", "\\")]
        for spelling in spellings:
            term = "-*%s*" % spelling
            if term.lower() not in have:
                terms.append(term)
                have.add(term.lower())
    if absent:
        print("[coverage-gate] note: %d declared vendored path(s) not present here, so no "
              "filefilter term was emitted for them (expected if the vendoring has not landed "
              "yet; check for a typo if one should be here): %s"
              % (len(absent), ", ".join(absent)), file=sys.stderr)
    return ";".join(terms)


def vendored_exclusions(m):
    """Synthetic `exclusions` entries for every declared scope.vendored_paths directory.

    A vendored reference project (a first-party library COPIED INTO this repo rather than consumed
    as a package or a sibling checkout) has to leave scope in TWO independent places, and declaring
    it once must cover both or they drift:

      1. MEASUREMENT: out of the ReportGenerator filefilter, so its lines never reach the
         denominator. Handled by resolve_file_filter().
      2. CLASSIFICATION: out of `exclusions`, so the sweep does not enumerate it, the backfill
         never opens a worklist item for it, and no test is written against another repo's source.

    Effect 1 alone looks sufficient because the reported percentage comes out right, but the sweep
    reads the FILESYSTEM, not the coverage XML. One real case enumerated 1,749 foreign files and
    would have generated tests for a shared library owned by a different team.

    Generated rather than required-in-`exclusions` so `vendored_paths` stays the single declaration.
    A hand-written exclusion for the same path is harmless: both match, first one wins.
    """
    out = []
    for path in ((m.get("scope") or {}).get("vendored_paths") or []):
        path = str(path).strip().strip("/\\")
        if not path:
            continue
        out.append({
            "pattern": "**/%s/**" % path,
            "category": "non-product",
            "reason": (
                "Vendored reference project: a copy of another repo's sources living inside this "
                "repo. Owned and tested by that repo, so it is neither measured nor a test target "
                "here. Declared once in scope.vendored_paths, which drives both the filefilter and "
                "this exclusion."
            ),
            "_generated_from": "scope.vendored_paths",
        })
    return out


def _localname(tag):
    return tag.rsplit("}", 1)[-1]


def parse_cobertura(path):
    """Return (files, methods).
    files[fn] = {cov,tot,bcov,btot,mcov,mtot,linemap}
    methods   = [ {file, cls, name, complexity, covered, line_rate} ]
    """
    root = ET.parse(path).getroot()
    files = {}
    methods = []
    cond = re.compile(r"\((\d+)/(\d+)\)")

    def line_stats(lines_el):
        cov = tot = bcov = btot = 0
        lm = {}
        if lines_el is not None:
            for ln in lines_el.findall("line"):
                no = int(ln.get("number", "0"))
                hit = int(ln.get("hits", "0")) > 0
                tot += 1
                if hit:
                    cov += 1
                isbranch = ln.get("branch") == "true"
                bc = bt = 0
                if isbranch:
                    mm = cond.search(ln.get("condition-coverage", ""))
                    if mm:
                        bc, bt = int(mm.group(1)), int(mm.group(2))
                        bcov += bc; btot += bt
                e = lm.get(no)
                if e is None:
                    lm[no] = {"hit": hit, "branch": isbranch, "bcov": bc, "btot": bt}
                else:
                    e["hit"] = e["hit"] or hit
                    e["branch"] = e["branch"] or isbranch
                    e["bcov"] += bc; e["btot"] += bt
        return cov, tot, bcov, btot, lm

    for cls in root.iter("class"):
        fn = cls.get("filename", "").replace("\\", "/")
        clsname = (cls.get("name", "") or "").split("/")[-1]
        f = files.setdefault(fn, {"cov": 0, "tot": 0, "bcov": 0, "btot": 0,
                                  "mcov": 0, "mtot": 0, "linemap": {}})
        # class-level lines (authoritative for C0/C1)
        cov, tot, bcov, btot, lm = line_stats(cls.find("lines"))
        f["cov"] += cov; f["tot"] += tot; f["bcov"] += bcov; f["btot"] += btot
        for no, e in lm.items():
            ex = f["linemap"].get(no)
            if ex is None:
                f["linemap"][no] = dict(e)
            else:
                ex["hit"] = ex["hit"] or e["hit"]
                ex["branch"] = ex["branch"] or e["branch"]
                ex["bcov"] += e["bcov"]; ex["btot"] += e["btot"]
        # methods (for method-coverage + risk hotspots)
        methods_el = cls.find("methods")
        if methods_el is not None:
            for me in methods_el.findall("method"):
                mcov, mtot, _, _, mlm = line_stats(me.find("lines"))
                covered = mcov > 0
                try:
                    cx = int(float(me.get("complexity", "0")))
                except ValueError:
                    cx = 0
                f["mtot"] += 1
                if covered:
                    f["mcov"] += 1
                methods.append({
                    "file": fn, "cls": clsname,
                    "bare": me.get("name", ""),
                    "name": me.get("name", "") + (me.get("signature", "") or ""),
                    "complexity": cx, "covered": covered,
                    "line_rate": (mcov / mtot) if mtot else 0.0,
                    "lines": {no: e["hit"] for no, e in mlm.items()},
                })
    return files, methods


def match(path, pattern):
    return fnmatch.fnmatch(path, pattern.replace("**", "*"))


# WHICH CHECKS MAY FAIL CI. Default: none of them.
#
# The gate measures and reports exactly as before; what changed is who decides red vs green. A run
# is red when the TEST RUN is red (`run-coverage.sh` fails the build or a failing `dotnet test`), not
# when a coverage number moves. Ratchet/diff/scope breaches are reported as ADVISORY and exit 0.
#
# Be clear-eyed about the trade: with `diff` unenforced, nothing mechanical requires a test for new
# code, and the suite stays green precisely BECAUSE untested code keeps it green. Re-arm per check
# via `gate.enforce` in the manifest (`true`, or a list like `[diff]`) or `--enforce` on the CLI.
_ENFORCE_CHECKS = ("ratchet", "diff", "scope")
_ENFORCE_ALL = ("all", "true", "yes", "1")
_ENFORCE_NONE = ("", "none", "false", "no", "0", "off")


def resolve_enforcement(m, cli_value):
    """Set of gate checks allowed to fail CI. CLI wins over the manifest; absent means none."""
    raw = cli_value if cli_value is not None else (m.get("gate") or {}).get("enforce", False)
    if raw is True:
        return set(_ENFORCE_CHECKS)
    if raw is False or raw is None:
        return set()
    items = [x.strip().lower() for x in (raw.split(",") if isinstance(raw, str) else [str(x) for x in raw])]
    items = [x for x in items if x]
    if len(items) == 1 and items[0] in _ENFORCE_ALL:
        return set(_ENFORCE_CHECKS)
    if not items or (len(items) == 1 and items[0] in _ENFORCE_NONE):
        return set()
    unknown = [x for x in items if x not in _ENFORCE_CHECKS]
    if unknown:
        print("coverage-gate: unknown gate.enforce value(s) %s; valid: %s, true, false"
              % (", ".join(repr(u) for u in unknown), ", ".join(_ENFORCE_CHECKS)), file=sys.stderr)
        sys.exit(2)
    return set(items)


# A test project directory segment: exactly "test"/"tests", separator-prefixed (`Foo.Tests`,
# `unit-tests`), or CamelCase-suffixed (`UserServiceTests`). The CamelCase arm is case-SENSITIVE on
# purpose so an ordinary word ending in "test" ("Latest", "Manifest") is not mistaken for a test
# folder.
_TEST_SEG_RE = re.compile(r"^(?:[Tt]ests?|.*[._\- ][Tt]ests?|.*[a-z0-9]Tests?)$")


def is_test_source(path, extra_patterns=()):
    """True when a repo-relative path is TEST code rather than product code.

    Used by the scope-change guard, which exists to catch PRODUCT code landing under an excluded
    path. Test code is never a scope reduction: every repo excludes its own test sources from the
    measured denominator (`**/Tests/**` and friends), so without this a PR that merely ADDS an
    xUnit file trips the guard and demands reviewer sign-off. That trains reviewers to rubber-stamp
    the one check that stops someone reclassifying real logic as untestable, which is worse than
    the false positive itself.

    Detection is by DIRECTORY segment (a .NET test file always lives in a test project), plus any
    repo-specific globs from the manifest's `gate.test_path_patterns` for layouts this misses.
    """
    p = path.replace("\\", "/")
    for pat in extra_patterns or ():
        if match(p, pat):
            return True
    return any(_TEST_SEG_RE.match(seg) for seg in p.split("/")[:-1])


def pct(cov, tot):
    return (100.0 * cov / tot) if tot else 0.0


def _slug(text):
    """GitHub-style heading anchor, so an in-report [jump](#...) link resolves in the HTML."""
    s = re.sub(r"`|\*\*", "", text).strip().lower()
    s = re.sub(r"[^a-z0-9 \-]", "", s)
    return re.sub(r"\s+", "-", s).strip("-")


def _inline(s):
    """Inline markdown -> HTML on already-escaped text. Handles `code`, **bold** and [text](href);
    underscores are left alone so identifiers like cannot_test are not mangled."""
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    # links last, so a [text](#anchor) in the action-required banner becomes clickable
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"<a href='\2'>\1</a>", s)
    # a table cell escaped its pipes for markdown; unescape for display
    return s.replace("\\|", "|")


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_to_html(md):
    """Render the report's markdown subset (h1-3, tables, lists, hr, bold/code, italic notes)."""
    body, i, lines = [], 0, md.split("\n")
    is_sep = re.compile(r"^\s*\|?\s*:?-{2,}.*$")
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|") and i + 1 < len(lines) and is_sep.match(lines[i + 1]):
            def cells(row):
                # Split on UNESCAPED pipes only. Cell text may legitimately contain a pipe (C# such
                # as `a || b`), escaped as \| by the emitter; a naive split("|") would break the row
                # into extra columns and shear the table. _inline() unescapes for display.
                return [c.strip() for c in re.split(r"(?<!\\)\|", row.strip().strip("|"))]
            head = cells(ln); i += 2
            # Tag the two prose-heavy tables so their columns can be sized in CSS. With
            # table-layout:fixed and no widths, a 1200-char explanation column gets the same share
            # as a 3-character severity column, which is unreadable.
            _h0 = (head[0] if head else "").strip().lower()
            tcls = ""
            if _h0 == "sev":
                tcls = " class='t-bugs'"
            elif _h0.startswith("class / method"):
                tcls = " class='t-ct'"
            body.append("<table%s><thead><tr>" % tcls + "".join("<th>%s</th>" % _inline(_esc(c)) for c in head) + "</tr></thead><tbody>")
            while i < len(lines) and lines[i].startswith("|"):
                rc = cells(lines[i])
                # Colour latent-bug rows by their severity letter (first cell "A".."E").
                sev_cls = ""
                if rc and rc[0].strip().upper() in ("A", "B", "C", "D", "E"):
                    sev_cls = " class='sev-%s'" % rc[0].strip().lower()
                body.append("<tr%s>" % sev_cls + "".join("<td>%s</td>" % _inline(_esc(c)) for c in rc) + "</tr>")
                i += 1
            body.append("</tbody></table>")
            continue
        # Headings carry an id so the action-required banner's [jump](#...) link resolves.
        if ln.startswith("### "):
            body.append("<h3 id='%s'>%s</h3>" % (_slug(ln[4:]), _inline(_esc(ln[4:]))))
        elif ln.startswith("## "):
            body.append("<h2 id='%s'>%s</h2>" % (_slug(ln[3:]), _inline(_esc(ln[3:]))))
        elif ln.startswith("# "):
            body.append("<h1 id='%s'>%s</h1>" % (_slug(ln[2:]), _inline(_esc(ln[2:]))))
        elif ln.strip() == "---":
            body.append("<hr/>")
        elif ln.startswith("- ") or ln.startswith("  - "):
            body.append("<li>%s</li>" % _inline(_esc(ln.lstrip().lstrip("- "))))
        elif ln.strip() == "":
            body.append("")
        elif ln.startswith("!!! "):
            # Red warning callout. Used by the action-required banner and the latent-bugs section.
            body.append("<div class='bugwarn'>%s</div>" % _inline(_esc(ln[4:])))
        elif ln.strip().startswith("_") and ln.strip().endswith("_"):
            body.append("<p class='note'>%s</p>" % _inline(_esc(ln.strip()[1:-1])))
        else:
            body.append("<p>%s</p>" % _inline(_esc(ln)))
        i += 1
    css = ("body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:1400px;margin:2rem auto;padding:0 1rem;color:#1b1f23}"
           "h1{border-bottom:2px solid #eaecef;padding-bottom:.3em}h2{border-bottom:1px solid #eaecef;padding-bottom:.2em;margin-top:1.8em}"
           "table{border-collapse:collapse;width:100%;margin:.6em 0;font-size:13px;table-layout:fixed}"
           "th,td{border:1px solid #d0d7de;padding:5px 9px;text-align:left}"
           # Long single tokens (test names like Upsert_Find..._QueryFiltersAreIgnored, method names,
           # file paths) have no wrap opportunity and push tables wider than the page, forcing a
           # horizontal scroll to read any detail. Break inside words instead.
           "th,td,code{overflow-wrap:anywhere;word-break:break-word}"
           "th{background:#f6f8fa}tr:nth-child(even){background:#fafbfc}code{background:#eff1f3;padding:1px 5px;border-radius:4px;font-size:12px}"
           ".note{color:#57606a;font-style:italic}hr{border:0;border-top:1px solid #eaecef;margin:1.5em 0}"
           # Action-required callouts + severity-tinted latent-bug rows.
           ".bugwarn{background:#fff5f5;border:1px solid #f5b5b5;border-left:5px solid #cf222e;"
           "color:#82071e;padding:.7em .9em;margin:.6em 0;border-radius:4px;font-weight:600}"
           "h2:has(+ .bugwarn),h2:has(+ p + .bugwarn){color:#cf222e;border-bottom-color:#f5b5b5}"
           "tr.sev-a td{background:#ffebe9}tr.sev-a td:first-child{background:#cf222e;color:#fff;"
           "font-weight:700;text-align:center}"
           "tr.sev-b td{background:#fff1e5}tr.sev-b td:first-child{background:#bc4c00;color:#fff;"
           "font-weight:700;text-align:center}"
           "tr.sev-c td{background:#fff8c5}tr.sev-c td:first-child{background:#9a6700;color:#fff;"
           "font-weight:700;text-align:center}"
           "tr.sev-d td:first-child,tr.sev-e td:first-child{background:#eaeef2;font-weight:700;"
           "text-align:center}"
           # Column widths for the two prose-heavy tables, so the explanation gets the space and
           # nothing overflows the page. Section 7: Sev | Class/Method | Where | What looks wrong | Pinned by
           ".t-bugs th:nth-child(1),.t-bugs td:nth-child(1){width:3rem}"
           ".t-bugs th:nth-child(2),.t-bugs td:nth-child(2){width:17%}"
           ".t-bugs th:nth-child(3),.t-bugs td:nth-child(3){width:9%}"
           ".t-bugs th:nth-child(5),.t-bugs td:nth-child(5){width:17%}"
           # Sections 6a/6b: Class/Method | Where | Why not unit-testable | Category | Mitigation
           ".t-ct th:nth-child(1),.t-ct td:nth-child(1){width:16%}"
           ".t-ct th:nth-child(2),.t-ct td:nth-child(2){width:6%}"
           ".t-ct th:nth-child(4),.t-ct td:nth-child(4){width:11%}"
           ".t-ct th:nth-child(5),.t-ct td:nth-child(5){width:22%}")
    return "<!doctype html><html><head><meta charset='utf-8'><title>Unit Test Report</title><style>%s</style></head><body>\n%s\n</body></html>\n" % (css, "\n".join(body))


_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/~^@-]*$")


def _safe_ref(ref):
    """Allowlist a git ref/sha. `--base` is spliced into `git diff <base>...HEAD`; a value
    starting with `-` (or carrying odd characters) would be read as a git *option* rather than
    a revision — argument injection (CWE-78). Anything that isn't a plain ref is rejected here,
    before it can reach git()."""
    if ref is None:
        return None
    if not _REF_RE.match(ref):
        print("coverage-gate: refusing suspicious --base ref %r" % ref, file=sys.stderr)
        sys.exit(2)
    return ref


def _within_cwd(path):
    """Resolve `path` and confine it to the working tree, returning the real path when it is the
    cwd or below it and None otherwise — blocks `../`-style traversal in --test-results-dir
    (CWE-22). Coverage always runs from the repo root with a relative results dir, so a legitimate
    value is never rejected."""
    if not path:
        return None
    root = os.path.realpath(os.getcwd())
    full = os.path.realpath(path)
    if full == root or full.startswith(root + os.sep):
        return full
    return None


_GIT_FLAGS_OK = {"--unified=0", "--diff-filter=ACMR", "--diff-filter=A",
                 "--name-only", "--short", "--abbrev-ref", "--"}
_GIT_ARG_OK = re.compile(r"^[A-Za-z0-9._/:~^@*-]+$")


def git(arglist):
    # Defense AT THE SINK (CWE-78 argument/command injection): every argument is validated here,
    # at the subprocess call itself, against an explicit allowlist — any "-"-prefixed token must
    # be a known git flag (so a value like "--upload-pack=..." can never be parsed as an option),
    # and every other token must match a safe character set. The process is launched list-form,
    # never shell=True, so there is also no shell for metacharacters to reach. (Sink-local on
    # purpose: scanners' taint analysis does not trace sanitizers in separate helper functions.)
    for a in arglist:
        if not isinstance(a, str):
            print("coverage-gate: refusing non-string git argument", file=sys.stderr)
            sys.exit(2)
        if a.startswith("-"):
            if a not in _GIT_FLAGS_OK:
                print("coverage-gate: refusing unknown git flag %r" % a, file=sys.stderr)
                sys.exit(2)
        elif not _GIT_ARG_OK.match(a):
            print("coverage-gate: refusing unsafe git argument %r" % a, file=sys.stderr)
            sys.exit(2)
    return subprocess.run(["git"] + list(arglist), capture_output=True, text=True)


def _diff(base, extra):
    r = git(["diff"] + ["%s...HEAD" % base] + extra)
    if r.returncode != 0:
        r = git(["diff"] + [base] + extra)
    return r if r.returncode == 0 else None


def changed_lines(base):
    r = _diff(base, ["--unified=0", "--diff-filter=ACMR", "--", "*.cs"])
    if r is None:
        return None
    out, cur = {}, None
    hunk = re.compile(r"^@@ .*\+(\d+)(?:,(\d+))? @@")
    for line in r.stdout.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:].replace("\\", "/"); out.setdefault(cur, set())
        elif line.startswith("@@") and cur is not None:
            m = hunk.match(line)
            if m:
                start, count = int(m.group(1)), int(m.group(2) or "1")
                for n in range(start, start + count):
                    out[cur].add(n)
    return {k: v for k, v in out.items() if v}


def added_files(base):
    r = _diff(base, ["--name-only", "--diff-filter=A", "--", "*.cs"])
    if r is None:
        return []
    return [l.replace("\\", "/") for l in r.stdout.splitlines() if l.strip()]


def base_manifest(base, manifest_path):
    r = git(["show", "%s:%s" % (base, manifest_path.replace("\\", "/"))])
    if r.returncode != 0:
        return None
    try:
        return yaml.safe_load(r.stdout)
    except Exception:
        return None


def find_key(files, gitpath):
    gp = gitpath.replace("\\", "/")
    if gp in files:
        return gp
    best = None
    for fn in files:
        if fn.endswith(gp) or gp.endswith(fn):
            if best is None or len(fn) > len(best):
                best = fn
    return best


def parse_trx(results_dir):
    """Aggregate VSTest .trx counters across all trx files. Returns dict or None."""
    if not results_dir:
        return None
    # Confine to the working tree AT THE SINK (CWE-22 path traversal): resolve the path and
    # require it to be the cwd or strictly below it (a realpath + startswith check) BEFORE it is
    # globbed, so a "../"-style value cannot escape the repo. Coverage always runs from the repo
    # root with a relative results dir, so a legitimate value is never rejected. (Sink-local on
    # purpose: scanners do not trace the containment when it lives in a separate helper.)
    root = os.path.realpath(os.getcwd())
    full = os.path.realpath(results_dir)
    if not (full == root or full.startswith(root + os.sep)) or not os.path.isdir(full):
        return None
    trx = glob.glob(os.path.join(full, "**", "*.trx"), recursive=True)
    if not trx:
        return None
    agg = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    dur = 0.0
    for path in trx:
        try:
            root = ET.parse(path).getroot()
        except Exception:
            continue
        for el in root.iter():
            ln = _localname(el.tag)
            if ln == "Counters":
                def gi(k):
                    try: return int(el.get(k, "0"))
                    except ValueError: return 0
                agg["total"] += gi("total")
                agg["passed"] += gi("passed")
                agg["failed"] += gi("failed") + gi("error") + gi("timeout") + gi("aborted")
                agg["skipped"] += gi("notExecuted") + gi("inconclusive") + gi("disconnected")
            elif ln == "Times":
                s, f = el.get("start"), el.get("finish")
                if s and f:
                    try:
                        ds = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
                        df = datetime.datetime.fromisoformat(f.replace("Z", "+00:00"))
                        dur += max(0.0, (df - ds).total_seconds())
                    except Exception:
                        pass
    agg["duration_s"] = dur
    return agg


COVERED_BY = {
    "integration-scope": "integration tests",
    "e2e-scope": "E2E / smoke",
    "dto-no-logic": "— (no behavior)",
    "mapper-config": "— (declarative mapping config)",
    "generated": "— (generated)",
    "non-product": "— (not shipped)",
    "nondeterministic": "— (frozen)",
}
ACTION = {
    "nondeterministic": "Frozen; needs an injected seam (clock/random/IO) to become testable",
    "integration-scope": "Cover via integration test, or extract a pure seam",
    "requires-source-change": "Needs a source change (inject a seam / add InternalsVisibleTo) to become testable",
    "unreachable": "None — structurally unreachable (compiler-lowered or dead branch); not coverable",
    "unreachable-branch": "None — compiler-lowered/unreachable branch; excluded from C1 by design",
    "framework-mismatch": "None via unit test — target framework differs from the test project; cover elsewhere or retarget",
    "dead-code": "Remove the dead code or wire up its caller; not a unit-test gap",
    "method-absent": "Stale entry — the method no longer exists; remove it from the manifest",
}

# Agents drift in vocabulary across parallel chunks (framework_mismatch vs framework-incompatible,
# method_absent vs method-absent, requires-seam vs requires-source-change), so the report
# normalizes to a fixed set before grouping — otherwise one real concept splits into several
# noisy rows and the "one seam unlocks N" signal is lost.
_CATEGORY_ALIASES = {
    "framework_mismatch": "framework-mismatch", "framework-incompatible": "framework-mismatch",
    "method_absent": "method-absent",
    "nondeterministic_dead_code": "dead-code", "dead_code": "dead-code",
    "requires_source_change": "requires-source-change", "requires_seam": "requires-source-change",
    "requires-seam": "requires-source-change", "bynder-internal-no-internalsvisibleto": "requires-source-change",
    "unreachable_branch": "unreachable-branch",
}
def canonical_category(cat):
    c = (cat or "").strip().lower()
    return _CATEGORY_ALIASES.get(c, c)

# Two natures of a Not-Testable entry — decides whether "should trend to zero" applies:
#   debt       — fixable by a source change (inject a seam, add InternalsVisibleTo, extract a pure
#                method). SHOULD trend to zero as the code is refactored.
#   structural — not debt and will not move: a compiler-lowered/unreachable branch, dead (uncalled)
#                code, a target-framework mismatch, generated code. Framing these as "should trend
#                to zero" is misleading — they are permanent, honest exclusions.
_STRUCTURAL_CATEGORIES = {
    "unreachable", "unreachable-branch", "framework-mismatch", "dead-code", "method-absent", "generated",
}
def category_nature(cat):
    return "structural" if canonical_category(cat) in _STRUCTURAL_CATEGORIES else "debt"


# CANNOT-TEST.md generation.
# The standalone cannot-test report groups every manifest `cannot_test` entry by its BLOCKING
# CONSTRUCT (finer-grained than the coarse manifest `category`), so a reader sees "these 6 are all
# blocked by the same rowversion insert" rather than a flat list. The bucket for an entry is the
# first whose keywords appear in its reason/category/mitigation text; unmatched debt entries fall
# back to a group keyed by their canonical category. Structural-nature entries (dead, unreachable,
# generated, framework-mismatch) are reported separately, since they are permanent, not seam-fixable.
_CT_BUCKETS = [
    ("Unset store-generated rowversion (`Timestamp`) on insert",
     ["rowversion", "timestamp"]),
    ("`ExecuteUpdateAsync` / `ExecuteDeleteAsync` (not supported by EF in-memory)",
     ["executeupdate", "executedelete", "execute update", "execute delete"]),
    ("linq2db / EFCore.BulkExtensions `Batch*` (relational-only)",
     ["batchdelete", "batchupdate", "batch*", "linq2db", "bulkextensions", "bulk update", "bulk delete"]),
    ("Untranslatable LINQ on the in-memory provider",
     ["untranslatable", "cannot translate", "in-memory provider cannot", "provider-specific linq", "groupby"]),
    ("Real DB transaction + mid-transaction failure",
     ["transaction", "begintransaction"]),
    ("Native crypto (libsodium / scrypt) and nondeterministic nonces",
     ["sodium", "libsodium", "scrypt", "nonce", "crypto", "hmac", "aes ciphertext"]),
    ("Concrete external SDK client injected by concrete type",
     ["cognito", "amazon", "sdk client", "concrete type", "injected by type", "no interface"]),
    ("Static cache factory / no injection seam (Redis)",
     ["redis", "cachefactory", "redlock"]),
    ("Real HTTP / S3 boundaries",
     ["httpclient", "ihttpclient", "sendasync", "getbytearray", "s3", "is3disk", "real http"]),
    ("Inline-new DbContext / raw SQL / type-init IO",
     ["fromsqlraw", "executesqlraw", "raw sql", "inline-new", "inline new", "new context", "readalltext"]),
    ("DnsClient A-record construction",
     ["dnsclient", "arecord", "a-record", "dns lookup", "dns positive"]),
    ("Nondeterministic clock / id (no seam)",
     ["datetime.utcnow", "datetime.now", "guid.newguid", "stopwatch", "random", "clock", "wall clock"]),
]


def _ct_bucket(ct):
    hay = " ".join([ct.get("reason", "") or "", ct.get("category", "") or "",
                    ct.get("mitigation", "") or ""]).lower()
    for heading, keys in _CT_BUCKETS:
        if any(k in hay for k in keys):
            return heading
    return None  # unmatched: grouped by canonical category by the caller


def render_cannot_test_md(cannot_test, repo, report_date, headline=None):
    """Build the dedicated CANNOT-TEST.md from the manifest cannot_test entries. Cites target,
    reason, and mitigation from the manifest, and lines only where the manifest supplies them (no
    invented line numbers). Returns the markdown string."""
    L = []
    L.append("# Cannot-Test Report: %s" % repo)
    L.append("")
    gen = "Generated %s." % report_date
    if headline:
        gen += " Companion to `REPORT.md` (%s)." % headline
    L.append(gen)
    L.append("")
    L.append("This lists every target-layer method or branch that is **genuinely not unit-testable** as "
             "the source stands, with the source citation from the manifest, the blocking construct, and "
             "the source change that would unlock it. Every row is a `cannot_test` entry in "
             "`coverage-manifest.yml`; none is closable by writing another test without a production-source "
             "change.")
    L.append("")
    L.append("## Why these cannot be unit-tested (categories)")
    L.append("")
    L.append("The EF in-memory provider is the seam for injected DbContexts, but it cannot execute: "
             "store-generated rowversion inserts, `ExecuteUpdate/DeleteAsync`, linq2db / EFCore.BulkExtensions "
             "`Batch*`, raw SQL, real transactions, or some LINQ shapes. Native crypto, concrete external SDK "
             "clients injected by concrete type, static cache factories, real HTTP/S3, and direct clock/nonce "
             "also have no seam in characterization mode (no source changes allowed). Each item below cites "
             "which one applies.")
    L.append("")

    if not cannot_test:
        L.append("---")
        L.append("")
        L.append("_No `cannot_test` entries recorded in the manifest._")
        L.append("")
        return "\n".join(L)

    debt = [ct for ct in cannot_test if category_nature(ct.get("category")) == "debt"]
    structural = [ct for ct in cannot_test if category_nature(ct.get("category")) == "structural"]

    # Assign debt entries to construct buckets; keep bucket order, then fallback groups.
    grouped = {}
    for ct in debt:
        grouped.setdefault(_ct_bucket(ct), []).append(ct)
    ordered_headings = [h for h, _ in _CT_BUCKETS if grouped.get(h)]
    # Unmatched (None): one group per canonical category, appended after the known buckets.
    for ct in grouped.get(None, []):
        h = "Other no-seam boundary: `%s`" % (canonical_category(ct.get("category")) or "uncategorized")
        grouped.setdefault(h, []).append(ct)
    known = [x for x, _ in _CT_BUCKETS]
    fallback_headings = sorted(h for h in grouped if h is not None and h not in known)

    def _table(rows):
        L.append("| Target | Where | Blocking construct | Unlock |")
        L.append("|--------|-------|--------------------|--------|")
        for ct in rows:
            where = ct.get("lines") or "file-level"
            cat = canonical_category(ct.get("category"))
            unlock = (ct.get("mitigation") or ACTION.get(cat, "Review")).replace("\n", " ")
            reason = (ct.get("reason", "") or "").replace("\n", " ")
            L.append("| `%s` | %s | %s | %s |" % (ct.get("target", "?"), where, reason, unlock))
        L.append("")

    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    idx = 0
    L.append("---")
    L.append("")
    for h in ordered_headings + fallback_headings:
        prefix = letters[idx] if idx < len(letters) else str(idx + 1)
        L.append("## %s. %s" % (prefix, h))
        L.append("")
        _table(grouped[h])
        idx += 1

    # Structural / dead code: derived rows from the manifest, PLUS a manual-append placeholder,
    # since branches that are neither testable nor cannot_test cannot be reliably derived here.
    L.append("---")
    L.append("")
    L.append("## Structurally-dead / unreachable defensive code (NOT cannot_test, but permanently uncovered)")
    L.append("")
    L.append("Defensive guards or branches that cannot execute given the current callers/contracts. Not "
             "testable and not seam-fixable; they are dead-branch coverage loss, candidates for deletion.")
    L.append("")
    if structural:
        _table(structural)
    else:
        L.append("_None derivable from the manifest. Append manually any uncovered target branch that is "
                 "structurally unreachable (compiler-lowered, dead, or contract-guaranteed) after reviewing "
                 "the HTML drill-down._")
        L.append("")
    L.append("<!-- MANUAL-APPEND: latent bugs frozen by characterization, and dead branches found in the "
             "drill-down but not yet in the manifest, go below. The generator does not invent these. -->")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cobertura")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--print-file-filter", action="store_true",
                    help="resolve the manifest's ReportGenerator filefilter, print it, and exit. "
                         "Lets report.sh and CI share one definition instead of retyping it.")
    ap.add_argument("--repo-root", default=".",
                    help="repo root used to test whether a declared vendored_paths entry exists")
    ap.add_argument("--print-test-project-exclude", action="store_true",
                    help="print `scope.test_project_exclude` (an extended-regex of csproj paths that "
                         "run-coverage.sh drops from discovery) and exit. Keeps the value in ONE place "
                         "so CI and a local run cannot disagree.")
    ap.add_argument("--print-kit-version", action="store_true")
    ap.add_argument("--print-kit-drift", action="store_true",
                    help="print `<state> <manifest kit_version> <kit semver>` (state: current|behind|"
                         "unstamped|ahead) and exit. Manifest-only, so any entry point can check "
                         "whether this repo is on the current kit without running coverage.")
    ap.add_argument("--summary", help="append the Markdown report to this file (e.g. $GITHUB_STEP_SUMMARY)")
    ap.add_argument("--repo-filter", help="only files whose path contains this substring")
    ap.add_argument("--needs-attention-top", type=int, default=15)
    ap.add_argument("--base", help="base git ref to diff against; enables diff-coverage + scope-change (PR mode).")
    ap.add_argument("--allow-scope-change", action="store_true")
    ap.add_argument("--enforce",
                    help="comma-separated checks allowed to FAIL the run: ratchet, diff, scope "
                         "(also `all` / `none`). Overrides the manifest's `gate.enforce`. Default is "
                         "none: every breach is reported as advisory and the exit code stays 0, so "
                         "only a failing test run turns CI red.")
    ap.add_argument("--test-results-dir", help="dir containing .trx files for the Test Results section")
    ap.add_argument("--repo-name", help="repo name for the report header")
    ap.add_argument("--html", help="also write the report as a self-contained HTML file at this path")
    ap.add_argument("--cannot-test-out", help="also write a dedicated, cited CANNOT-TEST.md at this path (derived from the manifest cannot_test entries)")
    ap.add_argument("--tooling", default="Microsoft Code Coverage (dotnet-coverage) + ReportGenerator + xUnit")
    args = ap.parse_args()
    args.base = _safe_ref(args.base)

    if args.print_kit_version:
        print(KIT_VERSION)
        sys.exit(0)

    with open(args.manifest, encoding="utf-8") as fh:
        m = yaml.safe_load(fh)

    # Query modes resolve from the manifest alone, before any coverage is needed.
    if args.print_kit_drift:
        _stamped, _state = kit_drift(m)
        print("%s %s %s" % (_state, _stamped or "-", KIT_SEMVER))
        sys.exit(0)

    if args.print_file_filter:
        print(resolve_file_filter(m, args.repo_filter, args.repo_root))
        sys.exit(0)

    if args.print_test_project_exclude:
        print(((m.get("scope") or {}).get("test_project_exclude") or "").strip())
        sys.exit(0)

    if not args.cobertura:
        ap.error("--cobertura is required unless --print-file-filter is given")

    exclusions = (m.get("exclusions") or []) + vendored_exclusions(m)
    category_map = m.get("category_map") or {}
    gate = m.get("gate") or {}
    baseline = (m.get("baseline") or {}).get("recorded_overall") or {}
    floor_c0, floor_c1 = baseline.get("c0"), baseline.get("c1")
    baseline_scope_lines = (m.get("baseline") or {}).get("scope_lines")
    target = m.get("target") or {}
    target_c0, target_c1 = target.get("c0"), target.get("c1")
    cannot_test = m.get("cannot_test") or []

    files, methods = parse_cobertura(args.cobertura)
    if args.repo_filter:
        files = {f: d for f, d in files.items() if args.repo_filter in f}
        methods = [mm for mm in methods if args.repo_filter in mm["file"]]

    file_methods = {}
    for mm in methods:
        file_methods.setdefault(mm["file"], []).append(mm)

    def is_excluded(fn):
        return any(match(fn, ex["pattern"]) for ex in exclusions)

    cannot_test_names = {(ct.get("target", "").split(".")[-1].split("(")[0]).strip()
                         for ct in cannot_test if ct.get("target")}

    def carveout_lineset(fn):
        """Line-number -> hit for lines inside this file's documented carve-out methods.
        Carve-out method names come from the matching exclusion's `reason` ("CARVE-OUT: a, b, …");
        tokens are intersected with the file's REAL method names, so prose words (both, overloads,
        verify, …) and signatures are filtered out. Names listed in `cannot_test` are removed — a
        reason may NAME an untestable method only to explain why it is NOT a carve-out, and
        diff-coverage must not demand coverage of something declared untestable. Empty when the
        file has no carve-out."""
        tokens = set()
        for ex in exclusions:
            if match(fn, ex["pattern"]):
                co = ex.get("carve_outs")
                if isinstance(co, list) and co:
                    # Structured form: one bare method name per entry. Preferred over prose because
                    # each carve-out is tied to a specific (per-file) exclusion entry, so it cannot
                    # leak across files the way a folder-glob CARVE-OUT: list can.
                    for item in co:
                        name = item.get("method", "") if isinstance(item, dict) else str(item)
                        name = name.split("(")[0].split(".")[-1].strip()
                        if name:
                            tokens.add(name)
                else:
                    r = ex.get("reason", "") or ""
                    idx = r.find("CARVE-OUT:")
                    if idx >= 0:
                        tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", r[idx + len("CARVE-OUT:"):]))
                break
        tokens -= cannot_test_names
        if not tokens:
            return {}
        out = {}
        for mm in file_methods.get(fn, []):
            if mm["bare"] in tokens:
                out.update(mm["lines"])
        return out

    def bucket_of(fn):
        for ex in exclusions:
            if match(fn, ex["pattern"]):
                return "excl: %s" % ex["category"]
        for name, globs in category_map.items():
            if any(match(fn, g) for g in (globs or [])):
                return name
        return "uncategorized"

    def testable(fn, d):
        """(testable_lines, testable_branches, covered_lines, covered_branches) — the UNIT-SCOPE
        slice of a file. For a target (non-excluded) file that is the whole file; for an excluded
        file it is only its documented carve-out methods (0 if none). 'Raw' (d['tot']/d['btot'])
        is the whole instrumented file regardless — raw shows size, testable shows what we own."""
        if not is_excluded(fn):
            return d["tot"], d["btot"], d["cov"], d["bcov"]
        co = carveout_lineset(fn)
        lm = d["linemap"]
        tl = tb = tlc = tbc = 0
        for no in co:
            e = lm.get(no)
            if e is None:
                continue
            tl += 1
            if e["hit"]:
                tlc += 1
            tb += e["btot"]; tbc += e["bcov"]
        return tl, tb, tlc, tbc

    # cat -> [cov, tot, bcov, btot, files, mcov, mtot]
    cat_totals = {}
    inscope = [0, 0, 0, 0, 0, 0]   # cov,tot,bcov,btot,mcov,mtot
    raw = [0, 0, 0, 0, 0, 0]
    for fn, d in files.items():
        cat = bucket_of(fn)
        # Adjusted counts the unit-testable slice of EVERY file: the whole file for a target
        # (non-excluded), and the carve-out methods for an excluded file. This is what puts the
        # carve-out slices of god-classes into the headline instead of leaving them only in
        # diff-coverage. testable() returns (line_tot, branch_tot, line_cov, branch_cov) for that
        # slice (zeros when an excluded file declares no carve-out).
        tl, tb, tlc, tbc = testable(fn, d)
        inscope[0] += tlc; inscope[1] += tl
        inscope[2] += tbc; inscope[3] += tb
        if not cat.startswith("excl:"):
            inscope[4] += d["mcov"]; inscope[5] += d["mtot"]
        else:
            co = carveout_lineset(fn)
            if co:
                lm = d["linemap"]
                for mm in file_methods.get(fn, []):
                    inter = set(mm["lines"]) & set(co)
                    if inter:
                        inscope[5] += 1
                        if all((lm.get(no) or {}).get("hit") for no in inter):
                            inscope[4] += 1
        t = cat_totals.setdefault(cat, [0, 0, 0, 0, 0, 0, 0])
        t[0] += d["cov"]; t[1] += d["tot"]; t[2] += d["bcov"]; t[3] += d["btot"]
        t[4] += 1; t[5] += d["mcov"]; t[6] += d["mtot"]
        raw[0] += d["cov"]; raw[1] += d["tot"]; raw[2] += d["bcov"]; raw[3] += d["btot"]
        raw[4] += d["mcov"]; raw[5] += d["mtot"]

    c0, c1 = pct(inscope[0], inscope[1]), pct(inscope[2], inscope[3])
    cm = pct(inscope[4], inscope[5])

    def short(fn):
        return "/".join(fn.split("/")[-2:])

    # ---- Scope-size sanity ----
    # A filefilter mistake does not look like a filter mistake, it looks like a
    # coverage collapse: the denominator grows, the percentage craters, and the
    # ratchet fails as though tests were deleted. Comparing the in-scope line
    # total against the size recorded at baseline separates "we regressed" from
    # "we are measuring different code", which is a much cheaper thing to be
    # told than to work out from a failing gate.
    scope_lines = inscope[1]
    scope_warning = None
    if baseline_scope_lines:
        ratio = scope_lines / float(baseline_scope_lines)
        if ratio > 1.5 or ratio < 0.67:
            scope_warning = (
                "in-scope size is %.1fx the baseline (%s lines now vs %s recorded). "
                "Check the filefilter before trusting this number: an unexcluded vendored or "
                "sibling-repo directory inflates the denominator and looks like a regression."
                % (ratio, "{:,}".format(scope_lines), "{:,}".format(int(baseline_scope_lines)))
            )

    # ---- Ratchet ----
    ratchet_on = gate.get("ratchet", True)
    ratchet_fail = False
    gate_lines = []
    if scope_warning:
        gate_lines.append("- **Scope size**: ⚠️ %s" % scope_warning)
    elif not baseline_scope_lines:
        gate_lines.append(
            "- **Scope size**: %s in-scope lines (not compared: stamp `baseline.scope_lines` "
            "in the manifest to enable the filter sanity check)." % "{:,}".format(scope_lines)
        )
    if ratchet_on and floor_c0 is not None and floor_c1 is not None:
        c0f = round(c0, 1) < float(floor_c0)
        c1f = round(c1, 1) < float(floor_c1)
        ratchet_fail = c0f or c1f
        gate_lines.append("- **Ratchet** (Adjusted must not drop below floor C0 %.1f%% / C1 %.1f%%): %s"
                          % (float(floor_c0), float(floor_c1), "❌ FAIL" if ratchet_fail else "✅ PASS"))
        if c0f:
            gate_lines.append("  - C0 %.1f%% < floor %.1f%%" % (c0, float(floor_c0)))
        if c1f:
            gate_lines.append("  - C1 %.1f%% < floor %.1f%%" % (c1, float(floor_c1)))
    else:
        gate_lines.append("- **Ratchet**: not enforced (no recorded floor or ratchet disabled).")

    # ---- Diff coverage + scope-change guard (PR mode: --base) ----
    diff_fail = scope_fail = False
    if args.base:
        dmin0 = gate.get("diff_coverage_min_c0")
        dmin1 = gate.get("diff_coverage_min_c1")
        cl = changed_lines(args.base)
        if cl is None:
            gate_lines.append("- **Diff coverage**: base `%s` unavailable (fetch full history)." % args.base)
        else:
            dcov = dtot = dbcov = dbtot = 0
            uncovered_changed = []
            for gp, lns in cl.items():
                key = find_key(files, gp)
                if key is None:
                    continue
                lm = files[key]["linemap"]
                if is_excluded(key):
                    # Excluded file: only the changed lines INSIDE a documented carve-out method
                    # are in scope — code outside the carve-out is genuinely integration-scope.
                    co = carveout_lineset(key)
                    target = [n for n in lns if n in co]
                    if not target:
                        continue
                else:
                    target = list(lns)  # in-scope file: every changed executable line
                miss = []
                for n in target:
                    e = lm.get(n)
                    if e is None:
                        continue
                    dtot += 1
                    if e["hit"]:
                        dcov += 1
                    else:
                        miss.append(n)
                    if e["branch"]:
                        dbcov += e["bcov"]; dbtot += e["btot"]
                if miss:
                    uncovered_changed.append((gp, sorted(miss)))
            dc0, dc1 = pct(dcov, dtot), pct(dbcov, dbtot)
            if dtot == 0:
                gate_lines.append("- **Diff coverage**: no changed in-scope executable lines — N/A ✅")
            else:
                parts = []
                if dmin0 is not None:
                    f0 = round(dc0, 1) < float(dmin0); diff_fail = diff_fail or f0
                    parts.append("C0 %.1f%% (need %.0f%%) %s" % (dc0, float(dmin0), "❌" if f0 else "✅"))
                if dmin1 is not None and dbtot > 0:
                    f1 = round(dc1, 1) < float(dmin1); diff_fail = diff_fail or f1
                    parts.append("C1 %.1f%% (need %.0f%%) %s" % (dc1, float(dmin1), "❌" if f1 else "✅"))
                gate_lines.append("- **Diff coverage** (%d changed in-scope lines, incl. carve-out lines in excluded files): %s" % (dtot, " · ".join(parts)))
                for gp, mlns in uncovered_changed[:10]:
                    rng = ",".join(str(x) for x in mlns[:12]) + (" …" if len(mlns) > 12 else "")
                    gate_lines.append("  - uncovered: `%s` : %s" % (short(gp), rng))
        bm = base_manifest(args.base, args.manifest)
        if bm is not None:
            # Floor-tamper guard: a PR must never LOWER baseline.recorded_overall (the ratchet
            # floor) — that would let someone weaken the bar in the same change that adds untested
            # code. Removing the floor counts as lowering. Raising it is always allowed.
            base_bl = (bm.get("baseline") or {}).get("recorded_overall") or {}
            lowered = []
            for axis, cur, base_v in (("C0", floor_c0, base_bl.get("c0")), ("C1", floor_c1, base_bl.get("c1"))):
                if base_v is None:
                    continue
                if cur is None or float(cur) < float(base_v) - 0.05:
                    lowered.append("%s floor %s < base %.1f%%" % (axis, ("%.1f%%" % float(cur)) if cur is not None else "removed", float(base_v)))
            if lowered:
                scope_fail = scope_fail or not args.allow_scope_change
                gate_lines.append("- **Floor lowered** %s"
                                  % ("(allowed) ✅" if args.allow_scope_change else "— needs reviewer sign-off ❌"))
                for l in lowered:
                    gate_lines.append("  - %s" % l)
            # Compare like with like: `exclusions` here carries the synthetic vendored entries, so
            # the base side must be expanded the same way. Otherwise every PR reports
            # "exclusions grew by <number of vendored paths>" and demands the sign-off label for a
            # change nobody made.
            grew_excl = len(exclusions) - len((bm.get("exclusions") or []) + vendored_exclusions(bm))
            grew_ct = len(cannot_test) - len(bm.get("cannot_test") or [])
            new_excluded = []
            added_tests = 0
            test_globs = gate.get("test_path_patterns") or []
            for gp in added_files(args.base):
                # Adding a test is the OPPOSITE of a scope reduction, but a new test file always
                # lands under the repo's own test exclusion. Count it and move on.
                if is_test_source(gp, test_globs):
                    added_tests += 1
                    continue
                for ex in exclusions:
                    if match(gp, ex["pattern"]):
                        new_excluded.append((gp, ex["category"])); break
            tests_note = ("  (%d added test file%s ignored: test code is not product scope)"
                          % (added_tests, "" if added_tests == 1 else "s")) if added_tests else ""
            if grew_excl > 0 or grew_ct > 0 or new_excluded:
                scope_fail = not args.allow_scope_change
                gate_lines.append("- **Scope change** %s"
                                  % ("(allowed) ✅" if args.allow_scope_change else "— needs reviewer sign-off ❌"))
                if grew_excl > 0:
                    gate_lines.append("  - `exclusions` grew by %d vs base" % grew_excl)
                if grew_ct > 0:
                    gate_lines.append("  - `cannot_test` grew by %d vs base" % grew_ct)
                for gp, cat in new_excluded[:10]:
                    gate_lines.append("  - new file under excluded path (`%s`): `%s`" % (cat, short(gp)))
                if tests_note:
                    gate_lines.append("  - %s" % tests_note.strip())
            else:
                gate_lines.append("- **Scope change**: none ✅%s" % tests_note)

    # Enforcement is decided here, AFTER every check has run: the measurement is unconditional, only
    # the exit code is configurable. A breach in a check that is not enforced is reported as advisory.
    enforce = resolve_enforcement(m, args.enforce)
    breaches = [n for n, f in (("ratchet", ratchet_fail), ("diff", diff_fail), ("scope", scope_fail)) if f]
    enforced_breaches = [n for n in breaches if n in enforce]
    advisory_breaches = [n for n in breaches if n not in enforce]
    gate_failed = bool(enforced_breaches)
    gate_active = (ratchet_on and floor_c0 is not None) or bool(args.base)

    # ---- header facts (tool/system sourced, not model) ----
    def g1(a):
        r = git(a); return r.stdout.strip() if r.returncode == 0 else "—"
    sha = g1(["rev-parse", "--short", "HEAD"])
    branch = g1(["rev-parse", "--abbrev-ref", "HEAD"])
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    repo = args.repo_name or (args.repo_filter or os.path.basename(os.getcwd()))
    tr = parse_trx(args.test_results_dir)

    out = []
    out.append("# Unit Test Report — %s\n" % repo)
    out.append("**Commit:** %s  **Branch:** %s  **Date:** %s  " % (sha, branch, now))
    out.append("**Tooling:** %s  " % args.tooling)
    out.append("**Adjusted coverage:** C0 %.1f%% / C1 %.1f%%  " % (c0, c1))
    # State the enforcement mode in the artifact people actually read. A report whose numbers look
    # like a gate, but whose checks cannot fail anything, must say so on its face.
    out.append("**Enforced checks:** %s\n" % (
        ", ".join(sorted(enforce)) if enforce
        else "none (report only: coverage breaches do not fail the run; a failing test run still does)"))

    # Red-suite banner: coverage measured with failing tests is unreliable, and a baseline must
    # never be recorded off it (see the generate-tests promotion gate). Surface it loudly at the top
    # — a partially-red run silently locking a baseline is exactly how a misleading floor gets set.
    if tr and tr.get("failed"):
        out.append("> ⚠️ **%d test(s) FAILING in this run.** Coverage measured off a red suite is "
                   "unreliable — do NOT record or trust a baseline until the suite is green. Fix the "
                   "failures, then re-measure.\n" % tr["failed"])

    # Kit-drift note. Emitted on EVERY run, so a repo left behind on an older kit says so by itself
    # rather than waiting for someone to think of asking. Placed under the header and above the
    # ACTION REQUIRED banner: visible, but never competing with a live-defect warning.
    _drift = drift_note(m)
    if _drift:
        out.append(_drift + "\n")

    # ---- ACTION REQUIRED banner ----
    # The frozen-bug backlog is the first thing a reader sees, rather than being buried under seven
    # sections. Without this, section 7 is below the fold in a long report and the "green suite,
    # live bugs" caveat reaches nobody. Links to section 7.
    _latent_top = m.get("latent_bugs") or []
    if _latent_top:
        _sev_counts = {}
        for _b in _latent_top:
            _s = (_b.get("severity") or "D").strip().upper()[:1]
            _sev_counts[_s] = _sev_counts.get(_s, 0) + 1
        _act = sum(v for k, v in _sev_counts.items() if k in ("A", "B", "C"))
        _parts = ", ".join("%d %s" % (_sev_counts[k], k) for k in ("A", "B", "C")
                           if _sev_counts.get(k))
        out.append("!!! ACTION REQUIRED: %d latent product bugs are FROZEN, NOT FIXED (%d need "
                   "resolving: %s). The suite is GREEN because the tests pin what the code does "
                   "TODAY, wrong behaviour included, so green means \"behaviour has not drifted\", "
                   "NOT \"behaviour is correct\". "
                   "[Jump to section 7 for the list](#%s)"
                   % (len(_latent_top), _act, _parts, _slug(LATENT_HEADING)))
        out.append("")

    # 1. Test Results
    out.append("## 1. Test Results")
    out.append("| Total | Passed | Failed | Skipped | Flaky | Duration |")
    out.append("|-------|--------|--------|---------|-------|----------|")
    if tr:
        dur = "%.1fs" % tr["duration_s"] if tr["duration_s"] else "—"
        out.append("| %d | %d | %d | %d | — | %s |" % (tr["total"], tr["passed"], tr["failed"], tr["skipped"], dur))
        out.append("\n_Flaky = `—`: not measurable from a single non-retry run._")
    else:
        out.append("| — | — | — | — | — | — |")
        out.append("\n_Test results not captured this run — run via `report.sh` (emits `.trx`) to populate._")

    # 2. Coverage Summary
    out.append("\n## 2. Coverage Summary")
    out.append("|              | Raw (all code) | Adjusted (testable) | Baseline | Δ |")
    out.append("|--------------|----------------|---------------------|----------|---|")
    def d_str(adj, floor):
        if floor is None:
            return "—"
        v = adj - float(floor)
        if abs(v) < 0.05:
            v = 0.0  # avoid "-0.0 pp" when Adjusted sits exactly on the floor
        return "%+.1f pp" % v
    fc0 = ("%.1f%%" % float(floor_c0)) if floor_c0 is not None else "—"
    fc1 = ("%.1f%%" % float(floor_c1)) if floor_c1 is not None else "—"
    out.append("| C0 (line)    | %.1f%% | %.1f%% | %s | %s |" % (pct(raw[0], raw[1]), c0, fc0, d_str(c0, floor_c0)))
    out.append("| C1 (branch)  | %.1f%% | %.1f%% | %s | %s |" % (pct(raw[2], raw[3]), c1, fc1, d_str(c1, floor_c1)))
    out.append("| Method       | %.1f%% | %.1f%% | — | — |" % (pct(raw[4], raw[5]), cm))
    out.append("")
    out.append("Total lines (Adjusted): %d/%d   Total branches (Adjusted): %d/%d" % (inscope[0], inscope[1], inscope[2], inscope[3]))
    # Target = the coverage GOAL for the Adjusted slice (manifest `target`). Advisory only: it is the
    # aim the backfill drives toward and the level to sustain, NOT a gate (the ratchet floor sits a
    # few points below it, so gating on target would flap CI). Shown so the report reads against the goal.
    if target_c0 is not None or target_c1 is not None:
        def _tgt(axis, adj, tgt):
            if tgt is None:
                return None
            gap = adj - float(tgt)
            mark = "✅ met" if round(adj, 1) >= float(tgt) else "▼ %.1f pp to goal" % (-gap)
            return "%s %.1f%% vs goal %.0f%% (%s)" % (axis, adj, float(tgt), mark)
        parts = [s for s in (_tgt("C0", c0, target_c0), _tgt("C1", c1, target_c1)) if s]
        out.append("\n**Target (goal for the Adjusted slice):** " + " · ".join(parts))
        out.append("_Advisory aim, not a gate. Enforcement is the diff gate (new code at target) + the ratchet floor (no regression); see the manifest `target` block._")
    # The gate's pass/fail verdict is intentionally NOT rendered in the report — this is a
    # test-quality report, not an exam. The gate still enforces via the process exit code, and
    # its check details go to stderr (CI logs) below.

    # 3. Coverage by Bucket
    bagg = {}    # cat -> [raw_l, raw_b, t_l, t_b, t_lc, t_bc, nfiles]
    frows = []   # (fn, cat, raw_l, raw_b, t_l, t_b, t_lc, t_bc, has_cov)
    for fn, d in files.items():
        cat = bucket_of(fn)
        tl, tb, tlc, tbc = testable(fn, d)
        a = bagg.setdefault(cat, [0, 0, 0, 0, 0, 0, 0])
        a[0] += d["tot"]; a[1] += d["btot"]; a[2] += tl; a[3] += tb; a[4] += tlc; a[5] += tbc; a[6] += 1
        frows.append((fn, cat, d["tot"], d["btot"], tl, tb, tlc, tbc, d["cov"] > 0))

    def layer_of(cat):
        key = cat[6:] if cat.startswith("excl: ") else cat
        return {
            "application": "Application / Service (business logic)",
            "uncategorized": "Uncategorized",
            "integration-scope": "Infrastructure / Integration",
            "e2e-scope": "Presentation / Workers",
            "dto-no-logic": "Models / DTOs",
            "generated": "Generated",
            "non-product": "Non-product",
        }.get(key, key)

    def is_target(cat):
        return not cat.startswith("excl:")

    out.append("\n## 3. Coverage by Layer")
    out.append("_Coverage per architectural layer. **Raw** = all instrumented code in the layer. "
               "**Testable** = its unit-testable slice — the whole file in the Application/Service "
               "(target) layer; in other layers only the pure carve-out methods (the rest of those "
               "layers is exercised by integration/E2E tests, not unit tests). **C0/C1 are coverage "
               "of the testable slice.** Only the target layer feeds the Adjusted headline; the "
               "other layers' figures are informational (the unit-tested pure slices inside them)._")
    def cell(cov, tot):
        return ("%.0f%% (%d/%d)" % (pct(cov, tot), cov, tot)) if tot else "—"

    HDR = "| Layer | Raw lines | Raw branches | Testable lines | Testable branches | C0 | C1 |"
    SEP = "|-------|----------:|-------------:|---------------:|------------------:|----|----|"
    out.append(HDR); out.append(SEP)
    for cat, a in sorted(bagg.items(), key=lambda kv: (not is_target(cat), kv[0])):
        name = layer_of(cat) + (" — TARGET" if is_target(cat) else "")
        out.append("| %s | %d | %d | %d | %d | %s | %s |"
                   % (name, a[0], a[1], a[2], a[3], cell(a[4], a[2]), cell(a[5], a[3])))

    # Per-file detail, same columns + the file's layer. Target-layer files show in full (Testable =
    # Raw); other layers' files show only their carve-out slice (Testable < Raw), which is why a
    # 1631-line infrastructure file reads as 131 testable lines.
    unit_files = [r for r in frows if r[4] > 0]
    unit_files.sort(key=lambda r: (not is_target(r[1]), -r[4]))
    out.append("\n### Coverage per file (unit-scope: %d files — target layer in full + carve-out slices)" % len(unit_files))
    out.append(HDR.replace("| Layer |", "| File | Layer |"))
    out.append(SEP.replace("|-------|", "|------|-------|"))
    FILE_CAP = 80
    for fn, cat, rl, rb, tl, tb, tlc, tbc, _ in unit_files[:FILE_CAP]:
        out.append("| `%s` | %s | %d | %d | %d | %d | %s | %s |"
                   % (short(fn), layer_of(cat), rl, rb, tl, tb, cell(tlc, tl), cell(tbc, tb)))
    if len(unit_files) > FILE_CAP:
        out.append("\n_+%d more — see the HTML drill-down._" % (len(unit_files) - FILE_CAP))

    # 4. Risk Hotspots
    out.append("\n## 4. Risk Hotspots")
    out.append("**What this is:** methods with high cyclomatic complexity (many branches/paths) AND low "
               "coverage — the code most likely to hide an untested bug. Complexity ≈ number of independent "
               "paths through the method (roughly: 1 + the count of `if`/`&&`/`||`/`case`/loops); 20+ is high, "
               "50+ is very high. A complex method at low coverage means most of those paths are never executed "
               "by a test.")
    out.append("\n**What to do**, by the row's bucket:")
    out.append("- **A target bucket** (e.g. `application`) → a direct unit-test gap you own. Write unit tests "
               "covering its branches. *This is the only kind that is your unit-testing TODO.*")
    out.append("- **`excl: integration-scope`** → not a unit target. Make sure an integration test exercises it, "
               "or pull the pure logic out into a small carve-out method and unit-test that.")
    out.append("- **`excl: e2e-scope`** → a controller/worker/startup path. Make sure an E2E test covers it, or "
               "refactor to cut the complexity down.")
    out.append("\nSorted **target-first** (your gaps), then by risk (complexity × uncovered fraction).")

    def action_for(b):
        if not b.startswith("excl:"):
            return "**Unit-test it** (in-scope gap)"
        if "integration" in b:
            return "Integration test, or extract a carve-out"
        if "e2e" in b:
            return "E2E coverage, or refactor"
        return "Review"

    hot_all = [mm for mm in methods if mm["complexity"] >= 5 and mm["line_rate"] < 0.8]
    # A method already declared in cannot_test (dead/unreachable/nondeterministic-no-seam) is NOT
    # an in-scope unit gap — it is accounted for in section 6. Leaving it here contradicts §6
    # (e.g. a dead private method with no caller shown as "unit-test it"). Drop it and note how many.
    hot = [mm for mm in hot_all if mm["bare"] not in cannot_test_names]
    suppressed_hot = len(hot_all) - len(hot)
    hot.sort(key=lambda x: (bucket_of(x["file"]).startswith("excl:"), -(x["complexity"] * (1.0 - x["line_rate"]))))
    if hot:
        in_scope_hot = [mm for mm in hot if not bucket_of(mm["file"]).startswith("excl:")]
        if in_scope_hot:
            out.append("\n⚠️ **%d of these sit in a target bucket — those are direct unit-test gaps; start there.**" % len(in_scope_hot))
        else:
            out.append("\n**Takeaway: none are in a target bucket.** Every hotspot is integration/E2E code, "
                       "covered (or not) by those test layers — there is **no direct unit-test action** here. "
                       "Address them only if you choose to extract carve-outs from the worst offenders.")
        out.append("\n| Class / Method | File | Complexity | Coverage | Bucket | What to do |")
        out.append("|----------------|------|-----------:|---------:|--------|------------|")
        for mm in hot[:args.needs_attention_top]:
            b = bucket_of(mm["file"])
            out.append("| `%s.%s` | `%s` | %d | %.0f%% | %s | %s |"
                       % (mm["cls"], mm["name"], mm["file"].split("/")[-1], mm["complexity"],
                          100.0 * mm["line_rate"], b, action_for(b)))
        if len(hot) > args.needs_attention_top:
            out.append("\n_+%d more (complexity ≥5, coverage <80%%) — see the HTML report._" % (len(hot) - args.needs_attention_top))
        if suppressed_hot:
            out.append("\n_(%d complex-but-uncovered method(s) omitted here — already logged in section 6 as `cannot_test`; not in-scope gaps.)_" % suppressed_hot)
    else:
        out.append("\nNone — no method with complexity ≥5 is below 80% coverage (after excluding cannot_test).")

    # 5. Excluded Code
    out.append("\n## 5. Excluded Code (intentional, out of scope)")
    out.append("_Mechanism is the manifest join (patterns applied at report time) — source is never annotated._")
    out.append("| Path / Pattern | Mechanism | Reason (category) | Covered by |")
    out.append("|----------------|-----------|-------------------|------------|")
    by_cat = {}
    for ex in exclusions:
        by_cat.setdefault(ex["category"], []).append(ex["pattern"])
    for cat in sorted(by_cat):
        pats = by_cat[cat]
        ex_examples = ", ".join("`%s`" % p for p in pats[:3]) + (" …(+%d)" % (len(pats) - 3) if len(pats) > 3 else "")
        out.append("| %s | manifest pattern | %s (%d patterns) | %s |"
                   % (ex_examples, cat, len(pats), COVERED_BY.get(cat, "—")))

    # 5b. Partially testable (mixed) files: the testable carve-out slice kept IN scope inside an
    # excluded file, emitted PER FILE so a mixed file is never hidden behind one folder-glob line.
    # Clip limits across the prose tables are deliberately generous. They used to be ~110-120 chars,
    # which truncated every reason and mitigation mid-sentence, so the detail could not be read at
    # all, scroll or no scroll. Cells wrap now (overflow-wrap in the CSS), so the limits exist only
    # as a guard against a pathological entry, not as a layout device.
    def _clip1(s, n=1200):
        s = (s or "").replace("\n", " ").strip()
        return s[:n - 1] + "…" if len(s) > n else s

    def tcell(s):
        """Escape a value for a markdown TABLE cell. Reasons quote C# such as `a || b`, and a bare
        pipe is the cell delimiter, so an unescaped one silently splits the row into extra columns.
        md_to_html splits on unescaped pipes only and unescapes for display.
        Defined here, before its first use in 5b, so every later section can reuse it."""
        return str(s or "").replace("|", "\\|")
    out.append("\n## 5b. Partially testable (mixed) files")
    out.append("_Excluded files that still carry a testable carve-out slice. The listed methods are IN "
               "scope (their lines count toward Adjusted and diff coverage); the rest of the file is "
               "excluded for the stated reason. Shown so a mixed file is never collapsed to one line._")
    ambiguous = []
    for ex in exclusions:
        matched = [fn for fn in files if match(fn, ex["pattern"])]
        has_co = (isinstance(ex.get("carve_outs"), list) and ex.get("carve_outs")) or ("CARVE-OUT:" in (ex.get("reason") or ""))
        if has_co and len(matched) > 1:
            ambiguous.append((ex["pattern"], len(matched)))
    mixed_rows = []
    for fn, d in sorted(files.items()):
        co_lines = carveout_lineset(fn)
        if not co_lines:
            continue
        exm = next((ex for ex in exclusions if match(fn, ex["pattern"])), None)
        names = sorted({mm["bare"] for mm in file_methods.get(fn, []) if set(mm["lines"]) & set(co_lines)})
        tl, tb, tlc, tbc = testable(fn, d)
        rest = (exm.get("excluded_rest", "") if exm else "") or ""
        cat = exm["category"] if exm else "?"
        mixed_rows.append((short(fn), names, tlc, tl, cat, rest))
    if mixed_rows:
        out.append("| File | Testable carve-outs (in scope) | Carve-out C0 | Excluded rest |")
        out.append("|------|--------------------------------|-------------:|---------------|")
        for fnm, names, tlc, tl, cat, rest in mixed_rows:
            nm = ", ".join("`%s`" % n for n in names[:6]) + (" …(+%d)" % (len(names) - 6) if len(names) > 6 else "")
            covtxt = ("%.0f%%" % (100.0 * tlc / tl)) if tl else "n/a"
            resttxt = tcell(_clip1(rest)) if rest else ("(%s; no per-method reason recorded)" % cat)
            out.append("| `%s` | %s | %s | %s |" % (tcell(fnm), nm or "n/a", covtxt, resttxt))
    else:
        out.append("_None: no excluded file declares a carve-out._")
    if ambiguous:
        out.append("\n> ⚠️ **Ambiguous carve-outs:** %d exclusion pattern(s) carrying carve-outs match MORE "
                   "than one file, so the manifest cannot say which method belongs to which file. Split each "
                   "into one per-file entry with a structured `carve_outs:` list:" % len(ambiguous))
        for pat, n in ambiguous[:10]:
            out.append(">  - `%s` (matches %d files)" % (pat, n))

    # 6. Not Testable — split by NATURE, because "should trend to zero" is only true for debt.
    def clip(s, n=1500):
        s = (s or "").replace("\n", " ")
        return s[:n - 3] + "…" if len(s) > n else s

    out.append("\n## 6. Not Testable")
    if not cannot_test:
        out.append("_None recorded._")
    else:
        debt = [ct for ct in cannot_test if category_nature(ct.get("category")) == "debt"]
        structural = [ct for ct in cannot_test if category_nature(ct.get("category")) == "structural"]

        def emit_table(rows):
            out.append("| Class / Method | Where | Why not unit-testable | Category | Mitigation |")
            out.append("|----------------|-------|----------------------|----------|------------|")
            for ct in rows:
                cat = canonical_category(ct.get("category"))
                lines = ct.get("lines") or "—"
                mitigation = tcell(clip(ct.get("mitigation"), 800)) or ACTION.get(cat, "Review")
                out.append("| `%s` | %s | %s | %s | %s |"
                           % (tcell(ct.get("target", "n/a")), lines,
                              tcell(clip(ct.get("reason", ""))), cat, mitigation))

        # 6a — design debt: fixable by a source change, SHOULD trend to zero.
        out.append("\n### 6a. Design debt — fixable by a seam/refactor; should trend to zero")
        out.append("_Genuine target logic blocked by a missing seam. Each is a refactor candidate, not a "
                   "permanent exemption; the Mitigation is the way out._")
        if debt:
            # Systematic-seam callout: many entries sharing one signal (a clock/id/Stopwatch at
            # method entry) are usually ONE base-class seam that unlocks all of them — the highest-
            # ROI move, and easy to miss in a long flat list. Quantify it so it can't be.
            def sig_count(needle):
                return sum(1 for ct in debt if needle.lower() in (ct.get("reason", "") or "").lower())
            clusters = [(n, c) for n, c in
                        (("Guid.NewGuid", sig_count("Guid.NewGuid")),
                         ("Stopwatch", sig_count("Stopwatch")),
                         ("DateTime.UtcNow/Now", sig_count("DateTime.UtcNow") + sig_count("DateTime.Now")),
                         ("InternalsVisibleTo", sig_count("InternalsVisibleTo")))
                        if c >= 3]
            if clusters:
                summary = "; ".join("%d share `%s`" % (c, n) for n, c in clusters)
                out.append("\n> **Systematic seam opportunity:** %s. These usually collapse to ONE injected "
                           "seam (e.g. an `IClock`/`IGuidProvider` on a shared base class, or a single "
                           "`InternalsVisibleTo`) that unlocks many at once — do that before writing per-method "
                           "workarounds.\n" % summary)
            emit_table(debt)
        else:
            out.append("_None — no seam-fixable entries._")

        # 6b — structural: will NOT move; not debt. Framing these as "trend to zero" is misleading.
        out.append("\n### 6b. Structurally uncoverable — not debt; expected to persist")
        out.append("_Compiler-lowered/unreachable branches, dead (uncalled) code, target-framework "
                   "mismatches, generated code. These are honest, permanent exclusions — they will NOT "
                   "trend to zero, and are not a unit-test gap. Audit that each is genuinely structural, "
                   "then leave it._")
        if structural:
            emit_table(structural)
        else:
            out.append("_None._")

    # 7. Latent bugs frozen by characterization.
    # A characterization backfill pins what the code does TODAY, wrong behaviour included, so some
    # tests assert a bug on purpose. Without this section, "554 tests, all green" reads as "the code
    # is correct" when it actually means "behaviour has not drifted". The defect backlog therefore
    # lives in the artifact people actually read, sorted by severity, in red.
    #
    # This is a DEFECT BACKLOG, not a coverage exemption: it does not affect scope, the Adjusted
    # number, the ratchet, or the diff gate. Untestable *code* still goes to cannot_test.
    latent = m.get("latent_bugs") or []
    if latent:
        counts = {}
        for b in latent:
            sev = (b.get("severity") or "D").strip().upper()[:1]
            counts[sev] = counts.get(sev, 0) + 1
        act = sum(v for k, v in counts.items() if k in ("A", "B", "C"))

        out.append("\n## %s" % LATENT_HEADING)
        out.append("")
        out.append("!!! %d known product bugs are FROZEN, NOT FIXED. %d of them are severity A/B/C and "
                   "need resolving. The tests below pin what the code does TODAY, wrong behaviour "
                   "included, so the suite is GREEN while these bugs are live. A green suite here means "
                   "\"behaviour has not drifted\", NOT \"behaviour is correct\"."
                   % (len(latent), act))
        out.append("")
        out.append("!!! Fixing any item REQUIRES updating or deleting its characterization test in the "
                   "same change. Several tests assert the bug on purpose, so a correct fix will turn the "
                   "suite red until its test is updated.")
        out.append("")
        out.append("| Severity | Count |")
        out.append("|----------|------:|")
        for sev in sorted(counts, key=lambda s: SEV_ORDER.get(s, 9)):
            out.append("| %s | %d |" % (SEV_LABEL.get(sev, sev), counts[sev]))
        out.append("| **Total** | **%d** |" % len(latent))

        for sev in sorted(counts, key=lambda s: SEV_ORDER.get(s, 9)):
            rows = [b for b in latent
                    if (b.get("severity") or "D").strip().upper().startswith(sev)]
            out.append("\n### 7%s. %s" % (chr(ord("a") + SEV_ORDER.get(sev, 9)), SEV_LABEL.get(sev, sev)))
            out.append("| Sev | Class / Method | Where | What looks wrong | Pinned by |")
            out.append("|-----|----------------|-------|------------------|-----------|")
            for b in rows:
                out.append("| %s | `%s` | %s | %s | %s |"
                           % (sev,
                              tcell(b.get("target", "n/a")),
                              ("`%s`" % tcell(b["file"])) if b.get("file") else "n/a",
                              tcell(clip(b.get("summary", ""), 1200)),
                              tcell(clip(b.get("pinned_by", ""), 300))))
        out.append("")
        out.append("_Source of truth: `latent_bugs:` in `.claude/coverage/refs/coverage-manifest.yml`. "
                   "Remove an entry when the bug is fixed and its characterization test updated._")

    out.append("\n---")
    out.append("_Full per-file drill-down: `coverage/html/summary.html` · exclusion reasons & cannot_test: `.claude/coverage/refs/coverage-manifest.yml`_")

    report = "\n".join(out) + "\n"
    print(report)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(report)
    if args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(md_to_html(report))
    if args.cannot_test_out:
        # report_date follows report.sh's dated folder (REPORT_DATE) so the header matches the path;
        # falls back to today's local date when the gate is run standalone.
        report_date = os.environ.get("REPORT_DATE") or now[:10]
        tests_note = ("%d tests" % tr["total"]) if (tr and tr.get("total")) else "tests not captured"
        headline = "Adjusted C0 %.1f%% / C1 %.1f%%, %s" % (c0, c1, tests_note)
        ct_md = render_cannot_test_md(cannot_test, repo, report_date, headline)
        with open(args.cannot_test_out, "w", encoding="utf-8") as fh:
            fh.write(ct_md)
    # Gate outcome to stderr only (CI logs / local terminal) — kept out of the report body so the
    # report stays a quality view, not a pass/fail exam. The exit code is what actually enforces.
    if gate_active:
        verdict = "FAIL (enforced: %s)" % ", ".join(enforced_breaches) if gate_failed else "PASS"
        print("\n[coverage-gate] %s" % verdict, file=sys.stderr)
        for g in gate_lines:
            print("[coverage-gate] " + g.replace("✅", "").replace("❌", "").replace("⚠️", "WARNING:").replace("**", "").strip().lstrip("- "), file=sys.stderr)
        # Name every breach that was seen and deliberately not enforced. Silence here would read as
        # "nothing was wrong", which is how an advisory check stops being read at all.
        if advisory_breaches:
            print("[coverage-gate] ADVISORY: %s breached but NOT enforced, so the run stays green. "
                  "Arm with `gate.enforce` in the manifest, or --enforce."
                  % ", ".join(advisory_breaches), file=sys.stderr)
    sys.exit(1 if gate_failed else 0)


if __name__ == "__main__":
    main()
