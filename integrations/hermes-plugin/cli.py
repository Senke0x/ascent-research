"""Subprocess wrapper for the ascent-research CLI.

Each handler builds argv from the tool's args dict, runs the binary with
`--json` (so stdout is a stable Envelope JSON), and relays it back to
hermes verbatim per the handler contract (return value must be a str).

Errors are wrapped as `{"error": "..."}` JSON strings.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

PRESET_NAME = "actionbook-only"
PRESET_DST = Path.home() / ".actionbook" / "research" / "presets" / f"{PRESET_NAME}.toml"

DEFAULT_TIMEOUT_SEC = 60
# These are the Python-subprocess wall-clock ceilings. They MUST be larger
# than whatever ACTIONBOOK_RESEARCH_ADD_TIMEOUT_MS the Rust binary is using
# internally (currently 120000ms in ~/.hermes/.env) — otherwise Python will
# kill the subprocess before Rust has a chance to finish or report.
LONG_TIMEOUT_SEC = {
    "ascent_synthesize": 600,           # render pass + bilingual translate
    "ascent_illustrate_hero": 420,       # 4-click + 180s image wait + download
    "ascent_loop_step": 300,             # single iteration can fetch more sources
    "ascent_wiki_query": 240,            # LLM prose generation
    "ascent_add": 150,                   # one URL, 120s Rust budget + 30s buffer
    "ascent_batch": 360,                 # 4 concurrency × 120s worst case + buffer
    "ascent_add_local": 180,             # filesystem walk + smell tests
}


def _binary() -> str:
    return os.environ.get("ASCENT_RESEARCH_BIN", "ascent-research")


def _error(message: str, **extra) -> str:
    return json.dumps({"error": message, **extra})


def _ensure_preset(plugin_dir: Path) -> None:
    """Copy the bundled actionbook-only preset into ~/.actionbook/research/presets/."""
    if PRESET_DST.exists():
        return
    src = plugin_dir / "presets" / f"{PRESET_NAME}.toml"
    if not src.exists():
        logger.warning("ascent-research: bundled preset missing at %s", src)
        return
    try:
        PRESET_DST.parent.mkdir(parents=True, exist_ok=True)
        PRESET_DST.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("ascent-research: installed preset → %s", PRESET_DST)
    except OSError as exc:
        logger.warning("ascent-research: failed to install preset: %s", exc)


def _run(argv: list[str], timeout: int) -> str:
    bin_name = argv[0]
    if shutil.which(bin_name) is None:
        return _error(f"binary '{bin_name}' not found on PATH")
    try:
        out = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _error(f"timeout after {timeout}s", argv=argv)
    except OSError as exc:
        return _error(f"subprocess failed: {exc}", argv=argv)

    stdout = (out.stdout or "").strip()
    if out.returncode == 0:
        if not stdout:
            return json.dumps({"ok": True})
        if stdout.startswith(("{", "[")):
            return stdout
        # Some subcommands (e.g. `show`) print raw markdown even with --json —
        # wrap so the handler contract (JSON string) holds.
        return json.dumps({"ok": True, "data": {"stdout": stdout}})
    # Non-zero: the binary still prints a JSON envelope on stdout for failures.
    if stdout.startswith("{"):
        return stdout
    stderr = (out.stderr or "").strip()
    return _error(stderr or stdout or f"exit {out.returncode}", code=out.returncode)


# ────────────────── argv builders (one per tool) ──────────────────

def _argv_new(a: dict) -> list[str]:
    argv = [_binary(), "--json", "new", a["topic"], "--preset", PRESET_NAME]
    if a.get("slug"):
        argv += ["--slug", a["slug"]]
    for tag in a.get("tags") or []:
        argv += ["--tag", str(tag)]
    if a.get("from_slug"):
        argv += ["--from", a["from_slug"]]
    return argv


def _argv_add(a: dict) -> list[str]:
    argv = [_binary(), "--json", "add", a["url"]]
    if a.get("slug"):
        argv += ["--slug", a["slug"]]
    if a.get("timeout_sec") is not None:
        argv += ["--timeout", str(int(a["timeout_sec"]) * 1000)]
    if a.get("readable") is True:
        argv += ["--readable"]
    elif a.get("readable") is False:
        argv += ["--no-readable"]
    return argv


def _argv_batch(a: dict) -> list[str]:
    argv = [_binary(), "--json", "batch"]
    argv += [str(u) for u in a["urls"]]
    if a.get("slug"):
        argv += ["--slug", a["slug"]]
    if a.get("concurrency") is not None:
        argv += ["--concurrency", str(int(a["concurrency"]))]
    if a.get("timeout_sec") is not None:
        argv += ["--timeout", str(int(a["timeout_sec"]) * 1000)]
    return argv


def _argv_add_local(a: dict) -> list[str]:
    argv = [_binary(), "--json", "add-local", a["path"]]
    if a.get("slug"):
        argv += ["--slug", a["slug"]]
    for g in a.get("globs") or []:
        argv += ["--glob", str(g)]
    if a.get("max_file_bytes") is not None:
        argv += ["--max-file-bytes", str(int(a["max_file_bytes"]))]
    if a.get("max_total_bytes") is not None:
        argv += ["--max-total-bytes", str(int(a["max_total_bytes"]))]
    return argv


def _argv_synthesize(a: dict) -> list[str]:
    argv = [_binary(), "--json", "synthesize"]
    if a.get("slug"):
        argv.append(a["slug"])
    if a.get("no_render"):
        argv.append("--no-render")
    if a.get("bilingual"):
        argv.append("--bilingual")
    return argv


def _argv_wiki_query(a: dict) -> list[str]:
    argv = [_binary(), "--json", "wiki", "query", a["question"]]
    if a.get("slug"):
        argv += ["--slug", a["slug"]]
    if a.get("save_as"):
        argv += ["--save-as", a["save_as"]]
    if a.get("format"):
        argv += ["--format", a["format"]]
    if a.get("provider"):
        argv += ["--provider", a["provider"]]
    return argv


def _argv_status(a: dict) -> list[str]:
    argv = [_binary(), "--json", "status"]
    if a.get("slug"):
        argv.append(a["slug"])
    return argv


def _argv_list(a: dict) -> list[str]:
    argv = [_binary(), "--json", "list"]
    if a.get("tag"):
        argv += ["--tag", a["tag"]]
    if a.get("tree"):
        argv.append("--tree")
    return argv


def _argv_show(a: dict) -> list[str]:
    return [_binary(), "--json", "show", a["slug"]]


def _argv_coverage(a: dict) -> list[str]:
    argv = [_binary(), "--json", "coverage"]
    if a.get("slug"):
        argv.append(a["slug"])
    return argv


def _argv_diff(a: dict) -> list[str]:
    argv = [_binary(), "--json", "diff"]
    if a.get("slug"):
        argv.append(a["slug"])
    if a.get("unused_only"):
        argv.append("--unused-only")
    return argv


def _argv_wiki_list(a: dict) -> list[str]:
    argv = [_binary(), "--json", "wiki", "list"]
    if a.get("slug"):
        argv += ["--slug", a["slug"]]
    return argv


def _argv_wiki_show(a: dict) -> list[str]:
    argv = [_binary(), "--json", "wiki", "show", a["page"]]
    if a.get("slug"):
        argv += ["--slug", a["slug"]]
    return argv


def _argv_schema_show(a: dict) -> list[str]:
    argv = [_binary(), "--json", "schema", "show"]
    if a.get("slug"):
        argv += ["--slug", a["slug"]]
    return argv


def _argv_close(a: dict) -> list[str]:
    argv = [_binary(), "--json", "close"]
    if a.get("slug"):
        argv.append(a["slug"])
    return argv


def _argv_loop_step(a: dict) -> list[str]:
    argv = [_binary(), "--json", "loop"]
    if a.get("slug"):
        argv.append(a["slug"])
    argv += ["--iterations", "1", "--provider", a.get("provider", "claude")]
    if a.get("max_actions") is not None:
        argv += ["--max-actions", str(int(a["max_actions"]))]
    if a.get("dry_run"):
        argv.append("--dry-run")
    return argv


_BUILDERS: dict[str, Callable[[dict], list[str]]] = {
    "ascent_new": _argv_new,
    "ascent_add": _argv_add,
    "ascent_batch": _argv_batch,
    "ascent_add_local": _argv_add_local,
    "ascent_synthesize": _argv_synthesize,
    "ascent_wiki_query": _argv_wiki_query,
    "ascent_status": _argv_status,
    "ascent_list": _argv_list,
    "ascent_show": _argv_show,
    "ascent_coverage": _argv_coverage,
    "ascent_diff": _argv_diff,
    "ascent_wiki_list": _argv_wiki_list,
    "ascent_wiki_show": _argv_wiki_show,
    "ascent_schema_show": _argv_schema_show,
    "ascent_close": _argv_close,
    "ascent_loop_step": _argv_loop_step,
}


def run_tool(name: str, args: dict, plugin_dir: Path) -> str:
    """Dispatch a hermes tool call to the ascent-research binary."""
    _ensure_preset(plugin_dir)

    if name == "ascent_close" and not args.get("confirm"):
        return _error("ascent_close requires confirm=true — this marks the session closed.")

    if name == "ascent_synthesize":
        return _handle_synthesize(args)

    if name == "ascent_illustrate_hero":
        return _handle_illustrate_hero(args)

    builder = _BUILDERS.get(name)
    if builder is None:
        return _error(f"unknown tool '{name}'")

    try:
        argv = builder(args)
    except KeyError as exc:
        return _error(f"missing required parameter: {exc}")
    except (TypeError, ValueError) as exc:
        return _error(f"invalid parameter: {exc}")

    return _run(argv, LONG_TIMEOUT_SEC.get(name, DEFAULT_TIMEOUT_SEC))


def _handle_synthesize(args: dict) -> str:
    """Run Rust `synthesize` and expose `session.md` as the featured markdown.

    Previously chained to `report --format brief-md` to produce a derived
    short summary — that turned out to lose nuance and the downstream
    `ascent_illustrate_hero` step gets better material reading the full
    `session.md` directly. Rust synthesize already writes report.json and
    report.html; session.md was authored by the loop all along and lives
    at a stable path. So we just surface that path in the envelope.
    """
    synth_argv = _argv_synthesize(args)
    synth_raw = _run(synth_argv, LONG_TIMEOUT_SEC.get("ascent_synthesize", 300))
    try:
        synth_env = json.loads(synth_raw)
    except json.JSONDecodeError:
        return synth_raw  # not JSON — shouldn't happen, but pass through

    if not synth_env.get("ok"):
        return synth_raw

    slug = args.get("slug") or (synth_env.get("context") or {}).get("session")
    if slug:
        session_md = Path.home() / ".actionbook" / "ascent-research" / slug / "session.md"
        if session_md.exists():
            synth_env.setdefault("data", {})["session_md"] = str(session_md)
    return json.dumps(synth_env)


def _handle_illustrate_hero(args: dict) -> str:
    """Run the actionbook→ChatGPT hero image workflow, fail loudly."""
    try:
        from .illustrate import generate_hero, HeroError
    except ImportError:
        # Allow standalone import (e.g. py_compile in the plugin dir with no package parent).
        from illustrate import generate_hero, HeroError  # type: ignore

    try:
        result = generate_hero(args or {})
        return json.dumps(result)
    except HeroError as exc:
        return json.dumps(exc.as_envelope())
    except Exception as exc:
        logger.exception("ascent_illustrate_hero unexpected failure")
        return json.dumps(
            {
                "ok": False,
                "command": "ascent_illustrate_hero",
                "error": {
                    "code": "UNEXPECTED",
                    "message": str(exc),
                    "details": {"type": type(exc).__name__},
                },
            }
        )
