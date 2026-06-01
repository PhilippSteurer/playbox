#!/usr/bin/env bash
#
# playbox provisioning script for DietPi / Raspberry Pi OS.
#
# Idempotent: safe to re-run. Must be run as root (sudo). It installs system
# packages, enables SPI/I2C, installs the WM8960 audio driver, installs playbox
# as a uv tool for the target user, creates the music directories and installs +
# enables the systemd service.
#
#   sudo ./scripts/install.sh
#
set -euo pipefail

# --- resolve user / paths --------------------------------------------------- #
if [[ $EUID -ne 0 ]]; then
    echo "Please run as root: sudo $0" >&2
    exit 1
fi

TARGET_USER="${SUDO_USER:-dietpi}"
if ! id "$TARGET_USER" &>/dev/null; then
    echo "User '$TARGET_USER' does not exist. Set SUDO_USER or create the user." >&2
    exit 1
fi
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installing playbox for user '$TARGET_USER' (home: $TARGET_HOME)"
echo "==> Repo: $REPO_DIR"

run_as_user() { sudo -u "$TARGET_USER" -H bash -lc "$*"; }

# --- 1. system packages ----------------------------------------------------- #
echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git build-essential curl alsa-utils i2c-tools
# libmpv runtime (package name varies across releases)
apt-get install -y libmpv2 || apt-get install -y libmpv1 || apt-get install -y libmpv-dev

# --- 2. enable SPI + I2C ---------------------------------------------------- #
CONFIG_TXT=/boot/config.txt
[[ -f /boot/firmware/config.txt ]] && CONFIG_TXT=/boot/firmware/config.txt
echo "==> Enabling SPI and I2C in $CONFIG_TXT"
enable_param() {
    local param="$1"
    if grep -qE "^\s*#?\s*${param%%=*}=" "$CONFIG_TXT"; then
        sed -i "s|^\s*#\?\s*${param%%=*}=.*|${param}|" "$CONFIG_TXT"
    else
        echo "$param" >> "$CONFIG_TXT"
    fi
}
enable_param "dtparam=spi=on"
enable_param "dtparam=i2c_arm=on"

# --- 3. WM8960 audio driver ------------------------------------------------- #
if aplay -l 2>/dev/null | grep -qi wm8960; then
    echo "==> WM8960 driver already active, skipping"
else
    echo "==> Installing WM8960 audio HAT driver"
    DRV_DIR=/opt/WM8960-Audio-HAT
    if [[ ! -d "$DRV_DIR" ]]; then
        git clone --depth 1 https://github.com/waveshareteam/WM8960-Audio-HAT "$DRV_DIR"
    fi
    ( cd "$DRV_DIR" && ./install.sh ) || \
        echo "!! WM8960 install.sh reported an error — see README troubleshooting"
fi

# --- 4. group memberships (GPIO / SPI / I2C / audio) ------------------------ #
echo "==> Adding $TARGET_USER to hardware groups"
for grp in gpio spi i2c audio; do
    getent group "$grp" >/dev/null && usermod -aG "$grp" "$TARGET_USER" || true
done

# --- 5. install uv + playbox (as the target user) --------------------------- #
if ! run_as_user "command -v uv" &>/dev/null; then
    echo "==> Installing uv for $TARGET_USER"
    run_as_user "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
echo "==> Installing playbox package (with [pi] hardware extras)"
run_as_user "cd '$REPO_DIR' && uv tool install --force '.[pi]'"

# --- 6. music directories --------------------------------------------------- #
MUSIC_DIR=/mnt/dietpi_userdata/music
echo "==> Creating music directories under $MUSIC_DIR"
mkdir -p "$MUSIC_DIR/playlists"
chown -R "$TARGET_USER": "$MUSIC_DIR"

# --- 7. passwordless shutdown (for the 'shutdown' callback) ----------------- #
echo "==> Allowing $TARGET_USER to run 'shutdown' without a password"
cat >/etc/sudoers.d/playbox-shutdown <<EOF
$TARGET_USER ALL=(root) NOPASSWD: /sbin/shutdown
EOF
chmod 0440 /etc/sudoers.d/playbox-shutdown

# --- 8. systemd service ----------------------------------------------------- #
echo "==> Installing systemd service"
sed -e "s|__USER__|$TARGET_USER|g" \
    -e "s|__HOME__|$TARGET_HOME|g" \
    -e "s|__REPO__|$REPO_DIR|g" \
    "$REPO_DIR/systemd/playbox.service" > /etc/systemd/system/playbox.service
systemctl daemon-reload
systemctl enable playbox.service

echo
echo "============================================================"
echo " playbox installed."
echo " A REBOOT is required to apply SPI/I2C and the WM8960 driver."
echo "   sudo reboot"
echo " After reboot the web UI is at: http://playbox:8050"
echo " Check the service with:  systemctl status playbox"
echo "============================================================"
