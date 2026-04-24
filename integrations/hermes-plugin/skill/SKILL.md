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

## Hard rules (READ THIS FIRST — violating these breaks reproducibility)

1. **NEVER use the `terminal` tool for HTTP** — no `curl`, no
   `wget`, no `python3 -c "import requests; ..."`, no `python3 -c
   "import urllib; ..."`. Web content acquisition is ONLY via
   `ascent_add` / `ascent_batch` / `ascent_add_local`.
2. **NEVER fall back to raw HTTP when an ascent tool times out or
   errors**. If `ascent_add` returns `ok: false`, report the error
   (`fetch_failed`, `wrong_url`, `empty_content`, etc.) and either
   (a) retry that single URL with `ascent_add {url, timeout_sec: 180}`
   or (b) move on to the next URL. DO NOT shell out to curl/requests
   to "get the content anyway" — that defeats the entire purpose of
   this skill and breaks the durable session's provenance chain.
3. **NEVER call `browser_*` or `web_*`** even if they're listed — they
   belong to a different toolset that this skill supersedes.
4. **NEVER scout via search engines** (Google/Bing/DuckDuckGo). Go
   directly to known primary URLs or to stable search endpoints
   (HN Algolia, specific subreddit top pages, author blogs).
5. **NEVER read, parse, or grep files under `~/.actionbook/ascent-research/`
   with `execute_code` / `read_file` / `search_files` / `terminal`.** That
   directory is this skill's internal session store. Direct access breaks
   provenance tracking and is the #1 cause of runaway tool loops (observed
   2026-04-24: session ran 18/120 iterations manually parsing raw fetch
   JSON and never reached `ascent_synthesize`). To inspect a session use
   `ascent_show` (full session.md), `ascent_wiki_show` / `ascent_wiki_list`
   (wiki pages), `ascent_coverage` (completeness + blockers), or
   `ascent_diff` (source usage). If a specific fact is missing from the
   wiki, ask `ascent_wiki_query` — do NOT hand-roll a Python parser over
   raw fetch JSON.
6. **Close any browser tab you opened outside the `ascent_*` toolchain.**
   `ascent_add` / `ascent_batch` already best-effort close-tab after each
   fetch — those are fine. But any tab opened via `terminal`
   (e.g. `actionbook browser new-tab ...`) or via hermes-native
   `browser_*` MUST be closed explicitly:
   `actionbook browser close-tab --session <SID> --tab <TID>`. Check
   with `actionbook browser list-tabs --session research-local`; if the
   shared session has 20+ tabs, reset the whole thing with
   `actionbook browser close --session research-local` and let the next
   `ascent_add` restart it. Excess tabs cause DOM-settle timeouts in
   `ascent_illustrate_hero` (observed 2026-04-24).

If you need to "debug why fetch failed", use `ascent_diff`,
`ascent_coverage`, or just describe the failure to the user — do not
use terminal to inspect the URL directly.

## Mental model

The user has 17 `ascent_*` tools installed as a hermes plugin (toolset
`ascent-research`). They replace hermes's native `browser_*` and
`web_*` tools for any durable research work. The plugin shells out to
the Rust `ascent-research` binary and stores sessions under
`~/.actionbook/ascent-research/<slug>/`.

## Auth (no API keys)

- Fetch (actionbook): uses local Chrome profile
- LLM steps (`wiki_query`, `loop_step`, `synthesize --bilingual`): via
  `claude` CLI subscription (cc-sdk reads Keychain token)
- Hero image (`illustrate_hero`): drives user's logged-in chatgpt.com
  session via actionbook — real GPT-Image-2, no API key

If any LLM step fails with an auth error, tell the user: "open `claude`
(or `chatgpt.com`) and refresh the session, then retry."

### Browser session (important for first-run)

By default ascent tries to auto-start `research-<slug>` for each session,
but the user's Chrome profile is usually already held by a long-lived
`research-local` actionbook session. If `ascent_batch` / `ascent_add`
returns `SESSION_NOT_FOUND: session 'research-<slug>' not found` or the
typed error `browser profile already owned by session 'research-local'`,
the fix is to reuse the existing session. The plugin handles this
internally, but when invoking the binary directly from `terminal`, export
it first:

```
export ACTIONBOOK_BROWSER_SESSION=research-local
```

Check with `actionbook browser list-sessions` before the first batch.

### Extension disconnected — daemon restart fallback (AUTOMATE)

`actionbook` extension mode depends on a Chrome-side extension pairing
with the local `actionbook daemon` over a websocket. When the daemon
says `bridge: listening, extension_connected: false`, every fetch fails
with `BRIDGE_NOT_CONNECTED` / `EXTENSION_DISCONNECTED` / an immediate
non-retryable envelope. **Your first response to this must be to
restart the daemon automatically, not to ask the user to reconnect.**

Automatic fallback sequence (run via `terminal` — this is the one
allowed use of `terminal` for an actionbook concern; hard rule 1
forbids HTTP, not daemon management):

```bash
actionbook daemon restart && sleep 3 && actionbook extension status
```

If `actionbook extension status` still reports
`extension_connected: false` after restart, THEN (and only then) tell
the user:

> Chrome extension isn't connecting. Open the Actionbook extension
> popup in Chrome and click Connect, then reply `done`.

Trigger conditions — invoke this fallback autonomously when:
- any `ascent_batch` / `ascent_add` returns `BRIDGE_NOT_CONNECTED` or a
  warning mentioning `extension_disconnected`
- `rejected_count` ≥ `accepted_count` on a single `ascent_batch` call
  AND rejections are mostly `fetch_failed` with no site-specific error
- `actionbook daemon status` or `extension status` is already queried
  and shows `extension_connected: false`

Do NOT ask the user about daemon restarts — just do them. Daemon
restart is idempotent and takes ~3s; the cost of a spurious restart is
trivial compared to stalling the whole chain waiting for manual
confirmation (observed 2026-04-24: user was blocked for 19 min of
ascent_loop_step iterations while half the sources stayed unfetched
due to a stale extension socket).

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

**Step 3 — Seed wiki + overview via loop_step (REQUIRED)**
- `ascent_loop_step {slug, provider: "claude", max_actions: 8}`
- One autonomous iteration — Claude reads SCHEMA.md + session state and
  runs up to 8 actions: `read_source`, `write_wiki_page`,
  `write_numbered_section`, etc.
- **This step cannot be skipped.** `ascent_batch` only fetches raw
  content; it does NOT populate the wiki. Without at least one
  `loop_step` call, `ascent_wiki_query` returns `WIKI_EMPTY` and
  `ascent_synthesize` returns `MISSING_OVERVIEW`.
- Tuning: `max_actions: 3` (the old default) is usually too few — Claude
  often spends them on `read_source` and never reaches
  `write_wiki_page`. Use **8** as the first-call default. Empirically
  (2026-04-24 demo): a single iter=2 CLI call at `max_actions: 8` →
  3 wiki pages + 2 numbered sections + ~1200-char overview in ~130s,
  enough for `synthesize` to succeed.
- **If coverage still blocks, call again.** The synthesize line is
  `overview_chars >= 1` AND `wiki_pages >= 1`. Most topics need **1-4
  calls** to cross it; `report_ready: true` (which also needs 3+ numbered
  sections, 1 resolved diagram, 0 unused sources) usually needs 3-5.
  Whether Claude writes `## Overview` early or late is topic-dependent
  and non-deterministic — announcement-type topics (product release,
  paper drop) tend to get an overview on call 1; "snapshot" or "feedback
  landscape" topics may delay it to call 3-4.
- **hermes-specific gotcha (iter=1 cold-start penalty):** `ascent_loop_step`
  hardcodes `iterations=1` in `cli.py:241`, so each call is a fresh
  planning turn. A fresh turn is significantly more conservative than
  staying inside one multi-iter run — 2026-04-24 measurements show two
  separate `iter=1 max=8` calls producing ~3 actions total vs. one
  `iter=2 max=8` call producing 6-8 actions. When `data.actions_executed
  <= 2` on a call, **immediately call again** without waiting for
  coverage re-check — the first call was just warming up. Expect 2-4
  calls before the session is synthesize-able, not 1.

**Step 4 — Wiki query to deepen (OPTIONAL)**
- `ascent_wiki_query {question, slug, save_as, format: "prose", provider: "claude"}`
- ONLY after Step 3 — the wiki must have pages first. Compose ONE
  synthesis question that references concrete dimensions (architecture,
  viral examples, pricing, failure modes, etc.). Don't just ask
  "summarize these sources" — be specific.
- `save_as` slug should be `<topic>-overview` or similar; this adds a
  `kind: analysis` page that `synthesize` will pull into `## Findings`.
- Skip this step if the user said "quick" / "fast" — Step 3 alone
  already produces a usable `synthesize`-able session.

**Step 5 — Synthesize**
- `ascent_synthesize {slug}`
- Produces `report.json` (canonical) + `session.md` (featured) +
  `report.html` (byproduct). Return `data.session_md` path to the user.

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
- `session.md` path
- `hero.png` path (or which error prevented it)

## User intent → which steps

| User phrasing | Steps to execute |
|---|---|
| "research X", "investigate X", "deep dive on X" | 1 → 2 → 3 (2-5 calls, until `report_ready` or no more coverage progress) → 4 → 5 → 6 |
| "quick look at X", "brief research on X" | 1 → 2 → 3 (keep calling until `overview_chars >= 1` AND `wiki_pages >= 1`, typically 1-4 calls) → 5  (skip 4 and 6) |
| "rebuild / redo research on X" | cleanup via terminal `rm -rf ~/.actionbook/ascent-research/*` → 1 → 2 → 3 → 4 → 5 → 6 |
| "add <url> to session X" | just `ascent_add` |
| "ask wiki about X" (existing session) | just `ascent_wiki_query` |
| "generate hero for session X" | just `ascent_illustrate_hero` |
| "synthesize X" | `ascent_synthesize` (+ optional 6 if user mentions image) |

Step 3 is **never** skippable — it's what populates the wiki. The only
difference between "deep dive" and "quick look" is whether Step 4 runs
and how many Step 3 calls you make.

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
- `ascent_synthesize` — session → report.json + session.md (+html byproduct)
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
| `SESSION_MD_MISSING` (illustrate_hero) | Call `ascent_synthesize` first; then retry |
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
6. NEVER read files under `~/.actionbook/ascent-research/` directly with
   `execute_code` / `read_file` / `search_files` / `terminal`. Use
   `ascent_show` / `ascent_wiki_show` / `ascent_coverage` / `ascent_diff`
   / `ascent_wiki_query` instead.
7. Close browser tabs you opened outside `ascent_*`
   (`actionbook browser close-tab --session <SID> --tab <TID>`). If the
   shared session has 20+ tabs, reset it with
   `actionbook browser close --session <SID>`.

---

## Example minimum prompt → expected automation

User types ONE line:
> "Use ascent-research to research GPT-5 capabilities and generate a hero."

You should execute automatically:

1. `ascent_new {topic: "OpenAI GPT-5 capabilities — 2026-Q2 snapshot", slug: "gpt-5-caps", tags: ["openai", "gpt-5"]}`
2. `ascent_batch {urls: ["https://openai.com/news/", "https://simonwillison.net/", "https://hn.algolia.com/?q=gpt-5", "https://news.ycombinator.com/"], slug: "gpt-5-caps"}`
3. `ascent_loop_step {slug: "gpt-5-caps", provider: "claude", max_actions: 8}`
   — inspect `data.final_coverage`; if `overview_chars < 200` or
   `wiki_pages == 0`, call `ascent_loop_step` once more with the same args.
4. `ascent_wiki_query {question: "Summarize GPT-5's capability set, benchmarks, pricing tiers, and notable limitations. Cite authors and URLs inline.", slug: "gpt-5-caps", save_as: "gpt-5-overview", format: "prose", provider: "claude"}`
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
Report: <absolute path to session.md>
Hero:   <absolute path to hero.png>   (or "skipped: <reason>")
Wiki pages written: <N>
Sources accepted: <N>
Errors: <list of code + human message, or "none">
```

Don't over-explain the process. The user watched the spinners, they
know what ran.
