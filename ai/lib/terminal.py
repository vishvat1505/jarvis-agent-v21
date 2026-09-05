"""
terminal.py — JARVIS Terminal Agent Layer.

Real terminal access: runs commands, reads output, streams to UI.
Supports: safe shell, PTY subprocess, timeout, kill, history.
"""

import os, re, subprocess, threading, queue, signal, shutil, time

# ── Safety filter ─────────────────────────────────────────────────────────────
_CONFIRM_PATTERNS = [
    r"\brm\s+(-rf?|--recursive)\s+/",
    r"\bdd\s+if=",
    r"\bmkfs\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bfdisk\b",
    r"\bparted\b",
    r">\s*/dev/sd",
    r">\s*/dev/nvme",
    r"\bsudo\s+rm\s+-rf",
    r"\bformat\b",
    r"\bwipe\b",
    r"\bcurl\b.*\|\s*(ba)?sh",
    r"\bwget\b.*\|\s*(ba)?sh",
]

_BLOCKED_PATTERNS = [
    r"\brm\s+-rf\s+/\s*$",         # rm -rf / alone
    r"\bdd\s+if=/dev/zero\s+of=/dev/sd",  # zero-wipe disk
]

def safety_check(cmd: str) -> tuple[str, bool]:
    """
    Returns (level, needs_confirm).
    level: 'ok' | 'confirm' | 'blocked'
    """
    cl = cmd.strip().lower()
    for p in _BLOCKED_PATTERNS:
        if re.search(p, cl):
            return "blocked", True
    for p in _CONFIRM_PATTERNS:
        if re.search(p, cl):
            return "confirm", True
    return "ok", False


# ── Async command runner ──────────────────────────────────────────────────────

class CommandResult:
    def __init__(self, cmd, stdout, stderr, returncode, duration):
        self.cmd        = cmd
        self.stdout     = stdout
        self.stderr     = stderr
        self.returncode = returncode
        self.duration   = duration
        self.success    = returncode == 0

    @property
    def output(self):
        o = self.stdout.strip()
        e = self.stderr.strip()
        if o and e: return f"{o}\n{e}"
        return o or e or ""

    def __str__(self):
        icon = "✓" if self.success else "✗"
        s = f"{icon} [{self.returncode}] {self.cmd}\n"
        if self.output:
            # cap long outputs
            lines = self.output.splitlines()
            if len(lines) > 60:
                s += "\n".join(lines[:30]) + f"\n... ({len(lines)-30} more lines)\n" + "\n".join(lines[-10:])
            else:
                s += self.output
        return s


def run(cmd: str, timeout: float = 30.0, cwd: str = None,
        env_extra: dict = None, stream_callback=None) -> CommandResult:
    """
    Run a shell command. Optional stream_callback(line) for live output.
    Returns CommandResult.
    """
    t0  = time.time()
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)

    try:
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd or os.path.expanduser("~"),
            env=env,
            text=True,
            preexec_fn=os.setsid,
        )

        stdout_lines = []
        stderr_lines = []

        def _read(pipe, lines, is_err=False):
            for line in iter(pipe.readline, ""):
                lines.append(line)
                if stream_callback:
                    stream_callback(line.rstrip(), is_err)

        t_out = threading.Thread(target=_read, args=(proc.stdout, stdout_lines, False), daemon=True)
        t_err = threading.Thread(target=_read, args=(proc.stderr, stderr_lines, True),  daemon=True)
        t_out.start(); t_err.start()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            proc.wait()
            return CommandResult(cmd, "".join(stdout_lines),
                                 f"TIMEOUT after {timeout}s",
                                 -1, time.time() - t0)

        t_out.join(2); t_err.join(2)

        return CommandResult(
            cmd,
            "".join(stdout_lines),
            "".join(stderr_lines),
            proc.returncode,
            time.time() - t0,
        )

    except Exception as e:
        return CommandResult(cmd, "", str(e), -1, time.time() - t0)


# ── Background terminal session ───────────────────────────────────────────────

class TerminalSession:
    """
    Persistent bash session. Commands run sequentially.
    Keeps working directory, environment across calls.
    """

    def __init__(self):
        self._history: list[CommandResult] = []
        self._cwd = os.path.expanduser("~")
        self._lock = threading.Lock()

    @property
    def cwd(self):
        return self._cwd

    @property
    def history(self):
        return list(self._history)

    def exec(self, cmd: str, timeout: float = 30.0,
             stream_callback=None) -> CommandResult:
        """Execute a command in the session's working directory."""

        # handle cd specially to track cwd
        cd_match = re.match(r"^\s*cd\s+(.*)", cmd.strip())
        if cd_match:
            target = cd_match.group(1).strip().strip("'\"") or os.path.expanduser("~")
            target = os.path.expanduser(target)
            if not os.path.isabs(target):
                target = os.path.join(self._cwd, target)
            target = os.path.normpath(target)
            if os.path.isdir(target):
                self._cwd = target
                r = CommandResult(cmd, f"Changed to: {target}", "", 0, 0)
            else:
                r = CommandResult(cmd, "", f"cd: {target}: No such directory", 1, 0)
            self._history.append(r)
            return r

        with self._lock:
            r = run(cmd, timeout=timeout, cwd=self._cwd,
                    stream_callback=stream_callback)
            self._history.append(r)
            return r

    def exec_multi(self, commands: list[str], stream_callback=None) -> list[CommandResult]:
        """Execute multiple commands in sequence, stopping on failure."""
        results = []
        for cmd in commands:
            if stream_callback:
                stream_callback(f"$ {cmd}", False)
            r = self.exec(cmd, stream_callback=stream_callback)
            results.append(r)
            if not r.success and r.returncode not in (1,):
                break
        return results

    def last_output(self, n=5) -> str:
        recent = self._history[-n:]
        return "\n".join(str(r) for r in recent)

    def clear_history(self):
        self._history.clear()


# ── Discovery runner ──────────────────────────────────────────────────────────

DISCOVERY_COMMANDS = [
    ("hyprland_version",    "hyprctl version 2>/dev/null || echo 'hyprland not running'"),
    ("hyprland_monitors",   "hyprctl monitors -j 2>/dev/null"),
    ("hyprland_workspaces", "hyprctl workspaces -j 2>/dev/null"),
    ("hyprland_clients",    "hyprctl clients -j 2>/dev/null"),
    ("hyprland_keybinds",   "hyprctl binds -j 2>/dev/null | head -c 8000"),
    ("config_tree",         "find ~/.config/hypr -name '*.conf' | head -40"),
    ("config_main",         "cat ~/.config/hypr/hyprland.conf 2>/dev/null | head -60"),
    ("config_keybinds",     "cat ~/.config/hypr/UserConfigs/UserKeybinds.conf 2>/dev/null"),
    ("config_decorations",  "cat ~/.config/hypr/UserConfigs/UserDecorations.conf 2>/dev/null"),
    ("config_animations",   "cat ~/.config/hypr/UserConfigs/UserAnimations.conf 2>/dev/null"),
    ("config_env",          "cat ~/.config/hypr/UserConfigs/ENVariables.conf 2>/dev/null"),
    ("config_startup",      "cat ~/.config/hypr/UserConfigs/Startup_Apps.conf 2>/dev/null"),
    ("config_monitors",     "cat ~/.config/hypr/monitors.conf 2>/dev/null"),
    ("config_rules",        "cat ~/.config/hypr/UserConfigs/WindowRules.conf 2>/dev/null"),
    ("waybar_config",       "cat ~/.config/waybar/config.jsonc 2>/dev/null | head -40"),
    ("installed_tools",     (
        "which hyprctl hyprlock hypridle swww grim slurp wf-recorder "
        "waybar dunst mako rofi wofi kitty alacritty foot wezterm "
        "brightnessctl wpctl playerctl 2>/dev/null"
    )),
    ("shell_info",          "echo $SHELL; echo $TERM; echo $EDITOR; echo $XDG_SESSION_TYPE"),
    ("kernel_display",      "uname -r; echo $WAYLAND_DISPLAY; echo $HYPRLAND_INSTANCE_SIGNATURE"),
]


def run_discovery(session: TerminalSession, progress_cb=None) -> dict:
    """
    Phase 1: System Discovery.
    Runs all discovery commands and returns a structured knowledge map.
    """
    results = {}
    total   = len(DISCOVERY_COMMANDS)

    for i, (name, cmd) in enumerate(DISCOVERY_COMMANDS):
        if progress_cb:
            progress_cb(i, total, name)
        r = session.exec(cmd, timeout=8)
        results[name] = {
            "cmd":    cmd,
            "output": r.output[:4000],
            "ok":     r.success,
        }

    if progress_cb:
        progress_cb(total, total, "done")

    return results


def format_discovery(data: dict) -> str:
    """Format discovery results into a readable knowledge map."""
    sections = []

    def _add(title, key):
        d = data.get(key, {})
        out = (d.get("output") or "").strip()
        if out:
            sections.append(f"── {title} ──\n{out[:1500]}")

    _add("Hyprland Version",       "hyprland_version")
    _add("Monitors",               "hyprland_monitors")
    _add("Active Workspaces",      "hyprland_workspaces")
    _add("Open Windows",           "hyprland_clients")
    _add("Config Files Found",     "config_tree")
    _add("Main Config",            "config_main")
    _add("User Keybinds",          "config_keybinds")
    _add("Decorations Config",     "config_decorations")
    _add("Animation Config",       "config_animations")
    _add("Env Variables",          "config_env")
    _add("Startup Apps",           "config_startup")
    _add("Monitor Config",         "config_monitors")
    _add("Window Rules",           "config_rules")
    _add("Waybar Config",          "waybar_config")
    _add("Installed Tools",        "installed_tools")
    _add("Shell / Terminal / Env", "shell_info")
    _add("Kernel / Display",       "kernel_display")

    return "\n\n".join(sections)
