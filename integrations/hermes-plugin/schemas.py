"""JSON schemas for the 16 hermes tools exposed by the ascent-research plugin.

Each schema follows hermes's tool contract: name + description + JSON Schema
under 'parameters'. Handlers shell out to the ascent-research CLI and relay
its Envelope JSON verbatim.
"""

from __future__ import annotations

NEW = {
    "name": "ascent_new",
    "description": (
        "Create a new ascent-research session. The session is forced to use "
        "the 'actionbook-only' preset so every subsequent add/batch fetch "
        "routes through actionbook browser. Returns the session slug."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Research topic / session title."},
            "slug": {"type": "string", "description": "Optional custom slug (lowercase-hyphenated). Auto-generated if omitted."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags for grouping sessions."},
            "from_slug": {"type": "string", "description": "Optional parent session slug to fork from (copies ## Overview → ## Context)."},
        },
        "required": ["topic"],
    },
}

ADD = {
    "name": "ascent_add",
    "description": (
        "Fetch a URL via actionbook browser, run the smell test, attach it "
        "to the session as a source. Returns the acceptance decision, "
        "observed URL, and stored raw file index."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "HTTP/HTTPS URL to fetch."},
            "slug": {"type": "string", "description": "Session slug. Defaults to active session."},
            "timeout_sec": {"type": "integer", "description": "Fetch timeout in seconds (default 30)."},
            "readable": {"type": "boolean", "description": "Use readability extraction. Default true for most pages."},
        },
        "required": ["url"],
    },
}

BATCH = {
    "name": "ascent_batch",
    "description": (
        "Fetch multiple URLs concurrently via actionbook, smell-test each, "
        "and attach accepted sources. Failed URLs are logged as rejected."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to fetch concurrently."},
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
            "concurrency": {"type": "integer", "description": "Worker threads 1-16 (default 4)."},
            "timeout_sec": {"type": "integer", "description": "Per-fetch timeout in seconds."},
        },
        "required": ["urls"],
    },
}

ADD_LOCAL = {
    "name": "ascent_add_local",
    "description": (
        "Ingest a local file or directory tree as sources. Walks the path, "
        "applies optional include/exclude globs (prefix ! to exclude), "
        "enforces per-file and per-walk size caps."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute, relative (./x), home-relative (~/x), or file:// path."},
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
            "globs": {"type": "array", "items": {"type": "string"}, "description": "Glob patterns. Prefix with ! to exclude. Omit for all files."},
            "max_file_bytes": {"type": "integer", "description": "Per-file cap (default 262144)."},
            "max_total_bytes": {"type": "integer", "description": "Total walk cap (default 2097152)."},
        },
        "required": ["path"],
    },
}

SYNTHESIZE = {
    "name": "ascent_synthesize",
    "description": (
        "Synthesize the session into a markdown report. Chains: Rust "
        "`synthesize` → `report --format brief-md`. Produces "
        "report.json (canonical data), report-brief.md (FEATURED "
        "output — pass this path to the user / to ascent_illustrate_hero), "
        "and report.html (byproduct, not featured). Long-running; costs "
        "LLM tokens only if 'bilingual' is true."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
            "bilingual": {"type": "boolean", "description": "Render Chinese translations alongside English. Requires a working Claude provider (via logged-in `claude` CLI)."},
            "no_render": {"type": "boolean", "description": "Skip HTML rendering; produce report.json only. Markdown render still runs."},
        },
    },
}

ILLUSTRATE_HERO = {
    "name": "ascent_illustrate_hero",
    "description": (
        "Generate a single Apple-style hero cover image for a synthesized "
        "session by driving the user's ChatGPT session via actionbook "
        "(real GPT-Image-2, no API key — uses the user's logged-in "
        "browser profile). Prepends `![hero](images/hero.png)` to "
        "report-brief.md on success. "
        "PREREQUISITE: ascent_synthesize has already run for this slug. "
        "PREREQUISITE: user is logged into chatgpt.com in the Chrome "
        "profile actionbook drives. "
        "POLICY: always overwrites any existing hero. Fails LOUDLY with "
        "typed error codes — the markdown is never mutated until a valid "
        "image is on disk, so it is safe to retry by simply calling this "
        "tool again."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Session slug. Must already be synthesized."},
            "prompt_override": {"type": "string", "description": "Skip Claude drafting and use this prompt verbatim (Apple style suffix still auto-appended)."},
            "use_flux_fallback": {"type": "boolean", "description": "On ChatGPT-path failure, retry via hermes FLUX 2 Pro (requires running inside a hermes process). Default false — prefer fail-loud."},
            "dry_run": {"type": "boolean", "description": "Draft the prompt (via Claude if no override) and return a preview; do NOT drive the browser."},
        },
        "required": ["slug"],
    },
}

WIKI_QUERY = {
    "name": "ascent_wiki_query",
    "description": (
        "Ask a question over the session's wiki pages. Optionally save "
        "the answer as a new analysis wiki page via 'save_as'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
            "save_as": {"type": "string", "description": "Save answer as wiki/<slug>.md with kind=analysis."},
            "format": {"type": "string", "enum": ["prose", "comparison", "table"], "description": "Answer shape."},
            "provider": {"type": "string", "enum": ["fake", "claude", "codex"], "description": "LLM provider (default claude)."},
        },
        "required": ["question"],
    },
}

STATUS = {
    "name": "ascent_status",
    "description": "Show counts and timings for a session: sources accepted/rejected, wiki pages, coverage state.",
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
        },
    },
}

LIST = {
    "name": "ascent_list",
    "description": "List all ascent-research sessions on disk. Filter by tag or show as parent→child tree.",
    "parameters": {
        "type": "object",
        "properties": {
            "tag": {"type": "string"},
            "tree": {"type": "boolean", "description": "Show parent→child hierarchy as ASCII tree."},
        },
    },
}

SHOW = {
    "name": "ascent_show",
    "description": "Print the full session.md of a session (topic, overview, context, sections, sources).",
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string"},
        },
        "required": ["slug"],
    },
}

COVERAGE = {
    "name": "ascent_coverage",
    "description": "Fact-based completeness stats + report_ready blockers for a session.",
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
        },
    },
}

DIFF = {
    "name": "ascent_diff",
    "description": "List sources fetched-but-uncited (unused) and body-but-unfetched (potentially hallucinated).",
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
            "unused_only": {"type": "boolean"},
        },
    },
}

WIKI_LIST = {
    "name": "ascent_wiki_list",
    "description": "List every wiki page in a session with slug, bytes, frontmatter kind.",
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
        },
    },
}

WIKI_SHOW = {
    "name": "ascent_wiki_show",
    "description": "Print one wiki page's markdown to stdout.",
    "parameters": {
        "type": "object",
        "properties": {
            "page": {"type": "string", "description": "Page slug (filename without .md)."},
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
        },
        "required": ["page"],
    },
}

SCHEMA_SHOW = {
    "name": "ascent_schema_show",
    "description": "Print the session's SCHEMA.md — the research-schema prompt that drives loop iterations.",
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
        },
    },
}

CLOSE = {
    "name": "ascent_close",
    "description": (
        "DESTRUCTIVE: Mark a session closed (files preserved, but no "
        "further adds/loops). Requires confirm=true to guard against "
        "accidental invocation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
            "confirm": {"type": "boolean", "description": "Must be true to execute."},
        },
        "required": ["confirm"],
    },
}

LOOP_STEP = {
    "name": "ascent_loop_step",
    "description": (
        "Run ONE iteration of the autonomous research loop: read SCHEMA.md "
        "+ session state, pick next actions, execute them. Does NOT loop — "
        "call again for the next step. Uses the configured LLM provider "
        "(default: claude, via the logged-in `claude` CLI — no API key "
        "needed). Requires the binary built with --features provider-claude "
        "or --features provider-codex."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Session slug. Defaults to active."},
            "provider": {"type": "string", "enum": ["claude", "codex", "fake"], "description": "LLM provider for this step. Default claude."},
            "max_actions": {"type": "integer", "description": "Cap actions executed in this step."},
            "dry_run": {"type": "boolean", "description": "Don't execute actions; print plan only."},
        },
    },
}

ALL_SCHEMAS = [
    NEW,
    ADD,
    BATCH,
    ADD_LOCAL,
    SYNTHESIZE,
    ILLUSTRATE_HERO,
    WIKI_QUERY,
    STATUS,
    LIST,
    SHOW,
    COVERAGE,
    DIFF,
    WIKI_LIST,
    WIKI_SHOW,
    SCHEMA_SHOW,
    CLOSE,
    LOOP_STEP,
]
