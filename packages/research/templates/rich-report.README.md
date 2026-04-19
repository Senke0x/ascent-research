# rich-report template — authoring guide

This is the agent-facing guide for producing editorial reports via
`research report <slug> --format rich-html`. If you are an LLM agent
finishing a research session, read this before writing session.md for
a report-worthy conclusion.

## What the template gives you

One embedded HTML shell (CSS + fonts + frame + legend-ready sources
block) with seven substitution points. You only author session content —
you never touch HTML/CSS yourself.

| You write | You get |
|-----------|---------|
| `## Overview` + prose | Lead-in paragraphs under the title |
| `> **aside:** …` | Editorial callout (serif italic, coral left bar) |
| `## 01 · WHY` | H2 with a coral monospace badge `01` next to the title |
| `![caption](diagrams/foo.svg)` | SVG inlined, captioned, wrapped in a `<div class="diagram">` card |
| Markdown tables | Styled comparison tables |
| Markdown `code` / fenced blocks | Technical monospace inline / block |
| Accepted sources in `session.jsonl` | Auto-generated clickable `<ul>` at the bottom |

## Conventions you must obey

### 1. Overview is mandatory

`## Overview` must have real content. A placeholder HTML comment is
rejected with `MISSING_OVERVIEW`. Write the story in 1–3 paragraphs:
what, why, conclusion. Do not put findings here — save those for the
numbered sections.

### 2. Aside — at most one, used for the hook

Convention: a blockquote whose first paragraph opens with `**aside:**`:

```markdown
> **aside:** The bitter lesson — the less you build, the more it works.
> — Gregor Zunic, Browser Use co-founder, Jan 16 2026
```

The text after `**aside:**` becomes `<p class="aside">…</p>` — serif
italic with a coral left bar. Multiple asides trigger an
`aside_multiple` warning and only the first is extracted; later ones
remain as plain blockquotes. Prefer placing the aside near the top as a
thesis statement, or before the main analysis as an epigraph.

### 3. Section numbers — `## 01 · WHY`

Structure the body into 3–6 numbered sections with the pattern
`## NN · TITLE` (space, middle-dot, space). The CLI renders
`<span class="section-num">NN</span><span>TITLE</span>`. Examples:

```markdown
## 01 · WHY
## 02 · WHAT
## 03 · HOW
## 04 · TAKEAWAYS
```

Non-numbered `## Regular heading` is left as-is — use this for
one-off sections that don't belong in the numbered sequence.

### 4. Diagrams — hand-authored SVG only

Store SVGs at `<session_dir>/diagrams/<name>.svg`. Reference them
in markdown as:

```markdown
![Fig · axis of trust](diagrams/axis.svg)
```

Rules:
- Path **must** start with `diagrams/` and end with `.svg` (case-insensitive).
- The resolved path **must** stay inside `<session_dir>/diagrams/`.
  A traversal attempt (`diagrams/../../etc/passwd.svg`) is fatal:
  `DIAGRAM_OUT_OF_BOUNDS`.
- Files larger than 512 KB degrade to `<img>` + `diagram_fallback_img` warning.
- Missing files degrade to `<img>` + warning — useful during drafting, but
  the final report should have all SVGs resolved (warnings list is
  surfaced in the envelope).
- Alt text becomes `<p class="caption">…</p>` under the diagram.

For diagram design (colors, fonts, primitives) use the `diagram-design`
skill. The template's CSS is tuned for stone+rust tokens matching the
skill defaults; if you use the skill's default palette, no extra CSS is
needed.

### 5. Sources are automatic — do not write them by hand

`research add` already maintains the `<!-- research:sources-start -->`
block in session.md, but the **report ignores that block**. The sources
section at the bottom is built from `source_accepted` events in
`session.jsonl` — the authoritative fact stream. You get:

- Ascending order by timestamp of acceptance
- `<span class="kind">…</span>` badge with the route kind
- Clickable `<a href>` linking back to the original URL

If you want a source to appear in the report, make sure it's in
the jsonl (i.e., `research add` succeeded). Editing the md sources
block has no effect on report output.

## A complete worked example

The `bu-harness` session in this repo is the canonical dogfood example
(see `/Users/zhangalex/.actionbook/research/bu-harness/` after running
the reverse-fill from `specs/research-report-templates.spec.md`). Its
`session.md` demonstrates every convention:

- 3 SVG diagrams under `diagrams/`
- Single `> **aside:**` with attribution
- 6 numbered sections (01–06)
- Markdown table comparing three stacks
- Mixed inline `code`, fenced `pre`, and clickable links

Run `research report bu-harness --format rich-html --open` to see it
render.

## Errors you might hit

| Code | What it means |
|------|---------------|
| `MISSING_OVERVIEW` | `## Overview` is empty or only HTML comments. Write at least one real paragraph. |
| `DIAGRAM_OUT_OF_BOUNDS` | A diagram path escapes the session_dir. Keep all SVGs under `diagrams/`. |
| `FORMAT_UNSUPPORTED` | Typo in `--format`. Check the `supported` list in `error.details`. |
| `FORMAT_NOT_IMPLEMENTED` | The format is declared in the spec but not yet wired up (e.g., `slides-reveal`). Use `rich-html` for now. |
| `SESSION_NOT_FOUND` | Bad slug. Run `research list` to see the session slugs you have. |
| `RENDER_FAILED` | I/O problem writing the output file. Check disk / permissions. |

Warnings (non-fatal; shown in `envelope.data.warnings`):

- `aside_multiple` — you have more than one `> **aside:** …`. Only the first
  renders as an aside card.
- `diagram_fallback_img` — one or more SVGs couldn't be inlined (missing
  file, too large, wrong extension). The report still renders with `<img>`
  tags as placeholders.
- `no_sources` — session.jsonl has no `source_accepted` events. The sources
  section shows a "(no sources accepted yet)" placeholder.

## Design principles

- **Restraint over ornament.** One coral accent — section-num badges and
  the aside left bar. Everything else is ink/muted. Don't add more
  colors via inline `<style>` in session.md; if the template is
  insufficient, update the template, not individual reports.
- **Session is canonical.** Anything worth in the report lives in
  session.md or session.jsonl. Do not author the HTML directly — it
  will not regenerate.
- **Diagrams are hand-made.** The CLI does not draw SVGs. Use the
  `diagram-design` skill or write them by hand. Save as files under
  `diagrams/`, let the CLI inline them.
- **Multiple formats, one source.** `rich-html` is the v1 target. Future
  `--format brief-md` / `slides-reveal` / `json-export` will consume
  the same session.md; your conventions carry over.
