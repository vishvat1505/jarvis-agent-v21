#!/usr/bin/env python3
"""
Jarvis CLI — Hyprland AI Desktop Manager (standalone terminal interface)

Usage:
    python jarvis_cli.py "Set gaps_in to 8 and gaps_out to 16"
    python jarvis_cli.py --dry-run "Enable blur on all windows"
    python jarvis_cli.py --exec "hyprctl keyword general:gaps_in 5"
    python jarvis_cli.py --status
    python jarvis_cli.py              # interactive REPL

Requires fcc-server running on port 8082.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jarvis.hyprland.brain import ask_jarvis
from jarvis.hyprland.manager import (
    build_hyprland_context,
    find_hypr_config_dir,
    get_hyprctl_info,
    is_safe_command,
    list_hypr_files,
    run_command,
)

R="\033[0m"; B="\033[1m"; D="\033[2m"
CY="\033[96m"; GR="\033[92m"; YL="\033[93m"; RD="\033[91m"; BL="\033[94m"

def c(col, t): return f"{col}{t}{R}"

def banner():
    print(c(CY, B+"  ╔══════════════════════════╗"))
    print(c(CY, B+"  ║  J A R V I S  v1.0      ║"))
    print(c(CY, B+"  ║  Hyprland Desktop AI     ║"))
    print(c(CY, B+"  ╚══════════════════════════╝"+R))
    print()

async def cmd_ask(prompt, dry_run, fcc_url):
    print(c(YL, f"\n▶ {prompt}"))
    if dry_run: print(c(D, "  (dry-run — no changes applied)\n"))
    else: print()
    resp = await ask_jarvis(prompt, fcc_base_url=fcc_url, dry_run=dry_run)
    if resp.reasoning:
        print(c(D, "Reasoning:"))
        for ln in resp.reasoning.splitlines()[:5]: print(c(D, "  "+ln))
        print()
    if resp.actions:
        print(c(B, "Actions:"))
        kind_col = {"exec":BL,"edit":GR,"create":YL,"read":D}
        for a in resp.actions:
            col = kind_col.get(a.kind, R)
            print(f"  {c(col,'['+a.kind.upper()+']')} {a.description}")
            if a.command: print(f"    {c(D,'$ '+a.command)}")
            if a.path:    print(f"    {c(D,'→ '+a.path)}")
        print()
    if resp.results:
        print(c(B, "Results:"))
        for r in resp.results:
            rd = r.to_dict() if hasattr(r,"to_dict") else r
            if rd.get("dry_run"):
                print(f"  {c(YL,'[DRY]')} {rd.get('action',{}).get('description','')}")
            elif "command" in rd:
                sym = c(GR,"✓") if rd["success"] else c(RD,"✗")
                print(f"  {sym} {rd['command']}")
                if rd.get("stdout"):
                    for ln in rd["stdout"].splitlines()[:6]: print(c(D,"    "+ln))
                if rd.get("stderr") and not rd["success"]:
                    print(c(RD, "    "+rd["stderr"][:200]))
            elif "file" in rd:
                sym = c(GR,"✓") if rd["success"] else c(RD,"✗")
                print(f"  {sym} {rd.get('action','')} {rd['file']}")
        print()
    print(c(GR, B+"✓ "+resp.summary))
    print()

async def cmd_exec(command):
    if not is_safe_command(command):
        print(c(RD, f"✗ Blocked: {command}")); sys.exit(1)
    print(c(D, f"$ {command}"))
    r = await run_command(command)
    if r.success:
        print(c(GR,"✓ OK"))
        if r.stdout: print(r.stdout)
    else:
        print(c(RD,"✗ Failed"))
        if r.stderr: print(c(RD, r.stderr))
        sys.exit(1)

async def cmd_status():
    cfg = find_hypr_config_dir()
    files = list_hypr_files()
    print(c(CY, "Hyprland Status"))
    print(f"  Config dir : {cfg or c(RD,'not found')}")
    print(f"  Files      : {len(files)}")
    for f in files: print(f"    {c(D,str(f))}")
    print()
    print(c(CY, "Live State:"))
    print(get_hyprctl_info())

def main():
    p = argparse.ArgumentParser(description="Jarvis — Hyprland AI Desktop Manager")
    p.add_argument("prompt", nargs="?")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--exec", metavar="CMD")
    p.add_argument("--status", action="store_true")
    p.add_argument("--config", action="store_true")
    p.add_argument("--fcc-url", default="http://127.0.0.1:8082")
    p.add_argument("--no-banner", action="store_true")
    args = p.parse_args()

    if not args.no_banner: banner()

    if args.status:          asyncio.run(cmd_status())
    elif args.config:        print(build_hyprland_context())
    elif args.exec:          asyncio.run(cmd_exec(args.exec))
    elif args.prompt:        asyncio.run(cmd_ask(args.prompt, args.dry_run, args.fcc_url))
    else:
        print(c(D, "Interactive mode. 'quit' to exit.\n"))
        while True:
            try:   prompt = input(c(CY,"jarvis> ")).strip()
            except (EOFError, KeyboardInterrupt): print(); break
            if not prompt: continue
            if prompt.lower() in ("quit","exit","q"): break
            asyncio.run(cmd_ask(prompt, False, args.fcc_url))

if __name__ == "__main__":
    main()
