"""Jarvis Hyprland routes — mounted into the free-claude-code FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from jarvis.api.security import require_loopback_jarvis
from jarvis.hyprland.brain import ask_jarvis
from jarvis.hyprland.manager import (
    build_hyprland_context,
    find_hypr_config_dir,
    get_hyprctl_info,
    is_safe_command,
    list_hypr_files,
    run_command,
)

router = APIRouter(prefix="/jarvis", tags=["jarvis"])

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# ── Models ────────────────────────────────────


class JarvisPromptRequest(BaseModel):
    prompt: str = Field(..., description="Natural language Hyprland management command")
    apply: bool = Field(
        False, description="Apply validated actions; false returns a safe plan only"
    )
    model: str | None = Field(
        None,
        description="Optional provider/model override; defaults to configured MODEL",
    )


class HyprctlRequest(BaseModel):
    command: str = Field(..., description="Raw hyprctl or shell command")


# ── Routes ────────────────────────────────────


@router.get("/")
async def jarvis_ui(request: Request):
    """Serve the Jarvis web UI."""
    require_loopback_jarvis(request)
    index = _STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Jarvis API online. UI not found."}


@router.post("/ask")
async def jarvis_ask(body: JarvisPromptRequest, request: Request):
    """
    Ask Jarvis to manage your Hyprland desktop.
    Jarvis reads all config files, calls Claude via the fcc proxy,
    returns a validated plan, and applies it only when ``apply`` is true.
    """
    require_loopback_jarvis(request)
    fcc_base_url = "http://127.0.0.1:8082"
    fcc_auth_token = "fcc-no-auth"
    model = body.model or "claude-opus-4-6"
    try:
        settings = getattr(request.app.state, "settings", None)
        if settings:
            port = getattr(settings, "port", 8082)
            token = getattr(settings, "anthropic_auth_token", "") or "fcc-no-auth"
            fcc_base_url = f"http://127.0.0.1:{port}"
            fcc_auth_token = token
            model = body.model or getattr(settings, "model", model)
    except Exception:
        pass

    try:
        response = await ask_jarvis(
            body.prompt,
            fcc_base_url=fcc_base_url,
            fcc_auth_token=fcc_auth_token,
            dry_run=not body.apply,
            model=model,
        )
        return response.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502, detail="Jarvis could not obtain a model response"
        ) from exc


@router.get("/status")
async def jarvis_status(request: Request):
    """Return Hyprland environment status."""
    require_loopback_jarvis(request)
    cfg_dir = find_hypr_config_dir()
    files = list_hypr_files()
    return {
        "hypr_config_dir": str(cfg_dir) if cfg_dir else None,
        "config_files": [str(f) for f in files],
        "file_count": len(files),
    }


@router.get("/config")
async def jarvis_config(request: Request):
    """Return all Hyprland config file contents."""
    require_loopback_jarvis(request)
    return {"config_context": build_hyprland_context()}


@router.get("/live")
async def jarvis_live(request: Request):
    """Return live hyprctl compositor state."""
    require_loopback_jarvis(request)
    return {"hyprctl_state": get_hyprctl_info()}


@router.post("/exec")
async def jarvis_exec(body: HyprctlRequest, request: Request):
    """Execute an allowlisted direct Hyprland command."""
    require_loopback_jarvis(request)
    if not is_safe_command(body.command):
        raise HTTPException(status_code=400, detail="Command blocked by safety filter")
    result = await run_command(body.command)
    return result.to_dict()
