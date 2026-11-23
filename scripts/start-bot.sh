#!/usr/bin/env bash
set -Eeuo pipefail

# OpenSim AI Bridge — run as the dedicated unprivileged service account.
# Compatible with a binary distribution extracted into INSTALL_DIR.
INSTALL_DIR="${OSAI_INSTALL_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
CONFIG_FILE="${OSAI_CONFIG_FILE:-$INSTALL_DIR/appsettings.json}"
PASSWORD_FILE="${OSAI_PASSWORD_FILE:-$INSTALL_DIR/bot-password.txt}"
LOCK_FILE="${OSAI_MAINTENANCE_FILE:-$INSTALL_DIR/maintenance.lock}"

cd "$INSTALL_DIR"

if [[ -e "$LOCK_FILE" ]]; then
  echo "OpenSim AI Bridge: maintenance mode active; avatar login is blocked."
  exit 0
fi

if [[ ! -f "$CONFIG_FILE" || ! -r "$CONFIG_FILE" ]]; then
  echo "Missing readable configuration file: $CONFIG_FILE" >&2
  exit 2
fi

if [[ ! -f "$PASSWORD_FILE" || ! -r "$PASSWORD_FILE" ]]; then
  echo "Missing readable password file: $PASSWORD_FILE" >&2
  exit 2
fi

# Prevent accidental logging of the secret. One line; no echo or shell tracing.
IFS= read -r OSAI_AVATAR_PASSWORD < "$PASSWORD_FILE" || [[ -n "${OSAI_AVATAR_PASSWORD:-}" ]]
if [[ -z "${OSAI_AVATAR_PASSWORD:-}" ]]; then
  echo "Avatar password file is empty." >&2
  exit 2
fi
export OSAI_AVATAR_PASSWORD

# Optional remote-AI secret lives beside each bot's private configuration.
# No key is printed or committed; a missing key simply disables AI.
AI_KEY_FILE="${OSAI_AI_KEY_FILE:-$(dirname -- "$CONFIG_FILE")/ai-api-key.txt}"
if [[ -f "$AI_KEY_FILE" ]]; then
  if [[ ! -r "$AI_KEY_FILE" || -L "$AI_KEY_FILE" ]]; then
    echo "AI key file permissions invalid." >&2
    exit 2
  fi
  ai_key_mode=$(stat -c '%a' -- "$AI_KEY_FILE")
  if (( (8#$ai_key_mode & 077) != 0 )); then
    echo "AI key file must not be readable by group or others." >&2
    exit 2
  fi
  IFS= read -r OSAI_AI_API_KEY < "$AI_KEY_FILE" || [[ -n "${OSAI_AI_API_KEY:-}" ]]
  export OSAI_AI_API_KEY
fi

# The maintenance check is repeated immediately before launch.
if [[ -e "$LOCK_FILE" ]]; then
  echo "OpenSim AI Bridge: maintenance activated; refusing to connect."
  exit 0
fi

exec /usr/bin/dotnet "$INSTALL_DIR/OpenSimAiBridge.Bot.dll" "$CONFIG_FILE"
