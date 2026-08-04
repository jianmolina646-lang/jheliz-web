#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${POSTGRES_USER:?POSTGRES_USER no configurado}"
: "${POSTGRES_DB:?POSTGRES_DB no configurado}"
: "${BACKUP_ARCHIVE_PASSWORD:?BACKUP_ARCHIVE_PASSWORD no configurada}"

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD no configurada}"
prefix="${BACKUP_NAME_PREFIX:-jheliz-control}"
archive="$(find /backups -maxdepth 1 -type f -name "${prefix}-*.tar.gz.enc" | sort | tail -n 1)"
: "${archive:?No existe un backup local para verificar}"

work_dir="$(mktemp -d)"
verify_db="${POSTGRES_DB}_verify_$(date +%s)"
cleanup() {
    dropdb --if-exists --host=db --username="$POSTGRES_USER" "$verify_db" \
        >/dev/null 2>&1 || true
    rm -rf "$work_dir"
}
trap cleanup EXIT

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "$archive" \
    -out "$work_dir/archive.tar.gz" \
    -pass env:BACKUP_ARCHIVE_PASSWORD
mkdir "$work_dir/payload"
tar -xzf "$work_dir/archive.tar.gz" -C "$work_dir/payload"
(
    cd "$work_dir/payload"
    sha256sum --check SHA256SUMS
)

createdb --host=db --username="$POSTGRES_USER" "$verify_db"
pg_restore --host=db --username="$POSTGRES_USER" --dbname="$verify_db" \
    --no-owner --no-acl "$work_dir/payload/database.dump"
table_count="$(psql --host=db --username="$POSTGRES_USER" --dbname="$verify_db" \
    -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema');")"
if [[ ! "$table_count" =~ ^[1-9][0-9]*$ ]]; then
    echo "La restauración no produjo tablas" >&2
    exit 1
fi

echo "Restauración verificada: $(basename "$archive") (${table_count} tablas)"
