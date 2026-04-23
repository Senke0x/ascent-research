"""ascent-research — hermes-agent plugin.

Registers 16 tools that shell out to the `ascent-research` CLI. All web
fetches are routed through actionbook browser via the auto-installed
`actionbook-only` preset, so hermes's built-in `browser` and `web`
toolsets should be disabled (remove them from `platform_toolsets` in
`~/.hermes/config.yaml`).

Entry point: `register(ctx)` — called once at plugin load time by
hermes's PluginManager.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .cli import run_tool
from .schemas import ALL_SCHEMAS

logger = logging.getLogger(__name__)

TOOLSET = "ascent-research"
PLUGIN_DIR = Path(__file__).resolve().parent


def _make_handler(name: str):
    def handler(args: dict, **_kw) -> str:
        return run_tool(name, args or {}, PLUGIN_DIR)

    handler.__name__ = f"ascent_{name}_handler"
    return handler


def _warn_builtin_fetch_active(**_kw) -> None:
    """Log a warning if hermes's built-in browser/web toolsets are still on."""
    try:
        from tools.registry import registry  # type: ignore
    except Exception:
        return
    clashing: list[str] = []
    try:
        for tool_name in registry.list_tool_names():
            entry = registry.get_entry(tool_name)
            if entry is not None and entry.toolset in ("browser", "web"):
                clashing.append(tool_name)
    except Exception as exc:
        logger.debug("ascent-research: registry introspection failed: %s", exc)
        return
    if clashing:
        logger.warning(
            "ascent-research: %d hermes built-in fetch tools still active "
            "in 'browser'/'web' toolsets. Remove those toolsets from "
            "platform_toolsets in ~/.hermes/config.yaml for consistent "
            "routing through actionbook.",
            len(clashing),
        )


def register(ctx) -> None:
    """Hermes plugin entry point."""
    for schema in ALL_SCHEMAS:
        name = schema["name"]
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=schema,
            handler=_make_handler(name),
            description=schema.get("description", ""),
            emoji="🔬",
        )

    try:
        ctx.register_hook("on_session_start", _warn_builtin_fetch_active)
    except Exception as exc:
        logger.debug("ascent-research: hook registration failed: %s", exc)

    logger.info(
        "ascent-research plugin loaded: %d tools registered in toolset '%s'.",
        len(ALL_SCHEMAS),
        TOOLSET,
    )
