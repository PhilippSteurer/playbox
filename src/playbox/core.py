"""Shared application core wiring together player, registry, library and config.

A single :class:`PlayboxCore` instance is created at startup and shared by every
input source (RFID service, button service, web app). It centralises dispatch
and tag persistence so the web Setup page and the hardware services stay in
sync.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import config as config_mod
from .callbacks import CallbackRegistry, build_default_registry
from .config import ButtonConfig, Settings, TagConfig
from .library import Library
from .player import PlayerController
from .scan_state import ScanState

log = logging.getLogger(__name__)


class PlayboxCore:
    def __init__(self, config_dir: Path, player_factory=PlayerController) -> None:
        self.config_dir = config_dir
        self.registry: CallbackRegistry = build_default_registry()
        self.settings: Settings = config_mod.load_settings(config_dir)
        self.library = Library(self.settings.music_dir)
        self.scan_state = ScanState()

        known = set(self.registry.names())
        self.tags: list[TagConfig] = config_mod.load_tags(config_dir, known)
        self.buttons: list[ButtonConfig] = config_mod.load_buttons(config_dir, known)

        # The player needs libmpv; allow it to be absent (dev box without mpv).
        try:
            self.player = player_factory(
                self.library,
                audio_device=self.settings.audio_device,
                volume=self.settings.volume,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Player disabled (libmpv unavailable?): %s", exc)
            self.player = None

    # -- dispatch ----------------------------------------------------------- #
    def dispatch(self, callback: str, args: dict) -> None:
        if self.player is None:
            log.warning("Ignoring callback %r: no player available", callback)
            return
        self.registry.dispatch(callback, self.player, **(args or {}))

    def dispatch_tag(self, tag: TagConfig) -> None:
        self.dispatch(tag.callback, tag.args)

    def dispatch_button(self, button: ButtonConfig) -> None:
        self.dispatch(button.callback, button.args)

    # -- tag lookup / persistence ------------------------------------------ #
    def find_tag(self, uid: str) -> TagConfig | None:
        uid = uid.upper()
        for tag in self.tags:
            if tag.id.upper() == uid:
                return tag
        return None

    def upsert_tag(self, tag: TagConfig) -> None:
        """Add or replace a tag (matched by UID) and persist to tags.yaml."""
        tag.id = tag.id.upper()
        self.tags = [t for t in self.tags if t.id.upper() != tag.id] + [tag]
        config_mod.save_tags(self.config_dir, self.tags)
        log.info("Saved tag %s (%s)", tag.id, tag.callback)

    def delete_tag(self, uid: str) -> None:
        uid = uid.upper()
        self.tags = [t for t in self.tags if t.id.upper() != uid]
        config_mod.save_tags(self.config_dir, self.tags)
        log.info("Deleted tag %s", uid)

    # -- settings ----------------------------------------------------------- #
    def update_settings(self, **changes) -> None:
        """Apply and persist setting changes. Some (audio device) only take
        effect after a restart; volume is applied live when possible."""
        if "music_dir" in changes and changes["music_dir"] is not None:
            changes["music_dir"] = Path(str(changes["music_dir"])).expanduser()
        for key, value in changes.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        config_mod.save_settings(self.config_dir, self.settings)
        if "music_dir" in changes:
            self.library = Library(self.settings.music_dir)
        if "volume" in changes and self.player is not None:
            self.player.set_volume(int(self.settings.volume))
        log.info("Settings updated: %s", ", ".join(changes))
