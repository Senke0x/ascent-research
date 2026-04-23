# Testing the ascent-research hermes plugin

A 10-step ladder from shell smoke to full E2E. Each step is independent —
if an earlier step fails, the later ones won't pass. Run in order the
first time, then cherry-pick for regression.

Estimated total cost if you run 1-10 end-to-end with default (claude)
provider: **~1.5 USD** of Anthropic API tokens (dominated by steps 5, 6, 7).
Steps 0-4 and 8-10 are free.

---

## 0. Shell pre-flight (free, 30 s)

No hermes needed — confirms the install is sound before touching agents.

```bash
# Binary reachable?
ascent-research --json list | python3 -m json.tool | head -20

# Plugin symlink correct?
readlink ~/.hermes/plugins/ascent-research
# → /Users/<you>/Document/Github/ascent-research/integrations/hermes-plugin

# Preset installed?
test -f ~/.actionbook/research/presets/actionbook-only.toml && echo "preset ok"

# actionbook reachable?
actionbook --version
```

If any fails → re-run `./install.sh` or fix the underlying PATH/binary issue.

---

## 1. Plugin loads in hermes (free, 1 min)

**Start hermes**, then in-session:

```
/tools list
```

**Expect**: a section for toolset `ascent-research` (or rendered as `🔌 Ascent Research`)
listing all 16 tools: `ascent_new`, `ascent_add`, `ascent_batch`,
`ascent_add_local`, `ascent_synthesize`, `ascent_wiki_query`,
`ascent_status`, `ascent_list`, `ascent_show`, `ascent_coverage`,
`ascent_diff`, `ascent_wiki_list`, `ascent_wiki_show`,
`ascent_schema_show`, `ascent_close`, `ascent_loop_step`.

**If missing**:
```bash
# Check hermes log for plugin load errors
grep -i ascent ~/.hermes/logs/*.log | tail -20
# Or (depending on hermes version):
hermes plugins list 2>/dev/null
```

---

## 2. Smoke — read-only (free, 30 s)

**Prompt**:
```
List all my ascent-research sessions.
```

**Expect**: LLM invokes `ascent_list`, returns an Envelope:
```json
{"ok": true, "command": "research list", "data": {"sessions": [...]}}
```
No network, no browser. Just reads `~/.actionbook/ascent-research/`.

---

## 3. Single-URL fetch — actionbook path (free except browser, 1-2 min)

**Prompt**:
```
Create a new ascent-research session titled "monoio vs tokio async runtimes",
then fetch https://github.com/bytedance/monoio. Show me the session status
when done.
```

**Expect LLM calls in order**:
1. `ascent_new {topic: "monoio vs tokio async runtimes"}` → returns slug
2. `ascent_add {url: "https://github.com/bytedance/monoio", slug}` → actionbook spawns, fetches
3. `ascent_status {slug}` → 1 source accepted

**Verify actionbook really ran**:
```bash
# List actionbook sessions — should show one named research-<slug>
actionbook browser list-sessions 2>/dev/null | grep -i research

# Raw file written?
ls ~/.actionbook/ascent-research/<slug>/raw/
```

**Common failures**:
- `browser profile already owned by session ...` → `export ACTIONBOOK_BROWSER_SESSION=<id>` (README troubleshooting)
- `binary 'actionbook' not found on PATH` → install actionbook

---

## 4. Batch — concurrency (free except browser, 2-3 min)

**Prompt** (continue same session):
```
In the same session, batch-fetch these three URLs concurrently:
- https://github.com/tokio-rs/tokio
- https://github.com/smol-rs/smol
- https://github.com/async-rs/async-std

Then list what's in the wiki.
```

**Expect**:
1. `ascent_batch {urls: [3 URLs], slug, concurrency: 3}` → 3 sources accepted
2. `ascent_wiki_list {slug}` → empty or sparse (loop hasn't written pages yet)

---

## 5. Wiki query — LLM + wiki (paid, 1-2 min)

**Prompt**:
```
Based on the sources we've fetched, what are the main design differences
between monoio, tokio, smol, and async-std? Ask via the ascent wiki and
save the answer as a page called "runtime-comparison".
```

**Expect**:
- `ascent_wiki_query {question: "...", slug, save_as: "runtime-comparison", provider: "claude"}`
- Returns synthesized prose; writes `wiki/runtime-comparison.md` with `kind: analysis` frontmatter

**Verify**:
```bash
cat ~/.actionbook/ascent-research/<slug>/wiki/runtime-comparison.md
```

---

## 6. Loop step — autonomous iteration (paid, 1 min)

**Prompt**:
```
Run one autonomous-research-loop iteration on this session with max 3
actions.
```

**Expect**:
- `ascent_loop_step {slug, provider: "claude", max_actions: 3}`
- Envelope data: `iterations_run: 1`, `actions_executed: N`, coverage delta
- Session `session.jsonl` has new `LoopStarted` / `LoopStep` / `LoopEnded` events

**Verify**:
```bash
tail -5 ~/.actionbook/ascent-research/<slug>/session.jsonl | python3 -m json.tool
```

---

## 7. Synthesize (paid, 2-5 min)

**Prompt**:
```
Synthesize this session into a report.
```

**Expect**: `ascent_synthesize {slug}` produces `report.json` + `report.html`.

**Verify**:
```bash
ls -la ~/.actionbook/ascent-research/<slug>/report.*
open ~/.actionbook/ascent-research/<slug>/report.html  # macOS
```

---

## 8. Negative — hermes browser/web actually disabled (free, 30 s)

**Prompt**:
```
Open https://example.com in a browser and tell me what's there.
```

**Expect**: LLM has **no** `browser_navigate` in its tool list, so it either:
- Says "I don't have a direct browser tool — do you want me to use `ascent_add` to fetch it via actionbook?"
- Calls `ascent_add` proactively

**If the LLM succeeds with `browser_navigate` or `web_extract`**: hermes
still has those toolsets active. Revisit `~/.hermes/config.yaml` →
`platform_toolsets` and remove `browser`, `web`. Restart hermes.

---

## 9. Destructive guard (free, 30 s)

**Prompt**:
```
Close session <slug-from-step-3>.
```

**Expect**: first call returns:
```json
{"error": "ascent_close requires confirm=true — this marks the session closed."}
```
LLM should ask for confirmation, then retry with `confirm: true`. Second
call succeeds.

This validates the handler-level guard works.

---

## 10. Cleanup (free, instant)

Remove the test session to keep the store tidy:

```bash
# By CLI (not via tool — rm is intentionally not exposed):
ascent-research rm <slug> --force
```

Or delete the dir directly:
```bash
rm -rf ~/.actionbook/ascent-research/<slug>
```

---

## One-shot full-chain prompt (steps 3 + 5 + 7 combined, paid, ~5 min)

If you just want a single prompt that exercises the whole stack:

```
Start a new ascent-research session on "Rust async runtimes landscape in
2026". Fetch these sources in a batch:
- https://github.com/tokio-rs/tokio
- https://github.com/bytedance/monoio
- https://github.com/smol-rs/smol
- https://github.com/async-rs/async-std

Then ask the wiki: "What are the architectural differences between these
four runtimes? Focus on task scheduling, IO backends, and stated tradeoffs."
Save the answer as a wiki page "arch-comparison".

Finally, synthesize the session into a report and tell me where the HTML
file lives.
```

This should trigger, in order: `ascent_new` → `ascent_batch` → `ascent_wiki_query` → `ascent_synthesize`.

---

## Checklist to sign off the integration

- [ ] Step 0 all four shell checks pass
- [ ] Step 1: all 16 tools visible in `/tools list`
- [ ] Step 3: `actionbook browser list-sessions` shows `research-<slug>`
- [ ] Step 5: `wiki/runtime-comparison.md` exists and has `kind: analysis`
- [ ] Step 7: `report.html` renders in browser
- [ ] Step 8: LLM declines or redirects the raw `browser` request
- [ ] Step 9: `confirm=true` guard triggers on first `ascent_close`
