# agent.py -- JARVIS Autonomous Agent Engine
import os, json, threading, re, time
from . import llm, tools, intent, terminal
from .prompt import get_system_prompt
from .system_state import (
    get_system_context, deep_read_system,
    save_machine_state, load_machine_state, UserPrefs,
)

CFG_PATH_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "jarvis_config.json")


class JarvisAgent:

    def __init__(self, cfg_path=None):
        self.cfg_path       = cfg_path or CFG_PATH_DEFAULT
        self.session        = terminal.TerminalSession()
        self.conversation   = []
        self.discovery      = None
        self.discovery_done = False
        self._lock          = threading.Lock()
        self._full_snapshot = None
        self._snapshot_age  = 0.0
        threading.Thread(target=self._background_scan, daemon=True).start()

    def _background_scan(self):
        try:
            snap = deep_read_system(fast=False)
            save_machine_state(snap)
            with self._lock:
                self._full_snapshot = snap
                self._snapshot_age  = time.time()
        except Exception:
            pass

    def _get_snapshot(self):
        if time.time() - self._snapshot_age > 300:
            threading.Thread(target=self._background_scan, daemon=True).start()
        with self._lock:
            return self._full_snapshot or load_machine_state()

    def run_discovery(self, progress_cb=None):
        self.discovery = terminal.run_discovery(self.session, progress_cb)
        self.discovery_done = True
        return terminal.format_discovery(self.discovery)

    def handle(self, user_text, confirm_fn=None, stream_cb=None, terminal_cb=None):
        try:
            UserPrefs.record_command(user_text)
        except Exception:
            pass

        self.conversation.append({"role": "user", "content": user_text})

        result, matched = intent.match(user_text, confirm_fn)
        if matched:
            reply = result or "Done."
            self.conversation.append({"role": "assistant", "content": reply})
            if stream_cb:
                stream_cb(reply)
            return reply

        sys_prompt = self._build_system_prompt()
        reply = self._agent_loop(
            list(self.conversation), sys_prompt,
            confirm_fn=confirm_fn, stream_cb=stream_cb, terminal_cb=terminal_cb,
        )

        if not reply.strip():
            reply = (
                "No response from AI backend.\n"
                "  * Run: uv run fcc-server  then retry\n"
                "  * Or set OPENROUTER_API_KEY in .env\n\n"
                "Tip: for offline-capable commands (open/close/wallpaper/files)"
                " the intent layer handles them without any LLM."
            )

        self.conversation.append({"role": "assistant", "content": reply})
        return reply

    def _build_system_prompt(self):
        base = get_system_prompt()
        try:
            live = deep_read_system(fast=True)
            stored = self._get_snapshot()
            if stored:
                for k in ("hardware","installed_apps","home_tree",
                          "recent_files","hypr_config"):
                    if k in stored and k not in live:
                        live[k] = stored[k]
            ctx = get_system_context(live)
            prefs = UserPrefs.load()
            pref_items = {k:v for k,v in prefs.items()
                          if k in ("name","preferred_browser","preferred_editor",
                                   "preferred_terminal","workspace_labels",
                                   "custom_app_aliases") and v}
            prefs_str = json.dumps(pref_items, indent=2) if pref_items else ""
            return (base + "\n\n" + ctx +
                    (f"\n\nUSER PREFERENCES:\n{prefs_str}" if prefs_str else ""))
        except Exception:
            return base

    def _agent_loop(self, messages, sys_prompt, confirm_fn, stream_cb,
                    terminal_cb, max_turns=8):
        tool_specs = tools.get_tool_specs() + _terminal_tool_specs()
        full_reply = []
        for turn in range(max_turns):
            resp = llm.chat(
                messages, sys_prompt, self.cfg_path,
                tools=tool_specs,
                stream_callback=(stream_cb if turn == 0 else None),
            )
            text       = resp.get("text","")
            tool_calls = resp.get("tool_calls",[])
            if text:
                full_reply.append(text)
            if not tool_calls:
                break
            messages.append({"role":"assistant","content": text or "(using tools)"})
            for tc in tool_calls:
                name   = tc.get("name","")
                args   = tc.get("arguments",{})
                result = self._dispatch_tool(name, args, confirm_fn, terminal_cb)
                messages.append({"role":"user",
                                  "content":f"Tool result for {name}:\n{result}"})
                if stream_cb:
                    stream_cb(f"\n[{name}] {result}")
        return "\n".join(full_reply)

    def _dispatch_tool(self, name, args, confirm_fn, terminal_cb):
        if name == "run_terminal_command":
            return self._run_terminal(
                args.get("command",""), args.get("timeout",30),
                confirm_fn, terminal_cb)
        if name == "run_terminal_commands":
            return "\n\n".join(
                f"$ {cmd}\n{self._run_terminal(cmd, 30, confirm_fn, terminal_cb)}"
                for cmd in args.get("commands",[]))
        if name == "read_file":
            path = os.path.expanduser(args.get("path",""))
            if not os.path.isfile(path):
                cands = tools._resolve_file_path(os.path.basename(path))
                if cands: path = cands[0]
            try:
                with open(path) as f:
                    content = f.read()
                lines = content.splitlines()
                return ("\n".join(lines[:150]) +
                        (f"\n...({len(lines)-150} more)" if len(lines)>150 else ""))
            except Exception as e:
                return f"Cannot read {path}: {e}"
        if name == "write_file":
            path    = os.path.expanduser(args.get("path",""))
            content = args.get("content","")
            if args.get("backup",True) and os.path.isfile(path):
                import shutil as _sh, datetime as _dt
                _sh.copy2(path, f"{path}.{_dt.datetime.now():%Y%m%d-%H%M%S}.bak")
            try:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path,"w") as f: f.write(content)
                return f"Written: {path} ({len(content.splitlines())} lines)"
            except Exception as e:
                return f"Write failed: {e}"
        if name == "patch_file":
            return self._patch_file(
                args.get("path",""), args.get("old",""), args.get("new",""))
        if name == "list_directory":
            path = os.path.expanduser(args.get("path","~/.config/hypr"))
            r = self.session.exec(
                f"find '{path}' -maxdepth {args.get('depth',2)} -type f | head -60",
                timeout=5)
            return r.output or "empty"
        if name == "hyprland_reload":
            r = self.session.exec("hyprctl reload", timeout=10)
            return r.output or "reloaded"
        if name == "get_system_state":
            try:
                return get_system_context(deep_read_system(fast=True))
            except Exception as e:
                return f"State read error: {e}"
        return tools.call_tool(name, args, confirm_fn)

    _OPEN_CMD_RE = re.compile(
        r"^\s*(?:xdg-open|gio\s+open|gtk-launch)\s+(.+?)\s*&?\s*$", re.IGNORECASE)

    def _run_terminal(self, cmd, timeout, confirm_fn, terminal_cb):
        m = self._OPEN_CMD_RE.match(cmd)
        if m:
            target = m.group(1).strip().strip("'\"")
            if terminal_cb:
                terminal_cb(f"$ {cmd}  -> resolved via open tools", False)
            return tools.smart_open({"target": target})
        level, _ = terminal.safety_check(cmd)
        if level == "blocked":
            return f"BLOCKED: '{cmd}'"
        if level == "confirm" and confirm_fn:
            if not confirm_fn(f"Execute:\n$ {cmd}"):
                return f"Cancelled: {cmd}"
        if terminal_cb:
            terminal_cb(f"$ {cmd}", False)
        r = self.session.exec(cmd, timeout=timeout, stream_callback=terminal_cb)
        return str(r)

    def _patch_file(self, path, old, new):
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            return f"File not found: {path}"
        import shutil as _sh, datetime as _dt
        bak = f"{path}.{_dt.datetime.now():%Y%m%d-%H%M%S}.bak"
        _sh.copy2(path, bak)
        with open(path) as f:
            content = f.read()
        if old not in content:
            return f"Pattern not found in {path}"
        with open(path,"w") as f:
            f.write(content.replace(old, new, 1))
        return f"Patched {path} (backup: {os.path.basename(bak)})"

    def clear_conversation(self):
        self.conversation.clear()

    def get_terminal_history(self, n=10):
        return self.session.last_output(n)


def _terminal_tool_specs():
    def s(name, desc, props=None, req=None):
        return {"name": name, "description": desc,
                "input_schema": {"type":"object",
                                 "properties": props or {},
                                 "required": req or []}}
    return [
        s("run_terminal_command",
          "Run a shell command. Use for hyprctl, git, logs, processes, anything "
          "not covered by a dedicated tool. Dangerous commands ask confirmation.",
          {"command":{"type":"string"},"timeout":{"type":"number"}}, ["command"]),
        s("run_terminal_commands",
          "Run multiple shell commands in sequence.",
          {"commands":{"type":"array","items":{"type":"string"}}}, ["commands"]),
        s("read_file",
          "Read any file (config, log, script). Capped at 150 lines. Resolves ~ paths.",
          {"path":{"type":"string"}}, ["path"]),
        s("write_file",
          "Write content to a file. Creates parent dirs. Auto-backs-up existing files.",
          {"path":{"type":"string"},"content":{"type":"string"},
           "backup":{"type":"boolean"}}, ["path","content"]),
        s("patch_file",
          "Replace exactly ONE occurrence of old text with new in a file. Auto-backs-up.",
          {"path":{"type":"string"},"old":{"type":"string"},"new":{"type":"string"}},
          ["path","old","new"]),
        s("list_directory",
          "List files in a directory tree.",
          {"path":{"type":"string"},"depth":{"type":"integer"}}, ["path"]),
        s("hyprland_reload", "Run hyprctl reload to apply config changes.", {}, []),
        s("get_system_state",
          "Get real-time system state: windows, workspaces, monitors, audio, CPU/RAM, net.",
          {}, []),
    ]
