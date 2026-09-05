"""
system_state.py  --  Real-time system intelligence for JARVIS.
Gathers CPU/RAM/GPU/temps/battery/network/audio/Hyprland state,
installed apps, home tree, recent files, and user preferences.
Produces a compact LLM-readable context string injected before every call.
"""

import os, json, subprocess, datetime, shutil, re, threading, time

STATE_FILE = os.path.expanduser("~/.config/hypr/jarvis-state.json")
PREFS_FILE = os.path.expanduser("~/.config/hypr/jarvis-prefs.json")
HYPR_DIR   = os.path.expanduser("~/.config/hypr")
HOME       = os.path.expanduser("~")


def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:
        return ""

def _json(cmd, timeout=8):
    raw = _run(cmd, timeout)
    try:   return json.loads(raw)
    except Exception: return None

def _read(path):
    try:
        with open(os.path.expanduser(path)) as f:
            return f.read()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Hardware fingerprint (cached -- never changes)
# ---------------------------------------------------------------------------

def read_hardware():
    hw = {}
    cpuinfo = _read("/proc/cpuinfo")
    m = re.search(r"model name\s*:\s*(.+)", cpuinfo)
    hw["cpu_model"]   = m.group(1).strip() if m else "Unknown"
    hw["cpu_cores"]   = _run("nproc --all")
    hw["cpu_threads"] = _run("nproc")
    meminfo = _read("/proc/meminfo")
    m = re.search(r"MemTotal:\s+(\d+)", meminfo)
    hw["ram_total_gb"] = round(int(m.group(1)) / 1048576, 1) if m else "?"
    hw["gpus"] = []
    for line in _run("lspci | grep -E 'VGA|3D|Display'").splitlines():
        hw["gpus"].append(line.split(":", 2)[-1].strip())
    if shutil.which("nvidia-smi"):
        hw["nvidia"] = _run(
            "nvidia-smi --query-gpu=name,driver_version,memory.total "
            "--format=csv,noheader")
    hw["disks"]    = _run("lsblk -d -o NAME,SIZE,MODEL,ROTA --noheadings | grep -v loop")
    bat_base = "/sys/class/power_supply"
    hw["has_battery"] = any(
        d.startswith(("BAT","battery"))
        for d in (os.listdir(bat_base) if os.path.isdir(bat_base) else []))
    hw["kernel"]   = _run("uname -r")
    hw["arch"]     = _run("uname -m")
    hw["distro"]   = _run("cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'")
    hw["hostname"] = _run("hostname")
    hw["user"]     = _run("whoami")
    return hw


# ---------------------------------------------------------------------------
# Live state
# ---------------------------------------------------------------------------

def read_live_resources():
    res = {}
    try:
        def _cpu():
            line = open("/proc/stat").readline().split()[1:]
            return [int(x) for x in line]
        s1 = _cpu(); time.sleep(0.2); s2 = _cpu()
        idle  = (s2[3]+s2[4]) - (s1[3]+s1[4])
        total = sum(s2) - sum(s1)
        res["cpu_pct"] = round(100*(1-idle/total), 1) if total else 0
    except Exception:
        res["cpu_pct"] = "?"

    meminfo = _read("/proc/meminfo")
    def _mi(k):
        m = re.search(rf"{k}:\s+(\d+)", meminfo)
        return int(m.group(1)) if m else 0
    total = _mi("MemTotal"); avail = _mi("MemAvailable"); used = total-avail
    res["ram_used_gb"]  = round(used/1048576, 1)
    res["ram_total_gb"] = round(total/1048576, 1)
    res["ram_pct"]      = round(100*used/total, 1) if total else 0
    res["disk_root"]    = _run("df -h / | awk 'NR==2{print $3\"/\"$2,\"(\"$5\")'")
    la = _read("/proc/loadavg").split()
    res["load"] = " ".join(la[:3]) if la else "?"

    if shutil.which("sensors"):
        res["temps"] = _run(
            "sensors 2>/dev/null | grep -E '(Core [0-9]|Tdie|edge|temp1):' "
            "| awk '{print $1,$2}' | head -6")
    else:
        zones = []
        if os.path.isdir("/sys/class/thermal"):
            for z in sorted(os.listdir("/sys/class/thermal")):
                if z.startswith("thermal_zone"):
                    try:
                        t  = int(_read(f"/sys/class/thermal/{z}/temp")) // 1000
                        ty = _read(f"/sys/class/thermal/{z}/type")
                        zones.append(f"{ty}:{t}C")
                    except Exception:
                        pass
        res["temps"] = "  ".join(zones[:6])

    if shutil.which("nvidia-smi"):
        res["gpu"] = _run(
            "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,"
            "temperature.gpu --format=csv,noheader,nounits")

    bat_base = "/sys/class/power_supply"
    if os.path.isdir(bat_base):
        for name in os.listdir(bat_base):
            if name.startswith(("BAT","battery")):
                try:
                    cap    = _read(f"{bat_base}/{name}/capacity").strip()
                    status = _read(f"{bat_base}/{name}/status").strip()
                    res["battery"] = f"{cap}% ({status})"
                except Exception:
                    pass
                break
    return res


def read_live_hyprland():
    return {
        "clients":       _json("hyprctl -j clients")       or [],
        "workspaces":    _json("hyprctl -j workspaces")    or [],
        "monitors":      _json("hyprctl -j monitors")      or [],
        "active_window": _json("hyprctl -j activewindow")  or {},
        "active_ws":     _json("hyprctl -j activeworkspace") or {},
    }


def read_live_audio():
    audio = {
        "sink_vol":   _run("wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null"),
        "source_vol": _run("wpctl get-volume @DEFAULT_AUDIO_SOURCE@ 2>/dev/null"),
        "players":    _run("playerctl -l 2>/dev/null"),
    }
    if audio["players"]:
        audio["now_playing"] = _run(
            "playerctl metadata --format "
            "'{{playerName}}: {{title}} -- {{artist}} [{{status}}]' 2>/dev/null")
    return audio


def read_live_network():
    return {
        "wifi_ssid":  _run("nmcli -t -f active,ssid dev wifi 2>/dev/null "
                           "| grep '^yes:' | cut -d: -f2 || iwgetid -r 2>/dev/null"),
        "ip_local":   _run("ip -4 addr show | grep 'inet ' | grep -v '127.0.0.1' "
                           "| awk '{print $2}' | head -3"),
        "interface":  _run("ip route get 1.1.1.1 2>/dev/null | grep -oP 'dev \\K\\S+'"),
        "connections":_run("ss -t state established 2>/dev/null | tail -n +2 | wc -l"),
    }


def read_live_processes():
    return {
        "top_cpu": _run("ps -eo pid,comm,%cpu --no-headers --sort=-%cpu | head -10"),
        "top_mem": _run("ps -eo pid,comm,%mem,rss --no-headers --sort=-%mem | head -10 "
                        "| awk '{print $1,$2,$3\"%\",int($4/1024)\"MB\"}'"),
        "count":   _run("ps -e --no-headers | wc -l"),
    }


def read_user_env():
    env = {
        "home":     HOME,
        "user":     _run("whoami"),
        "hostname": _run("hostname"),
        "shell":    os.environ.get("SHELL",""),
        "editor":   os.environ.get("EDITOR","") or "not set",
    }
    uc = os.path.join(HYPR_DIR, "UserConfigs", "01-UserDefaults.conf")
    if os.path.isfile(uc):
        content = _read(uc)
        for var in ("TERM","EDITOR","BROWSER","FILEMANAGER"):
            m = re.search(rf'\$?{var}\s*=\s*(\S+)', content)
            if m:
                env[f"default_{var.lower()}"] = m.group(1)
    return env


def read_installed_apps():
    buckets = {
        "browsers":     ["firefox","chromium","google-chrome-stable","brave","epiphany"],
        "terminals":    ["kitty","alacritty","foot","wezterm","xterm","konsole"],
        "editors":      ["code","nvim","vim","nano","gedit","kate","mousepad"],
        "media":        ["mpv","vlc","spotify","obs","gimp","inkscape","kdenlive"],
        "communication":["discord","telegram-desktop","slack","signal-desktop","thunderbird"],
        "development":  ["git","docker","podman","python","node","cargo","go"],
        "system":       ["htop","btop","gparted","timeshift","baobab"],
    }
    apps = {cat: [n for n in names if shutil.which(n)]
            for cat, names in buckets.items()}
    if shutil.which("flatpak"):
        fp = _run("flatpak list --app --columns=name 2>/dev/null")
        if fp:
            apps["flatpak"] = [l.strip() for l in fp.splitlines() if l.strip()]
    for d in ["~/Applications","~/.local/bin","~/Downloads"]:
        d = os.path.expanduser(d)
        if os.path.isdir(d):
            apps.setdefault("appimages",[]).extend(
                f for f in os.listdir(d) if f.lower().endswith(".appimage"))
    return apps


def read_home_tree():
    tree = {}
    try:
        for entry in sorted(os.listdir(HOME)):
            full = os.path.join(HOME, entry)
            if os.path.isdir(full) and not entry.startswith("."):
                try:   tree[entry] = f"{len(os.listdir(full))} items"
                except: tree[entry] = "?"
    except Exception:
        pass
    return tree


def read_recent_files(n=10):
    files = []
    for d in ["~/Downloads","~/Documents","~/Desktop",
               "~/Pictures","~/Videos","~/Music"]:
        d = os.path.expanduser(d)
        if not os.path.isdir(d): continue
        try:
            for f in os.listdir(d):
                full = os.path.join(d, f)
                if os.path.isfile(full):
                    files.append((os.path.getmtime(full), full))
        except Exception:
            continue
    return [f for _,f in sorted(files, reverse=True)[:n]]


def read_hypr_config_summary():
    result = {}
    conf_map = {
        "decorations": "UserConfigs/UserDecorations.conf",
        "animations":  "UserConfigs/UserAnimations.conf",
        "keybinds":    "UserConfigs/UserKeybinds.conf",
        "env":         "UserConfigs/ENVariables.conf",
        "settings":    "UserConfigs/01-UserDefaults.conf",
    }
    for name, rel in conf_map.items():
        full = os.path.join(HYPR_DIR, rel)
        if not os.path.isfile(full): continue
        try:
            with open(full) as f:
                lines = [l.rstrip() for l in f
                         if l.strip() and not l.strip().startswith("#")]
            result[name] = lines[:60]
        except Exception:
            result[name] = []

    kb_file = os.path.join(HYPR_DIR, "UserConfigs", "UserKeybinds.conf")
    if os.path.isfile(kb_file):
        keybinds = []
        with open(kb_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                m = re.match(r'bind[dem]?\s*=\s*(.+)', line, re.IGNORECASE)
                if m:
                    parts = [p.strip() for p in m.group(1).split(",")]
                    if len(parts) >= 3:
                        keybinds.append({
                            "combo":  f"{parts[0]}+{parts[1]}",
                            "action": ",".join(parts[2:]).strip(),
                        })
        result["keybinds_parsed"] = keybinds

    conf_files = []
    for root, dirs, files in os.walk(HYPR_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if fn.endswith(".conf"):
                conf_files.append(
                    os.path.relpath(os.path.join(root, fn), HYPR_DIR))
    result["conf_files"] = sorted(conf_files)
    return result


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------

class UserPrefs:
    _lock = threading.Lock()

    @classmethod
    def _defaults(cls):
        return {
            "name": "",
            "preferred_browser": "",
            "preferred_editor": "",
            "preferred_terminal": "",
            "preferred_file_manager": "",
            "wallpaper_folder": os.path.join(HOME,"Pictures","wallpapers"),
            "workspace_labels": {},
            "command_history": [],
            "custom_app_aliases": {},
            "notes": [],
        }

    @classmethod
    def load(cls):
        if os.path.isfile(PREFS_FILE):
            try:
                with open(PREFS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return cls._defaults()

    @classmethod
    def save(cls, prefs):
        with cls._lock:
            os.makedirs(os.path.dirname(PREFS_FILE), exist_ok=True)
            with open(PREFS_FILE,"w") as f:
                json.dump(prefs, f, indent=2)

    @classmethod
    def update(cls, key, value):
        prefs = cls.load()
        prefs[key] = value
        cls.save(prefs)

    @classmethod
    def record_command(cls, cmd):
        try:
            prefs = cls.load()
            history = prefs.get("command_history",[])
            history.insert(0,{"cmd":cmd,"ts":datetime.datetime.now().isoformat()})
            prefs["command_history"] = history[:100]
            cls.save(prefs)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Full snapshot
# ---------------------------------------------------------------------------

def deep_read_system(fast=False):
    snap = {"timestamp": datetime.datetime.now().isoformat()}
    snap["user_env"]   = read_user_env()
    snap["resources"]  = read_live_resources()
    snap["hypr_live"]  = read_live_hyprland()
    snap["audio"]      = read_live_audio()
    snap["network"]    = read_live_network()
    if not fast:
        snap["hardware"]       = read_hardware()
        snap["installed_apps"] = read_installed_apps()
        snap["home_tree"]      = read_home_tree()
        snap["recent_files"]   = read_recent_files()
        snap["hypr_config"]    = read_hypr_config_summary()
        snap["processes"]      = read_live_processes()
    return snap


def save_machine_state(snapshot=None):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    if snapshot is None:
        snapshot = deep_read_system()
    with open(STATE_FILE,"w") as f:
        json.dump(snapshot, f, indent=2)
    return snapshot


def load_machine_state():
    if not os.path.isfile(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LLM context builder
# ---------------------------------------------------------------------------

def get_system_context(snapshot=None, full=False):
    """Build the compact context string injected before every LLM call."""
    if snapshot is None:
        snapshot = deep_read_system(fast=True)
        stored = load_machine_state()
        if stored:
            for k in ("hardware","installed_apps","home_tree","recent_files","hypr_config"):
                if k in stored and k not in snapshot:
                    snapshot[k] = stored[k]

    prefs  = UserPrefs.load()
    env    = snapshot.get("user_env",{})
    hw     = snapshot.get("hardware",{})
    res    = snapshot.get("resources",{})
    hypr   = snapshot.get("hypr_live",{})
    audio  = snapshot.get("audio",{})
    net    = snapshot.get("network",{})
    inst   = snapshot.get("installed_apps",{})
    recent = snapshot.get("recent_files",[])
    hcfg   = snapshot.get("hypr_config",{})
    ts     = snapshot.get("timestamp","")[:16]

    name_str = f" ({prefs['name']})" if prefs.get("name") else ""
    host     = hw.get("hostname", env.get("hostname","?"))
    user     = hw.get("user",     env.get("user","?"))
    distro   = hw.get("distro","Arch Linux")
    kernel   = hw.get("kernel","?")
    hw_cpu   = hw.get("cpu_model","?")
    hw_ram   = f"{hw.get('ram_total_gb','?')} GB"
    hw_gpu   = (hw.get("gpus") or ["?"])[0][:55]

    cpu_pct = res.get("cpu_pct","?")
    ram_str = f"{res.get('ram_used_gb','?')}/{res.get('ram_total_gb','?')}GB ({res.get('ram_pct','?')}%)"
    disk    = res.get("disk_root","?")
    load    = res.get("load","?")
    temps   = res.get("temps","").replace("\n","  ") if res.get("temps") else ""
    bat     = res.get("battery","")
    gpu_res = res.get("gpu","")

    clients  = hypr.get("clients",[])
    aw       = hypr.get("active_window",{})
    aw_ws    = aw.get("workspace",{})
    aw_ws_id = aw_ws.get("id","?") if isinstance(aw_ws,dict) else "?"
    active_str = f"{aw.get('class','?')} -- {aw.get('title','?')[:45]} (WS{aw_ws_id})"

    ws_wins = {}
    for c in clients:
        ws = c.get("workspace",{})
        ws_id = ws.get("id",0) if isinstance(ws,dict) else int(ws or 0)
        ws_wins.setdefault(ws_id,[]).append(
            f"{c.get('class','?')}:{c.get('title','')[:20]}")
    ws_lines = []
    for ws_id in sorted(ws_wins):
        label = prefs.get("workspace_labels",{}).get(str(ws_id),"")
        label_s = f"({label})" if label else ""
        ws_lines.append(f"  WS{ws_id}{label_s}: {', '.join(ws_wins[ws_id])}")
    wins_str = "\n".join(ws_lines) if ws_lines else "  (no windows)"

    mons = hypr.get("monitors",[])
    mon_str = " | ".join(
        f"{m.get('name','?')} {m.get('width',0)}x{m.get('height',0)}"
        f"@{m.get('refreshRate',0):.0f}" for m in mons) if mons else "?"

    vol_str   = audio.get("sink_vol","?").replace("Volume:","").strip()
    playing   = audio.get("now_playing","")
    audio_str = f"vol={vol_str}" + (f"  Playing: {playing[:55]}" if playing else "")

    wifi  = net.get("wifi_ssid","?") or "not connected"
    ip    = net.get("ip_local","?")
    conns = net.get("connections","?")

    def _inst(cat):
        items = inst.get(cat,[])
        return ", ".join(items[:5]) if items else "none"

    inst_str = (f"browsers:{_inst('browsers')}  editors:{_inst('editors')}  "
                f"terminals:{_inst('terminals')}  media:{_inst('media')}")

    wp_found = []
    for d in [prefs.get("wallpaper_folder",""),
               os.path.join(HOME,"Pictures","wallpapers"),
               os.path.join(HOME,"Pictures","Wallpapers"),
               os.path.join(HOME,"Pictures"),
               os.path.join(HYPR_DIR,"wallpapers")]:
        if d and os.path.isdir(d):
            try:
                count = sum(1 for f in os.listdir(d)
                            if f.lower().endswith((".png",".jpg",".jpeg",".webp")))
                if count:
                    wp_found.append(f"{d} ({count} imgs)")
            except Exception:
                pass
    wp_str = " | ".join(wp_found) if wp_found else "none found"

    pref_parts = []
    for k in ("preferred_browser","preferred_editor","preferred_terminal"):
        if prefs.get(k):
            pref_parts.append(f"{k.split('_')[-1]}={prefs[k]}")
    pref_str = "  ".join(pref_parts) if pref_parts else "not configured"

    recent_str = ", ".join(os.path.basename(f) for f in recent[:5]) if recent else "none"
    kb_count   = len(hcfg.get("keybinds_parsed",[]))
    conf_files = ", ".join(hcfg.get("conf_files",[])[:8])

    ctx = (
        f"[JARVIS MACHINE CONTEXT {ts}]\n"
        f"USER: {user}@{host}{name_str} | {distro} kernel={kernel}\n"
        f"HW:   CPU={hw_cpu} ({hw.get('cpu_cores','?')} cores) "
        f"RAM={hw_ram} GPU={hw_gpu}\n"
        f"\nRESOURCES: CPU={cpu_pct}%  RAM={ram_str}  Disk={disk}  Load={load}"
        + (f"  Temps={temps}" if temps else "")
        + (f"  Battery={bat}" if bat else "")
        + (f"  GPU={gpu_res}" if gpu_res else "")
        + f"\n\nDESKTOP:\n  Monitor: {mon_str}\n  Active:  {active_str}"
        + f"\n  Windows:\n{wins_str}"
        + f"\n\nAUDIO:   {audio_str}"
        + f"\nNET:     wifi={wifi}  ip={ip}  connections={conns}"
        + f"\n\nINSTALLED: {inst_str}"
        + f"\nWALLPAPERS: {wp_str}"
        + f"\nPREFS:   {pref_str}"
        + f"\nRECENT:  {recent_str}"
        + f"\nCONFIG:  {kb_count} keybinds  {conf_files[:100]}"
    )
    return ctx


# ---------------------------------------------------------------------------
# Backward compatibility shims (imported by agent.py and jarvis.py)
# ---------------------------------------------------------------------------

def read_hardware_legacy():         return read_hardware()
def read_system_resources():        return read_live_resources()
def read_audio():                   return read_live_audio()
def read_network():                 return read_live_network()
def read_user_environment():        return read_user_env()
def read_installed_important_apps():
    inst = read_installed_apps()
    return {n: True for items in inst.values() for n in items}

def read_running_apps():
    hypr = read_live_hyprland()
    procs = _run("ps -eo comm --no-headers | sort -u")
    return {"windows": hypr.get("clients",[]),
            "all_procs_sample": procs.splitlines()[:40]}

def read_hypr_clients():            return _json("hyprctl -j clients") or []
def read_hypr_workspaces():
    ws = _json("hyprctl -j workspaces") or []
    return [{"id":w.get("id"),"name":w.get("name",""),"windows":w.get("windows",0)} for w in ws]
def read_hypr_active_window():
    w = _json("hyprctl -j activewindow") or {}
    return {"class":w.get("class",""),"title":w.get("title","")[:60],
            "workspace":w.get("workspace",{}).get("id",0) if isinstance(w.get("workspace"),dict) else 0}
def read_hypr_monitors():
    mons = _json("hyprctl -j monitors") or []
    return [{"name":m.get("name",""),
             "resolution":f"{m.get('width',0)}x{m.get('height',0)}@{m.get('refreshRate',0):.0f}",
             "scale":m.get("scale",1.0)} for m in mons]
def read_keybinds_summary():
    return read_hypr_config_summary().get("keybinds_parsed",[])
def read_hypr_config_values():
    cfg = read_hypr_config_summary()
    return {k:v for k,v in cfg.items() if isinstance(v,list) and k != "conf_files"}
def read_hypr_dotfiles_summary():
    return read_hypr_config_summary().get("conf_files",[])
