# Reference gallery

Real-world repo heroes, catalogued so Phase 1.4c can pattern-match. Not templates — prompts for recognizing archetypes.

## How to use

During the discovery scan, compare the target repo to the entries below and ask "which of these does it most structurally resemble?" When a clear match surfaces ("this feels like shallow-backup" or "this is an amplication-shape SaaS repo"), open the format recommendation with that archetype's default choice, cite the reference by name, and let the user push back. If nothing matches cleanly, fall back to the archetype-level defaults in the cross-cutting observations, not to a guess.

## Archetypes

**1. Terminal-demo GIF** — Interactive CLI or TUI where the payoff is "watch it run." Format gravitates to an animated GIF of the terminal, usually 600–900px wide, sometimes preceded by a small logo. Signal: the tool is invoked from a shell and its value is motion (prompts, progress, color). Members: `shallow-backup`, `stronghold`.

**2. Product-UI marketing** — A shipped app with a GUI where the README doubles as a landing page. Format is a UI screenshot (PNG) or occasionally an embedded video; branding logo often sits above it. Signal: the repo ships a desktop/web app end-users open, not a library. Members: `electron-markdownify`, `hydra`, `openai-agents-python` (tracing UI screenshot stands in for the "product").

**3. Brand-first logo** — Large org/ecosystem projects that skip demo imagery entirely and lead with identity. Format is SVG or PNG logo/wordmark, sometimes with light/dark variants. Signal: the repo is well-known enough that recognition, not explanation, is the job; OR it's a config/content repo with nothing to "show." Members: `freeCodeCamp`, `amplication`, `ArminC-AutoExec`, `ohmyzsh`, `EventualShop`.

**4. Banner/promo graphic** — A composed key-art image (photo, illustration, or stylized banner) that sells a vibe rather than showing the product. Format is a wide PNG/JPG banner. Signal: the project has atmosphere (gaming, community, lifestyle) that a UI screenshot would under-sell. Members: `docker-steam-headless`.

**5. Diagram-as-hero** — Didactic repos (learning, reference, architecture) where the hero *is* the content. Format is a technical diagram PNG. Signal: the repo teaches a system rather than shipping one. Members: `system-design-primer`.

## Catalog

### 1. freeCodeCamp/freeCodeCamp
- **README**: https://github.com/freeCodeCamp/freeCodeCamp
- **Format**: static PNG (social banner)
- **Content**: brand banner / wordmark
- **Dimensions**: full-width banner (`fcc_banner_new.png`)
- **Vibe**: confident, mission-driven, institutional
- **Why it suits**: freeCodeCamp is a movement more than a codebase — readers arrive knowing what it is, so identity beats explanation.
- **Lesson**: when the project is already famous, the hero's job is recognition, not pitch.

### 2. alichtman/shallow-backup
- **README**: https://github.com/alichtman/shallow-backup
- **Format**: animated GIF (`img/shallow-backup-demo.gif`)
- **Content**: terminal recording of the interactive menu
- **Dimensions**: standard terminal capture (~700–800px)
- **Vibe**: honest, practical, "watch me work"
- **Why it suits**: the whole product is an interactive prompt flow — a still frame would miss the entire UX.
- **Lesson**: if the value is motion (prompts advancing, progress, color changes), a GIF is non-negotiable.

### 3. alichtman/stronghold
- **README**: https://github.com/alichtman/stronghold
- **Format**: mixed — PNG logo (`img/stronghold-logo-left.png`) + GIF demo (`img/demo.gif`)
- **Content**: brand mark + terminal recording
- **Dimensions**: small logo above a demo GIF
- **Vibe**: polished indie CLI
- **Why it suits**: security-hardening CLI benefits from both trust signal (logo) and proof of behavior (GIF).
- **Lesson**: logo + GIF stacked is the "serious CLI" move — identity first, evidence second.

### 4. amitmerchant1990/electron-markdownify
- **README**: https://github.com/amitmerchant1990/electron-markdownify
- **Format**: static PNG (`app/img/markdownify.png`)
- **Content**: product logo / app brand mark
- **Dimensions**: standard centered logo
- **Vibe**: clean indie desktop app
- **Why it suits**: Electron markdown editor — the logo establishes product-ness; the UI screenshot lives further down the README.
- **Lesson**: for desktop apps, a branded logo hero frames the project as a product, not a script.

### 5. amplication/amplication
- **README**: https://github.com/amplication/amplication
- **Format**: SVG logo (light/dark variants via GitHub theme)
- **Content**: company wordmark
- **Dimensions**: vector, responsive
- **Vibe**: calm SaaS / VC-backed polish
- **Why it suits**: commercial open-source platform — hero does brand work, product screenshot comes after the pitch.
- **Lesson**: dual light/dark SVGs are table stakes for serious product/SaaS repos.

### 6. AntonioFalcaoJr/EventualShop
- **README**: https://github.com/AntonioFalcaoJr/EventualShop
- **Format**: static PNG (`.assets/img/new_logo.png`)
- **Content**: project logo
- **Dimensions**: centered logo (~200–400px)
- **Vibe**: portfolio-grade showcase project
- **Why it suits**: reference architecture repo — there's no "UI" to screenshot; the logo does positioning work before the diagrams land.
- **Lesson**: architecture-showcase repos often lead with logo, then let the structure diagrams carry the content later.

### 7. ArmynC/ArminC-AutoExec
- **README**: https://github.com/ArmynC/ArminC-AutoExec
- **Format**: SVG (`arminc_autoexec.svg`) as clickable logo
- **Content**: brand/wordmark that doubles as a download CTA
- **Dimensions**: centered vector
- **Vibe**: gamer-forum confident, sharp edges
- **Why it suits**: it's a config file, not software — there's nothing to demo; the SVG is identity plus primary call-to-action.
- **Lesson**: config/content repos can use the hero as a CTA button — image links aren't just decoration.

### 8. hydralauncher/hydra
- **README**: https://github.com/hydralauncher/hydra
- **Format**: static PNG (`resources/icon.png`)
- **Content**: app icon / logo
- **Dimensions**: icon-sized, centered
- **Vibe**: consumer app, launcher aesthetic
- **Why it suits**: desktop game launcher — the icon is the brand; UI screenshots appear in a features section below.
- **Lesson**: app-icon-as-hero is the short, humble variant of brand-first — works when the icon itself is recognizable art.

### 9. Steam-Headless/docker-steam-headless
- **README**: https://github.com/Steam-Headless/docker-steam-headless
- **Format**: static banner JPG (`images/banner.jpg`)
- **Content**: promotional banner graphic
- **Dimensions**: full README width banner
- **Vibe**: gaming key-art, atmospheric
- **Why it suits**: the value prop is a whole cloud-gaming setup — no single screenshot captures it, so a composed banner sells the vibe.
- **Lesson**: when the product is a system/experience rather than a UI, a composed banner beats any single real screenshot.

### 10. openai/openai-agents-python
- **README**: https://github.com/openai/openai-agents-python
- **Format**: static PNG (`cdn.openai.com/API/docs/images/orchestration.png`)
- **Content**: product UI screenshot (Agents Tracing UI)
- **Dimensions**: standard doc hero (~800px)
- **Vibe**: official, docs-grade, restrained
- **Why it suits**: an SDK with an accompanying tracing dashboard — the screenshot telegraphs "there's a real observability surface" instantly.
- **Lesson**: SDKs with a companion UI should hero the UI, not the code — the surface is the differentiator.

### 11. ohmyzsh/ohmyzsh
- **README**: https://github.com/ohmyzsh/ohmyzsh
- **Format**: static PNG (`omz-ansi-github.png`)
- **Content**: stylized ANSI-art wordmark / banner
- **Dimensions**: wide branded banner
- **Vibe**: retro-terminal, community-warm
- **Why it suits**: 170k-star ecosystem — the brand carries; the ANSI-styling is a tonal wink back to its terminal roots.
- **Lesson**: a wordmark styled *as the thing itself* (ANSI for a shell framework) is a cheap way to make a logo do double duty.

### 12. donnemartin/system-design-primer
- **README**: https://github.com/donnemartin/system-design-primer
- **Format**: static PNG diagram (`images/jj3A5N8.png`)
- **Content**: architecture diagram (load balancer / servers / DB / cache)
- **Dimensions**: ~800–900px wide
- **Vibe**: textbook, calm, authoritative
- **Why it suits**: a study guide for system design — the diagram IS the subject matter, not an illustration of it.
- **Lesson**: for didactic repos, the most representative artefact *from inside the content* is the right hero.

## Cross-cutting observations

- **CLI tools skew animated.** Both pure-CLI entries (`shallow-backup`, `stronghold`) use terminal GIFs; static screenshots of a terminal would bury their interactive payoff. Default: if it's a TUI/interactive CLI, start with GIF.
- **Big-brand or ecosystem repos skip demos entirely.** `freeCodeCamp`, `ohmyzsh`, `amplication` lead with identity — recognition is doing more work than persuasion.
- **SaaS-adjacent and SDK repos go PNG/SVG logo or product-UI screenshot, never GIF.** `amplication`, `openai-agents-python`, `hydra` all feel "corporate-calm"; motion would read as busy.
- **Config/content/architecture repos (`ArminC-AutoExec`, `EventualShop`, `system-design-primer`) either use logo-as-CTA or let a representative internal artefact (diagram) be the hero.** There's no UI to screenshot, so the hero either points somewhere or *is* the content.
- **Nobody in this set uses an embedded video as the hero.** GIF still wins for motion in READMEs — autoplay, no controls, no third-party host. A plausible rule: only reach for video when the motion exceeds ~15s or needs audio.
- **Light/dark-aware SVGs only appear on the most product-polished entry (`amplication`).** That pairing is a reliable tell for "this project wants to be perceived as a product."
- **If the hero shows a grid meant to represent scope, the grid must match the repo's real inventory.** Silent undercounts (hero shows 8 cards for a repo with 30 items) read as broken promises — worse than a sample honestly framed as a sample. Default rule: if real count > grid capacity, add a scroll affordance, a group-by-category view, or a literal "30+" label. This is enforced at `§1.3` (count the inventory), `§4.0` (entry gate), and `§6.3` (AI eval caps Intent delivery at 2 on detected undercount).
