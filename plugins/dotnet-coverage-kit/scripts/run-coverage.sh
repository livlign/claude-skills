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
mapfile -t TEST_PROJECTS < <(grep -rl --include='*.csproj' 'Microsoft.NET.Test.Sdk' . \
  | grep -vE '/(bin|obj)/' | sort -u)
if [[ ${#TEST_PROJECTS[@]} -eq 0 ]]; then
  echo "No test projects (Microsoft.NET.Test.Sdk) found under $(pwd)." >&2
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
