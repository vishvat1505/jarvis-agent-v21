"""
hypr_commands.py - Hyprland-specific command implementations for JARVIS.
Covers: sessions, workspaces, window management, themes, screenshots,
screen recording, focus mode, GPU/network monitoring, daily reports,
and workspace layouts.

All heavy shell work delegates to hyprctl / existing tools.
"""

import os, json, datetime, glob, shutil, subprocess
from . import editor, scanner

SESSIONS_DIR = os.path.expanduser("~/.config/hypr/jarvis-sessions")
LAYOUTS_DIR  = os.path.expanduser("~/.config/hypr/jarvis-layouts")
REPORTS_DIR  = os.path.expanduser("~/.local/share/jarvis-reports")


def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip() or "(ok)"
    except Exception as e:
        return f"(error: {e})"


def _hyprctl(args):
    return _run(f"hyprctl {args}")


def _ensure_dirs():
    for d in (SESSIONS_DIR, LAYOUTS_DIR, REPORTS_DIR):
        os.makedirs(d, exist_ok=True)


# ============================================================ Sessions =====

def save_session(args=None):
    """Save currently open windows + their workspaces as a named session."""
    _ensure_dirs()
    name = (args or {}).get("name", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    raw = _hyprctl("-j clients")
    try:
        clients = json.loads(raw)
    except Exception:
        return f"Could not parse hyprctl output: {raw[:200]}"

    session = []
    for c in clients:
        session.append({
            "class":     c.get("class", ""),
            "title":     c.get("title", ""),
            "workspace": c.get("workspace", {}).get("id", 1),
            "at":        c.get("at", [0, 0]),
            "size":      c.get("size", [800, 600]),
        })

    path = os.path.join(SESSIONS_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump({"name": name, "apps": session}, f, indent=2)
    return f"Session '{name}' saved ({len(session)} windows) → {path}"


def restore_session(args=None):
    """Restore a previously saved session by name (or latest if none given)."""
    _ensure_dirs()
    name = (args or {}).get("name", "")
    if name:
        path = os.path.join(SESSIONS_DIR, f"{name}.json")
    else:
        files = sorted(glob.glob(os.path.join(SESSIONS_DIR, "*.json")))
        if not files:
            return "No saved sessions found. Use 'save session' first."
        path = files[-1]

    if not os.path.isfile(path):
        return f"Session file not found: {path}"

    with open(path) as f:
        data = json.load(f)

    results = []
    for app in data.get("apps", []):
        cls = app.get("class", "")
        ws  = app.get("workspace", 1)
        if cls:
            _run(f"hyprctl dispatch workspace {ws}")
            _run(f"{cls} &")
            results.append(f"Launched {cls} on workspace {ws}")

    return "\n".join(results) or "Nothing to restore."


def list_sessions(_args=None):
    _ensure_dirs()
    files = sorted(glob.glob(os.path.join(SESSIONS_DIR, "*.json")))
    if not files:
        return "No saved sessions."
    lines = []
    for f in files:
        name = os.path.basename(f).replace(".json","")
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
        lines.append(f"  {name}  ({mtime})")
    return "Saved sessions:\n" + "\n".join(lines)


def open_workspace_preset(args):
    """Switch to a named workspace preset: ai, dev, cyber, coding, pentest."""
    preset = (args or {}).get("preset", "").lower()
    MAP = {
        "ai":       1,
        "dev":      2,
        "development": 2,
        "coding":   3,
        "cyber":    4,
        "cybersecurity": 4,
        "pentest":  4,
        "penetration testing": 4,
        "presentation": 5,
    }
    ws = MAP.get(preset)
    if not ws:
        return (f"Unknown preset '{preset}'. Known: " + ", ".join(MAP.keys()))
    _hyprctl(f"dispatch workspace {ws}")
    return f"Switched to workspace {ws} ({preset})"


# ======================================================= Window management =

def show_running_apps(_args=None):
    raw = _hyprctl("-j clients")
    try:
        clients = json.loads(raw)
    except Exception:
        return _run("hyprctl clients")
    if not clients:
        return "No windows open."
    lines = []
    for c in clients:
        ws    = c.get("workspace", {}).get("id", "?")
        cls   = c.get("class", "?")
        title = c.get("title", "")[:50]
        lines.append(f"  WS{ws}  {cls}  —  {title}")
    return f"{len(clients)} windows:\n" + "\n".join(lines)


def move_window_to_workspace(args):
    app   = (args or {}).get("app", "")
    ws    = (args or {}).get("workspace", 1)
    if not app:
        return "Specify app name, e.g. 'move firefox to workspace 2'."
    # focus the window by class then move it
    out = _hyprctl(f"dispatch focuswindow class:{app}")
    out += "\n" + _hyprctl(f"dispatch movetoworkspace {ws},class:{app}")
    return f"Moved {app} to workspace {ws}.\n{out}"


def arrange_windows(_args=None):
    return _hyprctl("dispatch layoutmsg orientationcycle") + \
           "\n" + _hyprctl("dispatch layoutmsg distribute")


def save_workspace_layout(args=None):
    _ensure_dirs()
    name = (args or {}).get("name", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    raw = _hyprctl("-j clients")
    try:
        clients = json.loads(raw)
    except Exception:
        return f"Could not parse clients: {raw[:200]}"

    layout = [{"class": c.get("class",""), "workspace": c.get("workspace",{}).get("id",1),
                "at": c.get("at",[0,0]), "size": c.get("size",[800,600])} for c in clients]

    path = os.path.join(LAYOUTS_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(layout, f, indent=2)
    return f"Layout '{name}' saved ({len(layout)} windows) → {path}"


def restore_workspace_layout(args=None):
    _ensure_dirs()
    name = (args or {}).get("name", "")
    if name:
        path = os.path.join(LAYOUTS_DIR, f"{name}.json")
    else:
        files = sorted(glob.glob(os.path.join(LAYOUTS_DIR, "*.json")))
        if not files:
            return "No saved layouts. Use 'save workspace layout' first."
        path = files[-1]

    if not os.path.isfile(path):
        return f"Layout not found: {path}"

    with open(path) as f:
        layout = json.load(f)

    results = []
    for item in layout:
        cls = item.get("class","")
        ws  = item.get("workspace", 1)
        if cls:
            _hyprctl(f"dispatch movetoworkspace {ws},class:{cls}")
            results.append(f"Moved {cls} → WS{ws}")
    return "\n".join(results) or "Layout restored."


# ============================================================ Screenshots ==

def take_screenshot(args=None):
    outdir = os.path.expanduser((args or {}).get("path", "~/Pictures/Screenshots"))
    os.makedirs(outdir, exist_ok=True)
    ts   = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(outdir, f"screenshot_{ts}.png")

    if shutil.which("grim"):
        out = _run(f"grim '{path}'")
        return f"Screenshot saved: {path}\n{out}"
    if shutil.which("scrot"):
        out = _run(f"scrot '{path}'")
        return f"Screenshot saved: {path}\n{out}"
    return "No screenshot tool found. Install grim: sudo pacman -S grim"


def record_screen(args=None):
    action = (args or {}).get("action", "start").lower()
    outdir = os.path.expanduser("~/Videos/Recordings")
    os.makedirs(outdir, exist_ok=True)

    if action == "stop":
        return _run("pkill wf-recorder || pkill ffmpeg") + "\nRecording stopped."

    if shutil.which("wf-recorder"):
        ts   = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(outdir, f"recording_{ts}.mp4")
        _run(f"wf-recorder -f '{path}' &")
        return f"Recording started → {path}\nSay 'stop recording' or pkill wf-recorder to stop."
    return "wf-recorder not found. Install: sudo pacman -S wf-recorder"


# ============================================================ Focus mode ===

FOCUS_CONF = os.path.expanduser("~/.config/hypr/jarvis-focus.conf")

def start_focus_mode(args=None, confirm_fn=None):
      """Enable focus mode: pause notifications, switch to workspace 1."""
      _run("dunstctl set-paused true 2>/dev/null || true")
      _hyprctl("dispatch workspace 1")
      return ("Focus mode enabled:\n"
              "  • Notifications paused (dunst)\n"
              "  • Switched to workspace 1\n"
              "Say 'end focus mode' to restore.")
   
def end_focus_mode(args=None, confirm_fn=None):
      """Disable focus mode: restore notifications."""
      _run("dunstctl set-paused false 2>/dev/null || true")
      return "Focus mode disabled. Notifications restored."


# ============================================================== Themes =====

def _ai_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_repo_ctx():
    ai_dir = _ai_dir()
    root   = scanner.find_repo_root(ai_dir)
    cfg_p  = os.path.join(ai_dir, "lib", "config.json")
    with open(cfg_p) as f:
        cfg = json.load(f)
    return root, cfg


def switch_theme(args, confirm_fn):
    """Switch between dark/light themes by editing UserSettings.conf and
    triggering hyprctl reload."""
    mode = (args or {}).get("mode", "dark").lower()
    try:
        root, cfg = _load_repo_ctx()
    except Exception as e:
        return f"Could not locate repo: {e}"

    settings_file = cfg.get("settings_file",
        "Hyprland-Dots/config/hypr/UserConfigs/UserSettings.conf")

    # common theme variable names used in Arch-Hyprland
    key   = "$THEME_STYLE"
    value = "dark" if mode == "dark" else "light"

    ok, msg = editor.replace_setting(root, settings_file, key, value, confirm_fn)
    if ok:
        _hyprctl("reload")
        return f"Switched to {mode} theme and reloaded Hyprland.\n{msg}"
    return msg


def enable_presentation_mode(args=None, confirm_fn=None):
    """Disable gaps, borders, and animations for presentations."""
    cmds = [
        "keyword general:gaps_in 0",
        "keyword general:gaps_out 0",
        "keyword general:border_size 0",
        "keyword animations:enabled false",
    ]
    results = [_hyprctl(c) for c in cmds]
    return "Presentation mode enabled (no gaps/borders/animations).\n" + "\n".join(results)


def disable_presentation_mode(_args=None):
    """Restore normal gaps, borders, animations."""
    try:
        root, cfg = _load_repo_ctx()
        # just reload to restore from config
        _hyprctl("reload")
        return "Presentation mode disabled. Hyprland config reloaded."
    except Exception:
        _hyprctl("reload")
        return "Presentation mode disabled. Config reloaded."


# ======================================================= System monitoring =

def check_gpu_usage(_args=None):
    # try nvidia, then amd, then intel
    if shutil.which("nvidia-smi"):
        return _run("nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader")
    if os.path.isfile("/sys/class/drm/card0/device/gpu_busy_percent"):
        busy = open("/sys/class/drm/card0/device/gpu_busy_percent").read().strip()
        vram_used = ""
        try:
            vram_used = open("/sys/class/drm/card0/device/mem_info_vram_used").read().strip()
            vram_total= open("/sys/class/drm/card0/device/mem_info_vram_total").read().strip()
            vram_used = f"  VRAM: {int(vram_used)//1024//1024}MB / {int(vram_total)//1024//1024}MB"
        except Exception:
            pass
        return f"AMD GPU busy: {busy}%{vram_used}"
    if shutil.which("intel_gpu_top"):
        return _run("timeout 2 intel_gpu_top -J 2>/dev/null | head -30 || echo 'intel_gpu_top requires root or group membership'")
    return "No GPU monitoring tool found (nvidia-smi / AMD sysfs / intel_gpu_top)."


def check_network_usage(_args=None):
    out = _run("cat /proc/net/dev | awk 'NR>2{print $1, \"RX:\", $2, \"TX:\", $10}'")
    # also try vnstat if available
    if shutil.which("vnstat"):
        out += "\n\n" + _run("vnstat -tr 2 2>/dev/null | tail -10")
    return out


def monitor_system_health(_args=None):
    cpu  = _run("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4\"% used\"}'")
    mem  = _run("free -h | awk '/Mem:/{print $3\"/\"$2\" used\"}'")
    disk = _run("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")'")
    temp = _run("cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | awk '{printf \"%.1f°C \", $1/1000}' || sensors 2>/dev/null | grep 'Core 0' | head -1")
    procs = _run("ps -eo pid,comm,%cpu --sort=-%cpu | head -6")
    gpu  = check_gpu_usage()
    return (
        f"System Health\n"
        f"  CPU:    {cpu}\n"
        f"  Memory: {mem}\n"
        f"  Disk:   {disk}\n"
        f"  Temp:   {temp}\n"
        f"  GPU:    {gpu}\n\n"
        f"Top processes:\n{procs}"
    )


# =========================================================== File ops =====

def clean_downloads(args=None, confirm_fn=None):
    folder = os.path.expanduser((args or {}).get("path", "~/Downloads"))
    if not os.path.isdir(folder):
        return f"Not found: {folder}"

    TYPE_MAP = {
        "Images":    [".jpg",".jpeg",".png",".gif",".webp",".svg"],
        "Documents": [".pdf",".docx",".doc",".txt",".md",".odt",".xlsx",".pptx"],
        "Archives":  [".zip",".tar",".gz",".rar",".7z",".xz"],
        "Videos":    [".mp4",".mkv",".webm",".mov",".avi"],
        "Audio":     [".mp3",".wav",".flac",".ogg",".m4a"],
        "Installers":[".AppImage",".deb",".rpm",".sh"],
        "Code":      [".py",".js",".ts",".html",".css",".json",".yaml",".toml"],
    }
    moves = []
    for fn in os.listdir(folder):
        full = os.path.join(folder, fn)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(fn)[1].lower()
        for subfolder, exts in TYPE_MAP.items():
            if ext in exts:
                moves.append((full, os.path.join(folder, subfolder, fn)))
                break

    if not moves:
        return "Downloads folder is already clean."

    preview = f"Will move {len(moves)} files into subfolders:\n"
    preview += "\n".join(f"  {os.path.basename(s)} → {os.path.relpath(d, folder)}"
                         for s, d in moves[:20])
    if len(moves) > 20:
        preview += f"\n  ... and {len(moves)-20} more"

    if confirm_fn and not confirm_fn(preview):
        return "Cancelled."

    for src, dst in moves:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
    return f"Cleaned Downloads: moved {len(moves)} files."


def archive_old_files(args=None, confirm_fn=None):
    folder  = os.path.expanduser((args or {}).get("path", "~/Downloads"))
    days    = int((args or {}).get("days", 30))
    cutoff  = datetime.datetime.now().timestamp() - days * 86400
    archive = os.path.join(folder, f"archive-{datetime.date.today()}")

    files = []
    for fn in os.listdir(folder):
        full = os.path.join(folder, fn)
        if os.path.isfile(full) and os.path.getmtime(full) < cutoff:
            files.append(full)

    if not files:
        return f"No files older than {days} days in {folder}."

    preview = f"Will archive {len(files)} file(s) older than {days} days → {archive}/\n"
    preview += "\n".join(f"  {os.path.basename(f)}" for f in files[:20])

    if confirm_fn and not confirm_fn(preview):
        return "Cancelled."

    os.makedirs(archive, exist_ok=True)
    for f in files:
        shutil.move(f, os.path.join(archive, os.path.basename(f)))
    return f"Archived {len(files)} file(s) to {archive}/"


def backup_hypr_configs(args=None, confirm_fn=None):
    src = os.path.expanduser("~/.config/hypr")
    if not os.path.isdir(src):
        return f"~/.config/hypr not found."
    ts  = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.expanduser(f"~/hypr-backup-{ts}.tar.gz")
    preview = f"Backup:\n  Source: {src}\n  Dest:   {dst}"
    if confirm_fn and not confirm_fn(preview):
        return "Cancelled."
    out = _run(f"tar -czf '{dst}' -C ~/.config hypr", timeout=60)
    if os.path.isfile(dst):
        size = os.path.getsize(dst) // 1024
        return f"Backup saved: {dst} ({size} KB)"
    return f"Backup may have failed: {out}"


def restore_hypr_configs(args=None, confirm_fn=None):
    pattern = os.path.expanduser("~/hypr-backup-*.tar.gz")
    files   = sorted(glob.glob(pattern))
    if not files:
        return "No backup files found (expected ~/hypr-backup-*.tar.gz)."
    latest  = files[-1]
    preview = f"Restore from: {latest}\nThis will overwrite ~/.config/hypr/"
    if confirm_fn and not confirm_fn(preview):
        return "Cancelled."
    out = _run(f"tar -xzf '{latest}' -C ~/.config/", timeout=60)
    _hyprctl("reload")
    return f"Restored from {latest}. Hyprland reloaded.\n{out}"


# ============================================================ Reports ======

def summarize_activity(_args=None):
    today = datetime.date.today().isoformat()
    lines = [f"Activity summary — {today}"]

    # recently modified files
    recent = _run(
        "find ~ -maxdepth 4 -newer /tmp -type f "
        r"\( -name '*.py' -o -name '*.sh' -o -name '*.conf' -o -name '*.md' \) "
        "2>/dev/null | grep -v __pycache__ | head -15"
    )
    lines.append("\nRecently modified files:\n" + (recent or "  none"))

    # hyprland log
    log = _run("journalctl -t Hyprland --since today --no-pager -n 20 2>/dev/null || "
               "cat ~/.local/share/hyprland/hyprland.log 2>/dev/null | tail -20")
    lines.append("\nHyprland log (today):\n" + (log or "  unavailable"))

    # disk
    disk = _run("df -h ~ | tail -1")
    lines.append(f"\nDisk: {disk}")

    return "\n".join(lines)


def generate_daily_report(_args=None):
    _ensure_dirs()
    today   = datetime.date.today().isoformat()
    content = summarize_activity()
    content += "\n\n" + monitor_system_health()

    path = os.path.join(REPORTS_DIR, f"report-{today}.txt")
    with open(path, "w") as f:
        f.write(content)
    return f"Daily report saved: {path}\n\n{content}"


def open_recent_project(_args=None):
    # check common dev dirs
    hits = []
    for base in ["~/Projects", "~/code", "~/dev", "~/src", "~/workspace"]:
        base = os.path.expanduser(base)
        if not os.path.isdir(base):
            continue
        dirs = sorted(
            (d for d in (os.path.join(base, x) for x in os.listdir(base))
             if os.path.isdir(d)),
            key=os.path.getmtime, reverse=True
        )
        hits.extend(dirs[:3])
    if not hits:
        return "No project directories found in ~/Projects, ~/code, ~/dev, ~/src."
    recent = hits[0]
    if shutil.which("code"):
        subprocess.Popen(f"code '{recent}' &", shell=True)
        return f"Opened recent project in VS Code: {recent}"
    if shutil.which("kitty"):
        subprocess.Popen(f"kitty --working-directory='{recent}' &", shell=True)
        return f"Opened terminal in: {recent}"
    return f"Most recent project: {recent}\n(VS Code / kitty not found to open it)"


# ================================================= Env launchers ===========

def launch_coding_env(_args=None):
    _hyprctl("dispatch workspace 3")
    cmds = []
    if shutil.which("code"):
        subprocess.Popen("code &", shell=True)
        cmds.append("VS Code")
    if shutil.which("kitty"):
        subprocess.Popen("kitty &", shell=True)
        cmds.append("Kitty terminal")
    return "Coding environment launched on WS3: " + ", ".join(cmds or ["(no apps found)"])


def launch_pentest_env(_args=None):
    _hyprctl("dispatch workspace 4")
    cmds = []
    for app, name in [("wireshark","Wireshark"), ("burpsuite","Burp Suite"),
                       ("kitty","terminal"), ("firefox","Firefox")]:
        if shutil.which(app):
            subprocess.Popen(f"{app} &", shell=True)
            cmds.append(name)
    return "Pentest environment launched on WS4: " + ", ".join(cmds or ["(tools not found)"])


def launch_ai_env(_args=None):
    _hyprctl("dispatch workspace 1")
    cmds = []
    if shutil.which("kitty"):
        subprocess.Popen("kitty &", shell=True)
        cmds.append("Kitty (for ollama)")
    if shutil.which("code"):
        subprocess.Popen("code &", shell=True)
        cmds.append("VS Code")
    return "AI workspace launched on WS1: " + ", ".join(cmds or ["(no apps found)"])


# ============================================================ Volume =======

def volume_up(_args=None):
    return _run("wpctl set-volume @DEFAULT_AUDIO_SINK@ 10%+")

def volume_down(_args=None):
    return _run("wpctl set-volume @DEFAULT_AUDIO_SINK@ 10%-")

def mute_volume(_args=None):
    return _run("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")

def check_volume(_args=None):
    return _run("wpctl get-volume @DEFAULT_AUDIO_SINK@")
