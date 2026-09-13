#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

MODE="${1:-}"
[[ "$MODE" =~ ^(base|wal|health)$ ]] || { echo "usage: $0 {base|wal|health}" >&2; exit 2; }

LOCK=/run/lock/jheliztv-pitr.lock
STATE=/var/lib/jheliztv-pitr
IDENTITY=/root/.config/production-backups/age/identity.txt
DRIVE_CONFIG=/root/.config/production-backups/drive/rclone.conf
DB_CONTAINER=jheliz-db-1
DB_NAME=jheliz_control
DB_USER=jheliz
WAL_DIR=/var/lib/docker/volumes/jheliz_postgres_data/_data/wal_archive
R2_PREFIX=jheliztv.xyz/pitr
DRIVE_PREFIX=mailcontrol_drive:ProductionBackups/jheliztv.xyz/pitr

exec 9>"$LOCK"
flock -n 9 || { echo "PITR already running"; exit 0; }
install -d -o root -g root -m 700 "$STATE"

set -a
# shellcheck disable=SC1091
. /root/.config/mail-control-backups/r2.env
set +a
export RCLONE_CONFIG="$DRIVE_CONFIG"
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ENDPOINT="$R2_ENDPOINT"
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
R2_ROOT="r2:${R2_BUCKET}/${R2_PREFIX}"
RECIPIENT="$(age-keygen -y "$IDENTITY")"

notify_failure() {
  # shellcheck disable=SC1091
  . /usr/local/lib/production-backup-notify.sh
  backup_notify "🔴 JhelizTV PITR $MODE falló. Revisa /var/log/production-backups/jheliztv-pitr.log."
}

WORK="$(mktemp -d)"
on_exit() {
  local status=$?
  rm -rf "$WORK"
  (( status == 0 )) || notify_failure || true
  return "$status"
}
trap on_exit EXIT

upload_verify() {
  local source="$1" destination="$2" label="$3"
  local downloaded="$WORK/downloaded-$label"
  rclone copyto "$source" "$destination" --retries 5
  rclone copyto "$destination" "$downloaded" --retries 5
  cmp -s "$source" "$downloaded"
}

run_base() {
  local stamp plain encrypted name restored
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  plain="$WORK/jheliztv-base-$stamp.tar.gz"
  encrypted="$plain.age"
  name="$(basename "$encrypted")"
  restored="$WORK/restored.tar.gz"

  docker exec -u postgres "$DB_CONTAINER" pg_basebackup \
    -U "$DB_USER" -D - -Ft -z -X fetch --checkpoint=fast > "$plain"
  tar -tzf "$plain" > "$WORK/contents"
  grep -qx 'PG_VERSION' "$WORK/contents"
  grep -qx 'backup_label' "$WORK/contents"
  grep -q '^pg_wal/' "$WORK/contents"
  age -r "$RECIPIENT" -o "$encrypted" "$plain"

  upload_verify "$encrypted" "$R2_ROOT/basebackups/$name" r2-base
  upload_verify "$encrypted" "$DRIVE_PREFIX/basebackups/$name" drive-base
  age -d -i "$IDENTITY" -o "$restored" "$WORK/downloaded-drive-base"
  cmp -s "$plain" "$restored"
  date -u +%s > "$STATE/last-base-success"
  echo "PITR_BASE_OK name=$name bytes=$(stat -c %s "$encrypted") r2=OK drive=OK"
}

run_wal() {
  local wal name compressed encrypted restored processed=0
  install -d -o 70 -g 70 -m 700 "$WAL_DIR"
  while IFS= read -r wal; do
    [[ -s "$wal" ]] || continue
    name="$(basename "$wal")"
    [[ "$name" =~ ^[0-9A-F]{24}$ ]] || continue
    compressed="$WORK/$name.gz"
    encrypted="$compressed.age"
    restored="$WORK/restored-$name.gz"
    gzip -9 -c "$wal" > "$compressed"
    age -r "$RECIPIENT" -o "$encrypted" "$compressed"
    upload_verify "$encrypted" "$R2_ROOT/wal/$name.gz.age" r2-wal
    upload_verify "$encrypted" "$DRIVE_PREFIX/wal/$name.gz.age" drive-wal
    age -d -i "$IDENTITY" -o "$restored" "$WORK/downloaded-drive-wal"
    gzip -t "$restored"
    cmp -s "$wal" <(gzip -dc "$restored")
    rm -f -- "$wal"
    processed=$((processed + 1))
  done < <(find "$WAL_DIR" -maxdepth 1 -type f -printf '%p\n' | sort)
  date -u +%s > "$STATE/last-wal-success"
  echo "PITR_WAL_OK processed=$processed r2=OK drive=OK"
}

run_health() {
  local now base wal
  now="$(date -u +%s)"
  [[ -s "$STATE/last-base-success" && -s "$STATE/last-wal-success" ]]
  base="$(cat "$STATE/last-base-success")"
  wal="$(cat "$STATE/last-wal-success")"
  (( now - base < 8 * 86400 ))
  (( now - wal < 35 * 60 ))
  echo "PITR_HEALTH_OK base_age_hours=$(( (now-base)/3600 )) wal_age_minutes=$(( (now-wal)/60 ))"
}

case "$MODE" in
  base) run_base ;;
  wal) run_wal ;;
  health) run_health ;;
esac
