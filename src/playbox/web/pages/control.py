"""Control page — transport, volume and now-playing display."""

from __future__ import annotations

import dash
from dash import Input, Output, callback, ctx, dcc, html, no_update

from playbox.web.components import now_playing_view
from playbox.web.server import get_core

dash.register_page(__name__, path="/control", name="Control")

# (button id, label, callback name)
_TRANSPORT = [
    ("pb-prev", "⏮ Prev", "previous"),
    ("pb-toggle", "⏯ Play/Pause", "toggle"),
    ("pb-stop", "⏹ Stop", "stop"),
    ("pb-next", "⏭ Next", "next"),
]


def layout(**_kwargs):
    core = get_core()
    vol = core.settings.volume
    return html.Div(
        className="pb-page",
        children=[
            html.H2("Control"),
            html.Div(now_playing_view(None), id="pb-now-playing"),
            dcc.Interval(id="pb-np-interval", interval=1000, n_intervals=0),
            html.Div(
                [html.Button(label, id=bid, className="pb-transport", n_clicks=0)
                 for bid, label, _ in _TRANSPORT],
                className="pb-transport-row",
            ),
            html.Div(
                [
                    html.Label("Volume"),
                    dcc.Slider(id="pb-volume", min=0, max=100, step=1, value=vol,
                               marks={0: "0", 50: "50", 100: "100"}),
                ],
                className="pb-volume-row",
            ),
        ],
    )


@callback(
    Output("pb-now-playing", "children"),
    Input("pb-np-interval", "n_intervals"),
)
def refresh_now_playing(_n):
    core = get_core()
    if core.player is None:
        return now_playing_view(None)
    return now_playing_view(core.player.now_playing())


@callback(
    Output("pb-now-playing", "children", allow_duplicate=True),
    [Input(bid, "n_clicks") for bid, _, _ in _TRANSPORT],
    prevent_initial_call=True,
)
def on_transport(*_clicks):
    trigger = ctx.triggered_id
    if not trigger:
        return no_update
    core = get_core()
    for bid, _label, cb in _TRANSPORT:
        if bid == trigger:
            core.dispatch(cb, {})
            break
    if core.player is None:
        return now_playing_view(None)
    return now_playing_view(core.player.now_playing())


@callback(
    Output("pb-now-playing", "children", allow_duplicate=True),
    Input("pb-volume", "value"),
    prevent_initial_call=True,
)
def on_volume(value):
    if value is None:
        return no_update
    core = get_core()
    core.dispatch("volume", {"level": int(value)})
    if core.player is None:
        return now_playing_view(None)
    return now_playing_view(core.player.now_playing())
