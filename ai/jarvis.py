#!/usr/bin/env python3
"""
J.A.R.V.I.S. — Just A Rather Very Intelligent System
Iron Man–style autonomous Hyprland desktop AI agent for Arch Linux.

Architecture:
  Floating GTK3 window  →  JarvisAgent  →  TerminalSession  →  System
                                        →  tools.py         →  Hyprland config
                                        →  LLM (fcc/openrouter/ollama)

Features:
  • Always-on-top glassmorphic window (layer-shell or fallback)
  • Animated arc reactor: STANDBY → PROCESSING → READY
  • Two-panel layout: Chat | Terminal output (collapsible)
  • Phase 1: Automatic system discovery on first launch
  • Full terminal access: runs any safe command, streams output live
  • File read/write/patch — direct access to ~/.config/hypr/**
  • Intent matching: zero-LLM for common commands
  • Tool loop: up to 8 LLM turns for complex tasks
  • Confirm dialogs for destructive operations
  • Settings panel: switch backend, paste API keys
  • Drag to move, resize, Escape to hide
"""

import os, sys, json, threading, math, mimetypes, datetime, subprocess, shutil
import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER = True
except Exception:
    HAS_LAYER = False

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Pango
import cairo

AI_DIR   = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(AI_DIR, "jarvis_config.json")
ICON     = os.path.join(AI_DIR, "assets", "jarvis_icon.png")
sys.path.insert(0, AI_DIR)

from lib import llm, tools, intent
from lib.agent import JarvisAgent
from lib.prompt import SYSTEM_PROMPT

# ─── colours ────────────────────────────────────────────────────────────────
C_CYAN = (0.13, 0.82, 0.95, 1.0)
C_CDIM = (0.07, 0.42, 0.55, 1.0)
C_ORG  = (1.0,  0.62, 0.10, 1.0)
C_GRN  = (0.18, 0.95, 0.45, 1.0)


# ═══════════════════════════════════════════════════════════════ Arc Reactor
class ArcReactor(Gtk.DrawingArea):
    def __init__(self, size=110):
        super().__init__()
        self._size  = size
        self._state = "standby"
        self._angle = 0.0
        self._pulse = 0.0
        self.set_size_request(size, size)
        self.connect("draw", self._draw)
        GLib.timeout_add(50, self._tick)

    def set_state(self, s):
        self._state = s
        self.queue_draw()

    def _tick(self):
        if self._state == "processing":
            self._angle = (self._angle + 8) % 360
            self.queue_draw()
        self._pulse = (self._pulse + 0.05) % (2 * math.pi)
        return True

    def _draw(self, w, cr):
        s = self._size; cx = cy = s / 2
        cr.set_antialias(cairo.ANTIALIAS_BEST)

        # dark bg circle
        cr.arc(cx, cy, s/2 - 1, 0, 2*math.pi)
        cr.set_source_rgba(0.02, 0.04, 0.08, 1.0)
        cr.fill()

        # outer glow
        pulse_alpha = 0.15 + 0.08 * math.sin(self._pulse)
        grad = cairo.RadialGradient(cx, cy, s*0.3, cx, cy, s*0.5)
        grad.add_color_stop_rgba(0, *C_CYAN[:3], pulse_alpha)
        grad.add_color_stop_rgba(1, *C_CYAN[:3], 0)
        cr.set_source(grad)
        cr.arc(cx, cy, s/2, 0, 2*math.pi)
        cr.fill()

        # outer ring
        cr.set_source_rgba(*C_CYAN[:3], 0.65)
        cr.set_line_width(2.0)
        cr.arc(cx, cy, s*0.44, 0, 2*math.pi)
        cr.stroke()

        # tick marks
        for i in range(36):
            a  = math.radians(i * 10 + self._angle)
            r1 = s*0.36; r2 = s*0.43
            lw = 1.8 if i % 3 == 0 else 0.7
            al = 0.85 if i % 3 == 0 else 0.28
            cr.set_source_rgba(*C_CYAN[:3], al)
            cr.set_line_width(lw)
            cr.move_to(cx + r1*math.cos(a), cy + r1*math.sin(a))
            cr.line_to(cx + r2*math.cos(a), cy + r2*math.sin(a))
            cr.stroke()

        # state arc
        cr.set_line_width(3.5)
        if self._state == "processing":
            cr.set_source_rgba(*C_ORG[:3], 0.9)
            start = math.radians(self._angle)
            cr.arc(cx, cy, s*0.38, start, start + math.pi * 1.5)
        elif self._state == "ready":
            cr.set_source_rgba(*C_GRN[:3], 0.9)
            cr.arc(cx, cy, s*0.38, 0, 2*math.pi)
        else:
            cr.set_source_rgba(*C_ORG[:3], 0.7)
            cr.arc(cx, cy, s*0.38, math.radians(200), math.radians(260))
        cr.stroke()

        # inner dot ring
        for i in range(8):
            a  = math.radians(i * 45 + self._angle * 0.25)
            r  = s * 0.27
            dx = cx + r * math.cos(a); dy = cy + r * math.sin(a)
            active = (i % 3 == 0)
            col    = C_ORG if (active and self._state != "ready") else (C_GRN if self._state == "ready" else C_CDIM)
            cr.arc(dx, dy, 2.8 if active else 1.5, 0, 2*math.pi)
            cr.set_source_rgba(*col[:3], 0.85)
            cr.fill()

        # inner ring
        cr.set_source_rgba(*C_CYAN[:3], 0.35)
        cr.set_line_width(1.2)
        cr.arc(cx, cy, s*0.22, 0, 2*math.pi)
        cr.stroke()

        # core glow
        glow_col = C_GRN if self._state == "ready" else C_CYAN
        grad2 = cairo.RadialGradient(cx, cy, 0, cx, cy, s*0.13)
        grad2.add_color_stop_rgba(0,   *glow_col[:3], 0.98)
        grad2.add_color_stop_rgba(0.5, *glow_col[:3], 0.35 + 0.1 * math.sin(self._pulse))
        grad2.add_color_stop_rgba(1,   *glow_col[:3], 0.0)
        cr.set_source(grad2)
        cr.arc(cx, cy, s*0.13, 0, 2*math.pi)
        cr.fill()

        # centre dot
        cr.arc(cx, cy, 4.0, 0, 2*math.pi)
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.fill()


# ═══════════════════════════════════════════════════════════════════ Bubbles
def _bubble(text, who):
    outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    outer.set_margin_top(2); outer.set_margin_bottom(2)
    lbl = Gtk.Label(label=text)
    lbl.set_line_wrap(True)
    lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    lbl.set_xalign(0); lbl.set_selectable(True)
    lbl.set_max_width_chars(46)
    evb = Gtk.EventBox(); evb.add(lbl)
    if who == "user":
        outer.set_halign(Gtk.Align.END); outer.set_margin_end(6)
        evb.get_style_context().add_class("b-user")
    elif who == "terminal":
        outer.set_halign(Gtk.Align.FILL); outer.set_margin_start(4)
        evb.get_style_context().add_class("b-term")
    elif who == "system":
        outer.set_halign(Gtk.Align.FILL); outer.set_margin_start(4)
        evb.get_style_context().add_class("b-sys")
    else:
        outer.set_halign(Gtk.Align.START); outer.set_margin_start(6)
        evb.get_style_context().add_class("b-bot")
    outer.pack_start(evb, True if who in ("terminal","system") else False, False, 0)
    return outer, lbl


# ═══════════════════════════════════════════════════════════════ Settings panel
class SettingsPanel(Gtk.Box):
    BACKENDS = [
        ("fcc",        "🌐  free-claude-code proxy"),
        ("openrouter", "🔀  OpenRouter"),
        ("ollama",     "🦙  Ollama (local)"),
        ("anthropic",  "☁   Anthropic API"),
    ]

    def __init__(self, on_close):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self._on_close = on_close
        self._cfg = self._load()
        self._build()

    def _load(self):
        try:
            with open(CFG_PATH) as f: return json.load(f)
        except Exception: return {}

    def _save(self):
        existing = self._load()
        existing.update(self._cfg)
        with open(CFG_PATH, "w") as f:
            json.dump(existing, f, indent=2)

    def _build(self):
        self.set_margin_start(10); self.set_margin_end(10)
        self.set_margin_top(6);    self.set_margin_bottom(8)

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        t = Gtk.Label(label="⚙  Settings"); t.get_style_context().add_class("j-title"); t.set_xalign(0)
        x = Gtk.Button(label="✕"); x.get_style_context().add_class("close-btn")
        x.connect("clicked", lambda *_: self._on_close())
        hdr.pack_start(t, True, True, 0); hdr.pack_end(x, False, False, 0)
        self.pack_start(hdr, False, False, 0)
        self.pack_start(Gtk.Separator(), False, False, 3)

        bl = Gtk.Label(label="Backend:"); bl.get_style_context().add_class("j-sub"); bl.set_xalign(0)
        self.pack_start(bl, False, False, 0)
        self._combo = Gtk.ComboBoxText()
        cur = self._cfg.get("llm_backend", "fcc")
        for i, (k, lbl) in enumerate(self.BACKENDS):
            self._combo.append(k, lbl)
            if k == cur: self._combo.set_active(i)
        self._combo.connect("changed", self._on_be)
        self.pack_start(self._combo, False, False, 0)
        self.pack_start(Gtk.Separator(), False, False, 3)

        self._secs = {
            "fcc": self._sec("free-claude-code proxy", [
                ("fcc_url",   "Proxy URL",    self._cfg.get("fcc_url",   "http://127.0.0.1:8082")),
                ("fcc_token", "Auth token",   self._cfg.get("fcc_token", "freecc")),
                ("fcc_model", "Model string", self._cfg.get("fcc_model", "claude-sonnet-4-6")),
            ]),
            "openrouter": self._sec("OpenRouter", [
                ("openrouter_api_key", "API key",  self._cfg.get("openrouter_api_key", "")),
                ("openrouter_model",   "Model ID", self._cfg.get("openrouter_model",   "meta-llama/llama-3.3-70b-instruct:free")),
            ]),
            "ollama": self._sec("Ollama", [
                ("ollama_url",   "URL",   self._cfg.get("ollama_url",   "http://localhost:11434")),
                ("ollama_model", "Model", self._cfg.get("ollama_model", "qwen3:1.7b")),
            ]),
            "anthropic": self._sec("Anthropic", [
                ("anthropic_api_key", "API key", self._cfg.get("anthropic_api_key", "")),
                ("anthropic_model",   "Model",   self._cfg.get("anthropic_model",   "claude-sonnet-4-6")),
            ]),
        }
        for s in self._secs.values():
            self.pack_start(s, False, False, 0)
        self._show_sec()

        # status
        self._stlbl = Gtk.Label(label=""); self._stlbl.get_style_context().add_class("j-sub"); self._stlbl.set_xalign(0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row.pack_start(self._stlbl, True, True, 0)
        chk = Gtk.Button(label="Check"); chk.get_style_context().add_class("j-btn")
        chk.connect("clicked", lambda *_: self._check())
        row.pack_end(chk, False, False, 0)
        self.pack_start(row, False, False, 4)

        hint = Gtk.Label(label="Free: meta-llama/llama-3.3-70b-instruct:free\n      google/gemma-3-27b-it:free")
        hint.get_style_context().add_class("j-sub"); hint.set_xalign(0); hint.set_line_wrap(True)
        self.pack_start(hint, False, False, 0)
        self.pack_start(Gtk.Separator(), False, False, 3)

        save = Gtk.Button(label="💾  Save & Apply")
        save.get_style_context().add_class("j-btn"); save.set_margin_top(4)
        save.connect("clicked", self._save_apply)
        self.pack_start(save, False, False, 0)
        GLib.timeout_add(300, self._check)

    def _sec(self, title, fields):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        tl = Gtk.Label(label=title); tl.get_style_context().add_class("j-sub"); tl.set_xalign(0)
        box.pack_start(tl, False, False, 0)
        box._entries = {}
        for key, ph, val in fields:
            e = Gtk.Entry(); e.get_style_context().add_class("j-input")
            e.set_placeholder_text(ph); e.set_text(str(val))
            if "key" in key or "token" in key: e.set_visibility(False)
            box.pack_start(e, False, False, 0)
            box._entries[key] = e
        return box

    def _on_be(self, combo):
        self._cfg["llm_backend"] = combo.get_active_id()
        self._show_sec()

    def _show_sec(self):
        b = self._cfg.get("llm_backend", "fcc")
        for k, s in self._secs.items():
            s.set_visible(k == b)

    def _save_apply(self, *_):
        for s in self._secs.values():
            for k, e in s._entries.items():
                self._cfg[k] = e.get_text().strip()
        self._save()
        self._on_close()

    def _check(self):
        def _do():
            bs = llm.available_backends(CFG_PATH)
            icons = {"fcc":"🌐","openrouter":"🔀","ollama":"🦙","anthropic":"☁"}
            parts = [f"{icons.get(k,k)}{'✓' if v else '✗'}" for k, v in bs.items()]
            GLib.idle_add(lambda: self._stlbl.set_text("  ".join(parts)) or False)
        threading.Thread(target=_do, daemon=True).start()
        return False


# ═══════════════════════════════════════════════════════════════ Main Window
class Jarvis(Gtk.Window):
    def __init__(self):
        super().__init__(title="J.A.R.V.I.S.")
        self.set_default_size(440, 720)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_resizable(True)

        visual = Gdk.Screen.get_default().get_rgba_visual()
        if visual: self.set_visual(visual)
        self.set_app_paintable(True)

        if HAS_LAYER:
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT,  True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT,  24)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, 24)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)

        self._drag    = None
        self._resize  = None
        self._collapsed      = False
        self._terminal_shown = False
        self._settings_open  = False
        self._attached       = None

        # agent
        self._agent = JarvisAgent(cfg_path=CFG_PATH)
        self._discovery_done = False

        self._css()
        self._build()

        if os.path.isfile(ICON):
            try: self.set_icon_from_file(ICON)
            except Exception: pass

        self.set_opacity(0.90)
        self.connect("enter-notify-event", lambda *_: self.set_opacity(1.0))
        self.connect("leave-notify-event", lambda *_: self.set_opacity(0.90))

        self._status("STANDBY")
        self._refresh_be()
        self._bot(
            "Analyzing current Hyprland environment.\n\n"
            "Please wait while I scan your system…"
        )

        # auto-start fcc server
        threading.Thread(target=self._ensure_fcc, daemon=True).start()
        # run discovery
        threading.Thread(target=self._do_discovery, daemon=True).start()

    # ── CSS ──────────────────────────────────────────────────────────────────
    def _css(self):
        css = b"""
        window { background: transparent; }
        .j-outer {
            background-color: rgba(8,12,22,0.93);
            border-radius: 16px;
            border: 1.5px solid rgba(20,200,230,0.30);
        }
        .j-header {
            background-color: rgba(5,8,16,0.97);
            border-radius: 16px 16px 0 0;
            border-bottom: 1px solid rgba(20,200,230,0.20);
            padding: 7px 10px;
        }
        .j-title  { color:#22d8ee; font-size:15px; font-weight:bold; letter-spacing:2px; }
        .j-sub    { color:rgba(100,170,190,0.60); font-size:9px; letter-spacing:.7px; }
        .j-status { color:#22d8ee; font-size:11px; letter-spacing:3px; font-weight:bold; }
        .j-be     { color:rgba(100,200,220,0.50); font-size:10px; }
        .j-phase  { color:rgba(255,200,50,0.8); font-size:10px; letter-spacing:1px; }

        .b-user {
            background-color: rgba(25,60,110,0.88);
            color:#d8eeff;
            border-radius:12px 12px 3px 12px;
            padding:7px 12px; font-size:12px;
        }
        .b-bot {
            background-color: rgba(12,20,38,0.92);
            color:#b8cedd;
            border-radius:12px 12px 12px 3px;
            padding:7px 12px; font-size:12px;
            border:1px solid rgba(20,200,230,0.12);
        }
        .b-term {
            background-color: rgba(0,0,0,0.75);
            color:#44ff88;
            border-radius:4px;
            padding:4px 8px;
            font-size:10px;
            font-family: monospace;
        }
        .b-sys {
            background-color: rgba(20,200,230,0.07);
            color:rgba(100,200,220,0.70);
            border-radius:4px;
            padding:4px 8px;
            font-size:10px;
            font-style: italic;
        }
        .term-panel {
            background-color: rgba(0,0,0,0.65);
            border-top: 1px solid rgba(20,200,230,0.15);
        }
        .term-label {
            color:#44ff88;
            font-family: monospace;
            font-size: 10px;
            padding: 3px 8px;
        }
        .j-input {
            background-color: rgba(6,10,20,0.95);
            color:#c0d8e8;
            border:1px solid rgba(20,200,230,0.30);
            border-radius:10px;
            padding:7px 10px; font-size:12px;
            caret-color:#22d8ee;
        }
        .j-input:focus { border-color:rgba(20,200,230,0.68); }
        .j-btn {
            background-color:rgba(20,200,230,0.10);
            color:#22d8ee;
            border:1px solid rgba(20,200,230,0.35);
            border-radius:8px;
            padding:5px 12px; font-size:12px; font-weight:600;
        }
        .j-btn:hover { background-color:rgba(20,200,230,0.22); }
        .attach-btn {
            background-color:rgba(20,200,230,0.06);
            color:#22d8ee;
            border:1px solid rgba(20,200,230,0.25);
            border-radius:8px;
            padding:5px 9px; font-size:14px;
        }
        .badge {
            background-color:rgba(20,200,230,0.12);
            color:#22d8ee;
            border-radius:5px;
            padding:2px 7px; font-size:10px;
            border:1px solid rgba(20,200,230,0.25);
        }
        .close-btn { background:transparent; color:rgba(20,200,230,0.50); border:none; font-size:14px; padding:0 4px; }
        .close-btn:hover { color:#ff5555; }
        .icon-btn  { background:transparent; color:rgba(20,200,230,0.42); border:none; font-size:13px; padding:0 3px; }
        .icon-btn:hover  { color:#22d8ee; }
        .settings-box { background-color:rgba(5,8,16,0.98); border-top:1px solid rgba(20,200,230,0.16); }
        scrolledwindow { background: transparent; }
        """
        p = Gtk.CssProvider()
        p.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build(self):
        self._outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._outer.get_style_context().add_class("j-outer")
        self.add(self._outer)
        self._mk_header()
        self._mk_reactor()
        self._mk_chat()
        self._mk_terminal_panel()
        self._mk_settings()
        self._mk_input()
        self.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.BUTTON_PRESS_MASK   |
            Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.connect("button-press-event",   self._wp)
        self.connect("button-release-event", self._wr)
        self.connect("motion-notify-event",  self._wm)
        self.connect("key-press-event",      self._key)

    def _mk_header(self):
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        hdr.get_style_context().add_class("j-header")
        if os.path.isfile(ICON):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(ICON, 24, 24, True)
                hdr.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 2)
            except Exception: pass
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        t1 = Gtk.Label(label="J.A.R.V.I.S."); t1.get_style_context().add_class("j-title"); t1.set_xalign(0)
        t2 = Gtk.Label(label="Autonomous Hyprland Desktop Agent"); t2.get_style_context().add_class("j-sub"); t2.set_xalign(0)
        titles.pack_start(t1, False, False, 0)
        titles.pack_start(t2, False, False, 0)
        hdr.pack_start(titles, True, True, 0)
        for lbl, fn, tip in [
            ("⊞", self._toggle_terminal, "Toggle terminal output"),
            ("⚙", self._toggle_settings, "Settings — backend, API keys"),
            ("⊟", self._toggle_collapse, "Collapse"),
            ("✕", lambda *_: self.hide(), "Hide"),
        ]:
            b = Gtk.Button(label=lbl)
            b.get_style_context().add_class("icon-btn" if lbl != "✕" else "close-btn")
            b.set_tooltip_text(tip)
            b.connect("clicked", fn)
            hdr.pack_end(b, False, False, 0)
        evb = Gtk.EventBox(); evb.add(hdr)
        evb.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.POINTER_MOTION_MASK)
        evb.connect("button-press-event",   self._hp)
        evb.connect("button-release-event", self._hr)
        evb.connect("motion-notify-event",  self._hm)
        self._outer.pack_start(evb, False, False, 0)

    def _mk_reactor(self):
        self._reactor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._reactor_box.set_margin_top(6)
        self._arc = ArcReactor(size=110)
        self._arc.set_halign(Gtk.Align.CENTER)
        self._reactor_box.pack_start(self._arc, False, False, 0)
        self._status_lbl = Gtk.Label(label="STANDBY")
        self._status_lbl.get_style_context().add_class("j-status")
        self._status_lbl.set_margin_top(3)
        self._reactor_box.pack_start(self._status_lbl, False, False, 0)
        self._phase_lbl = Gtk.Label(label="")
        self._phase_lbl.get_style_context().add_class("j-phase")
        self._phase_lbl.set_margin_bottom(2)
        self._reactor_box.pack_start(self._phase_lbl, False, False, 0)
        self._be_lbl = Gtk.Label(label="")
        self._be_lbl.get_style_context().add_class("j-be")
        self._be_lbl.set_margin_bottom(3)
        self._reactor_box.pack_start(self._be_lbl, False, False, 0)
        # discovery progress bar
        self._prog_bar = Gtk.ProgressBar()
        self._prog_bar.set_margin_start(20); self._prog_bar.set_margin_end(20)
        self._prog_bar.set_no_show_all(True)
        self._reactor_box.pack_start(self._prog_bar, False, False, 0)
        self._outer.pack_start(self._reactor_box, False, False, 0)

    def _mk_chat(self):
        self._chat_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._chat_frame.set_margin_start(6); self._chat_frame.set_margin_end(6)
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_vexpand(True); self._scroll.set_min_content_height(160)
        self._chatbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._chatbox.set_margin_start(4); self._chatbox.set_margin_end(4)
        self._chatbox.set_margin_top(5);   self._chatbox.set_margin_bottom(5)
        self._scroll.add(self._chatbox)
        self._chat_frame.pack_start(self._scroll, True, True, 0)
        self._outer.pack_start(self._chat_frame, True, True, 0)

    def _mk_terminal_panel(self):
        """Scrollable terminal output panel below chat."""
        self._term_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._term_panel.get_style_context().add_class("term-panel")
        # header bar
        th = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        th.set_margin_start(8); th.set_margin_end(8); th.set_margin_top(3)
        tl = Gtk.Label(label="⬛  TERMINAL"); tl.get_style_context().add_class("j-sub"); tl.set_xalign(0)
        self._term_clear_btn = Gtk.Button(label="clear")
        self._term_clear_btn.get_style_context().add_class("j-btn")
        self._term_clear_btn.connect("clicked", self._clear_terminal)
        th.pack_start(tl, True, True, 0)
        th.pack_end(self._term_clear_btn, False, False, 0)
        self._term_panel.pack_start(th, False, False, 0)
        # scrolled terminal output
        self._term_scroll = Gtk.ScrolledWindow()
        self._term_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._term_scroll.set_min_content_height(120)
        self._term_scroll.set_max_content_height(200)
        self._term_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self._term_box.set_margin_start(4); self._term_box.set_margin_end(4)
        self._term_box.set_margin_bottom(4)
        self._term_scroll.add(self._term_box)
        self._term_panel.pack_start(self._term_scroll, True, True, 0)
        self._outer.pack_start(self._term_panel, False, False, 0)
        # Hidden by default (runs in the background). Without set_no_show_all,
        # the top-level win.show_all() at startup would force this visible
        # regardless of _terminal_shown.
        self._term_panel.set_no_show_all(True)
        self._term_panel.set_visible(self._terminal_shown)

    def _mk_settings(self):
        self._settings_rev = Gtk.Revealer()
        self._settings_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._settings_rev.set_transition_duration(180)
        self._settings_panel = SettingsPanel(self._close_settings)
        self._settings_panel.get_style_context().add_class("settings-box")
        self._settings_rev.add(self._settings_panel)
        self._outer.pack_start(self._settings_rev, False, False, 0)

    def _mk_input(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(8); box.set_margin_end(8)
        box.set_margin_top(4);   box.set_margin_bottom(10)
        # file badge
        self._badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._badge_box.set_no_show_all(True)
        self._badge_lbl = Gtk.Label(label="")
        self._badge_lbl.get_style_context().add_class("badge")
        cb = Gtk.Button(label="✕"); cb.get_style_context().add_class("close-btn")
        cb.connect("clicked", self._clear_attach)
        self._badge_box.pack_start(self._badge_lbl, False, False, 0)
        self._badge_box.pack_start(cb, False, False, 0)
        box.pack_start(self._badge_box, False, False, 0)
        # input row
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        ab = Gtk.Button(label="📎"); ab.get_style_context().add_class("attach-btn")
        ab.set_tooltip_text("Attach file for JARVIS to analyse")
        ab.connect("clicked", self._attach)
        row.pack_start(ab, False, False, 0)
        self._entry = Gtk.Entry()
        self._entry.get_style_context().add_class("j-input")
        self._entry.set_placeholder_text("Command, question, or task…")
        self._entry.connect("activate", self._send)
        row.pack_start(self._entry, True, True, 0)
        sb = Gtk.Button(label="Send"); sb.get_style_context().add_class("j-btn")
        sb.connect("clicked", self._send)
        row.pack_start(sb, False, False, 0)
        box.pack_start(row, False, False, 0)
        self._outer.pack_start(box, False, False, 0)

    # ── Settings ──────────────────────────────────────────────────────────────
    def _toggle_settings(self, *_):
        self._settings_open = not self._settings_open
        self._settings_rev.set_reveal_child(self._settings_open)
        self._chat_frame.set_visible(not self._settings_open)
        self._reactor_box.set_visible(not self._settings_open)
        self._term_panel.set_visible(not self._settings_open and self._terminal_shown)

    def _close_settings(self):
        self._settings_open = False
        self._settings_rev.set_reveal_child(False)
        self._chat_frame.set_visible(not self._collapsed)
        self._reactor_box.set_visible(not self._collapsed)
        self._term_panel.set_visible(not self._collapsed and self._terminal_shown)
        self._refresh_be()

    def _toggle_terminal(self, *_):
        self._terminal_shown = not self._terminal_shown
        self._term_panel.set_visible(self._terminal_shown and not self._collapsed)

    def _toggle_collapse(self, *_):
        self._collapsed = not self._collapsed
        self._reactor_box.set_visible(not self._collapsed)
        self._chat_frame.set_visible(not self._collapsed)
        self._term_panel.set_visible(not self._collapsed and self._terminal_shown)

    def _clear_terminal(self, *_):
        for child in self._term_box.get_children():
            self._term_box.remove(child)
        self._agent.session.clear_history()

    # ── Status / BE label ────────────────────────────────────────────────────
    def _status(self, s):
        def _do():
            self._status_lbl.set_text(s)
            self._arc.set_state(s.lower())
            return False
        GLib.idle_add(_do)

    def _phase(self, s):
        def _do():
            self._phase_lbl.set_text(s)
            return False
        GLib.idle_add(_do)

    def _refresh_be(self):
        cfg = {}
        try:
            with open(CFG_PATH) as f: cfg = json.load(f)
        except Exception: pass
        b = cfg.get("llm_backend", "fcc")
        icons = {"fcc":"🌐 fcc-proxy","openrouter":"🔀 OpenRouter",
                 "ollama":"🦙 Ollama","anthropic":"☁ Anthropic"}
        GLib.idle_add(lambda: self._be_lbl.set_text(icons.get(b, b)) or False)

    # ── fcc auto-start ────────────────────────────────────────────────────────
    def _ensure_fcc(self):
        import urllib.request, urllib.error
        cfg = {}
        try:
            with open(CFG_PATH) as f: cfg = json.load(f)
        except Exception: pass
        if cfg.get("llm_backend") != "fcc": return
        url = cfg.get("fcc_url", "http://127.0.0.1:8082")
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2): return
        except Exception: pass
        fcc_dir = os.path.dirname(AI_DIR)
        if os.path.isfile(os.path.join(fcc_dir, "server.py")) and shutil.which("uv"):
            subprocess.Popen(
                ["uv", "run", "fcc-server"],
                cwd=fcc_dir,
                stdout=open("/tmp/fcc-server.log", "a"),
                stderr=subprocess.STDOUT,
            )

    # ── Discovery ─────────────────────────────────────────────────────────────
    def _do_discovery(self):
        def progress(done, total, name):
            frac = done / max(total, 1)
            def _up():
                self._prog_bar.set_visible(True)
                self._prog_bar.set_fraction(frac)
                self._phase(f"Scanning: {name.replace('_',' ')}")
                return False
            GLib.idle_add(_up)

        self._status("PROCESSING")
        result = self._agent.run_discovery(progress_cb=progress)

        def _done():
            self._prog_bar.set_visible(False)
            self._phase("")
            self._status("READY")
            # Add discovery result to terminal panel
            self._add_terminal_line("── Discovery Complete ──", False)
            cfg = {}
            try:
                with open(CFG_PATH) as f: cfg = json.load(f)
            except Exception: pass
            backend = cfg.get("llm_backend", "fcc")
            self._clear_chat()
            self._bot(
                f"System analysis complete.\n\n"
                f"I have mapped your Hyprland configuration:\n"
                f"  • Config files scanned\n"
                f"  • Keybinds loaded\n"
                f"  • Monitors detected\n"
                f"  • Installed tools inventoried\n\n"
                f"Backend: [{backend.upper()}]\n\n"
                f"Ready for commands. Try:\n"
                f"  • 'set gaps_in to 8'\n"
                f"  • 'add keybind SUPER+T exec kitty'\n"
                f"  • 'show my keybindings'\n"
                f"  • 'switch to workspace 3'\n"
                f"  • 'take a screenshot'\n"
                f"  • 'check system status'\n"
                f"  • 'apply futuristic preset'\n"
                f"  • any shell command like 'ls ~/.config/hypr'"
            )
            GLib.timeout_add(2000, lambda: self._status("STANDBY") or False)
            return False
        GLib.idle_add(_done)

    # ── Chat helpers ──────────────────────────────────────────────────────────
    def _add_widget(self, b, l):
        self._chatbox.pack_start(b, False, False, 2)
        self._chatbox.show_all()
        GLib.idle_add(self._scroll_bottom)
        return l

    def _bot(self, t):
        b, l = _bubble(t, "bot"); return self._add_widget(b, l)

    def _user(self, t):
        b, l = _bubble(t, "user"); return self._add_widget(b, l)

    def _sys_msg(self, t):
        b, l = _bubble(t, "system"); return self._add_widget(b, l)

    def _typing(self):
        b, l = _bubble("▋", "bot"); return self._add_widget(b, l)

    def _clear_chat(self):
        for c in self._chatbox.get_children():
            self._chatbox.remove(c)

    def _scroll_bottom(self):
        adj = self._scroll.get_vadjustment()
        adj.set_value(adj.get_upper())
        return False

    def _add_terminal_line(self, line: str, is_err: bool):
        """Add a line to the terminal panel (thread-safe via idle_add)."""
        def _do():
            b, l = _bubble(line[:200], "terminal")
            if is_err:
                l.set_markup(f'<span color="#ff6644">{GLib.markup_escape_text(line[:200])}</span>')
            self._term_box.pack_start(b, False, False, 0)
            self._term_box.show_all()
            adj = self._term_scroll.get_vadjustment()
            adj.set_value(adj.get_upper())
            return False
        GLib.idle_add(_do)

    # ── File attach ───────────────────────────────────────────────────────────
    def _attach(self, *_):
        dlg = Gtk.FileChooserDialog(title="Attach file", parent=self, action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        ff = Gtk.FileFilter(); ff.set_name("All supported")
        for p in ["*.conf","*.sh","*.py","*.txt","*.md","*.json","*.yaml","*.toml","*.css","*.log"]:
            ff.add_pattern(p)
        dlg.add_filter(ff)
        r = dlg.run(); path = dlg.get_filename(); dlg.destroy()
        if r != Gtk.ResponseType.OK or not path: return
        try: content = open(path, errors="replace").read(60000); kind = "text"
        except Exception as e: content = f"[error: {e}]"; kind = "error"
        self._attached = {"path": path, "content": content, "kind": kind, "name": os.path.basename(path)}
        self._badge_lbl.set_text(f"📎 {os.path.basename(path)}")
        self._badge_box.set_visible(True); self._badge_box.show_all()
        self._sys_msg(f"Attached: {os.path.basename(path)}")

    def _clear_attach(self, *_):
        self._attached = None; self._badge_box.set_visible(False)

    # ── Send ──────────────────────────────────────────────────────────────────
    def _send(self, *_):
        text = self._entry.get_text().strip()
        if not text: return
        self._entry.set_text("")

        display = text + (f"  [+{self._attached['name']}]" if self._attached else "")
        self._user(display)

        if self._attached:
            af = self._attached
            injected = (
                f"{text}\n\n[Attached file: {af['name']}]\n"
                f"```\n{af['content'][:50000]}\n```\n"
                f"Please analyse and: {text}"
            )
            # inject as user message in agent conversation
            self._agent.conversation.append({"role": "user", "content": injected})
            # remove last (we'll add again inside handle)
            self._agent.conversation.pop()
            user_text = injected
            self._clear_attach()
        else:
            user_text = text

        self._status("PROCESSING")
        self._phase("thinking…")
        sl = self._typing()
        threading.Thread(target=self._handle, args=(user_text, sl), daemon=True).start()

    # ── Handle ────────────────────────────────────────────────────────────────
    def _handle(self, user_text: str, sl):
        chunks = []

        def on_stream(piece):
            if not piece: return
            chunks.append(piece)
            txt = "".join(chunks)
            def _u():
                sl.set_text(txt + "▋")
                GLib.idle_add(self._scroll_bottom)
                return False
            GLib.idle_add(_u)

        def on_terminal(line, is_err):
            self._add_terminal_line(line, is_err)

        try:
            reply = self._agent.handle(
                user_text,
                confirm_fn=self._confirm,
                stream_cb=on_stream,
                terminal_cb=on_terminal,
            )
        except Exception as e:
            import traceback
            reply = f"❌ Agent error: {e}\n{traceback.format_exc()[-600:]}"

        if not reply.strip():
            reply = (
                "⚠️ No response from AI backend.\n\n"
                "Check:\n"
                "  1. Is fcc-server running?  (tail /tmp/fcc-server.log)\n"
                "  2. Is NVIDIA_NIM_API_KEY set in .env?\n"
                "  3. Click ⚙ → switch to OpenRouter with a :free model\n\n"
                "Tip: many commands work without AI — try:\n"
                "  'random wallpaper'  •  'screenshot'  •  'workspace 2'"
            )

        def _finish():
            sl.set_text(reply)
            self._scroll_bottom()
            self._status("READY")
            self._phase("")
            GLib.timeout_add(3000, lambda: self._status("STANDBY") or False)
            return False
        GLib.idle_add(_finish)

    # ── Confirm dialog ────────────────────────────────────────────────────────
    def _confirm(self, preview: str) -> bool:
        result = {"ok": False}; done = threading.Event()
        def _show():
            d = Gtk.MessageDialog(
                transient_for=self, flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Apply this change?",
            )
            d.format_secondary_text((preview or "")[:2000])
            d.set_keep_above(True)
            result["ok"] = d.run() == Gtk.ResponseType.YES
            d.destroy(); done.set(); return False
        GLib.idle_add(_show); done.wait()
        return result["ok"]

    # ── Drag / resize ─────────────────────────────────────────────────────────
    def _hp(self, w, ev):
        if ev.button == 1: self._drag = {"sx": ev.x_root, "sy": ev.y_root}
        return True
    def _hr(self, *_): self._drag = None; return True
    def _hm(self, w, ev):
        if not self._drag: return False
        dx = ev.x_root - self._drag["sx"]; dy = ev.y_root - self._drag["sy"]
        self._drag["sx"] = ev.x_root; self._drag["sy"] = ev.y_root
        if HAS_LAYER:
            mr = GtkLayerShell.get_margin(self, GtkLayerShell.Edge.RIGHT)
            mb = GtkLayerShell.get_margin(self, GtkLayerShell.Edge.BOTTOM)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT,  int(mr - dx))
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, int(mb - dy))
        else:
            x, y = self.get_position(); self.move(int(x+dx), int(y+dy))
        return True

    E = 12
    def _edge(self, x, y):
        w, h = self.get_size(); m = self.E
        return x <= m, x >= w-m, y <= m, y >= h-m

    def _wp(self, w, ev):
        if ev.button != 1: return False
        l, r, t, b = self._edge(ev.x, ev.y)
        if any((l, r, t, b)):
            sw, sh = self.get_size()
            self._resize = {"edge":(l,r,t,b),"sx":ev.x_root,"sy":ev.y_root,"sw":sw,"sh":sh}
            return True
        return False
    def _wr(self, *_): self._resize = None; return False
    def _wm(self, w, ev):
        if self._resize:
            l, r, t, b = self._resize["edge"]
            dx = ev.x_root - self._resize["sx"]; dy = ev.y_root - self._resize["sy"]
            nw = self._resize["sw"] + (dx if r else (-dx if l else 0))
            nh = self._resize["sh"] + (dy if b else (-dy if t else 0))
            self.resize(max(300, int(nw)), max(200, int(nh))); return True
        return False

    def _key(self, w, ev):
        if ev.keyval == Gdk.KEY_Escape: self.hide(); return True
        return False


# ════════════════════════════════════════════════════════════════════════════
def main():
    win = Jarvis()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
