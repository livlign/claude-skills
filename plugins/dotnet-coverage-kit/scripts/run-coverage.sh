#!/usr/bin/env bash
set -euo pipefail

SOLUTION="${1:-}"
OUTPUT_DIR="${2:-./coverage}"
RUNSETTINGS="${3:-.claude/coverage/refs/coverage.runsettings}"

if [[ -z "$SOLUTION" ]]; then
  SOLUTION="$(find . -maxdepth 2 -name '*.sln' | head -n1)"
fi
if [[ -z "$SOLUTION" ]]; then
  echo "No solution found. Pass the .sln path as the first argument." >&2
  exit 1
fi

if ! dotnet tool list -g | grep -q 'dotnet-coverage'; then
  dotnet tool install -g dotnet-coverage
fi
if ! dotnet tool list -g | grep -q 'dotnet-reportgenerator-globaltool'; then
  dotnet tool install -g dotnet-reportgenerator-globaltool
fi

# Optional 4th arg / FILEFILTER env: ReportGenerator file filter to scope the report to this
# repo's own sources (e.g. "+*myrepo*"), excluding referenced sibling repos from the denominator.
FILEFILTER="${4:-${FILEFILTER:-}}"

# Results dir lives under OUTPUT_DIR (relative) so paths resolve identically on Linux CI and
# Windows local — a mktemp /tmp path is misresolved by the native ReportGenerator on Windows.
RESULTS_DIR="$OUTPUT_DIR/results"
rm -rf "$RESULTS_DIR"; mkdir -p "$RESULTS_DIR"

# Optional TEST_FILTER env -> dotnet test --filter, to deselect known-excluded test projects
# (e.g. a vendor/ignored project with a failing or infra-bound test). Keep this narrow and
# documented; it must not be used to hide real regressions.
TEST_FILTER="${TEST_FILTER:-}"

# Collect coverage PER TEST PROJECT, not via a single `dotnet test <solution>` invocation.
# On multi-test-project solutions the solution-level run captures only ONE project's cobertura
# (the Code Coverage collector does not reliably emit one file per assembly in a combined run),
# which silently undercounts. Discover test projects (those referencing Microsoft.NET.Test.Sdk)
# and run each into its own results subdir; ReportGenerator then merges all cobertura natively.
#
# TEST_PROJECT_EXCLUDE is an extended-regex of csproj paths to DROP from discovery, for test
# projects that are deliberately not solution members (e.g. a Lambda test project that binds live
# AWS clients at construction and is e2e-scope in the manifest). Without it the solution-membership
# guard below hard-fails on them. It resolves env first, then `scope.test_project_exclude` in the
# manifest, so ONE declaration serves both CI and a local run: a value living only in a CI env block
# silently hard-fails every local report, and a value living only in this script is lost the next
# time these scripts are refreshed from the kit.
# Keep it narrow. It must only ever name projects the manifest already classifies out of unit scope,
# never a project whose absence would hide a real regression.
if [[ -z "${TEST_PROJECT_EXCLUDE:-}" ]]; then
  _HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _MANIFEST="$(dirname "$RUNSETTINGS")/coverage-manifest.yml"
  if [[ -f "$_HERE/coverage-gate.py" && -f "$_MANIFEST" ]]; then
    TEST_PROJECT_EXCLUDE="$(python "$_HERE/coverage-gate.py" --manifest "$_MANIFEST" \
      --print-test-project-exclude 2>/dev/null || true)"
  fi
fi
if [[ -n "${TEST_PROJECT_EXCLUDE:-}" ]]; then
  echo "TEST_PROJECT_EXCLUDE=$TEST_PROJECT_EXCLUDE (matching test projects are not discovered)"
fi
mapfile -t TEST_PROJECTS < <(grep -rl --include='*.csproj' 'Microsoft.NET.Test.Sdk' . \
  | grep -vE '/(bin|obj)/' \
  | { if [[ -n "${TEST_PROJECT_EXCLUDE:-}" ]]; then grep -vE "$TEST_PROJECT_EXCLUDE"; else cat; fi; } \
  | sort -u)
if [[ ${#TEST_PROJECTS[@]} -eq 0 ]]; then
  echo "No test projects (Microsoft.NET.Test.Sdk) found under $(pwd)." >&2
  exit 1
fi

# Guard against the SILENT-UNDERCOUNT trap. A discovered test project that is NOT a member of the
# solution never gets built by `dotnet build <sln>`, so `dotnet test --no-build` finds no fresh
# output, runs 0 tests, and still exits 0: a misleadingly low number with no error. (Real incident:
# 2 of 6 test projects were missing from the .sln, so CI ran 596 of 2004 tests and reported 35%
# instead of 82.9%.) Fail loudly here instead of trusting the low number.
# `dotnet sln list` prints project paths as stored in the .sln (backslashes on Windows-authored
# solutions), so normalize separators and compare by filename, which is stable across OSes.
SLN_LIST="$(dotnet sln "$SOLUTION" list 2>/dev/null | tr '\\' '/')"
MISSING=()
for proj in "${TEST_PROJECTS[@]}"; do
  base="$(basename "$proj")"
  if ! printf '%s\n' "$SLN_LIST" | grep -qiE "(^|/)${base}$"; then
    MISSING+=("$proj")
  fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
  {
    echo "ERROR: the following test project(s) are NOT members of $SOLUTION."
    echo "A clean checkout never builds them, so coverage would silently undercount"
    echo "(dotnet test --no-build runs 0 tests and still exits 0):"
    for p in "${MISSING[@]}"; do echo "  - $p"; done
    echo "Fix: add each to the solution, e.g. dotnet sln \"$SOLUTION\" add <project>, then re-run."
  } >&2
  exit 1
fi

dotnet build "$SOLUTION" -c Debug --nologo
for proj in "${TEST_PROJECTS[@]}"; do
  echo ">> coverage: $proj"
  dotnet test "$proj" --no-build \
    --collect "Code Coverage;Format=cobertura" \
    --settings "$RUNSETTINGS" \
    --results-directory "$RESULTS_DIR" \
    --logger "trx" \
    ${TEST_FILTER:+--filter "$TEST_FILTER"}
done

# Backstop: every discovered test project must have produced a .trx. `dotnet test --logger trx`
# writes one .trx per invocation, so fewer .trx files than test projects means a project ran
# nothing (built but collected 0 results, or errored before producing output). A zero-result run
# for a project that has test attributes is a failure, not a pass, so do not let the report proceed.
TRX_COUNT="$(find "$RESULTS_DIR" -name '*.trx' 2>/dev/null | wc -l | tr -d '[:space:]')"
if [[ "${TRX_COUNT:-0}" -lt "${#TEST_PROJECTS[@]}" ]]; then
  {
    echo "ERROR: expected at least ${#TEST_PROJECTS[@]} .trx result file(s) (one per discovered test"
    echo "project) under $RESULTS_DIR, but found ${TRX_COUNT:-0}. A test project produced no results:"
    echo "it likely built but ran 0 tests, or failed before emitting a .trx. Investigate before"
    echo "trusting the coverage number (this is the silent-undercount trap)."
  } >&2
  exit 1
fi

# ReportGenerator merges multiple cobertura inputs natively. Do NOT use `dotnet-coverage merge`
# here: it does not accept cobertura as an INPUT format and silently emits an empty report.
#
# Report types are deliberately single-file: the multi-file `Html` type writes one page PER
# CLASS (hundreds of files that bury the entry point). `HtmlSummary` is one self-contained
# summary.html. Set FULL_HTML=1 to also emit the drill-down site into html/site/ on demand.
# ReportGenerator trend/delta snapshots — one XML per run. LOCAL-ONLY: .claude/coverage/history/
# is gitignored (committing a snapshot per run is churn, and CI doesn't commit so it cannot build
# cross-PR history anyway). The real persisted trend is the manifest floor + the report's Δ. For a
# cross-checkout trend chart in CI, point HISTORY_DIR at a CI cache path instead.
HISTORY_DIR="${HISTORY_DIR:-.claude/coverage/history}"
mkdir -p "$HISTORY_DIR"

# HtmlSummary already includes a Risk Hotspots section. -historydir adds trend/delta across runs.
rm -rf "$OUTPUT_DIR/html"
reportgenerator \
  -reports:"$RESULTS_DIR/**/*.cobertura.xml" \
  -targetdir:"$OUTPUT_DIR/html" \
  -historydir:"$HISTORY_DIR" \
  -reporttypes:"HtmlSummary;MarkdownSummaryGithub;TextSummary;JsonSummary;Cobertura" \
  ${FILEFILTER:+-filefilters:"$FILEFILTER"}

if [[ "${FULL_HTML:-}" == "1" ]]; then
  reportgenerator \
    -reports:"$RESULTS_DIR/**/*.cobertura.xml" \
    -targetdir:"$OUTPUT_DIR/html/site" \
    -historydir:"$HISTORY_DIR" \
    -reporttypes:"Html" \
    ${FILEFILTER:+-filefilters:"$FILEFILTER"}
fi

# Strip ReportGenerator's promotional chrome from the generated HTML: the Star / Sponsor
# buttons in the header, every "Upgrade to PRO version" upsell, and the PRO-gated empty
# "Method coverage" card (the real method number is still in Summary.txt / Summary.json).
# Uses perl, not python: perl ships with Git for Windows and GitHub runners, so this has no
# extra dependency on top of the bash the script already requires. Cosmetic only — the OSS
# attribution in the footer is left intact.
if command -v perl >/dev/null 2>&1; then
  perl -0777 -i -pe '
    s{<a class="button" href="https://github\.com/danielpalme/ReportGenerator".*?</a>}{}gs;
    s{<a class="button" href="https://github\.com/sponsors/danielpalme".*?</a>}{}gs;
    s{<a class="pro-button".*?</a>}{}gs;
    s{<p>Feature is only available for sponsors</p>}{}gs;
    s{<div class="card">\s*<div class="card-header">Method coverage</div>.*?</div>\s*</div>\s*</div>}{}gs;
  ' "$OUTPUT_DIR"/html/*.html "$OUTPUT_DIR"/html/*.htm 2>/dev/null || true
fi

echo "HTML_REPORT=$OUTPUT_DIR/html/summary.html"
echo "TEXT_SUMMARY=$OUTPUT_DIR/html/Summary.txt"
echo "JSON_SUMMARY=$OUTPUT_DIR/html/Summary.json"
echo "MARKDOWN_SUMMARY=$OUTPUT_DIR/html/SummaryGithub.md"
echo "COBERTURA=$OUTPUT_DIR/html/Cobertura.xml"
