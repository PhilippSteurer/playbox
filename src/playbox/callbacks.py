"""Callback registry shared by RFID tags and GPIO buttons.

A *callback* is a named function invoked when a tag is read or a button pressed.
The mapping from a name (a string stored in YAML) to a function lives in a
``CallbackRegistry``. Built-in callbacks are registered below, but the registry
is open: decorate any function with ``@registry.callback("my_name")`` and it
becomes referenceable from ``tags.yaml`` / ``buttons.yaml``.

Every callback receives the shared :class:`~playbox.player.PlayerController` as
its first positional argument, plus whatever keyword ``args`` the YAML entry
supplies.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any, Callable

log = logging.getLogger(__name__)

CallbackFn = Callable[..., Any]


class CallbackRegistry:
    """Maps callback names to functions and dispatches them safely."""

    def __init__(self) -> None:
        self._callbacks: dict[str, CallbackFn] = {}

    def callback(self, name: str) -> Callable[[CallbackFn], CallbackFn]:
        """Decorator registering ``fn`` under ``name``."""

        def decorator(fn: CallbackFn) -> CallbackFn:
            if name in self._callbacks:
                log.warning("Overriding already-registered callback %r", name)
            self._callbacks[name] = fn
            return fn

        return decorator

    def register(self, name: str, fn: CallbackFn) -> None:
        self._callbacks[name] = fn

    def names(self) -> list[str]:
        return sorted(self._callbacks)

    def __contains__(self, name: str) -> bool:
        return name in self._callbacks

    def dispatch(self, name: str, player: "Any", **args: Any) -> None:
        """Invoke ``name`` with ``player`` and ``args``; never raise.

        A failing callback (bad args, unknown name, player error) is logged but
        does not propagate, so one misconfigured tag/button can't take down the
        RFID loop or button handler thread.
        """
        fn = self._callbacks.get(name)
        if fn is None:
            log.error("No callback registered under %r", name)
            return
        try:
            fn(player, **args)
        except Exception:  # noqa: BLE001 - we deliberately swallow & log
            log.exception("Callback %r failed (args=%r)", name, args)


def build_default_registry() -> CallbackRegistry:
    """Create a registry populated with the built-in callbacks."""
    registry = CallbackRegistry()

    @registry.callback("play_track")
    def play_track(player, track: str, **_: Any) -> None:
        """Play a single track. ``track`` is a path relative to the music dir."""
        player.play_track(track)

    @registry.callback("play_playlist")
    def play_playlist(player, playlist: str, **_: Any) -> None:
        """Play a named playlist (a .m3u/.m3u8 file under playlists/)."""
        player.play_playlist(playlist)

    @registry.callback("play")
    def play(player, **_: Any) -> None:
        """Resume playback."""
        player.play()

    @registry.callback("pause")
    def pause(player, **_: Any) -> None:
        """Pause playback."""
        player.pause()

    @registry.callback("toggle")
    def toggle(player, **_: Any) -> None:
        """Toggle play/pause."""
        player.toggle()

    @registry.callback("stop")
    def stop(player, **_: Any) -> None:
        """Stop playback and clear the queue."""
        player.stop()

    @registry.callback("next")
    def next_track(player, **_: Any) -> None:
        """Skip to the next track in the queue."""
        player.next()

    @registry.callback("previous")
    def previous_track(player, **_: Any) -> None:
        """Go to the previous track in the queue."""
        player.previous()

    @registry.callback("volume")
    def volume(player, delta: int | None = None, level: int | None = None, **_: Any) -> None:
        """Change volume. Pass ``level`` to set absolute (0-100) or ``delta``
        to adjust relative."""
        if level is not None:
            player.set_volume(int(level))
        elif delta is not None:
            player.set_volume(player.volume + int(delta))

    @registry.callback("shutdown")
    def shutdown(player, **_: Any) -> None:
        """Halt the system. Requires the service user to have passwordless
        ``sudo shutdown`` (configured by install.sh)."""
        player.stop()
        subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)

    return registry
