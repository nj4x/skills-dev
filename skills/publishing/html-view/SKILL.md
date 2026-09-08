---
name: html-view
description: Convert the current plan, spec, design doc, or conversation context into a single self-contained, share-able HTML file with rich visual structure (tables, SVG diagrams, code blocks, responsive layout, in-page navigation). Supports four output shapes — editorial, technical-doc, dashboard, and slide-deck. Use when the user invokes /html-view, asks to "export as HTML", "render this as HTML", "structure your response as HTML" (Karpathy-style), "make a web version", "share this as a link", "present this as slides / a slideshow / a deck", or wants a long plan or spec converted from markdown into something visually scannable or presentable.
---

# html-view

Render the current plan, spec, design doc, or conversation context as **one self-contained HTML file** that conveys the information more densely than markdown can — tables, inline SVG diagrams, semantic structure, in-page navigation, mobile-responsive layout, no external runtime dependencies.

This skill owns *what* to convert and *where* to put the file. Visual quality (typography, color, motion, layout polish) is delegated to the `frontend-design` skill — if it's installed, treat this skill as composing on top of it. Otherwise default to a clean modern editorial style.

## Source selection

Do not fire if: source is < 30 lines (ask first), already HTML (refuse), or a live dashboard needing data refresh (redirect to a real Next.js page).

Pick the source in this order; stop at the first match:

1. **Explicit path passed as argument.** `/html-view /path/to/file.md` → that file. Resolve relative paths against the cwd. If the file doesn't exist or isn't readable, stop and tell the user.
2. **`@`-referenced markdown file** in the user's most recent message → that file.
3. **Most recently modified plan file** under `~/.claude/plans/*.md` — but only if a plan-mode session just exited or the user explicitly says "the plan". Pick by `mtime`, not name.
4. **Conversation context** (last resort): assemble a synthesis from the recent conversation. Only use this branch when the prior three failed AND the conversation contains enough material (≥ ~30 substantive turns). Otherwise ask the user what to convert.

Once the source is picked, read the *whole* file (or the relevant conversation slice) before starting the design pass. Don't skim.

## Output location

- Source is a file on disk → write the HTML as a **sibling** with the same basename and a `.html` extension. Example: `~/.claude/plans/foo.md` → `~/.claude/plans/foo.html`. Project doc `project-management/ai-secretary/foo-design.md` → `project-management/ai-secretary/foo-design.html`.
- Source is conversation context (no file) → write to `~/.claude/plans/<short-kebab-slug>.html`, where the slug summarizes the topic in 3-5 words. Create the dir if it's missing.
- Overwrite if the target already exists — but only after a quick read of the existing file to confirm it's a previous output from this skill (look for the `data-generator="html-view"` attribute on `<html>`, see below). If it looks like unrelated content, append `-v2`, `-v3`, etc.

Always print the **absolute path** of the written file in the final reply.

## Design pass (mandatory before writing)

Before emitting a single line of HTML, decide:

1. **Visual direction.** Pick one of the four modes below from the source's actual shape — not your favorite default. If the user named a shape ("slideshow", "dashboard"), respect it. Otherwise infer from cues:

   | Mode | Pick when… | Hallmarks |
   |---|---|---|
   | **editorial** | Long-form prose, narrative arc, ≤ 1 big decision matrix | Wide reading column, generous line-height, drop caps optional, sticky TOC |
   | **technical-doc** | API ref, schema, spec with many cross-references | Sidebar nav, fixed left rail, prominent code blocks, anchor links on every heading |
   | **dashboard** | Comparison-heavy: matrices, decision logs, multiple tables | Multi-column grid, scannable cards, sparse prose, KPI-style callouts |
   | **deck** | User asked for slides, OR source is a sequence of ~5–25 discrete claims/sections each worth its own screen | One section per viewport, scroll-snap, big type (`clamp(2rem, 5vw, 4rem)` for headings), slide counter |

   See [Slideshow / deck mode](#slideshow--deck-mode) below for the specifics when picking *deck*.
2. **Typography.** System UI stack by default (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`) + a monospace stack for code. Use a CDN font (Google Fonts) **only** if the source clearly calls for one and the user is okay with one network reference.
3. **Color palette.** Always prefer a **colorblind-friendly palette** — never distinguish data by red vs green alone. Use the **Okabe-Ito colorblind-safe palette** from [PALETTE.md](PALETTE.md) as defaults; load it when selecting colors. Aim for AA contrast (≥ 4.5:1 body text). Dark mode via `@media (prefers-color-scheme: dark)`.
4. **Layout.** Single long-scroll with sticky TOC is the safe default. Use tabs only when sections are genuinely independent (e.g. comparing options). Use a deck layout only when the user asks.
5. **What becomes what.** Walk through the source and tag each section: prose → `<section>` with `<h2>`; matrix/comparison → `<table>`; flow/architecture → a diagram; code → `<pre><code>`; warnings/asides → `<aside>` callouts; lists of decisions → definition lists. For each diagram, route by the rule in the *Diagrams* section below — and decide CDN-Mermaid vs. no-network inline SVG there, since it reshapes the whole file.

If `frontend-design` skill is available, defer aesthetic decisions to it; this skill's job is the structural map.

## HTML structure rules (non-negotiable)

- **Single `.html` file.** Inline everything: `<style>` in `<head>`, inline `<svg>` for diagrams. No external CSS/JS — network references are limited per the `file://`-clean rule below (one CDN font; the Mermaid script only if you chose Mermaid).
- **Self-identifying.** Add `data-generator="html-view"` to the root `<html>` tag so future invocations can detect a regenerable file.
- **Semantic HTML.** `<header>`, `<nav>`, `<main>`, `<section>`, `<article>`, `<aside>`, `<footer>`. Headings nest properly (one `<h1>` per page, then `<h2>` for sections, `<h3>` for subsections).
- **CSS custom properties at `:root`** for color + spacing tokens. Use `clamp()` for responsive type sizes.
- **Mobile responsive.** Layout collapses cleanly at ≤ 768px (sidebar → top nav, multi-column → single column). Test by visualizing.
- **Print-friendly.** Include `@media print` block — hide nav, hide interactive elements, force light colors, ensure tables don't break mid-row where avoidable.
- **In-page nav.** Every `<section>` gets a stable `id`. Build a TOC of anchor links to those ids. Smooth-scroll via `scroll-behavior: smooth` on `:root`.
- **Code blocks.** `<pre><code>` with monospace + a subtle background. Minimal syntax highlighting via hand-emitted `<span class="kw|str|cmt|num">` if it adds value; otherwise leave code unhighlighted. **No** Prism.js, highlight.js, or any runtime script for highlighting.
- **`file://` clean.** No `<script type="module">`, no `import`, no `fetch()`. The single allowed network reference is a CDN **font**. **Diagrams are a decision, not a default:** Mermaid.js via CDN renders sequence/flow/state/class diagrams richly but breaks the zero-fetch promise and fails offline, so hand-drawn inline SVG is the offline-safe default. Pick Mermaid **only** for those four diagram types *and* when the user is fine with one network reference (or asks for Mermaid); otherwise render the diagram as inline SVG. State the choice in the design pass.

## Slideshow / deck mode

When the visual direction is *deck* (user asked for slides, or source is a sequence of discrete claims):

- **One slide per viewport.** Each `<section class="slide">` is `min-height: 100vh`, displayed as a flex container, content vertically centered. Use `scroll-snap-type: y mandatory` on `<main>` and `scroll-snap-align: center` on each slide so scroll/swipe lands cleanly.
- **Type scale up.** Slide headings around `clamp(2.5rem, 6vw, 5rem)`; body around `clamp(1.125rem, 2vw, 1.5rem)`. A slide should be readable from across a room.
- **One big claim per slide.** Don't pack four bullet points where one headline plus a sub-line will do. If a section in the source has a list, consider whether each item deserves its own slide.
- **Slide counter.** Fixed-position bottom-right, e.g. `<div class="counter">3 / 12</div>` — counter values can be hand-emitted; no need for runtime calculation.
- **Keyboard nav is allowed here.** A small inline `<script>` for arrow-key / space / `j`/`k` navigation that calls `scrollIntoView()` is fine — it's the one place the *no runtime* rule loosens. Still no module imports, no fetches, no external scripts. The file must still work fully if JS is disabled (scroll-snap handles the experience).
- **Title slide first, summary slide last.** Title slide: H1 + one-line subtitle + author/date footer. Summary slide: the 3–5 key takeaways as a list (this is the one place a list of bullets *is* the right call).
- **No transitions, no animations** beyond `scroll-behavior: smooth`. Distraction tax outweighs the polish.
- **Print mode** stacks slides as A4 pages (`@media print { .slide { page-break-after: always; min-height: auto; } }`).

A deck for a 12-section source should land around 30–80 KB. If you're over 100 KB, you've either inlined too much CSS or duplicated content per slide — trim.

## Required element checklist (for sources ≥ 50 lines)

The output **must** include:

- At least one **table** — decision log, comparison matrix, file-list, schema, etc. (For deck mode, this can be on a single dedicated "matrix" slide.)
- At least one **diagram** — architecture, data flow, sequence, state machine. Render it per the `file://`-clean rule above (inline SVG by default; Mermaid only under the stated conditions). No PNG.
- An **anchor-linked TOC** (sidebar nav, top nav, or — for deck mode — a "contents" slide near the front).
- A **`<footer>`** with: the source file path, the generation date (ISO), and a small "Generated by html-view" line.

## Mermaid.js diagrams

When you've decided Mermaid (per the `file://`-clean rule), [MERMAID.md](MERMAID.md) carries everything: CDN setup, the strict 11.x syntax rules, the safe-character table, PlantUML conversion, container styling, and the multi-file pattern for large sequence diagrams. Reach for it the moment you write a `<pre class="mermaid">` block.

## Forbidden patterns

- External script tags or stylesheets to anything off-host. Two allowed exceptions: one CDN **font**, and the Mermaid.js CDN script **only** when you chose Mermaid under the `file://`-clean rule.
- ASCII art diagrams when an SVG is feasible — that's the markdown trap this skill exists to escape.
- Emoji unless the source file used emoji.
- `<details open>` collapsing critical content — readers shouldn't have to hunt.
- Markdown-via-library renders (no `marked`, no `markdown-it`, no `pandoc` calls). Write the HTML directly.
- Auto-open in browser without asking.

## After write

1. Print the absolute path.
2. Print the byte size (one line, e.g. `42 KB`) so the user can sanity-check that it's a single shareable artifact.
3. Sanity-check size: a 100-line markdown plan should produce **≲ 50 KB** of HTML. If it's larger, the design pass got bloated — note this in the reply.
4. Automatically open the generated HTML file with `open <path>`.
5. If auto-open fails because the command is unavailable or blocked, print the absolute path and the exact `open <path>` command for the user to run manually.

## Examples of triggering inputs

- `/html-view` — convert the most recent plan file.
- `/html-view ./project-management/ai-secretary/background-tasks-design.md` — convert that specific file.
- "Can you make this an HTML page?" (right after writing a long plan) — same as `/html-view`.
- "Render the SRS as a shareable HTML doc" with a path in context — convert that path.
- "Structure your response as HTML" at the end of a long answer (Karpathy-style) — synthesize the conversation into an HTML file under `~/.claude/plans/<slug>.html`.
- "Turn this into a slide deck for the standup" / "Present this as slides" — same source-picking flow, but route to **deck mode**.
- "Make a slideshow version of the plan I just wrote" — pick the most recent plan file, deck mode.

## Out of scope (deferred, not denied)

- S3 / public-link upload — revisit when manual sharing becomes a pain.
- Interactive playgrounds (sliders, knobs, copy-prompt-back-to-Claude) — revisit when the user asks for an interactive plan.
- Diff / PR rendering — would be a separate `/html-review` skill.
- Bundled design-system stylesheet — revisit if outputs start visually drifting.
- Always-auto-open in external sharing contexts beyond the local generated file — revisit if users want uploads or browser automation beyond `open`.