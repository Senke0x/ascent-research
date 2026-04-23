# ascent-research — hermes-agent plugin

> **For a cold-start orientation** (new Claude Code session / new reader), read [`USAGE.md`](./USAGE.md) first — it covers architecture, the 16 tools, prompt templates, and troubleshooting in one file. This README focuses on install/config mechanics.

Integrates the [`ascent-research`](../..) CLI into
[hermes-agent](https://hermes-agent.nousresearch.com/) as **16 tools**.
All web fetches go through [actionbook](https://github.com/ZhangHanDong/actionbook)
browser — the plugin ships an `actionbook-only` preset that strips every
`postagent` rule, so every URL falls through to the browser fallback.

## Prerequisites

| Binary | Install |
|---|---|
| `ascent-research` | `cargo install --path packages/research --features provider-claude` (from repo root) |
| `actionbook` | See the actionbook project |
| hermes-agent | `v0.10.0+` |

LLM-backed tools (`ascent_loop_step`, `ascent_wiki_query`) reuse an
existing subscription via subprocess, not an API key:

- `provider=claude` (default) — needs `claude` (Claude Code CLI) logged
  in; `cc-sdk` reads the session token directly.
- `provider=codex` — needs `codex` CLI logged into a ChatGPT account;
  spawns `codex app-server` per call.
- `provider=fake` — no auth, returns canned responses (plumbing test only).

No `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` env var is consulted by
ascent-research in any provider path.

## Install

**One-command** (recommended — runs preflight, `cargo install`, symlink, preset copy, smoke test):

```bash
./integrations/hermes-plugin/install.sh
```

Re-runnable. Pass `--skip-build` to skip `cargo install` on subsequent runs.

**Manual** (if you want each step):

```bash
cargo install --path packages/research --features provider-claude --locked
mkdir -p ~/.hermes/plugins
ln -s "$(pwd)/integrations/hermes-plugin" ~/.hermes/plugins/ascent-research
# Preset is auto-copied on first tool call; or place it yourself:
mkdir -p ~/.actionbook/research/presets
cp integrations/hermes-plugin/presets/actionbook-only.toml ~/.actionbook/research/presets/
```

## Test

After install, follow the test-prompt ladder in [TESTING.md](./TESTING.md). Shortest verification:

```
/tools list          # inside hermes — confirm 16 ascent_* tools listed
```
then:
```
List all my ascent-research sessions.
```

## Disable hermes built-in fetch tools

Edit `~/.hermes/config.yaml` and remove `browser` + `web` from
`platform_toolsets` on each platform you run:

```yaml
platform_toolsets:
  cli:      [terminal, file, skills, todo, ascent-research]
  telegram: [terminal, file, ascent-research]
```

Or toggle in-session: `/tools disable browser` and `/tools disable web`.

The plugin also logs a warning at session start if either toolset is still
active.

## Tools

| Name | Purpose |
|---|---|
| `ascent_new` | Create a session (preset forced to `actionbook-only`) |
| `ascent_add` | Fetch a URL via actionbook browser |
| `ascent_batch` | Fetch multiple URLs concurrently |
| `ascent_add_local` | Ingest a local file or directory tree |
| `ascent_synthesize` | Render session into `report.json` + `report.html` |
| `ascent_wiki_query` | Ask a question over the session's wiki pages |
| `ascent_status` | Counts & timings |
| `ascent_list` | List all sessions (filter by tag, optional tree) |
| `ascent_show` | Print full `session.md` |
| `ascent_coverage` | Completeness stats & `report_ready` blockers |
| `ascent_diff` | Unused vs. potentially-hallucinated sources |
| `ascent_wiki_list` / `ascent_wiki_show` | Browse wiki pages |
| `ascent_schema_show` | Print `SCHEMA.md` (drives loop iterations) |
| `ascent_close` | Close a session (**requires `confirm=true`**) |
| `ascent_loop_step` | Run **one** autonomous-loop iteration |

## What's NOT exposed (and why)

| Command | Why omitted |
|---|---|
| `rm`, `wiki rm` | Destructive file deletion — LLMs should not delete user sessions |
| `resume` | LLMs address sessions by explicit slug; no global "active" toggle needed |
| `schema edit` | Launches `$EDITOR` — would hang the subprocess |
| `route`, `fork`, `series`, `report`, `wiki lint` | Parametrized duplicates (covered by `ascent_new`, `ascent_list`, `ascent_synthesize`) or rarely useful at runtime |
| `loop` (full auto) | Long task, no cancel protocol in hermes — use `ascent_loop_step` in a hermes agent loop instead |

## Environment variables

- `ASCENT_RESEARCH_BIN` — override `ascent-research` binary path
- `ACTIONBOOK_BIN` — override `actionbook` binary path
- `ACTIONBOOK_BROWSER_SESSION` — pin actionbook session ID (otherwise
  auto-named `research-<slug>`)
- `ACTIONBOOK_RESEARCH_ADD_TIMEOUT_MS` — default per-fetch timeout in ms
- `CODEX_BIN` — override `codex` binary path (only consulted when `provider=codex`)

LLM providers do **not** read API key env vars — they piggyback on
`claude` or `codex` CLI sessions. See "Prerequisites" above.

## Behavior contract

- Every handler returns a JSON string — either the raw Envelope from
  `ascent-research --json`, or `{"error": "..."}` on subprocess failures.
- `ascent_close` must be called with `confirm=true`.
- `ascent_loop_step` runs exactly **one** iteration. The hermes agent
  loop is responsible for sequencing multiple steps.
- On first `ascent_new` / `ascent_add` call, the `actionbook-only`
  preset is installed to `~/.actionbook/research/presets/` if absent.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `{"error": "binary 'ascent-research' not found on PATH"}` | Run `cargo install --path packages/research --features provider-claude` |
| `{"error": "binary 'actionbook' not found on PATH"}` | Install actionbook |
| `ascent_loop_step` → `PROVIDER_NOT_AVAILABLE` | Rebuild with `--features provider-claude` or `provider-codex`; confirm the matching CLI (`claude` / `codex`) is logged in |
| `ascent_loop_step` / `wiki_query` → `cc-sdk` auth error | Refresh the Claude Code session — open `claude` and send one message |
| `browser profile already owned by session ...` | `export ACTIONBOOK_BROWSER_SESSION=<that-id>` or close the owning session |
| Plugin doesn't appear in `/tools list` | Symlink missing / wrong name; check `~/.hermes/plugins/ascent-research/plugin.yaml` |

## Timeouts

Per-tool subprocess timeouts (seconds):

| Tool | Timeout |
|---|---|
| `ascent_synthesize` | 300 |
| `ascent_loop_step` | 240 |
| `ascent_wiki_query`, `ascent_batch` | 180 |
| `ascent_add_local` | 120 |
| all others | 60 |

Override by setting timeout at the subprocess layer — edit `cli.py`'s
`LONG_TIMEOUT_SEC` table if your workloads need more headroom.

## File layout

```
integrations/hermes-plugin/
├── plugin.yaml          # hermes plugin manifest
├── __init__.py          # register(ctx) entry
├── schemas.py           # 16 JSON schemas
├── cli.py               # subprocess argv builders + runner
├── presets/
│   └── actionbook-only.toml
└── README.md
```
