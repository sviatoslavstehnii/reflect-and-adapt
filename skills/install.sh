#!/usr/bin/env bash
set -e

SKILLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # skills/
PLUGIN_DIR="$(cd "$SKILLS_DIR/.." && pwd)"                  # plugin root
WORKSPACE_ROOT="$(cd "$PLUGIN_DIR/../../.." && pwd)"        # workspace root
WORKSPACE_SKILLS="$WORKSPACE_ROOT/skills"

echo "[reflect-and-adapt] Installing..."
echo "  Plugin:    $PLUGIN_DIR"
echo "  Workspace: $WORKSPACE_ROOT"
echo ""

# ── 1. npm install ────────────────────────────────────────────────────────────
echo "→ Installing npm dependencies..."
cd "$PLUGIN_DIR"
npm install

# ── 2. Copy .env if not present ───────────────────────────────────────────────
if [ ! -f "$PLUGIN_DIR/.env" ]; then
  cp "$PLUGIN_DIR/.env.example" "$PLUGIN_DIR/.env"
  echo "→ Created .env from .env.example — fill in your API keys before starting."
else
  echo "→ .env already exists, skipping."
fi

# ── 3. Symlink skills into workspace ─────────────────────────────────────────
mkdir -p "$WORKSPACE_SKILLS"

link_skill() {
  local name="$1"
  local src="$SKILLS_DIR/$name"
  local dst="$WORKSPACE_SKILLS/$name"

  if [ ! -d "$src" ]; then
    echo "  ⚠ Skill source not found: $src"
    return
  fi

  if [ -L "$dst" ]; then
    rm "$dst"
    ln -s "$src" "$dst"
    echo "→ Updated skill link: skills/$name"
  elif [ -d "$dst" ]; then
    echo "  ⚠ skills/$name exists as a real directory — skipping (remove it manually to let the plugin manage it)."
  else
    ln -s "$src" "$dst"
    echo "→ Linked skill: skills/$name"
  fi
}

link_skill "proposals"
link_skill "remember"

# ── 4. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "✓ reflect-and-adapt installed."
echo ""
echo "Next steps:"
if [ ! -s "$PLUGIN_DIR/.env" ] || grep -q "your-azure-" "$PLUGIN_DIR/.env" 2>/dev/null; then
  echo "  1. Edit .openclaw/extensions/reflect-and-adapt/.env with your API keys"
  echo "  2. Restart the gateway: openclaw gateway restart"
else
  echo "  1. Restart the gateway: openclaw gateway restart"
fi
echo ""
echo "Verify with: openclaw gateway status"
