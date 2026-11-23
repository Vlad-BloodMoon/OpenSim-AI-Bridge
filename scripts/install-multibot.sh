#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy multi-bot controller module, templates and directories.
# No additional avatar is created or connected by this installer.
BASE="${OSAI_INSTALL_DIR:-/home/louna49400/OpenSim-AI-Bridge}"
WORK="${1:-}"
if [[ -z "$WORK" || ! -f "$WORK/controller/multi_bot.py" ]]; then
  echo "Usage: sudo bash scripts/install-multibot.sh <EXTRACTED_ARTIFACT_DIR>" >&2
  exit 2
fi
if [[ $EUID -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 2
fi
USER_NAME="${OSAI_BOT_USER:-louna49400}"
if ! id "$USER_NAME" >/dev/null 2>&1; then
  echo "Unknown bot user" >&2
  exit 2
fi
if [[ ! -f "$BASE/OpenSimAiBridge.Bot.dll" || ! -f "$BASE/appsettings.json" ]]; then
  echo "Existing bot installation not found at $BASE" >&2
  exit 2
fi

install -d -o root -g root -m 0755 /usr/local/libexec/opensim-ai-bridge
install -d -o root -g root -m 0711 /var/lib/opensim-ai-bridge
install -d -o root -g root -m 0711 /var/lib/opensim-ai-bridge/bots
install -o root -g root -m 0644 "$WORK/controller/control.py" /usr/local/libexec/opensim-ai-bridge/control.py
install -o root -g root -m 0644 "$WORK/controller/multi_bot.py" /usr/local/libexec/opensim-ai-bridge/multi_bot.py

sed -e "s|@BOT_USER@|$USER_NAME|g" -e "s|@INSTALL_DIR@|$BASE|g" \
  "$WORK/deploy/systemd/opensim-ai-bridge@.service.example" \
  > /etc/systemd/system/opensim-ai-bridge@.service

sed -e "s|@INSTALL_DIR@|$BASE|g" \
  "$WORK/deploy/systemd/opensim-ai-bridge-control.service.example" \
  > /etc/systemd/system/opensim-ai-bridge-control.service

/usr/bin/python3 -m py_compile /usr/local/libexec/opensim-ai-bridge/control.py /usr/local/libexec/opensim-ai-bridge/multi_bot.py
/usr/bin/systemd-analyze verify /etc/systemd/system/opensim-ai-bridge@.service /etc/systemd/system/opensim-ai-bridge-control.service
systemctl daemon-reload
systemctl restart opensim-ai-bridge-control.service
echo "Multi-avatar controller installed. Existing avatar service unchanged."
