#!/usr/bin/env sh
set -eu
test "$#" -eq 1 || { echo "Uso: restore.sh /ruta/backup.dump"; exit 2; }
test -f "$1" || { echo "Backup no encontrado"; exit 2; }
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" "$1"
