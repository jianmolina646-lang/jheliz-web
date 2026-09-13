#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

LOG_DIR=/var/log/jheliz-security
LOG_FILE="$LOG_DIR/restore-$(date -u +%Y%m%d).log"
COMPLETE_STATUS=/var/lib/jheliz-backup-v2/success.json
status=0

install -d -o root -g root -m 700 "$LOG_DIR"
: > "$LOG_FILE"
chmod 600 "$LOG_FILE"

for container in \
  jheliz-digital-backup-1 \
  jheliz-web-backup-1 \
  jheliz-backup-1 \
  mail-control-backup-1 \
  mail-control-enterprise-enterprise-backup-1
do
  docker inspect "$container" >/dev/null 2>&1 || continue
  verifier="$(docker exec "$container" sh -c \
    'find /usr/local/bin -maxdepth 1 -type f -iname "*verify*restore*" | head -1')"
  if [[ -z "$verifier" ]]; then
    echo "ERROR $container: no restore verifier found" >> "$LOG_FILE"
    status=1
    continue
  fi
  echo "===== $container : $verifier =====" >> "$LOG_FILE"
  docker exec "$container" "$verifier" >> "$LOG_FILE" 2>&1 || status=1
done

if ! /usr/local/sbin/jheliz-backup-v2 --health >> "$LOG_FILE" 2>&1; then
  echo "ERROR: complete-v2 health check failed" >> "$LOG_FILE"
  status=1
fi

if [[ ! -s "$COMPLETE_STATUS" ]]; then
  echo "ERROR: complete-v2 success state missing" >> "$LOG_FILE"
  status=1
fi

if (( status != 0 )); then
  /usr/local/sbin/jheliz-security-notify \
    "🔴 Auditoría mensual de restauración FALLIDA. Informe: $LOG_FILE" || true
else
  /usr/local/sbin/jheliz-security-notify \
    "✅ Restauración mensual aislada completada correctamente en todos los sistemas." || true
fi

exit "$status"
