#!/usr/bin/env bash
# One command -> a full coverage report, any time.
#   ./.claude/coverage/tools/report.sh [solution] [repo-filter]
# Collects coverage, joins it against the manifest, writes the committed report to
# .claude/coverage/reports/<YYYY-MM-DD>/REPORT.{md,html} + CANNOT-TEST.md (one dated folder per
# run), and prints it. Exits non-zero if the gate fails (so it doubles as a local gate).
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
echo "FILE_FILTER=$FILE_FILTER"

# 2. Collect (auto-detects the .sln if not passed).
"$HERE/run-coverage.sh" "$SOLUTION" "$OUTPUT_DIR" "$REFS/coverage.runsettings" "$FILE_FILTER"

# 3. Join + gate + format. Tee the Markdown to the committed reports dir; emit HTML beside it.
# Set BASE=<ref> (e.g. BASE=origin/master) to preview the PR gate locally — adds diff-coverage
# and the scope-change guard. Without it this is a plain local report (ratchet only).
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
