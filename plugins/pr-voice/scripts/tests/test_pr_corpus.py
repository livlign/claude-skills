#!/usr/bin/env python3
"""Fixture test for pr-corpus.py.

Feeds a synthetic merged-PR history through the CLI and asserts on the profile. Covers the
behaviors the skill leans on when it checks a draft:

  - bots (is_bot flag and dependabot/renovate-style logins) never shape the voice
  - the target author's own history wins when they have >= 5 PRs, repo-wide otherwise
  - conventional-commit share, types and scopes are measured from titles
  - template comments and fenced code don't count as prose words
  - body length is bucketed by diff size (small / medium / large)
  - heading names AND order are captured (### Why / ### What), incl. **Bold:** labels
  - closing keywords are recognized; exemplars span diff-size buckets
  - empty / garbage input fails cleanly instead of with a traceback

Run:  python3 scripts/tests/test_pr_corpus.py
Exit: 0 = pass, 1 = a failure. Stdlib only.
"""
import json, os, subprocess, sys, tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "pr-corpus.py")


def pr(n, title, body, login="maint", lines=20, bot=False, day=None):
    return {
        "number": n, "title": title, "body": body,
        "author": {"login": login, "is_bot": bot},
        "mergedAt": "2026-09-%02dT10:00:00Z" % (day or n % 28 + 1),
        "additions": lines, "deletions": 0, "changedFiles": 1, "url": "https://example/pr/%d" % n,
    }


WHY_WHAT = "### Why\n\n{why}\n\n### What\n\n{what}\n\nCloses #{issue}"


def fixture():
    prs = []
    for i in range(1, 9):  # maintainer: conventional titles, Why/What sections
        lines = [10, 30, 120, 200, 600, 20, 90, 900][i - 1]
        prs.append(pr(i, "fix(parser): handle empty input case %d" % i if i % 2 else "feat(cli): add flag %d" % i,
                      WHY_WHAT.format(why="Users hit a crash on empty files.", what="Return early with a clear error. " * (1 + lines // 100), issue=100 + i),
                      lines=lines))
    # contributor: plain titles, one paragraph, a template comment and a code block that mustn't count
    prs.append(pr(20, "Update docs for install", "<!-- describe your change -->\nTypo fix in install docs.\n\n```\n" + "log line\n" * 50 + "```", login="drive-by"))
    prs.append(pr(21, "Speed up tokenizer", "**Summary:**\nUses a lookup table.\n\nFixes #7", login="drive-by", lines=300))
    # bots
    prs.append(pr(30, "Bump lodash from 4.17.20 to 4.17.21", "Bumps lodash. " * 40, login="dependabot[bot]"))
    prs.append(pr(31, "chore(deps): update all", "Renovate update", login="renovate-bot", bot=True))
    prs.append(pr(32, "Sync", "auto", login="some-app", bot=True))
    return prs


def run(args, stdin=None):
    return subprocess.run([sys.executable, "-I", SCRIPT] + args, input=stdin, capture_output=True, text=True)


def main():
    fails = 0

    def check(cond, label):
        nonlocal fails
        print(("  ok   " if cond else "  FAIL ") + label)
        fails += 0 if cond else 1

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "merged.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fixture(), f)

        # --- repo-wide (no author) ---------------------------------------------------------
        r = run([path])
        check(r.returncode == 0, "repo-wide run exits 0 (stderr: %s)" % r.stderr.strip()[:200])
        p = json.loads(r.stdout)
        check(p["sample"]["used"] == 10, "bots dropped: 10 human PRs used, got %s" % p["sample"]["used"])
        check(p["sample"]["skipped"].get("bot") == 3, "3 bots skipped (is_bot + [bot] + renovate login)")
        check(p["sample"]["scope"] == "repo", "no --author -> repo scope")
        check(p["title"]["conventional_share"] == 0.8, "conventional share 8/10, got %s" % p["title"]["conventional_share"])
        check(set(p["title"]["types"]) == {"fix", "feat"}, "types = fix, feat")
        check(set(p["title"]["scopes"]) == {"parser", "cli"}, "scopes = parser, cli")
        check("lodash" not in json.dumps(p), "nothing from a bot PR leaks into exemplars")

        # --- author-scoped --------------------------------------------------------------------
        r = run([path, "--author", "MAINT"])
        p = json.loads(r.stdout)
        check(p["sample"]["scope"] == "author" and p["sample"]["used"] == 8, "--author (case-insensitive) with >=5 PRs -> 8 of their own")
        check(p["sample"]["skipped"].get("other_author") == 2, "2 other-author PRs set aside")
        check(p["title"]["conventional_share"] == 1.0, "author-scoped titles all conventional")
        seq = (p["body"]["common_heading_sequence"] or {}).get("headings")
        check(seq == ["why", "what"], "heading order captured as why -> what, got %s" % seq)
        check(p["body"]["no_heading_share"] == 0.0, "every maintainer PR has headings")
        check(p["body"]["closing_keywords"] == ["closes"], "closing keyword = closes, got %s" % p["body"]["closing_keywords"])
        b = p["body"]["words_by_diff_size"]
        check(b["small"]["n"] == 3 and b["medium"]["n"] == 3 and b["large"]["n"] == 2,
              "diff buckets 3/3/2, got %s/%s/%s" % (b["small"]["n"], b["medium"]["n"], b["large"]["n"]))
        check(b["large"]["median"] > b["small"]["median"], "large-diff bodies measured longer than small ones")
        buckets = {e["bucket"] for e in p["exemplars"]}
        check(buckets == {"small", "medium", "large"}, "exemplars span all three buckets, got %s" % buckets)

        r = run([path, "--author", "drive-by"])
        p = json.loads(r.stdout)
        check(p["sample"]["scope"] == "repo", "--author with <5 PRs falls back to repo-wide")

        # --- prose counting -------------------------------------------------------------------
        only = os.path.join(d, "one.json")
        with open(only, "w", encoding="utf-8") as f:
            json.dump([fixture()[8]], f)
        p = json.loads(run([only]).stdout)
        check(p["body"]["words"]["median"] == 5, "comment + code fence excluded: 5 prose words, got %s" % p["body"]["words"]["median"])
        check(p["body"]["code_block_share"] == 1.0, "code block still detected")
        check(p["sample"]["confidence"] == "low", "1 PR -> low confidence")

        with open(only, "w", encoding="utf-8") as f:
            json.dump([fixture()[9]], f)
        p = json.loads(run([only]).stdout)
        check(any(h["heading"] == "summary" for h in p["body"]["common_headings"]), "**Summary:** bold label counts as a heading")
        check(p["body"]["closing_keywords"] == ["fixes"], "Fixes #7 recognized")

        # --- empty / bad input ----------------------------------------------------------------
        p = json.loads(run(["-"], stdin="[]").stdout)
        check(p["sample"]["confidence"] == "none" and p["exemplars"] == [], "empty history -> confidence none, no exemplars")
        r = run(["-"], stdin="{not json")
        check(r.returncode == 2 and "Traceback" not in r.stderr, "malformed JSON -> exit 2, no traceback")
        r = run(["-"], stdin='{"a": 1}')
        check(r.returncode == 2, "non-array JSON -> exit 2")

    if fails:
        print("\n%d check(s) FAILED" % fails)
        return 1
    print("\nAll pr-corpus checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
