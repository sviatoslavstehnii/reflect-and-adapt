#!/usr/bin/env bash
# Sets up isolated openclaw directories for baseline and adaptive arms.
# Run once before starting the experiment (or with --reset to recreate).
#
# Usage: bash setup_workspaces.sh [--reset]
#
# Creates:
#   ~/.openclaw-baseline/  — isolated workspace, Cortex disabled (CORTEX_COOLDOWN_HOURS=999)
#   ~/.openclaw-adaptive/  — isolated workspace, full adaptation pipeline

set -euo pipefail

RESET=false
for arg in "$@"; do
  [[ "$arg" == "--reset" ]] && RESET=true
done

OPENCLAW_SRC="$HOME/.openclaw"

if [[ ! -d "$OPENCLAW_SRC" ]]; then
  echo "ERROR: $OPENCLAW_SRC does not exist. Run openclaw at least once first."
  exit 1
fi

# Patch agents.defaults.workspace and plugins.load.paths in openclaw.json using Python
patch_openclaw_json() {
  local DIR="$1"
  local ARM_NAME="$2"
  local CONFIG="$DIR/openclaw.json"
  local ARM_WORKSPACE="$HOME/.openclaw-${ARM_NAME}/workspace"
  # Shared plugin source stays in the main workspace (source of truth for plugin code)
  local PLUGIN_PATHS='["/home/'"$USER"'/.openclaw/workspace/.openclaw/extensions"]'

  python3 - "$CONFIG" "$ARM_WORKSPACE" "$PLUGIN_PATHS" <<'PYEOF'
import json, sys
config_path, workspace, plugin_paths_json = sys.argv[1], sys.argv[2], sys.argv[3]
import json as _j
plugin_paths = _j.loads(plugin_paths_json)

with open(config_path) as f:
    cfg = json.load(f)

# Set arm-specific workspace
cfg.setdefault("agents", {}).setdefault("defaults", {})["workspace"] = workspace

# Set plugin load paths to shared source (no arm-specific plugin copies)
cfg.setdefault("plugins", {}).setdefault("load", {})["paths"] = plugin_paths
cfg["plugins"]["enabled"] = True

with open(config_path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")

print(f"  openclaw.json: workspace → {workspace}")
PYEOF
}

setup_arm() {
  local NAME="$1"
  local PORT="$2"
  local COOLDOWN="${3:-1}"
  local DIR="$HOME/.openclaw-${NAME}"

  if [[ -d "$DIR" && "$RESET" == "false" ]]; then
    echo "[$NAME] $DIR already exists — skipping (use --reset to recreate)"
    return
  fi

  if [[ -d "$DIR" ]]; then
    echo "[$NAME] Removing existing $DIR"
    rm -rf "$DIR"
  fi

  echo "[$NAME] Copying $OPENCLAW_SRC → $DIR"
  cp -r "$OPENCLAW_SRC" "$DIR"

  # Patch openclaw.json: arm-specific workspace + shared plugin source
  echo "[$NAME] Patching openclaw.json..."
  patch_openclaw_json "$DIR" "$NAME"

  # Write CORTEX_COOLDOWN_HOURS into the plugin .env
  PLUGIN_ENV="$HOME/.openclaw/workspace/.openclaw/extensions/reflect-and-adapt/.env"
  ARM_ENV="$DIR/workspace/.openclaw/extensions/reflect-and-adapt/.env"
  # The plugin source is shared, so we set arm-specific env via the arm's own .env symlink isn't ideal —
  # instead, set it in the arm's profile env (loaded by the runner via experiment.yaml arm config)
  echo "[$NAME] CORTEX_COOLDOWN_HOURS=${COOLDOWN} (set via experiment.yaml arm env)"

  # Ensure workspace dirs exist for the arm
  mkdir -p "$DIR/workspace/data"
  mkdir -p "$DIR/workspace/memory"

  echo "[$NAME] Port will be $PORT — use startup command below"
  echo "[$NAME] Done."
}

setup_arm "baseline" 3100 999
setup_arm "adaptive" 3101 0

echo ""
echo "Both arms ready. Each arm uses its own isolated workspace:"
echo "  ~/.openclaw-baseline/workspace  (no adaptation)"
echo "  ~/.openclaw-adaptive/workspace  (full Cortex pipeline)"
echo ""
echo "Start baseline arm:"
echo "  openclaw --profile baseline gateway --port 3100 --allow-unconfigured"
echo ""
echo "Start adaptive arm:"
echo "  openclaw --profile adaptive gateway --port 3101 --allow-unconfigured"
echo ""
echo "Then run the experiment:"
echo "  cd experiments && python run_experiment.py --personas sofia"
