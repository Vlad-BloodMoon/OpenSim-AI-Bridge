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
# Catalog data is separated from all bot profiles, quotas and knowledge.
install -d -o root -g root -m 0700 /var/lib/opensim-ai-bridge/catalog
install -o root -g root -m 0644 "$WORK/controller/control.py" /usr/local/libexec/opensim-ai-bridge/control.py
install -o root -g root -m 0644 "$WORK/controller/multi_bot.py" /usr/local/libexec/opensim-ai-bridge/multi_bot.py
install -o root -g root -m 0644 "$WORK/controller/provider_profiles.py" /usr/local/libexec/opensim-ai-bridge/provider_profiles.py
install -o root -g root -m 0644 "$WORK/controller/protected_terms.py" /usr/local/libexec/opensim-ai-bridge/protected_terms.py
install -o root -g root -m 0644 "$WORK/controller/catalog_models.py" /usr/local/libexec/opensim-ai-bridge/catalog_models.py
install -o root -g root -m 0644 "$WORK/controller/catalog_cache.py" /usr/local/libexec/opensim-ai-bridge/catalog_cache.py

# Shared knowledge indexer: does not modify the .NET bot executable.
# Data directory exists before systemd starts the isolated refresh job.
# The optional catalog timer is installed but NEVER enabled automatically.
if [[ -f "$WORK/deploy/systemd/opensim-ai-bridge-catalog.service.example"
      && -f "$WORK/deploy/systemd/opensim-ai-bridge-catalog.timer.example" ]]; then
  install -o root -g root -m 0644 "$WORK/deploy/systemd/opensim-ai-bridge-catalog.service.example" /etc/systemd/system/opensim-ai-bridge-catalog.service
  install -o root -g root -m 0644 "$WORK/deploy/systemd/opensim-ai-bridge-catalog.timer.example" /etc/systemd/system/opensim-ai-bridge-catalog.timer
fi

if [[ -f "$WORK/knowledge/knowledge_cli.py" ]]; then
  install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$BASE/data"
  install -d -o "$USER_NAME" -g "$USER_NAME" -m 0750 "$BASE/knowledge"
  install -o "$USER_NAME" -g "$USER_NAME" -m 0750 \
    "$WORK/knowledge/knowledge_cli.py" "$BASE/knowledge/knowledge_cli.py"
fi
if [[ -f "$WORK/deploy/systemd/opensim-ai-bridge-knowledge.service.example" ]]; then
  sed -e "s|@BOT_USER@|$USER_NAME|g" -e "s|@INSTALL_DIR@|$BASE|g" \
    "$WORK/deploy/systemd/opensim-ai-bridge-knowledge.service.example" \
    > /etc/systemd/system/opensim-ai-bridge-knowledge.service
fi

# Keep the working bot binary untouched; install only its updated launch script.
# This adds secure loading of a per-avatar AI key at the next bot restart.
if [[ -f "$WORK/scripts/start-bot.sh" ]]; then
  install -o "$USER_NAME" -g "$USER_NAME" -m 0750 "$WORK/scripts/start-bot.sh" "$BASE/scripts/start-bot.sh"
fi

sed -e "s|@BOT_USER@|$USER_NAME|g" -e "s|@INSTALL_DIR@|$BASE|g" \
  "$WORK/deploy/systemd/opensim-ai-bridge@.service.example" \
  > /etc/systemd/system/opensim-ai-bridge@.service

sed -e "s|@INSTALL_DIR@|$BASE|g" \
  "$WORK/deploy/systemd/opensim-ai-bridge-control.service.example" \
  > /etc/systemd/system/opensim-ai-bridge-control.service

# Prevent systemd from starting the legacy bot while fleet maintenance is active.
# An additive drop-in leaves the existing service definition untouched.
install -d -o root -g root -m 0755 /etc/systemd/system/opensim-ai-bridge.service.d
printf '%s\n' '[Unit]' 'ConditionPathExists=!/var/lib/opensim-ai-bridge/global-maintenance.lock' > /etc/systemd/system/opensim-ai-bridge.service.d/10-global-maintenance.conf
# Collect per-service usage through systemd without introducing arbitrary process inspection.
printf '%s\n' '[Service]' 'CPUAccounting=yes' 'MemoryAccounting=yes' > /etc/systemd/system/opensim-ai-bridge.service.d/20-resource-accounting.conf

/usr/bin/python3 -m py_compile /usr/local/libexec/opensim-ai-bridge/control.py /usr/local/libexec/opensim-ai-bridge/multi_bot.py /usr/local/libexec/opensim-ai-bridge/provider_profiles.py /usr/local/libexec/opensim-ai-bridge/protected_terms.py /usr/local/libexec/opensim-ai-bridge/catalog_models.py /usr/local/libexec/opensim-ai-bridge/catalog_cache.py
/usr/bin/systemd-analyze verify /etc/systemd/system/opensim-ai-bridge@.service /etc/systemd/system/opensim-ai-bridge-control.service
systemctl daemon-reload
systemctl restart opensim-ai-bridge-control.service
echo "Multi-avatar controller installed. Existing avatar service unchanged."
