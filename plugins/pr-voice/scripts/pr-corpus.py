#!/usr/bin/env python3
"""Turn a repo's merged-PR history into a measured voice profile.

The pr-voice skill rewrites a PR description "in the repo's existing PR voice". Left to judgment,
"voice" drifts toward a generic assistant template (Summary / Changes / Testing, a bullet per file).
This script pins it to numbers measured from what the repo actually merged, so the draft has a
target it can be checked against: title shape, body length by diff size, the headings that recur,
how issues get closed, and a few exemplar PRs to read in full.

Input is the JSON written by:

  gh pr list --state merged --limit 60 \
    --json number,title,body,author,mergedAt,additions,deletions,changedFiles,url > merged.json

Run:  python3 pr-corpus.py merged.json [--author LOGIN] [--max 40]
Out:  one JSON object on stdout (see build_profile). Stdlib only.

PR bodies are other people's text. This script only measures them; nothing in a body is ever
executed or treated as an instruction.
"""
import argparse, json, re, statistics, sys
from collections import Counter

BOT_LOGINS = re.compile(r"(\[bot\]$|^dependabot|^renovate|^github-actions|^greenkeeper|^snyk-bot|^pre-commit-ci|^allcontributors)", re.I)
CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?: \S")
CLOSING = re.compile(r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:[\w.-]+/[\w.-]+)?#\d+", re.I)
BARE_REF = re.compile(r"(?<![\w/])#\d+\b")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", re.M)
BOLD_LABEL = re.compile(r"^\s{0,3}\*\*([^*\n]{2,40}?):?\*\*:?\s*$", re.M)
BULLET = re.compile(r"^\s*[-*+]\s+(?!\[[ xX]\])\S", re.M)
CHECKBOX = re.compile(r"^\s*[-*+]\s+\[[ xX]\]", re.M)
FENCE = re.compile(r"^\s*(```|~~~)", re.M)
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)|<img\s", re.I)
COMMENT = re.compile(r"<!--.*?-->", re.S)
TRAILER = re.compile(r"^(co-authored-by|signed-off-by):", re.I | re.M)
GENERATED = re.compile(r"generated with \[?claude code|\U0001F916", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
WORD = re.compile(r"[A-Za-z0-9][\w'’-]*")

# Diff-size buckets (additions + deletions). Body length scales with change size far more than with
# author, so the target length is read from the bucket the PR being rewritten falls into.
BUCKETS = [("small", 0, 50), ("medium", 50, 400), ("large", 400, None)]


def is_bot(pr):
    a = pr.get("author") or {}
    return bool(a.get("is_bot")) or bool(BOT_LOGINS.search(a.get("login") or ""))


def bucket_of(lines):
    for name, lo, hi in BUCKETS:
        if lines >= lo and (hi is None or lines < hi):
            return name
    return BUCKETS[-1][0]


def norm_heading(text):
    t = re.sub(r"[*_`:]+", "", text).strip().lower()
    t = EMOJI.sub("", t).strip()
    return re.sub(r"\s+", " ", t)


def visible(body):
    """Body text as rendered: template comments stripped, line endings normalized."""
    return COMMENT.sub("", (body or "").replace("\r\n", "\n")).strip()


def words_in(text):
    # Fenced code is not prose; leaving it in makes a PR with one log dump look "long-winded".
    out, in_fence = [], False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return len(WORD.findall("\n".join(out)))


def share(n, d):
    return round(n / d, 2) if d else 0.0


def quartiles(values):
    if not values:
        return {"p25": 0, "median": 0, "p75": 0}
    if len(values) == 1:
        return {"p25": values[0], "median": values[0], "p75": values[0]}
    q = statistics.quantiles(values, n=4, method="inclusive")
    return {"p25": round(q[0]), "median": round(q[1]), "p75": round(q[2])}


def analyze(pr):
    title = (pr.get("title") or "").strip()
    body = visible(pr.get("body"))
    m = CONVENTIONAL.match(title)
    headings = [norm_heading(h) for _, h in HEADING.findall(body)]
    headings += [norm_heading(h) for h in BOLD_LABEL.findall(body)]
    lines = (pr.get("additions") or 0) + (pr.get("deletions") or 0)
    return {
        "number": pr.get("number"),
        "author": (pr.get("author") or {}).get("login"),
        "diff_lines": lines,
        "bucket": bucket_of(lines),
        "title": title,
        "title_len": len(title),
        "conventional": bool(m),
        "cc_type": m.group("type") if m else None,
        "cc_scope": m.group("scope") if m else None,
        "title_period": title.endswith("."),
        "title_lower_start": bool(re.match(r"^(?:[a-z]+(?:\([^)]*\))?!?: )?[a-z]", title)),
        "title_issue_ref": bool(BARE_REF.search(title)),
        "empty": not body,
        "words": words_in(body),
        "headings": [h for h in dict.fromkeys(headings) if h],
        "bullets": bool(BULLET.search(body)),
        "checkboxes": bool(CHECKBOX.search(body)),
        "code": bool(FENCE.search(body)),
        "image": bool(IMAGE.search(body)),
        "closing": [k.lower() for k in CLOSING.findall(body)],
        "issue_ref": bool(BARE_REF.search(body)),
        "emoji": bool(EMOJI.search(GENERATED.sub("", body))),
        "trailer": bool(TRAILER.search(body)),
        "generated_footer": bool(GENERATED.search(body)),
    }


def pick_exemplars(rows, top_headings, k=4):
    """Representative PRs to read in full: non-empty, typical headings, length near the median.

    Spread across diff buckets so the drafter sees how the voice stretches from a one-liner to a
    large change, instead of four near-identical mid-size PRs.
    """
    pool = [r for r in rows if not r["empty"]]
    if not pool:
        return []
    med = statistics.median(r["words"] for r in pool)
    common = set(top_headings)

    def score(r):
        overlap = len(common & set(r["headings"])) if common else 0
        return (-overlap, abs(r["words"] - med))

    picked = []
    for name, _, _ in BUCKETS:
        cands = sorted((r for r in pool if r["bucket"] == name), key=score)
        if cands:
            picked.append(cands[0])
    for r in sorted(pool, key=score):
        if len(picked) >= k:
            break
        if r not in picked:
            picked.append(r)
    return [{"number": r["number"], "bucket": r["bucket"], "words": r["words"], "title": r["title"]}
            for r in picked[:k]]


def build_profile(prs, author=None, max_n=40):
    skipped = Counter()
    kept = []
    for pr in prs:
        if is_bot(pr):
            skipped["bot"] += 1
            continue
        kept.append(pr)
    # Newest first, so the profile reflects the voice the repo uses now, not three years ago.
    kept.sort(key=lambda p: p.get("mergedAt") or "", reverse=True)

    # Prefer the target author's own history when there's enough of it: a solo maintainer's PRs and
    # a drive-by contributor's PRs in the same repo often read nothing alike.
    scope = "repo"
    if author:
        mine = [p for p in kept if ((p.get("author") or {}).get("login") or "").lower() == author.lower()]
        if len(mine) >= 5:
            skipped["other_author"] += len(kept) - len(mine)
            kept, scope = mine, "author"
    if len(kept) > max_n:
        skipped["over_max"] += len(kept) - max_n
        kept = kept[:max_n]

    rows = [analyze(p) for p in kept]
    n = len(rows)
    nonempty = [r for r in rows if not r["empty"]]
    ne = len(nonempty)

    heading_counts = Counter(h for r in nonempty for h in r["headings"])
    common_headings = [{"heading": h, "share": share(c, ne)} for h, c in heading_counts.most_common(8)
                       if share(c, ne) >= 0.2]
    # Heading order matters as much as heading names ("Why" before "Changes" is a voice choice).
    seq_counts = Counter(tuple(r["headings"]) for r in nonempty if r["headings"])
    common_seq = seq_counts.most_common(1)[0] if seq_counts else None

    conv = [r for r in rows if r["conventional"]]
    by_bucket = {}
    for name, lo, hi in BUCKETS:
        b = [r["words"] for r in nonempty if r["bucket"] == name]
        by_bucket[name] = {"range": [lo, hi], "n": len(b), **quartiles(b)}

    if n < 5:
        confidence = "none" if n == 0 else "low"
    elif n < 15:
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "sample": {"used": n, "scope": scope, "author": author if scope == "author" else None,
                   "skipped": dict(skipped), "confidence": confidence,
                   "newest": kept[0].get("mergedAt") if kept else None,
                   "oldest": kept[-1].get("mergedAt") if kept else None},
        "title": {
            "conventional_share": share(len(conv), n),
            "types": [t for t, _ in Counter(r["cc_type"] for r in conv).most_common(6)],
            "scope_share": share(sum(1 for r in conv if r["cc_scope"]), len(conv)),
            "scopes": [s for s, _ in Counter(r["cc_scope"] for r in conv if r["cc_scope"]).most_common(6)],
            "lowercase_start_share": share(sum(r["title_lower_start"] for r in rows), n),
            "trailing_period_share": share(sum(r["title_period"] for r in rows), n),
            "issue_ref_share": share(sum(r["title_issue_ref"] for r in rows), n),
            "length": quartiles(sorted(r["title_len"] for r in rows)),
        },
        "body": {
            "empty_share": share(n - ne, n),
            "words": quartiles(sorted(r["words"] for r in nonempty)),
            "words_by_diff_size": by_bucket,
            "common_headings": common_headings,
            "common_heading_sequence": {"headings": list(common_seq[0]), "share": share(common_seq[1], ne)} if common_seq else None,
            "no_heading_share": share(sum(1 for r in nonempty if not r["headings"]), ne),
            "bullets_share": share(sum(r["bullets"] for r in nonempty), ne),
            "checkbox_share": share(sum(r["checkboxes"] for r in nonempty), ne),
            "code_block_share": share(sum(r["code"] for r in nonempty), ne),
            "image_share": share(sum(r["image"] for r in nonempty), ne),
            "closing_keyword_share": share(sum(1 for r in nonempty if r["closing"]), ne),
            "closing_keywords": [k for k, _ in Counter(k for r in nonempty for k in r["closing"]).most_common(3)],
            "issue_ref_share": share(sum(r["issue_ref"] for r in nonempty), ne),
            "emoji_share": share(sum(r["emoji"] for r in nonempty), ne),
            "trailer_share": share(sum(r["trailer"] for r in nonempty), ne),
            "generated_footer_share": share(sum(r["generated_footer"] for r in nonempty), ne),
        },
        "exemplars": pick_exemplars(rows, [h["heading"] for h in common_headings]),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("merged_json", help="output of `gh pr list --state merged --json ...` ('-' for stdin)")
    ap.add_argument("--author", help="login of the PR being rewritten; their own history is preferred when >=5 PRs")
    ap.add_argument("--max", type=int, default=40, help="newest N human PRs to profile (default 40)")
    args = ap.parse_args(argv)
    try:
        raw = sys.stdin.read() if args.merged_json == "-" else open(args.merged_json, encoding="utf-8").read()
        prs = json.loads(raw or "[]")
    except (OSError, ValueError) as e:
        print("pr-corpus: cannot read %s: %s" % (args.merged_json, e), file=sys.stderr)
        return 2
    if not isinstance(prs, list):
        print("pr-corpus: expected a JSON array of PRs", file=sys.stderr)
        return 2
    json.dump(build_profile(prs, args.author, max(1, args.max)), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
