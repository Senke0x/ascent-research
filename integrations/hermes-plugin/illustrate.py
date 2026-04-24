"""Hero cover image generation workflow.

Drives actionbook to navigate to ChatGPT, prompts it to produce a
GPT-Image-2 illustration keyed to the research session's `session.md`,
and downloads the result to `<slug>/images/hero.png`. Fails loud with
typed error codes so the LLM/user can retry cleanly. Does NOT mutate
any markdown — session.md stays purely authored content; if the user
wants to reference hero.png they can add their own markdown link.

Auth model: this workflow **does not** read any API key. It piggybacks
on the user's existing ChatGPT session in the same Chrome profile that
actionbook drives (see USAGE.md §1). Losing the session is a
NOT_LOGGED_IN error that the user resolves by re-logging in their
browser.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)


# ─────────────────────────── Constants ───────────────────────────

AB_SESSION = "ascent-hero-gen"

APPLE_STYLE_SUFFIX = (
    "Style: Apple keynote info poster. 9:16 vertical composition. "
    "Clean matte background (soft off-white to pale slate gradient, ONE "
    "muted accent color such as bronze OR teal, never both). Tight, "
    "information-dense layout — like an Apple product feature page "
    "compressed onto one portrait poster: large bold headline at top "
    "(2-6 words, SF-Pro-Display-style sans-serif), short subhead line "
    "below, then a dense vertical stack or tight grid of 4-6 small "
    "modular panels (each panel = a section title + a one-line "
    "takeaway, with a small numeric label or icon). Typography is the "
    "primary design element; visual accents are geometric (circles, "
    "arcs, thin lines) rather than photographic. Tight kerning, clear "
    "hierarchy, plenty of negative space between panels. NO logos, NO "
    "photorealistic human faces, NO stock imagery."
)

SELECTORS = {
    "prompt_textarea": "#prompt-textarea",
    # The "+" attach/tools button next to the composer. Verified 2026-04-23.
    "composer_plus_btn": '[data-testid="composer-plus-btn"]',
    # XPath for the "Create image" menu item (role="menuitemradio"). Only
    # appears while the plus menu is open — clicked in the same actionbook
    # subprocess call as composer_plus_btn via multi-selector syntax, so the
    # menu doesn't have a chance to close between clicks.
    "menu_create_image": '//div[@role="menuitemradio" and descendant::div[text()="Create image"]]',
    # Confirms we're in image-generation mode: composer placeholder flips to
    # "Describe or edit an image" after Create image is clicked.
    "prompt_textarea_image_mode": '#prompt-textarea[data-placeholder*="image" i], textarea[data-placeholder*="image" i], textarea[placeholder*="image" i]',
    # Aspect-ratio chooser (only visible while Image mode is active).
    "aspect_ratio_btn": '[aria-label="Choose image aspect ratio"]',
    # Image response: ChatGPT wraps the generated image with alt starting
    # with "Generated image:". Much more reliable than the assistant-role
    # wrapper (which isn't used for image-mode responses).
    "assistant_latest": "[data-message-author-role='assistant']:last-of-type",
    "assistant_generated_img": 'img[alt^="Generated image"]',
}

# XPath per aspect-ratio label — keys match ILLUSTRATE_HERO.aspect_ratio enum.
ASPECT_XPATH = {
    # Fuzzy-match aspect options by ratio substring — ChatGPT DOM labels
    # drift (e.g. "Story 9:16" → just "9:16" or "Portrait 9:16"), so we
    # match the ratio substring which is more stable.
    "auto": '//div[@role="menuitemradio"][contains(., "Auto")]',
    "square": '//div[@role="menuitemradio"][contains(., "1:1")]',
    "portrait": '//div[@role="menuitemradio"][contains(., "3:4")]',
    "story": '//div[@role="menuitemradio"][contains(., "9:16")]',
    "landscape": '//div[@role="menuitemradio"][contains(., "4:3")]',
    "widescreen": '//div[@role="menuitemradio"][contains(., "16:9")]',
}

PROMPT_DRAFT_TIMEOUT_SEC = 180
# 60s per step: 2-click chain (+ / Create image) + type + waits + DOM settle.
# 2026-04-24: reduced chain from 4 clicks to 2 — aspect-ratio submenu was
# brittle (selectors for "Story 9:16" etc. stopped matching current DOM);
# we now let ChatGPT use its default Auto aspect. See ASPECT_XPATH comment.
AB_STEP_TIMEOUT_SEC = 60
IMAGE_WAIT_MS = 180_000  # ChatGPT GPT-Image-2 can take 30-90s


# ─────────────────────────── Error type ───────────────────────────

class HeroError(Exception):
    """Typed error with an envelope-ready code."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_envelope(self) -> dict:
        return {
            "ok": False,
            "command": "ascent_illustrate_hero",
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


# ─────────────────────────── Helpers ───────────────────────────

def _actionbook_bin() -> str:
    return os.environ.get("ACTIONBOOK_BIN", "actionbook")


def _ascent_bin() -> str:
    return os.environ.get("ASCENT_RESEARCH_BIN", "ascent-research")


def _session_dir(slug: str) -> Path:
    return Path.home() / ".actionbook" / "ascent-research" / slug


def _run_ab(*args: str, timeout: int = AB_STEP_TIMEOUT_SEC) -> dict:
    """Call actionbook with --json, return parsed envelope, raise on failure."""
    argv = [_actionbook_bin(), *args, "--json"]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise HeroError(
            "ACTIONBOOK_TIMEOUT",
            f"actionbook wall-clock exceeded {timeout}s",
            {"argv": argv},
        )
    except FileNotFoundError:
        raise HeroError(
            "ACTIONBOOK_NOT_FOUND",
            f"binary '{_actionbook_bin()}' not on PATH",
            {"argv": argv},
        )

    stdout = (r.stdout or "").strip()
    if r.returncode != 0:
        if stdout.startswith("{"):
            try:
                env = json.loads(stdout)
                err = env.get("error") or {}
                raise HeroError(
                    "ACTIONBOOK_CMD_FAILED",
                    err.get("message", f"exit {r.returncode}"),
                    {"argv": argv, "envelope": env},
                )
            except json.JSONDecodeError:
                pass
        raise HeroError(
            "ACTIONBOOK_CMD_FAILED",
            (r.stderr or stdout or f"exit {r.returncode}")[:500],
            {"argv": argv},
        )

    try:
        return json.loads(stdout) if stdout else {"ok": True}
    except json.JSONDecodeError:
        raise HeroError(
            "ACTIONBOOK_BAD_OUTPUT",
            "actionbook returned non-JSON on stdout",
            {"argv": argv, "stdout": stdout[:500]},
        )


def _ensure_synthesized(slug: str) -> tuple[Path, Path]:
    """Return (report.json path, session.md path). Raise if either missing.

    session.md is the canonical narrative (authored by the loop, includes
    Objective/Sources/Overview/Findings/editorial sections); it's what
    Claude reads to draft the image prompt. report.json is still required
    because it contains the canonical topic string and confirms that
    synthesize has actually run (report.json is only produced by synthesize,
    session.md can exist from plain `ascent_new`).
    """
    d = _session_dir(slug)
    report_json = d / "report.json"
    session_md = d / "session.md"
    if not report_json.exists():
        raise HeroError(
            "REPORT_JSON_MISSING",
            f"report.json not found at {report_json}. "
            "Run ascent_synthesize first.",
            {"session_dir": str(d)},
        )
    if not session_md.exists():
        raise HeroError(
            "SESSION_MD_MISSING",
            f"session.md not found at {session_md}. "
            "This session appears corrupted.",
            {"session_dir": str(d)},
        )
    return report_json, session_md


def _read_topic(report_json: Path) -> str:
    try:
        data = json.loads(report_json.read_text(encoding="utf-8"))
    except Exception as e:
        raise HeroError(
            "REPORT_JSON_UNREADABLE",
            f"failed to parse {report_json}: {e}",
            {},
        )
    return data.get("topic") or data.get("slug") or "research report"


def _craft_prompt(slug: str, topic: str, override: str | None) -> str:
    """Draft the ChatGPT image prompt.

    Uses `ascent wiki query` so Claude sees the wiki pages + SCHEMA.md +
    session metadata. The question asks for a multi-panel Apple-style
    info poster prompt (headline + 4-6 compressed panels, one per
    section of the report). This produces a vertical 9:16 poster that
    visually summarises the whole report in one image, not just a cover.
    """
    if override:
        return f"{override.strip()}. {APPLE_STYLE_SUFFIX}"

    question = (
        "Draft an image-generation prompt (under 700 characters) for a "
        "9:16 VERTICAL Apple-style information poster that compresses "
        f'the ENTIRE research report titled "{topic}" into a single image. '
        "The poster MUST include: "
        "(1) a large HEADLINE of 2-6 words at the top in bold sans-serif "
        "that captures the report's core thesis — use substantive "
        'language from the report (e.g. "Benchmark jump, premium price"), '
        "not a generic phrase; "
        "(2) a short SUBHEAD line below the headline; "
        "(3) a tight vertical stack OR 2-column compact grid of 4-6 "
        "MODULAR PANELS, one per numbered section of the report. Each "
        "panel must have a small number label (01, 02, ...), a 2-4 word "
        "section title, and a one-line takeaway quoted or distilled from "
        "that section's actual content (specific, not generic); "
        "(4) a small footer with the source count; "
        "(5) clean Apple-keynote aesthetic — off-white/pale-slate "
        "background, ONE muted accent color, typography is the primary "
        "design, geometric (not photographic) visual accents. "
        "Enumerate the 4-6 panels in your prompt with actual content from "
        "the wiki (section title + takeaway), not placeholders. "
        "Output ONLY the prompt string — no prefix, no quotes, no "
        "explanation, no leading/trailing whitespace."
    )
    argv = [
        _ascent_bin(), "--json", "wiki", "query", question,
        "--slug", slug, "--provider", "claude", "--format", "prose",
    ]
    try:
        r = subprocess.run(
            argv, capture_output=True, text=True,
            timeout=PROMPT_DRAFT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        raise HeroError(
            "PROMPT_DRAFT_TIMEOUT",
            f"Claude prompt draft exceeded {PROMPT_DRAFT_TIMEOUT_SEC}s",
            {"argv": argv},
        )
    except FileNotFoundError:
        raise HeroError(
            "ASCENT_BIN_MISSING",
            f"binary '{_ascent_bin()}' not on PATH",
            {"argv": argv},
        )

    stdout = (r.stdout or "").strip()
    if r.returncode != 0:
        try:
            env = json.loads(stdout)
            err = env.get("error") or {}
            raise HeroError(
                "PROMPT_DRAFT_FAILED",
                f"wiki query: {err.get('message', 'unknown')}",
                {"envelope": env},
            )
        except json.JSONDecodeError:
            raise HeroError(
                "PROMPT_DRAFT_FAILED",
                (r.stderr or stdout or f"exit {r.returncode}")[:500],
                {"argv": argv},
            )

    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        raise HeroError(
            "PROMPT_DRAFT_BAD_OUTPUT",
            "wiki query returned non-JSON",
            {"stdout": stdout[:500]},
        )

    if not env.get("ok"):
        err = env.get("error") or {}
        raise HeroError(
            "PROMPT_DRAFT_FAILED",
            err.get("message", "unknown"),
            {"envelope": env},
        )

    data = env.get("data") or {}
    # Envelope shape varies by command version; try the usual suspects.
    draft = (
        data.get("answer")
        or data.get("body")
        or data.get("text")
        or data.get("response")
        or ""
    )
    draft = draft.strip().strip('"').strip("'").strip()
    if not draft:
        raise HeroError(
            "PROMPT_DRAFT_EMPTY",
            "Claude returned an empty prompt",
            {"envelope_data_keys": list(data.keys())},
        )
    return f"{draft}. {APPLE_STYLE_SUFFIX}"


def _dump_debug(slug: str, tab: str | None = None) -> dict:
    """Best-effort dump of page HTML + screenshot for post-mortem.

    actionbook extension mode requires --tab on html/screenshot. If the
    caller didn't track a tab_id, fall back to the first tab in the
    session.
    """
    images_dir = _session_dir(slug) / "images"
    images_dir.mkdir(exist_ok=True)
    debug_html = images_dir / "hero-debug.html"
    debug_png = images_dir / "hero-debug.png"
    if tab is None:
        try:
            tabs_env = _run_ab(
                "browser", "list-tabs", "--session", AB_SESSION, timeout=10,
            )
            tabs = (tabs_env.get("data") or {}).get("tabs") or []
            tab = tabs[0]["tab_id"] if tabs else None
        except Exception as e:
            logger.debug("list-tabs for debug dump failed: %s", e)
            tab = None
    if tab is None:
        return {"debug_html": str(debug_html), "debug_png": str(debug_png)}
    try:
        r = _run_ab(
            "browser", "html", "body",
            "--session", AB_SESSION, "--tab", tab, timeout=15,
        )
        debug_html.write_text(
            (r.get("data") or {}).get("value", ""),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug("debug html dump failed: %s", e)
    try:
        _run_ab(
            "browser", "screenshot", str(debug_png),
            "--session", AB_SESSION, "--tab", tab, "--full",
            timeout=30,
        )
    except Exception as e:
        logger.debug("debug screenshot failed: %s", e)
    return {"debug_html": str(debug_html), "debug_png": str(debug_png)}


def _session_md_snippet(md_path: Path, max_chars: int = 200) -> str:
    """Tiny excerpt for the return envelope so the caller can verify the
    right session was used without us shipping the whole file back."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    return text.strip()[:max_chars]


# ─────────────────────────── Main entry ───────────────────────────

def generate_hero(args: dict) -> dict:
    """Full orchestration. Caller should catch HeroError → envelope JSON."""
    slug = args.get("slug")
    if not slug:
        raise HeroError("MISSING_SLUG", "slug is required", {})

    report_json_path, md_path = _ensure_synthesized(slug)
    topic = _read_topic(report_json_path)
    prompt_override = args.get("prompt_override")
    aspect_ratio = (args.get("aspect_ratio") or "story").lower()
    if aspect_ratio not in ASPECT_XPATH:
        raise HeroError(
            "INVALID_ASPECT",
            f"aspect_ratio '{aspect_ratio}' not recognized. "
            f"Valid: {sorted(ASPECT_XPATH)}",
            {},
        )

    full_prompt = _craft_prompt(slug, topic, prompt_override)

    if args.get("dry_run"):
        return {
            "ok": True,
            "command": "ascent_illustrate_hero",
            "data": {
                "topic": topic,
                "chatgpt_prompt_preview": full_prompt,
                "aspect_ratio": aspect_ratio,
                "dry_run": True,
                "note": "Image mode + aspect ratio applied via single multi-selector actionbook click; prompt sent verbatim (no 'Generate an image.' preamble).",
            },
        }

    try:
        return _generate_via_chatgpt(slug, full_prompt, md_path, aspect_ratio)
    except HeroError as first_err:
        # Cold-start Chrome can't always hit network-idle within 45s on the
        # first try after we close all sessions. Second attempt is almost
        # always fast because the profile is warm. Retry once transparently.
        if first_err.code == "CHATGPT_LOAD_TIMEOUT":
            logger.warning(
                "CHATGPT_LOAD_TIMEOUT on cold start — retrying once warm"
            )
            try:
                return _generate_via_chatgpt(slug, full_prompt, md_path, aspect_ratio)
            except HeroError as retry_err:
                first_err = retry_err  # fall through to FLUX fallback below
        chatgpt_err = first_err
        if not args.get("use_flux_fallback"):
            raise
        logger.warning(
            "ChatGPT hero path failed (%s): %s — falling back to FLUX",
            chatgpt_err.code, chatgpt_err.message,
        )
        try:
            return _generate_via_flux(slug, full_prompt, md_path)
        except HeroError as flux_err:
            raise HeroError(
                "BOTH_PATHS_FAILED",
                f"ChatGPT: [{chatgpt_err.code}] {chatgpt_err.message} "
                f"| FLUX: [{flux_err.code}] {flux_err.message}",
                {
                    "chatgpt": {
                        "code": chatgpt_err.code,
                        "message": chatgpt_err.message,
                        "details": chatgpt_err.details,
                    },
                    "flux": {
                        "code": flux_err.code,
                        "message": flux_err.message,
                        "details": flux_err.details,
                    },
                },
            )


# ─────────────────────────── ChatGPT path ───────────────────────────

def _generate_via_chatgpt(slug: str, full_prompt: str, md_path: Path, aspect_ratio: str = "story") -> dict:
    images_dir = _session_dir(slug) / "images"
    images_dir.mkdir(exist_ok=True)
    hero_path = images_dir / "hero.png"

    # Always regenerate per user policy (no skip-if-exists).

    # Fresh session: close ALL running actionbook sessions (not just our own)
    # because the Chrome profile is exclusive — if `research-local` (used by
    # ascent_batch) or any other session is running, our `browser start` below
    # will fail with "session was closed while command was pending" / profile
    # conflict. Hero generation needs the profile to itself for ChatGPT login.
    try:
        sess_env = _run_ab("browser", "list-sessions", timeout=10)
        sessions = (sess_env.get("data") or {}).get("sessions") or []
        for s in sessions:
            sid = s.get("session_id") or s.get("id") or s.get("session")
            if sid:
                try:
                    _run_ab("browser", "close", "--session", sid, timeout=15)
                except HeroError:
                    pass  # best-effort
    except HeroError:
        pass  # list-sessions failed — proceed and let start handle it
    # Also explicitly close our own session name in case list-sessions missed it
    try:
        _run_ab(
            "browser", "close", "--session", AB_SESSION, timeout=15,
        )
    except HeroError:
        pass
    try:
        _run_ab(
            "browser", "start",
            "--session", AB_SESSION,
            "--open-url", "https://chatgpt.com/?new=chat",
            timeout=30,
        )
    except HeroError as e:
        raise HeroError(
            "SESSION_START_FAILED",
            f"could not start actionbook session '{AB_SESSION}': {e.message}",
            {"underlying": e.details},
        )

    # Extract the auto-assigned tab_id — actionbook `browser start --tab-id`
    # only accepts integers, so we let it pick and read back.
    try:
        tabs_env = _run_ab(
            "browser", "list-tabs", "--session", AB_SESSION, timeout=10,
        )
        tabs = (tabs_env.get("data") or {}).get("tabs") or []
        if not tabs:
            raise HeroError(
                "TAB_ENUMERATE_FAILED", "no tabs after start", {},
            )
        ab_tab = tabs[0]["tab_id"]  # e.g. "t1"
    except HeroError:
        raise
    except Exception as e:
        raise HeroError(
            "TAB_ENUMERATE_FAILED", f"list-tabs failed: {e}", {},
        )

    try:
        _run_ab(
            "browser", "wait", "network-idle",
            "--session", AB_SESSION, "--tab", ab_tab, "--timeout", "45000",
            timeout=55,
        )
    except HeroError as e:
        _dump_debug(slug, tab=ab_tab)
        raise HeroError(
            "CHATGPT_LOAD_TIMEOUT",
            "ChatGPT did not reach network-idle in 45s",
            {"underlying": e.details},
        )

    # Composer doubles as login-state probe
    try:
        _run_ab(
            "browser", "wait", "element", SELECTORS["prompt_textarea"],
            "--session", AB_SESSION, "--tab", ab_tab, "--timeout", "30000",
            timeout=35,
        )
    except HeroError as e:
        debug = _dump_debug(slug, tab=ab_tab)
        raise HeroError(
            "NOT_LOGGED_IN",
            "ChatGPT composer (#prompt-textarea) not found in 30s. "
            "Open https://chatgpt.com/ in your default Chrome profile "
            "(the one actionbook uses) and log in, then retry this "
            f"tool. Debug HTML: {debug['debug_html']}.",
            {**debug, "underlying": e.details},
        )

    # Enter Image mode AND select the requested aspect ratio. All 4 clicks
    # must run inside ONE actionbook subprocess via multi-selector syntax
    # because intermediate menus (the + menu and the aspect-ratio menu)
    # close on focus-loss — splitting into separate subprocess calls (~1s
    # latency each) would find the second menu already closed.
    #
    # Click order:
    #   1. +                       opens the attachments/tools menu
    #   2. Create image            closes +menu, activates Image mode, shows aspect button
    #   3. aspect ratio button     opens aspect-ratio menu
    #   4. <aspect option>         selects requested ratio, closes menu
    aspect_xpath = ASPECT_XPATH.get(aspect_ratio) or ASPECT_XPATH["story"]
    try:
        _run_ab(
            "browser", "click",
            SELECTORS["composer_plus_btn"],
            SELECTORS["menu_create_image"],
            SELECTORS["aspect_ratio_btn"],
            aspect_xpath,
            "--session", AB_SESSION, "--tab", ab_tab,
            timeout=45,
        )
    except HeroError as e:
        # Aspect-selection is nice-to-have — if the 4th click fails because
        # ChatGPT's aspect menu labels moved again, fall back to the 2-click
        # chain (+ → Create image only) with default Auto aspect. Prompt
        # will still request 9:16 composition, model may approximate.
        logger.warning(
            "4-click aspect chain failed (%s) — falling back to 2-click with Auto aspect",
            e.message[:120],
        )
        try:
            _run_ab(
                "browser", "click",
                SELECTORS["composer_plus_btn"],
                SELECTORS["menu_create_image"],
                "--session", AB_SESSION, "--tab", ab_tab,
                timeout=45,
            )
        except HeroError as e2:
            debug = _dump_debug(slug, tab=ab_tab)
            raise HeroError(
                "IMAGE_MODE_ENTRY_FAILED",
                "Could not click + → Create image. The ChatGPT DOM may have "
                "changed. Inspect debug HTML and update SELECTORS in "
                f"illustrate.py. Debug: {debug['debug_html']}.",
                {**debug, "underlying": e2.details},
            )

    # Sanity check: composer placeholder should flip to "Describe or edit
    # an image" once Create image is active. Soft-verify.
    try:
        _run_ab(
            "browser", "wait", "element",
            SELECTORS["prompt_textarea_image_mode"],
            "--session", AB_SESSION, "--tab", ab_tab, "--timeout", "3000",
            timeout=8,
        )
    except HeroError:
        logger.warning(
            "image-mode placeholder not detected; proceeding anyway"
        )

    # Type + send. Mode is now explicitly Image, so no "Generate an
    # image." preamble needed — just the crafted prompt verbatim.
    _run_ab(
        "browser", "type", SELECTORS["prompt_textarea"], full_prompt,
        "--session", AB_SESSION, "--tab", ab_tab,
        timeout=30,
    )
    _run_ab(
        "browser", "press", "Enter",
        "--session", AB_SESSION, "--tab", ab_tab,
        timeout=15,
    )

    # Wait for the generated <img>. ChatGPT's image-mode response uses
    # `alt="Generated image: ..."`, NOT a conventional data-message-author-role
    # wrapper — the `img[alt^="Generated image"]` selector is the reliable
    # one (verified 2026-04-23).
    try:
        _run_ab(
            "browser", "wait", "element", SELECTORS["assistant_generated_img"],
            "--session", AB_SESSION, "--tab", ab_tab, "--timeout", str(IMAGE_WAIT_MS),
            timeout=IMAGE_WAIT_MS // 1000 + 30,
        )
    except HeroError as e:
        debug = _dump_debug(slug, tab=ab_tab)
        assistant_text = ""
        try:
            r = _run_ab(
                "browser", "text", SELECTORS["assistant_latest"],
                "--session", AB_SESSION, "--tab", ab_tab,
                timeout=15,
            )
            assistant_text = (r.get("data") or {}).get("value", "")[:500]
        except Exception:
            pass
        text_lower = assistant_text.lower()
        if "limit" in text_lower or "you've reached" in text_lower:
            code = "RATE_LIMITED"
        elif any(w in text_lower for w in ("policy", "can't", "cannot", "unable to")):
            code = "CONTENT_POLICY"
        else:
            code = "IMAGE_NOT_PRODUCED"
        raise HeroError(
            code,
            f"No generated <img> appeared in {IMAGE_WAIT_MS // 1000}s. "
            f"Assistant said: {assistant_text[:200]!r}. "
            f"Debug HTML: {debug['debug_html']}.",
            {**debug, "assistant_text": assistant_text,
             "underlying": e.details},
        )

    # Extract img src
    try:
        r = _run_ab(
            "browser", "html", SELECTORS["assistant_generated_img"],
            "--session", AB_SESSION, "--tab", ab_tab,
            timeout=15,
        )
        html_str = (r.get("data") or {}).get("value", "")
    except HeroError as e:
        raise HeroError(
            "SRC_EXTRACT_FAILED",
            f"could not read <img> HTML: {e.message}",
            e.details,
        )

    m = re.search(r'src=["\']([^"\']+)["\']', html_str)
    if not m:
        raise HeroError(
            "SRC_MISSING",
            "could not find src attribute in <img> tag",
            {"html_fragment": html_str[:300]},
        )
    # ChatGPT stores image URLs with HTML-entity-encoded ampersands; decode.
    import html as html_mod
    src_url = html_mod.unescape(m.group(1))

    # Download via actionbook eval: runs `fetch(src)` inside the logged-in
    # Chrome tab, so cookies travel automatically. Returns base64. This is
    # cleaner than urllib (which 403s on ChatGPT's estuary CDN) and richer
    # than element screenshot (which captures UI chrome around the image).
    js = (
        "(async () => {"
        "  try {"
        f"    const r = await fetch({json.dumps(src_url)});"
        "    if (!r.ok) return {error: 'HTTP ' + r.status};"
        "    const buf = await r.arrayBuffer();"
        "    const bytes = new Uint8Array(buf);"
        "    let bin = '';"
        "    for (let i=0; i<bytes.length; i++) bin += String.fromCharCode(bytes[i]);"
        "    return {size: bytes.length, b64: btoa(bin)};"
        "  } catch (e) { return {error: String(e)}; }"
        "})()"
    )
    try:
        eval_res = _run_ab(
            "browser", "eval", js,
            "--session", AB_SESSION, "--tab", ab_tab,
            timeout=60,
        )
    except HeroError as e:
        debug = _dump_debug(slug, tab=ab_tab)
        raise HeroError(
            "DOWNLOAD_FAILED",
            f"actionbook eval for image fetch failed: {e.message}",
            {**debug, "src_url": src_url, "underlying": e.details},
        )

    result = (eval_res.get("data") or {}).get("value") or (eval_res.get("data") or {}).get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pass
    if not isinstance(result, dict):
        raise HeroError(
            "DOWNLOAD_FAILED",
            f"unexpected eval result shape: {type(result).__name__}",
            {"src_url": src_url, "eval_result": str(result)[:200]},
        )
    if result.get("error"):
        raise HeroError(
            "DOWNLOAD_FAILED",
            f"in-browser fetch failed: {result['error']}",
            {"src_url": src_url},
        )
    b64 = result.get("b64")
    if not b64:
        raise HeroError(
            "DOWNLOAD_FAILED",
            "eval returned no base64 payload",
            {"src_url": src_url, "eval_keys": list(result.keys())},
        )
    import base64
    try:
        data = base64.b64decode(b64)
    except Exception as e:
        raise HeroError(
            "DOWNLOAD_FAILED",
            f"base64 decode failed: {e}",
            {"src_url": src_url},
        )
    if len(data) < 1024:
        raise HeroError(
            "DOWNLOAD_FAILED",
            f"downloaded image too small ({len(data)} bytes)",
            {"src_url": src_url},
        )
    hero_path.write_bytes(data)

    # Prepend to md, write meta
    # NOTE: we intentionally do NOT mutate session.md. Users edit it directly;
    # a hidden side-effect here would conflict with concurrent edits. If the
    # user wants to inline the hero, they can add the markdown link
    # themselves — hero.png is at a stable path relative to session.md.
    meta_path = images_dir / "hero.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "slug": slug,
                "via": "chatgpt",
                "model": "gpt-image-2 (via chatgpt.com)",
                "aspect_ratio": aspect_ratio,
                "source_url": src_url,
                "full_prompt": full_prompt,
                "bytes": len(data),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "command": "ascent_illustrate_hero",
        "data": {
            "hero_image": str(hero_path),
            "source_url": src_url,
            "session_md_path": str(md_path),
            "meta": str(meta_path),
            "aspect_ratio": aspect_ratio,
            "bytes": len(data),
            "via": "chatgpt",
        },
    }


# ─────────────────────────── FLUX fallback ───────────────────────────

def _generate_via_flux(slug: str, full_prompt: str, md_path: Path) -> dict:
    """Optional fallback — uses hermes's image_generation_tool (FLUX 2 Pro).

    Only imported lazily so the module stays loadable outside a hermes
    runtime (e.g. during standalone py_compile checks).
    """
    try:
        from tools.image_generation_tool import image_generate_tool  # type: ignore
    except ImportError as e:
        raise HeroError(
            "FLUX_TOOL_IMPORT_FAILED",
            f"cannot import hermes image_generation_tool: {e}. "
            "This fallback requires running inside a hermes process with "
            "the hermes-agent repo on sys.path.",
            {},
        )

    images_dir = _session_dir(slug) / "images"
    images_dir.mkdir(exist_ok=True)
    hero_path = images_dir / "hero.png"

    try:
        result_str = image_generate_tool(
            prompt=full_prompt,
            aspect_ratio="landscape",
            num_images=1,
            output_format="png",
        )
        result = json.loads(result_str)
    except Exception as e:
        raise HeroError("FLUX_CALL_FAILED", f"image_generate_tool raised: {e}", {})

    if not result.get("success") or not result.get("image"):
        raise HeroError(
            "FLUX_GENERATION_FAILED",
            "FLUX returned success=false or no image URL",
            {"flux_result": result},
        )
    img_url = result["image"]

    try:
        req = urllib.request.Request(
            img_url,
            headers={"User-Agent": "Mozilla/5.0 (ascent-research hero)"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if len(data) < 1024:
            raise RuntimeError(f"image too small ({len(data)} bytes)")
        hero_path.write_bytes(data)
    except Exception as e:
        raise HeroError(
            "DOWNLOAD_FAILED",
            f"failed to download FLUX image: {e}",
            {"img_url": img_url},
        )

    # NOTE: we intentionally do NOT mutate session.md. Users edit it directly;
    # a hidden side-effect here would conflict with concurrent edits. If the
    # user wants to inline the hero, they can add the markdown link
    # themselves — hero.png is at a stable path relative to session.md.
    meta_path = images_dir / "hero.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "slug": slug,
                "via": "flux-fallback",
                "model": "fal-ai/flux-2-pro",
                "source_url": img_url,
                "full_prompt": full_prompt,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "command": "ascent_illustrate_hero",
        "data": {
            "hero_image": str(hero_path),
            "source_url": img_url,
            "session_md_path": str(md_path),
            "meta": str(meta_path),
            "via": "flux-fallback",
        },
    }
