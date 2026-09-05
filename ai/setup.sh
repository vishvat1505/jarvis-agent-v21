#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FCC_DIR="$(dirname "$DIR")"

echo "══════════════════════════════════════════"
echo "  J.A.R.V.I.S. Setup — Arch + Hyprland"
echo "══════════════════════════════════════════"

echo "[1/4] System packages…"
sudo pacman -S --needed --noconfirm \
    python python-gobject python-cairo gtk3 gtk-layer-shell \
    python-pip curl git 2>/dev/null || true

echo "[2/4] fcc-server deps…"
if [ -f "$FCC_DIR/pyproject.toml" ]; then
    cd "$FCC_DIR" && uv sync && cd "$DIR"
fi

echo "[3/4] Hyprland keybind…"
HYPR="$HOME/.config/hypr/UserConfigs/UserKeybinds.conf"
[ -f "$HOME/.config/hypr/hyprland.conf" ] || HYPR="$HOME/.config/hypr/hyprland.conf"
BIND="bind = SUPER, J, exec, bash $DIR/jarvis.sh"
if [ -f "$HYPR" ] && ! grep -q "jarvis.sh" "$HYPR" 2>/dev/null; then
    read -p "  Add SUPER+J to $HYPR? [y/N] " a
    if [[ "$a" =~ ^[Yy]$ ]]; then
        echo "" >> "$HYPR"
        echo "# JARVIS AI toggle" >> "$HYPR"
        echo "$BIND" >> "$HYPR"
        echo "  Added SUPER+J keybind"
    fi
fi

echo "[4/4] Configure backend…"
echo ""
echo "  Edit: $DIR/jarvis_config.json"
echo "  Set llm_backend to one of:"
echo "    openrouter  — free models available (recommended to start)"
echo "    fcc         — use fcc-server with NIM/OpenRouter/etc"  
echo "    ollama      — fully local"
echo ""
echo "══════════════════════════════════════════"
echo "  Done! Launch JARVIS:"
echo "    bash $DIR/jarvis.sh"
echo "  Or press SUPER+J (if keybind added)"
echo "══════════════════════════════════════════"
