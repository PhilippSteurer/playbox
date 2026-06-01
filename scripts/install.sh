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

# Target user for the service. Override with PLAYBOX_USER; otherwise the invoking
# sudo user, otherwise DietPi's default 'dietpi'.
TARGET_USER="${PLAYBOX_USER:-${SUDO_USER:-dietpi}}"

# Create the user if it does not exist, as a normal login user with sudo.
if ! id "$TARGET_USER" &>/dev/null; then
    echo "==> Creating login user '$TARGET_USER' (with sudo)"
    useradd -m -s /bin/bash "$TARGET_USER"
    getent group sudo >/dev/null && usermod -aG sudo "$TARGET_USER" || true
    echo "${TARGET_USER}:${PLAYBOX_USER_PASSWORD:-playbox}" | chpasswd
    echo "!! Default password set to '${PLAYBOX_USER_PASSWORD:-playbox}'. Change it: sudo passwd $TARGET_USER"
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

# --- 3. WM8960 audio driver (best-effort; must never abort provisioning) ---- #
# Audio-driver problems (transient network, or a DKMS build that doesn't support
# the running kernel) should not block the rest of the install, so this whole
# step is non-fatal.
install_wm8960() {
    if aplay -l 2>/dev/null | grep -qi wm8960; then
        echo "==> WM8960 driver already active, skipping"
        return 0
    fi
    echo "==> Installing WM8960 audio HAT driver"
    local drv=/opt/WM8960-Audio-HAT
    if [[ ! -d "$drv/.git" ]]; then
        rm -rf "$drv"
        local n
        for n in 1 2 3; do
            git clone --depth 1 https://github.com/waveshareteam/WM8960-Audio-HAT "$drv" && break
            echo "!! WM8960 clone attempt $n failed (network?); retrying in 5s…"
            sleep 5
        done
    fi
    if [[ ! -d "$drv" ]]; then
        echo "!! Could not fetch WM8960 driver; skipping. Re-run install.sh later to set up audio."
        return 0
    fi
    ( cd "$drv" && ./install.sh ) || \
        echo "!! WM8960 install.sh failed (running kernel $(uname -r)) — see README troubleshooting"
}
install_wm8960 || true

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
