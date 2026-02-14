#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# OpenClaw + Gradient AI — Deploy Updates (run from repo on Droplet)
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

WORKSPACE_DIR="$HOME/.openclaw/workspace"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS=("web-researcher" "fundamental-analyst")

echo "Pulling latest changes..."
git -C "$SCRIPT_DIR" pull origin main

echo "Updating persona files..."

# Per-agent persona files
for agent in "${AGENTS[@]}"; do
  AGENT_WS="$WORKSPACE_DIR/agents/$agent"
  SRC_DIR="$SCRIPT_DIR/data/workspaces/$agent"
  if [ -d "$SRC_DIR" ]; then
    mkdir -p "$AGENT_WS"
    for f in IDENTITY.md AGENTS.md HEARTBEAT.md; do
      if [ -f "$SRC_DIR/$f" ]; then
        cp "$SRC_DIR/$f" "$AGENT_WS/$f"
      fi
    done
    # Ensure skills symlink exists
    SKILL_DIR="$SCRIPT_DIR/skills/$agent"
    if [ -d "$SKILL_DIR" ] && [ ! -e "$AGENT_WS/skills" ]; then
      ln -s "$SKILL_DIR" "$AGENT_WS/skills"
    fi
    echo "  ✓ $agent updated"
  fi
done

# Shared/legacy persona files
for f in IDENTITY.md AGENTS.md HEARTBEAT.md; do
  if [ -f "$SCRIPT_DIR/data/workspace/$f" ]; then
    cp "$SCRIPT_DIR/data/workspace/$f" "$WORKSPACE_DIR/$f"
  fi
done

echo "Updating Python dependencies..."
pip3 install --break-system-packages -q -r "$SCRIPT_DIR/requirements.txt"

echo "Restarting OpenClaw..."
sudo systemctl restart openclaw

sleep 3
if systemctl is-active --quiet openclaw; then
  echo "✅ OpenClaw restarted successfully"
else
  echo "⚠️  Check logs: journalctl -u openclaw -f"
fi

