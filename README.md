# playbox

playbox is a Raspberry Pi based **offline** music player controlled three ways: hardware buttons, RFID tags, and a web interface. It runs on a Pi Zero 2W with a WM8960 Audio HAT and an RC522 RFID reader.

Music plays entirely from local files — no network is needed at playback time. Tags and buttons trigger **callbacks** (play a track, play a playlist, pause, volume, shutdown, …), and the callback system is open so you can add your own.

- **Web app** (Plotly Dash), three pages: **Play** (browse and play), **Control** (transport, volume, now playing), **Setup** (register RFID tags, edit settings).
- **RFID tags** are registered *from the web app*: hold a tag to the reader, its UID is captured, then you pick a callback for it. Stored in `config/tags.yaml`.
- **Buttons** map GPIO pins to the same callbacks via `config/buttons.yaml`.
- A normal Python package (`pip install .`) exposing a `playbox` command, **started by hand**. No service is installed — see [section 7](#7-optional-run-it-on-boot) if you want that later.

---

## 1. Hardware

| Component | Interface |
|-----------|-----------|
| Raspberry Pi Zero 2W + microSD (16 GB+) | — |
| WM8960 Audio HAT | I2C (codec control) + I2S (audio) |
| RC522 RFID reader | SPI (+ IRQ, RST) |
| Push buttons | GPIO |

Wire per **[`pinout.md`](pinout.md)**, which is the authoritative reference. Key points:

- RC522 on **SPI0** (CE0=GPIO8, SCLK=GPIO11, MOSI=GPIO10, MISO=GPIO9) with **IRQ=GPIO24** and **RST=GPIO25**. Tag reads are interrupt-driven off the IRQ pin, so wiring IRQ is **required**.
- WM8960 uses I2C (GPIO2/3) and I2S (GPIO18/19/20/21).
- Default button pins, chosen to avoid those buses: GPIO27 play/pause, GPIO22 volume up, GPIO23 volume down, GPIO4 previous, GPIO14 next.

---

## 2. Operating system setup (once)

playbox runs on **Raspberry Pi OS Lite (32-bit)**. Everything the hardware needs is already in that image — there is **no driver to build**. This is the main difference from the old DietPi setup, which needed an out-of-tree WM8960 DKMS module.

### 2.1 Flash and first boot

Flash Raspberry Pi OS Lite (32-bit) with Raspberry Pi Imager. In the Imager's settings, set the hostname to `playbox`, create the user `playbox`, enable SSH with your public key, and configure Wi-Fi. Then SSH in:

```bash
ssh playbox@playbox.local
```

The `playbox` user is in the `sudo` group by default, along with `gpio`, `i2c`, `spi` and `audio` — so no `usermod` step is needed.

### 2.2 Enable SPI and I2C

```bash
sudo raspi-config
```

- **Interface Options → I4 SPI → Enable** — needed for the RC522.
- **Interface Options → I5 I2C → Enable** — gives you `/dev/i2c-1` for debugging the codec.

### 2.3 Enable the WM8960 sound card

`raspi-config` has no entry for this, so edit `/boot/firmware/config.txt` by hand:

```bash
sudo nano /boot/firmware/config.txt
```

Change the vc4 line to drop HDMI audio, so the WM8960 becomes card 0:

```diff
- dtoverlay=vc4-kms-v3d
+ dtoverlay=vc4-kms-v3d,noaudio
```

and add this at the **end of the file** (it must be under `[all]`, not under a `[pi5]`/`[cm4]` section):

```
# Waveshare WM8960 Audio HAT (I2C control + I2S audio)
dtoverlay=wm8960-soundcard
```

> **Watch the spelling.** The firmware silently ignores keys it doesn't recognise — a typo like `dtoverly=` produces no error anywhere, you just get no sound card.

That single line *is* the driver installation. The codec driver (`snd-soc-wm8960`), the generic `simple-audio-card` machine driver, and the overlay itself all ship with Raspberry Pi OS. The overlay enables I2S, declares the codec on I2C at address `0x1a`, and joins them into a card. Then reboot:

```bash
sudo reboot
```

### 2.4 Install system packages

```bash
sudo apt update
sudo apt install -y git python3-venv \
    alsa-utils i2c-tools \
    python3-mpv python3-yaml \
    python3-gpiozero python3-spidev python3-lgpio python3-rpi-lgpio
```

All prebuilt — **nothing compiles**, which matters on a Zero 2W. `python3-rpi-lgpio` is important: it provides the `RPi.GPIO` import name backed by lgpio. The stock `RPi.GPIO` fails with *"Failed to add edge detection"* on current kernels.

### 2.5 Verify the hardware

```bash
aplay -l          # expect: card 0: wm8960soundcard [wm8960-soundcard]
ls /dev/spidev*   # expect: /dev/spidev0.0  /dev/spidev0.1
i2cdetect -y 1    # expect: UU at address 1a  (UU = kernel driver bound — good)
```

### 2.6 Unmute the codec

The WM8960 powers up with its **output mixers muted**, so a correctly working card still plays silence. The DAC signal never reaches the headphone/speaker amplifiers until you close these two switches:

```bash
amixer -c 0 sset 'Left Output Mixer PCM' on
amixer -c 0 sset 'Right Output Mixer PCM' on
```

Test, then save so it survives a reboot:

```bash
speaker-test -D hw:0,0 -c 2 -t sine -f 440 -l 1
sudo alsactl store
```

`alsactl store` writes `/var/lib/alsa/asound.state`, which the `alsa-restore` service (part of `alsa-utils`) replays on every boot. Use `alsamixer -c 0` for interactive tweaking, then `sudo alsactl store` again.

---

## 3. Install playbox

```bash
git clone <your-repo-url> ~/playbox
cd ~/playbox

python3 -m venv --system-site-packages .venv
source .venv/bin/activate

pip install .
pip install --no-deps pi-rc522
```

Two things are worth understanding here:

- **`--system-site-packages`** lets the venv see the apt-installed `python3-mpv`, `python3-yaml`, `python3-gpiozero`, `python3-spidev` and `python3-rpi-lgpio`. Without it pip would try to build those from source on the Pi. With it, `pip install .` only needs to fetch `dash`.
- **`--no-deps` on pi-rc522** because it declares a hard dependency on `RPi.GPIO`. Letting pip install that would shadow the apt `rpi-lgpio` with the broken stock version. `pi-rc522` only *imports* `RPi.GPIO`, and `rpi-lgpio` already supplies that name.

You now have the `playbox` command at `~/playbox/.venv/bin/playbox`.

---

## 4. Add music

```
~/music/            ← tracks, any folder structure
~/music/playlists/  ← .m3u / .m3u8 playlists
```

Copy files over with `scp -r ./album playbox@playbox.local:~/music/`.

A playlist is a plain `.m3u` listing track paths (relative to the music dir, or absolute), one per line. Its *name* for callbacks is the filename without extension (`playlists/morning.m3u` → `morning`).

Supported: mp3, flac, ogg/opus, m4a/aac, wav, wma.

---

## 5. Run it

```bash
cd ~/playbox
source .venv/bin/activate
playbox
```

Logs go to the terminal; **Ctrl-C** stops it. Useful flags:

```bash
playbox -v                  # debug logging
playbox --port 8080         # override the web port
playbox --config-dir ./config
```

Then open **`http://playbox.local:8050`** (or the Pi's IP) from any device on the network.

To keep it running after you disconnect, `tmux` is the simplest option:

```bash
sudo apt install -y tmux
tmux new -s playbox         # run playbox inside, then Ctrl-B then D to detach
tmux attach -t playbox      # come back later
```

---

## 6. Using the web app

- **Play** — your playlists and tracks; click one to play.
- **Control** — play/pause/stop/prev/next, volume slider, live now-playing.
- **Setup**
  - **Register RFID tag:** click *Start scan*, hold a tag to the reader, and its UID is captured. Give it a name, pick a **callback**, optionally add **args** as JSON, then *Save tag*. It's written to `config/tags.yaml` and works immediately.
  - **Configured tags:** the existing tags, with delete buttons.
  - **Settings:** music directory, ALSA device, default volume.

The `shutdown` callback needs passwordless shutdown rights:

```bash
echo 'playbox ALL=(root) NOPASSWD: /sbin/shutdown' | sudo tee /etc/sudoers.d/playbox-shutdown
sudo chmod 0440 /etc/sudoers.d/playbox-shutdown
```

---

## 7. Optional: run it on boot

Not set up by default — start it by hand while you're still changing things. When you do want it automatic, a systemd unit is about ten lines:

```ini
# /etc/systemd/system/playbox.service
[Unit]
Description=playbox music player
After=network-online.target sound.target

[Service]
Type=simple
User=playbox
WorkingDirectory=/home/playbox/playbox
Environment=PLAYBOX_CONFIG_DIR=/home/playbox/playbox/config
ExecStart=/home/playbox/playbox/.venv/bin/playbox
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now playbox
journalctl -u playbox -f
```

---

## 8. Configuration reference

Config lives in `config/` next to the source checkout. Missing files are seeded from the packaged defaults in `src/playbox/defaults/` on first run.

### `settings.yaml`
| Key | Meaning |
|-----|---------|
| `music_dir` | Music root (`~` is expanded) |
| `audio_device` | mpv audio device. `auto` picks the ALSA default, which is the WM8960 since HDMI audio is off. `alsa/hw:0,0` for exclusive access |
| `volume` | Startup volume (0–100) |
| `web_host` / `web_port` | Web bind address / port |
| `rfid_debounce` | Seconds to ignore repeat reads of a held tag |

### `tags.yaml` / `buttons.yaml`
```yaml
tags:
  - id: "04A1B2C3"          # UID captured from the reader (hex)
    name: "Morning mix"
    description: "Wake-up playlist"
    callback: play_playlist  # a registered callback name
    args:
      playlist: morning      # passed to the callback as keyword args

buttons:
  - pin: 27                  # BCM GPIO number
    name: "Play/Pause"
    callback: toggle
    args: {}
```

### Built-in callbacks
| Callback | Args | Action |
|----------|------|--------|
| `play_track` | `track: <relative path>` | Play one track |
| `play_playlist` | `playlist: <name>` | Play a playlist |
| `play` / `pause` / `toggle` / `stop` | — | Transport |
| `next` / `previous` | — | Queue navigation |
| `volume` | `level: 0-100` **or** `delta: ±n` | Set/adjust volume |
| `shutdown` | — | Halt the system |

### Adding your own callback

This is the intended extension point. Register a function in `src/playbox/callbacks.py` (inside `build_default_registry`); it receives the shared player plus the YAML `args` as keywords:

```python
@registry.callback("announce")
def announce(player, message="hello", **_):
    ...
```

Then use `callback: announce` with `args: {message: "..."}` from any tag or button.

---

## 9. Development on a PC (no hardware)

The hardware services detect missing libraries and become no-ops (logged as warnings), so the web app and player logic can be worked on off-device.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
PLAYBOX_CONFIG_DIR=./config python -m playbox
```

`python-mpv` needs `libmpv` on the host to actually produce sound.

---

## 10. Troubleshooting

| Symptom | Check |
|---------|-------|
| No sound card in `aplay -l` | Is `dtoverlay=wm8960-soundcard` spelled correctly and under `[all]`? Did you reboot? |
| Card exists but silence | The output mixers — see [2.6](#26-unmute-the-codec). This is the usual cause |
| Mixer resets on reboot | Run `sudo alsactl store` after setting it |
| RFID not reading | `ls /dev/spidev*` — SPI enabled? IRQ on GPIO24 and RST on GPIO25 wired? |
| `Failed to add edge detection` | Stock `RPi.GPIO` got installed. `pip uninstall -y RPi.GPIO`, confirm `python3-rpi-lgpio` is present, reinstall pi-rc522 with `--no-deps` |
| `ModuleNotFoundError: mpv` | Venv made without `--system-site-packages`, or `python3-mpv` not installed |
| Buttons do nothing | Correct BCM pins in `buttons.yaml`? |
| Web app unreachable | Is the process still running? Check the terminal / `tmux attach` |

### Checking the RC522 without any library

If tags aren't reading, this narrows it to wiring vs. software. Reading `VersionReg` and checking registers with documented reset values proves the SPI link:

```python
import spidev
from gpiozero import DigitalOutputDevice
rst = DigitalOutputDevice(25, initial_value=True)
spi = spidev.SpiDev(); spi.open(0, 0); spi.max_speed_hz = 1_000_000
rd = lambda reg: spi.xfer2([((reg << 1) & 0x7E) | 0x80, 0x00])[1]
print(f"VersionReg 0x{rd(0x37):02X}   CommandReg 0x{rd(0x01):02X} (expect 0x20)")
```

`CommandReg` reading `0x20` means SPI works. `VersionReg` is `0x91`/`0x92` on genuine chips, but clones report other values (e.g. `0xB2`) and work fine — `pi-rc522` doesn't check it.
