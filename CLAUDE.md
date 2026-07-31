# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What playbox is

playbox is a Raspberry Pi Zero 2W based **offline** music player controlled three ways — hardware buttons, RFID tags, and a Plotly Dash web app. It targets a fixed hardware stack: **WM8960 Audio HAT** (I2C codec control + I2S audio), **RC522 RFID reader** (SPI, interrupt-driven via the IRQ pin), and **GPIO** buttons. OS is **Raspberry Pi OS Lite (32-bit)**, trixie, kernel 6.18. See [`pinout.md`](pinout.md) for the authoritative pin map.

## Development workflow (important)

- **Code is developed on a dev PC and deployed to the Pi to test.** Do **not** create/run the venv, install packages, or run hardware code on the dev PC — that all happens on the Pi. Author code, config, scripts, and docs only.
- **Keep the setup simple and manual.** The user deliberately removed `install.sh`, the DietPi first-boot hook and the systemd unit; the app is started by hand. Don't reintroduce provisioning automation, and explain system-level changes rather than scripting them — the user applies those themselves (README section 7 has the systemd unit as copy-paste text for when they want it).
- The app is designed to import and run without hardware: `hardware/rfid.py`, `hardware/buttons.py`, and `player.py` all degrade to no-ops (logged warnings) when their libs/devices are absent, so the web app can be worked on off-device.
- **On the Pi:** OS prerequisites are set up by hand (see README section 2); then `python3 -m venv --system-site-packages .venv && source .venv/bin/activate && pip install . && pip install --no-deps pi-rc522`, then run `playbox` in a terminal (or tmux). Logs go to stdout.
- Dev run (off-device): `pip install -e .` then `PLAYBOX_CONFIG_DIR=./config python -m playbox`.
- **Hardware libs come from apt, not pip:** `python3-mpv`, `python3-yaml`, `python3-gpiozero`, `python3-spidev`, `python3-lgpio`, `python3-rpi-lgpio` are all prebuilt on Raspberry Pi OS. The venv uses `--system-site-packages` to see them, so **nothing compiles on the Pi** and pip only fetches `dash` + `pi-rc522`.
- **RFID stack:** `pi-rc522` (import `pirc522`) + `rpi-lgpio` (an lgpio-backed `RPi.GPIO` shim — stock `RPi.GPIO` fails with "Failed to add edge detection" on the 6.18 kernel). `pi-rc522` is installed `--no-deps` so it doesn't pull `RPi.GPIO` and collide with `rpi-lgpio`. Construct the reader as bare `RFID()` (its BOARD-pin defaults map to our BCM25/24 wiring). Note the board is a **clone reporting `VersionReg=0xB2`** instead of 0x91/0x92; `pi-rc522` doesn't check it, but the `mfrc522` library would refuse to start.
- **Audio:** `dtoverlay=wm8960-soundcard` ships with Raspberry Pi OS (no DKMS build, unlike DietPi). HDMI audio is disabled via `dtoverlay=vc4-kms-v3d,noaudio`, so the WM8960 is **card 0** and `audio_device: auto` resolves to it. The codec's output mixers are muted at power-on — `Left/Right Output Mixer PCM` must be `on`, persisted with `alsactl store`.

## Architecture

Single process, started manually (no service by default). A shared `PlayboxCore` (`src/playbox/core.py`) owns the player, callback registry, config, library and scan state. Three input sources feed **one callback dispatcher**:

- **RFIDService** (`hardware/rfid.py`) — interrupt-driven via the RC522 IRQ pin (GPIO24); it does **not** poll SPI. Two modes via `ScanState`: NORMAL dispatches the tag's callback; REGISTER captures the next UID for the web Setup page (tag registration) instead of dispatching.
- **ButtonService** (`hardware/buttons.py`) — gpiozero buttons → callbacks.
- **Dash web app** (`web/`) — multi-page (Play/Control/Setup). The core is stored as a module global in `web/server.py` (`get_core()`); page modules are auto-discovered by Dash and use **absolute imports** (`from playbox.web.server import get_core`) because Dash may import them under a non-package name.

The **callback registry** (`callbacks.py`) maps YAML callback names → functions; `@registry.callback("name")` registers new ones. Every callback receives the shared `PlayerController` plus the YAML `args` as kwargs. This is the extension point — "callbacks can be anything."

Config (`config.py`): `settings.yaml`, `tags.yaml`, `buttons.yaml`. Defaults ship as package data under `src/playbox/defaults/` and seed the config dir on first run. `tags.yaml` is written by the app (web Setup page → `core.upsert_tag`).

## Key constraints

- **Offline is hard-required**: no network dependency at playback time (mpv is configured with `ytdl=False`). Network is for setup only.
- **Pin choices**: button pins in `buttons.yaml` must avoid the SPI/I2C/I2S pins used by the RC522 and WM8960 (see `pinout.md`).
- **Installable package**: keep it `pip`/`uv`-installable with the `playbox` console entry point. `pyproject.toml` lists only `dash`, `python-mpv` and `PyYAML` so plain `pip install .` works on a dev box; Pi-only libs are deliberately *not* declared as an extra because they come from apt (see above).
