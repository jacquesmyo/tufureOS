#!/usr/bin/env bash
# Cron entrypoint for trading bot
# Run every 30 minutes

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
source .env 2>/dev/null || true

# Run one trading cycle
python3 -m src.bot --one-shot --config config.json >> logs/cron.log 2>&1
