#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${POSTGRES_USER:?POSTGRES_USER no configurado}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD no configurada}"
: "${POSTGRES_DB:?POSTGRES_DB no configurado}"
: "${BACKUP_ARCHIVE_PASSWORD:?BACKUP_ARCHIVE_PASSWORD no configurada}"

mega_folder="${MEGA_FOLDER:-/JhelizDigitalBackups}"
prefix="${BACKUP_NAME_PREFIX:-jheliz-digital}"
keep_days="${BACKUP_DAILY_KEEP_DAYS:-30}"
keep_months="${BACKUP_MONTHLY_KEEP_MONTHS:-12}"
daily_folder="${mega_folder%/}/Daily"
monthly_folder="${mega_folder%/}/Monthly"
timestamp="$(date -u +%Y%m%d-%H%M%S)"
work_dir="$(mktemp -d)"
plain_archive="$work_dir/${prefix}-${timestamp}.tar.gz"
final_archive="/backups/${prefix}-${timestamp}.tar.gz.enc"

cleanup() {
    local status=$?
    rm -rf "$work_dir"
    return "$status"
}
trap cleanup EXIT

mkdir -p "$work_dir/payload/config"
export PGPASSWORD="$POSTGRES_PASSWORD"
pg_dump \
    --host=db \
    --port=5432 \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --no-owner \
    --no-acl \
    --file="$work_dir/payload/database.dump"

if [[ -f /source/config/.env ]]; then
    cp -a /source/config/.env "$work_dir/payload/config/.env"
fi

{
    printf 'created_utc=%s\n' "$(date -u --iso-8601=seconds)"
    printf 'database=%s\n' "$POSTGRES_DB"
    printf 'includes=database,environment\n'
} > "$work_dir/payload/manifest.txt"

(
    cd "$work_dir/payload"
    find . -type f ! -name SHA256SUMS -print0 \
        | sort -z \
        | xargs -0 sha256sum > SHA256SUMS
)

tar -czf "$plain_archive" -C "$work_dir/payload" .
export BACKUP_ARCHIVE_PASSWORD
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
    -in "$plain_archive" \
    -out "$final_archive" \
    -pass env:BACKUP_ARCHIVE_PASSWORD

if ! mega-whoami >/dev/null 2>&1; then
    : "${MEGA_EMAIL:?MEGA_EMAIL no configurado}"
    : "${MEGA_PASSWORD:?MEGA_PASSWORD no configurada}"
    mega-login "$MEGA_EMAIL" "$MEGA_PASSWORD"
fi

mega-mkdir -p "$daily_folder" >/dev/null 2>&1 || true
mega-mkdir -p "$monthly_folder" >/dev/null 2>&1 || true
mega-put "$final_archive" "$daily_folder/"
mega-ls "$daily_folder/$(basename "$final_archive")" >/dev/null

if [[ "$(date -u +%d)" == "01" ]]; then
    monthly_name="${prefix}-monthly-$(date -u +%Y%m).tar.gz.enc"
    cp "$final_archive" "/backups/$monthly_name"
    mega-put "/backups/$monthly_name" "$monthly_folder/"
    mega-ls "$monthly_folder/$monthly_name" >/dev/null
    rm -f "/backups/$monthly_name"
fi

cutoff="$(date -u -d "-${keep_days} days" +%Y%m%d%H%M%S)"
while IFS= read -r remote_file; do
    filename="$(basename "$remote_file")"
    if [[ "$filename" =~ ^${prefix}-([0-9]{8})-([0-9]{6})\.tar\.gz\.enc$ ]]; then
        file_timestamp="${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
        if [[ "$file_timestamp" < "$cutoff" ]]; then
            mega-rm "$remote_file"
        fi
    fi
done < <(mega-find "$daily_folder" --type=f --pattern="${prefix}-*.tar.gz.enc")

month_cutoff="$(date -u -d "-${keep_months} months" +%Y%m)"
while IFS= read -r remote_file; do
    filename="$(basename "$remote_file")"
    if [[ "$filename" =~ ^${prefix}-monthly-([0-9]{6})\.tar\.gz\.enc$ ]]; then
        if [[ "${BASH_REMATCH[1]}" < "$month_cutoff" ]]; then
            mega-rm "$remote_file"
        fi
    fi
done < <(mega-find "$monthly_folder" --type=f --pattern="${prefix}-monthly-*.tar.gz.enc")

find /backups -type f -name "${prefix}-*.tar.gz.enc" -mtime +1 -delete
echo "Backup cifrado completado: $(basename "$final_archive")"
