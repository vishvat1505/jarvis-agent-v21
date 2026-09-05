#!/usr/bin/env bash
# Toggle JARVIS: kill if running, launch if not.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FCC_DIR="$(dirname "$DIR")"
PIDFILE="/tmp/jarvis.pid"

if [[ "$1" == "--stop" ]]; then
    [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null && rm -f "$PIDFILE"
    pkill -f "fcc-server" 2>/dev/null; exit 0
fi

# Toggle: kill if running
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")"; rm -f "$PIDFILE"; exit 0
fi

# Auto-start fcc server if backend=fcc and server not running
BACKEND=$(python3 -c "import json; d=json.load(open('$DIR/jarvis_config.json')); print(d.get('llm_backend','fcc'))" 2>/dev/null)
if [ "$BACKEND" = "fcc" ]; then
    if ! curl -sf http://127.0.0.1:8082/health >/dev/null 2>&1; then
        if [ -f "$FCC_DIR/server.py" ] && command -v uv &>/dev/null; then
            echo "[JARVIS] Starting fcc-server…"
            cd "$FCC_DIR"
            uv run fcc-server >> /tmp/fcc-server.log 2>&1 &
            sleep 2
        fi
    fi
fi

cd "$DIR"
python3 jarvis.py &
echo $! > "$PIDFILE"
