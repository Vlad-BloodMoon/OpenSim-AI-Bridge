#!/usr/bin/env bash
set -Eeuo pipefail

# Create the private PHP admin credential config outside the web document root.
# Run interactively from SSH. Do not send the password as a shell argument.
if ! command -v php >/dev/null; then
  echo "PHP CLI is required." >&2
  exit 2
fi
if [[ ! -t 0 ]]; then
  echo "Run interactively from a terminal." >&2
  exit 2
fi
read -r -s -p "Nouveau mot de passe Web administrateur : " password
echo
read -r -s -p "Confirmer le mot de passe Web : " second
echo
if [[ "$password" != "$second" || ${#password} -lt 14 ]]; then
  echo "Passwords differ or are shorter than 14 characters." >&2
  exit 2
fi
unset second
hash="$(printf '%s' "$password" | php -r '$value = stream_get_contents(STDIN); echo password_hash($value, PASSWORD_DEFAULT);')"
unset password
if [[ -z "$hash" ]]; then
  echo "Hashing failed." >&2
  exit 2
fi
# The hash is not the original password; only www-data should be able to read it.
sudo install -d -o root -g www-data -m 0750 /etc/opensim-ai-bridge
printf "<?php\nreturn ['password_hash' => '%s'];\n" "$hash" |
  sudo install -o root -g www-data -m 0640 /dev/stdin /etc/opensim-ai-bridge/web-admin.php
unset hash
echo "Web admin config created in /etc/opensim-ai-bridge/web-admin.php"
