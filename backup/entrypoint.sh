#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: > /etc/jheliz-backup.env
for variable in \
    POSTGRES_USER POSTGRES_PASSWORD POSTGRES_PASSWORD_FILE POSTGRES_DB \
    MEGA_EMAIL MEGA_PASSWORD MEGA_FOLDER BACKUP_KEEP_DAYS \
    BACKUP_ARCHIVE_PASSWORD BACKUP_ARCHIVE_PASSWORD_FILE
do
    printf 'export %s=%q\n' "$variable" "${!variable:-}" \
        >> /etc/jheliz-backup.env
done
chmod 600 /etc/jheliz-backup.env

if (( $# > 0 )); then
    exec "$@"
fi
exec cron -f
