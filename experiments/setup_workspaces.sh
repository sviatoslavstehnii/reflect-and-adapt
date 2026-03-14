#!/usr/bin/env bash
# Sets up isolated openclaw directories for control and treatment arms.
# Run once before starting the experiment.
#
# Usage: bash setup_workspaces.sh [--reset]
#
# Creates:
#   ~/.openclaw-control/   — copy of ~/.openclaw with CORTEX_COOLDOWN_HOURS=999
#   ~/.openclaw-treatment/ — copy of ~/.openclaw with full plugin

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

setup_arm() {
  local NAME="$1"
  local PORT="$2"
  local DIR="$HOME/.openclaw-${NAME}"
  local COOLDOWN="${3:-1}"

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

  # Write arm-specific .env into the plugin directory
  PLUGIN_ENV="$DIR/workspace/.openclaw/extensions/reflect-and-adapt/.env"
  if [[ -f "$PLUGIN_ENV" ]]; then
    # Update or append CORTEX_COOLDOWN_HOURS
    if grep -q "CORTEX_COOLDOWN_HOURS" "$PLUGIN_ENV"; then
      sed -i "s/^CORTEX_COOLDOWN_HOURS=.*/CORTEX_COOLDOWN_HOURS=${COOLDOWN}/" "$PLUGIN_ENV"
    else
      echo "CORTEX_COOLDOWN_HOURS=${COOLDOWN}" >> "$PLUGIN_ENV"
    fi
  else
    echo "CORTEX_COOLDOWN_HOURS=${COOLDOWN}" > "$PLUGIN_ENV"
  fi

  echo "[$NAME] Port will be $PORT — set this in your openclaw startup command"
  echo "[$NAME] Done."
}

setup_arm "control"   3100 999
setup_arm "treatment" 3101 1

echo ""
echo "Both arms ready."
echo ""
echo "Start control arm:"
echo "  cd ~/.openclaw-control && PORT=3100 npx openclaw"
echo ""
echo "Start treatment arm:"
echo "  cd ~/.openclaw-treatment && PORT=3101 npx openclaw"
echo ""
echo "Then run the experiment:"
echo "  cd experiments && python run_experiment.py --personas sofia"
