#!/usr/bin/env bash
# One command -> a full coverage report, any time.
#   ./.claude/coverage/tools/report.sh [solution] [repo-filter]
# Collects coverage, joins it against the manifest, writes the committed report to
# .claude/coverage/reports/<YYYY-MM-DD>/REPORT.{md,html} + CANNOT-TEST.md (one dated folder per
# run), and prints it. Exits non-zero only for a check named in the manifest's gate.enforce.
#
# Layout (paths are relative to this script in .claude/coverage/tools/):
#   ../refs/      coverage-manifest.yml, coverage.runsettings          (committed)
#   ../reports/<YYYY-MM-DD>/   REPORT.md, REPORT.html, CANNOT-TEST.md   (committed snapshot, per run)
#   <repo>/coverage/           regenerated throwaway: HTML drill-down, cobertura, results (gitignored)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REFS="$HERE/../refs"
REPORTS="$HERE/../reports"
SOLUTION="${1:-}"
# Two DIFFERENT filters, kept separate on purpose:
#   REPO_FILTER  bare substring (e.g. "myrepo")        -> coverage-gate.py --repo-filter
#   FILE_FILTER  full ReportGenerator expression       -> run-coverage.sh -filefilters
# These used to be one variable, so a full expression was impossible locally: it got wrapped into
# "+*+*a*;-*b**" for ReportGenerator and handed to the gate where a bare substring was expected.
# The upshot was that exclusions only ever existed in CI, and a local run silently measured code
# the CI run excluded.
REPO_FILTER="${2:-}"
OUTPUT_DIR="coverage"            # throwaway collection + drill-down, at the repo root (gitignored)
MANIFEST="$REFS/coverage-manifest.yml"
# Each run's report is preserved in a dated subfolder (reports/YYYY-MM-DD/), not overwritten, so
# prior dates stay for comparison. Override the date with REPORT_DATE=YYYY-MM-DD if needed (e.g. to
# re-emit under a prior day). date +%F (ISO YYYY-MM-DD) is POSIX-portable (git-bash + Linux CI).
export REPORT_DATE="${REPORT_DATE:-$(date +%F)}"
REPORT_DIR="$REPORTS/$REPORT_DATE"
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/REPORT.md"

# 0. Self-update from the kit, so pulling a new kit reaches every repo by simply RUNNING the report.
# The repo's committed copies under tools/ are what CI executes, so they are the thing that has to
# move; nobody remembers to copy them by hand. kit-sync installs the new tool copies and applies the
# mechanical (`auto`) manifest migrations only: it never touches classifications, exclusions, the
# floor, or a workflow file. Silent no-op when no kit checkout is visible, which is the CI case.
# Opt out with KIT_AUTO_UPDATE=0. Exit 10 means this very script was replaced, so re-exec it once
# (bash reads a running script incrementally; continuing on a rewritten file can corrupt execution).
if [[ "${KIT_AUTO_UPDATE:-1}" != "0" && -f "$HERE/kit-sync.py" && -z "${KIT_SYNC_REEXEC:-}" ]]; then
  set +e
  python "$HERE/kit-sync.py" --repo "$HERE/../../.." --quiet
  SYNC_STATUS=$?
  set -e
  if [[ "$SYNC_STATUS" -eq 10 ]]; then
    echo "[kit-sync] report.sh itself was updated; re-running the new version."
    KIT_SYNC_REEXEC=1 exec "$HERE/report.sh" "$@"
  elif [[ "$SYNC_STATUS" -ne 0 ]]; then
    echo "[kit-sync] sync failed (exit $SYNC_STATUS); continuing with the installed copies." >&2
  fi
fi

# 1. Resolve the ReportGenerator filefilter from the manifest (scope.file_filter plus an exclusion
# for any declared scope.vendored_paths that is actually present). The manifest is the single source
# of truth so this run and CI cannot disagree; FILEFILTER in the environment still wins for one-offs.
if [[ -n "${FILEFILTER:-}" ]]; then
  FILE_FILTER="$FILEFILTER"
else
  FILE_FILTER="$(python "$HERE/coverage-gate.py" --manifest "$MANIFEST" --print-file-filter \
    --repo-root . ${REPO_FILTER:+--repo-filter "$REPO_FILTER"})"
fi
echo "KIT_VERSION=$(python "$HERE/coverage-gate.py" --manifest "$MANIFEST" --print-kit-version)"
# Printed before the (slow) collect so a repo left behind on an older kit is visible immediately,
# not only in the finished report. Format: `<state> <manifest stamp> <kit semver>`.
echo "KIT_DRIFT=$(python "$HERE/coverage-gate.py" --manifest "$MANIFEST" --print-kit-drift)"
echo "FILE_FILTER=$FILE_FILTER"

# 2. Collect (auto-detects the .sln if not passed).
"$HERE/run-coverage.sh" "$SOLUTION" "$OUTPUT_DIR" "$REFS/coverage.runsettings" "$FILE_FILTER"

# 3. Join + gate + format. Tee the Markdown to the committed reports dir; emit HTML beside it.
# Set BASE=<ref> (e.g. BASE=origin/master) to preview the PR gate locally — adds diff-coverage
# and the scope-change guard. Without it this is a plain local report (ratchet only).
# Breaches are reported but do NOT fail this script unless the manifest's `gate.enforce` names the
# check (or you pass --enforce below); by default only a failing build/test run is fatal, in
# run-coverage.sh above.
set +e
python "$HERE/coverage-gate.py" \
  --cobertura "$OUTPUT_DIR/html/Cobertura.xml" \
  --manifest "$MANIFEST" \
  --test-results-dir "$OUTPUT_DIR/results" \
  --html "$REPORT_DIR/REPORT.html" \
  --cannot-test-out "$REPORT_DIR/CANNOT-TEST.md" \
  ${REPO_FILTER:+--repo-filter "$REPO_FILTER"} \
  ${REPO_NAME:+--repo-name "$REPO_NAME"} \
  ${BASE:+--base "$BASE"} \
  | tee "$REPORT"
STATUS=${PIPESTATUS[0]}
set -e

echo ""
echo "REPORT_MD=$REPORT"
echo "REPORT_HTML=$REPORT_DIR/REPORT.html"                 # the Unit Test Report (our format, committed)
echo "CANNOT_TEST_MD=$REPORT_DIR/CANNOT-TEST.md"           # cited not-unit-testable report (generated)
echo "DRILLDOWN_HTML=$OUTPUT_DIR/html/summary.html"     # ReportGenerator per-file drill-down (throwaway)
exit "$STATUS"
