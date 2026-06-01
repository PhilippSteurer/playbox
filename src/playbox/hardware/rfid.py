"""RC522 RFID reader service — interrupt-driven via the IRQ pin.

Rather than polling the card over SPI in a tight loop, this arms the RC522's
IRQ register and blocks on the GPIO interrupt event (pin GPIO24 per pinout.md).
The wait uses a short timeout purely so the thread can notice a stop request;
it does not poll the card itself.

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

# Pins from pinout.md (BCM numbering).
PIN_RST = 25
PIN_IRQ = 24
PIN_CE = 0  # SPI0 CE0 -> GPIO8


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
            from pirc522 import RFID  # provided by pi-rc522-gpiozero
        except Exception as exc:  # noqa: BLE001
            log.warning("RFID reader disabled (library/hardware unavailable): %s", exc)
            return

        try:
            self._rfid = RFID(pin_rst=PIN_RST, pin_irq=PIN_IRQ, pin_ce=PIN_CE)
        except Exception as exc:  # noqa: BLE001
            log.warning("RFID reader disabled (init failed): %s", exc)
            self._rfid = None
            return

        self._thread = threading.Thread(target=self._run, name="rfid", daemon=True)
        self._thread.start()
        log.info("RFID service started (IRQ on GPIO%d)", PIN_IRQ)

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
        timeout = self.settings.rfid_wait_timeout
        while not self._stop.is_set():
            try:
                if not self._arm_and_wait(timeout):
                    continue  # timed out: re-check stop flag, re-arm
                uid = self._read_uid()
                if uid is None:
                    continue
                self._handle_uid(uid)
            except Exception:  # noqa: BLE001 - keep the reader alive
                log.exception("RFID loop error")
                time.sleep(0.2)

    def _arm_and_wait(self, timeout: float) -> bool:
        """Arm the RC522 IRQ for card detection and wait on the interrupt.

        Returns True if the IRQ fired (a card is likely present), False on
        timeout. Falls back to the library's blocking ``wait_for_tag`` if the
        low-level register API isn't available.
        """
        r = self._rfid
        irq = getattr(r, "irq", None)
        if irq is not None and hasattr(r, "dev_write") and hasattr(r, "init"):
            r.init()
            irq.clear()
            r.dev_write(0x04, 0x00)
            r.dev_write(0x02, 0xA0)  # enable RxIRq on the IRQ pin
            r.dev_write(0x09, 0x26)  # REQA
            r.dev_write(0x01, 0x0C)  # transceive
            r.dev_write(0x0D, 0x87)  # start transmission
            fired = irq.wait(timeout)
            irq.clear()
            return fired and not self._stop.is_set()
        # Fallback: blocking wait (no timeout-based stop responsiveness).
        r.wait_for_tag()
        return not self._stop.is_set()

    def _read_uid(self) -> str | None:
        r = self._rfid
        error, _ = r.request()
        if error:
            return None
        error, uid = r.anticoll()
        if error:
            return None
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
