from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from jarvis.hyprland.brain import _stream_prompt_response, ask_jarvis


class _FakeResponse:
    status_code = 200

    async def aiter_lines(self):
        yield "event: content_block_delta"
        yield "data: " + json.dumps(
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": '{"summary":"'},
            }
        )
        yield "data: " + json.dumps(
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": 'ok"}'},
            }
        )
        yield "data: [DONE]"


class _FakeStream:
    async def __aenter__(self) -> _FakeResponse:
        return _FakeResponse()

    async def __aexit__(self, *_args) -> None:
        return None


class _FakeClient:
    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    def stream(self, *_args, **_kwargs) -> _FakeStream:
        return _FakeStream()


@pytest.mark.asyncio
async def test_stream_prompt_response_collects_anthropic_text_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "jarvis.hyprland.brain.httpx.AsyncClient", lambda **_kwargs: _FakeClient()
    )

    text = await _stream_prompt_response({}, {}, "http://proxy.test")

    assert text == '{"summary":"ok"}'


@pytest.mark.asyncio
async def test_ask_jarvis_plans_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "jarvis.hyprland.brain._build_user_message", lambda _: "desktop context"
    )
    monkeypatch.setattr(
        "jarvis.hyprland.brain._stream_prompt_response",
        AsyncMock(
            return_value='{"reasoning":"safe","actions":[],"summary":"No change"}'
        ),
    )
    execute = AsyncMock()
    monkeypatch.setattr("jarvis.hyprland.brain.execute_actions", execute)

    response = await ask_jarvis("show my setup")

    assert response.summary == "No change"
    assert response.refined_prompt == "show my setup"
    assert response.results == []
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_jarvis_applies_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "jarvis.hyprland.brain._build_user_message", lambda _: "desktop context"
    )
    monkeypatch.setattr(
        "jarvis.hyprland.brain._stream_prompt_response",
        AsyncMock(
            return_value=(
                '{"reasoning":"apply","actions":[{"kind":"exec",'
                '"command":"hyprctl reload","description":"reload"}],'
                '"summary":"Reloaded"}'
            )
        ),
    )
    execute = AsyncMock(return_value=[{"success": True}])
    monkeypatch.setattr("jarvis.hyprland.brain.execute_actions", execute)

    response = await ask_jarvis("reload", dry_run=False)

    assert response.results == [{"success": True}]
    execute.assert_awaited_once_with(response.actions)
