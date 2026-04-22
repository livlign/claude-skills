# Showcase

Heroes made with `repo-visuals`.

To add yours, see [Contribute](#contribute).

---

<table>
<tr>
<td width="50%" valign="top">

<a href="https://github.com/htmlhint/HTMLHint"><img src="https://raw.githubusercontent.com/htmlhint/HTMLHint/main/website/src/assets/img/hero.gif" alt="HTMLHint hero"></a>
<sub><kbd>2026-04-22</kbd> &nbsp; <a href="https://github.com/htmlhint/HTMLHint"><b>htmlhint/HTMLHint</b></a></sub>

<br><br>

<a href="https://github.com/emtyty/ast-graph"><img src="https://raw.githubusercontent.com/emtyty/ast-graph/master/docs/ast-graph-demo.gif" alt="ast-graph hero"></a>
<sub><kbd>2026-04-20</kbd> &nbsp; <a href="https://github.com/emtyty/ast-graph"><b>emtyty/ast-graph</b></a></sub>

</td>
<td width="50%" valign="top">

<a href="https://github.com/affaan-m/everything-claude-code"><img src="https://raw.githubusercontent.com/affaan-m/everything-claude-code/main/assets/hero.png" alt="everything-claude-code hero"></a>
<sub><kbd>2026-04-21</kbd> &nbsp; <a href="https://github.com/affaan-m/everything-claude-code"><b>affaan-m/everything-claude-code</b></a></sub>

</td>
</tr>
</table>

---

## Contribute

You don't need an upstream PR or your own repo — if you made a hero and like it, submit it.

### Option A — hero already lives in a repo

Any public repo will do (target repo, your own, a fork). Link the raw image URL and fill in the template.

### Option B — hero is only local

Drop the file into [`showcase/`](./showcase/) in your PR to this repo and reference it with a relative path. That's it.

### Entry template

The layout is a 2-column Pinterest-style masonry. To add an entry, append it to whichever `<td>` column is currently shorter (keeps the wall tessellated). Paste this block inside that column:

```html
<a href="<repo URL>"><img src="<raw image URL, or ./showcase/<file> for Option B>" alt="<repo-name> hero"></a>
<sub><kbd>YYYY-MM-DD</kbd> &nbsp; <a href="<repo URL>"><b>owner/repo</b></a></sub>

<br><br>
```

Only the **hero image**, **repo link**, and **date** are required.

### Rules

- Hero must be yours or something you have permission to share.
- Keep files reasonably sized (GIF ≤ 10 MB, PNG ≤ 500 KB is the skill's own guidance).

### PR checklist

- [ ] Entry appended to the shorter column
- [ ] Image actually renders in the PR preview
- [ ] Required fields filled in (image, repo link, date)
