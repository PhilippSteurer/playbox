"""Dash application factory.

The shared :class:`~playbox.core.PlayboxCore` is stored in a module global so the
page modules (auto-imported by Dash's pages feature) can reach it via
``get_core()`` inside their layouts and callbacks. ``create_app`` sets the core
*before* constructing the ``Dash`` app, because constructing it triggers import
of the page modules.
"""

from __future__ import annotations

import logging

from ..core import PlayboxCore

log = logging.getLogger(__name__)

_CORE: PlayboxCore | None = None


def get_core() -> PlayboxCore:
    if _CORE is None:
        raise RuntimeError("PlayboxCore has not been initialised")
    return _CORE


def create_app(core: PlayboxCore):
    global _CORE
    _CORE = core

    import dash
    from dash import Dash, dcc, html

    app = Dash(
        __name__,
        use_pages=True,
        pages_folder="pages",
        title="playbox",
        suppress_callback_exceptions=True,
    )

    nav = html.Nav(
        className="pb-nav",
        children=[
            html.Span("🎵 playbox", className="pb-brand"),
            dcc.Link("Play", href="/"),
            dcc.Link("Control", href="/control"),
            dcc.Link("Setup", href="/setup"),
        ],
    )

    app.layout = html.Div(
        className="pb-app",
        children=[
            dcc.Location(id="pb-url"),
            nav,
            html.Main(dash.page_container, className="pb-main"),
        ],
    )
    return app
