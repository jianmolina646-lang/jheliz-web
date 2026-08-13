#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: > /etc/jheliz-digital-backup.env
for variable in \
    POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB \
    MEGA_EMAIL MEGA_PASSWORD MEGA_FOLDER BACKUP_DAILY_KEEP_DAYS \
    BACKUP_MONTHLY_KEEP_MONTHS BACKUP_NAME_PREFIX BACKUP_CRON_SCHEDULE \
    BACKUP_ARCHIVE_PASSWORD
do
    printf 'export %s=%q\n' "$variable" "${!variable:-}" \
        >> /etc/jheliz-digital-backup.env
done
chmod 600 /etc/jheliz-digital-backup.env

cron_schedule="${BACKUP_CRON_SCHEDULE:-20 4 * * *}"
{
    printf 'CRON_TZ=America/Lima\n'
    printf "%s /bin/bash -c '. /etc/jheliz-digital-backup.env; exec /usr/local/bin/jheliz-digital-backup' >> /proc/1/fd/1 2>> /proc/1/fd/2\n" "$cron_schedule"
    printf "10 5 * * 0 /bin/bash -c '. /etc/jheliz-digital-backup.env; exec /usr/local/bin/jheliz-digital-verify-restore' >> /proc/1/fd/1 2>> /proc/1/fd/2\n"
} > /etc/cron.d/jheliz-digital-backup
chmod 0644 /etc/cron.d/jheliz-digital-backup
crontab /etc/cron.d/jheliz-digital-backup

if (( $# > 0 )); then
    exec "$@"
fi
exec cron -f
