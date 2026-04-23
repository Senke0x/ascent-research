---
name: ascent-research
description: End-to-end incremental deep-research workflow via hermes plugin tools (17 `ascent_*` tools). All web fetches go through actionbook browser (zero API keys for fetching). LLM-backed steps reuse the user's Claude Code CLI subscription (no OPENAI/ANTHROPIC/FAL API keys). Hero cover image generation drives the user's logged-in ChatGPT session via actionbook to produce real GPT-Image-2 output. Activate this skill when the user asks to research, investigate, deep-dive, explore, survey, or compare any topic, or explicitly mentions ascent-research.
triggers: research, deep research, deep-dive, deep dive, investigate, explore, survey, literature review, compare, analyze topic, build report, ascent-research, ascent research, redo research, rebuild research, rebuild report
force_tool_turns: 20
---

# ascent-research — canonical workflow skill

Scope: how to turn a one-line user request like *"research X"* or
*"use ascent-research to investigate Y"* into the full 6-step chain
automatically, without forcing the user to name each tool by hand.

## Mental model

The user has 17 `ascent_*` tools installed as a hermes plugin (toolset
`ascent-research`). They replace hermes's native `browser_*` and
`web_*` tools for any durable research work. The plugin shells out to
the Rust `ascent-research` binary and stores sessions under
`~/.actionbook/ascent-research/<slug>/`.

Do NOT call `browser_*` or `web_*` when this skill is active. Do NOT
scout via search engines first unless the user explicitly asked.

## Auth (no API keys)

- Fetch (actionbook): uses local Chrome profile
- LLM steps (`wiki_query`, `loop_step`, `synthesize --bilingual`): via
  `claude` CLI subscription (cc-sdk reads Keychain token)
- Hero image (`illustrate_hero`): drives user's logged-in chatgpt.com
  session via actionbook — real GPT-Image-2, no API key

If any LLM step fails with an auth error, tell the user: "open `claude`
(or `chatgpt.com`) and refresh the session, then retry."

---

## Canonical 6-step chain

When the user invokes a research trigger, execute in order:

**Step 1 — Create or resume session**
- `ascent_new {topic, slug?, tags?, from_slug?}` for new work
- `ascent_list {tag?}` first if user referenced an existing session
- Use a descriptive *topic* (full sentence, not just keywords) — this
  seeds the hero image prompt later. Bad: `"gpt5"`. Good:
  `"OpenAI GPT-5 Q2 2026 — capabilities, benchmark deltas, reception"`.

**Step 2 — Batch-fetch primary sources**
- `ascent_batch {urls: [...], slug, concurrency?: 4}`
- Pick 5-10 stable landing pages / search URLs. Do NOT fabricate
  specific article slugs. Safe stable URLs:
  - Vendor news indexes (`openai.com/news/`, `anthropic.com/news`)
  - Author blogs (`simonwillison.net`, etc.)
  - HN Algolia search (`hn.algolia.com/?q=<topic>`)
  - Subreddit top-of-week (`old.reddit.com/r/<sub>/top/?t=week`)
  - arXiv subject listing (`arxiv.org/list/cs.AI/new`)
- If the user supplied specific URLs, use those.

**Step 3 — Wiki query with a focused question**
- `ascent_wiki_query {question, slug, save_as, format: "prose", provider: "claude"}`
- Compose ONE synthesis question that references concrete dimensions
  (architecture, viral examples, pricing, failure modes, etc.). Don't
  just ask "summarize these sources" — be specific.
- `save_as` slug should be `<topic>-overview` or similar.

**Step 4 — Loop step to patch gaps**
- `ascent_loop_step {slug, provider: "claude", max_actions: 3}`
- Single autonomous iteration — Claude reads SCHEMA.md + session state
  and picks next actions (may fetch more sources, write wiki pages).
- Skip this step when the user explicitly said "quick" or "fast".

**Step 5 — Synthesize**
- `ascent_synthesize {slug}`
- Produces `report.json` (canonical) + `report-brief.md` (featured) +
  `report.html` (byproduct). Return `data.report_md` path to the user.

**Step 6 — Hero cover image (optional by request)**
- `ascent_illustrate_hero {slug}` — Apple-style editorial cover via
  ChatGPT/GPT-Image-2.
- On `NOT_LOGGED_IN`: tell user plainly "open chatgpt.com and log in".
- On `RATE_LIMITED` / `CONTENT_POLICY` / `IMAGE_NOT_PRODUCED`: retry
  ONCE with `use_flux_fallback: true`.
- Default behavior: run unless the user said "no image / skip cover /
  md only".

Finally, tell the user:
- slug
- `report-brief.md` path
- `hero.png` path (or which error prevented it)

## User intent → which steps

| User phrasing | Steps to execute |
|---|---|
| "research X", "investigate X", "deep dive on X" | 1 → 2 → 3 → 4 → 5 → 6 |
| "quick look at X", "brief research on X" | 1 → 2 → 3 → 5  (skip 4 and 6) |
| "rebuild / redo research on X" | cleanup via terminal `rm -rf ~/.actionbook/ascent-research/*` → 1 → 2 → 3 → 4 → 5 → 6 |
| "add <url> to session X" | just `ascent_add` |
| "ask wiki about X" (existing session) | just `ascent_wiki_query` |
| "generate hero for session X" | just `ascent_illustrate_hero` |
| "synthesize X" | `ascent_synthesize` (+ optional 6 if user mentions image) |

---

## Tool reference (17 tools, toolset `ascent-research`)

### Session lifecycle
- `ascent_new` — new session, forces `actionbook-only` preset
- `ascent_list` — list sessions, `--tag` filter, `--tree` hierarchy
- `ascent_show` — print full session.md
- `ascent_status` — counts + timings + closed_at
- `ascent_close` — **requires `confirm: true`** — marks closed (files preserved)

### Fetch
- `ascent_add` — single URL via actionbook
- `ascent_batch` — concurrent fetch (default 4 workers)
- `ascent_add_local` — ingest local file/directory tree (globs, size caps)

### Analysis
- `ascent_coverage` — fact-completeness + `report_ready` blockers
- `ascent_diff` — unused vs. potentially-hallucinated sources

### Wiki
- `ascent_wiki_list` — list wiki pages with slug+bytes+kind
- `ascent_wiki_show` — read one page
- `ascent_wiki_query` — ask question over wiki, optional `save_as`
- `ascent_schema_show` — print user-authored SCHEMA.md

### Generation (featured: MD, byproduct: HTML)
- `ascent_synthesize` — session → report.json + report-brief.md (+html byproduct)
- `ascent_illustrate_hero` — Apple-style hero via ChatGPT/GPT-Image-2, prepends `![hero]` to MD
- `ascent_loop_step` — ONE autonomous iteration (not full loop)

### Intentionally NOT exposed
- `rm`, `wiki rm`, `resume`, `schema edit`, full auto `loop` — use
  terminal tool for destructive/interactive operations, or write a
  dedicated slash command later.

---

## Typed error codes (fail-loud)

When a tool returns `ok: false` with a typed `error.code`, handle:

| Code | Recovery |
|---|---|
| `NOT_LOGGED_IN` (illustrate_hero) | Ask user to open chatgpt.com in Chrome and log in, then retry this one tool |
| `RATE_LIMITED` (illustrate_hero) | Retry once with `use_flux_fallback: true` |
| `CONTENT_POLICY` (illustrate_hero) | Retry once with `use_flux_fallback: true`, OR ask user for a `prompt_override` |
| `IMAGE_NOT_PRODUCED` (illustrate_hero) | Retry once with `use_flux_fallback: true`; if still fails, tell user to inspect `images/hero-debug.html` |
| `PROMPT_DRAFT_FAILED` (illustrate_hero) | Tell user to run `claude` interactively once to refresh session, then retry |
| `PROVIDER_NOT_AVAILABLE` (loop_step / wiki_query) | Confirm binary was built with `--features provider-claude`; tell user to run `claude` once if session stale |
| `REPORT_MD_MISSING` (illustrate_hero) | Call `ascent_synthesize` first; then retry |
| `browser profile already owned` (any actionbook step) | `export ACTIONBOOK_BROWSER_SESSION=<holder>` in the relevant tool, or close the owning session |

**Do NOT silently swallow errors.** Surface the code + message to the
user before any retry decision the user might want to override.

---

## Hard rules

1. NEVER use `browser_*` or `web_*` tools when this skill is active —
   they are either disabled in config or should be avoided. Always
   prefer `ascent_add` / `ascent_batch`.
2. NEVER call `ascent_close` without `confirm: true`.
3. NEVER fabricate specific article URLs. Stick to stable landing
   pages, vendor news indexes, search endpoints, or URLs the user
   explicitly supplied.
4. NEVER call the full auto `loop` — it isn't exposed for good reason.
   Use `ascent_loop_step` and let your own agent loop drive multiple
   steps if the user asks for more depth.
5. For destructive cleanup (`rm -rf ~/.actionbook/ascent-research/*`),
   use the `terminal` tool and announce it clearly first.

---

## Example minimum prompt → expected automation

User types ONE line:
> "Use ascent-research to research GPT-5 capabilities and generate a hero."

You should execute automatically:

1. `ascent_new {topic: "OpenAI GPT-5 capabilities — 2026-Q2 snapshot", slug: "gpt-5-caps", tags: ["openai", "gpt-5"]}`
2. `ascent_batch {urls: ["https://openai.com/news/", "https://simonwillison.net/", "https://hn.algolia.com/?q=gpt-5", "https://news.ycombinator.com/"], slug: "gpt-5-caps"}`
3. `ascent_wiki_query {question: "Summarize GPT-5's capability set, benchmarks, pricing tiers, and notable limitations from the fetched sources. Cite authors and URLs inline.", slug: "gpt-5-caps", save_as: "gpt-5-overview", format: "prose", provider: "claude"}`
4. `ascent_loop_step {slug: "gpt-5-caps", provider: "claude", max_actions: 3}`
5. `ascent_synthesize {slug: "gpt-5-caps"}`
6. `ascent_illustrate_hero {slug: "gpt-5-caps"}`
7. Report back: slug, MD path, hero.png path.

Only pause to ask the user when:
- Topic has multiple well-known meanings (e.g., "Apollo" → NASA? Greek god? dev framework?)
- A tool returns an error code that has no automated recovery
- The user explicitly said "ask me before <step>"

---

## Output convention

When reporting back, use this format:

```
Session: <slug>
Report: <absolute path to report-brief.md>
Hero:   <absolute path to hero.png>   (or "skipped: <reason>")
Wiki pages written: <N>
Sources accepted: <N>
Errors: <list of code + human message, or "none">
```

Don't over-explain the process. The user watched the spinners, they
know what ran.
