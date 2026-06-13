"""RC522 RFID reader service — interrupt-driven via the IRQ pin.

Rather than polling the card over SPI in a tight loop, this uses pi-rc522's
``wait_for_tag()``, which arms the RC522's IRQ register and blocks on the GPIO
interrupt event (RST=GPIO24/IRQ wiring per pinout.md) until a card is present
or the wait is interrupted for shutdown. It does not poll the card itself.

The RFID stack on the Pi is ``pi-rc522`` (imported as ``pirc522``) plus
``rpi-lgpio`` — an lgpio-backed drop-in for ``RPi.GPIO``, because the stock
``RPi.GPIO`` fails with "Failed to add edge detection" on current kernels.

On a machine without the RFID library/hardware (e.g. a dev PC), the service
logs a warning and does nothing, so the rest of the app still runs.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from ..config import Settings, TagConfig
from ..scan_state import ScanState

log = logging.getLogger(__name__)

# Wiring per pinout.md: RST=GPIO25, IRQ=GPIO24, CE0=GPIO8. pi-rc522 uses BOARD
# pin numbering by default, and its defaults (RST=BOARD 22, IRQ=BOARD 18, CE0)
# map to exactly these BCM pins (BOARD 22 -> BCM25, BOARD 18 -> BCM24). So the
# reader is constructed with bare RFID() — passing BCM numbers here would target
# the wrong physical pins.


def uid_to_str(uid: list[int]) -> str:
    """Format an anticoll UID (list of ints, last byte is BCC) as hex."""
    return "".join(f"{b:02X}" for b in uid[:4])


class RFIDService:
    def __init__(
        self,
        settings: Settings,
        scan_state: ScanState,
        on_tag: Callable[[TagConfig], None],
        tag_lookup: Callable[[str], TagConfig | None],
    ) -> None:
        self.settings = settings
        self.scan_state = scan_state
        self._on_tag = on_tag
        self._tag_lookup = tag_lookup

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rfid = None
        self._last_uid: str | None = None
        self._last_time = 0.0

    # -- lifecycle ---------------------------------------------------------- #
    def start(self) -> None:
        try:
            from pirc522 import RFID  # provided by pi-rc522
        except Exception as exc:  # noqa: BLE001
            log.warning("RFID reader disabled (library/hardware unavailable): %s", exc)
            return

        try:
            # Bare RFID(): its BOARD-numbering defaults map to our BCM25/24/CE0
            # wiring (see module note). Passing BCM numbers would be wrong.
            self._rfid = RFID()
        except Exception as exc:  # noqa: BLE001
            log.warning("RFID reader disabled (init failed): %s", exc)
            self._rfid = None
            return

        self._thread = threading.Thread(target=self._run, name="rfid", daemon=True)
        self._thread.start()
        log.info("RFID service started (interrupt-driven via IRQ pin)")

    def stop(self) -> None:
        self._stop.set()
        rfid = self._rfid
        if rfid is not None:
            # Break any in-progress IRQ wait, then release GPIO/SPI.
            irq = getattr(rfid, "irq", None)
            if irq is not None:
                irq.set()
            if self._thread is not None:
                self._thread.join(timeout=2.0)
            try:
                rfid.cleanup()
            except Exception:  # noqa: BLE001
                pass

    # -- main loop ---------------------------------------------------------- #
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                # Interrupt-driven: blocks on the RC522 IRQ until a card is
                # present, or until stop() sets the reader's irq event.
                self._rfid.wait_for_tag()
                if self._stop.is_set():
                    break
                uid = self._read_uid()
                if uid is None:
                    continue
                self._handle_uid(uid)
            except Exception:  # noqa: BLE001 - keep the reader alive
                log.exception("RFID loop error")
                time.sleep(0.2)

    def _read_uid(self) -> str | None:
        r = self._rfid
        error, _ = r.request()
        if error:
            return None
        error, uid = r.anticoll()
        if error:
            return None
        try:
            r.stop_crypto()  # release the card after a successful read
        except Exception:  # noqa: BLE001
            pass
        return uid_to_str(uid)

    def _handle_uid(self, uid: str) -> None:
        # Debounce a tag that is held to the reader.
        now = time.monotonic()
        if uid == self._last_uid and (now - self._last_time) < self.settings.rfid_debounce:
            return
        self._last_uid = uid
        self._last_time = now

        from ..scan_state import Mode

        if self.scan_state.mode is Mode.REGISTER:
            log.info("Captured tag UID %s for registration", uid)
            self.scan_state.capture(uid)
            return

        tag = self._tag_lookup(uid)
        if tag is None:
            log.info("Unknown tag %s (not configured)", uid)
            return
        log.info("Tag %s -> %s(%s)", uid, tag.callback, tag.args)
        self._on_tag(tag)
