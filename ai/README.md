# J.A.R.V.I.S. — Hyprland Desktop AI

Iron Man-style floating AI assistant for Arch Linux + Hyprland.

## Quick Start

```bash
# 1. Run setup (installs deps, adds SUPER+J keybind)
bash ai/setup.sh

# 2. Edit jarvis_config.json — paste your OpenRouter key:
nano ai/jarvis_config.json
# set openrouter_api_key and use a :free model

# 3. Launch
bash ai/jarvis.sh
# or press SUPER+J
```

## Backend options (switch live in ⚙ Settings)

| Backend | Setup | Free? |
|---|---|---|
| `openrouter` | Paste key in ⚙ Settings | ✅ Free models (`:free` suffix) |
| `fcc` | Run `uv run fcc-server` + configure at /admin | ✅ With NIM free tier |
| `ollama` | `ollama serve && ollama pull qwen3:1.7b` | ✅ Fully local |
| `anthropic` | Paste Anthropic API key | ❌ Paid |

## Free OpenRouter models

```
deepseek/deepseek-r1:free
deepseek/deepseek-v3-base:free
meta-llama/llama-3.3-70b-instruct:free
google/gemma-3-27b-it:free
```

## What JARVIS can do

- **Hyprland config**: add/remove keybinds, edit settings, env vars, window rules
- **Live control**: `hyprctl` reload, switch workspace, move windows
- **System**: CPU/RAM/disk/GPU monitoring, process list, network
- **Apps**: launch/close, screenshot, screen recording
- **Audio/display**: volume, brightness, night mode, wallpaper
- **Files**: organise Downloads, backup configs, rename screenshots
- **Dev**: git status/commit, run tests, coding/pentest workspace presets
- **File analysis**: attach any .conf/.sh/.py and ask JARVIS to review/edit it

## Hyprland keybind

```ini
bind = SUPER, J, exec, bash ~/.config/hypr/ai/jarvis.sh
```
