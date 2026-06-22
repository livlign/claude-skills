#!/usr/bin/env bash
# One command -> a full coverage report, any time.
#   ./.claude/coverage/tools/report.sh [solution] [repo-filter]
# Collects coverage, joins it against the manifest, writes the committed report to
# .claude/coverage/reports/REPORT.{md,html}, and prints it. Exits non-zero if the gate fails
# (so it doubles as a local gate).
#
# Layout (paths are relative to this script in .claude/coverage/tools/):
#   ../refs/      coverage-manifest.yml, coverage.runsettings   (committed)
#   ../reports/   REPORT.md, REPORT.html                        (committed snapshot)
#   <repo>/coverage/   regenerated throwaway: HTML drill-down, cobertura, results (gitignored)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REFS="$HERE/../refs"
REPORTS="$HERE/../reports"
SOLUTION="${1:-}"
REPO_FILTER="${2:-${FILEFILTER:-}}"
OUTPUT_DIR="coverage"            # throwaway collection + drill-down, at the repo root (gitignored)
MANIFEST="$REFS/coverage-manifest.yml"
mkdir -p "$REPORTS"
REPORT="$REPORTS/REPORT.md"

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
  --html "$REPORTS/REPORT.html" \
  ${REPO_FILTER:+--repo-filter "$REPO_FILTER"} \
  ${REPO_NAME:+--repo-name "$REPO_NAME"} \
  ${BASE:+--base "$BASE"} \
  | tee "$REPORT"
STATUS=${PIPESTATUS[0]}
set -e

echo ""
echo "REPORT_MD=$REPORT"
echo "REPORT_HTML=$REPORTS/REPORT.html"                 # the Unit Test Report (our format, committed)
echo "DRILLDOWN_HTML=$OUTPUT_DIR/html/summary.html"     # ReportGenerator per-file drill-down (throwaway)
exit "$STATUS"
