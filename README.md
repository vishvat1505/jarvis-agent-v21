<div align="center">

# J.A.R.V.I.S.
### Just A Rather Very Intelligent System

**Autonomous Hyprland Desktop Agent — Arch Linux**

[![Python](https://img.shields.io/badge/Python-3.14-blue?logo=python)](https://python.org)
[![Hyprland](https://img.shields.io/badge/Hyprland-0.55+-58E1FF?logo=wayland)](https://hyprland.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![LLM Backend](https://img.shields.io/badge/Backend-NVIDIA%20NIM%20%7C%20OpenRouter%20%7C%20Ollama-76B900)](https://build.nvidia.com)

*A natural-language desktop controller that understands your system in real time — not a chatbot, an AI operating system layer.*

</div>

---

## What Is This?

JARVIS is a **GTK3 floating overlay widget** that sits on your Hyprland desktop and gives you full AI-powered control of your Linux system through natural conversation.

It is **not a ChatGPT wrapper**. It is a purpose-built autonomous agent that:
- Reads your machine's real hardware specs, running processes, open windows, current audio, battery, network, and Hyprland config **before every AI response**
- Routes ~80% of common commands through a **zero-latency regex intent layer** — no LLM call, no network, instant execution
- Falls back to a **full LLM tool-calling loop** only when needed, with the complete machine context already injected
- Persists **user preferences** across sessions — your name, preferred apps, notes, command history

---

## Architecture

```
User speaks / types
        │
        ▼
┌───────────────────────────┐
│  Intent Layer (177 rules) │  ◄── instant, no network
│  regex + NLU heuristics   │
└────────────┬──────────────┘
             │ no match
             ▼
┌────────────────────────────────────────────────────────────┐
│  System Context Builder  (system_state.py)                 │
│  CPU · RAM · GPU · Battery · Temps · Audio · Network       │
│  Open Windows · Workspaces · Monitors · Installed Apps     │
│  Recent Files · Hyprland Config · User Preferences         │
└────────────────────────────────────┬───────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────┐
│  LLM Tool-Calling Loop  (agent.py)                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  free-claude-code proxy  (FastAPI + uvicorn)         │  │
│  │  Providers: NVIDIA NIM · OpenRouter · Groq           │  │
│  │           · Mistral · Gemini · Ollama · LM Studio    │  │
│  │           · Cerebras · DeepSeek · Fireworks + more   │  │
│  └──────────────────────────────────────────────────────┘  │
│  Tool Registry (122 tools across 14 categories)            │
└────────────────────────────────────────────────────────────┘
```

---

## Features

### Desktop Control
| Category | What You Can Say |
|---|---|
| **Apps** | "open firefox", "open discord app", "launch vscode" |
| **Websites** | "open a website named google in firefox", "go to youtube", "search for python on google" |
| **Files** | "open a file named jarvis in my downloads", "open that v12", "edit report.pdf in vscode" |
| **Folders** | "create a folder named mine in my downloads", "open folder projects in vscode", "list my downloads" |
| **Wallpaper** | "change my wallpaper to 11.png", "random wallpaper", "set wallpaper to nature" |
| **Windows** | "move this firefox to workspace 10", "move all browsers to workspace 8", "close this firefox in workspace8" |
| **Workspaces** | "go to workspace 3", "move all windows to workspace 8", "switch to workspace10" |

### System Management
| Category | What You Can Say |
|---|---|
| **Audio** | "set volume to 60", "mute", "unmute mic", "play", "pause" |
| **Display** | "brightness 80", "enable night mode", "screenshot region" |
| **Power** | "suspend", "shut down the computer", "reboot", "hibernate" |
| **Battery** | "battery status" |
| **Recording** | "start recording", "stop recording" |
| **Network** | "wifi list", "connect wifi HomeNetwork", "turn off wifi" |
| **Bluetooth** | "turn on bluetooth", "connect bluetooth AirPods", "list bluetooth devices" |
| **Clipboard** | "copy to clipboard hello world", "what's in clipboard", "clipboard history" |
| **Notifications** | "clear notifications", (sends desktop notifications) |

### Linux System
| Category | What You Can Say |
|---|---|
| **Packages** | "install package neovim", "search for package btop", "update system", "what packages are installed" |
| **Services** | "service status NetworkManager", "restart the service nginx", "stop the service bluetooth", "list running services" |
| **Processes** | "kill process chrome", "list processes", "system status" |
| **Filesystem** | "find files named report", "disk usage", "file info report.pdf", "copy file X to downloads", "rename file X to Y" |

### Hyprland Config
| What You Can Say |
|---|
| "add keybind SUPER+B to open firefox" |
| "set blur size to 10" |
| "disable animations" |
| "set border size to 3" |
| "add startup app waybar" |
| "apply gaming preset" / "apply minimal preset" |

### Memory & Preferences
| What You Can Say |
|---|
| "my name is Charvish" → JARVIS remembers across sessions |
| "remember that I prefer dark wallpapers" |
| "my preferred browser is firefox" |
| "what do you remember?" |

---

## Installation

### Requirements
- Arch Linux + Hyprland
- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager
- A free [NVIDIA NIM API key](https://build.nvidia.com/settings/api-keys) (or OpenRouter / Ollama)
- GTK3, GtkLayerShell (`python-gobject`, `gtk-layer-shell`)

### 1. Clone

```bash
git clone <repo-url> jarvis
cd jarvis
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:
```env
# NVIDIA NIM (free tier, fastest)
NVIDIA_NIM_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx

# Optional alternatives
# OPENROUTER_API_KEY=sk-or-...
# GROQ_API_KEY=gsk_...
# ANTHROPIC_AUTH_TOKEN=...
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Launch

```bash
# Start everything (proxy server + JARVIS widget)
bash jarvis.sh

# Or use the Hyprland keybind (add to UserKeybinds.conf):
# bind = SUPER, J, exec, bash /path/to/jarvis/jarvis.sh
```

### jarvis.sh commands

```bash
bash jarvis.sh             # launch / toggle (hide if running)
bash jarvis.sh --server    # start proxy server only
bash jarvis.sh --stop      # stop everything
bash jarvis.sh --status    # show server + widget status
bash jarvis.sh --reset     # reset backend config and restart
```

---

## LLM Providers

The proxy layer (`free-claude-code`) supports **15+ providers** via a unified API translation layer:

| Provider | Notes |
|---|---|
| **NVIDIA NIM** | Default. Free tier available. Fastest inference. |
| **OpenRouter** | Access to 100+ models. Free models available. |
| **Groq** | Ultra-fast inference. Free tier. |
| **Mistral / Codestral** | European AI, strong coding models. |
| **Google Gemini** | Multimodal support. |
| **DeepSeek** | Very capable, low cost. |
| **Cerebras** | Wafer-scale inference. |
| **Fireworks / Kimi / Wafer** | Additional options. |
| **Ollama** | Fully local, no API key. |
| **LM Studio** | Local GUI-based inference. |
| **LlamaCPP** | Direct GGUF model loading. |

Switch providers via the admin UI at `http://127.0.0.1:8082/admin` without restarting.

---

## How It Works

### Two-Tier Command Dispatch

**Tier 1 — Intent Layer (177 regex rules, ~0ms)**

Every user message is matched against a hand-tuned set of patterns before the LLM is ever contacted. This covers the 80% case — opening apps, controlling audio, managing files, switching workspaces, changing wallpapers, etc. If a pattern matches, the tool runs instantly with no network call.

**Tier 2 — LLM Tool-Calling Loop (when intent layer misses)**

If no pattern matches, the agent:
1. Reads **live system state** — CPU/RAM/GPU, open windows, audio, network, battery, running processes, installed apps, recent files, Hyprland config
2. Merges that with a **cached full hardware scan** (run in the background at startup)
3. Injects this as a compact context string (~600 tokens) before the LLM call
4. Runs a tool-calling loop (up to 8 turns) with access to all 122 tools
5. Returns a grounded, accurate response — no guessing about your machine

### System State — What JARVIS Knows

At every LLM call, JARVIS knows:

```
USER: charvish@charvish (Charvish)
OS:   Arch Linux kernel=6.11.0-arch1-1
HW:   CPU=AMD Ryzen 7 7745HX (16 cores)  RAM=32.0 GB  GPU=NVIDIA RTX 4060

RESOURCES: CPU=12.4%  RAM=8.1/32.0GB (25.3%)  Disk=45G/500G (9%)  Load=1.2 0.8 0.6
  Temps=Core 0:52C  Battery=87% (Discharging)

DESKTOP:
  Monitor: eDP-1 2560x1600@165  
  Active:  firefox -- GitHub - JARVIS (WS2)
  Windows:
    WS1: kitty:~/projects  code:jarvis/tools.py
    WS2: firefox:GitHub — JARVIS
    WS3: discord:Discord

AUDIO: vol=0.85  Playing: kitty: bohemian rhapsody -- Queen [Playing]
NET:   wifi=HomeNetwork  ip=192.168.1.105/24  connections=12

INSTALLED: browsers:firefox,chromium  editors:code,nvim  terminals:kitty,alacritty
WALLPAPERS: ~/Pictures/wallpapers (47 imgs)
PREFS:  browser=firefox  editor=code  terminal=kitty
RECENT: report.pdf, jarvis-agent.zip, notes.txt
```

### App Discovery — All Arch Install Methods

JARVIS finds apps regardless of how they were installed:

| Method | Where JARVIS looks |
|---|---|
| pacman/AUR | `/usr/bin`, `/usr/local/bin`, `~/.local/bin` |
| Flatpak | `~/.local/share/flatpak/exports/bin` + `share/applications` |
| Snap | `/snap/bin` + desktop entries |
| AppImage | `~/Applications`, `~/Downloads`, `~/.local/bin` |
| Manual / /opt | `/opt/*/` subdirectories |
| .desktop files | All `share/applications` dirs (best source of human-friendly names) |

Fuzzy matching via `difflib` means "vs code" → `code`, "chrome" → `google-chrome-stable`, "discord" → whichever Discord client you actually have (`vesktop`/`legcord`/`equibop`/`discord`).

---

## Project Structure

```
jarvis/
├── ai/
│   ├── jarvis.py          # GTK3 floating overlay widget (arc reactor UI)
│   └── lib/
│       ├── agent.py       # Main agent loop, tool dispatch, LLM integration
│       ├── intent.py      # 177-rule instant command matcher (no LLM)
│       ├── tools.py       # 122 system tools across 14 categories
│       ├── system_state.py # Real-time machine intelligence + UserPrefs
│       ├── prompt.py      # System prompt with full tool directory
│       ├── terminal.py    # Safe shell execution with safety checks
│       ├── llm.py         # LLM client (speaks to fcc proxy)
│       └── hypr_config.py # Hyprland config reader/writer
├── providers/             # 15+ LLM provider adapters
├── core/                  # Anthropic ↔ OpenAI protocol translation
├── api/                   # FastAPI proxy server
├── cli/                   # CLI launchers and entrypoints
├── messaging/             # Discord / Telegram bot adapters
├── jarvis.sh              # Launch script
├── server.py              # Proxy server entry point
└── pyproject.toml         # Python 3.14, uv, ruff, pytest config
```

---

## Resume Highlights

This project demonstrates:

- **Custom NLU pipeline** — a two-tier hybrid architecture (regex intent layer + LLM tool-calling) that routes commands to zero-latency execution for common cases while preserving full LLM reasoning for novel requests
- **LLM protocol translation layer** — custom Anthropic Messages ↔ OpenAI Responses translation with streaming SSE reconstruction, tool-use block handling, and stream recovery across 15 upstream providers
- **Real-time system telemetry** — live CPU/RAM/GPU/temp/battery/network reads injected as machine-readable context before every LLM call, so the model never guesses about the machine it's running on
- **Install-method-agnostic app discovery** — resolves spoken app names across all Arch install methods (pacman, AUR, Flatpak user+system, Snap, AppImage, `/opt`) using `.desktop` file parsing as the canonical name source
- **Natural-language phrase parsing** — strips conversational filler, resolves pronouns (`"it"`, `"that"`) from session context, extracts directory and app hints from arbitrary word order, and handles compound sentences (`"open firefox and make youtube open in it"`)
- **Safety-aware shell execution** — tiered safety checks (blocked/confirm/allowed) on every shell command before execution, with confirmation prompts for destructive operations
- **Persistent user memory** — cross-session user preferences (name, default apps, workspace labels, notes, command history) stored in `~/.config/hypr/jarvis-prefs.json`

---

## Configuration

`ai/jarvis_config.json` — auto-created on first run:

```json
{
  "llm_backend": "fcc",
  "fcc_url": "http://127.0.0.1:8082",
  "fcc_model": "claude-sonnet-4-6",
  "fcc_max_tokens": 2048
}
```

Switch model/backend via the admin UI or edit this file directly. The proxy server does not need to restart when switching providers.

---

## Voice (Optional)

```bash
# NVIDIA Riva (cloud, needs GPU)
uv sync --extra voice

# Local Whisper (offline)
uv sync --extra voice_local
```

---

## Development

```bash
# Run tests
uv run pytest -v --tb=short

# Lint + format
uv run ruff format
uv run ruff check --fix

# Type check
uv run ty check

# Full CI sequence
./scripts/ci.sh
```

---

## Acknowledgements

Built on:
- [Hyprland](https://hyprland.org) — the Wayland compositor this was built for
- [free-claude-code](https://github.com/anthropics/claude-code) — the LLM proxy layer
- GTK3 + GtkLayerShell — native Wayland overlay
- Cairo — custom UI rendering
- [uv](https://docs.astral.sh/uv/) — Python package management

---

<div align="center">

*"Sometimes you gotta run before you can walk."*

**— Tony Stark**

</div>
