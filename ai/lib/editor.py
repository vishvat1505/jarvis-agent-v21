"""
editor.py - safe file editing: backup, diff preview, append/replace/comment-out,
all gated behind a user confirmation callback.
"""

import os
import shutil
import datetime
import difflib


def _backup(full_path):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{full_path}.{ts}.bak"
    shutil.copy2(full_path, bak)
    return bak


def preview_diff(old_lines, new_lines, filename):
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}", tofile=f"b/{filename}",
        lineterm=""
    )
    return "\n".join(diff)


def append_line(root, rel_path, new_line, confirm_fn):
    """Append a line to a file. confirm_fn(diff_text) -> bool"""
    full = os.path.join(root, rel_path)
    with open(full, "r", errors="ignore") as f:
        old_lines = f.readlines()

    new_lines = old_lines[:]
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"
    new_lines.append(new_line.rstrip("\n") + "\n")

    diff = preview_diff(old_lines, new_lines, rel_path)
    if not confirm_fn(diff):
        return False, "Cancelled."

    _backup(full)
    with open(full, "w") as f:
        f.writelines(new_lines)
    return True, f"Appended to {rel_path}"


def comment_out_line(root, rel_path, lineno, confirm_fn):
    """Comment out a specific 1-indexed line (used for unbind/remove)."""
    full = os.path.join(root, rel_path)
    with open(full, "r", errors="ignore") as f:
        old_lines = f.readlines()

    if lineno < 1 or lineno > len(old_lines):
        return False, f"Line {lineno} out of range in {rel_path}"

    new_lines = old_lines[:]
    target = new_lines[lineno - 1]
    if not target.lstrip().startswith("#"):
        new_lines[lineno - 1] = "# " + target

    diff = preview_diff(old_lines, new_lines, rel_path)
    if not confirm_fn(diff):
        return False, "Cancelled."

    _backup(full)
    with open(full, "w") as f:
        f.writelines(new_lines)
    return True, f"Commented out line {lineno} in {rel_path}"


def replace_line(root, rel_path, lineno, new_text, confirm_fn):
    """Replace a specific 1-indexed line entirely."""
    full = os.path.join(root, rel_path)
    with open(full, "r", errors="ignore") as f:
        old_lines = f.readlines()

    if lineno < 1 or lineno > len(old_lines):
        return False, f"Line {lineno} out of range in {rel_path}"

    new_lines = old_lines[:]
    new_lines[lineno - 1] = new_text.rstrip("\n") + "\n"

    diff = preview_diff(old_lines, new_lines, rel_path)
    if not confirm_fn(diff):
        return False, "Cancelled."

    _backup(full)
    with open(full, "w") as f:
        f.writelines(new_lines)
    return True, f"Replaced line {lineno} in {rel_path}"


def replace_setting(root, rel_path, key, new_value, confirm_fn, assign="="):
    """Find a 'key = value' style line and replace its value.
    If not found, appends a new 'key = value' line."""
    full = os.path.join(root, rel_path)
    with open(full, "r", errors="ignore") as f:
        old_lines = f.readlines()

    new_lines = old_lines[:]
    found = False
    for idx, line in enumerate(new_lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith(key) and assign in stripped:
            lhs = stripped.split(assign)[0].strip()
            if lhs == key:
                new_lines[idx] = f"{key} {assign} {new_value}\n"
                found = True
                break

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key} {assign} {new_value}\n")

    diff = preview_diff(old_lines, new_lines, rel_path)
    if not confirm_fn(diff):
        return False, "Cancelled."

    _backup(full)
    with open(full, "w") as f:
        f.writelines(new_lines)
    return True, f"Updated '{key}' in {rel_path}"
