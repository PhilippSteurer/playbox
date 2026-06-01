"""Audio playback via an in-process libmpv instance (python-mpv).

A single :class:`PlayerController` owns one ``mpv.MPV`` instance and is shared by
every input source (RFID, buttons, web). python-mpv is safe to send commands to
from multiple threads, which is what we rely on here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .library import Library

log = logging.getLogger(__name__)


class PlayerController:
    def __init__(self, library: Library, audio_device: str = "auto", volume: int = 70) -> None:
        self.library = library
        self._volume = max(0, min(100, int(volume)))

        import mpv  # imported here so the module imports even if libmpv is absent

        mpv_kwargs: dict[str, Any] = {
            "ytdl": False,            # fully offline
            "video": False,           # audio only
            "volume": self._volume,
        }
        if audio_device and audio_device != "auto":
            mpv_kwargs["audio_device"] = audio_device

        self._mpv = mpv.MPV(**mpv_kwargs)
        log.info("mpv initialised (audio_device=%s, volume=%d)", audio_device, self._volume)

    # -- queue / tracks ----------------------------------------------------- #
    def play_track(self, track: str) -> None:
        path = self.library.resolve_track(track)
        log.info("Playing track %s", path)
        self._mpv.play(str(path))
        self._mpv.pause = False

    def play_playlist(self, name: str) -> None:
        tracks = self.library.playlist_tracks(name)
        if not tracks:
            log.warning("Playlist %r is empty or missing; nothing to play", name)
            return
        log.info("Playing playlist %r (%d tracks)", name, len(tracks))
        self._mpv.playlist_clear()
        self._mpv.play(str(tracks[0]))
        for track in tracks[1:]:
            self._mpv.playlist_append(str(track))
        self._mpv.pause = False

    # -- transport ---------------------------------------------------------- #
    def play(self) -> None:
        self._mpv.pause = False

    def pause(self) -> None:
        self._mpv.pause = True

    def toggle(self) -> None:
        self._mpv.pause = not self._mpv.pause

    def stop(self) -> None:
        self._mpv.command("stop")

    def next(self) -> None:
        try:
            self._mpv.playlist_next("weak")
        except Exception:  # noqa: BLE001 - no next item
            log.debug("No next track")

    def previous(self) -> None:
        try:
            self._mpv.playlist_prev("weak")
        except Exception:  # noqa: BLE001 - no previous item
            log.debug("No previous track")

    # -- volume ------------------------------------------------------------- #
    @property
    def volume(self) -> int:
        return self._volume

    def set_volume(self, level: int) -> None:
        self._volume = max(0, min(100, int(level)))
        self._mpv.volume = self._volume
        log.info("Volume set to %d", self._volume)

    # -- introspection for the web UI --------------------------------------- #
    def now_playing(self) -> dict[str, Any]:
        def safe(attr: str, default: Any = None) -> Any:
            try:
                return getattr(self._mpv, attr)
            except Exception:  # noqa: BLE001
                return default

        media_title = safe("media_title")
        filename = safe("filename")
        path = safe("path")
        title = media_title or filename or (Path(path).name if path else None)
        return {
            "title": title,
            "paused": bool(safe("pause", True)),
            "idle": bool(safe("idle_active", True)),
            "position": safe("time_pos"),
            "duration": safe("duration"),
            "volume": self._volume,
            "playlist_pos": safe("playlist_pos"),
            "playlist_count": safe("playlist_count"),
        }

    def shutdown(self) -> None:
        """Release the mpv instance (called on service shutdown)."""
        try:
            self._mpv.terminate()
        except Exception:  # noqa: BLE001
            log.debug("mpv terminate raised during shutdown", exc_info=True)
