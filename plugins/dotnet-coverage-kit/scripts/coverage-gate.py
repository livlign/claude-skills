#!/usr/bin/env python3
"""
coverage-gate: join a ReportGenerator Cobertura report against the repo's
coverage-manifest.yml, compute IN-SCOPE (Adjusted) coverage, emit the Unit Test Report
(Markdown), and enforce the gate.

In-scope = every source file NOT matched by a manifest `exclusions` pattern. Exclusions
are checked first; remaining files are bucketed by `category_map` (unmatched -> uncategorized).
The excluded buckets are removed from the denominator, per rules/coverage-report.base.md.

Gate (all enforced when applicable):
- Ratchet: Adjusted (in-scope) C0/C1 must not drop below baseline.recorded_overall.
- Diff coverage (PR mode, --base given): changed in-scope lines must meet the manifest minimums.
- Scope-change guard (PR mode): growth of `exclusions`/`cannot_test`, or new source under an
  excluded path, fails unless --allow-scope-change is passed.

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


def pct(cov, tot):
    return (100.0 * cov / tot) if tot else 0.0


def _inline(s):
    """Inline markdown -> HTML on already-escaped text. Handles `code` and **bold** only;
    underscores are left alone so identifiers like cannot_test are not mangled."""
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


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
                return [c.strip() for c in row.strip().strip("|").split("|")]
            head = cells(ln); i += 2
            body.append("<table><thead><tr>" + "".join("<th>%s</th>" % _inline(_esc(c)) for c in head) + "</tr></thead><tbody>")
            while i < len(lines) and lines[i].startswith("|"):
                body.append("<tr>" + "".join("<td>%s</td>" % _inline(_esc(c)) for c in cells(lines[i])) + "</tr>")
                i += 1
            body.append("</tbody></table>")
            continue
        if ln.startswith("### "):
            body.append("<h3>%s</h3>" % _inline(_esc(ln[4:])))
        elif ln.startswith("## "):
            body.append("<h2>%s</h2>" % _inline(_esc(ln[3:])))
        elif ln.startswith("# "):
            body.append("<h1>%s</h1>" % _inline(_esc(ln[2:])))
        elif ln.strip() == "---":
            body.append("<hr/>")
        elif ln.startswith("- ") or ln.startswith("  - "):
            body.append("<li>%s</li>" % _inline(_esc(ln.lstrip().lstrip("- "))))
        elif ln.strip() == "":
            body.append("")
        elif ln.strip().startswith("_") and ln.strip().endswith("_"):
            body.append("<p class='note'>%s</p>" % _inline(_esc(ln.strip()[1:-1])))
        else:
            body.append("<p>%s</p>" % _inline(_esc(ln)))
        i += 1
    css = ("body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#1b1f23}"
           "h1{border-bottom:2px solid #eaecef;padding-bottom:.3em}h2{border-bottom:1px solid #eaecef;padding-bottom:.2em;margin-top:1.8em}"
           "table{border-collapse:collapse;width:100%;margin:.6em 0;font-size:13px}th,td{border:1px solid #d0d7de;padding:5px 9px;text-align:left}"
           "th{background:#f6f8fa}tr:nth-child(even){background:#fafbfc}code{background:#eff1f3;padding:1px 5px;border-radius:4px;font-size:12px}"
           ".note{color:#57606a;font-style:italic}hr{border:0;border-top:1px solid #eaecef;margin:1.5em 0}")
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
    "generated": "— (generated)",
    "non-product": "— (not shipped)",
    "nondeterministic": "— (frozen)",
}
ACTION = {
    "nondeterministic": "Frozen; needs an injected seam (clock/random/IO) to become testable",
    "integration-scope": "Cover via integration test, or extract a pure seam",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cobertura", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--summary", help="append the Markdown report to this file (e.g. $GITHUB_STEP_SUMMARY)")
    ap.add_argument("--repo-filter", help="only files whose path contains this substring")
    ap.add_argument("--needs-attention-top", type=int, default=15)
    ap.add_argument("--base", help="base git ref to diff against; enables diff-coverage + scope-change (PR mode).")
    ap.add_argument("--allow-scope-change", action="store_true")
    ap.add_argument("--test-results-dir", help="dir containing .trx files for the Test Results section")
    ap.add_argument("--repo-name", help="repo name for the report header")
    ap.add_argument("--html", help="also write the report as a self-contained HTML file at this path")
    ap.add_argument("--tooling", default="Microsoft Code Coverage (dotnet-coverage) + ReportGenerator + xUnit")
    args = ap.parse_args()
    args.base = _safe_ref(args.base)

    with open(args.manifest, encoding="utf-8") as fh:
        m = yaml.safe_load(fh)
    exclusions = m.get("exclusions") or []
    category_map = m.get("category_map") or {}
    gate = m.get("gate") or {}
    baseline = (m.get("baseline") or {}).get("recorded_overall") or {}
    floor_c0, floor_c1 = baseline.get("c0"), baseline.get("c1")
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
        if not cat.startswith("excl:"):
            inscope[0] += d["cov"]; inscope[1] += d["tot"]
            inscope[2] += d["bcov"]; inscope[3] += d["btot"]
            inscope[4] += d["mcov"]; inscope[5] += d["mtot"]
        t = cat_totals.setdefault(cat, [0, 0, 0, 0, 0, 0, 0])
        t[0] += d["cov"]; t[1] += d["tot"]; t[2] += d["bcov"]; t[3] += d["btot"]
        t[4] += 1; t[5] += d["mcov"]; t[6] += d["mtot"]
        raw[0] += d["cov"]; raw[1] += d["tot"]; raw[2] += d["bcov"]; raw[3] += d["btot"]
        raw[4] += d["mcov"]; raw[5] += d["mtot"]

    c0, c1 = pct(inscope[0], inscope[1]), pct(inscope[2], inscope[3])
    cm = pct(inscope[4], inscope[5])

    def short(fn):
        return "/".join(fn.split("/")[-2:])

    # ---- Ratchet ----
    ratchet_on = gate.get("ratchet", True)
    ratchet_fail = False
    gate_lines = []
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
            grew_excl = len(exclusions) - len(bm.get("exclusions") or [])
            grew_ct = len(cannot_test) - len(bm.get("cannot_test") or [])
            new_excluded = []
            for gp in added_files(args.base):
                for ex in exclusions:
                    if match(gp, ex["pattern"]):
                        new_excluded.append((gp, ex["category"])); break
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
            else:
                gate_lines.append("- **Scope change**: none ✅")

    gate_failed = ratchet_fail or diff_fail or scope_fail
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
    out.append("**Adjusted coverage:** C0 %.1f%% / C1 %.1f%%\n" % (c0, c1))

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

    hot = [mm for mm in methods if mm["complexity"] >= 5 and mm["line_rate"] < 0.8]
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
    else:
        out.append("\nNone — no method with complexity ≥5 is below 80% coverage.")

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

    # 6. Not Testable
    out.append("\n## 6. Not Testable (design findings — should trend to zero)")
    out.append("_Anything here that is genuinely target logic is a refactor candidate, not an exemption._")
    out.append("| Class / Method | Why not unit-testable | Category | Action |")
    out.append("|----------------|----------------------|----------|--------|")
    if cannot_test:
        for ct in cannot_test:
            reason = (ct.get("reason", "") or "").replace("\n", " ")
            if len(reason) > 110:
                reason = reason[:107] + "…"
            cat = ct.get("category", "—")
            out.append("| `%s` | %s | %s | %s |"
                       % (ct.get("target", "—"), reason, cat, ACTION.get(cat, "Review")))
    else:
        out.append("| — | — | — | none recorded |")

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
    # Gate outcome to stderr only (CI logs / local terminal) — kept out of the report body so the
    # report stays a quality view, not a pass/fail exam. The exit code is what actually enforces.
    if gate_active:
        print("\n[coverage-gate] %s" % ("PASS" if not gate_failed else "FAIL"), file=sys.stderr)
        for g in gate_lines:
            print("[coverage-gate] " + g.replace("✅", "").replace("❌", "").replace("**", "").strip().lstrip("- "), file=sys.stderr)
    sys.exit(1 if gate_failed else 0)


if __name__ == "__main__":
    main()
