"""playbox entry point.

Wires the shared core to the hardware input services and the Dash web server,
then runs until interrupted, cleaning up on the way out.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from .config import ensure_config_dir, resolve_config_dir
from .core import PlayboxCore
from .hardware.buttons import ButtonService
from .hardware.rfid import RFIDService
from .web.server import create_app

log = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="playbox", description="Offline music player for Raspberry Pi.")
    p.add_argument("--config-dir", help="Override the config directory.")
    p.add_argument("--host", help="Override the web bind host.")
    p.add_argument("--port", type=int, help="Override the web port.")
    p.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    config_dir = args.config_dir or resolve_config_dir()
    config_dir = ensure_config_dir(config_dir)
    log.info("Using config dir %s", config_dir)

    core = PlayboxCore(config_dir)

    rfid = RFIDService(
        settings=core.settings,
        scan_state=core.scan_state,
        on_tag=core.dispatch_tag,
        tag_lookup=core.find_tag,
    )
    buttons = ButtonService(buttons=core.buttons, on_press=core.dispatch_button)

    rfid.start()
    buttons.start()

    app = create_app(core)
    host = args.host or core.settings.web_host
    port = args.port or core.settings.web_port

    def _shutdown(*_a) -> None:
        log.info("Shutting down…")
        rfid.stop()
        buttons.stop()
        if core.player is not None:
            core.player.shutdown()

    # Handle SIGTERM (systemd stop) gracefully in addition to KeyboardInterrupt.
    signal.signal(signal.SIGTERM, lambda *_: (_shutdown(), sys.exit(0)))

    log.info("Starting web interface on http://%s:%d", host, port)
    try:
        app.run(host=host, port=port, debug=False)
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
