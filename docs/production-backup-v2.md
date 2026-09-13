# JhelizTV complete backup, installed 2026-09-06

Authoritative complete backup: `/usr/local/sbin/jheliz-backup-v2` on the VPS.
Source: `backup/production-complete.py`. This host service is independent of web
container replacement. Its cron file is `/etc/cron.d/jheliz-backup-v2`.

Runs daily at 08:20 UTC (03:20 Peru); hourly freshness and Google Drive capacity checks.
Success requires download, decryption, file checksums and isolated PostgreSQL
restoration from **each** destination. Production is never a restore target.
Table counts come from the same exported snapshot as pg_dump. Each restore
container has no network, a 512 MB limit, and temporary database storage.

Sources: running web DATABASE_URL, `/opt/jheliz-deploy/media`, `private_media`,
`.env`, `secrets`, compose files and web runtime environment (encrypted only).
The script rejects missing directories and mount drift. Database credentials
are never logged. All files are encrypted with the existing age identity.

Destinations:
- R2: `jheliztv.xyz/complete-v2/daily/` in the configured bucket.
- Google Drive: `ProductionBackups/jheliztv.xyz/complete-v2/daily/`.

Retention is independent per destination: R2 and Drive each keep 14 daily,
8 Sunday and 12 first-of-month copies.
Two local archives are kept. The scoped inventory tracks each destination
separately and checkpoints each deletion. Pruning runs only after the new daily
copy has been restored successfully from both destinations. Newly expired R2
copies are deleted, not moved to another space-consuming tier. Objects already
in the old `expired/` tier retain their original 30-day grace period.
Legacy copies and other projects are untouched. Archives remain complete,
compressed and encrypted, not incremental chains. The exact Git revision is
included along with the configuration. No cache, Docker image or backup
directories are selected as sources.

Status: `/var/lib/jheliz-backup-v2/success.json`. Logs:
`/var/log/production-backups/jheliz-backup-v2.log`, rotated weekly (8 files).
Failure notifications use the existing private server Telegram configuration.
Drive capacity warnings trigger at 85%, at most once per UTC day. No verified
copy for 30 hours triggers failure. Existing PITR jobs remain separate.

Initial actual restore: archive `jheliz-complete-20260906-220017.tar.gz.age`,
81 tables and 55 checksummed files, restored successfully from both remotes.
Recovery identity copied outside VPS to the owner's Windows profile with a
restricted ACL in `Documents/JhelizTV-Recovery/`.
Never commit this identity or move it into the backup bucket.

To recover: download a complete `.tar.gz.age` archive, decrypt with `age -d -i`
using the private identity, extract it into a private staging directory and
verify every manifest checksum. Restore `database.dump` into a fresh PostgreSQL
16 instance; compare all table counts in `manifest.json`, then reconnect the
application and restore media/configuration. Production replacement needs its
own maintenance procedure and rollback backup.

Google Drive and R2 are independent recovery destinations. The Drive remote
must use a dedicated Google OAuth client before rclone's shared client retires.
