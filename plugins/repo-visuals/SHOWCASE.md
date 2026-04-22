# Showcase

Heroes made with `repo-visuals`.

To add yours, see [Contribute](#contribute).

---

## ast-graph

[![ast-graph hero](https://raw.githubusercontent.com/emtyty/ast-graph/main/docs/ast-graph-demo.gif)](https://github.com/emtyty/ast-graph)

- **For:** [emtyty/ast-graph](https://github.com/emtyty/ast-graph)
- **Format:** animated GIF
- **Landed:** [PR #6](https://github.com/emtyty/ast-graph/pull/6) — 2026-04-20

---

## everything-claude-code

[![everything-claude-code hero](https://raw.githubusercontent.com/affaan-m/everything-claude-code/main/assets/hero.png)](https://github.com/affaan-m/everything-claude-code)

- **For:** [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code)
- **Format:** static PNG
- **Landed:** [PR #1532](https://github.com/affaan-m/everything-claude-code/pull/1532), follow-up [#1535](https://github.com/affaan-m/everything-claude-code/pull/1535) — 2026-04-21

---

## HTMLHint

[![HTMLHint hero](https://raw.githubusercontent.com/htmlhint/HTMLHint/main/website/src/assets/img/hero.gif)](https://github.com/htmlhint/HTMLHint)

- **For:** [htmlhint/HTMLHint](https://github.com/htmlhint/HTMLHint)
- **Format:** animated GIF
- **Landed:** [PR #1861](https://github.com/htmlhint/HTMLHint/pull/1861) — 2026-04-22

---

## Contribute

You don't need an upstream PR or your own repo — if you made a hero and like it, submit it.

### Option A — hero already lives in a repo

Any public repo will do (target repo, your own, a fork). Link the raw image URL and fill in the template.

### Option B — hero is only local

Drop the file into [`showcase/`](./showcase/) in your PR to this repo and reference it with a relative path. That's it.

### Entry template

Insert newest first:

```markdown
## <short title — usually the repo name or project name>

[![hero](<raw image URL, or ./showcase/<file> for Option B>)](<optional link target — repo URL, site, or omit>)

- **For:** <what the hero is for — repo link, product name, or "personal project">
- **Format:** animated GIF | static PNG
- **Landed:** <YYYY-MM-DD>, optional link to PR or site
```

Only the **hero image**, **format**, and **date** are required. Everything else is nice-to-have.

### Rules

- Hero must be yours or something you have permission to share.
- Keep files reasonably sized (GIF ≤ 10 MB, PNG ≤ 500 KB is the skill's own guidance).

### PR checklist

- [ ] Entry in date order (newest first)
- [ ] Image actually renders in the PR preview
- [ ] Required fields filled in (image, format, date)
