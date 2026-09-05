"""
keybinds.py - conflict detection and add/remove/edit logic for Hyprland binds.
"""

from . import scanner


def find_conflicts(index, mods, key, exclude_file=None, exclude_lineno=None):
    """Return list of existing keybind entries that use the same mods+key combo."""
    conflicts = []
    for kb in index["keybinds"]:
        if kb["file"] == exclude_file and kb["lineno"] == exclude_lineno:
            continue
        kb_mods, kb_key = scanner.normalize_combo(f"{kb['mods']}+{kb['key']}")
        if kb_mods == mods and kb_key == key:
            conflicts.append(kb)
    # dedupe identical (file, lineno, raw) entries
    seen = set()
    unique = []
    for c in conflicts:
        sig = (c["file"], c["lineno"], c["raw"])
        if sig not in seen:
            seen.add(sig)
            unique.append(c)
    return unique


def build_bind_line(mods, key, dispatcher, args, description=None, bind_type="bindd"):
    """Construct a Hyprland bind line.

    bindd = MODS, KEY, description, dispatcher, args
    bind  = MODS, KEY, dispatcher, args
    """
    mods_disp = mods if mods else ""
    if bind_type == "bindd":
        desc = description if description else "custom keybind"
        return f"{bind_type} = {mods_disp}, {key}, {desc}, {dispatcher}, {args}".rstrip(", ")
    else:
        return f"{bind_type} = {mods_disp}, {key}, {dispatcher}, {args}".rstrip(", ")


def find_existing_for_combo(index, mods, key):
    """Return all keybind dicts matching mods+key (for unbind/edit)."""
    matches = []
    for kb in index["keybinds"]:
        kb_mods, kb_key = scanner.normalize_combo(f"{kb['mods']}+{kb['key']}")
        if kb_mods == mods and kb_key == key:
            matches.append(kb)
    seen = set()
    unique = []
    for m in matches:
        sig = (m["file"], m["lineno"], m["raw"])
        if sig not in seen:
            seen.add(sig)
            unique.append(m)
    return unique


def unbind_line_for(kb):
    """Given an existing keybind entry, build the matching 'unbind' line
    (Hyprland requires unbinding the *exact original type* via 'unbind')."""
    mods_disp = kb["mods"]
    return f"unbind = {mods_disp}, {kb['key']}"
