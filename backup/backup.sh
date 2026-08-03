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

notify_telegram() {
    local message="$1"
    local token
    token="$(read_secret "${BACKUP_TELEGRAM_BOT_TOKEN:-}" "${BACKUP_TELEGRAM_BOT_TOKEN_FILE:-}")"
    local chat_id="${BACKUP_TELEGRAM_CHAT_ID:-}"
    if [[ -z "$token" || -z "$chat_id" ]]; then
        return 0
    fi
    curl --fail --silent --show-error --max-time 20 \
        --data-urlencode "chat_id=$chat_id" \
        --data-urlencode "text=$message" \
        --data-urlencode "parse_mode=HTML" \
        "https://api.telegram.org/bot${token}/sendMessage" \
        >/dev/null 2>&1 || true
}

: "${POSTGRES_USER:?POSTGRES_USER no configurado}"
: "${POSTGRES_DB:?POSTGRES_DB no configurado}"

DB_PASSWORD="$(read_secret "${POSTGRES_PASSWORD:-}" "${POSTGRES_PASSWORD_FILE:-}")"
ARCHIVE_PASSWORD="$(read_secret "${BACKUP_ARCHIVE_PASSWORD:-}" "${BACKUP_ARCHIVE_PASSWORD_FILE:-}")"
: "${DB_PASSWORD:?Contraseña PostgreSQL no configurada}"
: "${ARCHIVE_PASSWORD:?BACKUP_ARCHIVE_PASSWORD no configurada}"
export ARCHIVE_PASSWORD

MEGA_FOLDER="${MEGA_FOLDER:-/JhelizControlBackups}"
BACKUP_NAME_PREFIX="${BACKUP_NAME_PREFIX:-jheliz-control}"
if [[ ! "$BACKUP_NAME_PREFIX" =~ ^[a-z0-9-]+$ ]]; then
    echo "BACKUP_NAME_PREFIX inválido" >&2
    exit 1
fi
DAILY_FOLDER="${MEGA_FOLDER%/}/Daily"
MONTHLY_FOLDER="${MEGA_FOLDER%/}/Monthly"
KEEP_DAYS="${BACKUP_DAILY_KEEP_DAYS:-30}"
KEEP_MONTHS="${BACKUP_MONTHLY_KEEP_MONTHS:-12}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
WORK_DIR="$(mktemp -d)"
PLAIN_ARCHIVE="$WORK_DIR/${BACKUP_NAME_PREFIX}-${TIMESTAMP}.tar.gz"
FINAL_ARCHIVE="/backups/${BACKUP_NAME_PREFIX}-${TIMESTAMP}.tar.gz.enc"

on_exit() {
    local status=$?
    rm -rf "$WORK_DIR"
    if (( status != 0 )); then
        notify_telegram "🔴 <b>BACKUP FALLIDO</b>

Sistema: <b>${BACKUP_NAME_PREFIX}</b>
Revisa los logs del VPS."
    fi
    return "$status"
}
trap on_exit EXIT

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
if [[ -d /source/private_media ]]; then
    cp -a /source/private_media "$WORK_DIR/payload/private_media"
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
    MONTHLY_NAME="${BACKUP_NAME_PREFIX}-monthly-$(date -u +%Y%m).tar.gz.enc"
    cp "$FINAL_ARCHIVE" "/backups/$MONTHLY_NAME"
    mega-put "/backups/$MONTHLY_NAME" "$MONTHLY_FOLDER/"
    mega-ls "$MONTHLY_FOLDER/$MONTHLY_NAME" >/dev/null
    rm -f "/backups/$MONTHLY_NAME"
fi

CUTOFF="$(date -u -d "-${KEEP_DAYS} days" +%Y%m%d%H%M%S)"
while IFS= read -r remote_file; do
    filename="$(basename "$remote_file")"
    if [[ "$filename" =~ ^${BACKUP_NAME_PREFIX}-([0-9]{8})-([0-9]{6})\.tar\.gz\.enc$ ]]; then
        file_timestamp="${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
        if [[ "$file_timestamp" < "$CUTOFF" ]]; then
            mega-rm "$remote_file"
        fi
    fi
done < <(
    mega-find "$DAILY_FOLDER" \
        --type=f \
        --pattern="${BACKUP_NAME_PREFIX}-*.tar.gz.enc"
)

MONTH_CUTOFF="$(date -u -d "-${KEEP_MONTHS} months" +%Y%m)"
while IFS= read -r remote_file; do
    filename="$(basename "$remote_file")"
    if [[ "$filename" =~ ^${BACKUP_NAME_PREFIX}-monthly-([0-9]{6})\.tar\.gz\.enc$ ]]; then
        if [[ "${BASH_REMATCH[1]}" < "$MONTH_CUTOFF" ]]; then
            mega-rm "$remote_file"
        fi
    fi
done < <(
    mega-find "$MONTHLY_FOLDER" \
        --type=f \
        --pattern="${BACKUP_NAME_PREFIX}-monthly-*.tar.gz.enc"
)

find /backups -type f -name "${BACKUP_NAME_PREFIX}-*.tar.gz.enc" -mtime +1 -delete
if [[ "${BACKUP_NOTIFY_SUCCESS:-true}" == "true" ]]; then
    notify_telegram "✅ <b>BACKUP COMPLETADO</b>

Sistema: <b>${BACKUP_NAME_PREFIX}</b>
Archivo: <code>$(basename "$FINAL_ARCHIVE")</code>
Retención: 30 días + 12 meses."
fi
echo "Backup cifrado completado: $(basename "$FINAL_ARCHIVE")"
