"""
tools.py — JARVIS tool registry.
Hyprland-only. Thin wrappers over hypr_config.py.
"""
import os, subprocess, shutil, json, re, difflib, functools, urllib.parse
from . import hypr_config
try:
    from .system_state import UserPrefs as _UserPrefs
except Exception:
    _UserPrefs = None

HYPR    = os.path.expanduser("~/.config/hypr")
SCRIPTS = os.path.join(HYPR, "scripts")


def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return str(e)


def _run_rc(cmd, timeout=10):
    """Like _run, but also returns the process's exit code so callers (e.g.
    pkill) can tell success from failure instead of guessing from output text
    that's often empty on both success and failure."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip(), r.returncode
    except Exception as e:
        return str(e), 1


# ── Config reading ──────────────────────────────────────────────────────────

def hypr_read_config(args=None):
    what = (args or {}).get("what", "decorations")
    return hypr_config.show_config(what)


def hypr_live_values(_args=None):
    return hypr_config.get_live_values()


# ── Main setter ─────────────────────────────────────────────────────────────

def hypr_set_value(args, _=None):
    section  = (args or {}).get("section", "")
    key      = (args or {}).get("key", "")
    value    = str((args or {}).get("value", ""))
    file_key = (args or {}).get("file", None)
    if not key:
        return "No key given."
    return hypr_config.set_value(section, key, value, file_key)


# Aliases kept for backward compat
def hypr_set_setting(args, _=None):
    return hypr_set_value(args)

def hypr_set_decoration(args, _=None):
    # map spoken name → section+key
    name  = (args or {}).get("name", "").lower().strip()
    value = str((args or {}).get("value", ""))
    MAP   = {
        "rounding":          ("decoration", "rounding",          "decorations"),
        "active_opacity":    ("decoration", "active_opacity",    "decorations"),
        "active opacity":    ("decoration", "active_opacity",    "decorations"),
        "inactive_opacity":  ("decoration", "inactive_opacity",  "decorations"),
        "inactive opacity":  ("decoration", "inactive_opacity",  "decorations"),
        "dim_inactive":      ("decoration", "dim_inactive",      "decorations"),
        "dim_strength":      ("decoration", "dim_strength",      "decorations"),
        "border_size":       ("general",    "border_size",       "decorations"),
        "border size":       ("general",    "border_size",       "decorations"),
        "gaps_in":           ("general",    "gaps_in",           "decorations"),
        "gaps in":           ("general",    "gaps_in",           "decorations"),
        "gaps_out":          ("general",    "gaps_out",          "decorations"),
        "gaps out":          ("general",    "gaps_out",          "decorations"),
        "layout":            ("general",    "layout",            "system"),
        "blur":              ("blur",       "enabled",           "decorations"),
        "shadow":            ("shadow",     "enabled",           "decorations"),
    }
    if name in MAP:
        section, key, fkey = MAP[name]
        if name in ("blur", "shadow"):
            if name == "blur":
                return hypr_config.set_blur(enabled=(value.lower() in ("true","1","yes","on","enable")))
            else:
                return hypr_config.set_shadow(enabled=(value.lower() in ("true","1","yes","on","enable")))
        return hypr_config.set_value(section, key, value, fkey)
    return f"Unknown name '{name}'. Use hypr_set_value with explicit section+key."


# ── Blur / Shadow ───────────────────────────────────────────────────────────

def hypr_set_blur(args, _=None):
    a = args or {}
    return hypr_config.set_blur(
        enabled  = a.get("enabled"),
        size     = a.get("size"),
        passes   = a.get("passes"),
        xray     = a.get("xray"),
    )


def hypr_set_shadow(args, _=None):
    a = args or {}
    return hypr_config.set_shadow(
        enabled      = a.get("enabled"),
        rang         = a.get("range"),
        render_power = a.get("render_power"),
    )


# ── Keybinds ────────────────────────────────────────────────────────────────

def hypr_add_keybind(args, _=None):
    a = args or {}
    return hypr_config.add_keybind(
        combo       = a.get("combo", ""),
        dispatcher  = a.get("dispatcher", ""),
        disp_args   = a.get("dispatcher_args", ""),
        description = a.get("description", ""),
        bind_type   = a.get("bind_type", "bindd"),
    )

def hypr_apply_add_keybind(args, _=None):
    return hypr_add_keybind(args)

def hypr_remove_keybind(args, _=None):
    return hypr_config.remove_keybind((args or {}).get("combo", ""))

def hypr_unbind(args, _=None):
    return hypr_config.unbind_keybind((args or {}).get("combo", ""))

def hypr_list_keybinds(args=None):
    return hypr_config.list_all_keybinds((args or {}).get("filter",""))

def hypr_find_keybind(args):
    combo = (args or {}).get("combo","")
    return hypr_config.list_all_keybinds(combo)


# ── Window / Workspace rules ────────────────────────────────────────────────

def hypr_add_window_rule(args, _=None):
    a = args or {}
    return hypr_config.add_window_rule(a.get("rule",""), a.get("match",""))

def hypr_remove_window_rule(args, _=None):
    fragment = (args or {}).get("fragment","")
    path = hypr_config.F["rules"]
    bak  = hypr_config._backup(path)
    with open(path) as f: lines = f.readlines()
    count = 0
    for i, ln in enumerate(lines):
        if fragment.lower() in ln.lower() and not ln.strip().startswith("#"):
            lines[i] = "# " + ln
            count += 1
    with open(path,"w") as f: f.writelines(lines)
    r = hypr_config._reload()
    return f"Commented {count} rule(s) matching '{fragment}'\nReload: {r}"

def hypr_add_workspace_rule(args, _=None):
    return hypr_config.add_workspace_rule((args or {}).get("rule",""))


# ── Startup / Env / Defaults ────────────────────────────────────────────────

def hypr_add_startup_app(args, _=None):
    a = args or {}
    return hypr_config.add_startup_app(a.get("cmd",""), a.get("once", True))

def hypr_set_env(args, _=None):
    a = args or {}
    return hypr_config.set_env_var(a.get("key",""), a.get("value",""))

def hypr_set_default_app(args, _=None):
    a = args or {}
    return hypr_config.set_default_app(a.get("var",""), a.get("value",""))


# ── Monitor ─────────────────────────────────────────────────────────────────

def hypr_set_monitor(args, _=None):
    a = args or {}
    return hypr_config.set_monitor(
        name       = a.get("name",""),
        resolution = a.get("resolution","preferred"),
        position   = a.get("position","auto"),
        scale      = a.get("scale",1),
        extra      = a.get("extra",""),
    )


# ── Animations ──────────────────────────────────────────────────────────────

def hypr_switch_animation(args, _=None):
    return hypr_config.switch_animation_preset((args or {}).get("preset",""))

def hypr_list_animations(_args=None):
    return hypr_config.list_animation_presets()


# ── Scripts ─────────────────────────────────────────────────────────────────

def hypr_run_script(args, _=None):
    a = args or {}
    return hypr_config.run_script(a.get("name",""), a.get("args",""))

def hypr_list_scripts(_args=None):
    return hypr_config.list_scripts()


# ── Raw / Reload ─────────────────────────────────────────────────────────────

def hypr_apply_raw(args, _=None):
    a = args or {}
    return hypr_config.apply_raw(a.get("text",""), a.get("file","keybinds"))

def hypr_reload(_args=None):
    return hypr_config._reload()


# ── Live window control ──────────────────────────────────────────────────────

def execute_command(args, _=None):
    """Run any hyprctl / wpctl / brightnessctl / playerctl command."""
    cmd = (args or {}).get("command","").strip()
    if not cmd:
        return "No command."
    SAFE = ["hyprctl","wpctl","brightnessctl","playerctl","notify-send",
            "pkill","killall","swww","grim","loginctl"]
    if any(cmd.startswith(s) for s in SAFE):
        return _run(cmd, timeout=15) or "done"
    return f"⚠ Not in safe list: {cmd}"


def get_open_windows(_args=None):
    raw = _run("hyprctl -j clients")
    try:
        clients = json.loads(raw)
    except Exception:
        return "Could not read windows."
    if not clients:
        return "No open windows."
    lines = []
    for c in clients:
        ws  = c.get("workspace",{}).get("id","?")
        cls = c.get("class","?")
        ttl = c.get("title","")[:50]
        lines.append(f"WS{ws}  {cls}  —  {ttl}")
    return "\n".join(lines)


_CLOSE_WORKSPACE_SUFFIX_RE = re.compile(r"\s+(?:in|on)\s+workspace\s*\d+\s*$", re.IGNORECASE)
_CLOSE_LEADING_DEMONSTRATIVE_RE = re.compile(r"^(?:this|that|the)\s+(?=\S)", re.IGNORECASE)

def _clean_close_target(text):
    """Strip a trailing 'in workspace N' qualifier and a leading demonstrative
    ('this'/'that'/'the') from a close-target phrase, so e.g. 'close this
    firefox in workspace8' resolves to just 'firefox' instead of being passed
    through as one literal (nonexistent) window class."""
    t = _CLOSE_WORKSPACE_SUFFIX_RE.sub("", text.strip())
    t = _CLOSE_LEADING_DEMONSTRATIVE_RE.sub("", t)
    return t.strip()


def close_window(args, _=None):
    raw = (args or {}).get("class", "").strip()
    if not raw:
        return "No window specified."

    if raw.lower() in ("it", "that", "this") and _LAST_OPENED.get("app"):
        raw = _LAST_OPENED["app"]

    cls = _clean_close_target(raw)
    if not cls:
        return "No window specified."

    real_cls, found = _find_window_class(cls)
    if not found:
        return f"I don't see an open window matching '{cls}'."

    _run(f"hyprctl dispatch closewindow class:{real_cls}")
    return f"Closed {real_cls}"


# ══════════════════════════════════════════════════════════ REGISTRY + SPECS ═

WRITE_TOOLS = {
    "hypr_set_value","hypr_set_setting","hypr_set_decoration",
    "hypr_set_blur","hypr_set_shadow",
    "hypr_add_keybind","hypr_apply_add_keybind","hypr_remove_keybind","hypr_unbind",
    "hypr_add_window_rule","hypr_remove_window_rule","hypr_add_workspace_rule",
    "hypr_add_startup_app","hypr_set_env","hypr_set_default_app",
    "hypr_set_monitor","hypr_switch_animation","hypr_apply_raw",
    "delete_file", "power_shutdown", "power_reboot", "power_hibernate",
    "pkg_install", "pkg_remove", "pkg_update", "service_stop", "service_disable",
}

REGISTRY = {
    "hypr_read_config":      hypr_read_config,
    "hypr_live_values":      hypr_live_values,
    "hypr_set_value":        hypr_set_value,
    "hypr_set_setting":      hypr_set_setting,
    "hypr_set_decoration":   hypr_set_decoration,
    "hypr_set_blur":         hypr_set_blur,
    "hypr_set_shadow":       hypr_set_shadow,
    "hypr_add_keybind":      hypr_add_keybind,
    "hypr_apply_add_keybind":hypr_apply_add_keybind,
    "hypr_remove_keybind":   hypr_remove_keybind,
    "hypr_unbind":           hypr_unbind,
    "hypr_list_keybinds":    hypr_list_keybinds,
    "hypr_find_keybind":     hypr_find_keybind,
    "hypr_add_window_rule":  hypr_add_window_rule,
    "hypr_remove_window_rule":hypr_remove_window_rule,
    "hypr_add_workspace_rule":hypr_add_workspace_rule,
    "hypr_add_startup_app":  hypr_add_startup_app,
    "hypr_set_env":          hypr_set_env,
    "hypr_set_default_app":  hypr_set_default_app,
    "hypr_set_monitor":      hypr_set_monitor,
    "hypr_switch_animation": hypr_switch_animation,
    "hypr_list_animations":  hypr_list_animations,
    "hypr_run_script":       hypr_run_script,
    "hypr_list_scripts":     hypr_list_scripts,
    "hypr_apply_raw":        hypr_apply_raw,
    "hypr_reload":           hypr_reload,
    "execute_command":       execute_command,
    "get_open_windows":      get_open_windows,
    "close_window":          close_window,
}


def spec(name, desc, props=None, required=None):
    s = {"name": name, "description": desc,
         "input_schema": {"type": "object", "properties": props or {}, "required": required or []}}
    return s


def get_tool_specs():
    return [
        spec("hypr_read_config",
             "Read a config file. ALWAYS call before editing. "
             "what: 'decorations'|'animations'|'keybinds'|'settings'|'system'|"
             "'env'|'defaults'|'rules'|'startup'|'monitors'|'workspaces'|'main'",
             {"what": {"type":"string","description":"which config to read"}}),
        spec("hypr_live_values",
             "Get live Hyprland values via hyprctl getoption. Shows actual running values."),
        spec("hypr_set_value",
             "MAIN CONFIG SETTER. Set any section.key = value in any config file. "
             "Backs up, edits in-block, applies hyprctl keyword instantly, reloads. "
             "Examples: section='decoration' key='rounding' value='16' → UserDecorations.conf; "
             "section='general' key='gaps_in' value='4' → UserDecorations.conf; "
             "section='input' key='sensitivity' value='0.5' → SystemSettings.conf; "
             "section='general' key='layout' value='master' → SystemSettings.conf; "
             "file='settings' → UserSettings.conf; file='env' → ENVariables.conf",
             {"section":{"type":"string","description":"block name e.g. decoration, general, input, misc"},
              "key":    {"type":"string","description":"setting name"},
              "value":  {"type":"string","description":"new value"},
              "file":   {"type":"string","description":"optional file hint: decorations|system|settings|env|animations"}},
             ["key","value"]),
        spec("hypr_set_blur",
             "Set blur sub-block values in decoration.blur{} in UserDecorations.conf. "
             "Pass only the params you want to change.",
             {"enabled":{"type":"boolean"},"size":{"type":"integer"},
              "passes":{"type":"integer"},"xray":{"type":"boolean"}}),
        spec("hypr_set_shadow",
             "Set shadow sub-block values in decoration.shadow{} in UserDecorations.conf.",
             {"enabled":{"type":"boolean"},"range":{"type":"integer"},"render_power":{"type":"integer"}}),
        spec("hypr_add_keybind",
             "Add keybind to UserConfigs/UserKeybinds.conf as bindd (shows in SUPER+H help). "
             "Check conflicts automatically. Reloads after writing. "
             "combo examples: 'SUPER+T', 'SUPER SHIFT+E', 'CTRL ALT+T'. "
             "dispatcher examples: exec, workspace, killactive, togglefloating, fullscreen. "
             "To override a DEFAULT bind: call hypr_unbind first.",
             {"combo":         {"type":"string","description":"key combo e.g. SUPER+T"},
              "dispatcher":    {"type":"string","description":"hyprland dispatcher"},
              "dispatcher_args":{"type":"string","description":"args to dispatcher"},
              "description":   {"type":"string","description":"shown in SUPER+H help menu"},
              "bind_type":     {"type":"string","description":"bind|bindd|binde|bindm — default bindd"}},
             ["combo","dispatcher"]),
        spec("hypr_remove_keybind",
             "Comment out a keybind from UserKeybinds.conf. "
             "If it's in configs/Keybinds.conf (defaults), tells user to use hypr_unbind instead.",
             {"combo":{"type":"string","description":"e.g. SUPER+T"}},["combo"]),
        spec("hypr_unbind",
             "Add 'unbind = MODS, KEY' to UserKeybinds.conf to disable a default keybind.",
             {"combo":{"type":"string","description":"e.g. SUPER+B"}},["combo"]),
        spec("hypr_list_keybinds",
             "List all keybinds from configs/Keybinds.conf and UserConfigs/UserKeybinds.conf.",
             {"filter":{"type":"string","description":"optional filter text"}}),
        spec("hypr_add_window_rule",
             "Add windowrulev2 to UserConfigs/WindowRules.conf. "
             "rule examples: 'float', 'tile', 'opacity 0.85 0.85', 'workspace 2 silent', "
             "'size 900 600', 'center', 'pin', 'nofocus', 'noblur'. "
             "match examples: 'class:^(kitty)$', 'title:^(Bluetooth)$', "
             "'class:^(firefox)$,title:^(Picture-in-Picture)$'",
             {"rule": {"type":"string"},"match":{"type":"string"}},["rule","match"]),
        spec("hypr_remove_window_rule",
             "Comment out window rules containing a fragment.",
             {"fragment":{"type":"string"}},["fragment"]),
        spec("hypr_add_workspace_rule",
             "Add workspace rule to workspaces.conf. "
             "e.g. '2, monitor:DP-1' or '5, on-created-empty:[float] firefox'",
             {"rule":{"type":"string"}},["rule"]),
        spec("hypr_add_startup_app",
             "Add exec-once or exec line to UserConfigs/Startup_Apps.conf.",
             {"cmd":{"type":"string","description":"command to run at startup"},
              "once":{"type":"boolean","description":"true=exec-once (default), false=exec"}},["cmd"]),
        spec("hypr_set_env",
             "Set env = KEY,VALUE in UserConfigs/ENVariables.conf.",
             {"key":{"type":"string"},"value":{"type":"string"}},["key","value"]),
        spec("hypr_set_default_app",
             "Set $term, $files, or $edit in 01-UserDefaults.conf. "
             "var='term' value='kitty' changes the default terminal.",
             {"var":{"type":"string","description":"term|files|edit"},
              "value":{"type":"string"}},["var","value"]),
        spec("hypr_set_monitor",
             "Configure monitor in monitors.conf. name from 'hyprctl monitors'.",
             {"name":{"type":"string","description":"monitor name e.g. eDP-1, DP-1, HDMI-A-1"},
              "resolution":{"type":"string","description":"e.g. 1920x1080@144 or preferred"},
              "position":{"type":"string","description":"e.g. 0x0 or auto"},
              "scale":{"type":"number","description":"e.g. 1 or 1.5"},
              "extra":{"type":"string","description":"e.g. mirror,eDP-1"}},["name","resolution"]),
        spec("hypr_switch_animation",
             "Switch animation preset by copying animations/PRESET.conf → UserAnimations.conf. "
             "Call hypr_list_animations() first to see preset names.",
             {"preset":{"type":"string","description":"preset name or filename"}},["preset"]),
        spec("hypr_list_animations","List all animation presets in animations/ directory."),
        spec("hypr_run_script",
             "Run a script from scripts/ or UserScripts/. "
             "Built-in: ChangeBlur, ChangeLayout, GameMode, ThemeChanger, Refresh, "
             "WaybarStyles, WaybarLayout, Volume, Brightness, ScreenShot, LockScreen, Wlogout, "
             "KeyHints, KeyBinds, Animations, RofiSearch, RofiEmoji, ClipManager, Hypridle, Hyprsunset",
             {"name":{"type":"string","description":"script name (partial match ok)"},
              "args":{"type":"string","description":"optional args"}},["name"]),
        spec("hypr_list_scripts","List all scripts in scripts/ and UserScripts/."),
        spec("hypr_apply_raw",
             "Append raw config lines directly to a file. "
             "file: 'keybinds'|'decorations'|'settings'|'rules'|'startup'|'env'|'monitors'",
             {"text":{"type":"string","description":"raw hyprland config lines to append"},
              "file":{"type":"string","description":"target file key"}},["text"]),
        spec("hypr_reload","Run hyprctl reload."),
        spec("execute_command",
             "Run a live hyprctl dispatch, wpctl, brightnessctl, or playerctl command. "
             "Use for: switching workspaces, closing windows, volume, brightness. "
             "Examples: 'hyprctl dispatch workspace 3', 'hyprctl dispatch killactive', "
             "'wpctl set-volume @DEFAULT_AUDIO_SINK@ 10%+', 'brightnessctl set 10%+'",
             {"command":{"type":"string"}},["command"]),
        spec("get_open_windows","List all open windows with workspace, class, and title."),
        spec("close_window",
             "Close a window by its WM class name (Wayland-native).",
             {"class":{"type":"string"}},["class"]),
        spec("workspace_go",
             "Switch the active workspace.",
             {"number":{"type":"integer"}},["number"]),
        spec("workspace_move_window",
             "Move a named app's window (fuzzy-matched against open windows) to a "
             "workspace, e.g. 'move firefox to workspace 10'. Omit class to move the "
             "current/active window instead.",
             {"class":{"type":"string","description":"app name, optional"},
              "number":{"type":"integer"}},["number"]),
        spec("workspace_move_all",
             "Move EVERY currently open window to a workspace, e.g. 'move all windows to workspace 8'.",
             {"number":{"type":"integer"}},["number"]),
        spec("workspace_move_matching",
             "Move all windows matching a query (app name or group keyword like "
             "'browsers'/'terminals') to a workspace, e.g. 'move all browsers to workspace 8'.",
             {"query":{"type":"string"},"number":{"type":"integer"}},["query","number"]),
        spec("open_app",
             "Launch an application, or open a website/URL in the default browser. "
             "Use this for apps and websites (firefox, youtube, github, discord...), "
             "NOT for opening a file on disk — use open_file for that instead.",
             {"app":{"type":"string","description":"app name, website shortcut (youtube, github...), or full URL"},
              "url":{"type":"string","description":"explicit URL, alternative to app"},
              "workspace":{"type":"integer","description":"optional workspace to switch to first"}},
             ["app"]),
        spec("open_file",
             "Open a file that exists on disk with its default application (xdg-open). "
             "Give just the filename ('report.pdf', 'notes.txt') if you don't know the "
             "full path — this searches Home/Downloads/Documents/Desktop/Pictures/Videos/Music "
             "for a match. Use this instead of open_app whenever the target is a file, not an app or website.",
             {"path":{"type":"string","description":"filename or full path to open"}},
             ["path"]),
        spec("open_folder",
             "Open a folder/directory in the file manager. Give a path or a common "
             "shortcut name like 'downloads' or 'documents'.",
             {"path":{"type":"string"}},["path"]),
        spec("open_in_app",
             "Open a specific file/folder with a specific named app, overriding the "
             "default handler (e.g. 'open resume.pdf in vscode', 'open it in firefox'). "
             "'it'/'that'/'this' as target refers to the last file this agent opened.",
             {"target":{"type":"string","description":"filename, path, or 'it'/'that'/'this'"},
              "app":{"type":"string","description":"app to open it with, e.g. 'vscode', 'firefox'"}},
             ["target","app"]),
        spec("close_app",
             "Close/quit an application by name.",
             {"app":{"type":"string"}},["app"]),
        spec("close_file",
             "Close whatever window currently has a given file open (best-effort, by window title).",
             {"path":{"type":"string"}},["path"]),
        spec("delete_file",
             "Delete a file (moves it to trash when possible). Requires user confirmation.",
             {"path":{"type":"string"}},["path"]),
        spec("edit_file",
             "Open a file in a code/text editor (prefers VS Code) for editing.",
             {"path":{"type":"string"}},["path"]),
        spec("select_pending",
             "Pick one of the candidates from a previous ambiguous file/folder search "
             "(when the agent asked 'which one?' and listed numbered options).",
             {"index":{"type":"integer","description":"1-based number of the option to pick"}},
             ["index"]),
        spec("make_executable",
             "chmod +x a file so it can be run (e.g. an AppImage or script).",
             {"path":{"type":"string"}},["path"]),
        spec("open_file_by_type",
             "Open a file when the user only gave a file TYPE, not a name (e.g. "
             "'open a png file', 'open the pdf'). Searches for files of that "
             "extension instead of guessing a filename.",
             {"ext":{"type":"string","description":"extension or type word, e.g. 'png', 'image'"},
              "folder":{"type":"string","description":"optional folder name to search in (any name, not just standard shortcuts)"}},
             ["ext"]),
        spec("smart_open_vague",
             "Handles messy natural-language open requests that mix a file type "
             "with a custom folder name in any order, e.g. 'open any one of the "
             "image from sri folder'. Pass the whole phrase as-is.",
             {"text":{"type":"string"}},["text"]),
        spec("copy_file", "Copy a file to a destination folder/path.",
             {"path":{"type":"string"},"destination":{"type":"string"}},["path","destination"]),
        spec("move_file", "Move a file to a destination folder/path.",
             {"path":{"type":"string"},"destination":{"type":"string"}},["path","destination"]),
        spec("rename_file", "Rename a file (keeps it in the same folder).",
             {"path":{"type":"string"},"new_name":{"type":"string"}},["path","new_name"]),
        spec("create_folder",
             "Create a new directory. 'name' is the folder name, 'location' is where to create it "
             "(e.g. 'downloads', '~/projects', or any dir shortcut). For 'create a folder named mine "
             "in my downloads' -> name='mine', location='downloads'.",
             {"name":{"type":"string"},"location":{"type":"string","description":"parent dir, shortcut or path"}},
             ["name"]),
        spec("create_file",
             "Create a new empty file (or with content). 'name' is the filename, 'location' is where.",
             {"name":{"type":"string"},"location":{"type":"string"},"content":{"type":"string"}},["name"]),
        spec("list_folder", "List contents of a directory.",
             {"path":{"type":"string"}}, []),
        spec("disk_usage", "Show disk usage for the filesystem or a specific path.",
             {"path":{"type":"string"}}, []),
        spec("find_files", "Search for files matching a name pattern.",
             {"pattern":{"type":"string"},"location":{"type":"string"}},["pattern"]),
        spec("show_file_info", "Show file metadata: size, type, permissions, modified time.",
             {"path":{"type":"string"}},["path"]),
        spec("battery_status", "Get battery charge percentage and charging state.", {}, []),
        spec("power_shutdown", "Shut down the system. Always confirm with the user first.", {}, []),
        spec("power_reboot", "Reboot the system. Always confirm with the user first.", {}, []),
        spec("power_suspend", "Suspend (sleep) the system.", {}, []),
        spec("power_hibernate", "Hibernate the system. Always confirm with the user first.", {}, []),
        spec("bluetooth_toggle", "Turn Bluetooth on or off.",
             {"on":{"type":"boolean","description":"true=on, false=off, omit to toggle"}}, []),
        spec("bluetooth_list", "List paired Bluetooth devices.", {}, []),
        spec("bluetooth_connect", "Connect to a paired Bluetooth device by name.",
             {"device":{"type":"string"}},["device"]),
        spec("bluetooth_disconnect", "Disconnect a Bluetooth device (or all if none named).",
             {"device":{"type":"string"}}, []),
        spec("wifi_toggle", "Turn WiFi on or off.",
             {"on":{"type":"boolean","description":"true=on, false=off, omit to toggle"}}, []),
        spec("wifi_list", "List available WiFi networks with signal strength.", {}, []),
        spec("wifi_connect", "Connect to a WiFi network by SSID, optionally with a password.",
             {"ssid":{"type":"string"},"password":{"type":"string"}},["ssid"]),
        spec("clipboard_set", "Set the clipboard contents to the given text.",
             {"text":{"type":"string"}},["text"]),
        spec("clipboard_get", "Read the current clipboard contents.", {}, []),
        spec("clipboard_history", "Show recent clipboard history (requires cliphist).", {}, []),
        spec("notify_send", "Send a desktop notification.",
             {"title":{"type":"string"},"body":{"type":"string"}},["body"]),
        spec("notify_clear", "Dismiss/clear all active notifications.", {}, []),
        spec("screen_record_start", "Start recording the screen to a video file.",
             {"region":{"type":"boolean","description":"true to select a region instead of full screen"}}, []),
        spec("screen_record_stop", "Stop the current screen recording.", {}, []),
        # preferences
        spec("prefs_set_name", "Remember the user's name.",
             {"name":{"type":"string"}}, ["name"]),
        spec("prefs_set", "Store a user preference key/value.",
             {"key":{"type":"string"},"value":{"type":"string"}}, ["key","value"]),
        spec("prefs_get", "Read stored preferences.", {"key":{"type":"string"}}, []),
        spec("prefs_note", "Save a note the user wants JARVIS to remember.",
             {"note":{"type":"string"}}, ["note"]),
        spec("prefs_list_notes", "List all notes the user has saved.", {}, []),
        # system status
        spec("system_status",
             "Full real-time system snapshot: CPU/RAM/temps/GPU/battery/network/"
             "windows/audio/installed apps. Use when user asks about system state.",
             {}, []),
        spec("system_info_brief", "Quick one-line system stats.", {}, []),
        # packages
        spec("pkg_install", "Install a package (yay/pacman). Asks confirmation.",
             {"package":{"type":"string"}}, ["package"]),
        spec("pkg_remove", "Remove a package (pacman -Rns). Asks confirmation.",
             {"package":{"type":"string"}}, ["package"]),
        spec("pkg_search", "Search pacman + AUR for a package.",
             {"query":{"type":"string"}}, ["query"]),
        spec("pkg_update", "Update all packages. Asks confirmation.", {}, []),
        spec("pkg_list_installed", "List installed packages.",
             {"query":{"type":"string"}}, []),
        # services
        spec("service_status", "Show systemd service status.",
             {"service":{"type":"string"}}, ["service"]),
        spec("service_start",   "Start a systemd service.",
             {"service":{"type":"string"}}, ["service"]),
        spec("service_stop",    "Stop a systemd service. Asks confirmation.",
             {"service":{"type":"string"}}, ["service"]),
        spec("service_restart", "Restart a systemd service.",
             {"service":{"type":"string"}}, ["service"]),
        spec("service_enable",  "Enable a service on boot.",
             {"service":{"type":"string"}}, ["service"]),
        spec("service_disable", "Disable a service from boot. Asks confirmation.",
             {"service":{"type":"string"}}, ["service"]),
        spec("service_list",
             "List systemd services. filter: 'failed' (default), 'running', or name.",
             {"filter":{"type":"string"}}, []),
    ]


# ══════════════════════════════════════ call_tool — the missing function ════

def call_tool(name, args, confirm_fn=None):
    """
    Dispatch a tool call by name. Called by jarvis.py _tool_loop.
    This was the missing function causing 'has no attribute call_tool'.
    """
    fn = REGISTRY.get(name)
    if fn is None:
        return f"Unknown tool: '{name}'. Available: {', '.join(sorted(REGISTRY.keys()))}"
    try:
        # tools that need confirm_fn get it as second arg
        if name in WRITE_TOOLS:
            try:
                return fn(args, confirm_fn) or "done"
            except TypeError:
                return fn(args) or "done"
        else:
            try:
                return fn(args) or "done"
            except TypeError:
                return fn() or "done"
    except Exception as e:
        import traceback
        return f"Tool error ({name}): {e}\n{traceback.format_exc()[-400:]}"


# ════════════════════════════════════════ Full Desktop Management Tools ════

import signal as _signal

# ── Workspace control ───────────────────────────────────────────────────────

def workspace_go(args, _=None):
    n = (args or {}).get("number", (args or {}).get("workspace", 1))
    return _run(f"hyprctl dispatch workspace {n}") or f"Switched to workspace {n}"

_GENERIC_TERMINAL_CLASSES = {
    "kitty", "alacritty", "foot", "wezterm", "xterm",
    "konsole", "gnome-terminal", "terminator", "urxvt",
}

def _find_window_class(name):
    """Fuzzy-match a spoken app name against currently open windows' class/title,
    since Hyprland's WM class often doesn't match the binary/spoken name
    exactly (e.g. Chrome's class is 'google-chrome', not 'chrome').

    Matches in order of reliability: exact class -> class substring -> title
    substring. Title matching skips generic terminal emulators, since their
    titles are often arbitrary shell/command text (cwd, running program name,
    a filename someone has open) and can coincidentally contain a completely
    unrelated app's name — which was causing "move firefox" to sometimes grab
    a terminal window instead of the actual browser.
    """
    name_l = name.strip().lower()
    out = _run("hyprctl clients -j") or "[]"
    try:
        wins = json.loads(out)
    except Exception:
        wins = []

    for w in wins:
        if w.get("class", "").lower() == name_l:
            return w.get("class"), True

    for w in wins:
        if name_l in w.get("class", "").lower():
            return w.get("class"), True

    for w in wins:
        if w.get("class", "").lower() in _GENERIC_TERMINAL_CLASSES:
            continue
        if name_l in w.get("title", "").lower():
            return w.get("class"), True

    return name, False


def workspace_move_window(args, _=None):
    n   = (args or {}).get("number", 1)
    cls = (args or {}).get("class", "")
    if cls:
        real_cls, found = _find_window_class(cls)
        _run(f"hyprctl dispatch movetoworkspace {n},class:{real_cls}")
        if found:
            return f"Moved {real_cls} to workspace {n}"
        return f"Moved '{cls}' to workspace {n} (no open window matched that name exactly — tried it as-is)"
    _run(f"hyprctl dispatch movetoworkspacesilent {n}")
    return f"Moved this window to workspace {n}"

def workspace_move_here(args, _=None):
    n = (args or {}).get("number", 1)
    return _run(f"hyprctl dispatch movetoworkspace {n}")


def _all_windows():
    out = _run("hyprctl clients -j") or "[]"
    try:
        return json.loads(out)
    except Exception:
        return []


def workspace_move_all(args, _=None):
    n = (args or {}).get("number", 1)
    wins = _all_windows()
    if not wins:
        return "No open windows found."
    moved = 0
    for w in wins:
        addr = w.get("address")
        if addr:
            _run(f"hyprctl dispatch movetoworkspace {n},address:{addr}")
            moved += 1
    return f"Moved {moved} window(s) to workspace {n}"


# Multi-app keywords for "move all <query> to workspace N" — a query like
# "browsers" should match any of several actual WM classes.
_GROUP_CLASS_HINTS = {
    "browser":  ("firefox", "chrome", "chromium", "brave"),
    "browsers": ("firefox", "chrome", "chromium", "brave"),
    "terminal": ("kitty", "alacritty", "foot", "wezterm"),
    "terminals": ("kitty", "alacritty", "foot", "wezterm"),
}

def workspace_move_matching(args, _=None):
    n = (args or {}).get("number", 1)
    query = (args or {}).get("query", "").strip().lower()
    if not query:
        return "Move which windows? Give me an app name, or say 'all windows'."
    if query in ("windows", "window"):
        return workspace_move_all({"number": n})

    # strip a trailing "windows"/"window" from the query itself, e.g. "all
    # firefox windows to workspace 8" -> query ends up as "firefox windows"
    query = re.sub(r"\s+windows?$", "", query).strip()
    matchers = _GROUP_CLASS_HINTS.get(query, (query,))
    wants_terminals = query in ("terminal", "terminals") or any(
        m in _GENERIC_TERMINAL_CLASSES for m in matchers)

    wins = _all_windows()
    if not wins:
        return "No open windows found."

    # Prioritize matching by WM class; only fall back to matching by title
    # for windows whose title text is trustworthy — i.e. skip generic
    # terminal emulators unless the user is actually asking for terminals,
    # since a terminal's title is often arbitrary shell/command text that can
    # coincidentally contain some other app's name (e.g. "firefox-notes.txt"
    # open in vim), causing it to be wrongly swept up in an unrelated move.
    moved, names, moved_addrs = 0, [], set()
    for w in wins:
        cls = w.get("class", "").lower()
        if any(m in cls for m in matchers):
            addr = w.get("address")
            if addr and addr not in moved_addrs:
                _run(f"hyprctl dispatch movetoworkspace {n},address:{addr}")
                moved += 1
                moved_addrs.add(addr)
                names.append(w.get("class") or "?")

    if moved == 0:
        for w in wins:
            cls = w.get("class", "").lower()
            if cls in _GENERIC_TERMINAL_CLASSES and not wants_terminals:
                continue
            title = w.get("title", "").lower()
            if any(m in title for m in matchers):
                addr = w.get("address")
                if addr and addr not in moved_addrs:
                    _run(f"hyprctl dispatch movetoworkspace {n},address:{addr}")
                    moved += 1
                    moved_addrs.add(addr)
                    names.append(w.get("class") or "?")

    if moved == 0:
        return f"No open windows matched '{query}'."
    return f"Moved {moved} window(s) ({', '.join(names)}) to workspace {n}"

def workspace_list(_args=None):
    raw = _run("hyprctl -j workspaces")
    try:
        ws = json.loads(raw)
        lines = [f"WS{w.get('id')}  {w.get('name','')}  windows:{w.get('windows',0)}" for w in ws]
        return "\n".join(lines)
    except Exception:
        return raw

def window_float(args, _=None):
    return _run("hyprctl dispatch togglefloating")

def window_fullscreen(args, _=None):
    mode = (args or {}).get("mode", 0)  # 0=real, 1=maximize
    return _run(f"hyprctl dispatch fullscreen {mode}")

def window_kill_active(_args=None):
    return _run("hyprctl dispatch killactive")

def window_focus(args, _=None):
    cls = (args or {}).get("class","")
    return _run(f"hyprctl dispatch focuswindow class:{cls}")

def window_move(args, _=None):
    direction = (args or {}).get("direction","r")
    return _run(f"hyprctl dispatch movewindow {direction}")

def window_resize(args, _=None):
    w = (args or {}).get("w", 50)
    h = (args or {}).get("h", 0)
    return _run(f"hyprctl dispatch resizeactive {w} {h}")

def window_center(_args=None):
    return _run("hyprctl dispatch centerwindow")

def window_pin(_args=None):
    return _run("hyprctl dispatch pin")


# ── Audio ───────────────────────────────────────────────────────────────────

def audio_volume(args, _=None):
    """Set/change volume. value: '50%' or '+10%' or '-10%'."""
    val = str((args or {}).get("value", "50%"))
    if not val.endswith("%"):
        val += "%"
    if not val.startswith(("+","-")):
        return _run(f"wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ {val}")
    return _run(f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {val}")

def audio_mute(_args=None):
    return _run("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")

def audio_mic_mute(_args=None):
    return _run("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle")

def audio_get_volume(_args=None):
    return _run("wpctl get-volume @DEFAULT_AUDIO_SINK@")

def audio_player(args, _=None):
    """Control media player. action: play|pause|next|previous|stop"""
    action = (args or {}).get("action","play-pause")
    return _run(f"playerctl {action}")

def audio_status(_args=None):
    v    = _run("wpctl get-volume @DEFAULT_AUDIO_SINK@")
    play = _run("playerctl metadata --format '{{playerName}}: {{title}} — {{artist}}' 2>/dev/null")
    return f"Volume: {v}\nPlaying: {play or '(nothing)'}"


# ── Brightness ──────────────────────────────────────────────────────────────

def brightness_set(args, _=None):
    val = str((args or {}).get("value","50%"))
    if not val.endswith("%"):
        val += "%"
    return _run(f"brightnessctl set {val}")

def brightness_get(_args=None):
    return _run("brightnessctl get") + " / " + _run("brightnessctl max")


# ── Screenshot ──────────────────────────────────────────────────────────────

def screenshot(args, _=None):
    import datetime as _dt
    mode = (args or {}).get("mode","full")  # full|region|window|screen
    ts   = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out  = os.path.expanduser(f"~/Pictures/Screenshots/jarvis_{ts}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    script = os.path.join(HYPR, "scripts", "ScreenShot.sh")
    if os.path.isfile(script):
        return _run(f"bash '{script}' {mode}")

    if mode == "region" and shutil.which("slurp") and shutil.which("grim"):
        _run(f'grim -g "$(slurp)" \'{out}\'')
    elif shutil.which("grim"):
        _run(f"grim '{out}'")
    else:
        return "grim not installed"
    return f"Screenshot: {out}" if os.path.isfile(out) else "Screenshot failed"


# ── Screen recording ─────────────────────────────────────────────────────────

_RECORDING = {"proc": None, "path": None}

def screen_record_start(args, _=None):
    import datetime as _dt
    if not shutil.which("wf-recorder"):
        return "wf-recorder isn't installed."
    if _RECORDING["proc"] and _RECORDING["proc"].poll() is None:
        return f"Already recording to {_RECORDING['path']}."

    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.expanduser(f"~/Videos/jarvis_recording_{ts}.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    region = (args or {}).get("region")
    cmd = ["wf-recorder", "-f", out]
    if region and shutil.which("slurp"):
        geometry = subprocess.run(["slurp"], capture_output=True, text=True).stdout.strip()
        if geometry:
            cmd += ["-g", geometry]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    _RECORDING.update(proc=proc, path=out)
    return f"Recording started -> {out}"

def screen_record_stop(_args=None):
    proc = _RECORDING.get("proc")
    if not proc or proc.poll() is not None:
        return "Not currently recording."
    proc.send_signal(2)  # SIGINT — wf-recorder finalizes the file cleanly on this
    path = _RECORDING["path"]
    _RECORDING.update(proc=None, path=None)
    return f"Recording stopped -> {path}"


# ── System info ─────────────────────────────────────────────────────────────

def system_info(_args=None):
    cpu  = _run("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4\"%\"}'")
    ram  = _run("free -h | awk '/Mem:/{print $3\"/\"$2}'")
    disk = _run("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")'")
    gpu  = _run("nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>/dev/null || echo 'N/A'")
    load = _run("cat /proc/loadavg | cut -d' ' -f1-3")
    up   = _run("uptime -p")
    tmp  = _run("sensors 2>/dev/null | grep -E 'Core 0|Tdie|edge' | head -3")
    net  = _run("ip addr show | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | head -3")
    return (f"CPU: {cpu}  Load: {load}\nRAM: {ram}  Disk: {disk}\n"
            f"GPU: {gpu}\nUptime: {up}\nTemp:\n{tmp}\nNetwork: {net}")

def process_list(args=None):
    filt = (args or {}).get("filter","")
    if filt:
        return _run(f"ps aux | grep -i '{filt}' | grep -v grep | head -20")
    return _run("ps aux --sort=-%cpu | head -20")

def process_kill(args, _=None):
    name = (args or {}).get("name","")
    pid  = (args or {}).get("pid","")
    if pid:
        return _run(f"kill {pid}")
    if name:
        return _run(f"pkill -i '{name}'")
    return "Need name or pid"

def network_info(_args=None):
    local  = _run("ip addr show | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}'")
    wifi   = _run("iwgetid -r 2>/dev/null || nmcli -t -f active,ssid dev wifi 2>/dev/null | grep '^yes:' | cut -d: -f2")
    conns  = _run("ss -tunap 2>/dev/null | grep ESTABLISHED | wc -l")
    return f"Local: {local}\nWiFi: {wifi}\nConnections: {conns}"


# ── Wallpaper ────────────────────────────────────────────────────────────────

def wallpaper_set(args, _=None):
    raw = (args or {}).get("path", "").strip().strip("'\"")
    if not raw:
        return "Which wallpaper? Give a filename or path."
    expanded = os.path.expanduser(raw)
    if os.path.isfile(expanded):
        path = expanded
    else:
        wp_dirs = [
            "~/Pictures/wallpapers", "~/Pictures/Wallpapers",
            "~/Pictures", "~/.config/hypr/wallpapers",
            "~/wallpapers", "~/Wallpapers",
        ]
        candidates = []
        for d in wp_dirs:
            d = os.path.expanduser(d)
            if not os.path.isdir(d):
                continue
            for entry in os.listdir(d):
                full = os.path.join(d, entry)
                if os.path.isfile(full) and raw.lower() in entry.lower():
                    candidates.append(full)
        if not candidates:
            return (f"Couldn't find a wallpaper matching '{raw}' in "
                    f"~/Pictures/wallpapers, ~/Pictures, ~/.config/hypr/wallpapers.")
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        if len(candidates) > 1:
            listing = "\n".join(f"{i+1}. {p}" for i, p in enumerate(candidates[:6]))
            _PENDING_SELECTION.update(kind="wallpaper", candidates=candidates[:6], with_app=None)
            return f"Found {len(candidates)} matching wallpapers -- which one?\n{listing}\nSay \'open the first one\' or \'number 2\'."
        path = candidates[0]
    if shutil.which("swww"):
        r = _run(f"swww img \'{path}\' --transition-type wipe --transition-duration 1")
        return r or f"Wallpaper set: {path}"
    if shutil.which("hyprpaper"):
        r = _run(f"hyprctl hyprpaper wallpaper \',{path}\'")
        return r or f"Wallpaper set: {path}"
    if shutil.which("feh"):
        r = _run(f"feh --bg-scale \'{path}\'")
        return r or f"Wallpaper set: {path}"
    return f"No wallpaper tool found (swww/hyprpaper/feh). Path: {path}"


def wallpaper_random(_args=None):
    script = os.path.join(HYPR, "UserScripts", "WallpaperRandom.sh")
    if os.path.isfile(script):
        return _run(f"bash '{script}'")
    return "WallpaperRandom.sh not found"

def wallpaper_select(_args=None):
    script = os.path.join(HYPR, "UserScripts", "WallpaperSelect.sh")
    if os.path.isfile(script):
        return _run(f"bash '{script}'", timeout=60)
    return "WallpaperSelect.sh not found"


# ── Night mode / display ────────────────────────────────────────────────────

def night_mode(args, _=None):
    action = (args or {}).get("action","toggle")  # toggle|on|off
    script = os.path.join(HYPR, "scripts", "Hyprsunset.sh")
    if os.path.isfile(script):
        return _run(f"bash '{script}' {action}")
    if shutil.which("hyprsunset"):
        if action == "off":
            return _run("pkill hyprsunset")
        return _run("hyprsunset -t 4500 &")
    return "hyprsunset not installed"

def lock_screen(_args=None):
    for s in ["LockScreen.sh", "swaylock", "hyprlock"]:
        path = os.path.join(HYPR, "scripts", s)
        if os.path.isfile(path):
            return _run(f"bash '{path}'")
        if shutil.which(s.replace(".sh","")):
            return _run(s.replace(".sh",""))
    return _run("loginctl lock-session")

def logout(_args=None):
    script = os.path.join(HYPR, "scripts", "Wlogout.sh")
    if os.path.isfile(script):
        return _run(f"bash '{script}'")
    return _run("wlogout") or _run("hyprctl dispatch exit 0")


# ── Power management ─────────────────────────────────────────────────────────
# Destructive — always requires confirm_fn (see WRITE_TOOLS below).

def power_shutdown(_args=None, confirm_fn=None):
    if confirm_fn and not confirm_fn("Shut down the system now?"):
        return "Cancelled."
    return _run("systemctl poweroff") or _run("loginctl poweroff")

def power_reboot(_args=None, confirm_fn=None):
    if confirm_fn and not confirm_fn("Reboot the system now?"):
        return "Cancelled."
    return _run("systemctl reboot") or _run("loginctl reboot")

def power_suspend(_args=None, confirm_fn=None):
    return _run("systemctl suspend") or _run("loginctl suspend")

def power_hibernate(_args=None, confirm_fn=None):
    if confirm_fn and not confirm_fn("Hibernate the system now?"):
        return "Cancelled."
    return _run("systemctl hibernate") or _run("loginctl hibernate")

def battery_status(_args=None):
    if shutil.which("upower"):
        dev = _run("upower -e | grep -i battery | head -1").strip()
        if dev:
            out = _run(f"upower -i {dev}")
            pct  = re.search(r"percentage:\s*(\d+%)", out)
            state = re.search(r"state:\s*(\S+)", out)
            ttf  = re.search(r"time to (?:empty|full):\s*([\d.]+ \w+)", out)
            parts = []
            if pct:   parts.append(f"{pct.group(1)}")
            if state: parts.append(state.group(1))
            if ttf:   parts.append(f"{ttf.group(1)} remaining")
            if parts:
                return " · ".join(parts)
    # Fallback: read straight from sysfs
    base = "/sys/class/power_supply"
    try:
        for name in os.listdir(base):
            if name.startswith(("BAT", "battery")):
                cap = open(f"{base}/{name}/capacity").read().strip()
                status = open(f"{base}/{name}/status").read().strip()
                return f"{cap}% · {status}"
    except Exception:
        pass
    return "No battery found (likely a desktop system)."


# ── Bluetooth ────────────────────────────────────────────────────────────────

def bluetooth_toggle(args, _=None):
    on = (args or {}).get("on")
    if not shutil.which("bluetoothctl"):
        return "bluetoothctl isn't installed."
    if on is None:
        state = _run("bluetoothctl show | grep 'Powered:'")
        on = "no" in state.lower()
    _run(f"bluetoothctl power {'on' if on else 'off'}")
    return f"Bluetooth {'on' if on else 'off'}"

def bluetooth_list(_args=None):
    if not shutil.which("bluetoothctl"):
        return "bluetoothctl isn't installed."
    out = _run("bluetoothctl devices")
    if not out.strip():
        return "No paired Bluetooth devices found."
    return out

def bluetooth_connect(args, _=None):
    name = (args or {}).get("device", "").strip()
    if not name or not shutil.which("bluetoothctl"):
        return "Which device? (or bluetoothctl isn't installed)"
    devices = _run("bluetoothctl devices")
    mac = None
    for line in devices.splitlines():
        if name.lower() in line.lower():
            parts = line.split()
            if len(parts) >= 2:
                mac = parts[1]
                break
    if not mac:
        return f"Couldn't find a paired device matching '{name}'."
    r = _run(f"bluetoothctl connect {mac}")
    return r or f"Connecting to {name}..."

def bluetooth_disconnect(args, _=None):
    name = (args or {}).get("device", "").strip()
    if not shutil.which("bluetoothctl"):
        return "bluetoothctl isn't installed."
    if not name:
        return _run("bluetoothctl disconnect") or "Disconnected."
    devices = _run("bluetoothctl devices")
    for line in devices.splitlines():
        if name.lower() in line.lower():
            mac = line.split()[1]
            return _run(f"bluetoothctl disconnect {mac}") or f"Disconnected {name}."
    return f"Couldn't find a paired device matching '{name}'."


# ── WiFi ─────────────────────────────────────────────────────────────────────

def wifi_toggle(args, _=None):
    on = (args or {}).get("on")
    if not shutil.which("nmcli"):
        return "nmcli isn't installed."
    if on is None:
        state = _run("nmcli radio wifi")
        on = "disabled" in state.lower()
    _run(f"nmcli radio wifi {'on' if on else 'off'}")
    return f"WiFi {'on' if on else 'off'}"

def wifi_list(_args=None):
    if not shutil.which("nmcli"):
        return "nmcli isn't installed."
    out = _run("nmcli -t -f active,signal,ssid dev wifi list")
    if not out.strip():
        return "No WiFi networks found."
    lines = ["(active) " + l.split(":",2)[2] if l.startswith("yes:") else
             f"{l.split(':',2)[1]}% - {l.split(':',2)[2]}" for l in out.splitlines() if l]
    return "\n".join(lines[:15])

def wifi_connect(args, confirm_fn=None):
    ssid = (args or {}).get("ssid", "").strip()
    password = (args or {}).get("password", "").strip()
    if not ssid:
        return "Which network?"
    if not shutil.which("nmcli"):
        return "nmcli isn't installed."
    cmd = f"nmcli dev wifi connect '{ssid}'" + (f" password '{password}'" if password else "")
    r = _run(cmd)
    if "error" in r.lower() or "fail" in r.lower():
        return r
    return f"Connected to {ssid}." if r else f"Connecting to {ssid}..."


# ── Clipboard ────────────────────────────────────────────────────────────────

def clipboard_set(args, _=None):
    text = (args or {}).get("text", "")
    if not shutil.which("wl-copy"):
        return "wl-copy isn't installed (part of wl-clipboard)."
    try:
        subprocess.run(["wl-copy"], input=text, text=True, timeout=5)
        return "Copied to clipboard."
    except Exception as e:
        return f"Failed to copy: {e}"

def clipboard_get(_args=None):
    if not shutil.which("wl-paste"):
        return "wl-paste isn't installed (part of wl-clipboard)."
    try:
        r = subprocess.run(["wl-paste"], capture_output=True, text=True, timeout=5)
        return r.stdout or "(clipboard is empty)"
    except Exception as e:
        return f"Failed to read clipboard: {e}"

def clipboard_history(_args=None):
    if not shutil.which("cliphist"):
        return "cliphist isn't installed — clipboard history isn't available."
    out = _run("cliphist list | head -15")
    return out or "Clipboard history is empty."


# ── Notifications ────────────────────────────────────────────────────────────

def notify_send(args, _=None):
    title = (args or {}).get("title", "JARVIS")
    body  = (args or {}).get("body", "")
    if not shutil.which("notify-send"):
        return "notify-send isn't installed."
    subprocess.Popen(["notify-send", title, body], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, start_new_session=True)
    return "Notification sent."

def notify_clear(_args=None):
    if shutil.which("swaync-client"):
        _run("swaync-client -C")
        return "Cleared notifications."
    if shutil.which("dunstctl"):
        _run("dunstctl close-all")
        return "Cleared notifications."
    return "No supported notification daemon found (swaync/dunst)."


# -- User preferences ---------------------------------------------------------

def prefs_set(args, _=None):
    key   = (args or {}).get("key","").strip()
    value = (args or {}).get("value","")
    if not key or not value:
        return "Need both key and value."
    if _UserPrefs:
        _UserPrefs.update(key, value)
        return f"Remembered: {key} = {value}"
    return "Preferences module not available."

def prefs_get(args, _=None):
    key = (args or {}).get("key","").strip()
    if _UserPrefs:
        prefs = _UserPrefs.load()
        return str(prefs.get(key,"not set")) if key else __import__("json").dumps(prefs, indent=2)
    return "Preferences module not available."

def prefs_set_name(args, _=None):
    name = (args or {}).get("name","").strip()
    if not name:
        return "What name should I call you?"
    if _UserPrefs:
        _UserPrefs.update("name", name)
        return f"Got it -- I will call you {name}."
    return "Preferences module not available."

def prefs_note(args, _=None):
    note = (args or {}).get("note","").strip()
    if not note:
        return "What should I note down?"
    if _UserPrefs:
        import datetime
        prefs = _UserPrefs.load()
        notes = prefs.get("notes",[])
        notes.insert(0, {"text": note, "ts": datetime.datetime.now().isoformat()})
        prefs["notes"] = notes[:50]
        _UserPrefs.save(prefs)
        return f"Noted: {note}"
    return "Preferences module not available."

def prefs_list_notes(_args=None):
    if _UserPrefs:
        notes = _UserPrefs.load().get("notes",[])
        if not notes:
            return "No notes saved yet."
        return "\n".join(f"- {n['text']}  ({n['ts'][:10]})" for n in notes)
    return "Preferences module not available."


# -- System status ------------------------------------------------------------

def system_status(_args=None):
    try:
        from .system_state import deep_read_system, get_system_context
        return get_system_context(deep_read_system(fast=False))
    except Exception as e:
        return f"System status error: {e}"

def system_info_brief(_args=None):
    cpu  = _run("top -bn1 | grep \'Cpu(s)\' | awk \'{print $2+$4}\'") or "?"
    ram  = _run("free -h | awk \'/Mem:/{print $3\"\"/\"\"+$2}\'") or "?"
    disk = _run("df -h / | awk \'NR==2{print $3\"/\"$2,\"(\"$5\")\"}\'") or "?"
    load = _run("cut -d\' \' -f1-3 /proc/loadavg") or "?"
    lines = [f"CPU: {cpu}%  RAM: {ram}  Disk: {disk}  Load: {load}"]
    bat_base = "/sys/class/power_supply"
    if os.path.isdir(bat_base):
        for name in os.listdir(bat_base):
            if name.startswith(("BAT","battery")):
                try:
                    cap    = open(f"{bat_base}/{name}/capacity").read().strip()
                    status = open(f"{bat_base}/{name}/status").read().strip()
                    lines.append(f"Battery: {cap}% ({status})")
                except Exception:
                    pass
                break
    return "\n".join(lines)


# -- Package management -------------------------------------------------------

def pkg_install(args, confirm_fn=None):
    pkg = (args or {}).get("package","").strip()
    if not pkg:
        return "Which package?"
    mgr = "yay" if shutil.which("yay") else "paru" if shutil.which("paru") else "pacman"
    if confirm_fn and not confirm_fn(f"Install \'{pkg}\' using {mgr}?"):
        return "Cancelled."
    out = _run(f"{mgr} -S --noconfirm {pkg}", timeout=120)
    return out or f"Ran: {mgr} -S {pkg}"

def pkg_remove(args, confirm_fn=None):
    pkg = (args or {}).get("package","").strip()
    if not pkg:
        return "Which package?"
    if confirm_fn and not confirm_fn(f"Remove \'{pkg}\'?"):
        return "Cancelled."
    return _run(f"sudo pacman -Rns --noconfirm {pkg}", timeout=60) or f"Removed {pkg}"

def pkg_search(args, _=None):
    query = (args or {}).get("query","").strip()
    if not query:
        return "Search for what?"
    out = _run(f"pacman -Ss {query} | head -30")
    if shutil.which("yay"):
        aur = _run(f"yay -Ss {query} --aur 2>/dev/null | head -20")
        if aur:
            out += f"\n\n[AUR]\n{aur}"
    return out or f"No results for \'{query}\'"

def pkg_update(args, confirm_fn=None):
    if confirm_fn and not confirm_fn("Update all packages? (pacman -Syu)"):
        return "Cancelled."
    mgr = "yay" if shutil.which("yay") else "pacman"
    return _run(f"{mgr} -Syu --noconfirm", timeout=300) or "System update complete."

def pkg_list_installed(args, _=None):
    query = (args or {}).get("query","").strip()
    if query:
        return _run(f"pacman -Qq | grep -i {query} | head -30") or "No results."
    count    = _run("pacman -Qq | wc -l")
    explicit = _run("pacman -Qqe | head -30")
    return f"{count} total packages.\nExplicit (sample):\n{explicit}"


# -- Systemd services ---------------------------------------------------------

def service_status(args, _=None):
    name = (args or {}).get("service","").strip()
    if not name:
        return "Which service?"
    return _run(f"systemctl status {name} --no-pager -l | head -30") or f"Service \'{name}\' not found."

def service_start(args, _=None):
    name = (args or {}).get("service","").strip()
    if not name:
        return "Which service?"
    return _run(f"systemctl start {name}") or f"Started {name}."

def service_stop(args, confirm_fn=None):
    name = (args or {}).get("service","").strip()
    if not name:
        return "Which service?"
    if confirm_fn and not confirm_fn(f"Stop service \'{name}\'?"):
        return "Cancelled."
    return _run(f"systemctl stop {name}") or f"Stopped {name}."

def service_restart(args, _=None):
    name = (args or {}).get("service","").strip()
    if not name:
        return "Which service?"
    return _run(f"systemctl restart {name}") or f"Restarted {name}."

def service_enable(args, _=None):
    name = (args or {}).get("service","").strip()
    if not name:
        return "Which service?"
    return _run(f"systemctl enable {name}") or f"Enabled {name}."

def service_disable(args, confirm_fn=None):
    name = (args or {}).get("service","").strip()
    if not name:
        return "Which service?"
    if confirm_fn and not confirm_fn(f"Disable \'{name}\' on boot?"):
        return "Cancelled."
    return _run(f"systemctl disable {name}") or f"Disabled {name}."

def service_list(args, _=None):
    filt = (args or {}).get("filter","failed")
    if filt == "failed":
        return _run("systemctl --failed --no-pager --no-legend | head -20") or "No failed services."
    if filt == "running":
        return _run("systemctl list-units --type=service --state=running --no-pager --no-legend | head -30")
    return _run(f"systemctl list-units --type=service --no-pager --no-legend | grep {filt} | head -20")


# ── App launcher ─────────────────────────────────────────────────────────────

_BROWSERS   = ["google-chrome-stable","google-chrome","chromium","firefox","brave"]
_TERMINALS  = ["kitty","alacritty","foot","wezterm"]
_FILE_MGRS  = ["thunar","nautilus","dolphin","nemo"]
_WEBSITE_MAP= {
    "youtube":"https://youtube.com","github":"https://github.com",
    "gmail":"https://mail.google.com","google":"https://google.com",
    "reddit":"https://reddit.com","chatgpt":"https://chat.openai.com",
    "claude":"https://claude.ai","discord":"https://discord.com/app",
    "twitter":"https://twitter.com","x":"https://x.com",
    "netflix":"https://netflix.com","spotify":"https://open.spotify.com",
    "linkedin":"https://linkedin.com","stackoverflow":"https://stackoverflow.com",
    "figma":"https://figma.com","notion":"https://notion.so",
}

# Hand-written aliases for apps whose spoken name doesn't match their binary.
_APP_ALIASES = {
    "vscode":"code","vs code":"code","visual studio code":"code","visualstudiocode":"code",
    "chrome":"google-chrome-stable","google chrome":"google-chrome-stable",
    "calculator":"qalculate-gtk","calc":"qalculate-gtk",
    "text editor":"gedit","notes":"gedit","notepad":"gedit",
    "file manager":"thunar","files":"thunar","filemanager":"thunar",
    "terminal":"kitty","console":"kitty",
    "settings":"nwg-look","displays":"nwg-displays",
    "task manager":"btop","system monitor":"btop",
    "screenshot tool":"swappy",
}

# Remembers the last thing opened so "open it in vscode" / "open youtube in
# it" can resolve the "it"/"that" pronoun instead of failing.
_LAST_OPENED = {"path": None, "app": None, "url": None}

def _find_binary(candidates):
    for c in candidates:
        if shutil.which(c.split()[0]):
            return c
    return None


# Every place an Arch Linux app can end up, regardless of install method:
#   pacman/AUR      -> real binaries on PATH (/usr/bin, /usr/local/bin, yay builds land here too)
#   flatpak         -> ~/.local/share/flatpak/exports/{bin,share/applications} (user)
#                      /var/lib/flatpak/exports/{bin,share/applications} (system)
#   snap            -> /snap/bin, /var/lib/snapd/desktop/applications
#   AppImage        -> wherever the user put it — we check the common spots
#   manual/opt      -> /opt/<app>/<binary>, ~/.local/bin
_EXTRA_BIN_DIRS = [
    "/usr/bin", "/usr/local/bin",
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/.local/share/flatpak/exports/bin"),
    "/var/lib/flatpak/exports/bin",
    "/snap/bin",
]
_DESKTOP_ENTRY_DIRS = [
    "/usr/share/applications", "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    "/var/lib/flatpak/exports/share/applications",
    "/var/lib/snapd/desktop/applications",
]
_APPIMAGE_DIRS = [
    os.path.expanduser("~/Applications"),
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/Downloads"),
    "/opt",
]
_FIELD_CODE_RE = re.compile(r"%[a-zA-Z]")


@functools.lru_cache(maxsize=1)
def _scan_installed_apps():
    """
    One-time (cached) scan of everything that could plausibly be "an app" on
    an Arch system, across every install method — pacman/AUR binaries,
    flatpak (user + system), snap, AppImages, and manual /opt installs — plus
    ~/.config subfolder names as extra hints (e.g. a 'vesktop' folder there
    tells us which Discord client is actually installed).
    """
    bins = set()
    for d in _EXTRA_BIN_DIRS:
        try:
            for f in os.listdir(d):
                full = os.path.join(d, f)
                if os.path.isfile(full) and os.access(full, os.X_OK):
                    bins.add(f)
        except Exception:
            continue

    # /opt/<app>/<binary> — common for manually-installed or proprietary apps
    try:
        for sub in os.listdir("/opt"):
            subdir = os.path.join("/opt", sub)
            if not os.path.isdir(subdir):
                continue
            try:
                for f in os.listdir(subdir):
                    full = os.path.join(subdir, f)
                    if os.path.isfile(full) and os.access(full, os.X_OK):
                        bins.add(f)
            except Exception:
                continue
    except Exception:
        pass

    cfg_hints = set()
    try:
        for entry in os.listdir(os.path.expanduser("~/.config")):
            cfg_hints.add(entry)
    except Exception:
        pass

    return bins, cfg_hints


@functools.lru_cache(maxsize=1)
def _scan_desktop_entries():
    """
    Parse .desktop files -> {lowercase name-or-id: (desktop_id, exec_cmd)}.
    This is the best source of human-friendly app names (a flatpak/snap app's
    binary name is often unrecognizable, but its .desktop Name= is exactly
    what a person would say, e.g. "Visual Studio Code", "GIMP").
    """
    entries = {}
    for d in _DESKTOP_ENTRY_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            fnames = os.listdir(d)
        except Exception:
            continue
        for fname in fnames:
            if not fname.endswith(".desktop"):
                continue
            full = os.path.join(d, fname)
            name, exec_cmd, no_display = None, None, False
            try:
                with open(full, "r", errors="ignore") as fh:
                    in_main_section = False
                    for line in fh:
                        line = line.strip()
                        if line.startswith("[Desktop Entry]"):
                            in_main_section = True
                            continue
                        if line.startswith("[") and in_main_section:
                            break  # left the main section (e.g. Desktop Action)
                        if not in_main_section:
                            continue
                        if line.startswith("Name=") and name is None:
                            name = line.split("=", 1)[1].strip()
                        elif line.startswith("Exec=") and exec_cmd is None:
                            exec_cmd = line.split("=", 1)[1].strip()
                        elif line.strip() == "NoDisplay=true":
                            no_display = True
            except Exception:
                continue
            if no_display or not name or not exec_cmd:
                continue
            desktop_id = fname[:-len(".desktop")]
            clean_exec = _FIELD_CODE_RE.sub("", exec_cmd).strip()
            entries[name.lower()] = (desktop_id, clean_exec)
            entries.setdefault(desktop_id.lower(), (desktop_id, clean_exec))
    return entries


@functools.lru_cache(maxsize=1)
def _scan_appimages():
    """AppImages aren't registered anywhere — just look in the common spots."""
    found = {}
    for d in _APPIMAGE_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            for f in os.listdir(d):
                if f.lower().endswith(".appimage"):
                    full = os.path.join(d, f)
                    if os.access(full, os.X_OK):
                        found[f[:-len(".appimage")].lower()] = full
        except Exception:
            continue
    return found


def _launch_argv(resolved):
    """Turn whatever _resolve_app_binary returned into a real argv list."""
    if isinstance(resolved, tuple):
        kind, val = resolved
        if kind == "desktop":
            return ["gtk-launch", val]
        if kind == "appimage":
            return [val]
    return [resolved]


def _display_name(resolved):
    return resolved[1] if isinstance(resolved, tuple) else resolved


def _resolve_app_binary(name):
    """
    Fuzzy-resolve whatever the user called an app to something launchable,
    across every install method. Returns one of:
      "binary-name"                  -> exec directly
      ("desktop", "app-id")          -> `gtk-launch app-id` (flatpak/snap/etc.)
      ("appimage", "/path/to/x.AppImage") -> exec that file directly
      None                            -> nothing found
    """
    name = (name or "").strip().lower()
    # Strip trailing noise that commonly leaks in from NL parsing
    name = re.sub(r"\s+(?:app|application|program|software|browser|tool)\s*$", "", name).strip()
    if not name:
        return None

    # Generic words (file-type nouns, quantifiers, pronouns) should never be
    # treated as an app name — fuzzy-matching them against real binaries can
    # land on completely unrelated system utilities purely by string
    # similarity (e.g. "image" incorrectly resolving to "e2image", an ext2/3/4
    # filesystem imaging tool). These should be handled by the file-search
    # tools (open_file_by_type etc.) instead, never reach here as an app name.
    if name in _GENERIC_NOT_APP_WORDS:
        return None

    if name in _APP_ALIASES and shutil.which(_APP_ALIASES[name]):
        return _APP_ALIASES[name]

    bins, cfg_hints = _scan_installed_apps()
    desktop = _scan_desktop_entries()
    appimages = _scan_appimages()

    if shutil.which(name):
        return name
    squashed = name.replace(" ", "")
    if shutil.which(squashed):
        return squashed

    # Discord-likes: prefer whichever client the user actually has installed
    if "discord" in name:
        for cand in ("vesktop", "legcord", "equibop", "discord"):
            if shutil.which(cand):
                return cand

    # Exact match against a .desktop entry's Name= or file id (most reliable
    # for flatpak/snap/manually-installed apps whose binary name is opaque)
    if name in desktop:
        return ("desktop", desktop[name][0])
    if squashed in desktop:
        return ("desktop", desktop[squashed][0])

    # Fuzzy match, in order of how trustworthy the name source is:
    # desktop entries (human-friendly) -> real binaries -> AppImages -> config hints
    dmatch = difflib.get_close_matches(name, list(desktop.keys()), n=1, cutoff=0.7)
    if dmatch:
        return ("desktop", desktop[dmatch[0]][0])

    match = difflib.get_close_matches(squashed, bins, n=1, cutoff=0.72)
    if match and shutil.which(match[0]):
        return match[0]

    amatch = difflib.get_close_matches(name, list(appimages.keys()), n=1, cutoff=0.6)
    if amatch:
        return ("appimage", appimages[amatch[0]])

    match2 = difflib.get_close_matches(name, [c.lower() for c in cfg_hints], n=1, cutoff=0.75)
    if match2 and shutil.which(match2[0]):
        return match2[0]

    return None


_TRAILING_FILLER_RE = re.compile(
    r"\s+(?:in|on)\s+(?:it|that|this|the\s+browser|firefox|chrome|chromium|brave)\s*$"
)

def open_app(args, _=None):
    app_raw = (args or {}).get("app", "").strip()
    url     = (args or {}).get("url", "").strip()
    ws      = (args or {}).get("workspace")

    if ws:
        _run(f"hyprctl dispatch workspace {ws}")

    # "open youtube in it" -> strip the trailing filler so lookups still hit
    app_clean = _TRAILING_FILLER_RE.sub("", app_raw).strip()
    app = app_clean.lower()

    if app in ("it", "that", "this") and _LAST_OPENED.get("app"):
        app = _LAST_OPENED["app"]

    # URL or website shortcut
    site = _WEBSITE_MAP.get(app)
    target = url or site or (app_raw if app.startswith(("http://", "https://", "www.")) else None)
    if target:
        last_app = _LAST_OPENED.get("app")
        b = last_app if last_app in _BROWSERS and shutil.which(last_app) else None
        if not b:
            b = _find_binary(_BROWSERS)
        if b:
            subprocess.Popen([b, target], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, start_new_session=True)
            _LAST_OPENED.update(app=b, path=None, url=target)
            return f"Opening {target} in {b}"
        return "No browser found"

    # Terminal shortcut
    if app in ("terminal", "term", "console"):
        t = _find_binary(_TERMINALS)
        if t:
            subprocess.Popen([t], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, start_new_session=True)
            return f"Launched {t}"

    # File manager
    if app in ("files", "file manager", "filemanager"):
        fm = _find_binary(_FILE_MGRS)
        if fm:
            subprocess.Popen([fm], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, start_new_session=True)
            return f"Launched {fm}"

    # Resolve against real installed apps (aliases, /usr/bin, ~/.config hints,
    # fuzzy matching) rather than blindly shelling out the raw phrase — this is
    # what used to break on compound sentences like "firefox and open youtube
    # in it", where the whole sentence got passed as literal argv to firefox.
    binary = _resolve_app_binary(app_clean)
    if binary:
        argv = _launch_argv(binary)
        subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, start_new_session=True)
        name = _display_name(binary)
        _LAST_OPENED.update(app=name, path=None, url=None)
        return f"Launched {name}"

    # A multi-word phrase (e.g. "that umis portal link") can never be a real
    # xdg-open target — it's guaranteed to fail. Search the web for it in the
    # browser instead, which is almost always what the person actually wanted.
    if " " in app_clean.strip():
        b = _find_binary(_BROWSERS)
        if b:
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(app_clean)}"
            subprocess.Popen([b, search_url], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, start_new_session=True)
            _LAST_OPENED.update(app=b, path=None, url=search_url)
            return f"Couldn't find an app or file called '{app_clean}' — searching the web for it in {b} instead."

    # xdg-open fallback — last resort, only for the literal cleaned text
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", app_clean], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, start_new_session=True)
        return f"xdg-open {app_clean}"

    return f"'{app_clean}' not found. Install: sudo pacman -S {app_clean} or yay -S {app_clean}"

def close_app(args, _=None):
    raw = (args or {}).get("app", "").strip()
    if not raw:
        return "No app specified."

    if raw.lower() in ("it", "that", "this") and _LAST_OPENED.get("app"):
        raw = _LAST_OPENED["app"]

    cls = _clean_close_target(raw)
    if not cls:
        return "No app specified."

    real_cls, found = _find_window_class(cls)
    if found:
        _run(f"hyprctl dispatch closewindow class:{real_cls}")
        return f"Closed {real_cls}"

    # No open window matched — maybe it's running without a visible window;
    # try killing the process by name and honestly report whether pkill
    # actually found and killed something (its own exit code says so).
    _, rc = _run_rc(f"pkill -i '{cls}'")
    if rc == 0:
        return f"Closed {cls} (was running in the background, no window was open)"
    return f"I don't see anything open or running matching '{cls}'."


# ── File opening ─────────────────────────────────────────────────────────────
# "open file X" used to fall straight into open_app's `xdg-open '{app}'`
# fallback, which only works if X happens to already be a valid path relative
# to the process's cwd. Any other phrasing ("open file report.pdf" while
# jarvis is running from ~/.config/hypr/scripts, say) silently failed. This
# resolves a bare filename against the common user directories first.

_FILE_SEARCH_DIRS = [
    "~", "~/Downloads", "~/Documents", "~/Desktop", "~/Pictures",
    "~/Pictures/wallpapers", "~/Videos", "~/Music", "~/.config",
]

_DIR_SHORTCUTS = {
    "downloads": "~/Downloads", "download": "~/Downloads",
    "documents": "~/Documents", "document": "~/Documents",
    "desktop": "~/Desktop",
    "pictures": "~/Pictures", "picture": "~/Pictures",
    "videos": "~/Videos", "video": "~/Videos",
    "music": "~/Music",
    "home": "~",
    "config": "~/.config",
}

_GENERIC_NOT_APP_WORDS = {
    "image", "images", "photo", "photos", "picture", "pictures",
    "file", "files", "folder", "folders", "document", "documents",
    "video", "videos", "one", "any", "some", "it", "that", "this",
    "thing", "stuff", "a", "an", "the",
}

# Maps a spoken file-type word to the real extension(s) it could mean —
# used for vague requests like "open an image" / "open a document" where no
# specific filename was given.
_TYPE_WORD_EXTS = {
    "image": ("png", "jpg", "jpeg", "gif", "webp", "bmp"),
    "images": ("png", "jpg", "jpeg", "gif", "webp", "bmp"),
    "photo": ("png", "jpg", "jpeg", "gif", "webp"),
    "photos": ("png", "jpg", "jpeg", "gif", "webp"),
    "picture": ("png", "jpg", "jpeg", "gif", "webp"),
    "pictures": ("png", "jpg", "jpeg", "gif", "webp"),
    "video": ("mp4", "mkv", "mov", "avi", "webm"),
    "videos": ("mp4", "mkv", "mov", "avi", "webm"),
    "document": ("pdf", "docx", "doc", "txt", "odt"),
    "documents": ("pdf", "docx", "doc", "txt", "odt"),
}

_FOLDER_WORD_RE = re.compile(
    r"(?:from|in)\s+(?:the\s+|my\s+)?([a-zA-Z0-9_\-]+)\s+folder\b", re.IGNORECASE)

def _extract_folder_word(text):
    """
    Pulls an arbitrary (non-standard-shortcut) folder name out of a sentence,
    regardless of where it appears — "from sri folder open an image" and
    "open an image from sri folder" both yield ("sri", "<rest of sentence>").
    Unlike _DIR_SHORTCUTS, this isn't limited to a fixed list of folder
    names — "sri" gets resolved later via the same fuzzy folder search
    open_folder itself uses.
    """
    m = _FOLDER_WORD_RE.search(text)
    if not m:
        return None, text
    folder_word = m.group(1).strip()
    remainder = (text[:m.start()] + " " + text[m.end():]).strip()
    return folder_word, remainder

# Extra roots checked (shallow, bounded, timeboxed) if a file can't be found
# anywhere under $HOME — covers external/secondary drives and shared install
# locations without ever touching /proc, /sys, /dev, or other system internals.
_SYSTEM_SEARCH_ROOTS = ["/mnt", "/media", "/opt", "/srv"]

def _system_wide_search(base_lower, limit=15):
    results = []
    for root in _SYSTEM_SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        try:
            out = subprocess.run(
                ["find", root, "-maxdepth", "6", "-iname", f"*{base_lower}*", "-type", "f"],
                capture_output=True, text=True, timeout=4,
            )
            for line in out.stdout.splitlines():
                line = line.strip()
                if line:
                    results.append(line)
            if len(results) >= limit:
                break
        except Exception:
            continue
    return results


_LEADING_FILLER_RE = re.compile(r"^(?:that|this|the)\s+(?=\S)", re.IGNORECASE)

def _strip_leading_filler(text):
    """'open that v12' -> 'v12'. Only strips when something real follows —
    a bare 'that'/'this' on its own is still handled as a pronoun elsewhere."""
    return _LEADING_FILLER_RE.sub("", text.strip(), count=1)


_FILE_WORD_FILLER_RE  = re.compile(
    r"^(?:a|the|my|that|this)\s+(?:file|folder|document|directory)\s+(?:named|called)\s+",
    re.IGNORECASE)
_FILE_WORD_FILLER_RE2 = re.compile(
    r"^(?:a|the|my)\s+(?:file|folder|document|directory)\s+", re.IGNORECASE)
_NAMED_CALLED_RE = re.compile(r"^(?:named|called)\s+", re.IGNORECASE)
_IN_DIR_RE = re.compile(
    r"\s+(?:in|from|inside|under)\s+(?:my\s+|the\s+)?([a-zA-Z]+)\s*$", re.IGNORECASE)

def _extract_target_and_dir(text):
    """
    Turns a natural sentence fragment into (clean_name, dir_hint):
      "a file named jarvis in my downloads" -> ("jarvis", "~/Downloads")
      "that v12"                            -> ("v12", None)
      "report.pdf"                          -> ("report.pdf", None)
    Strips conversational filler ("a file named", "the folder called") and
    pulls a trailing "in/from <shortcut dir>" out as a directory hint instead
    of letting it pollute the search term.
    """
    t = text.strip()
    dir_hint = None
    m = _IN_DIR_RE.search(t)
    if m and m.group(1).lower() in _DIR_SHORTCUTS:
        dir_hint = _DIR_SHORTCUTS[m.group(1).lower()]
        t = t[:m.start()].strip()
    t = _FILE_WORD_FILLER_RE.sub("", t)
    t = _FILE_WORD_FILLER_RE2.sub("", t)
    t = _NAMED_CALLED_RE.sub("", t)
    t = _strip_leading_filler(t)
    return t.strip(), dir_hint


_TRAILING_IN_WITH_ON_RE = re.compile(r"\s+(?:in|with|on)\s+(.+)$", re.IGNORECASE)

def _extract_target_dir_app(text):
    """
    Like _extract_target_and_dir, but also pulls a trailing "in/with/on <app>"
    out as an app-to-open-with hint — as long as that trailing word isn't
    actually a directory shortcut (so "...in downloads" stays a dir_hint, but
    "...in vscode" becomes an app_hint). Handles combined phrasing like
    "a folder named jarvis from downloads in vscode".
    Returns (clean_name, dir_hint, app_hint).
    """
    t = text.strip()
    app_hint = None
    m = _TRAILING_IN_WITH_ON_RE.search(t)
    if m:
        candidate = m.group(1).strip()
        candidate_bare = re.sub(r"^(?:my|the)\s+", "", candidate.lower()).strip()
        if candidate_bare not in _DIR_SHORTCUTS:
            app_hint = candidate
            t = t[:m.start()].strip()
    target, dir_hint = _extract_target_and_dir(t)
    return target, dir_hint, app_hint


def _resolve_file_path(name, dir_hint=None, max_candidates=8):
    """
    Returns a ranked list of candidate file paths for `name` (possibly empty).
    len()==0 -> nothing found. len()==1 -> confident single match, safe to
    auto-open. len()>1 -> genuinely ambiguous, caller should list & ask.
    Search order: literal path -> (dir_hint, if given, else common dirs) ->
    bounded $HOME walk -> bounded system-wide roots.
    """
    raw = name.strip().strip("'\"")
    expanded = os.path.expanduser(raw)
    looks_like_path = "/" in raw or raw.startswith("~")

    if (not dir_hint or looks_like_path) and os.path.isfile(expanded):
        return [os.path.abspath(expanded)]
    candidate = os.path.join(os.getcwd(), raw)
    if (not dir_hint or looks_like_path) and os.path.isfile(candidate):
        return [os.path.abspath(candidate)]

    base_lower = os.path.basename(raw).lower()
    search_dirs = [dir_hint] if dir_hint else _FILE_SEARCH_DIRS
    exact, partial = [], []

    for d in search_dirs:
        d = os.path.expanduser(d)
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.listdir(d):
                full = os.path.join(d, entry)
                if not os.path.isfile(full):
                    continue
                if entry.lower() == base_lower:
                    exact.append(full)
                elif base_lower in entry.lower():
                    partial.append(full)
        except Exception:
            continue

    if exact:
        exact.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return exact[:max_candidates]

    if not partial:
        root_dir = os.path.expanduser(dir_hint) if dir_hint else os.path.expanduser("~")
        max_depth = 3 if dir_hint else 4
        if os.path.isdir(root_dir):
            for root, dirs, files in os.walk(root_dir):
                if root[len(root_dir):].count(os.sep) >= max_depth:
                    dirs[:] = []
                dirs[:] = [d for d in dirs if not d.startswith(".") or d == ".config"]
                for f in files:
                    full = os.path.join(root, f)
                    if f.lower() == base_lower:
                        partial.insert(0, full)
                    elif base_lower in f.lower():
                        partial.append(full)
                if len(partial) > 25:
                    break

    if not partial and not dir_hint:
        partial = _system_wide_search(base_lower)

    if partial:
        seen, deduped = set(), []
        for p in partial:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        deduped.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
        return deduped[:max_candidates]

    return []


def _resolve_folder_path(name, dir_hint=None, max_candidates=8):
    """Same idea as _resolve_file_path but for directories."""
    raw = name.strip().strip("'\"").rstrip("/")
    expanded = os.path.expanduser(raw)
    looks_like_path = "/" in raw or raw.startswith("~")
    if (not dir_hint or looks_like_path) and os.path.isdir(expanded):
        return [os.path.abspath(expanded)]

    base_lower = os.path.basename(raw).lower()
    search_dirs = [dir_hint] if dir_hint else _FILE_SEARCH_DIRS
    exact, partial = [], []

    for d in search_dirs:
        d = os.path.expanduser(d)
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.listdir(d):
                full = os.path.join(d, entry)
                if not os.path.isdir(full):
                    continue
                if entry.lower() == base_lower:
                    exact.append(full)
                elif base_lower in entry.lower():
                    partial.append(full)
        except Exception:
            continue

    if exact:
        exact.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return exact[:max_candidates]

    if not partial:
        root_dir = os.path.expanduser(dir_hint) if dir_hint else os.path.expanduser("~")
        max_depth = 3 if dir_hint else 3
        if os.path.isdir(root_dir):
            for root, dirs, _files in os.walk(root_dir):
                if root[len(root_dir):].count(os.sep) >= max_depth:
                    dirs[:] = []
                dirs[:] = [d for d in dirs if not d.startswith(".") or d == ".config"]
                for d in list(dirs):
                    if base_lower in d.lower():
                        partial.append(os.path.join(root, d))
                if len(partial) > 25:
                    break

    if partial:
        seen, deduped = set(), []
        for p in partial:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        deduped.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
        return deduped[:max_candidates]

    return []


# When a search turns up multiple real candidates, we ask instead of
# silently guessing — remembered here so "open the second one" / "open
# number 2" can resolve against it.
_PENDING_SELECTION = {"kind": None, "candidates": [], "with_app": None}
_ORDINAL_WORDS = {
    "first": 1, "1st": 1, "one": 1,
    "second": 2, "2nd": 2, "two": 2,
    "third": 3, "3rd": 3, "three": 3,
    "fourth": 4, "4th": 4, "four": 4,
    "fifth": 5, "5th": 5, "five": 5,
    "sixth": 6, "6th": 6, "seventh": 7, "7th": 7, "eighth": 8, "8th": 8,
}

def _ambiguous_reply(candidates, noun="files"):
    listing = "\n".join(f"{i+1}. {p}" for i, p in enumerate(candidates))
    return (f"I found {len(candidates)} matching {noun} — which one?\n{listing}\n"
            f"Say \"open the first one\" / \"open number 2\", or give me the full path.")


def select_pending(args, _=None):
    idx = (args or {}).get("index")
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return "Which one? Give me a number, like 'open number 2'."

    candidates = _PENDING_SELECTION.get("candidates") or []
    if not candidates or idx < 1 or idx > len(candidates):
        return "That selection isn't active anymore — try the open command again."

    path     = candidates[idx - 1]
    kind     = _PENDING_SELECTION.get("kind")
    with_app = _PENDING_SELECTION.get("with_app")
    _PENDING_SELECTION.update(kind=None, candidates=[], with_app=None)

    if with_app:
        return open_in_app({"target": path, "app": with_app})
    if kind == "wallpaper":
        return wallpaper_set({"path": path})
    if kind == "folder":
        return open_folder({"path": path})
    if kind == "chmod":
        return make_executable({"path": path})
    return open_file({"path": path})


def open_file(args, _=None):
    raw_target = ((args or {}).get("path") or (args or {}).get("file")
                  or (args or {}).get("app") or "").strip()
    with_app = ((args or {}).get("with_app") or (args or {}).get("app_name") or "").strip()
    if not raw_target:
        return "No file specified."

    if raw_target.lower() in ("it", "that", "this") and _LAST_OPENED.get("path"):
        candidates = [_LAST_OPENED["path"]]
        clean_target = raw_target
    else:
        clean_target, dir_hint, app_hint = _extract_target_dir_app(raw_target)
        if app_hint and not with_app:
            with_app = app_hint
        candidates = _resolve_file_path(clean_target, dir_hint)
        if not candidates:
            where = f" in {dir_hint}" if dir_hint else (
                " in Home/Downloads/Documents/Desktop/Pictures/Videos/Music/.config, "
                "or any other mounted drive")
            return (f"Couldn't find a file matching '{clean_target}'{where}. "
                     f"Give me the full path and I'll open it.")

    if len(candidates) > 1:
        _PENDING_SELECTION.update(kind="file", candidates=candidates, with_app=with_app or None)
        return _ambiguous_reply(candidates, "files")

    path = candidates[0]

    if with_app:
        return open_in_app({"target": path, "app": with_app})

    if not shutil.which("xdg-open"):
        return "xdg-open isn't installed — install xdg-utils to open files."

    try:
        p = subprocess.Popen(["xdg-open", path],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              start_new_session=True)
    except Exception as e:
        return f"Failed to launch xdg-open: {e}"

    # xdg-open normally detaches instantly for GUI handlers; give it a beat
    # to surface an immediate "no application found" style failure.
    try:
        _, stderr = p.communicate(timeout=0.6)
        if p.returncode not in (0, None) and stderr:
            return f"Failed to open '{os.path.basename(path)}': {stderr.decode(errors='ignore').strip()}"
    except subprocess.TimeoutExpired:
        pass  # still running = normal, it launched an app

    _LAST_OPENED.update(path=path, app=None, url=None)
    return f"Opening {path}"


def open_folder(args, _=None):
    raw = ((args or {}).get("path") or (args or {}).get("app") or "").strip().strip("'\"")
    with_app = ((args or {}).get("with_app") or "").strip()
    if not raw:
        return "No folder specified."

    if raw.lower() in ("it", "that", "this") and _LAST_OPENED.get("path"):
        last = _LAST_OPENED["path"]
        candidates = [os.path.dirname(last) if os.path.isfile(last) else last]
    else:
        cleaned, dir_hint, app_hint = _extract_target_dir_app(raw)
        if app_hint and not with_app:
            with_app = app_hint
        guess = os.path.expanduser(f"~/{cleaned.strip('/').capitalize()}")
        if os.path.isdir(guess):
            candidates = [guess]
        else:
            candidates = _resolve_folder_path(cleaned, dir_hint)
        if not candidates:
            return f"Couldn't find a folder matching '{cleaned}'. Give me the full path."

    if len(candidates) > 1:
        _PENDING_SELECTION.update(kind="folder", candidates=candidates, with_app=with_app or None)
        return _ambiguous_reply(candidates, "folders")

    path = candidates[0]

    if with_app:
        binary = _resolve_app_binary(with_app)
        if not binary:
            return f"Couldn't find an installed app matching '{with_app}'."
        argv = _launch_argv(binary) + [path]
        name = _display_name(binary)
        subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, start_new_session=True)
        _LAST_OPENED.update(path=path, app=name, url=None)
        return f"Opening {path} in {name}"

    if not shutil.which("xdg-open"):
        return "xdg-open isn't installed — install xdg-utils to open folders."

    subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, start_new_session=True)
    _LAST_OPENED.update(path=path, app=None, url=None)
    return f"Opening {path}"


def open_file_by_type(args, _=None):
    """
    Handles vague requests like "open a png file" / "open the pdf" / "open an
    image from sri folder" — no specific filename given, just a type (and
    optionally a folder name). Searches for files of that type instead of
    blindly xdg-opening the literal sentence.
    """
    ext_word = (args or {}).get("ext", "").strip().lower().lstrip(".")
    folder_word = (args or {}).get("folder", "").strip()
    if not ext_word:
        return "Which file type?"

    exts = _TYPE_WORD_EXTS.get(ext_word, (ext_word,))

    search_dirs = _FILE_SEARCH_DIRS
    where_desc = "Home/Downloads/Documents/Desktop/Pictures/Videos/Music/.config"
    if folder_word:
        folder_matches = _resolve_folder_path(folder_word)
        if not folder_matches:
            return f"Couldn't find a folder matching '{folder_word}'."
        search_dirs = [folder_matches[0]]
        where_desc = folder_matches[0]

    candidates = []
    for d in search_dirs:
        d = os.path.expanduser(d)
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.listdir(d):
                full = os.path.join(d, entry)
                if not os.path.isfile(full):
                    continue
                if "." in entry and entry.lower().rsplit(".", 1)[1] in exts:
                    candidates.append(full)
        except Exception:
            continue

    if not candidates:
        return f"Couldn't find any {ext_word} files in {where_desc}. Give me a filename or path."

    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    candidates = candidates[:8]

    if len(candidates) > 1:
        _PENDING_SELECTION.update(kind="file", candidates=candidates, with_app=None)
        return _ambiguous_reply(candidates, f"{ext_word} files")

    return open_file({"path": candidates[0]})


def make_executable(args, _=None):
    raw_target = (args or {}).get("path", "").strip()
    if not raw_target:
        return "No file specified."

    if raw_target.lower() in ("it", "that", "this") and _LAST_OPENED.get("path"):
        candidates = [_LAST_OPENED["path"]]
    else:
        clean_target, dir_hint = _extract_target_and_dir(raw_target)
        expanded = os.path.expanduser(clean_target)
        if os.path.isfile(expanded):
            candidates = [os.path.abspath(expanded)]
        else:
            candidates = _resolve_file_path(clean_target, dir_hint)
        if not candidates:
            return f"Couldn't find a file matching '{raw_target}' to make executable."

    if len(candidates) > 1:
        _PENDING_SELECTION.update(kind="chmod", candidates=candidates, with_app=None)
        return _ambiguous_reply(candidates, "files")

    path = candidates[0]
    try:
        st = os.stat(path)
        os.chmod(path, st.st_mode | 0o111)
        return f"Made {path} executable (chmod +x)"
    except Exception as e:
        return f"Failed to chmod {path}: {e}"


def _resolve_single_file(raw_target):
    """Shared helper: resolve a single target to one confident file path, or
    return (None, message) for the "not found"/"ambiguous" case."""
    if raw_target.lower() in ("it", "that", "this") and _LAST_OPENED.get("path"):
        return _LAST_OPENED["path"], None
    clean_target, dir_hint = _extract_target_and_dir(raw_target)
    expanded = os.path.expanduser(clean_target)
    if os.path.isfile(expanded):
        return os.path.abspath(expanded), None
    candidates = _resolve_file_path(clean_target, dir_hint)
    if not candidates:
        return None, f"Couldn't find a file matching '{clean_target}'."
    if len(candidates) > 1:
        _PENDING_SELECTION.update(kind="file", candidates=candidates, with_app=None)
        return None, _ambiguous_reply(candidates, "files")
    return candidates[0], None


def copy_file(args, _=None):
    src_raw = (args or {}).get("path", "").strip()
    dest_raw = (args or {}).get("destination", "").strip()
    if not src_raw or not dest_raw:
        return "Need both a source file and a destination."

    src, err = _resolve_single_file(src_raw)
    if err:
        return err

    dest_dir = _DIR_SHORTCUTS.get(dest_raw.lower())
    dest = os.path.expanduser(dest_dir) if dest_dir else os.path.expanduser(dest_raw)
    if os.path.isdir(dest):
        dest = os.path.join(dest, os.path.basename(src))

    try:
        shutil.copy2(src, dest)
        return f"Copied {src} -> {dest}"
    except Exception as e:
        return f"Failed to copy: {e}"


def move_file(args, _=None):
    src_raw = (args or {}).get("path", "").strip()
    dest_raw = (args or {}).get("destination", "").strip()
    if not src_raw or not dest_raw:
        return "Need both a source file and a destination."

    src, err = _resolve_single_file(src_raw)
    if err:
        return err

    dest_dir = _DIR_SHORTCUTS.get(dest_raw.lower())
    dest = os.path.expanduser(dest_dir) if dest_dir else os.path.expanduser(dest_raw)
    if os.path.isdir(dest):
        dest = os.path.join(dest, os.path.basename(src))

    try:
        shutil.move(src, dest)
        if _LAST_OPENED.get("path") == src:
            _LAST_OPENED.update(path=dest)
        return f"Moved {src} -> {dest}"
    except Exception as e:
        return f"Failed to move: {e}"


def rename_file(args, _=None):
    src_raw = (args or {}).get("path", "").strip()
    new_name = (args or {}).get("new_name", "").strip()
    if not src_raw or not new_name:
        return "Need both the file and its new name."

    src, err = _resolve_single_file(src_raw)
    if err:
        return err

    dest = os.path.join(os.path.dirname(src), new_name)
    try:
        os.rename(src, dest)
        if _LAST_OPENED.get("path") == src:
            _LAST_OPENED.update(path=dest)
        return f"Renamed {os.path.basename(src)} -> {new_name}"
    except Exception as e:
        return f"Failed to rename: {e}"


def create_folder(args, _=None):
    """Create a directory — handles natural phrasing like
    'create a folder named mine in my downloads' or
    'create a folder in my downloads name that as mine'."""
    name_raw = (args or {}).get("name", "").strip().strip("'\"")
    where_raw = (args or {}).get("location", "").strip().strip("'\"")

    if not name_raw:
        return "What should the folder be called?"

    # Handle "name it/that as X" / "name that as X" / "call it X" embedded
    # anywhere inside the name string — the intent regex may have captured the
    # whole clause rather than just the folder name, e.g.:
    #   "in my downloads name that as mine" -> name="mine", location="downloads"
    _name_clause_re = re.compile(
        r"(?:^|\s)(?:name|call|title)\s+(?:it|that|this)\s+(?:as\s+)?(.+)", re.IGNORECASE)
    _in_location_re = re.compile(
        r"\s+(?:in|at|under|inside)\s+(?:my\s+)?(\w+)\s*$", re.IGNORECASE)

    m_name = _name_clause_re.search(name_raw)
    if m_name:
        # extract the location from what precedes the "name it as" clause
        prefix = name_raw[:m_name.start()].strip()
        m_loc = _in_location_re.search(prefix)
        if m_loc and not where_raw:
            where_raw = m_loc.group(1)
            prefix = prefix[:m_loc.start()].strip()
        name_raw = m_name.group(1).strip().strip("'\"")
    else:
        m_loc = _in_location_re.search(name_raw)
        if m_loc and not where_raw:
            where_raw = m_loc.group(1)
            name_raw = name_raw[:m_loc.start()].strip().strip("'\"")

    if not name_raw:
        return "What should the folder be called?"

    # Resolve destination directory
    if where_raw:
        where_lower = re.sub(r"^my\s+", "", where_raw.lower().strip())
        base_dir = _DIR_SHORTCUTS.get(where_lower)
        if not base_dir:
            expanded = os.path.expanduser(where_raw)
            base_dir = expanded if os.path.isdir(expanded) else os.path.expanduser("~")
        base_dir = os.path.expanduser(base_dir)
    else:
        base_dir = os.path.expanduser("~")

    full_path = os.path.join(base_dir, name_raw)
    if os.path.exists(full_path):
        return f"'{full_path}' already exists."

    try:
        os.makedirs(full_path, exist_ok=True)
        _LAST_OPENED.update(path=full_path, app=None, url=None)
        return f"Created folder: {full_path}"
    except Exception as e:
        return f"Failed to create folder: {e}"


def create_file(args, _=None):
    """Create an empty file (or with content) at a given path."""
    name_raw = (args or {}).get("name", "").strip().strip("'\"")
    where_raw = (args or {}).get("location", "").strip().strip("'\"")
    content   = (args or {}).get("content", "")

    if not name_raw:
        return "What should the file be called?"

    if where_raw:
        where_lower = where_raw.lower()
        base_dir = _DIR_SHORTCUTS.get(where_lower)
        if not base_dir:
            expanded = os.path.expanduser(where_raw)
            base_dir = expanded if os.path.isdir(expanded) else os.path.expanduser("~")
        base_dir = os.path.expanduser(base_dir)
    else:
        base_dir = os.path.expanduser("~")

    full_path = os.path.join(base_dir, name_raw)
    if os.path.exists(full_path):
        return f"'{full_path}' already exists."

    try:
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            if content:
                f.write(content)
        _LAST_OPENED.update(path=full_path, app=None, url=None)
        return f"Created file: {full_path}"
    except Exception as e:
        return f"Failed to create file: {e}"


def list_folder(args, _=None):
    """List contents of a directory with basic stats."""
    raw = (args or {}).get("path", "").strip() or "~"
    shortcut = _DIR_SHORTCUTS.get(raw.lower())
    if shortcut:
        path = os.path.expanduser(shortcut)
    else:
        path = os.path.expanduser(raw)

    if not os.path.isdir(path):
        folder_matches = _resolve_folder_path(raw)
        if not folder_matches:
            return f"Couldn't find a folder matching '{raw}'."
        path = folder_matches[0]

    try:
        entries = sorted(os.listdir(path))
        if not entries:
            return f"{path} is empty."
        lines = []
        for e in entries[:50]:
            full = os.path.join(path, e)
            kind = "📁" if os.path.isdir(full) else "📄"
            try:
                size = os.path.getsize(full)
                size_str = f"{size:,} B" if size < 1024 else (
                    f"{size//1024:,} KB" if size < 1024**2 else f"{size//1024**2:,} MB")
            except Exception:
                size_str = "?"
            lines.append(f"{kind} {e}  ({size_str})")
        suffix = f"\n...and {len(entries)-50} more" if len(entries) > 50 else ""
        return f"📂 {path}  ({len(entries)} items)\n" + "\n".join(lines) + suffix
    except Exception as e:
        return f"Failed to list {path}: {e}"


def disk_usage(args, _=None):
    """Show disk usage for a path or the whole system."""
    raw = (args or {}).get("path", "/")
    path = os.path.expanduser(raw) if raw != "/" else "/"
    out = _run(f"df -h '{path}'")
    if not out.strip():
        return "Couldn't get disk usage."
    # Also show large dirs under home
    home = os.path.expanduser("~")
    du_home = _run(f"du -sh {home}/* 2>/dev/null | sort -rh | head -10")
    return out + (f"\n\nLargest items in ~:\n{du_home}" if du_home else "")


def find_files(args, _=None):
    """Search for files by name pattern across the system."""
    pattern = (args or {}).get("pattern", "").strip()
    where   = (args or {}).get("location", "~").strip()
    if not pattern:
        return "What pattern should I search for?"

    base = os.path.expanduser(_DIR_SHORTCUTS.get(where.lower(), where))
    if not os.path.isdir(base):
        base = os.path.expanduser("~")

    results = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if pattern.lower() in f.lower():
                results.append(os.path.join(root, f))
        if len(results) >= 20:
            break

    if not results:
        return f"No files matching '{pattern}' found under {base}."
    return f"Found {len(results)} file(s):\n" + "\n".join(results[:20])


def show_file_info(args, _=None):
    """Show file metadata: size, type, permissions, modified time."""
    raw = (args or {}).get("path", "").strip()
    if not raw:
        return "Which file?"

    if raw.lower() in ("it", "that", "this") and _LAST_OPENED.get("path"):
        path = _LAST_OPENED["path"]
    else:
        candidates = _resolve_file_path(raw)
        if not candidates:
            return f"Couldn't find '{raw}'."
        path = candidates[0]

    try:
        st = os.stat(path)
        import stat as _stat, datetime as _dt
        size = st.st_size
        size_str = (f"{size:,} B" if size < 1024 else
                    f"{size//1024:,} KB" if size < 1024**2 else
                    f"{size//1024**2:,} MB")
        perms = oct(st.st_mode)[-3:]
        mtime = _dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        kind  = "directory" if os.path.isdir(path) else "file"
        mime  = _run(f"file --brief --mime-type '{path}'")
        return (f"📄 {path}\nType: {kind} ({mime.strip()})\nSize: {size_str}\n"
                f"Permissions: {perms}\nModified: {mtime}")
    except Exception as e:
        return f"Failed to stat {path}: {e}"


def open_in_app(args, _=None):
    """
    "open <file> in <app>" — e.g. "open resume.pdf in vscode", or with pronoun
    resolution, "open it in visualstudiocode" (uses the last file/folder we
    touched). Also handles the reverse phrasing "open youtube in it" (target
    is the site/app, "it" means "the last app/browser") by delegating to
    smart_open/open_app rather than treating "it" as a file.
    """
    target = (args or {}).get("target", "").strip()
    app    = (args or {}).get("app", "").strip()
    if not target or not app:
        return "Need both what to open and which app to open it with."

    tl, al = target.lower(), app.lower()

    # Guards against a common misparse: "open a file named jarvis in my
    # downloads" can get split as target="a file named jarvis", app="my
    # downloads" by a generic "X in Y" pattern. "my downloads" is a
    # directory, not an app — reroute through the real sentence instead of
    # failing on a fake app name.
    al_bare = re.sub(r"^(?:my|the)\s+", "", al).strip()
    if al_bare in _DIR_SHORTCUTS:
        return smart_open({"target": f"{target} in {app}"})

    # Strip "website named", "site called", "webpage", etc. filler phrases
    # from the target so "a website named google" -> "google".
    _SITE_FILLER_RE = re.compile(
        r"^(?:a\s+|the\s+)?(?:website|site|url|webpage|web page|page)"
        r"(?:\s+(?:named|called|at|of))?\s*", re.IGNORECASE)
    tl_clean = _SITE_FILLER_RE.sub("", tl).strip()
    target_clean = _SITE_FILLER_RE.sub("", target).strip()

    # If the cleaned target is a known site or URL, open it in the named browser
    site = _WEBSITE_MAP.get(tl_clean)
    is_url = tl_clean.startswith(("http://", "https://", "www."))
    if site or is_url:
        url = target_clean if is_url else site
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        binary = _resolve_app_binary(app)
        if not binary:
            binary = _find_binary(_BROWSERS)
        if binary:
            argv = _launch_argv(binary) + [url]
            name = _display_name(binary)
            import subprocess as _sp
            _sp.Popen(argv, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, start_new_session=True)
            _LAST_OPENED.update(app=name, path=None, url=url)
            return f"Opening {url} in {name}"
    # If target looks like a website description but no match found, web-search it
    if tl_clean and not os.path.sep in tl_clean and " " not in tl_clean:
        # single word not in our map - try as a domain
        url = f"https://{tl_clean}.com" if "." not in tl_clean else f"https://{tl_clean}"
        binary = _resolve_app_binary(app) or _find_binary(_BROWSERS)
        if binary:
            argv = _launch_argv(binary) + [url]
            name = _display_name(binary)
            import subprocess as _sp
            _sp.Popen(argv, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, start_new_session=True)
            _LAST_OPENED.update(app=name, path=None, url=url)
            return f"Opening {url} in {name}"
    # Use cleaned target for subsequent file resolution
    if target_clean and target_clean != target:
        target = target_clean
        tl = tl_clean

    # "open <site/app> in it" -> "it" = last app/browser, not a file
    if al in ("it", "that", "this"):
        return smart_open({"target": f"{target} in it"})

    # "open <website> in <browser>" — e.g. "open youtube in firefox", "open
    # youtube in chrome". This lets the person pick a SPECIFIC browser rather
    # than whichever one open_app would auto-select (last-used/first-found).
    site = _WEBSITE_MAP.get(tl)
    is_url = tl.startswith(("http://", "https://", "www."))
    if site or is_url:
        url = target if is_url else site
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        binary = _resolve_app_binary(app)
        if not binary:
            return f"Couldn't find an installed app matching '{app}'."
        argv = _launch_argv(binary) + [url]
        name = _display_name(binary)
        try:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception as e:
            return f"Failed to launch {name}: {e}"
        _LAST_OPENED.update(app=name, path=None, url=url)
        return f"Opening {url} in {name}"

    # "open it in <app>" -> "it" = last opened file/folder
    if tl in ("it", "that", "this", "the file", "the folder"):
        if not _LAST_OPENED.get("path"):
            return "I don't have a previous file to reference — tell me the filename."
        path = _LAST_OPENED["path"]
    else:
        expanded = os.path.expanduser(target)
        if os.path.exists(expanded):
            path = os.path.abspath(expanded)
        else:
            clean_target, dir_hint = _extract_target_and_dir(target)
            candidates = _resolve_file_path(clean_target, dir_hint)
            if not candidates:
                return f"Couldn't find a file matching '{target}'."
            if len(candidates) > 1:
                _PENDING_SELECTION.update(kind="file", candidates=candidates, with_app=app)
                return _ambiguous_reply(candidates, "files")
            path = candidates[0]

    binary = _resolve_app_binary(app)
    if not binary:
        return f"Couldn't find an installed app matching '{app}'."

    argv = _launch_argv(binary) + [path]
    name = _display_name(binary)
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        return f"Failed to launch {name}: {e}"

    _LAST_OPENED.update(path=path, app=name, url=None)
    return f"Opening {path} in {name}"


def close_file(args, _=None):
    """Best-effort: close whatever window has this file open, by title match."""
    target = (args or {}).get("path", "").strip()
    if not target:
        return "No file specified."

    if target.lower() in ("it", "that", "this"):
        if _LAST_OPENED.get("path"):
            target = _LAST_OPENED["path"]
        elif _LAST_OPENED.get("url") and _LAST_OPENED.get("app"):
            # last thing opened was a website, not a file — closing "that"
            # means closing the browser window that had it open.
            return close_app({"app": _LAST_OPENED["app"]})
        else:
            return "I don't have a previous file to reference — tell me the filename."

    base = os.path.basename(target)
    if len(base) < 3:
        # Too short/generic to safely substring-match against arbitrary
        # window titles (would risk closing an unrelated window whose title
        # just happens to contain the same short text).
        return f"'{base}' is too generic to safely match a window — give me more of the filename."

    wins = _all_windows()
    for w in wins:
        title = w.get("title", "")
        if base.lower() in title.lower():
            addr = w.get("address")
            _run(f"hyprctl dispatch closewindow address:{addr}")
            return f"Closed the window showing {base}"
    return f"Couldn't find an open window for '{base}'."


def delete_file(args, confirm_fn=None):
    target = (args or {}).get("path", "").strip()
    if not target:
        return "No file specified."
    if target.lower() in ("it", "that", "this") and _LAST_OPENED.get("path"):
        candidates = [_LAST_OPENED["path"]]
    else:
        clean_target, dir_hint = _extract_target_and_dir(target)
        candidates = _resolve_file_path(clean_target, dir_hint)
        if not candidates:
            return f"Couldn't find a file matching '{clean_target}' to delete."

    if len(candidates) > 1:
        _PENDING_SELECTION.update(kind="file", candidates=candidates, with_app=None)
        return _ambiguous_reply(candidates, "files") + "\n(I won't delete anything until you pick one.)"

    path = candidates[0]

    if confirm_fn and not confirm_fn(f"Delete {path}? This moves it to trash if possible."):
        return "Cancelled."

    try:
        if shutil.which("gio"):
            subprocess.run(["gio", "trash", path], check=True, timeout=10)
            return f"Moved {path} to trash"
        if shutil.which("trash-put"):
            subprocess.run(["trash-put", path], check=True, timeout=10)
            return f"Moved {path} to trash"
        os.remove(path)
        return f"Deleted {path} (no trash utility found — this was permanent)"
    except Exception as e:
        return f"Failed to delete {path}: {e}"


def edit_file(args, _=None):
    target = (args or {}).get("path", "").strip()
    if not target:
        return "No file specified."
    if target.lower() in ("it", "that", "this") and _LAST_OPENED.get("path"):
        candidates = [_LAST_OPENED["path"]]
    else:
        clean_target, dir_hint = _extract_target_and_dir(target)
        candidates = _resolve_file_path(clean_target, dir_hint)
        if not candidates:
            return f"Couldn't find a file matching '{clean_target}' to edit."

    if len(candidates) > 1:
        _PENDING_SELECTION.update(kind="file", candidates=candidates,
                                   with_app="code")  # editor picked below is used on selection too
        return _ambiguous_reply(candidates, "files")

    path = candidates[0]

    editor = _resolve_app_binary("code") or _find_binary(
        ["code", "gedit", "kate", "mousepad", "leafpad", "nano"])
    if not editor:
        return open_file({"path": path})  # fall back to the default handler

    argv = _launch_argv(editor) + [path]
    name = _display_name(editor)
    subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, start_new_session=True)
    _LAST_OPENED.update(path=path, app=name, url=None)
    return f"Opening {path} in {name} for editing"


_FILE_EXT_RE = re.compile(r"\.([a-zA-Z0-9]{1,5})$")
_URL_TLDS = {"com","org","net","io","co","dev","app","gg","tv","ai","edu","gov","me","xyz"}

def smart_open_vague(args, _=None):
    """
    Catches messier vague file requests that the stricter type-only pattern
    misses — extra words ("any one of the..."), or a custom (non-shortcut)
    folder name, in any order: "open any one of the image from sri folder",
    "from sri folder open a image". Extracts a folder-name hint (if any) and
    a recognized file-type word from anywhere in the sentence; falls back to
    normal smart_open handling if no type word is found.
    """
    text = (args or {}).get("text", "").strip()
    if not text:
        return "What would you like to open?"

    folder_word, remainder = _extract_folder_word(text)

    words = re.findall(r"[a-zA-Z0-9]+", remainder.lower())
    ext_word = None
    for w in words:
        if w in _TYPE_WORD_EXTS:
            ext_word = w
            break
    if not ext_word:
        for w in words:
            if w in ("png", "jpg", "jpeg", "pdf", "docx", "txt", "mp4", "mp3", "gif", "webp"):
                ext_word = w
                break

    if not ext_word:
        return smart_open({"target": remainder})

    return open_file_by_type({"ext": ext_word, "folder": folder_word or ""})


def smart_open(args, _=None):
    """
    Router for the bare "open X" phrase. Keeps app/website launches exactly
    as before. For anything else, tries in order: an installed app, a folder
    fuzzy-matched by name, then a file fuzzy-matched by name — instead of
    falling straight to open_app's raw xdg-open-on-literal-text fallback.
    """
    raw_target = (args or {}).get("target", "").strip()
    if not raw_target:
        return "Nothing to open."

    # Strip trailing noise words so "open firefox please" -> "open firefox",
    # "open discord app" -> "open discord", "open github website" -> "open github"
    _TNR = re.compile(
        r"\s+(?:please|now|quickly|app|application|program|software|"
        r"website|site|page|browser|tool|utility|bro|man|buddy|ok|okay)\s*$",
        re.IGNORECASE)
    raw_target = _TNR.sub("", raw_target).strip()

    if raw_target.lower() in ("it", "that", "this"):
        if _LAST_OPENED.get("url"):
            return open_app({"app": _LAST_OPENED["url"]})
        if _LAST_OPENED.get("path"):
            path = _LAST_OPENED["path"]
            return open_folder({"path": path}) if os.path.isdir(path) else open_file({"path": path})
        return "I don't have anything previous to reopen — tell me what you'd like to open."

    low = raw_target.lower()

    if low.startswith(("http://", "https://", "www.")):
        return open_app({"app": raw_target})

    first_word = low.split()[0] if low.split() else low
    if first_word in _WEBSITE_MAP or first_word in _BROWSERS or first_word in (
        "firefox", "terminal", "term", "console", "files", "manager", "filemanager"
    ):
        return open_app({"app": raw_target})

    m = _FILE_EXT_RE.search(raw_target)
    if m:
        ext = m.group(1).lower()
        if ext in _URL_TLDS and "/" not in raw_target and " " not in raw_target:
            return open_app({"app": raw_target})   # e.g. "open netflix.com"
        return open_file({"path": raw_target})     # e.g. "open report.pdf"

    # Strip filler and pull out any "in <dir>" hint before treating the rest
    # as a search term — "open a file named v12 in downloads" should search
    # for "v12" in ~/Downloads, not fail outright on the whole sentence.
    target, dir_hint = _extract_target_and_dir(raw_target)

    # A real installed app takes priority (matches previous behavior for
    # "open discord", "open spotify", etc.)
    binary = _resolve_app_binary(target)
    if binary:
        return open_app({"app": target})

    # Then try a folder by name...
    if _resolve_folder_path(target, dir_hint):
        return open_folder({"path": raw_target})

    # ...then a file by name.
    if _resolve_file_path(target, dir_hint):
        return open_file({"path": raw_target})

    return open_app({"app": target})   # will surface a clean "not found" message


# ── Theme presets ────────────────────────────────────────────────────────────

def apply_preset(args, confirm_fn=None):
    """
    Apply a named desktop preset: minimal|gaming|macos|focus|battery|futuristic|programming
    Modifies rounding, gaps, blur, shadow, animations, opacity, layout to match the vibe.
    """
    preset = (args or {}).get("preset","minimal").lower().strip()

    PRESETS = {
        "minimal": {
            "decoration.rounding": "4",
            "general.gaps_in": "2", "general.gaps_out": "4",
            "general.border_size": "1",
            "decoration.blur.enabled": "false",
            "decoration.shadow.enabled": "false",
            "decoration.active_opacity": "1.0",
            "decoration.inactive_opacity": "1.0",
            "animations.enabled": "no",
        },
        "gaming": {
            "decoration.rounding": "0",
            "general.gaps_in": "0", "general.gaps_out": "0",
            "general.border_size": "0",
            "decoration.blur.enabled": "false",
            "decoration.shadow.enabled": "false",
            "animations.enabled": "no",
            "misc.vrr": "1",
        },
        "macos": {
            "decoration.rounding": "12",
            "general.gaps_in": "4", "general.gaps_out": "10",
            "general.border_size": "1",
            "decoration.blur.enabled": "true", "decoration.blur.size": "8",
            "decoration.blur.passes": "3",
            "decoration.shadow.enabled": "true",
            "decoration.active_opacity": "1.0",
            "decoration.inactive_opacity": "0.95",
            "general.layout": "master",
        },
        "futuristic": {
            "decoration.rounding": "16",
            "general.gaps_in": "6", "general.gaps_out": "12",
            "general.border_size": "2",
            "decoration.blur.enabled": "true", "decoration.blur.size": "12",
            "decoration.blur.passes": "4",
            "decoration.shadow.enabled": "true", "decoration.shadow.range": "20",
            "decoration.active_opacity": "0.95",
            "decoration.inactive_opacity": "0.85",
        },
        "focus": {
            "decoration.rounding": "8",
            "general.gaps_in": "8", "general.gaps_out": "16",
            "general.border_size": "2",
            "decoration.blur.enabled": "true",
            "decoration.dim_inactive": "true", "decoration.dim_strength": "0.4",
            "decoration.active_opacity": "1.0",
            "decoration.inactive_opacity": "0.8",
        },
        "battery": {
            "decoration.rounding": "4",
            "general.gaps_in": "2", "general.gaps_out": "4",
            "decoration.blur.enabled": "false",
            "decoration.shadow.enabled": "false",
            "animations.enabled": "no",
            "misc.vrr": "1", "misc.vfr": "true",
        },
        "programming": {
            "decoration.rounding": "6",
            "general.gaps_in": "4", "general.gaps_out": "8",
            "general.border_size": "1",
            "decoration.blur.enabled": "true", "decoration.blur.size": "4",
            "decoration.dim_inactive": "true", "decoration.dim_strength": "0.2",
            "decoration.active_opacity": "1.0",
            "decoration.inactive_opacity": "0.9",
            "general.layout": "dwindle",
        },
    }

    if preset not in PRESETS:
        return f"Unknown preset '{preset}'. Available: {', '.join(PRESETS.keys())}"

    cfg = PRESETS[preset]
    results = [f"Applying preset: {preset.upper()}"]

    from . import hypr_config
    for dotkey, value in cfg.items():
        # dotkey like "decoration.blur.enabled" or "general.gaps_in"
        parts = dotkey.split(".")
        if len(parts) == 2:
            section, key = parts
            fkey = "decorations" if section in ("decoration","general") else (
                   "system" if section in ("misc","input") else
                   "animations" if section == "animations" else "settings")
            hypr_config.set_value(section, key, value, fkey, instant=True)
            results.append(f"  {dotkey} = {value}")
        elif len(parts) == 3:
            outer, inner, key = parts
            # handle decoration.blur.enabled etc
            if inner == "blur":
                if key == "enabled":
                    hypr_config.set_blur(enabled=(value.lower() in ("true","yes","1")))
                elif key == "size":
                    hypr_config.set_blur(size=int(value))
                elif key == "passes":
                    hypr_config.set_blur(passes=int(value))
            elif inner == "shadow":
                if key == "enabled":
                    hypr_config.set_shadow(enabled=(value.lower() in ("true","yes","1")))
                elif key == "range":
                    hypr_config.set_shadow(rang=int(value))
            else:
                hypr_config.set_value(inner, key, value, "decorations")
            results.append(f"  {dotkey} = {value}")

    r = hypr_config._reload()
    results.append(f"\nReload: {r}")
    return "\n".join(results)


# ── Register all new tools ───────────────────────────────────────────────────

REGISTRY.update({
    # workspace
    "workspace_go":           workspace_go,
    "workspace_move_window":  workspace_move_window,
    "workspace_move_here":    workspace_move_here,
    "workspace_move_all":     workspace_move_all,
    "workspace_move_matching": workspace_move_matching,
    "workspace_list":         workspace_list,
    # window
    "window_float":           window_float,
    "window_fullscreen":      window_fullscreen,
    "window_kill_active":     window_kill_active,
    "window_focus":           window_focus,
    "window_move":            window_move,
    "window_resize":          window_resize,
    "window_center":          window_center,
    "window_pin":             window_pin,
    # audio
    "audio_volume":           audio_volume,
    "audio_mute":             audio_mute,
    "audio_mic_mute":         audio_mic_mute,
    "audio_get_volume":       audio_get_volume,
    "audio_player":           audio_player,
    "audio_status":           audio_status,
    # brightness
    "brightness_set":         brightness_set,
    "brightness_get":         brightness_get,
    # screenshot / recording
    "screenshot":             screenshot,
    "screen_record_start":    screen_record_start,
    "screen_record_stop":     screen_record_stop,
    # system
    "system_info":            system_info,
    "process_list":           process_list,
    "process_kill":           process_kill,
    "network_info":           network_info,
    "battery_status":         battery_status,
    # power
    "power_shutdown":         power_shutdown,
    "power_reboot":           power_reboot,
    "power_suspend":          power_suspend,
    "power_hibernate":        power_hibernate,
    # bluetooth
    "bluetooth_toggle":       bluetooth_toggle,
    "bluetooth_list":         bluetooth_list,
    "bluetooth_connect":      bluetooth_connect,
    "bluetooth_disconnect":   bluetooth_disconnect,
    # wifi
    "wifi_toggle":            wifi_toggle,
    "wifi_list":              wifi_list,
    "wifi_connect":           wifi_connect,
    # clipboard
    "clipboard_set":          clipboard_set,
    "clipboard_get":          clipboard_get,
    "clipboard_history":      clipboard_history,
    # notifications
    "notify_send":            notify_send,
    "notify_clear":           notify_clear,
    # preferences
    "prefs_set":              prefs_set,
    "prefs_get":              prefs_get,
    "prefs_set_name":         prefs_set_name,
    "prefs_note":             prefs_note,
    "prefs_list_notes":       prefs_list_notes,
    # system status
    "system_status":          system_status,
    "system_info_brief":      system_info_brief,
    # packages
    "pkg_install":            pkg_install,
    "pkg_remove":             pkg_remove,
    "pkg_search":             pkg_search,
    "pkg_update":             pkg_update,
    "pkg_list_installed":     pkg_list_installed,
    # services
    "service_status":         service_status,
    "service_start":          service_start,
    "service_stop":           service_stop,
    "service_restart":        service_restart,
    "service_enable":         service_enable,
    "service_disable":        service_disable,
    "service_list":           service_list,
    # wallpaper
    "wallpaper_set":          wallpaper_set,
    "wallpaper_random":       wallpaper_random,
    "wallpaper_select":       wallpaper_select,
    # display
    "night_mode":             night_mode,
    "lock_screen":            lock_screen,
    "logout":                 logout,
    # apps
    "open_app":               open_app,
    "open_file":              open_file,
    "open_folder":            open_folder,
    "open_in_app":            open_in_app,
    "close_app":              close_app,
    "close_file":             close_file,
    "delete_file":            delete_file,
    "edit_file":              edit_file,
    "copy_file":              copy_file,
    "move_file":              move_file,
    "rename_file":            rename_file,
    "create_folder":          create_folder,
    "create_file":            create_file,
    "list_folder":            list_folder,
    "disk_usage":             disk_usage,
    "find_files":             find_files,
    "show_file_info":         show_file_info,
    "select_pending":         select_pending,
    "make_executable":        make_executable,
    "open_file_by_type":      open_file_by_type,
    "smart_open_vague":       smart_open_vague,
    # presets
    "apply_preset":           apply_preset,
})

WRITE_TOOLS.update({
    "audio_volume","audio_mute","audio_mic_mute",
    "brightness_set","wallpaper_set","wallpaper_random",
    "night_mode","lock_screen","logout",
    "process_kill","close_app","close_window",
    "apply_preset","workspace_go","workspace_move_window",
    "window_float","window_fullscreen","window_kill_active",
    "window_move","window_resize","window_center","window_pin",
})
