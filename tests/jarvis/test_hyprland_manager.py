from __future__ import annotations

import pytest

from jarvis.hyprland.manager import JarvisAction, execute_actions, is_safe_command


@pytest.mark.parametrize(
    ("command", "allowed"),
    [
        ("hyprctl reload", True),
        ("hyprctl keyword general:gaps_in 8", True),
        ("hyprctl dispatch workspace 2", True),
        ("hyprctl dispatch exec kitty", False),
        ("rm -rf /", False),
        ("hyprctl reload; rm -rf /", False),
    ],
)
def test_is_safe_command_uses_a_hyprland_allowlist(
    command: str, *, allowed: bool
) -> None:
    assert is_safe_command(command) is allowed


@pytest.mark.asyncio
async def test_execute_actions_rejects_paths_outside_hyprland_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    config_dir = tmp_path / "hypr"
    config_dir.mkdir()
    monkeypatch.setattr(
        "jarvis.hyprland.manager.find_hypr_config_dir", lambda: config_dir
    )

    results = await execute_actions(
        [
            JarvisAction(
                kind="create",
                path="../outside.conf",
                content="general { gaps_in = 8 }",
                command=None,
                description="escape config directory",
            )
        ]
    )

    assert results == [
        {
            "file": "../outside.conf",
            "action": "create",
            "success": False,
            "error": "Path must remain inside the Hyprland config directory",
        }
    ]
    assert not (tmp_path / "outside.conf").exists()
