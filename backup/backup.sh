#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

read_secret() {
    local value="${1:-}"
    local file="${2:-}"
    if [[ -n "$file" && -s "$file" ]]; then
        tr -d '\r\n' < "$file"
    else
        printf '%s' "$value"
    fi
}

: "${POSTGRES_USER:?POSTGRES_USER no configurado}"
: "${POSTGRES_DB:?POSTGRES_DB no configurado}"

DB_PASSWORD="$(read_secret "${POSTGRES_PASSWORD:-}" "${POSTGRES_PASSWORD_FILE:-}")"
ARCHIVE_PASSWORD="$(read_secret "${BACKUP_ARCHIVE_PASSWORD:-}" "${BACKUP_ARCHIVE_PASSWORD_FILE:-}")"
: "${DB_PASSWORD:?Contraseña PostgreSQL no configurada}"
: "${ARCHIVE_PASSWORD:?BACKUP_ARCHIVE_PASSWORD no configurada}"
export ARCHIVE_PASSWORD

MEGA_FOLDER="${MEGA_FOLDER:-/JhelizControlBackups}"
DAILY_FOLDER="${MEGA_FOLDER%/}/Daily"
MONTHLY_FOLDER="${MEGA_FOLDER%/}/Monthly"
KEEP_DAYS="${BACKUP_DAILY_KEEP_DAYS:-30}"
KEEP_MONTHS="${BACKUP_MONTHLY_KEEP_MONTHS:-12}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
WORK_DIR="$(mktemp -d)"
PLAIN_ARCHIVE="$WORK_DIR/jheliz-control-${TIMESTAMP}.tar.gz"
FINAL_ARCHIVE="/backups/jheliz-control-${TIMESTAMP}.tar.gz.enc"

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

mkdir -p "$WORK_DIR/payload/config"
export PGPASSWORD="$DB_PASSWORD"

pg_dump \
    --host=db \
    --port=5432 \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --no-owner \
    --no-acl \
    --file="$WORK_DIR/payload/database.dump"

if [[ -d /source/media ]]; then
    cp -a /source/media "$WORK_DIR/payload/media"
fi
if [[ -f /source/config/.env ]]; then
    cp -a /source/config/.env "$WORK_DIR/payload/config/.env"
fi
if [[ -d /source/config/secrets ]]; then
    cp -a /source/config/secrets "$WORK_DIR/payload/config/secrets"
fi

{
    printf 'created_utc=%s\n' "$(date -u --iso-8601=seconds)"
    printf 'database=%s\n' "$POSTGRES_DB"
    printf 'includes=database,media,environment,secrets\n'
} > "$WORK_DIR/payload/manifest.txt"

(
    cd "$WORK_DIR/payload"
    find . -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

tar -czf "$PLAIN_ARCHIVE" -C "$WORK_DIR/payload" .
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
    -in "$PLAIN_ARCHIVE" \
    -out "$FINAL_ARCHIVE" \
    -pass env:ARCHIVE_PASSWORD

if ! mega-whoami >/dev/null 2>&1; then
    : "${MEGA_EMAIL:?MEGA_EMAIL no configurado y no existe una sesión MEGA}"
    : "${MEGA_PASSWORD:?MEGA_PASSWORD no configurado y no existe una sesión MEGA}"
    mega-login "$MEGA_EMAIL" "$MEGA_PASSWORD"
fi

mega-mkdir -p "$DAILY_FOLDER" >/dev/null 2>&1 || true
mega-mkdir -p "$MONTHLY_FOLDER" >/dev/null 2>&1 || true
mega-put "$FINAL_ARCHIVE" "$DAILY_FOLDER/"
mega-ls "$DAILY_FOLDER/$(basename "$FINAL_ARCHIVE")" >/dev/null

if [[ "$(date -u +%d)" == "01" ]]; then
    MONTHLY_NAME="jheliz-control-monthly-$(date -u +%Y%m).tar.gz.enc"
    cp "$FINAL_ARCHIVE" "/backups/$MONTHLY_NAME"
    mega-put "/backups/$MONTHLY_NAME" "$MONTHLY_FOLDER/"
    mega-ls "$MONTHLY_FOLDER/$MONTHLY_NAME" >/dev/null
    rm -f "/backups/$MONTHLY_NAME"
fi

CUTOFF="$(date -u -d "-${KEEP_DAYS} days" +%Y%m%d%H%M%S)"
while IFS= read -r remote_file; do
    filename="$(basename "$remote_file")"
    if [[ "$filename" =~ ^jheliz-control-([0-9]{8})-([0-9]{6})\.tar\.gz\.enc$ ]]; then
        file_timestamp="${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
        if [[ "$file_timestamp" < "$CUTOFF" ]]; then
            mega-rm "$remote_file"
        fi
    fi
done < <(
    mega-find "$DAILY_FOLDER" \
        --type=f \
        --pattern="jheliz-control-*.tar.gz.enc"
)

MONTH_CUTOFF="$(date -u -d "-${KEEP_MONTHS} months" +%Y%m)"
while IFS= read -r remote_file; do
    filename="$(basename "$remote_file")"
    if [[ "$filename" =~ ^jheliz-control-monthly-([0-9]{6})\.tar\.gz\.enc$ ]]; then
        if [[ "${BASH_REMATCH[1]}" < "$MONTH_CUTOFF" ]]; then
            mega-rm "$remote_file"
        fi
    fi
done < <(
    mega-find "$MONTHLY_FOLDER" \
        --type=f \
        --pattern="jheliz-control-monthly-*.tar.gz.enc"
)

find /backups -type f -name "jheliz-control-*.tar.gz.enc" -mtime +1 -delete
echo "Backup cifrado completado: $(basename "$FINAL_ARCHIVE")"
