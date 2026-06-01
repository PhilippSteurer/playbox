"""Music library: discover tracks and playlists under the music directory.

Layout assumed::

    <music_dir>/
        any/nested/track.mp3
        playlists/
            my_playlist.m3u

Track paths are handled relative to ``music_dir`` so they stay portable between
the dev PC and the Pi.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wav", ".wma",
}
PLAYLIST_EXTENSIONS = {".m3u", ".m3u8"}


class Library:
    def __init__(self, music_dir: Path) -> None:
        self.music_dir = Path(music_dir)
        self.playlists_dir = self.music_dir / "playlists"

    # -- tracks ------------------------------------------------------------- #
    def tracks(self) -> list[str]:
        """All audio files under music_dir, as paths relative to music_dir."""
        if not self.music_dir.is_dir():
            log.warning("Music dir %s does not exist", self.music_dir)
            return []
        found: list[str] = []
        for path in sorted(self.music_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                if self.playlists_dir in path.parents:
                    continue
                found.append(str(path.relative_to(self.music_dir)))
        return found

    def resolve_track(self, track: str) -> Path:
        """Resolve a track path (relative or absolute) to an absolute path,
        guarding against escaping the music dir."""
        candidate = Path(track)
        path = candidate if candidate.is_absolute() else (self.music_dir / candidate)
        path = path.resolve()
        music_root = self.music_dir.resolve()
        if music_root not in path.parents and path != music_root:
            raise ValueError(f"Track {track!r} is outside the music directory")
        return path

    # -- playlists ---------------------------------------------------------- #
    def playlists(self) -> list[str]:
        """Names (without extension) of playlists under playlists/."""
        if not self.playlists_dir.is_dir():
            return []
        return sorted(
            p.stem
            for p in self.playlists_dir.iterdir()
            if p.is_file() and p.suffix.lower() in PLAYLIST_EXTENSIONS
        )

    def playlist_path(self, name: str) -> Path:
        for ext in (".m3u", ".m3u8"):
            candidate = self.playlists_dir / f"{name}{ext}"
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"Playlist {name!r} not found in {self.playlists_dir}")

    def playlist_tracks(self, name: str) -> list[Path]:
        """Resolve the (existing) tracks listed in a playlist to absolute paths."""
        path = self.playlist_path(name)
        tracks: list[Path] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entry = Path(line)
            resolved = entry if entry.is_absolute() else (self.music_dir / entry)
            if resolved.exists():
                tracks.append(resolved)
            else:
                log.warning("Playlist %s references missing track %s", name, line)
        return tracks
