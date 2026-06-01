"""GPIO push-button service using gpiozero.

Each configured button (by BCM pin) dispatches a callback on press, sharing the
same callback registry as RFID tags. Buttons use a debounce (``bounce_time``)
per pinout.md's 50-100 ms recommendation.

On a machine without gpiozero/GPIO hardware, the service logs a warning and
does nothing.
"""

from __future__ import annotations

import logging
from typing import Callable

from ..config import ButtonConfig

log = logging.getLogger(__name__)

DEFAULT_BOUNCE_TIME = 0.075  # 75 ms, within the 50-100 ms guidance


class ButtonService:
    def __init__(
        self,
        buttons: list[ButtonConfig],
        on_press: Callable[[ButtonConfig], None],
    ) -> None:
        self._configs = buttons
        self._on_press = on_press
        self._buttons: list = []  # keep gpiozero.Button refs alive

    def start(self) -> None:
        if not self._configs:
            log.info("No buttons configured")
            return
        try:
            from gpiozero import Button
        except Exception as exc:  # noqa: BLE001
            log.warning("Buttons disabled (gpiozero/hardware unavailable): %s", exc)
            return

        for cfg in self._configs:
            try:
                bounce = cfg.bounce_time if cfg.bounce_time is not None else DEFAULT_BOUNCE_TIME
                button = Button(cfg.pin, bounce_time=bounce)
                # Bind via default arg to capture the current cfg.
                button.when_pressed = lambda c=cfg: self._on_press(c)
                self._buttons.append(button)
                log.info("Button GPIO%d -> %s(%s) [%s]", cfg.pin, cfg.callback, cfg.args, cfg.name)
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to set up button on GPIO%d: %s", cfg.pin, exc)

    def stop(self) -> None:
        for button in self._buttons:
            try:
                button.close()
            except Exception:  # noqa: BLE001
                pass
        self._buttons.clear()
