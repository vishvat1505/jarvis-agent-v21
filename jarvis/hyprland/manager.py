"""Jarvis Hyprland Manager — reads, edits, and executes Hyprland config/scripts."""

from __future__ import annotations

import asyncio
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

# ──────────────────────────────────────────────
# Hyprland config locations (ordered by priority)
# ──────────────────────────────────────────────
_HYPR_CONFIG_DIRS = [
    Path.home() / ".config" / "hypr",
    Path("/etc/hypr"),
]


@dataclass
class CommandResult:
    """Result of a hyprctl / shell command."""

    command: str
    stdout: str
    stderr: str
    returncode: int
    success: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "success": self.success,
        }


@dataclass
class JarvisAction:
    """One action Jarvis decided to take (edit or execute)."""

    kind: str  # "edit" | "exec" | "read" | "create"
    path: str | None  # file path for edit/read/create
    content: str | None  # new file content for edit/create
    command: str | None  # shell/hyprctl command for exec
    description: str  # human-readable explanation

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class JarvisResponse:
    """Full response from one Jarvis prompt."""

    prompt: str
    reasoning: str
    actions: list[JarvisAction]
    results: list[CommandResult | dict[str, Any]]
    summary: str
    refined_prompt: str = ""
    assumptions: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "reasoning": self.reasoning,
            "actions": [a.to_dict() for a in self.actions],
            "results": [
                r.to_dict() if isinstance(r, CommandResult) else r for r in self.results
            ],
            "summary": self.summary,
            "refined_prompt": self.refined_prompt,
            "assumptions": self.assumptions,
            "timestamp": self.timestamp,
        }


# ──────────────────────────────────────────────
# File I/O helpers
# ──────────────────────────────────────────────


def find_hypr_config_dir() -> Path | None:
    for d in _HYPR_CONFIG_DIRS:
        if d.exists():
            return d
    return None


def list_hypr_files() -> list[Path]:
    """Return all .conf and shell scripts in the hyprland config dir."""
    found: list[Path] = []
    cfg_dir = find_hypr_config_dir()
    if not cfg_dir:
        return found
    for pattern in ("*.conf", "*.sh", "*.py"):
        found.extend(sorted(cfg_dir.glob(pattern)))
    for sub in cfg_dir.iterdir():
        if sub.is_dir():
            for pattern in ("*.conf", "*.sh", "*.py"):
                found.extend(sorted(sub.glob(pattern)))
    return found


def read_hypr_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not read {}: {}", path, exc)
        return ""


def write_hypr_file(path: Path, content: str) -> None:
    """Backup the original and write new content."""
    backup = path.with_suffix(path.suffix + ".jarvis_bak")
    if path.exists():
        shutil.copy2(path, backup)
        logger.info("Backed up {} → {}", path, backup)
    path.write_text(content, encoding="utf-8")
    logger.info("Wrote {}", path)


def create_hypr_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("Created {}", path)


# ──────────────────────────────────────────────
# Command execution
# ──────────────────────────────────────────────


def _command_parts(cmd: str) -> list[str] | None:
    """Parse a command without accepting shell syntax."""
    try:
        return shlex.split(cmd)
    except ValueError:
        return None


def is_safe_command(cmd: str) -> bool:
    """Allow only non-shell Hyprland control commands.

    Model output is untrusted.  This deliberately does not provide a generic
    shell escape hatch: persistent configuration belongs in managed files and
    live changes go through Hyprland's own control interface.
    """
    parts = _command_parts(cmd)
    if not parts or parts[0] != "hyprctl":
        return False
    if any(token in {";", "&&", "||", "|", "`"} for token in parts):
        return False
    if parts[1:] == ["reload"]:
        return True
    if len(parts) >= 3 and parts[1] == "keyword":
        return True
    if len(parts) >= 3 and parts[1] == "dispatch":
        return parts[2] != "exec"
    return len(parts) == 2 and parts[1] in {
        "version",
        "monitors",
        "workspaces",
        "clients",
    }


async def run_command(cmd: str, timeout: float = 10.0) -> CommandResult:
    """Run an allowlisted Hyprland command without invoking a shell."""
    parts = _command_parts(cmd)
    if not is_safe_command(cmd) or parts is None:
        return CommandResult(
            command=cmd,
            stdout="",
            stderr="Command is not in the Jarvis Hyprland allowlist",
            returncode=-1,
            success=False,
        )
    try:
        proc = await asyncio.create_subprocess_exec(
            *parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout = stdout_b.decode(errors="replace").strip()
        stderr = stderr_b.decode(errors="replace").strip()
        rc = proc.returncode or 0
        return CommandResult(
            command=cmd,
            stdout=stdout,
            stderr=stderr,
            returncode=rc,
            success=(rc == 0),
        )
    except TimeoutError:
        return CommandResult(
            command=cmd,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            returncode=-1,
            success=False,
        )
    except Exception as exc:
        return CommandResult(
            command=cmd,
            stdout="",
            stderr=str(exc),
            returncode=-1,
            success=False,
        )


# ──────────────────────────────────────────────
# Context builder for Claude
# ──────────────────────────────────────────────


def build_hyprland_context(max_chars: int = 14000) -> str:
    """Gather all Hyprland config files into a single context string."""
    files = list_hypr_files()
    if not files:
        return (
            "(No Hyprland config files found — ~/.config/hypr/ does not exist yet.\n"
            " Jarvis can create it for you if you ask.)"
        )
    parts: list[str] = []
    total = 0
    for p in files:
        content = read_hypr_file(p)
        entry = f"\n### FILE: {p}\n{content}\n"
        if total + len(entry) > max_chars:
            parts.append(f"\n### FILE: {p}\n(truncated — file too large)\n")
            break
        parts.append(entry)
        total += len(entry)
    return "".join(parts)


def get_hyprctl_info() -> str:
    """Run hyprctl to get live compositor state."""
    cmds = [
        "hyprctl version",
        "hyprctl monitors",
        "hyprctl workspaces",
        "hyprctl clients",
    ]
    lines: list[str] = []
    for cmd in cmds:
        try:
            result = subprocess.run(
                cmd.split(), capture_output=True, text=True, timeout=3
            )
            lines.append(f"$ {cmd}\n{result.stdout.strip()}")
        except Exception:
            lines.append(f"$ {cmd}\n(not available)")
    return "\n\n".join(lines)


# ──────────────────────────────────────────────
# Action executor
# ──────────────────────────────────────────────


async def execute_actions(actions: list[JarvisAction]) -> list[CommandResult | dict]:
    """Execute the list of actions Jarvis decided on."""
    results: list[CommandResult | dict] = []
    cfg_dir = find_hypr_config_dir() or Path.home() / ".config" / "hypr"

    for action in actions:
        if action.kind == "exec" and action.command:
            cmd = action.command
            if not is_safe_command(cmd):
                results.append(
                    {
                        "command": cmd,
                        "error": "Blocked: command matched safety filter",
                        "success": False,
                    }
                )
                logger.warning("Blocked unsafe command: {}", cmd)
                continue
            logger.info("Jarvis exec: {}", cmd)
            result = await run_command(cmd)
            results.append(result)

        elif (
            action.kind in ("edit", "create")
            and action.path
            and action.content is not None
        ):
            path = _managed_hypr_path(cfg_dir, action.path)
            if path is None:
                results.append(
                    {
                        "file": action.path,
                        "action": action.kind,
                        "success": False,
                        "error": "Path must remain inside the Hyprland config directory",
                    }
                )
                continue
            try:
                if action.kind == "edit":
                    write_hypr_file(path, action.content)
                else:
                    create_hypr_file(path, action.content)
                results.append(
                    {
                        "file": str(path),
                        "action": action.kind,
                        "success": True,
                        "backed_up": action.kind == "edit",
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "file": str(path),
                        "action": action.kind,
                        "success": False,
                        "error": str(exc),
                    }
                )

        elif action.kind == "read" and action.path:
            path = _managed_hypr_path(cfg_dir, action.path)
            if path is None:
                results.append(
                    {
                        "file": action.path,
                        "action": "read",
                        "success": False,
                        "error": "Path must remain inside the Hyprland config directory",
                    }
                )
                continue
            content = read_hypr_file(path) if path.exists() else "(file not found)"
            results.append(
                {
                    "file": str(path),
                    "action": "read",
                    "content": content[:3000],
                    "success": path.exists(),
                }
            )

    return results


def _managed_hypr_path(config_dir: Path, requested_path: str) -> Path | None:
    """Resolve a model-requested path only when it is inside ``config_dir``."""
    root = config_dir.resolve()
    candidate = (root / requested_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate
