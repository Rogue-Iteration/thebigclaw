#!/bin/bash
set -e

SKILL_DIR="/app/skills/gradient-research-assistant"
DATA_DIR="/app/data"
WATCHLIST="$DATA_DIR/watchlist.json"

# ─── First-run setup ─────────────────────────────────────────────
# If no watchlist.json exists in the data volume, copy the default.
# This only happens on the very first deploy — after that, the
# volume-mounted file persists across rebuilds.

if [ ! -f "$WATCHLIST" ]; then
    echo "🆕 First run detected — copying default watchlist.json to data volume..."
    cp "$SKILL_DIR/watchlist.json" "$WATCHLIST"
fi

# Symlink so the skill code always reads from the persistent location
ln -sf "$WATCHLIST" "$SKILL_DIR/watchlist.json"

TICKER_COUNT=$(python3 -c "import json; print(len(json.load(open('$WATCHLIST'))['tickers']))")
echo "✅ Watchlist: $TICKER_COUNT tickers loaded"

# ─── Start the agent ──────────────────────────────────────────────
# Replace this with the actual OpenClaw start command.
# For now, we keep the container alive for development.

echo "🚀 Research Assistant ready."
echo "   Skill dir: $SKILL_DIR"
echo "   Data dir:  $DATA_DIR"

# If OPENCLAW_CMD is set, run it; otherwise keep container alive
if [ -n "$OPENCLAW_CMD" ]; then
    echo "Starting OpenClaw: $OPENCLAW_CMD"
    exec $OPENCLAW_CMD
else
    echo "⏳ No OPENCLAW_CMD set — running in standby mode (tail -f /dev/null)"
    echo "   Set OPENCLAW_CMD in .env to start the agent automatically."
    exec tail -f /dev/null
fi
