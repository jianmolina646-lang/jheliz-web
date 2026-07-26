#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: > /etc/jheliz-backup.env
for variable in \
    POSTGRES_USER POSTGRES_PASSWORD POSTGRES_PASSWORD_FILE POSTGRES_DB \
    MEGA_EMAIL MEGA_PASSWORD MEGA_FOLDER BACKUP_DAILY_KEEP_DAYS \
    BACKUP_MONTHLY_KEEP_MONTHS \
    BACKUP_NAME_PREFIX BACKUP_CRON_SCHEDULE \
    BACKUP_TELEGRAM_BOT_TOKEN BACKUP_TELEGRAM_BOT_TOKEN_FILE \
    BACKUP_TELEGRAM_CHAT_ID BACKUP_NOTIFY_SUCCESS \
    BACKUP_ARCHIVE_PASSWORD BACKUP_ARCHIVE_PASSWORD_FILE
do
    printf 'export %s=%q\n' "$variable" "${!variable:-}" \
        >> /etc/jheliz-backup.env
done
chmod 600 /etc/jheliz-backup.env

CRON_SCHEDULE="${BACKUP_CRON_SCHEDULE:-20 3 * * *}"
{
    printf 'CRON_TZ=America/Lima\n'
    printf '%s root /bin/bash -c '"'"'. /etc/jheliz-backup.env; exec /usr/local/bin/jheliz-backup'"'"' >> /proc/1/fd/1 2>> /proc/1/fd/2\n' "$CRON_SCHEDULE"
} > /etc/cron.d/jheliz-backup
chmod 0644 /etc/cron.d/jheliz-backup
crontab /etc/cron.d/jheliz-backup

if (( $# > 0 )); then
    exec "$@"
fi
exec cron -f
