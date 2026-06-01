"""Shared UI helpers."""

from __future__ import annotations

from typing import Any

from dash import html


def _fmt_time(seconds: Any) -> str:
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def now_playing_view(info: dict[str, Any] | None) -> Any:
    """Render the now-playing block from PlayerController.now_playing()."""
    if not info or info.get("idle") or not info.get("title"):
        return html.Div("Nothing playing", className="pb-np pb-np-idle")

    pos = _fmt_time(info.get("position"))
    dur = _fmt_time(info.get("duration"))
    state = "Paused" if info.get("paused") else "Playing"
    queue = ""
    count = info.get("playlist_count") or 0
    if count and count > 1:
        queue = f"  ·  track {(info.get('playlist_pos') or 0) + 1}/{count}"

    return html.Div(
        className="pb-np",
        children=[
            html.Div(info["title"], className="pb-np-title"),
            html.Div(f"{state}  ·  {pos} / {dur}{queue}", className="pb-np-meta"),
            html.Div(f"Volume {info.get('volume')}", className="pb-np-vol"),
        ],
    )
