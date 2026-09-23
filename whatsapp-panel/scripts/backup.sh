#!/usr/bin/env sh
set -eu
backup_dir="${BACKUP_DIR:-/backups}"
mkdir -p "$backup_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
pg_dump "$DATABASE_URL" --format=custom --file="$backup_dir/jheliz-whatsapp-$stamp.dump"
find "$backup_dir" -type f -name 'jheliz-whatsapp-*.dump' -mtime +14 -delete
