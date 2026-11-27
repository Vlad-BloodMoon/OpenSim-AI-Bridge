#!/usr/bin/env bash
set -Eeuo pipefail

# Install only the PDF indexer and its dedicated timer. Does not restart bots,
# OpenSimulator, the Web controller, or alter existing private config.
WORK="${1:?Usage: sudo bash scripts/install-files-pdfs.sh <EXTRACTED_ARTIFACT_DIR>}"
BASE="${OSAI_INSTALL_DIR:-/home/louna49400/OpenSim-AI-Bridge}"
OWNER="${OSAI_BOT_USER:-louna49400}"
[[ $EUID -eq 0 ]] || { echo "Use sudo"; exit 2; }
[[ -f "$WORK/knowledge/knowledge_cli.py" &&
   -f "$WORK/deploy/systemd/opensim-ai-bridge-files-pdfs.service.example" &&
   -f "$WORK/deploy/systemd/opensim-ai-bridge-files-pdfs.timer.example" &&
   -f "$BASE/appsettings.json" &&
   -d /var/www/BloodMoon/files ]] || { echo "Missing checked source or installation"; exit 2; }
command -v pdftotext >/dev/null || { echo "Install poppler-utils first"; exit 2; }
id "$OWNER" >/dev/null
[[ -d "$BASE/data" && ! -L "$BASE/data" ]] || { echo "Missing safe data directory"; exit 2; }
[[ -d "$BASE/knowledge" && ! -L "$BASE/knowledge" ]] || { echo "Missing safe knowledge directory"; exit 2; }
[[ ! -L /var/www/BloodMoon/files ]] || { echo "Unsafe source symlink"; exit 2; }
# Backup previously installed script so existing TXT jobs can be restored.
if [[ -f "$BASE/knowledge/knowledge_cli.py" ]]; then
  cp -a -- "$BASE/knowledge/knowledge_cli.py" "$BASE/knowledge/knowledge_cli.py.bak-$(date +%Y%m%d-%H%M%S)"
fi
install -o "$OWNER" -g "$OWNER" -m 0750 "$WORK/knowledge/knowledge_cli.py" "$BASE/knowledge/knowledge_cli.py"
python3 -m py_compile "$BASE/knowledge/knowledge_cli.py"
sed -e "s|@BOT_USER@|$OWNER|g" -e "s|@INSTALL_DIR@|$BASE|g" \
  "$WORK/deploy/systemd/opensim-ai-bridge-files-pdfs.service.example" \
  > /etc/systemd/system/opensim-ai-bridge-files-pdfs.service
install -o root -g root -m 0644 \
  "$WORK/deploy/systemd/opensim-ai-bridge-files-pdfs.timer.example" \
  /etc/systemd/system/opensim-ai-bridge-files-pdfs.timer
systemctl daemon-reload
systemctl enable --now opensim-ai-bridge-files-pdfs.timer
systemctl start opensim-ai-bridge-files-pdfs.service
echo "PDF indexing timer ready. Existing avatar services were not restarted."
