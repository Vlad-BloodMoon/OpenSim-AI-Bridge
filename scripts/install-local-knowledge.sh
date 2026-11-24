#!/usr/bin/env bash
set -Eeuo pipefail
# Run only on robust-vm after downloading a trusted build artifact.
WORK="${1:?Usage: sudo bash scripts/install-local-knowledge.sh <EXTRACTED_ARTIFACT_DIR>}"
BASE="${OSAI_INSTALL_DIR:-/home/louna49400/OpenSim-AI-Bridge}"
OWNER="${OSAI_BOT_USER:-louna49400}"
ROOT=/var/www/BloodMoon/AI_Knowledge
[[ $EUID -eq 0 ]] || { echo "Run with sudo" >&2; exit 2; }
[[ -f "$WORK/knowledge/knowledge_cli.py" && -f "$BASE/appsettings.json" ]] || {
  echo "Missing build artifact or installation" >&2; exit 2;
}
id "$OWNER" >/dev/null
# The web server's www-data account must not be able to traverse the
# directory. 0700 is the actual privacy boundary; .htaccess is defense in depth.
if [[ -L "$ROOT" ]]; then echo "Unsafe symlink at $ROOT" >&2; exit 2; fi
install -d -o "$OWNER" -g "$OWNER" -m 0700 "$ROOT"
for category in marketplace opensim grid_bloodmoon roleplay_bloodmoon; do
  if [[ -L "$ROOT/$category" ]]; then echo "Unsafe category symlink" >&2; exit 2; fi
  install -d -o "$OWNER" -g "$OWNER" -m 0700 "$ROOT/$category"
done
printf '%s\n' 'Require all denied' > "$ROOT/.htaccess"
chown "$OWNER:$OWNER" "$ROOT/.htaccess"
chmod 0600 "$ROOT/.htaccess"
install -d -o "$OWNER" -g "$OWNER" -m 0750 "$BASE/knowledge"
install -o "$OWNER" -g "$OWNER" -m 0750 "$WORK/knowledge/knowledge_cli.py" "$BASE/knowledge/knowledge_cli.py"
sed -e "s|@BOT_USER@|$OWNER|g" -e "s|@INSTALL_DIR@|$BASE|g" \
 "$WORK/deploy/systemd/opensim-ai-bridge-local-knowledge.service.example" \
 > /etc/systemd/system/opensim-ai-bridge-local-knowledge.service
install -o root -g root -m 0644 \
 "$WORK/deploy/systemd/opensim-ai-bridge-local-knowledge.timer.example" \
 /etc/systemd/system/opensim-ai-bridge-local-knowledge.timer
systemctl daemon-reload
systemctl enable --now opensim-ai-bridge-local-knowledge.timer
systemctl start opensim-ai-bridge-local-knowledge.service
echo "TXT folders ready. Local knowledge is refreshed every 5 minutes."
