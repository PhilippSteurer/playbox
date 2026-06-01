"""Play page — browse and start tracks and playlists."""

from __future__ import annotations

import dash
from dash import ALL, Input, Output, callback, ctx, html, no_update

from playbox.web.server import get_core

dash.register_page(__name__, path="/", name="Play")


def _track_item(track: str):
    return html.Button(
        track,
        id={"type": "pb-track", "index": track},
        className="pb-list-item",
        n_clicks=0,
    )


def _playlist_item(name: str):
    return html.Button(
        f"▶ {name}",
        id={"type": "pb-playlist", "index": name},
        className="pb-list-item pb-playlist-item",
        n_clicks=0,
    )


def layout(**_kwargs):
    core = get_core()
    tracks = core.library.tracks()
    playlists = core.library.playlists()

    return html.Div(
        className="pb-page",
        children=[
            html.H2("Play"),
            html.Div(id="pb-play-feedback", className="pb-feedback"),
            html.Section(
                [
                    html.H3(f"Playlists ({len(playlists)})"),
                    html.Div(
                        [_playlist_item(p) for p in playlists]
                        or [html.P("No playlists found.", className="pb-empty")],
                        className="pb-list",
                    ),
                ]
            ),
            html.Section(
                [
                    html.H3(f"Tracks ({len(tracks)})"),
                    html.Div(
                        [_track_item(t) for t in tracks]
                        or [html.P("No tracks found in the music directory.", className="pb-empty")],
                        className="pb-list",
                    ),
                ]
            ),
        ],
    )


@callback(
    Output("pb-play-feedback", "children"),
    Input({"type": "pb-track", "index": ALL}, "n_clicks"),
    Input({"type": "pb-playlist", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def on_play(_track_clicks, _playlist_clicks):
    trigger = ctx.triggered_id
    if not trigger or not isinstance(trigger, dict):
        return no_update
    # Ignore the initial render where n_clicks is 0/None for all items.
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update

    core = get_core()
    name = trigger["index"]
    if trigger["type"] == "pb-track":
        core.dispatch("play_track", {"track": name})
        return f"▶ Playing track: {name}"
    core.dispatch("play_playlist", {"playlist": name})
    return f"▶ Playing playlist: {name}"
