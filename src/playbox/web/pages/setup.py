"""Setup page — register RFID tags, manage existing tags, edit settings."""

from __future__ import annotations

import json

import dash
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from playbox.config import TagConfig
from playbox.scan_state import Mode
from playbox.web.server import get_core

dash.register_page(__name__, path="/setup", name="Setup")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _callback_options():
    return [{"label": n, "value": n} for n in get_core().registry.names()]


def render_tags_table():
    core = get_core()
    if not core.tags:
        return html.P("No tags registered yet.", className="pb-empty")
    rows = [
        html.Tr(
            [
                html.Th("UID"), html.Th("Name"), html.Th("Callback"),
                html.Th("Args"), html.Th(""),
            ]
        )
    ]
    for tag in sorted(core.tags, key=lambda t: t.id):
        rows.append(
            html.Tr(
                [
                    html.Td(tag.id),
                    html.Td(tag.name or "—"),
                    html.Td(tag.callback),
                    html.Td(json.dumps(tag.args) if tag.args else "{}"),
                    html.Td(
                        html.Button(
                            "Delete",
                            id={"type": "pb-del-tag", "index": tag.id},
                            className="pb-del",
                            n_clicks=0,
                        )
                    ),
                ]
            )
        )
    return html.Table(rows, className="pb-table")


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def layout(**_kwargs):
    core = get_core()
    s = core.settings
    return html.Div(
        className="pb-page",
        children=[
            html.H2("Setup"),

            # --- Register a new tag ---------------------------------------- #
            html.Section(
                className="pb-card",
                children=[
                    html.H3("Register RFID tag"),
                    html.P("Click 'Start scan', then hold a tag to the reader."),
                    html.Button("Start scan", id="pb-scan-start", n_clicks=0, className="pb-btn"),
                    html.Span(id="pb-scan-status", className="pb-feedback"),
                    dcc.Store(id="pb-scan-seq", data=0),
                    dcc.Interval(id="pb-scan-interval", interval=700, disabled=True),
                    html.Div(
                        className="pb-form",
                        children=[
                            html.Label("Tag UID"),
                            dcc.Input(id="pb-tag-uid", type="text", placeholder="scan a tag…"),
                            html.Label("Name"),
                            dcc.Input(id="pb-tag-name", type="text"),
                            html.Label("Description"),
                            dcc.Input(id="pb-tag-desc", type="text"),
                            html.Label("Callback"),
                            dcc.Dropdown(id="pb-tag-callback", options=_callback_options()),
                            html.Label("Args (JSON)"),
                            dcc.Textarea(id="pb-tag-args", value="{}", className="pb-textarea"),
                            html.Button("Save tag", id="pb-tag-save", n_clicks=0, className="pb-btn pb-btn-primary"),
                            html.Span(id="pb-tag-save-status", className="pb-feedback"),
                        ],
                    ),
                ],
            ),

            # --- Existing tags --------------------------------------------- #
            html.Section(
                className="pb-card",
                children=[
                    html.H3("Configured tags"),
                    html.Div(render_tags_table(), id="pb-tags-table"),
                ],
            ),

            # --- Settings -------------------------------------------------- #
            html.Section(
                className="pb-card",
                children=[
                    html.H3("Settings"),
                    html.Div(
                        className="pb-form",
                        children=[
                            html.Label("Music directory"),
                            dcc.Input(id="pb-set-music", type="text", value=str(s.music_dir)),
                            html.Label("Audio device (ALSA, e.g. alsa/hw:0,0 — restart to apply)"),
                            dcc.Input(id="pb-set-audio", type="text", value=s.audio_device),
                            html.Label("Default volume"),
                            dcc.Input(id="pb-set-volume", type="number", min=0, max=100, value=s.volume),
                            html.Button("Save settings", id="pb-set-save", n_clicks=0, className="pb-btn pb-btn-primary"),
                            html.Span(id="pb-set-status", className="pb-feedback"),
                        ],
                    ),
                ],
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# Register-tag flow
# --------------------------------------------------------------------------- #
@callback(
    Output("pb-scan-interval", "disabled"),
    Output("pb-scan-status", "children"),
    Output("pb-tag-uid", "value", allow_duplicate=True),
    Input("pb-scan-start", "n_clicks"),
    prevent_initial_call=True,
)
def start_scan(_n):
    get_core().scan_state.start_register()
    return False, "Waiting for a tag… hold one to the reader.", ""


@callback(
    Output("pb-tag-uid", "value"),
    Output("pb-scan-seq", "data"),
    Output("pb-scan-interval", "disabled", allow_duplicate=True),
    Output("pb-scan-status", "children", allow_duplicate=True),
    Input("pb-scan-interval", "n_intervals"),
    State("pb-scan-seq", "data"),
    prevent_initial_call=True,
)
def poll_scan(_n, last_seq):
    core = get_core()
    captured = core.scan_state.captured()
    if captured and captured.seq != last_seq:
        return captured.uid, captured.seq, True, f"Captured UID {captured.uid}."
    # Still waiting (or scanning was cancelled elsewhere).
    if core.scan_state.mode is not Mode.REGISTER:
        return no_update, no_update, True, no_update
    return no_update, no_update, no_update, no_update


@callback(
    Output("pb-tag-save-status", "children"),
    Output("pb-tags-table", "children", allow_duplicate=True),
    Input("pb-tag-save", "n_clicks"),
    State("pb-tag-uid", "value"),
    State("pb-tag-name", "value"),
    State("pb-tag-desc", "value"),
    State("pb-tag-callback", "value"),
    State("pb-tag-args", "value"),
    prevent_initial_call=True,
)
def save_tag(_n, uid, name, desc, cb, args_text):
    if not uid:
        return "Scan a tag first (UID is empty).", no_update
    if not cb:
        return "Choose a callback.", no_update
    try:
        args = json.loads(args_text) if args_text and args_text.strip() else {}
        if not isinstance(args, dict):
            raise ValueError("args must be a JSON object")
    except (ValueError, json.JSONDecodeError) as exc:
        return f"Invalid args JSON: {exc}", no_update

    core = get_core()
    core.upsert_tag(TagConfig(id=uid, callback=cb, name=name or "", description=desc or "", args=args))
    return f"Saved tag {uid.upper()} → {cb}.", render_tags_table()


@callback(
    Output("pb-tags-table", "children", allow_duplicate=True),
    Input({"type": "pb-del-tag", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def delete_tag(_clicks):
    trigger = ctx.triggered_id
    if not trigger or not isinstance(trigger, dict):
        return no_update
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    get_core().delete_tag(trigger["index"])
    return render_tags_table()


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@callback(
    Output("pb-set-status", "children"),
    Input("pb-set-save", "n_clicks"),
    State("pb-set-music", "value"),
    State("pb-set-audio", "value"),
    State("pb-set-volume", "value"),
    prevent_initial_call=True,
)
def save_settings(_n, music, audio, volume):
    core = get_core()
    try:
        core.update_settings(
            music_dir=music,
            audio_device=audio or "auto",
            volume=int(volume) if volume is not None else core.settings.volume,
        )
    except Exception as exc:  # noqa: BLE001
        return f"Failed to save: {exc}"
    return "Settings saved. (Audio device change needs a restart.)"
