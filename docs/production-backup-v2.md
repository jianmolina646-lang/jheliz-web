# JhelizTV complete backup, installed 2026-09-06

Authoritative complete backup: `/usr/local/sbin/jheliz-backup-v2` on the VPS.
Source: `backup/production-complete.py`. This host service is independent of web
container replacement. Its cron file is `/etc/cron.d/jheliz-backup-v2`.

Runs daily at 08:20 UTC (03:20 Peru); hourly freshness and MEGA capacity checks.
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
- MEGA: `/JhelizControlBackups/CompleteV2/daily/`.

Retention: 14 daily, 4 Sunday copies and 6 first-of-month copies in the new
namespace, managed through `/var/lib/jheliz-backup-v2/inventory.json`. Expired
MEGA objects are removed only after moving their R2 copies into `expired/`.
R2 expired copies are retained for 30 additional days before deletion through
the same scoped inventory. Three local archives
are kept. Legacy copies and other projects are untouched.

Status: `/var/lib/jheliz-backup-v2/success.json`. Logs:
`/var/log/production-backups/jheliz-backup-v2.log`, rotated weekly (8 files).
Failure notifications use the existing private server Telegram configuration.
MEGA capacity warnings trigger at 85%, at most once per UTC day. No verified
copy for 30 hours triggers failure. Existing PITR jobs remain separate.

Initial actual restore: archive `jheliz-complete-20260906-220017.tar.gz.age`,
81 tables and 55 checksummed files, restored successfully from MEGA and R2.
Recovery identity copied outside VPS to the owner's laptop, mode 0600,
`/home/jheliz/.config/jheliz-backup-recovery/age-identity-20260906.txt`.
Never commit this identity or move it into the backup bucket.

To recover: download a complete `.tar.gz.age` archive, decrypt with `age -d -i`
using the private identity, extract it into a private staging directory and
verify every manifest checksum. Restore `database.dump` into a fresh PostgreSQL
16 instance; compare all table counts in `manifest.json`, then reconnect the
application and restore media/configuration. Production replacement needs its
own maintenance procedure and rollback backup.

Open capacity issue: shared MEGA storage was 92% full after validation. This
change does not delete other applications' copies or purchase additional quota.
