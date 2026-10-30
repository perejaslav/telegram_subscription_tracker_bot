#!/usr/bin/env bash
# Prepare a local encrypted snapshot; never sends data over the network.
set -euo pipefail
umask 077
if ! command -v age >/dev/null 2>&1; then
  echo 'age must be installed before encrypted backups are enabled' >&2
  exit 1
fi
: "${BACKUP_AGE_RECIPIENT:?Set the age public recipient key first}"
: "${BOT_BACKUP_SOURCE:?Set the path of an integrity-checked SQLite backup}"
: "${BOT_ENCRYPTED_BACKUP_DIR:?Set a private local output directory}"
test -s "$BOT_BACKUP_SOURCE"
mkdir -p "$BOT_ENCRYPTED_BACKUP_DIR"
chmod 700 "$BOT_ENCRYPTED_BACKUP_DIR"
target="$BOT_ENCRYPTED_BACKUP_DIR/$(basename "$BOT_BACKUP_SOURCE").age"
tmp="${target}.pending"
trap 'rm -f "$tmp"' EXIT
age -r "$BACKUP_AGE_RECIPIENT" -o "$tmp" "$BOT_BACKUP_SOURCE"
test -s "$tmp"
mv "$tmp" "$target"
echo 'Encrypted backup prepared locally; no upload was performed.'
