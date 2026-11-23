#!/usr/bin/env bash
set -Eeuo pipefail
# Local CLI only. Do not expose this shell script directly to the web server.
# First install the systemd service with restricted permissions.
INSTALL_DIR="${OSAI_INSTALL_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
LOCK_FILE="${OSAI_MAINTENANCE_FILE:-$INSTALL_DIR/maintenance.lock}"
SERVICE="${OSAI_SERVICE_NAME:-opensim-ai-bridge.service}"

usage() {
  echo "Usage: $0 {status|start|stop|restart|firestorm|resume}"
  echo "  firestorm: persistently lock out bot login, then stop service"
  echo "  resume: unlock bot login and start service (close Firestorm first)"
}
if [[ $# -ne 1 ]]; then usage; exit 2; fi
case "$1" in
  status)
    if [[ -e "$LOCK_FILE" ]]; then echo "Maintenance/Firestorm: ENABLED"; else echo "Maintenance/Firestorm: disabled"; fi
    systemctl status "$SERVICE" --no-pager || true
    ;;
  start)
    if [[ -e "$LOCK_FILE" ]]; then echo "Maintenance enabled. Use resume only after closing Firestorm." >&2; exit 3; fi
    sudo systemctl start "$SERVICE"
    ;;
  stop)
    sudo systemctl stop "$SERVICE"
    ;;
  restart)
    if [[ -e "$LOCK_FILE" ]]; then echo "Maintenance enabled. Restart refused." >&2; exit 3; fi
    sudo systemctl restart "$SERVICE"
    ;;
  firestorm)
    # Lock first, and never remove the lock merely because stopping fails.
    if [[ ! -e "$LOCK_FILE" ]]; then
      ( umask 077; printf '%s\n' "Firestorm maintenance requested at $(date -Is)" > "$LOCK_FILE" )
    fi
    sudo systemctl stop "$SERVICE"
    echo "Firestorm mode active. You may now connect the avatar via Firestorm."
    ;;
  resume)
    echo "WARNING: make sure Firestorm is fully disconnected from this avatar."
    read -r -p "Type RESUME to unlock and start: " answer
    if [[ "$answer" != "RESUME" ]]; then echo "Aborted."; exit 1; fi
    rm -f -- "$LOCK_FILE"
    sudo systemctl start "$SERVICE"
    ;;
  *)
    usage
    exit 2
    ;;
esac
