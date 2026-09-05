#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  jarvis.sh — Launch / toggle J.A.R.V.I.S. with free-claude-code
#
#  FIXES applied vs original ai/jarvis.sh:
#   1. Forces fcc backend (no more OpenRouter 404 errors)
#   2. Starts fcc-server with python3 (no uv required)
#   3. Waits properly for server to be ready
#   4. Sets ANTHROPIC_AUTH_TOKEN so jarvis→fcc auth works
#   5. Works on any Linux (not only Arch/Hyprland)
#
#  Usage:
#    bash jarvis.sh              — launch / toggle JARVIS window
#    bash jarvis.sh --server     — start fcc-server only
#    bash jarvis.sh --stop       — stop everything
#    bash jarvis.sh --status     — show server status
#    bash jarvis.sh --reset      — reset backend to fcc and restart
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_DIR="$SCRIPT_DIR/ai"
FCC_PIDFILE="/tmp/fcc-server.pid"
JARVIS_PIDFILE="/tmp/jarvis-widget.pid"
FCC_LOG="/tmp/fcc-server.log"
FCC_URL="http://127.0.0.1:8082"
CFG_FILE="$AI_DIR/jarvis_config.json"

# ── Colours ──────────────────────────────────────────────────────
R="\033[0m"; B="\033[1m"
CY="\033[96m"; GR="\033[92m"; YL="\033[93m"; RD="\033[91m"; DIM="\033[2m"
c() { printf "${1}${2}${R}"; }

banner() {
  echo ""
  c $CY "$B  ╔══════════════════════════════════════╗\n"
  c $CY "$B  ║  J.A.R.V.I.S.  +  free-claude-code  ║\n"
  c $CY "$B  ╚══════════════════════════════════════╝\n"
  echo ""
}

# ── Helper: ensure jarvis_config.json uses fcc backend ───────────
fix_backend() {
  if [ ! -f "$CFG_FILE" ]; then
    mkdir -p "$AI_DIR"
    cat > "$CFG_FILE" << 'CFG'
{
  "llm_backend": "fcc",
  "fcc_url": "http://127.0.0.1:8082",
  "fcc_token": "",
  "fcc_model": "claude-sonnet-4-6",
  "fcc_max_tokens": 2048,
  "anthropic_model": "claude-sonnet-4-6",
  "anthropic_api_key": "",
  "openrouter_model": "deepseek/deepseek-chat",
  "openrouter_url": "https://openrouter.ai/api/v1",
  "openrouter_api_key": "",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "qwen3:1.7b"
}
CFG
    printf "$(c $GR '✓') Created jarvis_config.json with fcc backend\n"
  else
    # Patch only the llm_backend key to "fcc" without destroying other settings
    python3 -c "
import json, sys
try:
    with open('$CFG_FILE') as f:
        cfg = json.load(f)
except Exception:
    cfg = {}
if cfg.get('llm_backend') != 'fcc':
    old = cfg.get('llm_backend', 'none')
    cfg['llm_backend'] = 'fcc'
    if not cfg.get('fcc_url'):
        cfg['fcc_url'] = 'http://127.0.0.1:8082'
    with open('$CFG_FILE', 'w') as f:
        json.dump(cfg, f, indent=2)
    print(f'  Switched backend: {old} → fcc')
else:
    print('  Backend already set to fcc')
"
  fi
}

# ── Helper: check if fcc server is up ────────────────────────────
server_running() {
  curl -sf "$FCC_URL/jarvis/status" >/dev/null 2>&1
}

# ── Helper: wait for server to start ─────────────────────────────
wait_for_server() {
  local max=30 i=0
  printf "  Waiting for fcc-server"
  while [ $i -lt $max ]; do
    if server_running; then
      printf " $(c $GR '✓')\n"
      return 0
    fi
    printf "."
    sleep 1
    i=$((i+1))
  done
  printf " $(c $RD '✗ timed out')\n"
  printf "  $(c $DIM 'Check log: tail -50 %s')\n" "$FCC_LOG"
  return 1
}

# ── Start fcc-server ─────────────────────────────────────────────
start_server() {
  if server_running; then
    printf "$(c $GR '✓') fcc-server already running at %s\n" "$FCC_URL"
    return 0
  fi

  # Check if NVIDIA_NIM_API_KEY is set
  local nim_key=""
  if [ -f "$SCRIPT_DIR/.env" ]; then
    nim_key=$(grep -E '^NVIDIA_NIM_API_KEY=' "$SCRIPT_DIR/.env" 2>/dev/null \
      | cut -d= -f2 | tr -d '"' | tr -d "'" | tr -d ' ' | head -1 || true)
  fi
  nim_key="${NVIDIA_NIM_API_KEY:-$nim_key}"

  if [ -z "$nim_key" ] || [ "$nim_key" = "YOUR_NVIDIA_NIM_API_KEY_HERE" ]; then
    printf "\n$(c $RD '╔══════════════════════════════════════════════════╗')\n"
    printf "$(c $RD '║')  $(c $YL '⚠  NVIDIA_NIM_API_KEY is not set!')              $(c $RD '║')\n"
    printf "$(c $RD '╠══════════════════════════════════════════════════╣')\n"
    printf "$(c $RD '║')  Without a key the server will return empty       $(c $RD '║')\n"
    printf "$(c $RD '║')  responses causing:                               $(c $RD '║')\n"
    printf "$(c $RD '║')    [fcc error: Expecting value: line 1 col 1]     $(c $RD '║')\n"
    printf "$(c $RD '╠══════════════════════════════════════════════════╣')\n"
    printf "$(c $RD '║')  Get a FREE key (takes 1 min):                    $(c $RD '║')\n"
    printf "$(c $RD '║')  $(c $CY 'https://build.nvidia.com/settings/api-keys')  $(c $RD '║')\n"
    printf "$(c $RD '║')                                                    $(c $RD '║')\n"
    printf "$(c $RD '║')  Then set in .env:                                 $(c $RD '║')\n"
    printf "$(c $RD '║')  $(c $YL 'NVIDIA_NIM_API_KEY=nvapi-xxxxxxxxxxxx')         $(c $RD '║')\n"
    printf "$(c $RD '╚══════════════════════════════════════════════════╝')\n\n"
    read -p "  Continue anyway? (server will start but AI calls will fail) [y/N] " ans
    if [[ ! "$ans" =~ ^[Yy]$ ]]; then
      printf "  Aborted. Set your key and try again.\n"
      exit 1
    fi
  else
    printf "$(c $GR '✓') NVIDIA NIM key found (nvapi-...${nim_key: -4})\n"
  fi


  # Read ANTHROPIC_AUTH_TOKEN from .env if not set in environment
  local token="${ANTHROPIC_AUTH_TOKEN:-}"
  if [ -z "$token" ] && [ -f "$SCRIPT_DIR/.env" ]; then
    token=$(grep -E '^ANTHROPIC_AUTH_TOKEN=' "$SCRIPT_DIR/.env" 2>/dev/null \
      | cut -d= -f2 | tr -d '"' | tr -d "'" | tr -d ' ' | head -1 || true)
  fi
  export ANTHROPIC_AUTH_TOKEN="${token:-freecc}"

  cd "$SCRIPT_DIR"
  export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

  # Try uv first, then python3 directly
  if command -v uv >/dev/null 2>&1 && [ -f "pyproject.toml" ]; then
    uv run python3 -m uvicorn server:app \
      --host 127.0.0.1 --port 8082 \
      --timeout-graceful-shutdown 5 \
      --log-level warning \
      > "$FCC_LOG" 2>&1 &
  else
    python3 -m uvicorn server:app \
      --host 127.0.0.1 --port 8082 \
      --timeout-graceful-shutdown 5 \
      --log-level warning \
      > "$FCC_LOG" 2>&1 &
  fi

  echo $! > "$FCC_PIDFILE"
  wait_for_server
}

# ── Stop fcc-server ──────────────────────────────────────────────
stop_server() {
  if [ -f "$FCC_PIDFILE" ] && kill -0 "$(cat "$FCC_PIDFILE")" 2>/dev/null; then
    kill "$(cat "$FCC_PIDFILE")" 2>/dev/null || true
    rm -f "$FCC_PIDFILE"
    printf "$(c $GR '✓') fcc-server stopped\n"
  else
    printf "$(c $DIM '–') fcc-server not running\n"
  fi
}

# ── Stop JARVIS widget ───────────────────────────────────────────
stop_jarvis() {
  if [ -f "$JARVIS_PIDFILE" ] && kill -0 "$(cat "$JARVIS_PIDFILE")" 2>/dev/null; then
    kill "$(cat "$JARVIS_PIDFILE")" 2>/dev/null || true
    rm -f "$JARVIS_PIDFILE"
    printf "$(c $GR '✓') JARVIS widget stopped\n"
    return 0
  fi
  return 1
}

# ── Launch JARVIS GTK widget ─────────────────────────────────────
launch_jarvis() {
  printf "$(c $YL '▶') Launching JARVIS widget...\n"

  # Set token so GTK app can read it
  local token="${ANTHROPIC_AUTH_TOKEN:-}"
  if [ -z "$token" ] && [ -f "$SCRIPT_DIR/.env" ]; then
    token=$(grep -E '^ANTHROPIC_AUTH_TOKEN=' "$SCRIPT_DIR/.env" 2>/dev/null \
      | cut -d= -f2 | tr -d '"' | tr -d "'" | tr -d ' ' | head -1 || true)
  fi
  export ANTHROPIC_AUTH_TOKEN="${token:-freecc}"
  export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

  cd "$AI_DIR"
  python3 jarvis.py &
  local pid=$!
  echo $pid > "$JARVIS_PIDFILE"
  printf "$(c $GR '✓') JARVIS launched (PID %s)\n" "$pid"
}

# ── Show status ───────────────────────────────────────────────────
show_status() {
  printf "\n$(c $CY 'fcc-server:')  "
  if server_running; then
    printf "$(c $GR 'RUNNING') at %s\n" "$FCC_URL"
    printf "  Status: %s\n" "$(curl -sf "$FCC_URL/jarvis/status" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(f\"{d.get('file_count',0)} config files\")" 2>/dev/null || echo "ok")"
  else
    printf "$(c $RD 'OFFLINE')\n"
  fi

  printf "$(c $CY 'JARVIS widget:')  "
  if [ -f "$JARVIS_PIDFILE" ] && kill -0 "$(cat "$JARVIS_PIDFILE")" 2>/dev/null; then
    printf "$(c $GR 'RUNNING') (PID %s)\n" "$(cat "$JARVIS_PIDFILE")"
  else
    printf "$(c $DIM 'not running')\n"
  fi

  printf "$(c $CY 'Backend config:')  "
  python3 -c "
import json
try:
    with open('$CFG_FILE') as f:
        cfg = json.load(f)
    b = cfg.get('llm_backend','?')
    url = cfg.get('fcc_url','') if b=='fcc' else ''
    print(f'{b}  {url}')
except Exception as e:
    print(f'error reading config: {e}')
" 2>/dev/null || printf "?\n"

  echo ""
}

# ════════════════════════════════════════════════════════════════
#  Main dispatch
# ════════════════════════════════════════════════════════════════
case "${1:-}" in
  --server)
    banner
    fix_backend
    start_server
    ;;
  --stop)
    banner
    stop_jarvis
    stop_server
    ;;
  --status)
    show_status
    ;;
  --reset)
    banner
    printf "$(c $YL '▶') Resetting to fcc backend...\n"
    stop_jarvis
    fix_backend
    start_server
    launch_jarvis
    ;;
  ""|--toggle)
    # Toggle: if JARVIS is running, kill it. Otherwise start everything.
    if stop_jarvis; then
      printf "$(c $DIM '(JARVIS hidden — fcc-server still running)')\n"
      exit 0
    fi
    banner
    fix_backend
    start_server
    launch_jarvis
    printf "\n$(c $CY '  Active backend:') $(c $GR 'free-claude-code proxy')  %s\n" "$FCC_URL"
    printf "$(c $CY '  Admin UI:')        %s/admin\n" "$FCC_URL"
    printf "$(c $DIM '  Press SUPER+J again to hide JARVIS')\n\n"
    ;;
  *)
    printf "Usage: %s [--server|--stop|--status|--reset|--toggle]\n" "$0"
    exit 1
    ;;
esac
