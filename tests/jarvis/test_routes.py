from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from jarvis.api.routes import (
    HyprctlRequest,
    JarvisPromptRequest,
    jarvis_ask,
    jarvis_exec,
)
from jarvis.hyprland.manager import JarvisResponse


def _request(*, settings: object | None = None) -> Request:
    app = FastAPI()
    if settings is not None:
        app.state.settings = settings
    return Request(
        {
            "type": "http",
            "app": app,
            "client": ("127.0.0.1", 50000),
            "headers": [],
            "method": "POST",
            "path": "/jarvis/ask",
            "query_string": b"",
            "scheme": "http",
            "server": ("127.0.0.1", 8082),
        }
    )


@pytest.mark.asyncio
async def test_jarvis_exec_rejects_non_hyprland_command() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await jarvis_exec(HyprctlRequest(command="rm -rf /"), _request())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Command blocked by safety filter"


@pytest.mark.asyncio
async def test_jarvis_ask_plans_unless_apply_is_explicitly_true(monkeypatch) -> None:
    ask = AsyncMock(
        return_value=JarvisResponse(
            prompt="change gaps",
            reasoning="safe plan",
            actions=[],
            results=[],
            summary="Planned",
        )
    )
    monkeypatch.setattr("jarvis.api.routes.ask_jarvis", ask)

    response = await jarvis_ask(JarvisPromptRequest(prompt="change gaps"), _request())

    assert response["summary"] == "Planned"
    assert ask.await_args.kwargs["dry_run"] is True


@pytest.mark.asyncio
async def test_jarvis_ask_applies_when_requested(monkeypatch) -> None:
    ask = AsyncMock(
        return_value=JarvisResponse(
            prompt="change gaps",
            reasoning="safe plan",
            actions=[],
            results=[],
            summary="Applied",
        )
    )
    monkeypatch.setattr("jarvis.api.routes.ask_jarvis", ask)

    response = await jarvis_ask(
        JarvisPromptRequest(prompt="change gaps", apply=True), _request()
    )

    assert response["summary"] == "Applied"
    assert ask.await_args.kwargs["dry_run"] is False


@pytest.mark.asyncio
async def test_jarvis_ask_uses_the_configured_provider_model(monkeypatch) -> None:
    ask = AsyncMock(
        return_value=JarvisResponse(
            prompt="change gaps",
            reasoning="safe plan",
            actions=[],
            results=[],
            summary="Planned",
        )
    )
    monkeypatch.setattr("jarvis.api.routes.ask_jarvis", ask)
    settings = SimpleNamespace(
        port=9123,
        anthropic_auth_token="proxy-token",
        model="gemini/models/gemini-3.1-flash-lite",
    )

    await jarvis_ask(JarvisPromptRequest(prompt="change gaps"), _request(settings=settings))

    assert ask.await_args.kwargs["fcc_base_url"] == "http://127.0.0.1:9123"
    assert ask.await_args.kwargs["fcc_auth_token"] == "proxy-token"
    assert ask.await_args.kwargs["model"] == "gemini/models/gemini-3.1-flash-lite"
