# pr-voice

A Claude Code plugin that **rewrites thin pull-request descriptions in the repo's own PR voice** — measured from what the repo actually merged, grounded in what the diff actually does.

Generic rewrites turn every PR into **Summary / Changes / Testing** with a bullet per file and a confident "All tests pass". That reads as foreign in a repo whose PRs are two plain sentences, and it's wrong when nobody ran the tests. `pr-voice` profiles the merged history first (title convention, body length per diff size, the headings that recur and in what order, how issues get closed), then writes a description that would blend into the PR list — saying only what the diff, commits, and linked issues support.

## Install

```
/plugin marketplace add livlign/claude-skills
/plugin install pr-voice@livlign
```

After install, restart Claude Code (or start a new session) so the plugin's skills are discovered.

Needs the [`gh` CLI](https://cli.github.com/), authenticated, and `python3` (stdlib only).

## How to run

> Rewrite the description for PR #42

> Write a PR description for this branch

What a run looks like:

```
> /pr-voice 42
  target → PR #42 · 3 files, +38/−9 · body: "fix"
  voice  → 31 merged PRs (author-scoped, 14 bots skipped)
           fix(scope): titles · ~70 words for a small diff · Why → What · "Closes #n"
  draft  → before/after shown · dropped "Testing" (no evidence tests ran)
  apply? → gh pr edit 42 ✓
```

Works on an open PR, the current branch's PR, or a branch with no PR yet (drafts the text for `gh pr create`).

## What it guarantees

- **No invented facts.** Motivation comes from the existing body, commits, linked issues, or you — if the "why" is missing it asks once, or leaves it out. "Tested" only appears when something shows it was.
- **Nothing the author wrote is lost.** Issue links, screenshots, benchmark numbers, reviewer notes, template checklists (unticked boxes stay unticked), co-author trailers.
- **Measured voice, not house style.** Prefixes, casing, headings, and length come from the repo's numbers. When there's no history, it uses a plain neutral shape and says so — never the generic template.
- **Never writes silently.** Before/after first; `gh pr edit` only after you confirm, in every mode.

## Operating modes

Same three modes as `repo-visuals` and `repo-doctor`.

| Mode | What **you** decide | Typical back-and-forths |
|---|---|---|
| **Auto** | the final apply | 1 |
| **Semi-auto** _(default)_ | missing "why" questions, the apply | ~2 |
| **Manual** | voice scope, exemplars, each question, the draft, the apply | 4–6 |

## Layout

- [`skills/pr-voice/SKILL.md`](./skills/pr-voice/SKILL.md) — the skill (target → voice → draft → apply).
- [`scripts/pr-corpus.py`](./scripts/pr-corpus.py) — turns `gh pr list --state merged --json …` into a voice profile JSON. Drops bots, prefers the author's own history, buckets body length by diff size, picks exemplars.
- [`scripts/tests/test_pr_corpus.py`](./scripts/tests/test_pr_corpus.py) — fixture test, run in CI.
