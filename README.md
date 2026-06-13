# playbox

playbox is a Raspberry Pi based **offline** music player that supports control via hardware buttons, RFID tags and a web interface. It uses the WM8960 Audio HAT and an RC522 RFID reader on a Raspberry Pi Zero 2W.

Music plays entirely from local files — no network is required at playback time. Tags and buttons trigger **callbacks** (play a track, play a playlist, pause, stop, shutdown, …) and the callback system is open so you can add your own.

- **Web app** (Plotly Dash) with three pages: **Play** (browse/play tracks & playlists), **Control** (transport, volume, now-playing), **Setup** (register RFID tags, manage tags, edit settings).
- **RFID** tags are configured *from the web app*: hold a tag to the reader, its UID is captured, and you assign a name, description and callback. Configurations are stored in `config/tags.yaml`.
- **Buttons** are wired to the same callbacks via `config/buttons.yaml`.
- Packaged as an installable Python package (`pip install .`) exposing a `playbox` command, run as a systemd service.

---

## 1. Hardware

| Component | Interface |
|-----------|-----------|
| Raspberry Pi Zero 2W + microSD (16 GB+) | — |
| WM8960 Audio HAT | I2C (codec control) + I2S (audio) |
| RC522 RFID reader | SPI (+ IRQ, RST) |
| Push buttons (play/pause, volume, prev/next) | GPIO |

Wire everything according to **[`pinout.md`](pinout.md)** — it is the authoritative pin reference. Key points:

- RC522 is on **SPI0** (CE0=GPIO8, SCLK=GPIO11, MOSI=GPIO10, MISO=GPIO9) and uses **IRQ=GPIO24** and **RST=GPIO25**. playbox reads the reader **interrupt-driven** via the IRQ pin (no constant polling), so wiring IRQ is required.
- WM8960 uses I2C (GPIO2/3) and I2S (GPIO18/19/20/21) — handled by its driver.
- Default button pins (free pins, chosen to avoid the buses above): GPIO27 play/pause, GPIO22 volume up, GPIO23 volume down, GPIO4 previous, GPIO14 next.

---

## 2. Operating system setup (manual, done once)

playbox targets **DietPi**. Flash a current DietPi image for the Pi Zero 2W and complete the base setup, then perform the prerequisites below. These are done by hand once; the playbox app itself is installed in [section 3](#3-install-playbox).

1. **Flash & first boot.** Flash the DietPi image and complete DietPi's initial setup: connect Wi-Fi, run updates, switch the SSH server to **OpenSSH**, set timezone/keyboard.

2. **Enable buses & audio** with `dietpi-config`:
   - Enable **I2C** and **SPI**.
   - Under *Audio Options*, enable the sound card and select **WM8960**.

3. **WM8960 quirk.** Add the following line to `/boot/dietpi.txt` (required for the WM8960 driver to build/load on this image):
   ```
   arm_64bit=0
   ```

4. **Hostname & user.** Set the hostname to `playbox`. Create a login user `playbox` with sudo rights, and add your SSH public key so you can log in over SSH without a password.

5. **Install system packages:**
   ```bash
   sudo apt update
   sudo apt install -y git build-essential swig curl wget \
       alsa-utils i2c-tools libasound2-dev libmpv2 liblgpio-dev \
       python3-pip python3-venv python3-dev linux-headers-rpi-v8
   ```
   `swig` + `python3-dev` + `liblgpio-dev` are needed to build the `lgpio`/`rpi-lgpio` wheels (without `liblgpio-dev` the build fails with `cannot find -llgpio`); `libmpv2` is the audio backend; `linux-headers-*` lets the WM8960 DKMS module build.

6. **Hardware group access** for the `playbox` user:
   ```bash
   sudo usermod -aG audio,i2c,spi,gpio playbox
   ```
   Log out/in (or reboot) for the new groups to take effect.

7. **Verify audio.** After a reboot, the WM8960 should enumerate as **card 0**:
   ```bash
   aplay -l        # expect: card 0: wm8960soundcard ...
   ```

---

## 3. Install playbox

playbox installs into a normal Python **venv** with `pip`. As the `playbox` user:

```bash
git clone <your-repo-url> ~/playbox
cd ~/playbox

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install '.[pi]'
pip install --no-deps pi-rc522     # RFID library — see note below
```

This provides the `playbox` command at `~/playbox/.venv/bin/playbox`.

> **About the RFID stack.** The reader uses **`pi-rc522`** plus **`rpi-lgpio`** (an lgpio-backed drop-in for `RPi.GPIO`). The stock `RPi.GPIO` fails on current kernels with *"Failed to add edge detection"*, so `rpi-lgpio` replaces it. Because `pi-rc522` hard-depends on `RPi.GPIO` (which would collide with `rpi-lgpio`), it is installed with `--no-deps`; the `[pi]` extra already supplies `rpi-lgpio` + `spidev`.
>
> If the `lgpio` wheel fails to build with `cannot find -llgpio`, install the C library it links against: `sudo apt install -y liblgpio-dev` (plus `swig` + `python3-dev` for the build), then re-run the install.

### systemd service

Install the service so playbox starts on boot. Substitute your user and repo path into the template:

```bash
sed -e "s|__USER__|playbox|g" \
    -e "s|__REPO__|/home/playbox/playbox|g" \
    systemd/playbox.service | sudo tee /etc/systemd/system/playbox.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now playbox
```

The unit runs `~/playbox/.venv/bin/playbox` and sets `PLAYBOX_CONFIG_DIR` to the repo's `config/`. For the `shutdown` callback to work, allow passwordless shutdown:

```bash
echo 'playbox ALL=(root) NOPASSWD: /sbin/shutdown' | sudo tee /etc/sudoers.d/playbox-shutdown
sudo chmod 0440 /etc/sudoers.d/playbox-shutdown
```

> **Automated install (work in progress).** `scripts/install.sh` performs the same package/venv/pip/systemd steps unattended (and `scripts/Automation_Custom_Script.sh` is a DietPi first-boot hook around it). These are kept for later automation but the manual path above is the supported one today.

---

## 4. Add music

Copy audio files into the music directory on the Pi (over SSH/SCP, or enable Samba in `dietpi-software`):

```
/mnt/dietpi_userdata/music/            ← tracks (any folder structure)
/mnt/dietpi_userdata/music/playlists/  ← .m3u / .m3u8 playlists
```

A playlist is a plain `.m3u` file listing track paths (relative to the music directory or absolute), one per line. The playlist *name* used by callbacks is the filename without extension (e.g. `playlists/morning.m3u` → `morning`).

Supported track formats: mp3, flac, ogg/opus, m4a/aac, wav, wma.

---

## 5. Use the web app

Open **`http://playbox:8050`** (or the Pi's IP) from any device on the same network.

- **Play** — lists your playlists and tracks; click one to play it.
- **Control** — play/pause/stop/prev/next, a volume slider, and a live now-playing display.
- **Setup**
  - **Register RFID tag:** click *Start scan*, hold a tag to the reader; its UID is captured automatically. Fill in a name/description, pick a **callback**, optionally provide **args** (as JSON), and *Save tag*. The tag is written to `config/tags.yaml` and works immediately.
  - **Configured tags:** table of existing tags with delete buttons.
  - **Settings:** music directory, ALSA audio device, default volume.

---

## 6. Configuration reference

Config files live in `config/` (the service sets `PLAYBOX_CONFIG_DIR` to the repo's `config/`). Missing files are seeded from packaged defaults on first run.

### `settings.yaml`
| Key | Meaning |
|-----|---------|
| `music_dir` | Music root directory |
| `audio_device` | ALSA device for mpv. With the WM8960 HAT this is **card 0**, so `alsa/hw:0,0`; `auto` lets mpv choose (find the card with `aplay -l`) |
| `volume` | Default startup volume (0–100) |
| `web_host` / `web_port` | Web bind address / port |
| `rfid_wait_timeout` | (reserved) IRQ wait re-arm timeout |
| `rfid_debounce` | Seconds to ignore repeat reads of a held tag |

### `tags.yaml` / `buttons.yaml`
```yaml
tags:
  - id: "04A1B2C3"          # UID captured from the reader (hex)
    name: "Morning mix"
    description: "Wake-up playlist"
    callback: play_playlist  # a registered callback name
    args:
      playlist: morning      # keyword args passed to the callback

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

### Adding a custom callback
Register any function in `src/playbox/callbacks.py` (in `build_default_registry`). It receives the shared player plus the YAML `args` as keywords:

```python
@registry.callback("announce")
def announce(player, message="hello", **_):
    ...
```

Then reference `callback: announce` with `args: {message: "..."}` from a tag or button.

---

## 7. Service management

```bash
systemctl status playbox          # is it running?
sudo systemctl restart playbox    # apply config / audio-device changes
journalctl -u playbox -f          # live logs
```

---

## 8. Development on a PC (no hardware)

playbox runs without the Pi hardware for working on the web app/player. The hardware services detect the missing libraries/devices and become no-ops (logged as warnings).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                          # core deps only (no [pi] extra)
# point at a local music folder and run:
PLAYBOX_CONFIG_DIR=./config python -m playbox
```

Core deps (`dash`, `python-mpv`, `PyYAML`) install anywhere; the `[pi]` extra (`gpiozero`, `lgpio`, `rpi-lgpio`, `spidev`) plus `pi-rc522` are for the device. `python-mpv` needs `libmpv` present on the host to actually play audio.

---

## 9. Troubleshooting

| Symptom | Check |
|---------|-------|
| No sound | `aplay -l` shows the WM8960 card (card 0)? Is `audio_device` set to `alsa/hw:0,0`? Did you reboot after enabling the HAT? Is `arm_64bit=0` in `/boot/dietpi.txt`? |
| RFID not reading | SPI enabled (`ls /dev/spidev*`)? IRQ/RST wired to GPIO24/GPIO25? User in `spi`/`gpio` groups? `rpi-lgpio` installed (not stock `RPi.GPIO`)? |
| `Failed to add edge detection` | Stock `RPi.GPIO` is installed — `pip uninstall -y RPi.GPIO && pip install rpi-lgpio` (then reinstall `pi-rc522` with `--no-deps`) |
| Buttons do nothing | Correct BCM pins in `buttons.yaml`? User in `gpio` group? |
| Web app unreachable | `systemctl status playbox`; firewall/port; reachable as `http://playbox:8050` |
| `shutdown` callback fails | `/etc/sudoers.d/playbox-shutdown` present? |
