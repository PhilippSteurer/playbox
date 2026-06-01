"""Configuration loading and persistence.

playbox keeps three YAML files in a config directory:

* ``settings.yaml`` — runtime settings (music dir, audio device, web port, ...)
* ``tags.yaml``     — RFID UID -> callback mappings (written by the web app)
* ``buttons.yaml``  — GPIO pin -> callback mappings

The config directory is resolved (in order) from:

1. the ``PLAYBOX_CONFIG_DIR`` environment variable, if set;
2. ``<repo>/config`` when running from a source checkout (this file lives at
   ``src/playbox/config.py`` so the repo root is three parents up);
3. ``~/.config/playbox`` otherwise.

On first use any missing file is seeded from the defaults shipped inside the
package (``playbox/defaults/*.yaml``), so a fresh install is self-contained.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

_DEFAULT_FILES = ("settings.yaml", "tags.yaml", "buttons.yaml")


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    music_dir: Path = Path("/mnt/dietpi_userdata/music")
    audio_device: str = "auto"
    volume: int = 70
    web_host: str = "0.0.0.0"
    web_port: int = 8050
    rfid_wait_timeout: float = 0.5
    rfid_debounce: float = 1.0

    @property
    def playlists_dir(self) -> Path:
        return self.music_dir / "playlists"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        data = dict(data or {})
        if "music_dir" in data:
            data["music_dir"] = Path(data["music_dir"]).expanduser()
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(data) - known
        for key in unknown:
            log.warning("Ignoring unknown setting %r in settings.yaml", key)
            data.pop(key)
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "music_dir": str(self.music_dir),
            "audio_device": self.audio_device,
            "volume": self.volume,
            "web_host": self.web_host,
            "web_port": self.web_port,
            "rfid_wait_timeout": self.rfid_wait_timeout,
            "rfid_debounce": self.rfid_debounce,
        }


@dataclass
class TagConfig:
    id: str
    callback: str
    name: str = ""
    description: str = ""
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "callback": self.callback,
            "args": dict(self.args),
        }


@dataclass
class ButtonConfig:
    pin: int
    callback: str
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    bounce_time: float | None = None


# --------------------------------------------------------------------------- #
# Config directory resolution + seeding
# --------------------------------------------------------------------------- #
def resolve_config_dir() -> Path:
    env = os.environ.get("PLAYBOX_CONFIG_DIR")
    if env:
        return Path(env).expanduser()

    repo_config = Path(__file__).resolve().parents[2] / "config"
    if repo_config.parent.joinpath("pyproject.toml").exists():
        # Running from a source checkout: prefer the repo's config/ dir.
        return repo_config

    return Path.home() / ".config" / "playbox"


def ensure_config_dir(config_dir: Path | None = None) -> Path:
    """Create the config dir and seed any missing files from packaged defaults."""
    config_dir = config_dir or resolve_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    defaults = resources.files("playbox").joinpath("defaults")
    for name in _DEFAULT_FILES:
        target = config_dir / name
        if not target.exists():
            content = defaults.joinpath(name).read_text(encoding="utf-8")
            target.write_text(content, encoding="utf-8")
            log.info("Seeded default config %s", target)
    return config_dir


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _write_yaml(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
    tmp.replace(path)  # atomic on POSIX


# --------------------------------------------------------------------------- #
# Loaders / savers
# --------------------------------------------------------------------------- #
def load_settings(config_dir: Path) -> Settings:
    data = _read_yaml(config_dir / "settings.yaml") or {}
    return Settings.from_dict(data)


def save_settings(config_dir: Path, settings: Settings) -> None:
    _write_yaml(config_dir / "settings.yaml", settings.to_dict())


def load_tags(config_dir: Path, known_callbacks: set[str] | None = None) -> list[TagConfig]:
    data = _read_yaml(config_dir / "tags.yaml") or {}
    tags: list[TagConfig] = []
    for entry in data.get("tags", []) or []:
        if "id" not in entry or "callback" not in entry:
            log.warning("Skipping tag entry without id/callback: %r", entry)
            continue
        if known_callbacks is not None and entry["callback"] not in known_callbacks:
            log.warning(
                "Tag %s references unknown callback %r; skipping",
                entry.get("id"), entry["callback"],
            )
            continue
        tags.append(
            TagConfig(
                id=str(entry["id"]).upper(),
                callback=entry["callback"],
                name=entry.get("name", ""),
                description=entry.get("description", ""),
                args=entry.get("args") or {},
            )
        )
    return tags


def save_tags(config_dir: Path, tags: list[TagConfig]) -> None:
    _write_yaml(config_dir / "tags.yaml", {"tags": [t.to_dict() for t in tags]})


def load_buttons(config_dir: Path, known_callbacks: set[str] | None = None) -> list[ButtonConfig]:
    data = _read_yaml(config_dir / "buttons.yaml") or {}
    buttons: list[ButtonConfig] = []
    for entry in data.get("buttons", []) or []:
        if "pin" not in entry or "callback" not in entry:
            log.warning("Skipping button entry without pin/callback: %r", entry)
            continue
        if known_callbacks is not None and entry["callback"] not in known_callbacks:
            log.warning(
                "Button on pin %s references unknown callback %r; skipping",
                entry.get("pin"), entry["callback"],
            )
            continue
        buttons.append(
            ButtonConfig(
                pin=int(entry["pin"]),
                callback=entry["callback"],
                name=entry.get("name", ""),
                args=entry.get("args") or {},
                bounce_time=entry.get("bounce_time"),
            )
        )
    return buttons
