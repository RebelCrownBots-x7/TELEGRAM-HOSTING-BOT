#!/usr/bin/env bash
# Simple production start script (VPS without Docker)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "❌ .env missing. Copy .env.example to .env and fill BOT_TOKEN + ADMIN_IDS"
  exit 1
fi

mkdir -p data storage runtime logs \
  storage/users storage/uploads storage/bots storage/exports storage/backups

# Optional venv
if [ -d venv ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
elif [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export PYTHONUNBUFFERED=1
# If a reverse proxy / PaaS sets PORT, health server will bind to it automatically
exec python main.py
