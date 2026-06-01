"""Thread-safe coordination between the RFID reader and the web Setup page.

The RFID reader normally dispatches callbacks for known tags. When the user
clicks "Register tag" in the web UI, the reader is switched to REGISTER mode:
the next UID seen is captured here (instead of being dispatched) so the web page
can poll for it, build a tag config, and switch the reader back to NORMAL.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum


class Mode(str, Enum):
    NORMAL = "normal"
    REGISTER = "register"


@dataclass(frozen=True)
class CapturedTag:
    uid: str
    seq: int  # increments each capture so the UI can detect a fresh scan


class ScanState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mode = Mode.NORMAL
        self._captured: CapturedTag | None = None
        self._seq = 0

    @property
    def mode(self) -> Mode:
        with self._lock:
            return self._mode

    def start_register(self) -> None:
        """Enter REGISTER mode and clear any previously captured UID."""
        with self._lock:
            self._mode = Mode.REGISTER
            self._captured = None

    def cancel_register(self) -> None:
        with self._lock:
            self._mode = Mode.NORMAL
            self._captured = None

    def capture(self, uid: str) -> None:
        """Called by the RFID reader when in REGISTER mode. Stores the UID and
        returns to NORMAL mode so a single scan completes registration."""
        with self._lock:
            self._seq += 1
            self._captured = CapturedTag(uid=uid, seq=self._seq)
            self._mode = Mode.NORMAL

    def captured(self) -> CapturedTag | None:
        with self._lock:
            return self._captured
