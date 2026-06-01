#!/bin/bash
#
# DietPi first-boot automation hook for playbox.
#
# DietPi runs this script once, automatically, near the end of the first-boot
# setup when referenced from /boot/dietpi.txt via:
#
#     AUTO_SETUP_CUSTOM_SCRIPT_EXEC=/boot/Automation_Custom_Script.sh
#
# It clones the playbox repository and runs scripts/install.sh, then reboots so
# the SPI/I2C overlays and the WM8960 driver take effect.
#
# SETUP: copy this file to /boot/Automation_Custom_Script.sh before first boot
# and set REPO_URL below to your repository.

set -e

# ---- EDIT ME --------------------------------------------------------------- #
REPO_URL="https://github.com/youruser/playbox.git"
TARGET_USER="playbox"          # dedicated login user the service runs as
USER_PASSWORD="playbox"        # CHANGE THIS — initial password for $TARGET_USER
# --------------------------------------------------------------------------- #

CLONE_DIR="/home/${TARGET_USER}/playbox"

echo "[playbox] First-boot setup starting"

# DietPi only ships 'root' and 'dietpi'; create our login + sudo user.
if ! id "$TARGET_USER" &>/dev/null; then
    echo "[playbox] Creating login user '$TARGET_USER'"
    useradd -m -s /bin/bash "$TARGET_USER"
    getent group sudo >/dev/null && usermod -aG sudo "$TARGET_USER" || true
    echo "${TARGET_USER}:${USER_PASSWORD}" | chpasswd
fi

# DietPi installs git as part of base deps, but make sure.
command -v git >/dev/null || apt-get install -y git

if [[ ! -d "$CLONE_DIR" ]]; then
    git clone --depth 1 "$REPO_URL" "$CLONE_DIR"
    chown -R "${TARGET_USER}:" "$CLONE_DIR"
fi

# Run the main installer (as root; it drops to the target user where needed).
PLAYBOX_USER="$TARGET_USER" bash "$CLONE_DIR/scripts/install.sh"

echo "[playbox] First-boot setup complete; rebooting"
reboot
