# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What playbox is

playbox is a Raspberry Pi Zero 2W based **offline** music player controlled three ways — hardware buttons, RFID tags, and a Plotly Dash web app. It targets a fixed hardware stack: **WM8960 Audio HAT** (I2C codec control + I2S audio), **RC522 RFID reader** (SPI, interrupt-driven via the IRQ pin), and **GPIO** buttons. OS is **DietPi**. See [`pinout.md`](pinout.md) for the authoritative pin map.

## Development workflow (important)

- **Code is developed on a dev PC and deployed to the Pi to test.** Do **not** create/run the uv venv, install packages, or run hardware code on the dev PC — that all happens on the Pi. Author code, config, scripts, and docs only.
- The app is designed to import and run without hardware: `hardware/rfid.py`, `hardware/buttons.py`, and `player.py` all degrade to no-ops (logged warnings) when their libs/devices are absent, so the web app can be worked on off-device.
- On the Pi: `sudo bash scripts/install.sh` provisions everything (packages, SPI/I2C, WM8960 driver, `uv tool install '.[pi]'`, systemd). Then `systemctl {status,restart} playbox` and `journalctl -u playbox -f`.
- Dev run (off-device): `uv sync` then `PLAYBOX_CONFIG_DIR=./config uv run playbox`.

## Architecture

Single process, one systemd service. A shared `PlayboxCore` (`src/playbox/core.py`) owns the player, callback registry, config, library and scan state. Three input sources feed **one callback dispatcher**:

- **RFIDService** (`hardware/rfid.py`) — interrupt-driven via the RC522 IRQ pin (GPIO24); it does **not** poll SPI. Two modes via `ScanState`: NORMAL dispatches the tag's callback; REGISTER captures the next UID for the web Setup page (tag registration) instead of dispatching.
- **ButtonService** (`hardware/buttons.py`) — gpiozero buttons → callbacks.
- **Dash web app** (`web/`) — multi-page (Play/Control/Setup). The core is stored as a module global in `web/server.py` (`get_core()`); page modules are auto-discovered by Dash and use **absolute imports** (`from playbox.web.server import get_core`) because Dash may import them under a non-package name.

The **callback registry** (`callbacks.py`) maps YAML callback names → functions; `@registry.callback("name")` registers new ones. Every callback receives the shared `PlayerController` plus the YAML `args` as kwargs. This is the extension point — "callbacks can be anything."

Config (`config.py`): `settings.yaml`, `tags.yaml`, `buttons.yaml`. Defaults ship as package data under `src/playbox/defaults/` and seed the config dir on first run. `tags.yaml` is written by the app (web Setup page → `core.upsert_tag`).

## Key constraints

- **Offline is hard-required**: no network dependency at playback time (mpv is configured with `ytdl=False`). Network is for setup only.
- **Pin choices**: button pins in `buttons.yaml` must avoid the SPI/I2C/I2S pins used by the RC522 and WM8960 (see `pinout.md`).
- **Installable package**: keep it `pip`/`uv`-installable with the `playbox` console entry point; hardware-only deps live in the `[pi]` optional-dependencies extra so plain `pip install .` still works on a dev box.
