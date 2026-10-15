# Contributing

Thanks for considering a contribution. This marketplace is small and opinionated — read this first so we can align before you spend real time.

## What lives here

Two plugins, both aimed at GitHub repo quality:

- **[repo-visuals](./plugins/repo-visuals)** — designs bespoke README hero visuals through a discovery dialog.
- **[repo-doctor](./plugins/repo-doctor)** — audits READMEs and produces a P0/P1/P2 punch list.

The bar for both: **production-grade defaults, encoded from real maintainer pushback** — not generic templates.

## Easiest ways to contribute

### 1. Submit a hero to the showcase

If you've used `repo-visuals` and the result shipped upstream (or lives in your own repo), add it. See [SHOWCASE.md](./plugins/repo-visuals/SHOWCASE.md) for the format. Heroes that landed via merged PR are especially welcome — they're proof the skill survives contact with real maintainers.

### 2. Report a real failure

If a skill produced something wrong, lazy, or off-voice — open an issue with:
- the repo you ran it against
- what came out
- what you wanted instead

Failure modes are the most useful signal we get. Don't sand them down.

### 3. Pick something from the wishlist

Skill ideas that fit the marketplace's spirit. Open an issue before starting one — direction matters more than effort here.

| Idea | Plugin | What it would do |
|---|---|---|
| **New visual mode** | repo-visuals | A new format (e.g. terminal-recording, architecture diagram, side-by-side before/after) that fits a repo category not yet served. |
| **New audit criterion** | repo-doctor | A check the current 9 criteria miss — bring an example repo where the gap matters. |
| **Badge auditor** | repo-doctor | Flags badge sprawl, dead `shields.io` links, stale version pins. Could ship as a doctor mode or stand alone. |
| **Social-card generator** | new | Generate the OG image (`<meta property="og:image">`) so the repo looks right when pasted in chat or shared on socials. Lighter cousin of `repo-visuals`. |
| **Repo-postcard** | new | A single static image summarizing what the repo does, how to install, and one screenshot — for blog posts and talks. |
| **README translation** | new | Translate a README into a target language while preserving maintainer voice and code-block fidelity. |
| **License/attribution checker** | new | Surfaces missing `LICENSE`, mismatched SPDX headers, undeclared deps behind README's "built with" claims. |
| **Acknowledgments builder** | new | Generates a "Thanks to" section from contributor history, sponsors, and prior-art repos cited in commits. |
| **Sunset notice** | new | For archived or abandoned repos: detects staleness, drafts a top-of-README sunset block pointing to the successor or fork. |

If your idea isn't on the list, that's fine — open an issue and pitch it. The list is a starting point, not a fence.

### 4. Fix something small

Typos, broken links, doc clarifications, dead examples — open a PR directly, no issue needed.

## PRs to skill internals

For non-trivial changes to skill behavior (prompts, gates, modes, output format):

1. **Open an issue first.** Describe the change and the maintainer pain it solves. We'll align on direction before code.
2. **Show a real before/after.** Run the skill against a real repo, paste the output. Abstract arguments rarely survive contact with a real README.
3. **Keep the voice.** Skills here are built to sound like a senior maintainer, not an assistant. If your change makes the output more polite, more hedged, or more "helpful," it's probably wrong.

## What we won't merge

- Generic templates or fixed layouts dressed up as new modes.
- Output that quotes star counts, contributor counts, or version numbers (drift hazard — see existing skill rules).
- Marketing voice in skill output. Status-readout shape > punchy taglines.
- Features added "for completeness" without a real repo behind them.

## Status

Personal project, pre-1.0, evolving fast. Breaking changes are expected. If you depend on a specific skill behavior, pin a commit.
