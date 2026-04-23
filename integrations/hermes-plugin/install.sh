#!/usr/bin/env bash
#
# One-command install: build the ascent-research binary, symlink the
# hermes plugin, install the actionbook-only preset, run a smoke test.
#
# Idempotent — safe to re-run.
#
# Usage:
#   ./integrations/hermes-plugin/install.sh             # full install
#   ./integrations/hermes-plugin/install.sh --skip-build  # skip cargo install
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

SKIP_BUILD=0
for arg in "$@"; do
    case "$arg" in
        --skip-build) SKIP_BUILD=1 ;;
        -h|--help)
            sed -n '2,13p' "$0"; exit 0 ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

log() { printf '[%s] %s\n' "ascent-research" "$*"; }
die() { printf '[%s] ERROR: %s\n' "ascent-research" "$*" >&2; exit 1; }

# ─── 1. Pre-flight ────────────────────────────────────────────────
log "1/7 preflight checks"
command -v cargo >/dev/null   || die "cargo not found. Install Rust from https://rustup.rs"
command -v python3 >/dev/null || die "python3 not found."
command -v actionbook >/dev/null || log "  WARN: actionbook not on PATH — tools requiring fetch will fail until installed"

# Verify cargo bin dir is on PATH (common gotcha on macOS).
CARGO_BIN="${CARGO_HOME:-$HOME/.cargo}/bin"
case ":$PATH:" in
    *":$CARGO_BIN:"*) ;;
    *) log "  WARN: $CARGO_BIN is not in PATH — add it to your shell rc before running hermes" ;;
esac

# ─── 2. Build + install binary ────────────────────────────────────
if [ "$SKIP_BUILD" -eq 1 ]; then
    log "2/7 skipping cargo install (--skip-build)"
    command -v ascent-research >/dev/null \
        || die "ascent-research binary not found; re-run without --skip-build"
else
    log "2/7 cargo install ascent-research (this takes 1-3 min, cold cache)"
    ( cd "$REPO_ROOT" && cargo install --path packages/research \
        --features provider-claude --locked --quiet )
fi

# ─── 3. Symlink plugin into ~/.hermes/plugins/ ────────────────────
log "3/7 symlinking plugin into ~/.hermes/plugins/ascent-research"
mkdir -p "$HOME/.hermes/plugins"
TARGET="$HOME/.hermes/plugins/ascent-research"
if [ -L "$TARGET" ] || [ -e "$TARGET" ]; then
    rm -rf "$TARGET"
fi
ln -s "$SCRIPT_DIR" "$TARGET"

# ─── 4. Install actionbook-only preset ────────────────────────────
log "4/7 installing actionbook-only preset"
PRESET_DST="$HOME/.actionbook/research/presets/actionbook-only.toml"
mkdir -p "$(dirname "$PRESET_DST")"
cp "$SCRIPT_DIR/presets/actionbook-only.toml" "$PRESET_DST"

# ─── 5. Install hermes skill (so "research X" auto-triggers chain) ─
log "5/7 installing hermes skill (~/.hermes/skills/ascent-research/SKILL.md)"
SKILL_DST_DIR="$HOME/.hermes/skills/ascent-research"
SKILL_DST="$SKILL_DST_DIR/SKILL.md"
mkdir -p "$SKILL_DST_DIR"
if [ -f "$SKILL_DST" ]; then
    BACKUP="$SKILL_DST.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$SKILL_DST" "$BACKUP"
    log "  backed up existing SKILL.md → $BACKUP"
fi
cp "$SCRIPT_DIR/skill/SKILL.md" "$SKILL_DST"

# ─── 6. Smoke ──────────────────────────────────────────────────────
log "6/7 smoke test: ascent-research --json list"
if ! ascent-research --json list > /tmp/ar-smoke.json 2>&1; then
    echo "--- smoke output ---" >&2
    cat /tmp/ar-smoke.json >&2
    die "smoke test failed — see output above"
fi
python3 -c "
import json, sys
d = json.load(open('/tmp/ar-smoke.json'))
assert d.get('ok') is True, d
print('  ok, envelope parsed, sessions:', len(d.get('data', {}).get('sessions', [])))
"

# ─── 7. Next-step banner ──────────────────────────────────────────
log "7/7 done"
cat <<EOF

Install complete.

If this is your first install, edit ~/.hermes/config.yaml and add
'ascent-research' to platform_toolsets (remove 'browser' + 'web' for
consistent routing through actionbook):

  platform_toolsets:
    cli:      [terminal, file, skills, todo, ascent-research]
    telegram: [terminal, file, ascent-research]

Then restart hermes. With the skill installed, you can now trigger
the full research chain with a one-liner:

  "Use ascent-research to research <topic> and generate a hero image."

The skill (~/.hermes/skills/ascent-research/SKILL.md) teaches hermes
the 6-step chain — new → batch → wiki_query → loop_step → synthesize
→ illustrate_hero — so you don't have to spell it out.

Full test ladder: integrations/hermes-plugin/TESTING.md
Cold-start doc:   integrations/hermes-plugin/USAGE.md
EOF
