# playbox

playbox is a Raspberry Pi based **offline** music player that supports control via hardware buttons, RFID tags and a web interface. It uses the WM8960 Audio HAT and an RC522 RFID reader on a Raspberry Pi Zero 2W.

Music plays entirely from local files — no network is required at playback time. Tags and buttons trigger **callbacks** (play a track, play a playlist, pause, stop, shutdown, …) and the callback system is open so you can add your own.

- **Web app** (Plotly Dash) with three pages: **Play** (browse/play tracks & playlists), **Control** (transport, volume, now-playing), **Setup** (register RFID tags, manage tags, edit settings).
- **RFID** tags are configured *from the web app*: hold a tag to the reader, its UID is captured, and you assign a name, description and callback. Configurations are stored in `config/tags.yaml`.
- **Buttons** are wired to the same callbacks via `config/buttons.yaml`.
- Packaged as an installable Python package (`uv` / `pip`) exposing a `playbox` command, run as a systemd service.

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

## 2. Flash and configure DietPi (automated first boot)

playbox can install itself on first boot using DietPi's automation.

1. **Download DietPi** for the Raspberry Pi Zero 2W from [dietpi.com](https://dietpi.com) and flash it to the microSD card.

2. **Edit `/boot/dietpi.txt`** on the card before first boot (see the [DietPi automation docs](https://dietpi.com/docs/usage/#how-to-do-an-automatic-base-installation-at-first-boot-dietpi-automation)):
   - `AUTO_SETUP_NET_HOSTNAME=playbox`
   - Wi-Fi: set `AUTO_SETUP_NET_WIFI_ENABLED=1` and fill in `/boot/dietpi-wifi.txt` with your SSID/key (or use Ethernet for setup).
   - `AUTO_SETUP_SSH_SERVER_INDEX=-1` (Dropbear) or `-2` (OpenSSH) to enable SSH.
   - `AUTO_SETUP_AUTOMATED=1` for an unattended install.
   - Point the custom script hook at the playbox automation:
     ```
     AUTO_SETUP_CUSTOM_SCRIPT_EXEC=/boot/Automation_Custom_Script.sh
     ```

3. **Copy the automation script** to the card's boot partition:
   - Copy [`scripts/Automation_Custom_Script.sh`](scripts/Automation_Custom_Script.sh) to `/boot/Automation_Custom_Script.sh`.
   - Edit the top of that file: set `REPO_URL` to your playbox repository, and **change `USER_PASSWORD`** (the initial password for the `playbox` user).

4. **Boot the Pi.** DietPi completes its base install, then runs the script, which creates a dedicated **`playbox` login user** (with sudo), clones the repo into `/home/playbox/playbox`, and executes `scripts/install.sh` (below). The Pi reboots when done.

> **About the user:** DietPi only ever ships two accounts — `root` and `dietpi` — and there is no `dietpi.txt` option to create or rename a user before first boot. The `playbox` user is therefore created by the first-boot script (`useradd` + sudo group + password). The service runs as this user, and you can SSH in as `playbox` for administration. Change its password after first boot: `sudo passwd playbox`.

The custom-script log is at `/var/tmp/dietpi/logs/dietpi-automation_custom_script.log` if you need to debug the first boot.

---

## 3. What the installer does (`scripts/install.sh`)

If you prefer a manual install (or are re-provisioning), clone the repo onto the Pi and run:

```bash
git clone <your-repo-url> ~/playbox
cd ~/playbox
# Create & target a dedicated 'playbox' user (set a password instead of the default):
sudo PLAYBOX_USER=playbox PLAYBOX_USER_PASSWORD='choose-one' bash scripts/install.sh
sudo reboot
```

To instead run as the existing `dietpi` user, just `sudo bash scripts/install.sh` (it defaults to the invoking sudo user, falling back to `dietpi`).

The script is idempotent and performs:

1. Creates the target login user with sudo if it doesn't exist (skipped if it already does).
2. Installs system packages (`git`, `build-essential`, `libmpv`, `alsa-utils`, `i2c-tools`).
3. Enables **SPI** and **I2C** in `config.txt` (`dtparam=spi=on`, `dtparam=i2c_arm=on`).
4. Installs the **WM8960** driver from [waveshareteam/WM8960-Audio-HAT](https://github.com/waveshareteam/WM8960-Audio-HAT).
5. Adds the user to the `gpio`, `spi`, `i2c`, `audio` groups.
6. Installs **uv** and then installs playbox with hardware extras: `uv tool install '.[pi]'` → provides the `playbox` command in `~/.local/bin`.
7. Creates the music directory `/mnt/dietpi_userdata/music/playlists`.
8. Grants passwordless `shutdown` (for the `shutdown` callback) via `/etc/sudoers.d/playbox-shutdown`.
9. Installs and enables the **systemd** service `playbox.service`.

A **reboot is required** afterwards for SPI/I2C and the WM8960 overlay.

> **Known issue:** on some 6.6.x kernels the `wm8960-soundcard` service can fail to load the overlay. If `aplay -l` doesn't show the WM8960 card after reboot, see the driver repo's issues, or fall back to manually adding `dtoverlay=wm8960-soundcard` to `config.txt`.

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
| `audio_device` | ALSA device for mpv, e.g. `alsa/hw:1,0`; `auto` lets mpv choose (find the card with `aplay -l`) |
| `volume` | Default startup volume (0–100) |
| `web_host` / `web_port` | Web bind address / port |
| `rfid_wait_timeout` | IRQ wait re-arm timeout (shutdown responsiveness, not polling) |
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
uv sync                                   # create the dev venv
# point at a local music folder and run:
PLAYBOX_CONFIG_DIR=./config uv run playbox
```

Core deps (`dash`, `python-mpv`, `PyYAML`) install anywhere; the `[pi]` extra (`gpiozero`, `lgpio`, `pi-rc522-gpiozero`, `spidev`) is for the device. `python-mpv` needs `libmpv` present on the host to actually play audio.

---

## 9. Troubleshooting

| Symptom | Check |
|---------|-------|
| No sound | `aplay -l` shows the WM8960 card? Is `audio_device` set correctly (e.g. `alsa/hw:1,0`)? Did you reboot after install? |
| RFID not reading | SPI enabled (`ls /dev/spidev*`)? IRQ/RST wired to GPIO24/GPIO25? User in `spi`/`gpio` groups? |
| Buttons do nothing | Correct BCM pins in `buttons.yaml`? User in `gpio` group? |
| Web app unreachable | `systemctl status playbox`; firewall/port; reachable as `http://playbox:8050` |
| `shutdown` callback fails | `/etc/sudoers.d/playbox-shutdown` present (created by install.sh)? |
