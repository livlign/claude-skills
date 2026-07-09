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
REPO_FILTER="${2:-${FILEFILTER:-}}"
OUTPUT_DIR="coverage"            # throwaway collection + drill-down, at the repo root (gitignored)
MANIFEST="$REFS/coverage-manifest.yml"
# Each run's report is preserved in a dated subfolder (reports/YYYY-MM-DD/), not overwritten, so
# prior dates stay for comparison. Override the date with REPORT_DATE=YYYY-MM-DD if needed (e.g. to
# re-emit under a prior day). date +%F (ISO YYYY-MM-DD) is POSIX-portable (git-bash + Linux CI).
export REPORT_DATE="${REPORT_DATE:-$(date +%F)}"
REPORT_DIR="$REPORTS/$REPORT_DATE"
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/REPORT.md"

# 1. Collect (auto-detects the .sln if not passed). REPO_FILTER is a plain substring (e.g. the
# repo name); ReportGenerator needs a +glob, the gate needs the bare substring — derive both here.
"$HERE/run-coverage.sh" "$SOLUTION" "$OUTPUT_DIR" "$REFS/coverage.runsettings" "${REPO_FILTER:++*$REPO_FILTER*}"

# 2. Join + gate + format. Tee the Markdown to the committed reports dir; emit HTML beside it.
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
