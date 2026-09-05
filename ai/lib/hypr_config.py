"""
hypr_config.py — JARVIS Hyprland config engine.
Built from the user's actual ~/.config/hypr/ structure (JaKooLit dotfiles).

FILE MAP (exact paths, no guessing):
  UserDecorations.conf  — general{} + decoration{} + group{}
  UserAnimations.conf   — animations{}
  UserKeybinds.conf     — user keybinds (ONLY file to add binds to)
  UserSettings.conf     — misc user hyprland settings
  ENVariables.conf      — env = KEY,VALUE
  01-UserDefaults.conf  — $term $files $edit variables
  WindowRules.conf      — windowrulev2 user rules
  WorkSpaceRules.conf   — workspace rules
  Startup_Apps.conf     — exec-once user apps
  monitors.conf         — monitor = lines (nwg-displays managed)
  workspaces.conf       — workspace rules (nwg-displays managed)
  configs/SystemSettings.conf — input{} misc{} dwindle{} master{} etc
  configs/Keybinds.conf       — default keybinds (READ-ONLY, use UserKeybinds)
  animations/*.conf     — animation preset files
  scripts/*.sh          — scripts invoked by keybinds
"""

import os, re, shutil, datetime, subprocess, json

HYPR      = os.path.expanduser("~/.config/hypr")
UCFG      = os.path.join(HYPR, "UserConfigs")
SCRIPTS   = os.path.join(HYPR, "scripts")
USCRIPTS  = os.path.join(HYPR, "UserScripts")
ANIMS_DIR = os.path.join(HYPR, "animations")

# ── Exact file paths from hyprland.conf source= lines ────────────────────
F = {
    "decorations":   os.path.join(UCFG, "UserDecorations.conf"),
    "animations":    os.path.join(UCFG, "UserAnimations.conf"),
    "keybinds":      os.path.join(UCFG, "UserKeybinds.conf"),
    "settings":      os.path.join(UCFG, "UserSettings.conf"),
    "env":           os.path.join(UCFG, "ENVariables.conf"),
    "defaults":      os.path.join(UCFG, "01-UserDefaults.conf"),
    "rules":         os.path.join(UCFG, "WindowRules.conf"),
    "workspace_rules": os.path.join(UCFG, "WorkSpaceRules.conf"),
    "startup":       os.path.join(UCFG, "Startup_Apps.conf"),
    "monitors":      os.path.join(HYPR, "monitors.conf"),
    "workspaces":    os.path.join(HYPR, "workspaces.conf"),
    "system":        os.path.join(HYPR, "configs", "SystemSettings.conf"),
    "keybinds_default": os.path.join(HYPR, "configs", "Keybinds.conf"),
    "main":          os.path.join(HYPR, "hyprland.conf"),
    "hypridle":      os.path.join(HYPR, "hypridle.conf"),
    "hyprlock":      os.path.join(HYPR, "hyprlock.conf"),
}

# ── What setting lives in which file ─────────────────────────────────────
SETTING_FILE = {
    # UserDecorations.conf
    "rounding":           "decorations",
    "active_opacity":     "decorations",
    "inactive_opacity":   "decorations",
    "fullscreen_opacity": "decorations",
    "dim_inactive":       "decorations",
    "dim_strength":       "decorations",
    "dim_special":        "decorations",
    "border_size":        "decorations",
    "gaps_in":            "decorations",
    "gaps_out":           "decorations",
    "col.active_border":  "decorations",
    "col.inactive_border":"decorations",
    "blur":               "decorations",
    "blur_enabled":       "decorations",
    "blur_size":          "decorations",
    "blur_passes":        "decorations",
    "shadow":             "decorations",
    "shadow_enabled":     "decorations",
    "shadow_range":       "decorations",
    "drop_shadow":        "decorations",
    # configs/SystemSettings.conf
    "layout":             "system",
    "kb_layout":          "system",
    "sensitivity":        "system",
    "natural_scroll":     "system",
    "numlock_by_default": "system",
    "repeat_rate":        "system",
    "repeat_delay":       "system",
    "vrr":                "system",
    "vfr":                "system",
    "enable_swallow":     "system",
    "swallow_regex":      "system",
    "pseudotile":         "system",
    "preserve_split":     "system",
    "mfact":              "system",
    # UserAnimations.conf
    "animations_enabled": "animations",
}


def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return str(e)


def _backup(path):
    ts  = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{path}.{ts}.bak"
    try:
        shutil.copy2(path, bak)
    except Exception:
        pass
    return bak


def _reload():
    r = _run("hyprctl reload")
    return r if r else "reloaded"


def _keyword(key, value):
    r = _run(f"hyprctl keyword {key} {value}")
    return r if r else "applied"


def read_file(key):
    path = F.get(key, key)
    if not os.path.isfile(path):
        # try as literal path
        if os.path.isfile(key):
            path = key
        else:
            return f"File not found: {key} (tried {path})"
    with open(path) as f:
        return f.read()


# ── Block-aware value setter ───────────────────────────────────────────────
def _set_in_file(path, section, key, value):
    """
    Set key=value inside section{} block.
    Handles nested blocks like blur{} inside decoration{}.
    If section="", does top-level replacement.
    Returns (changed_lines, result_msg).
    """
    with open(path) as f:
        lines = f.readlines()

    new_val_line = f"{key} = {value}"

    # ── Nested section: e.g. section="decoration", key="blur.enabled"
    if "." in key:
        outer_key, inner_key = key.split(".", 1)
        # find outer block, then inner block inside it, then set inner_key
        return _set_nested(lines, path, section, outer_key, inner_key, value)

    # ── Top-level (section="")
    if not section:
        for i, ln in enumerate(lines):
            s = ln.strip()
            if s.startswith("#"):
                continue
            if re.match(rf'^\s*{re.escape(key)}\s*=', ln):
                lines[i] = re.sub(rf'(^\s*{re.escape(key)}\s*=\s*).*', rf'\g<1>{value}', ln)
                if not lines[i].endswith("\n"):
                    lines[i] += "\n"
                with open(path, "w") as f: f.writelines(lines)
                return lines, f"Updated: {key} = {value}"
        lines.append(f"{key} = {value}\n")
        with open(path, "w") as f: f.writelines(lines)
        return lines, f"Appended: {key} = {value}"

    # ── Inside a named section block
    in_block  = False
    depth     = 0
    found     = False
    block_end = None

    for i, ln in enumerate(lines):
        s = ln.strip()
        if not in_block:
            # match "section {" or "section{" or just "section" followed by "{"
            if re.match(rf'^\s*{re.escape(section)}\s*\{{', ln, re.IGNORECASE):
                in_block = True
                depth    = ln.count("{") - ln.count("}")
                continue
        else:
            depth += ln.count("{") - ln.count("}")
            if depth <= 0:
                block_end = i
                break
            # replace if key found
            if not s.startswith("#") and re.match(rf'^\s*{re.escape(key)}\s*=', ln):
                indent = len(ln) - len(ln.lstrip())
                lines[i] = " " * indent + f"{key} = {value}\n"
                found = True

    if in_block and not found:
        if block_end is not None:
            lines.insert(block_end, f"  {key} = {value}\n")
        else:
            lines.append(f"  {key} = {value}\n")
    elif not in_block:
        # section not found — append it
        lines.append(f"\n{section} {{\n  {key} = {value}\n}}\n")

    with open(path, "w") as f: f.writelines(lines)
    return lines, f"Set {section}.{key} = {value}"


def _set_nested(lines, path, outer_section, inner_section, key, value):
    """Set key inside outer_section { inner_section { key = value } }"""
    in_outer  = False
    in_inner  = False
    outer_d   = 0
    inner_d   = 0
    found     = False
    inner_end = None

    for i, ln in enumerate(lines):
        s = ln.strip()
        if not in_outer:
            if re.match(rf'^\s*{re.escape(outer_section)}\s*\{{', ln, re.IGNORECASE):
                in_outer = True
                outer_d  = ln.count("{") - ln.count("}")
        elif not in_inner:
            outer_d += ln.count("{") - ln.count("}")
            if outer_d <= 0:
                break
            if re.match(rf'^\s*{re.escape(inner_section)}\s*\{{', ln, re.IGNORECASE):
                in_inner = True
                inner_d  = ln.count("{") - ln.count("}")
        else:
            inner_d += ln.count("{") - ln.count("}")
            if inner_d <= 0:
                inner_end = i
                break
            if not s.startswith("#") and re.match(rf'^\s*{re.escape(key)}\s*=', ln):
                indent = len(ln) - len(ln.lstrip())
                lines[i] = " " * indent + f"{key} = {value}\n"
                found = True

    if in_inner and not found and inner_end:
        lines.insert(inner_end, f"    {key} = {value}\n")
    elif not in_inner:
        lines.append(f"\n{outer_section} {{\n  {inner_section} {{\n    {key} = {value}\n  }}\n}}\n")

    with open(path, "w") as f: f.writelines(lines)
    return lines, f"Set {outer_section}.{inner_section}.{key} = {value}"


# ── Public API ─────────────────────────────────────────────────────────────

def set_value(section, key, value, file_key=None, instant=True):
    """
    Universal setter. Finds right file, backs up, edits in-block, 
    applies hyprctl keyword instantly, reloads.
    """
    # auto-detect file
    if not file_key:
        file_key = SETTING_FILE.get(key, SETTING_FILE.get(f"{section}_{key}", "settings"))

    path = F.get(file_key)
    if not path or not os.path.isfile(path):
        return f"File not found for '{file_key}'. Check path: {path}"

    bak = _backup(path)
    _, msg = _set_in_file(path, section, key, value)

    results = [msg, f"File: {os.path.relpath(path, HYPR)}  Backup: {os.path.basename(bak)}"]

    # instant apply
    if instant:
        kw = f"{section}:{key}" if section else key
        kw = kw.replace(".",":")
        r  = _keyword(kw, value)
        results.append(f"Live: hyprctl keyword {kw} {value} → {r}")

    r = _reload()
    results.append(f"Reload: {r}")
    return "\n".join(results)


def set_blur(enabled=None, size=None, passes=None, xray=None):
    """Set blur sub-block values in UserDecorations.conf."""
    path = F["decorations"]
    bak  = _backup(path)
    results = []

    if enabled is not None:
        _set_in_file(path, "decoration", "blur.enabled", str(enabled).lower())
        _keyword("decoration:blur:enabled", str(enabled).lower())
        results.append(f"blur enabled = {enabled}")
    if size is not None:
        _set_in_file(path, "decoration", "blur.size", str(size))
        _keyword("decoration:blur:size", str(size))
        results.append(f"blur size = {size}")
    if passes is not None:
        _set_in_file(path, "decoration", "blur.passes", str(passes))
        _keyword("decoration:blur:passes", str(passes))
        results.append(f"blur passes = {passes}")
    if xray is not None:
        _set_in_file(path, "decoration", "blur.xray", str(xray).lower())
        results.append(f"blur xray = {xray}")

    r = _reload()
    return "\n".join(results) + f"\nFile: UserDecorations.conf  Backup: {os.path.basename(bak)}\nReload: {r}"


def set_shadow(enabled=None, rang=None, render_power=None):
    """Set shadow sub-block values in UserDecorations.conf."""
    path = F["decorations"]
    bak  = _backup(path)
    results = []
    if enabled is not None:
        _set_in_file(path, "decoration", "shadow.enabled", str(enabled).lower())
        _keyword("decoration:shadow:enabled", str(enabled).lower())
        results.append(f"shadow enabled = {enabled}")
    if rang is not None:
        _set_in_file(path, "decoration", "shadow.range", str(rang))
        _keyword("decoration:shadow:range", str(rang))
        results.append(f"shadow range = {rang}")
    if render_power is not None:
        _set_in_file(path, "decoration", "shadow.render_power", str(render_power))
        results.append(f"shadow render_power = {render_power}")
    r = _reload()
    return "\n".join(results) + f"\nFile: UserDecorations.conf\nReload: {r}"


def add_keybind(combo, dispatcher, disp_args="", description="", bind_type="bindd"):
    """
    Add keybind to UserKeybinds.conf.
    combo like 'SUPER+T' or 'SUPER SHIFT, E'
    Always uses bindd (with description) — shows in SUPER+H keybind help.
    """
    # parse combo
    combo_clean = combo.replace(" ", "").replace(",", "+")
    parts = [p.strip() for p in combo_clean.split("+") if p.strip()]
    key   = parts[-1].upper()
    mods  = " ".join(p.upper() for p in parts[:-1])
    if not key:
        return "No key given."

    # check conflict in default keybinds
    conflicts = _find_bind_in_file(F["keybinds_default"], mods, key)
    conflicts += _find_bind_in_file(F["keybinds"], mods, key)

    path = F["keybinds"]
    bak  = _backup(path)

    desc = description or f"{dispatcher} {disp_args}".strip()
    if bind_type == "bindd":
        line = f"bindd = {mods}, {key}, {desc}, {dispatcher}, {disp_args}\n"
    else:
        line = f"{bind_type} = {mods}, {key}, {dispatcher}, {disp_args}\n"

    with open(path, "a") as f:
        f.write(line)

    r = _reload()
    warn = ""
    if conflicts:
        warn = f"⚠ Conflict: {mods}+{key} already in {conflicts[0]['file']}: {conflicts[0]['raw']}\n"

    return (warn +
            f"Added: {line.strip()}\n"
            f"File: UserConfigs/UserKeybinds.conf  Backup: {os.path.basename(bak)}\n"
            f"Reload: {r}")


def _find_bind_in_file(path, mods, key):
    if not os.path.isfile(path):
        return []
    found = []
    mods_n = mods.upper().replace(" ", "")
    with open(path) as f:
        for ln in f:
            s = ln.strip()
            if s.startswith("#") or not s.startswith("bind"):
                continue
            m = re.match(r'bind[a-z]*\s*=\s*([^,]*),\s*([^,]*),', s, re.I)
            if m:
                lm = m.group(1).strip().upper().replace(" ","")
                lk = m.group(2).strip().upper()
                if lm == mods_n and lk == key.upper():
                    found.append({"file": os.path.basename(path), "raw": s})
    return found


def remove_keybind(combo):
    """Comment out keybind in UserKeybinds.conf (and warn if it's in default)."""
    combo_clean = combo.replace(" ", "").replace(",", "+")
    parts = [p.strip() for p in combo_clean.split("+") if p.strip()]
    key   = parts[-1].upper()
    mods  = " ".join(p.upper() for p in parts[:-1])

    in_default = _find_bind_in_file(F["keybinds_default"], mods, key)
    if in_default:
        return (f"⚠ {mods}+{key} is in configs/Keybinds.conf (default keybinds) — "
                f"cannot remove from there (it's managed by the dotfiles).\n"
                f"To override: add an unbind in UserKeybinds.conf:\n"
                f"  unbind = {mods}, {key}\n"
                f"Run: jarvis add unbind {mods}+{key}")

    path = F["keybinds"]
    if not os.path.isfile(path):
        return "UserKeybinds.conf not found"

    bak = _backup(path)
    with open(path) as f:
        lines = f.readlines()

    mods_n = mods.replace(" ","")
    count  = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("#"):
            continue
        m = re.match(r'bind[a-z]*\s*=\s*([^,]*),\s*([^,]*),', s, re.I)
        if m:
            lm = m.group(1).strip().upper().replace(" ","")
            lk = m.group(2).strip().upper()
            if lm == mods_n and lk == key.upper():
                lines[i] = "# " + ln
                count += 1

    with open(path, "w") as f: f.writelines(lines)
    r = _reload()
    return (f"Commented out {count} bind(s) for {mods}+{key}\n"
            f"File: UserConfigs/UserKeybinds.conf  Backup: {os.path.basename(bak)}\n"
            f"Reload: {r}")


def unbind_keybind(combo):
    """Add unbind = line to UserKeybinds.conf to override a default keybind."""
    combo_clean = combo.replace(" ", "").replace(",", "+")
    parts = [p.strip() for p in combo_clean.split("+") if p.strip()]
    key   = parts[-1].upper()
    mods  = " ".join(p.upper() for p in parts[:-1])

    path = F["keybinds"]
    bak  = _backup(path)
    line = f"unbind = {mods}, {key}\n"
    with open(path, "a") as f:
        f.write(line)
    r = _reload()
    return f"Added: {line.strip()}\nFile: UserConfigs/UserKeybinds.conf\nReload: {r}"


def list_all_keybinds(filter_text=""):
    """List all keybinds from both Keybinds.conf and UserKeybinds.conf."""
    results = []
    for label, fkey in [("DEFAULT", "keybinds_default"), ("USER", "keybinds")]:
        path = F.get(fkey, "")
        if not os.path.isfile(path):
            continue
        results.append(f"\n═══ {label} ({os.path.relpath(path, HYPR)}) ═══")
        with open(path) as f:
            for ln in f:
                s = ln.strip()
                if not s or s.startswith("#"):
                    continue
                m = re.match(r'(bind[a-z]*)\s*=\s*([^,]*),\s*([^,]*),\s*(.*)', s, re.I)
                if m:
                    btype, mods, key, rest = m.groups()
                    entry = f"  {mods.strip().upper()}+{key.strip().upper()}  →  {rest.strip()}"
                    if not filter_text or filter_text.lower() in entry.lower():
                        results.append(entry)
    return "\n".join(results) if results else "No keybinds found."


def add_window_rule(rule, match_expr):
    """Add windowrulev2 to UserConfigs/WindowRules.conf."""
    path = F["rules"]
    bak  = _backup(path)
    line = f"windowrulev2 = {rule}, {match_expr}\n"
    with open(path, "a") as f: f.write(line)
    r = _reload()
    return f"Added: {line.strip()}\nFile: UserConfigs/WindowRules.conf\nReload: {r}"


def add_workspace_rule(rule):
    """Add workspace rule to workspaces.conf."""
    path = F["workspaces"]
    bak  = _backup(path)
    line = f"workspace = {rule}\n"
    with open(path, "a") as f: f.write(line)
    r = _reload()
    return f"Added: {line.strip()}\nFile: workspaces.conf\nReload: {r}"


def add_startup_app(cmd, once=True):
    """Add exec-once or exec to UserConfigs/Startup_Apps.conf."""
    path = F["startup"]
    bak  = _backup(path)
    prefix = "exec-once" if once else "exec"
    line   = f"{prefix} = {cmd}\n"
    with open(path, "a") as f: f.write(line)
    r = _reload()
    return f"Added: {line.strip()}\nFile: UserConfigs/Startup_Apps.conf\nReload: {r}"


def set_env_var(key, value):
    """Set env = KEY,VALUE in UserConfigs/ENVariables.conf."""
    path = F["env"]
    bak  = _backup(path)
    with open(path) as f:
        lines = f.readlines()
    new_line  = f"env = {key},{value}\n"
    replaced  = False
    for i, ln in enumerate(lines):
        if re.match(rf'^\s*env\s*=\s*{re.escape(key)}\s*,', ln) and not ln.strip().startswith("#"):
            lines[i]  = new_line
            replaced  = True
            break
    if not replaced:
        lines.append(new_line)
    with open(path, "w") as f: f.writelines(lines)
    r = _reload()
    return (f"{'Updated' if replaced else 'Added'}: {new_line.strip()}\n"
            f"File: UserConfigs/ENVariables.conf\nReload: {r}")


def set_default_app(var, value):
    """Set $term, $files, $edit in 01-UserDefaults.conf."""
    path = F["defaults"]
    bak  = _backup(path)
    with open(path) as f:
        lines = f.readlines()
    new_line = f"${var} = {value}\n"
    replaced = False
    for i, ln in enumerate(lines):
        if re.match(rf'^\s*\${re.escape(var)}\s*=', ln) and not ln.strip().startswith("#"):
            lines[i]  = new_line
            replaced  = True
            break
    if not replaced:
        lines.append(new_line)
    with open(path, "w") as f: f.writelines(lines)
    r = _reload()
    return (f"{'Updated' if replaced else 'Added'}: {new_line.strip()}\n"
            f"File: UserConfigs/01-UserDefaults.conf\nReload: {r}")


def set_monitor(name, resolution, position="auto", scale=1, extra=""):
    """Set monitor = line in monitors.conf (managed by nwg-displays)."""
    path = F["monitors"]
    bak  = _backup(path)
    with open(path) as f:
        lines = f.readlines()
    new_line = f"monitor = {name}, {resolution}, {position}, {scale}"
    if extra:
        new_line += f", {extra}"
    new_line += "\n"
    replaced = False
    for i, ln in enumerate(lines):
        if re.match(rf'^\s*monitor\s*=\s*{re.escape(name)}\s*,', ln) and not ln.strip().startswith("#"):
            lines[i]  = new_line
            replaced  = True
            break
    if not replaced:
        lines.append(new_line)
    with open(path, "w") as f: f.writelines(lines)
    # instant apply
    r2 = _run(f"hyprctl keyword monitor {name},{resolution},{position},{scale}")
    r  = _reload()
    return (f"{'Updated' if replaced else 'Added'}: {new_line.strip()}\n"
            f"File: monitors.conf  Live: {r2}  Reload: {r}")


def switch_animation_preset(preset_name):
    """
    Switch animation preset by copying one of the animations/*.conf files
    into UserConfigs/UserAnimations.conf.
    """
    # list available presets
    available = {}
    for fn in os.listdir(ANIMS_DIR):
        if fn.endswith(".conf"):
            available[fn.lower().replace(".conf","")] = os.path.join(ANIMS_DIR, fn)
            available[fn.lower()] = os.path.join(ANIMS_DIR, fn)

    target = preset_name.lower().strip()
    found  = available.get(target) or available.get(target + ".conf")
    if not found:
        # fuzzy match
        for k, v in available.items():
            if target in k:
                found = v
                break

    if not found:
        presets = [os.path.basename(p) for p in available.values() if p.endswith(".conf")]
        presets = sorted(set(presets))
        return f"Preset '{preset_name}' not found.\nAvailable: {', '.join(presets)}"

    path = F["animations"]
    bak  = _backup(path)
    shutil.copy2(found, path)
    r = _reload()
    return (f"Switched animation to: {os.path.basename(found)}\n"
            f"Copied to: UserConfigs/UserAnimations.conf  Backup: {os.path.basename(bak)}\n"
            f"Reload: {r}")


def list_animation_presets():
    """List all available animation preset files."""
    presets = sorted(f for f in os.listdir(ANIMS_DIR) if f.endswith(".conf"))
    return "Available animation presets:\n" + "\n".join(f"  {p}" for p in presets)


def run_script(script_name, args=""):
    """
    Run a hypr script by name. Searches scripts/ and UserScripts/.
    """
    candidates = []
    for d in [SCRIPTS, USCRIPTS]:
        for fn in os.listdir(d) if os.path.isdir(d) else []:
            if script_name.lower() in fn.lower():
                candidates.append(os.path.join(d, fn))

    if not candidates:
        return f"Script '{script_name}' not found in scripts/ or UserScripts/"
    path = candidates[0]
    result = _run(f"bash '{path}' {args}", timeout=30)
    return f"Ran {os.path.basename(path)}: {result}"


def list_scripts():
    """List all available scripts."""
    out = ["═══ scripts/ ═══"]
    if os.path.isdir(SCRIPTS):
        out += sorted(os.listdir(SCRIPTS))
    out += ["\n═══ UserScripts/ ═══"]
    if os.path.isdir(USCRIPTS):
        out += sorted(os.listdir(USCRIPTS))
    return "\n".join(out)


def get_live_values():
    """Get current live Hyprland values via hyprctl getoption."""
    keys = [
        "decoration:rounding",
        "decoration:active_opacity", "decoration:inactive_opacity",
        "decoration:dim_inactive", "decoration:dim_strength",
        "decoration:blur:enabled", "decoration:blur:size", "decoration:blur:passes",
        "decoration:shadow:enabled", "decoration:shadow:range",
        "general:gaps_in", "general:gaps_out", "general:border_size", "general:layout",
        "animations:enabled", "misc:vrr", "misc:vfr",
        "input:sensitivity", "input:natural_scroll", "input:kb_layout",
    ]
    out = ["═══ LIVE HYPRLAND VALUES (hyprctl getoption) ═══"]
    for k in keys:
        raw = _run(f"hyprctl getoption {k} -j")
        try:
            d = json.loads(raw)
            v = d.get("int","") or d.get("float","") or d.get("str","") or d.get("custom","") or d.get("data","")
            out.append(f"  {k} = {v}")
        except Exception:
            out.append(f"  {k} = {raw[:50]}")
    return "\n".join(out)


def show_config(what="decorations"):
    """Read and return a config file by key."""
    what = what.lower().strip()
    key_map = {
        "decorations": "decorations", "decoration": "decorations",
        "animations": "animations", "animation": "animations",
        "keybinds": "keybinds", "keybind": "keybinds",
        "user keybinds": "keybinds",
        "settings": "settings", "system": "system",
        "env": "env", "environment": "env",
        "defaults": "defaults", "default": "defaults",
        "rules": "rules", "window rules": "rules",
        "workspace": "workspace_rules", "workspaces": "workspace_rules",
        "startup": "startup", "startup apps": "startup",
        "monitors": "monitors", "monitor": "monitors",
        "main": "main",
    }
    fkey = key_map.get(what)
    if fkey:
        return read_file(fkey)
    # try as direct file key
    if what in F:
        return read_file(what)
    # try all
    if what == "all":
        return "\n\n".join(
            f"══ {k} ══\n{read_file(v)}"
            for k, v in F.items()
            if os.path.isfile(v)
        )
    return f"Unknown config section: '{what}'. Known: {', '.join(key_map.keys())}"


def apply_raw(text, file_key="keybinds"):
    """Append raw config lines to a file."""
    path = F.get(file_key, file_key)
    if not os.path.isfile(path):
        return f"File not found: {file_key}"
    bak = _backup(path)
    with open(path, "a") as f:
        f.write(f"\n# Added by JARVIS\n{text.strip()}\n")
    r = _reload()
    return f"Appended to {os.path.relpath(path, HYPR)}\nBackup: {os.path.basename(bak)}\nReload: {r}"
