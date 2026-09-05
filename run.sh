#!/usr/bin/env bash
# ============================================================
#  free-claude-code — run script (Python 3.12 compatible)
#  Fixes applied:
#    1. Python 3.12 forward-ref fix in config/settings.py
#    2. Python 2-style "except A, B:" → "except (A, B):" in 6 files
#    3. tiktoken network-unavailable fallback in tokens.py + usage.py
#    4. NVIDIA NIM as default provider (no OpenRouter DNS needed)
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 1. Verify .env exists ────────────────────────────────────
if [ ! -f ".env" ]; then
  echo "[ERROR] No .env file found."
  echo "  Copy .env.example to .env and set NVIDIA_NIM_API_KEY."
  exit 1
fi

# ── 2. Check NVIDIA NIM key is set ──────────────────────────
NIM_KEY=$(grep -E '^NVIDIA_NIM_API_KEY=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")
if [ -z "$NIM_KEY" ] || [ "$NIM_KEY" = "YOUR_NVIDIA_NIM_API_KEY_HERE" ]; then
  echo ""
  echo "╔══════════════════════════════════════════════════════╗"
  echo "║  ⚠  NVIDIA NIM API key not set in .env              ║"
  echo "╠══════════════════════════════════════════════════════╣"
  echo "║  1. Go to: https://build.nvidia.com/settings/api-keys║"
  echo "║  2. Create a free API key                            ║"
  echo "║  3. Set NVIDIA_NIM_API_KEY=nvapi-xxxx in your .env  ║"
  echo "╚══════════════════════════════════════════════════════╝"
  echo ""
  echo "  You can still start the server — it will use whatever"
  echo "  providers have keys set in .env."
  echo ""
fi

# ── 3. Add project root to PYTHONPATH ────────────────────────
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# ── 4. Pick Python 3 interpreter ────────────────────────────
PYTHON=$(which python3 || which python)
echo "▶ Using Python: $($PYTHON --version)"

# ── 5. Start the proxy server ───────────────────────────────
PORT="${FCC_PORT:-8082}"
HOST="${FCC_HOST:-127.0.0.1}"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  free-claude-code proxy  →  http://$HOST:$PORT     ║"
echo "║  Admin UI               →  http://$HOST:$PORT/admin║"
echo "║  Provider: NVIDIA NIM   (openrouter.ai NOT needed)  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

$PYTHON -m uvicorn server:app \
  --host "$HOST" \
  --port "$PORT" \
  --timeout-graceful-shutdown 5 \
  --log-level info
