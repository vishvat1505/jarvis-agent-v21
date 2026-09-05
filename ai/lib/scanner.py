"""
scanner.py - Walks the Arch-Hyprland repo and builds an index of:
  - config files (.conf)
  - shell/python scripts (.sh, .py)
  - all keybind lines (bind, bindd, bindm, bindl, binde, bindr, etc.)

The index is rebuilt fresh on every agent run so it always reflects the
current on-disk state (the "AI reads all configs and scripts" requirement).
"""

import os
import re

BIND_RE = re.compile(
    r'^\s*(bind[a-z]*)\s*=\s*([^,]*),\s*([^,]*),\s*(.*)$'
)


def find_repo_root(start_path, hint="Arch-Hyprland"):
    """Walk upward from start_path until we find a dir named `hint`
    or a dir containing 'Hyprland-Dots' and 'install-scripts'."""
    cur = os.path.abspath(start_path)
    for _ in range(10):
        if os.path.basename(cur) == hint:
            return cur
        if os.path.isdir(os.path.join(cur, "Hyprland-Dots")) and \
           os.path.isdir(os.path.join(cur, "install-scripts")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    # fallback: assume start_path itself is root
    return os.path.abspath(start_path)


def scan_repo(root, scan_dirs):
    """Return dict with lists of conf files, script files, and all keybinds.

    Each keybind entry:
      {
        "file": relpath,
        "lineno": int,
        "raw": str,
        "bind_type": "bindd"/"bind"/...,
        "mods": "SUPER",
        "key": "M",
        "dispatcher_and_args": "exec, firefox  # Open browser"
      }
    """
    conf_files = []
    script_files = []
    keybinds = []

    visited_files = set()
    for d in scan_dirs:
        full_d = os.path.join(root, d)
        if not os.path.isdir(full_d):
            continue
        for dirpath, dirnames, filenames in os.walk(full_d):
            dirnames[:] = [dn for dn in dirnames if dn not in (".git",)]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                if rel in visited_files:
                    continue
                visited_files.add(rel)
                if fn.endswith(".conf"):
                    conf_files.append(rel)
                    keybinds.extend(_extract_keybinds(full, rel))
                elif fn.endswith(".sh") or fn.endswith(".py"):
                    script_files.append(rel)

    return {
        "conf_files": sorted(conf_files),
        "script_files": sorted(script_files),
        "keybinds": keybinds,
    }


def _extract_keybinds(full_path, rel_path):
    out = []
    try:
        with open(full_path, "r", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return out

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        m = BIND_RE.match(line)
        if not m:
            continue
        bind_type, mods, key, rest = m.groups()
        out.append({
            "file": rel_path,
            "lineno": i,
            "raw": line.rstrip("\n"),
            "bind_type": bind_type.strip(),
            "mods": mods.strip(),
            "key": key.strip(),
            "dispatcher_and_args": rest.strip(),
        })
    return out


def normalize_combo(combo):
    """Normalize a key combo string like 'super+m' or 'SUPER, M'
    into (mods, key) tuple comparable to parsed keybinds.

    Accepts: 'SUPER+M', 'super + shift + m', 'SUPER, M', '$mainMod+M'
    """
    combo = combo.replace("$mainMod", "SUPER")
    # split on + or ,
    parts = re.split(r'[+,]', combo)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return "", ""
    key = parts[-1]
    mods = " ".join(parts[:-1])
    return _norm_mods(mods), _norm_key(key)


def _norm_mods(mods):
    aliases = {
        "SUPER": "SUPER", "WIN": "SUPER", "$MAINMOD": "SUPER",
        "SHIFT": "SHIFT", "CTRL": "CTRL", "CONTROL": "CTRL",
        "ALT": "ALT",
    }
    toks = re.split(r'[\s_]+', mods.upper())
    toks = [aliases.get(t, t) for t in toks if t]
    # canonical order
    order = ["SUPER", "CTRL", "ALT", "SHIFT"]
    toks_sorted = [t for t in order if t in toks] + [t for t in toks if t not in order]
    return " ".join(toks_sorted)


def _norm_key(key):
    key = key.strip()
    if not key:
        return key
    if len(key) == 1:
        return key.upper()
    return key  # leave special keys (mouse_down, Return, etc.) as-is
